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
