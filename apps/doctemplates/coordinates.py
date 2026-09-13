"""
Conversao entre os tres sistemas de coordenadas do editor visual.

Sao tres, e confundi-los e o erro mais caro possivel neste subsistema --
um documento sai com tudo espelhado verticalmente e ninguem entende por
que. Por isso as contas vivem aqui, sozinhas, sem Django, sem modelo,
sem template: funcoes puras que se testam com numeros.

    1. DOCUMENTO (o que fica gravado)
       pontos, origem em cima a esquerda, Y para baixo.
       E o formato de `TemplateVersion.visual_schema`.

    2. CANVAS (o que o navegador desenha)
       pixels CSS, origem em cima a esquerda, Y para baixo.
       So muda de escala: canvas = documento * zoom.

    3. PDF (o que o renderer vai usar na Etapa 4.2D)
       pontos, origem em BAIXO a esquerda, Y para CIMA.
       E o sistema do reportlab e do pypdf.

A unica diferenca real e entre 1 e 3: a inversao do eixo Y. Entre 1 e 2 e
so multiplicacao.

ATENCAO AO CONVERTER PARA O PDF: uma caixa e ancorada pelo seu topo no
documento e pela sua BASE no PDF. Por isso a conta subtrai tambem a
altura -- esquecer disso desloca todo elemento pela propria altura, um
erro que parece "quase certo" e passa despercebido em elementos baixos.

    y_pdf = altura_da_pagina - y_documento - altura_do_elemento

A funcao inversa existe e e testada em par com a direta: converter ida e
volta tem de devolver o valor original.
"""

# Mesma familia de constantes do contrato; reexportadas para quem so
# precisa de geometria nao ter de importar o schema inteiro.
from .visual_schema import A4_HEIGHT_PT, A4_WIDTH_PT

# Limites de zoom do editor. Abaixo de 25% nada e legivel; acima de 400% o
# canvas fica maior do que qualquer tela util.
ZOOM_MINIMO = 0.25
ZOOM_MAXIMO = 4.0


def clamp_zoom(zoom):
    """Mantem o zoom dentro do que o editor sabe desenhar."""
    return max(ZOOM_MINIMO, min(ZOOM_MAXIMO, float(zoom)))


# ---------------------------------------------------------------------------
# Documento <-> canvas (so escala)
# ---------------------------------------------------------------------------


def pontos_para_pixels(valor, zoom):
    """Um comprimento em pontos, na escala atual do canvas."""
    return float(valor) * float(zoom)


def pixels_para_pontos(valor, zoom):
    """O inverso: o que o mouse mediu em pixels, em pontos do documento."""
    zoom = float(zoom)
    if zoom == 0:
        raise ZeroDivisionError("zoom nao pode ser zero")
    return float(valor) / zoom


def caixa_para_canvas(caixa, zoom):
    """Uma caixa do documento nas coordenadas de tela do canvas."""
    return {
        "x": pontos_para_pixels(caixa["x"], zoom),
        "y": pontos_para_pixels(caixa["y"], zoom),
        "width": pontos_para_pixels(caixa["width"], zoom),
        "height": pontos_para_pixels(caixa["height"], zoom),
    }


def caixa_do_canvas(caixa, zoom):
    """O caminho de volta, para quando o arrasto termina."""
    return {
        "x": pixels_para_pontos(caixa["x"], zoom),
        "y": pixels_para_pontos(caixa["y"], zoom),
        "width": pixels_para_pontos(caixa["width"], zoom),
        "height": pixels_para_pontos(caixa["height"], zoom),
    }


def zoom_para_caber(largura_disponivel, largura_da_pagina=A4_WIDTH_PT, margem=32.0):
    """
    O zoom que faz a pagina caber na largura disponivel ("fit page").

    Nunca passa de 100%: ampliar uma pagina so porque sobra tela daria uma
    falsa impressao de tamanho real.
    """
    util = float(largura_disponivel) - float(margem)
    if util <= 0:
        return ZOOM_MINIMO
    return clamp_zoom(min(1.0, util / float(largura_da_pagina)))


# ---------------------------------------------------------------------------
# Documento <-> PDF (inversao do eixo Y)
# ---------------------------------------------------------------------------


def para_coordenadas_pdf(caixa, altura_da_pagina=A4_HEIGHT_PT):
    """
    Uma caixa do documento (origem em cima) no sistema do PDF (origem
    embaixo). `x`, `width` e `height` nao mudam; so o `y` e reancorado do
    topo para a base.

    E a UNICA porta entre os dois sistemas. Nao repetir esta conta em
    outro lugar.
    """
    altura_da_pagina = float(altura_da_pagina)
    return {
        "x": float(caixa["x"]),
        "y": altura_da_pagina - float(caixa["y"]) - float(caixa["height"]),
        "width": float(caixa["width"]),
        "height": float(caixa["height"]),
    }


def do_pdf_para_documento(caixa, altura_da_pagina=A4_HEIGHT_PT):
    """
    O inverso de `para_coordenadas_pdf` -- que e a PROPRIA
    `para_coordenadas_pdf`.

    Nao e descuido: inverter um eixo duas vezes devolve o original.
    Aplicando a conta a si mesma,

        H - (H - y - h) - h  ==  y

    entao a transformacao e involutiva e delegar e mais honesto do que
    repetir a formula -- se um dia a conta mudar, muda nos dois sentidos
    ao mesmo tempo. O nome separado existe porque quem le o codigo de
    importacao quer ver "do PDF para o documento", nao o contrario.

    Serve para importar um layout ja medido no sistema do PDF -- e o que
    a Etapa 4.2B vai precisar para trazer o mapa do documento frances
    (`pdfengine/layouts/carta_convite_fr.py`) para dentro do editor.
    """
    return para_coordenadas_pdf(caixa, altura_da_pagina)


def linha_de_base_para_pdf(y_topo, altura_da_pagina=A4_HEIGHT_PT):
    """
    Um Y de topo (documento) como Y de linha de base (PDF), para texto
    desenhado com `canvas.drawString`, que ancora na base do glifo e nao
    numa caixa.
    """
    return float(altura_da_pagina) - float(y_topo)
