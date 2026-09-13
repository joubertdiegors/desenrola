"""
Contrato do modelo visual e conversao de coordenadas (Etapa 4.2A).

Testes sem banco: `visual_schema.py` e `coordinates.py` sao codigo puro
de proposito -- e o que permite exercitar cada regra de validacao e cada
conta de geometria diretamente, sem passar por HTTP.
"""

import copy

import pytest
from django.core.exceptions import ValidationError

from apps.doctemplates import coordinates as geo
from apps.doctemplates.visual_schema import (
    A4_HEIGHT_PT,
    A4_WIDTH_PT,
    MAX_ELEMENTS,
    SCHEMA_VERSION,
    documento_vazio,
    field_keys_of,
    validate_visual_schema,
)


def elemento(tipo="text", **overrides):
    base = {
        "id": f"el-{tipo}",
        "type": tipo,
        "x": 72.0,
        "y": 120.0,
        "width": 200.0,
        "height": 24.0,
        "z_index": 1,
        "properties": {},
    }
    padroes = {
        "text": {"content": "Olá"},
        "field": {"field": "guest_name"},
        "image": {"asset_id": 1},
        "line": {"thickness": 1},
        "rect": {"border_width": 1},
        "qrcode": {"content": "https://exemplo.be/x"},
        "table": {
            "columns": [{"width": 100}, {"width": 120}],
            "rows": [{"min_height": 16, "cells": [{"content": "a"}, {"content": "b"}]}],
        },
    }
    base["properties"] = padroes.get(tipo, {})
    base.update(overrides)
    return base


def documento(*elementos):
    doc = documento_vazio()
    doc["elements"] = list(elementos)
    return doc


# ---------------------------------------------------------------------------
# 1. O documento vazio e o formato base
# ---------------------------------------------------------------------------


class TestDocumentoBase:
    def test_um_documento_vazio_e_valido(self):
        validate_visual_schema(documento_vazio())

    def test_uma_versao_sem_layout_nenhum_e_valida(self):
        """`{}` e o estado de toda versao criada antes do editor existir."""
        validate_visual_schema({})

    def test_a_pagina_nasce_em_a4_exato(self):
        page = documento_vazio()["page"]

        assert page["width"] == A4_WIDTH_PT == 595.2756
        assert page["height"] == A4_HEIGHT_PT == 841.8898
        assert page["unit"] == "pt"
        assert page["origin"] == "top-left"

    def test_a_versao_do_formato_e_declarada(self):
        assert documento_vazio()["schema_version"] == SCHEMA_VERSION

    @pytest.mark.parametrize("versao", [0, 2, "1", None])
    def test_versao_de_formato_desconhecida_e_recusada(self, versao):
        doc = documento_vazio()
        doc["schema_version"] = versao

        with pytest.raises(ValidationError):
            validate_visual_schema(doc)

    @pytest.mark.parametrize("valor", ["texto", [], 42, None])
    def test_o_documento_precisa_ser_um_objeto(self, valor):
        if valor is None:
            return
        with pytest.raises(ValidationError):
            validate_visual_schema(valor)


# ---------------------------------------------------------------------------
# 2. Pagina
# ---------------------------------------------------------------------------


class TestPagina:
    @pytest.mark.parametrize("chave", ["width", "height"])
    def test_dimensao_nao_numerica_e_recusada(self, chave):
        doc = documento_vazio()
        doc["page"][chave] = "595"

        with pytest.raises(ValidationError):
            validate_visual_schema(doc)

    @pytest.mark.parametrize("valor", [0, -1])
    def test_dimensao_nao_positiva_e_recusada(self, valor):
        doc = documento_vazio()
        doc["page"]["width"] = valor

        with pytest.raises(ValidationError):
            validate_visual_schema(doc)

    def test_unidade_diferente_de_pontos_e_recusada(self):
        """Pixel nao e unidade de papel. Aceitar aqui contaminaria o PDF."""
        doc = documento_vazio()
        doc["page"]["unit"] = "px"

        with pytest.raises(ValidationError):
            validate_visual_schema(doc)

    def test_origem_diferente_e_recusada(self):
        doc = documento_vazio()
        doc["page"]["origin"] = "bottom-left"

        with pytest.raises(ValidationError):
            validate_visual_schema(doc)


