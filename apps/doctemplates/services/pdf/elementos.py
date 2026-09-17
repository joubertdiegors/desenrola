"""
Um desenhador por TIPO de elemento (Etapa 3.4).

Cada funcao recebe o canvas do reportlab, o elemento do layout, o
contexto com os valores e a pagina -- e desenha. O despacho e por
`type`, pelo registro no fim do modulo: NAO ha `if slug ==` nem `if
language ==` em lugar nenhum. Um documento novo desenha sozinho desde
que use os tipos registrados; um tipo novo entra acrescentando uma
funcao e uma linha no registro.

COORDENADAS
-----------
O layout tem origem no canto superior esquerdo com Y para baixo; o
reportlab tem origem embaixo com Y para cima. A virada acontece so em
`_para_baixo()`. Nenhuma coordenada do layout e alterada para acomodar a
biblioteca -- e a biblioteca que e acomodada.
"""

import io

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

from . import texto as motor
from .contexto import texto_do_bloco

# Traco pontilhado/tracejado, em pontos. Valores pequenos porque as
# linhas de documento sao finas: um tracejado grosso viraria outra coisa.
PADROES_DE_TRACO = {
    "solid": None,
    "dashed": (3, 2),
    "dotted": (1, 2),
}

# A face concreta de cada familia/peso/estilo. O layout declara so a
# familia e o peso; o nome registrado no reportlab e escolhido aqui.
#
#   LiberationSans -- as QUATRO faces EMBUTIDAS (`pdfengine.fontconfig`),
#     clone metrico da Arial; e a tipografia do documento oficial. O
#     italico e a face italica de verdade, nao a regular inclinada.
#   Times, Courier -- as familias padrao do PDF (14 fontes base), com
#     as quatro variantes. Nao sao embutidas: o leitor as substitui pela
#     fonte compativel que tiver (Times New Roman/Courier New no
#     Windows), e todo leitor as renderiza.
_FACES = {
    ("LiberationSans", "regular", "normal"): "LiberationSans",
    ("LiberationSans", "bold", "normal"): "LiberationSans-Bold",
    ("LiberationSans", "regular", "italic"): "LiberationSans-Italic",
    ("LiberationSans", "bold", "italic"): "LiberationSans-BoldItalic",
    ("Times", "regular", "normal"): "Times-Roman",
    ("Times", "bold", "normal"): "Times-Bold",
    ("Times", "regular", "italic"): "Times-Italic",
    ("Times", "bold", "italic"): "Times-BoldItalic",
    ("Courier", "regular", "normal"): "Courier",
    ("Courier", "bold", "normal"): "Courier-Bold",
    ("Courier", "regular", "italic"): "Courier-Oblique",
    ("Courier", "bold", "italic"): "Courier-BoldOblique",
}

# Largura minima do recuo de um bloco com marcador de lista quando o
# layout nao declara `indent`: o marcador precisa de onde ficar.
RECUO_MINIMO_DO_MARCADOR = 18.0

# Quanto de largura o texto guarda para si, custe o que custar. Um recuo
# maior do que a propria caixa deixaria largura zero -- e largura zero
# nao desenha nada, ou seja, o texto SUMIRIA do documento sem aviso.
# Melhor um recuo menor do que o pedido e o texto visivel: o documento
# fica feio, mas ninguem perde conteudo em silencio.
LARGURA_MINIMA_DO_TEXTO = 12.0

# A numeracao de paginas: tamanho e distancia do pe da pagina.
TAMANHO_DO_NUMERO_DE_PAGINA = 9.0
PE_DO_NUMERO_DE_PAGINA = 28.0


class FonteIndisponivelError(LookupError):
    """A combinacao familia/peso/estilo nao tem face embutida."""


class AssetAusenteError(KeyError):
    """O elemento aponta para um asset que nao veio no lote."""


def face(familia, peso="regular", estilo="normal"):
    """
    O nome registrado da face para uma familia/peso/estilo.

    Uma combinacao que nao existe levanta: desenhar com outra face
    produziria um documento que MENTE sobre a propria tipografia.
    """
    try:
        return _FACES[(familia, peso, estilo)]
    except KeyError:
        raise FonteIndisponivelError(
            f'Não há face para "{familia}" com peso "{peso}" e estilo "{estilo}".'
        ) from None


def _para_baixo(y, altura, pagina):
    """Y do layout (do topo) -> Y do reportlab (de baixo)."""
    return pagina["height"] - y - altura


