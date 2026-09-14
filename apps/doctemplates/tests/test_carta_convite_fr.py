"""
Reconstrucao estrutural do modelo oficial frances (Etapa 3.3).

O servico testado aqui e `apps.doctemplates.services.carta_convite`
(era `modelo_fr.py` ate a Etapa 3.6, quando passou a gerar os quatro
idiomas; os outros tres tem cobertura em test_carta_convite_idiomas.py).

O que estes testes protegem, no fundo, e uma afirmacao so: o documento
frances agora existe como ELEMENTOS, nao como uma folha rasterizada com
texto por cima. Por isso ha testes que parecem obvios -- "nenhum
elemento e uma imagem de pagina inteira" -- e nao sao: eram exatamente
a saida facil que a arquitetura anterior tomava.

Os numeros conferidos aqui saem da medicao do PDF oficial. Quando um
deles mudar, o teste falha e alguem tem de dizer por que -- que e o
ponto: coordenada de documento oficial nao muda por acidente.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.doctemplates import datasources, elements, layout_schema
from apps.doctemplates.services import carta_convite

SLUG_FR = "carta-convite-fr"
OUTROS_OFICIAIS = ["carta-convite-nl", "carta-convite-en", "carta-convite-pt"]


@pytest.fixture
def layout():
    return carta_convite.layout("fr")


@pytest.fixture
def elementos(layout):
    return layout["elements"]


def por_id(elementos, identificador):
    for elemento in elementos:
        if elemento["id"] == identificador:
            return elemento
    raise AssertionError(f"não há elemento com id {identificador!r}")


def do_tipo(elementos, tipo):
    return [elemento for elemento in elementos if elemento["type"] == tipo]


def textos_do_layout(estrutura):
    """
    Todo texto FIXO do layout, venha de onde vier -- conteúdo solto,
    trecho de `mixed` ou célula de tabela.

    Percorrer a estrutura em vez de olhar o JSON serializado evita a
    armadilha de acusar sintaxe do próprio JSON como se fosse conteúdo.
    """
    encontrados = []
    if isinstance(estrutura, dict):
        if estrutura.get("kind") == "text" and isinstance(estrutura.get("value"), str):
            encontrados.append(estrutura["value"])
        for valor in estrutura.values():
            encontrados.extend(textos_do_layout(valor))
    elif isinstance(estrutura, list):
        for item in estrutura:
            encontrados.extend(textos_do_layout(item))
    return encontrados


# ===========================================================================
# 1. O modelo na biblioteca
# ===========================================================================


@pytest.mark.django_db
class TestModeloNaBiblioteca:
    def modelo(self):
        from apps.doctemplates.models import DocumentTemplate

        return DocumentTemplate.objects.get(slug=SLUG_FR)

    def test_o_modelo_fr_existe(self):
        assert self.modelo().language == "fr"

    def test_continua_sendo_oficial(self):
        assert self.modelo().is_system is True

    def test_continua_destravado(self):
        """A Etapa 3.3 não trava nada: o bloqueio vem só após validação visual."""
        assert self.modelo().is_locked is False

    def test_continua_ativo(self):
        assert self.modelo().is_active is True

    def test_tem_o_layout_reconstruido(self):
        assert len(self.modelo().layout["elements"]) == 23

    def test_o_layout_gravado_valida_pelo_contrato(self):
        self.modelo().full_clean()

    def test_o_tipo_de_documento_nao_foi_alterado(self):
        """A página continua sendo a do DocumentType, não a do PDF."""
        pagina = self.modelo().type.page

        assert pagina["width"] == 595.2756
        assert pagina["height"] == 841.8898
        assert pagina["unit"] == "pt"

    def test_os_outros_tres_idiomas_tambem_tem_desenho(self):
        """Etapa 3.6: EN/NL/PT deixaram de nascer vazios."""
        from apps.doctemplates.models import DocumentTemplate

        for slug in OUTROS_OFICIAIS:
            assert len(DocumentTemplate.objects.get(slug=slug).layout["elements"]) == 23

    def test_o_field_schema_do_fr_nao_foi_tocado(self):
        """A Etapa 3.3 mexe no desenho, não no formulário."""
        from apps.doctemplates.models import DocumentTemplate
        from apps.doctemplates.official_templates import CARTA_CONVITE_FIELD_SCHEMA

        modelo = DocumentTemplate.objects.get(slug=SLUG_FR)

        assert modelo.field_schema == CARTA_CONVITE_FIELD_SCHEMA


# ===========================================================================
# 2. O layout em si
# ===========================================================================


class TestLayout:
    def test_o_layout_e_valido(self, layout):
        layout_schema.validate_layout(layout)

    def test_esta_na_versao_do_formato(self, layout):
        assert layout["version"] == layout_schema.VERSION

    def test_os_ids_sao_unicos(self, elementos):
        identificadores = [elemento["id"] for elemento in elementos]

        assert len(identificadores) == len(set(identificadores))

    def test_os_ids_sao_estaveis_entre_execucoes(self):
        """Semeadura determinística: duas montagens dão o mesmo layout."""
        primeira = carta_convite.layout("fr")
        segunda = carta_convite.layout("fr")

        assert primeira == segunda

    def test_todo_tipo_pertence_ao_registro(self, elementos):
        for elemento in elementos:
            assert elemento["type"] in elements.codigos()

    def test_a_composicao_por_tipo(self, elementos):
        from collections import Counter

        assert Counter(e["type"] for e in elementos) == {
            "text": 12,
            "rich_text": 4,
            "rectangle": 3,
            "table": 1,
            "image": 1,
            "qr_code": 1,
            "line": 1,
        }

    def test_toda_geometria_e_finita_e_nao_negativa(self, elementos):
        for elemento in elementos:
            assert elemento["width"] >= 0
            assert elemento["height"] >= 0
            for chave in ("x", "y", "width", "height"):
                assert isinstance(elemento[chave], (int, float))

    def test_tudo_cabe_na_pagina(self, elementos):
        """Nada escapa do A4 do DocumentType."""
        for elemento in elementos:
            assert elemento["x"] >= 0
            assert elemento["y"] >= 0
            assert elemento["x"] + elemento["width"] <= 595.2756 + 0.5
            assert elemento["y"] + elemento["height"] <= 841.8898

    def test_as_coordenadas_guardam_as_casas_decimais(self, elementos):
        """Arredondar deslocaria o texto: o original foi medido com decimais."""
        titulo = por_id(elementos, "fr-titulo")

        assert titulo["x"] == carta_convite.MARGEM_ESQUERDA == 49.6063


# ===========================================================================
# 3. Nada depende do PDF original
# ===========================================================================


class TestIndependenciaDoPdf:
    def test_nenhum_elemento_cobre_a_pagina_inteira(self, elementos):
        """
        Uma imagem do tamanho da folha seria a página rasterizada -- a
        saída que esta etapa existe para não tomar.
        """
        for elemento in elementos:
            ocupa_tudo = elemento["width"] > 500 and elemento["height"] > 700
            assert not ocupa_tudo, f"{elemento['id']} cobre a página inteira"

    def test_a_unica_imagem_e_o_logo(self, elementos):
        imagens = do_tipo(elementos, "image")

        assert len(imagens) == 1
        assert imagens[0]["id"] == "fr-logo-ibz"

    def test_a_imagem_do_logo_e_pequena(self, elementos):
        """Um logo tem tamanho de logo; uma página raster, não."""
        logo = por_id(elementos, "fr-logo-ibz")

        assert logo["width"] < 60
        assert logo["height"] < 60

    def test_nao_ha_retangulo_branco_de_mascara(self, elementos):
        for elemento in do_tipo(elementos, "rectangle"):
            preenchimento = elemento["properties"].get("fill_color")
            assert preenchimento != "#FFFFFF"
            assert preenchimento != "#ffffff"

    def test_os_retangulos_sao_so_a_faixa_tricolor(self, elementos):
        cores = [e["properties"]["fill_color"] for e in do_tipo(elementos, "rectangle")]

        assert cores == list(carta_convite.FAIXA_CORES)

    def test_o_qr_nao_e_uma_imagem(self, elementos):
        qr = por_id(elementos, "fr-qr-code")

        assert qr["type"] == "qr_code"

    def test_nenhum_texto_virou_imagem(self, elementos):
        """Todo texto do documento é texto -- nenhum foi rasterizado."""
        textos = do_tipo(elementos, "text") + do_tipo(elementos, "rich_text")

        assert len(textos) == 16


# ===========================================================================
# 4. Conteúdo dinâmico estrutural
# ===========================================================================


class TestCamposDinamicos:
    def test_toda_referencia_existe_no_registro(self, layout):
        for referencia in layout_schema.referencias_usadas(layout):
            assert datasources.referencia_valida(referencia)

    def test_as_referencias_usadas(self, layout):
        assert layout_schema.referencias_usadas(layout) == {
            "anfitriao.nome",
            "anfitriao.nacionalidade",
            "anfitriao.data_nascimento",
            "anfitriao.documento_identidade",
            "anfitriao.endereco",
            "anfitriao.cidade",
            "anfitriao.telefone",
            "convidado.nome",
            "convidado.nacionalidade",
            "convidado.data_nascimento",
            "convidado.passaporte",
            "estadia.chegada",
            "estadia.partida",
            "calculado.data_documento",
            "calculado.duracao_dias",
        }

    def test_nenhum_campo_virou_placeholder_em_texto(self, layout):
        """
        `{{convidado.nome}}` dentro de uma string seria o atalho errado:
        o campo tem de ser um bloco estrutural.

        A conferência percorre os VALORES de texto -- olhar o JSON cru
        acusaria "}}" toda vez que dois objetos fechassem juntos.
        """
        for valor in textos_do_layout(layout):
            assert "{{" not in valor
            assert "}}" not in valor
            assert "%s" not in valor

    def test_nenhum_valor_de_amostra_ficou_no_documento(self, layout):
        """
        O PDF oficial vem preenchido com dados de exemplo. Se algum deles
        sobreviveu como texto fixo, virou dado errado no documento real.
        """
        import json

        bruto = json.dumps(layout, ensure_ascii=False)

        for amostra in (
            "Claire Dubois", "Carlos Eduardo Silva", "Brésilienne",
            "14/03/1985", "22/07/1990", "YY000000", "00000000",
            "Rue des Exemple", "Woluwe-Saint-Lambert", "+32 470",
            "10/10/2026", "24/10/2026", "09/09/2026", "15 jours",
        ):
            assert amostra not in bruto, f"o valor de amostra {amostra!r} virou texto fixo"

    def test_o_nome_do_anfitriao_aparece_duas_vezes(self, elementos):
        """Na declaração e na assinatura -- o mesmo campo, não texto repetido."""
        assinatura = por_id(elementos, "fr-assinatura-nome")

        assert assinatura["properties"]["content"] == {
            "kind": "field", "source": "anfitriao.nome",
        }

    def test_a_nacionalidade_do_anfitriao_serve_aos_dois_trechos(self, elementos):
        """
        "de nationalité belge" e "carte d'identité belge" são o mesmo
        dado -- o próprio gerador de PDF diz isso.
        """
        partes = por_id(elementos, "fr-declaracao")["properties"]["content"]["parts"]
        referencias = [p.get("source") for p in partes if p["kind"] == "field"]

        assert referencias.count("anfitriao.nacionalidade") == 2


# ===========================================================================
# 5. Ênfase dentro da linha corrida
# ===========================================================================


class TestEnfase:
    def test_a_declaracao_mistura_pesos(self, elementos):
        partes = por_id(elementos, "fr-declaracao")["properties"]["content"]["parts"]
        pesos = {parte.get("font_weight", "regular") for parte in partes}

        assert pesos == {"regular", "bold"}

    def test_o_nome_do_anfitriao_esta_em_negrito(self, elementos):
        partes = por_id(elementos, "fr-declaracao")["properties"]["content"]["parts"]
        nome = next(p for p in partes if p.get("source") == "anfitriao.nome")

        assert nome["font_weight"] == "bold"

    def test_a_data_de_nascimento_nao_esta_em_negrito(self, elementos):
        """No original só alguns campos são negrito; reproduzido como está."""
        partes = por_id(elementos, "fr-declaracao")["properties"]["content"]["parts"]
        nascimento = next(
            p for p in partes if p.get("source") == "anfitriao.data_nascimento"
        )

        assert "font_weight" not in nascimento

    def test_texto_fixo_tambem_pode_ter_enfase(self, elementos):
        """"visite privée" é negrito e não é campo nenhum."""
        partes = por_id(elementos, "fr-item-1")["properties"]["content"]["parts"]
        negritos = [p["value"] for p in partes if p.get("font_weight") == "bold"]

        assert negritos == ["visite privée"]


# ===========================================================================
# 6. A tabela
# ===========================================================================


class TestTabela:
    @pytest.fixture
    def tabela(self, elementos):
        return por_id(elementos, "fr-tabela")

    def test_e_um_elemento_table(self, tabela):
        assert tabela["type"] == "table"

    def test_a_geometria_medida(self, tabela):
        assert (tabela["x"], tabela["y"]) == (49.5, 201.5)
        assert (tabela["width"], tabela["height"]) == (497.0, 123.0)

    def test_duas_colunas_com_as_larguras_medidas(self, tabela):
        larguras = [coluna["width"] for coluna in tabela["properties"]["columns"]]

        assert larguras == [118.0, 379.0]

    def test_as_larguras_das_colunas_somam_a_largura_da_tabela(self, tabela):
        larguras = [coluna["width"] for coluna in tabela["properties"]["columns"]]

        assert sum(larguras) == tabela["width"]

    def test_cinco_linhas_com_as_alturas_medidas(self, tabela):
        alturas = [linha["min_height"] for linha in tabela["properties"]["rows"]]

        assert alturas == [24.0, 25.0, 25.0, 25.0, 24.0]

    def test_as_alturas_das_linhas_somam_a_altura_da_tabela(self, tabela):
        alturas = [linha["min_height"] for linha in tabela["properties"]["rows"]]

        assert sum(alturas) == tabela["height"]

    def test_a_espessura_da_borda_e_a_medida(self, tabela):
        assert tabela["properties"]["border_width"] == 0.75

    def test_toda_linha_tem_duas_celulas(self, tabela):
        for linha in tabela["properties"]["rows"]:
            assert len(linha["cells"]) == 2

    def test_os_rotulos_sao_negrito_e_os_valores_nao(self, tabela):
        for linha in tabela["properties"]["rows"]:
            rotulo, valor = linha["cells"]
            assert rotulo["bold"] is True
            assert valor["bold"] is False

    def test_os_rotulos_sao_os_do_documento(self, tabela):
        rotulos = [
            linha["cells"][0]["content"]["value"] for linha in tabela["properties"]["rows"]
        ]

        assert rotulos == [
            "Nom et prénom :",
            "Nationalité :",
            "Date de naissance :",
            "N° de passeport :",
            "Durée :",
        ]

    def test_os_valores_sao_campos_dinamicos(self, tabela):
        for linha in tabela["properties"]["rows"]:
            conteudo = linha["cells"][1]["content"]
            assert conteudo["kind"] in ("field", "mixed")

    def test_a_duracao_compoe_tres_campos(self, tabela):
        duracao = tabela["properties"]["rows"][4]["cells"][1]["content"]
        referencias = [p["source"] for p in duracao["parts"] if p["kind"] == "field"]

        assert referencias == [
            "estadia.chegada", "estadia.partida", "calculado.duracao_dias",
        ]

    def test_a_tabela_nao_foi_desenhada_com_retangulos(self, elementos):
        """As células não viraram retângulos soltos: o `table` dá conta."""
        retangulos_na_area = [
            elemento for elemento in do_tipo(elementos, "rectangle")
            if 200 <= elemento["y"] <= 325
        ]

        assert retangulos_na_area == []


# ===========================================================================
# 7. QR Code, logo e linha
# ===========================================================================


class TestGraficos:
    def test_o_qr_aponta_para_a_pagina_oficial(self, elementos):
        qr = por_id(elementos, "fr-qr-code")

        assert qr["properties"]["source"] == {
            "kind": "text",
            "value": "https://dofi.ibz.be/fr/themes/third-country-nationals/court-sejour",
        }

    def test_o_qr_e_quadrado(self, elementos):
        qr = por_id(elementos, "fr-qr-code")

        assert qr["width"] == qr["height"] == 78.0

    def test_o_qr_tem_correcao_de_erro_valida(self, elementos):
        qr = por_id(elementos, "fr-qr-code")

        assert qr["properties"]["error_correction"] in elements.QR_ERROR_LEVELS

    def test_o_logo_referencia_um_asset(self, elementos):
        origem = por_id(elementos, "fr-logo-ibz")["properties"]["source"]

        assert origem["kind"] == "asset"
        assert isinstance(origem["asset_id"], int)

    def test_o_logo_preserva_a_proporcao(self, elementos):
        propriedades = por_id(elementos, "fr-logo-ibz")["properties"]

        assert propriedades["preserve_aspect_ratio"] is True
        assert propriedades["fit"] in elements.IMAGE_FITS

    def test_a_linha_da_assinatura_e_uma_linha(self, elementos):
        linha = por_id(elementos, "fr-assinatura-linha")

        assert linha["type"] == "line"
        assert linha["height"] == 0.0

    def test_a_espessura_da_linha_veio_do_glifo_medido(self, elementos):
        linha = por_id(elementos, "fr-assinatura-linha")

        assert linha["properties"]["thickness"] == pytest.approx(0.6982, abs=0.0001)

    def test_a_linha_nao_ficou_como_sublinhados(self, layout):
        """No original é uma fileira de "_"; aqui é uma régua de verdade."""
        import json

        assert "____" not in json.dumps(layout, ensure_ascii=False)

    def test_a_faixa_tricolor_tem_tres_partes_iguais(self, elementos):
        faixas = do_tipo(elementos, "rectangle")
        larguras = {faixa["width"] for faixa in faixas}

        assert len(larguras) == 1
        assert sum(f["width"] for f in faixas) == carta_convite.FAIXA_LARGURA_TOTAL

    def test_a_faixa_fica_no_topo_da_pagina(self, elementos):
        for faixa in do_tipo(elementos, "rectangle"):
            assert faixa["y"] == 0.0


# ===========================================================================
# 8. Texto: hierarquia e medidas
# ===========================================================================


class TestTexto:
    def test_o_titulo_e_maior_que_o_corpo(self, elementos):
        titulo = por_id(elementos, "fr-titulo")
        corpo = por_id(elementos, "fr-destinatario")

        assert titulo["properties"]["font_size"] == 14.0
        assert corpo["properties"]["font_size"] == 11.0

    def test_o_titulo_e_negrito_e_centrado(self, elementos):
        propriedades = por_id(elementos, "fr-titulo")["properties"]

        assert propriedades["font_weight"] == "bold"
        assert propriedades["align"] == "center"

    def test_os_paragrafos_do_corpo_sao_justificados(self, elementos):
        for identificador in ("fr-declaracao", "fr-fecho-1", "fr-fecho-2", "fr-fecho-3"):
            assert por_id(elementos, identificador)["properties"]["align"] == "justify"

    def test_local_e_data_alinham_a_direita(self, elementos):
        assert por_id(elementos, "fr-local-e-data")["properties"]["align"] == "right"

    def test_a_entrelinha_e_a_medida(self, elementos):
        entrelinha = por_id(elementos, "fr-destinatario")["properties"]["line_height"]

        assert entrelinha * 11.0 == pytest.approx(13.5)

    def test_a_fonte_e_uma_que_o_motor_conhece(self, elementos):
        for elemento in elementos:
            familia = elemento["properties"].get("font_family")
            if familia is not None:
                assert familia in elements.FONT_FAMILIES

    def test_os_marcadores_da_lista_ficam_a_esquerda_do_corpo(self, elementos):
        for numero in (1, 2, 3):
            marcador = por_id(elementos, f"fr-item-{numero}-marcador")
            corpo = por_id(elementos, f"fr-item-{numero}")
            assert marcador["x"] < corpo["x"]

    def test_marcador_e_corpo_partilham_a_mesma_linha(self, elementos):
        """Medido: não é recuo de primeira linha, são dois elementos."""
        for numero in (1, 2, 3):
            marcador = por_id(elementos, f"fr-item-{numero}-marcador")
            corpo = por_id(elementos, f"fr-item-{numero}")
            assert marcador["y"] == corpo["y"]

    def test_a_altura_reservada_acompanha_o_numero_de_linhas(self, elementos):
        """A declaração ocupa três linhas no original."""
        declaracao = por_id(elementos, "fr-declaracao")

        assert declaracao["height"] == pytest.approx(3 * 13.5)

    def test_os_elementos_estao_em_ordem_de_leitura(self, elementos):
        """A ordem da lista é a de desenho; aqui ela também é legível."""
        assinatura = por_id(elementos, "fr-assinatura-rotulo")

        assert elementos.index(assinatura) == len(elementos) - 1


# ===========================================================================
# 9. Nada da arquitetura antiga entrou
# ===========================================================================


class TestSemArquiteturaAntiga:
    def test_o_servico_nao_importa_a_arquitetura_antiga(self):
        import inspect

        codigo = inspect.getsource(carta_convite)

        for proibido in ("TemplateVersion", "LetterTemplate"):
            assert proibido not in codigo, f"{proibido} não pode aparecer aqui"

    def test_o_layout_nao_usa_z_index(self, layout):
        """No contrato novo a camada é a ordem da lista."""
        import json

        assert "z_index" not in json.dumps(layout)

    def test_nao_ha_tipos_do_contrato_antigo(self, elementos):
        """`rect`/`qrcode`/`field` eram do contrato aposentado, não deste."""
        tipos = {elemento["type"] for elemento in elementos}

        assert tipos.isdisjoint({"rect", "qrcode", "field", "paragraph"})

    def test_a_pagina_nao_se_repete_no_layout(self, layout):
        """A página vem do DocumentType; o layout não a redeclara."""
        assert "page" not in layout
        assert "schema_version" not in layout


# ===========================================================================
# 10. Semeadura: idempotente e não destrutiva
# ===========================================================================


@pytest.mark.django_db
class TestSemeadura:
    def modelo(self):
        from apps.doctemplates.models import DocumentTemplate

        return DocumentTemplate.objects.get(slug=SLUG_FR)

    def test_aplicar_nao_sobrescreve_layout_existente(self):
        from apps.doctemplates.models import DocumentTemplate

        DocumentTemplate.objects.filter(slug=SLUG_FR).update(
            layout={"version": 1, "elements": []}
        )

        assert carta_convite.aplicar(DocumentTemplate, "fr") is None
        assert self.modelo().layout == {"version": 1, "elements": []}

    def test_forcar_reescreve(self):
        from apps.doctemplates.models import DocumentTemplate

        DocumentTemplate.objects.filter(slug=SLUG_FR).update(
            layout={"version": 1, "elements": []}
        )

        carta_convite.aplicar(DocumentTemplate, "fr", forcar=True)

        assert len(self.modelo().layout["elements"]) == 23

    def test_rodar_duas_vezes_da_o_mesmo_resultado(self):
        from apps.doctemplates.models import DocumentTemplate

        primeiro = self.modelo().layout
        carta_convite.aplicar(DocumentTemplate, "fr", forcar=True)

        assert self.modelo().layout == primeiro

    def test_a_semeadura_nao_trava_o_modelo(self):
        from apps.doctemplates.models import DocumentTemplate

        carta_convite.aplicar(DocumentTemplate, "fr", forcar=True)

        assert self.modelo().is_locked is False

    def test_vincular_logo_troca_so_o_asset(self):
        from apps.doctemplates.models import DocumentTemplate

        antes = self.modelo().layout

        carta_convite.vincular_logo(DocumentTemplate, "fr", 77)

        depois = self.modelo().layout
        assert por_id(depois["elements"], "fr-logo-ibz")["properties"]["source"] == {
            "kind": "asset", "asset_id": 77,
        }
        # todo o resto ficou igual
        outros_antes = [e for e in antes["elements"] if e["id"] != "fr-logo-ibz"]
        outros_depois = [e for e in depois["elements"] if e["id"] != "fr-logo-ibz"]
        assert outros_antes == outros_depois

    def test_vincular_o_mesmo_asset_duas_vezes_nao_regrava(self):
        from apps.doctemplates.models import DocumentTemplate

        carta_convite.vincular_logo(DocumentTemplate, "fr", 77)

        assert carta_convite.vincular_logo(DocumentTemplate, "fr", 77) is None

    def test_a_semeadura_nao_cria_um_segundo_modelo(self):
        from apps.doctemplates.models import DocumentTemplate

        carta_convite.aplicar(DocumentTemplate, "fr", forcar=True)

        assert DocumentTemplate.objects.filter(slug=SLUG_FR).count() == 1


# ===========================================================================
# 11. O logo sai do PDF oficial
# ===========================================================================


class TestLogo:
    def test_extrai_um_png(self):
        assert carta_convite.extrair_logo_ibz()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_o_recorte_tem_a_proporcao_da_caixa_do_layout(self):
        import io as _io

        from PIL import Image

        figura = Image.open(_io.BytesIO(carta_convite.extrair_logo_ibz()))
        proporcao_da_arte = figura.width / figura.height
        proporcao_da_caixa = carta_convite.LOGO_LARGURA / carta_convite.LOGO_ALTURA

        assert proporcao_da_arte == pytest.approx(proporcao_da_caixa, abs=0.01)

    def test_o_recorte_tira_a_margem_branca(self):
        """O arquivo dentro do PDF tem folga em volta; a arte, não."""
        import io as _io

        from PIL import Image, ImageChops

        figura = Image.open(_io.BytesIO(carta_convite.extrair_logo_ibz())).convert("RGB")
        branco = Image.new("RGB", figura.size, (255, 255, 255))

        assert ImageChops.difference(figura, branco).getbbox() == (
            0, 0, figura.width, figura.height,
        )

    def test_um_pdf_inexistente_falha_claramente(self, tmp_path):
        with pytest.raises(carta_convite.LogoNaoEncontradoError, match="não foi encontrado"):
            carta_convite.extrair_logo_ibz(tmp_path / "nao-existe.pdf")


@pytest.mark.django_db
class TestAssetDoLogo:
    def test_cria_o_asset_uma_vez_so(self, tmp_path, settings):
        from apps.content.models import Asset

        settings.MEDIA_ROOT = tmp_path

        primeiro, criado = carta_convite.garantir_asset_do_logo(Asset)
        segundo, recriado = carta_convite.garantir_asset_do_logo(Asset)

        assert criado is True
        assert recriado is False
        assert primeiro.pk == segundo.pk
        assert Asset.objects.filter(key=carta_convite.LOGO_CHAVE_DO_ASSET).count() == 1

    def test_reconstruir_liga_o_asset_ao_layout(self, tmp_path, settings):
        from apps.content.models import Asset
        from apps.doctemplates.models import DocumentTemplate

        settings.MEDIA_ROOT = tmp_path

        resultado = carta_convite.reconstruir(DocumentTemplate, Asset, "fr")

        asset = Asset.objects.get(key=carta_convite.LOGO_CHAVE_DO_ASSET)
        origem = por_id(
            resultado.modelo.layout["elements"], "fr-logo-ibz"
        )["properties"]["source"]
        assert origem["asset_id"] == asset.pk

    def test_reconstruir_relata_o_que_fez(self, tmp_path, settings):
        """O relato é o que permite ao comando dizer "criado" ou "reaproveitado"."""
        from apps.content.models import Asset
        from apps.doctemplates.models import DocumentTemplate

        settings.MEDIA_ROOT = tmp_path

        primeiro = carta_convite.reconstruir(DocumentTemplate, Asset, "fr")
        segundo = carta_convite.reconstruir(DocumentTemplate, Asset, "fr")

        assert primeiro.asset_criado is True
        assert primeiro.logo_vinculado is True
        assert segundo.asset_criado is False
        assert segundo.logo_vinculado is False
        # o layout ja vinha da migration nos dois casos
        assert primeiro.layout_gravado is False

    def test_reconstruir_e_idempotente(self, tmp_path, settings):
        from apps.content.models import Asset
        from apps.doctemplates.models import DocumentTemplate

        settings.MEDIA_ROOT = tmp_path

        primeiro = carta_convite.reconstruir(DocumentTemplate, Asset, "fr").modelo.layout
        segundo = carta_convite.reconstruir(DocumentTemplate, Asset, "fr").modelo.layout

        assert primeiro == segundo
        assert Asset.objects.filter(key=carta_convite.LOGO_CHAVE_DO_ASSET).count() == 1


# ===========================================================================
# 12. Inventário
# ===========================================================================


class TestInventario:
    def test_cobre_todos_os_elementos(self, layout):
        assert len(carta_convite.inventario(layout)) == len(layout["elements"])

    def test_preserva_a_ordem_das_camadas(self, layout):
        linhas = carta_convite.inventario(layout)

        assert [linha["id"] for linha in linhas] == [
            elemento["id"] for elemento in layout["elements"]
        ]

    def test_lista_os_campos_de_cada_elemento(self, layout):
        linhas = {linha["id"]: linha for linha in carta_convite.inventario(layout)}

        assert linhas["fr-assinatura-nome"]["campos"] == ["anfitriao.nome"]
        assert linhas["fr-titulo"]["campos"] == []

    def test_enxerga_os_campos_dentro_da_tabela(self, layout):
        linhas = {linha["id"]: linha for linha in carta_convite.inventario(layout)}

        assert "convidado.passaporte" in linhas["fr-tabela"]["campos"]

    def test_o_texto_sai_legivel(self, layout):
        saida = carta_convite.inventario_texto(layout)

        assert "fr-titulo" in saida
        assert "23 elementos" in saida
        assert "estadia.chegada" in saida


# ===========================================================================
# 13. A reconstrução conferida contra o PDF oficial
# ===========================================================================


def baselines_do_pdf():
    """
    As linhas de base de cada linha de texto do PDF oficial, medidas do
    próprio arquivo.

    O CTM da página é `[0.75, 0, 0, -0.75, ...]`: sem aplicar essa escala
    o tamanho da fonte sai 4/3 maior do que é.
    """
    from pypdf import PdfReader

    pagina = PdfReader(str(carta_convite.CAMINHO_DO_PDF)).pages[0]
    altura = float(pagina.mediabox.height)
    encontrados = []

    def visitar(texto, cm, tm, fonte, tamanho):
        if not texto or not texto.strip():
            return
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        escala = (cm[3] ** 2 + cm[1] ** 2) ** 0.5 or 1
        encontrados.append((round(altura - y, 2), round(x, 3), tamanho * escala))

    pagina.extract_text(visitor_text=visitar)
    return encontrados


@pytest.fixture(scope="module")
def medidas():
    """Medido uma vez só: abrir o PDF a cada teste seria desperdício."""
    return baselines_do_pdf()


class TestConfereComOPdfOficial:
    """
    O teste que dá sentido a todos os outros: os números do layout são os
    do documento oficial, não uma aproximação que ficou parecida.
    """

    # elemento -> linha de base da sua PRIMEIRA linha no PDF
    PRIMEIRA_BASE = {
        "fr-titulo": 64.44,
        "fr-subtitulo": 78.06,
        "fr-destinatario": 134.06,
        "fr-declaracao": 159.06,
        "fr-item-1": 371.06,
        "fr-item-2": 384.06,
        "fr-item-3": 411.06,
        "fr-fecho-1": 475.56,
        "fr-fecho-2": 514.56,
        "fr-fecho-3": 567.06,
        "fr-local-e-data": 631.56,
        "fr-assinatura-nome": 696.06,
        "fr-assinatura-rotulo": 709.56,
    }

    def test_o_pdf_oficial_esta_no_lugar(self):
        assert carta_convite.CAMINHO_DO_PDF.is_file()

    def test_as_bases_medidas_existem_no_pdf(self, medidas):
        bases = {base for base, _x, _tam in medidas}

        assert set(self.PRIMEIRA_BASE.values()) <= bases

    @pytest.mark.parametrize("identificador", sorted(PRIMEIRA_BASE))
    def test_cada_texto_cai_na_linha_de_base_do_original(
        self, identificador, elementos, medidas
    ):
        elemento = por_id(elementos, identificador)
        base_reconstruida = elemento["y"] + elemento["properties"]["font_size"] * (
            carta_convite.ASCENT
        )

        assert base_reconstruida == pytest.approx(
            self.PRIMEIRA_BASE[identificador], abs=0.01
        )

    def test_os_tamanhos_de_fonte_sao_os_do_pdf(self, medidas):
        """11pt no corpo e 14pt no título -- não 14.67 e 18.67."""
        tamanhos = {round(tam, 2) for _base, _x, tam in medidas}

        assert tamanhos == {11.0, 14.0}

    def test_a_margem_esquerda_e_a_do_pdf(self, medidas):
        do_corpo = [x for base, x, _t in medidas if base == 134.06]

        assert min(do_corpo) == pytest.approx(carta_convite.MARGEM_ESQUERDA, abs=0.001)

    def test_a_entrelinha_e_a_do_pdf(self, medidas):
        """13,5pt de baseline a baseline, medido em linhas seguidas."""
        bases = sorted({base for base, _x, _t in medidas})
        distancias = [
            round(b - a, 2) for a, b in zip(bases, bases[1:], strict=False)
        ]

        assert distancias.count(13.5) >= 8
        assert carta_convite.ALTURA_DA_LINHA == 13.5

    def test_o_marcador_e_o_corpo_da_lista_nas_posicoes_medidas(self, elementos, medidas):
        xs = sorted({x for base, x, _t in medidas if base == 371.06})

        assert xs[0] == pytest.approx(carta_convite.LISTA_X_MARCADOR, abs=0.001)
        assert xs[1] == pytest.approx(carta_convite.LISTA_X_CORPO, abs=0.001)


# ===========================================================================
# 14. As referências novas do registro
# ===========================================================================


class TestReferenciasNovas:
    @pytest.mark.parametrize(
        "referencia",
        [
            "anfitriao.nacionalidade",
            "anfitriao.data_nascimento",
            "anfitriao.documento_identidade",
            "estadia.chegada",
            "estadia.partida",
            "calculado.duracao_dias",
        ],
    )
    def test_a_referencia_existe(self, referencia):
        assert datasources.referencia_valida(referencia)

    def test_estadia_e_uma_fonte_registrada(self):
        assert datasources.fonte("estadia").chaves == ("chegada", "partida")

    def test_as_datas_sao_declaradas_como_data(self):
        for chave in ("chegada", "partida"):
            assert datasources.fonte("estadia").campo(chave).kind == "data"

    def test_a_duracao_e_declarada_como_numero(self):
        assert datasources.fonte("calculado").campo("duracao_dias").kind == "numero"

    def test_as_referencias_antigas_continuam_valendo(self):
        """Estender o registro não pode invalidar layout já gravado."""
        for referencia in (
            "documento.numero", "documento.data", "convidado.nome",
            "anfitriao.endereco", "calculado.data_documento",
        ):
            assert datasources.referencia_valida(referencia)

    def test_uma_referencia_inventada_continua_recusada(self):
        with pytest.raises(ValidationError):
            layout_schema.validar_conteudo(
                {"kind": "field", "source": "estadia.fantasma"}, "c"
            )
