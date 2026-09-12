"""Testes de internacionalizacao do roteamento."""

from django.conf import settings
from django.urls import reverse
from django.utils import translation


def test_idiomas_configurados():
    codigos = [codigo for codigo, _nome in settings.LANGUAGES]

    assert codigos == ["pt", "fr", "nl", "en"]
    assert settings.LANGUAGE_CODE == "pt"
    assert settings.USE_I18N is True


def test_url_recebe_prefixo_do_idioma():
    """i18n_patterns deve prefixar as rotas da aplicacao."""
    for codigo in ("pt", "fr", "nl", "en"):
        with translation.override(codigo):
            assert reverse("core:home") == f"/{codigo}/"


def test_troca_de_idioma_responde(client):
    url_pt = "/pt/"
    url_en = "/en/"

    assert client.get(url_pt).status_code == 200
    assert client.get(url_en).status_code == 200


def test_set_language_fora_do_prefixo():
    """A rota de troca de idioma precisa de URL estavel, sem prefixo."""
    assert reverse("set_language") == "/i18n/setlang/"
