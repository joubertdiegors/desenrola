"""
Editor visual de documentos (Fase 5, Etapa 4.2A).

Tres telas e tres acoes, todas dentro do backoffice:

    GET  documentos/                      lista modelos e versoes
    GET  documentos/<pk>/                 abre o editor
    POST documentos/<pk>/salvar/          grava o JSON (rascunho)
    POST documentos/<pk>/publicar/        publica o rascunho
    POST documentos/<pk>/nova-versao/     cria o proximo rascunho

AUTORIZACAO -- sempre no servidor
---------------------------------
O editor esconde botoes conforme a permissao, mas esconder nao e
proteger: cada acao reconfere do lado de ca. As permissoes sao as do
proprio Django sobre `TemplateVersion` (`change_`, `add_`, e a
`publish_templateversion` que ja existia no modelo desde a Fase 2) --
nenhuma permissao nova foi inventada, e nenhum usuario comum ganha
acesso por acidente.

IMUTABILIDADE
-------------
Uma versao publicada nunca e editada. Quem abrir uma e quiser mexer cria
a proxima versao em rascunho (`create_next_version`, que ja herda campos
e layout) e edita essa. A regra ja e garantida no `save()` do modelo; as
views param antes, para dar uma mensagem em vez de uma exception.
"""

import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.content.models import Asset
from apps.core import demo
from apps.core.views import staff_required

from .models import LetterTemplate, TemplateVersion, TemplateVersionImmutableError
from .services import visual_import
from .visual_schema import (
    A4_HEIGHT_PT,
    A4_WIDTH_PT,
    ALIGNMENTS,
    ELEMENT_TYPES,
    FONT_FAMILIES,
    MAX_ELEMENTS,
    QR_ERROR_LEVELS,
    SCHEMA_VERSION,
    documento_vazio,
    field_keys_of,
    validate_visual_schema,
)

# Tamanho maximo do corpo aceito no salvamento. Um documento no limite de
# elementos com textos longos fica bem abaixo disto; o limite existe para
# um envio absurdo ser recusado antes de virar JSON na memoria.
MAX_CORPO_BYTES = 2 * 1024 * 1024


def _exige(request, permissao):
    if not request.user.has_perm(permissao):
        raise PermissionDenied


def _pode_editar(version):
    """So rascunho se edita. Publicada e inativa sao historico."""
    return version.status == TemplateVersion.Status.DRAFT


def _chaves_de_campo(version):
    """
    As referencias que um elemento pode apontar nesta versao.

    Sao DOIS vocabularios, e os dois valem:

      * as chaves do formulario (`field_schema`) -- o que a pessoa
        preenche no assistente;
      * as chaves do documento -- o que o PDF daquele modelo sabe
        imprimir. Nem todas vem de uma pergunta: `duration_days` e
        calculada e `place` vem do perfil do anfitriao.

    Um layout importado usa o segundo. Recusa-lo aqui inviabilizaria
    a importacao do documento oficial.
    """
    return field_keys_of(version.field_schema) | visual_import.campos_do_documento(
        version.template.slug
    )


# ---------------------------------------------------------------------------
# Lista
# ---------------------------------------------------------------------------


@staff_required
def document_list(request):
    templates = (
        LetterTemplate.objects.prefetch_related(
            Prefetch("versions", queryset=TemplateVersion.objects.order_by("-version_number"))
        )
        .order_by("name", "language")
    )
    return render(
        request,
        "backoffice/documents.html",
        {
            "active": "templates",
            "admin_user": demo.ADMIN,
            "bo_title": _("Documentos"),
            "bo_action_icon": "ph-plus",
            "bo_action_label": _("Novo documento"),
            "templates": templates,
            "pode_editar": request.user.has_perm("doctemplates.change_templateversion"),
            "pode_criar": request.user.has_perm("doctemplates.add_templateversion"),
            "pode_publicar": request.user.has_perm("doctemplates.publish_templateversion"),
        },
    )


# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------


@staff_required
def document_editor(request, version_pk):
    version = get_object_or_404(
        TemplateVersion.objects.select_related("template"), pk=version_pk
    )
    _exige(request, "doctemplates.view_templateversion")

    documento = version.visual_schema or documento_vazio()

    # Os campos que um elemento do tipo `field` pode referenciar saem do
    # `field_schema` DESTA versao -- e o que faz o editor oferecer uma
    # lista em vez de deixar digitar uma referencia qualquer.
    campos = [
        {
            "key": campo.get("key"),
            "label": campo.get("label") or campo.get("key"),
            "type": campo.get("type", ""),
        }
        for campo in (version.field_schema or {}).get("fields", [])
        if isinstance(campo, dict) and campo.get("key")
    ]
    ja_listados = {campo["key"] for campo in campos}
    # Os campos do DOCUMENTO tambem entram no seletor: sao os que um
    # layout importado usa, e sem eles o editor mostraria a referencia
    # como se fosse invalida.
    campos += [
        {"key": chave, "label": chave, "type": "documento"}
        for chave in sorted(visual_import.campos_do_documento(version.template.slug))
        if chave not in ja_listados
    ]

    assets = [
        {
            "id": asset.pk,
            "label": str(asset),
            "url": asset.file.url if asset.file else "",
        }
        for asset in Asset.objects.filter(is_active=True).order_by("kind", "key")
    ]

    editavel = _pode_editar(version) and request.user.has_perm(
        "doctemplates.change_templateversion"
    )

    return render(
        request,
        "backoffice/document_editor.html",
        {
            "active": "templates",
            "admin_user": demo.ADMIN,
            "bo_title": version.template.name,
            "bo_action_icon": "ph-floppy-disk",
            "bo_action_label": _("Salvar"),
            "version": version,
            "editavel": editavel,
            "pode_publicar": (
                version.status == TemplateVersion.Status.DRAFT
                and request.user.has_perm("doctemplates.publish_templateversion")
            ),
            "pode_criar_versao": request.user.has_perm("doctemplates.add_templateversion"),
            # O estado inicial vai para o navegador pelo filtro
            # |json_script do Django, que serializa E escapa -- nunca
            # interpolado dentro de JavaScript, que seria injecao na veia.
            # Por isso vao como OBJETOS: serializar aqui tambem faria o
            # template codificar um JSON dentro de outro.
            "documento_json": documento,
            "campos_json": campos,
            "assets_json": assets,
            "config_json": (
                {
                    "schemaVersion": SCHEMA_VERSION,
                    "pageWidth": A4_WIDTH_PT,
                    "pageHeight": A4_HEIGHT_PT,
                    "elementTypes": list(ELEMENT_TYPES),
                    "alignments": list(ALIGNMENTS),
                    "fontFamilies": list(FONT_FAMILIES),
                    "qrErrorLevels": list(QR_ERROR_LEVELS),
                    "maxElements": MAX_ELEMENTS,
                    "editable": editavel,
                    "saveUrl": reverse("backoffice:document_save", args=[version.pk]),
                }
            ),
        },
    )


