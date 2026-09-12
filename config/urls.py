"""
Rotas raiz do projeto Desenrola.

As rotas da aplicacao ficam dentro de `i18n_patterns`, ganhando prefixo de
idioma (/pt/, /fr/, /nl/, /en/). Isso mantem as URLs indexaveis e
compartilhaveis por idioma, o que importa num dominio .be multilingue.

Ficam FORA do prefixo:
  - /i18n/setlang/ : troca de idioma, que precisa de URL estavel;
  - /healthz/      : sonda de monitoramento, que nao deve redirecionar.
"""

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path

from apps.core.views import healthz

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("healthz/", healthz, name="healthz"),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
)

if settings.DEBUG:
    from django.conf.urls.static import static

    # Em desenvolvimento o Django serve a midia. Em producao os PDFs das
    # cartas sao privados e serao entregues por view autenticada.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
