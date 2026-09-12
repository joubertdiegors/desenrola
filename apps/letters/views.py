"""
Views de cartas.

`start`/`wizard_step` sao o assistente real (Fase 3): alimentado pelo
field_schema da TemplateVersion publicada do modelo oficial DO IDIOMA da
carta, persistido em Letter.data por etapa.

Criacao: `GET /letters/new/` so APRESENTA a primeira etapa — nao grava
nada. E o POST valido dessa tela que cria a Letter em rascunho. Assim
nenhum link, prefetch ou recarregamento cria carta por engano.

`generate`/`result` sao a fase de apresentacao anterior (dados ficticios
de apps.core.demo) — nenhuma tela do assistente real aponta mais para
elas; ficam como estao, sem geracao de PDF ainda (isso e Fase 4), so como
referencia visual da conclusao.
"""

import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from apps.core import demo
from apps.letters import services
from apps.letters.models import Letter

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

# Metadados de exibicao de cada idioma disponivel (nome/dica/bandeira). Os
# CODIGOS validos continuam vindo so de settings.LANGUAGES — isto e so a
# camada visual de apoio, nunca a fonte de verdade sobre quais idiomas
# existem, nem sobre quais tem documento oficial publicado.
LANGUAGE_META = {
    "pt": {
        "name": "Português",
        "hint": _("Versão completa do documento."),
        "flag": "lang-flag-pt",
    },
    "fr": {
        "name": "Français",
        "hint": _("Idioma mais utilizado para processos na Bélgica."),
        "flag": "lang-flag-fr",
    },
    "nl": {
        "name": "Nederlands",
        "hint": _("Também é idioma oficial na Bélgica e nos Países Baixos."),
        "flag": "lang-flag-nl",
    },
    "en": {
        "name": "English",
        "hint": _("Widely accepted internationally."),
        "flag": "lang-flag-en",
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
    }


def _handle_form_step(request, letter, step):
    data = request.POST if request.method == "POST" else None
    form = services.form_for_step(letter, step, data=data)

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
        context["duration_days"] = _stay_duration_days(letter, form)

    return render(request, "letters/wizard.html", context)


def _stay_duration_days(letter, form):
    """
    Duracao da estadia, para exibicao (etapa 'Viagem'). So calculada
    quando ja ha datas validas — no formulario vinculado (POST invalido de
    outro campo) ou no que ja estiver salvo em Letter.data (GET).
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

    arrival_date = _as_date(arrival)
    departure_date = _as_date(departure)
    if not arrival_date or not departure_date:
        return None
    days = (departure_date - arrival_date).days
    return days if days > 0 else None


def _handle_language_step(request, letter):
    if request.method == "POST":
        if services.change_language(letter, request.POST.get("language")):
            return redirect("letters:step", letter_uuid=letter.uuid, step=services.REVIEW_STEP)
        messages.error(request, DOCUMENT_UNAVAILABLE)

    available = set(services.available_languages())
    context = _steps_context(letter, services.LANGUAGE_STEP)
    context["language_options"] = [
        {"code": code, "available": code in available, **LANGUAGE_META[code]}
        for code, _label in settings.LANGUAGES
    ]
    context["selected_language"] = letter.language
    return render(request, "letters/wizard.html", context)


def _handle_review_step(request, letter):
    if request.method == "POST":
        return _finalize(request, letter)

    context = _steps_context(letter, services.REVIEW_STEP)
    context["review_sections"] = services.grouped_review(letter)
    context["review_language"] = LANGUAGE_META.get(letter.language)
    return render(request, "letters/wizard.html", context)


def _finalize(request, letter):
    invalid_step = services.validate_all_steps(letter)
    if invalid_step is not None:
        messages.error(
            request, _("Há etapas incompletas ou inválidas. Revise antes de finalizar.")
        )
        return redirect("letters:step", letter_uuid=letter.uuid, step=invalid_step)

    letter.snapshot = services.build_snapshot(letter, request.user)
    letter.status = Letter.Status.COMPLETED
    letter.save(update_fields=["snapshot", "status", "updated_at"])

    messages.success(request, _("Carta Convite registrada com sucesso."))
    return redirect("core:dashboard")


# --- Fase de apresentação (dados fictícios) — mantidas sem alteração -------


@login_required
def generate(request):
    """Recebe o envio da etapa 6 da fase de apresentação (so redireciona)."""
    return redirect("letters:result", pk=1)


@login_required
def result(request, pk):
    """Conclusão da fase de apresentação: carta ficticia, com preview e ações."""
    letter = demo.get_letter(pk)
    if letter is None:
        raise Http404("Carta não encontrada.")
    return render(
        request,
        "letters/result.html",
        {"letter": letter, "active_nav": "letters", "mobile_nav": True},
    )
