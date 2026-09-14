"""
Editor estrutural dos modelos da biblioteca (Etapa 3.2).

    GET  backoffice/modelos/<pk>/editar/        abre o editor
    POST backoffice/modelos/<pk>/salvar/        grava o layout
    POST backoffice/modelos/<pk>/ids/           mais ids para elementos novos

E o unico editor de documentos do produto desde a Etapa 3.5.3, que
aposentou o editor visual da 4.2A/4.2C e a tela que o servia.


O SERVIDOR E A AUTORIDADE
-------------------------
O editor esconde controles conforme o estado do modelo, mas esconder nao
e proteger: o salvamento reconfere tudo do lado de ca -- se o modelo
aceita edicao, se o corpo e JSON, e se o layout cumpre o contrato da
Etapa 3.1. O JavaScript nunca decide se algo pode ser gravado.

E o endpoint le APENAS `layout` do corpo. `type`, `language`,
`is_system`, `duplicated_from` e `created_by` nao tem por onde chegar:
nao sao lidos, nao sao escritos. A protecao vem de nao existir caminho,
nao de uma lista de campos proibidos que alguem possa esquecer de
atualizar.


DE ONDE VEM CADA ID DE ELEMENTO
-------------------------------
Do servidor, nunca do navegador. Ao abrir o editor a pagina recebe um
lote de ids gerados por `services/layout.py` -- o mesmo gerador que o
salvamento usaria -- e o JavaScript apenas CONSOME desse lote quando
insere um elemento. Assim nao ha duas estrategias de identificacao
podendo divergir, e o contrato continua tendo um dono so.

Se o lote acabar numa sessao muito longa, `template_editor_ids` entrega
outro. E, como ultima rede, `services.layout.adicionar_elemento`
regenera qualquer id vazio ou repetido que chegue ao salvamento.
"""

import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.content.models import Asset
from apps.core.views import backoffice_required

from . import datasources, elements, layout_schema
from .models import DocumentTemplate, DocumentTemplateLockedError
from .services import layout as servico_de_layout

# Tamanho maximo do corpo aceito no salvamento. Um layout no limite de
# elementos fica bem abaixo disto; o limite existe para um envio absurdo
# ser recusado antes de virar JSON na memoria.
MAX_CORPO_BYTES = 2 * 1024 * 1024

# Quantos ids a pagina leva de antemao. Uma sessao de edicao real usa
# uma fracao disto; e barato e evita ida ao servidor a cada insercao.
IDS_POR_LOTE = 200


def _pode_editar(modelo):
    """
    So um modelo comum e destravado aceita edicao pelo fluxo normal.

    Um oficial (`is_system`) abre em leitura mesmo destravado: a
    reconstrucao controlada dos oficiais sera feita por um servico
    proprio, fora do editor. As regras de verdade estao em
    `DocumentTemplate.save()`; aqui a checagem existe para a tela abrir
    no modo certo e para o salvamento recusar antes de tentar.
    """
    return not modelo.is_system and not modelo.is_locked


def _motivo_da_leitura(modelo):
    if modelo.is_locked:
        return _(
            "Este modelo está travado. Para alterá-lo, destrave-o na administração "
            "ou duplique-o — a cópia nasce editável."
        )
    if modelo.is_system:
        return _(
            "Este é um modelo oficial do sistema e não é editado por aqui. "
            "Duplique-o para trabalhar numa cópia sua."
        )
    return ""


def _lote_de_ids(quantos=IDS_POR_LOTE):
    return [servico_de_layout.novo_id() for _ in range(quantos)]


@backoffice_required
def template_editor(request, pk):
    """A tela do editor."""
    modelo = get_object_or_404(
        DocumentTemplate.objects.select_related("type", "created_by"), pk=pk
    )
    editavel = _pode_editar(modelo)

    return render(
        request,
        "backoffice/template_editor.html",
        {
            "active": "templates",
            "bo_title": modelo.name,
            "bo_action_icon": "ph-floppy-disk",
            "bo_action_label": _("Salvar"),
            "modelo": modelo,
            "editavel": editavel,
            "motivo_da_leitura": _motivo_da_leitura(modelo),
            "voltar_url": reverse("admin:doctemplates_documenttemplate_changelist"),
            # Estado inicial. Vai pelo filtro |json_script, que serializa E
            # escapa -- nunca interpolado dentro de <script>, o que seria
            # injecao. Por isso sao OBJETOS, nao strings ja serializadas.
            "layout_json": modelo.layout or layout_schema.layout_vazio(),
            "pagina_json": modelo.type.page,
            "tipos_json": elements.para_o_editor(),
            "fontes_json": datasources.para_o_editor(),
            "ids_json": _lote_de_ids(),
            "assets_json": [
                {
                    "id": asset.pk,
                    "label": str(asset),
                    "url": asset.file.url if asset.file else "",
                }
                for asset in Asset.objects.filter(is_active=True).order_by("kind", "key")
            ],
            "config_json": {
                "editable": editavel,
                "saveUrl": reverse("backoffice:template_editor_save", args=[modelo.pk]),
                "idsUrl": reverse("backoffice:template_editor_ids", args=[modelo.pk]),
                "maxElements": layout_schema.MAX_ELEMENTS,
                "layoutVersion": layout_schema.VERSION,
            },
        },
    )


@backoffice_required
@require_POST
def template_editor_save(request, pk):
    """
    Grava o layout. Responde JSON -- e chamado por fetch().

    Nada aqui confia no editor: permissao, estado do modelo, forma do
    corpo e contrato do layout sao todos reconferidos.
    """
    modelo = get_object_or_404(DocumentTemplate, pk=pk)

    if not _pode_editar(modelo):
        return JsonResponse(
            {"ok": False, "error": _motivo_da_leitura(modelo)}, status=409
        )

    if len(request.body) > MAX_CORPO_BYTES:
        return JsonResponse(
            {"ok": False, "error": _("O layout é grande demais.")}, status=413
        )

    try:
        corpo = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": _("JSON inválido.")}, status=400)

    if not isinstance(corpo, dict) or "layout" not in corpo:
        return JsonResponse(
            {"ok": False, "error": _('O corpo precisa ter a chave "layout".')},
            status=400,
        )

    documento = corpo["layout"]
    try:
        layout_schema.validate_layout(documento)
    except ValidationError as erro:
        return JsonResponse(
            {"ok": False, "error": " ".join(erro.messages)}, status=400
        )

    # SO o layout. As regras de `DocumentTemplate.save()` continuam
    # valendo -- nada de `queryset.update()` para contorna-las.
    modelo.layout = documento
    try:
        modelo.save(update_fields=["layout", "updated_at"])
    except DocumentTemplateLockedError as erro:
        return JsonResponse({"ok": False, "error": str(erro)}, status=409)

    return JsonResponse(
        {
            "ok": True,
            "elementos": len(documento.get("elements", [])),
            "atualizado_em": modelo.updated_at.isoformat(),
        }
    )


@backoffice_required
@require_POST
def template_editor_ids(request, pk):
    """Outro lote de ids, para uma sessao que esgotou o primeiro."""
    modelo = get_object_or_404(DocumentTemplate, pk=pk)
    if not _pode_editar(modelo):
        raise PermissionDenied
    return JsonResponse({"ok": True, "ids": _lote_de_ids()})
