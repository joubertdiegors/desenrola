"""
Importacao do modelo oficial frances para o editor visual (Etapa 4.2B).

O criterio que guia tudo aqui: NADA pode ter sido inventado. Cada
coordenada que sai da importacao tem de ser exatamente a que esta em
`pdfengine/layouts/carta_convite_fr.py` -- o mapa medido do PDF oficial.
Por isso os testes comparam contra o mapa, nao contra numeros escritos a
mao: se alguem "ajustar" um valor na importacao, o teste acusa.
"""

import pytest
from django.urls import reverse

from apps.content.models import Asset
from apps.doctemplates.models import TemplateVersion
from apps.doctemplates.official_templates import official_slug
from apps.doctemplates.services import visual_import as vi
from apps.doctemplates.visual_schema import validate_visual_schema
from pdfengine.layouts import carta_convite_fr as mapa_fr
from pdfengine.layouts.carta_convite_fr import FieldRef

from .test_editor_views import _salvar, _usuario, documento_com_texto  # noqa: F401

pytestmark = pytest.mark.django_db

# `asset_id` de mentira para os testes que so olham a estrutura: a
# rasterizacao e testada a parte, e nao precisa rodar 20 vezes.
ASSET_FALSO = 1


@pytest.fixture
def versao_fr(db):
    """O rascunho da proxima versao do modelo oficial FRANCES."""
    publicada = TemplateVersion.objects.get(
        template__slug=official_slug("fr"), status=TemplateVersion.Status.PUBLISHED
    )
    return publicada.create_next_version()


@pytest.fixture
def documento_fr():
    return vi.construir_visual_schema_fr(ASSET_FALSO)


def _por_id(documento, identificador):
    for elemento in documento["elements"]:
        if elemento["id"] == identificador:
            return elemento
    raise AssertionError(f"elemento {identificador} não está no documento")


# ---------------------------------------------------------------------------
# 1. O schema produzido
# ---------------------------------------------------------------------------


class TestSchemaProduzido:
    def test_o_resultado_e_valido(self, documento_fr):
        validate_visual_schema(
            documento_fr, field_keys=set(vi.CAMPOS_DO_DOCUMENTO_FR), asset_ids={ASSET_FALSO}
        )

    def test_a_pagina_e_a_do_documento_oficial(self, documento_fr):
        page = documento_fr["page"]

        assert page["width"] == mapa_fr.PAGE_WIDTH == 596.0
        assert page["height"] == mapa_fr.PAGE_HEIGHT == 842.0
        assert page["unit"] == "pt"
        assert page["origin"] == "top-left"

    def test_ha_um_elemento_para_cada_coisa_do_mapa(self, documento_fr):
        """Uma base + uma mascara por zona + um conteudo por zona."""
        esperado = 1 + 2 * len(mapa_fr.ZONES)

        assert len(documento_fr["elements"]) == esperado

    def test_os_ids_sao_unicos(self, documento_fr):
        ids = [elemento["id"] for elemento in documento_fr["elements"]]

        assert len(ids) == len(set(ids))

    def test_os_ids_derivam_da_zona_e_nao_de_uuid(self, documento_fr):
        """
        Ids estaveis sao o que torna a reimportacao comparavel: com UUID,
        todo reimport pareceria um documento diferente.
        """
        ids = {elemento["id"] for elemento in documento_fr["elements"]}

        assert "fr-base" in ids
        for zone in mapa_fr.ZONES:
            assert f"fr-{zone.key}" in ids
            assert f"fr-mask-{zone.key}" in ids

    def test_todo_elemento_cabe_na_pagina(self, documento_fr):
        largura = documento_fr["page"]["width"]
        altura = documento_fr["page"]["height"]

        for elemento in documento_fr["elements"]:
            assert elemento["x"] >= 0
            assert elemento["y"] >= 0
            assert elemento["x"] + elemento["width"] <= largura + 0.01
            assert elemento["y"] + elemento["height"] <= altura + 0.01


# ---------------------------------------------------------------------------
# 2. Coordenadas: batem com o mapa, sem excecao
# ---------------------------------------------------------------------------


