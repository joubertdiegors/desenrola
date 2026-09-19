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

import base64
import json
from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from apps.core.views import exige_permissao

from . import blocos as blocos_svc
from . import rodape, section_schema, services
from .forms import (
    FormularioDeImagem,
    FormularioDeItemDoMenu,
    FormularioDeParceiro,
    FormularioDePergunta,
    FormularioDeSecao,
)
from .models import (
    Asset,
    AssetFileImmutableError,
    ContentBlock,
    ContentTranslation,
    FaqItem,
    MenuItem,
    Page,
    PageSection,
    PageSectionTranslation,
    Partner,
)
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
            "bo_title": _("Home - Configurações"),
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
    declarada = section_schema.secao_declarada(secao)

    if not section_schema.editavel(secao):
        messages.error(
            request,
            _("Esta seção ainda não tem campos definidos e não pode ser editada aqui."),
        )
        return redirect(_url_da_lista(idioma))

    if request.method == "POST":
        if not pode_editar:
            raise PermissionDenied
        # A imagem ANTERIOR, antes do formulario mutar `secao.image` --
        # `aplicar_na_secao` grava por cima da mesma instancia, entao
        # depois dela rodar nao ha mais como saber qual era a antiga.
        imagem_anterior = secao.image
        form = FormularioDeSecao(
            secao, traducao.content if traducao else {}, data=request.POST, files=request.FILES
        )
        if form.is_valid():
            PageSectionTranslation.objects.update_or_create(
                section=secao,
                language=idioma,
                defaults={"content": form.conteudo()},
            )
            # Desenho e imagem sao da SECAO, nao da traducao: gravados
            # aqui, valem em todos os idiomas.
            form.aplicar_na_secao(secao)
            if imagem_anterior and imagem_anterior.pk != secao.image_id:
                _apagar_asset_se_orfao(imagem_anterior)
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
            "bo_title": _("Home - Configurações"),
            "secao": secao,
            # O nome amigavel, e nao `secao.key`: chave tecnica na tela e
            # vazamento de implementacao para quem administra.
            "nome_da_secao": declarada.nome,
            "descricao_da_secao": declarada.descricao,
            "form": form,
            "idioma": idioma,
            "idiomas": idiomas_disponiveis(idioma),
            "tem_traducao": bool(traducao and traducao.content),
            "pode_editar": pode_editar,
            "url_da_lista": _url_da_lista(idioma),
            # O cadastro proprio desta secao, quando ela tem um.
            "cadastro": declarada.cadastro,
            "itens_do_menu": (
                _linhas_com_pontas(MenuItem.objects.all())
                if declarada.cadastro == "menu"
                else None
            ),
            "url_dos_parceiros": (
                reverse("backoffice:partners") if declarada.cadastro == "parceiros" else None
            ),
            "perguntas": (
                _linhas_com_pontas(FaqItem.objects.all())
                if declarada.cadastro == "faq"
                else None
            ),
            # Os atalhos que o editor rico oferece -- so nas secoes que tem
            # conteudo rico (hoje, o rodape).
            "atalhos_do_editor": rodape.ATALHOS if form.tem_editor_rico() else None,
        },
    )


@exige_permissao(VER_PERM)
@xframe_options_sameorigin
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

    POR QUE `xframe_options_sameorigin`
    -----------------------------------
    Em produção o projeto manda `X_FRAME_OPTIONS = "DENY"`, que proíbe
    QUALQUER enquadramento -- inclusive o de mesma origem. Sem esta
    exceção, a miniatura da Central e o quadro do editor apareceriam
    vazios no ar, e em lugar nenhum antes: a suíte roda com as
    configurações de desenvolvimento, onde `DENY` não está ligado.

    A exceção é só desta view. O resto do site continua recusando ser
    enquadrado, que é a defesa contra clickjacking.

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

    # O contador da prévia faz a MESMA conta da Home, com o valor inicial
    # DESTA seção -- também quando ela está desativada, e por isso fora
    # de `contexto_da_home()`.
    declarada = section_schema.secao_declarada(secao)
    if declarada and declarada.contador:
        contexto["cartas_emitidas"] = services.numero_do_contador(secao.counter_initial_value)

    if request.method == "POST":
        contexto = _com_o_que_esta_digitado(
            contexto, secao, chave, desenho, request.POST, request.FILES
        )

    contexto.update(
        {
            "parcial": parcial,
            "secao": secao,
            "nome_da_secao": section_schema.nome_amigavel(secao),
            "viewport": _viewport_pedido(request),
        }
    )
    return render(request, "backoffice/content_preview.html", contexto)


def _asset_temporario_para_previa(arquivo):
    """
    O arquivo ENVIADO AGORA, como algo que os parciais sabem desenhar
    (`imagem.file.url`, `imagem.alt_text`) -- sem criar um `Asset` de
    verdade. A prévia nunca grava nada; um `Asset` novo a cada tecla
    digitada encheria a Biblioteca de lixo antes mesmo de alguém clicar
    em Salvar.
    """
    arquivo.seek(0)
    dados = base64.b64encode(arquivo.read()).decode("ascii")
    tipo = getattr(arquivo, "content_type", None) or "image/png"
    return SimpleNamespace(file=SimpleNamespace(url=f"data:{tipo};base64,{dados}"), alt_text="")