def _cor(valor):
    return HexColor(valor)


def _caixa(valor):
    lados = valor or {}
    return (
        float(lados.get("top", 0) or 0),
        float(lados.get("right", 0) or 0),
        float(lados.get("bottom", 0) or 0),
        float(lados.get("left", 0) or 0),
    )


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------


def _trechos_do_conteudo(bloco, propriedades, contexto):
    """
    O conteudo de um elemento como trechos do motor de texto.

    Um `mixed` vira varios trechos, cada um podendo trazer peso e estilo
    proprios (a extensao da Etapa 3.3). Qualquer outra forma vira um
    trecho so, com o estilo do elemento.
    """
    familia = propriedades.get("font_family", "LiberationSans")
    tamanho = float(propriedades.get("font_size", 11.0))
    peso = propriedades.get("font_weight", "regular")
    estilo = propriedades.get("font_style", "normal")
    cor = propriedades.get("color", "#000000")
    espacamento = float(propriedades.get("letter_spacing", 0.0) or 0.0)
    decoracao = propriedades.get("text_decoration", "none")

    def um(conteudo, parte=None):
        # Cada trecho de `mixed` pode sobrepor o estilo do elemento
        # (ver `layout_schema.ESTILO_DO_TRECHO`); o que nao declarar,
        # herda.
        proprio = parte if isinstance(parte, dict) else {}
        return motor.Trecho(
            texto_do_bloco(conteudo, contexto),
            face(
                proprio.get("font_family", familia),
                proprio.get("font_weight", peso),
                proprio.get("font_style", estilo),
            ),
            float(proprio.get("font_size", tamanho)),
            proprio.get("color", cor),
            espacamento,
            proprio.get("text_decoration", decoracao),
            proprio.get("highlight"),
            proprio.get("link"),
        )

    if isinstance(bloco, dict) and bloco.get("kind") == "mixed":
        trechos = [um(parte, parte) for parte in bloco.get("parts") or []]
        return [t for t in trechos if t.texto]

    return [um(bloco)]


