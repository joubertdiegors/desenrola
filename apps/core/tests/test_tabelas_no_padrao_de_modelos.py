"""
Usuários, Cartas e Parceiros no desenho da tabela de "Modelos de cartas".

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que cada lista volte a ter um desenho próprio.** As três usam as
   classes `mod-*` de `biblioteca-modelos.css` -- cabeçalho, barra,
   cartão, linhas, ações e rodapé de Modelos -- e só a grade é de cada;
2. **Que o celular volte a ter uma segunda marcação.** A MESMA linha vira
   cartão no celular; não há mais tabela `d-only` + lista `m-only`;
3. **Que os filtros percam o que já estava escolhido.** Cada opção da
   barra é um link que preserva os demais filtros;
4. **Que Usuários e Cartas voltem a empilhar informação.** Uma coluna
   por informação, cada célula filha direta da linha, na ordem pedida
   (Rodada 16);
5. **Que uma grade seja recortada.** O cartão tem `overflow: hidden`: a
   soma das colunas fixas de cada faixa tem de caber na largura útil
   dela, senão a coluna de ações some.
"""

import pathlib
import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

CSS = pathlib.Path("static/css/biblioteca-modelos.css")

TELAS = {
    "backoffice:users": "mod-tabela-colunas mod-tabela-usuarios",
    "backoffice:letters": "mod-tabela-colunas mod-tabela-cartas",
    "backoffice:partners": "mod-tabela-lista mod-tabela-parceiros",
}

COLUNAS = {
    "backoffice:users": [
        "Nome", "E-mail", "Telefone", "Endereço", "Cidade", "Cadastro",
        "Último acesso", "Cartas", "Status", "Ações",
    ],
    "backoffice:letters": [
        "Referência", "Criada por", "Para", "Idioma", "Data de ida", "Data de volta",
        "Status", "Criada em", "Finalizada em", "Ações",
    ],
}


@pytest.fixture
def cliente(db):
    """Vê as três telas: gerência de usuários, supervisão e parceiros."""
    pessoa = get_user_model().objects.create_user(
        email="tabelas@mail.com", password="x", full_name="Tabela Única"
    )
    for app_label, codename in (
        ("core", "access_backoffice"),
        ("accounts", "manage_users"),
        ("letters", "view_all_letters"),
        ("content", "view_partner"),
        ("content", "change_partner"),
        ("content", "add_partner"),
        ("content", "delete_partner"),
    ):
        pessoa.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    c = Client()
    c.force_login(pessoa)
    return c


@pytest.fixture
def com_linhas(modelos_oficiais_prontos, user, other_user):
    """
    Uma linha em cada tabela -- a tabela só é desenhada quando há o que
    mostrar. `modelos_oficiais_prontos`: sem o modelo do idioma pronto,
    `start_draft` não cria carta nenhuma (devolve `None`).
    """
    from apps.content.models import Partner
    from apps.letters import services

    assert services.start_draft(user, "fr") is not None
    Partner.objects.create(name="Padaria", url="https://exemplo.test/")


class TestOMesmoDesenho:
    @pytest.mark.parametrize("rota,grade", TELAS.items())
    def test_usa_a_folha_e_as_classes_de_modelos(self, cliente, com_linhas, rota, grade):
        corpo = cliente.get(reverse(rota)).content.decode()

        assert "css/biblioteca-modelos.css" in corpo
        assert '<div class="mod">' in corpo
        assert 'class="mod-cabecalho"' in corpo
        assert 'class="mod-cartao"' in corpo
        assert f'class="mod-tabela {grade}" role="table"' in corpo
        assert 'class="mod-rodape"' in corpo

    @pytest.mark.parametrize("rota", TELAS)
    def test_uma_marcacao_so_para_desktop_e_celular(self, cliente, com_linhas, rota):
        corpo = cliente.get(reverse(rota)).content.decode()

        assert "<table" not in corpo
        assert 'class="list m-only"' not in corpo
        assert "table-wrap d-only" not in corpo

    @pytest.mark.parametrize("rota", TELAS)
    def test_um_h1_so(self, cliente, com_linhas, rota):
        corpo = cliente.get(reverse(rota)).content.decode()

        assert corpo.count("<h1") == 1

    @pytest.mark.parametrize("rota", COLUNAS)
    def test_uma_coluna_por_informacao(self, cliente, com_linhas, rota):
        """
        O cabeçalho tem as colunas pedidas, na ordem pedida -- e cada
        linha tem exatamente uma célula por coluna, filha direta da
        linha: nada empilhado numa célula só.
        """
        corpo = cliente.get(reverse(rota)).content.decode()
        tabela = corpo[corpo.index('class="mod-tabela mod-tabela-colunas') :]
        cabecalho = tabela[: tabela.index('<div class="mod-linha')]
        rotulos = [
            re.sub(r"<[^>]+>", "", r).strip()
            for r in re.findall(r'<span role="columnheader"[^>]*>(.*?)</span>', cabecalho, re.S)
        ]

        assert rotulos == COLUNAS[rota]
        assert "mod-celulas-meio" not in tabela
        primeira_linha = tabela.split('<div class="mod-linha')[1]
        assert primeira_linha.count('role="cell"') == len(COLUNAS[rota])

    def test_as_celulas_do_meio_sao_div_e_nao_span(self):
        """
        As regras de cartão da tabela de Modelos alcançam
        `.mod-linha > span:nth-child(...)`; as destas grades não podem
        herdar aquela arrumação por acidente.
        """
        for arquivo in ("users.html", "letters.html", "partners.html"):
            marcacao = pathlib.Path("templates/backoffice", arquivo).read_text(encoding="utf-8")

            assert 'role="cell"' in marcacao, arquivo
            assert not re.search(r'<span[^>]*role="cell"', marcacao), arquivo


