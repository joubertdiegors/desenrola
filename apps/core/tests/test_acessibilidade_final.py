"""
As travas de acessibilidade que a auditoria final produziu.

COMO ELAS FORAM ENCONTRADAS
---------------------------
Num navegador de verdade (Edge, por Playwright), vinte telas em cinco
larguras -- 1440, 1280, 834, 390 e 375 --, medindo o que nem o CSS nem
um teste de HTTP contam: rolagem horizontal, elemento fora da tela,
alvo de toque pequeno, coluna de texto estreita, imagem sem alternativa,
controle sem nome, campo sem rótulo, `id` repetido e ordem dos títulos.

O QUE SOBRA AQUI
----------------
O que dá para guardar sem navegador. Medida de pixel não dá -- e por
isso as regras de CSS que produzem os alvos grandes são conferidas no
arquivo, e a estrutura (títulos, rótulos) é conferida no HTML que o
servidor devolve.
"""

import pathlib
import re

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

COMPONENTS = pathlib.Path("static/css/components.css")
LAYOUT = pathlib.Path("static/css/layout.css")

# As telas públicas, e onde encontrar o `<h1>` de cada uma.
PUBLICAS = [
    "core:home",
    "accounts:login",
    "accounts:signup",
    "accounts:password_reset",
]

LOGADAS = [
    "core:dashboard",
    "letters:history",
    "accounts:profile",
]


def publico():
    return Client()


def regra(css, seletor, ate=200):
    texto = css.read_text(encoding="utf-8")
    onde = texto.index(seletor)
    return texto[onde : onde + ate]


# ===========================================================================
# 1. Uma página, um `h1`
# ===========================================================================


class TestUmH1PorPagina:
    """
    É pelo `h1` que um leitor de tela responde "onde eu estou?".

    As telas de conta usavam `<h2>` como título da página -- e o Perfil
    tinha DOIS `h1`, um `d-only` e outro `m-only`: um só na tela, dois no
    documento.
    """

    @pytest.mark.parametrize("rota", PUBLICAS)
    def test_tela_publica_tem_exatamente_um(self, rota):
        html = publico().get(reverse(rota)).content.decode()

        assert html.count("<h1") == 1, f"{rota}: {html.count('<h1')} h1"

    @pytest.mark.parametrize("rota", LOGADAS)
    def test_tela_logada_tem_exatamente_um(self, auth_client, rota):
        html = auth_client.get(reverse(rota)).content.decode()

        assert html.count("<h1") == 1, f"{rota}: {html.count('<h1')} h1"

    def test_a_tela_de_conclusao_tem_um(self, auth_client, letter):
        html = auth_client.get(
            reverse("letters:detail", kwargs={"letter_uuid": letter.uuid})
        ).content.decode()

        assert html.count("<h1") == 1

    def test_o_titulo_das_telas_de_conta_e_o_h1(self):
        """Não um `h2` que parece título por causa do tamanho."""
        html = publico().get(reverse("accounts:signup")).content.decode()
        onde = html.index('class="auth-title"')

        assert "<h1>" in html[onde : onde + 300]

    def test_o_perfil_nao_repete_o_nome_em_dois_cabecalhos(self, auth_client, user):
        html = auth_client.get(reverse("accounts:profile")).content.decode()

        assert html.count("profile-topo") == 1
        assert "profile-avatar-row" not in html


# ===========================================================================
# 2. Os títulos não pulam nível
# ===========================================================================


class TestOrdemDosTitulos:
    """
    Quem navega por títulos numa página longa -- e é assim que se navega
    com leitor de tela -- ouve "nível 1", "nível 3" e não sabe se pulou
    alguma coisa.
    """

    def _niveis(self, html):
        return [int(n) for n in re.findall(r"<h([1-6])[ >]", html)]

    def _pulos(self, html):
        niveis = self._niveis(html)
        return [
            (anterior, atual)
            # `strict=False`: as duas listas TEM tamanhos diferentes de
            # propósito -- a segunda é a primeira deslocada em um.
            for anterior, atual in zip(niveis, niveis[1:], strict=False)
            if atual > anterior + 1
        ]

    @pytest.mark.parametrize("rota", PUBLICAS)
    def test_tela_publica_nao_pula_nivel(self, rota):
        html = publico().get(reverse(rota)).content.decode()

        assert not self._pulos(html), f"{rota}: {self._pulos(html)}"

    @pytest.mark.parametrize("rota", LOGADAS)
    def test_tela_logada_nao_pula_nivel(self, auth_client, rota):
        html = auth_client.get(reverse(rota)).content.decode()

        assert not self._pulos(html), f"{rota}: {self._pulos(html)}"

    def test_o_backoffice_nao_pula_nivel(self, staff_user, client):
        client.force_login(staff_user)

        html = client.get(reverse("backoffice:overview")).content.decode()

        assert not self._pulos(html), self._pulos(html)

    def test_o_titulo_de_cartao_do_backoffice_e_h2(self):
        """
        Eram 46 `h3` logo depois do `h1` da página. O CSS casa as duas
        etiquetas para nenhum cabeçalho esquecido mudar de tamanho.
        """
        marcacao = pathlib.Path("templates/backoffice/system.html").read_text(
            encoding="utf-8"
        )

        assert '<div class="bo-card-head">' in marcacao
        assert "<h3>" not in marcacao
        assert ".bo-card-head h2, .bo-card-head h3" in LAYOUT.read_text(encoding="utf-8")