def _desenhar_paragrafo(canvas, elemento, contexto, pagina, trechos):
    """
    O caminho comum de `text`, `rich_text` e `number`.

    A caixa e a do elemento menos o `padding`; as linhas sao posicionadas
    da primeira baseline para baixo, e o alinhamento vertical desloca o
    bloco inteiro dentro da caixa.
    """
    propriedades = elemento.get("properties") or {}
    if not trechos or not any(t.texto for t in trechos):
        return 0

    topo, direita, baixo, esquerda = _caixa(propriedades.get("padding"))
    # O recuo (lista, "aumentar recuo") empurra o texto para a direita
    # dentro da caixa; o marcador, se houver, e desenhado nele.
    marcador = propriedades.get("list_marker") or ""
    recuo = float(propriedades.get("indent", 0.0) or 0.0)
    if marcador and recuo <= 0:
        recuo = RECUO_MINIMO_DO_MARCADOR
    # O recuo nunca come a caixa inteira (ver LARGURA_MINIMA_DO_TEXTO).
    disponivel = float(elemento["width"]) - esquerda - direita
    recuo = min(recuo, max(0.0, disponivel - LARGURA_MINIMA_DO_TEXTO))
    largura = max(0.0, disponivel - recuo)
    altura = max(0.0, float(elemento["height"]) - topo - baixo)
    if largura <= 0:
        return 0

    tamanho = float(propriedades.get("font_size", 11.0))
    entrelinha = float(propriedades.get("line_height", 1.25)) * tamanho
    transbordo = propriedades.get("overflow", "shrink")
    quebra = propriedades.get("white_space", "normal") != "nowrap"

    linhas, fator = motor.encaixar(
        trechos, largura, altura, entrelinha,
        transbordo=transbordo, quebrar_linhas=quebra,
    )
    entrelinha *= fator

    altura_do_bloco = len(linhas) * entrelinha
    alinhamento_vertical = propriedades.get("vertical_align", "top")
    if alinhamento_vertical == "middle":
        recuo_vertical = max(0.0, (altura - altura_do_bloco) / 2)
    elif alinhamento_vertical == "bottom":
        recuo_vertical = max(0.0, altura - altura_do_bloco)
    else:
        recuo_vertical = 0.0

    x0 = float(elemento["x"]) + esquerda + recuo
    topo_do_texto = float(elemento["y"]) + topo + recuo_vertical
    alinhamento = propriedades.get("align", "left")

    if marcador and linhas:
        # O marcador segue a tipografia do ELEMENTO, na primeira linha,
        # encostado no comeco do recuo -- como um item de lista.
        primeiro = trechos[0]
        ascent_do_marcador, _d = motor.altura_da_fonte(primeiro.fonte, primeiro.tamanho)
        objeto = canvas.beginText(
            float(elemento["x"]) + esquerda, pagina["height"] - (topo_do_texto + ascent_do_marcador)
        )
        objeto.setFont(primeiro.fonte, primeiro.tamanho)
        objeto.setFillColor(_cor(primeiro.cor))
        objeto.textOut(marcador)
        canvas.drawText(objeto)

    if transbordo == "clip":
        canvas.saveState()
        canvas.rect(
            x0, _para_baixo(topo_do_texto, altura, pagina), largura, altura, stroke=0, fill=0,
        )
        canvas.clipPath(_caminho_da_caixa(canvas, x0, topo_do_texto, largura, altura, pagina),
                        stroke=0, fill=0)

    desenhadas = 0
    for indice, linha in enumerate(linhas):
        ascent, _descent = motor.altura_da_fonte(
            linha.pedacos[0].fonte if linha.pedacos else trechos[0].fonte,
            linha.pedacos[0].tamanho if linha.pedacos else trechos[0].tamanho,
        )
        base_do_topo = topo_do_texto + indice * entrelinha + ascent
        y = pagina["height"] - base_do_topo

        posicoes, extra = motor.posicionar(linha, largura, alinhamento)
        # Cada pedaco vai num objeto de texto proprio. E por ele que o
        # PDF aplica `wordSpace` (a justificacao estica os ESPACOS, nao
        # as letras) e `charSpace`; o Canvas nao expoe o primeiro. A
        # vantagem de esticar assim, em vez de posicionar palavra a
        # palavra, e que o texto continua saindo inteiro na extracao.
        for deslocamento, pedaco in posicoes:
            if not pedaco.texto.strip():
                continue
            _realcar(canvas, pedaco, x0 + deslocamento, y,
                     extra * pedaco.texto.count(" "))
            objeto = canvas.beginText(x0 + deslocamento, y)
            objeto.setFont(pedaco.fonte, pedaco.tamanho)
            objeto.setFillColor(_cor(pedaco.cor))
            # SEMPRE declarar os dois, inclusive como zero: `Tw` e `Tc`
            # sao estado do PDF e PERSISTEM entre objetos de texto. Sem
            # zerar, a linha seguinte a uma justificada herdava o
            # esticamento dela -- e a ultima linha do paragrafo, que por
            # convencao nao estica, saia esticada.
            objeto.setWordSpace(extra)
            objeto.setCharSpace(pedaco.espaco_entre_letras or 0)
            objeto.textOut(pedaco.texto)
            canvas.drawText(objeto)
            _decorar(canvas, pedaco, x0 + deslocamento, y,
                     extra * pedaco.texto.count(" "))
            _ligar(canvas, pedaco, x0 + deslocamento, y,
                   extra * pedaco.texto.count(" "))
        desenhadas += 1

    if transbordo == "clip":
        canvas.restoreState()
    return desenhadas


def _caminho_da_caixa(canvas, x, y_do_topo, largura, altura, pagina):
    caminho = canvas.beginPath()
    caminho.rect(x, _para_baixo(y_do_topo, altura, pagina), largura, altura)
    return caminho


def _caixa_do_pedaco(pedaco, x, y, extra=0.0):
    """O retangulo que o pedaco ocupa: (x0, y0, x1, y1), Y do reportlab."""
    largura = motor.largura_do_trecho(pedaco) + extra
    ascent, descent = motor.altura_da_fonte(pedaco.fonte, pedaco.tamanho)
    return x, y - descent, x + largura, y + ascent


def _realcar(canvas, pedaco, x, y, extra=0.0):
    """O fundo de um trecho realcado, desenhado ANTES do texto."""
    if not pedaco.fundo:
        return
    x0, y0, x1, y1 = _caixa_do_pedaco(pedaco, x, y, extra)
    canvas.saveState()
    canvas.setFillColor(_cor(pedaco.fundo))
    canvas.rect(x0, y0, x1 - x0, y1 - y0, stroke=0, fill=1)
    canvas.restoreState()


