"""
Supervisão de cartas no Backoffice: a listagem real e o detalhe de uma
carta de qualquer usuário.

Arquivo PRÓPRIO, no app que tem o modelo -- mesma convenção de
`doctemplates/library_views.py`: a view mora junto do que ela lê, e só a
ROTA mora em `core/backoffice_urls.py`, porque a tela pertence ao
backoffice.

SOMENTE LEITURA
---------------
Nenhuma ação administrativa sobre a carta existe aqui: nem editar, nem
cancelar, nem regerar. Ter permissão de VER não é ter permissão de
mexer, e botão que não funciona é pior do que botão nenhum.

DUAS PERMISSÕES, NÃO UMA
------------------------
Entrar no Backoffice (`core.access_backoffice`) e ver as cartas de todo
mundo (`letters.view_all_letters`) são decisões separadas -- alguém pode
administrar modelos e conteúdo sem ter acesso aos documentos das
pessoas. `supervisao_de_cartas` exige as duas.

O ESTADO NÃO VEM DO BANCO
-------------------------
"Expirada" é derivado da política vigente e do instante atual
(`apps.letters.lifecycle`) -- não existe coluna para ele. Por isso o
filtro de estado e o de período da viagem rodam em Python, sobre os
cartões já montados, enquanto idioma e usuário (que SÃO colunas) filtram
no banco. A alternativa seria repetir a regra de prazo em SQL, que é
exatamente o que esta arquitetura evita.
"""

import datetime
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from apps.core.views import backoffice_required
from apps.letters import lifecycle, presentation
from apps.letters.models import Letter

# Quantas cartas por página. A filtragem por estado acontece depois da
# consulta (ver o cabeçalho), então paginar aqui é o que impede a tela de
# crescer sem limite junto com o banco.
POR_PAGINA = 50

# Os estados que o filtro oferece, na ordem em que fazem sentido para
# quem supervisiona. Os rótulos são os mesmos que a pessoa lê na etiqueta.
ESTADOS = [
    (lifecycle.RASCUNHO, _("Rascunho")),
    (lifecycle.FINALIZADA, _("Finalizada")),
    (lifecycle.EXPIRADA, _("Expirada")),
    (lifecycle.CANCELADA, _("Cancelada")),
]


def supervisao_de_cartas(view):
    """
    Exige entrar no Backoffice E `letters.view_all_letters`.

    Duas checagens porque são duas decisões: `backoffice_required` diz
    quem entra na área administrativa; esta segunda diz quem, lá dentro,
    pode ver documentos de outras pessoas. Superusuário passa pelas duas
    por como `has_perm` funciona.
    """

    @backoffice_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not lifecycle.supervisiona(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def _contexto_do_backoffice(active, titulo):
    """A casca da área administrativa (menu, cabeçalho)."""
    return {
        "active": active,
        "bo_title": titulo,
        "bo_action_icon": "ph-files",
        "bo_action_label": titulo,
    }


@supervisao_de_cartas
def backoffice_letters(request):
    """
    Todas as cartas do sistema, com o estado de cada uma.

    Filtros por querystring: `state`, `language`, `user` e o período da
    viagem (`from`/`to`, em ISO). Combináveis; vazio significa "sem
    filtro".
    """
    cartas = Letter.objects.select_related("user", "document_template").order_by("-created_at")

    # --- o que o banco sabe filtrar ---------------------------------------
    idioma = request.GET.get("language") or ""
    if idioma:
        cartas = cartas.filter(language=idioma)

    usuario_id = request.GET.get("user") or ""
    if usuario_id.isdigit():
        cartas = cartas.filter(user_id=int(usuario_id))

    # --- o que só o lifecycle sabe responder ------------------------------
    cards = presentation.build_cards(cartas)

    estado = request.GET.get("state") or ""
    if estado:
        cards = [card for card in cards if card.state == estado]

    de = _data_iso(request.GET.get("from"))
    ate = _data_iso(request.GET.get("to"))
    if de:
        cards = [card for card in cards if card.arrival and card.arrival >= de]
    if ate:
        cards = [card for card in cards if card.arrival and card.arrival <= ate]

    pagina = Paginator(cards, POR_PAGINA).get_page(request.GET.get("page"))

    # A querystring SEM o `page`, para os links de navegacao nao
    # acumularem um parametro a cada clique (?page=2&page=3&...).
    querystring = request.GET.copy()
    querystring.pop("page", None)

    contexto = _contexto_do_backoffice("letters", _("Cartas"))
    contexto.update(
        {
            "pagina": pagina,
            "querystring": querystring.urlencode(),
            "cards": pagina.object_list,
            "total": pagina.paginator.count,
            "estados": ESTADOS,
            "idiomas": Letter._meta.get_field("language").choices,
            "usuarios": _usuarios_com_cartas(),
            "filtros": {
                "state": estado,
                "language": idioma,
                "user": usuario_id,
                "from": request.GET.get("from") or "",
                "to": request.GET.get("to") or "",
            },
            "politica": lifecycle.policy(),
        }
    )
    return render(request, "backoffice/letters.html", contexto)


@supervisao_de_cartas
def backoffice_letter_detail(request, letter_uuid):
    """
    Uma carta qualquer, vista por quem supervisiona -- inclusive de
    outro usuário e inclusive expirada.

    Somente leitura. O PDF, quando existe, continua saindo pela única
    porta que há (`letters:pdf`), que decide por conta própria quem pode
    obtê-lo (`lifecycle.can_user_download_pdf`) -- a regra não é
    reescrita aqui.
    """
    carta = (
        Letter.objects.select_related("user", "document_template", "document_template__type")
        .filter(uuid=letter_uuid)
        .first()
    )
    if carta is None:
        raise Http404("Carta não encontrada.")

    card = presentation.build_card(carta)
    contexto = _contexto_do_backoffice("letters", _("Carta"))
    contexto.update(
        {
            "card": card,
            "carta": carta,
            "dono": carta.user,
            "politica": lifecycle.policy(),
            "pode_baixar_pdf": lifecycle.can_user_download_pdf(request.user, carta),
            "revisao": _revisao_da_carta(carta),
        }
    )
    return render(request, "backoffice/letter_detail.html", contexto)


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


def _data_iso(valor):
    """Uma data vinda da querystring, ou None se ausente/ilegível."""
    if not valor:
        return None
    try:
        return datetime.date.fromisoformat(valor)
    except ValueError:
        return None


def _usuarios_com_cartas():
    """
    Só quem tem carta entra no seletor -- uma lista com todos os
    usuários do sistema não ajudaria a filtrar nada.
    """
    from django.contrib.auth import get_user_model

    return (
        get_user_model()
        .objects.filter(letters__isnull=False)
        .distinct()
        .order_by("full_name", "email")
    )


def _revisao_da_carta(carta):
    """
    Os dados preenchidos, agrupados por seção e já com os rótulos
    resolvidos -- o mesmo resumo que a pessoa vê na etapa 6 do
    assistente, montado por `services.grouped_review`.

    Reusar em vez de reescrever: os rótulos saem do `field_schema` do
    modelo, e uma segunda montagem aqui sairia do ar assim que o schema
    mudasse.
    """
    from apps.letters import services

    return services.grouped_review(carta)
