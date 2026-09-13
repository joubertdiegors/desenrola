"""
Operacoes sobre o `layout` de um `DocumentTemplate` (Etapa 3.1).

Tudo aqui e funcao PURA sobre dicionarios: recebe um layout, devolve um
layout NOVO, e nunca toca no que recebeu -- nem na superficie, nem nas
estruturas aninhadas. Nao ha banco, nao ha `save()`, nao ha request.

POR QUE IMUTAVEL
----------------
E o que permite ao editor guardar estados inteiros para desfazer/refazer
sem clonar a cada tecla, e o que evita a classe de bug mais cara deste
subsistema: alterar um elemento e descobrir, muito depois, que o objeto
alterado era compartilhado com outro lugar. Por isso `deepcopy` na
entrada de cada operacao, e por isso ha teste conferindo estrutura
ANINHADA, nao so a de cima.

VALIDACAO
---------
Toda operacao valida o RESULTADO antes de devolve-lo (`validate_layout`).
Uma operacao que produzisse um layout invalido falha na hora, com a
mensagem do contrato -- em vez de gravar algo que o editor nao consegue
abrir depois.

CAMADAS
-------
A ordem da lista `elements` E a ordem de desenho: indice 0 ao fundo,
ultimo por cima. Nao ha `z_index` para manter em sincronia com a lista;
reordenar e mover um item de posicao, e pronto.
"""

import copy
import uuid

from .. import elements as registro_de_tipos
from ..layout_schema import VERSION, layout_vazio, validate_layout


class ElementoNaoEncontradoError(KeyError):
    """
    Nao ha elemento com esse id no layout.

    `KeyError` de proposito: quem chama esta procurando por chave. A
    mensagem diz qual id faltou e quais existem, para o erro ser
    resolvido sem precisar inspecionar o JSON na mao.
    """


def _novo_id_aleatorio():
    return uuid.uuid4().hex[:12]


def _indice_de(layout, element_id):
    for indice, elemento in enumerate(layout.get("elements", [])):
        if elemento.get("id") == element_id:
            return indice
    existentes = [e.get("id") for e in layout.get("elements", [])]
    raise ElementoNaoEncontradoError(
        f'Não há elemento com id "{element_id}" neste layout. '
        f"Ids presentes: {', '.join(map(str, existentes)) or '(nenhum)'}."
    )


def _normalizado(layout):
    """
    Uma copia profunda do layout, ja com a forma minima garantida.

    `{}` (modelo sem desenho) vira um layout vazio de verdade, para as
    operacoes nao precisarem tratar esse caso uma a uma.
    """
    if not layout:
        return layout_vazio()
    copia = copy.deepcopy(layout)
    copia.setdefault("version", VERSION)
    copia.setdefault("elements", [])
    return copia


def _devolver(layout):
    validate_layout(layout)
    return layout


def _ids(layout):
    return {e.get("id") for e in layout.get("elements", [])}


def _id_livre(layout, gerar=None):
    """Um id que ainda nao existe no layout."""
    gerar = gerar or _novo_id_aleatorio
    usados = _ids(layout)
    novo = gerar()
    while novo in usados:
        novo = gerar()
    return novo


# ---------------------------------------------------------------------------
# Criacao
# ---------------------------------------------------------------------------


def criar_layout():
    """Um layout vazio e valido."""
    return layout_vazio()


def criar_elemento(tipo, *, x=0.0, y=0.0, width=100.0, height=20.0, id=None, **propriedades):
    """
    Monta um elemento novo do `tipo`, ja com os padroes declarados no
    registro (`elements.py`) e com o que vier em `propriedades` por cima.

    Nao o adiciona a layout nenhum -- e so a estrutura. Quem coloca no
    documento e `adicionar_elemento`, que tambem garante o id unico.
    """
    declarado = registro_de_tipos.tipo(tipo)
    valores = declarado.padroes()
    valores.update(copy.deepcopy(propriedades))
    return {
        "id": id or _novo_id_aleatorio(),
        "type": declarado.code,
        "x": float(x),
        "y": float(y),
        "width": float(width),
        "height": float(height),
        "properties": valores,
    }


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def obter_elemento(layout, element_id):
    """
    O elemento, em copia -- alterar o que sai daqui nunca alcanca o
    layout de origem.
    """
    atual = layout or {}
    for elemento in atual.get("elements", []):
        if elemento.get("id") == element_id:
            return copy.deepcopy(elemento)
    # Nao achou: `_indice_de` levanta com a mensagem que lista os ids
    # existentes, que e mais util do que um KeyError seco aqui.
    _indice_de(atual if atual.get("elements") else layout_vazio(), element_id)


