"""
Renderer da Carta Convite oficial (frances).

Estrategia hibrida obrigatoria: o PDF oficial e a base/background
IMUTAVEL -- titulo, textos juridicos, bordas da tabela, bandeira, logo
IBZ, QR Code e a linha de assinatura vem inalterados dele. So as zonas
variaveis (`pdfengine.layouts.carta_convite_fr.ZONES`) sao mascaradas
(pintadas de branco) e redesenhadas por cima, numa camada de overlay
gerada com reportlab e fundida ao original com pypdf.

Biblioteca pura: nao importa Django, nao conhece request, usuario
autenticado nem sessao. Recebe um dict ja resolvido e devolve bytes.
"""

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from pdfengine.exceptions import (
    BasePdfUnavailableError,
    MissingSnapshotDataError,
    UnrenderableCharacterError,
)
from pdfengine.fontconfig import register_fonts
from pdfengine.layouts.carta_convite_fr import (
    FONT_BOLD,
    FONT_REGULAR,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    REQUIRED_FIELDS,
    ZONES,
    FieldRef,
)
from pdfengine.measure import Run, layout_runs, line_width
from pdfengine.redact import redact_page_content
from pdfengine.textnorm import (
    describe_characters,
    normalize_for_document,
    unsupported_characters,
)

BASE_PDF_PATH = Path(__file__).parent / "assets" / "fr" / "Modelo-Carta-Convite-FR.pdf"


def _read_base_pdf():
    """
    Abre o PDF oficial que serve de base. Falha explicitamente se ele
    nao estiver la ou nao puder ser lido -- sem a base nao existe
    documento, porque todo o conteudo fixo vem dela.
    """
    if not BASE_PDF_PATH.is_file():
        raise BasePdfUnavailableError(
            f"O PDF oficial de base não foi encontrado em {BASE_PDF_PATH}."
        )
    try:
        reader = PdfReader(str(BASE_PDF_PATH))
        if not reader.pages:
            raise BasePdfUnavailableError(
                f"O PDF oficial de base ({BASE_PDF_PATH}) não tem nenhuma página."
            )
    except BasePdfUnavailableError:
        raise
    except Exception as exc:
        raise BasePdfUnavailableError(
            f"O PDF oficial de base ({BASE_PDF_PATH}) não pôde ser lido: {exc}"
        ) from exc
    return reader


def _validate_data(data):
    missing = [key for key in REQUIRED_FIELDS if not str(data.get(key, "")).strip()]
    if missing:
        raise MissingSnapshotDataError(
            "Dados obrigatórios ausentes ou vazios para gerar o PDF: "
            + ", ".join(missing)
        )


def _resolve_runs(zone_runs, data):
    """
    Troca cada `FieldRef` pelo valor real, ja na forma que o documento
    usa (ver `pdfengine.textnorm`). O texto fixo do layout passa
    inalterado -- ele ja esta escrito com os caracteres do original.
    """
    resolved = []
    for item in zone_runs:
        if isinstance(item, FieldRef):
            texto = normalize_for_document(data[item.key])
            resolved.append(Run(text=texto, bold=item.bold))
        else:
            resolved.append(item)
    return resolved


def _check_renderable(runs, zone_key):
    """
    Interrompe se algum caractere nao existir na fonte embutida -- senao
    o reportlab desenharia um glifo vazio e o PDF sairia errado em
    silencio.
    """
    for run in runs:
        fonte = FONT_BOLD if run.bold else FONT_REGULAR
        faltando = unsupported_characters(run.text, fonte)
        if faltando:
            raise UnrenderableCharacterError(
                f'A fonte "{fonte}" não tem como desenhar '
                f"{describe_characters(faltando)} — presente(s) no campo "
                f'"{zone_key}". O PDF não foi gerado para não sair com '
                "caracteres em branco."
            )


def _draw_zone(c, zone, data):
    runs = _resolve_runs(zone.runs, data)
    _check_renderable(runs, zone.key)
    laid_out = layout_runs(
        runs,
        max_width=zone.box.width,
        max_lines=zone.box.max_lines,
        font_size=zone.box.font_size,
        min_font_size=zone.box.min_font_size,
        regular_font=FONT_REGULAR,
        bold_font=FONT_BOLD,
    )

    size = laid_out.font_size
    space = c.stringWidth(" ", FONT_REGULAR, size)
    last_index = len(laid_out.lines) - 1

    y = zone.box.first_baseline_y
    for index, line in enumerate(laid_out.lines):
        # Justificacao: o documento oficial estica os espacos das linhas
        # do meio ate a margem direita e deixa a ULTIMA linha do
        # paragrafo com espacamento natural. Uma linha sozinha tambem
        # fica natural -- ela e a ultima.
        gap = space
        if zone.box.justify and index < last_index and len(line) > 1:
            natural = line_width(line, size, FONT_REGULAR, FONT_BOLD)
            gap = space + (zone.box.width - natural) / (len(line) - 1)

        x = zone.box.x
        for word in line:
            # Cada pedaco da palavra e desenhado com o seu proprio peso:
            # em "Dubois," o nome sai em negrito e a virgula em regular,
            # como no documento oficial.
            for part in word.parts:
                font = FONT_BOLD if part.bold else FONT_REGULAR
                c.setFont(font, size)
                c.drawString(x, y, part.text)
                x += c.stringWidth(part.text, font, size)
            x += gap
        y -= zone.box.leading


def _build_overlay(data):
    register_fonts()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))

    # Primeiro todas as máscaras (retângulos brancos, sem contorno), só
    # depois o texto -- assim uma zona nunca pinta por cima do texto de
    # outra, mesmo que suas áreas fiquem próximas.
    c.setFillColorRGB(1, 1, 1)
    for zone in ZONES:
        c.rect(zone.mask.x, zone.mask.y, zone.mask.width, zone.mask.height, stroke=0, fill=1)

    c.setFillColorRGB(0, 0, 0)
    for zone in ZONES:
        _draw_zone(c, zone, data)

    c.save()
    buffer.seek(0)
    return buffer


def render_invitation_letter_fr(data: dict) -> bytes:
    """
    Gera o PDF da Carta Convite oficial francesa a partir de `data`, um
    dict simples com todas as chaves de
    `pdfengine.layouts.carta_convite_fr.REQUIRED_FIELDS` já resolvidas
    como texto (datas e números já formatados como string).

    Nunca inventa um valor ausente: levanta `MissingSnapshotDataError`.
    Nunca deixa um texto invadir outra área: levanta `TextOverflowError`
    (de `pdfengine.measure`) se algum campo não couber mesmo com a fonte
    reduzida ao mínimo.

    O texto de amostra do PDF oficial (nas zonas variáveis) é removido do
    conteúdo da página base antes da fusão -- não só coberto visualmente
    -- para que extrair/copiar o texto do PDF final nunca revele os
    valores de amostra por baixo dos valores reais (ver
    `pdfengine.redact`).
    """
    _validate_data(data)

    # A base primeiro: sem ela nao ha documento nenhum a gerar, entao nao
    # faz sentido montar o overlay (nem deixar um erro de overflow
    # aparecer na frente de um problema de infraestrutura).
    base_reader = _read_base_pdf()
    overlay_reader = PdfReader(_build_overlay(data))

    # A pagina precisa estar anexada a um writer ANTES de ter seu
    # conteudo trocado (redacao) -- fazer isso numa pagina solta de um
    # reader esta depreciado no pypdf.
    writer = PdfWriter()
    writer.append(base_reader)
    page = writer.pages[0]

    redact_page_content(page, [zone.mask for zone in ZONES])
    page.merge_page(overlay_reader.pages[0])

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
