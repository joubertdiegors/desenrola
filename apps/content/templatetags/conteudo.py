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

import re

from django import template

register = template.Library()

# Até onde o desenho "Editorial" numera. Três é o que a referência
# visual pede, e é o que o schema declara em campos.
QUANTOS_PASSOS = 3

# Quantos parceiros a Home mostra: UMA fileira de quatro, que é o que a
# referência visual desenha. Acima disso o "Ver todos" leva à página de
# parceiros -- nunca uma segunda fileira, nunca um carrossel com barra
# de rolagem.
QUANTOS_PARCEIROS_NA_HOME = 4


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


# Uma numeracao escrita no comeco do texto: "1. ", "01 - ", "2) ".
# Ancorada no inicio e com o separador obrigatorio, para nao comer um
# titulo que COMECE com numero de verdade ("2026 em diante").
NUMERACAO_NO_COMECO = re.compile(r"^\s*\d{1,2}\s*[.)\-–]\s+")


@register.filter
def sem_numeracao(texto):
    """
    O texto sem a numeracao escrita a mao no comeco.

    O passo ja e numerado pelo DESENHO (ver `core/secoes/how.html`), a
    partir da posicao na lista. Um titulo cadastrado como "1. Preencha"
    apareceria como "01  1. Preencha" -- entao a numeracao do texto sai
    na hora de desenhar, e o que esta no banco continua como esta.
    """
    return NUMERACAO_NO_COMECO.sub("", str(texto or ""))


@register.filter
def parceiros_visiveis(parceiros):
    """
    Os parceiros que a Home desenha: no máximo QUATRO.

    Uma fileira, sempre. Acima de quatro, os demais não somem do site --
    eles estão na página pública de parceiros, para onde o "Ver todos"
    leva (ver `core/secoes/partners.html`).

    O corte mora AQUI, e não no template, porque é uma regra: "a Home
    mostra uma fileira" tem um número, e um número escrito no meio da
    marcação é um número que ninguém encontra quando ele muda.
    """
    return list(parceiros)[:QUANTOS_PARCEIROS_NA_HOME]
