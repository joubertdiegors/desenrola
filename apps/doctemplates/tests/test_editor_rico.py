"""
O editor rico (Etapa 3.7): o contrato ampliado, o renderer que o desenha,
as rotas que o servem e a corrente inteira num modelo oficial.

O QUE ESTA SUÍTE PROTEGE
------------------------
1. Que a formatação por trecho (peso, estilo, cor, tamanho, fonte,
   realce, link) e por bloco (recuo, marcador, estilo) SOBREVIVE ao ciclo
   editor -> salvar -> reabrir -> PDF -- e que o campo dinâmico no meio
   de tudo isso continua campo;
2. Que a única porta de URL do layout (`link`) recusa `javascript:` e
   companhia, que texto é sempre texto e que a página do editor nunca
   interpola conteúdo em `<script>`;
3. Que a prévia desenha o que está na tela sem gravar nada, e exige
   CSRF, login e permissão como tudo o mais;
4. Que os quatro oficiais continuam exatamente como eram: o contrato
   cresceu por baixo deles, não por cima.
"""

import copy
import io
import json
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from pypdf import PdfReader

from apps.doctemplates import datasources, elements, layout_schema
from apps.doctemplates.models import DocumentTemplate, DocumentType
from apps.doctemplates.services import carta_convite, dados_de_exemplo, pdf
from apps.doctemplates.services import layout as servico_de_layout
from apps.doctemplates.services.duplicacao import duplicar_modelo
from apps.doctemplates.services.pdf import elementos as desenhadores

A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}
SENHA = "senha-forte-123"
RAIZ_DO_PROJETO = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Ajudantes
# ---------------------------------------------------------------------------


def texto(valor, **estilo):
    return {"kind": "text", "value": valor, **estilo}


def campo(referencia, **estilo):
    return {"kind": "field", "source": referencia, **estilo}


def misto(*partes):
    return {"kind": "mixed", "parts": list(partes)}


def rico(conteudo, identificador="r", y=100.0, **props):
    return {
        "id": identificador, "type": "rich_text", "x": 50.0, "y": y, "width": 400.0,
        "height": 40.0,
        "properties": {"content": conteudo, **props},
    }


def layout(*elementos_do_layout, **extra):
    return {"version": 1, "elements": list(elementos_do_layout), **extra}


def ler(dados):
    return PdfReader(io.BytesIO(dados))


def texto_do_pdf(dados, pagina=0):
    return ler(dados).pages[pagina].extract_text()


def operadores(dados, pagina=0):
    return ler(dados).pages[pagina].get_contents().get_data()


def fontes_do_pdf(dados, pagina=0):
    recursos = ler(dados).pages[pagina]["/Resources"]["/Font"]
    return {str(f.get_object().get("/BaseFont")) for f in recursos.values()}


def _fora_dos_dados(html):
    """
    A página SEM os blocos `json_script`.

    É onde a marcação de verdade vive -- e é onde conteúdo do usuário
    nunca pode aparecer. Dentro de um `<script type="application/json">`
    o Django escapa `<`, `>` e `&`, então o texto do modelo fica lá
    inerte; misturar os dois numa busca só daria falso alarme.
    """
    import re

    return re.sub(
        r'<script id="[^"]+" type="application/json">.*?</script>', "", html, flags=re.S
    )


# ---------------------------------------------------------------------------
# 1. O contrato: estilo por trecho, bloco, documento, quebra
# ---------------------------------------------------------------------------


class TestEstiloDoTrecho:
    @pytest.mark.parametrize(
        "estilo",
        [
            {"text_decoration": "underline"},
            {"text_decoration": "line-through"},
            {"color": "#cc0000"},
            {"highlight": "#fff6c9"},
            {"font_size": 14},
            {"font_size": 8.5},
            {"font_family": "Times"},
            {"font_family": "Courier"},
            {"link": "https://exemplo.be/x?y=1"},
            {"link": "mailto:alguem@exemplo.be"},
            {"link": "tel:+32470000000"},
            {"font_weight": "bold", "font_style": "italic", "color": "#000000", "font_size": 12},
        ],
    )
    def test_cada_estilo_do_editor_e_aceito(self, estilo):
        layout_schema.validar_conteudo(misto(texto("x", **estilo)), "c", permite_misto=True)

    @pytest.mark.parametrize(
        "estilo",
        [
            {"text_decoration": "blink"},
            {"color": "red"},
            {"color": "#ccc"},
            {"highlight": "yellow"},
            {"font_size": 0},
            {"font_size": -3},
            {"font_size": 999},
            {"font_size": "grande"},
            {"font_family": "Georgia"},
            {"font_family": "Manrope"},
        ],
    )
    def test_fora_do_vocabulario_e_recusado(self, estilo):
        with pytest.raises(ValidationError):
            layout_schema.validar_conteudo(misto(texto("x", **estilo)), "c", permite_misto=True)

    @pytest.mark.parametrize(
        "link",
        [
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "java\nscript:alert(1)",
            " javascript:alert(1)",
            "data:text/html;base64,PHNjcmlwdD4=",
            "vbscript:msgbox",
            "file:///etc/passwd",
            "/relativo",
            "#ancora",
            "exemplo.be",
            "",
            "https://" + "a" * 3000,
            42,
        ],
    )
    def test_link_perigoso_ou_fora_do_padrao_e_recusado(self, link):
        with pytest.raises(ValidationError, match="link"):
            layout_schema.validar_conteudo(
                misto(texto("clique", link=link)), "c", permite_misto=True
            )

    def test_link_aceito_limpa_espacos_e_controle(self):
        assert layout_schema.link_aceito("  https://exemplo.be/\x00x ") == "https://exemplo.be/x"
        assert layout_schema.link_aceito("javascript:x") is None

    def test_o_vocabulario_e_o_mesmo_do_registro(self):
        assert set(layout_schema.ESTILO_DO_TRECHO) == {
            "font_weight", "font_style", "text_decoration", "color", "highlight",
            "font_size", "font_family", "link",
        }
        assert layout_schema.ENFASE_DO_TRECHO == layout_schema.ESTILO_DO_TRECHO
        for familia in elements.FONT_FAMILIES:
            layout_schema.validar_conteudo(
                misto(texto("x", font_family=familia)), "c", permite_misto=True
            )

    def test_o_texto_e_texto_e_nao_html(self):
        """Marcação dentro de um valor é só caracteres; nada a sanitizar."""
        perigoso = '<script>alert(1)</script><img src=x onerror=alert(1)>'
        bloco = misto(texto(perigoso, font_weight="bold"))

        layout_schema.validar_conteudo(bloco, "c", permite_misto=True)

        assert bloco["parts"][0]["value"] == perigoso