class TestCoordenadasPreservadas:
    @pytest.mark.parametrize("zone", mapa_fr.ZONES, ids=lambda z: z.key)
    def test_a_mascara_bate_exatamente_com_o_mapa(self, documento_fr, zone):
        """
        Mesma area, so que ancorada em cima. O X e a largura nao mudam; o
        Y vira `altura_da_pagina - y - height`.
        """
        elemento = _por_id(documento_fr, f"fr-mask-{zone.key}")

        assert elemento["x"] == zone.mask.x
        assert elemento["width"] == zone.mask.width
        assert elemento["height"] == zone.mask.height
        assert elemento["y"] == pytest.approx(
            mapa_fr.PAGE_HEIGHT - zone.mask.y - zone.mask.height
        )

    @pytest.mark.parametrize("zone", mapa_fr.ZONES, ids=lambda z: z.key)
    def test_a_caixa_de_texto_bate_com_o_mapa(self, documento_fr, zone):
        elemento = _por_id(documento_fr, f"fr-{zone.key}")

        assert elemento["x"] == zone.box.x
        assert elemento["width"] == zone.box.width
        # A altura e a area que o renderer reserva: linhas x entrelinha.
        assert elemento["height"] == pytest.approx(
            zone.box.max_lines * zone.box.leading
        )

    @pytest.mark.parametrize("zone", mapa_fr.ZONES, ids=lambda z: z.key)
    def test_a_linha_de_base_original_fica_guardada(self, documento_fr, zone):
        """
        O editor ancora pelo topo; o renderer, pela linha de base. Guardar
        a linha de base evita que a Etapa 4.2D tenha de refazer a conta do
        ascent ao contrario -- e que um arredondamento no meio desloque o
        texto.
        """
        elemento = _por_id(documento_fr, f"fr-{zone.key}")

        assert elemento["properties"]["first_baseline_y"] == zone.box.first_baseline_y

    @pytest.mark.parametrize("zone", mapa_fr.ZONES, ids=lambda z: z.key)
    def test_o_topo_sai_da_linha_de_base_menos_o_ascent(self, documento_fr, zone):
        """A conversao usa a metrica da fonte real, nao um chute."""
        elemento = _por_id(documento_fr, f"fr-{zone.key}")
        ascent = vi._ascent(zone.box.font_size)

        esperado = mapa_fr.PAGE_HEIGHT - zone.box.first_baseline_y - ascent
        assert elemento["y"] == pytest.approx(esperado)

    def test_as_casas_decimais_nao_sao_arredondadas(self, documento_fr):
        paragrafo = _por_id(documento_fr, "fr-host_paragraph")

        assert paragrafo["x"] == mapa_fr.BODY_LEFT == 49.6
        assert paragrafo["width"] == pytest.approx(mapa_fr.BODY_RIGHT - mapa_fr.BODY_LEFT)

    def test_a_conversao_de_y_e_reversivel(self, documento_fr):
        """Voltar ao sistema do PDF tem de devolver o numero do mapa."""
        from apps.doctemplates.coordinates import para_coordenadas_pdf

        for zone in mapa_fr.ZONES:
            elemento = _por_id(documento_fr, f"fr-mask-{zone.key}")
            volta = para_coordenadas_pdf(elemento, altura_da_pagina=mapa_fr.PAGE_HEIGHT)

            assert volta["y"] == pytest.approx(zone.mask.y)


# ---------------------------------------------------------------------------
# 3. Campos variaveis e textos fixos
# ---------------------------------------------------------------------------


