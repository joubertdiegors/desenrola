"""
Contrato do LAYOUT de um `DocumentTemplate` (Etapa 3.1).

    {
      "version": 1,
      "elements": [
        {
          "id": "a1b2c3",
          "type": "text",
          "x": 49.6, "y": 120.0, "width": 400.0, "height": 13.5,
          "properties": { "content": {...}, "font_size": 11.0, ... }
        }
      ]
    }

`{}` tambem e valido: e o estado de um modelo ainda sem desenho -- os
quatro oficiais nascem assim.


POR QUE UM CONTRATO NOVO, E NAO A EVOLUCAO DE `visual_schema.py`
----------------------------------------------------------------
`visual_schema.py` existe e descreve um layout -- mas descreve o layout
da arquitetura ANTIGA (`TemplateVersion.visual_schema`), que continua em
uso: e ele que `TemplateVersion.clean()` valida, que o importador do PDF
produz e que o editor atual desenha. Mais de uma dezena de modulos
dependem daquele formato exato.

Os dois contratos divergem em pontos que nao dao para conciliar sem
quebrar um dos lados:

    visual_schema (antigo)          layout (novo)
    ----------------------          -------------------------------
    schema_version + page           version (a pagina vem do
                                    DocumentType, nao se repete)
    z_index numerico                a ORDEM da lista e a camada
    tipo `field` proprio            campo e CONTEUDO de text/number
    `rect`, `qrcode`                `rectangle`, `qr_code`
    sem `number`                    `number`
    properties.field = "guest_name" content = {kind, source} com
    (vocabulario plano)             namespace: "convidado.nome"

Evoluir o modulo antigo no lugar quebraria a importacao do documento
frances e a suite que a protege. Entao sao dois contratos, um por
arquitetura, enquanto as duas coexistem. O antigo morre junto com
`TemplateVersion`, no cutover -- e este fica.


CONTEUDO ESTRUTURAL, NAO PLACEHOLDER
------------------------------------
Um campo dinamico NAO e `{{nome}}` dentro de uma string. E um bloco:

    {"kind": "text",  "value": "Je soussigné "}
    {"kind": "field", "source": "convidado.nome"}
    {"kind": "mixed", "parts": [ <text>, <field>, <text> ]}

`mixed` e o que permite "Je soussigné " + convidado.nome + ", domicilié
à " + anfitriao.endereco numa linha corrida -- e so `rich_text` o
aceita, porque so ele sabe fluir trechos de pesos diferentes. Cada
`source` e conferido contra `datasources.py`: uma referencia inexistente
e recusada aqui, nao descoberta na hora de gerar o documento.

Um trecho de `mixed` pode ainda declarar `font_weight` e/ou `font_style`
proprios:

    {"kind": "text", "value": "Je soussignée, "}
    {"kind": "field", "source": "anfitriao.nome", "font_weight": "bold"}

E o que permite ENFASE DENTRO da linha corrida -- negritar so o nome no
meio da frase. Ausentes, o trecho herda o peso e o estilo do elemento; o
vocabulario e o mesmo de `elements.py`, para nao haver um segundo jeito
de dizer "negrito". So valem dentro de `mixed`: num bloco de conteudo
solto quem manda e a propriedade do proprio elemento, e aceitar os dois
caminhos criaria ambiguidade sobre qual vence.


CAMADAS
-------
Nao ha `z_index`. A ORDEM da lista `elements` e a ordem de desenho: o
primeiro fica ao fundo, o ultimo por cima. Uma fonte de verdade so,
sem empates possiveis e sem renumerar nada ao reordenar.


UNIDADES E PRECISAO
-------------------
Coordenadas e medidas estao na unidade do documento (`DocumentType.page`,
hoje `pt`). Guardadas como float, sem arredondamento: o documento oficial
frances foi medido com casas decimais e arredondar deslocaria o texto.
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from . import datasources, elements

# Versao do formato. Subir quando a estrutura mudar de um jeito que exija
# migrar os layouts ja gravados.
VERSION = 1

# Formas de conteudo estrutural.
KIND_TEXT = "text"
KIND_FIELD = "field"
KIND_MIXED = "mixed"
KIND_ASSET = "asset"
CONTENT_KINDS = (KIND_TEXT, KIND_FIELD, KIND_MIXED, KIND_ASSET)

MAX_ELEMENTS = 500
MAX_TEXT_LENGTH = 5000
MAX_PARTS = 100
MAX_TABLE_ROWS = 200
MAX_TABLE_COLUMNS = 20
MAX_ID_LENGTH = 64

LADOS_DA_CAIXA = ("top", "right", "bottom", "left")


def layout_vazio():
    """Um layout novo: sem elementos."""
    return {"version": VERSION, "elements": []}


# ---------------------------------------------------------------------------
# Conferencias basicas
# ---------------------------------------------------------------------------


def _numero(valor, descricao):
    """Numero real de verdade -- bool nao conta, NaN e infinito nao contam."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValidationError(_("%(desc)s precisa ser um número.") % {"desc": descricao})
    valor = float(valor)
    if valor != valor or valor in (float("inf"), float("-inf")):
        raise ValidationError(
            _("%(desc)s precisa ser um número finito.") % {"desc": descricao}
        )
    return valor


