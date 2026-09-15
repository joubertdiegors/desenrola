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
from django.utils.translation import gettext_lazy as _

from .models import ContentTranslation, Page, PageSection

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


# ---------------------------------------------------------------------------
# Paginas legais
# ---------------------------------------------------------------------------
#
# POR QUE `ContentBlock`, E NAO `Page`/`PageSection`
# -------------------------------------------------
# Um texto legal e UM CORPO DE TEXTO. `PageSection` existe porque a Home
# tem hero, features, parceiros e chamada -- coisas com ordem, icone e
# ativacao propria. Um Termo de Uso nao tem nada disso, e representa-lo
# como uma lista de secoes tipadas seria pagar a complexidade de uma
# estrutura que ele nao usa.
#
# `ContentBlock` existe no projeto desde a primeira migration do app,
# e o docstring do modulo cita literalmente "legal.terms_of_use" como
# exemplo do que ele serve para guardar. Esta e a etapa que finalmente o
# consome.
#
# O CONTEUDO NASCE VAZIO, DE PROPOSITO
# ------------------------------------
# A migration cria os dois blocos SEM traducao. Texto juridico e do
# cliente, nao do codigo -- ele entra depois, pelo Django Admin. Enquanto
# nao entrar, a pagina responde 404 e o link NAO aparece em lugar nenhum
# do site. Um link que leva a uma pagina em branco e pior do que link
# nenhum.

# (slug da URL, chave do ContentBlock, titulo da pagina)
#
# Os slugs sao literais nas rotas: nenhuma parte da URL vira chave de
# consulta sem passar por aqui.
PAGINAS_LEGAIS = (
    ("termos-de-uso", "legal.terms_of_use", _("Termos de uso")),
    ("privacidade", "legal.privacy_policy", _("Privacidade")),
)

CHAVES_LEGAIS = tuple(chave for _slug, chave, _titulo in PAGINAS_LEGAIS)


def texto_legal(chave, language=None):
    """
    O texto publicado daquele documento, ou `None`.

    `None` -- que a view transforma em 404 -- em QUALQUER um destes
    casos, todos legitimos e nenhum deles erro:

      * o bloco nao existe;
      * o bloco esta desativado;
      * nao ha traducao no idioma pedido nem no idioma padrao;
      * a traducao existe mas esta em branco (o estado em que a
        migration deixa tudo, ate o cliente escrever o texto).

    O idioma segue a MESMA regra de `secoes_da_pagina`: o pedido e,
    nao havendo, o padrao do projeto. Nao ha traducao inventada -- so a
    queda que o resto do CMS ja faz.

    UMA CONSULTA. A pergunta e sobre o TEXTO, nao sobre o objeto: um
    join nas traducoes responde de uma vez, enquanto
    `prefetch_related` custaria sempre duas idas ao banco. O filtro por
    `block__is_active` faz o bloco desativado simplesmente nao trazer
    linha nenhuma.
    """
    idioma = language or _idioma_do_conteudo()
    padrao = settings.LANGUAGE_CODE

    por_idioma = dict(
        ContentTranslation.objects.filter(
            block__key=chave,
            block__is_active=True,
            language__in={idioma, padrao},
        ).values_list("language", "content")
    )

    texto = por_idioma.get(idioma) or por_idioma.get(padrao) or ""
    if not isinstance(texto, str):
        return None
    return texto.strip() or None


def legais_publicadas(language=None):
    """
    Quais documentos legais ja tem texto -- numa consulta so.

    E o que permite o rodape, o cadastro e o perfil mostrarem o link
    SOMENTE quando ha o que abrir. UMA consulta para os dois documentos,
    e nao uma por link.
    """
    idioma = language or _idioma_do_conteudo()
    padrao = settings.LANGUAGE_CODE

    por_chave = {}
    linhas = ContentTranslation.objects.filter(
        block__key__in=CHAVES_LEGAIS,
        block__is_active=True,
        language__in={idioma, padrao},
    ).values_list("block__key", "language", "content")
    for chave, lingua, texto in linhas:
        por_chave.setdefault(chave, {})[lingua] = texto

    publicadas = set()
    for chave, por_idioma in por_chave.items():
        texto = por_idioma.get(idioma) or por_idioma.get(padrao) or ""
        if isinstance(texto, str) and texto.strip():
            publicadas.add(chave)
    return publicadas