class TestBlocoEDocumento:
    def test_recuo_marcador_e_estilo_do_bloco(self):
        el = rico(misto(texto("item")), indent=18.0, list_marker="1.", block_style="p")

        layout_schema.validate_layout(layout(el))

    @pytest.mark.parametrize("props", [{"indent": -1}, {"block_style": "h3"}, {"list_marker": 7}])
    def test_bloco_fora_do_contrato_e_recusado(self, props):
        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(rico(misto(texto("x")), **props)))

    def test_as_opcoes_de_documento(self):
        documento = layout(
            rico(misto(texto("x"))), document={"margin": 70.87, "page_numbers": True}
        )

        layout_schema.validate_layout(documento)

        assert layout_schema.documento(documento) == {"margin": 70.87, "page_numbers": True}
        assert layout_schema.documento({}) == {"margin": None, "page_numbers": False}

    @pytest.mark.parametrize(
        "opcoes",
        [{"margin": -1}, {"margin": "x"}, {"page_numbers": "sim"}, {"fundo": "#fff"}, []],
    )
    def test_opcoes_de_documento_fora_do_contrato_sao_recusadas(self, opcoes):
        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(rico(misto(texto("x"))), document=opcoes))

    def test_a_quebra_de_pagina_e_um_elemento_sem_propriedades(self):
        quebra = {"id": "q", "type": "page_break", "x": 0.0, "y": 300.0,
                  "width": 595.2756, "height": 0.0, "properties": {}}

        layout_schema.validate_layout(layout(quebra))
        assert elements.tipo("page_break").categoria == elements.ESTRUTURA
        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout({**quebra, "properties": {"cor": "#000"}}))

    def test_o_elemento_padrao_de_todo_tipo_continua_valido(self):
        for codigo in elements.codigos():
            layout_schema.validate_layout(layout(servico_de_layout.criar_elemento(codigo, id="x")))

    def test_um_layout_anterior_ao_editor_rico_continua_valido(self):
        """Nada do que o contrato ganhou é obrigatório."""
        antigo = rico(misto(texto("Je soussignée, "), campo("anfitriao.nome", font_weight="bold")))
        del antigo["properties"]["content"]["parts"][0]  # so o campo
        layout_schema.validate_layout(layout(antigo))


# ---------------------------------------------------------------------------
# 2. O renderer
# ---------------------------------------------------------------------------


class TestRendererRico:
    def test_as_faces_do_editor(self):
        assert desenhadores.face("LiberationSans", "regular", "italic") == "LiberationSans-Italic"
        assert desenhadores.face("LiberationSans", "bold", "italic") == "LiberationSans-BoldItalic"
        assert desenhadores.face("Times", "bold", "italic") == "Times-BoldItalic"
        assert desenhadores.face("Courier") == "Courier"
        with pytest.raises(desenhadores.FonteIndisponivelError):
            desenhadores.face("Georgia")

    def test_cada_trecho_leva_a_propria_fonte_tamanho_e_cor(self):
        conteudo = misto(
            texto("normal "),
            texto("forte ", font_weight="bold", color="#cc0000"),
            texto("curvo ", font_style="italic"),
            texto("serifa ", font_family="Times"),
            texto("mono", font_family="Courier", font_size=8),
        )

        dados, relatorio = pdf.render_layout(layout(rico(conteudo)), A4)

        assert relatorio["desenhados"] == 1
        assert "normal forte curvo serifa mono" in texto_do_pdf(dados)
        fontes = fontes_do_pdf(dados)
        assert any("LiberationSans-Bold" in f for f in fontes)
        assert any("LiberationSans-Italic" in f for f in fontes)
        assert "/Times-Roman" in fontes
        assert "/Courier" in fontes
        # A cor do trecho: o reportlab escreve ".8 0 0 rg" para #cc0000.
        assert b".8 0 0 rg" in operadores(dados)
        assert b"/F" in operadores(dados)

    def test_o_realce_pinta_um_retangulo_atras_do_texto(self):
        com = pdf.render_layout(layout(rico(misto(texto("marcado", highlight="#fff6c9")))), A4)[0]
        sem = pdf.render_layout(layout(rico(misto(texto("marcado")))), A4)[0]

        # #fff6c9 -> "1 .964706 .788235 rg" e um `re ... f` a mais.
        assert b".964706 .788235 rg" in operadores(com)
        assert operadores(com).count(b" re") == operadores(sem).count(b" re") + 1

    def test_o_link_vira_anotacao_do_pdf(self):
        dados, _ = pdf.render_layout(
            layout(rico(misto(texto("clique", link="https://exemplo.be/x")))), A4
        )

        anotacoes = ler(dados).pages[0].get("/Annots")
        assert anotacoes, "nenhuma anotação de link"
        uri = anotacoes[0].get_object()["/A"]["/URI"]
        assert uri == "https://exemplo.be/x"

    def test_o_marcador_de_lista_e_escrito_no_recuo(self):
        dados, _ = pdf.render_layout(
            layout(rico(misto(texto("primeiro item")), list_marker="1.", indent=18.0)), A4
        )

        assert "1. primeiro item" in texto_do_pdf(dados).replace("\n", " ")

    def test_um_recuo_maior_que_a_caixa_nao_faz_o_texto_sumir(self):
        """
        Achado na homologação: transformar em lista um bloco ESTREITO --
        o marcador "2." do documento oficial tem 18pt de largura -- dava
        um recuo de 18pt numa caixa de 18pt. Largura zero não desenha
        nada, e o texto simplesmente não aparecia no PDF, sem erro
        nenhum. Agora o recuo cede: o documento fica apertado, mas o
        conteúdo existe.
        """
        estreito = rico(misto(texto("texto num bloco estreito")), list_marker="2.", indent=18.0)
        estreito["width"] = 18.0

        dados, relatorio = pdf.render_layout(layout(estreito), A4)

        assert relatorio["desenhados"] == 1
        assert "texto" in texto_do_pdf(dados)

    def test_largura_zero_continua_sem_desenhar(self):
        """A guarda do recuo não ressuscita uma caixa que não existe."""
        vazio = rico(misto(texto("nada")))
        vazio["width"] = 0.0

        _dados, relatorio = pdf.render_layout(layout(vazio), A4)

        assert relatorio["desenhados"] == 0

    def test_o_recuo_encolhe_a_largura_do_texto(self):
        """Com recuo o texto quebra antes -- e a caixa que encolhe."""
        frase = "palavra " * 40
        sem = pdf.render_layout(layout(rico(misto(texto(frase)))), A4)[0]
        com = pdf.render_layout(layout(rico(misto(texto(frase)), indent=200.0)), A4)[0]

        assert texto_do_pdf(com).count("\n") > texto_do_pdf(sem).count("\n")

    def test_a_quebra_de_pagina_gera_a_segunda_pagina(self):
        documento = layout(
            rico(misto(texto("primeira")), "a", y=100.0),
            {"id": "q", "type": "page_break", "x": 0.0, "y": 200.0, "width": 595.2756,
             "height": 0.0, "properties": {}},
            rico(misto(texto("segunda")), "b", y=841.8898 + 70.0),
        )

        dados, relatorio = pdf.render_layout(documento, A4)

        assert relatorio["paginas"] == 2
        assert relatorio["elementos"] == 3
        assert len(ler(dados).pages) == 2
        assert "primeira" in texto_do_pdf(dados, 0)
        assert "segunda" not in texto_do_pdf(dados, 0)
        assert "segunda" in texto_do_pdf(dados, 1)
        # A segunda pagina tambem e A4.
        assert round(float(ler(dados).pages[1].mediabox.height), 1) == 841.9

    def test_sem_quebra_tudo_e_pagina_um_como_sempre(self):
        longe = rico(misto(texto("fora")), y=1200.0)

        dados, relatorio = pdf.render_layout(layout(longe), A4)

        assert relatorio["paginas"] == 1
        assert len(ler(dados).pages) == 1

    def test_a_distribuicao_por_pagina(self):
        documento = layout(
            rico(misto(texto("a")), "a", y=100.0),
            {"id": "q1", "type": "page_break", "x": 0.0, "y": 200.0, "width": 595.0,
             "height": 0.0, "properties": {}},
            rico(misto(texto("b")), "b", y=900.0),
            {"id": "q2", "type": "page_break", "x": 0.0, "y": 1000.0, "width": 595.0,
             "height": 0.0, "properties": {}},
            rico(misto(texto("c")), "c", y=1800.0),
        )

        paginas = pdf.distribuir_por_pagina(documento, 841.8898)

        assert [[e["id"] for e in nesta] for _d, nesta in paginas] == [
            ["a", "q1"], ["b", "q2"], ["c"],
        ]
        assert [d for d, _n in paginas] == [0.0, 841.8898, 2 * 841.8898]

    def test_a_numeracao_de_paginas(self):
        documento = layout(
            rico(misto(texto("a")), "a", y=100.0),
            {"id": "q", "type": "page_break", "x": 0.0, "y": 200.0, "width": 595.0,
             "height": 0.0, "properties": {}},
            rico(misto(texto("b")), "b", y=900.0),
            document={"page_numbers": True},
        )

        dados, _ = pdf.render_layout(documento, A4)

        assert "1 / 2" in texto_do_pdf(dados, 0)
        assert "2 / 2" in texto_do_pdf(dados, 1)
        sem = pdf.render_layout(layout(rico(misto(texto("a")))), A4)[0]
        assert "1 / 1" not in texto_do_pdf(sem)

    def test_o_campo_no_meio_do_estilo_continua_sendo_resolvido(self):
        conteudo = misto(
            texto("Eu, ", font_style="italic"),
            campo("anfitriao.nome", font_weight="bold", color="#1d4ed8"),
            texto(", convido ", font_size=14),
            campo("convidado.nome", link="https://exemplo.be", text_decoration="underline"),
        )
        contexto = pdf.Contexto({"anfitriao.nome": "Claire Dubois", "convidado.nome": "Carlos"})

        dados, _ = pdf.render_layout(layout(rico(conteudo)), A4, contexto)

        assert "Eu, Claire Dubois, convido Carlos" in texto_do_pdf(dados).replace("\n", " ")
        assert "anfitriao.nome" not in texto_do_pdf(dados)