def _com_o_que_esta_digitado(contexto, secao, chave, desenho, dados, arquivos=None):
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

    form = FormularioDeSecao(espelho, parte.conteudo, data=dados, files=arquivos)
    if not form.is_valid():
        return contexto

    def _proposto_ou_atual(nome_do_campo, nome_na_parte):
        """
        O que está no formulário, quando o campo existe nele -- senão o
        que já está gravado. Mesma regra da `imagem`, generalizada: os
        campos estruturais (contador e botão dos parceiros)
        só aparecem no formulário das seções que os declaram, e a prévia
        de uma seção sem eles não pode inventar um valor.
        """
        if nome_do_campo in form.fields:
            return form.cleaned_data.get(nome_do_campo)
        return getattr(parte, nome_na_parte)

    def _imagem_proposta():
        """
        Upload novo (Bloco D) vence a seleção da biblioteca, que vence
        "remover", que vence a imagem já gravada -- mesma ordem de
        `FormularioDeSecao.aplicar_na_secao`. Um upload novo NUNCA vira
        `Asset`: a prévia mostra o arquivo em memória, direto.
        """
        if "imagem" not in form.fields:
            return parte.imagem
        novo_arquivo = form.cleaned_data.get("imagem_upload")
        if novo_arquivo:
            return _asset_temporario_para_previa(novo_arquivo)
        if form.cleaned_data.get("imagem_remover"):
            return None
        return form.cleaned_data.get("imagem")

    proposto = services.ParteDaPagina(
        chave=chave,
        conteudo=form.conteudo(),
        desenho=desenho,
        ordem=parte.ordem,
        imagem=_imagem_proposta(),
        contador_ativo=bool(_proposto_ou_atual("contador_ativo", "contador_ativo")),
        contador_posicao=_proposto_ou_atual("contador_posicao", "contador_posicao"),
        contador_ao_vivo_ativo=bool(
            _proposto_ou_atual("contador_ao_vivo_ativo", "contador_ao_vivo_ativo")
        ),
        parceiros_posicao_botao=parte.parceiros_posicao_botao,
        parceiros_ver_todos_ativo=bool(
            _proposto_ou_atual("parceiros_ver_todos_ativo", "parceiros_ver_todos_ativo")
        ),
    )
    contexto = dict(contexto)
    contexto["partes"] = {**contexto["partes"], chave: proposto}
    contexto["secoes"] = {**contexto["secoes"], chave: proposto.conteudo}
    if "contador_valor_inicial" in form.fields:
        # O valor inicial DIGITADO, ainda não salvo -- na mesma conta.
        contexto["cartas_emitidas"] = services.numero_do_contador(
            form.cleaned_data.get("contador_valor_inicial") or 0
        )
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


# ---------------------------------------------------------------------------
# Parceiros
# ---------------------------------------------------------------------------
#
# As quatro permissoes que o Django ja gera para o modelo. Nao ha
# permissao inventada aqui: `view/add/change/delete_partner` sao as
# mesmas que a administracao do Django cobra neste cadastro, e agora sao
# cobradas tambem por estas telas.
VER_PARCEIRO = "content.view_partner"
CRIAR_PARCEIRO = "content.add_partner"
EDITAR_PARCEIRO = "content.change_partner"
EXCLUIR_PARCEIRO = "content.delete_partner"


def _url_dos_parceiros():
    return reverse("backoffice:partners")


def _contexto_de_parceiros(request, extra=None):
    """
    O basico que toda tela de parceiro precisa.

    Os `pode_*` existem para o template NAO desenhar botao que o
    servidor recusaria. Eles nao sao a protecao -- a protecao e o
    decorador --, sao a cortesia de nao oferecer o que nao se pode
    fazer.
    """
    contexto = {
        "active": "partners",
        "bo_title": _("Parceiros"),
        "pode_criar": request.user.has_perm(CRIAR_PARCEIRO),
        "pode_editar": request.user.has_perm(EDITAR_PARCEIRO),
        "pode_excluir": request.user.has_perm(EXCLUIR_PARCEIRO),
        "url_dos_parceiros": _url_dos_parceiros(),
    }
    contexto.update(extra or {})
    return contexto


@exige_permissao(VER_PARCEIRO)
def backoffice_partners(request):
    """
    A lista de parceiros -- os mesmos que a Home mostra.

    Ate a Etapa 11 esta tela era so leitura e mandava quem quisesse
    cadastrar para a administracao do Django. Agora o cadastro inteiro
    mora aqui: o produto nao depende do Admin do Django para uma tela
    que e do produto.

    `select_related`: cada linha diz se ha imagem, e sem isto cada
    parceiro custaria uma consulta a mais.
    """
    parceiros = list(Partner.objects.select_related("logo"))
    linhas = [
        {"parceiro": linha["objeto"], "primeiro": linha["primeiro"], "ultimo": linha["ultimo"]}
        for linha in _linhas_com_pontas(parceiros)
    ]

    return render(
        request,
        "backoffice/partners.html",
        _contexto_de_parceiros(
            request,
            {
                "linhas": linhas,
                "total": len(parceiros),
                "ativos": sum(1 for parceiro in parceiros if parceiro.is_active),
            },
        ),
    )


@exige_permissao(CRIAR_PARCEIRO)
def backoffice_partner_new(request):
    """Cadastra um parceiro."""
    if request.method == "POST":
        form = FormularioDeParceiro(request.POST, request.FILES)
        if form.is_valid():
            parceiro = form.save()
            messages.success(request, _("Parceiro cadastrado: %(nome)s.") % {"nome": parceiro.name})
            return redirect(_url_dos_parceiros())
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = FormularioDeParceiro()

    return render(
        request,
        "backoffice/partner_form.html",
        _contexto_de_parceiros(
            request,
            {
                "form": form,
                "parceiro": None,
                "titulo": _("Novo parceiro"),
                "pode_salvar": True,
            },
        ),
    )