# ===========================================================================
# 3. Os alvos de toque
# ===========================================================================


class TestAlvosDeToque:
    """
    Medidos no navegador, um a um. O que se guarda aqui é a REGRA que
    produziu cada medida -- pixel não se mede sem navegador.
    """

    @pytest.mark.parametrize(
        "seletor,minimo",
        [
            (".pw-toggle {", 40),
            (".btn-icon-sm {", 40),
            (".btn-sm {", 40),
            (".dropdown-item {", 40),
            (".date-input .date-input-open {", 40),
        ],
    )
    def test_os_controles_pequenos_do_design_system(self, seletor, minimo):
        bloco = regra(COMPONENTS, seletor, 400)
        medida = re.search(r"(?:min-)?height: (\d+)px", bloco)

        assert medida, f"{seletor}: nenhuma altura declarada"
        assert int(medida.group(1)) >= minimo, f"{seletor}: {medida.group(1)}px"

    @pytest.mark.parametrize(
        "seletor", [".user-menu > summary", ".seg-opt {", ".letters-table td .btn {"]
    )
    def test_os_controles_das_telas(self, seletor):
        bloco = regra(LAYOUT, seletor, 300)
        medida = re.search(r"min-height: (\d+)px", bloco)

        assert medida, f"{seletor}: nenhuma altura mínima"
        assert int(medida.group(1)) >= 40, f"{seletor}: {medida.group(1)}px"

    def test_o_interruptor_estica_o_proprio_alvo(self):
        """
        22px de desenho, 44px de alvo -- a faixa invisível não muda um
        pixel do que se vê.
        """
        css = COMPONENTS.read_text(encoding="utf-8")

        assert '.toggle::before { content: ""; position: absolute; inset: -11px 0; }' in css

    def test_a_pergunta_frequente_tem_alvo_de_56px(self):
        """É o que a referência do cliente usa, e vale também no desktop."""
        bloco = regra(LAYOUT, ".faq-pergunta {", 500)

        assert "min-height: 56px" in bloco


# ===========================================================================
# 4. O que já estava certo, e não pode deixar de estar
# ===========================================================================


class TestOQueJaEstavaCerto:
    @pytest.mark.parametrize("rota", PUBLICAS)
    def test_a_pagina_declara_o_idioma(self, rota):
        html = publico().get(reverse(rota)).content.decode()

        assert 'lang="pt"' in html

    @pytest.mark.parametrize("rota", PUBLICAS + ["accounts:signup"])
    def test_nenhuma_imagem_sem_alternativa(self, rota):
        html = publico().get(reverse(rota)).content.decode()
        imagens = re.findall(r"<img[^>]*>", html)

        for imagem in imagens:
            assert "alt=" in imagem or 'aria-hidden="true"' in imagem, imagem

    @pytest.mark.parametrize("rota", PUBLICAS)
    def test_nenhum_id_repetido(self, rota):
        html = publico().get(reverse(rota)).content.decode()
        ids = re.findall(r'\sid="([^"]+)"', html)

        assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]

    def test_o_foco_do_teclado_e_visivel(self):
        """
        Sem isto, quem navega por Tab não sabe onde está -- e o
        navegador não desenha nada porque o projeto tira o contorno
        padrão dos campos.
        """
        css = pathlib.Path("static/css/base.css").read_text(encoding="utf-8")

        assert ":focus-visible" in css

    def test_ha_um_atalho_para_pular_a_navegacao(self, client):
        """
        Quem usa teclado não deve atravessar a barra inteira em toda
        página para chegar ao conteúdo.
        """
        html = client.get(reverse("core:home")).content.decode()

        assert 'href="#main"' in html
        assert 'id="main"' in html
