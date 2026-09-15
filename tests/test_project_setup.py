"""
Testes da fundacao do projeto.

Protegem decisoes arquiteturais que sao caras de reverter depois:
o User customizado, os labels curtos dos apps e a exigencia de
PostgreSQL em producao.
"""

import pytest
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def test_user_customizado_esta_ativo():
    assert settings.AUTH_USER_MODEL == "accounts.User"


def test_apps_locais_registrados_com_label_curto():
    """
    Os apps moram em `apps/`, mas o label precisa ser curto para que
    migracoes e permissoes usem "accounts.User", nao "apps.accounts.User".
    """
    esperado = {"core", "accounts", "doctemplates", "letters", "content"}
    labels = {app.label for app in apps.get_app_configs()}

    assert esperado.issubset(labels)

    for label in esperado:
        assert apps.get_app_config(label).name == f"apps.{label}"


def test_locale_paths_configurado():
    assert settings.LOCALE_PATHS
    assert (settings.BASE_DIR / "locale").exists()


def test_locale_middleware_na_ordem_correta():
    """LocaleMiddleware precisa ficar depois de Session e antes de Common."""
    ordem = settings.MIDDLEWARE

    i_session = ordem.index("django.contrib.sessions.middleware.SessionMiddleware")
    i_locale = ordem.index("django.middleware.locale.LocaleMiddleware")
    i_common = ordem.index("django.middleware.common.CommonMiddleware")

    assert i_session < i_locale < i_common


def _importa_prod():
    """Importa config.settings.prod do zero, lendo o ambiente atual."""
    import importlib
    import sys

    sys.modules.pop("config.settings.prod", None)
    try:
        return importlib.import_module("config.settings.prod")
    finally:
        sys.modules.pop("config.settings.prod", None)


def test_prod_recusa_banco_que_nao_seja_postgres(monkeypatch):
    """Producao nao pode subir gravando num SQLite esquecido."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///naodeveria.sqlite3")
    monkeypatch.setenv("ALLOWED_HOSTS", "exemplo.test")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://exemplo.test")

    with pytest.raises(ImproperlyConfigured):
        _importa_prod()


def test_prod_aceita_postgres_e_endurece_https(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pwd@localhost:5432/desenrola")
    monkeypatch.setenv("ALLOWED_HOSTS", "exemplo.test,www.exemplo.test")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://exemplo.test")

    prod = _importa_prod()

    assert prod.DEBUG is False
    assert prod.ALLOWED_HOSTS == ["exemplo.test", "www.exemplo.test"]
    assert "postgresql" in prod.DATABASES["default"]["ENGINE"]
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.SECURE_HSTS_SECONDS > 0
