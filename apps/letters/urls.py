"""Rotas do app letters."""

from django.urls import path

from . import views

app_name = "letters"

urlpatterns = [
    path("new/", views.new, name="new"),
    path("<int:pk>/", views.result, name="result"),
]
