"""
Configuracoes de producao (PythonAnywhere).

Diferente de dev, aqui nao ha fallback de banco: DATABASE_URL precisa existir
e precisa apontar para PostgreSQL. Falhar no boot e melhor do que subir em
producao gravando num SQLite esquecido.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")

# Banco: obrigatorio e obrigatoriamente PostgreSQL.
DATABASES = {"default": env.db("DATABASE_URL")}

if "postgresql" not in DATABASES["default"]["ENGINE"]:
    raise ImproperlyConfigured(
        "Em producao DATABASE_URL deve apontar para PostgreSQL, e nao para "
        + DATABASES["default"]["ENGINE"]
    )


# ---------------------------------------------------------------------------
# E-mail (recuperacao de senha)
# ---------------------------------------------------------------------------
# EMAIL_URL no formato do django-environ, ex.:
#   smtp+tls://usuario:senha@smtp.exemplo.com:587
# Sem a variavel, os e-mails sao apenas escritos no log do servidor: o
# fluxo funciona, mas nenhuma mensagem chega ao usuario ate o SMTP existir.

globals().update(env.email_url("EMAIL_URL", default="consolemail://"))


# ---------------------------------------------------------------------------
# Endurecimento HTTPS
# ---------------------------------------------------------------------------
# O PythonAnywhere termina o TLS no proxy dele e repassa X-Forwarded-Proto.

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 ano
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
