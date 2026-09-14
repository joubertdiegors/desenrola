"""
Views do app core.

As areas do usuario exigem login; a area administrativa exige a
permissao `core.access_backoffice`. O dashboard e a supervisao de
cartas (esta em `apps.letters.backoffice_views`) leem o banco; a
landing e as demais telas administrativas continuam com dados
ficticios (apps.core.demo) ate as proximas etapas do backend.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.letters import lifecycle, presentation

from . import demo
from .forms import LetterPolicyForm

# A permissao que abre a porta do Backoffice. Uma constante, e nao a
# string solta em cada view/template, para o dia em que alguem precisar
# procurar "quem decide isso".
BACKOFFICE_PERM = "core.access_backoffice"

# Permissao para MUDAR a politica das cartas. Entrar no Backoffice e uma
# coisa; alterar uma regra que vale para todo mundo e outra.
LETTER_POLICY_PERM = "letters.change_letterpolicy"


def backoffice_required(view):
    """
    Exige login e a permissao `core.access_backoffice`; sem ela, 403.

    E a UNICA porta do Backoffice, e ela e no servidor: esconder o
    link no dashboard nao protege nada -- a URL continua sendo
    digitavel. Superusuario passa por `has_perm` automaticamente.

    Substituiu a checagem de `is_staff` (a flag do Django Admin, que
    este projeto nao usa como backoffice). Quem ja era staff recebeu a
    permissao na migration `core.0001`, entao ninguem perdeu acesso.
    """

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.has_perm(BACKOFFICE_PERM):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def home(request):
    """
    Landing publica (layouts 2a, 3a e 4a).

    Quem ja esta logado nao tem o que fazer na pagina de apresentacao:
    vai direto para a sua area. O logout traz de volta para ca
    (LOGOUT_REDIRECT_URL), e ai a sessao ja acabou -- entao nao ha laco.
    """
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    return render(
        request,
        "core/home.html",
        {"landing_stat": demo.LANDING_STAT, "partners": demo.PARTNERS},
    )


@login_required
def dashboard(request):
    """
    Area do usuario: as cartas DELE, vindas do banco.

    Lista as mais recentes (`presentation.RECENT_LIMIT`), mas conta o
    total -- o numero ao lado do titulo e quantas cartas a pessoa tem, nao
    quantas couberam na lista.
    """
    letters = presentation.own_letters(request.user)
    return render(
        request,
        "core/dashboard.html",
        {
            "cards": presentation.build_cards(letters[: presentation.RECENT_LIMIT]),
            "letters_total": letters.count(),
            # O atalho para o Backoffice so existe para quem tem a
            # permissao. Nao e seguranca -- isso e o
            # `backoffice_required` -- e sim nao oferecer uma porta
            # que bateria na cara da pessoa.
            "can_access_backoffice": request.user.has_perm(BACKOFFICE_PERM),
            "active_nav": "home",
            "mobile_nav": True,
        },
    )


def healthz(request):
    """
    Verificacao de saude da aplicacao.

    Responde sem tocar no banco nem em templates, para servir de sonda
    barata de monitoramento apos o deploy.
    """
    return HttpResponse("ok", content_type="text/plain")


# ---------------------------------------------------------------------------
# Area administrativa (representacao visual; nao substitui o Django Admin)
# ---------------------------------------------------------------------------


def _backoffice_context(active):
    section = demo.BACKOFFICE_SECTIONS[active]
    return {
        "active": active,
        "bo_title": section["title"],
        "bo_action_icon": section["icon"],
        "bo_action_label": section["action"],
    }


@backoffice_required
def backoffice_users(request, active="users"):
    """Usuarios e permissoes (layout 2j). Tambem responde por visao geral."""
    context = _backoffice_context(active)
    context.update(
        {
            "stats": demo.STATS,
            "stats_mobile": demo.STATS_MOBILE,
            "users": demo.ADMIN_USERS,
            "permissions": demo.PERMISSIONS,
        }
    )
    return render(request, "backoffice/users.html", context)


@backoffice_required
def backoffice_templates(request, active="templates"):
    """Modelos, conteudo e idiomas (sem layout proprio na v2; mantido da v1)."""
    context = _backoffice_context(active)
    context["languages"] = demo.LANGUAGES
    return render(request, "backoffice/templates.html", context)


@backoffice_required
def backoffice_partners(request):
    """Parceiros (novo menu na v2; sem layout de tela detalhado)."""
    context = _backoffice_context("partners")
    context["partners"] = demo.ADMIN_PARTNERS
    return render(request, "backoffice/partners.html", context)


@backoffice_required
def backoffice_appearance(request):
    """
    Aparencia (layouts 2i e 4m): cor principal e cor de sucesso do site.

    A escolha e aplicada de verdade no navegador de quem está usando o
    backoffice (mesmo mecanismo do seletor de tema em static/js/theme.js),
    mas ainda nao e publicada num banco para valer para todos os
    visitantes — isso depende de um modelo de configuracao, fora do
    escopo desta etapa.
    """
    context = _backoffice_context("appearance")
    context.update(
        {
            "primary_swatches": demo.THEME_PRIMARY_SWATCHES,
            "success_swatches": demo.THEME_SUCCESS_SWATCHES,
        }
    )
    return render(request, "backoffice/appearance.html", context)


@backoffice_required
def backoffice_letter_policy(request):
    """
    Política das cartas: por quanto tempo uma carta finalizada pode ser
    editada, e quando ela expira.

    Entrar aqui exige `core.access_backoffice`; SALVAR exige, além
    disso, `letters.change_letterpolicy` -- ver uma regra que vale para
    todo mundo é uma coisa, mudá-la é outra. A checagem é no POST, não
    só no botão.

    Os valores vão para `letters.LetterPolicy` (um registro só). Quem
    faz a conta com eles é `apps.letters.lifecycle`; esta view não
    calcula prazo nenhum.
    """
    config = lifecycle.policy()
    pode_editar = request.user.has_perm(LETTER_POLICY_PERM)

    if request.method == "POST":
        if not pode_editar:
            raise PermissionDenied
        form = LetterPolicyForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, _("Política das cartas atualizada."))
            return redirect(reverse("backoffice:letter_policy"))
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = LetterPolicyForm(instance=config)

    context = _backoffice_context("letter_policy")
    context.update({"form": form, "pode_editar": pode_editar})
    return render(request, "backoffice/letter_policy.html", context)
