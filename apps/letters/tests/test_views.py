"""
Testes das views basicas de cartas: exigencia de login e a fase de
apresentacao (conclusao com dados ficticios, `letters:generate`/
`letters:result`), inalterada nesta fase. O assistente real (`letters:new`
-> `letters:step`) tem cobertura propria em test_wizard.py.
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.parametrize("url", [reverse("letters:new"), reverse("letters:result", args=[1])])
def test_telas_de_carta_exigem_login(client, url):
    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={url}"


def test_gerar_redireciona_para_a_conclusao(auth_client):
    response = auth_client.get(reverse("letters:generate"))

    assert response.status_code == 302
    assert response.url == reverse("letters:result", args=[1])


def test_resultado_responde(auth_client):
    response = auth_client.get(reverse("letters:result", args=[1]))

    assert response.status_code == 200
    assert "Maria Santos da Silva" in response.content.decode()


def test_resultado_inexistente_da_404(auth_client):
    response = auth_client.get(reverse("letters:result", args=[999]))

    assert response.status_code == 404
