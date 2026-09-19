"""
A paginação das tabelas do Backoffice: página, quantidade por página e
o "Mostrando 21–40 de 87".

SERVER-SIDE
-----------
É o `Paginator` do Django sobre o que a view já filtrou -- nada de
carregar tudo e paginar no navegador. Este módulo só decide a
quantidade (lista fechada), monta os endereços e entrega ao parcial
`backoffice/_paginacao.html` tudo pronto.

O QUE FICA NO ENDEREÇO
----------------------
`page` e `page_size`, ao lado da busca e dos filtros:

  * trocar de PÁGINA preserva busca, filtros e quantidade;
  * trocar a QUANTIDADE volta para a primeira página (a página 7 de 10
    em 10 não existe de 50 em 50) e preserva o resto;
  * trocar BUSCA ou FILTRO também volta para a primeira página -- é
    `filtros.url_de_filtro`, que já tira o `page`, e os formulários da
    barra, que não o levam.
"""

from django.core.paginator import Paginator
from django.urls import reverse

from . import filtros

TAMANHOS = (10, 20, 30, 50)
TAMANHO_PADRAO = 20
PARAMETRO_DO_TAMANHO = "page_size"


def tamanho_pedido(request, padrao=TAMANHO_PADRAO):
    """A quantidade por página pedida -- só uma das da lista; senão, a padrão."""
    bruto = request.GET.get(PARAMETRO_DO_TAMANHO) or ""
    if bruto.isdigit() and int(bruto) in TAMANHOS:
        return int(bruto)
    return padrao


def url_da_pagina(request, rota, numero):
    """A URL de `rota` na página `numero`, com todo o resto preservado."""
    parametros = request.GET.copy()
    parametros.pop("page", None)
    if numero > 1:
        parametros["page"] = str(numero)
    consulta = parametros.urlencode()
    caminho = reverse(rota)
    return f"{caminho}?{consulta}" if consulta else caminho


def url_sem_filtros(request, rota):
    """
    "Limpar filtros": `rota` sem busca, sem filtro e na primeira página --
    mas com a quantidade por página que a pessoa escolheu, se escolheu.
    """
    caminho = reverse(rota)
    bruto = request.GET.get(PARAMETRO_DO_TAMANHO) or ""
    if bruto.isdigit() and int(bruto) in TAMANHOS:
        return f"{caminho}?{PARAMETRO_DO_TAMANHO}={bruto}"
    return caminho


def paginar(request, objetos, rota, padrao=TAMANHO_PADRAO):
    """
    Pagina `objetos` (queryset ou lista) e devolve o que o parcial usa:

      pagina, total, inicio, fim   -- o `Page` e o "Mostrando inicio–fim de total";
      tamanho, tamanhos            -- a quantidade em vigor e as opções (com URL);
      paginas                      -- os números (com URL), com reticências no meio;
      url_anterior, url_proxima    -- vazias quando não há para onde ir.
    """
    tamanho = tamanho_pedido(request, padrao)
    pagina = Paginator(objetos, tamanho).get_page(request.GET.get("page"))
    paginador = pagina.paginator

    paginas = []
    if paginador.num_pages > 1:
        for numero in paginador.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1):
            if isinstance(numero, int):
                paginas.append(
                    {
                        "numero": numero,
                        "url": url_da_pagina(request, rota, numero),
                        "atual": numero == pagina.number,
                    }
                )
            else:
                paginas.append({"reticencias": True})

    return {
        "pagina": pagina,
        "total": paginador.count,
        "inicio": pagina.start_index(),
        "fim": pagina.end_index(),
        "tamanho": tamanho,
        "tamanhos": [
            {
                "valor": valor,
                "url": filtros.url_de_filtro(request, rota, **{PARAMETRO_DO_TAMANHO: str(valor)}),
                "atual": valor == tamanho,
            }
            for valor in TAMANHOS
        ],
        "paginas": paginas,
        "url_anterior": (
            url_da_pagina(request, rota, pagina.previous_page_number())
            if pagina.has_previous()
            else ""
        ),
        "url_proxima": (
            url_da_pagina(request, rota, pagina.next_page_number()) if pagina.has_next() else ""
        ),
    }
