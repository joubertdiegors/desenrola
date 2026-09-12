"""
Rotas da area administrativa (representacao visual).

Os layouts de referencia definem duas telas: "Usuarios e permissoes" (1i)
e "Modelos, conteudo e idiomas" (1j). Os demais itens do menu apontam para
a tela que contem a secao correspondente, mantendo o item ativo correto.
"""

from django.urls import path

from . import views

app_name = "backoffice"

urlpatterns = [
    path("", views.backoffice_users, {"active": "overview"}, name="overview"),
    path("users/", views.backoffice_users, name="users"),
    path("permissions/", views.backoffice_users, {"active": "permissions"}, name="permissions"),
    path("letters/", views.backoffice_letters, name="letters"),
    path("templates/", views.backoffice_templates, name="templates"),
    path("content/", views.backoffice_templates, {"active": "content"}, name="content"),
    path("languages/", views.backoffice_templates, {"active": "languages"}, name="languages"),
    path("system/", views.backoffice_templates, {"active": "system"}, name="system"),
]
