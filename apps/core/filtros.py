"""
Os filtros das tabelas do Backoffice -- a barra do desenho de Modelos.

Nasceram em `doctemplates.library_views`, com a tabela de Modelos, e
moram aqui desde que Usuários, Cartas e Parceiros passaram a usar o mesmo
desenho: a barra é a mesma, e a regra de montar os endereços também. Uma
cópia por tela seria uma segunda regra esperando para divergir.

OS FILTROS SÃO LINKS
--------------------
Cada opção é o endereço da MESMA tela com um filtro trocado e o resto
preservado -- clicar em "Inativos" mantém a busca que já estava lá.
Funciona sem JavaScript, e trocar de filtro sempre volta para a primeira
página (a página 3 do filtro anterior quase nunca existe no novo).
"""

from django.urls import reverse


def url_de_filtro(request, rota, **mudancas):
    """A URL de `rota` com alguns filtros trocados e o RESTO preservado."""
    parametros = request.GET.copy()
    for chave, valor in mudancas.items():
        parametros.pop(chave, None)
        if valor:
            parametros[chave] = valor
    parametros.pop("page", None)
    consulta = parametros.urlencode()
    caminho = reverse(rota)
    return f"{caminho}?{consulta}" if consulta else caminho


def opcoes(request, rota, parametro, atual, valores):
    """
    As opções de um filtro: rótulo, endereço e qual está valendo.

    `atual` é o valor em vigor; a opção que bate com ele ganha
    `atual=True`, e é ela que a barra mostra acesa.
    """
    return [
        {
            "valor": valor,
            "rotulo": rotulo,
            "url": url_de_filtro(request, rota, **{parametro: valor}),
            "atual": (atual or "") == valor,
        }
        for valor, rotulo in valores
    ]


def pilula(request, rota, rotulo, parametro, atual, valores):
    """Uma pílula com menu: o rótulo, o valor em vigor e as opções."""
    lista = opcoes(request, rota, parametro, atual, valores)
    escolhida = next((opcao for opcao in lista if opcao["atual"]), lista[0])
    return {
        "rotulo": rotulo,
        "escolhido": bool(atual),
        "atual": escolhida["rotulo"],
        "opcoes": lista,
    }