# ---------------------------------------------------------------------------
# 3. Fontes de dados e dados de amostra
# ---------------------------------------------------------------------------


class TestRegistros:
    def test_cada_fonte_tem_cor_e_ela_chega_ao_editor(self):
        cores = {f.code: f.color for f in datasources.fontes()}

        assert cores["documento"] == "#1d4ed8"
        assert cores["convidado"] == "#0f9d70"
        assert cores["anfitriao"] == "#8a5cf6"
        assert cores["estadia"] == "#e08a1e"
        assert cores["calculado"] == "#7c8aa6"
        for grupo in datasources.para_o_editor():
            assert grupo["color"] == cores[grupo["code"]]

    def test_uma_fonte_nova_nasce_com_a_cor_padrao(self):
        nova = datasources.FonteDeDados(code="empresa", label="Empresa")

        assert nova.color == datasources.COR_PADRAO

    def test_os_dados_de_amostra_do_editor_cobrem_toda_referencia(self):
        amostra = dados_de_exemplo.para_o_editor("carta-convite-fr")

        assert set(amostra) == datasources.todas_as_referencias()
        assert amostra["anfitriao.nome"] == "Claire Dubois"
        assert dados_de_exemplo.para_o_editor("qualquer-copia")["convidado.nome"]
        # `para()` continua como era: so o que o modelo declara.
        assert "documento.numero" not in dados_de_exemplo.para("carta-convite-fr")


# ---------------------------------------------------------------------------
# 4. As rotas do editor
# ---------------------------------------------------------------------------


@pytest.fixture
def tipo(db):
    return DocumentType.objects.create(
        code="contrato", name="Contrato", page=dict(A4), data_sources=["documento", "convidado"],
    )


@pytest.fixture
def modelo(tipo):
    return DocumentTemplate.objects.create(
        type=tipo, name="Meu contrato", slug="meu-contrato", language="pt",
        layout=layout(rico(misto(texto("Olá, "), campo("convidado.nome")))),
    )


@pytest.fixture
def staff(db, permissao_backoffice, permissoes_de_modelos):
    usuario = get_user_model().objects.create_user(
        email="editor@desenrola.be", password=SENHA, full_name="Editor", is_staff=True
    )
    usuario.user_permissions.add(permissao_backoffice, *permissoes_de_modelos)
    return get_user_model().objects.get(pk=usuario.pk)


@pytest.fixture
def leitor(db, permissao_backoffice):
    """Quem só pode VER a biblioteca."""
    usuario = get_user_model().objects.create_user(
        email="leitor@desenrola.be", password=SENHA, full_name="Leitor", is_staff=True
    )
    usuario.user_permissions.add(
        permissao_backoffice,
        Permission.objects.get(
            content_type__app_label="doctemplates", codename="view_documenttemplate"
        ),
    )
    return get_user_model().objects.get(pk=usuario.pk)


@pytest.fixture
def cliente(client, staff):
    client.force_login(staff)
    return client


def _url(nome, modelo):
    return reverse(f"backoffice:{nome}", args=[modelo.pk])


def _salvar(client, modelo, documento, **extra):
    return client.post(
        _url("template_editor_save", modelo),
        data=json.dumps({"layout": documento, **extra}),
        content_type="application/json",
    )


@pytest.mark.django_db
class TestPaginaDoEditor:
    def test_leva_os_dados_de_amostra_os_idiomas_e_as_opcoes(self, cliente, modelo):
        contexto = cliente.get(_url("template_editor", modelo)).context

        assert contexto["exemplo_json"]["convidado.nome"]
        assert {i["code"] for i in contexto["idiomas_json"]} >= {"pt", "fr", "en", "nl"}
        config = contexto["config_json"]
        assert config["language"] == "pt"
        assert config["fontFamilies"] == list(elements.FONT_FAMILIES)
        assert [m["mm"] for m in config["margins"]] == [25, 15, 35]
        assert config["flagStripe"]["colors"] == list(carta_convite.FAIXA_CORES)
        assert contexto["previa_url"] == _url("template_editor_preview", modelo)

    def test_o_conteudo_vai_por_json_script_e_nunca_interpolado(self, cliente, modelo):
        """Um `</script>` dentro do texto do modelo não fecha o script."""
        modelo.layout = layout(rico(misto(texto('</script><script>alert(1)</script>'))))
        modelo.save()

        html = cliente.get(_url("template_editor", modelo)).content.decode()

        assert "<script>alert(1)</script>" not in html
        assert "\\u003C/script\\u003E" in html or "\\u003c/script\\u003e" in html

    def test_a_tela_tem_a_estrutura_do_design(self, cliente, modelo):
        html = cliente.get(_url("template_editor", modelo)).content.decode()

        for marca in (
            "Backoffice · Modelos", "Ver com dados de exemplo", "Visualizar", "Descartar",
            "Campos do banco", "Buscar campo", "Idioma do modelo", "Margens",
            "Faixa da bandeira no topo", "Numeração de páginas no PDF", "Notas de integração",
            'data-cmd="bold"', 'data-cmd="quebra"', 'data-cmd="assinatura"', 'data-cmd="html"',
            'data-aba="texto"', 'data-aba="campos"', 'data-aba="documento"',
            'data-form-previa', "Título do documento", "Entrelinha normal",
        ):
            assert marca in html, marca

    def test_a_copia_de_um_oficial_pode_restaurar_o_padrao(
        self, cliente, staff, modelos_oficiais_prontos
    ):
        oficial = DocumentTemplate.objects.get(slug="carta-convite-fr")
        copia = duplicar_modelo(oficial, "Minha FR", created_by=staff)

        contexto = cliente.get(_url("template_editor", copia)).context

        assert contexto["pode_restaurar"] is True
        assert contexto["layout_padrao_json"] == oficial.layout

    def test_um_modelo_sem_origem_nem_tipo_oficial_nao_tem_padrao(self, cliente, modelo):
        contexto = cliente.get(_url("template_editor", modelo)).context

        assert contexto["pode_restaurar"] is False
        assert contexto["layout_padrao_json"] is None

    def test_em_leitura_os_controles_do_documento_ficam_desabilitados(self, cliente, tipo):
        travado = DocumentTemplate.objects.create(
            type=tipo, name="Travado", slug="travado", language="pt", is_locked=True
        )

        html = cliente.get(_url("template_editor", travado)).content.decode()

        assert "data-idioma disabled" in html
        assert 'data-acao="salvar"' not in html
        assert 'data-acao="restaurar"' not in html