class TestCamposETextos:
    def test_uma_zona_de_campo_unico_vira_field(self, documento_fr):
        elemento = _por_id(documento_fr, "fr-table_guest_name")

        assert elemento["type"] == "field"
        assert elemento["properties"]["field"] == "guest_name"

    def test_uma_zona_mista_vira_rich_text(self, documento_fr):
        elemento = _por_id(documento_fr, "fr-host_paragraph")

        assert elemento["type"] == "rich_text"
        assert len(elemento["properties"]["runs"]) == len(
            mapa_fr.ZONES[0].runs
        )

    @pytest.mark.parametrize("zone", mapa_fr.ZONES, ids=lambda z: z.key)
    def test_a_sequencia_de_trechos_e_preservada(self, documento_fr, zone):
        """
        Texto fixo continua texto fixo, campo continua campo, na mesma
        ordem. Trocar um pelo outro mudaria o documento oficial.
        """
        elemento = _por_id(documento_fr, f"fr-{zone.key}")

        if elemento["type"] == "field":
            assert len(zone.runs) == 1
            assert isinstance(zone.runs[0], FieldRef)
            assert elemento["properties"]["field"] == zone.runs[0].key
            return

        for trecho, original in zip(
            elemento["properties"]["runs"], zone.runs, strict=True
        ):
            if isinstance(original, FieldRef):
                assert trecho["field"] == original.key
                assert "text" not in trecho
            else:
                assert trecho["text"] == original.text
                assert "field" not in trecho
            assert trecho["bold"] == original.bold

    def test_nenhum_valor_real_de_carta_entra_no_schema(self, documento_fr):
        """
        O modelo guarda referencias, nunca dados de uma pessoa. Os nomes
        de amostra do PDF oficial nao podem ter vazado para ca.
        """
        import json

        texto = json.dumps(documento_fr, ensure_ascii=False)

        for amostra in ("Carlos Eduardo", "Claire Dubois", "YY000000", "Woluwe"):
            assert amostra not in texto

    def test_todos_os_campos_do_documento_sao_usados(self, documento_fr):
        usados = set()
        for elemento in documento_fr["elements"]:
            props = elemento["properties"]
            if elemento["type"] == "field":
                usados.add(props["field"])
            for trecho in props.get("runs", []):
                if trecho.get("field"):
                    usados.add(trecho["field"])

        assert usados == set(mapa_fr.REQUIRED_FIELDS)

    def test_o_texto_legal_continua_texto_fixo(self, documento_fr):
        """
        "Je soussignée, " e do documento oficial -- nao pode virar campo
        so porque esta perto de um.
        """
        trechos = _por_id(documento_fr, "fr-host_paragraph")["properties"]["runs"]

        assert trechos[0] == {"text": "Je soussignée, ", "bold": False}
        assert trechos[-1]["text"] == ", invite par la présente :"

    def test_o_negrito_do_mapa_e_respeitado(self, documento_fr):
        trechos = _por_id(documento_fr, "fr-host_paragraph")["properties"]["runs"]
        por_campo = {t["field"]: t for t in trechos if t.get("field")}

        assert por_campo["host_name"]["bold"] is True
        assert por_campo["host_birth"]["bold"] is False

    def test_a_justificacao_do_mapa_e_respeitada(self, documento_fr):
        assert _por_id(documento_fr, "fr-host_paragraph")["properties"]["align"] == (
            "justify"
        )
        # Celula de tabela nao e justificada.
        assert _por_id(documento_fr, "fr-table_guest_name")["properties"]["align"] == (
            "left"
        )

    def test_a_entrelinha_vai_em_pontos(self, documento_fr):
        """13,5pt tem de voltar 13,5 -- por isso `leading` nao e multiplicador."""
        assert _por_id(documento_fr, "fr-host_paragraph")["properties"]["leading"] == (
            mapa_fr.LEADING
        )

    def test_a_fonte_e_a_do_renderer(self, documento_fr):
        props = _por_id(documento_fr, "fr-host_paragraph")["properties"]

        assert props["font_family"] == mapa_fr.FONT_REGULAR == "LiberationSans"
        assert props["font_size"] == mapa_fr.BODY_SIZE == 11.0
        assert props["min_font_size"] == mapa_fr.MIN_FONT_SIZE


# ---------------------------------------------------------------------------
# 4. Camadas
# ---------------------------------------------------------------------------


