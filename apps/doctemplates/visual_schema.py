"""
Contrato do MODELO VISUAL de um documento (Fase 5, Etapa 4.2A).

Este modulo responde a uma pergunta so: ONDE cada coisa fica na pagina.
Quem responde "o que a pessoa preenche" e `schema.py` (o `field_schema`),
que continua intocado -- sao dois contratos independentes de proposito:
reposicionar um rotulo nao pode exigir mexer no formulario, e acrescentar
um campo ao formulario nao obriga a desenhar nada.


SISTEMA DE COORDENADAS
----------------------
UNIDADE: pontos PDF (pt). Nunca pixels. Pixel e uma escolha de
visualizacao do navegador e muda com o zoom; ponto e a unidade fisica do
papel e nao muda nunca.

ORIGEM: canto SUPERIOR esquerdo, com Y crescendo para BAIXO.

    (0,0) ┌──────────────┐
          │   x ->       │
          │   y          │
          │   |          │
          │   v          │
          └──────────────┘

Essa escolha e deliberada e vale a pena explicar, porque o PDF usa o
sistema OPOSTO (origem embaixo, Y para cima):

  * o editor vive no navegador, onde CSS, eventos de mouse e `getBoundingClientRect`
    todos usam origem em cima. Guardar em cima significa que arrastar um
    elemento 10pt para baixo soma 10 a `y` -- sem inversao no meio do
    caminho, que e exatamente o tipo de conta que se erra uma vez e
    depois ninguem acha;
  * a conversao para o sistema do PDF acontece num lugar unico e testado
    (`para_coordenadas_pdf`), no momento de gerar o documento -- a Etapa
    4.2D --, nao espalhada pelo editor.

NUNCA misturar os dois sistemas sem passar por `coordinates.py`.


PRECISAO
--------
As coordenadas sao guardadas como float, sem arredondamento. O documento
oficial frances foi medido com casas decimais (ver
`pdfengine/layouts/carta_convite_fr.py`) e arredondar para o inteiro mais
proximo deslocaria o texto visivelmente. `595.2756` nao e `595`.


POR QUE UM JSON ATOMICO, E NAO TABELAS
--------------------------------------
Um documento e lido e gravado inteiro, sempre. Modelar elemento como
linha de tabela obrigaria a transacoes, ordenacao e joins para reconstruir
algo que so faz sentido junto -- e, pior, quebraria a imutabilidade: hoje
uma `TemplateVersion` publicada e congelada comparando campos em
`save()`. Com o layout num unico JSONField, a mesma regra que ja protege
`field_schema` protege o visual de graca.
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Versao do formato. Subir quando a estrutura mudar de um jeito que exija
# migracao dos documentos ja gravados.
SCHEMA_VERSION = 1

# A4 em pontos. Nao arredondar: sao as medidas reais do papel.
A4_WIDTH_PT = 595.2756
A4_HEIGHT_PT = 841.8898

UNIT = "pt"
ORIGIN = "top-left"

# --- Tipos de elemento ------------------------------------------------------

TEXT = "text"
FIELD = "field"
IMAGE = "image"
LINE = "line"
RECT = "rect"
QRCODE = "qrcode"
TABLE = "table"

# Paragrafo que MISTURA texto fixo e campos na mesma linha corrida.
#
# Por que existe (Etapa 4.2B): o documento oficial frances tem frases
# como "Je soussignée, <host_name>, née le <host_birth>, ... invite par
# la présente :" -- um unico paragrafo justificado onde os valores
# entram no meio do texto. Com `text` e `field` separados seria preciso
# uma caixa posicionada por trecho, e a posicao de cada trecho so existe
# depois de medir o texto na hora de desenhar (o renderer faz isso, com
# justificacao). Ou seja: representar essas frases com os tipos
# anteriores exigiria INVENTAR coordenadas que ninguem mediu.
#
# `rich_text` guarda a sequencia de trechos (`runs`) exatamente como o
# mapa do renderer ja a descreve, e deixa a medicao para quem desenha --
# que e onde ela pode ser feita com exatidao.
RICH_TEXT = "rich_text"

ELEMENT_TYPES = (TEXT, FIELD, IMAGE, LINE, RECT, QRCODE, TABLE, RICH_TEXT)

# Atributos de caixa que todo elemento tem, seja qual for o tipo.
GEOMETRY_KEYS = ("x", "y", "width", "height")

ALIGNMENTS = ("left", "center", "right", "justify")
VERTICAL_ALIGNMENTS = ("top", "middle", "bottom")
FONT_WEIGHTS = ("regular", "bold")
# Como tratar texto que nao cabe na caixa reservada.
OVERFLOW_MODES = ("clip", "shrink", "grow")
# Niveis de correcao de erro do QR, na nomenclatura do proprio padrao.
QR_ERROR_LEVELS = ("L", "M", "Q", "H")

# Fontes que o motor de PDF sabe embutir hoje (ver pdfengine/fontconfig.py).
# Manter curto de proposito: uma fonte que o renderer nao tem vira um PDF
# com a fonte trocada silenciosamente.
FONT_FAMILIES = ("LiberationSans",)

MAX_ELEMENTS = 500
MAX_TEXT_LENGTH = 5000
# Trechos de um paragrafo misto. O maior do documento oficial tem 15.
MAX_RUNS = 100
# Um documento gigante trava o editor e nao cabe no papel; o limite existe
# para a validacao falhar com uma mensagem, em vez de o navegador morrer.
MAX_TABLE_ROWS = 200
MAX_TABLE_COLUMNS = 20


def documento_vazio():
    """Um documento novo: pagina A4 em branco, sem elementos."""
    return {
        "schema_version": SCHEMA_VERSION,
        "page": {
            "width": A4_WIDTH_PT,
            "height": A4_HEIGHT_PT,
            "unit": UNIT,
            "origin": ORIGIN,
        },
        "elements": [],
    }


# ---------------------------------------------------------------------------
# Validacao
# ---------------------------------------------------------------------------
#
# Roda no servidor, SEMPRE, mesmo que o editor ja tenha validado no
# navegador: o JSON chega por POST e quem envia pode ser qualquer coisa.


def _numero(valor, descricao):
    """Um numero real de verdade -- bool nao conta, `float("nan")` nao conta."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValidationError(
            _('%(desc)s precisa ser um número.') % {"desc": descricao}
        )
    valor = float(valor)
    if valor != valor or valor in (float("inf"), float("-inf")):
        raise ValidationError(
            _('%(desc)s precisa ser um número finito.') % {"desc": descricao}
        )
    return valor