@exige_permissao(VER_PARCEIRO)
def backoffice_partner_edit(request, pk):
    """
    Altera um parceiro.

    VER abre a tela; GRAVAR exige `change_partner` -- e a checagem do
    POST e aqui, no servidor, nao no botao.
    """
    parceiro = get_object_or_404(Partner.objects.select_related("logo"), pk=pk)
    pode_salvar = request.user.has_perm(EDITAR_PARCEIRO)
    # Antes do formulario mutar `parceiro.logo` (a mesma instancia, via
    # `instance=parceiro`): sem isto nao haveria como saber, depois do
    # `save()`, qual era a imagem de antes.
    imagem_anterior = parceiro.logo

    if request.method == "POST":
        if not pode_salvar:
            raise PermissionDenied
        form = FormularioDeParceiro(request.POST, request.FILES, instance=parceiro)
        if form.is_valid():
            parceiro = form.save()
            if imagem_anterior and imagem_anterior.pk != parceiro.logo_id:
                _apagar_asset_se_orfao(imagem_anterior)
            messages.success(request, _("Parceiro salvo."))
            return redirect(_url_dos_parceiros())
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = FormularioDeParceiro(instance=parceiro)

    return render(
        request,
        "backoffice/partner_form.html",
        _contexto_de_parceiros(
            request,
            {
                "form": form,
                "parceiro": parceiro,
                "titulo": parceiro.name,
                "pode_salvar": pode_salvar,
            },
        ),
    )


@exige_permissao(EDITAR_PARCEIRO)
@require_POST
def backoffice_partner_activation(request, pk):
    """
    Liga e desliga um parceiro. Desligado, ele some da Home na hora.

    Nao apaga nada -- e o caminho recomendado para tirar alguem da
    pagina sem perder o registro.
    """
    parceiro = get_object_or_404(Partner, pk=pk)
    parceiro.is_active = request.POST.get("ativo") == "1"
    parceiro.save(update_fields=["is_active", "updated_at"])

    if parceiro.is_active:
        messages.success(request, _("Parceiro ativado. Volta a aparecer na Home."))
    else:
        messages.success(request, _("Parceiro desativado. Deixa de aparecer na Home."))
    return redirect(_url_dos_parceiros())


@exige_permissao(EDITAR_PARCEIRO)
@require_POST
def backoffice_partner_move(request, pk):
    """
    Sobe ou desce um parceiro na ordem da Home.

    A renumeracao mora em `_reordenar` -- e a mesma dos itens do menu, e
    a razao dela esta la.
    """
    parceiro = get_object_or_404(Partner, pk=pk)
    if _reordenar(Partner, parceiro, request.POST.get("direcao")):
        messages.success(request, _("Ordem atualizada."))

    return redirect(_url_dos_parceiros())


@exige_permissao(EXCLUIR_PARCEIRO)
def backoffice_partner_delete(request, pk):
    """
    Apaga um parceiro, depois de confirmar.

    GET pergunta; POST apaga. Apagar e para quem foi cadastrado errado
    -- para tirar da Home quem existe de verdade, o caminho e desativar,
    e a tela de confirmacao diz isso.

    A IMAGEM SO VAI JUNTO SE FICAR ORFA
    ------------------------------------
    `logo` e um `Asset`, que e uma biblioteca compartilhada: apagar o
    parceiro nao apaga a imagem cegamente -- `_apagar_asset_se_orfao`
    confere primeiro se mais alguem a usa (outro parceiro, um banner,
    um modelo de documento, uma carta finalizada) antes de decidir.
    """
    parceiro = get_object_or_404(Partner.objects.select_related("logo"), pk=pk)

    if request.method == "POST":
        nome = parceiro.name
        imagem = parceiro.logo
        parceiro.delete()
        _apagar_asset_se_orfao(imagem)
        messages.success(request, _("Parceiro removido: %(nome)s.") % {"nome": nome})
        return redirect(_url_dos_parceiros())

    imagem_sera_removida = bool(
        parceiro.logo and not _onde_esta_em_uso(parceiro.logo, excluir_parceiro=parceiro)
    )
    return render(
        request,
        "backoffice/partner_delete.html",
        _contexto_de_parceiros(
            request, {"parceiro": parceiro, "imagem_sera_removida": imagem_sera_removida}
        ),
    )


# ---------------------------------------------------------------------------
# Ordem: o que parceiros e itens do menu fazem igual
# ---------------------------------------------------------------------------


def _reordenar(modelo, objeto, direcao):
    """
    Sobe ou desce um registro na lista, renumerando tudo pela posição.

    POR QUE RENUMERAR, E NÃO TROCAR DOIS `order`
    --------------------------------------------
    `order` nasce 0 para todo mundo nos dois cadastros, e a ordem real é
    desempatada pelo `pk`. Trocar o número de dois empatados não moveria
    ninguém -- o botão pareceria quebrado. Renumerar pela POSIÇÃO resolve
    o empate de uma vez e faz o botão significar o que diz.

    Devolve se houve movimento: nas pontas não há, e a tela nem oferece.
    """
    ordenados = list(modelo.objects.all())
    atual = next((i for i, o in enumerate(ordenados) if o.pk == objeto.pk), None)
    if atual is None:
        return False

    destino = atual - 1 if direcao == "subir" else atual + 1
    if not 0 <= destino < len(ordenados):
        return False

    ordenados[atual], ordenados[destino] = ordenados[destino], ordenados[atual]
    for posicao, registro in enumerate(ordenados, start=1):
        if registro.order != posicao:
            registro.order = posicao
            registro.save(update_fields=["order", "updated_at"])
    return True


def _linhas_com_pontas(objetos):
    """
    Cada registro sabendo se é o primeiro ou o último.

    É o que permite a tela não desenhar "subir" no topo nem "descer" no
    fim -- botão que não faz nada é o que estas telas tinham antes da
    Etapa I, e não volta.
    """
    objetos = list(objetos)
    return [
        {"objeto": objeto, "primeiro": i == 0, "ultimo": i == len(objetos) - 1}
        for i, objeto in enumerate(objetos)
    ]


