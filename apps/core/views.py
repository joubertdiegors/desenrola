"""
Views do app core.

As areas do usuario exigem login; a area administrativa exige `is_staff`.
Cartas, estatisticas, parceiros e aparencia continuam com dados ficticios
(apps.core.demo) ate as proximas etapas do backend.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render

from . import demo


def staff_required(view):
    """Exige login e, alem disso, `is_staff`; sem isso responde 403."""

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def home(request):
    """Landing publica (layouts 2a, 3a e 4a)."""
    return render(
        request,
        "core/home.html",
        {"landing_stat": demo.LANDING_STAT, "partners": demo.PARTNERS},
    )


@login_required
def dashboard(request):
    """Area do usuario. As cartas listadas ainda sao ficticias."""
    return render(
        request,
        "core/dashboard.html",
        {"letters": demo.LETTERS, "active_nav": "home", "mobile_nav": True},
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
        "admin_user": demo.ADMIN,
    }


@staff_required
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


@staff_required
def backoffice_letters(request, active="letters"):
    """Cartas de todos os usuarios (sem layout proprio; deriva de 2c e 2j)."""
    context = _backoffice_context(active)
    context["letters"] = demo.ALL_LETTERS
    return render(request, "backoffice/letters.html", context)


@staff_required
def backoffice_templates(request, active="templates"):
    """Modelos, conteudo e idiomas (sem layout proprio na v2; mantido da v1)."""
    context = _backoffice_context(active)
    context["languages"] = demo.LANGUAGES
    return render(request, "backoffice/templates.html", context)


@staff_required
def backoffice_partners(request):
    """Parceiros (novo menu na v2; sem layout de tela detalhado)."""
    context = _backoffice_context("partners")
    context["partners"] = demo.ADMIN_PARTNERS
    return render(request, "backoffice/partners.html", context)


@staff_required
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
