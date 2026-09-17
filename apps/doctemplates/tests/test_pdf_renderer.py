"""
Renderer PDF generico (Etapa 3.4).

A maior parte roda SEM banco: o motor de texto e a camada `render_layout`
sao puros de proposito. So o que envolve `DocumentTemplate` ou `Asset`
pede `django_db`.

O que estes testes protegem, no fundo: que o PDF sai dos ELEMENTOS. E
facil escrever um renderer que parece certo porque desenha por cima de
uma imagem da pagina -- entao ha testes que conferem justamente a
ausencia disso, e testes que conferem que o renderer nao sabe o que e
uma "carta convite".
"""

import io

import pytest
from django.core.exceptions import ValidationError
from pypdf import PdfReader

from apps.doctemplates.services import pdf
from apps.doctemplates.services.pdf import elementos
from apps.doctemplates.services.pdf import texto as motor
from apps.doctemplates.services.pdf.contexto import (
    CampoDesconhecidoError,
    Contexto,
    ValorAusenteError,
)

A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}


# ---------------------------------------------------------------------------
# Ajudantes
# ---------------------------------------------------------------------------


def elemento(tipo, **campos):
    base = {
        "id": campos.pop("id", "e1"),
        "type": tipo,
        "x": campos.pop("x", 50.0),
        "y": campos.pop("y", 100.0),
        "width": campos.pop("width", 200.0),
        "height": campos.pop("height", 20.0),
        "properties": campos.pop("properties", {}),
    }
    base.update(campos)
    return base


GEOMETRIA = ("id", "x", "y", "width", "height")


def texto_simples(valor="Olá mundo", **campos):
    """Geometria vai para o elemento; o resto, para `properties`."""
    geometria = {chave: campos.pop(chave) for chave in list(campos) if chave in GEOMETRIA}
    campos.setdefault("content", {"kind": "text", "value": valor})
    return elemento("text", properties=campos, **geometria)


def layout(*elementos_do_layout):
    return {"version": 1, "elements": list(elementos_do_layout)}


def render(*elementos_do_layout, contexto=None, pagina=None, **extra):
    return pdf.render_layout(
        layout(*elementos_do_layout), pagina or A4, contexto, **extra
    )


def ler(dados):
    return PdfReader(io.BytesIO(dados))


def texto_do_pdf(dados):
    return ler(dados).pages[0].extract_text()


def operadores(dados):
    """
    O content stream JA DESCOMPRIMIDO.

    O reportlab comprime o stream, entao procurar "2.5 w" nos bytes
    crus do arquivo nunca acharia nada -- e o teste passaria a verde
    por nao encontrar o que deveria encontrar.
    """
    return ler(dados).pages[0].get_contents().get_data()


# ---------------------------------------------------------------------------
# 1. Página e coordenadas
# ---------------------------------------------------------------------------


class TestPagina:
    def test_gera_um_pdf_valido(self):
        dados, _relatorio = render(texto_simples())

        assert dados[:5] == b"%PDF-"
        assert len(ler(dados).pages) == 1

    def test_a_pagina_e_a_do_tipo_de_documento(self):
        dados, _ = render(texto_simples())

        pagina = ler(dados).pages[0]
        assert float(pagina.mediabox.width) == pytest.approx(595.2756, abs=0.001)
        assert float(pagina.mediabox.height) == pytest.approx(841.8898, abs=0.001)

    def test_uma_pagina_de_outro_tamanho_e_respeitada(self):
        """Nada aqui presume A4: a página vem do DocumentType."""
        dados, _ = render(texto_simples(), pagina={"width": 300.0, "height": 400.0})

        pagina = ler(dados).pages[0]
        assert float(pagina.mediabox.width) == pytest.approx(300.0, abs=0.001)

    @pytest.mark.parametrize("pagina", [
        {"width": 0, "height": 800},
        {"width": 600, "height": 999999},
        {"width": "a", "height": 800},
        {"height": 800},
        "não é objeto",
    ])
    def test_pagina_invalida_e_recusada(self, pagina):
        with pytest.raises(pdf.PaginaInvalidaError):
            render(texto_simples(), pagina=pagina)

    def test_pagina_em_outra_unidade_e_recusada(self):
        """O layout é em pontos; aceitar mm sem converter mentiria."""
        with pytest.raises(pdf.PaginaInvalidaError, match="pontos"):
            render(texto_simples(), pagina={"width": 210, "height": 297, "unit": "mm"})

    def test_a_conversao_de_coordenadas_inverte_o_eixo_y(self):
        """
        O layout mede do TOPO; o PDF, de baixo. Um elemento colado no
        topo tem de sair no topo.
        """
        pagina = {"width": 600.0, "height": 800.0}
        assert elementos._para_baixo(0.0, 10.0, pagina) == 790.0
        assert elementos._para_baixo(100.0, 20.0, pagina) == 680.0

    def test_o_layout_nao_e_alterado_pelo_render(self):
        """O renderer lê o layout; não o reescreve para caber na biblioteca."""
        import copy

        original = layout(texto_simples())
        copia = copy.deepcopy(original)

        pdf.render_layout(original, A4)

        assert original == copia


