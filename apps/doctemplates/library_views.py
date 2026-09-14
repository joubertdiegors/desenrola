"""
Biblioteca de modelos: a gestão administrativa dos `DocumentTemplate`.

    GET  backoffice/modelos/                 a listagem
    GET  backoffice/modelos/<pk>/            o detalhe de um modelo
    POST backoffice/modelos/<pk>/duplicar/   cria uma cópia independente
    POST backoffice/modelos/<pk>/situacao/   ativa ou desativa

Arquivo PRÓPRIO, separado de `editor_views.py` (o editor em si). É a
única biblioteca de modelos do produto.

DUAS PERMISSÕES, AMBAS JÁ EXISTENTES
------------------------------------
`doctemplates.view_documenttemplate` para VER a biblioteca;
`doctemplates.change_documenttemplate` para ADMINISTRAR (duplicar,
ativar/desativar, editar no editor). As duas são as permissões que o
Django cria sozinho para o modelo -- não foi preciso inventar
`manage_templates`: elas já dizem exatamente isso, e reusá-las evita uma
segunda linguagem de permissão para o mesmo assunto.

A migration `doctemplates.0016` concedeu ambas a quem já tinha
`core.access_backoffice`, para a atualização não trancar ninguém fora de
uma tela que já usava.

NÃO EXISTE EXCLUSÃO
-------------------
A biblioteca não apaga modelo nenhum -- nem comum, nem cópia. Um modelo
pode ter cartas apontando para ele (`Letter.document_template`, PROTECT)
e, mesmo sem nenhuma, sumir com um registro é irreversível onde
desativar resolve: o modelo sai das opções de carta nova e todo o
histórico continua reproduzível.

O QUE ESTA VIEW NÃO DECIDE
--------------------------
Quem pode ser editado é `editor_views._pode_editar`; o que um modelo
travado ou oficial aceita mudar é `DocumentTemplate.save()`; como se
duplica é `services.duplicacao`. Esta camada só apresenta e chama.
"""

from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.views import backoffice_required

from .models import DocumentTemplate, DocumentTemplateLockedError, DocumentType
from .services.duplicacao import duplicar_modelo

# As duas permissões desta seção. Constantes, e não strings soltas por
# view e template, para o dia em que alguém procurar "quem decide isto".
VER_PERM = "doctemplates.view_documenttemplate"
ADMINISTRAR_PERM = "doctemplates.change_documenttemplate"

POR_PAGINA = 25


def exige_permissao(permissao):
    """
    Decorador: entrar no Backoffice E ter `permissao`; senão, 403.

    Público de propósito: `editor_views` também o usa -- o editor é a
    outra metade desta seção, e as duas portas são a mesma decisão.

    A porta é no SERVIDOR. Esconder o botão não protege nada -- a URL
    continua sendo digitável, e é o que alguém tentaria.
    """

    def decorador(view):
        @backoffice_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.has_perm(permissao):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorador


def _contexto_do_backoffice(titulo):
    """A casca administrativa. Sem `bo_action_*`: estas telas não têm uma
    ação única de cabeçalho, e o botão do celular só aparece quando há
    uma de verdade (ver `backoffice/base.html`)."""
    return {"active": "templates", "bo_title": titulo}


def pode_administrar(user):
    """Quem pode duplicar, ativar/desativar e salvar no editor."""
    return user.has_perm(ADMINISTRAR_PERM)


# ---------------------------------------------------------------------------
# Listagem
# ---------------------------------------------------------------------------


@exige_permissao(VER_PERM)
def document_library(request):
    """
    A biblioteca: todos os modelos, com o que cada um é e o que se pode
    fazer com ele.

    TODO FILTRO NO BANCO
    --------------------
    Busca, tipo, idioma, situação e natureza viram `WHERE` -- nenhum é
    resolvido em Python sobre a lista inteira. `Count("letters")` também
    vem na mesma consulta, em vez de uma por linha.
    """
    modelos = DocumentTemplate.objects.select_related(
        "type", "duplicated_from", "created_by"
    ).annotate(cartas=Count("letters", distinct=True))

    busca = (request.GET.get("q") or "").strip()
    if busca:
        modelos = modelos.filter(Q(name__icontains=busca) | Q(slug__icontains=busca))

    tipo_id = request.GET.get("type") or ""
    if tipo_id.isdigit():
        modelos = modelos.filter(type_id=int(tipo_id))

    idioma = request.GET.get("language") or ""
    if idioma:
        modelos = modelos.filter(language=idioma)

    ativo = request.GET.get("active") or ""
    if ativo in ("1", "0"):
        modelos = modelos.filter(is_active=(ativo == "1"))

    origem = request.GET.get("system") or ""
    if origem in ("1", "0"):
        modelos = modelos.filter(is_system=(origem == "1"))

    modelos = modelos.order_by("type__order", "type__name", "-is_system", "language", "name")
    pagina = Paginator(modelos, POR_PAGINA).get_page(request.GET.get("page"))

    querystring = request.GET.copy()
    querystring.pop("page", None)

    contexto = _contexto_do_backoffice(_("Modelos"))
    contexto.update(
        {
            "pagina": pagina,
            "querystring": querystring.urlencode(),
            "modelos": pagina.object_list,
            "total": pagina.paginator.count,
            "pode_administrar": pode_administrar(request.user),
            "tipos": DocumentType.objects.order_by("order", "name"),
            "idiomas": DocumentTemplate._meta.get_field("language").choices,
            "filtros": {
                "q": busca,
                "type": tipo_id,
                "language": idioma,
                "active": ativo,
                "system": origem,
            },
        }
    )
    return render(request, "backoffice/document_library.html", contexto)


