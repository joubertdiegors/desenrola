"""
Integracao: carta-convite-fr -> renderer -> PDF (Etapa 3.4).

O caminho inteiro, com o modelo reconstruido na Etapa 3.3 e os valores
vindo de um contexto de teste. O ponto central e que o PDF sai dos 23
elementos do layout -- nao de uma imagem da pagina oficial com texto por
cima, que era como a arquitetura anterior resolvia.

OS DADOS SAO DE TESTE, NAO DO MODELO
------------------------------------
`DADOS` reproduz os valores visiveis no PDF oficial, mas vive AQUI. O
modelo nao os guarda -- e ha teste que confirma isso, porque um modelo
que guardasse dados de uma pessoa deixaria de servir a todas as outras.
"""

import io

import pytest
from pypdf import PdfReader

from apps.content.models import Asset
from apps.doctemplates.models import DocumentTemplate
from apps.doctemplates.services import dados_de_exemplo, modelo_fr, pdf

pytestmark = pytest.mark.django_db

SLUG = "carta-convite-fr"

# Os valores visiveis no documento oficial. Vem do modulo compartilhado
# para que a previa gerada pelo comando e o que este teste afirma nunca
# possam divergir.
DADOS = dados_de_exemplo.para(SLUG)


@pytest.fixture
def modelo(tmp_path, settings):
    """O modelo oficial com o logo materializado, em MEDIA_ROOT próprio."""
    settings.MEDIA_ROOT = tmp_path
    modelo_fr.reconstruir(DocumentTemplate, Asset)
    return DocumentTemplate.objects.get(slug=SLUG)


@pytest.fixture
def gerado(modelo):
    dados, relatorio = pdf.render_template(modelo, DADOS)
    return dados, relatorio


@pytest.fixture
def documento(gerado):
    return PdfReader(io.BytesIO(gerado[0]))


def texto_do(documento):
    return documento.pages[0].extract_text()


# ===========================================================================
# 1. O PDF
# ===========================================================================


class TestOPdf:
    def test_abre_corretamente(self, gerado):
        dados, _ = gerado

        assert dados[:5] == b"%PDF-"
        assert PdfReader(io.BytesIO(dados)).pages

    def test_tem_uma_unica_pagina(self, documento):
        assert len(documento.pages) == 1

    def test_a_pagina_e_a4(self, documento):
        pagina = documento.pages[0]

        assert float(pagina.mediabox.width) == pytest.approx(595.2756, abs=0.001)
        assert float(pagina.mediabox.height) == pytest.approx(841.8898, abs=0.001)

    def test_a_pagina_veio_do_tipo_de_documento(self, modelo, documento):
        assert float(documento.pages[0].mediabox.width) == pytest.approx(
            modelo.type.page["width"], abs=0.001
        )

    def test_os_23_elementos_foram_processados(self, gerado):
        _dados, relatorio = gerado

        assert relatorio["elementos"] == 23
        assert relatorio["elementos"] == len(
            DocumentTemplate.objects.get(slug=SLUG).layout["elements"]
        )

    def test_todos_os_23_foram_desenhados(self, gerado):
        """Processar não basta: cada um tem de ter produzido algo."""
        _dados, relatorio = gerado

        assert relatorio["desenhados"] == 23

    def test_a_composicao_por_tipo(self, gerado):
        _dados, relatorio = gerado

        assert relatorio["por_tipo"] == {
            "rectangle": 3, "text": 12, "rich_text": 4,
            "table": 1, "image": 1, "qr_code": 1, "line": 1,
        }

    def fontes_do_documento(self, documento):
        return {
            str(nome): recurso.get_object()
            for nome, recurso in documento.pages[0]["/Resources"]["/Font"].items()
        }

    def test_a_fonte_usada_esta_embutida(self, documento):
        """
        Fonte não embutida muda de aparência em cada leitor. As faces
        Liberation entram como subconjunto TrueType, com FontFile2.
        """
        embutidas = [
            fonte for fonte in self.fontes_do_documento(documento).values()
            if "Liberation" in str(fonte.get("/BaseFont"))
        ]

        assert embutidas
        for fonte in embutidas:
            descritor = fonte["/FontDescriptor"].get_object()
            assert "/FontFile2" in descritor

    def test_nenhum_texto_e_desenhado_com_fonte_nao_embutida(self, gerado, documento):
        """
        O reportlab DECLARA Helvetica e Times nos recursos de toda
        página e ainda abre um bloco `BT /F1 12 Tf ET` vazio -- sem
        desenhar nada. O que importa é que nenhum bloco que MOSTRE texto
        (`Tj`) esteja com uma dessas selecionada: aí sim parte do
        documento sairia com a fonte que o leitor tivesse à mão.
        """
        import re

        operadores = PdfReader(io.BytesIO(gerado[0])).pages[0].get_contents().get_data()
        fontes = self.fontes_do_documento(documento)
        embutidas = {
            nome for nome, fonte in fontes.items()
            if "Liberation" in str(fonte.get("/BaseFont"))
        }

        assert set(fontes) - embutidas, "o cenário pressupõe as padrão declaradas"

        blocos_com_texto = 0
        for bloco in operadores.decode("latin-1").split("BT")[1:]:
            bloco = bloco.split("ET")[0]
            if "Tj" not in bloco and "TJ" not in bloco:
                continue
            blocos_com_texto += 1
            usadas = set(re.findall(r"(/F[\w+]+)\s+[\d.]+\s+Tf", bloco))
            assert usadas <= embutidas, f"bloco desenha com {usadas - embutidas}"

        assert blocos_com_texto > 20

    def test_usa_regular_e_negrito(self, documento):
        nomes = {
            str(fonte.get("/BaseFont"))
            for fonte in self.fontes_do_documento(documento).values()
            if "Liberation" in str(fonte.get("/BaseFont"))
        }

        assert any("Bold" in nome for nome in nomes)
        assert any("Bold" not in nome for nome in nomes)