# ---------------------------------------------------------------------------
# 2. Layout inválido
# ---------------------------------------------------------------------------


class TestLayoutInvalido:
    def test_layout_fora_do_contrato_e_recusado(self):
        ruim = {"version": 1, "elements": [{"id": "x", "type": "text"}]}

        with pytest.raises(ValidationError):
            pdf.render_layout(ruim, A4)

    def test_tipo_desconhecido_e_recusado(self):
        ruim = {"version": 1, "elements": [
            {"id": "x", "type": "hologram", "x": 0, "y": 0,
             "width": 1, "height": 1, "properties": {}},
        ]}

        with pytest.raises(ValidationError):
            pdf.render_layout(ruim, A4)

    def test_sem_validar_um_tipo_desconhecido_falha_no_desenho(self):
        """Mesmo pulando a validação, ninguém desenha o que não conhece."""
        ruim = {"version": 1, "elements": [
            {"id": "x", "type": "hologram", "x": 0, "y": 0,
             "width": 1, "height": 1, "properties": {}},
        ]}

        with pytest.raises(elementos.TipoSemDesenhadorError):
            pdf.render_layout(ruim, A4, validar=False)

    def test_layout_vazio_gera_pagina_em_branco(self):
        dados, relatorio = pdf.render_layout({}, A4)

        assert len(ler(dados).pages) == 1
        assert relatorio["elementos"] == 0

    def test_todo_tipo_do_registro_tem_desenhador(self):
        """Um tipo novo em `elements.py` não pode ficar sem quem o desenhe."""
        from apps.doctemplates import elements

        assert set(elements.codigos()) == set(elementos.DESENHADORES)


# ---------------------------------------------------------------------------
# 3. Contexto e campos
# ---------------------------------------------------------------------------


class TestContexto:
    def test_resolve_um_campo(self):
        contexto = Contexto({"convidado.nome": "Ana"})

        assert contexto.resolver("convidado.nome") == "Ana"

    def test_referencia_inexistente_no_contexto_e_recusada_na_construcao(self):
        with pytest.raises(CampoDesconhecidoError):
            Contexto({"convidado.fantasma": "x"})

    def test_referencia_inexistente_no_layout_e_recusada_ao_resolver(self):
        with pytest.raises(CampoDesconhecidoError):
            Contexto({}).resolver("inexistente.campo")

    def test_campo_sem_valor_falha_no_modo_estrito(self):
        with pytest.raises(ValorAusenteError):
            Contexto({}).resolver("convidado.nome")

    def test_campo_sem_valor_fica_vazio_fora_do_estrito(self):
        assert Contexto({}, estrito=False).resolver("convidado.nome") == ""

    def test_valor_nulo_vira_texto_vazio(self):
        assert Contexto({"convidado.nome": None}).resolver("convidado.nome") == ""

    def test_valor_nao_texto_e_convertido(self):
        assert Contexto({"calculado.duracao_dias": 15}).resolver(
            "calculado.duracao_dias"
        ) == "15"

    def test_diz_quais_referencias_faltam(self):
        contexto = Contexto({"convidado.nome": "Ana"}, estrito=False)

        assert contexto.referencias_faltando(
            {"convidado.nome", "convidado.passaporte"}
        ) == ["convidado.passaporte"]

    def test_um_campo_do_layout_sem_valor_derruba_a_geracao(self):
        campo = texto_simples()
        campo["properties"]["content"] = {"kind": "field", "source": "convidado.nome"}

        with pytest.raises(ValorAusenteError):
            render(campo, contexto=Contexto({}))


# ---------------------------------------------------------------------------
# 4. Texto
# ---------------------------------------------------------------------------


