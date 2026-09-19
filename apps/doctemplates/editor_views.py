"""
Editor rico dos modelos da biblioteca (Etapa 3.2; editor rico na 3.7).

    GET  backoffice/modelos/<pk>/editar/        abre o editor
    POST backoffice/modelos/<pk>/salvar/        grava o layout
    POST backoffice/modelos/<pk>/ids/           mais ids para elementos novos
    POST backoffice/modelos/<pk>/previa/        o PDF do layout em edicao

E o unico editor de documentos do produto desde a Etapa 3.5.3, que
aposentou o editor visual da 4.2A/4.2C e a tela que o servia. Desde a
Etapa 3.7 e um editor de TEXTO RICO sobre o mesmo layout: a tela e a do
arquivo de design "Editor Carta Estatico" (cabecalho, barra de
ferramentas em duas linhas, campos do banco a esquerda, folha A4 no
centro, opcoes do documento a direita; abas Texto/Campos/Documento no
celular), e o que ela grava continua sendo o `layout` estrutural.

A PREVIA NAO E O PDF DA CARTA
-----------------------------
`template_editor_preview` desenha o layout que esta NA TELA (ainda nao
salvo) com os dados de amostra de `services.dados_de_exemplo`, pelo
mesmo `render_layout` que gera as cartas. O navegador nunca gera PDF:
ele manda o layout e recebe os bytes. Nada e gravado.


O SERVIDOR E A AUTORIDADE
-------------------------
O editor esconde controles conforme o estado do modelo, mas esconder nao
e proteger: o salvamento reconfere tudo do lado de ca -- se o modelo
aceita edicao, se o corpo e JSON, e se o layout cumpre o contrato da
Etapa 3.1. O JavaScript nunca decide se algo pode ser gravado.

E o endpoint le APENAS `layout` (e, desde o editor rico, o `language`
do painel "Idioma do modelo", conferido contra `settings.LANGUAGES`) do
corpo. `type`, `is_system`, `is_locked`, `slug`, `name`,
`duplicated_from`, `created_by` e `field_schema` nao tem por onde
chegar: nao sao lidos, nao sao escritos. A protecao vem de nao existir
caminho, nao de uma lista de campos proibidos que alguem possa esquecer
de atualizar.


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

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.content.models import Asset
from apps.doctemplates.library_views import ADMINISTRAR_PERM, VER_PERM, exige_permissao

from . import datasources, elements, layout_schema
from .models import DocumentTemplate, DocumentTemplateLockedError
from .services import biblioteca, carta_convite, dados_de_exemplo
from .services import layout as servico_de_layout
from .services import pdf as servico_de_pdf

# As tres margens que o painel "Margens" oferece, em milimetros -- as do
# arquivo de design. O layout guarda pontos; a conversao e 72/25.4.
MARGENS_MM = (("normal", 25), ("estreita", 15), ("ampla", 35))
PT_POR_MM = 72 / 25.4

# Tamanho maximo do corpo aceito no salvamento. Um layout no limite de
# elementos fica bem abaixo disto; o limite existe para um envio absurdo
# ser recusado antes de virar JSON na memoria.
MAX_CORPO_BYTES = 2 * 1024 * 1024

# Quantos ids a pagina leva de antemao. Uma sessao de edicao real usa
# uma fracao disto; e barato e evita ida ao servidor a cada insercao.
IDS_POR_LOTE = 200


def _pode_editar(modelo):
    """
    Destravado edita; travado so le -- oficial ou nao.

    Ate a Rodada 18 um oficial (`is_system`) abria em leitura mesmo
    destravado, e o ajuste passava por uma copia. Agora o que decide e
    so `is_locked`: o oficial destravado se edita direto (o cliente
    ajusta texto e logo na homologacao) e, aprovado, e TRAVADO -- dai
    em diante, so leitura. As regras de verdade estao em
    `DocumentTemplate.save()`; aqui a checagem existe para a tela abrir
    no modo certo e para o salvamento recusar antes de tentar.
    """
    return not modelo.is_locked


def _motivo_da_leitura(modelo, user=None):
    if user is not None and not user.has_perm(ADMINISTRAR_PERM):
        return _(
            "Você pode consultar este modelo, mas não tem permissão para alterá-lo."
        )
    if modelo.is_locked:
        return _(
            "Este modelo está travado. Para alterá-lo, destrave-o na administração "
            "ou duplique-o — a cópia nasce editável."
        )
    return ""


def _lote_de_ids(quantos=IDS_POR_LOTE):
    return [servico_de_layout.novo_id() for _ in range(quantos)]


def _layout_padrao(modelo):
    """
    O layout que "Restaurar modelo padrao" devolve ao editor, ou None.

    Uma copia volta ao modelo de que foi duplicada; um modelo da Carta
    Convite sem origem volta ao oficial do seu idioma (montado pelo
    mesmo servico que semeia os oficiais, com o logo que o layout atual
    ja referencia). Fora disso nao ha "padrao" a que voltar -- e o botao
    nem aparece.
    """
    origem = modelo.duplicated_from
    if origem is not None and (origem.layout or {}).get("elements"):
        return origem.layout
    if (
        modelo.type.code == biblioteca.CODIGO_CARTA_CONVITE
        and modelo.language in carta_convite.IDIOMAS
    ):
        assets = layout_schema.assets_referenciados(modelo.layout or {})
        return carta_convite.layout(
            modelo.language, asset_do_logo=min(assets) if assets else 0
        )
    return None


def _idiomas():
    return [{"code": codigo, "label": str(nome)} for codigo, nome in settings.LANGUAGES]


def _margens():
    return [
        {"key": chave, "mm": mm, "pt": round(mm * PT_POR_MM, 4)} for chave, mm in MARGENS_MM
    ]


def _faixa_da_bandeira():
    """
    As medidas da faixa tricolor do documento oficial, para o interruptor
    "Faixa da bandeira no topo" desenhar a mesma faixa dos oficiais. Vem
    de `carta_convite`, a unica fonte dessas medidas.
    """
    return {
        "x": carta_convite.FAIXA_X,
        "width": carta_convite.FAIXA_LARGURA_TOTAL,
        "height": carta_convite.FAIXA_ALTURA,
        "colors": list(carta_convite.FAIXA_CORES),
    }


@exige_permissao(VER_PERM)
def template_editor(request, pk):
    """
    A tela do editor.

    VER exige `doctemplates.view_documenttemplate`; SALVAR exige
    `change_documenttemplate` (ver `template_editor_save`). Quem so
    pode ver abre em leitura -- a mesma tela, sem a possibilidade de
    gravar, em vez de um 403 que esconderia o documento de quem tem
    direito de consulta.
    """
    modelo = get_object_or_404(
        DocumentTemplate.objects.select_related("type", "created_by"), pk=pk
    )
    # Duas condicoes: o MODELO aceita edicao, e a PESSOA pode
    # administrar. Faltando qualquer uma, a tela abre em leitura.
    editavel = _pode_editar(modelo) and request.user.has_perm(ADMINISTRAR_PERM)

    layout_padrao = _layout_padrao(modelo) if editavel else None

    return render(
        request,
        "backoffice/template_editor.html",
        {
            "active": "templates",
            "bo_title": modelo.name,
            "modelo": modelo,
            "editavel": editavel,
            "motivo_da_leitura": _motivo_da_leitura(modelo, request.user),
            # As DUAS saidas do editor, nesta ordem de proximidade: o
            # modelo (a tela de onde se entra no editor) e a biblioteca
            # (a listagem). Nada aqui volta para o Django Admin: o
            # caminho do produto e biblioteca -> modelo -> editor.
            "voltar_url": reverse("backoffice:document_detail", args=[modelo.pk]),
            "biblioteca_url": reverse("backoffice:document_library"),
            "previa_url": reverse("backoffice:template_editor_preview", args=[modelo.pk]),
            "pode_restaurar": layout_padrao is not None,
            # Estado inicial. Vai pelo filtro |json_script, que serializa E
            # escapa -- nunca interpolado dentro de <script>, o que seria
            # injecao. Por isso sao OBJETOS, nao strings ja serializadas.
            "layout_json": modelo.layout or layout_schema.layout_vazio(),
            "layout_padrao_json": layout_padrao,
            "pagina_json": modelo.type.page,
            "tipos_json": elements.para_o_editor(),
            "fontes_json": datasources.para_o_editor(),
            # Os valores de amostra dos campos ("Ver com dados de exemplo").
            # Nao sao gravados: ficam so na tela.
            "exemplo_json": dados_de_exemplo.para_o_editor(modelo.slug),
            "idiomas_json": _idiomas(),
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
                "language": modelo.language,
                # Para onde "Descartar" sai depois de jogar fora o que
                # nao foi salvo -- a mesma URL do botao "Voltar".
                "backUrl": reverse("backoffice:document_detail", args=[modelo.pk]),
                "saveUrl": reverse("backoffice:template_editor_save", args=[modelo.pk]),
                "idsUrl": reverse("backoffice:template_editor_ids", args=[modelo.pk]),
                "maxElements": layout_schema.MAX_ELEMENTS,
                "layoutVersion": layout_schema.VERSION,
                "fontFamilies": list(elements.FONT_FAMILIES),
                "margins": _margens(),
                "flagStripe": _faixa_da_bandeira(),
            },
        },
    )


@exige_permissao(ADMINISTRAR_PERM)
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

    # O layout e, se vier, o idioma do painel "Idioma do modelo". As
    # regras de `DocumentTemplate.save()` continuam valendo -- nada de
    # `queryset.update()` para contorna-las.
    campos = ["layout", "updated_at"]
    modelo.layout = documento
    if "language" in corpo:
        idioma = corpo["language"]
        if idioma not in dict(settings.LANGUAGES):
            return JsonResponse(
                {"ok": False, "error": _("Idioma desconhecido.")}, status=400
            )
        if idioma != modelo.language:
            modelo.language = idioma
            campos.append("language")
    try:
        modelo.save(update_fields=campos)
    except DocumentTemplateLockedError as erro:
        return JsonResponse({"ok": False, "error": str(erro)}, status=409)

    return JsonResponse(
        {
            "ok": True,
            "elementos": len(documento.get("elements", [])),
            "language": modelo.language,
            "atualizado_em": modelo.updated_at.isoformat(),
        }
    )


@exige_permissao(VER_PERM)
@require_POST
def template_editor_preview(request, pk):
    """
    O PDF do layout que esta na tela, com os dados de amostra.

    Chega por um formulario comum (`layout` e o JSON, `exemplo` liga os
    valores de amostra) aberto numa aba nova -- e o botao "Visualizar".
    Quem so pode VER tambem pode visualizar: o que sai daqui e o
    desenho, com dados ficticios, e nada e gravado. O layout e
    revalidado pelo contrato antes de desenhar, como no salvamento.
    """
    modelo = get_object_or_404(DocumentTemplate.objects.select_related("type"), pk=pk)

    bruto = request.POST.get("layout", "")
    if len(bruto) > MAX_CORPO_BYTES:
        return JsonResponse(
            {"ok": False, "error": _("O layout é grande demais.")}, status=413
        )
    try:
        documento = json.loads(bruto)
        layout_schema.validate_layout(documento)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": _("JSON inválido.")}, status=400)
    except ValidationError as erro:
        return JsonResponse(
            {"ok": False, "error": " ".join(erro.messages)}, status=400
        )
    if not isinstance(documento, dict) or not documento.get("elements"):
        return JsonResponse(
            {"ok": False, "error": _("Não há elementos para desenhar.")}, status=400
        )

    dados = (
        dados_de_exemplo.para_o_editor(modelo.slug)
        if request.POST.get("exemplo") == "1"
        else {}
    )
    contexto = servico_de_pdf.Contexto(dados, estrito=False)
    try:
        conteudo, _relatorio = servico_de_pdf.render_layout(
            documento,
            modelo.type.page,
            contexto,
            assets=servico_de_pdf.carregar_assets(documento),
            validar=False,
        )
    except (
        servico_de_pdf.AssetAusenteError,
        servico_de_pdf.FonteIndisponivelError,
        servico_de_pdf.PaginaInvalidaError,
        servico_de_pdf.CampoDesconhecidoError,
    ) as erro:
        return JsonResponse({"ok": False, "error": str(erro)}, status=400)

    resposta = HttpResponse(conteudo, content_type="application/pdf")
    resposta["Content-Disposition"] = f'inline; filename="{modelo.slug}-previa.pdf"'
    return resposta


@exige_permissao(ADMINISTRAR_PERM)
@require_POST
def template_editor_ids(request, pk):
    """Outro lote de ids, para uma sessao que esgotou o primeiro."""
    modelo = get_object_or_404(DocumentTemplate, pk=pk)
    if not _pode_editar(modelo):
        raise PermissionDenied
    return JsonResponse({"ok": True, "ids": _lote_de_ids()})
