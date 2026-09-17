"""
Registro central das FONTES DE DADOS que um documento pode imprimir
(Etapa 3.1 da nova arquitetura).

Uma referencia de campo tem a forma `namespace.campo` -- por exemplo
`convidado.nome`, `anfitriao.cidade`, `calculado.data_documento`. E ela
que um elemento do layout guarda; o valor so existe quando um documento
e emitido.

POR QUE UM REGISTRO, E NAO CHAVES SOLTAS
----------------------------------------
Na arquitetura antiga as chaves viviam espalhadas: uma lista no mapa do
renderer, outra derivada do `field_schema`, e a validacao tinha de unir
as duas na mao. O resultado era que ninguem sabia, olhando um lugar so,
o que um documento podia imprimir.

Aqui ha um lugar so. O editor le daqui para montar o painel de dados; o
validador do layout le daqui para recusar uma referencia inexistente; e
o renderer (etapa futura) vai ler daqui para saber o que resolver.

EXTENSIBILIDADE
---------------
Acrescentar `empresa.*` ou `cliente.*` no futuro e registrar uma fonte
nova -- nada mais muda. `registrar_fonte()` existe para isso, e para
testes poderem exercitar namespaces novos sem tocar no registro real.

Este modulo NAO resolve valores. Ele so declara o que existe; quem sabe
ler `User.city` ou calcular a duracao de uma estadia e outra etapa.
"""

from dataclasses import dataclass, field

# Separador entre o namespace e o campo numa referencia.
SEPARADOR = "."


class FonteDesconhecidaError(KeyError):
    """O namespace da referencia nao esta registrado."""


class CampoDesconhecidoError(KeyError):
    """O namespace existe, mas nao tem esse campo."""


class ReferenciaInvalidaError(ValueError):
    """A referencia nao tem a forma `namespace.campo`."""


@dataclass(frozen=True)
class Campo:
    """Um dado que um documento pode imprimir."""

    key: str
    label: str
    # Como o valor se comporta, nao como ele e desenhado: orienta o
    # formato do elemento `number`/`text` e, mais tarde, o resolver.
    kind: str = "texto"

    KINDS = ("texto", "data", "numero")


# Cor com que uma fonte SEM cor propria aparece no editor.
COR_PADRAO = "#7c8aa6"


@dataclass(frozen=True)
class FonteDeDados:
    """
    Um namespace de campos (`convidado`, `anfitriao`, ...).

    `color` e a cor que identifica o grupo no editor de modelos (o ponto
    ao lado do nome do grupo, o ponto de cada chip de "Campos no
    documento"). Mora aqui, e nao no JavaScript, para uma fonte nova
    registrada por `registrar_fonte()` nascer com a sua cor -- ou com a
    padrao, se nao declarar nenhuma.
    """

    code: str
    label: str
    campos: tuple = field(default_factory=tuple)
    color: str = COR_PADRAO

    @property
    def chaves(self):
        return tuple(campo.key for campo in self.campos)

    def campo(self, key):
        for campo in self.campos:
            if campo.key == key:
                return campo
        raise CampoDesconhecidoError(
            f'A fonte "{self.code}" não tem o campo "{key}". '
            f"Campos disponíveis: {', '.join(self.chaves) or '(nenhum)'}."
        )


# ---------------------------------------------------------------------------
# As fontes conhecidas hoje
# ---------------------------------------------------------------------------
#
# Os rotulos sao os que o editor vai mostrar no painel de dados. As
# chaves sao estaveis: mudar uma delas invalidaria os layouts que a
# referenciam, entao trate-as como contrato.