class TestTexto:
    def test_desenha_o_texto_fixo(self):
        dados, _ = render(texto_simples("Convite oficial"))

        assert "Convite oficial" in texto_do_pdf(dados)

    def test_desenha_o_valor_de_um_campo(self):
        campo = texto_simples()
        campo["properties"]["content"] = {"kind": "field", "source": "convidado.nome"}

        dados, _ = render(campo, contexto=Contexto({"convidado.nome": "Ana Lima"}))

        assert "Ana Lima" in texto_do_pdf(dados)

    def test_o_valor_vem_do_contexto_e_nao_do_renderer(self):
        """
        O mesmo layout com contextos diferentes tem de dar documentos
        diferentes -- é o que prova que nada está fixo no código.
        """
        campo = texto_simples()
        campo["properties"]["content"] = {"kind": "field", "source": "convidado.nome"}

        primeiro, _ = render(campo, contexto=Contexto({"convidado.nome": "Ana"}))
        segundo, _ = render(campo, contexto=Contexto({"convidado.nome": "Bruno"}))

        assert "Ana" in texto_do_pdf(primeiro)
        assert "Bruno" in texto_do_pdf(segundo)
        assert "Ana" not in texto_do_pdf(segundo)

    def test_conteudo_misto_junta_texto_e_campos(self):
        rico = elemento("rich_text", width=400.0, properties={
            "content": {"kind": "mixed", "parts": [
                {"kind": "text", "value": "Je soussignée, "},
                {"kind": "field", "source": "anfitriao.nome"},
                {"kind": "text", "value": ", née le "},
                {"kind": "field", "source": "anfitriao.data_nascimento"},
            ]},
        })

        dados, _ = render(rico, contexto=Contexto({
            "anfitriao.nome": "Claire Dubois",
            "anfitriao.data_nascimento": "14/03/1985",
        }))

        saida = texto_do_pdf(dados)
        assert "Je soussignée," in saida
        assert "Claire Dubois" in saida
        assert "14/03/1985" in saida

    def test_nenhum_placeholder_textual_sobrevive(self):
        """O campo é estrutural até o desenho: nunca vira "{{campo}}"."""
        campo = texto_simples()
        campo["properties"]["content"] = {"kind": "field", "source": "convidado.nome"}

        dados, _ = render(campo, contexto=Contexto({"convidado.nome": "Ana"}))

        assert "{{" not in texto_do_pdf(dados)

    def test_um_valor_com_chaves_nao_e_reinterpretado(self):
        """Um dado que contenha "{{" continua sendo dado."""
        campo = texto_simples()
        campo["properties"]["content"] = {"kind": "field", "source": "convidado.nome"}

        dados, _ = render(campo, contexto=Contexto({"convidado.nome": "{{x}} Ana"}))

        assert "{{x}} Ana" in texto_do_pdf(dados)

    def test_texto_vazio_nao_desenha_nada(self):
        _dados, relatorio = render(texto_simples(""))

        assert relatorio["desenhados"] == 0

    def test_acentos_sobrevivem(self):
        dados, _ = render(texto_simples("À l’attention des autorités compétentes."))

        assert "autorités compétentes" in texto_do_pdf(dados)


class TestTipografia:
    def test_negrito_usa_a_face_bold(self):
        assert elementos.face("LiberationSans", "bold") == "LiberationSans-Bold"

    def test_regular_usa_a_face_regular(self):
        assert elementos.face("LiberationSans", "regular") == "LiberationSans"

    def test_italico_usa_a_face_italica_embutida(self):
        """
        Até o editor rico não havia face itálica e o pedido era recusado --
        fingir itálico com a face regular seria mentir sobre a tipografia.
        Agora a face existe (`pdfengine/fonts/`), e é ela que sai.
        """
        assert elementos.face("LiberationSans", "regular", "italic") == "LiberationSans-Italic"
        assert elementos.face("LiberationSans", "bold", "italic") == "LiberationSans-BoldItalic"

    def test_familia_desconhecida_e_recusada(self):
        with pytest.raises(elementos.FonteIndisponivelError):
            elementos.face("ComicSans", "regular")

    def test_um_trecho_do_mixed_pode_ter_peso_proprio(self):
        rico = elemento("rich_text", width=400.0, properties={
            "content": {"kind": "mixed", "parts": [
                {"kind": "text", "value": "normal "},
                {"kind": "text", "value": "forte", "font_weight": "bold"},
            ]},
        })

        dados, _ = render(rico)

        fontes = ler(dados).pages[0]["/Resources"]["/Font"]
        nomes = {
            str(f.get_object().get("/BaseFont")) for f in fontes.values()
        }
        assert any("Bold" in nome for nome in nomes)
        assert any("Bold" not in nome for nome in nomes)

    def test_a_cor_do_layout_e_usada(self):
        dados, _ = render(texto_simples("colorido", color="#CC0000"))

        # O reportlab escreve ".8" e nao "0.8".
        assert b".8 0 0 rg" in operadores(dados)

    def test_o_ascent_e_o_tipografico_e_nao_o_do_os2(self):
        """
        O reportlab devolve o `typoAscender` (0,728em); o layout foi
        construído com o `hhea.ascender` (0,905em). Usar o errado subiria
        o documento inteiro em 1,95pt.
        """
        from pdfengine import fontconfig

        fontconfig.register_fonts()

        assert motor.ascent("LiberationSans", 11.0) == pytest.approx(9.958, abs=0.001)


