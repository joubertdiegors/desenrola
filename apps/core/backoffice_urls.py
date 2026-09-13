"""
Rotas da area administrativa (representacao visual).

Os layouts de referencia da v2 detalham "Usuarios e permissoes" (2j) e
"Aparencia" (2i). Os demais itens do menu apontam para a tela que contem a
secao correspondente (heranca da v1) ou para uma tela nova e simples
(Parceiros), mantendo o item ativo correto no menu.

"Modelos" aponta para a biblioteca de `DocumentTemplate` (Etapa 3.2.1),
nao mais para a tela antiga de `LetterTemplate`/`TemplateVersion` -- essa
continua registrada em `templates`/`documentos/` para o legado, mas nao e
mais alcancavel pela navegacao normal.
"""

from django.urls import path

from apps.doctemplates import editor_views as doc_editor_views
from apps.doctemplates import library_views as doc_library_views
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
    # Biblioteca dos modelos da nova arquitetura (Etapa 3.2.1). E a tela
    # que o menu "Modelos" abre agora -- a antiga (`templates`, abaixo)
    # continua registrada, mas deixou de ser alcancavel pela navegacao.
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
    # Editor visual dos modelos da biblioteca (Etapa 3.2). As views ficam
    # em apps.doctemplates.editor_views, separadas das do editor anterior.
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