def _texto(valor, descricao, *, maximo=MAX_TEXT_LENGTH, obrigatorio=False):
    if valor is None and not obrigatorio:
        return ""
    if not isinstance(valor, str):
        raise ValidationError(
            _('%(desc)s precisa ser um texto.') % {"desc": descricao}
        )
    if obrigatorio and not valor.strip():
        raise ValidationError(
            _('%(desc)s não pode ficar vazio.') % {"desc": descricao}
        )
    if len(valor) > maximo:
        raise ValidationError(
            _('%(desc)s passa do limite de %(max)s caracteres.')
            % {"desc": descricao, "max": maximo}
        )
    return valor


def _escolha(valor, opcoes, descricao):
    if valor not in opcoes:
        raise ValidationError(
            _('%(desc)s deve ser um de: %(opcoes)s.')
            % {"desc": descricao, "opcoes": ", ".join(opcoes)}
        )
    return valor


def _validar_pagina(page):
    if not isinstance(page, dict):
        raise ValidationError(_('"page" deve ser um objeto.'))

    largura = _numero(page.get("width"), _("A largura da página"))
    altura = _numero(page.get("height"), _("A altura da página"))
    if largura <= 0 or altura <= 0:
        raise ValidationError(_("A página precisa ter largura e altura positivas."))

    if page.get("unit", UNIT) != UNIT:
        raise ValidationError(
            _('A unidade da página deve ser "%(unit)s".') % {"unit": UNIT}
        )
    if page.get("origin", ORIGIN) != ORIGIN:
        raise ValidationError(
            _('A origem das coordenadas deve ser "%(origin)s".') % {"origin": ORIGIN}
        )


