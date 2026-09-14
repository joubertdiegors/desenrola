"""
Views de cartas.

`start`/`wizard_step` sao o assistente real (Fase 3): alimentado pelo
field_schema do DocumentTemplate oficial DO IDIOMA da
carta, persistido em Letter.data por etapa.

Criacao: `GET /letters/new/` so APRESENTA a primeira etapa — nao grava
nada. E o POST valido dessa tela que cria a Letter em rascunho. Assim
nenhum link, prefetch ou recarregamento cria carta por engano.

`detail`/`letter_pdf` sao a carta pronta: sempre pela UUID publica,
sempre so para o dono. O PDF nunca sai por midia estatica — `letter_pdf`
e a unica porta.
"""

import datetime
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.letters import lifecycle, presentation, services
from apps.letters.models import DefaultDocumentTemplateMissingError, Letter, LetterRenderError
from apps.letters.rules import MAX_STAY_DAYS, exceeds_max_stay, stay_duration_days

logger = logging.getLogger(__name__)

STEP_META = {
    1: {
        "title": _("1. Dados do convidado"),
        "hint": _("Preencha as informações da pessoa que será convidada."),
    },
    2: {
        "title": _("2. Período da viagem"),
        "hint": _("Informe as datas da viagem."),
    },
    3: {
        "title": _("3. Dados do anfitrião"),
        "hint": _(
            "Confirme os seus dados. A carta é sempre emitida em nome do "
            "titular da conta."
        ),
    },
    4: {
        "title": _("4. Avisos importantes"),
        "hint": _("Leia atentamente as informações abaixo."),
    },
    5: {
        "title": _("5. Escolha o idioma da Carta Convite"),
        "hint": _("Selecione o idioma em que o documento será gerado."),
    },
    6: {
        "title": _("6. Revise seu documento"),
        "hint": _(
            "Confira atentamente todas as informações antes de finalizar sua "
            "Carta Convite."
        ),
    },
}


DOCUMENT_UNAVAILABLE = _(
    "O documento oficial da Carta Convite ainda não está disponível neste idioma."
)

# As tres respostas do ciclo de vida (Etapa do ciclo de vida). Texto de
# produto, sem detalhe tecnico: a pessoa precisa saber o que pode fazer,
# nao por que o servidor recusou.
LETTER_NOT_EDITABLE = _("Esta carta não pode mais ser editada.")
LETTER_EXPIRED = _("Esta carta expirou e não pode mais ser aberta.")
LANGUAGE_LOCKED = _(
    "O idioma não pode mais ser alterado: o documento desta carta já foi emitido."
)


def _biblioteca_quebrada(request):
    """
    Resposta para `DefaultDocumentTemplateMissingError`: o modelo
    oficial do idioma nao existe ou esta inativo.

    E erro de INFRAESTRUTURA (biblioteca nao semeada, ou registro
    desativado por engano) -- diferente de "este idioma ainda nao tem
    documento pronto", que e o `DOCUMENT_UNAVAILABLE`. Por isso a
    pessoa recebe um aviso generico e a equipe recebe o traceback,
    em vez de um 500.

    So faz sentido chamada de dentro de um `except`: usa
    `logger.exception`.
    """
    logger.exception("Modelo estrutural oficial indisponível ao iniciar uma carta")
    messages.error(
        request,
        _("Não foi possível iniciar a Carta Convite agora. Nossa equipe foi avisada."),
    )
    return redirect("core:dashboard")


def _field_rows(fields, form):
    """As linhas que o template renderiza: tipo, layout e o campo ja ligado."""
    return [
        {
            "key": field_def["key"],
            "type": field_def["type"],
            "full_width": bool(field_def.get("full_width")),
            "bound": form[field_def["key"]],
        }
        for field_def in fields
    ]


