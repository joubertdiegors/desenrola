"""
O e-mail de recuperação de senha: as duas versões.

O QUE ESTA SUÍTE ACRESCENTA
---------------------------
`test_identidade_do_email.py` já cobre o endereço e o nome do site na
versão de TEXTO. Esta cuida da alternativa HTML, que é nova, e de três
coisas que valem para as duas.

O QUE ELA EXISTE PARA IMPEDIR
-----------------------------
1. **Que o HTML substitua o texto.** As duas versões vão juntas: quem lê
   em texto puro, em cliente antigo ou com HTML desligado recebe a mesma
   informação. O HTML é a apresentação, não o conteúdo;
2. **Que o e-mail minta sobre o prazo.** Ele promete três dias por
   escrito; `PASSWORD_RESET_TIMEOUT` é quem decide de verdade. Se alguém
   mudar o ajuste, o texto passaria a mentir -- e o teste compara os
   dois;
3. **Que o nome de alguém vire HTML.** A versão de texto usa `autoescape
   off`, e ali é inofensivo. No HTML seria injeção: o nome vem do
   cadastro da própria pessoa;
4. **Que o e-mail deixe de acompanhar a Aparência.** Cor e logomarca vêm
   de `SiteSettings`, não de valores escritos no template;
5. **Que entre coisa que cliente de e-mail não executa** -- script, folha
   de estilo externa, fonte remota.
"""

import re
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from freezegun import freeze_time

pytestmark = pytest.mark.django_db

PEDIR = reverse("accounts:password_reset")

GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@pytest.fixture(autouse=True)
def _media_isolada(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def pessoa(db):
    return get_user_model().objects.create_user(
        email="marina@exemplo.test", password="x" * 12, full_name="Marina Souza"
    )


def pedir(client, quem):
    mail.outbox = []
    client.post(PEDIR, {"email": quem.email})
    assert len(mail.outbox) == 1, "o e-mail não foi enviado"
    return mail.outbox[0]


def html_de(mensagem):
    """A alternativa HTML da mensagem."""
    for conteudo, tipo in mensagem.alternatives:
        if tipo == "text/html":
            return conteudo
    raise AssertionError("a mensagem não tem alternativa HTML")


def link_de(texto):
    """O endereço de confirmação que aparece no corpo."""
    achado = re.search(r"https?://[^\s\"'<>]*/password-reset/[^\s\"'<>]+", texto)
    assert achado, f"nenhum link de recuperação em:\n{texto[:600]}"
    return achado.group(0)


def com_logomarca(alt="Desenrola"):
    from apps.content.models import Asset, SiteSettings

    imagem = Asset.objects.create(
        kind=Asset.Kind.LOGO,
        file=SimpleUploadedFile("logo.gif", GIF, content_type="image/gif"),
        alt_text=alt,
    )
    config = SiteSettings.load()
    config.logo = imagem
    config.save()
    return imagem


# ===========================================================================
# 1. As duas versões vão juntas
# ===========================================================================


class TestAsDuasVersoes:
    def test_o_email_tem_texto_e_html(self, client, pessoa):
        msg = pedir(client, pessoa)

        assert msg.body.strip(), "a versão de texto não pode sumir"
        assert [tipo for _c, tipo in msg.alternatives] == ["text/html"]

    def test_as_duas_levam_ao_mesmo_lugar(self, client, pessoa):
        """
        Dois links diferentes seriam dois caminhos para manter em dia --
        e um deles acabaria errado.
        """
        msg = pedir(client, pessoa)

        assert link_de(msg.body) == link_de(html_de(msg))

    def test_a_versao_de_texto_continua_completa(self, client, pessoa):
        """Regressão: o HTML acrescenta, não substitui."""
        corpo = pedir(client, pessoa).body

        assert "Marina" in corpo
        assert "3 dias" in corpo
        assert "marina@exemplo.test" in corpo

    def test_o_assunto_nao_mudou(self, client, pessoa):
        assert pedir(client, pessoa).subject == "Desenrola: criar nova senha"


# ===========================================================================
# 2. O prazo escrito é o prazo configurado
# ===========================================================================


class TestPrazo:
    def test_o_texto_promete_o_que_o_ajuste_cumpre(self, client, pessoa):
        """
        O e-mail diz "3 dias"; quem decide é `PASSWORD_RESET_TIMEOUT`. Se
        alguém mudar o ajuste sem mexer no texto, o e-mail passa a
        mentir -- e é isto que o teste pega.
        """
        dias = settings.PASSWORD_RESET_TIMEOUT // (60 * 60 * 24)
        msg = pedir(client, pessoa)

        assert f"{dias} dias" in msg.body
        assert f"{dias} dias" in html_de(msg)

    def test_o_link_abre_dentro_do_prazo(self, client, pessoa):
        """
        Dois dias depois -- dentro dos três -- o link leva ao formulário
        de nova senha, com o campo para digitá-la.
        """
        with freeze_time("2026-03-17 12:00:00"):
            link = link_de(pedir(client, pessoa).body)

        with freeze_time("2026-03-19 12:00:00"):
            resposta = client.get(link, follow=True)

        corpo = resposta.content.decode()
        assert resposta.status_code == 200
        assert 'name="new_password1"' in corpo, "não é o formulário de nova senha"

    def test_o_link_para_de_valer_depois_do_prazo(self, client, pessoa):
        """
        O prazo não é decoração. Congelar o relógio é a única forma de
        provar isto sem esperar três dias.
        """
        with freeze_time("2026-03-17 12:00:00"):
            link = link_de(pedir(client, pessoa).body)

        depois = timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 60)
        with freeze_time("2026-03-17 12:00:00") as relogio:
            relogio.tick(depois)
            resposta = client.get(link, follow=True)

        corpo = resposta.content.decode().lower()
        assert "inválido" in corpo or "invalido" in corpo or "expirou" in corpo


