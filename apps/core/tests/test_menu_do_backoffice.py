"""
O menu do Backoffice, na organização final (Rodada 21).

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a ordem se perca.** Primeiro o que se opera no dia a dia --
   Visão geral, Usuários, Cartas, Modelos de cartas, Wizzard - gerar
   carta (com Idiomas dentro), Home - Configurações, Parceiros --,
   depois o grupo Sistema (com Documentos legais dentro dele);
2. **Que "Sistema" e "Wizzard - gerar carta" parem de ser sanfona.**
   Os dois são `<details>`: abrem e fecham ao clicar, e entram JÁ
   ABERTOS quando a página atual é um deles ou um filho deles;
3. **Que "Idiomas" volte para dentro de Sistema.** Mora dentro de
   "Wizzard - gerar carta" agora -- é a mesma tela de sempre
   (`backoffice:languages`), só o LUGAR no menu que mudou;
4. **Que "Bandeiras" volte.** Era um segundo caminho até a MESMA seção
   de Idiomas (`#bandeiras`); o atalho saiu, a seção continua lá;
5. **Que "Documentos legais" volte a ser uma tela só.** Virou um
   SUBTÍTULO dentro de Sistema, com Termos de uso e Privacidade como
   duas telas independentes, cada uma com a sua rota;
6. **Que o menu ofereça porta que bateria na cara.** Cada item continua
   com a MESMA permissão que a tela cobra no servidor;
7. **Que "Wizzard - gerar carta" deixe de ser a "Política das cartas".**
   Mudou só o nome (Rodada 16): a página, a rota e o conteúdo são os de
   antes.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

pytestmark = pytest.mark.django_db

# A ordem em que os `<a>` aparecem no HTML -- não a hierarquia visual.
# "Idiomas" vem logo depois de "Wizzard - gerar carta" (é o filho dele,
# a próxima tag `<a>` no documento); "Termos de uso"/"Privacidade" vêm
# depois de "Identidade" (são os filhos de "Documentos legais", que é
# um `<span>`, não conta aqui).
PRINCIPAIS = [
    "Visão geral",
    "Usuários",
    "Cartas",
    "Modelos de cartas",
    "Wizzard - gerar carta",
    "Idiomas",
    "Home - Configurações",
    "Parceiros",
]
DO_SISTEMA = [
    "E-mail",
    "Imagens",
    "Aparência",
    "Identidade",
    "Termos de uso",
    "Privacidade",
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


def _menu_celular(html):
    inicio = html.index('<div class="dropdown-menu is-left">')
    return html[inicio : html.index("</nav>", inicio)]


def _rotulos(menu):
    """O texto de cada link, na ordem da tela -- só `<a>`, não `<span>`."""
    return [
        re.sub(r"<[^>]+>", "", corpo).strip()
        for corpo in re.findall(r"<a [^>]*>(.*?)</a>", menu, re.S)
    ]


class TestOrdem:
    def test_os_itens_principais_e_depois_o_sistema(self, client, administradora):
        client.force_login(administradora)

        menu = _menu_lateral(client.get(reverse("backoffice:overview")).content.decode())

        assert _rotulos(menu) == [*PRINCIPAIS, *DO_SISTEMA, "Voltar ao início"]

    def test_o_menu_do_celular_tem_a_mesma_ordem(self, client, administradora):
        client.force_login(administradora)

        celular = _menu_celular(client.get(reverse("backoffice:overview")).content.decode())

        assert _rotulos(celular) == [*PRINCIPAIS, *DO_SISTEMA, "Voltar ao início"]


class TestSanfona:
    def test_sistema_e_um_details_com_titulo_que_nao_e_link(self, client, administradora):
        client.force_login(administradora)

        menu = _menu_lateral(client.get(reverse("backoffice:overview")).content.decode())
        sistema = menu[menu.index("<span class=\"side-menu-pai-rotulo\"") :]

        assert "<details class=\"side-menu-acordeao\"" in menu
        assert "Sistema</span>" in sistema[:120]
        # O rótulo do grupo não é um link para lugar nenhum.
        assert not re.match(r"^<a\b", sistema.split(">", 1)[0])

    def test_documentos_legais_e_um_subtitulo_dentro_de_sistema(self, client, administradora):
        client.force_login(administradora)

        menu = _menu_lateral(client.get(reverse("backoffice:overview")).content.decode())

        assert '<span class="side-menu-filho side-menu-filho-titulo"' in menu
        assert "Documentos legais</span>" in menu
        # E as duas páginas vêm logo depois dele, mais recuadas.
        pos = menu.index("Documentos legais</span>")
        depois = menu[pos:]
        assert depois.index("Termos de uso") < depois.index("Privacidade")

    @pytest.mark.parametrize(
        "pagina,aberto,fechado",
        [
            ("backoffice:letter_policy", "Wizzard - gerar carta", "E-mail"),
            ("backoffice:languages", "Wizzard - gerar carta", "E-mail"),
            ("backoffice:system", "E-mail", "Wizzard - gerar carta"),
            ("backoffice:legal_documents_terms", "E-mail", "Wizzard - gerar carta"),
            ("backoffice:legal_documents_privacy", "E-mail", "Wizzard - gerar carta"),
        ],
    )
    def test_o_grupo_certo_comeca_aberto(self, client, administradora, pagina, aberto, fechado):
        """
        `aberto`/`fechado` são só marcadores: um rótulo lido dentro de
        cada `<details>` (Wizzard tem o próprio nome; Sistema tem
        "E-mail", o primeiro filho). Está aberto quem tem `open` logo
        depois de `side-menu-acordeao`.
        """
        client.force_login(administradora)

        menu = _menu_lateral(client.get(reverse(pagina)).content.decode())
        blocos = re.findall(r"<details[^>]*>.*?</details>", menu, re.S)

        bloco_aberto = next(b for b in blocos if aberto in b)
        bloco_fechado = next(b for b in blocos if fechado in b)

        assert re.match(r"^<details class=\"side-menu-acordeao\" open>", bloco_aberto)
        assert re.match(r"^<details class=\"side-menu-acordeao\">", bloco_fechado)

    def test_fora_dos_dois_grupos_nenhum_comeca_aberto(self, client, administradora):
        client.force_login(administradora)

        menu = _menu_lateral(client.get(reverse("backoffice:overview")).content.decode())

        assert "<details" in menu
        assert " open>" not in menu

    def test_o_svg_do_chevron_esta_nos_dois_grupos(self, client, administradora):
        client.force_login(administradora)

        menu = _menu_lateral(client.get(reverse("backoffice:overview")).content.decode())

        assert menu.count("side-menu-chevron") == 2


class TestNomes:
    @pytest.mark.parametrize(
        "antigo", ["Conteúdo do site", "Política das cartas", "Bandeiras"]
    )
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
            ("backoffice:legal_documents_terms", "Termos de uso"),
            ("backoffice:legal_documents_privacy", "Privacidade"),
        ],
    )
    def test_cada_tela_tem_o_nome_do_menu(self, client, administradora, rota, titulo):
        client.force_login(administradora)

        html = client.get(reverse(rota)).content.decode()

        assert re.search(rf"<h1[^>]*>\s*{re.escape(titulo)}\s*</h1>", html), titulo
        assert f"<title>{titulo} · " in html

    def test_bandeiras_continua_dentro_de_idiomas(self, client, administradora):
        client.force_login(administradora)

        idiomas = client.get(reverse("backoffice:languages")).content.decode()

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
        aparecem; as que cobram permissão própria, não -- inclusive
        "Documentos legais" (o subtítulo some junto com os links, já
        que os três dependem de `content.view_contentblock`).
        """
        client.force_login(staff_user)

        menu = _menu_lateral(client.get(reverse("backoffice:overview")).content.decode())

        assert _rotulos(menu) == [
            "Visão geral",
            "Wizzard - gerar carta",
            "Idiomas",
            "Aparência",
            "Identidade",
            "Voltar ao início",
        ]
        assert "Documentos legais" not in menu

    def test_a_barra_do_celular_acende_mais_no_grupo_sistema(self, client, administradora):
        client.force_login(administradora)

        html = client.get(reverse("backoffice:legal_documents_terms")).content.decode()
        barra = html[html.index('class="tabbar tabbar-auto m-only"') :]
        mais = barra[: barra.index("Mais")]

        assert 'aria-current="page"' in mais[mais.rindex("<a") :]