@pytest.mark.django_db
class TestSalvamentoRico:
    def test_a_formatacao_sobrevive_ao_salvar_e_reabrir(self, cliente, modelo):
        documento = layout(rico(
            misto(
                texto("Eu, ", font_style="italic"),
                campo("convidado.nome", font_weight="bold", color="#1d4ed8"),
                texto(" convido", font_size=14, highlight="#fff6c9",
                      link="https://exemplo.be", text_decoration="underline"),
            ),
            indent=18.0, list_marker="1.", block_style="h2",
        ), document={"margin": 70.87, "page_numbers": True})

        assert _salvar(cliente, modelo, documento).status_code == 200
        modelo.refresh_from_db()
        assert modelo.layout == documento

        reaberto = cliente.get(_url("template_editor", modelo)).context["layout_json"]
        assert reaberto == documento

    @pytest.mark.parametrize(
        "parte",
        [
            texto("x", link="javascript:alert(1)"),
            texto("x", link="data:text/html,x"),
            texto("x", color="expression(alert(1))"),
            texto("x", font_family="Comic Sans"),
            texto("x", font_size=0),
            texto("x", text_decoration="onload"),
        ],
    )
    def test_um_trecho_perigoso_ou_invalido_e_recusado_e_nada_muda(self, cliente, modelo, parte):
        antes = copy.deepcopy(modelo.layout)

        resposta = _salvar(cliente, modelo, layout(rico(misto(parte))))

        assert resposta.status_code == 400
        assert resposta.json()["ok"] is False
        modelo.refresh_from_db()
        assert modelo.layout == antes

    def test_uma_quebra_de_pagina_e_gravada(self, cliente, modelo):
        documento = layout(
            rico(misto(texto("a")), "a"),
            {"id": "q", "type": "page_break", "x": 0.0, "y": 200.0, "width": 595.2756,
             "height": 0.0, "properties": {}},
        )

        assert _salvar(cliente, modelo, documento).status_code == 200
        modelo.refresh_from_db()
        assert modelo.layout["elements"][1]["type"] == "page_break"

    def test_salvar_sem_csrf_e_recusado(self, staff, modelo):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(staff)

        resposta = sem_token.post(
            _url("template_editor_save", modelo),
            data=json.dumps({"layout": layout()}),
            content_type="application/json",
        )

        assert resposta.status_code == 403

    def test_quem_so_ve_nao_salva(self, client, leitor, modelo):
        client.force_login(leitor)

        assert _salvar(client, modelo, layout()).status_code == 403


@pytest.mark.django_db
class TestPrevia:
    def _previa(self, client, modelo, documento, exemplo="1"):
        return client.post(
            _url("template_editor_preview", modelo),
            {"layout": json.dumps(documento), "exemplo": exemplo},
        )

    def test_devolve_o_pdf_do_layout_da_tela_sem_gravar(self, cliente, modelo):
        na_tela = layout(rico(misto(texto("SÓ NA TELA "), campo("convidado.nome"))))
        antes = copy.deepcopy(modelo.layout)

        resposta = self._previa(cliente, modelo, na_tela)

        assert resposta.status_code == 200
        assert resposta["Content-Type"] == "application/pdf"
        assert "inline" in resposta["Content-Disposition"]
        assert "SÓ NA TELA" in texto_do_pdf(resposta.content)
        assert "Carlos Eduardo Silva" in texto_do_pdf(resposta.content)
        modelo.refresh_from_db()
        assert modelo.layout == antes

    def test_sem_dados_de_exemplo_os_campos_ficam_em_branco(self, cliente, modelo):
        resposta = self._previa(cliente, modelo, modelo.layout, exemplo="0")

        assert resposta.status_code == 200
        assert "Carlos" not in texto_do_pdf(resposta.content)

    def test_layout_invalido_ou_vazio_e_recusado(self, cliente, modelo):
        assert self._previa(cliente, modelo, layout()).status_code == 400
        assert self._previa(cliente, modelo, {"schema_version": 1}).status_code == 400
        assert cliente.post(
            _url("template_editor_preview", modelo), {"layout": "{nao e json"}
        ).status_code == 400

    def test_um_link_perigoso_nao_chega_ao_pdf(self, cliente, modelo):
        resposta = self._previa(
            cliente, modelo, layout(rico(misto(texto("x", link="javascript:alert(1)"))))
        )

        assert resposta.status_code == 400

    def test_quem_so_ve_pode_visualizar(self, client, leitor, modelo):
        client.force_login(leitor)

        assert self._previa(client, modelo, modelo.layout).status_code == 200

    def test_exige_login_post_e_csrf(self, client, staff, modelo):
        assert client.post(_url("template_editor_preview", modelo)).status_code in (302, 403)
        client.force_login(staff)
        assert client.get(_url("template_editor_preview", modelo)).status_code == 405
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(staff)
        assert self._previa(sem_token, modelo, modelo.layout).status_code == 403