class TestZIndex:
    def test_a_base_fica_atras_de_tudo(self, documento_fr):
        base = _por_id(documento_fr, "fr-base")
        outros = [e for e in documento_fr["elements"] if e["id"] != "fr-base"]

        assert base["z_index"] == vi.Z_BASE
        assert all(e["z_index"] > base["z_index"] for e in outros)

    def test_as_mascaras_ficam_entre_a_base_e_o_conteudo(self, documento_fr):
        mascaras = [e for e in documento_fr["elements"] if e["id"].startswith("fr-mask-")]
        conteudo = [
            e
            for e in documento_fr["elements"]
            if not e["id"].startswith("fr-mask-") and e["id"] != "fr-base"
        ]

        assert all(e["z_index"] == vi.Z_MASCARA for e in mascaras)
        assert all(e["z_index"] == vi.Z_CONTEUDO for e in conteudo)
        assert vi.Z_BASE < vi.Z_MASCARA < vi.Z_CONTEUDO

    def test_a_mascara_cobre_o_valor_de_amostra_da_sua_zona(self, documento_fr):
        """
        A mascara e o conteudo da mesma zona tem de se sobrepor -- senao a
        amostra do PDF ficaria visivel ao lado do valor novo.
        """
        for zone in mapa_fr.ZONES:
            mascara = _por_id(documento_fr, f"fr-mask-{zone.key}")
            texto = _por_id(documento_fr, f"fr-{zone.key}")

            assert mascara["x"] <= texto["x"]
            assert mascara["x"] + mascara["width"] >= texto["x"]
            assert mascara["y"] <= texto["y"] + texto["height"]


# ---------------------------------------------------------------------------
# 5. Determinismo
# ---------------------------------------------------------------------------


class TestDeterminismo:
    def test_importar_duas_vezes_da_o_mesmo_documento(self):
        primeiro = vi.construir_visual_schema_fr(ASSET_FALSO)
        segundo = vi.construir_visual_schema_fr(ASSET_FALSO)

        assert primeiro == segundo

    def test_nao_ha_uuid_nem_carimbo_de_tempo(self, documento_fr):
        import json
        import re

        texto = json.dumps(documento_fr)

        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", texto)
        assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:", texto)

    def test_a_ordem_dos_elementos_e_estavel(self):
        a = [e["id"] for e in vi.construir_visual_schema_fr(1)["elements"]]
        b = [e["id"] for e in vi.construir_visual_schema_fr(1)["elements"]]

        assert a == b

    def test_a_rasterizacao_e_deterministica(self):
        """
        Bytes iguais a cada chamada -- e o que permite ao `get_or_create`
        do Asset decidir por SHA-256 se precisa regravar o arquivo.
        """
        assert vi.rasterizar_pagina_oficial() == vi.rasterizar_pagina_oficial()


# ---------------------------------------------------------------------------
# 6. A imagem de fundo
# ---------------------------------------------------------------------------


class TestImagemDeFundo:
    def test_a_rasterizacao_produz_um_png(self):
        conteudo = vi.rasterizar_pagina_oficial()

        assert conteudo.startswith(b"\x89PNG\r\n\x1a\n")

    def test_a_imagem_tem_a_proporcao_da_pagina(self):
        import io as _io

        from PIL import Image

        imagem = Image.open(_io.BytesIO(vi.rasterizar_pagina_oficial()))

        proporcao_pagina = mapa_fr.PAGE_WIDTH / mapa_fr.PAGE_HEIGHT
        assert imagem.width / imagem.height == pytest.approx(proporcao_pagina, abs=0.01)

    def test_o_asset_e_criado_uma_vez_so(self):
        primeiro = vi.obter_asset_da_base()
        segundo = vi.obter_asset_da_base()

        assert primeiro.pk == segundo.pk
        assert Asset.objects.filter(key=vi.CHAVE_DO_ASSET_FR).count() == 1

    def test_o_elemento_de_fundo_cobre_a_pagina_inteira(self, documento_fr):
        base = _por_id(documento_fr, "fr-base")

        assert (base["x"], base["y"]) == (0.0, 0.0)
        assert base["width"] == mapa_fr.PAGE_WIDTH
        assert base["height"] == mapa_fr.PAGE_HEIGHT
        assert base["properties"]["preserve_aspect_ratio"] is False

    def test_o_fundo_e_marcado_como_referencia_do_editor(self, documento_fr):
        """
        A Etapa 4.2D precisa saber que esta imagem NAO vai para o PDF: o
        documento e gerado a partir do arquivo oficial, nao do raster.
        """
        base = _por_id(documento_fr, "fr-base")

        assert base["properties"]["is_base_reference"] is True


# ---------------------------------------------------------------------------
# 7. A acao no backoffice
# ---------------------------------------------------------------------------


