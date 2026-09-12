"""Rotas do app letters."""

from django.urls import path

from . import views

app_name = "letters"

# A carta e sempre identificada pela UUID publica, nunca pelo id
# sequencial: um id em sequencia deixaria adivinhar quantas cartas
# existem e tentar as dos outros.
urlpatterns = [
    path("new/", views.start, name="new"),
    path("<uuid:letter_uuid>/step/<int:step>/", views.wizard_step, name="step"),
    path("<uuid:letter_uuid>/pdf/", views.letter_pdf, name="pdf"),
    path("<uuid:letter_uuid>/", views.detail, name="detail"),
]
