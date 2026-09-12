"""Testes das views do app core."""

import pytest
from django.urls import reverse

BACKOFFICE = [
    "backoffice:overview",
    "backoffice:users",
    "backoffice:permissions",
    "backoffice:letters",
    "backoffice:templates",
    "backoffice:content",
    "backoffice:languages",
    "backoffice:system",
]


def test_healthz_responde_ok(client):
    """A sonda fica fora do prefixo de idioma e nao deve redirecionar."""
    response = client.get("/healthz/")

    assert response.status_code == 200
    assert response.content == b"ok"


def test_home_publica(client):
    response = client.get(reverse("core:home"))

    assert response.status_code == 200
    assert "Sua carta convite pronta em minutos." in response.content.decode()


@pytest.mark.django_db
def test_dashboard_exige_login(client):
    url = reverse("core:dashboard")

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={url}"


def test_dashboard_abre_para_usuario_logado(auth_client):
    response = auth_client.get(reverse("core:dashboard"))

    assert response.status_code == 200
    assert "Olá, Claire" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("nome", BACKOFFICE)
def test_backoffice_exige_login(client, nome):
    response = client.get(reverse(nome))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


@pytest.mark.parametrize("nome", BACKOFFICE)
def test_backoffice_nega_usuario_comum(auth_client, nome):
    assert auth_client.get(reverse(nome)).status_code == 403


@pytest.mark.parametrize("nome", BACKOFFICE)
def test_backoffice_responde_para_staff(client, staff_user, nome):
    """Cada item do menu administrativo resolve para uma tela."""
    client.force_login(staff_user)

    assert client.get(reverse(nome)).status_code == 200


def test_backoffice_nao_conflita_com_django_admin():
    """A area visual vive em /backoffice/; o Django Admin continua em /admin/."""
    assert reverse("backoffice:overview") == "/pt/backoffice/"
    assert reverse("admin:index") == "/pt/admin/"