# ---------------------------------------------------------------------------
# 5. A corrente nos quatro oficiais
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCorrenteRica:
    """
    oficial -> duplicar -> formatar no editor rico -> salvar -> reabrir ->
    PDF, nos quatro idiomas -- e o oficial intacto.
    """

    @pytest.fixture(autouse=True)
    def _prontos(self, modelos_oficiais_prontos):
        pass

    def _declaracao(self, documento):
        return next(
            e for e in documento["elements"] if e["id"].endswith("-declaracao")
        )

    @pytest.mark.parametrize("idioma", carta_convite.IDIOMAS)
    def test_formatar_salvar_reabrir_e_gerar(self, cliente, staff, idioma):
        oficial = DocumentTemplate.objects.get(slug=carta_convite.slug_do_modelo(idioma))
        antes = copy.deepcopy(oficial.layout)
        copia = duplicar_modelo(oficial, f"Minha carta {idioma}", created_by=staff)

        editado = copy.deepcopy(copia.layout)
        declaracao = self._declaracao(editado)
        partes = declaracao["properties"]["content"]["parts"]
        partes.insert(0, texto("NOVO TRECHO ", font_weight="bold", color="#b4262a", font_size=12))
        partes.append(texto(" (grifado)", highlight="#fff6c9", font_style="italic"))
        partes.append(campo("documento.numero", text_decoration="underline"))
        declaracao["properties"]["list_marker"] = "1."
        declaracao["properties"]["indent"] = 18.0
        editado["document"] = {"page_numbers": True}

        assert _salvar(cliente, copia, editado, language=idioma).status_code == 200

        copia.refresh_from_db()
        reaberto = cliente.get(_url("template_editor", copia)).context["layout_json"]
        assert reaberto == editado
        assert copia.layout == editado

        dados = dados_de_exemplo.para_o_editor(copia.slug)
        conteudo, relatorio = pdf.render_template(copia, dados)
        texto_pdf = texto_do_pdf(conteudo).replace("\n", " ")
        assert "NOVO TRECHO" in texto_pdf
        assert "(grifado)" in texto_pdf
        assert "CC-2026-0001" in texto_pdf
        assert "Claire Dubois" in texto_pdf
        assert "1 / 1" in texto_pdf
        assert relatorio["paginas"] == 1
        fontes = fontes_do_pdf(conteudo)
        assert any("Italic" in f for f in fontes)

        oficial.refresh_from_db()
        assert oficial.layout == antes
        assert len(oficial.layout["elements"]) == 23
        pdf_oficial = pdf.render_template(oficial, dados_de_exemplo.para(oficial.slug))[0]
        assert "NOVO TRECHO" not in texto_do_pdf(pdf_oficial)

    @pytest.mark.parametrize("idioma", carta_convite.IDIOMAS)
    def test_o_oficial_destravado_abre_no_editor_rico_editavel(self, cliente, idioma):
        oficial = DocumentTemplate.objects.get(slug=carta_convite.slug_do_modelo(idioma))
        assert oficial.is_locked is False

        resposta = cliente.get(_url("template_editor", oficial))

        assert resposta.status_code == 200
        assert resposta.context["editavel"] is True
        assert resposta.context["layout_json"] == oficial.layout
        assert resposta.context["exemplo_json"]["convidado.nome"] == "Carlos Eduardo Silva"

    @pytest.mark.parametrize("idioma", carta_convite.IDIOMAS)
    def test_o_oficial_destravado_salva_reabre_e_gera(self, cliente, idioma):
        """Rodada 19: a mesma corrente, agora DIRETO no oficial -- sem cópia."""
        oficial = DocumentTemplate.objects.get(slug=carta_convite.slug_do_modelo(idioma))
        editado = copy.deepcopy(oficial.layout)
        self._declaracao(editado)["properties"]["content"]["parts"].insert(
            0, texto("AJUSTE DIRETO ", font_weight="bold")
        )

        assert _salvar(cliente, oficial, editado).status_code == 200

        oficial.refresh_from_db()
        assert oficial.layout == editado
        assert cliente.get(_url("template_editor", oficial)).context["layout_json"] == editado
        conteudo = pdf.render_template(oficial, dados_de_exemplo.para(oficial.slug))[0]
        assert "AJUSTE DIRETO" in texto_do_pdf(conteudo).replace("\n", " ")

    def test_o_oficial_travado_continua_recusando_o_salvamento(self, cliente):
        oficial = DocumentTemplate.objects.get(slug="carta-convite-pt")
        DocumentTemplate.objects.filter(pk=oficial.pk).update(is_locked=True)
        antes = copy.deepcopy(oficial.layout)

        assert _salvar(cliente, oficial, layout()).status_code == 409
        oficial.refresh_from_db()
        assert oficial.layout == antes


# ---------------------------------------------------------------------------
# 6. A saída do editor
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSaidaDoEditor:
    """
    O editor ocupa a janela inteira -- sem o menu do Backoffice, sem a
    barra de abas. Então ele PRECISA levar embora: quem entra tem de
    conseguir sair sem depender do botão do navegador.

    São três saídas, todas por URL nomeada: "Voltar" (o modelo), o
    kicker "Backoffice · Modelos" (a biblioteca) e "Descartar" (sai sem
    salvar). O que este grupo prova é que elas existem, apontam para
    rota real e continuam existindo quando o modelo abre em leitura.
    """

    def test_a_tela_leva_ao_modelo_e_a_biblioteca(self, cliente, modelo):
        resposta = cliente.get(_url("template_editor", modelo))
        html = resposta.content.decode()

        detalhe = reverse("backoffice:document_detail", args=[modelo.pk])
        biblioteca = reverse("backoffice:document_library")
        assert resposta.context["voltar_url"] == detalhe
        assert resposta.context["biblioteca_url"] == biblioteca
        assert f'class="te-voltar" href="{detalhe}"' in html
        assert f'href="{biblioteca}"' in html

    def test_as_duas_saidas_respondem_de_verdade(self, cliente, modelo):
        """Rota que não abre não é saída."""
        for nome, args in (
            ("backoffice:document_detail", [modelo.pk]),
            ("backoffice:document_library", []),
        ):
            assert cliente.get(reverse(nome, args=args)).status_code == 200

    def test_o_editor_diz_ao_javascript_para_onde_descartar_sai(self, cliente, modelo):
        config = cliente.get(_url("template_editor", modelo)).context["config_json"]

        assert config["backUrl"] == reverse("backoffice:document_detail", args=[modelo.pk])

    def test_descartar_existe_no_desktop_e_no_celular(self, cliente, modelo):
        """
        Dois botões: o do cabeçalho (desktop) e o da barra inferior
        (celular). No celular o do cabeçalho está escondido por CSS --
        se só ele existisse, a saída sumiria justamente onde a tela é
        menor.
        """
        html = cliente.get(_url("template_editor", modelo)).content.decode()

        assert html.count('data-acao="descartar"') == 2
        cabecalho = html[html.index("te-cabecalho-dir"): html.index("te-abas")]
        rodape = html[html.index('class="te-rodape"'):]
        assert 'data-acao="descartar"' in cabecalho
        assert 'data-acao="descartar"' in rodape

    def test_em_leitura_ainda_ha_como_sair(self, cliente, tipo):
        """
        Sem permissão de salvar não há "Descartar" -- não há o que
        descartar --, mas "Voltar" e a biblioteca continuam lá.
        """
        oficial = DocumentTemplate.objects.create(
            type=tipo, name="Oficial", slug="oficial-leitura", language="pt", is_system=True
        )
        # Rodada 19: destravado, o oficial se edita; em leitura fica o travado.
        DocumentTemplate.objects.filter(pk=oficial.pk).update(is_locked=True)

        html = cliente.get(_url("template_editor", oficial)).content.decode()

        assert 'class="te-voltar"' in html
        assert reverse("backoffice:document_detail", args=[oficial.pk]) in html
        assert reverse("backoffice:document_library") in html
        assert 'data-acao="descartar"' not in html

    def test_nenhuma_url_do_editor_e_escrita_a_mao(self):
        """
        Endereço escrito à mão no template é o que quebra em silêncio
        quando uma rota muda de caminho. Aqui todos saem de `{% url %}`
        ou do contexto.
        """
        fonte = (
            RAIZ_DO_PROJETO / "templates" / "backoffice" / "template_editor.html"
        ).read_text(encoding="utf-8")
        marcacao = fonte[fonte.index("{% block content %}"):]

        assert 'href="/' not in marcacao
        assert 'action="/' not in marcacao

    def test_o_caminho_inteiro_nao_deixa_ninguem_preso(self, cliente, modelo):
        """
        biblioteca -> modelo -> editor -> modelo -> biblioteca, pelas
        URLs que cada tela realmente publica.
        """
        biblioteca = cliente.get(reverse("backoffice:document_library")).content.decode()
        detalhe_url = reverse("backoffice:document_detail", args=[modelo.pk])
        assert detalhe_url in biblioteca

        detalhe = cliente.get(detalhe_url).content.decode()
        assert _url("template_editor", modelo) in detalhe

        editor = cliente.get(_url("template_editor", modelo)).content.decode()
        assert detalhe_url in editor
        assert reverse("backoffice:document_library") in editor


