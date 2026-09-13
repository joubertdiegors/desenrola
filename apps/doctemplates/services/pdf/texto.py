"""
Motor de texto do renderer (Etapa 3.4): medir, quebrar e alinhar.

Recebe TRECHOS (texto + estilo) e devolve LINHAS ja posicionadas. Nada
aqui desenha; nada aqui importa Django. E o que permite testar quebra de
linha e justificacao com asserts diretos, sem gerar PDF e sem banco.

POR QUE TRECHOS, E NAO UMA STRING
---------------------------------
Um `rich_text` mistura pesos na mesma linha corrida -- "Je soussignée,
**Claire Dubois**, née le ...". Se o conteudo virasse uma string antes da
quebra, o negrito se perderia; se cada trecho virasse um elemento
proprio, a linha nao fluiria. Entao a unidade que atravessa o motor e o
trecho: a quebra acontece ENTRE palavras de trechos diferentes, e cada
pedaco chega ao desenho com a sua propria fonte.

JUSTIFICACAO
------------
So os espacos ENTRE palavras esticam, e a ultima linha de um paragrafo
nunca estica -- e a convencao tipografica, e e o que o documento oficial
faz. Esticar a ultima linha delataria na hora que o texto foi
reconstruido por um programa.
"""

from reportlab.pdfbase import pdfmetrics

# Piso do `overflow: shrink`. O contrato novo nao tem `min_font_size`
# (isso era do schema antigo), mas encolher sem limite produziria texto
# ilegivel em silencio -- melhor parar e deixar transbordar de forma
# visivel do que entregar um documento que ninguem le.
FATOR_MINIMO_DE_REDUCAO = 0.5

# De quanto em quanto o `shrink` tenta. Passo fino: o documento oficial
# foi medido com casas decimais e um salto grosso erraria o encaixe.
PASSO_DA_REDUCAO = 0.25

# Folga na comparacao de altura. Sem ela, uma celula de 13,5pt "nao cabe"
# numa area de 13,499999999999998pt -- que e o que `24 - 6.1 - 4.4` da em
# ponto flutuante -- e o texto encolhe 2,3% sem motivo nenhum. Um
# milionesimo de ponto nao e transbordo.
TOLERANCIA_DE_ALTURA = 1e-6


class Trecho:
    """Um pedaco de texto com o seu estilo. A unidade que o motor move."""

    __slots__ = ("texto", "fonte", "tamanho", "cor", "espaco_entre_letras", "decoracao")

    def __init__(self, texto, fonte, tamanho, cor="#000000",
                 espaco_entre_letras=0.0, decoracao="none"):
        self.texto = texto
        self.fonte = fonte
        self.tamanho = tamanho
        self.cor = cor
        self.espaco_entre_letras = espaco_entre_letras
        self.decoracao = decoracao

    def com_texto(self, texto):
        return Trecho(
            texto, self.fonte, self.tamanho, self.cor,
            self.espaco_entre_letras, self.decoracao,
        )

    def com_tamanho(self, tamanho):
        return Trecho(
            self.texto, self.fonte, tamanho, self.cor,
            self.espaco_entre_letras, self.decoracao,
        )

    def __repr__(self):  # pragma: no cover - so para depuracao
        return f"Trecho({self.texto!r}, {self.fonte}, {self.tamanho})"


class Linha:
    """Uma linha ja montada: os seus pedacos e a largura que ocupam."""

    __slots__ = ("pedacos", "largura", "ultima")

    def __init__(self, pedacos, largura, ultima=False):
        self.pedacos = pedacos
        self.largura = largura
        self.ultima = ultima

    @property
    def texto(self):
        return "".join(pedaco.texto for pedaco in self.pedacos)


def largura_do_texto(texto, fonte, tamanho, espaco_entre_letras=0.0):
    """
    A largura de um texto em pontos.

    O `letter_spacing` entra aqui e nao no desenho porque a quebra de
    linha precisa da largura REAL -- medir sem ele faria caber na conta
    uma palavra que nao cabe na pagina.
    """
    if not texto:
        return 0.0
    largura = pdfmetrics.stringWidth(texto, fonte, tamanho)
    if espaco_entre_letras:
        largura += espaco_entre_letras * len(texto)
    return largura


def largura_do_trecho(trecho):
    return largura_do_texto(
        trecho.texto, trecho.fonte, trecho.tamanho, trecho.espaco_entre_letras
    )


# Ascent tipografico por fonte, em fracao do em. Cache: o arquivo e lido
# uma vez por processo, nao a cada linha de texto.
_ASCENT_POR_FONTE = {}