# ---------------------------------------------------------------------------
# Acoes
# ---------------------------------------------------------------------------


@staff_required
@require_POST
def document_save(request, version_pk):
    """
    Grava o documento visual. Responde JSON -- e chamado por fetch().

    Nada aqui confia no editor: o corpo e revalidado inteiro, a permissao
    e reconferida e o status da versao e checado de novo.
    """
    version = get_object_or_404(TemplateVersion, pk=version_pk)
    _exige(request, "doctemplates.change_templateversion")

    if not _pode_editar(version):
        return JsonResponse(
            {"ok": False, "error": _("Uma versão publicada não pode ser editada.")},
            status=409,
        )

    if len(request.body) > MAX_CORPO_BYTES:
        return JsonResponse(
            {"ok": False, "error": _("O documento é grande demais.")}, status=413
        )

    try:
        documento = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": _("JSON inválido.")}, status=400)

    try:
        validate_visual_schema(
            documento,
            field_keys=_chaves_de_campo(version),
            asset_ids=set(
                Asset.objects.filter(is_active=True).values_list("pk", flat=True)
            ),
        )
    except ValidationError as erro:
        return JsonResponse(
            {"ok": False, "error": " ".join(erro.messages)}, status=400
        )

    version.visual_schema = documento
    version.save(update_fields=["visual_schema", "updated_at"])

    return JsonResponse(
        {
            "ok": True,
            "elementos": len(documento.get("elements", [])),
            "atualizado_em": version.updated_at.isoformat(),
        }
    )


@staff_required
@require_POST
def document_publish(request, version_pk):
    version = get_object_or_404(TemplateVersion, pk=version_pk)
    _exige(request, "doctemplates.publish_templateversion")

    try:
        # Publicar congela o layout: revalidar agora, ligado ao banco, e a
        # ultima chance de impedir um documento quebrado de virar imutavel.
        # `para_publicar` aperta a regra -- nada de campo sem referencia,
        # imagem sem arquivo ou QR sem conteudo num documento definitivo.
        validate_visual_schema(
            version.visual_schema,
            field_keys=_chaves_de_campo(version),
            asset_ids=set(
                Asset.objects.filter(is_active=True).values_list("pk", flat=True)
            ),
            para_publicar=True,
        )
        version.publish()
    except ValidationError as erro:
        messages.error(
            request,
            _("O documento não pode ser publicado: %(motivo)s")
            % {"motivo": " ".join(erro.messages)},
        )
    except TemplateVersionImmutableError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(
            request,
            _("Versão %(n)s publicada.") % {"n": version.version_number},
        )

    return redirect("backoffice:document_editor", version_pk=version.pk)


@staff_required
@require_POST
def document_import_official(request, version_pk):
    """
    Traz o layout do documento oficial para dentro deste rascunho.

    E DESTRUTIVO -- substitui o que estiver la. A confirmacao acontece no
    navegador; aqui o que importa e que a acao so alcance um rascunho, e
    so de quem pode editar.
    """
    version = get_object_or_404(
        TemplateVersion.objects.select_related("template"), pk=version_pk
    )
    _exige(request, "doctemplates.change_templateversion")

    if not _pode_editar(version):
        messages.error(
            request,
            _("Uma versão publicada não pode ser alterada. Crie uma nova versão."),
        )
        return redirect("backoffice:document_editor", version_pk=version.pk)

    try:
        documento = visual_import.importar_modelo_oficial(version)
    except ValueError as erro:
        messages.error(request, str(erro))
    except (ValidationError, OSError) as erro:
        messages.error(
            request,
            _("Não foi possível importar o modelo oficial: %(motivo)s")
            % {"motivo": erro},
        )
    else:
        messages.success(
            request,
            _("Modelo oficial importado: %(n)s elementos.")
            % {"n": len(documento["elements"])},
        )

    return redirect("backoffice:document_editor", version_pk=version.pk)


@staff_required
@require_POST
def document_new_version(request, version_pk):
    """
    Cria o proximo rascunho a partir desta versao e abre o editor nele.

    E o caminho para "editar" uma versao publicada sem violar a
    imutabilidade.
    """
    version = get_object_or_404(TemplateVersion, pk=version_pk)
    _exige(request, "doctemplates.add_templateversion")

    nova = version.create_next_version()
    messages.success(
        request,
        _("Versão %(n)s criada em rascunho, a partir da v%(origem)s.")
        % {"n": nova.version_number, "origem": version.version_number},
    )
    return redirect("backoffice:document_editor", version_pk=nova.pk)