# ---------------------------------------------------------------------------
# 7. Rich text em volta de um campo dinâmico
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCampoNoMeioDoTexto:
    """
    "Prezado [Convidado · Nome completo], seja bem-vindo." -- texto,
    campo, texto. É a forma mais comum do documento, e a que mais tem a
    perder: qualquer operação que transforme o campo em texto literal
    quebra a carta de todo mundo, e só apareceria no PDF.
    """

    def frase(self, **estilo_do_campo):
        return misto(
            texto("Prezado "),
            campo("convidado.nome", **estilo_do_campo),
            texto(", seja bem-vindo."),
        )

    def _salvar_e_reabrir(self, cliente, modelo, conteudo):
        assert _salvar(cliente, modelo, layout(rico(conteudo))).status_code == 200
        modelo.refresh_from_db()
        reaberto = cliente.get(_url("template_editor", modelo)).context["layout_json"]
        assert reaberto == modelo.layout
        return modelo.layout["elements"][0]["properties"]["content"]

    @pytest.mark.parametrize(
        "estilo",
        [
            {"font_weight": "bold"},
            {"color": "#b4262a"},
            {"font_size": 14},
            {"font_family": "Times"},
            {"highlight": "#fff6c9"},
            {"text_decoration": "underline"},
            {"font_weight": "bold", "font_size": 14, "color": "#1d4ed8"},
        ],
    )
    def test_o_estilo_pode_ficar_so_no_campo(self, cliente, modelo, estilo):
        gravado = self._salvar_e_reabrir(cliente, modelo, self.frase(**estilo))

        partes = gravado["parts"]
        assert partes[1] == {"kind": "field", "source": "convidado.nome", **estilo}
        # O texto em volta não herdou nada.
        assert partes[0] == texto("Prezado ")
        assert partes[2] == texto(", seja bem-vindo.")

    def test_editar_o_texto_antes_e_depois_nao_toca_no_campo(self, cliente, modelo):
        editado = misto(
            texto("Caríssimo "),
            campo("convidado.nome", font_weight="bold"),
            texto(", seja muito bem-vindo ao país."),
        )

        gravado = self._salvar_e_reabrir(cliente, modelo, editado)

        assert gravado["parts"][1]["source"] == "convidado.nome"
        assert gravado["parts"][1]["font_weight"] == "bold"
        assert gravado["parts"][0]["value"] == "Caríssimo "

    def test_apagar_o_texto_em_volta_deixa_o_campo(self, cliente, modelo):
        gravado = self._salvar_e_reabrir(
            cliente, modelo, misto(campo("convidado.nome", font_weight="bold"))
        )

        assert gravado == misto(campo("convidado.nome", font_weight="bold"))

    def test_apagar_o_campo_deixa_o_texto_e_da_para_inserir_de_novo(self, cliente, modelo):
        sem_campo = misto(texto("Prezado "), texto(", seja bem-vindo."))

        gravado = self._salvar_e_reabrir(cliente, modelo, sem_campo)
        # `mixed` de dois textos seguidos é o que o editor manda; o
        # contrato aceita, e o campo pode voltar depois.
        assert all(p["kind"] == "text" for p in gravado["parts"])

        de_volta = self._salvar_e_reabrir(cliente, modelo, self.frase())
        assert de_volta["parts"][1] == campo("convidado.nome")

    def test_o_pdf_imprime_o_valor_e_nunca_a_referencia(self, cliente, modelo):
        self._salvar_e_reabrir(cliente, modelo, self.frase(font_weight="bold"))

        conteudo, _r = pdf.render_template(modelo, {"convidado.nome": "Marta Alves"})
        saiu = texto_do_pdf(conteudo).replace("\n", " ")

        assert "Prezado Marta Alves, seja bem-vindo." in saiu
        assert "convidado.nome" not in saiu
        assert "[Convidado" not in saiu
        fontes = fontes_do_pdf(conteudo)
        assert any("Bold" in f for f in fontes)
        assert any("Bold" not in f for f in fontes)

    def test_o_campo_sobrevive_a_duplicacao_e_a_edicao_da_copia(self, cliente, modelo, staff):
        self._salvar_e_reabrir(cliente, modelo, self.frase(font_weight="bold"))
        copia = duplicar_modelo(modelo, "Cópia com campo", created_by=staff)

        editado = copy.deepcopy(copia.layout)
        editado["elements"][0]["properties"]["content"]["parts"][0]["value"] = "Olá, "
        assert _salvar(cliente, copia, editado).status_code == 200

        copia.refresh_from_db()
        modelo.refresh_from_db()
        assert copia.layout["elements"][0]["properties"]["content"]["parts"][1] == {
            "kind": "field", "source": "convidado.nome", "font_weight": "bold",
        }
        assert modelo.layout["elements"][0]["properties"]["content"]["parts"][0]["value"] == (
            "Prezado "
        )


# ---------------------------------------------------------------------------
# 8. O botão HTML
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHtmlDoBloco:
    """
    O botão HTML deixa colar marcação no bloco. O caminho é: DOMParser
    (documento INERTE -- nada executa, nada carrega) -> `TERuns.
    serializar`, que só reconhece texto e estilo -> o layout estrutural
    -> o servidor, que revalida tudo.

    Aqui se prova a última parte: o que o navegador mandar, o servidor
    confere. Se alguém contornar o editor e postar direto no endpoint --
    que é o que faria quem tentasse -- o resultado é o mesmo.
    """

    PERIGOSOS = [
        '<script>alert(1)</script>',
        '<img src=x onerror=alert(1)>',
        '<a href="javascript:alert(1)">teste</a>',
        '<div onclick="alert(1)">teste</div>',
        '<style>body{display:none}</style>',
        '<iframe src="data:text/html,<script>alert(1)</script>"></iframe>',
        '<svg/onload=alert(1)>',
        "<a href=\"data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==\">x</a>",
    ]

    @pytest.mark.parametrize("carga", PERIGOSOS)
    def test_marcacao_perigosa_colada_e_so_texto(self, cliente, modelo, carga):
        """
        Um layout é DADO, não documento: `value` é texto e sai como
        glifo no PDF. Gravar "<script>" não cria script nenhum -- cria
        um texto que se lê "<script>".
        """
        assert _salvar(cliente, modelo, layout(rico(misto(texto(carga))))).status_code == 200

        modelo.refresh_from_db()
        gravado = modelo.layout["elements"][0]["properties"]["content"]["parts"][0]
        assert gravado == {"kind": "text", "value": carga}

        # E na tela do editor ele volta ESCAPADO, dentro de json_script:
        # `<` e `>` viram \u003C/\u003E e nenhuma tag chega a se formar.
        html = cliente.get(_url("template_editor", modelo)).content.decode()
        assert carga not in html
        assert _fora_dos_dados(html).count("alert(1)") == 0
        for pedaco in ("<script>alert", "<img ", "<iframe", "onerror=", "onclick="):
            assert pedaco not in _fora_dos_dados(html), pedaco
        if "<" in carga:
            assert "\\u003C" in html or "\\u003c" in html

    def test_nenhum_atributo_ou_tag_entra_no_layout(self, cliente, modelo):
        """
        O contrato não tem onde guardar tag, atributo ou estilo livre:
        uma propriedade desconhecida é recusada pelo validador.
        """
        el = rico(misto(texto("x")))
        el["properties"]["style"] = "position:fixed"

        resposta = _salvar(cliente, modelo, layout(el))

        assert resposta.status_code == 400
        assert "style" in resposta.json()["error"]

    def test_o_pdf_desenha_o_texto_literal(self, cliente, modelo):
        _salvar(cliente, modelo, layout(rico(misto(texto("<script>alert(1)</script>")))))
        modelo.refresh_from_db()

        conteudo, _r = pdf.render_template(modelo, {})

        assert "<script>alert(1)</script>" in texto_do_pdf(conteudo).replace("\n", "")

    def test_a_previa_tambem_revalida(self, cliente, modelo):
        resposta = cliente.post(
            _url("template_editor_preview", modelo),
            {"layout": json.dumps(layout(rico(misto(texto("x", link="javascript:alert(1)")))))},
        )

        assert resposta.status_code == 400

    def test_nenhum_html_do_modelo_e_marcado_como_seguro(self):
        """
        O projeto tem um `mark_safe` só, e é o do rodapé. O editor de
        modelos não acrescentou nenhum: o que ele grava é dado, e o
        template o escapa como qualquer outro texto.
        """
        for modulo in (
            "editor_views.py", "layout_schema.py", "elements.py", "datasources.py",
        ):
            fonte = (RAIZ_DO_PROJETO / "apps" / "doctemplates" / modulo).read_text(
                encoding="utf-8"
            )
            assert "mark_safe" not in fonte, modulo
        for parcial in ("template_editor.html",):
            fonte = (RAIZ_DO_PROJETO / "templates" / "backoffice" / parcial).read_text(
                encoding="utf-8"
            )
            assert "|safe" not in fonte
            assert "autoescape off" not in fonte