@login_required
def start(request):
    """
    Gerar Carta Convite: apresenta a etapa 1 (GET) e cria o rascunho no
    envio (POST).

    O idioma inicial e sempre `services.IDIOMA_PADRAO_DA_CARTA` — uma
    decisao de produto, nao o idioma da interface (que e so portugues
    desde a Etapa 4.1). Ele decide qual documento oficial sera usado e
    pode ser trocado na etapa 5. Se aquele idioma ainda nao tem documento
    publicado, o fluxo para aqui com um aviso claro — nunca usa o
    documento de outro idioma no lugar.
    """
    language = services.IDIOMA_PADRAO_DA_CARTA
    try:
        document_template = services.official_document_template(language)
    except DefaultDocumentTemplateMissingError:
        return _biblioteca_quebrada(request)
    if document_template is None:
        messages.error(request, DOCUMENT_UNAVAILABLE)
        return redirect("core:dashboard")

    data = request.POST if request.method == "POST" else None
    form = services.form_for_new_letter(document_template, data=data)

    if request.method == "POST":
        if form.is_valid():
            try:
                letter = services.start_draft(request.user, language)
            except DefaultDocumentTemplateMissingError:
                # `start_draft` resolve o modelo de novo, por conta
                # propria (o cliente nunca manda um id). Entre a
                # resolucao la em cima e esta, alguem pode ter
                # desativado o registro: nenhuma Letter chega a
                # existir nesse caso -- nada para desfazer, so avisar.
                return _biblioteca_quebrada(request)
            if letter is None:
                messages.error(request, DOCUMENT_UNAVAILABLE)
                return redirect("core:dashboard")
            services.save_step_data(letter, services.FIRST_STEP, form.cleaned_data)
            return redirect("letters:step", letter_uuid=letter.uuid, step=2)
        messages.error(request, _("Corrija os campos destacados antes de continuar."))

    fields = services.fields_for_section_in(
        document_template.field_schema, services.STEP_SECTIONS[services.FIRST_STEP]
    )
    return render(
        request,
        "letters/wizard.html",
        {
            "step": services.FIRST_STEP,
            "steps": range(1, services.LAST_STEP + 1),
            "step_info": STEP_META[services.FIRST_STEP],
            "form": form,
            "field_rows": _field_rows(fields, form),
        },
    )


@login_required
def wizard_step(request, letter_uuid, step):
    """
    Uma etapa do assistente (1 a 6), identificada na URL.

    Ownership estrita: so o dono da carta acessa, mesmo que seja staff com
    `letters.view_all_letters` — essa permissao e so de visualizacao/
    supervisão (ver Letter.objects.visible_to()), nunca de edicao aqui.
    Uma URL de outro usuario, mesmo com UUID correto, sempre 404 (nunca
    revela se a carta existe).

    PRAZO DE EDICAO, NO SERVIDOR
    ----------------------------
    Rascunho edita sempre; carta finalizada, so enquanto a politica
    administrativa permitir (`lifecycle.is_letter_editable`). Fora do
    prazo a URL da etapa NAO abre -- esconder o botao no dashboard
    nunca foi protecao. A pessoa e devolvida ao detalhe da carta com
    um aviso, em vez de um 404 seco: a carta existe e e dela.
    """
    if step < 1 or step > services.LAST_STEP:
        raise Http404("Etapa inválida.")

    letter = services.get_owned_editable_letter(request.user, letter_uuid)
    if letter is None:
        propria = _get_own_letter(request.user, letter_uuid)
        if propria is None:
            raise Http404("Carta não encontrada.")
        messages.error(request, LETTER_NOT_EDITABLE)
        return redirect("letters:detail", letter_uuid=propria.uuid)

    # Voltar e livre; avancar so ate onde os dados sustentam. Isto e o
    # servidor decidindo -- digitar a URL da etapa 5 com a 2 incompleta
    # devolve a pessoa para a 2.
    bloqueio = services.blocking_step_before(letter, step)
    if bloqueio is not None:
        messages.error(request, _("Complete esta etapa antes de seguir adiante."))
        return redirect("letters:step", letter_uuid=letter.uuid, step=bloqueio)

    if step in services.STEP_SECTIONS:
        return _handle_form_step(request, letter, step)
    if step == services.LANGUAGE_STEP:
        return _handle_language_step(request, letter)
    return _handle_review_step(request, letter)


def _steps_context(letter, step):
    return {
        "letter": letter,
        "step": step,
        "steps": range(1, services.LAST_STEP + 1),
        "step_info": STEP_META[step],
        "reachable_steps": services.reachable_steps(letter),
    }


HOST_STEP = 3


