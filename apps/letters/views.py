"""
Views de cartas.

Exigem login. O formulario e o resultado ainda usam dados ficticios
(apps.core.demo): a logica definitiva do formulario, o modelo Letter e a
geracao real do PDF entram nas proximas etapas. Os dados do anfitriao que
o modelo de usuario ja guarda (nome, telefone, endereco) vem do usuario
autenticado.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from apps.core import demo

LAST_STEP = 4


@login_required
def new(request):
    """Gerar Carta Convite (layouts 1f e 1o). ?passo=N escolhe o passo no celular."""
    try:
        step = int(request.GET.get("passo", 1))
    except (TypeError, ValueError):
        step = 1
    step = min(max(step, 1), LAST_STEP)
    return render(
        request,
        "letters/form.html",
        {
            "host": demo.HOST,
            "guest": demo.GUEST,
            "stay": demo.STAY,
            "step": step,
            "steps": range(1, LAST_STEP + 1),
            "step_info": demo.FORM_STEPS[step],
        },
    )


@login_required
def result(request, pk):
    """Resultado / PDF (layouts 1g e 1p)."""
    letter = demo.get_letter(pk)
    if letter is None:
        raise Http404("Carta não encontrada.")
    return render(request, "letters/result.html", {"letter": letter})
