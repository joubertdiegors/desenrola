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
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.core.views import exige_permissao

from . import section_schema, services
from .forms import FormularioDeSecao
from .models import Page, PageSection, PageSectionTranslation
from .services import CHAVE_DA_HOME

# As duas permissões desta seção. Constantes, e não a string solta em
# cada view e template, para o dia em que alguém procurar "quem decide
# isto".
# As tres larguras que a previa simula, em pixels. Sao as larguras do
# CSS de verdade -- a media query de celular do projeto corta em 767px
# (ver static/css/layout.css), entao 390 e 1280 caem dos dois lados dela
# com folga, e 834 exercita a faixa do meio.
#
# Lista FECHADA: o valor chega do navegador e acaba num `<meta>`.
VIEWPORTS = {
    "desktop": 1280,
    "tablet": 834,
    "mobile": 390,
    # A miniatura da Central: quadro pequeno, desenho de desktop. E o
    # unico caso em que a largura de referencia e FORCADA por `<meta>`.
    "miniatura": 1280,
}
PADRAO_DO_VIEWPORT = "desktop"

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

    todas = list(pagina.sections.all()) if pagina else []

    # Topo / Meio / Final, na ordem da página. Os grupos vêm de
    # `section_schema` -- são a forma de ler a página, não uma tabela.
    grupos = []
    for chave, nome, explicacao in [
        (g[0], g[1], g[2]) for g in section_schema.GRUPOS
    ]:
        do_grupo = [
            _linha_da_central(secao, idioma)
            for secao in todas
            if (section_schema.secao_declarada(secao) or None)
            and section_schema.secao_declarada(secao).grupo == chave
        ]
        if do_grupo:
            grupos.append(
                {"chave": chave, "nome": nome, "explicacao": explicacao, "partes": do_grupo}
            )

    # As que nenhuma declaração conhece. Não somem da tela: some a
    # ILUSÃO de que a Central sabe editá-las.
    sem_declaracao = [
        secao for secao in todas if section_schema.secao_declarada(secao) is None
    ]

    return render(
        request,
        "backoffice/content.html",
        {
            "active": "content",
            "bo_title": _("Conteúdo do site"),
            "pagina": pagina,
            "grupos": grupos,
            "sem_declaracao": sem_declaracao,
            "idioma": idioma,
            "idiomas": idiomas_disponiveis(idioma),
            "pode_editar": request.user.has_perm(EDITAR_PERM),
        },
    )


def _linha_da_central(secao, idioma):
    """Uma parte da página, como a Central a apresenta."""
    declarada = section_schema.secao_declarada(secao)
    traducao = _traducao(secao, idioma)
    return {
        "secao": secao,
        "nome": declarada.nome,
        "descricao": declarada.descricao,
        "editavel": section_schema.editavel(secao),
        "tem_traducao": bool(traducao and traducao.content),
        "atualizada_em": traducao.updated_at if traducao else None,
    }


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


@exige_permissao(VER_PERM)
def backoffice_content_preview(request, pk):
    """
    UMA parte da Home, desenhada com o código real.

    É o que a Central põe no `<iframe>` de cada miniatura e o que o
    editor põe no painel de pré-visualização. O contexto é
    `contexto_da_home()` -- o mesmo da página pública -- e o parcial é o
    mesmo que a Home inclui. Não existe segunda implementação visual,
    então a prévia não tem como divergir.

    GET desenha o que está SALVO. POST desenha o que está DIGITADO,
    sem gravar nada: é o que permite ver antes de salvar.

    Mostra a parte MESMO QUE ELA ESTEJA DESATIVADA: quem administra
    precisa ver o que está prestes a religar. A Home pública continua
    não a mostrando -- são perguntas diferentes.

    O NAVEGADOR NUNCA ESCOLHE TEMPLATE
    ----------------------------------
    Ele manda, no máximo, o DESENHO (`imagem_texto`, ...) e a LARGURA.
    Os dois passam por lista fechada: desenho desconhecido cai no
    padrão, largura desconhecida cai em `desktop`. Nenhum caminho de
    arquivo atravessa daqui.
    """
    secao = get_object_or_404(
        PageSection.objects.select_related("page"), pk=pk, page__key=CHAVE_DA_HOME
    )
    chave = secao.key or secao.kind

    # O desenho: o gravado, ou o que o formulário está propondo.
    desenho = secao.layout
    if request.method == "POST":
        desenho = request.POST.get("layout") or desenho

    parcial = section_schema.parcial_da_secao(chave, desenho)
    if parcial is None:
        raise Http404("esta parte não tem desenho próprio")

    contexto = services.contexto_da_home()

    # A parte desativada nao vem em `contexto_da_home()` (ele so traz as
    # ativas). Para a previa, ela e reposta -- so aqui, e so para
    # desenhar.
    if chave not in contexto["partes"]:
        reposta = services.parte_avulsa(secao)
        contexto["partes"] = {**contexto["partes"], chave: reposta}
        contexto["secoes"] = {**contexto["secoes"], chave: reposta.conteudo}
        if chave == "footer":
            contexto.update(services.contexto_do_rodape())

    if request.method == "POST":
        contexto = _com_o_que_esta_digitado(contexto, secao, chave, desenho, request.POST)

    contexto.update(
        {
            "parcial": parcial,
            "secao": secao,
            "viewport": _viewport_pedido(request),
        }
    )
    return render(request, "backoffice/content_preview.html", contexto)


def _com_o_que_esta_digitado(contexto, secao, chave, desenho, dados):
    """
    O contexto da prévia, com o conteúdo do formulário por cima -- em
    memória, sem tocar no banco.

    `FormularioDeSecao.conteudo()` é o MESMO método que o salvamento
    usa: o que a prévia mostra é exatamente o que seria gravado. Duas
    montagens diferentes divergiriam, e a prévia passaria a mentir.

    Formulário inválido não derruba a prévia: ela continua desenhando o
    que está salvo, e quem valida é a tela de edição.
    """
    from copy import deepcopy

    parte = contexto["partes"][chave]
    # A seção precisa do desenho proposto para o formulário montar os
    # campos certos -- sem gravar.
    espelho = deepcopy(secao)
    espelho.layout = desenho

    form = FormularioDeSecao(espelho, parte.conteudo, data=dados)
    if not form.is_valid():
        return contexto

    proposto = services.ParteDaPagina(
        chave=chave, conteudo=form.conteudo(), desenho=desenho, ordem=parte.ordem
    )
    contexto = dict(contexto)
    contexto["partes"] = {**contexto["partes"], chave: proposto}
    contexto["secoes"] = {**contexto["secoes"], chave: proposto.conteudo}
    if chave == "footer":
        from .section_schema import blocos_do_rodape

        blocos = blocos_do_rodape(proposto.conteudo)
        contexto["blocos_do_rodape"] = blocos
        contexto["mostra_contato_do_rodape"] = "contato" in blocos
    return contexto


def _viewport_pedido(request):
    """
    Qual largura simular. Lista fechada -- o valor vem do navegador e
    acaba num `<meta>`.
    """
    pedido = request.POST.get("viewport") or request.GET.get("viewport") or ""
    return pedido if pedido in VIEWPORTS else PADRAO_DO_VIEWPORT


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