class TestAcaoDeImportar:
    def _url(self, versao):
        return reverse("backoffice:document_import_official", args=[versao.pk])

    def test_importa_para_um_rascunho(self, client, versao_fr):
        client.force_login(_usuario("edita@desenrola.be", "ver", "editar"))

        resposta = client.post(self._url(versao_fr))

        versao_fr.refresh_from_db()
        assert resposta.status_code == 302
        assert len(versao_fr.visual_schema["elements"]) == 1 + 2 * len(mapa_fr.ZONES)

    def test_o_resultado_gravado_e_valido(self, client, versao_fr):
        client.force_login(_usuario("edita2@desenrola.be", "ver", "editar"))

        client.post(self._url(versao_fr))

        versao_fr.refresh_from_db()
        validate_visual_schema(
            versao_fr.visual_schema,
            field_keys=set(vi.CAMPOS_DO_DOCUMENTO_FR),
            asset_ids=set(Asset.objects.values_list("pk", flat=True)),
        )

    def test_substitui_o_que_estava_no_rascunho(self, client, versao_fr):
        """A acao e destrutiva, e o botao avisa antes de chamar."""
        client.force_login(_usuario("edita3@desenrola.be", "ver", "editar"))
        versao_fr.visual_schema = documento_com_texto("vai embora")
        versao_fr.save()

        client.post(self._url(versao_fr))

        versao_fr.refresh_from_db()
        ids = {e["id"] for e in versao_fr.visual_schema["elements"]}
        assert "t1" not in ids
        assert "fr-base" in ids

    def test_uma_versao_publicada_nao_e_alterada(self, client, db):
        publicada = TemplateVersion.objects.get(
            template__slug=official_slug("fr"), status=TemplateVersion.Status.PUBLISHED
        )
        client.force_login(_usuario("edita4@desenrola.be", "ver", "editar"))

        resposta = client.post(self._url(publicada))

        publicada.refresh_from_db()
        assert resposta.status_code == 302
        assert publicada.visual_schema == {}

    def test_sem_permissao_de_editar_nao_importa(self, client, versao_fr):
        client.force_login(_usuario("so-ve@desenrola.be", "ver"))

        resposta = client.post(self._url(versao_fr))

        versao_fr.refresh_from_db()
        assert resposta.status_code == 403
        assert versao_fr.visual_schema == {}

    def test_usuario_comum_nao_importa(self, client, user, versao_fr):
        client.force_login(user)

        assert client.post(self._url(versao_fr)).status_code == 403

    def test_get_nao_importa(self, client, versao_fr):
        client.force_login(_usuario("edita5@desenrola.be", "ver", "editar"))

        assert client.get(self._url(versao_fr)).status_code == 405

    def test_um_modelo_sem_documento_oficial_e_recusado(self, client, draft_version):
        """
        `draft_version` e um modelo de teste generico, nao o oficial
        frances. Importar nele nao pode inventar um layout.
        """
        client.force_login(_usuario("edita6@desenrola.be", "ver", "editar"))

        resposta = client.post(self._url(draft_version))

        draft_version.refresh_from_db()
        assert resposta.status_code == 302
        assert draft_version.visual_schema == {}

    def test_o_servico_recusa_modelo_sem_documento(self, draft_version):
        with pytest.raises(ValueError, match="francês|frances"):
            vi.importar_modelo_oficial(draft_version)


# ---------------------------------------------------------------------------
# 8. Ida e volta pelo editor
# ---------------------------------------------------------------------------


