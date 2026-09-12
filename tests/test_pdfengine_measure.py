"""
Testes de `pdfengine.measure`: quebra de linha determinística e detecção
de overflow. Biblioteca pura -- sem Django, sem banco de dados.
"""

import pytest

from pdfengine.exceptions import TextOverflowError
from pdfengine.measure import Run, layout_runs


def _words(laid_out):
    return [[w.text for w in line] for line in laid_out.lines]


class TestQuebraDeLinha:
    def test_texto_curto_fica_numa_linha_so(self):
        laid_out = layout_runs(
            [Run("Olá mundo")],
            max_width=500,
            max_lines=3,
            font_size=11,
            min_font_size=9,
            regular_font="Helvetica",
            bold_font="Helvetica-Bold",
        )
        assert _words(laid_out) == [["Olá", "mundo"]]

    def test_texto_longo_quebra_em_varias_linhas(self):
        texto = " ".join(["palavra"] * 30)
        laid_out = layout_runs(
            [Run(texto)],
            max_width=150,
            max_lines=20,
            font_size=11,
            min_font_size=9,
            regular_font="Helvetica",
            bold_font="Helvetica-Bold",
        )
        assert len(laid_out.lines) > 1
        # nenhuma palavra foi perdida
        total_palavras = sum(len(line) for line in laid_out.lines)
        assert total_palavras == 30

    def test_reduz_a_fonte_antes_de_estourar_max_lines(self):
        texto = " ".join(["palavra"] * 12)
        laid_out = layout_runs(
            [Run(texto)],
            max_width=200,
            max_lines=2,
            font_size=11,
            min_font_size=6,
            regular_font="Helvetica",
            bold_font="Helvetica-Bold",
        )
        assert len(laid_out.lines) <= 2
        assert laid_out.font_size < 11

    def test_estoura_mesmo_no_tamanho_minimo_levanta_erro(self):
        texto = " ".join(["palavra"] * 12)
        with pytest.raises(TextOverflowError):
            layout_runs(
                [Run(texto)],
                max_width=200,
                max_lines=1,
                font_size=11,
                min_font_size=10,
                regular_font="Helvetica",
                bold_font="Helvetica-Bold",
            )

    def test_uma_palavra_isolada_maior_que_a_largura_nao_trava(self):
        """Uma palavra sozinha que não cabe ainda assim vira uma linha
        (não há como quebrar no meio de uma palavra) -- o overflow, se
        houver, aparece no número de linhas, não num loop infinito."""
        laid_out = layout_runs(
            [Run("a" * 200)],
            max_width=50,
            max_lines=5,
            font_size=11,
            min_font_size=9,
            regular_font="Helvetica",
            bold_font="Helvetica-Bold",
        )
        assert len(laid_out.lines) == 1


class TestUniaoDePontuacao:
    """
    Regressão: uma pontuação fixa colada ao fim de um valor variável (ex.:
    ", née le" logo após o nome) não pode virar um token isolado com um
    espaço artificial antes dela.
    """

    def test_pontuacao_colada_ao_valor_variavel_nao_ganha_espaco(self):
        runs = [Run("Claire Dubois", bold=True), Run(", née le "), Run("14/03/1985")]
        laid_out = layout_runs(
            runs,
            max_width=1000,
            max_lines=1,
            font_size=11,
            min_font_size=9,
            regular_font="Helvetica",
            bold_font="Helvetica-Bold",
        )
        words = [w.text for w in laid_out.lines[0]]
        assert words == ["Claire", "Dubois,", "née", "le", "14/03/1985"]

    def test_palavra_colada_preserva_o_peso_de_cada_pedaco(self):
        """
        No documento oficial a virgula logo depois do nome em negrito NAO
        e negrito (verificado na medicao do PDF: ela e um objeto de texto
        proprio, com a fonte regular). Entao "Dubois," e uma palavra so,
        mas com dois pesos dentro dela.
        """
        runs = [Run("Claire Dubois", bold=True), Run(", née le ")]
        laid_out = layout_runs(
            runs,
            max_width=1000,
            max_lines=1,
            font_size=11,
            min_font_size=9,
            regular_font="Helvetica",
            bold_font="Helvetica-Bold",
        )
        by_text = {w.text: w for w in laid_out.lines[0]}

        pedacos = [(p.text, p.bold) for p in by_text["Dubois,"].parts]
        assert pedacos == [("Dubois", True), (",", False)]
        assert [(p.text, p.bold) for p in by_text["Claire"].parts] == [("Claire", True)]
        assert [(p.text, p.bold) for p in by_text["née"].parts] == [("née", False)]

    def test_largura_da_palavra_mista_soma_os_dois_pesos(self):
        from reportlab.pdfbase.pdfmetrics import stringWidth

        runs = [Run("Dubois", bold=True), Run(", ")]
        laid_out = layout_runs(
            runs,
            max_width=1000,
            max_lines=1,
            font_size=11,
            min_font_size=9,
            regular_font="Helvetica",
            bold_font="Helvetica-Bold",
        )
        palavra = laid_out.lines[0][0]
        esperado = stringWidth("Dubois", "Helvetica-Bold", 11) + stringWidth(
            ",", "Helvetica", 11
        )
        assert palavra.width(11, "Helvetica", "Helvetica-Bold") == pytest.approx(esperado)

    def test_parenteses_colados_no_valor_seguinte(self):
        runs = [Run(" ("), Run("15"), Run(" jours)")]
        laid_out = layout_runs(
            runs,
            max_width=1000,
            max_lines=1,
            font_size=11,
            min_font_size=9,
            regular_font="Helvetica",
            bold_font="Helvetica-Bold",
        )
        words = [w.text for w in laid_out.lines[0]]
        assert words == ["(15", "jours)"]
