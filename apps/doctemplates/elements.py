"""
Registro central dos TIPOS DE ELEMENTO de um documento (Etapa 3.1).

Cada tipo declara aqui, de forma legivel por codigo, quais propriedades
aceita, quais sao obrigatorias e qual e o padrao de cada uma. Tres
consumidores leem deste mesmo lugar:

  * o validador do layout (`layout_schema.py`), para recusar propriedade
    desconhecida ou valor fora do contrato;
  * o servico de layout, para criar um elemento novo ja com os padroes;
  * a interface do editor (etapa futura), para montar o painel de
    propriedades sem ter a lista repetida em JavaScript.

CATEGORIA
---------
A especificacao da etapa lista "documento, convidado, anfitriao,
calculado" como categorias -- mas esses sao os namespaces das FONTES DE
DADOS (ver `datasources.py`), nao dos tipos de elemento: os oito tipos
abaixo pertenceriam todos a "documento", o que nao ajudaria uma UI a
agrupar nada. Aqui a categoria separa o que a interface precisa separar:
`conteudo` (o que imprime texto ou dado) e `grafico` (o que desenha
forma ou imagem).

UNIDADES
--------
Geometria (`x`, `y`, `width`, `height`) e medidas visuais estao na
unidade do documento -- hoje `pt`, declarada em `DocumentType.page`. O
layout nao repete a unidade: quem a define e o tipo de documento.
"""

from dataclasses import dataclass, field

# --- codigos dos tipos ------------------------------------------------------

TEXT = "text"
RICH_TEXT = "rich_text"
NUMBER = "number"
IMAGE = "image"
QR_CODE = "qr_code"
TABLE = "table"
LINE = "line"
RECTANGLE = "rectangle"
# Marca "o que vem depois comeca na pagina seguinte" (editor rico). Nao
# desenha nada: o renderer conta as quebras para saber quantas paginas
# ha e em qual delas cada elemento cai (ver services/pdf).
PAGE_BREAK = "page_break"

# --- categorias -------------------------------------------------------------

CONTEUDO = "conteudo"
GRAFICO = "grafico"
# Nem conteudo nem desenho: organiza o documento (quebra de pagina).
ESTRUTURA = "estrutura"

# --- vocabularios fechados --------------------------------------------------

FONT_WEIGHTS = ("regular", "bold")
FONT_STYLES = ("normal", "italic")
TEXT_DECORATIONS = ("none", "underline", "line-through")
ALIGNMENTS = ("left", "center", "right", "justify")
VERTICAL_ALIGNMENTS = ("top", "middle", "bottom")
WHITE_SPACES = ("normal", "nowrap", "pre-wrap")
# O que fazer com texto que nao cabe na caixa reservada.
OVERFLOWS = ("clip", "shrink", "grow")
LINE_STYLES = ("solid", "dashed", "dotted")
IMAGE_FITS = ("contain", "cover", "fill")
QR_ERROR_LEVELS = ("L", "M", "Q", "H")

# Fontes que o motor de PDF sabe desenhar. Deliberadamente curto: uma
# fonte que o renderer nao tem viraria substituicao silenciosa no
# documento final.
#
#   LiberationSans -- embutida (pdfengine/fonts/), clone metrico da Arial,
#                     nas quatro faces: regular, bold, italico e
#                     bold-italico.
#   Times, Courier -- as 14 fontes padrao do PDF (Times-Roman, Courier e
#                     suas variantes), que todo leitor de PDF renderiza.
#                     Sao o equivalente de "Times New Roman" e "Courier
#                     New" do editor.
#
# Georgia e Manrope NAO estao aqui de proposito: nao ha equivalente livre
# que o motor possa embutir, e oferece-las no editor seria prometer uma
# tipografia que o documento nao tem.
FONT_FAMILIES = ("LiberationSans", "Times", "Courier")

# O estilo semantico de um bloco de texto no editor rico: paragrafo,
# titulo do documento ou subtitulo. O renderer nao le isto -- o que ele
# desenha vem de font_size/font_weight/align --; e o editor que o usa para
# mostrar no seletor "Estilo do bloco" o que o bloco e.
BLOCK_STYLES = ("p", "h1", "h2")


@dataclass(frozen=True)
class Propriedade:
    """
    A declaracao de uma propriedade: o que ela aceita e o que vale quando
    nao vem informada.

    `kind` diz ao validador COMO conferir o valor:

        texto      -- str
        numero     -- int/float finito (bool nao conta)
        positivo   -- numero > 0
        nao_neg    -- numero >= 0
        booleano   -- bool
        cor        -- "#rrggbb"
        escolha    -- um dos `opcoes`
        conteudo   -- bloco de conteudo estrutural (ver layout_schema)
        colunas    -- estrutura de colunas de tabela
        linhas     -- estrutura de linhas de tabela
        caixa      -- {top,right,bottom,left} em unidades do documento
    """

    nome: str
    label: str
    kind: str
    obrigatoria: bool = False
    padrao: object = None
    opcoes: tuple = ()
    # Cor de preenchimento pode ser ausente de proposito (transparente).
    permite_nulo: bool = False