# ===========================================================================
# 3. A identidade vem do CMS
# ===========================================================================


class TestIdentidade:
    def test_o_html_usa_o_nome_do_site(self, client, pessoa):
        from apps.content.models import SiteSettings

        config = SiteSettings.load()
        config.site_name = "Convite Fácil"
        config.save()

        assert "Convite Fácil" in html_de(pedir(client, pessoa))

    def test_o_html_usa_a_cor_do_site(self, client, pessoa):
        """
        Uma cor escrita no template seria uma segunda fonte de verdade, e
        o e-mail deixaria de acompanhar a tela de Aparência.
        """
        from apps.content.models import SiteSettings

        config = SiteSettings.load()
        config.theme_primary_color = "#aa3311"
        config.save()

        corpo = html_de(pedir(client, pessoa))

        assert "#aa3311" in corpo
        assert "#1a5fd6" not in corpo

    def test_com_logomarca_sai_a_imagem_com_endereco_absoluto(self, client, pessoa):
        """
        Relativo não resolve dentro de um cliente de e-mail: não há
        página de origem.
        """
        imagem = com_logomarca()

        corpo = html_de(pedir(client, pessoa))

        assert f'src="http://testserver{imagem.file.url}"' in corpo

    def test_a_logomarca_tem_texto_alternativo(self, client, pessoa):
        """
        Cliente de e-mail bloqueia imagem por padrão. O `alt` é o nome do
        site, então o cabeçalho continua dizendo quem está falando.
        """
        com_logomarca()

        assert 'alt="Desenrola"' in html_de(pedir(client, pessoa))

    def test_sem_logomarca_sai_a_marca_escrita(self, client, pessoa):
        """A mesma queda que o site faz (ver components/logo.html)."""
        corpo = html_de(pedir(client, pessoa))

        assert "<img" not in corpo
        assert "Carta Convite" in corpo
        assert "Desenrola" in corpo

    def test_a_logomarca_usa_o_mesmo_host_do_link(self, client, pessoa):
        """Um host diferente seria uma segunda fonte de verdade."""
        com_logomarca()
        msg = pedir(client, pessoa)
        corpo = html_de(msg)

        host = re.match(r"(https?://[^/]+)", link_de(msg.body)).group(1)
        assert f'src="{host}' in corpo

    def test_nenhum_dominio_escrito_no_template(self):
        """
        O endereço é sempre o de onde a pessoa pediu -- nunca um escrito
        no arquivo. Mesma regra que a versão de texto já cumpre.
        """
        from pathlib import Path

        arquivo = Path("templates/accounts/password_reset_email.html")
        texto = arquivo.read_text(encoding="utf-8")

        assert "desenrola.be" not in texto
        assert "http://" not in texto.replace("{{ protocol }}://", "")
        assert "https://" not in texto.replace("{{ protocol }}://", "")