def _handle_form_step(request, letter, step):
    data = request.POST if request.method == "POST" else None
    form = services.form_for_step(letter, step, data=data)

    # A etapa do anfitriao usa dados do PERFIL (nome, endereco, telefone,
    # nascimento, nacionalidade, documento). Faltando qualquer um deles,
    # nao ha o que preencher aqui nem carta possivel adiante -- entao a
    # etapa nao deixa avancar, e diz exatamente o que falta.
    #
    # Isto vale tambem no POST: tentar enviar a etapa direto, sem passar
    # pela tela, esbarra na mesma checagem.
    faltando = (
        services.missing_host_profile_fields(request.user) if step == HOST_STEP else []
    )
    if faltando and request.method == "POST":
        messages.error(
            request,
            _("Complete o seu perfil antes de continuar. Falta: %(campos)s.")
            % {"campos": ", ".join(str(item) for item in faltando)},
        )
        return redirect("letters:step", letter_uuid=letter.uuid, step=step)

    if request.method == "POST":
        if form.is_valid():
            services.save_step_data(letter, step, form.cleaned_data)
            next_step = min(step + 1, services.LAST_STEP)
            return redirect("letters:step", letter_uuid=letter.uuid, step=next_step)
        messages.error(request, _("Corrija os campos destacados antes de continuar."))

    context = _steps_context(letter, step)
    context["form"] = form
    context["field_rows"] = _field_rows(
        services.fields_for_section(letter, services.STEP_SECTIONS[step]), form
    )

    if step == 2:
        duracao = _stay_duration_days(letter, form)
        context["duration_days"] = duracao
        context["duration_exceeded"] = exceeds_max_stay(duracao)
        context["max_stay_days"] = MAX_STAY_DAYS
        # A chegada nao pode ser no passado: o `min` fecha o calendario
        # nativo nas datas anteriores a hoje. A regra de verdade continua
        # sendo a do servidor (apps/letters/forms.py).
        context["today"] = timezone.localdate()

    if step == HOST_STEP:
        context["missing_profile_fields"] = faltando
        # Depois de completar o perfil, a pessoa volta para esta etapa.
        context["profile_return_url"] = request.get_full_path()

    return render(request, "letters/wizard.html", context)


def _stay_duration_days(letter, form):
    """
    Duracao da estadia, para exibicao (etapa 'Viagem'). Sai do
    formulario vinculado (POST invalido de outro campo) ou do que ja
    estiver salvo em Letter.data (GET).

    A conta e a de `rules.stay_duration_days` -- a mesma que o PDF usa,
    para a tela nunca dizer um numero e o documento outro.
    """
    if form.is_bound:
        arrival = form["stay_arrival"].value()
        departure = form["stay_departure"].value()
    else:
        arrival = letter.data.get("stay_arrival")
        departure = letter.data.get("stay_departure")

    def _as_date(value):
        if isinstance(value, datetime.date):
            return value
        if isinstance(value, str) and value:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
        return None

    return stay_duration_days(_as_date(arrival), _as_date(departure))


def _handle_language_step(request, letter):
    # O idioma escolhe o `DocumentTemplate`, e o modelo estrutural fica
    # congelado na carta assim que ela e finalizada -- `Letter.save()`
    # recusa troca-lo depois disso. Numa carta reaberta para edicao,
    # portanto, o idioma NAO muda: seria pedir ao modelo algo que ele
    # (corretamente) recusa. Os dados mudam; o documento e o mesmo.
    if letter.document_snapshot_hash:
        if request.method == "POST":
            messages.error(request, LANGUAGE_LOCKED)
            return redirect(
                "letters:step", letter_uuid=letter.uuid, step=services.REVIEW_STEP
            )
        context = _steps_context(letter, services.LANGUAGE_STEP)
        context["language_options"] = [
            {"code": code, "available": code == letter.language,
             **services.LANGUAGE_META[code]}
            for code, _label in settings.LANGUAGES
        ]
        context["selected_language"] = letter.language
        context["language_locked"] = True
        return render(request, "letters/wizard.html", context)

    if request.method == "POST":
        if services.change_language(letter, request.POST.get("language")):
            return redirect("letters:step", letter_uuid=letter.uuid, step=services.REVIEW_STEP)
        messages.error(request, DOCUMENT_UNAVAILABLE)

    available = set(services.available_languages())
    context = _steps_context(letter, services.LANGUAGE_STEP)
    context["language_options"] = [
        {"code": code, "available": code in available, **services.LANGUAGE_META[code]}
        for code, _label in settings.LANGUAGES
    ]
    context["selected_language"] = letter.language
    return render(request, "letters/wizard.html", context)