# ---------------------------------------------------------------------------
# 9. A carta já emitida é imune ao editor
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSnapshotDaCarta:
    """
    Uma `Letter` finalizada guarda o modelo CONGELADO
    (`document_snapshot`). O editor rico não muda essa regra -- e é
    justamente agora que ela mais importa: formatar o texto de um
    modelo não pode reescrever cartas já emitidas.

    `test_render_letter.py` já prova a independência para mudanças de
    nome e de layout inteiro. Aqui o que se altera é o que esta rodada
    introduziu: ênfase por trecho, cor, tamanho, marcador, margem e
    quebra de página.
    """

    @pytest.fixture
    def carta(self, user, modelos_oficiais_prontos, nacionalidade_factory):
        from apps.letters import services as letters
        from apps.letters.models import Letter

        nacionalidade_factory("brasileira", name_fr="Brésilienne")
        letra = letters.start_draft(user, "fr")
        letra.data = {
            "guest_name": "Carlos Eduardo Silva",
            "guest_nationality": "brasileira",
            "guest_birth_date": "1990-07-22",
            "guest_passport": "YY000000",
            "stay_arrival": "2026-10-10",
            "stay_departure": "2026-10-24",
        }
        letra.save(update_fields=["data", "updated_at"])
        letra.snapshot = letters.build_snapshot(letra, letra.user)
        letra.status = Letter.Status.COMPLETED
        letra.save(update_fields=["snapshot", "status", "updated_at"])
        letters.capture_document_template_snapshot(letra, letra.document_template)
        return letra

    def test_editar_o_modelo_com_texto_rico_nao_alcanca_a_carta(self, carta, cliente, staff):
        from apps.letters import services as letters

        antes = letters.render_letter(carta)
        texto_antes = texto_do_pdf(antes)
        hash_antes = carta.document_snapshot_hash

        # O oficial não se edita: o caminho real é duplicar e editar a
        # cópia. Para provar a imunidade, porém, o que interessa é o
        # PRÓPRIO modelo da carta mudar -- e um administrador pode fazer
        # isso pelo caminho administrativo (`queryset.update`), como
        # `services/carta_convite.py` faz.
        modelo = carta.document_template
        novo = copy.deepcopy(modelo.layout)
        for elemento in novo["elements"]:
            propriedades = elemento.get("properties") or {}
            conteudo = propriedades.get("content")
            if isinstance(conteudo, dict) and conteudo.get("kind") == "mixed":
                conteudo["parts"].insert(
                    0, texto("DEPOIS DA CARTA ", font_weight="bold", color="#b4262a")
                )
                propriedades["list_marker"] = "9."
                propriedades["indent"] = 18.0
        novo["document"] = {"margin": 100.0, "page_numbers": True}
        layout_schema.validate_layout(novo)
        DocumentTemplate.objects.filter(pk=modelo.pk).update(layout=novo)

        depois = letters.render_letter(carta)

        assert texto_do_pdf(depois) == texto_antes
        assert "DEPOIS DA CARTA" not in texto_do_pdf(depois)
        assert len(ler(depois).pages) == 1
        carta.refresh_from_db()
        assert carta.document_snapshot_hash == hash_antes
        # o modelo mudou de verdade -- a carta é que ficou imune
        assert "DEPOIS DA CARTA" in json.dumps(
            DocumentTemplate.objects.get(pk=modelo.pk).layout, ensure_ascii=False
        )

    def test_o_snapshot_guarda_o_layout_rico_como_estava(self, carta, cliente, staff):
        """
        Uma carta emitida de uma CÓPIA com formatação: o snapshot leva a
        formatação junto, e continua reproduzindo o documento mesmo
        depois de a cópia mudar.
        """
        from apps.letters import services as letters
        from apps.letters.models import Letter

        copia = duplicar_modelo(carta.document_template, "Cópia rica", created_by=staff)
        rico_editado = copy.deepcopy(copia.layout)
        alvo = next(
            e for e in rico_editado["elements"]
            if (e.get("properties") or {}).get("content", {}).get("kind") == "mixed"
        )
        alvo["properties"]["content"]["parts"].insert(
            0, texto("COM FORMATAÇÃO ", font_weight="bold", highlight="#fff6c9")
        )
        assert _salvar(cliente, copia, rico_editado).status_code == 200
        copia.refresh_from_db()

        outra = Letter.objects.create(
            user=carta.user, document_template=copia, language=copia.language,
            data=carta.data, status=Letter.Status.COMPLETED,
            snapshot=carta.snapshot,
        )
        letters.capture_document_template_snapshot(outra, copia)

        pdf_da_copia = letters.render_letter(outra)
        assert "COM FORMATAÇÃO" in texto_do_pdf(pdf_da_copia)

        # a cópia muda DEPOIS; a carta não se move
        outro = copy.deepcopy(copia.layout)
        outro["elements"][0]["properties"].pop("fill_color", None)
        alvo2 = next(
            e for e in outro["elements"]
            if (e.get("properties") or {}).get("content", {}).get("kind") == "mixed"
        )
        alvo2["properties"]["content"]["parts"][0]["value"] = "MUDOU DEPOIS "
        assert _salvar(cliente, copia, outro).status_code == 200

        de_novo = letters.render_letter(outra)
        assert "COM FORMATAÇÃO" in texto_do_pdf(de_novo)
        assert "MUDOU DEPOIS" not in texto_do_pdf(de_novo)


