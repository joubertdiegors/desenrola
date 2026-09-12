"""
Views minimas de fundacao.

Sao apenas o esqueleto de navegacao para validar roteamento, i18n e
autenticacao. O layout definitivo e o fluxo da carta serao implementados
em fase posterior.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render


def home(request):
    """Pagina publica inicial."""
    return render(request, "core/home.html")


@login_required
def dashboard(request):
    """Area logada do usuario."""
    return render(request, "core/dashboard.html")


def healthz(request):
    """
    Verificacao de saude da aplicacao.

    Responde sem tocar no banco nem em templates, para servir de sonda
    barata de monitoramento apos o deploy.
    """
    return HttpResponse("ok", content_type="text/plain")
