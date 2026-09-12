"""
Ferramenta de desenvolvimento: gera o PDF de amostra e imagens PNG para
conferencia visual, lado a lado com o PDF oficial.

Por que existe: `extract_text()` prova que o texto certo esta no PDF, mas
nao prova que ele esta no LUGAR certo, com o peso certo, sem sobrepor
outra coisa. So uma imagem raster mostra isso.

Tres saidas:

  * `preview_fr.png`    -- so a pagina gerada;
  * `comparacao_fr.png` -- oficial em cima, gerada embaixo, para olhar;
  * `diff_fr.png`       -- onde as duas diferem (deveria ser exatamente
                           as areas variaveis, e nada mais).

A comprovacao automatica dessa mesma ideia esta em
`tests/test_pdfengine_render_fr.py::TestFidelidadeVisual`, que compara as
duas paginas pixel a pixel fora das areas variaveis. Este script e para
quando se quer OLHAR o resultado.

Uso:
    python -m pdfengine.tools.render_preview [pasta_de_saida]

Sem argumento, salva em `pdfengine/tools/` (fora do controle de versao --
ver .gitignore).
"""

import sys
from pathlib import Path

import pypdfium2 as pdfium

from pdfengine.render import BASE_PDF_PATH, render_invitation_letter_fr
from pdfengine.sample_data import FR_SAMPLE_DATA

DEFAULT_DIR = Path(__file__).parent


def _rasterizar(pdf_bytes, scale):
    return pdfium.PdfDocument(pdf_bytes)[0].render(scale=scale).to_pil()


def render_preview_png(output_path: Path, *, scale: float = 2.0) -> Path:
    """A pagina gerada com os dados de amostra, como PNG."""
    _rasterizar(render_invitation_letter_fr(FR_SAMPLE_DATA), scale).save(output_path)
    return output_path


def render_comparison_png(output_dir: Path, *, scale: float = 2.0):
    """
    Salva a comparacao com o documento oficial: as duas paginas empilhadas
    e um mapa das diferencas. Devolve os caminhos gravados.
    """
    from PIL import Image, ImageChops

    oficial = _rasterizar(BASE_PDF_PATH.read_bytes(), scale)
    gerada = _rasterizar(render_invitation_letter_fr(FR_SAMPLE_DATA), scale)

    lado_a_lado = Image.new(
        "RGB", (max(oficial.width, gerada.width), oficial.height + gerada.height + 8), "white"
    )
    lado_a_lado.paste(oficial.convert("RGB"), (0, 0))
    lado_a_lado.paste(gerada.convert("RGB"), (0, oficial.height + 8))

    diferenca = ImageChops.difference(oficial.convert("L"), gerada.convert("L"))
    mapa = diferenca.point(lambda v: 0 if v else 255)

    caminho_cmp = output_dir / "comparacao_fr.png"
    caminho_diff = output_dir / "diff_fr.png"
    lado_a_lado.save(caminho_cmp)
    mapa.save(caminho_diff)
    return caminho_cmp, caminho_diff


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    destino.mkdir(parents=True, exist_ok=True)

    preview = render_preview_png(destino / "preview_fr.png")
    comparacao, diff = render_comparison_png(destino)

    print(f"Página gerada:      {preview}")
    print(f"Comparação:         {comparacao}")
    print(f"Mapa de diferenças: {diff}")
