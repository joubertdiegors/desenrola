"""
Views de cartas.

Fase de apresentacao visual: o formulario e o resultado usam dados
ficticios (apps.core.demo). A logica definitiva do formulario, o modelo
Letter e a geracao real do PDF entram em fases posteriores.
"""

from django.http import Http404
from django.shortcuts import render

from apps.core import demo

LAST_STEP = 4


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
            "demo_user": demo.USER,
            "guest": demo.GUEST,
            "stay": demo.STAY,
            "step": step,
            "steps": range(1, LAST_STEP + 1),
            "step_info": demo.FORM_STEPS[step],
        },
    )


def result(request, pk):
    """Resultado / PDF (layouts 1g e 1p)."""
    letter = demo.get_letter(pk)
    if letter is None:
        raise Http404("Carta não encontrada.")
    return render(request, "letters/result.html", {"demo_user": demo.USER, "letter": letter})
