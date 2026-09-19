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
    # Exportacao da listagem para Excel (.xlsx), por POST.
    path(
        "usuarios/exportar/",
        accounts_backoffice.backoffice_users_export,
        name="users_export",
    ),
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
    # Exportacao da listagem para Excel (.xlsx), por POST.
    path(
        "letters/exportar/",
        letters_backoffice.backoffice_letters_export,
        name="letters_export",
    ),
    path(
        "letters/<uuid:letter_uuid>/",
        letters_backoffice.backoffice_letter_detail,
        name="letter_detail",
    ),
    # Politica do ciclo de vida das cartas (editabilidade e expiracao).
    # No menu, "Wizzard - gerar carta" -- mudou so o nome.
    path("cartas/politica/", views.backoffice_letter_policy, name="letter_policy"),
    # As declaracoes da etapa 4 do assistente. A tela delas e a propria
    # Politica das cartas (ver `letters.backoffice_views`), entao nao ha
    # rota de lista: toda acao volta para la.
    path(
        "cartas/declaracoes/nova/",
        letters_backoffice.backoffice_letter_notice_new,
        name="letter_notice_new",
    ),
    path(
        "cartas/declaracoes/<int:pk>/",
        letters_backoffice.backoffice_letter_notice_edit,
        name="letter_notice_edit",
    ),
    path(
        "cartas/declaracoes/<int:pk>/situacao/",
        letters_backoffice.backoffice_letter_notice_activation,
        name="letter_notice_activation",
    ),
    path(
        "cartas/declaracoes/<int:pk>/ordem/",
        letters_backoffice.backoffice_letter_notice_move,
        name="letter_notice_move",
    ),
    path(
        "cartas/declaracoes/<int:pk>/excluir/",
        letters_backoffice.backoffice_letter_notice_delete,
        name="letter_notice_delete",
    ),
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
    # O PDF do modelo gravado -- a janela "visualizar" da biblioteca.
    path(
        "modelos/<int:pk>/documento.pdf",
        doc_library_views.document_preview,
        name="document_preview",
    ),
    path(
        "modelos/<int:pk>/situacao/",
        doc_library_views.document_library_activation,
        name="document_library_activation",
    ),
    # Bloqueia um modelo destravado (Rodada 21) -- so liga o cadeado;
    # destravar continua sendo administracao ou duplicar.
    path(
        "modelos/<int:pk>/bloquear/",
        doc_library_views.document_library_lock,
        name="document_library_lock",
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
    path(
        "modelos/<int:pk>/previa/",
        doc_editor_views.template_editor_preview,
        name="template_editor_preview",
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
    path(
        "idiomas/<str:code>/bandeira/",
        letters_backoffice.backoffice_language_flag,
        name="language_flag",
    ),
    # Itens da barra superior do SITE (nao deste menu lateral). A tela
    # deles e o editor da secao "navbar" -- ver `cadastro="menu"` em
    # `content.section_schema` --, entao nao ha rota de lista propria.
    path(
        "conteudo/menu/novo/",
        content_backoffice.backoffice_menu_item_new,
        name="menu_item_new",
    ),
    path(
        "conteudo/menu/<int:pk>/",
        content_backoffice.backoffice_menu_item_edit,
        name="menu_item_edit",
    ),
    path(
        "conteudo/menu/<int:pk>/situacao/",
        content_backoffice.backoffice_menu_item_activation,
        name="menu_item_activation",
    ),
    path(
        "conteudo/menu/<int:pk>/ordem/",
        content_backoffice.backoffice_menu_item_move,
        name="menu_item_move",
    ),
    path(
        "conteudo/menu/<int:pk>/excluir/",
        content_backoffice.backoffice_menu_item_delete,
        name="menu_item_delete",
    ),
    # Perguntas frequentes da Home. Mesma forma dos itens do menu: a
    # tela delas e o editor da secao "faq" (ver `cadastro="faq"` em
    # `content.section_schema`), entao nao ha rota de lista propria.
    path(
        "conteudo/faq/nova/",
        content_backoffice.backoffice_faq_item_new,
        name="faq_item_new",
    ),
    path(
        "conteudo/faq/<int:pk>/",
        content_backoffice.backoffice_faq_item_edit,
        name="faq_item_edit",
    ),
    path(
        "conteudo/faq/<int:pk>/situacao/",
        content_backoffice.backoffice_faq_item_activation,
        name="faq_item_activation",
    ),
    path(
        "conteudo/faq/<int:pk>/ordem/",
        content_backoffice.backoffice_faq_item_move,
        name="faq_item_move",
    ),
    path(
        "conteudo/faq/<int:pk>/excluir/",
        content_backoffice.backoffice_faq_item_delete,
        name="faq_item_delete",
    ),
    # Blocos do rodape. Mesma forma dos itens do menu e das perguntas: a
    # tela deles e o editor da secao "footer" (ver `cadastro="rodape"`
    # em `content.section_schema`) -- so que os "itens" sao os quatro
    # blocos fixos, identificados pela chave, nao por um `pk` de banco.
    # Biblioteca de imagens: toda imagem administravel do projeto.
    path("imagens/", content_backoffice.backoffice_assets, name="assets"),
    path("imagens/nova/", content_backoffice.backoffice_asset_new, name="asset_new"),
    path("imagens/<int:pk>/", content_backoffice.backoffice_asset_edit, name="asset_edit"),
    path(
        "imagens/<int:pk>/situacao/",
        content_backoffice.backoffice_asset_activation,
        name="asset_activation",
    ),
    path(
        "imagens/<int:pk>/excluir/",
        content_backoffice.backoffice_asset_delete,
        name="asset_delete",
    ),
    # Parceiros: o cadastro inteiro, no produto. Ate a Etapa 11 esta
    # tela era so leitura e mandava para a administracao do Django.
    path("partners/", content_backoffice.backoffice_partners, name="partners"),
    path("partners/novo/", content_backoffice.backoffice_partner_new, name="partner_new"),
    path("partners/<int:pk>/", content_backoffice.backoffice_partner_edit, name="partner_edit"),
    path(
        "partners/<int:pk>/situacao/",
        content_backoffice.backoffice_partner_activation,
        name="partner_activation",
    ),
    path(
        "partners/<int:pk>/ordem/",
        content_backoffice.backoffice_partner_move,
        name="partner_move",
    ),
    path(
        "partners/<int:pk>/excluir/",
        content_backoffice.backoffice_partner_delete,
        name="partner_delete",
    ),
    path("appearance/", views.backoffice_appearance, name="appearance"),
    # Configuracoes globais do site (nome, contato, redes). Deixou de
    # ser o placeholder na Etapa F.
    path("sistema/", views.backoffice_system, name="system"),
    # Documentos legais (Termos de uso, Privacidade): cada documento com
    # a sua propria rota de visualizacao e a sua propria rota de edicao
    # (Rodada 21) -- nunca os dois juntos, nunca ver e editar na mesma
    # tela. O idioma continua se escolhendo na propria tela (`?idioma=`).
    path(
        "sistema/documentos-legais/termos-de-uso/",
        content_backoffice.backoffice_legal_terms,
        name="legal_documents_terms",
    ),
    path(
        "sistema/documentos-legais/termos-de-uso/editar/",
        content_backoffice.backoffice_legal_terms_edit,
        name="legal_documents_terms_edit",
    ),
    # A previa ao vivo (Rodada 22) da aba "Visualizar" do editor por
    # blocos -- o quadro de um <iframe>, nunca uma pagina que se navega.
    path(
        "sistema/documentos-legais/termos-de-uso/previa/",
        content_backoffice.backoffice_legal_terms_preview,
        name="legal_documents_terms_preview",
    ),
    path(
        "sistema/documentos-legais/privacidade/",
        content_backoffice.backoffice_legal_privacy,
        name="legal_documents_privacy",
    ),
    path(
        "sistema/documentos-legais/privacidade/editar/",
        content_backoffice.backoffice_legal_privacy_edit,
        name="legal_documents_privacy_edit",
    ),
    path(
        "sistema/documentos-legais/privacidade/previa/",
        content_backoffice.backoffice_legal_privacy_preview,
        name="legal_documents_privacy_preview",
    ),
]
