"""
O menu do Backoffice, na organização final (Rodada 15).

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a ordem se perca.** Primeiro o que se opera no dia a dia --
   Visão geral, Usuários, Cartas, Modelos de cartas, Wizzard - gerar
   carta, Home - Configurações, Parceiros --, depois o grupo Sistema;
2. **Que um nome antigo volte.** "Conteúdo do site", "Política das
   cartas" e o "Modelos" solto deram lugar aos nomes novos;
3. **Que "Bandeiras" vire uma segunda tela.** É um caminho até a seção
   delas em Idiomas -- a mesma fonte, um lugar só;
4. **Que o menu ofereça porta que bateria na cara.** Cada item continua
   com a MESMA permissão que a tela cobra no servidor;
5. **Que "Wizzard - gerar carta" deixe de ser a "Política das cartas".**
   Mudou só o nome (Rodada 16): a página, a rota e o conteúdo são os de
   antes.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

pytestmark = pytest.mark.django_db

PRINCIPAIS = [
    "Visão geral",
    "Usuários",
    "Cartas",
    "Modelos de cartas",
    "Wizzard - gerar carta",
    "Home - Configurações",
    "Parceiros",
]
DO_SISTEMA = [
    "E-mail",
    "Imagens",
    "Idiomas",
    "Bandeiras",
    "Aparência",
    "Identidade",
    "Documentos legais",
]


@pytest.fixture
def administradora(db):
    """Todas as permissões dos apps do produto -- vê o menu inteiro."""
    pessoa = get_user_model().objects.create_user(
        email="menu@mail.com", password="x", full_name="Menu Inteiro"
    )
    pessoa.user_permissions.set(
        Permission.objects.filter(
            content_type__app_label__in=("core", "accounts", "content", "letters", "doctemplates")
        )
    )
    return get_user_model().objects.get(pk=pessoa.pk)


def _menu_lateral(html):
    """O `<nav class="side-menu">` do desktop -- o menu, e nada mais da tela."""
    inicio = html.index('<nav class="side-menu"')
    return html[inicio : html.index("</nav>", inicio)]


def _rotulos(menu):
    """O texto de cada link, na ordem da tela."""
    return [
        re.sub(r"<[^>]+>", "", corpo).strip()
        for corpo in re.findall(r"<a [^>]*>(.*?)</a>", menu, re.S)
    ]


class TestOrdem:
    def test_os_itens_principais_e_depois_o_sistema(self, client, administradora):
        client.force_login(administradora)

        menu = _menu_lateral(client.get(reverse("backoffice:overview")).content.decode())

        assert _rotulos(menu) == [*PRINCIPAIS, *DO_SISTEMA, "Voltar ao início"]

    def test_sistema_e_um_grupo_com_titulo(self, client, administradora):
        client.force_login(administradora)

        menu = _menu_lateral(client.get(reverse("backoffice:overview")).content.decode())
        grupo = menu[menu.index('class="side-menu-grupo"') :]

        assert 'role="group"' in grupo[:120]
        assert '<span class="side-menu-grupo-titulo" aria-hidden="true">Sistema</span>' in grupo
        # Todo o grupo, e só ele, fica depois do título.
        assert _rotulos(grupo) == [*DO_SISTEMA, "Voltar ao início"]

    def test_o_menu_do_celular_tem_a_mesma_ordem(self, client, administradora):
        client.force_login(administradora)

        html = client.get(reverse("backoffice:overview")).content.decode()
        inicio = html.index('<div class="dropdown-menu is-left">')
        celular = html[inicio : html.index("</nav>", inicio)]

        assert _rotulos(celular) == [*PRINCIPAIS, *DO_SISTEMA, "Voltar ao início"]
        assert '<span class="dropdown-grupo-titulo" aria-hidden="true">Sistema</span>' in celular


class TestNomes:
    @pytest.mark.parametrize("antigo", ["Conteúdo do site", "Política das cartas"])
    def test_os_nomes_antigos_sairam_do_menu(self, client, administradora, antigo):
        client.force_login(administradora)

        menu = _menu_lateral(client.get(reverse("backoffice:overview")).content.decode())

        assert antigo not in menu

    @pytest.mark.parametrize(
        "rota,titulo",
        [
            ("backoffice:document_library", "Modelos de cartas"),
            ("backoffice:letter_policy", "Wizzard - gerar carta"),
            ("backoffice:content", "Home - Configurações"),
            ("backoffice:system", "Identidade"),
            ("backoffice:legal_documents", "Documentos legais"),
        ],
    )
    def test_cada_tela_tem_o_nome_do_menu(self, client, administradora, rota, titulo):
        client.force_login(administradora)

        html = client.get(reverse(rota)).content.decode()

        assert re.search(rf"<h1[^>]*>\s*{re.escape(titulo)}\s*</h1>", html), titulo
        assert f"<title>{titulo} · " in html

    def test_bandeiras_leva_a_secao_delas_em_idiomas(self, client, administradora):
        client.force_login(administradora)

        menu = _menu_lateral(client.get(reverse("backoffice:overview")).content.decode())
        idiomas = client.get(reverse("backoffice:languages")).content.decode()

        assert f'href="{reverse("backoffice:languages")}#bandeiras"' in menu
        assert 'id="bandeiras"' in idiomas
        assert reverse("backoffice:language_flag", args=["fr"]) in idiomas


class TestWizzardSoONome:
    def test_a_rota_e_a_de_sempre(self):
        assert reverse("backoffice:letter_policy").endswith("/backoffice/cartas/politica/")

    def test_a_pagina_nao_ganhou_nada_alem_do_nome(self, client, administradora):
        """Prazos e declarações, como antes -- sem bandeiras, sem atalho novo."""
        client.force_login(administradora)

        html = client.get(reverse("backoffice:letter_policy")).content.decode()

        assert "Salvar política" in html
        assert "Declarações da etapa 4" in html
        assert 'id="bandeiras"' not in html
        assert reverse("backoffice:language_flag", args=["fr"]) not in html
        assert reverse("letters:new") not in html

    def test_o_nome_antigo_nao_aparece_como_titulo(self, client, administradora):
        client.force_login(administradora)

        html = client.get(reverse("backoffice:letter_policy")).content.decode()

        assert "<h1>Política das cartas</h1>" not in html


class TestPermissoes:
    def test_quem_so_entra_ve_so_o_que_abre(self, client, staff_user):
        """
        `core.access_backoffice` sozinho: as telas que cobram só isso
        aparecem; as que cobram permissão própria, não.
        """
        client.force_login(staff_user)

        rotulos = _rotulos(
            _menu_lateral(client.get(reverse("backoffice:overview")).content.decode())
        )

        assert rotulos == [
            "Visão geral",
            "Wizzard - gerar carta",
            "Idiomas",
            "Bandeiras",
            "Aparência",
            "Identidade",
            "Voltar ao início",
        ]

    def test_a_barra_do_celular_acende_mais_no_grupo_sistema(self, client, administradora):
        client.force_login(administradora)

        html = client.get(reverse("backoffice:legal_documents")).content.decode()
        barra = html[html.index('class="tabbar tabbar-auto m-only"') :]
        mais = barra[: barra.index("Mais")]

        assert 'aria-current="page"' in mais[mais.rindex("<a") :]