def _handle_review_step(request, letter):
    if request.method == "POST":
        return _finalize(request, letter)

    context = _steps_context(letter, services.REVIEW_STEP)
    context["review_sections"] = services.grouped_review(letter)
    context["review_language"] = services.LANGUAGE_META.get(letter.language)
    return render(request, "letters/wizard.html", context)


def _finalize(request, letter):
    invalid_step = services.validate_all_steps(letter)
    if invalid_step is not None:
        messages.error(
            request, _("Há etapas incompletas ou inválidas. Revise antes de finalizar.")
        )
        return redirect("letters:step", letter_uuid=letter.uuid, step=invalid_step)

    # O documento usa dados do perfil que nao sao perguntados no
    # assistente (endereco, telefone e a cidade do fecho "Fait à ..."). Se
    # faltar algum, a carta nao pode ser finalizada: o snapshot e
    # congelado no fechamento, entao finalizar agora deixaria a carta
    # presa, sem PDF possivel nem depois de corrigir o perfil.
    missing = services.missing_host_profile_fields(request.user)
    if missing:
        messages.error(
            request,
            _("Complete o seu perfil antes de finalizar a carta. Falta: %(campos)s.")
            % {"campos": ", ".join(str(item) for item in missing)},
        )
        return redirect("accounts:profile")

    letter.snapshot = services.build_snapshot(letter, request.user)
    letter.status = Letter.Status.COMPLETED
    campos = ["snapshot", "status", "updated_at"]
    # O marco zero dos prazos do ciclo de vida, gravado UMA vez. Uma
    # carta reaberta e finalizada de novo mantem o instante original --
    # senao bastaria reeditar para esticar o proprio prazo.
    if letter.finalized_at is None:
        letter.finalized_at = timezone.now()
        campos.append("finalized_at")
    letter.save(update_fields=campos)

    # O modelo estrutural e congelado AQUI, no mesmo instante da
    # finalizacao -- nunca depois, para nao correr atras de um modelo
    # que ja pode ter mudado. Numa carta reaberta o hash ja existe e
    # este passo e pulado: o documento continua sendo o mesmo.
    if not letter.document_snapshot_hash:
        services.capture_document_template_snapshot(letter, letter.document_template)

    # A carta ja fica registrada (COMPLETED) aconteca o que acontecer com
    # o PDF: e melhor do que perder o preenchimento. O status so vira
    # GENERATED quando o arquivo existir de verdade.
    try:
        services.generate_pdf(letter)
    except LetterRenderError:
        # `LetterRenderError` embrulha qualquer falha do renderer
        # estrutural -- ver `services.render_letter()`.
        logger.exception("Falha ao gerar o PDF da carta %s", letter.reference)
        messages.warning(
            request,
            _(
                "A carta foi registrada, mas o PDF não pôde ser gerado. "
                "Nossa equipe foi avisada."
            ),
        )
        return redirect("letters:detail", letter_uuid=letter.uuid)

    messages.success(request, _("Carta Convite gerada com sucesso."))
    return redirect("letters:detail", letter_uuid=letter.uuid)


# ---------------------------------------------------------------------------
# Carta pronta: detalhe e PDF
# ---------------------------------------------------------------------------


def _get_own_letter(user, letter_uuid):
    """
    A Letter identificada por `letter_uuid`, apenas se pertencer a `user`.
    None em qualquer outro caso -- carta de outra pessoa ou inexistente --
    para a view responder sempre o mesmo 404, sem revelar qual dos dois
    aconteceu (nenhuma enumeracao de UUID de terceiros).
    """
    return (
        Letter.objects.filter(uuid=letter_uuid, user=user)
        .select_related("document_template")
        .first()
    )