def _ligar(canvas, pedaco, x, y, extra=0.0):
    """
    A area clicavel de um trecho-link. Anotacao de link do proprio PDF:
    o texto continua texto, e quem abre o documento num leitor clica.
    """
    if not pedaco.link:
        return
    canvas.linkURL(pedaco.link, _caixa_do_pedaco(pedaco, x, y, extra), relative=0)


def _decorar(canvas, pedaco, x, y, extra=0.0):
    """Sublinhado e riscado -- o reportlab nao os desenha sozinho."""
    if pedaco.decoracao not in ("underline", "line-through"):
        return
    largura = motor.largura_do_trecho(pedaco) + extra
    deslocamento = -0.1 * pedaco.tamanho if pedaco.decoracao == "underline" else (
        0.3 * pedaco.tamanho
    )
    canvas.setStrokeColor(_cor(pedaco.cor))
    canvas.setLineWidth(max(0.4, pedaco.tamanho * 0.05))
    canvas.line(x, y + deslocamento, x + largura, y + deslocamento)


def desenhar_text(canvas, elemento, contexto, pagina, recursos):
    propriedades = elemento.get("properties") or {}
    trechos = _trechos_do_conteudo(propriedades.get("content"), propriedades, contexto)
    return _desenhar_paragrafo(canvas, elemento, contexto, pagina, trechos)


def desenhar_rich_text(canvas, elemento, contexto, pagina, recursos):
    return desenhar_text(canvas, elemento, contexto, pagina, recursos)


def desenhar_number(canvas, elemento, contexto, pagina, recursos):
    """
    Como `text`, mas passando o valor por `format` antes.

    `format` vazio imprime o valor como veio -- e o caso comum, porque o
    dado ja costuma chegar formatado da camada de aplicacao.
    """
    propriedades = elemento.get("properties") or {}
    bruto = texto_do_bloco(propriedades.get("content"), contexto)
    gabarito = (propriedades.get("format") or "").strip()
    valor = _formatar_numero(bruto, gabarito)

    trechos = _trechos_do_conteudo({"kind": "text", "value": valor}, propriedades, contexto)
    return _desenhar_paragrafo(canvas, elemento, contexto, pagina, trechos)


def _formatar_numero(bruto, gabarito):
    """
    Aplica o gabarito, e devolve o valor intacto se nao der.

    Nao adivinha: se o texto nao for numero ou o gabarito nao servir, o
    que estava escrito continua escrito. Um documento com o valor cru e
    conferivel; um com valor inventado, nao.
    """
    if not gabarito or not bruto:
        return bruto
    try:
        return format(float(bruto.replace(",", ".")), gabarito)
    except (ValueError, TypeError):
        return bruto


# ---------------------------------------------------------------------------
# Graficos
# ---------------------------------------------------------------------------


def desenhar_line(canvas, elemento, contexto, pagina, recursos):
    propriedades = elemento.get("properties") or {}
    x = float(elemento["x"])
    y = float(elemento["y"])
    x2 = x + float(elemento["width"])
    y2 = y + float(elemento["height"])

    canvas.saveState()
    canvas.setStrokeColor(_cor(propriedades.get("color", "#000000")))
    canvas.setLineWidth(float(propriedades.get("thickness", 1.0)))
    padrao = PADROES_DE_TRACO.get(propriedades.get("style", "solid"))
    if padrao:
        canvas.setDash(*padrao)
    canvas.line(
        x, pagina["height"] - y,
        x2, pagina["height"] - y2,
    )
    canvas.restoreState()
    return 1


def desenhar_rectangle(canvas, elemento, contexto, pagina, recursos):
    propriedades = elemento.get("properties") or {}
    largura = float(elemento["width"])
    altura = float(elemento["height"])
    x = float(elemento["x"])
    y = _para_baixo(float(elemento["y"]), altura, pagina)

    espessura = float(propriedades.get("border_width", 1.0) or 0.0)
    preenchimento = propriedades.get("fill_color")
    raio = float(propriedades.get("radius", 0.0) or 0.0)

    canvas.saveState()
    if preenchimento:
        canvas.setFillColor(_cor(preenchimento))
    if espessura:
        canvas.setStrokeColor(_cor(propriedades.get("border_color", "#000000")))
        canvas.setLineWidth(espessura)
        padrao = PADROES_DE_TRACO.get(propriedades.get("border_style", "solid"))
        if padrao:
            canvas.setDash(*padrao)

    desenhar_borda = 1 if espessura else 0
    preencher = 1 if preenchimento else 0
    if desenhar_borda or preencher:
        if raio:
            canvas.roundRect(x, y, largura, altura, raio,
                             stroke=desenhar_borda, fill=preencher)
        else:
            canvas.rect(x, y, largura, altura, stroke=desenhar_borda, fill=preencher)
    canvas.restoreState()
    return 1