# ---------------------------------------------------------------------------
# Itens da barra superior
# ---------------------------------------------------------------------------
#
# A tela deles é o editor da seção "navbar" (ver `cadastro="menu"` em
# `section_schema`), então toda ação volta para lá.


def _url_do_menu(idioma=None):
    navbar = PageSection.objects.filter(page__key=CHAVE_DA_HOME, key="navbar").first()
    if navbar is None:
        return _url_da_lista(idioma or settings.LANGUAGE_CODE)
    url = reverse("backoffice:content_section", args=[navbar.pk])
    return f"{url}?idioma={idioma}" if idioma else url


def _contexto_do_item(request, form, item, titulo):
    return {
        "active": "content",
        "bo_title": _("Home - Configurações"),
        "form": form,
        "item": item,
        "titulo": titulo,
        "ancoras": sorted(services.ANCORAS_DA_HOME),
        "url_do_menu": _url_do_menu(idioma_pedido(request)),
    }


@exige_permissao(EDITAR_PERM)
def backoffice_menu_item_new(request):
    """Acrescenta um item à barra superior."""
    if request.method == "POST":
        form = FormularioDeItemDoMenu(request.POST)
        if form.is_valid():
            item = form.save()
            messages.success(request, _("Item acrescentado: %(rotulo)s.") % {"rotulo": item.label})
            return redirect(_url_do_menu(idioma_pedido(request)))
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = FormularioDeItemDoMenu()

    return render(
        request,
        "backoffice/menu_item_form.html",
        _contexto_do_item(request, form, None, _("Novo item do menu")),
    )


@exige_permissao(VER_PERM)
def backoffice_menu_item_edit(request, pk):
    """
    Altera um item.

    VER abre a tela; GRAVAR exige `change_pagesection` -- e a checagem do
    POST é aqui, no servidor, não no botão.
    """
    item = get_object_or_404(MenuItem, pk=pk)

    if request.method == "POST":
        if not request.user.has_perm(EDITAR_PERM):
            raise PermissionDenied
        form = FormularioDeItemDoMenu(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, _("Item salvo."))
            return redirect(_url_do_menu(idioma_pedido(request)))
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = FormularioDeItemDoMenu(instance=item)

    return render(
        request,
        "backoffice/menu_item_form.html",
        _contexto_do_item(request, form, item, item.label),
    )


@exige_permissao(EDITAR_PERM)
@require_POST
def backoffice_menu_item_activation(request, pk):
    """Liga e desliga um item. Desligado, some da barra -- sem apagar nada."""
    item = get_object_or_404(MenuItem, pk=pk)
    item.is_active = request.POST.get("ativo") == "1"
    item.save(update_fields=["is_active", "updated_at"])

    if item.is_active:
        messages.success(request, _("Item ativado. Volta a aparecer na barra."))
    else:
        messages.success(request, _("Item desativado. Deixa de aparecer na barra."))
    return redirect(_url_do_menu(idioma_pedido(request)))


@exige_permissao(EDITAR_PERM)
@require_POST
def backoffice_menu_item_move(request, pk):
    """Sobe ou desce um item na barra."""
    item = get_object_or_404(MenuItem, pk=pk)
    if _reordenar(MenuItem, item, request.POST.get("direcao")):
        messages.success(request, _("Ordem atualizada."))
    return redirect(_url_do_menu(idioma_pedido(request)))


@exige_permissao(EDITAR_PERM)
def backoffice_menu_item_delete(request, pk):
    """
    Apaga um item, depois de confirmar.

    Um item do menu não guarda conteúdo -- é um rótulo e um destino --,
    então apagar não perde texto de ninguém. Ainda assim pergunta: some
    da barra do site na hora, e refazer é redigitar.
    """
    item = get_object_or_404(MenuItem, pk=pk)

    if request.method == "POST":
        rotulo = item.label
        item.delete()
        messages.success(request, _("Item removido: %(rotulo)s.") % {"rotulo": rotulo})
        return redirect(_url_do_menu(idioma_pedido(request)))

    return render(
        request,
        "backoffice/menu_item_delete.html",
        {
            "active": "content",
            "bo_title": _("Home - Configurações"),
            "item": item,
            "url_do_menu": _url_do_menu(idioma_pedido(request)),
        },
    )


# ---------------------------------------------------------------------------
# Biblioteca de imagens
# ---------------------------------------------------------------------------
#
# As quatro que o Django ja gera para `Asset`. Nenhuma permissao
# inventada: sao as mesmas que a administração do Django cobra neste
# cadastro, agora cobradas tambem aqui.
VER_IMAGEM = "content.view_asset"
CRIAR_IMAGEM = "content.add_asset"
EDITAR_IMAGEM = "content.change_asset"
EXCLUIR_IMAGEM = "content.delete_asset"


def _url_das_imagens():
    return reverse("backoffice:assets")


def _contexto_de_imagens(request, extra=None):
    contexto = {
        "active": "assets",
        "bo_title": _("Imagens"),
        "pode_criar": request.user.has_perm(CRIAR_IMAGEM),
        "pode_editar": request.user.has_perm(EDITAR_IMAGEM),
        "pode_excluir": request.user.has_perm(EXCLUIR_IMAGEM),
        "url_das_imagens": _url_das_imagens(),
    }
    contexto.update(extra or {})
    return contexto


