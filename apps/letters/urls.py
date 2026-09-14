"""Rotas do app letters."""

from django.urls import path

from . import views

app_name = "letters"

# A carta e sempre identificada pela UUID publica, nunca pelo id
# sequencial: um id em sequencia deixaria adivinhar quantas cartas
# existem e tentar as dos outros.
urlpatterns = [
    # O historico completo: todas as cartas da pessoa, paginadas. O
    # painel mostra so as mais recentes e aponta para ca.
    path("", views.history, name="history"),
    path("new/", views.start, name="new"),
    path("<uuid:letter_uuid>/step/<int:step>/", views.wizard_step, name="step"),
    path("<uuid:letter_uuid>/pdf/", views.letter_pdf, name="pdf"),
    # A MESMA view, em modo anexo: o navegador baixa em vez de exibir.
    path(
        "<uuid:letter_uuid>/pdf/baixar/",
        views.letter_pdf,
        {"anexo": True},
        name="pdf_download",
    ),
    path("<uuid:letter_uuid>/", views.detail, name="detail"),
]