def _ascent_do_arquivo(caminho):
    """
    O `hhea.ascender` de um TrueType, em fracao do em.

    Devolve None se o arquivo nao puder ser lido ou nao tiver as tabelas
    -- quem chama entao cai no valor do reportlab.
    """
    import struct

    try:
        with open(caminho, "rb") as arquivo:
            dados = arquivo.read()
        quantas = struct.unpack(">H", dados[4:6])[0]
        tabelas = {}
        for indice in range(quantas):
            posicao = 12 + indice * 16
            etiqueta = dados[posicao:posicao + 4].decode("latin-1")
            tabelas[etiqueta] = struct.unpack(">II", dados[posicao + 8:posicao + 16])[0]
        head = tabelas["head"]
        por_em = struct.unpack(">H", dados[head + 18:head + 20])[0]
        hhea = tabelas["hhea"]
        ascender = struct.unpack(">h", dados[hhea + 4:hhea + 6])[0]
        return ascender / por_em if por_em else None
    except (OSError, KeyError, struct.error, IndexError):
        return None


def ascent(fonte, tamanho):
    """
    O ascent TIPOGRAFICO da fonte, em pontos.

    NAO e o que `pdfmetrics.getAscent()` devolve. O reportlab usa o
    `typoAscender` da tabela OS/2, que na Liberation Sans vale 0,728em
    contra os 0,905em do `hhea.ascender`. A diferenca nao e academica:
    sao 1,95pt a 11pt, e o documento inteiro subiria isso na pagina.

    O layout guarda o TOPO da caixa. A Etapa 3.3 derivou esse topo da
    linha de base medida no documento oficial, usando o Ascent que o PDF
    declara para a Arial (0,905em). Liberation Sans e clone metrico da
    Arial e tem exatamente o mesmo `hhea.ascender`, entao ler o hhea faz
    o renderer desfazer a conta com o MESMO numero -- e sem repetir a
    constante aqui: ela vem do arquivo da fonte, seja ela qual for.
    """
    if fonte not in _ASCENT_POR_FONTE:
        fracao = None
        try:
            face = pdfmetrics.getFont(fonte).face
            caminho = getattr(face, "filename", None)
            if caminho:
                if isinstance(caminho, bytes):
                    caminho = caminho.decode("utf-8", "replace")
                fracao = _ascent_do_arquivo(caminho)
        except Exception:  # noqa: BLE001 - fonte sem arquivo (Type1 padrao)
            fracao = None
        if fracao is None:
            # Sem arquivo legivel, o valor do reportlab e o que ha.
            fracao = pdfmetrics.getAscent(fonte, 1000.0) / 1000.0
        _ASCENT_POR_FONTE[fonte] = fracao
    return _ASCENT_POR_FONTE[fonte] * tamanho


def altura_da_fonte(fonte, tamanho):
    """Ascent tipografico e descent, em pontos."""
    return ascent(fonte, tamanho), abs(pdfmetrics.getDescent(fonte, tamanho))


def _palavras(trecho):
    """
    Quebra um trecho em palavras e espacos, preservando o estilo.

    Os espacos viram itens proprios para a justificacao saber onde
    esticar, e para a quebra saber onde pode cortar.
    """
    itens = []
    atual = ""
    for caractere in trecho.texto:
        if caractere == " ":
            if atual:
                itens.append(trecho.com_texto(atual))
                atual = ""
            itens.append(trecho.com_texto(" "))
        else:
            atual += caractere
    if atual:
        itens.append(trecho.com_texto(atual))
    return itens


def quebrar(trechos, largura_disponivel, *, quebrar_linhas=True):
    """
    Monta as linhas de um paragrafo.

    `quebrar_linhas=False` corresponde a `white_space: nowrap`: tudo numa
    linha so, custe o que custar -- quem pediu nowrap quer exatamente
    isso.
    """
    itens = []
    for trecho in trechos:
        if "\n" in trecho.texto:
            # Quebra explicita: cada pedaco vira o seu, com marca propria.
            partes = trecho.texto.split("\n")
            for posicao, parte in enumerate(partes):
                if posicao:
                    itens.append(None)          # marca de quebra forcada
                if parte:
                    itens.extend(_palavras(trecho.com_texto(parte)))
        else:
            itens.extend(_palavras(trecho))

    if not quebrar_linhas:
        pedacos = [item for item in itens if item is not None]
        return [Linha(_juntar(pedacos), sum(largura_do_trecho(p) for p in pedacos), True)]

    linhas = []
    atual = []
    largura_atual = 0.0

    for item in itens:
        if item is None:
            linhas.append(_fechar(atual, largura_atual))
            atual, largura_atual = [], 0.0
            continue

        largura = largura_do_trecho(item)

        if item.texto == " ":
            # Espaco no comeco de linha some: e o que sobra da quebra
            # anterior, nao um recuo pedido pelo documento.
            if not atual:
                continue
            atual.append(item)
            largura_atual += largura
            continue

        if atual and largura_atual + largura > largura_disponivel:
            # Tira o espaco pendente antes de fechar: ele pertencia a
            # juncao que acabou de ser desfeita.
            while atual and atual[-1].texto == " ":
                largura_atual -= largura_do_trecho(atual.pop())
            linhas.append(_fechar(atual, largura_atual))
            atual, largura_atual = [], 0.0

        atual.append(item)
        largura_atual += largura

    linhas.append(_fechar(atual, largura_atual))

    # Uma palavra unica maior que a caixa gera linha cheia; nao ha o que
    # cortar sem inventar hifenizacao, entao ela transborda e o
    # `overflow` do elemento decide o que fazer.
    resultado = [linha for linha in linhas if linha.pedacos] or [Linha([], 0.0, True)]
    resultado[-1].ultima = True
    return resultado


