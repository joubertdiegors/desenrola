"""Testes das views de fundacao."""

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


def test_dashboard_exige_login(client):
    response = client.get(reverse("core:dashboard"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


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
