"""
Rotas da area administrativa (representacao visual).

Os layouts de referencia da v2 detalham "Usuarios e permissoes" (2j) e
"Aparencia" (2i). Os demais itens do menu apontam para a tela que contem a
secao correspondente (heranca da v1) ou para uma tela nova e simples
(Parceiros), mantendo o item ativo correto no menu.
"""

from django.urls import path

from apps.doctemplates import views as doc_views

from . import views

app_name = "backoffice"

urlpatterns = [
    path("", views.backoffice_users, {"active": "overview"}, name="overview"),
    path("users/", views.backoffice_users, name="users"),
    path("permissions/", views.backoffice_users, {"active": "permissions"}, name="permissions"),
    path("letters/", views.backoffice_letters, name="letters"),
    path("templates/", views.backoffice_templates, name="templates"),
    # Editor visual de documentos (Etapa 4.2A). As views ficam em
    # apps.doctemplates, junto do modelo que editam; so a rota mora aqui,
    # porque a tela pertence ao backoffice.
    path("documentos/", doc_views.document_list, name="documents"),
    path("documentos/<int:version_pk>/", doc_views.document_editor, name="document_editor"),
    path(
        "documentos/<int:version_pk>/salvar/",
        doc_views.document_save,
        name="document_save",
    ),
    path(
        "documentos/<int:version_pk>/publicar/",
        doc_views.document_publish,
        name="document_publish",
    ),
    path(
        "documentos/<int:version_pk>/importar-oficial/",
        doc_views.document_import_official,
        name="document_import_official",
    ),
    path(
        "documentos/<int:version_pk>/nova-versao/",
        doc_views.document_new_version,
        name="document_new_version",
    ),
    path("content/", views.backoffice_templates, {"active": "content"}, name="content"),
    path("languages/", views.backoffice_templates, {"active": "languages"}, name="languages"),
    path("partners/", views.backoffice_partners, name="partners"),
    path("appearance/", views.backoffice_appearance, name="appearance"),
    path("system/", views.backoffice_templates, {"active": "system"}, name="system"),
]
