"""Rotas do app core."""

from django.urls import path

from apps.content.services import PAGINAS_LEGAIS

from . import views

app_name = "core"


def _chave(slug):
    """A chave de ContentBlock daquele slug, declarada em services."""
    for declarado, chave, _titulo in PAGINAS_LEGAIS:
        if declarado == slug:
            return chave
    raise ValueError(f"slug legal desconhecido: {slug!r}")


def _titulo(slug):
    for declarado, _chave, titulo in PAGINAS_LEGAIS:
        if declarado == slug:
            return titulo
    raise ValueError(f"slug legal desconhecido: {slug!r}")


urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    # Todos os parceiros. A Home mostra quatro; o "Ver todos" vem para ca.
    path("parceiros/", views.parceiros, name="parceiros"),
    # Paginas legais. Os slugs sao LITERAIS e a chave do ContentBlock vai
    # fixa em cada rota: nenhuma parte da URL vira consulta ao banco.
    #
    # O prefixo `legal/` tambem evita disputa com `path("")` acima, que e
    # a landing -- um `<slug>/` solto aqui competiria com toda rota nova
    # que este arquivo ganhasse depois.
    path(
        "legal/termos-de-uso/",
        views.legal,
        {"chave": _chave("termos-de-uso"), "titulo": _titulo("termos-de-uso")},
        name="legal_termos",
    ),
    path(
        "legal/privacidade/",
        views.legal,
        {"chave": _chave("privacidade"), "titulo": _titulo("privacidade")},
        name="legal_privacidade",
    ),
]