FONTES_PADRAO = (
    FonteDeDados(
        code="documento",
        label="Documento",
        color="#1d4ed8",
        campos=(
            Campo("numero", "Número do documento"),
            Campo("data", "Data do documento", kind="data"),
        ),
    ),
    FonteDeDados(
        code="convidado",
        label="Convidado",
        color="#0f9d70",
        campos=(
            Campo("nome", "Nome completo"),
            Campo("nacionalidade", "Nacionalidade"),
            Campo("data_nascimento", "Data de nascimento", kind="data"),
            Campo("passaporte", "Número do passaporte"),
        ),
    ),
    FonteDeDados(
        code="anfitriao",
        label="Anfitrião",
        color="#8a5cf6",
        campos=(
            Campo("nome", "Nome completo"),
            Campo("nacionalidade", "Nacionalidade"),
            Campo("data_nascimento", "Data de nascimento", kind="data"),
            Campo("documento_identidade", "Documento de identidade"),
            Campo("endereco", "Endereço"),
            Campo("cidade", "Cidade"),
            Campo("telefone", "Telefone"),
            Campo("email", "E-mail"),
        ),
    ),
    # A visita em si. Nao cabia em nenhum dos outros namespaces: as datas
    # nao sao do documento (que tem a sua propria), nao sao um atributo do
    # convidado nem do anfitriao -- sao da estadia.
    FonteDeDados(
        code="estadia",
        label="Estadia",
        color="#e08a1e",
        campos=(
            Campo("chegada", "Data de chegada", kind="data"),
            Campo("partida", "Data de partida", kind="data"),
        ),
    ),
    FonteDeDados(
        code="calculado",
        label="Calculado",
        color="#7c8aa6",
        campos=(
            Campo("data_documento", "Data de emissão", kind="data"),
            # Sempre recalculada a partir de chegada/partida, nunca lida
            # de um campo guardado -- por isso mora em "calculado" e nao
            # em "estadia".
            Campo("duracao_dias", "Duração em dias", kind="numero"),
        ),
    ),
)

_FONTES = {fonte.code: fonte for fonte in FONTES_PADRAO}


def registrar_fonte(fonte, *, substituir=False):
    """
    Acrescenta uma fonte ao registro (`empresa`, `cliente`, ...).

    Recusa sobrescrever uma ja registrada sem `substituir=True`: duas
    fontes com o mesmo codigo seria um erro silencioso, e o layout que
    referencia uma delas deixaria de significar o que significava.
    """
    if not substituir and fonte.code in _FONTES:
        raise ValueError(f'A fonte "{fonte.code}" já está registrada.')
    _FONTES[fonte.code] = fonte
    return fonte


def remover_fonte(code):
    """Tira uma fonte do registro. Existe para testes voltarem ao estado limpo."""
    _FONTES.pop(code, None)


def fontes():
    """Todas as fontes registradas, na ordem em que foram registradas."""
    return tuple(_FONTES.values())


def fonte(code):
    try:
        return _FONTES[code]
    except KeyError:
        raise FonteDesconhecidaError(
            f'Não existe a fonte de dados "{code}". '
            f"Disponíveis: {', '.join(sorted(_FONTES))}."
        ) from None


def dividir(referencia):
    """
    `"convidado.nome"` -> `("convidado", "nome")`.

    Recusa o que nao tiver exatamente um separador: `"nome"` sozinho nao
    diz de onde o dado vem, e `"a.b.c"` nao e uma forma que exista.
    """
    if not isinstance(referencia, str):
        raise ReferenciaInvalidaError("A referência de campo precisa ser um texto.")
    partes = referencia.split(SEPARADOR)
    if len(partes) != 2 or not all(parte.strip() for parte in partes):
        raise ReferenciaInvalidaError(
            f'"{referencia}" não é uma referência válida. '
            'Use o formato "fonte.campo", por exemplo "convidado.nome".'
        )
    return partes[0], partes[1]


def validar_referencia(referencia):
    """
    Devolve `(fonte, campo)` se a referencia existir; levanta o erro
    especifico se nao existir. Quem quiser so um booleano usa
    `referencia_valida()`.
    """
    codigo, chave = dividir(referencia)
    origem = fonte(codigo)
    return origem, origem.campo(chave)


def referencia_valida(referencia):
    try:
        validar_referencia(referencia)
    except (ReferenciaInvalidaError, FonteDesconhecidaError, CampoDesconhecidoError):
        return False
    return True


def todas_as_referencias():
    """Todas as referencias validas hoje, como `{"convidado.nome", ...}`."""
    return {
        f"{origem.code}{SEPARADOR}{campo.key}"
        for origem in _FONTES.values()
        for campo in origem.campos
    }


def para_o_editor():
    """
    O registro na forma que o painel de dados do editor consome:
    uma lista de grupos, cada um com os seus campos.
    """
    return [
        {
            "code": origem.code,
            "label": origem.label,
            "color": origem.color,
            "fields": [
                {
                    "reference": f"{origem.code}{SEPARADOR}{campo.key}",
                    "key": campo.key,
                    "label": campo.label,
                    "kind": campo.kind,
                }
                for campo in origem.campos
            ],
        }
        for origem in _FONTES.values()
    ]