# ---------------------------------------------------------------------------
# 3. Elementos: identidade, tipo, geometria
# ---------------------------------------------------------------------------


class TestElementos:
    def test_os_sete_tipos_sao_aceitos(self):
        tipos = ["text", "field", "image", "line", "rect", "qrcode", "table"]
        elementos = [elemento(tipo, id=f"id-{tipo}") for tipo in tipos]

        validate_visual_schema(
            documento(*elementos), field_keys={"guest_name"}, asset_ids={1}
        )

    def test_tipo_desconhecido_e_recusado(self):
        with pytest.raises(ValidationError, match="tipo desconhecido"):
            validate_visual_schema(documento(elemento("video")))

    def test_ids_precisam_ser_unicos(self):
        a = elemento("text", id="mesmo")
        b = elemento("text", id="mesmo")

        with pytest.raises(ValidationError, match="mais de um elemento"):
            validate_visual_schema(documento(a, b))

    @pytest.mark.parametrize("valor", ["", "   ", None, 42])
    def test_id_precisa_existir(self, valor):
        with pytest.raises(ValidationError):
            validate_visual_schema(documento(elemento("text", id=valor)))

    @pytest.mark.parametrize("chave", ["x", "y", "width", "height"])
    def test_coordenada_nao_numerica_e_recusada(self, chave):
        with pytest.raises(ValidationError):
            validate_visual_schema(documento(elemento("text", **{chave: "72"})))

    @pytest.mark.parametrize("chave", ["width", "height"])
    def test_dimensao_negativa_e_recusada(self, chave):
        with pytest.raises(ValidationError):
            validate_visual_schema(documento(elemento("text", **{chave: -1})))

    def test_booleano_nao_passa_por_numero(self):
        """`True` é `1` em Python -- não pode virar uma coordenada."""
        with pytest.raises(ValidationError):
            validate_visual_schema(documento(elemento("text", x=True)))

    @pytest.mark.parametrize("valor", [float("nan"), float("inf")])
    def test_numero_nao_finito_e_recusado(self, valor):
        with pytest.raises(ValidationError):
            validate_visual_schema(documento(elemento("text", x=valor)))

    def test_coordenadas_decimais_sao_preservadas(self):
        """
        O documento oficial foi medido com casas decimais. Arredondar
        deslocaria o texto visivelmente.
        """
        preciso = elemento("text", x=72.3456, y=120.9876, width=400.125, height=13.5)

        validate_visual_schema(documento(preciso))

        assert preciso["x"] == 72.3456
        assert preciso["y"] == 120.9876

    def test_elemento_fora_da_pagina_e_aceito(self):
        """
        Recusar aqui faria o editor perder trabalho no meio de um arrasto.
        Quem recorta e o renderer.
        """
        validate_visual_schema(documento(elemento("text", x=-50, y=2000)))

    @pytest.mark.parametrize("valor", [1.5, "3", True, None])
    def test_z_index_precisa_ser_inteiro(self, valor):
        with pytest.raises(ValidationError):
            validate_visual_schema(documento(elemento("text", z_index=valor)))

    def test_z_index_negativo_e_valido(self):
        validate_visual_schema(documento(elemento("text", z_index=-3)))

    def test_documento_gigante_e_recusado(self):
        demais = [elemento("text", id=f"e{i}") for i in range(MAX_ELEMENTS + 1)]

        with pytest.raises(ValidationError, match="limite"):
            validate_visual_schema(documento(*demais))

    def test_elements_precisa_ser_lista(self):
        doc = documento_vazio()
        doc["elements"] = {}

        with pytest.raises(ValidationError):
            validate_visual_schema(doc)