class TestFiltrosPreservados:
    def test_usuarios_a_situacao_preserva_a_busca(self, cliente, com_linhas):
        resposta = cliente.get(reverse("backoffice:users"), {"q": "ana"})
        opcoes = {o["valor"]: o["url"] for o in resposta.context["filtros_situacao"]}

        assert opcoes["inativos"] == f"{reverse('backoffice:users')}?q=ana&status=inativos"
        assert opcoes[""] == f"{reverse('backoffice:users')}?q=ana"

    def test_usuarios_a_busca_leva_a_situacao(self, cliente, com_linhas):
        corpo = cliente.get(reverse("backoffice:users"), {"status": "inativos"}).content.decode()

        assert '<input type="hidden" name="status" value="inativos">' in corpo

    def test_usuarios_situacao_desconhecida_nao_acende_nada_errado(self, cliente, com_linhas):
        resposta = cliente.get(reverse("backoffice:users"), {"status": "todos-os-reis"})

        atual = [o["valor"] for o in resposta.context["filtros_situacao"] if o["atual"]]
        assert atual == [""]

    def test_cartas_o_estado_preserva_idioma_e_usuario(self, cliente, com_linhas, user):
        resposta = cliente.get(
            reverse("backoffice:letters"), {"language": "fr", "user": str(user.pk)}
        )
        rascunho = next(o for o in resposta.context["filtros_estado"] if o["valor"] == "rascunho")

        assert "language=fr" in rascunho["url"]
        assert f"user={user.pk}" in rascunho["url"]
        assert "state=rascunho" in rascunho["url"]

    def test_cartas_as_pilulas_sao_idioma_e_usuario(self, cliente, com_linhas, user):
        resposta = cliente.get(reverse("backoffice:letters"), {"state": "rascunho"})
        idioma, usuario = resposta.context["filtros_pilula"]

        assert idioma["rotulo"] == "Idioma" and usuario["rotulo"] == "Usuário"
        assert any(o["valor"] == str(user.pk) for o in usuario["opcoes"])
        assert all("state=rascunho" in o["url"] for o in idioma["opcoes"])

    def test_cartas_o_periodo_leva_os_outros_filtros(self, cliente, com_linhas, user):
        corpo = cliente.get(
            reverse("backoffice:letters"), {"state": "rascunho", "user": str(user.pk)}
        ).content.decode()
        periodo = corpo[corpo.index('class="mod-periodo"') :]
        periodo = periodo[: periodo.index("</form>")]

        assert '<input type="hidden" name="state" value="rascunho">' in periodo
        assert f'<input type="hidden" name="user" value="{user.pk}">' in periodo
        assert 'name="from"' in periodo and 'name="to"' in periodo

    def test_cartas_o_periodo_leva_a_busca_e_a_quantidade(self, cliente, com_linhas):
        corpo = cliente.get(
            reverse("backoffice:letters"), {"q": "DSR", "page_size": "30"}
        ).content.decode()
        periodo = corpo[corpo.index('class="mod-periodo"') :]
        periodo = periodo[: periodo.index("</form>")]

        assert '<input type="hidden" name="q" value="DSR">' in periodo
        assert '<input type="hidden" name="page_size" value="30">' in periodo

    def test_cartas_trocar_de_filtro_volta_a_primeira_pagina(self, cliente, com_linhas):
        resposta = cliente.get(reverse("backoffice:letters"), {"page": "2"})

        assert all("page=" not in o["url"] for o in resposta.context["filtros_estado"])


def _minimo(colunas, vao, respiro):
    """Soma das colunas fixas (e dos mínimos de `minmax`), dos vãos e do respiro."""
    total = 0
    for coluna in re.findall(r"minmax\((\d+)px,[^)]*\)|(\d+)px", colunas):
        total += int(coluna[0] or coluna[1])
    quantas = len(re.findall(r"minmax\([^)]*\)|\d+px", colunas))
    return total + (quantas - 1) * vao + 2 * respiro


