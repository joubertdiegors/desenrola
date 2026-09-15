"""
A identidade do sistema no e-mail de recuperação de senha.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que volte a existir domínio escrito à mão.** A assinatura do
   e-mail trazia o endereço do site no código. O endereço agora é o
   mesmo de onde a pessoa pediu a senha -- em teste, `testserver`. O
   domínio de produção só aparece neste arquivo DENTRO das asserções
   que o proíbem: um teste que veta uma string precisa nomeá-la.
2. **Que alguém "resolva" isso com processador de contexto.** O corpo é
   renderizado por `render_to_string` SEM request: `site_config` não
   existe lá, e usá-lo deixaria o nome vazio em silêncio. A ponte é
   `extra_email_context`;
3. **Que renomear o site no Backoffice não mude o e-mail.** Era o caso
   até aqui: o nome estava escrito no template, em três lugares;
4. **Que pedir uma senha nova escreva no banco de configuração.**
"""

import re

import pytest
from django.core import mail
from django.urls import reverse

from apps.content.models import SiteSettings

pytestmark = pytest.mark.django_db

PEDIDO = reverse("accounts:password_reset")


def pedir(client, email):
    resposta = client.post(PEDIDO, {"email": email})
    assert resposta.status_code == 302
    return mail.outbox[-1]


# ===========================================================================
# 1. O endereço
# ===========================================================================


class TestEndereco:
    def test_nenhum_dominio_escrito_no_template(self):
        """
        A pergunta é sobre a FONTE, e não sobre o que saiu desta vez:
        um domínio de volta no template passaria despercebido em teste,
        onde o host é `testserver` de qualquer jeito.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        for nome in ("password_reset_email.txt", "password_reset_subject.txt"):
            fonte = (raiz / "templates" / "accounts" / nome).read_text(encoding="utf-8")
            assert "desenrola.be" not in fonte, nome
            assert re.search(r"https?://(?!\{)", fonte) is None, nome

    def test_o_endereco_sai_do_host_do_pedido(self, client, user):
        mensagem = pedir(client, user.email)

        assert "http://testserver" in mensagem.body
        assert "desenrola.be" not in mensagem.body

    def test_o_link_continua_abrindo(self, client, user):
        """Regressão: a mudança da assinatura não pode ter mexido no link."""
        mensagem = pedir(client, user.email)

        link = re.search(
            r"http://testserver(/pt/accounts/password-reset/[^/\s]+/[^/\s]+/)",
            mensagem.body,
        )
        assert link, mensagem.body
        assert client.get(link.group(1)).status_code == 302

    def test_a_assinatura_usa_o_mesmo_endereco_do_link(self, client, user):
        """
        Assinatura e link vêm da MESMA fonte. Duas fontes discordariam
        um dia -- e o rodapé de um e-mail apontando para outro lugar é
        exatamente o tipo de coisa que ninguém percebe.
        """
        mensagem = pedir(client, user.email)

        assert mensagem.body.count("http://testserver") >= 2


# ===========================================================================
# 2. O nome do site
# ===========================================================================


class TestNomeDoSite:
    def test_o_nome_vem_do_cms(self, client, user):
        registro = SiteSettings.load()
        registro.site_name = "Outro Nome"
        registro.save()

        mensagem = pedir(client, user.email)

        assert "Outro Nome" in mensagem.body
        assert "Outro Nome" in mensagem.subject
        assert "Desenrola" not in mensagem.body
        assert "Desenrola" not in mensagem.subject

    def test_sem_configuracao_usa_o_padrao_do_modelo(self, client, user):
        """
        Instalação nova, sem ninguém ter aberto a tela de Sistema: o
        nome é o padrão do modelo, e não uma string vazia.
        """
        assert not SiteSettings.objects.exists()

        mensagem = pedir(client, user.email)

        assert "Desenrola" in mensagem.subject
        assert ": criar nova senha" in mensagem.subject

    def test_o_nome_nao_chega_vazio(self, client, user):
        """
        O erro que um processador de contexto teria produzido aqui:
        `site_config` não existe num template renderizado sem request, e
        o nome sairia em branco, em silêncio.
        """
        mensagem = pedir(client, user.email)

        assert mensagem.subject.strip() != ": criar nova senha"
        assert " ·  · " not in mensagem.body
        assert "sua conta  (" not in mensagem.body

    def test_pedir_senha_nao_escreve_configuracao(self, client, user):
        """
        `globais()` LÊ sem criar. `SiteSettings.load()` criaria a linha
        -- e pedir uma senha nova não é motivo para escrever no banco de
        configuração.
        """
        assert not SiteSettings.objects.exists()

        pedir(client, user.email)

        assert not SiteSettings.objects.exists()


# ===========================================================================
# 3. O que o e-mail continua sendo
# ===========================================================================


class TestRegressaoDoEmail:
    def test_email_desconhecido_continua_nao_revelando_nada(self, client):
        resposta = client.post(PEDIDO, {"email": "ninguem@mail.com"})

        assert resposta.status_code == 302
        assert len(mail.outbox) == 0

    def test_a_saudacao_e_o_aviso_de_prazo_continuam(self, client, user):
        mensagem = pedir(client, user.email)

        assert "Olá, Claire." in mensagem.body
        assert "O link vale por 3 dias" in mensagem.body

    def test_vai_para_quem_pediu(self, client, user):
        mensagem = pedir(client, user.email)

        assert mensagem.to == [user.email]


# ===========================================================================
# 4. A versão fictícia
# ===========================================================================


class TestSemVersaoInventada:
    def test_o_perfil_nao_mostra_versao(self, auth_client):
        """
        "v1.0" não vinha de lugar nenhum -- não há versão do produto em
        `pyproject.toml`, em arquivo próprio nem em constante. Era texto
        da maquete. Sumiu, em vez de virar configuração para sustentar
        um número inventado.
        """
        corpo = auth_client.get(reverse("accounts:profile")).content.decode()

        assert "v1.0" not in corpo

    def test_o_nome_do_site_continua_no_rodape_do_perfil(self, auth_client):
        """Tirar a versão não podia levar o nome junto."""
        registro = SiteSettings.load()
        registro.site_name = "Outro Nome"
        registro.save()

        corpo = auth_client.get(reverse("accounts:profile")).content.decode()

        assert "Outro Nome" in corpo

    def test_nao_ha_versao_inventada_em_template_nenhum(self):
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        for caminho in (raiz / "templates").rglob("*.html"):
            assert "v1.0" not in caminho.read_text(encoding="utf-8"), caminho
