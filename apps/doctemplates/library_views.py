"""
Biblioteca de modelos (Etapa 3.2.1).

    GET  backoffice/modelos/                    lista os DocumentTemplate
    POST backoffice/modelos/<pk>/duplicar/       duplica um modelo
    POST backoffice/modelos/<pk>/excluir/        exclui um modelo comum

Arquivo PROPRIO, separado de `editor_views.py` (o editor em si). E a
unica biblioteca de modelos do produto: a listagem antiga, com
versionamento, foi aposentada na Etapa 3.5.3.

FONTE DE DADOS
--------------
Exclusivamente `DocumentTemplate`: e a unica arquitetura de documentos
do produto.

DUPLICAR
--------
So chama `services.duplicacao.duplicar_modelo()`. Nao ha copia manual de
JSON nem logica de linhagem nesta view -- se o servico decidir algo
diferente (outro criterio de slug, outro campo herdado), a tela nao
precisa mudar.

EXCLUIR
-------
Chama `modelo.delete()` direto, nunca `queryset.delete()`: e o metodo de
instancia que aplica as guardas de `DocumentTemplate` (nunca excluir
`is_system` ou `is_locked`, e o `PROTECT` de quem referenciar o modelo).
Pular para o queryset seria contornar exatamente essas guardas.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.views import backoffice_required

from .models import DocumentTemplate, DocumentTemplateLockedError, DocumentType
from .services.duplicacao import duplicar_modelo


def _pode_excluir(modelo):
    """Mesma regra de `DocumentTemplate.delete()`, para a tela decidir o que mostrar."""
    return not modelo.is_system and not modelo.is_locked


@backoffice_required
def document_library(request):
    """A listagem. Filtros simples por querystring: tipo, idioma, ativo, system."""
    modelos = DocumentTemplate.objects.select_related("type", "duplicated_from")

    tipo_id = request.GET.get("type")
    if tipo_id:
        modelos = modelos.filter(type_id=tipo_id)

    idioma = request.GET.get("language")
    if idioma:
        modelos = modelos.filter(language=idioma)

    ativo = request.GET.get("active")
    if ativo in ("1", "0"):
        modelos = modelos.filter(is_active=(ativo == "1"))

    origem = request.GET.get("system")
    if origem in ("1", "0"):
        modelos = modelos.filter(is_system=(origem == "1"))

    modelos = modelos.order_by("type__order", "type__name", "-is_system", "language", "name")

    return render(
        request,
        "backoffice/document_library.html",
        {
            "active": "templates",
            "bo_title": _("Modelos"),
            "bo_action_icon": "ph-files",
            "bo_action_label": _("Biblioteca"),
            "modelos": modelos,
            "tipos": DocumentType.objects.order_by("order", "name"),
            "idiomas": DocumentTemplate._meta.get_field("language").choices,
            "filtros": {
                "type": tipo_id or "",
                "language": idioma or "",
                "active": ativo or "",
                "system": origem or "",
            },
        },
    )


@backoffice_required
@require_POST
def document_library_duplicate(request, pk):
    """
    Duplica um modelo -- oficial, comum, travado ou ja duplicado, todos
    funcionam: e exatamente o que `duplicar_modelo()` garante.
    """
    origem = get_object_or_404(DocumentTemplate, pk=pk)
    nome = (request.POST.get("name") or "").strip()

    try:
        copia = duplicar_modelo(origem, nome, created_by=request.user)
    except ValidationError as erro:
        detalhe = " ".join(erro.messages) if hasattr(erro, "messages") else str(erro)
        messages.error(
            request,
            _('Não foi possível duplicar "%(origem)s": %(motivo)s')
            % {"origem": origem.name, "motivo": detalhe},
        )
        return redirect("backoffice:document_library")

    messages.success(
        request,
        _('"%(nome)s" criado a partir de "%(origem)s". A cópia já pode ser editada.')
        % {"nome": copia.name, "origem": origem.name},
    )
    return redirect("backoffice:template_editor", pk=copia.pk)


@backoffice_required
@require_POST
def document_library_delete(request, pk):
    """
    Exclui um modelo comum e destravado. Modelos do sistema ou travados
    nunca chegam a esta linha com sucesso -- `modelo.delete()` e quem
    impede, nao esta view.
    """
    modelo = get_object_or_404(DocumentTemplate, pk=pk)
    nome = modelo.name

    try:
        modelo.delete()
    except DocumentTemplateLockedError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, _('"%(nome)s" foi excluído.') % {"nome": nome})

    return redirect("backoffice:document_library")
