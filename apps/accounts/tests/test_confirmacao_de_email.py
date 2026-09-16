"""
A confirmação de e-mail.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o link valha para sempre.** Ele morre no uso e morre quando o
   endereço muda -- é o que `email_verified_at` e `email` fazem dentro
   do hash do token;
2. **Que o link de uma conta sirva para outra.** O `pk` entra no hash;
3. **Que um e-mail fora do ar derrube o cadastro.** A conta já existe e
   a pessoa já está dentro quando o convite sai;
4. **Que trocar o endereço herde a confirmação do anterior.** A marca
   passaria a dizer algo falso;
5. **Que a tela conte quem tem conta aqui.** Link inválido, vencido e de
   conta inexistente dão a MESMA resposta;
6. **Que reenviar vire um disparador de e-mail para terceiros.** É POST,
   e só para `request.user`;
7. **Que confirmar vire exigência.** Ninguém é trancado fora -- isso
   derrubaria toda conta criada antes desta etapa.
"""

import re

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts import confirmacao
from apps.accounts.confirmacao import token_de_email
from apps.accounts.models import User

pytestmark = pytest.mark.django_db

CADASTRO = reverse("accounts:signup")
REENVIAR = reverse("accounts:email_confirm_resend")

DADOS = {
    "full_name": "Rui Santos",
    "email": "rui@exemplo.test",
    "password1": "Correto-Cavalo-Bateria-7",
    "password2": "Correto-Cavalo-Bateria-7",
    "phone_0": "+32",
    "phone_1": "",
    "terms": "on",
}


def link_de(pessoa):
    return reverse(
        "accounts:email_confirm",
        args=[urlsafe_base64_encode(force_bytes(pessoa.pk)), token_de_email.make_token(pessoa)],
    )


def endereco_no_corpo(mensagem):
    """O caminho de confirmação que o e-mail carrega."""
    achados = re.findall(r"/pt/accounts/email/confirmar/[^\s\"<]+", mensagem.body)
    return achados[0] if achados else ""


# ===========================================================================
# 1. O cadastro manda o convite
# ===========================================================================