# ===========================================================================
# 2. Não há PDF oficial por baixo
# ===========================================================================


class TestSemFundoOficial:
    def test_a_unica_imagem_e_o_logo(self, documento):
        """
        Se a página oficial estivesse sendo usada como fundo, haveria
        uma imagem do tamanho da folha aqui.
        """
        recursos = documento.pages[0]["/Resources"]
        imagens = [
            x.get_object() for x in (recursos.get("/XObject") or {}).values()
            if x.get_object().get("/Subtype") == "/Image"
        ]

        assert len(imagens) == 1

    def test_a_imagem_tem_tamanho_de_logo(self, documento):
        recursos = documento.pages[0]["/Resources"]
        imagem = next(
            x.get_object() for x in recursos["/XObject"].values()
            if x.get_object().get("/Subtype") == "/Image"
        )

        # A arte do logo tem menos de 250px de lado; uma pagina
        # rasterizada teria milhares.
        assert int(imagem["/Width"]) < 250
        assert int(imagem["/Height"]) < 250

    def test_nao_ha_pagina_importada_de_outro_pdf(self, documento):
        """Um PDF embutido entraria como Form XObject."""
        recursos = documento.pages[0]["/Resources"]
        formularios = [
            x.get_object() for x in (recursos.get("/XObject") or {}).values()
            if x.get_object().get("/Subtype") == "/Form"
        ]

        assert formularios == []

    def test_o_texto_e_texto_de_verdade(self, documento):
        """Texto rasterizado não sairia na extração."""
        assert len(texto_do(documento)) > 1000

    def test_o_renderer_nao_abriu_o_pdf_oficial(self, modelo):
        """
        Prova de comportamento: com o PDF oficial fora do lugar, a
        geração continua funcionando igual.
        """
        caminho = modelo_fr.CAMINHO_DO_PDF
        original = caminho.read_bytes()
        caminho.unlink()
        try:
            dados, relatorio = pdf.render_template(modelo, DADOS)
        finally:
            caminho.write_bytes(original)

        assert relatorio["desenhados"] == 23
        assert "Claire Dubois" in PdfReader(io.BytesIO(dados)).pages[0].extract_text()