def _validar_geometria(elemento, indice, page):
    posicao = {}
    for chave in GEOMETRY_KEYS:
        posicao[chave] = _numero(
            elemento.get(chave),
            _('"%(chave)s" do elemento na posição %(i)s') % {"chave": chave, "i": indice},
        )

    if posicao["width"] < 0 or posicao["height"] < 0:
        raise ValidationError(
            _("O elemento na posição %(i)s tem largura ou altura negativa.")
            % {"i": indice}
        )

    # Deliberadamente NAO recusamos elemento fora da pagina: no meio de um
    # arrasto e normal passar da borda, e recusar o salvamento faria o
    # editor perder trabalho. O renderer e que recorta.
    return posicao


def _validar_propriedades_texto(props, indice):
    _texto(props.get("content"), _("O conteúdo do texto"))
    _escolha(
        props.get("font_family", FONT_FAMILIES[0]), FONT_FAMILIES, _("A fonte")
    )
    tamanho = _numero(props.get("font_size", 11), _("O tamanho da fonte"))
    if tamanho <= 0:
        raise ValidationError(
            _("O elemento na posição %(i)s tem tamanho de fonte inválido.")
            % {"i": indice}
        )
    _escolha(props.get("font_weight", "regular"), FONT_WEIGHTS, _("O peso da fonte"))
    _escolha(props.get("align", "left"), ALIGNMENTS, _("O alinhamento"))
    _escolha(
        props.get("vertical_align", "top"), VERTICAL_ALIGNMENTS, _("O alinhamento vertical")
    )
    _escolha(props.get("overflow", "shrink"), OVERFLOW_MODES, _("O modo de transbordo"))
    _numero(props.get("line_height", 1.25), _("A altura da linha"))
    _numero(props.get("letter_spacing", 0), _("O espaçamento entre letras"))
    _validar_cor(props.get("color", "#000000"), _("A cor do texto"))
    if not isinstance(props.get("italic", False), bool):
        raise ValidationError(_('"italic" deve ser verdadeiro ou falso.'))
    if not isinstance(props.get("wrap", True), bool):
        raise ValidationError(_('"wrap" deve ser verdadeiro ou falso.'))


def _validar_cor(valor, descricao):
    """Cor em hexadecimal `#rrggbb`. Nada de `rgb()`, `url()` ou nome livre."""
    texto = _texto(valor, descricao, maximo=7, obrigatorio=True)
    if len(texto) != 7 or not texto.startswith("#"):
        raise ValidationError(
            _('%(desc)s deve estar no formato #rrggbb.') % {"desc": descricao}
        )
    try:
        int(texto[1:], 16)
    except ValueError:
        raise ValidationError(
            _('%(desc)s deve estar no formato #rrggbb.') % {"desc": descricao}
        ) from None
    return texto


def _validar_propriedades_campo(props, indice, chaves_validas, para_publicar):
    """
    Um campo guarda so a REFERENCIA (`field`), nunca o valor. O valor vem
    da carta no momento de gerar o PDF -- guardar aqui congelaria o dado
    de uma pessoa dentro do modelo.
    """
    referencia = _texto(
        props.get("field"),
        _("A referência do campo"),
        maximo=200,
        obrigatorio=para_publicar,
    )

    if not referencia:
        # Rascunho pode ter o campo ainda por escolher: e assim que se
        # trabalha -- larga o elemento na pagina, decide depois. O editor
        # marca como incompleto e a publicacao barra.
        _validar_propriedades_texto(props, indice)
        return

    if chaves_validas is not None and referencia not in chaves_validas:
        raise ValidationError(
            _('O elemento na posição %(i)s aponta para o campo "%(ref)s", que não '
              "existe na configuração de campos desta versão.")
            % {"i": indice, "ref": referencia}
        )

    # A aparencia de um campo e a de um texto: mesma validacao.
    _validar_propriedades_texto(props, indice)