def _caixa(valor=0.0):
    return {"top": valor, "right": valor, "bottom": valor, "left": valor}


# --- blocos de propriedades reutilizaveis -----------------------------------
#
# Tipografia aparece em text, rich_text, number e table. Declarar uma vez
# evita que os tipos divirjam sem ninguem perceber.

TIPOGRAFIA = (
    Propriedade("font_family", "Fonte", "escolha", padrao=FONT_FAMILIES[0],
                opcoes=FONT_FAMILIES),
    Propriedade("font_size", "Tamanho", "positivo", padrao=11.0),
    Propriedade("font_weight", "Peso", "escolha", padrao="regular", opcoes=FONT_WEIGHTS),
    Propriedade("font_style", "Estilo", "escolha", padrao="normal", opcoes=FONT_STYLES),
    Propriedade("text_decoration", "Decoração", "escolha", padrao="none",
                opcoes=TEXT_DECORATIONS),
    Propriedade("color", "Cor", "cor", padrao="#000000"),
    Propriedade("letter_spacing", "Espaço entre letras", "numero", padrao=0.0),
)

PARAGRAFO = (
    Propriedade("align", "Alinhamento", "escolha", padrao="left", opcoes=ALIGNMENTS),
    Propriedade("vertical_align", "Alinhamento vertical", "escolha", padrao="top",
                opcoes=VERTICAL_ALIGNMENTS),
    Propriedade("line_height", "Entrelinha", "positivo", padrao=1.25),
    Propriedade("white_space", "Quebra de linha", "escolha", padrao="normal",
                opcoes=WHITE_SPACES),
    Propriedade("overflow", "Transbordo", "escolha", padrao="shrink", opcoes=OVERFLOWS),
    Propriedade("padding", "Espaçamento interno", "caixa", padrao=_caixa()),
    # Idioma do trecho -- interessa a hifenizacao e a formatos de data.
    # Vazio significa "o idioma do documento".
    Propriedade("language", "Idioma", "texto", padrao=""),
    # --- editor rico (Etapa 3.7) ---
    # Recuo do texto a partir da borda esquerda da caixa, em pontos. E o
    # que uma lista usa para abrir espaco ao marcador, e o que os botoes
    # "Aumentar/Diminuir recuo" mexem.
    Propriedade("indent", "Recuo", "nao_neg", padrao=0.0),
    # Marcador desenhado no recuo ("1.", "•"). Texto explicito, e nao um
    # "tipo de lista" calculado na hora: o que o editor mostra e
    # exatamente o que o PDF escreve, sem duas numeracoes para divergir.
    Propriedade("list_marker", "Marcador de lista", "texto", padrao=""),
    Propriedade("block_style", "Estilo do bloco", "escolha", padrao="p",
                opcoes=BLOCK_STYLES),
)


@dataclass(frozen=True)
class TipoDeElemento:
    code: str
    label: str
    categoria: str
    propriedades: tuple = field(default_factory=tuple)
    # Quantos trechos de conteudo o tipo aceita: `rich_text` e o unico
    # que mistura texto fixo e campos na mesma linha corrida.
    aceita_conteudo_misto: bool = False

    @property
    def nomes_das_propriedades(self):
        return tuple(p.nome for p in self.propriedades)

    def propriedade(self, nome):
        for p in self.propriedades:
            if p.nome == nome:
                return p
        return None

    def padroes(self):
        """As propriedades com os seus valores padrao, prontas para um
        elemento novo. Copia rasa por chave; estruturas mutaveis sao
        recriadas por `_caixa()`/listas proprias no registro."""
        import copy as _copy

        return {p.nome: _copy.deepcopy(p.padrao) for p in self.propriedades}