# ---------------------------------------------------------------------------
# 4. Propriedades por tipo
# ---------------------------------------------------------------------------


class TestTexto:
    def test_alinhamento_desconhecido_e_recusado(self):
        el = elemento("text")
        el["properties"]["align"] = "meio-ish"

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))

    def test_tamanho_de_fonte_nao_positivo_e_recusado(self):
        el = elemento("text")
        el["properties"]["font_size"] = 0

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))

    def test_fonte_fora_da_lista_e_recusada(self):
        """
        Uma fonte que o motor de PDF nao tem viraria substituicao
        silenciosa no documento final.
        """
        el = elemento("text")
        el["properties"]["font_family"] = "Comic Sans MS"

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))

    @pytest.mark.parametrize("cor", ["preto", "#fff", "rgb(0,0,0)", "#gggggg", ""])
    def test_cor_fora_do_formato_e_recusada(self, cor):
        el = elemento("text")
        el["properties"]["color"] = cor

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))

    def test_cor_hexadecimal_e_aceita(self):
        el = elemento("text")
        el["properties"]["color"] = "#1A5FD6"

        validate_visual_schema(documento(el))

    def test_texto_absurdamente_longo_e_recusado(self):
        el = elemento("text")
        el["properties"]["content"] = "x" * 6000

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))

    def test_italico_precisa_ser_booleano(self):
        el = elemento("text")
        el["properties"]["italic"] = "sim"

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))


class TestCampo:
    def test_um_campo_guarda_a_referencia_e_nao_o_valor(self):
        el = elemento("field")

        validate_visual_schema(documento(el), field_keys={"guest_name"})

        assert el["properties"]["field"] == "guest_name"
        assert "value" not in el["properties"]

    def test_campo_sem_referencia_e_aceito_como_rascunho(self):
        """
        E assim que se desenha: larga o campo na pagina, escolhe qual
        depois. Recusar o salvamento faria perder trabalho.
        """
        el = elemento("field")
        el["properties"]["field"] = ""

        validate_visual_schema(documento(el))

    def test_campo_sem_referencia_nao_pode_ser_publicado(self):
        """Publicar congela o documento -- nada pode ficar pela metade."""
        el = elemento("field")
        el["properties"]["field"] = ""

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el), para_publicar=True)

    def test_referencia_inexistente_e_recusada(self):
        el = elemento("field")
        el["properties"]["field"] = "nao_existe"

        with pytest.raises(ValidationError, match="não\n?\\s?existe|não existe"):
            validate_visual_schema(documento(el), field_keys={"guest_name"})

    def test_sem_lista_de_campos_so_a_estrutura_e_cobrada(self):
        """
        `Model.clean()` valida sem consultar o banco; a ligacao com o
        `field_schema` e conferida na view que salva.
        """
        el = elemento("field")
        el["properties"]["field"] = "qualquer_coisa"

        validate_visual_schema(documento(el))

    def test_field_keys_of_le_o_field_schema(self):
        schema = {"fields": [{"key": "a"}, {"key": "b"}, {"nao_tem": "key"}, "lixo"]}

        assert field_keys_of(schema) == {"a", "b"}


class TestImagem:
    def test_imagem_sem_arquivo_e_aceita_como_rascunho(self):
        el = elemento("image")
        el["properties"]["asset_id"] = 0

        validate_visual_schema(documento(el))

    def test_imagem_sem_arquivo_nao_pode_ser_publicada(self):
        el = elemento("image")
        el["properties"]["asset_id"] = 0

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el), para_publicar=True)

    @pytest.mark.parametrize("valor", ["1", -3, True, None])
    def test_asset_id_precisa_ser_inteiro(self, valor):
        el = elemento("image")
        el["properties"]["asset_id"] = valor

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))

    def test_asset_inexistente_e_recusado(self):
        el = elemento("image")
        el["properties"]["asset_id"] = 99

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el), asset_ids={1, 2})

    def test_asset_valido_passa(self):
        validate_visual_schema(documento(elemento("image")), asset_ids={1})

    def test_a_imagem_nao_e_embutida_no_json(self):
        """Existe modelo Asset: base64 dentro do documento seria duplicacao."""
        el = elemento("image")

        validate_visual_schema(documento(el), asset_ids={1})

        assert "data" not in el["properties"]
        assert isinstance(el["properties"]["asset_id"], int)


