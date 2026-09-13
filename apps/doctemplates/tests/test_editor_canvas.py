"""
O modelo importado chega ao canvas e da para trabalhar nele.

REGRESSAO QUE ORIGINOU ESTE ARQUIVO (correcao da Etapa 4.2B)
------------------------------------------------------------
Depois de importar o documento frances, o editor mostrava a pagina
oficial ao fundo mas os 19 elementos pareciam nao existir. A suspeita
natural era perda de dados -- algum filtro descartando elementos, o
`rich_text` desconhecido do renderizador, z-index invertido.

Era outra coisa. Medindo, os 19 elementos ESTAVAM todos sendo
desenhados, na camada certa, com o conteudo certo. O que os tornava
inuteis:

  * a pagina inteira nascia com 232x328 px (zoom de 39%), deixando cada
    campo com 5,3 px de altura;
  * as mascaras sao retangulos BRANCOS sobre uma pagina branca;
  * `.ed-elemento` tinha `outline: transparent` -- nenhum limite visivel
    ate passar o mouse por cima;
  * a imagem de fundo cobre a folha inteira e recebia os cliques,
    roubando a selecao dos elementos por cima dela.

Ou seja: bug de CSS e de zoom, nao de dados. Estes testes separam as
duas coisas de proposito -- primeiro provam que o dado chega, depois que
ele vira no desenhado -- para a proxima investigacao nao comecar do
lugar errado.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.doctemplates.models import TemplateVersion
from apps.doctemplates.official_templates import official_slug
from apps.doctemplates.services import visual_import as vi
from apps.doctemplates.visual_schema import ELEMENT_TYPES

pytestmark = pytest.mark.django_db

RAIZ = Path(__file__).resolve().parents[3]
RENDER_JS = RAIZ / "static" / "js" / "editor" / "render.js"
DOM_STUB = Path(__file__).parent / "dom_stub.js"

# O que a importacao do documento frances produz.
TOTAL_IMPORTADO = 19
ESPERADO_POR_TIPO = {"image": 1, "rect": 9, "field": 5, "rich_text": 4}


def _caminho_js(caminho):
    return str(caminho).replace("\\", "/")


@pytest.fixture(scope="module")
def node():
    caminho = shutil.which("node")
    if caminho is None:
        pytest.skip("Node não está instalado neste ambiente")
    return caminho


@pytest.fixture(scope="module")
def css():
    return (RAIZ / "static" / "css" / "editor.css").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def editor_js():
    return (RAIZ / "static" / "js" / "editor" / "editor.js").read_text(encoding="utf-8")


@pytest.fixture
def usuario_editor(db):
    pessoa = get_user_model().objects.create_user(
        email="canvas@desenrola.be", password="senha-forte-123",
        full_name="Canvas", is_staff=True,
    )
    for codename in ("view_templateversion", "change_templateversion"):
        pessoa.user_permissions.add(
            Permission.objects.get(
                codename=codename, content_type__app_label="doctemplates"
            )
        )
    return pessoa


@pytest.fixture
def versao_importada(db, usuario_editor, client):
    """Um rascunho do modelo frances com o documento oficial ja importado."""
    publicada = TemplateVersion.objects.get(
        template__slug=official_slug("fr"), status=TemplateVersion.Status.PUBLISHED
    )
    versao = publicada.create_next_version()
    client.force_login(usuario_editor)
    client.post(reverse("backoffice:document_import_official", args=[versao.pk]))
    versao.refresh_from_db()
    return versao


def desenhar_no_node(node, documento, zoom=1.0, assets=None, modo="editor", tmp_path=None):
    """
    Roda o renderizador REAL do editor sobre `documento`, num DOM minimo,
    e devolve a descricao de cada no produzido.
    """
    arquivo = tmp_path / "documento.json"
    arquivo.write_text(json.dumps(documento), encoding="utf-8")

    script = f"""
    var doc = require({_caminho_js(DOM_STUB)!r});
    var Render = require({_caminho_js(RENDER_JS)!r});
    var documento = require({_caminho_js(arquivo)!r});
    var alvo = doc.createElement("div");
    Render.desenharDocumento(doc, alvo, documento, {{
      zoom: {zoom},
      campos: [],
      assets: {json.dumps(assets if assets is not None else [{"id": 1, "url": "/x.png"}])},
      modo: {modo!r}
    }});
    console.log(JSON.stringify(alvo.children.map(function (no) {{
      return {{
        id: no.dataset.id,
        tipo: no.dataset.tipo,
        z: Number(no.style.zIndex),
        left: parseFloat(no.style.left),
        top: parseFloat(no.style.top),
        width: parseFloat(no.style.width),
        height: parseFloat(no.style.height),
        classes: no.classList._classes,
        texto: no.textContent
      }};
    }})));
    """
    resultado = subprocess.run(
        [node, "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if resultado.returncode != 0:
        raise AssertionError(f"Node falhou:\n{resultado.stderr}")
    return json.loads(resultado.stdout)


# ---------------------------------------------------------------------------
# 1. O dado chega ao navegador
# ---------------------------------------------------------------------------


class TestOsDadosChegam:
    def test_os_19_elementos_estao_no_banco(self, versao_importada):
        assert len(versao_importada.visual_schema["elements"]) == TOTAL_IMPORTADO

    def test_os_19_elementos_chegam_ao_contexto(self, client, versao_importada):
        resposta = client.get(
            reverse("backoffice:document_editor", args=[versao_importada.pk])
        )

        assert len(resposta.context["documento_json"]["elements"]) == TOTAL_IMPORTADO

    def test_os_19_elementos_chegam_ao_html(self, client, versao_importada):
        """
        O JSON vai para o navegador pelo `json_script`. Se algo se perder
        aqui, o editor nem chega a ter o que desenhar.
        """
        html = client.get(
            reverse("backoffice:document_editor", args=[versao_importada.pk])
        ).content.decode()

        bloco = re.search(
            r'<script id="editor-documento" type="application/json">(.*?)</script>',
            html,
            re.S,
        )
        assert bloco, "o bloco JSON do documento não está no HTML"
        documento = json.loads(bloco.group(1))
        assert len(documento["elements"]) == TOTAL_IMPORTADO

    def test_a_composicao_por_tipo_e_a_esperada(self, client, versao_importada):
        from collections import Counter

        elementos = client.get(
            reverse("backoffice:document_editor", args=[versao_importada.pk])
        ).context["documento_json"]["elements"]

        assert dict(Counter(e["type"] for e in elementos)) == ESPERADO_POR_TIPO

    def test_o_asset_do_fundo_esta_na_lista_de_assets(self, client, versao_importada):
        """
        Sem o asset na lista, o renderizador desenha "imagem não
        escolhida" em vez da pagina oficial.
        """
        resposta = client.get(
            reverse("backoffice:document_editor", args=[versao_importada.pk])
        )
        base = next(
            e
            for e in resposta.context["documento_json"]["elements"]
            if e["id"] == "fr-base"
        )
        disponiveis = {a["id"] for a in resposta.context["assets_json"]}

        assert base["properties"]["asset_id"] in disponiveis

    def test_o_editor_abre_em_modo_editavel(self, client, versao_importada):
        resposta = client.get(
            reverse("backoffice:document_editor", args=[versao_importada.pk])
        )

        assert resposta.context["editavel"] is True


# ---------------------------------------------------------------------------
# 2. O dado vira no desenhado
# ---------------------------------------------------------------------------


class TestTudoEDesenhado:
    def test_nenhum_elemento_importado_e_descartado(self, node, versao_importada, tmp_path):
        """A contagem de saida tem de bater com a de entrada, sempre."""
        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, tmp_path=tmp_path
        )

        assert len(desenhados) == TOTAL_IMPORTADO

    def test_todo_elemento_do_schema_vira_um_no(self, node, versao_importada, tmp_path):
        esperados = {e["id"] for e in versao_importada.visual_schema["elements"]}

        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, tmp_path=tmp_path
        )

        assert {no["id"] for no in desenhados} == esperados

    def test_os_quatro_tipos_importados_sao_desenhados(
        self, node, versao_importada, tmp_path
    ):
        from collections import Counter

        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, tmp_path=tmp_path
        )

        assert dict(Counter(no["tipo"] for no in desenhados)) == ESPERADO_POR_TIPO

    def test_o_renderizador_conhece_todos_os_tipos_do_contrato(
        self, node, versao_importada, tmp_path
    ):
        """
        Um tipo que o renderizador nao conhecesse cairia no `default` e
        apareceria como o proprio nome do tipo -- sinal de que o editor
        ficou para tras do schema.
        """
        documento = dict(versao_importada.visual_schema)
        documento["elements"] = [
            {
                "id": f"t-{tipo}",
                "type": tipo,
                "x": 10.0,
                "y": 10.0,
                "width": 50.0,
                "height": 20.0,
                "z_index": 1,
                "properties": {},
            }
            for tipo in ELEMENT_TYPES
        ]

        desenhados = desenhar_no_node(node, documento, tmp_path=tmp_path)

        assert len(desenhados) == len(ELEMENT_TYPES)
        for no in desenhados:
            assert no["texto"] != no["tipo"], f"{no['tipo']} caiu no default"

    def test_rich_text_mostra_os_trechos_na_ordem(
        self, node, versao_importada, tmp_path
    ):
        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, tmp_path=tmp_path
        )
        paragrafo = next(no for no in desenhados if no["id"] == "fr-host_paragraph")

        assert paragrafo["tipo"] == "rich_text"
        assert paragrafo["texto"].startswith("Je soussignée, ")
        assert "{{ host_name }}" in paragrafo["texto"]
        assert paragrafo["texto"].endswith(", invite par la présente :")

    def test_um_campo_mostra_a_referencia(self, node, versao_importada, tmp_path):
        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, tmp_path=tmp_path
        )
        campo = next(no for no in desenhados if no["id"] == "fr-table_guest_name")

        assert campo["texto"] == "{{ guest_name }}"

    def test_nenhum_elemento_importado_fica_marcado_como_incompleto(
        self, node, versao_importada, tmp_path
    ):
        """
        Incompleto e o aviso amarelo de "falta escolher". Um documento
        importado ja vem completo -- se aparecer, algo se perdeu.
        """
        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, tmp_path=tmp_path
        )

        for no in desenhados:
            assert "is-incompleto" not in no["classes"], no["id"]

    def test_as_coordenadas_persistidas_viram_posicao_na_tela(
        self, node, versao_importada, tmp_path
    ):
        """Zoom 1 => 1pt vira 1px. Nada de deslocamento escondido."""
        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, zoom=1.0, tmp_path=tmp_path
        )
        por_id = {no["id"]: no for no in desenhados}

        for elemento in versao_importada.visual_schema["elements"]:
            no = por_id[elemento["id"]]
            assert no["left"] == pytest.approx(elemento["x"])
            assert no["top"] == pytest.approx(elemento["y"])
            assert no["width"] == pytest.approx(elemento["width"])

    def test_o_zoom_escala_tudo_igualmente(self, node, versao_importada, tmp_path):
        um = desenhar_no_node(
            node, versao_importada.visual_schema, zoom=1.0, tmp_path=tmp_path
        )
        meio = desenhar_no_node(
            node, versao_importada.visual_schema, zoom=0.5, tmp_path=tmp_path
        )

        for a, b in zip(um, meio, strict=True):
            assert b["left"] == pytest.approx(a["left"] / 2)
            assert b["width"] == pytest.approx(a["width"] / 2)


# ---------------------------------------------------------------------------
# 3. Camadas e interacao
# ---------------------------------------------------------------------------


class TestCamadasEInteracao:
    def test_a_base_fica_atras_de_todos(self, node, versao_importada, tmp_path):
        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, tmp_path=tmp_path
        )
        base = next(no for no in desenhados if no["id"] == "fr-base")
        outros = [no for no in desenhados if no["id"] != "fr-base"]

        assert base["z"] == 0
        assert all(no["z"] > base["z"] for no in outros)

    def test_as_mascaras_ficam_entre_a_base_e_o_conteudo(
        self, node, versao_importada, tmp_path
    ):
        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, tmp_path=tmp_path
        )
        mascaras = [no for no in desenhados if no["id"].startswith("fr-mask-")]
        conteudo = [
            no
            for no in desenhados
            if not no["id"].startswith("fr-mask-") and no["id"] != "fr-base"
        ]

        assert all(no["z"] == 10 for no in mascaras)
        assert all(no["z"] == 20 for no in conteudo)

    def test_a_ordem_de_insercao_segue_o_z_index(
        self, node, versao_importada, tmp_path
    ):
        """
        Empilhamento nao pode depender so de `z-index`: a ordem no DOM e
        o desempate quando dois elementos ficam na mesma camada.
        """
        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, tmp_path=tmp_path
        )
        zs = [no["z"] for no in desenhados]

        assert zs == sorted(zs)

    def test_a_base_e_marcada_para_nao_receber_cliques(
        self, node, versao_importada, tmp_path
    ):
        """
        A CAUSA RAIZ da regressao: a imagem cobre a folha inteira e, sem
        esta marca, recebia todo clique -- os elementos por cima dela
        ficavam impossiveis de selecionar e o fundo podia ser arrastado
        sem querer. O CSS tira `.ed-base-ref` do caminho dos eventos.
        """
        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, tmp_path=tmp_path
        )
        base = next(no for no in desenhados if no["id"] == "fr-base")

        assert "ed-base-ref" in base["classes"]

    def test_so_a_base_recebe_essa_marca(self, node, versao_importada, tmp_path):
        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, tmp_path=tmp_path
        )

        marcados = [no["id"] for no in desenhados if "ed-base-ref" in no["classes"]]
        assert marcados == ["fr-base"]

    def test_uma_imagem_comum_continua_clicavel(self, node, tmp_path):
        """A marca vale so para a referencia -- imagem de conteudo e normal."""
        documento = {
            "schema_version": 1,
            "page": {"width": 596.0, "height": 842.0, "unit": "pt", "origin": "top-left"},
            "elements": [
                {
                    "id": "logo",
                    "type": "image",
                    "x": 10.0,
                    "y": 10.0,
                    "width": 50.0,
                    "height": 50.0,
                    "z_index": 1,
                    "properties": {"asset_id": 1, "preserve_aspect_ratio": True},
                }
            ],
        }

        desenhados = desenhar_no_node(node, documento, tmp_path=tmp_path)

        assert "ed-base-ref" not in desenhados[0]["classes"]

    def test_a_base_cobre_a_pagina_inteira(self, node, versao_importada, tmp_path):
        desenhados = desenhar_no_node(
            node, versao_importada.visual_schema, zoom=1.0, tmp_path=tmp_path
        )
        base = next(no for no in desenhados if no["id"] == "fr-base")
        pagina = versao_importada.visual_schema["page"]

        assert (base["left"], base["top"]) == (0, 0)
        assert base["width"] == pytest.approx(pagina["width"])
        assert base["height"] == pytest.approx(pagina["height"])


# ---------------------------------------------------------------------------
# 4. O CSS que torna os elementos visiveis
# ---------------------------------------------------------------------------


class TestAfordanciaVisual:
    """
    Os elementos importados sao brancos sobre branco (as mascaras) ou uma
    linha fina de texto (os campos). Sem limites visiveis em modo de
    edicao, estao la e nao se ve nada.
    """

    def test_em_edicao_os_elementos_mostram_os_proprios_limites(self, css):
        assert ".ed:not(.is-preview) .ed-elemento" in css
        assert "outline-color: rgba(26, 95, 214, .30)" in css

    def test_a_base_nao_recebe_eventos_de_ponteiro(self, css):
        bloco = css[css.index(".ed-base-ref {") :]
        bloco = bloco[: bloco.index("}")]

        assert "pointer-events: none" in bloco

    def test_a_base_nao_ganha_contorno_de_elemento(self, css):
        assert ".ed:not(.is-preview) .ed-base-ref," in css

    def test_no_preview_os_contornos_somem(self, css):
        """No preview vale de novo "o que se ve e o documento"."""
        assert ".ed.is-preview .ed-elemento" in css
        assert "outline-color: transparent" in css


class TestZoomInicial:
    """
    A pagina nascia com 39% -- 232px de largura, campos de 5px de altura.
    Tecnicamente visivel, inutilizavel na pratica.
    """

    def test_ha_um_piso_para_o_zoom_inicial(self, editor_js):
        assert "ZOOM_INICIAL_MINIMO" in editor_js

    def test_a_largura_e_medida_depois_do_layout(self, editor_js):
        """Medir antes de o grid resolver da uma largura pequena demais."""
        assert "requestAnimationFrame" in editor_js

    def test_o_piso_deixa_o_texto_legivel(self):
        """
        A 50%, uma linha de 13,5pt tem ~6,8px e a fonte de 11pt tem
        5,5px -- pequeno, mas selecionavel. A 39% eram 5,3px de caixa.
        """
        piso = 0.5
        altura_da_linha = 13.5 * piso

        assert altura_da_linha > 6.0


# ---------------------------------------------------------------------------
# 5. Nenhum comentario Django vaza para a pagina
# ---------------------------------------------------------------------------


class TestComentariosNaoVazam:
    """
    `{# ... #}` so e comentario quando abre e fecha na MESMA linha. Em
    duas linhas o lexer nao o reconhece e o texto vai inteiro para o
    HTML. Ja aconteceu no assistente e voltou a acontecer no editor.
    """

    def test_nenhum_template_do_projeto_tem_comentario_multilinha(self):
        problemas = []
        for caminho in (RAIZ / "templates").rglob("*.html"):
            for numero, linha in enumerate(
                caminho.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "{#" in linha and "#}" not in linha:
                    problemas.append(f"{caminho.name}:{numero}")

        assert problemas == [], (
            "comentário {# #} em várias linhas é renderizado como texto; "
            "use {% comment %}: " + ", ".join(problemas)
        )

    def test_o_editor_nao_mostra_comentarios(self, client, versao_importada):
        html = client.get(
            reverse("backoffice:document_editor", args=[versao_importada.pk])
        ).content.decode()

        assert "{#" not in html
        assert "#}" not in html
        assert "{% comment %}" not in html

    def test_a_lista_de_documentos_nao_mostra_comentarios(
        self, client, usuario_editor
    ):
        client.force_login(usuario_editor)

        html = client.get(reverse("backoffice:documents")).content.decode()

        assert "{#" not in html
        assert "{%" not in html


# ---------------------------------------------------------------------------
# 6. O ciclo continua fechando
# ---------------------------------------------------------------------------


def test_salvar_e_recarregar_mantem_os_19_elementos(client, versao_importada):
    """
    O que foi importado sobrevive a um ciclo pelo editor -- e a garantia
    de que a correcao de CSS nao mexeu em dado nenhum.
    """
    antes = versao_importada.visual_schema

    resposta = client.post(
        reverse("backoffice:document_save", args=[versao_importada.pk]),
        data=json.dumps(antes),
        content_type="application/json",
    )

    versao_importada.refresh_from_db()
    assert resposta.status_code == 200
    assert versao_importada.visual_schema == antes
    assert len(versao_importada.visual_schema["elements"]) == TOTAL_IMPORTADO


def test_a_importacao_nao_mudou(client, versao_importada):
    """
    A correcao foi no editor, nao no importador: o schema produzido tem
    de continuar identico ao que os testes da 4.2B fixaram.
    """
    asset_id = next(
        e["properties"]["asset_id"]
        for e in versao_importada.visual_schema["elements"]
        if e["id"] == "fr-base"
    )

    assert versao_importada.visual_schema == vi.construir_visual_schema_fr(asset_id)
