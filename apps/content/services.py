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

from dataclasses import dataclass

from django.conf import settings
from django.db.models import Prefetch
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from .models import ContentTranslation, FaqItem, MenuItem, Page, PageSection, Partner

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


@dataclass(frozen=True)
class ParteDaPagina:
    """
    Uma parte da página como o template a enxerga: o texto, o desenho
    escolhido e a ordem.

    Não é o `PageSection`: é o retrato do que aquela parte publica. Um
    template não tem por que alcançar `is_active` ou `page_id` -- se
    chegou até aqui, é porque está ativa.
    """

    chave: str
    conteudo: dict
    desenho: str
    ordem: int
    # O `Asset` desta parte, ou None. O template pergunta
    # `partes.hero.imagem.file.url` -- mesma forma do parceiro.
    imagem: object = None
    # Estrutural, das colunas de `PageSection` -- não do JSON de
    # conteúdo. Valem em qualquer idioma, e por isso não moram em
    # `conteudo`. Ver os campos equivalentes em `PageSection`.
    #
    # `partners_carousel_enabled` e `partners_carousel_controls_enabled`
    # continuam no modelo, com os valores gravados, mas não são lidos:
    # a Home passou a mostrar uma fileira de quatro e o "Ver todos", sem
    # carrossel (ver `core/secoes/partners.html`). As colunas ficaram
    # para que a mudança seja reversível sem perder configuração.
    contador_ativo: bool = False
    contador_posicao: str = PageSection.Posicao9.SUPERIOR_ESQUERDA
    contador_ao_vivo_ativo: bool = True
    parceiros_posicao_botao: str = PageSection.Posicao9.INFERIOR_CENTRO
    parceiros_ver_todos_ativo: bool = True


