"""
Views de cartas.

`start`/`wizard_step` sao o assistente real (Fase 3): alimentado pelo
field_schema da TemplateVersion publicada do modelo oficial DO IDIOMA da
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
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from apps.letters import presentation, services
from apps.letters.models import Letter
from apps.letters.pdf_generation import UnsupportedLanguageError
from apps.letters.rules import MAX_STAY_DAYS, exceeds_max_stay, stay_duration_days
from pdfengine.exceptions import PdfEngineError

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

    O idioma inicial e o idioma em que a pessoa esta navegando; ele decide
    qual documento oficial sera usado e pode ser trocado na etapa 5. Se
    aquele idioma ainda nao tem documento publicado, o fluxo para aqui com
    um aviso claro — nunca usa o documento de outro idioma no lugar.
    """
    language = services.normalize_language(get_language())
    template_version = services.get_template_version_for_language(language)
    if template_version is None:
        messages.error(request, DOCUMENT_UNAVAILABLE)
        return redirect("core:dashboard")

    data = request.POST if request.method == "POST" else None
    form = services.form_for_new_letter(template_version, language, data=data)

    if request.method == "POST":
        if form.is_valid():
            letter = services.start_draft(request.user, language)
            if letter is None:
                messages.error(request, DOCUMENT_UNAVAILABLE)
                return redirect("core:dashboard")
            services.save_step_data(letter, services.FIRST_STEP, form.cleaned_data)
            return redirect("letters:step", letter_uuid=letter.uuid, step=2)
        messages.error(request, _("Corrija os campos destacados antes de continuar."))

    fields = services.fields_for_section_in(
        template_version.field_schema, services.STEP_SECTIONS[services.FIRST_STEP]
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
    """
    if step < 1 or step > services.LAST_STEP:
        raise Http404("Etapa inválida.")

    letter = services.get_owned_draft(request.user, letter_uuid)
    if letter is None:
        raise Http404("Carta não encontrada.")

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
    letter.save(update_fields=["snapshot", "status", "updated_at"])

    # A carta ja fica registrada (COMPLETED) aconteca o que acontecer com
    # o PDF: e melhor do que perder o preenchimento. O status so vira
    # GENERATED quando o arquivo existir de verdade.
    try:
        services.generate_pdf(letter)
    except UnsupportedLanguageError:
        # Nao e uma falha: e o limite conhecido de so existir documento
        # oficial em frances por enquanto. Dizer isso claramente, em vez
        # de sugerir que algo deu errado.
        messages.warning(
            request,
            _(
                "A carta foi registrada. O documento oficial em PDF ainda só "
                "existe em francês — escolha o francês na etapa de idioma "
                "para gerá-lo."
            ),
        )
        return redirect("letters:detail", letter_uuid=letter.uuid)
    except PdfEngineError:
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

    So o dono, de proposito: `letters.view_all_letters` e permissao de
    supervisao (ver `Letter.objects.visible_to()`), e a tela de supervisao
    nao existe ainda. Quando existir, sera ela a usar aquele filtro.
    """
    return (
        Letter.objects.filter(uuid=letter_uuid, user=user)
        .select_related("template", "template_version")
        .first()
    )


@login_required
def detail(request, letter_uuid):
    """A carta em si: dados reais e a acao que faz sentido no seu estado."""
    letter = _get_own_letter(request.user, letter_uuid)
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
def letter_pdf(request, letter_uuid):
    """
    Entrega o PDF da carta.

    O arquivo e privado: nunca e servido por mapeamento estatico de midia
    (isso so existe em DEBUG e nao valida ninguem). A unica porta e esta
    view, que exige login, exige ser o dono e exige que o PDF exista --
    qualquer outro caso e 404, sempre igual.
    """
    letter = _get_own_letter(request.user, letter_uuid)
    if letter is None or not letter.pdf_file:
        raise Http404("Carta não encontrada.")

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
    )