class TestAlinhamento:
    def medir(self, alinhamento):
        el = texto_simples("abc", align=alinhamento, width=400.0)
        linhas = motor.quebrar(
            [motor.Trecho("abc", "LiberationSans", 11.0)], 400.0
        )
        posicoes, _extra = motor.posicionar(linhas[0], 400.0, alinhamento)
        del el
        return posicoes[0][0]

    def test_esquerda_comeca_em_zero(self):
        assert self.medir("left") == 0.0

    def test_centro_desloca_metade_da_sobra(self):
        largura = motor.largura_do_texto("abc", "LiberationSans", 11.0)

        assert self.medir("center") == pytest.approx((400.0 - largura) / 2)

    def test_direita_encosta_na_margem(self):
        largura = motor.largura_do_texto("abc", "LiberationSans", 11.0)

        assert self.medir("right") == pytest.approx(400.0 - largura)


# ---------------------------------------------------------------------------
# 5. Motor de texto
# ---------------------------------------------------------------------------


class TestMotorDeTexto:
    def frase(self, texto, tamanho=11.0):
        return motor.Trecho(texto, "LiberationSans", tamanho)

    def test_texto_curto_cabe_numa_linha(self):
        linhas = motor.quebrar([self.frase("uma frase curta")], 400.0)

        assert len(linhas) == 1

    def test_texto_longo_quebra_em_varias(self):
        linhas = motor.quebrar([self.frase("palavra " * 60)], 200.0)

        assert len(linhas) > 1

    def test_nenhuma_linha_passa_da_largura(self):
        linhas = motor.quebrar([self.frase("palavra " * 60)], 200.0)

        for linha in linhas:
            assert linha.largura <= 200.0

    def test_a_ultima_linha_e_marcada(self):
        linhas = motor.quebrar([self.frase("palavra " * 40)], 200.0)

        assert linhas[-1].ultima is True
        assert all(not linha.ultima for linha in linhas[:-1])

    def test_nowrap_mantem_tudo_numa_linha(self):
        linhas = motor.quebrar(
            [self.frase("palavra " * 60)], 100.0, quebrar_linhas=False
        )

        assert len(linhas) == 1

    def test_quebra_explicita_e_respeitada(self):
        linhas = motor.quebrar([self.frase("um\ndois\ntrês")], 400.0)

        assert [linha.texto for linha in linhas] == ["um", "dois", "três"]

    def test_a_justificacao_estica_as_linhas_do_meio(self):
        linhas = motor.quebrar([self.frase("palavra " * 40)], 200.0)

        assert motor.espaco_extra(linhas[0], 200.0, "justify") > 0

    def test_a_justificacao_nao_estica_a_ultima_linha(self):
        """Convenção tipográfica -- e é o que o documento oficial faz."""
        linhas = motor.quebrar([self.frase("palavra " * 40)], 200.0)

        assert motor.espaco_extra(linhas[-1], 200.0, "justify") == 0.0

    def test_sem_justificar_nao_ha_esticamento(self):
        linhas = motor.quebrar([self.frase("palavra " * 40)], 200.0)

        assert motor.espaco_extra(linhas[0], 200.0, "left") == 0.0

    def test_o_esticamento_leva_a_linha_a_margem(self):
        linhas = motor.quebrar([self.frase("palavra " * 40)], 200.0)
        linha = linhas[0]

        extra = motor.espaco_extra(linha, 200.0, "justify")
        final = linha.largura + extra * linha.texto.count(" ")

        assert final == pytest.approx(200.0, abs=0.01)

    def test_shrink_reduz_para_caber(self):
        trechos = [self.frase("palavra " * 40)]

        _linhas, fator = motor.encaixar(trechos, 200.0, 30.0, 13.5)

        assert fator < 1.0

    def test_clip_nao_reduz(self):
        trechos = [self.frase("palavra " * 40)]

        _linhas, fator = motor.encaixar(
            trechos, 200.0, 30.0, 13.5, transbordo="clip"
        )

        assert fator == 1.0

    def test_shrink_tem_piso(self):
        trechos = [self.frase("palavra " * 400)]

        _linhas, fator = motor.encaixar(trechos, 200.0, 14.0, 13.5)

        assert fator >= motor.FATOR_MINIMO_DE_REDUCAO

    def test_o_letter_spacing_entra_na_medida(self):
        sem = motor.largura_do_texto("abcde", "LiberationSans", 11.0)
        com = motor.largura_do_texto("abcde", "LiberationSans", 11.0, 2.0)

        assert com == pytest.approx(sem + 10.0)

    def test_pedacos_de_mesmo_estilo_sao_fundidos(self):
        """Menos operações de desenho e texto extraível como palavra."""
        linhas = motor.quebrar([self.frase("uma frase curta")], 400.0)

        assert len(linhas[0].pedacos) == 1

    def test_pedacos_de_estilos_diferentes_nao_se_fundem(self):
        trechos = [
            motor.Trecho("normal ", "LiberationSans", 11.0),
            motor.Trecho("forte", "LiberationSans-Bold", 11.0),
        ]

        linhas = motor.quebrar(trechos, 400.0)

        assert len(linhas[0].pedacos) == 2