def _onde_esta_em_uso(imagem, excluir_parceiro=None):
    """
    Onde esta imagem está sendo usada, em português.

    Quem vai apagar precisa saber o que vai quebrar ANTES de tentar --
    e, quando o banco recusar, precisa entender por quê. As duas
    primeiras são as que o PROTECT defende; as outras duas somem
    sozinhas (SET_NULL) e por isso são aviso, não impedimento.

    `excluir_parceiro`: quando a pergunta é "sobra alguma referência
    DEPOIS de apagar ESTE parceiro" (a tela de confirmação, Bloco D) --
    o parceiro ainda existe no banco neste momento, e contaria como uso
    dele mesmo se fosse a única referência.
    """
    usos = []
    if imagem.referenciado_por_carta_finalizada():
        usos.append(_("uma carta já finalizada"))
    if imagem.referenciado_por_modelo():
        usos.append(_("um modelo de documento"))
    if imagem.page_sections.exists():
        usos.append(_("uma parte da página inicial"))
    parceiros = imagem.partners.all()
    if excluir_parceiro is not None:
        parceiros = parceiros.exclude(pk=excluir_parceiro.pk)
    if parceiros.exists():
        usos.append(_("um parceiro"))
    if imagem.language_flags.exists():
        usos.append(_("a bandeira de um idioma"))
    return usos


def _apagar_asset_se_orfao(imagem):
    """
    Apaga o `Asset` -- arquivo incluído -- SE nada mais o referenciar.

    Reusa `_onde_esta_em_uso`: a MESMA verificação que decide se a
    Biblioteca oferece o botão de apagar decide, aqui, se um upload
    contextual (Bloco D) pode limpar a imagem que acabou de deixar de
    usar. Chamar isto depois de já ter aplicado a nova associação --
    nunca antes -- é o que garante que "nada mais usa" reflita o estado
    de VERDADE, não o de um instante atrás.

    Nunca apaga uma imagem com `key`: essas são as fixas que o próprio
    código localiza por nome (logotipo, favicon) -- perdê-las por
    engano não é o tipo de "órfã" que este upload contextual cria.
    """
    if imagem is None or imagem.key:
        return
    if _onde_esta_em_uso(imagem):
        return
    imagem.file.delete(save=False)
    imagem.delete()


@exige_permissao(VER_IMAGEM)
def backoffice_assets(request):
    """
    A biblioteca de imagens do site.

    Toda imagem administrável do projeto mora aqui: logotipo, favicon,
    banner, marca de parceiro. Não há `ImageField` espalhado pelos
    modelos -- quem precisa de imagem aponta para cá.
    """
    imagens = Asset.objects.prefetch_related(
        "page_sections",
        "partners",
        "letter_references",
        "template_references",
        "language_flags",
    )
    linhas = [{"imagem": imagem, "usos": _onde_esta_em_uso(imagem)} for imagem in imagens]

    return render(
        request,
        "backoffice/assets.html",
        _contexto_de_imagens(request, {"linhas": linhas}),
    )


@exige_permissao(CRIAR_IMAGEM)
def backoffice_asset_new(request):
    """Envia uma imagem para a biblioteca."""
    if request.method == "POST":
        form = FormularioDeImagem(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, _("Imagem enviada."))
            return redirect(_url_das_imagens())
        messages.error(request, _("Corrija os campos destacados antes de enviar."))
    else:
        form = FormularioDeImagem()

    return render(
        request,
        "backoffice/asset_form.html",
        _contexto_de_imagens(
            request,
            {"form": form, "imagem": None, "titulo": _("Nova imagem"), "pode_salvar": True},
        ),
    )


@exige_permissao(VER_IMAGEM)
def backoffice_asset_edit(request, pk):
    """
    Altera uma imagem.

    TROCAR O ARQUIVO PODE SER RECUSADO
    ----------------------------------
    `Asset.save()` levanta `AssetFileImmutableError` quando uma carta já
    finalizada depende daquele arquivo -- trocá-lo mudaria um documento
    histórico em silêncio. Aqui isso vira erro de formulário, não erro
    500: é uma regra do produto, e quem administra tem de LER a razão.
    """
    imagem = get_object_or_404(Asset, pk=pk)
    pode_salvar = request.user.has_perm(EDITAR_IMAGEM)

    if request.method == "POST":
        if not pode_salvar:
            raise PermissionDenied
        form = FormularioDeImagem(request.POST, request.FILES, instance=imagem)
        if form.is_valid():
            try:
                form.save()
            except AssetFileImmutableError as recusa:
                form.add_error("file", str(recusa))
            else:
                messages.success(request, _("Imagem salva."))
                return redirect(_url_das_imagens())
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = FormularioDeImagem(instance=imagem)

    return render(
        request,
        "backoffice/asset_form.html",
        _contexto_de_imagens(
            request,
            {
                "form": form,
                "imagem": imagem,
                "titulo": str(imagem),
                "pode_salvar": pode_salvar,
                "usos": _onde_esta_em_uso(imagem),
            },
        ),
    )


@exige_permissao(EDITAR_IMAGEM)
@require_POST
def backoffice_asset_activation(request, pk):
    """
    Liga e desliga uma imagem.

    Desligada, ela deixa de ser OFERECIDA para novas escolhas -- mas
    continua aparecendo onde já foi escolhida. Tirar do ar o que já está
    publicado é decisão de cada tela, não desta.
    """
    imagem = get_object_or_404(Asset, pk=pk)
    imagem.is_active = request.POST.get("ativa") == "1"
    imagem.save(update_fields=["is_active", "updated_at"])

    if imagem.is_active:
        messages.success(request, _("Imagem ativada."))
    else:
        messages.success(
            request, _("Imagem desativada. Deixa de ser oferecida para novas escolhas.")
        )
    return redirect(_url_das_imagens())


