"""
Qual modelo cada idioma usa -- e a troca que mantem UM SO ativo.

A REGRA
-------
Dentro de um TIPO de documento, cada idioma tem no maximo UM
`DocumentTemplate` ativo. E ele, e so ele, que o assistente usa para
emitir a carta naquele idioma. Ativar outro do mesmo idioma nao
acrescenta um segundo: TROCA -- o que estava ativo e desativado no
mesmo instante.

Sem nenhum ativo, o idioma simplesmente nao esta disponivel, e o
assistente avisa. Modelos inativos continuam existindo, editaveis e
duplicaveis: "inativo" e "fora de uso", nao "apagado".

POR QUE (TIPO, IDIOMA) E NAO SO O IDIOMA
----------------------------------------
"Um ativo por idioma" e o que o produto pede, e hoje ha um tipo de
documento so (Carta Convite) -- as duas formulacoes dao exatamente no
mesmo. A diferenca aparece no dia em que existir um segundo tipo: um
contrato em frances e uma carta convite em frances pertencem a fluxos
diferentes, e ativar um nao pode desativar o outro. Amarrar a regra ao
par (tipo, idioma) e o que mantem a frase verdadeira hoje e correta
depois.

O BANCO E A AUTORIDADE
----------------------
A troca roda numa transacao, mas quem GARANTE que nunca existam dois
ativos e o indice parcial `uniq_documenttemplate_ativo_por_idioma`
(ver `DocumentTemplate.Meta.constraints`). Duas requisicoes simultaneas
que passem pela mesma janela nao conseguem gravar o segundo ativo: o
banco recusa. Aqui a transacao existe para a troca ser atomica -- nunca
um instante com zero ativos por causa de um erro no meio.

NAO E VERSIONAMENTO
-------------------
Nada aqui guarda historico nem numera revisoes. E um interruptor: qual
dos modelos daquele idioma esta em uso agora.
"""

from django.db import transaction
from django.utils import timezone

from ..models import DocumentTemplate
from .biblioteca import CODIGO_CARTA_CONVITE

# As tres situacoes que uma pessoa ve na biblioteca. "Rascunho" nao e
# coluna do banco: e ATIVO + ainda nao utilizavel (ver
# `pronto_para_uso`). Chamar de "Ativo" um modelo que o assistente
# recusaria seria a tela mentindo sobre o sistema.
ATIVO = "ativo"
RASCUNHO = "rascunho"
INATIVO = "inativo"
SITUACOES = (ATIVO, RASCUNHO, INATIVO)


def irmaos_do_mesmo_idioma(modelo):
    """
    Os outros modelos que disputam o mesmo lugar: mesmo tipo, mesmo
    idioma. E o conjunto sobre o qual a regra do ativo unico vale.
    """
    return DocumentTemplate.objects.filter(
        type_id=modelo.type_id, language=modelo.language
    ).exclude(pk=modelo.pk)


def modelo_ativo(language, *, tipo=CODIGO_CARTA_CONVITE):
    """
    O modelo ATIVO daquele idioma, ou `None` se nao houver nenhum.

    Nao pergunta se o modelo esta pronto para desenhar -- isso e outra
    pergunta, e quem a faz e quem vai emitir a carta
    (`letters.services.active_document_template`). Aqui a resposta e so
    "qual e o modelo em uso".
    """
    return (
        DocumentTemplate.objects.filter(
            type__code=tipo, language=language, is_active=True
        )
        .select_related("type")
        .first()
    )


def _assets_exigidos(layout):
    """
    Os `asset_id` que o desenho referencia -- `None` quando nao ha
    desenho nenhum.

    `layout_schema.assets_referenciados()` NAO serve aqui: para ele
    `asset_id: 0` significa "sem asset" e nem entra no conjunto. Para
    esta pergunta o zero e justamente o caso que interessa -- o layout
    recem-semeado, que ainda aponta para lugar nenhum.
    """
    layout = layout or {}
    if not layout.get("elements"):
        return None
    exigidos = set()
    for elemento in layout["elements"]:
        if not isinstance(elemento, dict) or elemento.get("type") != "image":
            continue
        origem = (elemento.get("properties") or {}).get("source") or {}
        exigidos.add(int(origem.get("asset_id") or 0))
    return exigidos