def desenhar_image(canvas, elemento, contexto, pagina, recursos):
    """
    A imagem vem do lote de assets, nunca do disco e nunca do PDF
    oficial: quem carrega bytes e a camada de aplicacao, e o renderer
    so desenha o que recebeu.
    """
    propriedades = elemento.get("properties") or {}
    origem = propriedades.get("source") or {}
    if origem.get("kind") != "asset":
        return 0

    identificador = origem.get("asset_id")
    dados = (recursos.get("assets") or {}).get(identificador)
    if not dados:
        raise AssetAusenteError(
            f'O elemento "{elemento.get("id")}" aponta para o asset '
            f"{identificador}, que não veio no lote de imagens."
        )

    largura = float(elemento["width"])
    altura = float(elemento["height"])
    x = float(elemento["x"])
    y = _para_baixo(float(elemento["y"]), altura, pagina)

    imagem = ImageReader(io.BytesIO(dados))
    preservar = propriedades.get("preserve_aspect_ratio", True)
    ajuste = propriedades.get("fit", "contain")

    if preservar and ajuste != "fill":
        largura_original, altura_original = imagem.getSize()
        if largura_original and altura_original:
            proporcao = largura_original / altura_original
            if ajuste == "cover":
                escala = max(largura / largura_original, altura / altura_original)
            else:
                escala = min(largura / largura_original, altura / altura_original)
            nova_largura = largura_original * escala
            nova_altura = altura_original * escala
            # Centraliza a sobra, como faz qualquer "contain".
            x += (largura - nova_largura) / 2
            y += (altura - nova_altura) / 2
            largura, altura = nova_largura, nova_altura
            del proporcao

    canvas.drawImage(imagem, x, y, largura, altura, mask="auto")
    return 1


def desenhar_qr_code(canvas, elemento, contexto, pagina, recursos):
    """
    QR gerado de verdade a partir do valor configurado.

    Nada de raster do documento original: o conteudo pode ser um campo
    dinamico, e um QR rasterizado nunca acompanharia o dado.
    """
    propriedades = elemento.get("properties") or {}
    valor = texto_do_bloco(propriedades.get("source"), contexto)
    if not valor:
        return 0

    largura = float(elemento["width"])
    altura = float(elemento["height"])
    margem = float(propriedades.get("margin", 0.0) or 0.0)
    lado_util_x = max(0.0, largura - 2 * margem)
    lado_util_y = max(0.0, altura - 2 * margem)
    if not lado_util_x or not lado_util_y:
        return 0

    componente = QrCodeWidget(
        valor, barLevel=propriedades.get("error_correction", "M")
    )
    limites = componente.getBounds()
    largura_do_qr = limites[2] - limites[0]
    altura_do_qr = limites[3] - limites[1]

    desenho = Drawing(
        lado_util_x, lado_util_y,
        transform=[lado_util_x / largura_do_qr, 0, 0, lado_util_y / altura_do_qr, 0, 0],
    )
    desenho.add(componente)
    renderPDF.draw(
        desenho, canvas,
        float(elemento["x"]) + margem,
        _para_baixo(float(elemento["y"]), altura, pagina) + margem,
    )
    return 1


# ---------------------------------------------------------------------------
# Tabela
# ---------------------------------------------------------------------------