# ---------------------------------------------------------------------------
# Detalhe
# ---------------------------------------------------------------------------


@exige_permissao(VER_PERM)
def document_detail(request, pk):
    """
    Um modelo por inteiro: identidade, estrutura, origem e o que se pode
    fazer com ele.

    A leitura do LAYOUT (quantos elementos, de que tipos, que campos e
    que assets usa) é resumida aqui uma vez, em vez de o template
    percorrer JSON -- é o mesmo princípio das outras telas: a view
    entrega pronto, o template escolhe o que mostrar.
    """
    from .editor_views import _motivo_da_leitura, _pode_editar

    modelo = get_object_or_404(
        DocumentTemplate.objects.select_related("type", "duplicated_from", "created_by"),
        pk=pk,
    )

    contexto = _contexto_do_backoffice(modelo.name)
    contexto.update(
        {
            "modelo": modelo,
            "estrutura": _resumo_da_estrutura(modelo),
            "assets": _assets_do_modelo(modelo),
            "copias": modelo.duplicates.order_by("name"),
            "cartas": modelo.letters.count(),
            "pode_administrar": pode_administrar(request.user),
            "editavel": _pode_editar(modelo),
            "motivo_da_leitura": _motivo_da_leitura(modelo),
        }
    )
    return render(request, "backoffice/document_detail.html", contexto)


def _resumo_da_estrutura(modelo):
    """
    O que o `layout` tem dentro, em números que uma pessoa entende.

    Os CAMPOS saem de `layout_schema.referencias_usadas()`, a mesma
    função que o renderer usa para montar o contexto do PDF -- e não
    de uma travessia própria daqui. A diferença não é teórica: um
    campo pode estar dentro da célula de uma tabela ou de um pedaço
    de `rich_text`, e uma leitura ingênua de `properties.content`
    deixaria de fora justamente os dados do convidado.
    """
    from .layout_schema import referencias_usadas

    layout = modelo.layout or {}
    elementos = layout.get("elements") or []

    tipos = {}
    for elemento in elementos:
        if not isinstance(elemento, dict):
            continue
        chave = elemento.get("type") or "?"
        tipos[chave] = tipos.get(chave, 0) + 1

    return {
        "elementos": len(elementos),
        "tipos": sorted(tipos.items()),
        "campos": sorted(referencias_usadas(layout)),
        "campos_do_formulario": len((modelo.field_schema or {}).get("fields") or []),
    }


def _assets_do_modelo(modelo):
    """
    Os `content.Asset` que o layout referencia, pela tabela de vínculos
    (`DocumentTemplateAsset`) -- que é derivada do layout a cada
    gravação, e é ela que protege o asset de ser apagado.
    """
    return [
        vinculo.asset
        for vinculo in modelo.asset_links.select_related("asset").order_by("asset__key")
    ]


# ---------------------------------------------------------------------------
# Ações
# ---------------------------------------------------------------------------


@exige_permissao(ADMINISTRAR_PERM)
@require_POST
def document_library_duplicate(request, pk):
    """
    Duplica um modelo -- oficial, comum, travado ou já duplicado, todos
    funcionam: é exatamente o que `duplicar_modelo()` garante.

    Este é o caminho de criação do produto: modelo oficial -> duplicar ->
    editar a cópia. Não há "criar modelo em branco", que começaria com
    uma página vazia e nenhum campo.
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
        return redirect("backoffice:document_detail", pk=origem.pk)

    messages.success(
        request,
        _('"%(nome)s" criado a partir de "%(origem)s". A cópia já pode ser editada.')
        % {"nome": copia.name, "origem": origem.name},
    )
    return redirect("backoffice:template_editor", pk=copia.pk)


@exige_permissao(ADMINISTRAR_PERM)
@require_POST
def document_library_activation(request, pk):
    """
    Ativa ou desativa um modelo. NUNCA apaga.

    Desativado, o modelo sai das opções de carta nova
    (`letters.services.official_document_template` devolve `None` para um
    modelo inativo do idioma, e o assistente avisa em vez de estourar).
    As cartas já emitidas não sentem nada: elas renderizam do
    `document_snapshot` congelado, não do modelo.

    `is_active` é um dos três campos que até um modelo OFICIAL aceita
    mudar (`DocumentTemplate.SYSTEM_MUTABLE_FIELDS`) -- desativar um
    oficial é uma decisão administrativa legítima, e a guarda do modelo
    já a permite sem abrir mão do resto.
    """
    modelo = get_object_or_404(DocumentTemplate, pk=pk)
    ativar = request.POST.get("ativo") == "1"

    if modelo.is_active == ativar:
        messages.info(request, _("Nenhuma alteração a fazer."))
        return redirect("backoffice:document_detail", pk=modelo.pk)

    modelo.is_active = ativar
    try:
        modelo.save(update_fields=["is_active", "updated_at"])
    except DocumentTemplateLockedError as erro:
        # A guarda do modelo é a autoridade; a tela só relata.
        messages.error(request, str(erro))
    else:
        messages.success(
            request,
            _('"%(nome)s" foi ativado.') % {"nome": modelo.name}
            if ativar
            else _('"%(nome)s" foi desativado e não será usado em novas cartas.')
            % {"nome": modelo.name},
        )
    return redirect("backoffice:document_detail", pk=modelo.pk)


def url_da_biblioteca():
    """Para o editor voltar para cá, e não para o Django Admin."""
    return reverse("backoffice:document_library")
