"""
Views do app core.

Fase de apresentacao visual: as telas usam dados ficticios (apps.core.demo)
e ainda nao exigem login. Na fase de autenticacao, o dashboard volta a
usar `login_required` e a ler as cartas do banco.
"""

from django.http import HttpResponse
from django.shortcuts import render

from . import demo


def home(request):
    """Landing publica."""
    return render(request, "core/home.html")


def dashboard(request):
    """Area do usuario. TODO(fase de autenticacao): restaurar @login_required."""
    return render(
        request,
        "core/dashboard.html",
        {
            "demo_user": demo.USER,
            "letters": demo.LETTERS,
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
        "admin_user": demo.ADMIN,
    }


def backoffice_users(request, active="users"):
    """Usuarios e permissoes (layout 1i). Tambem responde por visao geral."""
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


def backoffice_letters(request, active="letters"):
    """Cartas de todos os usuarios (sem layout proprio; deriva de 1e e 1i)."""
    context = _backoffice_context(active)
    context["letters"] = demo.ALL_LETTERS
    return render(request, "backoffice/letters.html", context)


def backoffice_templates(request, active="templates"):
    """Modelos, conteudo, idiomas e sistema (layout 1j)."""
    context = _backoffice_context(active)
    context["languages"] = demo.LANGUAGES
    return render(request, "backoffice/templates.html", context)
