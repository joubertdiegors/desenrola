"""
A Carta Convite nos quatro idiomas (Etapa 3.6).

O que estes testes protegem: os quatro modelos oficiais sao o MESMO
documento em idiomas diferentes. Mesma estrutura, mesmos elementos,
mesmos campos dinamicos, mesmo asset -- so o texto muda. Uma traducao
que mexesse na estrutura por engano (perder um campo, virar texto fixo,
duplicar o logo) falha aqui.

A comparacao e sempre contra o FRANCES, que e o unico reconstruido do
PDF oficial. Os outros tres sao traducoes dele.

MEDIA_ROOT
----------
Todo teste que materializa arquivo aponta `settings.MEDIA_ROOT` para um
`tmp_path`. Sem isso a suite escreveria no `media/` do repositorio a cada
execucao.
"""

import io
from collections import Counter

import pytest
from pypdf import PdfReader

from apps.content.models import Asset
from apps.doctemplates import layout_schema
from apps.doctemplates.models import DocumentTemplate
from apps.doctemplates.services import carta_convite as cc
from apps.doctemplates.services import dados_de_exemplo, pdf

OUTROS = ("en", "nl", "pt")


@pytest.fixture
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def layout_de(idioma):
    return cc.layout(idioma)


def elementos_de(idioma):
    return layout_de(idioma)["elements"]


def campos_de(idioma):
    return sorted({ref for linha in cc.inventario(layout_de(idioma)) for ref in linha["campos"]})


def sufixo(identificador):
    """O id sem o prefixo de idioma: `pt-tabela` -> `tabela`."""
    return identificador.split("-", 1)[1]


# ===========================================================================
# 1. Os quatro modelos existem na biblioteca
# ===========================================================================


@pytest.mark.django_db
class TestOsQuatroModelos:
    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_o_modelo_existe(self, idioma):
        modelo = DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma))

        assert modelo.language == idioma

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_tem_o_layout_completo(self, idioma):
        modelo = DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma))

        assert len(modelo.layout["elements"]) == 23

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_o_layout_gravado_valida_pelo_contrato(self, idioma):
        DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma)).full_clean()

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_continua_oficial_ativo_e_destravado(self, idioma):
        """A auditoria humana ainda vai acontecer: nada de travar agora."""
        modelo = DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma))

        assert modelo.is_system is True
        assert modelo.is_active is True
        assert modelo.is_locked is False

    def test_o_field_schema_e_o_mesmo_nos_quatro(self):
        """
        O formulario do assistente nao muda com o idioma do documento: e
        o mesmo conjunto de perguntas.
        """
        schemas = [
            DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma)).field_schema
            for idioma in cc.IDIOMAS
        ]

        assert all(schema == schemas[0] for schema in schemas)
        assert len(schemas[0]["fields"]) == 9

    def test_nao_ha_modelos_oficiais_duplicados(self):
        oficiais = DocumentTemplate.objects.filter(is_system=True)

        assert oficiais.count() == len(cc.IDIOMAS)


# ===========================================================================
# 2. A estrutura e a mesma; so o texto muda
# ===========================================================================


