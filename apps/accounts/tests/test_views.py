"""Testes da autenticacao real: cadastro, login, logout, perfil e recuperacao."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import translation

from conftest import SENHA

User = get_user_model()
IDIOMAS = ["pt", "fr", "nl", "en"]

DADOS_CADASTRO = {
    "full_name": "Sofia Nkemelu",
    "email": "sofia@exemplo.be",
    "password1": "Correto-Cavalo-Bateria-7",
    "password2": "Correto-Cavalo-Bateria-7",
    "phone": "+32 470 11 22 33",
    "address_line1": "Rue des Exemple 25",
    "postal_code": "1200",
    "city": "Woluwe-Saint-Lambert",
    "terms": "on",
}


def esta_logado(client):
    return "_auth_user_id" in client.session


# ---------------------------------------------------------------------------
# Cadastro
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cadastro_valido_cria_usuario_autentica_e_vai_ao_dashboard(client):
    response = client.post(reverse("accounts:signup"), DADOS_CADASTRO)

    assert response.status_code == 302
    assert response.url == reverse("core:dashboard")
    user = User.objects.get(email="sofia@exemplo.be")
    assert user.full_name == "Sofia Nkemelu"
    assert user.phone == "+32 470 11 22 33"
    assert user.city == "Woluwe-Saint-Lambert"
    assert user.password != DADOS_CADASTRO["password1"]  # nunca em texto
    assert user.check_password(DADOS_CADASTRO["password1"])
    assert esta_logado(client)


@pytest.mark.django_db
def test_cadastro_com_email_duplicado_e_recusado(client, user):
    dados = {**DADOS_CADASTRO, "email": user.email.upper()}

    response = client.post(reverse("accounts:signup"), dados)

    assert response.status_code == 200
    assert "Já existe uma conta com este e-mail." in response.content.decode()
    assert User.objects.filter(email__iexact=user.email).count() == 1
    assert not esta_logado(client)


@pytest.mark.django_db
def test_cadastro_com_senhas_diferentes_e_recusado(client):
    dados = {**DADOS_CADASTRO, "password2": "outra-senha-999"}

    response = client.post(reverse("accounts:signup"), dados)

    assert response.status_code == 200
    assert response.context["form"].errors["password2"]
    assert not User.objects.filter(email="sofia@exemplo.be").exists()


@pytest.mark.django_db
def test_cadastro_com_senha_fraca_e_recusado(client):
    dados = {**DADOS_CADASTRO, "password1": "12345678", "password2": "12345678"}

    response = client.post(reverse("accounts:signup"), dados)

    assert response.status_code == 200
    assert response.context["form"].errors["password2"]
    assert not User.objects.exists()


@pytest.mark.django_db
def test_cadastro_exige_aceite_dos_termos(client):
    dados = {**DADOS_CADASTRO}
    del dados["terms"]

    response = client.post(reverse("accounts:signup"), dados)

    assert response.status_code == 200
    assert "terms" in response.context["form"].errors
    assert not User.objects.exists()


@pytest.mark.django_db
def test_cadastro_normaliza_email_para_minusculas(client):
    client.post(reverse("accounts:signup"), {**DADOS_CADASTRO, "email": "Sofia@Exemplo.BE"})

    assert User.objects.filter(email="sofia@exemplo.be").exists()


@pytest.mark.django_db
def test_cadastro_respeita_next_interno(client):
    destino = reverse("letters:new")

    response = client.post(reverse("accounts:signup") + f"?next={destino}", DADOS_CADASTRO)

    assert response.status_code == 302
    assert response.url == destino


@pytest.mark.django_db
def test_cadastro_ignora_next_externo(client):
    url = reverse("accounts:signup") + "?next=https://malicioso.example/"

    response = client.post(url, DADOS_CADASTRO)

    assert response.url == reverse("core:dashboard")


def test_cadastro_redireciona_quem_ja_esta_logado(auth_client):
    response = auth_client.get(reverse("accounts:signup"))

    assert response.status_code == 302
    assert response.url == reverse("core:dashboard")


# ---------------------------------------------------------------------------
# Login e logout
# ---------------------------------------------------------------------------


def test_login_valido_vai_ao_dashboard(client, user):
    response = client.post(
        reverse("accounts:login"), {"username": user.email, "password": SENHA}
    )

    assert response.status_code == 302
    assert response.url == reverse("core:dashboard")
    assert esta_logado(client)


def test_login_aceita_email_com_maiusculas(client, user):
    response = client.post(
        reverse("accounts:login"), {"username": user.email.upper(), "password": SENHA}
    )

    assert response.status_code == 302
    assert esta_logado(client)


def test_login_invalido_fica_na_tela_com_erro(client, user):
    response = client.post(
        reverse("accounts:login"), {"username": user.email, "password": "errada"}
    )

    assert response.status_code == 200
    assert "E-mail ou senha incorretos." in response.content.decode()
    assert not esta_logado(client)


def test_login_respeita_next(client, user):
    destino = reverse("accounts:profile")

    response = client.post(
        reverse("accounts:login"),
        {"username": user.email, "password": SENHA, "next": destino},
    )

    assert response.status_code == 302
    assert response.url == destino


def test_login_a_partir_de_uma_url_de_outro_idioma_cai_no_painel_portugues(
    client, user
):
    """
    A interface e so em portugues (Fase 5, Etapa 4.1): uma URL em frances
    e trazida para /pt/ antes de chegar a view. O login continua
    funcionando -- so nao sobrevive mais um "idioma da sessao".
    """
    with translation.override("fr"):
        url = reverse("accounts:login")
    assert url == "/fr/accounts/login/"

    assert client.get(url).url == "/pt/accounts/login/"

    response = client.post(
        reverse("accounts:login"), {"username": user.email, "password": SENHA}
    )

    assert response.status_code == 302
    assert response.url == "/pt/dashboard/"


def test_login_redireciona_quem_ja_esta_logado(auth_client):
    response = auth_client.get(reverse("accounts:login"))

    assert response.status_code == 302
    assert response.url == reverse("core:dashboard")


def test_logout_encerra_a_sessao_e_volta_para_a_landing(auth_client):
    response = auth_client.post(reverse("accounts:logout"))

    assert response.status_code == 302
    assert response.url == reverse("core:home")
    assert not esta_logado(auth_client)


def test_logout_nao_aceita_get(auth_client):
    response = auth_client.get(reverse("accounts:logout"))

    assert response.status_code == 405
    assert esta_logado(auth_client)


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_perfil_exige_login(client):
    url = reverse("accounts:profile")

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={url}"


def test_perfil_mostra_apenas_os_dados_do_proprio_usuario(auth_client, user, other_user):
    response = auth_client.get(reverse("accounts:profile"))

    html = response.content.decode()
    assert response.status_code == 200
    assert user.email in html
    assert user.full_name in html
    assert other_user.email not in html
    assert other_user.full_name not in html


def test_perfil_salva_os_dados_do_proprio_usuario(auth_client, user, other_user):
    response = auth_client.post(
        reverse("accounts:profile"),
        {
            "action": "dados",
            "full_name": "Claire D. Martin",
            "email": "claire.martin@exemplo.be",
            "phone": "",
            "address_line1": "Avenue Louise 1",
            "postal_code": "1050",
            "city": "Bruxelles",
        },
    )

    assert response.status_code == 302
    user.refresh_from_db()
    other_user.refresh_from_db()
    assert user.full_name == "Claire D. Martin"
    assert user.email == "claire.martin@exemplo.be"
    assert user.get_address_display() == "Avenue Louise 1 – 1050 Bruxelles"
    assert other_user.full_name == "Rafael Costa"


def test_perfil_nao_aceita_email_de_outro_usuario(auth_client, user, other_user):
    response = auth_client.post(
        reverse("accounts:profile"),
        {"action": "dados", "full_name": user.full_name, "email": other_user.email.upper()},
    )

    assert response.status_code == 200
    assert "Já existe uma conta com este e-mail." in response.content.decode()
    user.refresh_from_db()
    assert user.email == "claire@exemplo.be"


def test_perfil_volta_para_a_secao_do_celular(auth_client, user):
    response = auth_client.post(
        reverse("accounts:profile"),
        {"action": "dados", "secao": "dados", "full_name": user.full_name, "email": user.email},
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:profile") + "?secao=dados"


def test_alteracao_de_senha(auth_client, user):
    nova = "Nova-Senha-Segura-42"

    response = auth_client.post(
        reverse("accounts:profile"),
        {
            "action": "senha",
            "old_password": SENHA,
            "new_password1": nova,
            "new_password2": nova,
        },
    )

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password(nova)
    # A sessao continua valida depois da troca.
    assert auth_client.get(reverse("core:dashboard")).status_code == 200


def test_alteracao_de_senha_com_senha_atual_errada(auth_client, user):
    response = auth_client.post(
        reverse("accounts:profile"),
        {
            "action": "senha",
            "old_password": "errada",
            "new_password1": "Nova-Senha-Segura-42",
            "new_password2": "Nova-Senha-Segura-42",
        },
    )

    assert response.status_code == 200
    assert response.context["section"] == "senha"
    assert response.context["password_form"].errors["old_password"]
    user.refresh_from_db()
    assert user.check_password(SENHA)


# ---------------------------------------------------------------------------
# Recuperacao de senha
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_recuperacao_de_senha_do_pedido_a_nova_senha(client, user):
    # 1. Pedido do link
    response = client.post(reverse("accounts:password_reset"), {"email": user.email})
    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_done")
    assert client.get(response.url).status_code == 200

    # 2. E-mail com o link (backend locmem nos testes)
    assert len(mail.outbox) == 1
    corpo = mail.outbox[0].body
    assert user.email in mail.outbox[0].to
    assert "Olá, Claire." in corpo
    link = re.search(r"http://testserver(/pt/accounts/password-reset/[^/\s]+/[^/\s]+/)", corpo)
    assert link, corpo
    link = link.group(1)

    # 3. O link redireciona para a pagina de nova senha
    response = client.get(link)
    assert response.status_code == 302
    pagina = response.url
    assert client.get(pagina).status_code == 200

    # 4. Nova senha
    nova = "Outra-Senha-Segura-99"
    response = client.post(pagina, {"new_password1": nova, "new_password2": nova})
    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_complete")
    assert client.get(response.url).status_code == 200

    user.refresh_from_db()
    assert user.check_password(nova)

    # 5. O link nao vale uma segunda vez
    response = client.get(link, follow=True)
    assert response.context["validlink"] is False
    assert "Link inválido" in response.content.decode()


@pytest.mark.django_db
def test_recuperacao_com_email_desconhecido_nao_revela_nada(client):
    response = client.post(reverse("accounts:password_reset"), {"email": "ninguem@exemplo.be"})

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_link_de_recuperacao_invalido(client):
    url = reverse(
        "accounts:password_reset_confirm", kwargs={"uidb64": "abc", "token": "xyz-123"}
    )

    response = client.get(url)

    assert response.status_code == 200
    assert response.context["validlink"] is False


# ---------------------------------------------------------------------------
# Idiomas
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("idioma", IDIOMAS)
def test_telas_de_conta_respondem_em_todos_os_prefixos(client, idioma):
    """
    Nenhum prefixo pode dar 404. Em /pt/ a pagina responde direto; nos
    outros ela e trazida para o portugues antes de responder -- mas
    sempre acaba em 200, nunca num link morto.
    """
    for rota in ("accounts:login", "accounts:signup", "accounts:password_reset"):
        with translation.override(idioma):
            url = reverse(rota)
        assert url.startswith(f"/{idioma}/")

        response = client.get(url, follow=True)

        assert response.status_code == 200
        destino = response.redirect_chain[-1][0] if response.redirect_chain else url
        assert destino.startswith("/pt/")


@pytest.mark.django_db
@pytest.mark.parametrize("idioma", IDIOMAS)
def test_area_protegida_sempre_manda_para_o_login_em_portugues(client, idioma):
    """
    Quem nao esta logado vai para o login, com `next` de volta -- e, venha
    de que prefixo vier, o login que abre e o portugues.
    """
    response = client.get(f"/{idioma}/accounts/profile/", follow=True)

    assert response.status_code == 200
    destino = response.redirect_chain[-1][0]
    assert destino.startswith("/pt/accounts/login/")
    assert "next=" in destino
    assert destino.endswith("/accounts/profile/")


@pytest.mark.django_db
def test_login_mantem_a_view_nativa(client):
    """A tela e do Desenrola, mas a rota continua na LoginView do Django."""
    response = client.get(reverse("accounts:login"))

    assert "form" in response.context
