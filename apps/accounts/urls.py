"""
Rotas de conta.

Login e logout continuam nas views nativas do Django. Cadastro, recuperacao
de senha e perfil sao, nesta fase, telas de apresentacao com envio
simulado; a logica real entra na fase de autenticacao.
"""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("password-reset/", views.password_reset, name="password_reset"),
    path("profile/", views.profile, name="profile"),
]