class TestNoCadastro:
    def test_criar_conta_manda_um_e_mail(self, client):
        client.post(CADASTRO, DADOS)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["rui@exemplo.test"]

    def test_a_conta_nasce_sem_confirmacao(self, client):
        client.post(CADASTRO, DADOS)

        assert User.objects.get(email="rui@exemplo.test").email_confirmado is False

    def test_o_e_mail_leva_o_link_que_funciona(self, client):
        client.post(CADASTRO, DADOS)
        caminho = endereco_no_corpo(mail.outbox[0])

        assert caminho
        assert client.get(caminho).status_code == 200
        assert User.objects.get(email="rui@exemplo.test").email_confirmado is True

    def test_manda_as_duas_versoes(self, client):
        """Texto é o conteúdo; HTML é a apresentação."""
        client.post(CADASTRO, DADOS)
        mensagem = mail.outbox[0]

        assert mensagem.body.strip()
        assert mensagem.alternatives
        assert mensagem.alternatives[0][1] == "text/html"

    def test_o_assunto_e_uma_linha_so(self, client):
        """Quebra de linha num cabeçalho de e-mail é injeção de cabeçalho."""
        client.post(CADASTRO, DADOS)

        assert "\n" not in mail.outbox[0].subject

    def test_nao_ha_dominio_escrito_no_corpo(self, client):
        """O endereço é sempre o de onde a conta foi criada."""
        client.post(CADASTRO, DADOS)

        assert "desenrola.be" not in mail.outbox[0].body
        assert "testserver" in mail.outbox[0].body

    def test_o_e_mail_fora_do_ar_nao_derruba_o_cadastro(self, client, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.EMAIL_HOST = "127.0.0.1"
        settings.EMAIL_PORT = 1  # ninguém escuta aqui

        resposta = client.post(CADASTRO, DADOS)

        assert resposta.status_code == 302
        assert User.objects.filter(email="rui@exemplo.test").exists()


# ===========================================================================
# 2. O token morre
# ===========================================================================


class TestTokenDeUmUso:
    def test_confirmar_invalida_o_proprio_token(self, client, user):
        """
        O LINK VALE UMA VEZ -- perguntado ao gerador, não à tela.

        Olhar a tela não prova isto: ela reconhece quem já confirmou
        ANTES de conferir o token, então diria "já estava confirmado"
        mesmo com um token que continuasse válido. Foi o que uma mutação
        deliberada mostrou.
        """
        token = token_de_email.make_token(user)
        assert token_de_email.check_token(user, token) is True

        client.get(link_de(user))
        user.refresh_from_db()

        assert user.email_confirmado is True
        assert token_de_email.check_token(user, token) is False

    def test_abrir_o_mesmo_link_duas_vezes_nao_e_erro(self, client, user):
        """O pré-carregador do cliente de e-mail passa por ele sozinho."""
        caminho = link_de(user)
        client.get(caminho)

        html = client.get(caminho).content.decode()

        assert "já estava confirmado" in html

    def test_o_hash_do_token_carrega_as_tres_coisas(self, user):
        """
        Quem é, qual endereço, e se já confirmou.

        Estrutural de propósito: `pk` é o que impede o token de uma
        conta de servir para outra, e HOJE isso já sai de graça porque o
        e-mail é único -- tirar o `pk` não muda resposta nenhuma. É a
        mesma composição que o token de senha do Django usa, e este
        teste é o que a guarda no dia em que o e-mail deixar de ser a
        chave de login.
        """
        confirmacao.confirmar(user)

        # IGUALDADE, e não `in`: procurar o `pk` dentro do texto passava
        # mesmo sem ele -- a data de confirmação já carrega o dígito "1".
        # Foi o que uma mutação deliberada mostrou.
        assert token_de_email._make_hash_value(user, 1) == (
            f"{user.pk}{user.email}{user.email_verified_at}1"
        )

    def test_o_hash_muda_quando_a_conta_ainda_nao_confirmou(self, user):
        assert token_de_email._make_hash_value(user, 1) == f"{user.pk}{user.email}1"

    def test_trocar_o_e_mail_invalida_o_link(self, client, user):
        caminho = link_de(user)
        user.email = "outro@exemplo.test"
        user.save(update_fields=["email"])

        client.get(caminho)
        user.refresh_from_db()

        assert user.email_confirmado is False

    def test_o_link_de_uma_conta_nao_serve_para_outra(self, client, user, other_user):
        caminho = reverse(
            "accounts:email_confirm",
            args=[
                urlsafe_base64_encode(force_bytes(other_user.pk)),
                token_de_email.make_token(user),
            ],
        )

        client.get(caminho)
        other_user.refresh_from_db()

        assert other_user.email_confirmado is False

    def test_token_adulterado_nao_confirma(self, client, user):
        caminho = reverse(
            "accounts:email_confirm",
            args=[urlsafe_base64_encode(force_bytes(user.pk)), "aaaaaa-bbbbbbbbbbbbbbbbbbbb"],
        )

        client.get(caminho)
        user.refresh_from_db()

        assert user.email_confirmado is False

    def test_o_link_vence(self, client, user):
        """
        Três dias -- o mesmo prazo do link de senha
        (`PASSWORD_RESET_TIMEOUT`).

        O relógio ANDA de verdade, com freezegun. Pôr o prazo em zero
        não serviria: o token é gerado e conferido no mesmo segundo, e
        `0 <= 0` continua dentro do prazo -- o teste passaria sem provar
        nada sobre vencimento.
        """
        import datetime

        from freezegun import freeze_time

        caminho = link_de(user)

        with freeze_time(timezone.now() + datetime.timedelta(days=4)):
            client.get(caminho)

        user.refresh_from_db()
        assert user.email_confirmado is False

    def test_dentro_do_prazo_ainda_vale(self, client, user):
        import datetime

        from freezegun import freeze_time

        caminho = link_de(user)

        with freeze_time(timezone.now() + datetime.timedelta(days=2)):
            client.get(caminho)

        user.refresh_from_db()
        assert user.email_confirmado is True


# ===========================================================================
# 3. A tela não conta quem tem conta aqui
# ===========================================================================


class TestNaoVazaQuemTemConta:
    def _html(self, client, uid, token="aaaaaa-bbbbbbbbbbbbbbbbbbbb"):
        return client.get(
            reverse("accounts:email_confirm", args=[uid, token])
        ).content.decode()

    def test_conta_inexistente_e_token_ruim_dizem_a_mesma_coisa(self, client, user):
        de_verdade = self._html(client, urlsafe_base64_encode(force_bytes(user.pk)))
        inventada = self._html(client, urlsafe_base64_encode(force_bytes(999999)))

        assert "não vale mais" in de_verdade
        assert "não vale mais" in inventada

    def test_uid_ilegivel_nao_derruba_a_pagina(self, client):
        assert "não vale mais" in self._html(client, "nao-e-base64-!!")

    def test_conta_desativada_nao_confirma(self, client, user):
        caminho = link_de(user)
        user.is_active = False
        user.save(update_fields=["is_active"])

        client.get(caminho)
        user.refresh_from_db()

        assert user.email_confirmado is False


# ===========================================================================
# 4. Reenviar
# ===========================================================================


class TestReenviar:
    def test_manda_outro_link(self, auth_client, user):
        auth_client.post(REENVIAR)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]

    def test_o_link_novo_funciona(self, auth_client, user):
        auth_client.post(REENVIAR)
        caminho = endereco_no_corpo(mail.outbox[0])

        auth_client.get(caminho)
        user.refresh_from_db()

        assert user.email_confirmado is True

    def test_nao_aceita_GET(self, auth_client):
        """Um GET seria disparado por qualquer pré-carregador de navegador."""
        resposta = auth_client.get(REENVIAR)

        assert resposta.status_code == 405
        assert not mail.outbox

    def test_visitante_nao_dispara_e_mail(self, client):
        resposta = client.post(REENVIAR)

        assert resposta.status_code == 302
        assert not mail.outbox

    def test_manda_so_para_o_proprio_endereco(self, auth_client, user, other_user):
        """Um destinatário vindo do pedido seria um disparador para terceiros."""
        auth_client.post(REENVIAR, {"email": other_user.email, "to": other_user.email})

        assert mail.outbox[0].to == [user.email]

    def test_quem_ja_confirmou_nao_recebe_de_novo(self, auth_client, user):
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])

        auth_client.post(REENVIAR)

        assert not mail.outbox


