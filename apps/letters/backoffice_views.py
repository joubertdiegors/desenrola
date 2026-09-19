"""
Supervisão de cartas no Backoffice: a listagem real e o detalhe de uma
carta de qualquer usuário.

Arquivo PRÓPRIO, no app que tem o modelo -- mesma convenção de
`doctemplates/library_views.py`: a view mora junto do que ela lê, e só a
ROTA mora em `core/backoffice_urls.py`, porque a tela pertence ao
backoffice.

SOMENTE LEITURA
---------------
Nenhuma ação administrativa sobre a carta existe aqui: nem editar, nem
cancelar, nem regerar. Ter permissão de VER não é ter permissão de
mexer, e botão que não funciona é pior do que botão nenhum.

DUAS PERMISSÕES, NÃO UMA
------------------------
Entrar no Backoffice (`core.access_backoffice`) e ver as cartas de todo
mundo (`letters.view_all_letters`) são decisões separadas -- alguém pode
administrar modelos e conteúdo sem ter acesso aos documentos das
pessoas. `supervisao_de_cartas` exige as duas.

O ESTADO NÃO VEM DO BANCO
-------------------------
"Expirada" é derivado da política vigente e do instante atual
(`apps.letters.lifecycle`) -- não existe coluna para ele. Por isso o
filtro de estado e o de período da viagem rodam em Python, sobre os
cartões já montados, enquanto idioma e usuário (que SÃO colunas) filtram
no banco. A alternativa seria repetir a regra de prazo em SQL, que é
exatamente o que esta arquitetura evita.
"""

import datetime
from functools import wraps

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.core import exportacao_excel, filtros, paginacao
from apps.core.exportacao_excel import DATA, Coluna
from apps.core.forms import LetterNoticeForm
from apps.core.views import backoffice_required
from apps.letters import lifecycle, presentation, services
from apps.letters.models import LanguageFlag, Letter, LetterNotice

# Quantas cartas por página, por padrão; quem usa a tela escolhe entre
# `paginacao.TAMANHOS` (10, 20, 30, 50). A filtragem por estado acontece
# depois da consulta (ver o cabeçalho), então paginar aqui é o que impede
# a tela de crescer sem limite junto com o banco.
POR_PAGINA = paginacao.TAMANHO_PADRAO

# Os estados que o filtro oferece, na ordem em que fazem sentido para
# quem supervisiona. Os rótulos são os mesmos que a pessoa lê na etiqueta.
ESTADOS = [
    (lifecycle.RASCUNHO, _("Rascunho")),
    (lifecycle.FINALIZADA, _("Finalizada")),
    (lifecycle.EXPIRADA, _("Expirada")),
    (lifecycle.CANCELADA, _("Cancelada")),
]