def desenhar_table(canvas, elemento, contexto, pagina, recursos):
    """
    Tabela de verdade: grade desenhada e celulas com conteudo
    estrutural -- inclusive campos dinamicos e trechos mistos.
    """
    propriedades = elemento.get("properties") or {}
    colunas = propriedades.get("columns") or []
    linhas = propriedades.get("rows") or []
    if not colunas or not linhas:
        return 0

    x0 = float(elemento["x"])
    y0 = float(elemento["y"])
    espessura = float(propriedades.get("border_width", 0.5) or 0.0)
    cor_da_borda = propriedades.get("border_color", "#000000")
    topo, direita, baixo, esquerda = _caixa(propriedades.get("cell_padding"))

    larguras = [float(coluna.get("width", 0)) for coluna in colunas]
    alturas = [float(linha.get("min_height", 0)) for linha in linhas]
    largura_total = sum(larguras)
    altura_total = sum(alturas)

    # --- grade ---
    if espessura:
        canvas.saveState()
        canvas.setStrokeColor(_cor(cor_da_borda))
        canvas.setLineWidth(espessura)
        y_corrente = y0
        for altura in [0, *alturas]:
            y_corrente = y_corrente if altura == 0 else y_corrente + altura
            y = pagina["height"] - y_corrente
            canvas.line(x0, y, x0 + largura_total, y)
        x_corrente = x0
        for largura in [0, *larguras]:
            x_corrente = x_corrente if largura == 0 else x_corrente + largura
            canvas.line(
                x_corrente, pagina["height"] - y0,
                x_corrente, pagina["height"] - (y0 + altura_total),
            )
        canvas.restoreState()

    # --- celulas ---
    desenhadas = 0
    y_da_linha = y0
    for indice, linha in enumerate(linhas):
        altura_da_linha = alturas[indice]
        x_da_coluna = x0
        for posicao, celula in enumerate(linha.get("cells") or []):
            if posicao >= len(larguras):
                break
            largura_da_coluna = larguras[posicao]
            propriedades_da_celula = dict(propriedades)
            propriedades_da_celula["align"] = (
                celula.get("align") or colunas[posicao].get("align") or "left"
            )
            propriedades_da_celula["font_weight"] = (
                "bold" if celula.get("bold") else propriedades.get("font_weight", "regular")
            )
            propriedades_da_celula["padding"] = {
                "top": topo, "right": direita, "bottom": baixo, "left": esquerda,
            }
            propriedades_da_celula["vertical_align"] = "top"
            propriedades_da_celula["overflow"] = "shrink"

            falso_elemento = {
                "id": f"{elemento.get('id')}-c{indice}-{posicao}",
                "type": "text",
                "x": x_da_coluna,
                "y": y_da_linha,
                "width": largura_da_coluna,
                "height": altura_da_linha,
                "properties": propriedades_da_celula,
            }
            trechos = _trechos_do_conteudo(
                celula.get("content"), propriedades_da_celula, contexto
            )
            desenhadas += _desenhar_paragrafo(
                canvas, falso_elemento, contexto, pagina, trechos
            )
            x_da_coluna += largura_da_coluna
        y_da_linha += altura_da_linha

    return desenhadas or 1


# ---------------------------------------------------------------------------
# Estrutura
# ---------------------------------------------------------------------------


def desenhar_page_break(canvas, elemento, contexto, pagina, recursos):
    """
    Nao desenha nada: a quebra e lida por `render_layout`, que a usa para
    distribuir os elementos pelas paginas. Esta aqui para o despacho por
    tipo continuar completo -- todo tipo registrado tem desenhador.
    """
    return 0


def desenhar_numero_de_pagina(canvas, numero, total, pagina, *, familia="LiberationSans"):
    """"n / N" centralizado no pe da pagina. Chamado por `render_layout`."""
    texto = f"{numero} / {total}"
    fonte = face(familia)
    largura = motor.largura_do_texto(texto, fonte, TAMANHO_DO_NUMERO_DE_PAGINA)
    objeto = canvas.beginText((pagina["width"] - largura) / 2, PE_DO_NUMERO_DE_PAGINA)
    objeto.setFont(fonte, TAMANHO_DO_NUMERO_DE_PAGINA)
    objeto.setFillColor(_cor("#000000"))
    objeto.textOut(texto)
    canvas.drawText(objeto)


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

DESENHADORES = {
    "text": desenhar_text,
    "rich_text": desenhar_rich_text,
    "number": desenhar_number,
    "image": desenhar_image,
    "qr_code": desenhar_qr_code,
    "table": desenhar_table,
    "line": desenhar_line,
    "rectangle": desenhar_rectangle,
    "page_break": desenhar_page_break,
}


class TipoSemDesenhadorError(KeyError):
    """O tipo existe no registro de elementos mas ninguem sabe desenha-lo."""


def desenhador(tipo):
    try:
        return DESENHADORES[tipo]
    except KeyError:
        raise TipoSemDesenhadorError(
            f'O renderer não sabe desenhar elementos do tipo "{tipo}". '
            f"Tipos conhecidos: {', '.join(sorted(DESENHADORES))}."
        ) from None