# ---------------------------------------------------------------------------
# 6. Número
# ---------------------------------------------------------------------------


class TestNumero:
    def numero(self, valor, formato=""):
        return elemento("number", properties={
            "content": {"kind": "text", "value": valor},
            "format": formato,
        })

    def test_sem_formato_imprime_como_veio(self):
        dados, _ = render(self.numero("15"))

        assert "15" in texto_do_pdf(dados)

    def test_com_formato_aplica(self):
        dados, _ = render(self.numero("15", ".2f"))

        assert "15.00" in texto_do_pdf(dados)

    def test_valor_nao_numerico_sobrevive_intacto(self):
        """Um documento com o valor cru é conferível; com valor inventado, não."""
        dados, _ = render(self.numero("quinze", ".2f"))

        assert "quinze" in texto_do_pdf(dados)

    def test_aceita_campo_dinamico(self):
        el = self.numero("")
        el["properties"]["content"] = {
            "kind": "field", "source": "calculado.duracao_dias",
        }

        dados, _ = render(el, contexto=Contexto({"calculado.duracao_dias": "15"}))

        assert "15" in texto_do_pdf(dados)


# ---------------------------------------------------------------------------
# 7. Gráficos
# ---------------------------------------------------------------------------


class TestLinha:
    def test_desenha(self):
        _dados, relatorio = render(
            elemento("line", height=0.0, properties={"thickness": 0.75})
        )

        assert relatorio["desenhados"] == 1

    def test_a_espessura_vai_para_o_pdf(self):
        dados, _ = render(
            elemento("line", height=0.0, properties={"thickness": 2.5})
        )

        assert b"2.5 w" in operadores(dados)

    @pytest.mark.parametrize("estilo", ["solid", "dashed", "dotted"])
    def test_todos_os_estilos_desenham(self, estilo):
        _dados, relatorio = render(
            elemento("line", height=0.0, properties={"thickness": 1.0, "style": estilo})
        )

        assert relatorio["desenhados"] == 1


class TestRetangulo:
    def test_desenha_com_preenchimento(self):
        _dados, relatorio = render(elemento("rectangle", properties={
            "border_width": 0.0, "fill_color": "#FFD966",
        }))

        assert relatorio["desenhados"] == 1

    def test_a_cor_de_preenchimento_vai_para_o_pdf(self):
        dados, _ = render(elemento("rectangle", properties={
            "border_width": 0.0, "fill_color": "#FF0000",
        }))

        assert b"1 0 0 rg" in operadores(dados)

    def test_sem_borda_nem_preenchimento_nao_desenha_forma(self):
        _dados, relatorio = render(elemento("rectangle", properties={
            "border_width": 0.0, "fill_color": None,
        }))

        assert relatorio["elementos"] == 1

    def test_cantos_arredondados_desenham(self):
        _dados, relatorio = render(elemento("rectangle", properties={
            "border_width": 1.0, "radius": 4.0,
        }))

        assert relatorio["desenhados"] == 1