class TestMesmaEstrutura:
    @pytest.mark.parametrize("idioma", OUTROS)
    def test_tem_os_mesmos_elementos_na_mesma_ordem(self, idioma):
        assert [sufixo(e["id"]) for e in elementos_de(idioma)] == [
            sufixo(e["id"]) for e in elementos_de("fr")
        ]

    @pytest.mark.parametrize("idioma", OUTROS)
    def test_tem_os_mesmos_tipos_na_mesma_ordem(self, idioma):
        assert [e["type"] for e in elementos_de(idioma)] == [
            e["type"] for e in elementos_de("fr")
        ]

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_a_composicao_por_tipo(self, idioma):
        assert Counter(e["type"] for e in elementos_de(idioma)) == {
            "text": 12,
            "rich_text": 4,
            "rectangle": 3,
            "table": 1,
            "image": 1,
            "qr_code": 1,
            "line": 1,
        }

    @pytest.mark.parametrize("idioma", OUTROS)
    def test_os_campos_dinamicos_sao_identicos_aos_do_frances(self, idioma):
        """
        Traduzir muda o texto ao redor do campo, nunca o campo. Um campo
        que virasse texto fixo sumiria daqui.
        """
        assert campos_de(idioma) == campos_de("fr")

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_sao_quinze_campos_dinamicos(self, idioma):
        assert len(campos_de(idioma)) == 15

    @pytest.mark.parametrize("idioma", OUTROS)
    def test_a_tabela_tem_a_mesma_geometria(self, idioma):
        def tabela(lingua):
            return next(e for e in elementos_de(lingua) if e["type"] == "table")

        nossa, francesa = tabela(idioma), tabela("fr")

        assert nossa["properties"]["columns"] == francesa["properties"]["columns"]
        assert [linha["min_height"] for linha in nossa["properties"]["rows"]] == [
            linha["min_height"] for linha in francesa["properties"]["rows"]
        ]
        assert nossa["properties"]["cell_padding"] == francesa["properties"]["cell_padding"]

    @pytest.mark.parametrize("idioma", OUTROS)
    def test_so_a_lista_numerada_muda_de_posicao(self, idioma):
        """
        A unica diferenca de POSICAO aceita: o item 2 pode ocupar uma
        linha a mais, e entao o item 3 desce junto. Qualquer outro
        elemento fora do lugar e regressao.
        """
        moveis = {"item-3", "item-3-marcador"}
        for nosso, frances in zip(elementos_de(idioma), elementos_de("fr"), strict=True):
            if sufixo(nosso["id"]) in moveis:
                continue
            assert (nosso["x"], nosso["y"]) == (frances["x"], frances["y"]), nosso["id"]

    @pytest.mark.parametrize("idioma", OUTROS)
    def test_a_largura_nunca_muda(self, idioma):
        """Traduzir muda quantas linhas o bloco ocupa, nunca a coluna."""
        for nosso, frances in zip(elementos_de(idioma), elementos_de("fr"), strict=True):
            assert nosso["width"] == frances["width"], nosso["id"]

    @pytest.mark.parametrize("idioma", OUTROS)
    def test_so_bloco_de_texto_pode_mudar_de_altura(self, idioma):
        """
        A altura de um paragrafo e o numero de linhas depois de quebrado
        -- e isso depende do idioma. Tabela, imagem, QR, linha e faixa
        NAO tem essa liberdade: altura diferente ali seria regressao.
        """
        for nosso, frances in zip(elementos_de(idioma), elementos_de("fr"), strict=True):
            if nosso["type"] in ("text", "rich_text"):
                continue
            assert nosso["height"] == frances["height"], nosso["id"]

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_a_lista_numerada_nunca_se_sobrepoe(self, idioma):
        """O item 3 tem de comecar depois do fim do item 2."""
        por_id = {sufixo(e["id"]): e for e in elementos_de(idioma)}
        item_2, item_3 = por_id["item-2"], por_id["item-3"]

        assert item_2["y"] + item_2["height"] <= item_3["y"] + 0.001

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_nenhum_bloco_invade_o_seguinte(self, idioma):
        """
        Traducao mais longa nao pode escrever por cima do proximo bloco.
        Confere os blocos de texto corridos, na ordem da pagina.
        """
        por_id = {sufixo(e["id"]): e for e in elementos_de(idioma)}
        ordem = ("declaracao", "item-3", "fecho-1", "fecho-2", "fecho-3", "local-e-data")
        for atual, proximo in zip(ordem, ordem[1:], strict=False):
            fim = por_id[atual]["y"] + por_id[atual]["height"]
            assert fim <= por_id[proximo]["y"] + 0.001, f"{atual} invade {proximo}"

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_tudo_cabe_na_pagina_a4(self, idioma):
        for elemento in elementos_de(idioma):
            assert elemento["x"] >= 0
            assert elemento["y"] >= 0
            assert elemento["x"] + elemento["width"] <= 595.2756 + 0.5
            assert elemento["y"] + elemento["height"] <= 841.8898


# ===========================================================================
# 3. Conteudo: traduzido, sem inventar nem perder
# ===========================================================================


