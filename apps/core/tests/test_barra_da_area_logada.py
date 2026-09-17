"""
A barra superior da área logada: uma marca no centro, uma porta por destino.

DOIS PROBLEMAS, UM ARQUIVO
--------------------------
No CELULAR a barra trazia o logotipo à esquerda e as iniciais da pessoa
à direita. O Perfil já tem destino próprio na barra inferior
(`components/tabbar.html`), então as iniciais eram um segundo caminho
para o mesmo lugar -- e, de quebra, desequilibravam a barra.

No DESKTOP havia DOIS acessos ao Perfil: o link solto ao lado de
"Minhas cartas" e o menu das iniciais. Ficou o menu, que é o único que
também abriga o "Sair".

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o avatar volte à barra superior do celular;**
2. **Que o logotipo deixe de ficar centrado** por alguém reintroduzir um
   elemento à direita dentro do fluxo;
3. **Que o Perfil volte a ter duas portas no desktop;**
4. **Que o acesso ao Perfil suma junto** -- tirar duplicata não é tirar
   o destino;
5. **Que o atalho do Backoffice desapareça** de quem tem a permissão, ou
   apareça para quem não tem.
"""

import pathlib
import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

NAV = pathlib.Path("templates/components/app_nav.html")
LAYOUT = pathlib.Path("static/css/layout.css")

# As telas da área logada que desenham a barra superior no celular.
COM_BARRA_NO_CELULAR = ["core:dashboard", "accounts:profile"]


@pytest.fixture
def pessoa(db):
    return get_user_model().objects.create_user(
        email="barra@mail.com", password="x", full_name="Clara Dias Souza"
    )


@pytest.fixture
def cliente(pessoa):
    c = Client()
    c.force_login(pessoa)
    return c


@pytest.fixture
def cliente_admin(pessoa):
    pessoa.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="core", codename="access_backoffice"
        )
    )
    c = Client()
    c.force_login(get_user_model().objects.get(pk=pessoa.pk))
    return c


def barra(html):
    """Só o `<header>` da área logada -- o resto da página não conta."""
    inicio = html.index('<header class="app-header')
    return html[inicio : html.index("</header>", inicio)]


# ===========================================================================
# 1. O celular: uma coisa só na barra
# ===========================================================================


class TestNoCelular:
    def test_a_barra_nao_traz_avatar(self, cliente):
        html = barra(cliente.get(reverse("core:dashboard")).content.decode())

        assert 'class="avatar avatar-md m-only"' not in html

    def test_nenhum_avatar_fora_do_menu_do_desktop(self, cliente):
        """
        O avatar que sobrou é o do `<summary>` do menu, e esse menu é
        `d-only`: no celular ele não existe.
        """
        html = barra(cliente.get(reverse("core:dashboard")).content.decode())
        antes_do_menu = html[: html.index("user-menu")]

        assert "avatar" not in antes_do_menu

    def test_o_logotipo_fica_centrado(self):
        css = LAYOUT.read_text(encoding="utf-8")
        celular = css[css.index("@media (max-width: 767px)", css.index(".app-nav {")) :]
        regra = celular[celular.index(".app-nav {") : celular.index(".app-nav {") + 200]

        assert "justify-content: center" in regra

    def test_o_atalho_do_backoffice_sai_do_fluxo_para_nao_descentrar(self):
        """
        Com `justify-content: center`, um botão no fluxo empurraria o
        logotipo para a esquerda -- e o centro deixaria de ser centro
        justamente para quem administra.
        """
        css = LAYOUT.read_text(encoding="utf-8")
        celular = css[css.index("@media (max-width: 767px)", css.index(".app-nav {")) :]
        regra = celular[
            celular.index(".app-nav .nav-backoffice") : celular.index(
                ".app-nav .nav-backoffice"
            )
            + 200
        ]

        assert "position: absolute" in regra

    @pytest.mark.parametrize("rota", COM_BARRA_NO_CELULAR)
    def test_o_perfil_continua_a_um_toque_pela_barra_inferior(self, cliente, rota):
        """Tirar a duplicata não pode ser tirar o destino."""
        html = cliente.get(reverse(rota)).content.decode()

        assert reverse("accounts:profile") in html


# ===========================================================================
# 2. O desktop: uma porta por destino
# ===========================================================================


class TestNoDesktop:
    def test_ha_um_unico_acesso_ao_perfil(self, cliente):
        html = barra(cliente.get(reverse("core:dashboard")).content.decode())

        assert html.count(f'href="{reverse("accounts:profile")}"') == 1

    def test_o_acesso_que_ficou_e_o_do_menu(self, cliente):
        """
        É o único que também abriga o "Sair": manter o link solto seria
        duas portas para o Perfil e uma só para sair.
        """
        html = barra(cliente.get(reverse("core:dashboard")).content.decode())
        menu = html[html.index("dropdown-menu") :]

        assert reverse("accounts:profile") in menu
        assert reverse("accounts:logout") in menu

    def test_nao_ha_mais_link_solto_de_perfil(self):
        marcacao = NAV.read_text(encoding="utf-8")
        soltos = re.findall(r'<a class="nav-link[^"]*"[^>]*>', marcacao)

        for link in soltos:
            assert "profile" not in link

    def test_os_outros_destinos_continuam(self, cliente):
        html = barra(cliente.get(reverse("core:dashboard")).content.decode())

        assert reverse("core:dashboard") in html
        assert reverse("letters:history") in html

    def test_o_perfil_aberto_se_anuncia_no_menu(self, cliente):
        """
        Era o link solto que carregava o `aria-current`. Ele saiu; o
        estado tinha de ir junto, ou o menu passaria a mentir.
        """
        html = barra(cliente.get(reverse("accounts:profile")).content.decode())
        item = html[html.index("dropdown-item") : html.index("dropdown-sep")]

        assert 'aria-current="page"' in item
        assert "is-current" in item


# ===========================================================================
# 3. O atalho do Backoffice
# ===========================================================================


class TestAtalhoDoBackoffice:
    def test_quem_tem_a_permissao_ve_o_atalho(self, cliente_admin):
        html = barra(cliente_admin.get(reverse("core:dashboard")).content.decode())

        assert reverse("backoffice:overview") in html

    def test_quem_nao_tem_nao_ve(self, cliente):
        html = barra(cliente.get(reverse("core:dashboard")).content.decode())

        assert reverse("backoffice:overview") not in html
