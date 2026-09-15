"""
A gestão do conteúdo das páginas, no Backoffice.

O QUE ESTA TELA É
-----------------
O editor das seções que a Home mostra. Lista o que existe, abre uma
seção por vez e grava os textos daquele idioma. Os campos vêm de
`section_schema`, então a tela oferece exatamente o que o template lê.

O QUE ELA NÃO É
---------------
Não é um construtor de páginas: não cria nem apaga seção, não reordena
e não inventa tipo. Isso é estrutura, e estrutura mora no template e nas
migrations. Aqui se escreve.

IDIOMA DO CONTEÚDO ≠ IDIOMA DA INTERFACE
----------------------------------------
A tela é sempre em português -- é a decisão do produto para toda a
administração. O que se ESCOLHE aqui é o idioma do CONTEÚDO, e ele vem
de `settings.LANGUAGES`: o que o cliente manda é conferido contra essa
lista antes de virar consulta, nunca usado como veio.
"""

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.core.views import exige_permissao

from . import section_schema
from .forms import FormularioDeSecao
from .models import Page, PageSection, PageSectionTranslation
from .services import CHAVE_DA_HOME

# As duas permissões desta seção. Constantes, e não a string solta em
# cada view e template, para o dia em que alguém procurar "quem decide
# isto".
VER_PERM = "content.view_pagesection"
EDITAR_PERM = "content.change_pagesection"


def idioma_pedido(request):
    """
    O idioma do conteúdo, conferido contra `settings.LANGUAGES`.

    Nunca o que veio na querystring: `?idioma=` é entrada do cliente, e
    ela acabaria num filtro de banco e num rótulo de tela.
    """
    aceitos = [codigo for codigo, _nome in settings.LANGUAGES]
    pedido = request.GET.get("idioma") or request.POST.get("idioma")
    return pedido if pedido in aceitos else settings.LANGUAGE_CODE


def idiomas_disponiveis(idioma_atual):
    """Os quatro idiomas, com o nome e qual está sendo editado."""
    return [
        {"codigo": codigo, "nome": nome, "atual": codigo == idioma_atual}
        for codigo, nome in settings.LANGUAGES
    ]


def _traducao(secao, idioma):
    """A tradução daquele idioma, ou `None` -- ausência não é erro."""
    return secao.translations.filter(language=idioma).first()


@exige_permissao(VER_PERM)
def backoffice_content(request):
    """
    As seções da Home, no idioma escolhido.

    Mostra quais já têm texto naquele idioma e quais não têm. Falta de
    tradução aparece como FALTA -- não se inventa texto nem se conta
    porcentagem de tradução.
    """
    idioma = idioma_pedido(request)
    pagina = (
        Page.objects.filter(key=CHAVE_DA_HOME)
        .prefetch_related("sections__translations")
        .first()
    )

    secoes = []
    for secao in pagina.sections.all() if pagina else []:
        traducao = _traducao(secao, idioma)
        secoes.append(
            {
                "secao": secao,
                "editavel": section_schema.editavel(secao),
                "tem_traducao": bool(traducao and traducao.content),
                "atualizada_em": traducao.updated_at if traducao else None,
            }
        )

    return render(
        request,
        "backoffice/content.html",
        {
            "active": "content",
            "bo_title": _("Conteúdo do site"),
            "pagina": pagina,
            "secoes": secoes,
            "idioma": idioma,
            "idiomas": idiomas_disponiveis(idioma),
            "pode_editar": request.user.has_perm(EDITAR_PERM),
        },
    )


@exige_permissao(VER_PERM)
def backoffice_content_section(request, pk):
    """
    Edita os textos de UMA seção, num idioma.

    VER exige `content.view_pagesection`; GRAVAR exige, além disso,
    `content.change_pagesection` -- e a checagem do POST é aqui, no
    servidor, não no botão.

    A seção é buscada pelo `pk` DENTRO da página conhecida: um id de
    outra página não abre esta tela.
    """
    secao = get_object_or_404(
        PageSection.objects.select_related("page"), pk=pk, page__key=CHAVE_DA_HOME
    )
    idioma = idioma_pedido(request)
    traducao = _traducao(secao, idioma)
    pode_editar = request.user.has_perm(EDITAR_PERM)

    if not section_schema.editavel(secao):
        messages.error(
            request,
            _("Esta seção ainda não tem campos definidos e não pode ser editada aqui."),
        )
        return redirect(_url_da_lista(idioma))

    if request.method == "POST":
        if not pode_editar:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        form = FormularioDeSecao(
            secao, traducao.content if traducao else {}, data=request.POST
        )
        if form.is_valid():
            PageSectionTranslation.objects.update_or_create(
                section=secao,
                language=idioma,
                defaults={"content": form.conteudo()},
            )
            messages.success(request, _("Conteúdo salvo."))
            return redirect(_url_da_lista(idioma))
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = FormularioDeSecao(secao, traducao.content if traducao else {})

    return render(
        request,
        "backoffice/content_section.html",
        {
            "active": "content",
            "bo_title": _("Conteúdo do site"),
            "secao": secao,
            "form": form,
            "idioma": idioma,
            "idiomas": idiomas_disponiveis(idioma),
            "tem_traducao": bool(traducao and traducao.content),
            "pode_editar": pode_editar,
            "url_da_lista": _url_da_lista(idioma),
        },
    )


@exige_permissao(EDITAR_PERM)
@require_POST
def backoffice_content_activation(request, pk):
    """
    Liga e desliga uma seção. Desligada, ela some da Home -- em todos os
    idiomas: a situação é da SEÇÃO, não da tradução.

    Não apaga nada: o texto continua guardado e volta quando a seção for
    ligada de novo.
    """
    secao = get_object_or_404(PageSection, pk=pk, page__key=CHAVE_DA_HOME)
    secao.is_active = request.POST.get("ativa") == "1"
    secao.save(update_fields=["is_active", "updated_at"])

    if secao.is_active:
        messages.success(request, _("Seção ativada."))
    else:
        messages.success(request, _("Seção desativada. Ela deixa de aparecer na Home."))
    return redirect(_url_da_lista(idioma_pedido(request)))


def _url_da_lista(idioma):
    return f"{reverse('backoffice:content')}?idioma={idioma}"
