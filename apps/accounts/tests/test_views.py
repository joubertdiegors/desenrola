"""Testes das telas de conta na fase de apresentacao visual."""

import pytest
from django.urls import reverse


@pytest.mark.parametrize(
    ("nome", "texto"),
    [
        ("accounts:login", "Bem-vindo de volta."),
        ("accounts:signup", "Criar conta"),
        ("accounts:password_reset", "Recuperar senha"),
        ("accounts:profile", "Dados pessoais"),
    ],
)
def test_telas_de_conta_respondem(client, nome, texto):
    response = client.get(reverse(nome))

    assert response.status_code == 200
    assert texto in response.content.decode()


def test_perfil_abre_secao_no_celular(client):
    response = client.get(reverse("accounts:profile"), {"secao": "senha"})

    assert response.status_code == 200
    assert response.context["section"] == "senha"
    assert 'class="profile container has-section"' in response.content.decode()


def test_perfil_ignora_secao_desconhecida(client):
    response = client.get(reverse("accounts:profile"), {"secao": "inexistente"})

    assert response.status_code == 200
    assert response.context["section"] is None


def test_login_mantem_a_view_nativa(client):
    """A tela e de apresentacao, mas a rota continua na LoginView do Django."""
    response = client.get(reverse("accounts:login"))

    assert "form" in response.context
