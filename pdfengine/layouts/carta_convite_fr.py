"""
Mapa de layout do PDF oficial da Carta Convite (frances).

Todas as coordenadas abaixo foram MEDIDAS diretamente do arquivo
`pdfengine/assets/fr/Modelo-Carta-Convite-FR.pdf` com `pypdf`
(`page.extract_text(visitor_text=...)` para as posicoes de texto,
composicao manual de `tm`/`cm` para coordenadas de dispositivo, e
`ContentStream` para os retangulos da tabela) -- nenhum numero aqui foi
estimado visualmente. Ver `pdfengine/docs/` para o metodo completo.

Sistema de coordenadas: pontos PDF, origem no canto inferior esquerdo,
eixo Y para cima -- o mesmo sistema do reportlab, entao estes valores vao
direto para `canvas.drawString()` sem nenhuma conversao.

Este e o UNICO lugar do projeto com numeros de posicao/tamanho deste
documento. Nenhum outro modulo deve hardcodar coordenada, fonte ou
tamanho -- isso e o que possibilita, mais adiante, mover este mapa para
dentro de `TemplateVersion.layout` (um dado administravel) sem tocar no
motor de renderizacao.
"""

from dataclasses import dataclass

from pdfengine import fontconfig
from pdfengine.measure import Run

# ---------------------------------------------------------------------------
# Pagina e fontes
# ---------------------------------------------------------------------------

PAGE_WIDTH = 596.0
PAGE_HEIGHT = 842.0

# As fontes do overlay vem de `pdfengine.fontconfig` -- Liberation Sans,
# livre (SIL OFL 1.1) e desenhada como clone da Arial do documento
# oficial, embutida no PDF para o resultado nao depender de fonte
# instalada no servidor nem da substituicao que cada leitor faria. O
# porque completo, com as medicoes, esta no docstring daquele modulo.
FONT_REGULAR = fontconfig.REGULAR
FONT_BOLD = fontconfig.BOLD

BODY_SIZE = 11.0
LEADING = 13.5
MIN_FONT_SIZE = 9.0

# Margens do corpo do texto. Medidas: as linhas comecam em x=49.6 e
# terminam entre x=545.2 e x=545.9 -- o documento justifica os
# paragrafos (ver `TextBox.justify`) e o proprio gerador original varia
# um pouco no alvo da direita, entao 546.0 e a borda util arredondada.
BODY_LEFT = 49.6
BODY_RIGHT = 546.0

# Limite direito da area da assinatura. Medido: o logo do IBZ comeca em
# x=373,5 e a linha da assinatura do documento vai de x=49,6 a x=239,2.
# 370 deixa folga para um nome bem mais longo que o da amostra sem nunca
# encostar no logo.
SIGNATURE_AREA_RIGHT = 370.0


