"""
Testes do assistente de 6 etapas e da conclusao (ainda com dados
ficticios, mas protegidas por login).
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.parametrize("url", [reverse("letters:new"), reverse("letters:result", args=[1])])
def test_telas_de_carta_exigem_login(client, url):
    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={url}"


def test_etapa_1_convidado_comeca_vazia(auth_client):
    """A etapa 1 e um formulario em branco: sem estado salvo entre etapas."""
    response = auth_client.get(reverse("letters:new"))

    html = response.content.decode()
    assert response.status_code == 200
    assert response.context["step"] == 1
    assert "1. Dados do convidado" in html


def test_etapa_3_anfitriao_mostra_dados_do_usuario_logado(auth_client, user):
    """
    A etapa 3 (Anfitrião) e somente confirmacao: nome, telefone e
    endereco vem do usuario autenticado, nao de um formulario.
    """
    response = auth_client.get(reverse("letters:new"), {"passo": 3})

    html = response.content.decode()
    assert response.status_code == 200
    assert user.full_name in html
    assert user.phone in html


@pytest.mark.parametrize(
    ("passo", "esperado"),
    [("1", 1), ("3", 3), ("6", 6), ("0", 1), ("9", 6), ("abc", 1)],
)
def test_formulario_limita_o_passo_entre_1_e_6(auth_client, passo, esperado):
    response = auth_client.get(reverse("letters:new"), {"passo": passo})

    assert response.status_code == 200
    assert response.context["step"] == esperado


def test_etapa_6_revisao_mostra_o_exemplo_preenchido(auth_client):
    response = auth_client.get(reverse("letters:new"), {"passo": 6})

    assert response.status_code == 200
    assert "Maria Santos da Silva" in response.content.decode()


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