class TestConteudo:
    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_o_layout_e_valido(self, idioma):
        layout_schema.validate_layout(layout_de(idioma))

    @pytest.mark.parametrize("idioma", OUTROS)
    def test_o_texto_nao_ficou_em_frances(self, idioma):
        """Uma traducao esquecida apareceria como o texto frances intacto."""
        conteudo = cc.CONTEUDO[idioma]
        frances = cc.CONTEUDO["fr"]

        assert conteudo["titulo"] != frances["titulo"]
        assert conteudo["subtitulo"] != frances["subtitulo"]
        assert conteudo["destinatario"] != frances["destinatario"]
        assert conteudo["fechos"] != frances["fechos"]
        assert conteudo["assinatura_rotulo"] != frances["assinatura_rotulo"]

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_a_url_do_qr_e_a_mesma_em_todos(self, idioma):
        """Endereco nao se traduz -- inventar uma variante criaria conteudo."""
        qr = next(e for e in elementos_de(idioma) if e["type"] == "qr_code")

        assert qr["properties"]["source"]["value"] == cc.QR_CONTEUDO

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_a_referencia_legal_nao_foi_traduzida(self, idioma):
        """"Annexe 3bis" identifica um documento: fica como esta."""
        assert "Annexe 3bis" in cc.CONTEUDO[idioma]["fechos"][0]

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_tem_as_tres_clausulas_numeradas(self, idioma):
        marcadores = [
            e["properties"]["content"]["value"]
            for e in elementos_de(idioma)
            if sufixo(e["id"]).endswith("-marcador")
        ]

        assert marcadores == ["1.", "2.", "3."]

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_tem_os_tres_paragrafos_de_fecho(self, idioma):
        assert len(cc.CONTEUDO[idioma]["fechos"]) == 3

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_a_tabela_tem_cinco_rotulos(self, idioma):
        assert len(cc.CONTEUDO[idioma]["tabela_rotulos"]) == 5

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_a_declaracao_alterna_literais_e_campos(self, idioma):
        """Oito literais para sete campos: a forma e a mesma nos quatro."""
        assert len(cc.CONTEUDO[idioma]["declaracao"]) == len(cc.CAMPOS_DA_DECLARACAO) + 1

    def test_um_idioma_desconhecido_e_recusado(self):
        with pytest.raises(cc.IdiomaDesconhecidoError):
            cc.layout("de")


# ===========================================================================
# 4. Assets: um logo so para os quatro
# ===========================================================================


class TestAssets:
    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_a_unica_imagem_e_o_logo(self, idioma):
        imagens = [e for e in elementos_de(idioma) if e["type"] == "image"]

        assert len(imagens) == 1
        assert imagens[0]["id"] == cc.id_do_logo(idioma)

    @pytest.mark.django_db
    def test_os_quatro_apontam_para_o_mesmo_asset(self, media):
        cc.reconstruir_todos(DocumentTemplate, Asset)

        ids = set()
        for idioma in cc.IDIOMAS:
            modelo = DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma))
            for elemento in modelo.layout["elements"]:
                if elemento["type"] == "image":
                    ids.add(elemento["properties"]["source"]["asset_id"])

        assert len(ids) == 1
        assert Asset.objects.filter(key=cc.LOGO_CHAVE_DO_ASSET).count() == 1

    @pytest.mark.django_db
    def test_reconstruir_todos_e_idempotente(self, media):
        primeiro = cc.reconstruir_todos(DocumentTemplate, Asset)
        layouts = {
            idioma: DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma)).layout
            for idioma in cc.IDIOMAS
        }

        segundo = cc.reconstruir_todos(DocumentTemplate, Asset)

        assert [r.asset.pk for r in primeiro] == [r.asset.pk for r in segundo]
        assert Asset.objects.filter(key=cc.LOGO_CHAVE_DO_ASSET).count() == 1
        for idioma in cc.IDIOMAS:
            atual = DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma)).layout
            assert atual == layouts[idioma]

    @pytest.mark.django_db
    def test_nao_recria_o_asset_que_ja_existe(self, media):
        cc.reconstruir(DocumentTemplate, Asset, "fr")
        antes = Asset.objects.get(key=cc.LOGO_CHAVE_DO_ASSET)

        cc.reconstruir_todos(DocumentTemplate, Asset)

        assert Asset.objects.get(key=cc.LOGO_CHAVE_DO_ASSET).pk == antes.pk


# ===========================================================================
# 5. Render: os quatro saem em PDF de verdade
# ===========================================================================


