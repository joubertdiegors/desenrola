"""
Testes das views do app core: landing, healthz e backoffice.

O dashboard tem suite propria em test_dashboard.py.
"""

import pytest
from django.urls import reverse

# As telas que abrem com `core.access_backoffice` e mais nada.
#
# Ficam de fora as que exigem uma SEGUNDA permissao, cada uma com suite
# propria: `backoffice:letters` (`letters.view_all_letters`, em
# apps/letters/tests/test_backoffice_supervisao.py) e `backoffice:users`
# (`accounts.manage_users`, em
# apps/accounts/tests/test_backoffice_usuarios.py).
BACKOFFICE = [
    "backoffice:overview",
    "backoffice:templates",
    "backoffice:content",
    "backoffice:languages",
    "backoffice:partners",
    "backoffice:appearance",
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
    assert "Gere sua Carta Convite em poucos minutos" in response.content.decode()


@pytest.mark.django_db
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


def test_landing_mostra_a_secao_de_parceiros(client):
    response = client.get(reverse("core:home"))

    html = response.content.decode()
    assert "Nossos parceiros" in html
    assert "JD-Print" in html


def test_backoffice_aparencia_lista_as_cores(client, staff_user):
    client.force_login(staff_user)

    response = client.get(reverse("backoffice:appearance"))

    html = response.content.decode()
    assert response.status_code == 200
    assert 'data-theme-primary="t-roxo"' in html
    assert 'data-theme-success="s-teal"' in html