def partes_da_pagina(page_key, language=None):
    """
    As partes ATIVAS de `page_key`, na ordem da página.

    Devolve `{"hero": ParteDaPagina(...), ...}` -- um dicionário, porque
    o template alcança cada parte pelo nome (`partes.hero`), e em ordem,
    porque quem itera precisa da sequência real.

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
                queryset=PageSection.objects.filter(is_active=True)
                .select_related("image")
                .prefetch_related("translations"),
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
        resultado[secao.key or secao.kind] = _parte_de(secao, conteudo)
    return resultado


def _parte_de(secao, conteudo):
    """
    Monta o `ParteDaPagina` de uma `PageSection` já carregada.

    UM LUGAR SÓ PARA OS CAMPOS ESTRUTURAIS
    ---------------------------------------
    `partes_da_pagina()` e `parte_avulsa()` fazem a MESMA pergunta --
    "como esta seção se parece?" -- só que para conjuntos diferentes de
    seções (ativas / uma qualquer). Manter os campos estruturais
    (contador, botão e carrossel de parceiros) escritos nos dois lugares
    seria exatamente o tipo de duplicação que este projeto evita: o dia
    em que uma coluna nova entrar em `PageSection`, só este ponto muda.
    """
    return ParteDaPagina(
        chave=secao.key or secao.kind,
        conteudo=conteudo if isinstance(conteudo, dict) else {},
        desenho=secao.layout or "",
        ordem=secao.order,
        imagem=secao.image,
        contador_ativo=secao.counter_enabled,
        contador_posicao=secao.counter_position,
        contador_ao_vivo_ativo=secao.counter_live_enabled,
        parceiros_posicao_botao=secao.partners_button_position,
        parceiros_ver_todos_ativo=secao.partners_view_all_enabled,
    )


def parte_avulsa(secao, language=None):
    """
    O retrato de UMA seção, ativa ou não.

    `partes_da_pagina()` só traz as ativas, e está certo: é o que a
    página pública deve mostrar. A pré-visualização do Backoffice
    pergunta outra coisa -- "como ficaria esta parte?" -- e precisa
    desenhar também a que está desligada.
    """
    idioma = language or _idioma_do_conteudo()
    padrao = settings.LANGUAGE_CODE

    por_idioma = {t.language: t.content for t in secao.translations.all()}
    conteudo = por_idioma.get(idioma) or por_idioma.get(padrao) or {}
    return _parte_de(secao, conteudo)


def secoes_da_pagina(page_key, language=None):
    """
    Só o texto de cada parte ativa: `{"hero": {...}, "partners": {...}}`.

    Continua existindo porque é o que a maioria dos templates precisa --
    `partes_da_pagina()` é para quem também precisa do desenho.
    """
    return {
        chave: parte.conteudo
        for chave, parte in partes_da_pagina(page_key, language).items()
    }


# ---------------------------------------------------------------------------
# O contexto da Home -- UM lugar so
# ---------------------------------------------------------------------------
#
# A pagina publica, a miniatura da Central e a pre-visualizacao saem
# daqui. E o que faz "uma unica fonte visual real" ser verdade e nao
# promessa: nao ha um segundo desenho da Home em lugar nenhum, entao a
# miniatura nao tem como ficar desatualizada.


def contexto_do_rodape(language=None):
    """
    O que `components/site_footer.html` precisa, em qualquer página.

    O rodapé aparece na Home E nas páginas legais. Sem isto, a página
    legal incluiria o componente sem os dados e o rodapé simplesmente
    não desenharia -- que foi exatamente o que aconteceu quando a
    composição passou a vir do CMS.
    """
    from .section_schema import blocos_do_rodape

    rodape = partes_da_pagina(CHAVE_DA_HOME, language).get("footer")
    blocos = blocos_do_rodape(rodape.conteudo) if rodape else []
    return {
        "partes": {"footer": rodape} if rodape else {},
        "blocos_do_rodape": blocos,
    }


def contexto_dos_parceiros(language=None):
    """
    O que a pagina publica de parceiros precisa.

    Os MESMOS parceiros da Home, do mesmo modelo e na mesma ordem -- a
    Home mostra os quatro primeiros, esta pagina mostra todos. Nao ha
    segunda fonte de dados nem cadastro proprio.

    Leva a barra e o rodape junto porque a pagina e publica: sem eles a
    casca simplesmente nao desenharia (mesma razao de
    `contexto_do_rodape`).
    """
    partes = partes_da_pagina(CHAVE_DA_HOME, language)
    parceiros = list(Partner.objects.publicados())
    perguntas = list(FaqItem.objects.publicadas())

    from .section_schema import blocos_do_rodape

    rodape = partes.get("footer")
    return {
        "partes": partes,
        "secoes": {chave: parte.conteudo for chave, parte in partes.items()},
        "blocos_do_rodape": blocos_do_rodape(rodape.conteudo) if rodape else [],
        "menu_itens": _menu_sem_ancora_morta(partes, parceiros, perguntas),
        "parceiros": parceiros,
    }


def contexto_da_home(language=None):
    """
    Tudo o que `core/home.html` precisa para desenhar a Home.

    Carregado aqui, e não no processador de contexto global: são dados
    DESTA página. O processador guarda o que vale para o site inteiro.
    """
    from apps.letters import statistics

    from .section_schema import blocos_do_rodape, template_do_desenho

    partes = partes_da_pagina(CHAVE_DA_HOME, language)
    parceiros = list(Partner.objects.publicados())
    perguntas = list(FaqItem.objects.publicadas())

    # Qual desenho o Banner usa. Resolvido AQUI, e nao no template: um
    # valor invalido na coluna nao pode virar um `{% include %}` de um
    # arquivo que nao existe.
    banner = partes.get("hero")
    template_do_banner = (
        template_do_desenho("hero", banner.desenho) if banner else None
    )

    rodape = partes.get("footer")
    blocos = blocos_do_rodape(rodape.conteudo) if rodape else []

    return {
        "partes": partes,
        "template_do_banner": template_do_banner,
        "blocos_do_rodape": blocos,
        # `secoes` continua no contexto: e o que os templates ja leem, e
        # trocar tudo de uma vez seria mexer em marcacao que funciona.
        "secoes": {chave: parte.conteudo for chave, parte in partes.items()},
        "menu_itens": _menu_sem_ancora_morta(partes, parceiros, perguntas),
        "parceiros": parceiros,
        "perguntas": perguntas,
        "cartas_emitidas": statistics.cartas_emitidas(),
    }


# As ancoras que a Home desenha, e de que parte cada uma depende.
# `#parceiros` tem uma condicao a mais: a secao so aparece quando ha
# parceiro cadastrado (ver `core/home.html`).
# As ancoras que a Home DESENHA, e de que parte cada uma depende.
#
# Conferido nos parciais: `core/secoes/how.html` e
# `core/secoes/partners.html` sao os dois unicos com `id=`. Uma ancora
# fora desta lista nao existe na pagina -- nao e "desconhecida", e MORTA.
ANCORAS_DA_HOME = {
    "#como-funciona": "how",
    "#parceiros": "partners",
    "#faq": "faq",
}

# As ancoras cuja secao some quando o CADASTRO dela esta vazio -- nao
# basta a parte estar ativa na pagina. O valor e o nome da lista que
# `contexto_da_home` carrega para aquela secao.
ANCORAS_QUE_DEPENDEM_DE_CADASTRO = {
    "partners": "parceiros",
    "faq": "perguntas",
}


def _menu_sem_ancora_morta(partes, parceiros, perguntas=()):
    """
    Os itens do menu, menos os que levariam a lugar nenhum.

    Um item que aponta para `#parceiros` some quando a seção de
    parceiros não está na página -- desativada, ou sem nenhum parceiro
    cadastrado. `#faq` segue a mesma regra, com as perguntas. Era o
    comportamento do template antes de o menu virar
    cadastro (`{% if parceiros %}`), e ele não podia se perder: âncora
    que não leva a lugar nenhum é o defeito que este projeto remove
    desde a Etapa G.

    Destino que não é âncora (um caminho ou um endereço externo) passa
    sempre -- quem digitou sabe para onde aponta.

    ÂNCORA QUE NÃO EXISTE TAMBÉM SOME
    ---------------------------------
    Até a Etapa 11, um `#promoções` -- que a Home não desenha em lugar
    nenhum -- caía no caso "não é âncora conhecida" e aparecia na barra
    levando a lugar nenhum. É o mesmo defeito que a seção desativada já
    não tinha. O formulário passou a recusar criar assim; isto aqui
    protege o que já esteja gravado, e o dia em que um `id` sair de um
    parcial.
    """
    visiveis = []
    for item in MenuItem.objects.publicados():
        if item.destination.startswith("#"):
            parte = ANCORAS_DA_HOME.get(item.destination)
            if parte is None:
                continue
        else:
            visiveis.append(item)
            continue
        if parte not in partes:
            continue
        cadastro = ANCORAS_QUE_DEPENDEM_DE_CADASTRO.get(parte)
        if cadastro and not {"parceiros": parceiros, "perguntas": perguntas}[cadastro]:
            continue
        visiveis.append(item)
    return visiveis


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