class TestLinhaERetangulo:
    def test_espessura_nao_positiva_e_recusada(self):
        el = elemento("line")
        el["properties"]["thickness"] = 0

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))

    def test_retangulo_sem_preenchimento_e_valido(self):
        el = elemento("rect")
        el["properties"]["fill_color"] = None

        validate_visual_schema(documento(el))

    def test_preenchimento_invalido_e_recusado(self):
        el = elemento("rect")
        el["properties"]["fill_color"] = "azul"

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))


class TestQr:
    def test_qr_sem_conteudo_e_aceito_como_rascunho(self):
        el = elemento("qrcode")
        el["properties"]["content"] = ""

        validate_visual_schema(documento(el))

    def test_qr_sem_conteudo_nao_pode_ser_publicado(self):
        el = elemento("qrcode")
        el["properties"]["content"] = ""

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el), para_publicar=True)

    @pytest.mark.parametrize("nivel", ["L", "M", "Q", "H"])
    def test_os_quatro_niveis_de_correcao_sao_aceitos(self, nivel):
        el = elemento("qrcode")
        el["properties"]["error_correction"] = nivel

        validate_visual_schema(documento(el))

    def test_nivel_desconhecido_e_recusado(self):
        el = elemento("qrcode")
        el["properties"]["error_correction"] = "Z"

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))


class TestTabela:
    def test_tabela_sem_coluna_e_recusada(self):
        el = elemento("table")
        el["properties"]["columns"] = []

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))

    def test_linha_com_numero_errado_de_celulas_e_recusada(self):
        el = elemento("table")
        el["properties"]["rows"] = [{"cells": [{"content": "só uma"}]}]

        with pytest.raises(ValidationError, match="células"):
            validate_visual_schema(documento(el))

    def test_coluna_com_largura_invalida_e_recusada(self):
        el = elemento("table")
        el["properties"]["columns"][0]["width"] = 0

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el))

    def test_celula_pode_referenciar_um_campo(self):
        el = elemento("table")
        el["properties"]["rows"][0]["cells"][0] = {"field": "guest_name"}

        validate_visual_schema(documento(el), field_keys={"guest_name"})

    def test_celula_com_campo_inexistente_e_recusada(self):
        el = elemento("table")
        el["properties"]["rows"][0]["cells"][0] = {"field": "fantasma"}

        with pytest.raises(ValidationError):
            validate_visual_schema(documento(el), field_keys={"guest_name"})

    def test_tabela_sem_linhas_e_valida(self):
        """Uma tabela so com cabecalho definido ainda e um layout util."""
        el = elemento("table")
        el["properties"]["rows"] = []

        validate_visual_schema(documento(el))


# ---------------------------------------------------------------------------
# 5. Coordenadas
# ---------------------------------------------------------------------------


