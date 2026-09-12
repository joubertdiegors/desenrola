"""
Engine de geracao de PDF do Desenrola.

Esta e uma biblioteca Python pura: nao importa Django, nao acessa banco e nao
conhece models. Recebe o PDF oficial, um mapa de campos e os valores; devolve
bytes. Isso mantem testavel em isolamento a parte mais critica do sistema.

Principio: o PDF oficial NUNCA e recriado em HTML/CSS. Ele e aberto e recebe
uma camada com os dados variaveis, preservando o conteudo original intacto.

Ainda nao implementada: sera construida em fase posterior, apos a analise do
PDF oficial da Carta Convite.
"""

__all__: list[str] = []
