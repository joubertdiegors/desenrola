"""
Views de conta: cadastro, login, perfil e recuperacao de senha.

Tudo usa os mecanismos nativos do Django: sessao, hash de senha, CSRF,
validacao de formularios e os tokens de recuperacao de senha. Cada view
opera apenas sobre `request.user`; nao ha rota que exponha dados de outro
usuario.
"""

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from .forms import LoginForm, PasswordChangeForm, ProfileForm, SetPasswordForm, SignupForm

# Secoes do perfil e o titulo usado no cabecalho do celular.
PROFILE_SECTIONS = {
    "dados": gettext_lazy("Dados pessoais"),
    "senha": gettext_lazy("Alterar senha"),
    "idioma": gettext_lazy("Idioma e aparência"),
    "comunicacoes": gettext_lazy("Comunicações"),
}


def _safe_next(request):
    """URL de retorno (?next=) apenas se apontar para este site."""
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return None


@sensitive_post_parameters("password1", "password2")
@never_cache
def signup(request):
    """Criar conta (layouts 1d e 1m). Apos criar, autentica e vai ao dashboard."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect(_safe_next(request) or "core:dashboard")
    else:
        form = SignupForm()

    return render(
        request,
        "accounts/signup.html",
        {"form": form, "next": request.GET.get("next", "")},
    )


class LoginView(auth_views.LoginView):
    """Entrar (layouts 1c e 1l). Template em registration/login.html."""

    authentication_form = LoginForm
    redirect_authenticated_user = True


def _profile_url(section):
    url = reverse("accounts:profile")
    if section in PROFILE_SECTIONS:
        url += f"?secao={section}"
    return url


@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@login_required
def profile(request):
    """
    Perfil (layouts 1h e 1q).

    Uma pagina, dois formularios: dados pessoais (action=dados) e troca de
    senha (action=senha). No celular, ?secao= abre uma secao por vez; o
    campo oculto `secao` devolve o usuario a mesma secao apos salvar.
    """
    user = request.user
    section = request.GET.get("secao")
    profile_form = ProfileForm(instance=user)
    password_form = PasswordChangeForm(user)

    if request.method == "POST":
        section = request.POST.get("secao") or None
        if request.POST.get("action") == "senha":
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                password_form.save()
                # Mantem a sessao valida apos trocar a senha.
                update_session_auth_hash(request, password_form.user)
                messages.success(request, _("Senha atualizada."))
                return redirect(_profile_url(section))
            section = "senha"
        else:
            profile_form = ProfileForm(request.POST, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, _("Alterações salvas."))
                return redirect(_profile_url(section))
            section = "dados"

    if section not in PROFILE_SECTIONS:
        section = None

    return render(
        request,
        "accounts/profile.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
            "section": section,
            "section_title": PROFILE_SECTIONS.get(section, ""),
            "active_nav": "profile",
        },
    )


# ---------------------------------------------------------------------------
# Recuperacao de senha: fluxo nativo do Django (token assinado, com prazo
# PASSWORD_RESET_TIMEOUT), apenas com os templates do Desenrola.
# ---------------------------------------------------------------------------


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    form_class = SetPasswordForm
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
