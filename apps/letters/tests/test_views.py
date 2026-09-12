"""Testes das telas de carta na fase de apresentacao visual."""

import pytest
from django.urls import reverse


def test_formulario_responde(client):
    response = client.get(reverse("letters:new"))

    assert response.status_code == 200
    assert response.context["step"] == 1
    assert "Gerar Carta Convite" in response.content.decode()


@pytest.mark.parametrize(
    ("passo", "esperado"),
    [("1", 1), ("2", 2), ("4", 4), ("0", 1), ("9", 4), ("abc", 1)],
)
def test_formulario_limita_o_passo(client, passo, esperado):
    """No celular o formulario mostra um passo por tela; o passo fica entre 1 e 4."""
    response = client.get(reverse("letters:new"), {"passo": passo})

    assert response.status_code == 200
    assert response.context["step"] == esperado


def test_resultado_responde(client):
    response = client.get(reverse("letters:result", args=[1]))

    assert response.status_code == 200
    assert "Carlos Eduardo Silva" in response.content.decode()


def test_resultado_inexistente_da_404(client):
    response = client.get(reverse("letters:result", args=[999]))

    assert response.status_code == 404
