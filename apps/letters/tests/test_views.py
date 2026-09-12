"""Testes das telas de carta (ainda com dados ficticios, mas protegidas por login)."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.parametrize("url", [reverse("letters:new"), reverse("letters:result", args=[1])])
def test_telas_de_carta_exigem_login(client, url):
    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={url}"


def test_formulario_responde(auth_client, user):
    response = auth_client.get(reverse("letters:new"))

    html = response.content.decode()
    assert response.status_code == 200
    assert response.context["step"] == 1
    assert "Gerar Carta Convite" in html
    # Os dados do anfitriao que o modelo ja guarda vem do usuario logado.
    assert user.full_name in html
    assert user.phone in html


@pytest.mark.parametrize(
    ("passo", "esperado"),
    [("1", 1), ("2", 2), ("4", 4), ("0", 1), ("9", 4), ("abc", 1)],
)
def test_formulario_limita_o_passo(auth_client, passo, esperado):
    """No celular o formulario mostra um passo por tela; o passo fica entre 1 e 4."""
    response = auth_client.get(reverse("letters:new"), {"passo": passo})

    assert response.status_code == 200
    assert response.context["step"] == esperado


def test_resultado_responde(auth_client):
    response = auth_client.get(reverse("letters:result", args=[1]))

    assert response.status_code == 200
    assert "Carlos Eduardo Silva" in response.content.decode()


def test_resultado_inexistente_da_404(auth_client):
    response = auth_client.get(reverse("letters:result", args=[999]))

    assert response.status_code == 404