def _get_visible_letter(user, letter_uuid):
    """
    A Letter que `user` pode VER: a propria sempre; qualquer uma, se
    tiver `letters.view_all_letters` (supervisao).

    E a mesma regra de `Letter.objects.visible_to()`, usada aqui para
    que quem supervisiona alcance tambem uma carta EXPIRADA -- a
    expiracao tira o documento do usuario comum, nao do registro nem
    de quem responde por ele.
    """
    return (
        Letter.objects.visible_to(user)
        .filter(uuid=letter_uuid)
        .select_related("document_template")
        .first()
    )


@login_required
def detail(request, letter_uuid):
    """
    A carta em si: dados reais e a acao que faz sentido no seu estado.

    Uma carta EXPIRADA continua abrindo aqui -- e o registro dela, e a
    pessoa precisa poder ver que expirou. O que a expiracao tira e o
    documento (ver `letter_pdf`), nao a pagina.
    """
    letter = _get_visible_letter(request.user, letter_uuid)
    if letter is None:
        raise Http404("Carta não encontrada.")

    return render(
        request,
        "letters/detail.html",
        {
            "card": presentation.build_card(letter),
            "active_nav": "letters",
            "mobile_nav": True,
        },
    )


@login_required
def letter_pdf(request, letter_uuid, anexo=False):
    """
    Entrega o PDF da carta.

    `anexo=True` (rota `letters:pdf_download`) manda
    `Content-Disposition: attachment`, e o navegador BAIXA em vez de
    exibir. Uma view so para os dois casos, de proposito: login,
    propriedade, expiracao e arquivo ausente sao exatamente as mesmas
    checagens -- duplicar a view duplicaria as guardas, e uma delas
    acabaria ficando para tras.

    O arquivo e privado: nunca e servido por mapeamento estatico de midia
    (isso so existe em DEBUG e nao valida ninguem). A unica porta e esta
    view, que exige login, exige poder ver a carta e exige que o PDF
    exista -- qualquer outro caso e 404, sempre igual.

    EXPIRACAO
    ---------
    Quem decide e `lifecycle.can_user_download_pdf()`, que junta a
    regra de prazo com a autorizacao de quem pede -- a mesma funcao
    que a supervisao consulta para saber se mostra o botao. Carta
    expirada nao entrega uma segunda copia ao usuario comum (e o que
    a politica existe para impedir), mas continua alcancavel por quem
    supervisiona: o registro nao deixa de existir por ter expirado.
    """
    letter = _get_visible_letter(request.user, letter_uuid)
    if letter is None or not letter.pdf_file:
        raise Http404("Carta não encontrada.")

    if not lifecycle.can_user_download_pdf(request.user, letter):
        messages.error(request, LETTER_EXPIRED)
        return redirect("letters:detail", letter_uuid=letter.uuid)

    try:
        arquivo = letter.pdf_file.open("rb")
    except (FileNotFoundError, OSError):
        # O registro aponta para um arquivo que nao esta mais la. Para
        # quem pede, e o mesmo que nao existir.
        raise Http404("Carta não encontrada.") from None

    return FileResponse(
        arquivo,
        content_type="application/pdf",
        filename=f"{letter.reference}.pdf",
        as_attachment=anexo,
    )


# ---------------------------------------------------------------------------
# Histórico: todas as cartas da pessoa
# ---------------------------------------------------------------------------

# Quantas cartas por página no histórico. O painel continua mostrando só
# as `presentation.RECENT_LIMIT` mais recentes -- são telas com propósitos
# diferentes: o painel é um resumo, o histórico é o arquivo.
POR_PAGINA = 20


@login_required
def history(request):
    """
    Minhas cartas: TODAS as do usuário, da mais recente para a mais
    antiga, paginadas.

    Reusa `presentation.own_letters()` -- o mesmo filtro por dono que o
    painel usa, e que deliberadamente NÃO é `visible_to()`: esta é a área
    pessoal, então nem quem supervisiona vê aqui carta de outra pessoa.

    Os estados e as ações de cada cartão vêm de `build_cards()`, iguais
    aos do painel: um estado, um conjunto de ações, em toda a aplicação.
    """
    cartas = presentation.own_letters(request.user)
    pagina = Paginator(cartas, POR_PAGINA).get_page(request.GET.get("page"))

    return render(
        request,
        "letters/history.html",
        {
            "pagina": pagina,
            "cards": presentation.build_cards(pagina.object_list),
            "total": pagina.paginator.count,
            "active_nav": "letters",
            "mobile_nav": True,
        },
    )