def _colunas(css, grade, inicio=0):
    regra = css[css.index(f".{grade} .mod-linha {{", inicio) :]
    return re.search(r"grid-template-columns:\s*([^;]+);", regra).group(1)


def _largura_minima(css, grade, inicio=0):
    regra = css[css.index(f".{grade} .mod-linha {{", inicio) :]
    return int(re.search(r"min-width:\s*(\d+)px;", regra[: regra.index("}")]).group(1))


class TestAGradeCabe:
    """
    A largura útil do Backoffice (menu de 240px, 40px de respiro de cada
    lado): 943px numa janela de 1280 com barra de rolagem, ~1063 a 1400,
    861px a 1181 para a grade de Parceiros.

    Usuários e Cartas declaram uma largura MÍNIMA igual à soma dos
    mínimos das colunas, dos vãos (8px) e do respiro (14px): abaixo dela
    a tabela rola dentro do cartão -- e ela cabe inteira a 1280.
    """

    def test_parceiros_cabe_antes_de_virar_cartao(self):
        css = CSS.read_text(encoding="utf-8")

        assert _minimo(_colunas(css, "mod-tabela-parceiros"), 12, 18) <= 1181 - 320

    @pytest.mark.parametrize("grade", ["mod-tabela-usuarios", "mod-tabela-cartas"])
    def test_a_largura_minima_e_a_soma_das_colunas_e_cabe_a_1280(self, grade):
        css = CSS.read_text(encoding="utf-8")

        assert _minimo(_colunas(css, grade), 8, 14) == _largura_minima(css, grade)
        assert _largura_minima(css, grade) <= 943

    def test_cartas_a_partir_de_1400_cabe_com_o_nome_do_idioma(self):
        css = CSS.read_text(encoding="utf-8")
        largo = css.index("@media (min-width: 1400px)")

        colunas = _colunas(css, "mod-tabela-cartas", largo)
        assert _minimo(colunas, 8, 14) == _largura_minima(css, "mod-tabela-cartas", largo)
        assert _largura_minima(css, "mod-tabela-cartas", largo) <= 1400 - 17 - 320

    def test_abaixo_da_largura_minima_rola_a_tabela_e_nao_a_pagina(self):
        css = CSS.read_text(encoding="utf-8")
        cartao = css[css.index("@media (max-width: 1023px)") :]

        assert ".mod-tabela-colunas { overflow-x: auto; }" in css
        assert ".mod-tabela-colunas { overflow-x: visible; }" in cartao
        linha_do_cartao = cartao[cartao.index(".mod-tabela-colunas .mod-linha {") :]
        assert "min-width: 0;" in linha_do_cartao[: linha_do_cartao.index("}")]

    def test_colunas_ate_1024_e_cartao_abaixo(self):
        css = CSS.read_text(encoding="utf-8")
        cartao = css[css.index("@media (max-width: 1023px)") :]

        assert ".mod-tabela-colunas .mod-cabecalho-tabela { display: none; }" in cartao
        assert ".mod-tabela-colunas .mod-rotulo-celula {" in cartao

    def test_parceiros_continua_virando_cartao_em_1180(self):
        css = CSS.read_text(encoding="utf-8")
        bloco = css[css.index(".mod-celulas-meio { display: contents; }") :]

        assert "@media (max-width: 1180px)" in bloco
        assert '"nome acoes"' in bloco and '"meio meio"' in bloco


class TestModelosEntre1181E1399:
    """
    A grade de Modelos precisa de 1054px, e entre 1181 e 1399px o
    Backoffice tem menos que isso: o cartão recortava a coluna de ações.
    Nessa faixa -- e só nela -- a TABELA rola para o lado dentro do
    cartão; a página não rola e nenhuma coluna muda.
    """

    def _faixa(self):
        css = CSS.read_text(encoding="utf-8")
        inicio = css.index("@media (min-width: 1181px) and (max-width: 1399px)")
        return css, css[inicio : css.index("\n}\n", inicio)]

    def test_so_a_tabela_rola_e_so_nessa_faixa(self):
        css, faixa = self._faixa()

        assert ".mod-tabela-modelos { overflow-x: auto; }" in faixa
        assert css.count(".mod-tabela-modelos { overflow-x: auto; }") == 1

    def test_a_largura_minima_e_a_da_grade_de_modelos(self):
        css, faixa = self._faixa()
        grade = re.search(
            r"\.mod-cabecalho-tabela,\s*\.mod-linha \{\s*display: grid;"
            r"\s*grid-template-columns:\s*([^;]+);",
            css,
        ).group(1)

        assert f"min-width: {_minimo(grade, 12, 18)}px;" in faixa

    def test_a_biblioteca_marca_a_tabela_dela(self):
        marcacao = pathlib.Path("templates/backoffice/document_library.html").read_text(
            encoding="utf-8"
        )

        assert 'class="mod-tabela mod-tabela-modelos" role="table"' in marcacao