@exige_permissao(EXCLUIR_IMAGEM)
def backoffice_asset_delete(request, pk):
    """
    Apaga uma imagem, depois de confirmar.

    O banco tem a última palavra: `ProtectedError` quando um modelo ou
    uma carta finalizada dependem dela. A tela avisa antes, e explica
    depois -- mas quem recusa é o PROTECT, não o aviso.
    """
    imagem = get_object_or_404(Asset, pk=pk)

    if request.method == "POST":
        nome = str(imagem)
        try:
            imagem.delete()
        except ProtectedError:
            messages.error(
                request,
                _(
                    "Esta imagem não pode ser apagada: um modelo de documento ou uma "
                    "carta já finalizada depende dela. Desative-a para não ser mais "
                    "oferecida."
                ),
            )
            return redirect(_url_das_imagens())
        messages.success(request, _("Imagem removida: %(nome)s.") % {"nome": nome})
        return redirect(_url_das_imagens())

    return render(
        request,
        "backoffice/asset_delete.html",
        _contexto_de_imagens(
            request, {"imagem": imagem, "usos": _onde_esta_em_uso(imagem)}
        ),
    )


# ---------------------------------------------------------------------------
# Perguntas frequentes
# ---------------------------------------------------------------------------
#
# A tela delas é o editor da seção "faq" (ver `cadastro="faq"` em
# `section_schema`), então toda ação volta para lá -- mesma forma dos
# itens do menu, e pela mesma razão: título e chamada da seção são texto
# da seção, e as perguntas são cadastro.


def _url_do_faq(idioma=None):
    secao = PageSection.objects.filter(page__key=CHAVE_DA_HOME, key="faq").first()
    if secao is None:
        return _url_da_lista(idioma or settings.LANGUAGE_CODE)
    url = reverse("backoffice:content_section", args=[secao.pk])
    return f"{url}?idioma={idioma}" if idioma else url


def _contexto_da_pergunta(request, form, pergunta, titulo):
    return {
        "active": "content",
        "bo_title": _("Home - Configurações"),
        "form": form,
        "pergunta": pergunta,
        "titulo": titulo,
        "url_do_faq": _url_do_faq(idioma_pedido(request)),
    }


@exige_permissao(EDITAR_PERM)
def backoffice_faq_item_new(request):
    """Acrescenta uma pergunta à seção."""
    if request.method == "POST":
        form = FormularioDePergunta(request.POST)
        if form.is_valid():
            pergunta = form.save()
            messages.success(
                request,
                _("Pergunta acrescentada: %(texto)s.") % {"texto": pergunta.question},
            )
            return redirect(_url_do_faq(idioma_pedido(request)))
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = FormularioDePergunta()

    return render(
        request,
        "backoffice/faq_item_form.html",
        _contexto_da_pergunta(request, form, None, _("Nova pergunta")),
    )


@exige_permissao(VER_PERM)
def backoffice_faq_item_edit(request, pk):
    """
    Altera uma pergunta.

    VER abre a tela; GRAVAR exige `change_pagesection` -- e a checagem do
    POST é aqui, no servidor, não no botão.
    """
    pergunta = get_object_or_404(FaqItem, pk=pk)

    if request.method == "POST":
        if not request.user.has_perm(EDITAR_PERM):
            raise PermissionDenied
        form = FormularioDePergunta(request.POST, instance=pergunta)
        if form.is_valid():
            form.save()
            messages.success(request, _("Pergunta salva."))
            return redirect(_url_do_faq(idioma_pedido(request)))
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = FormularioDePergunta(instance=pergunta)

    return render(
        request,
        "backoffice/faq_item_form.html",
        _contexto_da_pergunta(request, form, pergunta, pergunta.question),
    )


@exige_permissao(EDITAR_PERM)
@require_POST
def backoffice_faq_item_activation(request, pk):
    """Liga e desliga uma pergunta. Desligada, some da Home -- sem apagar nada."""
    pergunta = get_object_or_404(FaqItem, pk=pk)
    pergunta.is_active = request.POST.get("ativo") == "1"
    pergunta.save(update_fields=["is_active", "updated_at"])

    if pergunta.is_active:
        messages.success(request, _("Pergunta ativada. Volta a aparecer na página."))
    else:
        messages.success(request, _("Pergunta desativada. Deixa de aparecer na página."))
    return redirect(_url_do_faq(idioma_pedido(request)))


@exige_permissao(EDITAR_PERM)
@require_POST
def backoffice_faq_item_move(request, pk):
    """Sobe ou desce uma pergunta na lista."""
    pergunta = get_object_or_404(FaqItem, pk=pk)
    if _reordenar(FaqItem, pergunta, request.POST.get("direcao")):
        messages.success(request, _("Ordem atualizada."))
    return redirect(_url_do_faq(idioma_pedido(request)))


@exige_permissao(EDITAR_PERM)
def backoffice_faq_item_delete(request, pk):
    """
    Apaga uma pergunta, depois de confirmar.

    Aqui SE PERDE TEXTO -- a resposta inteira --, e por isso a tela de
    confirmação mostra a resposta antes de perguntar. Quem só quer tirar
    a pergunta do ar tem o botão de desativar, que não apaga nada.
    """
    pergunta = get_object_or_404(FaqItem, pk=pk)

    if request.method == "POST":
        texto = pergunta.question
        pergunta.delete()
        messages.success(request, _("Pergunta removida: %(texto)s.") % {"texto": texto})
        return redirect(_url_do_faq(idioma_pedido(request)))

    return render(
        request,
        "backoffice/faq_item_delete.html",
        {
            "active": "content",
            "bo_title": _("Home - Configurações"),
            "pergunta": pergunta,
            "url_do_faq": _url_do_faq(idioma_pedido(request)),
        },
    )