# ---------------------------------------------------------------------------
# Estruturas do mapa
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rect:
    """Uma area retangular, em pontos PDF (x, y = canto inferior esquerdo)."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class TextBox:
    """Onde e como o texto de uma zona e desenhado."""

    x: float
    first_baseline_y: float
    width: float
    max_lines: int
    leading: float = LEADING
    font_size: float = BODY_SIZE
    min_font_size: float = MIN_FONT_SIZE
    # O documento oficial justifica os paragrafos do corpo: todas as
    # linhas menos a ultima sao esticadas ate a margem direita (medido:
    # espacos de 3,78 a 4,55pt contra 3,06pt do espaco natural, com as
    # linhas terminando exatamente em BODY_RIGHT). Celulas de tabela e
    # linhas soltas nao sao justificadas.
    justify: bool = False


@dataclass(frozen=True)
class FieldRef:
    """Um espaço reservado dentro de `Zone.runs`, referenciando uma chave
    de dado. O renderer substitui por um `Run` de verdade, com o valor já
    resolvido."""

    key: str
    bold: bool = False


@dataclass(frozen=True)
class Zone:
    """
    Uma area variavel do documento: a mascara que cobre o valor de
    amostra do PDF original, a caixa de texto onde o valor real e
    desenhado, e o "molde" de Runs/FieldRefs que descreve a mistura de
    texto fixo e variavel dessa zona (ver secao 3 da especificacao em
    pdfengine/docs/).
    """

    key: str
    mask: Rect
    box: TextBox
    runs: tuple


# ---------------------------------------------------------------------------
# As oito zonas variaveis do documento
# ---------------------------------------------------------------------------
# A mascara de cada zona cobre a AREA RESERVADA inteira (nao so o
# tamanho do valor de amostra) -- assim um valor mais curto que a
# amostra nunca deixa sobra do texto original visivel por baixo.

ZONES = (
    # 3.1 — paragrafo do anfitriao ("Je soussignée, ..., invite par la présente :")
    Zone(
        key="host_paragraph",
        # A mascara cobre as TRES linhas do texto de amostra (linhas de
        # base em 682,9 / 669,4 / 655,9), com folga para acentos e
        # descidas -- e para ai. Nao pode descer ate a tabela: as celulas
        # sao retangulos com contorno, e o de cima fecha em y=640,25; uma
        # mascara que chegasse la apagaria a borda superior da tabela
        # inteira. (Invariante coberto por teste.)
        mask=Rect(x=45.0, y=652.0, width=506.0, height=42.0),
        box=TextBox(
            x=BODY_LEFT,
            first_baseline_y=682.9,
            width=BODY_RIGHT - BODY_LEFT,
            # Tres linhas, como no original. Uma quarta linha caberia em
            # altura (base em 642,4), mas as descidas dela chegariam a
            # 640,1 -- dentro do traco da borda superior da tabela, que
            # fecha em 640,25. Preso a tres linhas, um texto mais longo
            # que o da amostra reduz a fonte (ate MIN_FONT_SIZE) em vez de
            # encostar num elemento fixo; se nem assim couber, e erro
            # explicito.
            max_lines=3,
            justify=True,
        ),
        runs=(
            Run("Je soussignée, "),
            FieldRef("host_name", bold=True),
            Run(", née le "),
            FieldRef("host_birth"),
            Run(", de nationalité "),
            FieldRef("host_nationality"),
            Run(", titulaire de la carte d’identité "),
            FieldRef("host_document_type"),
            Run(" n° "),
            FieldRef("host_document", bold=True),
            Run(", domiciliée au "),
            FieldRef("host_address", bold=True),
            Run(", téléphone "),
            FieldRef("host_phone", bold=True),
            Run(", invite par la présente :"),
        ),
    ),
    # Item 2 da lista — endereço citado uma segunda vez.
    Zone(
        key="item2_address",
        mask=Rect(x=80.0, y=440.0, width=466.0, height=27.0),
        box=TextBox(
            x=85.6,
            first_baseline_y=457.9,
            width=BODY_RIGHT - 85.6,
            max_lines=2,
            justify=True,
        ),
        runs=(
            Run(
                "Pendant toute la durée de son séjour en Belgique, la personne "
                "invitée sera hébergée à mon domicile situé à l’adresse suivante : "
            ),
            FieldRef("host_address", bold=True),
        ),
    ),
    # Linha de fechamento — "Fait à {place}, le {document_date}".
    Zone(
        key="closing_line",
        mask=Rect(x=326.0, y=195.0, width=220.0, height=30.0),
        box=TextBox(
            x=331.0,
            # Largura propria, nao BODY_RIGHT - x: com o espacamento
            # natural esta linha pede 215,2pt, e o gerador do documento
            # original coube em 214,9pt apertando UM dos espacos (medido:
            # 2,79pt contra 3,06pt dos outros). Em vez de imitar esse
            # aperto, reservamos 216pt -- 1pt a mais que a margem nominal,
            # invisivel, e a linha sai inteira como no original. Uma
            # cidade mais longa que a da amostra quebra para a 2a linha,
            # que e para isso que existe `max_lines=2`.
            first_baseline_y=210.4,
            width=216.0,
            max_lines=2,
        ),
        runs=(
            Run("Fait à "),
            FieldRef("place"),
            Run(", le "),
            FieldRef("document_date"),
        ),
    ),
    # Tabela do convidado — 4 células isoladas + 1 célula composta (Durée).
    # Coordenadas dos retângulos das células medidas via ContentStream
    # (linhas divisórias em y = 640.5 / 616.5 / 591.5 / 566.5 / 541.5 /
    # 517.5; coluna de valor entre x = 167.5 e x = 546.5).
    Zone(
        key="table_guest_name",
        mask=Rect(x=169.1, y=617.2, width=376.0, height=22.0),
        box=TextBox(x=172.6, first_baseline_y=624.4, width=368.9, max_lines=1),
        runs=(FieldRef("guest_name"),),
    ),
    Zone(
        key="table_guest_nationality",
        mask=Rect(x=169.1, y=592.5, width=376.0, height=22.0),
        box=TextBox(x=172.6, first_baseline_y=599.7, width=368.9, max_lines=1),
        runs=(FieldRef("guest_nationality"),),
    ),
    Zone(
        key="table_guest_birth",
        mask=Rect(x=169.1, y=567.8, width=376.0, height=22.0),
        box=TextBox(x=172.6, first_baseline_y=574.9, width=368.9, max_lines=1),
        runs=(FieldRef("guest_birth"),),
    ),
    Zone(
        key="table_guest_passport",
        mask=Rect(x=169.1, y=543.0, width=376.0, height=22.0),
        box=TextBox(x=172.6, first_baseline_y=550.2, width=368.9, max_lines=1),
        runs=(FieldRef("guest_passport"),),
    ),
    Zone(
        key="table_duration",
        mask=Rect(x=169.1, y=518.2, width=376.0, height=22.0),
        box=TextBox(x=172.6, first_baseline_y=525.4, width=368.9, max_lines=1),
        runs=(
            Run("du "),
            FieldRef("arrival_date"),
            Run(" au "),
            FieldRef("departure_date"),
            Run(" ("),
            FieldRef("duration_days"),
            Run(" jours)"),
        ),
    ),
    # Nome sob a linha de assinatura.
    Zone(
        key="signature_name",
        # A area do nome NAO pode ir ate a margem direita do corpo: nesta
        # faixa de altura estao o logo do IBZ (x 373,5..475,8) e o QR Code
        # (x 466,7..552,2). Uma mascara larga demais apagaria uma fatia
        # horizontal dos dois -- as abas preta e amarela da bandeira do
        # logo somem e o topo do QR Code fica em branco, o que o torna
        # ilegivel. Por isso a area para aqui, bem antes do logo.
        # (Invariante coberto por teste: nenhuma mascara pode cruzar uma
        # imagem do documento.)
        # Altura medida a tinta, nao estimada: o nome de amostra ocupa
        # y=146,0..153,8; logo acima, a LINHA da assinatura (os
        # sublinhados) ocupa y=157,4..158,0; logo abaixo, "Signature de
        # l'invitante" ocupa y=135,2..140,4. A mascara fica entre os dois,
        # com folga -- indo ate 158 ela apagava uma fatia da linha da
        # assinatura. (Invariante coberto por teste.)
        mask=Rect(x=45.0, y=143.0, width=SIGNATURE_AREA_RIGHT - 45.0, height=13.0),
        box=TextBox(
            x=BODY_LEFT,
            first_baseline_y=145.9,
            width=SIGNATURE_AREA_RIGHT - BODY_LEFT,
            max_lines=1,
        ),
        runs=(FieldRef("signature_name", bold=True),),
    ),
)

# Todas as chaves de dado que o documento realmente usa -- a lista de
# validação (`render._validate_data`) vem daqui, não de uma lista
# mantida à mão em outro lugar.
REQUIRED_FIELDS = tuple(
    sorted(
        {ref.key for zone in ZONES for ref in zone.runs if isinstance(ref, FieldRef)}
    )
)