class TestQrCode:
    def qr(self, valor="https://exemplo.be", **extra):
        propriedades = {"source": {"kind": "text", "value": valor}}
        propriedades.update(extra)
        return elemento("qr_code", width=80.0, height=80.0, properties=propriedades)

    def test_gera_um_qr(self):
        _dados, relatorio = render(self.qr())

        assert relatorio["desenhados"] == 1

    def test_o_qr_e_vetorial_e_nao_uma_imagem(self):
        """Nada de raster: o QR é desenhado, e por isso acompanha o dado."""
        dados, _ = render(self.qr())

        recursos = ler(dados).pages[0]["/Resources"]
        assert "/XObject" not in recursos

    def test_um_conteudo_diferente_gera_um_qr_diferente(self):
        primeiro, _ = render(self.qr("https://a.be"))
        segundo, _ = render(self.qr("https://b.be"))

        assert primeiro != segundo

    def test_aceita_campo_dinamico(self):
        el = self.qr("")
        el["properties"]["source"] = {"kind": "field", "source": "documento.numero"}

        _dados, relatorio = render(el, contexto=Contexto({"documento.numero": "A-1"}))

        assert relatorio["desenhados"] == 1

    def test_sem_conteudo_nao_desenha(self):
        _dados, relatorio = render(self.qr(""))

        assert relatorio["desenhados"] == 0

    @pytest.mark.parametrize("nivel", ["L", "M", "Q", "H"])
    def test_todos_os_niveis_de_correcao(self, nivel):
        _dados, relatorio = render(self.qr(error_correction=nivel))

        assert relatorio["desenhados"] == 1

    def test_a_margem_encolhe_o_desenho(self):
        sem, _ = render(self.qr(margin=0.0))
        com, _ = render(self.qr(margin=10.0))

        assert sem != com


class TestImagem:
    def png(self):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (40, 20), (10, 20, 30)).save(buffer, format="PNG")
        return buffer.getvalue()

    def imagem(self, asset_id=7, **extra):
        propriedades = {"source": {"kind": "asset", "asset_id": asset_id}}
        propriedades.update(extra)
        return elemento("image", width=100.0, height=50.0, properties=propriedades)

    def test_desenha_a_imagem_do_lote(self):
        _dados, relatorio = render(self.imagem(), assets={7: self.png()})

        assert relatorio["desenhados"] == 1

    def test_a_imagem_entra_como_xobject(self):
        dados, _ = render(self.imagem(), assets={7: self.png()})

        assert "/XObject" in ler(dados).pages[0]["/Resources"]

    def test_asset_ausente_falha_claramente(self):
        with pytest.raises(pdf.AssetAusenteError, match="lote"):
            render(self.imagem(), assets={})

    def test_asset_zero_significa_sem_imagem(self):
        """`asset_id: 0` é "ainda não escolhida" -- não é erro de layout."""
        with pytest.raises(pdf.AssetAusenteError):
            render(self.imagem(asset_id=0), assets={})

    def test_contain_preserva_a_proporcao(self):
        _dados, relatorio = render(
            self.imagem(fit="contain", preserve_aspect_ratio=True),
            assets={7: self.png()},
        )

        assert relatorio["desenhados"] == 1

    @pytest.mark.parametrize("ajuste", ["contain", "cover", "fill"])
    def test_todos_os_ajustes_desenham(self, ajuste):
        _dados, relatorio = render(
            self.imagem(fit=ajuste), assets={7: self.png()}
        )

        assert relatorio["desenhados"] == 1