# ---------------------------------------------------------------------------
# Documentos legais (Sistema › Documentos legais › Termos de uso/Privacidade)
# ---------------------------------------------------------------------------
#
# Os MESMOS dois blocos de sempre (`legal.terms_of_use`,
# `legal.privacy_policy`) e as MESMAS rotas públicas. O que mudou foi
# onde se escreve: até a Rodada 15, texto simples no Django Admin; desde
# então, um editor de conteúdo rico -- só que combinado, com os dois
# documentos e os dois modos (ver/editar) na MESMA tela, por seletores.
#
# DUAS ROTAS POR DOCUMENTO (Rodada 21)
# -------------------------------------
# Cada documento passa a ter a sua PRÓPRIA rota de visualização e a sua
# PRÓPRIA rota de edição -- nunca os dois documentos juntos, nunca ver e
# editar na mesma tela. A VISUALIZAÇÃO mostra o documento exatamente
# como a página pública o renderiza -- nunca o HTML cru, nunca os
# controles do editor --, com um botão "Editar" para quem tiver
# permissão. É a mesma separação leitura/escrita que a biblioteca de
# modelos já usa (o detalhe do modelo e o editor são telas distintas).
#
# QUATRO ROTAS, DOIS HELPERS
# ---------------------------
# `backoffice_legal_terms`/`_privacy` (ver) e `_terms_edit`/`_privacy_edit`
# (editar) são wrappers finos: cada um fixa o SLUG do seu documento e
# chama o helper que faz o trabalho de verdade
# (`_ver_documento_legal`/`_editar_documento_legal`). Não há mais um
# "documento pedido" na querystring -- a rota já diz qual é.
#
# PERMISSÃO
# ---------
# Ver: `content.view_contentblock`; editar: `content.change_contentblock`
# -- as MESMAS que o Django Admin já cobrava destes blocos, agora
# aplicadas por ROTA: quem só tem a de ver nunca alcança a de editar
# (403 direto do decorador, sem precisar de um `if` dentro da view).

VER_DOCUMENTOS_PERM = "content.view_contentblock"
EDITAR_DOCUMENTOS_PERM = "content.change_contentblock"

# O slug de cada documento e a rota pública dele -- os slugs são os de
# `services.PAGINAS_LEGAIS`, a única lista dos documentos.
ROTA_PUBLICA_DO_DOCUMENTO = {
    "termos-de-uso": "core:legal_termos",
    "privacidade": "core:legal_privacidade",
}

# As rotas do Backoffice de cada documento, e o `active` que destaca o
# item certo no menu (e mantém "Sistema" e "Documentos legais"
# expandidos -- ver `backoffice/menu.html`).
ROTA_VER_DO_DOCUMENTO = {
    "termos-de-uso": "backoffice:legal_documents_terms",
    "privacidade": "backoffice:legal_documents_privacy",
}
ROTA_EDITAR_DO_DOCUMENTO = {
    "termos-de-uso": "backoffice:legal_documents_terms_edit",
    "privacidade": "backoffice:legal_documents_privacy_edit",
}
# A prévia ao vivo (Rodada 22) -- a aba "Visualizar" do editor por
# blocos, num `<iframe>`, a mesma técnica de `backoffice_content_preview`.
ROTA_PREVIA_DO_DOCUMENTO = {
    "termos-de-uso": "backoffice:legal_documents_terms_preview",
    "privacidade": "backoffice:legal_documents_privacy_preview",
}
ACTIVE_DO_DOCUMENTO = {
    "termos-de-uso": "legal_documents_terms",
    "privacidade": "legal_documents_privacy",
}


def _documento_fixo(slug):
    """A chave e o título de `slug` -- de `services.PAGINAS_LEGAIS`, a lista dos documentos."""
    for outro_slug, chave, titulo in services.PAGINAS_LEGAIS:
        if outro_slug == slug:
            return chave, titulo
    raise Http404(f"documento legal desconhecido: {slug}")


def _imagens_para_o_documento():
    """
    As imagens que o editor oferece: as ATIVAS da biblioteca, menos o
    favicon (que não é imagem de ler). Só da biblioteca -- é a única
    origem que o sanitizador aceita num documento.
    """
    return [
        {"url": imagem.file.url, "alt": imagem.alt_text, "nome": imagem.alt_text or imagem.key}
        for imagem in Asset.objects.filter(is_active=True)
        .exclude(kind=Asset.Kind.FAVICON)
        .exclude(file="")[:100]
    ]


def _ver_documento_legal(request, slug):
    """
    A visualização de UM documento: como a página pública o desenha,
    num idioma -- nunca o HTML cru, nunca os controles do editor.

    Quem também tem `EDITAR_DOCUMENTOS_PERM` ganha o botão "Editar", que
    leva à edição deste MESMO documento. Quem não tem, só consulta.
    """
    chave, titulo = _documento_fixo(slug)
    idioma = idioma_pedido(request)
    pode_editar = request.user.has_perm(EDITAR_DOCUMENTOS_PERM)

    bloco = ContentBlock.objects.filter(key=chave).first()
    traducao = (
        ContentTranslation.objects.filter(block=bloco, language=idioma).first() if bloco else None
    )
    publicadas = services.legais_publicadas()

    return render(
        request,
        "backoffice/legal_document_view.html",
        {
            "active": ACTIVE_DO_DOCUMENTO[slug],
            "bo_title": titulo,
            "pode_editar": pode_editar,
            "documento": {"slug": slug, "titulo": titulo},
            "idioma": idioma,
            "idiomas": idiomas_disponiveis(idioma),
            "e_o_idioma_padrao": idioma == settings.LANGUAGE_CODE,
            "bloco": bloco,
            "traducao": traducao,
            "tem_texto_no_idioma": bool(traducao and (traducao.content or "").strip()),
            "publicado": chave in publicadas,
            "url_publica": reverse(ROTA_PUBLICA_DO_DOCUMENTO[slug]),
            "url_editar": reverse(ROTA_EDITAR_DO_DOCUMENTO[slug]) if pode_editar else "",
            # Sempre calculada -- é o que esta tela existe para mostrar,
            # tenha ou não permissão de editar (ver docstring do módulo).
            "previa": rodape.renderizar_documento_em_blocos(
                services.blocos_do_documento(chave, idioma)
            ),
        },
    )


