"""
Rotas da area administrativa (nao substitui o Django Admin em /admin/).

Todas as telas leem o banco. A rota "templates/", que servia uma maqueta
com um editor de conteudo falso e um cartao de modelos inventado, foi
retirada na Etapa I: ela nao estava em menu nenhum e duplicava duas
telas reais -- "conteudo/" (Etapa D) e "modelos/" (a biblioteca).

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
from apps.content import backoffice_views as content_backoffice
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
    # Configuracao de envio de e-mail (SMTP). Tres rotas separadas de
    # proposito: salvar os dados, ligar/desligar o envio e disparar um
    # teste sao tres decisoes diferentes, e o teste nao pode ser um
    # efeito colateral de salvar.
    path("email/", views.backoffice_email_settings, name="email_settings"),
    path(
        "email/teste/",
        views.backoffice_email_settings_test,
        name="email_settings_test",
    ),
    path(
        "email/situacao/",
        views.backoffice_email_settings_activation,
        name="email_settings_activation",
    ),
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
    # Conteudo do site: as secoes da Home, editadas por tipo. As views
    # ficam em apps.content (junto dos modelos que leem); so a rota mora
    # aqui.
    path("conteudo/", content_backoffice.backoffice_content, name="content"),
    path(
        "conteudo/<int:pk>/",
        content_backoffice.backoffice_content_section,
        name="content_section",
    ),
    # A previa de UMA parte, para o `<iframe>` da miniatura. Mesma
    # permissao de ver o conteudo.
    path(
        "conteudo/<int:pk>/previa/",
        content_backoffice.backoffice_content_preview,
        name="content_preview",
    ),
    path(
        "conteudo/<int:pk>/situacao/",
        content_backoffice.backoffice_content_activation,
        name="content_activation",
    ),
    # Idiomas dos DOCUMENTOS (nao os da interface, que e so
    # portuguesa). Deixou de ser o placeholder na Etapa E.
    path("idiomas/", views.backoffice_languages, name="languages"),
    path("partners/", views.backoffice_partners, name="partners"),
    path("appearance/", views.backoffice_appearance, name="appearance"),
    # Configuracoes globais do site (nome, contato, redes). Deixou de
    # ser o placeholder na Etapa F.
    path("sistema/", views.backoffice_system, name="system"),
]