# ===========================================================================
# 3. Os dados dinâmicos
# ===========================================================================


class TestDadosDinamicos:
    @pytest.mark.parametrize("valor", sorted(set(DADOS.values())))
    def test_cada_valor_do_contexto_aparece(self, documento, valor):
        assert valor in texto_do(documento)

    def test_o_texto_fixo_do_documento_aparece(self, documento):
        saida = texto_do(documento)

        for trecho in (
            "LETTRE D'INVITATION ET D’HÉBERGEMENT",
            "(COURT SÉJOUR EN BELGIQUE)",
            "À l’attention des autorités compétentes.",
            "Nom et prénom :",
            "Signature de l’invitante",
        ):
            assert trecho in saida

    def test_os_valores_vem_do_contexto_e_nao_do_codigo(self, modelo):
        """
        Trocando o contexto, o documento muda. Se algum valor estivesse
        fixo no renderer ou no layout, ele sobreviveria à troca.
        """
        outros = dict(DADOS)
        outros["convidado.nome"] = "Zoé Martin"
        outros["anfitriao.nome"] = "Jean Petit"

        dados, _ = pdf.render_template(modelo, outros)
        saida = PdfReader(io.BytesIO(dados)).pages[0].extract_text()

        assert "Zoé Martin" in saida
        assert "Jean Petit" in saida
        assert "Carlos Eduardo Silva" not in saida
        assert "Claire Dubois" not in saida

    def test_o_modelo_nao_guarda_os_dados(self, modelo):
        pdf.render_template(modelo, DADOS)

        modelo.refresh_from_db()
        bruto = str(modelo.layout)
        for valor in ("Claire Dubois", "Carlos Eduardo Silva", "YY000000"):
            assert valor not in bruto

    def test_o_contexto_cobre_todos_os_campos_do_layout(self, modelo):
        assert pdf.campos_do_layout(modelo.layout) == set(DADOS)

    def test_faltando_um_campo_a_geracao_falha(self, modelo):
        """Um documento oficial com campo vazio é um documento errado."""
        incompleto = {k: v for k, v in DADOS.items() if k != "convidado.passaporte"}

        with pytest.raises(pdf.ValorAusenteError, match="passaporte"):
            pdf.render_template(modelo, incompleto)

    def test_nenhum_placeholder_textual_no_documento(self, documento):
        saida = texto_do(documento)

        assert "{{" not in saida
        assert "convidado.nome" not in saida


# ===========================================================================
# 4. QR, logo e tabela
# ===========================================================================