class TestTabela:
    def tabela(self, **extra):
        propriedades = {
            "columns": [{"width": 100.0, "align": "left"},
                        {"width": 200.0, "align": "left"}],
            "rows": [
                {"min_height": 20.0, "cells": [
                    {"content": {"kind": "text", "value": "Nome :"},
                     "align": "left", "bold": True},
                    {"content": {"kind": "field", "source": "convidado.nome"},
                     "align": "left", "bold": False},
                ]},
                {"min_height": 20.0, "cells": [
                    {"content": {"kind": "text", "value": "Passaporte :"},
                     "align": "left", "bold": True},
                    {"content": {"kind": "text", "value": "YY000000"},
                     "align": "left", "bold": False},
                ]},
            ],
            "border_width": 0.75,
            "border_color": "#000000",
            "cell_padding": {"top": 4.0, "right": 4.0, "bottom": 4.0, "left": 4.0},
        }
        propriedades.update(extra)
        return elemento("table", width=300.0, height=40.0, properties=propriedades)

    @pytest.fixture
    def contexto(self):
        return Contexto({"convidado.nome": "Ana Lima"})

    def test_desenha(self, contexto):
        _dados, relatorio = render(self.tabela(), contexto=contexto)

        assert relatorio["desenhados"] == 1

    def test_o_conteudo_das_celulas_aparece(self, contexto):
        dados, _ = render(self.tabela(), contexto=contexto)

        saida = texto_do_pdf(dados)
        assert "Nome :" in saida
        assert "Passaporte :" in saida

    def test_um_campo_dentro_da_celula_e_resolvido(self, contexto):
        dados, _ = render(self.tabela(), contexto=contexto)

        assert "Ana Lima" in texto_do_pdf(dados)

    def test_a_celula_em_negrito_usa_a_face_bold(self, contexto):
        dados, _ = render(self.tabela(), contexto=contexto)

        nomes = {
            str(f.get_object().get("/BaseFont"))
            for f in ler(dados).pages[0]["/Resources"]["/Font"].values()
        }
        assert any("Bold" in nome for nome in nomes)

    def test_a_tabela_desenha_a_grade(self, contexto):
        """Sem bordas o PDF fica menor: é a grade que some."""
        com, _ = render(self.tabela(), contexto=contexto)
        sem, _ = render(self.tabela(border_width=0.0), contexto=contexto)

        assert len(com) != len(sem)

    def test_celula_com_conteudo_misto(self, contexto):
        tabela = self.tabela()
        tabela["properties"]["rows"][1]["cells"][1]["content"] = {
            "kind": "mixed", "parts": [
                {"kind": "text", "value": "du "},
                {"kind": "field", "source": "estadia.chegada"},
            ],
        }

        dados, _ = render(tabela, contexto=Contexto({
            "convidado.nome": "Ana", "estadia.chegada": "10/10/2026",
        }))

        assert "10/10/2026" in texto_do_pdf(dados)

    def test_tabela_sem_colunas_nao_desenha(self, contexto):
        vazia = self.tabela(columns=[], rows=[])

        _dados, relatorio = render(vazia, contexto=contexto)

        assert relatorio["desenhados"] == 0


# ---------------------------------------------------------------------------
# 8. Elementos fora da página
# ---------------------------------------------------------------------------


class TestForaDaPagina:
    def test_elemento_alem_da_borda_nao_derruba_a_geracao(self):
        """
        O renderer desenha onde mandaram. Recortar ou recusar seria
        decidir por quem projetou o documento.
        """
        longe = texto_simples("fora", x=900.0, y=1200.0)

        dados, relatorio = render(longe)

        assert len(ler(dados).pages) == 1
        assert relatorio["elementos"] == 1

    def test_coordenada_negativa_nao_derruba(self):
        dados, _ = render(texto_simples("acima", x=-50.0, y=-20.0))

        assert len(ler(dados).pages) == 1

    def test_largura_zero_nao_desenha_texto(self):
        _dados, relatorio = render(texto_simples("nada", width=0.0))

        assert relatorio["desenhados"] == 0


# ---------------------------------------------------------------------------
# 9. O renderer é genérico
# ---------------------------------------------------------------------------


class TestGenerico:
    def codigo(self):
        """
        O código EXECUTÁVEL dos módulos, sem docstrings.

        Os docstrings explicam o contrato dando exemplos -- "convidado.
        nome", "Claire Dubois", "não há `if language ==`" -- e são
        justamente o que documenta a independência do renderer. Varrer o
        texto cru acusaria a documentação como se fosse lógica.
        """
        import ast
        import inspect

        from apps.doctemplates.services.pdf import contexto as mod_contexto

        partes = []
        for modulo in (pdf, elementos, motor, mod_contexto):
            arvore = ast.parse(inspect.getsource(modulo))
            for no in ast.walk(arvore):
                corpo = getattr(no, "body", None)
                if not isinstance(corpo, list) or not corpo:
                    continue
                primeiro = corpo[0]
                if (isinstance(primeiro, ast.Expr)
                        and isinstance(primeiro.value, ast.Constant)
                        and isinstance(primeiro.value.value, str)):
                    primeiro.value.value = ""
            partes.append(ast.unparse(arvore))
        return "\n".join(partes)

    @pytest.mark.parametrize("proibido", [
        "carta-convite", "carta_convite", "Claire", "Dubois",
        "ibz", "dofi", "convidado.nome", "anfitriao.",
    ])
    def test_nao_conhece_documento_nenhum(self, proibido):
        assert proibido not in self.codigo()

    def test_nao_despacha_por_slug_nem_idioma(self):
        codigo = self.codigo()

        assert "modelo.slug ==" not in codigo
        assert "language ==" not in codigo
        assert '== "fr"' not in codigo

    def test_nao_usa_a_arquitetura_antiga(self):
        codigo = self.codigo()

        for proibido in (
            "TemplateVersion", "LetterTemplate", "render_invitation_letter",
        ):
            assert proibido not in codigo

    def test_nao_usa_o_pdf_oficial(self):
        """Nem como fundo, nem rasterizado, nem para extrair coisa nenhuma."""
        codigo = self.codigo()

        for proibido in ("Modelo-Carta-Convite", "BASE_PDF", "assets/fr",
                         "pdfium", "render_preview"):
            assert proibido not in codigo

    def test_o_despacho_e_por_tipo(self):
        assert sorted(elementos.DESENHADORES) == [
            "image", "line", "number", "page_break", "qr_code",
            "rectangle", "rich_text", "table", "text",
        ]

    def test_a_camada_pura_nao_importa_django(self):
        """`texto` e `contexto` rodam fora do Django -- e é o que os testa."""
        import inspect

        from apps.doctemplates.services.pdf import contexto as mod_contexto

        for modulo in (motor, mod_contexto):
            assert "import django" not in inspect.getsource(modulo)
            assert "from django" not in inspect.getsource(modulo)