def _texto(valor, descricao, *, maximo=MAX_TEXT_LENGTH, obrigatorio=False):
    if valor is None and not obrigatorio:
        return ""
    if not isinstance(valor, str):
        raise ValidationError(_("%(desc)s precisa ser um texto.") % {"desc": descricao})
    if obrigatorio and not valor.strip():
        raise ValidationError(_("%(desc)s não pode ficar vazio.") % {"desc": descricao})
    if len(valor) > maximo:
        raise ValidationError(
            _("%(desc)s passa do limite de %(max)s caracteres.")
            % {"desc": descricao, "max": maximo}
        )
    return valor


def _cor(valor, descricao):
    """Cor em `#rrggbb`. Nada de `rgb()`, `url()` ou nome livre."""
    texto = _texto(valor, descricao, maximo=7, obrigatorio=True)
    if len(texto) != 7 or not texto.startswith("#"):
        raise ValidationError(
            _("%(desc)s deve estar no formato #rrggbb.") % {"desc": descricao}
        )
    try:
        int(texto[1:], 16)
    except ValueError:
        raise ValidationError(
            _("%(desc)s deve estar no formato #rrggbb.") % {"desc": descricao}
        ) from None
    return texto


def _caixa(valor, descricao):
    """`{top, right, bottom, left}`, todos numeros não negativos."""
    if not isinstance(valor, dict):
        raise ValidationError(
            _("%(desc)s deve ser um objeto com top, right, bottom e left.")
            % {"desc": descricao}
        )
    for lado in LADOS_DA_CAIXA:
        medida = _numero(valor.get(lado, 0), f"{descricao} ({lado})")
        if medida < 0:
            raise ValidationError(
                _("%(desc)s não pode ser negativo.") % {"desc": f"{descricao} ({lado})"}
            )
    return valor


def _escolha(valor, opcoes, descricao):
    if valor not in opcoes:
        raise ValidationError(
            _("%(desc)s deve ser um de: %(opcoes)s.")
            % {"desc": descricao, "opcoes": ", ".join(map(str, opcoes))}
        )
    return valor


# ---------------------------------------------------------------------------
# Conteudo estrutural
# ---------------------------------------------------------------------------


# Estilo que um TRECHO de `mixed` pode sobrepor ao do elemento. Mesmos
# vocabularios de `elements.py`.
ENFASE_DO_TRECHO = ("font_weight", "font_style")


def _validar_enfase(parte, descricao):
    """
    A enfase opcional de um trecho de `mixed`.

    Ausente significa "herda do elemento" -- por isso nada aqui e
    obrigatorio. Presente, tem de ser um valor do vocabulario, senao um
    "font_weight": "negrito" passaria batido e sumiria na geracao.
    """
    if not isinstance(parte, dict):
        return
    if "font_weight" in parte:
        _escolha(parte["font_weight"], elements.FONT_WEIGHTS, f"{descricao} (peso)")
    if "font_style" in parte:
        _escolha(parte["font_style"], elements.FONT_STYLES, f"{descricao} (estilo)")