def _validar_propriedades_rich_text(props, indice, chaves_validas, para_publicar):
    """
    Um paragrafo de trechos. Cada trecho e texto fixo (`text`) OU uma
    referencia de campo (`field`) -- nunca os dois: sao coisas
    diferentes, e aceitar as duas chaves juntas deixaria ambiguo o que
    desenhar.
    """
    _validar_propriedades_texto(props, indice)

    runs = props.get("runs")
    if not isinstance(runs, list):
        raise ValidationError(
            _('"runs" do elemento na posição %(i)s deve ser uma lista.') % {"i": indice}
        )
    if len(runs) > MAX_RUNS:
        raise ValidationError(
            _("O elemento na posição %(i)s passa de %(max)s trechos.")
            % {"i": indice, "max": MAX_RUNS}
        )

    for posicao, trecho in enumerate(runs):
        if not isinstance(trecho, dict):
            raise ValidationError(
                _("O trecho %(t)s do elemento na posição %(i)s deve ser um objeto.")
                % {"t": posicao, "i": indice}
            )
        tem_texto = "text" in trecho
        referencia = trecho.get("field")
        if tem_texto and referencia:
            raise ValidationError(
                _('O trecho %(t)s do elemento na posição %(i)s tem "text" e "field" '
                  "ao mesmo tempo.")
                % {"t": posicao, "i": indice}
            )
        if referencia:
            referencia = _texto(
                referencia, _("A referência de um trecho"), maximo=200, obrigatorio=True
            )
            if chaves_validas is not None and referencia not in chaves_validas:
                raise ValidationError(
                    _('Um trecho aponta para o campo "%(ref)s", que não existe.')
                    % {"ref": referencia}
                )
        elif tem_texto:
            _texto(trecho.get("text"), _("O texto de um trecho"))
        else:
            raise ValidationError(
                _('O trecho %(t)s do elemento na posição %(i)s precisa de "text" '
                  'ou "field".')
                % {"t": posicao, "i": indice}
            )
        if not isinstance(trecho.get("bold", False), bool):
            raise ValidationError(_('"bold" de um trecho deve ser verdadeiro ou falso.'))

    # `leading` em PONTOS, nao multiplicador: o renderer trabalha com
    # entrelinha absoluta (13,5pt no documento oficial) e um
    # multiplicador faria esse valor voltar diferente do medido.
    leading = _numero(props.get("leading", 13.5), _("A entrelinha"))
    if leading <= 0:
        raise ValidationError(
            _("O elemento na posição %(i)s tem entrelinha inválida.") % {"i": indice}
        )
    _numero(props.get("min_font_size", 9.0), _("O tamanho mínimo da fonte"))

    max_linhas = props.get("max_lines", 1)
    if isinstance(max_linhas, bool) or not isinstance(max_linhas, int) or max_linhas < 1:
        raise ValidationError(
            _('"max_lines" do elemento na posição %(i)s deve ser um inteiro positivo.')
            % {"i": indice}
        )


def _validar_propriedades_imagem(props, indice, assets_validos, para_publicar):
    asset_id = props.get("asset_id")
    if not isinstance(asset_id, int) or isinstance(asset_id, bool) or asset_id < 0:
        raise ValidationError(
            _('"asset_id" do elemento na posição %(i)s deve ser um número inteiro.')
            % {"i": indice}
        )
    if asset_id == 0:
        # Imagem ainda por escolher -- so bloqueia na publicacao.
        if para_publicar:
            raise ValidationError(
                _("O elemento na posição %(i)s precisa referenciar uma imagem cadastrada.")
                % {"i": indice}
            )
        return
    if assets_validos is not None and asset_id not in assets_validos:
        raise ValidationError(
            _("A imagem #%(id)s do elemento na posição %(i)s não existe ou não está ativa.")
            % {"id": asset_id, "i": indice}
        )
    if not isinstance(props.get("preserve_aspect_ratio", True), bool):
        raise ValidationError(_('"preserve_aspect_ratio" deve ser verdadeiro ou falso.'))


def _validar_propriedades_linha(props, indice):
    espessura = _numero(props.get("thickness", 1), _("A espessura da linha"))
    if espessura <= 0:
        raise ValidationError(
            _("O elemento na posição %(i)s tem espessura inválida.") % {"i": indice}
        )
    _validar_cor(props.get("color", "#000000"), _("A cor da linha"))


def _validar_propriedades_retangulo(props, indice):
    _numero(props.get("border_width", 1), _("A espessura da borda"))
    _validar_cor(props.get("border_color", "#000000"), _("A cor da borda"))
    preenchimento = props.get("fill_color")
    if preenchimento is not None:
        _validar_cor(preenchimento, _("A cor de preenchimento"))
    _numero(props.get("radius", 0), _("O raio dos cantos"))


