"""
Testes de internacionalizacao do roteamento.

A infraestrutura continua multilingue (settings.LANGUAGES, i18n_patterns,
LocaleMiddleware, set_language) porque e ela que alimenta o idioma da
CARTA. A INTERFACE, desde a Fase 5 / Etapa 4.1, e sempre portuguesa -- o
que a interface faz com os prefixos de outro idioma esta em
apps/core/tests/test_etapa41.py.
"""

import pytest
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


@pytest.mark.django_db  # a Home le o conteudo do CMS desde a Etapa B
def test_prefixo_de_outro_idioma_continua_atendido(client):
    """
    Nenhum prefixo pode dar 404: links antigos e indexados tem de
    continuar funcionando. O que mudou e o destino -- /en/ agora leva a
    interface em portugues, em vez de responder ali mesmo.
    """
    assert client.get("/pt/").status_code == 200

    response = client.get("/en/")

    assert response.status_code == 302
    assert response.url == "/pt/"
    assert client.get("/en/", follow=True).status_code == 200


def test_set_language_fora_do_prefixo():
    """A rota de troca de idioma precisa de URL estavel, sem prefixo."""
    assert reverse("set_language") == "/i18n/setlang/"