class TestConversaoDeCoordenadas:
    def test_documento_para_pdf_inverte_o_eixo_y(self):
        caixa = {"x": 72.0, "y": 100.0, "width": 200.0, "height": 20.0}

        pdf = geo.para_coordenadas_pdf(caixa, altura_da_pagina=842.0)

        # A caixa e ancorada pelo topo no documento e pela base no PDF.
        assert pdf["y"] == 842.0 - 100.0 - 20.0 == 722.0
        assert pdf["x"] == 72.0
        assert pdf["width"] == 200.0
        assert pdf["height"] == 20.0

    def test_a_altura_do_elemento_entra_na_conta(self):
        """
        Esquecer a altura desloca todo elemento por si mesmo -- erro que
        parece "quase certo" e passa despercebido em elementos baixos.
        """
        baixo = geo.para_coordenadas_pdf({"x": 0, "y": 100, "width": 10, "height": 2})
        alto = geo.para_coordenadas_pdf({"x": 0, "y": 100, "width": 10, "height": 200})

        assert baixo["y"] - alto["y"] == 198

    def test_ida_e_volta_devolve_o_original(self):
        caixa = {"x": 72.3456, "y": 120.9876, "width": 400.125, "height": 13.5}

        volta = geo.do_pdf_para_documento(geo.para_coordenadas_pdf(caixa))

        assert volta == pytest.approx(caixa)

    def test_o_topo_da_pagina_vira_o_alto_no_pdf(self):
        topo = geo.para_coordenadas_pdf(
            {"x": 0, "y": 0, "width": 10, "height": 10}, altura_da_pagina=A4_HEIGHT_PT
        )

        assert topo["y"] == pytest.approx(A4_HEIGHT_PT - 10)

    def test_linha_de_base_para_pdf(self):
        assert geo.linha_de_base_para_pdf(100, altura_da_pagina=842.0) == 742.0

    @pytest.mark.parametrize("zoom", [0.5, 1.0, 1.5, 2.0])
    def test_pontos_e_pixels_sao_inversos(self, zoom):
        assert geo.pixels_para_pontos(geo.pontos_para_pixels(72.5, zoom), zoom) == (
            pytest.approx(72.5)
        )

    def test_caixa_para_canvas_multiplica_tudo(self):
        canvas = geo.caixa_para_canvas(
            {"x": 10, "y": 20, "width": 30, "height": 40}, 2
        )

        assert canvas == {"x": 20, "y": 40, "width": 60, "height": 80}

    def test_caixa_do_canvas_desfaz(self):
        original = {"x": 10.25, "y": 20.5, "width": 30.75, "height": 40.125}

        volta = geo.caixa_do_canvas(geo.caixa_para_canvas(original, 1.75), 1.75)

        assert volta == pytest.approx(original)

    def test_zoom_zero_nao_passa_despercebido(self):
        with pytest.raises(ZeroDivisionError):
            geo.pixels_para_pontos(10, 0)

    def test_o_zoom_fica_dentro_dos_limites(self):
        assert geo.clamp_zoom(99) == geo.ZOOM_MAXIMO
        assert geo.clamp_zoom(0.01) == geo.ZOOM_MINIMO
        assert geo.clamp_zoom(1.0) == 1.0

    def test_ajustar_nunca_amplia_acima_do_tamanho_real(self):
        """Ampliar so porque sobra tela daria falsa impressao de tamanho."""
        assert geo.zoom_para_caber(5000) == 1.0

    def test_ajustar_encolhe_quando_falta_espaco(self):
        zoom = geo.zoom_para_caber(400, largura_da_pagina=A4_WIDTH_PT, margem=0)

        assert zoom == pytest.approx(400 / A4_WIDTH_PT)
        assert zoom < 1.0

    def test_ajustar_com_largura_impossivel_nao_quebra(self):
        assert geo.zoom_para_caber(10, margem=32) == geo.ZOOM_MINIMO


# ---------------------------------------------------------------------------
# 6. O validador nao altera o que recebe
# ---------------------------------------------------------------------------


def test_um_documento_completo_passa_nos_dois_modos():
    """O aperto da publicacao so alcanca o que esta incompleto."""
    doc = documento(
        elemento("text"),
        elemento("field", id="f1"),
        elemento("image", id="i1"),
        elemento("qrcode", id="q1"),
    )

    validate_visual_schema(doc, field_keys={"guest_name"}, asset_ids={1})
    validate_visual_schema(
        doc, field_keys={"guest_name"}, asset_ids={1}, para_publicar=True
    )


def test_validar_nao_modifica_o_documento():
    """
    Um validador que preenche padroes em silencio esconderia diferenca
    entre o que foi enviado e o que foi gravado.
    """
    doc = documento(elemento("text"), elemento("rect", id="r1"))
    antes = copy.deepcopy(doc)

    validate_visual_schema(doc)

    assert doc == antes