def _validar_propriedades_qr(props, indice, para_publicar):
    # `content` e um gabarito: pode conter referencias que so serao
    # resolvidas na geracao (ex.: a URL de verificacao da carta).
    # Vazio so e problema na hora de publicar.
    _texto(
        props.get("content"),
        _("O conteúdo do QR"),
        maximo=2000,
        obrigatorio=para_publicar,
    )
    _escolha(
        props.get("error_correction", "M"), QR_ERROR_LEVELS, _("O nível de correção do QR")
    )


def _validar_propriedades_tabela(props, indice, chaves_validas):
    colunas = props.get("columns")
    if not isinstance(colunas, list) or not colunas:
        raise ValidationError(
            _("A tabela na posição %(i)s precisa de pelo menos uma coluna.") % {"i": indice}
        )
    if len(colunas) > MAX_TABLE_COLUMNS:
        raise ValidationError(
            _("A tabela na posição %(i)s passa de %(max)s colunas.")
            % {"i": indice, "max": MAX_TABLE_COLUMNS}
        )
    for posicao, coluna in enumerate(colunas):
        if not isinstance(coluna, dict):
            raise ValidationError(_("Cada coluna da tabela deve ser um objeto."))
        largura = _numero(coluna.get("width"), _("A largura de uma coluna"))
        if largura <= 0:
            raise ValidationError(
                _("A coluna %(c)s da tabela na posição %(i)s tem largura inválida.")
                % {"c": posicao, "i": indice}
            )
        _escolha(coluna.get("align", "left"), ALIGNMENTS, _("O alinhamento da coluna"))

    linhas = props.get("rows")
    if not isinstance(linhas, list):
        raise ValidationError(_('"rows" da tabela deve ser uma lista.'))
    if len(linhas) > MAX_TABLE_ROWS:
        raise ValidationError(
            _("A tabela na posição %(i)s passa de %(max)s linhas.")
            % {"i": indice, "max": MAX_TABLE_ROWS}
        )

    for numero, linha in enumerate(linhas):
        if not isinstance(linha, dict):
            raise ValidationError(_("Cada linha da tabela deve ser um objeto."))
        _numero(linha.get("min_height", 0), _("A altura mínima da linha"))
        celulas = linha.get("cells")
        if not isinstance(celulas, list):
            raise ValidationError(_('"cells" de uma linha deve ser uma lista.'))
        if len(celulas) != len(colunas):
            raise ValidationError(
                _("A linha %(l)s da tabela na posição %(i)s tem %(tem)s células, "
                  "mas a tabela tem %(cols)s colunas.")
                % {"l": numero, "i": indice, "tem": len(celulas), "cols": len(colunas)}
            )
        for celula in celulas:
            if not isinstance(celula, dict):
                raise ValidationError(_("Cada célula da tabela deve ser um objeto."))
            # Uma celula e texto fixo OU referencia de campo -- nunca as duas.
            referencia = celula.get("field")
            if referencia:
                referencia = _texto(referencia, _("A referência de uma célula"), maximo=200)
                if chaves_validas is not None and referencia not in chaves_validas:
                    raise ValidationError(
                        _('Uma célula da tabela aponta para o campo "%(ref)s", que não existe.')
                        % {"ref": referencia}
                    )
            else:
                _texto(celula.get("content"), _("O conteúdo de uma célula"))
            _escolha(celula.get("align", "left"), ALIGNMENTS, _("O alinhamento de uma célula"))
            if not isinstance(celula.get("bold", False), bool):
                raise ValidationError(_('"bold" de uma célula deve ser verdadeiro ou falso.'))

    _numero(props.get("padding", 4), _("O espaçamento interno da tabela"))
    _numero(props.get("border_width", 0.5), _("A espessura das bordas da tabela"))
    _validar_cor(props.get("border_color", "#000000"), _("A cor das bordas da tabela"))


