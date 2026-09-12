"""Testes das views do app core."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


def test_healthz_responde_ok(client):
    """A sonda fica fora do prefixo de idioma e nao deve redirecionar."""
    response = client.get("/healthz/")

    assert response.status_code == 200
    assert response.content == b"ok"


def test_home_publica(client):
    response = client.get(reverse("core:home"))

    assert response.status_code == 200
    assert "Sua carta convite pronta em minutos." in response.content.decode()


def test_dashboard_responde_na_fase_visual(client):
    """
    Na fase de apresentacao o dashboard usa dados ficticios e nao exige
    login. O `login_required` volta na fase de autenticacao.
    """
    response = client.get(reverse("core:dashboard"))

    assert response.status_code == 200
    assert "Olá, Claire" in response.content.decode()


@pytest.mark.django_db
def test_dashboard_abre_para_usuario_logado(client):
    User.objects.create_user(
        email="logado@exemplo.be",
        password="senha-forte-123",
        full_name="Usuario Logado",
    )
    client.login(email="logado@exemplo.be", password="senha-forte-123")

    response = client.get(reverse("core:dashboard"))

    assert response.status_code == 200


@pytest.mark.parametrize(
    "nome",
    [
        "backoffice:overview",
        "backoffice:users",
        "backoffice:permissions",
        "backoffice:letters",
        "backoffice:templates",
        "backoffice:content",
        "backoffice:languages",
        "backoffice:system",
    ],
)
def test_backoffice_responde(client, nome):
    """Cada item do menu administrativo resolve para uma tela."""
    response = client.get(reverse(nome))

    assert response.status_code == 200


def test_backoffice_nao_conflita_com_django_admin(client):
    """A area visual vive em /backoffice/; o Django Admin continua em /admin/."""
    assert reverse("backoffice:overview") == "/pt/backoffice/"
    assert reverse("admin:index") == "/pt/admin/"