def supervisao_de_cartas(view):
    """
    Exige entrar no Backoffice E `letters.view_all_letters`.

    Duas checagens porque são duas decisões: `backoffice_required` diz
    quem entra na área administrativa; esta segunda diz quem, lá dentro,
    pode ver documentos de outras pessoas. Superusuário passa pelas duas
    por como `has_perm` funciona.
    """

    @backoffice_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not lifecycle.supervisiona(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def _contexto_do_backoffice(active, titulo):
    """
    A casca da área administrativa (menu, cabeçalho).

    Sem `bo_action_*` de propósito: esta tela é real, e o botão do
    cabeçalho do celular só existe nas telas ilustrativas (ver
    `backoffice/base.html`). Havia um aqui, com o próprio título como
    rótulo, que não fazia nada -- os controles de verdade são os
    filtros, no corpo da tela.
    """
    return {
        "active": active,
        "bo_title": titulo,
    }


@supervisao_de_cartas
def backoffice_letters(request):
    """
    Todas as cartas do sistema, com o estado de cada uma.

    Filtros por querystring: `state`, `language`, `user` e o período da
    viagem (`from`/`to`, em ISO). Combináveis; vazio significa "sem
    filtro".

    BUSCA (`q`)
    -----------
    Referência, nome e e-mail de quem criou e nome do convidado -- no
    QUERYSET, junto com os filtros que o banco sabe fazer. O nome do
    convidado mora nos dados da carta: nos do rascunho (`data`) ou,
    depois de fechada, nos congelados (`snapshot.data`) -- a busca olha
    os dois, a mesma escolha de `lifecycle.dados_da_carta`.
    """
    cards, busca, idioma, usuario_id, estado, de, ate = _cartas_filtradas(request.GET)

    paginada = paginacao.paginar(request, cards, "backoffice:letters", POR_PAGINA)
    pagina = paginada["pagina"]

    # A querystring SEM o `page`, para os links de navegacao nao
    # acumularem um parametro a cada clique (?page=2&page=3&...).
    querystring = request.GET.copy()
    querystring.pop("page", None)

    usuarios = list(_usuarios_com_cartas())
    rota = "backoffice:letters"

    contexto = _contexto_do_backoffice("letters", _("Cartas"))
    contexto.update(
        {
            "pagina": pagina,
            "querystring": querystring.urlencode(),
            "cards": pagina.object_list,
            "total": pagina.paginator.count,
            "estados": ESTADOS,
            "idiomas": Letter._meta.get_field("language").choices,
            "usuarios": usuarios,
            "filtros": {
                "q": busca,
                "state": estado,
                "language": idioma,
                "user": usuario_id,
                "from": request.GET.get("from") or "",
                "to": request.GET.get("to") or "",
                "page_size": str(paginada["tamanho"]) if request.GET.get("page_size") else "",
            },
            # A barra do desenho de Modelos (`apps.core.filtros`): o
            # estado vira o seletor segmentado; idioma e usuario, pilulas
            # com menu. Cada opcao e um link que preserva os demais
            # filtros. O periodo da viagem continua sendo um formulario
            # (duas datas nao cabem num link).
            "filtros_estado": filtros.opcoes(
                request, rota, "state", estado, (("", _("Todos")), *ESTADOS)
            ),
            "filtros_pilula": [
                filtros.pilula(
                    request,
                    rota,
                    _("Idioma"),
                    "language",
                    idioma,
                    (("", _("Todos")), *Letter._meta.get_field("language").choices),
                ),
                filtros.pilula(
                    request,
                    rota,
                    _("Usuário"),
                    "user",
                    usuario_id if usuario_id.isdigit() else "",
                    (
                        ("", _("Todos")),
                        *(
                            (str(pessoa.pk), pessoa.full_name or pessoa.email)
                            for pessoa in usuarios
                        ),
                    ),
                ),
            ],
            "tem_filtro": bool(busca or estado or idioma or usuario_id or de or ate),
            "url_limpar": paginacao.url_sem_filtros(request, rota),
            "url_sem_busca": filtros.url_de_filtro(request, rota, q=""),
            "paginacao": paginada,
            "politica": lifecycle.policy(),
        }
    )
    return render(request, "backoffice/letters.html", contexto)


def _cartas_filtradas(parametros):
    """
    Os cartões da listagem com a busca e TODOS os filtros aplicados --
    ANTES da paginação. Devolve
    `(cards, busca, idioma, usuario_id, estado, de, ate)`.

    A tela chama com `request.GET` e pagina o resultado; a exportação
    para Excel chama com `request.POST` e leva o resultado inteiro. Uma
    filtragem só, para as duas nunca discordarem.
    """
    cartas = Letter.objects.select_related("user", "document_template").order_by("-created_at")

    busca = (parametros.get("q") or "").strip()
    if busca:
        cartas = cartas.filter(
            Q(reference__icontains=busca)
            | Q(user__full_name__icontains=busca)
            | Q(user__email__icontains=busca)
            | Q(data__guest_name__icontains=busca)
            | Q(snapshot__data__guest_name__icontains=busca)
        )

    # --- o que o banco sabe filtrar ---------------------------------------
    idioma = parametros.get("language") or ""
    if idioma:
        cartas = cartas.filter(language=idioma)

    usuario_id = parametros.get("user") or ""
    if usuario_id.isdigit():
        cartas = cartas.filter(user_id=int(usuario_id))

    # --- o que só o lifecycle sabe responder ------------------------------
    cards = presentation.build_cards(cartas)

    estado = parametros.get("state") or ""
    if estado:
        cards = [card for card in cards if card.state == estado]

    de = _data_iso(parametros.get("from"))
    ate = _data_iso(parametros.get("to"))
    if de:
        cards = [card for card in cards if card.arrival and card.arrival >= de]
    if ate:
        cards = [card for card in cards if card.arrival and card.arrival <= ate]

    return cards, busca, idioma, usuario_id, estado, de, ate


@supervisao_de_cartas
@require_POST
def backoffice_letters_export(request):
    """
    A listagem em .xlsx: a "Tabela completa" (as colunas da tela, sem
    Ações) ou os "Contatos".

    CONTATOS: nome, e-mail e telefone de quem CRIOU a carta -- a conta
    dona dela, a mesma pessoa da coluna "Criada por". É a única pessoa
    da carta que tem e-mail e telefone: o convidado tem nome, mas nenhum
    dos dois. Uma linha por carta; faltando um dado, a célula fica vazia.
    Nada é lido do snapshot nem gravado nele.

    As mesmas portas da listagem (`supervisao_de_cartas`): quem não vê as
    cartas de todo mundo não baixa a planilha. POST com o token CSRF, e a
    busca e os filtros chegam no corpo, não na URL. Sai o resultado
    INTEIRO: `page` e `page_size` não entram aqui.
    """
    tipo = request.POST.get("tipo") or ""
    if tipo not in ("completa", "contatos"):
        return HttpResponseBadRequest(_("Exportação desconhecida."))

    cards = _cartas_filtradas(request.POST)[0]

    if tipo == "contatos":
        colunas = exportacao_excel.colunas_de_contato()
        linhas = (
            (card.letter.user.full_name, card.letter.user.email, card.letter.user.phone)
            for card in cards
        )
        prefixo = "cartas_contatos"
    else:
        rotulos = dict(ESTADOS)
        colunas = [
            Coluna(_("Referência"), largura=26),
            Coluna(_("Criada por"), largura=30),
            Coluna(_("Para"), largura=30),
            Coluna(_("Idioma"), largura=14),
            Coluna(_("Data de ida"), DATA, 13),
            Coluna(_("Data de volta"), DATA, 14),
            Coluna(_("Status"), largura=12),
            Coluna(_("Criada em"), DATA, 13),
            Coluna(_("Finalizada em"), DATA, 15),
        ]
        linhas = (
            (
                card.reference,
                # Como a tabela mostra: o nome, ou o e-mail de quem não tem.
                card.letter.user.full_name or card.letter.user.email,
                card.guest_name,
                card.language_name if card.letter.language else "",
                card.arrival,
                card.departure,
                rotulos.get(card.state, ""),
                card.letter.created_at,
                card.letter.finalized_at,
            )
            for card in cards
        )
        prefixo = "cartas_tabela_completa"

    return exportacao_excel.resposta(colunas, linhas, prefixo, _("Cartas"))


@supervisao_de_cartas
def backoffice_letter_detail(request, letter_uuid):
    """
    Uma carta qualquer, vista por quem supervisiona -- inclusive de
    outro usuário e inclusive expirada.

    Somente leitura. O PDF, quando existe, continua saindo pela única
    porta que há (`letters:pdf`), que decide por conta própria quem pode
    obtê-lo (`lifecycle.can_user_download_pdf`) -- a regra não é
    reescrita aqui.
    """
    carta = (
        Letter.objects.select_related("user", "document_template", "document_template__type")
        .filter(uuid=letter_uuid)
        .first()
    )
    if carta is None:
        raise Http404("Carta não encontrada.")

    card = presentation.build_card(carta)
    contexto = _contexto_do_backoffice("letters", _("Carta"))
    contexto.update(
        {
            "card": card,
            "carta": carta,
            "dono": carta.user,
            "politica": lifecycle.policy(),
            "pode_baixar_pdf": lifecycle.can_user_download_pdf(request.user, carta),
            "revisao": _revisao_da_carta(carta),
        }
    )
    return render(request, "backoffice/letter_detail.html", contexto)


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


def _data_iso(valor):
    """Uma data vinda da querystring, ou None se ausente/ilegível."""
    if not valor:
        return None
    try:
        return datetime.date.fromisoformat(valor)
    except ValueError:
        return None


def _usuarios_com_cartas():
    """
    Só quem tem carta entra no seletor -- uma lista com todos os
    usuários do sistema não ajudaria a filtrar nada.
    """
    from django.contrib.auth import get_user_model

    return (
        get_user_model()
        .objects.filter(letters__isnull=False)
        .distinct()
        .order_by("full_name", "email")
    )


def _revisao_da_carta(carta):
    """
    Os dados preenchidos, agrupados por seção e já com os rótulos
    resolvidos -- o mesmo resumo que a pessoa vê na etapa 6 do
    assistente, montado por `services.grouped_review`.

    Reusar em vez de reescrever: os rótulos saem do `field_schema` do
    modelo, e uma segunda montagem aqui sairia do ar assim que o schema
    mudasse.
    """
    from apps.letters import services

    return services.grouped_review(carta)


# ---------------------------------------------------------------------------
# Declaracoes da etapa 4 do assistente
# ---------------------------------------------------------------------------
#
# A tela delas e a Politica das cartas (`backoffice/letter_policy.html`):
# as duas respondem a mesma pergunta -- "o que vale para TODAS as Cartas
# Convite" --, e uma tela nova no menu para dois textos seria uma porta a
# mais para o mesmo lugar. Toda acao volta para la.
#
# PERMISSAO
# ---------
# A mesma da politica (`letters.change_letterpolicy`): ver as regras que
# valem para todo mundo e uma coisa, muda-las e outra -- e quem pode
# mudar o prazo de expiracao e quem pode mudar o texto que o usuario
# aceita. A checagem e no servidor, em cada rota, nunca so no botao.


LETTER_POLICY_PERM = "letters.change_letterpolicy"


def _url_da_politica():
    return reverse("backoffice:letter_policy")


def exige_politica(view):
    """Backoffice + permissao de alterar a politica das cartas."""

    @wraps(view)
    @backoffice_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.has_perm(LETTER_POLICY_PERM):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return _wrapped


def declaracoes_com_pontas():
    """
    Cada declaracao sabendo se e a primeira ou a ultima -- e o que
    permite a tela nao desenhar "subir" no topo nem "descer" no fim.
    Mesma forma de `content.backoffice_views._linhas_com_pontas`.
    """
    itens = list(LetterNotice.objects.all())
    return [
        {"objeto": item, "primeiro": i == 0, "ultimo": i == len(itens) - 1}
        for i, item in enumerate(itens)
    ]


def _chave_disponivel(texto):
    """
    Uma `key` estavel a partir do texto, sem repetir uma que ja exista.

    A chave nasce do primeiro pedaco do texto so para ser legivel no
    banco e no `Letter.data`; ela NUNCA muda depois (o formulario nao a
    edita), entao reescrever a declaracao nao desliga o historico.
    """
    base = slugify(texto)[:48].strip("-") or "declaracao"
    chave = base
    sufixo = 2
    while LetterNotice.objects.filter(key=chave).exists():
        chave = f"{base[:52]}-{sufixo}"
        sufixo += 1
    return chave


@exige_politica
def backoffice_letter_notice_new(request):
    """Acrescenta uma declaracao a etapa 4."""
    if request.method == "POST":
        form = LetterNoticeForm(request.POST)
        if form.is_valid():
            declaracao = form.save(commit=False)
            declaracao.key = _chave_disponivel(declaracao.text)
            # Entra no fim da lista: quem acrescenta decide a posicao
            # depois, com as setas, em vez de a nova declaracao aparecer
            # no meio das que ja estavam.
            ultima = LetterNotice.objects.order_by("-order").first()
            declaracao.order = (ultima.order + 1) if ultima else 1
            declaracao.save()
            messages.success(request, _("Declaração acrescentada."))
            return redirect(_url_da_politica())
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = LetterNoticeForm()

    contexto = _contexto_do_backoffice("letter_policy", _("Wizzard - gerar carta"))
    contexto.update(
        {"form": form, "declaracao": None, "titulo": _("Nova declaração")}
    )
    return render(request, "backoffice/letter_notice_form.html", contexto)


@exige_politica
def backoffice_letter_notice_edit(request, pk):
    """Altera o texto (ou a situacao) de uma declaracao."""
    declaracao = get_object_or_404(LetterNotice, pk=pk)

    if request.method == "POST":
        form = LetterNoticeForm(request.POST, instance=declaracao)
        if form.is_valid():
            form.save()
            messages.success(request, _("Declaração salva."))
            return redirect(_url_da_politica())
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = LetterNoticeForm(instance=declaracao)

    contexto = _contexto_do_backoffice("letter_policy", _("Wizzard - gerar carta"))
    contexto.update(
        {"form": form, "declaracao": declaracao, "titulo": _("Editar declaração")}
    )
    return render(request, "backoffice/letter_notice_form.html", contexto)


@exige_politica
@require_POST
def backoffice_letter_notice_activation(request, pk):
    """
    Liga e desliga uma declaracao.

    Desligada, ela some da etapa 4 na hora -- e nao e apagada nem some
    das cartas que ja a aceitaram: `Letter.data` guarda a resposta pela
    chave, que continua existindo.
    """
    declaracao = get_object_or_404(LetterNotice, pk=pk)
    declaracao.is_active = request.POST.get("ativo") == "1"
    declaracao.save(update_fields=["is_active", "updated_at"])

    if declaracao.is_active:
        messages.success(request, _("Declaração ativada. Volta a aparecer na etapa 4."))
    else:
        messages.success(request, _("Declaração desativada. Deixa de aparecer na etapa 4."))
    return redirect(_url_da_politica())


@exige_politica
@require_POST
def backoffice_letter_notice_move(request, pk):
    """
    Sobe ou desce uma declaracao na etapa 4.

    Renumera pela POSICAO, e nao troca dois `order`: a ordem nasce igual
    para todo mundo e o desempate e o `pk` -- trocar o numero de dois
    empatados nao moveria ninguem, e o botao pareceria quebrado. Mesma
    razao (e mesma forma) de `content.backoffice_views._reordenar`.
    """
    declaracao = get_object_or_404(LetterNotice, pk=pk)
    ordenadas = list(LetterNotice.objects.all())
    atual = next((i for i, o in enumerate(ordenadas) if o.pk == declaracao.pk), None)
    if atual is None:
        return redirect(_url_da_politica())

    destino = atual - 1 if request.POST.get("direcao") == "subir" else atual + 1
    if 0 <= destino < len(ordenadas):
        ordenadas[atual], ordenadas[destino] = ordenadas[destino], ordenadas[atual]
        for posicao, item in enumerate(ordenadas, start=1):
            if item.order != posicao:
                item.order = posicao
                item.save(update_fields=["order", "updated_at"])
        messages.success(request, _("Ordem atualizada."))

    return redirect(_url_da_politica())


@exige_politica
def backoffice_letter_notice_delete(request, pk):
    """
    Apaga uma declaracao, depois de confirmar.

    GET pergunta; POST apaga. Para tirar da etapa 4 sem perder o texto o
    caminho e desativar, e a tela de confirmacao diz isso -- aqui SE
    PERDE o texto, e ele e juridico.
    """
    declaracao = get_object_or_404(LetterNotice, pk=pk)

    if request.method == "POST":
        declaracao.delete()
        messages.success(request, _("Declaração removida."))
        return redirect(_url_da_politica())

    contexto = _contexto_do_backoffice("letter_policy", _("Wizzard - gerar carta"))
    contexto.update({"declaracao": declaracao})
    return render(request, "backoffice/letter_notice_delete.html", contexto)


# ---------------------------------------------------------------------------
# Bandeiras dos idiomas do documento
# ---------------------------------------------------------------------------
#
# A tela delas e a de Idiomas (`backoffice/languages.html`): e la que se
# decide o que cada idioma e' no assistente, e a bandeira e a cara dele.
#
# O ENVIO REUSA A BIBLIOTECA DE IMAGENS
# -------------------------------------
# Nao ha sistema de imagens novo: o arquivo vira um `content.Asset`,
# com a MESMA validacao de formato e tamanho de todo upload do projeto
# (`content.forms._validar_arquivo_de_imagem`) e a MESMA limpeza de
# orfaos (`content.backoffice_views._apagar_asset_se_orfao`) que o
# upload direto de Parceiros e Banners usa.


DOCUMENT_LANGUAGES_PERM = "letters.change_documentlanguagesettings"


def _url_dos_idiomas():
    return reverse("backoffice:languages")


def exige_idiomas(view):
    """Backoffice + permissao de alterar os idiomas dos documentos."""

    @wraps(view)
    @backoffice_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.has_perm(DOCUMENT_LANGUAGES_PERM):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return _wrapped


def bandeiras_para_administrar():
    """
    Um item por idioma de `settings.LANGUAGES`, com a imagem cadastrada
    quando houver.

    A lista vem das CONFIGURACOES, nao da tabela: um idioma sem linha em
    `LanguageFlag` continua precisando aparecer na tela -- e' justamente
    nele que alguem vai querer enviar a primeira bandeira.
    """
    from django.conf import settings

    cadastradas = {b.language: b for b in LanguageFlag.objects.select_related("asset")}
    itens = []
    for codigo, _rotulo in settings.LANGUAGES:
        meta = services.LANGUAGE_META.get(codigo) or {}
        bandeira = cadastradas.get(codigo)
        itens.append(
            {
                "codigo": codigo,
                "nome": meta.get("name") or codigo,
                "classe": meta.get("flag") or "",
                "url": bandeira.url if bandeira else "",
            }
        )
    return itens


@exige_idiomas
@require_POST
def backoffice_language_flag(request, code):
    """
    Envia (ou remove) a bandeira de um idioma.

    O codigo vem da URL e e conferido contra `settings.LANGUAGES`: um
    idioma que o produto nao tem nao ganha bandeira por um POST montado
    a mao.

    Remover nao apaga a imagem cegamente -- `_apagar_asset_se_orfao`
    confere antes se mais alguem a usa, exatamente como no upload direto
    de Parceiros e Banners.
    """
    from django.conf import settings

    from apps.content.backoffice_views import _apagar_asset_se_orfao
    from apps.content.forms import _validar_arquivo_de_imagem
    from apps.content.models import Asset

    if code not in {codigo for codigo, _rotulo in settings.LANGUAGES}:
        raise Http404("idioma desconhecido")

    bandeira, _criada = LanguageFlag.objects.get_or_create(language=code)
    anterior = bandeira.asset

    if request.POST.get("remover") == "1":
        bandeira.asset = None
        bandeira.save(update_fields=["asset", "updated_at"])
        _apagar_asset_se_orfao(anterior)
        messages.success(request, _("Bandeira removida. Volta a bandeira padrão."))
        return redirect(_url_dos_idiomas())

    arquivo = request.FILES.get("bandeira")
    if not arquivo:
        messages.error(request, _("Escolha uma imagem para enviar."))
        return redirect(_url_dos_idiomas())

    formulario = forms.ImageField(required=True)
    try:
        # As duas conferencias, na ordem: o Pillow ABRE o arquivo (e
        # recusa o que nao for imagem de verdade, por mais que a
        # extensao diga o contrario), e depois valem tamanho e formato.
        arquivo = formulario.clean(arquivo)
        _validar_arquivo_de_imagem(arquivo)
    except ValidationError as erro:
        messages.error(request, erro.messages[0])
        return redirect(_url_dos_idiomas())

    bandeira.asset = Asset.objects.create(
        file=arquivo, kind=Asset.Kind.CONTENT, alt_text=f"{code}"
    )
    bandeira.save(update_fields=["asset", "updated_at"])
    if anterior and anterior.pk != bandeira.asset_id:
        _apagar_asset_se_orfao(anterior)

    messages.success(request, _("Bandeira atualizada."))
    return redirect(_url_dos_idiomas())