def _editar_documento_legal(request, slug):
    """
    A edição de UM documento: o editor por BLOCOS (Rodada 22), num
    idioma.

    Abrir o editor não muda nada: os blocos de hoje são mostrados já
    prontos para editar (convertidos na hora, se ainda estiverem no
    formato de antes -- ver `services.blocos_do_documento`). Só SALVAR
    grava -- e aí o documento passa a "Blocos estruturados" (ver
    `services.salvar_blocos_do_documento`). Depois de salvar, a tela
    volta a si mesma: quem está ajustando o documento continua no
    editor, não é jogado para a visualização.

    O QUE VEM NO POST
    ------------------
    Um campo só, `blocos`: o JSON da lista inteira, montado pelo
    JavaScript do editor (`editor-blocos.js`) a partir do que está no
    quadro -- a ORDEM da lista É a ordem dos blocos, então reordenar
    (arrastar) é só mandar a lista na ordem nova. Um JSON inválido é
    tratado como lista vazia -- o mesmo "documento sem texto" de um
    editor esvaziado, nunca um erro de servidor.
    """
    chave, titulo = _documento_fixo(slug)
    idioma = idioma_pedido(request)
    endereco = f"{reverse(ROTA_EDITAR_DO_DOCUMENTO[slug])}?idioma={idioma}"

    if request.method == "POST":
        try:
            blocos_brutos = json.loads(request.POST.get("blocos") or "[]")
        except ValueError:
            blocos_brutos = []
        gravado = services.salvar_blocos_do_documento(chave, idioma, blocos_brutos)
        if gravado:
            messages.success(request, _("%(documento)s salvo.") % {"documento": titulo})
        else:
            messages.warning(
                request,
                _(
                    "%(documento)s salvo sem conteúdo neste idioma. Sem conteúdo em "
                    "nenhum idioma, a página sai do ar e os links para ela somem."
                )
                % {"documento": titulo},
            )
        return redirect(endereco)

    blocos_iniciais = services.blocos_do_documento(chave, idioma)
    publicadas = services.legais_publicadas()

    return render(
        request,
        "backoffice/legal_document_edit.html",
        {
            "active": ACTIVE_DO_DOCUMENTO[slug],
            "bo_title": _("Editar: %(documento)s") % {"documento": titulo},
            "documento": {"slug": slug, "titulo": titulo},
            "idioma": idioma,
            "idiomas": idiomas_disponiveis(idioma),
            "e_o_idioma_padrao": idioma == settings.LANGUAGE_CODE,
            "publicado": chave in publicadas,
            "url_publica": reverse(ROTA_PUBLICA_DO_DOCUMENTO[slug]),
            "url_ver": reverse(ROTA_VER_DO_DOCUMENTO[slug]),
            "url_previa": reverse(ROTA_PREVIA_DO_DOCUMENTO[slug]),
            "blocos_json": blocos_iniciais,
            "catalogo_de_blocos": blocos_svc.catalogo_para_o_menu(),
            "imagens": _imagens_para_o_documento(),
        },
    )


def _preview_documento_legal(request, slug):
    """
    A aba "Visualizar" de UM documento -- a MESMA prévia de
    `backoffice_content_preview`: código real, num `<iframe>` próprio.

    GET mostra o que está GRAVADO (o quadro abre a aba Visualizar sem
    ter digitado nada ainda). POST mostra o que está no FORMULÁRIO,
    ainda não salvo -- é como `editor-blocos.js` atualiza a prévia a
    cada alternância de aba, sem gravar nada.
    """
    chave, titulo = _documento_fixo(slug)
    idioma = idioma_pedido(request)

    if request.method == "POST":
        try:
            blocos_brutos = json.loads(request.POST.get("blocos") or "[]")
        except ValueError:
            blocos_brutos = []
        lista = blocos_svc.sanitizar_blocos(blocos_brutos)
    else:
        lista = services.blocos_do_documento(chave, idioma)

    return render(
        request,
        "backoffice/legal_document_preview.html",
        {
            "titulo": titulo,
            "previa": rodape.renderizar_documento_em_blocos(lista),
            "viewport": _viewport_pedido(request),
        },
    )


@exige_permissao(VER_DOCUMENTOS_PERM)
def backoffice_legal_terms(request):
    return _ver_documento_legal(request, "termos-de-uso")


@exige_permissao(EDITAR_DOCUMENTOS_PERM)
def backoffice_legal_terms_edit(request):
    return _editar_documento_legal(request, "termos-de-uso")


@exige_permissao(EDITAR_DOCUMENTOS_PERM)
@xframe_options_sameorigin
def backoffice_legal_terms_preview(request):
    return _preview_documento_legal(request, "termos-de-uso")


@exige_permissao(VER_DOCUMENTOS_PERM)
def backoffice_legal_privacy(request):
    return _ver_documento_legal(request, "privacidade")


@exige_permissao(EDITAR_DOCUMENTOS_PERM)
def backoffice_legal_privacy_edit(request):
    return _editar_documento_legal(request, "privacidade")


@exige_permissao(EDITAR_DOCUMENTOS_PERM)
@xframe_options_sameorigin
def backoffice_legal_privacy_preview(request):
    return _preview_documento_legal(request, "privacidade")