# ---------------------------------------------------------------------------
# 10. Os cinco estados de um modelo, um a um
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOsCincoEstados:
    """
    O editor esconde controles conforme o estado -- mas esconder não é
    proteger. Aqui cada estado é atacado pela URL, sem passar pela
    interface, que é exatamente o que alguém faria.

    Os estados: comum, oficial, oficial ativo, oficial travado, oficial
    com cópias, e a cópia de um oficial.

    Desde a Rodada 19 o que separa edição de leitura é só o cadeado: o
    oficial destravado se edita direto; travado -- oficial ou comum --,
    só se lê.
    """

    @pytest.fixture
    def estados(self, tipo, staff, modelos_oficiais_prontos):
        oficial = DocumentTemplate.objects.get(slug="carta-convite-fr")
        oficial_com_copia = DocumentTemplate.objects.get(slug="carta-convite-pt")
        copia = duplicar_modelo(oficial_com_copia, "Cópia do PT", created_by=staff)
        travado = DocumentTemplate.objects.get(slug="carta-convite-en")
        DocumentTemplate.objects.filter(pk=travado.pk).update(is_locked=True)
        comum_travado = DocumentTemplate.objects.create(
            type=tipo, name="Comum travado", slug="comum-travado", language="pt",
            layout=layout(rico(misto(texto("x")))),
            # Inativo porque "comum" já é o ativo deste (tipo, idioma).
            # O que este estado testa é o cadeado, e travado continua
            # travado ligado ou desligado.
            is_active=False,
        )
        DocumentTemplate.objects.filter(pk=comum_travado.pk).update(is_locked=True)
        return {
            "comum": DocumentTemplate.objects.create(
                type=tipo, name="Comum", slug="comum-editavel", language="pt"
            ),
            "oficial": oficial,
            "oficial_travado": DocumentTemplate.objects.get(pk=travado.pk),
            "oficial_com_copia": oficial_com_copia,
            "comum_travado": DocumentTemplate.objects.get(pk=comum_travado.pk),
            "copia": copia,
        }

    @pytest.mark.parametrize(
        ("estado", "editavel"),
        [
            ("comum", True),
            ("copia", True),
            ("oficial", True),
            ("oficial_travado", False),
            ("oficial_com_copia", True),
            ("comum_travado", False),
        ],
    )
    def test_a_tela_abre_no_modo_certo(self, cliente, estados, estado, editavel):
        modelo = estados[estado]

        resposta = cliente.get(_url("template_editor", modelo))

        assert resposta.status_code == 200
        assert resposta.context["editavel"] is editavel
        assert resposta.context["config_json"]["editable"] is editavel
        if not editavel:
            assert resposta.context["motivo_da_leitura"]

    @pytest.mark.parametrize("estado", ["oficial_travado", "comum_travado"])
    def test_nenhum_salvamento_passa_e_nada_muda(self, cliente, estados, estado):
        """Pela URL, sem interface: 409 e o layout intacto."""
        modelo = estados[estado]
        antes = copy.deepcopy(modelo.layout)

        resposta = _salvar(cliente, modelo, layout(rico(misto(texto("INVASÃO")))))

        assert resposta.status_code == 409
        modelo.refresh_from_db()
        assert modelo.layout == antes
        # e nem o idioma, que é o único metadado que o editor grava
        assert cliente.post(
            _url("template_editor_save", modelo),
            data=json.dumps({"layout": antes, "language": "nl"}),
            content_type="application/json",
        ).status_code == 409

    @pytest.mark.parametrize("estado", ["oficial_travado", "comum_travado"])
    def test_nem_ids_novos_saem(self, cliente, estados, estado):
        assert cliente.post(_url("template_editor_ids", estados[estado])).status_code == 403

    @pytest.mark.parametrize("estado", ["oficial", "oficial_com_copia"])
    def test_o_oficial_destravado_salva_direto(self, cliente, estados, estado):
        """
        Pela URL: o layout novo passa, e os ids novos saem. O idioma, não
        -- ele é a identidade do oficial, destravado ou não.
        """
        modelo = estados[estado]
        novo = layout(rico(misto(texto("AJUSTE"))))

        assert _salvar(cliente, modelo, novo).status_code == 200
        modelo.refresh_from_db()
        assert modelo.layout == novo
        assert cliente.post(_url("template_editor_ids", modelo)).status_code == 200

        idioma = modelo.language
        assert _salvar(cliente, modelo, novo, language="nl").status_code == 409
        modelo.refresh_from_db()
        assert modelo.language == idioma

    def test_a_tela_do_oficial_destravado_traz_os_controles_de_gravar(self, cliente, estados):
        html = cliente.get(_url("template_editor", estados["oficial"])).content.decode()

        assert 'data-acao="salvar"' in html
        assert 'data-acao="descartar"' in html

    @pytest.mark.parametrize("estado", ["oficial_travado", "comum_travado"])
    def test_a_tela_em_leitura_nao_traz_os_controles_de_gravar(self, cliente, estados, estado):
        html = cliente.get(_url("template_editor", estados[estado])).content.decode()

        assert 'data-acao="salvar"' not in html
        assert 'data-acao="descartar"' not in html
        assert 'data-acao="restaurar"' not in html
        # e o que resta é leitura: os campos do banco não inserem nada
        assert "data-idioma disabled" in html

    def test_duplicar_um_oficial_travado_continua_possivel(self, cliente, estados, staff):
        """
        Travado é "fechado para edição", não "fechado para sempre": o
        caminho de criação do produto (duplicar) tem de continuar aberto,
        senão um oficial travado viraria um beco sem saída.
        """
        travado = estados["oficial_travado"]

        resposta = cliente.post(
            reverse("backoffice:document_library_duplicate", args=[travado.pk]),
            {"name": "Cópia de um travado"},
        )

        copia = DocumentTemplate.objects.get(name="Cópia de um travado")
        assert resposta.status_code == 302
        assert resposta.url == _url("template_editor", copia)
        assert copia.is_locked is False and copia.is_system is False
        assert copia.layout == travado.layout
        assert cliente.get(_url("template_editor", copia)).context["editavel"] is True

    def test_editar_a_copia_nunca_alcanca_o_oficial_nem_as_irmas(
        self, cliente, estados, staff
    ):
        oficial = estados["oficial_com_copia"]
        copia = estados["copia"]
        irma = duplicar_modelo(oficial, "Outra cópia do PT", created_by=staff)
        antes_do_oficial = copy.deepcopy(oficial.layout)
        antes_da_irma = copy.deepcopy(irma.layout)

        editado = copy.deepcopy(copia.layout)
        alvo = next(
            e for e in editado["elements"]
            if (e.get("properties") or {}).get("content", {}).get("kind") == "mixed"
        )
        alvo["properties"]["content"]["parts"].insert(
            0, texto("SÓ NA CÓPIA ", font_weight="bold", color="#b4262a")
        )
        assert _salvar(cliente, copia, editado).status_code == 200

        oficial.refresh_from_db()
        irma.refresh_from_db()
        copia.refresh_from_db()
        assert "SÓ NA CÓPIA" in json.dumps(copia.layout, ensure_ascii=False)
        assert oficial.layout == antes_do_oficial
        assert irma.layout == antes_da_irma
        assert "SÓ NA CÓPIA" not in texto_do_pdf(
            pdf.render_template(oficial, dados_de_exemplo.para(oficial.slug))[0]
        )
        assert "SÓ NA CÓPIA" in texto_do_pdf(
            pdf.render_template(copia, dados_de_exemplo.para_o_editor(copia.slug))[0]
        )

    def test_quem_so_ve_nao_edita_nem_um_modelo_comum(self, client, leitor, estados):
        """A permissão vale por PESSOA, não só pelo estado do modelo."""
        client.force_login(leitor)
        comum = estados["comum"]

        assert client.get(_url("template_editor", comum)).context["editavel"] is False
        assert _salvar(client, comum, layout()).status_code == 403
        assert client.post(_url("template_editor_ids", comum)).status_code == 403

    def test_quem_so_ve_nao_edita_nem_o_oficial_destravado(self, client, leitor, estados):
        client.force_login(leitor)
        oficial = estados["oficial"]
        antes = copy.deepcopy(oficial.layout)

        assert client.get(_url("template_editor", oficial)).context["editavel"] is False
        assert _salvar(client, oficial, layout()).status_code == 403
        assert client.post(_url("template_editor_ids", oficial)).status_code == 403
        oficial.refresh_from_db()
        assert oficial.layout == antes
