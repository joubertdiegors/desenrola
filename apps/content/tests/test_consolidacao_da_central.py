"""
Consolidação da Central de Conteúdo: a varredura que fecha o bloco.

O QUE ESTA SUÍTE ACRESCENTA
---------------------------
`test_central_de_conteudo.py` já cobre agrupamento, nomes, miniaturas,
prévia, situação e acesso. O que faltava era uma varredura SISTEMÁTICA
das três telas -- Central, editor e prévia -- atrás de chave técnica
VISÍVEL, para as sete partes de uma vez.

POR QUE "VISÍVEL", E NÃO "PRESENTE"
-----------------------------------
As chaves técnicas aparecem legitimamente em lugares que não são texto:
`/backoffice/partners/` é uma URL, `hero-art` é uma classe de CSS,
`value="content.view_partner"` é o identificador que um formulário
submete. Procurar a palavra solta no corpo pegaria todos esses e não
provaria nada.

O que não pode acontecer é a chave virar TÍTULO -- foi o defeito real
que o editor tinha (`<h1>navbar</h1>`) e que a prévia ainda tinha no
`<title>`. Por isso a varredura olha só os títulos.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.content import section_schema
from apps.content.models import PageSection

pytestmark = pytest.mark.django_db

CENTRAL = reverse("backoffice:content")

# As partes da Home, na estrutura que o produto declara -- e que é a
# mesma que o Bloco E exige. Eram sete; as Perguntas frequentes entraram
# no grupo do meio.
#
# Escrita à mão de propósito: derivá-la de `section_schema` faria o teste
# concordar com qualquer coisa que o schema viesse a dizer.
ESTRUTURA = {
    "topo": [
        ("navbar", "Barra superior"),
        ("hero", "Banner superior"),
        ("trust", "Destaques abaixo do Banner superior"),
    ],
    "meio": [
        ("partners", "Nossos Parceiros"),
        ("how", "Como funciona"),
        ("faq", "Perguntas frequentes"),
    ],
    "final": [
        ("cta", "Mini Banner"),
        ("footer", "Rodapé"),
    ],
}

CHAVES = [chave for partes in ESTRUTURA.values() for chave, _nome in partes]


def _com_permissoes(*codenames, email="editora@mail.com"):
    pessoa = get_user_model().objects.create_user(
        email=email, password="x", full_name="Clara Dias"
    )
    pessoa.user_permissions.add(
        Permission.objects.get(content_type__app_label="core", codename="access_backoffice")
    )
    for codename in codenames:
        pessoa.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename=codename)
        )
    return get_user_model().objects.get(pk=pessoa.pk)


@pytest.fixture
def cliente(db):
    c = Client()
    c.force_login(_com_permissoes("view_pagesection", "change_pagesection"))
    return c


def secao(chave):
    return PageSection.objects.get(page__key="home", key=chave)


def titulos(corpo):
    """Todo texto que a página apresenta como título."""
    achados = []
    for marca in ("title", "h1", "h2", "h3"):
        achados += re.findall(rf"<{marca}[^>]*>(.*?)</{marca}>", corpo, re.S)
    return [re.sub(r"<[^>]+>", "", t).strip() for t in achados]


# ===========================================================================
# 1. A estrutura que o bloco exige
# ===========================================================================


class TestEstrutura:
    @pytest.mark.parametrize(("grupo", "partes"), ESTRUTURA.items())
    def test_cada_grupo_tem_exatamente_as_suas_partes(self, grupo, partes):
        declaradas = [
            chave for chave, s in section_schema.SECOES.items() if s.grupo == grupo
        ]

        assert declaradas == [chave for chave, _nome in partes]

    @pytest.mark.parametrize("chave,nome", [p for ps in ESTRUTURA.values() for p in ps])
    def test_cada_parte_tem_o_nome_combinado(self, chave, nome):
        assert section_schema.SECOES[chave].nome == nome

    def test_nao_ha_parte_a_mais_nem_a_menos(self):
        assert set(section_schema.SECOES) == set(CHAVES)

    def test_a_central_mostra_TODAS_com_o_nome_combinado(self, cliente):
        corpo = cliente.get(CENTRAL).content.decode()

        for _chave, nome in [p for ps in ESTRUTURA.values() for p in ps]:
            assert nome in corpo, nome


# ===========================================================================
# 2. Nenhuma chave técnica como título -- nas três telas
# ===========================================================================


class TestNenhumaChaveTecnicaVisivel:
    def test_na_central(self, cliente):
        vistos = titulos(cliente.get(CENTRAL).content.decode())

        assert not set(vistos) & set(CHAVES), set(vistos) & set(CHAVES)

    @pytest.mark.parametrize("chave", CHAVES)
    def test_no_editor_de_cada_parte(self, cliente, chave):
        corpo = cliente.get(
            reverse("backoffice:content_section", args=[secao(chave).pk])
        ).content.decode()

        assert chave not in titulos(corpo)
        assert section_schema.SECOES[chave].nome in titulos(corpo)

    @pytest.mark.parametrize("chave", CHAVES)
    def test_na_previa_de_cada_parte(self, cliente, chave):
        """
        A prévia vive dentro de um `<iframe>` e o seu `<title>` raramente
        é visto -- mas chave técnica continua sendo chave técnica.
        """
        corpo = cliente.get(
            reverse("backoffice:content_preview", args=[secao(chave).pk])
        ).content.decode()

        assert chave not in titulos(corpo)
        assert section_schema.SECOES[chave].nome in titulos(corpo)


# ===========================================================================
# 3. Nenhuma ação falsa, em nenhuma das sete
# ===========================================================================


class TestNenhumaAcaoFalsa:
    @pytest.mark.parametrize("chave", CHAVES)
    def test_o_editor_de_cada_parte_abre(self, cliente, chave):
        assert cliente.get(
            reverse("backoffice:content_section", args=[secao(chave).pk])
        ).status_code == 200

    @pytest.mark.parametrize("chave", CHAVES)
    def test_nenhum_botao_sem_destino_no_editor(self, cliente, chave):
        corpo = cliente.get(
            reverse("backoffice:content_section", args=[secao(chave).pk])
        ).content.decode()

        assert 'href="#"' not in corpo
        assert "href=''" not in corpo

    @pytest.mark.parametrize("chave", CHAVES)
    def test_todo_link_do_editor_responde(self, cliente, chave):
        """
        Cada `href` interno da tela é visitado de verdade. Um link para
        uma rota que não existe mais só aparece quando se clica.
        """
        corpo = cliente.get(
            reverse("backoffice:content_section", args=[secao(chave).pk])
        ).content.decode()
        internos = {
            href
            for href in re.findall(r'href="(/[^"#?]*)', corpo)
            if not href.startswith("/static/") and not href.startswith("/media/")
        }

        for href in sorted(internos):
            assert cliente.get(href).status_code in (200, 302), href

    def test_cada_parte_com_cadastro_leva_ao_cadastro_dela(self, cliente):
        """
        As duas que administram registros próprios (`section_schema`)
        precisam oferecer o caminho -- senão a declaração seria letra
        morta na tela.
        """
        com_cadastro = {
            chave for chave, s in section_schema.SECOES.items() if s.cadastro
        }
        assert com_cadastro == {"navbar", "partners", "faq", "footer"}

        corpo_navbar = cliente.get(
            reverse("backoffice:content_section", args=[secao("navbar").pk])
        ).content.decode()
        # O link de parceiros só aparece para quem pode entrar na tela
        # deles -- por isso aqui vai alguém que tenha a permissão.
        com_parceiros = Client()
        com_parceiros.force_login(
            _com_permissoes(
                "view_pagesection", "change_pagesection", "view_partner",
                email="tambem-parceiros@mail.com",
            )
        )
        corpo_parceiros = com_parceiros.get(
            reverse("backoffice:content_section", args=[secao("partners").pk])
        ).content.decode()

        assert reverse("backoffice:menu_item_new") in corpo_navbar
        assert reverse("backoffice:partners") in corpo_parceiros

    def test_quem_nao_pode_ver_parceiros_nao_recebe_o_link(self, cliente):
        """A porta que bateria na cara não é oferecida."""
        corpo = cliente.get(
            reverse("backoffice:content_section", args=[secao("partners").pk])
        ).content.decode()

        assert "Os parceiros" in corpo
        assert "Abrir o cadastro" not in corpo


# ===========================================================================
# 4. Sem JavaScript, a Central continua inteira
# ===========================================================================


class TestSemJavaScript:
    def test_as_miniaturas_sao_iframes_e_nao_dependem_de_script(self, cliente):
        """
        O `src` de cada miniatura é um GET comum -- sem script, ela
        continua mostrando o que está salvo.

        "A tela não tem script nenhum" seria falso e não é o ponto: o
        `base.html` carrega o `app.js` do projeto em toda página. O que
        importa é que as miniaturas não passem por ele.
        """
        corpo = cliente.get(CENTRAL).content.decode()

        molduras = re.findall(r"<iframe[^>]*>", corpo)
        assert len(molduras) == len(CHAVES)
        for moldura in molduras:
            assert 'src="/' in moldura, moldura
            assert "data-" not in moldura, moldura

    def test_os_botoes_de_largura_do_editor_ficam_escondidos_sem_script(self, cliente):
        """
        O CSS só os mostra com `js-ligado` no `<html>`, que é o próprio
        script quem põe. Botão que não faz nada é o que estas telas
        tinham antes da Etapa I.
        """
        from pathlib import Path

        css = Path("static/css/layout.css").read_text(encoding="utf-8")

        assert ".bo-previa-head nav { display: none; }" in css
        assert ".js-ligado .bo-previa-head nav" in css

    def test_ativar_e_desativar_e_um_post_comum(self, cliente):
        """A confirmação é do navegador; a ação não depende dela."""
        corpo = cliente.get(CENTRAL).content.decode()

        assert corpo.count('method="post"') >= len(CHAVES)
        assert "csrfmiddlewaretoken" in corpo


# ===========================================================================
# 5. O seletor de idioma cabe no celular
# ===========================================================================


class TestSeletorDeIdioma:
    def test_os_quatro_idiomas_sao_oferecidos(self, cliente):
        from django.conf import settings

        corpo = cliente.get(
            reverse("backoffice:content_section", args=[secao("hero").pk])
        ).content.decode()

        for codigo, _nome in settings.LANGUAGES:
            assert f"?idioma={codigo}" in corpo, codigo

    def test_no_celular_o_seletor_quebra_linha_em_vez_de_cortar(self):
        """
        `.seg` tem `overflow: hidden`. Sem quebrar linha, os quatro
        idiomas não cabem em 390px e o quarto fica CLIPADO -- invisível e
        inalcançável, e não haveria como editar o conteúdo em inglês pelo
        telefone.
        """
        from pathlib import Path

        css = Path("static/css/layout.css").read_text(encoding="utf-8")
        celular = css.split("@media (max-width: 767px)")

        assert any(
            ".seg { flex-wrap: wrap; overflow: visible; }" in bloco for bloco in celular[1:]
        ), "a regra de celular do seletor sumiu"