class TestIdaEVolta:
    def test_importar_abrir_salvar_e_reabrir_preserva_o_layout(self, client, versao_fr):
        """
        O criterio de conclusao da etapa: o que foi importado sobrevive a
        um ciclo completo pelo editor, ate a ultima casa decimal.
        """
        client.force_login(
            _usuario("ciclo@desenrola.be", "ver", "editar", "criar", "publicar")
        )
        client.post(reverse("backoffice:document_import_official", args=[versao_fr.pk]))
        versao_fr.refresh_from_db()
        importado = versao_fr.visual_schema

        # Abrir o editor.
        aberto = client.get(
            reverse("backoffice:document_editor", args=[versao_fr.pk])
        ).context["documento_json"]
        assert aberto == importado

        # Salvar de volta sem mexer em nada.
        resposta = _salvar(client, versao_fr, aberto)
        assert resposta.status_code == 200

        # Reabrir.
        versao_fr.refresh_from_db()
        assert versao_fr.visual_schema == importado

    def test_editar_uma_propriedade_e_salvar_funciona(self, client, versao_fr):
        client.force_login(_usuario("ciclo2@desenrola.be", "ver", "editar"))
        client.post(reverse("backoffice:document_import_official", args=[versao_fr.pk]))
        versao_fr.refresh_from_db()

        documento = versao_fr.visual_schema
        for elemento in documento["elements"]:
            if elemento["id"] == "fr-signature_name":
                elemento["x"] = 60.5
        resposta = _salvar(client, versao_fr, documento)

        versao_fr.refresh_from_db()
        assert resposta.status_code == 200
        assert _por_id(versao_fr.visual_schema, "fr-signature_name")["x"] == 60.5

    def test_o_importado_pode_ser_publicado(self, client, versao_fr):
        """
        Nada fica incompleto na importacao -- todo campo tem referencia e
        a imagem existe. Se algo faltasse, a publicacao barraria.
        """
        client.force_login(
            _usuario("publica@desenrola.be", "ver", "editar", "publicar")
        )
        client.post(reverse("backoffice:document_import_official", args=[versao_fr.pk]))

        client.post(reverse("backoffice:document_publish", args=[versao_fr.pk]))

        versao_fr.refresh_from_db()
        assert versao_fr.status == TemplateVersion.Status.PUBLISHED


# ---------------------------------------------------------------------------
# 9. O renderer FR nao foi tocado
# ---------------------------------------------------------------------------


class TestRendererIntacto:
    def test_o_mapa_continua_com_as_nove_zonas(self):
        assert len(mapa_fr.ZONES) == 9

    def test_a_importacao_nao_altera_o_mapa(self, documento_fr):
        """Ler o mapa nao pode mexer nele -- os dataclasses sao frozen."""
        assert mapa_fr.ZONES[0].box.first_baseline_y == 682.9
        assert mapa_fr.ZONES[0].mask.y == 652.0

    def test_o_pdf_frances_continua_sendo_gerado(self, db, nacionalidade_factory):
        from pdfengine.render import render_invitation_letter_fr
        from pdfengine.sample_data import FR_SAMPLE_DATA

        pdf = render_invitation_letter_fr(FR_SAMPLE_DATA)

        assert pdf.startswith(b"%PDF-")
        assert len(pdf) > 10000

    def test_o_pdf_frances_continua_deterministico(self):
        from pdfengine.render import render_invitation_letter_fr
        from pdfengine.sample_data import FR_SAMPLE_DATA

        assert render_invitation_letter_fr(FR_SAMPLE_DATA) == (
            render_invitation_letter_fr(FR_SAMPLE_DATA)
        )


# ---------------------------------------------------------------------------
# 10. Conferencia contra o PDF oficial -- medida, nao impressao
# ---------------------------------------------------------------------------


def _texto_posicionado_do_pdf_oficial():
    """
    Cada trecho de texto do PDF oficial com a sua posicao real na pagina.

    A posicao sai da composicao da matriz de texto (`tm`) com a de
    transformacao (`cm`) -- `tm` sozinha nao da coordenada de pagina. E o
    mesmo metodo com que o mapa do renderer foi medido.
    """
    from pypdf import PdfReader

    from pdfengine.render import BASE_PDF_PATH

    def multiplicar(a, b):
        return [
            a[0] * b[0] + a[1] * b[2],
            a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2],
            a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4],
            a[4] * b[1] + a[5] * b[3] + b[5],
        ]

    achados = []

    def visitante(texto, cm, tm, fontes, tamanho):
        if texto.strip():
            device = multiplicar(tm, cm)
            achados.append((texto, device[4], device[5]))

    PdfReader(str(BASE_PDF_PATH)).pages[0].extract_text(visitor_text=visitante)
    return achados