# ===========================================================================
# 5. Trocar o e-mail no perfil
# ===========================================================================


class TestTrocaDeEmailNoPerfil:
    def _salvar(self, auth_client, user, email):
        return auth_client.post(
            reverse("accounts:profile"),
            {
                "action": "dados",
                "full_name": user.full_name,
                "email": email,
                "phone_0": "+32",
                "phone_1": "",
            },
        )

    def test_a_confirmacao_nao_e_herdada_pelo_endereco_novo(self, auth_client, user):
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])

        self._salvar(auth_client, user, "novo@exemplo.test")
        user.refresh_from_db()

        assert user.email == "novo@exemplo.test"
        assert user.email_confirmado is False

    def test_o_convite_sai_para_o_endereco_novo(self, auth_client, user):
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])

        self._salvar(auth_client, user, "novo@exemplo.test")

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["novo@exemplo.test"]

    def test_salvar_sem_trocar_o_e_mail_nao_manda_nada(self, auth_client, user):
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])

        self._salvar(auth_client, user, user.email)
        user.refresh_from_db()

        assert not mail.outbox
        assert user.email_confirmado is True


# ===========================================================================
# 6. O aviso na área logada
# ===========================================================================


class TestAvisoNaAreaLogada:
    def test_quem_nao_confirmou_ve_o_aviso(self, auth_client):
        html = auth_client.get(reverse("core:dashboard")).content.decode()

        assert "aviso-do-email" in html
        assert REENVIAR in html

    def test_quem_confirmou_nao_ve(self, auth_client, user):
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])

        html = auth_client.get(reverse("core:dashboard")).content.decode()

        assert "aviso-do-email" not in html

    def test_o_aviso_alcanca_as_outras_telas_da_area_logada(self, auth_client):
        for rota in ("core:dashboard", "accounts:profile", "letters:history"):
            html = auth_client.get(reverse(rota)).content.decode()

            assert "aviso-do-email" in html, rota

    def test_o_visitante_nao_ve_aviso_nenhum(self, client):
        html = client.get(reverse("core:home")).content.decode()

        assert "aviso-do-email" not in html


# ===========================================================================
# 7. Confirmar não é exigência
# ===========================================================================


class TestNaoTrancaNinguem:
    def test_quem_nao_confirmou_entra_no_painel(self, auth_client):
        assert auth_client.get(reverse("core:dashboard")).status_code == 200

    def test_quem_nao_confirmou_comeca_uma_carta(self, auth_client, modelos_oficiais_prontos):
        resposta = auth_client.post(reverse("letters:new"), {"language": "fr"})

        assert resposta.status_code in (200, 302)

    def test_quem_nao_confirmou_abre_o_perfil(self, auth_client):
        assert auth_client.get(reverse("accounts:profile")).status_code == 200


# ===========================================================================
# 8. As funções, em isolamento
# ===========================================================================