@pytest.mark.django_db
class TestRender:
    @pytest.fixture(autouse=True)
    def _reconstruido(self, media):
        cc.reconstruir_todos(DocumentTemplate, Asset)

    def _render(self, idioma):
        modelo = DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma))
        dados = dados_de_exemplo.para(modelo.slug)
        conteudo, _relatorio = pdf.render_template(modelo, dados)
        return conteudo

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_sai_um_pdf_de_uma_pagina_a4(self, idioma):
        documento = PdfReader(io.BytesIO(self._render(idioma)))

        assert len(documento.pages) == 1
        caixa = documento.pages[0].mediabox
        assert round(float(caixa.width), 1) == 595.3
        assert round(float(caixa.height), 1) == 841.9

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_ha_dados_de_exemplo_para_todos(self, idioma):
        assert dados_de_exemplo.para(cc.slug_do_modelo(idioma))

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_nenhum_campo_fica_sem_valor_na_previa(self, idioma):
        modelo = DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma))
        dados = dados_de_exemplo.para(modelo.slug)

        assert not set(pdf.campos_do_layout(modelo.layout)) - set(dados)

    @pytest.mark.parametrize(
        ("idioma", "esperado"),
        [
            ("fr", "LETTRE D'INVITATION"),
            ("en", "LETTER OF INVITATION"),
            ("nl", "UITNODIGINGS"),
            ("pt", "CARTA DE CONVITE"),
        ],
    )
    def test_o_titulo_traduzido_sai_no_pdf(self, idioma, esperado):
        texto = PdfReader(io.BytesIO(self._render(idioma))).pages[0].extract_text()

        assert esperado in texto

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_os_dados_reais_saem_no_pdf(self, idioma):
        texto = PdfReader(io.BytesIO(self._render(idioma))).pages[0].extract_text()

        assert "Carlos Eduardo Silva" in texto
        assert "YY000000" in texto

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_o_logo_entra_como_imagem(self, idioma):
        pagina = PdfReader(io.BytesIO(self._render(idioma))).pages[0]

        assert "/XObject" in pagina["/Resources"]

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_o_texto_e_vetorial_e_nao_raster(self, idioma):
        """
        Se o documento fosse a pagina rasterizada, nao haveria texto
        extraivel -- e e exatamente a saida que esta arquitetura recusa.
        """
        texto = PdfReader(io.BytesIO(self._render(idioma))).pages[0].extract_text()

        assert len(texto) > 800

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_a_unica_imagem_do_pdf_e_o_logo(self, idioma):
        """Uma segunda imagem seria o PDF oficial entrando como fundo."""
        pagina = PdfReader(io.BytesIO(self._render(idioma))).pages[0]

        assert len(pagina.images) == 1
        largura, altura = pagina.images[0].image.size
        assert largura < 600 and altura < 600


# ===========================================================================
# 6. Nada da arquitetura aposentada
# ===========================================================================


class TestSemArquiteturaAposentada:
    def test_o_servico_nao_cita_a_arquitetura_antiga(self):
        import inspect

        codigo = inspect.getsource(cc)

        for proibido in (
            "visual_schema", "visual_import", "elementos_fixos",
            "TemplateVersion", "LetterTemplate",
        ):
            assert proibido not in codigo, f"{proibido} não pode aparecer aqui"

    def test_nao_ha_pdf_de_fundo_no_layout(self):
        """
        O PDF oficial e fonte de MEDIDA e do logo -- nunca entra no
        desenho como pagina, raster ou mascara.
        """
        import inspect

        codigo = inspect.getsource(cc.layout)

        for proibido in ("BASE_PDF", "background", "mascara", "raster"):
            assert proibido not in codigo

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_nenhum_elemento_cobre_a_pagina_inteira(self, idioma):
        for elemento in elementos_de(idioma):
            ocupa_tudo = elemento["width"] > 500 and elemento["height"] > 700
            assert not ocupa_tudo, f"{elemento['id']} cobre a página inteira"

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_nao_ha_retangulo_branco_de_mascara(self, idioma):
        for elemento in elementos_de(idioma):
            if elemento["type"] != "rectangle":
                continue
            assert elemento["properties"].get("fill_color") not in ("#FFFFFF", "#ffffff")
