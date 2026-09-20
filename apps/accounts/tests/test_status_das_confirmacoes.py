"""
O estado das confirmações no Perfil -- e a saída de cada pendência.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. que a tela diga "confirmado" sobre um estado que o sistema não tem:
   o que ela lê é `email_verified_at` / `phone_verified_at`, as mesmas
   datas que a regra de geração de carta lê -- nunca `bool(user.phone)`
   nem um terceiro mecanismo só para a tela;
2. que uma pendência apareça sem o caminho para resolvê-la;
3. que um estado JÁ confirmado ofereça uma ação que não faz nada --
   reenviar um convite para quem já confirmou, por exemplo;
4. que a ação oferecida deixe de levar ao fluxo que existe
   (`accounts:email_confirm_resend` e `accounts:phone_confirm`).
"""

import pytest
from django.urls import reverse
from django.utils import timezone

pytestmark = pytest.mark.django_db

PERFIL = reverse("accounts:profile")
REENVIO = reverse("accounts:email_confirm_resend")
TELEFONE = reverse("accounts:phone_confirm")

CONFIRMADO = "Confirmado"
PENDENTE = "Pendente de confirmação"


def linha(corpo, qual):
    """
    Só o pedaço da página que fala de UM dado.

    A faixa da área logada também traz um botão de reenviar e-mail
    (`app_base.html`), e o Perfil inteiro diria "Confirmado" por causa
    de outra seção. Afirmar sobre a linha certa é o que faz o teste
    dizer alguma coisa.
    """
    inicio = corpo.index(f'id="confirmacao-{qual}"')
    return corpo[inicio : corpo.index("</li>", inicio)]


def pagina(client):
    resposta = client.get(PERFIL)
    assert resposta.status_code == 200
    return resposta.content.decode()


def confirmar_email(user):
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at"])


def confirmar_telefone(user):
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at"])


# ===========================================================================
# 1. E-mail
# ===========================================================================


class TestEmail:
    def test_confirmado_aparece_como_confirmado(self, auth_client, user):
        confirmar_email(user)

        email = linha(pagina(auth_client), "email")

        assert CONFIRMADO in email
        assert PENDENTE not in email

    def test_confirmado_nao_oferece_acao(self, auth_client, user):
        """Não há o que reenviar para quem já confirmou."""
        confirmar_email(user)

        assert REENVIO not in linha(pagina(auth_client), "email")

    def test_pendente_aparece_como_pendente(self, auth_client, user):
        assert user.email_confirmado is False

        email = linha(pagina(auth_client), "email")

        assert PENDENTE in email
        assert CONFIRMADO not in email

    def test_pendente_oferece_o_reenvio_que_ja_existe(self, auth_client):
        email = linha(pagina(auth_client), "email")

        assert REENVIO in email
        assert "Reenviar e-mail" in email

    def test_o_reenvio_volta_para_o_perfil(self, auth_client):
        """O `next` escondido no formulário é o que traz a pessoa de
        volta ao ponto onde ela estava."""
        email = linha(pagina(auth_client), "email")
        assert f'name="next" value="{PERFIL}"' in email

        resposta = auth_client.post(REENVIO, {"next": PERFIL})

        assert resposta.status_code == 302
        assert resposta.url == PERFIL

    def test_o_endereco_aparece_na_linha(self, auth_client, user):
        assert user.email in linha(pagina(auth_client), "email")

    def test_trocar_o_e_mail_devolve_a_linha_para_pendente(self, auth_client, user):
        """
        A tela não guarda estado próprio: ela lê a data que o sistema
        apaga quando o endereço muda.
        """
        confirmar_email(user)
        assert CONFIRMADO in linha(pagina(auth_client), "email")

        from apps.accounts import confirmacao

        confirmacao.esquecer(user)

        assert PENDENTE in linha(pagina(auth_client), "email")


# ===========================================================================
# 2. Telefone
# ===========================================================================


