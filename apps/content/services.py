"""
Leitura do conteúdo editável das páginas.

O QUE ESTE MÓDULO FAZ, E O QUE NÃO FAZ
--------------------------------------
Faz uma coisa: entregar a uma view as seções ATIVAS de uma página, já
com o conteúdo no idioma certo, numa consulta. Não é um editor, não
valida formato e não sabe o que cada tipo de seção significa -- quem
sabe disso é o template que a desenha.

O FORMATO DE `content` É DO TIPO DA SEÇÃO
-----------------------------------------
`PageSectionTranslation.content` é um JSON livre de propósito: uma seção
`hero` guarda título e chamada; uma `features` guarda uma lista de
cartões. Impor um esquema aqui obrigaria este módulo a conhecer cada
tipo, e seria o primeiro passo para um CMS genérico -- que não é o que
o produto precisa.

AUSÊNCIA NÃO É ERRO
-------------------
Página que não existe, seção desativada, idioma sem tradução: tudo isso
devolve vazio, e o template desenha o que tiver. Uma instalação nova, com
o banco recém-migrado, mostra a Home com as seções vazias em vez de um
500 -- e o administrador preenche pela tela.
"""

from django.conf import settings
from django.db.models import Prefetch
from django.utils.translation import get_language

from .models import Page, PageSection

# A página que a landing pública consome.
CHAVE_DA_HOME = "home"


def _idioma_do_conteudo():
    """
    O idioma em que o conteúdo deve sair.

    Hoje é sempre português -- a interface é só em português desde a
    Etapa 4.1, e `InterfaceEmPortuguesMiddleware` garante isso. Ler o
    idioma ativo em vez de escrever "pt" aqui é o que faz esta camada
    continuar certa no dia em que essa decisão mudar.
    """
    return get_language() or settings.LANGUAGE_CODE


def secoes_da_pagina(page_key, language=None):
    """
    As seções ativas de `page_key`, indexadas pela chave da seção.

    Devolve `{"hero": {...}, "partners": {...}}`. Seção sem `key` cai no
    seu `kind`, que é o que basta quando há uma só daquele tipo.

    O idioma pedido, com queda para o padrão do projeto: uma seção sem
    tradução no idioma ativo aparece no idioma de origem em vez de
    sumir da página.
    """
    idioma = language or _idioma_do_conteudo()
    padrao = settings.LANGUAGE_CODE

    pagina = (
        Page.objects.filter(key=page_key, is_active=True)
        .prefetch_related(
            # Uma consulta para as seções e uma para as traduções -- e não
            # uma por seção. Sem isto, uma Home com cinco seções custaria
            # seis consultas a mais.
            Prefetch(
                "sections",
                queryset=PageSection.objects.filter(is_active=True).prefetch_related(
                    "translations"
                ),
            )
        )
        .first()
    )
    if pagina is None:
        return {}

    resultado = {}
    for secao in pagina.sections.all():
        por_idioma = {t.language: t.content for t in secao.translations.all()}
        conteudo = por_idioma.get(idioma) or por_idioma.get(padrao) or {}
        resultado[secao.key or secao.kind] = conteudo if isinstance(conteudo, dict) else {}
    return resultado
