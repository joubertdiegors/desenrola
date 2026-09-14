"""
Rotas da area administrativa (representacao visual).

Os layouts de referencia da v2 detalham "Usuarios e permissoes" (2j) e
"Aparencia" (2i). Os demais itens do menu apontam para a tela que contem a
secao correspondente (heranca da v1) ou para uma tela nova e simples
(Parceiros), mantendo o item ativo correto no menu.

"Modelos" aponta para a biblioteca de `DocumentTemplate`: e a unica
biblioteca de modelos do produto. A tela antiga de versionamento
(`/backoffice/documentos/`, Etapa 4.2A/4.2C) foi aposentada na Etapa
3.5.3, junto com o editor visual que ela servia.
"""

from django.urls import path

from apps.doctemplates import editor_views as doc_editor_views
from apps.doctemplates import library_views as doc_library_views

from . import views

app_name = "backoffice"

urlpatterns = [
    path("", views.backoffice_users, {"active": "overview"}, name="overview"),
    path("users/", views.backoffice_users, name="users"),
    path("permissions/", views.backoffice_users, {"active": "permissions"}, name="permissions"),
    path("letters/", views.backoffice_letters, name="letters"),
    path("templates/", views.backoffice_templates, name="templates"),
    # Biblioteca dos modelos: a tela que o menu "Modelos" abre.
    path("modelos/", doc_library_views.document_library, name="document_library"),
    path(
        "modelos/<int:pk>/duplicar/",
        doc_library_views.document_library_duplicate,
        name="document_library_duplicate",
    ),
    path(
        "modelos/<int:pk>/excluir/",
        doc_library_views.document_library_delete,
        name="document_library_delete",
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