def validar_conteudo(bloco, descricao, *, permite_misto=False, profundidade=0):
    """
    Um bloco de conteudo: texto fixo, referencia de campo, imagem ou uma
    sequencia deles.
    """
    if not isinstance(bloco, dict):
        raise ValidationError(_("%(desc)s deve ser um objeto.") % {"desc": descricao})

    kind = bloco.get("kind")
    if kind not in CONTENT_KINDS:
        raise ValidationError(
            _('%(desc)s tem forma desconhecida: "%(kind)s". Use uma de: %(kinds)s.')
            % {"desc": descricao, "kind": kind, "kinds": ", ".join(CONTENT_KINDS)}
        )

    if kind == KIND_TEXT:
        _texto(bloco.get("value"), f"{descricao} (texto)")
        return bloco

    if kind == KIND_FIELD:
        referencia = _texto(
            bloco.get("source"), f"{descricao} (referência)", maximo=200, obrigatorio=True
        )
        try:
            datasources.validar_referencia(referencia)
        except (
            datasources.ReferenciaInvalidaError,
            datasources.FonteDesconhecidaError,
            datasources.CampoDesconhecidoError,
        ) as erro:
            raise ValidationError(str(erro)) from None
        return bloco

    if kind == KIND_ASSET:
        asset_id = bloco.get("asset_id")
        if isinstance(asset_id, bool) or not isinstance(asset_id, int) or asset_id < 0:
            raise ValidationError(
                _("%(desc)s precisa de um asset_id inteiro.") % {"desc": descricao}
            )
        return bloco

    # kind == mixed
    if not permite_misto:
        raise ValidationError(
            _("%(desc)s não aceita conteúdo misto.") % {"desc": descricao}
        )
    if profundidade:
        # Um `mixed` dentro de outro nao acrescenta expressividade e
        # tornaria a medicao do texto recursiva sem motivo.
        raise ValidationError(
            _("%(desc)s não pode ter conteúdo misto aninhado.") % {"desc": descricao}
        )
    partes = bloco.get("parts")
    if not isinstance(partes, list):
        raise ValidationError(
            _('%(desc)s precisa de "parts" (lista).') % {"desc": descricao}
        )
    if len(partes) > MAX_PARTS:
        raise ValidationError(
            _("%(desc)s passa do limite de %(max)s trechos.")
            % {"desc": descricao, "max": MAX_PARTS}
        )
    for posicao, parte in enumerate(partes):
        validar_conteudo(
            parte, f"{descricao} (trecho {posicao})", permite_misto=False, profundidade=1
        )
        _validar_enfase(parte, f"{descricao} (trecho {posicao})")
    return bloco


def referencias_de(bloco):
    """As referencias de campo usadas num bloco de conteudo."""
    if not isinstance(bloco, dict):
        return set()
    if bloco.get("kind") == KIND_FIELD:
        origem = bloco.get("source")
        return {origem} if isinstance(origem, str) else set()
    if bloco.get("kind") == KIND_MIXED:
        usadas = set()
        for parte in bloco.get("parts") or []:
            usadas |= referencias_de(parte)
        return usadas
    return set()


# ---------------------------------------------------------------------------
# Tabela
# ---------------------------------------------------------------------------


def _validar_colunas(valor, descricao):
    if not isinstance(valor, list):
        raise ValidationError(_("%(desc)s deve ser uma lista.") % {"desc": descricao})
    if len(valor) > MAX_TABLE_COLUMNS:
        raise ValidationError(
            _("%(desc)s passa de %(max)s colunas.")
            % {"desc": descricao, "max": MAX_TABLE_COLUMNS}
        )
    for posicao, coluna in enumerate(valor):
        if not isinstance(coluna, dict):
            raise ValidationError(
                _("A coluna %(i)s deve ser um objeto.") % {"i": posicao}
            )
        largura = _numero(coluna.get("width"), f"A largura da coluna {posicao}")
        if largura <= 0:
            raise ValidationError(
                _("A coluna %(i)s tem largura inválida.") % {"i": posicao}
            )
        _escolha(
            coluna.get("align", "left"), elements.ALIGNMENTS,
            f"O alinhamento da coluna {posicao}",
        )
    return valor


