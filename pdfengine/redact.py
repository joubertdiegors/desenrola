"""
Remove, da PAGINA-BASE original, o texto de amostra que cai dentro das
areas variaveis do layout -- nao so cobre visualmente.

Por que isto existe: pintar um retangulo branco por cima de um texto
(a "mascara" do overlay) esconde o texto NA TELA, mas o texto original
continua no fluxo de conteudo do PDF -- copiar/colar ou extrair o texto
do documento gerado revelaria os dois valores, o de amostra E o real.
E o mesmo erro conhecido de "redacao por caixa preta" em PDFs (esconder
visualmente sem remover o conteudo).

Como funciona
-------------
O texto de um PDF e posicionado por duas matrizes: a matriz de texto
(`Tm`, absoluta) e deslocamentos relativos (`Td`) a partir dela. Neste
documento, cada bloco `BT ... ET` tem UM `Tm` -- que e a ancora do
paragrafo, nao a posicao de uma palavra -- seguido de varios pares
(`Td`, `Tj`), um por palavra. Ou seja: a posicao onde cada palavra e
realmente desenhada so aparece depois de aplicar o `Td`.

Por isso a decisao aqui e tomada POR OPERADOR DE DESENHO (`Tj`), com a
matriz de texto acompanhada operador a operador -- nao pela ancora do
bloco. Olhar so a ancora deixaria passar exatamente os casos em que ela
fica fora da area mascarada e as palavras dentro (foi o que acontecia
antes: a amostra do item 2 e o nome da assinatura continuavam
extraiveis do PDF final).

Remover um `Tj` e seguro para o posicionamento: `Td` desloca a matriz de
LINHA (`Tlm`), que nao depende do que foi desenhado. Todo o resto do
bloco (`Tf`, `Tm`, `Td`) e preservado, entao nada se desloca.
"""

from pypdf.generic import ContentStream, NameObject

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

# Operadores que pintam texto. Neste documento so aparece `Tj`, mas os
# outros sao tratados para o modulo continuar correto se o documento
# oficial for substituido por uma versao gerada por outra ferramenta.
SHOW_TEXT = {"Tj", "TJ", "'", '"'}


def _apply(matrix, x, y):
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)


def _mat_mult(m1, m2):
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def _translation(tx, ty):
    return (1.0, 0.0, 0.0, 1.0, float(tx), float(ty))


def _point_in_rect(x, y, rect):
    return rect.x <= x <= rect.x + rect.width and rect.y <= y <= rect.y + rect.height


def redact_masked_text(page, mask_rects):
    """
    Devolve `(operacoes, removidos)`: a lista de operacoes de conteudo de
    `page` sem os operadores de desenho de texto cuja posicao real (a
    matriz de texto do momento, ja composta com o `cm` vigente) cai
    dentro de algum retangulo de `mask_rects`.

    Nao modifica `page` -- quem chama decide o que fazer com o resultado
    (ver `redact_page_content`).
    """
    content = ContentStream(page.get_contents(), page.pdf)

    ctm_stack = [IDENTITY]
    text_matrix = IDENTITY  # Tm corrente
    line_matrix = IDENTITY  # Tlm: de onde cada Td parte
    leading = 0.0

    kept = []
    removed = 0

    for operands, operator in content.operations:
        op = operator.decode() if isinstance(operator, bytes) else operator

        if op == "q":
            ctm_stack.append(ctm_stack[-1])
        elif op == "Q":
            if len(ctm_stack) > 1:
                ctm_stack.pop()
        elif op == "cm":
            ctm_stack[-1] = _mat_mult(tuple(float(v) for v in operands), ctm_stack[-1])
        elif op == "BT":
            text_matrix = line_matrix = IDENTITY
        elif op == "Tm":
            text_matrix = line_matrix = tuple(float(v) for v in operands)
        elif op == "TL":
            leading = float(operands[0])
        elif op == "Td":
            line_matrix = _mat_mult(_translation(*operands), line_matrix)
            text_matrix = line_matrix
        elif op == "TD":
            leading = -float(operands[1])
            line_matrix = _mat_mult(_translation(*operands), line_matrix)
            text_matrix = line_matrix
        elif op == "T*":
            line_matrix = _mat_mult(_translation(0, -leading), line_matrix)
            text_matrix = line_matrix
        elif op in ("'", '"'):
            # ambos fazem um T* implicito antes de pintar
            line_matrix = _mat_mult(_translation(0, -leading), line_matrix)
            text_matrix = line_matrix

        if op in SHOW_TEXT:
            x, y = _apply(_mat_mult(text_matrix, ctm_stack[-1]), 0, 0)
            if any(_point_in_rect(x, y, rect) for rect in mask_rects):
                removed += 1
                continue  # o operador de desenho e descartado; o resto fica

        kept.append((operands, operator))

    return kept, removed


def redact_page_content(page, mask_rects):
    """
    Substitui o conteudo de `page` (ja anexada a um `PdfWriter` -- ver
    nota em `pdfengine.render.render_invitation_letter_fr`), removendo o
    texto de amostra dentro de `mask_rects`. Modifica `page` em lugar;
    devolve quantos operadores de desenho foram removidos.
    """
    kept_ops, removed = redact_masked_text(page, mask_rects)

    new_content = ContentStream(None, page.pdf)
    new_content.operations = kept_ops
    page[NameObject("/Contents")] = new_content
    return removed