class TestTelefone:
    def test_confirmado_aparece_como_confirmado(self, auth_client, user):
        confirmar_telefone(user)

        telefone = linha(pagina(auth_client), "telefone")

        assert CONFIRMADO in telefone
        assert PENDENTE not in telefone

    def test_confirmado_nao_oferece_acao(self, auth_client, user):
        confirmar_telefone(user)

        assert TELEFONE not in linha(pagina(auth_client), "telefone")

    def test_pendente_aparece_como_pendente(self, auth_client, user):
        assert user.telefone_confirmado is False

        telefone = linha(pagina(auth_client), "telefone")

        assert PENDENTE in telefone
        assert CONFIRMADO not in telefone

    def test_um_numero_preenchido_nao_confirma_nada(self, auth_client, user):
        """
        Digitar o número é uma coisa; provar que ele é seu é outra. A
        linha lê `phone_verified_at`, não `user.phone`.
        """
        assert user.phone

        assert PENDENTE in linha(pagina(auth_client), "telefone")

    def test_pendente_leva_a_tela_de_codigo(self, auth_client):
        telefone = linha(pagina(auth_client), "telefone")

        assert TELEFONE in telefone
        assert "Confirmar telefone" in telefone

    def test_o_link_traz_de_volta_ao_perfil(self, auth_client):
        telefone = linha(pagina(auth_client), "telefone")
        assert f"?next={PERFIL}" in telefone

        resposta = auth_client.get(TELEFONE, {"next": PERFIL})

        assert resposta.status_code == 200
        assert resposta.context["voltar_para"] == PERFIL

    def test_o_numero_aparece_na_linha(self, auth_client, user):
        assert user.phone in linha(pagina(auth_client), "telefone")

    def test_sem_numero_a_linha_diz_que_nao_ha(self, auth_client, user):
        user.phone = ""
        user.save(update_fields=["phone"])

        telefone = linha(pagina(auth_client), "telefone")

        assert "Não informado" in telefone
        assert PENDENTE in telefone
        assert TELEFONE in telefone


# ===========================================================================
# 3. As duas linhas juntas
# ===========================================================================


class TestAsDuas:
    def test_tudo_confirmado_nao_oferece_acao_nenhuma(self, auth_client, user):
        confirmar_email(user)
        confirmar_telefone(user)

        corpo = pagina(auth_client)

        assert PENDENTE not in corpo
        # A faixa do topo da área logada também some: ela é a mesma
        # pendência, dita noutro lugar.
        assert REENVIO not in corpo
        assert TELEFONE not in corpo

    def test_uma_confirmada_e_a_outra_nao(self, auth_client, user):
        confirmar_email(user)

        corpo = pagina(auth_client)

        assert CONFIRMADO in linha(corpo, "email")
        assert PENDENTE in linha(corpo, "telefone")

    def test_a_secao_tem_titulo_e_ancora(self, auth_client):
        corpo = pagina(auth_client)

        assert 'id="confirmacoes"' in corpo
        assert "Confirmações" in corpo

    def test_o_formulario_de_reenvio_fica_fora_do_de_dados(self, auth_client):
        """
        Um `<form>` dentro de outro não é HTML válido: o navegador
        descarta a tag interna e os campos dela vão junto no salvamento
        dos dados pessoais. A seção das confirmações existe depois do
        formulário de dados justamente por isto.
        """
        corpo = pagina(auth_client)
        dados = corpo.index('id="dados"')
        confirmacoes = corpo.index('id="confirmacoes"')

        assert corpo.index("</form>", dados) < confirmacoes

    def test_so_o_dono_ve_o_proprio_estado(self, client, user, other_user):
        confirmar_email(other_user)
        client.force_login(user)

        assert PENDENTE in linha(pagina(client), "email")

    def test_anonimo_nao_chega_ao_perfil(self, client):
        resposta = client.get(PERFIL)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url