def _validar_linhas(valor, descricao, *, colunas):
    if not isinstance(valor, list):
        raise ValidationError(_("%(desc)s deve ser uma lista.") % {"desc": descricao})
    if len(valor) > MAX_TABLE_ROWS:
        raise ValidationError(
            _("%(desc)s passa de %(max)s linhas.")
            % {"desc": descricao, "max": MAX_TABLE_ROWS}
        )
    quantas_colunas = len(colunas) if isinstance(colunas, list) else 0
    for numero, linha in enumerate(valor):
        if not isinstance(linha, dict):
            raise ValidationError(_("A linha %(i)s deve ser um objeto.") % {"i": numero})
        altura = _numero(linha.get("min_height", 0), f"A altura mínima da linha {numero}")
        if altura < 0:
            raise ValidationError(
                _("A linha %(i)s tem altura negativa.") % {"i": numero}
            )
        celulas = linha.get("cells")
        if not isinstance(celulas, list):
            raise ValidationError(
                _('A linha %(i)s precisa de "cells" (lista).') % {"i": numero}
            )
        if quantas_colunas and len(celulas) != quantas_colunas:
            raise ValidationError(
                _("A linha %(i)s tem %(tem)s células, mas a tabela tem %(cols)s colunas.")
                % {"i": numero, "tem": len(celulas), "cols": quantas_colunas}
            )
        for posicao, celula in enumerate(celulas):
            if not isinstance(celula, dict):
                raise ValidationError(
                    _("A célula %(c)s da linha %(i)s deve ser um objeto.")
                    % {"c": posicao, "i": numero}
                )
            # Uma celula tem conteudo estrutural, como qualquer texto do
            # documento -- e isso que permite um campo dentro dela.
            validar_conteudo(
                celula.get("content", {"kind": KIND_TEXT, "value": ""}),
                f"O conteúdo da célula {posicao} da linha {numero}",
                permite_misto=True,
            )
            _escolha(
                celula.get("align", "left"), elements.ALIGNMENTS,
                f"O alinhamento da célula {posicao} da linha {numero}",
            )
            if not isinstance(celula.get("bold", False), bool):
                raise ValidationError(
                    _("O negrito da célula %(c)s da linha %(i)s deve ser "
                      "verdadeiro ou falso.") % {"c": posicao, "i": numero}
                )
    return valor


# ---------------------------------------------------------------------------
# Propriedades
# ---------------------------------------------------------------------------


def _validar_propriedade(declaracao, valor, descricao, *, tipo_do_elemento, propriedades):
    kind = declaracao.kind

    if valor is None and declaracao.permite_nulo:
        return valor

    if kind == "texto":
        return _texto(valor, descricao)
    if kind == "numero":
        return _numero(valor, descricao)
    if kind == "positivo":
        medida = _numero(valor, descricao)
        if medida <= 0:
            raise ValidationError(
                _("%(desc)s precisa ser maior que zero.") % {"desc": descricao}
            )
        return medida
    if kind == "nao_neg":
        medida = _numero(valor, descricao)
        if medida < 0:
            raise ValidationError(
                _("%(desc)s não pode ser negativo.") % {"desc": descricao}
            )
        return medida
    if kind == "booleano":
        if not isinstance(valor, bool):
            raise ValidationError(
                _("%(desc)s deve ser verdadeiro ou falso.") % {"desc": descricao}
            )
        return valor
    if kind == "cor":
        return _cor(valor, descricao)
    if kind == "escolha":
        return _escolha(valor, declaracao.opcoes, descricao)
    if kind == "caixa":
        return _caixa(valor, descricao)
    if kind == "conteudo":
        return validar_conteudo(
            valor, descricao, permite_misto=tipo_do_elemento.aceita_conteudo_misto
        )
    if kind == "colunas":
        return _validar_colunas(valor, descricao)
    if kind == "linhas":
        return _validar_linhas(valor, descricao, colunas=propriedades.get("columns"))

    raise ValidationError(
        _("Propriedade com tipo de validação desconhecido: %(kind)s.") % {"kind": kind}
    )