def pronto_para_uso(modelo):
    """
    O modelo tem desenho E todas as imagens dele existem?

    Sao DUAS condicoes, e a segunda nao e teorica: o layout oficial
    nasce da migration com `asset_id: 0` (migration nao escreve em
    MEDIA_ROOT, de proposito) e so ganha o binario quando
    `reconstruir_modelos_oficiais` roda, no deploy. Entre uma coisa e
    outra o modelo tem desenho e nao tem logo -- e desenhar assim
    levanta `AssetAusenteError` no meio da finalizacao da carta.
    """
    from apps.content.models import Asset

    exigidos = _assets_exigidos(modelo.layout)
    if exigidos is None or 0 in exigidos:
        return False
    if not exigidos:
        return True
    return Asset.objects.filter(pk__in=exigidos).count() == len(exigidos)


def situacao(modelo):
    """`ativo`, `rascunho` ou `inativo` -- as constantes do topo."""
    if not modelo.is_active:
        return INATIVO
    return ATIVO if pronto_para_uso(modelo) else RASCUNHO


def situacoes(modelos):
    """
    A situacao de VARIOS modelos, `{pk: situacao}`, com UMA consulta de
    assets para a lista inteira.

    A biblioteca precisa disto: perguntar modelo a modelo daria uma
    consulta por linha so para escrever uma palavra na tela.
    """
    from apps.content.models import Asset

    exigidos_por_modelo = {m.pk: _assets_exigidos(m.layout) for m in modelos}
    todos = {
        identificador
        for exigidos in exigidos_por_modelo.values()
        for identificador in (exigidos or ())
        if identificador
    }
    existentes = (
        set(Asset.objects.filter(pk__in=todos).values_list("pk", flat=True))
        if todos
        else set()
    )

    saida = {}
    for modelo in modelos:
        exigidos = exigidos_por_modelo[modelo.pk]
        pronto = (
            exigidos is not None and 0 not in exigidos and exigidos <= existentes
        )
        saida[modelo.pk] = (
            INATIVO if not modelo.is_active else (ATIVO if pronto else RASCUNHO)
        )
    return saida


def ativar(modelo):
    """
    Poe `modelo` em uso e tira do lugar quem estava.

    Devolve a lista dos que foram desativados por causa disto -- quem
    chama costuma querer dizer a quem clicou o que mais mudou, e um
    "ativado" que esconde o "desativado" seria meia verdade.

    Idempotente: ativar o que ja esta ativo nao mexe em nada e devolve
    lista vazia.
    """
    with transaction.atomic():
        anteriores = list(
            irmaos_do_mesmo_idioma(modelo).filter(is_active=True).select_for_update()
        )
        if anteriores:
            DocumentTemplate.objects.filter(
                pk__in=[m.pk for m in anteriores]
            ).update(is_active=False, updated_at=timezone.now())
        if not modelo.is_active:
            modelo.is_active = True
            # `save()` e nao `update()`: as guardas do modelo (travado,
            # oficial) sao a autoridade sobre o que pode mudar, e
            # `is_active` passa por elas de proposito.
            modelo.save(update_fields=["is_active", "updated_at"])
    return anteriores


def desativar(modelo):
    """
    Tira `modelo` de uso. O idioma fica sem modelo ativo -- e o
    assistente passa a avisar que o documento nao esta disponivel --
    ate que alguem ative outro.
    """
    if not modelo.is_active:
        return modelo
    modelo.is_active = False
    modelo.save(update_fields=["is_active", "updated_at"])
    return modelo


def definir_situacao(modelo, ativo):
    """
    O interruptor da tela: liga ou desliga, com a troca embutida.
    Devolve `(mudou, desativados)`.
    """
    if modelo.is_active == ativo:
        return False, []
    if ativo:
        return True, ativar(modelo)
    desativar(modelo)
    return True, []
