"""
O que a interface precisa saber sobre a geração de carta.

POR QUE UMA ETIQUETA, E NÃO CONTEXTO DE VIEW
--------------------------------------------
O botão "Gerar Carta Convite" aparece em quatro telas (painel,
histórico -- em dois lugares --, e a conclusão de uma carta). Passar os
requisitos pelo contexto obrigaria cada uma dessas views a lembrar de
calculá-los, e a próxima tela com o botão nasceria destrancada por
esquecimento. A etiqueta pergunta a quem sabe
(`apps.letters.requisitos`), e o template só decide como mostrar.

POR QUE NÃO UM PROCESSADOR DE CONTEXTO
--------------------------------------
Ele rodaria em TODA requisição do site -- inclusive nas páginas
públicas, que não têm botão nenhum -- para responder uma pergunta que
quatro telas fazem. A etiqueta cobra a consulta de quem precisa dela.

UMA CONSULTA POR REQUISIÇÃO
---------------------------
O resultado fica guardado no próprio `request`: o histórico usa a
etiqueta duas vezes (lista cheia e lista vazia), e não há motivo para
ler a política duas vezes na mesma página.
"""

from django import template

from apps.letters import requisitos

register = template.Library()

CHAVE = "_requisitos_de_geracao"


@register.simple_tag(takes_context=True)
def requisitos_de_geracao(context):
    """
    Os requisitos da conta desta requisição -- use com `as`:

        {% requisitos_de_geracao as geracao %}
        {% if geracao.pode_gerar %}...{% endif %}
    """
    request = context.get("request")
    if request is None:
        # Renderização sem request (e-mail, comando): nada a bloquear.
        return requisitos.LIBERADO
    guardado = getattr(request, CHAVE, None)
    if guardado is None:
        guardado = requisitos.requisitos_para_gerar(getattr(request, "user", None))
        setattr(request, CHAVE, guardado)
    return guardado


@register.inclusion_tag("components/botao_gerar_carta.html", takes_context=True)
def botao_gerar_carta(context, rotulo, classe="btn btn-primary", seta=True, aviso_id=""):
    """
    O botão que leva ao assistente -- ou o mesmo botão desabilitado,
    quando falta confirmação. Uma linha por tela:

        {% botao_gerar_carta rotulo %}

    O rótulo e as classes mudam de tela para tela (o painel diz
    "Começar"; o histórico, "Gerar Carta Convite"); o que NÃO muda é
    quem decide se ele está liberado.
    """
    return {
        "geracao": requisitos_de_geracao(context),
        "rotulo": rotulo,
        "classe": classe,
        "seta": seta,
        "aviso_id": aviso_id or "aviso-para-gerar",
    }


@register.inclusion_tag("components/aviso_para_gerar.html", takes_context=True)
def aviso_para_gerar(context, aviso_id=""):
    """
    O aviso vermelho com o que falta confirmar, e o caminho para
    resolver. Some sozinho quando não falta nada.

    É etiqueta, e não `{% include %}`, para não depender de a tela ter
    lembrado de calcular os requisitos antes: um `include` com variável
    ausente não dá erro -- apenas não desenha nada, e o aviso sumiria em
    silêncio justamente onde ele é a explicação do bloqueio.
    """
    return {
        "geracao": requisitos_de_geracao(context),
        "aviso_id": aviso_id or "aviso-para-gerar",
        "request": context.get("request"),
    }