class TestElementosDoFr:
    def test_o_qr_e_desenhado_e_nao_colado(self, documento):
        """
        O QR é vetorial: se fosse o raster do documento oficial, ele
        apareceria como uma segunda imagem.
        """
        recursos = documento.pages[0]["/Resources"]
        imagens = [
            x.get_object() for x in (recursos.get("/XObject") or {}).values()
            if x.get_object().get("/Subtype") == "/Image"
        ]

        assert len(imagens) == 1  # só o logo

    def test_o_qr_muda_quando_o_conteudo_muda(self, modelo):
        """Prova de que ele é gerado, e não uma figura fixa."""
        import copy

        outro = copy.deepcopy(modelo.layout)
        for elemento in outro["elements"]:
            if elemento["id"] == "fr-qr-code":
                elemento["properties"]["source"] = {
                    "kind": "text", "value": "https://exemplo.be/outro",
                }

        primeiro, _ = pdf.render_template(modelo, DADOS)
        modelo.layout = outro
        segundo, _ = pdf.render_layout(
            outro, modelo.type.page, pdf.Contexto(DADOS),
            assets=pdf._carregar_assets(outro),
        )

        assert primeiro != segundo

    def test_o_logo_vem_do_asset(self, modelo, documento):
        asset = Asset.objects.get(key=modelo_fr.LOGO_CHAVE_DO_ASSET)
        elemento = next(
            e for e in modelo.layout["elements"] if e["id"] == modelo_fr.ID_DO_LOGO
        )

        assert elemento["properties"]["source"]["asset_id"] == asset.pk
        assert "/XObject" in documento.pages[0]["/Resources"]

    def test_sem_o_asset_a_geracao_falha_claramente(self, modelo):
        """
        O asset do logo esta protegido contra exclusao pelo vinculo
        `DocumentTemplateAsset` (PROTECT). Para simular "o arquivo sumiu"
        e conferir que o RENDERER falha alto, o vinculo e desfeito antes
        -- e exatamente o cenario que a protecao existe para impedir.
        """
        from apps.doctemplates.models import DocumentTemplateAsset

        DocumentTemplateAsset.objects.filter(asset__key=modelo_fr.LOGO_CHAVE_DO_ASSET).delete()
        Asset.objects.filter(key=modelo_fr.LOGO_CHAVE_DO_ASSET).delete()

        with pytest.raises(pdf.AssetAusenteError):
            pdf.render_template(modelo, DADOS)

    def test_a_tabela_traz_rotulos_e_valores(self, documento):
        saida = texto_do(documento)

        assert "Nationalité :" in saida
        assert "Brésilienne" in saida
        assert "N° de passeport :" in saida
        assert "YY000000" in saida

    def test_a_linha_da_duracao_compoe_tres_campos(self, documento):
        saida = texto_do(documento)

        assert "du 10/10/2026 au 24/10/2026 (15 jours)" in saida

    def test_a_faixa_tricolor_pinta_as_tres_cores(self, gerado):
        dados, _ = gerado
        operadores = PdfReader(io.BytesIO(dados)).pages[0].get_contents().get_data()

        assert b"0 0 0 rg" in operadores        # preto
        assert b"1 0 0 rg" in operadores        # vermelho
        assert b"1 .85" in operadores           # #FFD966

    def test_o_endereco_aparece_nos_dois_lugares(self, documento):
        """O mesmo campo é impresso na declaração e no item 2."""
        assert texto_do(documento).count(DADOS["anfitriao.endereco"]) == 2

    def test_o_nome_do_anfitriao_aparece_nos_dois_lugares(self, documento):
        assert texto_do(documento).count(DADOS["anfitriao.nome"]) == 2


# ===========================================================================
# 5. Fidelidade geométrica ao documento oficial
# ===========================================================================


class TestFidelidade:
    """
    Compara o PDF gerado com o oficial pelas POSICOES do texto, medidas
    do mesmo jeito nos dois. E o que impede uma regressao silenciosa: o
    documento continuaria "parecendo certo" com meio milimetro de
    deslocamento em tudo.
    """

    def medir(self, dados):
        leitor = PdfReader(dados if isinstance(dados, str) else io.BytesIO(dados))
        pagina = leitor.pages[0]
        altura = float(pagina.mediabox.height)
        linhas = {}

        def visitar(texto, cm, tm, fonte, tamanho):
            if not texto or not texto.strip():
                return
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            escala = (cm[3] ** 2 + cm[1] ** 2) ** 0.5 or 1
            base = round(altura - y, 2)
            linhas.setdefault(base, []).append((round(x, 3), tamanho * escala))

        pagina.extract_text(visitor_text=visitar)
        return linhas

    @pytest.fixture
    def medidas(self, gerado):
        return self.medir(gerado[0]), self.medir(str(modelo_fr.CAMINHO_DO_PDF))

    # As linhas de base do documento oficial, medidas na Etapa 3.3.
    BASES = [64.44, 78.06, 134.06, 159.06, 172.56, 186.06, 371.06, 384.06,
             397.56, 411.06, 424.56, 475.56, 489.06, 514.56, 528.06, 541.56,
             567.06, 580.56, 631.56, 696.06, 709.56]

    @pytest.mark.parametrize("base", BASES)
    def test_cada_linha_cai_na_baseline_do_oficial(self, medidas, base):
        gerado, _oficial = medidas

        assert base in gerado, f"nenhuma linha do gerado na base {base}"

    def test_a_margem_esquerda_e_a_do_oficial(self, medidas):
        gerado, oficial = medidas

        for base in (134.06, 475.56, 567.06):
            assert min(x for x, _t in gerado[base]) == pytest.approx(
                min(x for x, _t in oficial[base]), abs=0.05
            )

    def test_os_tamanhos_de_fonte_sao_os_do_oficial(self, medidas):
        gerado, oficial = medidas
        do_gerado = {round(t, 2) for linha in gerado.values() for _x, t in linha}
        do_oficial = {round(t, 2) for linha in oficial.values() for _x, t in linha}

        assert do_gerado == do_oficial == {11.0, 14.0}

    def test_o_recuo_da_lista_e_o_do_oficial(self, medidas):
        gerado, oficial = medidas

        for base in (371.06, 384.06, 411.06):
            assert min(x for x, _t in gerado[base]) == pytest.approx(
                min(x for x, _t in oficial[base]), abs=0.05
            )


