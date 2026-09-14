"""
Configuracoes base do projeto Desenrola.

Nunca use este modulo diretamente: use `config.settings.dev` ou
`config.settings.prod`, que herdam daqui e ajustam o que for especifico
de cada ambiente.

Todo valor sensivel ou dependente de ambiente vem do arquivo `.env`
(ver `.env.example`). Nada de segredo versionado no repositorio.
"""

from pathlib import Path

import environ
from django.utils.translation import gettext_lazy as _

# BASE_DIR aponta para a raiz do projeto (onde fica o manage.py).
# config/settings/base.py -> settings -> config -> raiz
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
)

# Carrega o .env da raiz, se existir.
environ.Env.read_env(BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# Seguranca
# ---------------------------------------------------------------------------

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")


# ---------------------------------------------------------------------------
# Aplicacoes
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS: list[str] = []

# Os apps locais moram no pacote `apps/`. O AppConfig de cada um define um
# `label` curto (ex.: "accounts"), entao referencias em models, migracoes e
# permissoes continuam sendo "accounts.User" e nao "apps.accounts.User".
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.doctemplates",
    "apps.letters",
    "apps.content",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # A interface e so em portugues (Fase 5, Etapa 4.1): este middleware
    # fecha as tres portas por onde outro idioma entraria (prefixo da URL,
    # cookie e Accept-Language) ANTES de o LocaleMiddleware decidir.
    "apps.core.middleware.InterfaceEmPortuguesMiddleware",
    # LocaleMiddleware precisa vir depois de Session e antes de Common.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------
#
# Producao usa PostgreSQL via DATABASE_URL. O fallback SQLite existe apenas
# para o desenvolvimento inicial; `config.settings.prod` recusa subir sem um
# DATABASE_URL apontando para PostgreSQL.

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="sqlite:///" + str(BASE_DIR / "db.sqlite3"),
    )
}


# ---------------------------------------------------------------------------
# Autenticacao
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "core:home"

# Prazo do link de recuperacao de senha (segundos): 3 dias.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24 * 3


# ---------------------------------------------------------------------------
# E-mail
# ---------------------------------------------------------------------------
#
# Usado hoje pela recuperacao de senha.
#
# O backend do projeto e o `ConfiguredEmailBackend`: a cada envio ele
# olha `core.EmailSettings` (cadastrado no Backoffice) e, havendo
# configuracao ATIVA, fala SMTP com ela. Sem configuracao ativa, entrega
# ao EMAIL_FALLBACK_BACKEND do ambiente -- console em desenvolvimento,
# EMAIL_URL em producao. Assim o codigo que envia continua sendo
# `send_mail()` de sempre, e o interruptor da tela significa alguma
# coisa de fato.

EMAIL_BACKEND = "apps.core.mail.ConfiguredEmailBackend"
EMAIL_FALLBACK_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Desenrola <no-reply@desenrola.be>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Chave que cifra a senha SMTP guardada no banco (apps.core.crypto).
# Vazia, a chave e derivada da SECRET_KEY. Definir uma propria permite
# rodar SECRET_KEY sem tornar a senha guardada ilegivel -- e vice-versa.
# NUNCA versionada: mora no .env, como a SECRET_KEY.
EMAIL_SECRET_KEY = env("EMAIL_SECRET_KEY", default="")


# ---------------------------------------------------------------------------
# Internacionalizacao
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "pt"

LANGUAGES = [
    ("pt", _("Portugues")),
    ("fr", _("Frances")),
    ("nl", _("Holandes")),
    ("en", _("Ingles")),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

TIME_ZONE = "Europe/Brussels"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Arquivos estaticos e de midia
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# MEDIA_ROOT guarda os PDFs base dos modelos e as cartas geradas.
# As cartas sao privadas: nunca devem ser expostas por mapeamento estatico
# publico, e sim entregues por uma view que valida o usuario.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# ---------------------------------------------------------------------------
# Diversos
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DEFAULT_CHARSET = "utf-8"