# ---------------------------------------------------------------------------
# 10. A camada de aplicação
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRenderTemplate:
    def modelo(self, layout_do_modelo):
        from apps.doctemplates.models import DocumentTemplate, DocumentType

        tipo = DocumentType.objects.create(
            code="teste", name="Teste", page=dict(A4)
        )
        return DocumentTemplate.objects.create(
            type=tipo, name="M", slug="m-teste", language="pt",
            layout=layout_do_modelo,
        )

    def test_renderiza_um_modelo(self):
        modelo = self.modelo(layout(texto_simples("Documento")))

        dados, relatorio = pdf.render_template(modelo, {})

        assert "Documento" in texto_do_pdf(dados)
        assert relatorio["elementos"] == 1

    def test_usa_a_pagina_do_tipo_de_documento(self):
        modelo = self.modelo(layout(texto_simples("x")))
        modelo.type.page = {"width": 300.0, "height": 500.0, "unit": "pt"}

        dados, _ = pdf.render_template(modelo, {})

        assert float(ler(dados).pages[0].mediabox.width) == pytest.approx(300.0, abs=0.01)

    def test_modelo_sem_layout_e_recusado(self):
        modelo = self.modelo({})

        with pytest.raises(ValidationError, match="não tem layout"):
            pdf.render_template(modelo, {})

    def test_os_dados_nao_ficam_gravados_no_modelo(self):
        """
        O mesmo modelo serve a todas as cartas: os valores passam pelo
        render e não encostam no banco.
        """
        campo = texto_simples()
        campo["properties"]["content"] = {"kind": "field", "source": "convidado.nome"}
        modelo = self.modelo(layout(campo))

        pdf.render_template(modelo, {"convidado.nome": "Ana"})

        modelo.refresh_from_db()
        assert "Ana" not in str(modelo.layout)

    def test_carrega_o_asset_referenciado(self, tmp_path, settings):
        from django.core.files.base import ContentFile
        from PIL import Image

        from apps.content.models import Asset

        settings.MEDIA_ROOT = tmp_path
        buffer = io.BytesIO()
        Image.new("RGB", (10, 10), (0, 0, 0)).save(buffer, format="PNG")
        asset = Asset(key="teste-logo", kind="content")
        asset.file.save("t.png", ContentFile(buffer.getvalue()), save=True)

        imagem = elemento("image", properties={
            "source": {"kind": "asset", "asset_id": asset.pk},
            "fit": "contain", "preserve_aspect_ratio": True,
        })
        modelo = self.modelo(layout(imagem))

        dados, relatorio = pdf.render_template(modelo, {})

        assert relatorio["desenhados"] == 1
        assert "/XObject" in ler(dados).pages[0]["/Resources"]

    def test_asset_inexistente_falha_claramente(self):
        imagem = elemento("image", properties={
            "source": {"kind": "asset", "asset_id": 9999},
            "fit": "contain", "preserve_aspect_ratio": True,
        })
        modelo = self.modelo(layout(imagem))

        with pytest.raises(pdf.AssetAusenteError):
            pdf.render_template(modelo, {})

    def test_campos_do_layout_lista_as_referencias(self):
        campo = texto_simples()
        campo["properties"]["content"] = {"kind": "field", "source": "convidado.nome"}

        assert pdf.campos_do_layout(layout(campo)) == {"convidado.nome"}
