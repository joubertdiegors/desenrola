"""
Rotas da area administrativa (representacao visual).

"Usuarios" e "Cartas" leem o banco de verdade; as demais telas ainda
sao ilustrativas e apontam para a secao correspondente (heranca da v1),
mantendo o item ativo correto no menu.

A rota "permissions/" foi retirada: permissao agora se administra POR
PESSOA, em usuarios/<id>/permissoes/ -- nao havia tela geral de
permissoes para onde apontar.

"Modelos" aponta para a biblioteca de `DocumentTemplate`: e a unica
biblioteca de modelos do produto. A tela antiga de versionamento
(`/backoffice/documentos/`, Etapa 4.2A/4.2C) foi aposentada na Etapa
3.5.3, junto com o editor visual que ela servia.
"""

from django.urls import path

from apps.accounts import backoffice_views as accounts_backoffice
from apps.doctemplates import editor_views as doc_editor_views
from apps.doctemplates import library_views as doc_library_views
from apps.letters import backoffice_views as letters_backoffice

from . import views

app_name = "backoffice"

urlpatterns = [
    path("", views.backoffice_overview, name="overview"),
    # Gerenciador de usuarios e permissoes. As views ficam em
    # apps.accounts (junto do modelo que leem); so a rota mora aqui.
    path("usuarios/", accounts_backoffice.backoffice_users, name="users"),
    path(
        "usuarios/<int:pk>/",
        accounts_backoffice.backoffice_user_detail,
        name="user_detail",
    ),
    path(
        "usuarios/<int:pk>/permissoes/",
        accounts_backoffice.backoffice_user_permissions,
        name="user_permissions",
    ),
    path(
        "usuarios/<int:pk>/situacao/",
        accounts_backoffice.backoffice_user_activation,
        name="user_activation",
    ),
    # Supervisao de cartas: le o banco de verdade. As views ficam em
    # apps.letters (junto do modelo que leem); so a rota mora aqui.
    path("letters/", letters_backoffice.backoffice_letters, name="letters"),
    path(
        "letters/<uuid:letter_uuid>/",
        letters_backoffice.backoffice_letter_detail,
        name="letter_detail",
    ),
    # Politica do ciclo de vida das cartas (editabilidade e expiracao).
    path("cartas/politica/", views.backoffice_letter_policy, name="letter_policy"),
    path("templates/", views.backoffice_templates, name="templates"),
    # Biblioteca dos modelos: a tela que o menu "Modelos" abre.
    path("modelos/", doc_library_views.document_library, name="document_library"),
    path(
        "modelos/<int:pk>/",
        doc_library_views.document_detail,
        name="document_detail",
    ),
    path(
        "modelos/<int:pk>/duplicar/",
        doc_library_views.document_library_duplicate,
        name="document_library_duplicate",
    ),
    path(
        "modelos/<int:pk>/situacao/",
        doc_library_views.document_library_activation,
        name="document_library_activation",
    ),
    # Editor estrutural dos modelos da biblioteca (Etapa 3.2).
    path(
        "modelos/<int:pk>/editar/",
        doc_editor_views.template_editor,
        name="template_editor",
    ),
    path(
        "modelos/<int:pk>/salvar/",
        doc_editor_views.template_editor_save,
        name="template_editor_save",
    ),
    path(
        "modelos/<int:pk>/ids/",
        doc_editor_views.template_editor_ids,
        name="template_editor_ids",
    ),
    path("content/", views.backoffice_templates, {"active": "content"}, name="content"),
    path("languages/", views.backoffice_templates, {"active": "languages"}, name="languages"),
    path("partners/", views.backoffice_partners, name="partners"),
    path("appearance/", views.backoffice_appearance, name="appearance"),
    path("system/", views.backoffice_templates, {"active": "system"}, name="system"),
]