def existe_elemento(layout, element_id):
    return element_id in _ids(layout or {})


def elementos_em_ordem_de_desenho(layout):
    """Os elementos do fundo para a frente -- que e a ordem da lista."""
    return copy.deepcopy((layout or {}).get("elements", []))


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------


def adicionar_elemento(layout, elemento, *, gerar_id=None):
    """
    Acrescenta `elemento` por cima de todos (fim da lista = frente).

    Se o id vier vazio ou ja existir no layout, um novo e gerado: dois
    elementos com o mesmo id tornariam ambiguo qual deles uma operacao
    seguinte alcancaria.
    """
    novo = _normalizado(layout)
    copia = copy.deepcopy(elemento)
    if not copia.get("id") or copia["id"] in _ids(novo):
        copia["id"] = _id_livre(novo, gerar_id)
    novo["elements"].append(copia)
    return _devolver(novo)


def atualizar_elemento(layout, element_id, changes):
    """
    Aplica `changes` ao elemento. `properties` e MESCLADO (chave a
    chave); os demais campos sao substituidos.

    Mesclar e o comportamento util no editor: mudar a cor de um texto nao
    pode apagar o tamanho da fonte. Trocar o `id` por aqui e recusado --
    seria renomear a identidade do elemento no meio de uma edicao.
    """
    novo = _normalizado(layout)
    indice = _indice_de(novo, element_id)
    alvo = novo["elements"][indice]

    mudancas = copy.deepcopy(changes or {})
    if "id" in mudancas and mudancas["id"] != element_id:
        raise ValueError(
            "O id de um elemento não pode ser alterado; "
            "duplique o elemento ou remova e acrescente outro."
        )
    mudancas.pop("id", None)

    propriedades = mudancas.pop("properties", None)
    alvo.update(mudancas)
    if propriedades is not None:
        alvo.setdefault("properties", {}).update(propriedades)
    return _devolver(novo)


def remover_elemento(layout, element_id):
    novo = _normalizado(layout)
    indice = _indice_de(novo, element_id)
    novo["elements"].pop(indice)
    return _devolver(novo)


def mover_elemento(layout, element_id, x, y):
    """Reposiciona pelo canto superior esquerdo."""
    return atualizar_elemento(layout, element_id, {"x": float(x), "y": float(y)})


def redimensionar_elemento(layout, element_id, width, height):
    return atualizar_elemento(
        layout, element_id, {"width": float(width), "height": float(height)}
    )


def duplicar_elemento(layout, element_id, *, deslocamento=10.0, gerar_id=None):
    """
    Copia o elemento com id NOVO, deslocado alguns pontos e colocado por
    cima -- para a copia nao ficar escondida exatamente sobre o original.

    Devolve `(layout, novo_id)`: quem chama costuma querer selecionar a
    copia logo em seguida.
    """
    novo = _normalizado(layout)
    indice = _indice_de(novo, element_id)
    copia = copy.deepcopy(novo["elements"][indice])
    copia["id"] = _id_livre(novo, gerar_id)
    copia["x"] = float(copia.get("x", 0.0)) + deslocamento
    copia["y"] = float(copia.get("y", 0.0)) + deslocamento
    novo["elements"].append(copia)
    return _devolver(novo), copia["id"]


# ---------------------------------------------------------------------------
# Camadas
# ---------------------------------------------------------------------------


def _reordenar(layout, element_id, destino):
    novo = _normalizado(layout)
    indice = _indice_de(novo, element_id)
    elemento = novo["elements"].pop(indice)
    total = len(novo["elements"])
    posicao = max(0, min(total, destino(indice, total)))
    novo["elements"].insert(posicao, elemento)
    return _devolver(novo)


def trazer_para_frente(layout, element_id):
    """Para o topo da pilha: desenhado por ultimo, portanto por cima."""
    return _reordenar(layout, element_id, lambda indice, total: total)


def enviar_para_tras(layout, element_id):
    """Para o fundo da pilha."""
    return _reordenar(layout, element_id, lambda indice, total: 0)


def mover_para_frente(layout, element_id):
    """Uma camada acima. No topo, nao muda nada."""
    return _reordenar(layout, element_id, lambda indice, total: indice + 1)


def mover_para_tras(layout, element_id):
    """Uma camada abaixo. No fundo, nao muda nada."""
    return _reordenar(layout, element_id, lambda indice, total: indice - 1)