# ===========================================================================
# 6. O comando de prévia
# ===========================================================================


class TestComandoDePrevia:
    """
    A ferramenta de conferência visual. Não substitui o olho humano --
    ela existe para que gerar o PDF e medir a diferença seja um comando,
    e não um roteiro que cada um refaz do seu jeito.
    """

    def rodar(self, *argumentos):
        import io as _io

        from django.core.management import call_command

        saida = _io.StringIO()
        call_command("previa_documento", *argumentos, stdout=saida)
        return saida.getvalue()

    def test_gera_o_pdf(self, modelo, tmp_path):
        destino = tmp_path / "previa.pdf"

        self.rodar(SLUG, "--saida", str(destino), "--exemplo")

        assert destino.is_file()
        assert destino.read_bytes()[:5] == b"%PDF-"

    def test_relata_os_elementos_desenhados(self, modelo, tmp_path):
        saida = self.rodar(SLUG, "--saida", str(tmp_path / "p.pdf"), "--exemplo")

        assert "23/23" in saida

    def test_sem_dados_avisa_quais_campos_faltam(self, modelo, tmp_path):
        saida = self.rodar(SLUG, "--saida", str(tmp_path / "p.pdf"))

        assert "campos sem valor" in saida
        assert "convidado.nome" in saida

    def test_com_exemplo_nao_falta_campo(self, modelo, tmp_path):
        saida = self.rodar(SLUG, "--saida", str(tmp_path / "p.pdf"), "--exemplo")

        assert "campos sem valor" not in saida

    def test_aceita_dados_de_um_json(self, modelo, tmp_path):
        import json as _json

        arquivo = tmp_path / "dados.json"
        arquivo.write_text(_json.dumps({"convidado.nome": "Zoé"}), encoding="utf-8")

        self.rodar(SLUG, "--saida", str(tmp_path / "p.pdf"), "--dados", str(arquivo))

        conteudo = PdfReader(str(tmp_path / "p.pdf")).pages[0].extract_text()
        assert "Zoé" in conteudo

    def test_compara_com_a_referencia(self, modelo, tmp_path):
        saida = self.rodar(
            SLUG, "--saida", str(tmp_path / "p.pdf"), "--exemplo",
            "--comparar", str(modelo_fr.CAMINHO_DO_PDF),
        )

        assert "diferença média por pixel" in saida

    def test_grava_as_imagens_da_comparacao(self, modelo, tmp_path):
        self.rodar(
            SLUG, "--saida", str(tmp_path / "p.pdf"), "--exemplo",
            "--comparar", str(modelo_fr.CAMINHO_DO_PDF),
            "--imagens", str(tmp_path / "img"),
        )

        for nome in ("gerado.png", "referencia.png", "diferenca.png", "lado_a_lado.png"):
            assert (tmp_path / "img" / nome).is_file()

    def test_slug_inexistente_falha_claramente(self, modelo, tmp_path):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError, match="Não existe"):
            self.rodar("nao-existe", "--saida", str(tmp_path / "p.pdf"))

    def test_modelo_sem_layout_falha_claramente(self, modelo, tmp_path):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError, match="não tem layout"):
            self.rodar("carta-convite-nl", "--saida", str(tmp_path / "p.pdf"))
