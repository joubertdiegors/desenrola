"""
Rotas da area administrativa (representacao visual).

Os layouts de referencia da v2 detalham "Usuarios e permissoes" (2j) e
"Aparencia" (2i). Os demais itens do menu apontam para a tela que contem a
secao correspondente (heranca da v1) ou para uma tela nova e simples
(Parceiros), mantendo o item ativo correto no menu.
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
    path("partners/", views.backoffice_partners, name="partners"),
    path("appearance/", views.backoffice_appearance, name="appearance"),
    path("system/", views.backoffice_templates, {"active": "system"}, name="system"),
]
