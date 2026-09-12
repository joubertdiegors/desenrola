"""Rotas do app letters."""

from django.urls import path

from . import views

app_name = "letters"

urlpatterns = [
    path("new/", views.start, name="new"),
    path("new/gerar/", views.generate, name="generate"),
    path("<uuid:letter_uuid>/step/<int:step>/", views.wizard_step, name="step"),
    path("<int:pk>/", views.result, name="result"),
]