_VALIDADORES = {
    TEXT: lambda props, i, campos, assets, pub: _validar_propriedades_texto(props, i),
    FIELD: lambda props, i, campos, assets, pub: _validar_propriedades_campo(
        props, i, campos, pub
    ),
    IMAGE: lambda props, i, campos, assets, pub: _validar_propriedades_imagem(
        props, i, assets, pub
    ),
    LINE: lambda props, i, campos, assets, pub: _validar_propriedades_linha(props, i),
    RECT: lambda props, i, campos, assets, pub: _validar_propriedades_retangulo(props, i),
    QRCODE: lambda props, i, campos, assets, pub: _validar_propriedades_qr(props, i, pub),
    TABLE: lambda props, i, campos, assets, pub: _validar_propriedades_tabela(
        props, i, campos
    ),
    RICH_TEXT: lambda props, i, campos, assets, pub: _validar_propriedades_rich_text(
        props, i, campos, pub
    ),
}


def validate_visual_schema(schema, *, field_keys=None, asset_ids=None, para_publicar=False):
    """
    Levanta ValidationError se `schema` nao for um documento visual valido.

    `{}` e valido: uma versao pode ainda nao ter layout nenhum -- e o
    estado de toda versao criada antes desta etapa.

    `field_keys` e `asset_ids`, quando fornecidos, ligam o documento ao
    resto do sistema: um campo so pode apontar para uma chave que existe
    no `field_schema` daquela versao, e uma imagem so para um Asset ativo.
    Ficam opcionais porque a validacao estrutural precisa rodar tambem em
    `Model.clean()`, onde consultar o banco a cada save seria caro.

    `para_publicar` aperta a regra. Rascunho aceita elemento INCOMPLETO --
    um campo ainda sem referencia, uma imagem ainda sem arquivo, um QR
    ainda sem conteudo --, porque e assim que se desenha: larga na pagina
    e decide depois; recusar o salvamento faria perder trabalho. Publicar
    e o momento em que o documento vira imutavel, e ai nada pode ficar
    pela metade.
    """
    if not isinstance(schema, dict):
        raise ValidationError(_("O modelo visual deve ser um objeto (JSON)."))

    if not schema:
        return

    versao = schema.get("schema_version")
    if versao != SCHEMA_VERSION:
        raise ValidationError(
            _('O modelo visual está na versão de formato "%(tem)s"; esperada "%(esperada)s".')
            % {"tem": versao, "esperada": SCHEMA_VERSION}
        )

    _validar_pagina(schema.get("page"))

    elementos = schema.get("elements")
    if not isinstance(elementos, list):
        raise ValidationError(_('"elements" deve ser uma lista.'))
    if len(elementos) > MAX_ELEMENTS:
        raise ValidationError(
            _("O documento passa do limite de %(max)s elementos.") % {"max": MAX_ELEMENTS}
        )

    vistos = set()
    for indice, elemento in enumerate(elementos):
        if not isinstance(elemento, dict):
            raise ValidationError(
                _("O elemento na posição %(i)s deve ser um objeto.") % {"i": indice}
            )

        identificador = _texto(
            elemento.get("id"),
            _('"id" do elemento na posição %(i)s') % {"i": indice},
            maximo=64,
            obrigatorio=True,
        )
        if identificador in vistos:
            raise ValidationError(
                _('Há mais de um elemento com o id "%(id)s".') % {"id": identificador}
            )
        vistos.add(identificador)

        tipo = elemento.get("type")
        if tipo not in ELEMENT_TYPES:
            raise ValidationError(
                _('O elemento na posição %(i)s tem tipo desconhecido: "%(tipo)s".')
                % {"i": indice, "tipo": tipo}
            )

        _validar_geometria(elemento, indice, schema["page"])

        z = elemento.get("z_index", 0)
        if isinstance(z, bool) or not isinstance(z, int):
            raise ValidationError(
                _('"z_index" do elemento na posição %(i)s deve ser um número inteiro.')
                % {"i": indice}
            )

        propriedades = elemento.get("properties", {})
        if not isinstance(propriedades, dict):
            raise ValidationError(
                _('"properties" do elemento na posição %(i)s deve ser um objeto.')
                % {"i": indice}
            )

        _VALIDADORES[tipo](propriedades, indice, field_keys, asset_ids, para_publicar)


def field_keys_of(field_schema):
    """As chaves de campo declaradas num `field_schema` -- o que um elemento
    do tipo `field` pode referenciar."""
    if not isinstance(field_schema, dict):
        return set()
    return {
        campo.get("key")
        for campo in field_schema.get("fields", [])
        if isinstance(campo, dict) and campo.get("key")
    }