TIPOS_PADRAO = (
    TipoDeElemento(
        code=TEXT,
        label="Texto",
        categoria=CONTEUDO,
        propriedades=(
            Propriedade("content", "Conteúdo", "conteudo", obrigatoria=True,
                        padrao={"kind": "text", "value": ""}),
            *TIPOGRAFIA,
            *PARAGRAFO,
        ),
    ),
    TipoDeElemento(
        code=RICH_TEXT,
        label="Parágrafo",
        categoria=CONTEUDO,
        aceita_conteudo_misto=True,
        propriedades=(
            Propriedade("content", "Conteúdo", "conteudo", obrigatoria=True,
                        padrao={"kind": "mixed", "parts": []}),
            *TIPOGRAFIA,
            *PARAGRAFO,
        ),
    ),
    TipoDeElemento(
        code=NUMBER,
        label="Número",
        categoria=CONTEUDO,
        propriedades=(
            Propriedade("content", "Conteúdo", "conteudo", obrigatoria=True,
                        padrao={"kind": "text", "value": "0"}),
            # Gabarito de formatacao, resolvido na geracao. Vazio =
            # imprime o valor como veio.
            Propriedade("format", "Formato", "texto", padrao=""),
            *TIPOGRAFIA,
            Propriedade("align", "Alinhamento", "escolha", padrao="right",
                        opcoes=ALIGNMENTS),
            Propriedade("vertical_align", "Alinhamento vertical", "escolha",
                        padrao="top", opcoes=VERTICAL_ALIGNMENTS),
            Propriedade("line_height", "Entrelinha", "positivo", padrao=1.25),
        ),
    ),
    TipoDeElemento(
        code=IMAGE,
        label="Imagem",
        categoria=GRAFICO,
        propriedades=(
            # A imagem em si vive no modelo Asset; o layout guarda so a
            # referencia. Nunca bytes, nunca base64.
            Propriedade("source", "Imagem", "conteudo", obrigatoria=True,
                        padrao={"kind": "asset", "asset_id": 0}),
            Propriedade("fit", "Ajuste", "escolha", padrao="contain", opcoes=IMAGE_FITS),
            Propriedade("preserve_aspect_ratio", "Manter proporção", "booleano",
                        padrao=True),
        ),
    ),
    TipoDeElemento(
        code=QR_CODE,
        label="QR Code",
        categoria=GRAFICO,
        propriedades=(
            Propriedade("source", "Conteúdo", "conteudo", obrigatoria=True,
                        padrao={"kind": "text", "value": ""}),
            Propriedade("margin", "Margem", "nao_neg", padrao=0.0),
            Propriedade("error_correction", "Correção de erro", "escolha", padrao="M",
                        opcoes=QR_ERROR_LEVELS),
        ),
    ),
    TipoDeElemento(
        code=LINE,
        label="Linha",
        categoria=GRAFICO,
        propriedades=(
            Propriedade("thickness", "Espessura", "positivo", padrao=1.0),
            Propriedade("style", "Estilo", "escolha", padrao="solid", opcoes=LINE_STYLES),
            Propriedade("color", "Cor", "cor", padrao="#000000"),
        ),
    ),
    TipoDeElemento(
        code=RECTANGLE,
        label="Retângulo",
        categoria=GRAFICO,
        propriedades=(
            Propriedade("border_width", "Espessura da borda", "nao_neg", padrao=1.0),
            Propriedade("border_style", "Estilo da borda", "escolha", padrao="solid",
                        opcoes=LINE_STYLES),
            Propriedade("border_color", "Cor da borda", "cor", padrao="#000000"),
            # Ausente (None) = sem preenchimento.
            Propriedade("fill_color", "Preenchimento", "cor", padrao=None,
                        permite_nulo=True),
            Propriedade("radius", "Raio dos cantos", "nao_neg", padrao=0.0),
        ),
    ),
    TipoDeElemento(
        code=TABLE,
        label="Tabela",
        categoria=CONTEUDO,
        propriedades=(
            Propriedade("columns", "Colunas", "colunas", obrigatoria=True, padrao=[]),
            Propriedade("rows", "Linhas", "linhas", obrigatoria=True, padrao=[]),
            Propriedade("border_width", "Espessura das bordas", "nao_neg", padrao=0.5),
            Propriedade("border_color", "Cor das bordas", "cor", padrao="#000000"),
            Propriedade("cell_padding", "Espaçamento das células", "caixa",
                        padrao=_caixa(2.0)),
            *TIPOGRAFIA,
            Propriedade("align", "Alinhamento", "escolha", padrao="left",
                        opcoes=ALIGNMENTS),
            Propriedade("line_height", "Entrelinha", "positivo", padrao=1.25),
        ),
    ),
    # Sem propriedades: a quebra e so uma posicao. `x`/`width` sao os da
    # pagina e `height` e zero; o que importa e o `y` -- tudo o que vier
    # abaixo dele pertence a pagina seguinte.
    TipoDeElemento(
        code=PAGE_BREAK,
        label="Quebra de página",
        categoria=ESTRUTURA,
    ),
)

_TIPOS = {tipo.code: tipo for tipo in TIPOS_PADRAO}


class TipoDesconhecidoError(KeyError):
    """O `type` do elemento nao esta registrado."""


def registrar_tipo(tipo, *, substituir=False):
    """Acrescenta um tipo ao registro. Existe para extensao e para testes."""
    if not substituir and tipo.code in _TIPOS:
        raise ValueError(f'O tipo "{tipo.code}" já está registrado.')
    _TIPOS[tipo.code] = tipo
    return tipo


def remover_tipo(code):
    _TIPOS.pop(code, None)


def tipos():
    return tuple(_TIPOS.values())


def codigos():
    return tuple(_TIPOS)


def tipo(code):
    try:
        return _TIPOS[code]
    except KeyError:
        raise TipoDesconhecidoError(
            f'Não existe o tipo de elemento "{code}". '
            f"Disponíveis: {', '.join(sorted(_TIPOS))}."
        ) from None


def para_o_editor():
    """O registro na forma que a paleta do editor consome."""
    return [
        {
            "code": t.code,
            "label": t.label,
            "category": t.categoria,
            "properties": [
                {
                    "name": p.nome,
                    "label": p.label,
                    "kind": p.kind,
                    "required": p.obrigatoria,
                    "default": p.padrao,
                    "options": list(p.opcoes),
                }
                for p in t.propriedades
            ],
        }
        for t in _TIPOS.values()
    ]
