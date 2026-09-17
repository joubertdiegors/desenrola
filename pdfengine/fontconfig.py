"""
Registro das fontes do overlay no reportlab.

Por que Liberation Sans
-----------------------
O documento oficial usa Arial (embutida como subconjunto:
`/AAAAAA+Arial-BoldMT` e `/BAAAAA+ArialMT`). Arial e proprietaria da
Monotype -- o PDF original pode embuti-la porque quem o gerou tinha
licenca, mas isso NAO nos autoriza a extrair e redistribuir esses bytes
no overlay que nos geramos. Entao precisamos de um substituto livre.

A escolha foi medida, nao estimada (ver `pdfengine/docs/`):

  * Metrica: as larguras dos 114 glifos embutidos no PDF oficial foram
    comparadas uma a uma com Liberation Sans e com a Helvetica padrao do
    PDF. AMBAS batem exatamente (diferenca < 0,5/1000 em em todos os
    glifos) -- Arial foi desenhada como clone metrico da Helvetica, e a
    Liberation Sans como clone metrico da Arial. Reproduzindo as posicoes
    palavra a palavra do paragrafo do anfitriao, o erro acumulado ficou
    em +-0,03pt. Ou seja: pela metrica, as duas empatam.

  * Desenho: o desempate. Helvetica e Arial tem a mesma largura, mas nao
    o mesmo desenho de letra (o 'R', o 'G', o 'a', o 't' e os terminais
    do 'C'/'S'/'e' sao visivelmente diferentes). Liberation Sans foi
    feita justamente para ter o desenho da Arial, nao so a largura dela.

  * Determinismo: Helvetica e uma das 14 fontes padrao do PDF -- ela nao
    e embutida, entao cada leitor a substitui pela fonte que tiver
    (o Acrobat usa a Helvetica de verdade; outros usam Arial ou um
    clone). O resultado visual mudaria de leitor para leitor. Embutindo
    a Liberation Sans, o PDF carrega o proprio desenho e fica igual em
    qualquer lugar -- e o renderer deixa de depender do que esta
    instalado no sistema operacional do servidor.

  * Licenca: SIL Open Font License 1.1 (ver LICENSE.txt nesta pasta),
    que permite expressamente usar, embutir e redistribuir. Nenhuma
    fonte proprietaria entra no projeto.

Os arquivos ficam versionados em `pdfengine/fonts/` de proposito: o
renderer nao pode depender de fonte instalada no sistema.
"""

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONTS_DIR = Path(__file__).parent / "fonts"

# Nomes com que as fontes ficam registradas no reportlab. O layout
# referencia estes nomes, nunca os arquivos. As faces italicas entraram
# com o editor rico (Etapa 3.7): antes delas, italico era recusado --
# desenhar italico com a face regular seria mentir sobre a tipografia.
REGULAR = "LiberationSans"
BOLD = "LiberationSans-Bold"
ITALIC = "LiberationSans-Italic"
BOLD_ITALIC = "LiberationSans-BoldItalic"

_FILES = {
    REGULAR: "LiberationSans-Regular.ttf",
    BOLD: "LiberationSans-Bold.ttf",
    ITALIC: "LiberationSans-Italic.ttf",
    BOLD_ITALIC: "LiberationSans-BoldItalic.ttf",
}

_registered = False


def register_fonts():
    """
    Registra as fontes do overlay no reportlab, uma unica vez por
    processo (registrar de novo e inofensivo, mas reler o arquivo a cada
    PDF gerado seria desperdicio).
    """
    global _registered
    if _registered:
        return

    for name, filename in _FILES.items():
        path = FONTS_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(
                f"Fonte obrigatória do renderer não encontrada: {path}. "
                "Os arquivos .ttf fazem parte do repositório (licença SIL OFL "
                "1.1, ver pdfengine/fonts/LICENSE.txt)."
            )
        pdfmetrics.registerFont(TTFont(name, str(path)))

    _registered = True
