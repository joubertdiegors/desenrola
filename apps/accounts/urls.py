"""
Rotas de conta.

Login, logout e recuperacao de senha usam as views nativas do Django
(com formularios e templates do Desenrola). Cadastro e perfil sao views
proprias em `views.py`.
"""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("profile/", views.profile, name="profile"),
    # Confirmacao de e-mail. `email_confirm` NAO exige sessao: o link
    # chega por e-mail e costuma ser aberto noutro navegador.
    path(
        "email/confirmar/<uidb64>/<token>/",
        views.confirmar_email,
        name="email_confirm",
    ),
    path(
        "email/reenviar/",
        views.reenviar_confirmacao,
        name="email_confirm_resend",
    ),
    path("password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "password-reset/<uidb64>/<token>/",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
