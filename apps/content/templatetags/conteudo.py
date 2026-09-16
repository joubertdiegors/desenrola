"""
Os filtros que só os desenhos da Home usam.

POR QUE UM FILTRO, E NÃO CONTA NO `services`
--------------------------------------------
"Quais passos têm texto" é uma pergunta de DESENHO: só o banner
"Editorial" a faz, e só para decidir o que numerar. `services.py`
entrega o conteúdo gravado como ele está, igual para todos os desenhos
-- se ele passasse a montar listas para um deles, passaria a saber qual
template está no ar, e é justamente isso que o schema existe para
evitar.

POR QUE NÃO RESOLVER NO PRÓPRIO TEMPLATE
----------------------------------------
Dava para escrever três `{% if %}`, mas a numeração sairia da POSIÇÃO do
campo, não da ordem do que foi preenchido: quem escrevesse só o primeiro
e o terceiro passo veria "01" e "03" na tela. O filtro devolve apenas os
passos com texto, e o `forloop` numera o que sobrou.
"""

from django import template

register = template.Library()

# Até onde o desenho "Editorial" numera. Três é o que a referência
# visual pede, e é o que o schema declara em campos.
QUANTOS_PASSOS = 3

# Quantos parceiros a composição principal mostra sem carrossel -- o
# desenho de referência (2a) cabe quatro por fileira sem espichar nem
# espremer. Acima disso, ou rola (carrossel) ou "Ver todos" leva ao
# resto -- nunca uma segunda fileira.
QUANTOS_PARCEIROS_SEM_CARROSSEL = 4


@register.filter
def passos_do_banner(conteudo):
    """
    Os passos escritos do banner "Editorial", na ordem, sem os vazios.

    Recebe o dicionário de textos da seção. Devolve lista de
    dicionários com `title` e `text` -- um passo com só um dos dois
    ainda conta: um título sem texto é um passo curto, não um passo
    esquecido.
    """
    if not hasattr(conteudo, "get"):
        return []

    escritos = []
    for numero in range(1, QUANTOS_PASSOS + 1):
        titulo = (conteudo.get(f"passo{numero}_title") or "").strip()
        texto = (conteudo.get(f"passo{numero}_text") or "").strip()
        if titulo or texto:
            escritos.append({"title": titulo, "text": texto})
    return escritos


@register.filter
def parceiros_visiveis(parceiros, parte):
    """
    Os parceiros que a composição SEM carrossel desenha.

    Até quatro, é a lista inteira -- a grade cabe sem espichar nem
    criar fileira vazia. Com mais de quatro e o carrossel LIGADO, quem
    desenha o resto é `partners.html`, direto de `parceiros`: este
    filtro não entra nesse caminho. Com o carrossel DESLIGADO, só os
    quatro primeiros saem daqui -- é o botão "Ver todos" que leva ao
    resto, e a seção nunca ganha uma segunda fileira.

    `parte` é o `ParteDaPagina` de "partners" -- `parceiros_carrossel_ativo`
    é estrutural (`PageSection.partners_carousel_enabled`), não um texto.
    """
    parceiros = list(parceiros)
    if len(parceiros) <= QUANTOS_PARCEIROS_SEM_CARROSSEL:
        return parceiros
    if parte is not None and getattr(parte, "parceiros_carrossel_ativo", True):
        return parceiros
    return parceiros[:QUANTOS_PARCEIROS_SEM_CARROSSEL]
