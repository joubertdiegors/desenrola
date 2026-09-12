"""
Medicao de texto e quebra de linha determinística.

Biblioteca pura: so usa `reportlab.pdfbase.pdfmetrics` para medir a
largura do texto ANTES de desenhar -- e o que permite detectar overflow
antes de gerar o PDF, em vez de descobrir tarde demais que um texto foi
cortado ou invadiu outra area.

Cada `Run` e um trecho de texto com um peso (negrito ou nao). Uma lista
de Runs representa um paragrafo que mistura texto fixo com texto
variavel -- exatamente o formato das zonas mistas do documento oficial
(ver pdfengine/layouts/carta_convite_fr.py). `layout_runs()` quebra a
lista inteira como um unico fluxo de palavras.

Uma palavra pode MISTURAR pesos internamente, e isso importa: no
documento oficial, "Claire Dubois," tem o nome em negrito e a virgula
logo em seguida em peso normal, ainda que nao haja espaco entre eles
(verificado na medicao do PDF: a virgula e um objeto de texto proprio,
com a fonte regular). Por isso `Word` guarda uma lista de `Segment`, cada
um com o seu peso, em vez de um unico peso para a palavra toda.
"""

from dataclasses import dataclass

from reportlab.pdfbase.pdfmetrics import stringWidth

from pdfengine.exceptions import TextOverflowError

DEFAULT_FONT_STEP = 0.5


@dataclass(frozen=True)
class Run:
    """Um trecho de texto (fixo ou ja com o valor variavel resolvido)."""

    text: str
    bold: bool = False


@dataclass(frozen=True)
class Segment:
    """Um pedaco de palavra com peso uniforme."""

    text: str
    bold: bool


@dataclass(frozen=True)
class Word:
    """
    Uma palavra (nao contem espacos), possivelmente formada por pedacos
    de pesos diferentes -- ver o exemplo de "Dubois," no docstring do
    modulo.
    """

    parts: tuple  # tuple[Segment, ...]

    @property
    def text(self):
        return "".join(part.text for part in self.parts)

    @property
    def bold(self):
        """Peso do primeiro pedaco -- atalho de leitura; quem desenha deve
        percorrer `parts`, nao usar isto."""
        return self.parts[0].bold if self.parts else False

    def width(self, font_size, regular_font, bold_font):
        return sum(
            stringWidth(part.text, bold_font if part.bold else regular_font, font_size)
            for part in self.parts
        )


@dataclass(frozen=True)
class LaidOutText:
    """O resultado de `layout_runs`: linhas de palavras e o tamanho de fonte usado."""

    lines: tuple  # tuple[tuple[Word, ...], ...]
    font_size: float


def _split_words(runs):
    """
    Achata os Runs em palavras, tratando TODOS os Runs como uma unica
    string continua antes de quebrar por espaco -- assim uma pontuacao
    colada ao fim de um valor variavel (o "," logo depois do nome, em
    "Claire Dubois, née le...") vira parte da MESMA palavra, em vez de um
    token isolado com um espaco artificial antes dele.

    Cada palavra preserva a fronteira entre os Runs de origem como
    `Segment`s, para que so a parte que era negrito continue negrito.
    """
    words = []
    parts = []  # Segments ja fechados da palavra atual
    chars = []  # caracteres do Segment atual
    bold = False

    def close_segment():
        if chars:
            parts.append(Segment(text="".join(chars), bold=bold))
            chars.clear()

    def close_word():
        close_segment()
        if parts:
            words.append(Word(parts=tuple(parts)))
            parts.clear()

    for run in runs:
        if chars and run.bold != bold:
            close_segment()
        bold = run.bold
        for ch in run.text:
            if ch == " ":
                close_word()
                continue
            chars.append(ch)
    close_word()
    return words


def _wrap_words(words, font_size, max_width, regular_font, bold_font):
    space_width = stringWidth(" ", regular_font, font_size)
    lines = []
    current = []
    current_width = 0.0
    for word in words:
        width = word.width(font_size, regular_font, bold_font)
        extra = (space_width if current else 0.0) + width
        if current and current_width + extra > max_width:
            lines.append(tuple(current))
            current = [word]
            current_width = width
        else:
            current.append(word)
            current_width += extra
    if current:
        lines.append(tuple(current))
    return tuple(lines)


def line_width(line, font_size, regular_font, bold_font):
    """Largura da linha com espacamento natural (sem justificacao)."""
    if not line:
        return 0.0
    space_width = stringWidth(" ", regular_font, font_size)
    return sum(w.width(font_size, regular_font, bold_font) for w in line) + space_width * (
        len(line) - 1
    )


def layout_runs(
    runs,
    *,
    max_width,
    max_lines,
    font_size,
    min_font_size,
    regular_font,
    bold_font,
    font_step=DEFAULT_FONT_STEP,
):
    """
    Quebra `runs` em linhas que cabem em `max_width` pontos.

    Tenta primeiro com `font_size`; se o resultado tiver mais linhas do
    que `max_lines`, reduz a fonte em `font_step` (nunca abaixo de
    `min_font_size`) e tenta de novo. Se mesmo em `min_font_size` o texto
    ainda exigir mais linhas do que `max_lines`, levanta
    `TextOverflowError` -- nunca corta texto nem deixa sobrepor outra
    area silenciosamente.
    """
    words = _split_words(runs)
    if not words:
        return LaidOutText(lines=((),), font_size=font_size)

    size = font_size
    while True:
        lines = _wrap_words(words, size, max_width, regular_font, bold_font)
        if len(lines) <= max_lines:
            return LaidOutText(lines=lines, font_size=size)
        if size <= min_font_size:
            raise TextOverflowError(
                f"O texto precisaria de {len(lines)} linha(s) para caber em "
                f"{max_width}pt de largura, mas a área reservada permite no "
                f"máximo {max_lines}, mesmo com a fonte reduzida ao mínimo "
                f"({min_font_size}pt)."
            )
        size = max(min_font_size, round(size - font_step, 2))
