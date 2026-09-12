"""
Views de cartas.

Exigem login. O assistente de 6 etapas e a conclusao ainda usam dados
ficticios (apps.core.demo): a logica definitiva do formulario, o modelo
Letter e a geracao real do PDF entram em fases posteriores. Os dados do
anfitriao que o modelo de usuario ja guarda (nome, telefone, endereco) vem
do usuario autenticado; os demais (nacionalidade, nascimento, documento)
seguem ficticios ate o modelo ganhar esses campos.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render

from apps.core import demo


@login_required
def new(request):
    """
    Gerar Carta Convite: assistente de 6 etapas (layouts 2e/2f/3c e
    4e-4j). Cada etapa e uma tela propria, em ?passo=N.

    Sem um modelo Letter ainda, nao ha estado salvo entre etapas: as
    etapas 1 e 2 comecam em branco (o usuario preenche); a etapa 6 mostra
    um exemplo ja preenchido, para demonstrar a revisao antes de gerar.
    """
    try:
        step = int(request.GET.get("passo", 1))
    except (TypeError, ValueError):
        step = 1
    step = min(max(step, 1), demo.LAST_STEP)

    return render(
        request,
        "letters/wizard.html",
        {
            "step": step,
            "steps": range(1, demo.LAST_STEP + 1),
            "last_step": demo.LAST_STEP,
            "step_info": demo.FORM_STEPS[step],
            "host_extra": demo.HOST_EXTRA,
            "guest": demo.GUEST_EXAMPLE,
            "stay": demo.STAY_EXAMPLE,
            "language_options": demo.LANGUAGE_OPTIONS,
            "default_language": demo.DEFAULT_LANGUAGE,
            "legal_notices": demo.LEGAL_NOTICES,
        },
    )


@login_required
def generate(request):
    """Recebe o envio da etapa 6 (fase de apresentacao: so redireciona)."""
    return redirect("letters:result", pk=1)


@login_required
def result(request, pk):
    """Conclusão: carta gerada, com preview e acoes (layouts 2g e 4k)."""
    letter = demo.get_letter(pk)
    if letter is None:
        raise Http404("Carta não encontrada.")
    return render(
        request,
        "letters/result.html",
        {"letter": letter, "active_nav": "letters", "mobile_nav": True},
    )
