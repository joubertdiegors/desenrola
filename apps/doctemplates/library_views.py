"""
Biblioteca de modelos: a gestão administrativa dos `DocumentTemplate`.

    GET  backoffice/modelos/                 a listagem
    GET  backoffice/modelos/<pk>/            o detalhe de um modelo
    POST backoffice/modelos/<pk>/duplicar/   cria uma cópia independente
    POST backoffice/modelos/<pk>/situacao/   ativa ou desativa

Arquivo PRÓPRIO, separado de `editor_views.py` (o editor em si). É a
única biblioteca de modelos do produto.

DUAS PERMISSÕES, AMBAS JÁ EXISTENTES
------------------------------------
`doctemplates.view_documenttemplate` para VER a biblioteca;
`doctemplates.change_documenttemplate` para ADMINISTRAR (duplicar,
ativar/desativar, editar no editor). As duas são as permissões que o
Django cria sozinho para o modelo -- não foi preciso inventar
`manage_templates`: elas já dizem exatamente isso, e reusá-las evita uma
segunda linguagem de permissão para o mesmo assunto.

A migration `doctemplates.0016` concedeu ambas a quem já tinha
`core.access_backoffice`, para a atualização não trancar ninguém fora de
uma tela que já usava.

NÃO EXISTE EXCLUSÃO
-------------------
A biblioteca não apaga modelo nenhum -- nem comum, nem cópia. Um modelo
pode ter cartas apontando para ele (`Letter.document_template`, PROTECT)
e, mesmo sem nenhuma, sumir com um registro é irreversível onde
desativar resolve: o modelo sai das opções de carta nova e todo o
histórico continua reproduzível.

O QUE ESTA VIEW NÃO DECIDE
--------------------------
Quem pode ser editado é `editor_views._pode_editar`; o que um modelo
travado ou oficial aceita mudar é `DocumentTemplate.save()`; como se
duplica é `services.duplicacao`. Esta camada só apresenta e chama.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from apps.core import filtros
from apps.core.views import exige_permissao

from .models import DocumentTemplate, DocumentTemplateLockedError, DocumentType
from .services import ativacao
from .services.duplicacao import duplicar_modelo

# As duas permissões desta seção. Constantes, e não strings soltas por
# view e template, para o dia em que alguém procurar "quem decide isto".
VER_PERM = "doctemplates.view_documenttemplate"
ADMINISTRAR_PERM = "doctemplates.change_documenttemplate"

POR_PAGINA = 25


def _contexto_do_backoffice(titulo):
    """A casca administrativa. Sem `bo_action_*`: estas telas não têm uma
    ação única de cabeçalho, e o botão do celular só aparece quando há
    uma de verdade (ver `backoffice/base.html`)."""
    return {"active": "templates", "bo_title": titulo}


def pode_administrar(user):
    """Quem pode duplicar, ativar/desativar e salvar no editor."""
    return user.has_perm(ADMINISTRAR_PERM)


# ---------------------------------------------------------------------------
# Listagem
# ---------------------------------------------------------------------------


def _url_de_filtro(request, **mudancas):
    """
    A URL desta mesma tela com alguns filtros trocados e o RESTO
    preservado.

    Os filtros da barra são links, não um formulário com botão: clicar
    em "Inativos" tem de manter a busca e o idioma que já estavam lá, e
    tem de funcionar sem JavaScript. Montar a querystring no servidor é o
    que permite as duas coisas -- o template só escreve o endereço pronto.

    A regra mora em `apps.core.filtros`, compartilhada com as tabelas de
    Usuários e de Cartas, que usam a mesma barra.
    """
    return filtros.url_de_filtro(request, "backoffice:document_library", **mudancas)


def _quando(momento):
    """
    "hoje", "ontem", "há 3 dias" -- UMA unidade.

    `timesince` do Django devolve duas ("2 dias, 21 horas"), e numa
    coluna estreita isso vira duas linhas e nenhuma informação a mais:
    quem olha a lista quer saber se mexeram nisso hoje ou no mês
    passado.
    """
    from django.utils import timezone
    from django.utils.translation import ngettext

    if momento is None:
        return ""
    dias = (timezone.localdate() - timezone.localtime(momento).date()).days
    if dias <= 0:
        return _("hoje")
    if dias == 1:
        return _("ontem")
    if dias < 30:
        return ngettext("há %(n)d dia", "há %(n)d dias", dias) % {"n": dias}
    if dias < 365:
        meses = dias // 30
        return ngettext("há %(n)d mês", "há %(n)d meses", meses) % {"n": meses}
    anos = dias // 365
    return ngettext("há %(n)d ano", "há %(n)d anos", anos) % {"n": anos}


def _opcoes(request, parametro, atual, valores):
    """
    As opções de um filtro: rótulo, endereço e qual está valendo.

    `atual` é o valor em vigor; a opção que bate com ele ganha
    `atual=True`, e é ela que a barra mostra na pílula fechada.
    """
    return filtros.opcoes(request, "backoffice:document_library", parametro, atual, valores)


def _pilula(request, rotulo, parametro, atual, valores):
    """Uma pílula com menu: o rótulo, o valor em vigor e as opções."""
    return filtros.pilula(
        request, "backoffice:document_library", rotulo, parametro, atual, valores
    )


@exige_permissao(VER_PERM)
def document_library(request):
    """
    A biblioteca: todos os modelos, com o que cada um é e o que se pode
    fazer com ele.

    QUASE TUDO VAI PARA O BANCO
    ---------------------------
    Busca, tipo, idioma, natureza e a parte booleana da situação viram
    `WHERE`; `Count("letters")` e `Count("duplicates")` vêm na mesma
    consulta, em vez de uma por linha.

    A EXCEÇÃO É "RASCUNHO", e ela é honesta: separar um modelo ATIVO
    entre "pronto" e "rascunho" depende de as imagens do desenho
    existirem de fato (`ativacao.pronto_para_uso`), e isso é uma
    pergunta sobre outra tabela que não cabe num `WHERE` sobre JSON.
    Então os ativos são materializados, classificados com UMA consulta
    de assets para a lista toda (`ativacao.situacoes`) e só então
    paginados -- nunca uma consulta por linha, e nunca uma contagem de
    página que não bate com o que se vê.

    O QUE CADA LINHA LEVA
    ---------------------
    Situação em três estados, se tem desenho (é o que decide se há o
    que pré-visualizar), quantos elementos e quantos campos do banco o
    documento usa. Tudo calculado aqui: o template não percorre JSON.
    """
    from .layout_schema import referencias_usadas
    from .services import ativacao

    modelos = DocumentTemplate.objects.select_related(
        "type", "duplicated_from", "created_by"
    ).annotate(
        cartas=Count("letters", distinct=True),
        copias=Count("duplicates", distinct=True),
    )

    busca = (request.GET.get("q") or "").strip()
    if busca:
        modelos = modelos.filter(Q(name__icontains=busca) | Q(slug__icontains=busca))

    tipo_id = request.GET.get("type") or ""
    if tipo_id.isdigit():
        modelos = modelos.filter(type_id=int(tipo_id))

    idioma = request.GET.get("language") or ""
    if idioma:
        modelos = modelos.filter(language=idioma)

    # A situação do desenho (as três do rodapé da tabela). Valor
    # desconhecido não filtra nada: a lista volta inteira, e a barra
    # mostra "Todas" -- nunca uma tela vazia sem explicação.
    pedida = (request.GET.get("situacao") or "").strip()
    if pedida not in ativacao.SITUACOES:
        pedida = ""
    if pedida == ativacao.INATIVO:
        modelos = modelos.filter(is_active=False)
    elif pedida in (ativacao.ATIVO, ativacao.RASCUNHO):
        modelos = modelos.filter(is_active=True)

    origem = request.GET.get("system") or ""
    if origem in ("1", "0"):
        modelos = modelos.filter(is_system=(origem == "1"))

    modelos = modelos.order_by(
        "type__order", "type__name", "-is_system", "language", "name"
    )

    encontrados = list(modelos)
    situacoes = ativacao.situacoes(encontrados)
    if pedida in (ativacao.ATIVO, ativacao.RASCUNHO):
        encontrados = [m for m in encontrados if situacoes[m.pk] == pedida]

    for modelo in encontrados:
        layout = modelo.layout or {}
        modelo.situacao = situacoes[modelo.pk]
        modelo.tem_desenho = bool(layout.get("elements"))
        modelo.elementos = len(layout.get("elements") or [])
        modelo.campos = len(referencias_usadas(layout))
        modelo.versao = layout.get("version") or ""
        modelo.relativo = _quando(modelo.updated_at)

    pagina = Paginator(encontrados, POR_PAGINA).get_page(request.GET.get("page"))

    querystring = request.GET.copy()
    querystring.pop("page", None)

    ativos = sum(1 for m in encontrados if m.situacao == ativacao.ATIVO)
    ultima = max((m.updated_at for m in encontrados), default=None)

    contexto = _contexto_do_backoffice(_("Modelos de cartas"))
    contexto.update(
        {
            "pagina": pagina,
            "querystring": querystring.urlencode(),
            "modelos": pagina.object_list,
            "total": len(encontrados),
            "ativos": ativos,
            "ultima_alteracao": ultima,
            "pode_administrar": pode_administrar(request.user),
            "tipos": DocumentType.objects.order_by("order", "name"),
            "idiomas": DocumentTemplate._meta.get_field("language").choices,
            # Os modelos que servem de base para um modelo novo: o
            # caminho de criação do produto é duplicar um que já existe.
            "bases": [
                m for m in DocumentTemplate.objects.filter(is_system=True)
                .select_related("type")
                .order_by("type__order", "language")
            ],
            "filtros": {
                "q": busca,
                "type": tipo_id,
                "language": idioma,
                "situacao": pedida,
                "system": origem,
            },
            "tem_filtro": bool(busca or tipo_id or idioma or pedida or origem),
            # Os filtros já montados -- rótulo, endereço e qual está
            # valendo. Assim o template percorre uma lista em vez de
            # procurar chave por chave, e quem lê a tela vê a barra do
            # desenho sem template nenhum decidindo regra.
            "filtros_situacao": _opcoes(
                request,
                "situacao",
                pedida,
                (
                    ("", _("Todas")),
                    (ativacao.ATIVO, _("Ativos")),
                    (ativacao.INATIVO, _("Inativos")),
                    (ativacao.RASCUNHO, _("Rascunho")),
                ),
            ),
            # As duas pílulas com menu da barra: rótulo fixo, o valor
            # em vigor escrito ao lado e a lista para trocar.
            "filtros_pilula": [
                _pilula(
                    request,
                    _("Idioma"),
                    "language",
                    idioma,
                    (
                        ("", _("Todos")),
                        *DocumentTemplate._meta.get_field("language").choices,
                    ),
                ),
                _pilula(
                    request,
                    _("Natureza"),
                    "system",
                    origem,
                    (("", _("Todas")), ("1", _("Oficiais")), ("0", _("Personalizados"))),
                ),
            ],
            "url_limpar": reverse("backoffice:document_library"),
            "url_sem_busca": _url_de_filtro(request, q=""),
        }
    )
    return render(request, "backoffice/document_library.html", contexto)


@exige_permissao(VER_PERM)
@xframe_options_sameorigin
def document_preview(request, pk):
    """
    O PDF do modelo COMO ELE ESTÁ GRAVADO -- o que a janela "visualizar"
    da biblioteca mostra no `<iframe>`.

    `?exemplo=1` desenha com os valores de amostra
    (`services.dados_de_exemplo`); sem ele, os campos saem vazios, que é
    o que o modelo literalmente é antes de virar carta de alguém.

    DUAS PRÉVIAS, DUAS PERGUNTAS DIFERENTES
    ---------------------------------------
    Esta (GET, por id) responde "como está o modelo salvo?" e por isso
    serve a um `<iframe>`. A do editor (`template_editor_preview`, POST)
    responde "como ficaria o que estou editando agora?", e por isso
    recebe o layout no corpo. Nenhuma das duas grava nada.

    Quem pode VER a biblioteca pode ver isto: é o mesmo documento que a
    tela já descreve, com dados fictícios.

    POR QUE `xframe_options_sameorigin`
    -----------------------------------
    O site responde `X-Frame-Options: DENY` em tudo, e é assim que tem
    de continuar. Mas esta resposta é justamente a que a própria tela
    enquadra: com DENY o navegador recusa mostrá-la e a janela abre
    vazia. SAMEORIGIN libera só a própria aplicação -- nenhum outro
    site pode enquadrar o documento.
    """
    from .services import dados_de_exemplo
    from .services import pdf as servico_de_pdf

    modelo = get_object_or_404(DocumentTemplate.objects.select_related("type"), pk=pk)
    if not (modelo.layout or {}).get("elements"):
        # Sem desenho não há o que mostrar -- e a tela nem oferece o
        # botão. Chegar aqui é URL digitada à mão.
        raise Http404("Este modelo ainda não tem desenho.")

    dados = (
        dados_de_exemplo.para_o_editor(modelo.slug)
        if request.GET.get("exemplo") == "1"
        else {}
    )
    try:
        conteudo, _relatorio = servico_de_pdf.render_template(
            modelo, dados, estrito=False
        )
    except (
        servico_de_pdf.AssetAusenteError,
        servico_de_pdf.FonteIndisponivelError,
        servico_de_pdf.PaginaInvalidaError,
        ValidationError,
    ) as erro:
        # Um modelo que não desenha é exatamente o "Rascunho" da lista.
        # Dizer isso em texto é melhor do que um 500 dentro do iframe.
        return HttpResponse(
            _("Este modelo ainda não pode ser desenhado: %(motivo)s") % {"motivo": erro},
            content_type="text/plain; charset=utf-8",
            status=409,
        )

    resposta = HttpResponse(conteudo, content_type="application/pdf")
    resposta["Content-Disposition"] = f'inline; filename="{modelo.slug}.pdf"'
    return resposta


# ---------------------------------------------------------------------------
# Detalhe
# ---------------------------------------------------------------------------


@exige_permissao(VER_PERM)
def document_detail(request, pk):
    """
    Um modelo por inteiro: identidade, estrutura, origem e o que se pode
    fazer com ele.

    A leitura do LAYOUT (quantos elementos, de que tipos, que campos e
    que assets usa) é resumida aqui uma vez, em vez de o template
    percorrer JSON -- é o mesmo princípio das outras telas: a view
    entrega pronto, o template escolhe o que mostrar.
    """
    from .editor_views import _motivo_da_leitura, _pode_editar

    modelo = get_object_or_404(
        DocumentTemplate.objects.select_related("type", "duplicated_from", "created_by"),
        pk=pk,
    )

    # Quem esta em uso neste idioma agora. Serve para a tela dizer, ANTES
    # do clique, que ativar este aqui tira aquele do ar -- a troca e a
    # regra, e esconde-la seria a tela mentindo por omissao.
    em_uso = (
        ativacao.irmaos_do_mesmo_idioma(modelo).filter(is_active=True).first()
        if not modelo.is_active
        else None
    )

    contexto = _contexto_do_backoffice(modelo.name)
    contexto.update(
        {
            "modelo": modelo,
            "situacao": ativacao.situacao(modelo),
            "em_uso_no_idioma": em_uso,
            "estrutura": _resumo_da_estrutura(modelo),
            "assets": _assets_do_modelo(modelo),
            "copias": modelo.duplicates.order_by("name"),
            "cartas": modelo.letters.count(),
            "pode_administrar": pode_administrar(request.user),
            "editavel": _pode_editar(modelo),
            "motivo_da_leitura": _motivo_da_leitura(modelo),
        }
    )
    return render(request, "backoffice/document_detail.html", contexto)


def _resumo_da_estrutura(modelo):
    """
    O que o `layout` tem dentro, em números que uma pessoa entende.

    Os CAMPOS saem de `layout_schema.referencias_usadas()`, a mesma
    função que o renderer usa para montar o contexto do PDF -- e não
    de uma travessia própria daqui. A diferença não é teórica: um
    campo pode estar dentro da célula de uma tabela ou de um pedaço
    de `rich_text`, e uma leitura ingênua de `properties.content`
    deixaria de fora justamente os dados do convidado.
    """
    from .layout_schema import referencias_usadas

    layout = modelo.layout or {}
    elementos = layout.get("elements") or []

    tipos = {}
    for elemento in elementos:
        if not isinstance(elemento, dict):
            continue
        chave = elemento.get("type") or "?"
        tipos[chave] = tipos.get(chave, 0) + 1

    return {
        "elementos": len(elementos),
        "tipos": sorted(tipos.items()),
        "campos": sorted(referencias_usadas(layout)),
        "campos_do_formulario": len((modelo.field_schema or {}).get("fields") or []),
    }


def _assets_do_modelo(modelo):
    """
    Os `content.Asset` que o layout referencia, pela tabela de vínculos
    (`DocumentTemplateAsset`) -- que é derivada do layout a cada
    gravação, e é ela que protege o asset de ser apagado.
    """
    return [
        vinculo.asset
        for vinculo in modelo.asset_links.select_related("asset").order_by("asset__key")
    ]


# ---------------------------------------------------------------------------
# Ações
# ---------------------------------------------------------------------------


@exige_permissao(ADMINISTRAR_PERM)
@require_POST
def document_library_duplicate(request, pk):
    """
    Duplica um modelo -- oficial, comum, travado ou já duplicado, todos
    funcionam: é exatamente o que `duplicar_modelo()` garante.

    Este é o caminho de criação do produto: modelo oficial -> duplicar ->
    editar a cópia. Não há "criar modelo em branco", que começaria com
    uma página vazia e nenhum campo.

    A cópia nasce INATIVA: cada idioma tem um modelo em uso, e duplicar
    não pode trocar sozinho o documento da próxima carta (ver
    `services/ativacao.py`). Ativá-la é um clique à parte, e é ele que
    desativa o anterior.
    """
    origem = get_object_or_404(DocumentTemplate, pk=pk)
    nome = (request.POST.get("name") or "").strip()

    try:
        copia = duplicar_modelo(origem, nome, created_by=request.user)
    except ValidationError as erro:
        detalhe = " ".join(erro.messages) if hasattr(erro, "messages") else str(erro)
        messages.error(
            request,
            _('Não foi possível duplicar "%(origem)s": %(motivo)s')
            % {"origem": origem.name, "motivo": detalhe},
        )
        return redirect("backoffice:document_detail", pk=origem.pk)

    messages.success(
        request,
        _('"%(nome)s" criado a partir de "%(origem)s". A cópia já pode ser editada '
          'e entra em uso quando você a ativar.')
        % {"nome": copia.name, "origem": origem.name},
    )
    return redirect("backoffice:template_editor", pk=copia.pk)


@exige_permissao(ADMINISTRAR_PERM)
@require_POST
def document_library_activation(request, pk):
    """
    Ativa ou desativa um modelo. NUNCA apaga.

    ATIVAR É UMA TROCA
    ------------------
    Cada idioma tem UM modelo em uso. Ativar outro do mesmo idioma
    desativa o anterior no mesmo instante (`services.ativacao.ativar`),
    e a mensagem diz qual saiu -- um "ativado" que escondesse o
    "desativado" seria meia verdade sobre o documento que a próxima
    carta vai usar.

    Desativado, o modelo sai das opções de carta nova
    (`letters.services.active_document_template` devolve `None` quando o
    idioma fica sem nenhum ativo, e o assistente avisa em vez de
    estourar). As cartas já emitidas não sentem nada: elas renderizam do
    `document_snapshot` congelado, não do modelo.

    `is_active` é um dos três campos que até um modelo OFICIAL aceita
    mudar (`DocumentTemplate.SYSTEM_MUTABLE_FIELDS`) -- desativar um
    oficial é uma decisão administrativa legítima, e a guarda do modelo
    já a permite sem abrir mão do resto.

    VOLTA PARA ONDE SE CLICOU
    -------------------------
    O interruptor existe em duas telas (a biblioteca e o detalhe). O
    `voltar` do formulário diz de qual delas veio; sem ele, o padrão é
    o detalhe.
    """
    modelo = get_object_or_404(DocumentTemplate.objects.select_related("type"), pk=pk)
    ativar = request.POST.get("ativo") == "1"
    destino = (
        reverse("backoffice:document_library")
        if request.POST.get("voltar") == "biblioteca"
        else reverse("backoffice:document_detail", args=[modelo.pk])
    )

    try:
        mudou, desativados = ativacao.definir_situacao(modelo, ativar)
    except DocumentTemplateLockedError as erro:
        # A guarda do modelo é a autoridade; a tela só relata.
        messages.error(request, str(erro))
        return redirect(destino)

    if not mudou:
        messages.info(request, _("Nenhuma alteração a fazer."))
    elif not ativar:
        messages.success(
            request,
            _('"%(nome)s" foi desativado e não será usado em novas cartas.')
            % {"nome": modelo.name},
        )
    elif desativados:
        messages.success(
            request,
            _('"%(nome)s" passou a ser o modelo em uso para %(idioma)s; '
              '"%(anterior)s" foi desativado.')
            % {
                "nome": modelo.name,
                "idioma": modelo.get_language_display(),
                "anterior": ", ".join(m.name for m in desativados),
            },
        )
    else:
        messages.success(
            request,
            _('"%(nome)s" passou a ser o modelo em uso para %(idioma)s.')
            % {"nome": modelo.name, "idioma": modelo.get_language_display()},
        )
    return redirect(destino)


@exige_permissao(ADMINISTRAR_PERM)
@require_POST
def document_library_lock(request, pk):
    """
    Bloqueia um modelo DESTRAVADO -- a partir daqui, somente leitura.

    UMA VIA SÓ
    ----------
    Esta ação só liga o cadeado. Desligá-lo continua sendo uma decisão
    da administração (Django Admin) ou nascer destravado numa cópia --
    a mesma orientação que a leitura do editor já dá
    (`editor_views._motivo_da_leitura`): "destrave-o na administração ou
    duplique-o". Não há "Desbloquear" nesta tela.

    O FLUXO (Rodada 19 abriu a porta; esta rodada fecha o círculo)
    -----------------------------------------------------------------
    Desde a Rodada 19, um modelo destravado -- oficial ou não -- se
    edita direto no editor. O que faltava era encerrar o ajuste: abrir,
    editar, salvar e então bloquear, sem sair da tela nem depender do
    Django Admin. "Bloquear modelo" existe no editor (ao lado de
    "Salvar modelo") e aqui, no detalhe -- as DUAS telas onde a ação
    de travar/destravar já existe hoje (a de ativar/desativar é a
    mesma dupla). `voltar` diz para onde a resposta retorna.

    `is_locked` É CAMPO ADMINISTRATIVO SIMPLES
    ---------------------------------------------
    Ligar o cadeado nunca esbarra em `DocumentTemplateLockedError`: não
    está nem em `STRUCTURAL_FIELDS` (é o PRÓPRIO campo que essas regras
    olham) nem precisa estar em `SYSTEM_MUTABLE_FIELDS` para um oficial
    -- e está (`DocumentTemplate.SYSTEM_MUTABLE_FIELDS`). O `try` aqui
    é defensivo, não uma via que se espera abrir.
    """
    modelo = get_object_or_404(DocumentTemplate, pk=pk)
    destino = (
        reverse("backoffice:template_editor", args=[modelo.pk])
        if request.POST.get("voltar") == "editor"
        else reverse("backoffice:document_detail", args=[modelo.pk])
    )

    if modelo.is_locked:
        messages.info(request, _("Este modelo já está bloqueado."))
        return redirect(destino)

    modelo.is_locked = True
    try:
        modelo.save(update_fields=["is_locked", "updated_at"])
    except DocumentTemplateLockedError as erro:
        # A guarda do modelo é a autoridade; a tela só relata.
        messages.error(request, str(erro))
        return redirect(destino)

    messages.success(
        request,
        _('"%(nome)s" foi bloqueado. Para editar de novo, destrave-o na administração '
          'ou duplique-o.')
        % {"nome": modelo.name},
    )
    return redirect(destino)


def url_da_biblioteca():
    """Para o editor voltar para cá, e não para o Django Admin."""
    return reverse("backoffice:document_library")