@pytest.fixture(scope="module")
def texto_do_pdf():
    """Lido uma vez por modulo -- abrir o PDF a cada teste seria desperdicio."""
    return _texto_posicionado_do_pdf_oficial()


class TestConferenciaComOPdfOficial:
    """
    A prova de que a importacao caiu no lugar certo: cada area importada
    tem de cobrir, no PDF oficial, exatamente o texto de amostra que ela
    existe para substituir. Isto mede -- nao compara impressoes.
    """

    # O que a amostra do documento oficial traz em cada zona.
    AMOSTRA = {
        "host_paragraph": "Je soussignée",
        "item2_address": "Pendant toute la durée",
        "closing_line": "Fait à",
        "table_guest_name": "Carlos Eduardo Silva",
        "table_guest_nationality": "Brésilienne",
        "table_guest_birth": "22/07/1990",
        "table_guest_passport": "YY000000",
        "table_duration": "10/10/2026",
        "signature_name": "Claire Dubois",
    }

    def test_o_pdf_oficial_tem_texto_extraivel(self, texto_do_pdf):
        assert len(texto_do_pdf) > 100

    @pytest.mark.parametrize("zone", mapa_fr.ZONES, ids=lambda z: z.key)
    def test_a_mascara_cobre_a_amostra_daquela_zona(self, texto_do_pdf, zone):
        # Folga de 2pt na horizontal e 4pt abaixo: a mascara e ancorada na
        # area reservada, e a linha de base do glifo fica um pouco abaixo
        # do canto da caixa.
        dentro = " ".join(
            texto
            for texto, x, y in texto_do_pdf
            if zone.mask.x - 2 <= x <= zone.mask.x + zone.mask.width + 2
            and zone.mask.y - 4 <= y <= zone.mask.y + zone.mask.height + 2
        )

        assert self.AMOSTRA[zone.key] in dentro

    @pytest.mark.parametrize("zone", mapa_fr.ZONES, ids=lambda z: z.key)
    def test_a_caixa_de_texto_comeca_onde_a_amostra_comeca(self, texto_do_pdf, zone):
        """
        O X da caixa importada tem de bater com o X real do texto de
        amostra daquela zona -- e o alinhamento a esquerda do documento.
        """
        xs = [
            x
            for texto, x, y in texto_do_pdf
            if zone.mask.x - 2 <= x <= zone.mask.x + zone.mask.width + 2
            and zone.mask.y - 4 <= y <= zone.mask.y + zone.mask.height + 2
        ]

        assert min(xs) == pytest.approx(zone.box.x, abs=1.0)

    def test_a_pagina_importada_tem_o_tamanho_da_pagina_oficial(self):
        from pypdf import PdfReader

        from pdfengine.render import BASE_PDF_PATH

        pagina = PdfReader(str(BASE_PDF_PATH)).pages[0]
        documento = vi.construir_visual_schema_fr(ASSET_FALSO)

        assert documento["page"]["width"] == pytest.approx(
            float(pagina.mediabox.width), abs=0.5
        )
        assert documento["page"]["height"] == pytest.approx(
            float(pagina.mediabox.height), abs=0.5
        )

    def test_nenhuma_mascara_cobre_o_logo_ou_o_qr(self):
        """
        Invariante ja protegido no renderer e que a importacao nao pode
        perder: uma mascara larga demais apagaria uma fatia do logo do IBZ
        ou do QR Code, deixando o QR ilegivel.
        """
        from pypdf import PdfReader

        from pdfengine.render import BASE_PDF_PATH

        pagina = PdfReader(str(BASE_PDF_PATH)).pages[0]
        documento = vi.construir_visual_schema_fr(ASSET_FALSO)

        # As imagens do documento vivem a direita, na faixa baixa da
        # pagina (logo IBZ x 373,5..475,8; QR x 466,7..552,2).
        for elemento in documento["elements"]:
            if not elemento["id"].startswith("fr-mask-"):
                continue
            direita = elemento["x"] + elemento["width"]
            abaixo_de = elemento["y"]
            # Em coordenadas do editor, a faixa das imagens fica abaixo de
            # y=620 (842 - 222). Nenhuma mascara pode chegar la a direita.
            if abaixo_de > 620:
                assert direita <= 373.5, elemento["id"]
        assert pagina is not None
