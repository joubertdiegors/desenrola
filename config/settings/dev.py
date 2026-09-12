"""Configuracoes de desenvolvimento local."""

from .base import *  # noqa: F403
from .base import INSTALLED_APPS, MIDDLEWARE, env

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]

# Em desenvolvimento os e-mails (ex.: recuperacao de senha) sao impressos no
# console. O envio real sera configurado em fase posterior.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# O django-debug-toolbar e opcional: so entra se DEBUG_TOOLBAR=True no .env,
# para nao interferir na execucao dos testes.
if env.bool("DEBUG_TOOLBAR", default=False):
    INSTALLED_APPS = INSTALLED_APPS + ["debug_toolbar"]
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE
    INTERNAL_IPS = ["127.0.0.1"]