# ===========================================================================
# 4. Compatível com cliente de e-mail
# ===========================================================================


class TestCompatibilidade:
    def test_nao_ha_javascript(self, client, pessoa):
        corpo = html_de(pedir(client, pessoa)).lower()

        assert "<script" not in corpo
        assert "javascript:" not in corpo
        assert "onclick" not in corpo

    def test_nao_ha_arquivo_externo(self, client, pessoa):
        """
        Folha de estilo e fonte remota são bloqueadas ou ignoradas -- o
        Gmail remove o `<head>` inteiro.
        """
        corpo = html_de(pedir(client, pessoa)).lower()

        assert "<link" not in corpo
        assert "@import" not in corpo
        assert "fonts.googleapis" not in corpo

    def test_o_desenho_e_de_tabela_com_estilo_em_linha(self, client, pessoa):
        """
        O Outlook desenha com o motor do Word: `flex` e `grid` não
        existem lá.
        """
        corpo = html_de(pedir(client, pessoa))

        assert 'role="presentation"' in corpo
        assert "display:flex" not in corpo
        assert "display:grid" not in corpo

    def test_o_botao_e_uma_celula_colorida(self, client, pessoa):
        """
        Um `<a>` com padding não é clicável inteiro no Outlook -- só o
        texto é. A célula com cor de fundo resolve em todos.
        """
        corpo = html_de(pedir(client, pessoa))

        assert "bgcolor=" in corpo
        assert "Escolher nova senha" in corpo

    def test_o_endereco_aparece_tambem_escrito(self, client, pessoa):
        """
        Para quem prefere copiar e colar, e para o cliente que não
        desenha o botão.
        """
        msg = pedir(client, pessoa)
        corpo = html_de(msg)
        link = link_de(msg.body)

        # Uma vez no botão, outra por extenso no corpo do texto.
        assert corpo.count(link) >= 2


# ===========================================================================
# 5. Segurança
# ===========================================================================


class TestSeguranca:
    def test_o_nome_da_pessoa_e_escapado(self, client):
        """
        A versão de texto usa `autoescape off` e ali é inofensivo -- texto
        puro não interpreta marcação. No HTML seria injeção: o nome vem do
        cadastro da própria pessoa.
        """
        quem = get_user_model().objects.create_user(
            email="x@exemplo.test",
            password="x" * 12,
            full_name="<b>Marina</b><script>alert(1)</script>",
        )

        corpo = html_de(pedir(client, quem))

        assert "<script>alert(1)</script>" not in corpo
        assert "&lt;b&gt;" in corpo or "&lt;script&gt;" in corpo

    def test_o_token_so_aparece_dentro_do_link(self, client, pessoa):
        """
        Nada de "o seu código é X" numa linha à parte: o token é
        credencial, e o único lugar dele é o endereço.
        """
        msg = pedir(client, pessoa)
        link = link_de(msg.body)
        token = link.rstrip("/").rsplit("/", 1)[-1]
        corpo = html_de(msg)

        assert token in corpo
        # Toda ocorrência do token faz parte de uma ocorrência do link.
        assert corpo.count(token) == corpo.count(link)

    def test_a_senha_nao_vai_no_email(self, client, pessoa):
        msg = pedir(client, pessoa)

        assert "x" * 12 not in msg.body
        assert "x" * 12 not in html_de(msg)

    def test_email_desconhecido_nao_manda_nada(self, client):
        """Regressão: não revelar quem tem conta."""
        mail.outbox = []

        resposta = client.post(PEDIR, {"email": "ninguem@exemplo.test"})

        assert resposta.status_code == 302
        assert mail.outbox == []
