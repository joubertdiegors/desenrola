"""
Rotas de autenticacao.

Nesta fase apenas login e logout, usando as views nativas do Django sem
logica propria, para que `login_required` funcione e a fundacao fique
coerente. Cadastro, recuperacao de senha e perfil entram na fase de
autenticacao, junto com os templates definitivos.
"""

from django.contrib.auth import views as auth_views
from django.urls import path

app_name = "accounts"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