def _fechar(pedacos, largura):
    while pedacos and pedacos[-1].texto == " ":
        largura -= largura_do_trecho(pedacos[-1])
        pedacos = pedacos[:-1]
    return Linha(_juntar(pedacos), largura)


def _juntar(pedacos):
    """
    Funde pedacos vizinhos de mesmo estilo.

    Menos operacoes de desenho e, principalmente, texto que se extrai do
    PDF como palavra inteira em vez de letra solta.
    """
    juntos = []
    for pedaco in pedacos:
        anterior = juntos[-1] if juntos else None
        mesmo_estilo = (
            anterior is not None
            and anterior.fonte == pedaco.fonte
            and anterior.tamanho == pedaco.tamanho
            and anterior.cor == pedaco.cor
            and anterior.espaco_entre_letras == pedaco.espaco_entre_letras
            and anterior.decoracao == pedaco.decoracao
        )
        if mesmo_estilo:
            juntos[-1] = anterior.com_texto(anterior.texto + pedaco.texto)
        else:
            juntos.append(pedaco)
    return juntos


def espaco_extra(linha, largura_disponivel, alinhamento):
    """
    Quanto cada espaco da linha estica, na justificacao.

    Conta os espacos no TEXTO da linha, e nao os pedacos que sejam so
    espaco: `_juntar()` funde vizinhos de mesmo estilo, entao " " quase
    sempre acaba dentro de um pedaco maior. Contar pedacos daria zero e
    a justificacao nunca aconteceria -- foi exatamente esse o bug que a
    comparacao com o documento oficial revelou.
    """
    if alinhamento != "justify" or linha.ultima:
        return 0.0
    espacos = linha.texto.count(" ")
    if not espacos or linha.largura >= largura_disponivel:
        return 0.0
    return (largura_disponivel - linha.largura) / espacos


def posicionar(linha, largura_disponivel, alinhamento):
    """
    Onde cada pedaco da linha comeca, no eixo X.

    Devolve `([(deslocamento, trecho)], extra_por_espaco)`. O extra e da
    LINHA inteira: quem desenha o aplica com `setWordSpace`, que e como
    o PDF estica espacos sem precisar quebrar o texto em palavras.
    """
    if not linha.pedacos:
        return [], 0.0

    extra = espaco_extra(linha, largura_disponivel, alinhamento)
    largura_final = linha.largura + extra * linha.texto.count(" ")

    if alinhamento == "center":
        deslocamento = (largura_disponivel - largura_final) / 2
    elif alinhamento == "right":
        deslocamento = largura_disponivel - largura_final
    else:
        deslocamento = 0.0

    posicoes = []
    for pedaco in linha.pedacos:
        posicoes.append((deslocamento, pedaco))
        deslocamento += largura_do_trecho(pedaco) + extra * pedaco.texto.count(" ")
    return posicoes, extra


def encaixar(trechos, largura, altura, entrelinha, *, transbordo="shrink",
             quebrar_linhas=True):
    """
    Quebra o texto e, se preciso, reduz a fonte ate caber na altura.

    Devolve `(linhas, fator)`. `fator` e o quanto a fonte foi reduzida --
    1.0 quando nao precisou.

    `clip` e `grow` nao reduzem nada: o primeiro deixa quem desenha
    recortar, o segundo deixa transbordar de proposito. So `shrink`
    mexe no tamanho, e ainda assim ate um piso.
    """
    linhas = quebrar(trechos, largura, quebrar_linhas=quebrar_linhas)
    if transbordo != "shrink" or not altura:
        return linhas, 1.0

    if len(linhas) * entrelinha <= altura + TOLERANCIA_DE_ALTURA:
        return linhas, 1.0

    tamanho_base = max((t.tamanho for t in trechos), default=0) or 0
    if not tamanho_base:
        return linhas, 1.0

    fator = 1.0
    while fator > FATOR_MINIMO_DE_REDUCAO:
        fator -= PASSO_DA_REDUCAO / tamanho_base
        reduzidos = [t.com_tamanho(t.tamanho * fator) for t in trechos]
        tentativa = quebrar(reduzidos, largura, quebrar_linhas=quebrar_linhas)
        if len(tentativa) * entrelinha * fator <= altura + TOLERANCIA_DE_ALTURA:
            return tentativa, fator

    # Chegou ao piso e ainda nao cabe: melhor transbordar legivel do que
    # continuar encolhendo. Quem revisar o documento ve o problema.
    reduzidos = [t.com_tamanho(t.tamanho * FATOR_MINIMO_DE_REDUCAO) for t in trechos]
    return (
        quebrar(reduzidos, largura, quebrar_linhas=quebrar_linhas),
        FATOR_MINIMO_DE_REDUCAO,
    )
