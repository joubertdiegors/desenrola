"""
Views publicas de conta.

Fase de apresentacao visual: cadastro, recuperacao de senha e perfil sao
telas com dados ficticios e envio simulado. A logica real (formularios,
validacao, e-mail, sessao) entra na fase de autenticacao.
"""

from django.shortcuts import render

from apps.core import demo


def signup(request):
    """Criar conta (layouts 1d e 1m)."""
    return render(request, "accounts/signup.html")


def password_reset(request):
    """Recuperar senha (sem layout proprio; deriva da tela de entrar)."""
    return render(request, "accounts/password_reset.html")


def profile(request):
    """Perfil (layouts 1h e 1q). No celular, ?secao= abre uma secao."""
    section = request.GET.get("secao")
    if section not in demo.PROFILE_SECTIONS:
        section = None
    return render(
        request,
        "accounts/profile.html",
        {
            "demo_user": demo.USER,
            "section": section,
            "section_title": demo.PROFILE_SECTIONS.get(section, ""),
            "active_nav": "profile",
        },
    )
