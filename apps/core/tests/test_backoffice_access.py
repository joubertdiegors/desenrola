"""
Quem entra no Backoffice, e quem só pensa que entra.

A permissão é `core.access_backoffice`, uma permissão de verdade do
Django -- no mesmo sistema que já guarda `letters.view_all_letters`.
Ela vive num modelo sem tabela (`core.BackofficeAccess`), que existe só
para carregá-la.

AS DUAS METADES
---------------
Esconder o atalho no dashboard NÃO é proteção; a proteção é
`backoffice_required` em cada view. Esta suíte cobra as duas: o link
aparece só para quem tem a permissão, E a URL recusa quem não tem --
mesmo digitando o endereço direto, que é exatamente o que alguém faria.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

DASHBOARD = reverse("core:dashboard")

# As rotas administrativas que abrem SÓ com `core.access_backoffice`.
# Uma lista, e não uma amostra: a proteção tem de valer em TODAS --
# basta uma esquecida.
#
# `backoffice:letters` fica de fora porque exige uma segunda permissão
# (ver TestSupervisaoDeCartasExigeMais, abaixo, e a suíte completa em
# apps/letters/tests/test_backoffice_supervisao.py).
ROTAS = [
    "backoffice:overview",
    "backoffice:users",
    "backoffice:permissions",
    "backoffice:templates",
    "backoffice:document_library",
    "backoffice:letter_policy",
    "backoffice:partners",
    "backoffice:appearance",
]


# ===========================================================================
# O atalho no dashboard
# ===========================================================================


class TestAtalhoNoDashboard:
    def test_quem_tem_a_permissao_ve_o_link(self, client, staff_user):
        client.force_login(staff_user)

        corpo = client.get(DASHBOARD).content.decode()

        assert reverse("backoffice:overview") in corpo
        assert "Backoffice" in corpo

    def test_usuario_comum_nao_ve_o_link(self, auth_client):
        corpo = auth_client.get(DASHBOARD).content.decode()

        assert reverse("backoffice:overview") not in corpo
        assert "Backoffice" not in corpo

    def test_is_staff_sozinho_nao_faz_o_link_aparecer(self, client, staff_sem_backoffice):
        """
        A flag do Django Admin não é a chave desta porta -- a permissão é.
        """
        client.force_login(staff_sem_backoffice)

        corpo = client.get(DASHBOARD).content.decode()

        assert reverse("backoffice:overview") not in corpo

    def test_superusuario_ve_o_link(self, client, django_user_model):
        """`has_perm` devolve True para superusuário em qualquer permissão."""
        chefe = django_user_model.objects.create_superuser(
            email="chefe@desenrola.be", password="x", full_name="Chefe"
        )
        client.force_login(chefe)

        corpo = client.get(DASHBOARD).content.decode()

        assert reverse("backoffice:overview") in corpo

    def test_o_contexto_diz_a_verdade(self, auth_client, client, staff_user):
        assert auth_client.get(DASHBOARD).context["can_access_backoffice"] is False

        client.force_login(staff_user)
        assert client.get(DASHBOARD).context["can_access_backoffice"] is True


# ===========================================================================
# A porta de verdade: o servidor
# ===========================================================================


class TestAcessoDireto:
    @pytest.mark.parametrize("rota", ROTAS)
    def test_com_a_permissao_entra(self, client, staff_user, rota):
        client.force_login(staff_user)

        assert client.get(reverse(rota)).status_code == 200

    @pytest.mark.parametrize("rota", ROTAS)
    def test_sem_a_permissao_e_recusado(self, auth_client, rota):
        """403, não um redirect simpático: a pessoa não deveria estar aqui."""
        assert auth_client.get(reverse(rota)).status_code == 403

    @pytest.mark.parametrize("rota", ROTAS)
    def test_is_staff_sozinho_e_recusado(self, client, staff_sem_backoffice, rota):
        client.force_login(staff_sem_backoffice)

        assert client.get(reverse(rota)).status_code == 403

    @pytest.mark.parametrize("rota", ROTAS)
    def test_anonimo_vai_para_o_login(self, client, rota):
        resposta = client.get(reverse(rota))

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_perder_a_permissao_fecha_a_porta_na_hora(self, client, staff_user):
        """Não há cache de permissão atravessando a sessão."""
        client.force_login(staff_user)
        assert client.get(reverse("backoffice:overview")).status_code == 200

        staff_user.user_permissions.clear()
        client.force_login(staff_user)  # nova requisição, permissões relidas

        assert client.get(reverse("backoffice:overview")).status_code == 403


# ===========================================================================
# Alterar a política é uma segunda permissão
# ===========================================================================


class TestPermissaoDeAlterarAPolitica:
    URL = reverse("backoffice:letter_policy")

    @pytest.fixture
    def permissao_de_alterar(self, db):
        from django.contrib.auth.models import Permission

        return Permission.objects.get(
            content_type__app_label="letters", codename="change_letterpolicy"
        )

    def test_quem_so_entra_no_backoffice_ve_mas_nao_salva(self, client, staff_user):
        """
        Consultar a regra e mudá-la são coisas diferentes. Sem
        `letters.change_letterpolicy`, o POST é recusado -- e não só o
        botão escondido.
        """
        client.force_login(staff_user)

        leitura = client.get(self.URL)
        escrita = client.post(self.URL, {"editability": "por_dias", "editability_amount": 3,
                                         "expiration": "nunca", "expiration_amount": 0})

        assert leitura.status_code == 200
        assert leitura.context["pode_editar"] is False
        assert escrita.status_code == 403

    def test_com_a_permissao_salva(self, client, staff_user, permissao_de_alterar):
        from apps.letters import lifecycle

        staff_user.user_permissions.add(permissao_de_alterar)
        client.force_login(staff_user)

        resposta = client.post(
            self.URL,
            {"editability": "por_dias", "editability_amount": 3,
             "expiration": "na_data_da_viagem", "expiration_amount": 0},
        )

        assert resposta.status_code == 302
        config = lifecycle.policy()
        assert config.editability == "por_dias"
        assert config.editability_amount == 3
        assert config.expiration == "na_data_da_viagem"

    def test_valor_invalido_nao_grava(self, client, staff_user, permissao_de_alterar):
        """Política que exige número não aceita zero -- regra do modelo."""
        from apps.letters import lifecycle

        staff_user.user_permissions.add(permissao_de_alterar)
        client.force_login(staff_user)

        resposta = client.post(
            self.URL,
            {"editability": "por_horas", "editability_amount": 0,
             "expiration": "nunca", "expiration_amount": 0},
        )

        assert resposta.status_code == 200
        assert resposta.context["form"].errors
        assert lifecycle.policy().editability == "nao_editavel"


# ===========================================================================
# A supervisão de cartas pede mais do que entrar no Backoffice
# ===========================================================================


class TestSupervisaoDeCartasExigeMais:
    """
    Entrar na área administrativa e ver o documento das pessoas são
    decisões separadas. Quem administra modelos e conteúdo não passa a
    ver as cartas de ninguém por causa disso.
    """

    LISTA = reverse("backoffice:letters")

    def test_so_com_access_backoffice_e_recusado(self, client, staff_user):
        client.force_login(staff_user)

        assert client.get(self.LISTA).status_code == 403

    def test_com_as_duas_permissoes_entra(self, client, staff_user, permissao_ver_todas):
        staff_user.user_permissions.add(permissao_ver_todas)
        client.force_login(staff_user)

        assert client.get(self.LISTA).status_code == 200

    def test_usuario_comum_e_recusado(self, auth_client):
        assert auth_client.get(self.LISTA).status_code == 403