def _validar_propriedades(elemento, indice, tipo_do_elemento):
    propriedades = elemento.get("properties", {})
    if not isinstance(propriedades, dict):
        raise ValidationError(
            _('"properties" do elemento na posição %(i)s deve ser um objeto.')
            % {"i": indice}
        )

    conhecidas = set(tipo_do_elemento.nomes_das_propriedades)
    desconhecidas = sorted(set(propriedades) - conhecidas)
    if desconhecidas:
        raise ValidationError(
            _('O elemento na posição %(i)s tem propriedades que "%(tipo)s" não '
              "aceita: %(nomes)s.")
            % {"i": indice, "tipo": tipo_do_elemento.code, "nomes": ", ".join(desconhecidas)}
        )

    for declaracao in tipo_do_elemento.propriedades:
        presente = declaracao.nome in propriedades
        if not presente:
            if declaracao.obrigatoria:
                raise ValidationError(
                    _('O elemento na posição %(i)s ("%(tipo)s") precisa da '
                      'propriedade "%(nome)s".')
                    % {"i": indice, "tipo": tipo_do_elemento.code, "nome": declaracao.nome}
                )
            continue
        _validar_propriedade(
            declaracao,
            propriedades[declaracao.nome],
            f'"{declaracao.nome}" do elemento na posição {indice}',
            tipo_do_elemento=tipo_do_elemento,
            propriedades=propriedades,
        )
    return propriedades


# ---------------------------------------------------------------------------
# Elemento e layout
# ---------------------------------------------------------------------------


def validar_elemento(elemento, indice=0):
    """Valida um elemento isolado. Devolve o tipo registrado dele."""
    if not isinstance(elemento, dict):
        raise ValidationError(
            _("O elemento na posição %(i)s deve ser um objeto.") % {"i": indice}
        )

    _texto(
        elemento.get("id"),
        _('"id" do elemento na posição %(i)s') % {"i": indice},
        maximo=MAX_ID_LENGTH,
        obrigatorio=True,
    )

    codigo = elemento.get("type")
    try:
        tipo_do_elemento = elements.tipo(codigo)
    except elements.TipoDesconhecidoError as erro:
        raise ValidationError(str(erro)) from None

    for chave in ("x", "y"):
        _numero(elemento.get(chave), f'"{chave}" do elemento na posição {indice}')
    for chave in ("width", "height"):
        medida = _numero(elemento.get(chave), f'"{chave}" do elemento na posição {indice}')
        if medida < 0:
            raise ValidationError(
                _('"%(chave)s" do elemento na posição %(i)s não pode ser negativo.')
                % {"chave": chave, "i": indice}
            )

    _validar_propriedades(elemento, indice, tipo_do_elemento)
    return tipo_do_elemento


def validate_layout(layout):
    """
    Levanta `ValidationError` se `layout` nao seguir o contrato.

    `{}` e valido: um modelo pode nao ter desenho nenhum ainda -- e o
    estado dos quatro oficiais recem-semeados.
    """
    if not isinstance(layout, dict):
        raise ValidationError(_("O layout deve ser um objeto (JSON)."))

    if not layout:
        return

    versao = layout.get("version")
    if versao != VERSION:
        raise ValidationError(
            _('O layout está na versão de formato "%(tem)s"; esperada "%(esperada)s".')
            % {"tem": versao, "esperada": VERSION}
        )

    elementos = layout.get("elements")
    if not isinstance(elementos, list):
        raise ValidationError(_('"elements" deve ser uma lista.'))
    if len(elementos) > MAX_ELEMENTS:
        raise ValidationError(
            _("O layout passa do limite de %(max)s elementos.") % {"max": MAX_ELEMENTS}
        )

    vistos = set()
    for indice, elemento in enumerate(elementos):
        validar_elemento(elemento, indice)
        identificador = elemento["id"]
        if identificador in vistos:
            raise ValidationError(
                _('Há mais de um elemento com o id "%(id)s".') % {"id": identificador}
            )
        vistos.add(identificador)


def referencias_usadas(layout):
    """Todas as referencias de campo que o layout imprime."""
    usadas = set()
    for elemento in (layout or {}).get("elements", []):
        if not isinstance(elemento, dict):
            continue
        propriedades = elemento.get("properties") or {}
        for chave in ("content", "source"):
            usadas |= referencias_de(propriedades.get(chave))
        for linha in propriedades.get("rows") or []:
            if not isinstance(linha, dict):
                continue
            for celula in linha.get("cells") or []:
                if isinstance(celula, dict):
                    usadas |= referencias_de(celula.get("content"))
    return usadas