class TestFuncoes:
    def test_confirmar_grava_a_data(self, user):
        assert confirmacao.confirmar(user) is True
        assert user.email_verified_at is not None

    def test_confirmar_duas_vezes_nao_reescreve_a_data(self, user):
        confirmacao.confirmar(user)
        primeira = user.email_verified_at

        assert confirmacao.confirmar(user) is False
        assert user.email_verified_at == primeira

    def test_esquecer_desfaz(self, user):
        confirmacao.confirmar(user)

        assert confirmacao.esquecer(user) is True
        assert user.email_confirmado is False

    def test_esquecer_o_que_nao_estava_confirmado_nao_faz_nada(self, user):
        assert confirmacao.esquecer(user) is False

    def test_nao_manda_para_conta_ja_confirmada(self, rf, user):
        confirmacao.confirmar(user)

        assert confirmacao.enviar(rf.get("/"), user) is False
        assert not mail.outbox

    def test_nao_manda_para_conta_sem_e_mail(self, rf):
        assert confirmacao.enviar(rf.get("/"), User(email="")) is False

    @pytest.mark.parametrize(
        "bruto,esperado",
        [
            ("Desenrola: confirme o seu e-mail\n", "Desenrola: confirme o seu e-mail"),
            ("\n\nDesenrola\n", "Desenrola"),
            ("Linha um\nBcc: invasor@exemplo.test", "Linha umBcc: invasor@exemplo.test"),
        ],
    )
    def test_o_assunto_sai_sempre_numa_linha(self, bruto, esperado):
        """
        Quebra de linha num cabeçalho de e-mail é injeção de cabeçalho.

        O template de assunto de hoje já é uma linha só -- e foi
        justamente por isso que uma mutação que tirava o achatamento
        passou despercebida. Testar a função, e não o template, mede a
        regra em vez do dado.
        """
        assert confirmacao.uma_linha(bruto) == esperado


# ===========================================================================
# 9. A identidade do site chega ao e-mail
# ===========================================================================


class TestIdentidade:
    def test_o_nome_do_site_sai_no_assunto_e_no_corpo(self, client):
        from apps.content.models import SiteSettings

        config = SiteSettings.load()
        config.site_name = "Desenrola Homologação"
        config.save(update_fields=["site_name"])

        client.post(CADASTRO, DADOS)

        assert "Desenrola Homologação" in mail.outbox[0].subject
        assert "Desenrola Homologação" in mail.outbox[0].body

    def test_a_cor_do_site_sai_no_html(self, client):
        from apps.content.models import SiteSettings

        config = SiteSettings.load()
        config.theme_primary_color = "#8a2be2"
        config.save(update_fields=["theme_primary_color"])

        client.post(CADASTRO, DADOS)
        html = mail.outbox[0].alternatives[0][0]

        # No BOTAO, e nao solta no documento: a cor aparece em varios
        # lugares, e procura-la em qualquer um deixava passar um valor
        # escrito a mao no `bgcolor`.
        assert 'bgcolor="#8a2be2"' in html
        assert "#1a5fd6" not in html

    def test_sem_logomarca_sai_a_marca_escrita(self, client):
        client.post(CADASTRO, DADOS)
        html = mail.outbox[0].alternatives[0][0]

        assert "<img" not in html
        assert "Carta Convite" in html

    def test_o_html_nao_desliga_o_escape(self, client):
        """O nome vem do cadastro da própria pessoa."""
        dados = {**DADOS, "full_name": "<script>alert(1)</script> Rui"}
        client.post(CADASTRO, dados)
        html = mail.outbox[0].alternatives[0][0]

        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_o_link_aparece_duas_vezes_no_html(self, client):
        """Botão e endereço por extenso -- cliente que não desenha o botão."""
        client.post(CADASTRO, DADOS)
        html = mail.outbox[0].alternatives[0][0]
        caminho = endereco_no_corpo(mail.outbox[0])

        assert html.count(caminho) >= 2


# ===========================================================================
# 10. O visitante também consegue abrir o link
# ===========================================================================


class TestSemSessao:
    def test_o_link_funciona_noutro_navegador(self, client, user):
        """
        O link chega por e-mail e costuma ser aberto no celular, sem
        sessão. Exigir login o perderia no caminho.
        """
        caminho = link_de(user)
        outro = Client()

        outro.get(caminho)
        user.refresh_from_db()

        assert user.email_confirmado is True

    def test_a_tela_oferece_entrar_a_quem_nao_esta_logado(self, user):
        outro = Client()

        html = outro.get(link_de(user)).content.decode()

        assert reverse("accounts:login") in html
