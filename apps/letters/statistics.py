"""
Os números sobre cartas que o site mostra em público.

Hoje há um só: quantas Cartas Convite já foram emitidas -- o selo da
Home, que até esta etapa era a string "12.458" escrita em
`apps/core/demo.py`.

POR QUE `finalized_at`, E NÃO `status` NEM `generated_at`
--------------------------------------------------------
`finalized_at` é gravado UMA vez, no fechamento, e nunca reescrito. Os
outros dois não servem:

  `status`        muda depois (uma carta cancelada continua tendo sido
                  emitida -- e um contador de site não anda para trás);
  `generated_at`  é reescrito a cada reemissão, então não marca o
                  momento em que a carta passou a existir.

Contar rascunho seria pior ainda: ninguém "gerou" nada.

O QUE O NÚMERO SIGNIFICA
------------------------
CARTAS, não pessoas. A mesma pessoa emite várias, e o rótulo na Home
tem de dizer o que este número conta. Contar pessoas seria
`.values("user").distinct().count()` -- outra pergunta, outro rótulo.
"""

from django.core.cache import cache

from apps.letters.models import Letter

# A Home é pública e este `COUNT` roda a cada visita. Dez minutos: o
# número muda devagar, e ninguém percebe a diferença entre "agora" e
# "há dez minutos" num contador de apresentação.
CHAVE_DO_CACHE = "letters.cartas_emitidas"
VALIDADE_EM_SEGUNDOS = 600


def _contar():
    return Letter.objects.filter(finalized_at__isnull=False).count()


def cartas_emitidas():
    """
    Quantas Cartas Convite já foram emitidas. Zero é uma resposta
    legítima -- um site novo não tem nenhuma, e o selo mostra 0.
    """
    return cache.get_or_set(CHAVE_DO_CACHE, _contar, VALIDADE_EM_SEGUNDOS)


def esquecer_a_contagem():
    """
    Descarta o valor guardado; a próxima leitura volta ao banco.

    Existe para os testes e para o dia em que alguém quiser o número
    exato logo após uma emissão. Não há sinal ligado a isto de
    propósito: o contador não precisa ser instantâneo, e um `post_save`
    em `Letter` por causa de um selo de apresentação seria caro demais
    para o que entrega.
    """
    cache.delete(CHAVE_DO_CACHE)
