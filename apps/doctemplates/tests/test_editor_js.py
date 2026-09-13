"""
A logica do editor que vive no navegador (Etapa 4.2A).

Os modulos de `static/js/editor/` foram escritos para funcionar tambem no
Node (`module.exports` quando existe, global quando nao), entao aqui eles
sao `require()`-ados de verdade e exercitados com dados -- nao ha
extracao por regex nem conferencia de string em HTML.

Dois grupos:

  * COMPORTAMENTO -- criar, mover, duplicar, desfazer, serializar. E a
    logica que o usuario sente;
  * PARIDADE -- as mesmas contas de geometria feitas em Python e em
    JavaScript tem de dar o mesmo numero. Sao duas implementacoes da
    mesma regra, e duas implementacoes divergem em silencio se ninguem
    comparar.

Sem Node instalado tudo aqui e pulado: a suite do projeto e Python e nao
vai ganhar uma dependencia obrigatoria de outra ferramenta.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from apps.doctemplates import coordinates as geo
from apps.doctemplates.visual_schema import A4_HEIGHT_PT, A4_WIDTH_PT

RAIZ = Path(__file__).resolve().parents[3]
EDITOR_JS = RAIZ / "static" / "js" / "editor"

MODULOS = {
    "Geo": "geometry.js",
    "Doc": "document.js",
    "Hist": "history.js",
    "Render": "render.js",
}


@pytest.fixture(scope="module")
def node():
    caminho = shutil.which("node")
    if caminho is None:
        pytest.skip("Node não está instalado neste ambiente")
    return caminho


def executar(node, corpo):
    """
    Roda `corpo` no Node com os modulos do editor ja carregados, e
    devolve o que o script imprimir como JSON.
    """
    requires = "\n".join(
        f'var {nome} = require({str(EDITOR_JS / arquivo).replace(chr(92), "/")!r});'
        for nome, arquivo in MODULOS.items()
    )
    resultado = subprocess.run(
        [node, "-e", requires + "\n" + corpo],
        capture_output=True,
        text=True,
        # O Node escreve UTF-8. Sem dizer isto, o Python decodifica
        # com o locale do Windows (cp1252) e todo acento vira lixo.
        encoding="utf-8",
        timeout=30,
    )
    if resultado.returncode != 0:
        raise AssertionError(f"Node falhou:\n{resultado.stderr}")
    return json.loads(resultado.stdout)


# ---------------------------------------------------------------------------
# 1. Os modulos carregam
# ---------------------------------------------------------------------------


def test_os_modulos_do_editor_carregam_no_node(node):
    saida = executar(
        node,
        "console.log(JSON.stringify({"
        "geo: typeof Geo.paraCoordenadasPdf,"
        "doc: typeof Doc.criarElemento,"
        "hist: typeof Hist.registrar,"
        "render: typeof Render.estiloDeTexto}));",
    )

    assert saida == {
        "geo": "function",
        "doc": "function",
        "hist": "function",
        "render": "function",
    }


@pytest.mark.parametrize("arquivo", sorted(p.name for p in EDITOR_JS.glob("*.js")))
def test_todo_javascript_do_editor_tem_sintaxe_valida(node, arquivo):
    resultado = subprocess.run(
        [node, "--check", str(EDITOR_JS / arquivo)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )

    assert resultado.returncode == 0, resultado.stderr


# ---------------------------------------------------------------------------
# 2. Paridade de geometria entre JavaScript e Python
# ---------------------------------------------------------------------------


class TestParidadeDeCoordenadas:
    CAIXAS = [
        {"x": 72.0, "y": 100.0, "width": 200.0, "height": 20.0},
        {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0},
        # Valores com casas decimais: e assim que o documento oficial foi
        # medido, e e onde um arredondamento escondido apareceria.
        {"x": 72.3456, "y": 120.9876, "width": 400.125, "height": 13.5},
        {"x": 12.5, "y": 821.8898, "width": 570.0, "height": 20.0},
        {"x": -5.25, "y": -10.75, "width": 30.5, "height": 40.25},
    ]

    def test_a_conversao_para_pdf_da_o_mesmo_resultado(self, node):
        do_js = executar(
            node,
            "var caixas = " + json.dumps(self.CAIXAS) + ";"
            "console.log(JSON.stringify(caixas.map(function (c) {"
            f"  return Geo.paraCoordenadasPdf(c, {A4_HEIGHT_PT});"
            "})));",
        )

        do_python = [geo.para_coordenadas_pdf(c, A4_HEIGHT_PT) for c in self.CAIXAS]

        assert do_js == [
            {chave: pytest.approx(valor, abs=1e-9) for chave, valor in caixa.items()}
            for caixa in do_python
        ]

    def test_o_zoom_para_caber_da_o_mesmo_resultado(self, node):
        larguras = [200, 400, 640, 1024, 1600, 5000]

        do_js = executar(
            node,
            "var ls = " + json.dumps(larguras) + ";"
            "console.log(JSON.stringify(ls.map(function (l) {"
            f"  return Geo.zoomParaCaber(l, {A4_WIDTH_PT}, 32);"
            "})));",
        )

        do_python = [
            geo.zoom_para_caber(largura, A4_WIDTH_PT, 32) for largura in larguras
        ]

        assert do_js == pytest.approx(do_python, abs=1e-9)

    def test_os_limites_de_zoom_sao_os_mesmos(self, node):
        do_js = executar(
            node,
            "console.log(JSON.stringify([Geo.ZOOM_MINIMO, Geo.ZOOM_MAXIMO,"
            "Geo.clampZoom(99), Geo.clampZoom(0.01)]));",
        )

        assert do_js == [
            geo.ZOOM_MINIMO,
            geo.ZOOM_MAXIMO,
            geo.clamp_zoom(99),
            geo.clamp_zoom(0.01),
        ]

    def test_as_constantes_da_pagina_sao_as_mesmas(self, node):
        do_js = executar(
            node,
            "console.log(JSON.stringify([Geo.A4_WIDTH_PT, Geo.A4_HEIGHT_PT,"
            "Doc.SCHEMA_VERSION]));",
        )

        assert do_js[0] == A4_WIDTH_PT
        assert do_js[1] == A4_HEIGHT_PT
        assert do_js[2] == 1

    def test_ida_e_volta_no_javascript_devolve_o_original(self, node):
        do_js = executar(
            node,
            "var caixas = " + json.dumps(self.CAIXAS) + ";"
            "console.log(JSON.stringify(caixas.map(function (c) {"
            "  return Geo.doPdfParaDocumento(Geo.paraCoordenadasPdf(c));"
            "})));",
        )

        for original, volta in zip(self.CAIXAS, do_js, strict=True):
            assert volta == {k: pytest.approx(v) for k, v in original.items()}

    def test_encaixar_na_grade_com_passo_zero_nao_arredonda(self, node):
        """
        Passo 0 = encaixe desligado. Tem de devolver o valor intacto, com
        as casas decimais -- e o que permite precisao de PDF.
        """
        do_js = executar(
            node,
            "console.log(JSON.stringify(["
            "Geo.encaixarNaGrade(72.3456, 0),"
            "Geo.encaixarNaGrade(72.3456, 12),"
            "Geo.encaixarNaGrade(80, 12)]));",
        )

        assert do_js == [72.3456, 72, 84]


# ---------------------------------------------------------------------------
# 3. Operacoes sobre elementos
# ---------------------------------------------------------------------------


class TestOperacoesDeElemento:
    def test_todo_tipo_nasce_com_propriedades_que_o_servidor_aceita(self, node):
        """
        Um padrao do editor que o validador do servidor recusasse daria
        um elemento impossivel de salvar assim que criado.
        """
        do_js = executar(
            node,
            "console.log(JSON.stringify(Doc.TIPOS.map(function (t) {"
            "  return Doc.criarElemento(t, {x: 10, y: 20});"
            "})));",
        )

        from apps.doctemplates.visual_schema import (
            ELEMENT_TYPES,
            documento_vazio,
            validate_visual_schema,
        )

        doc = documento_vazio()
        doc["elements"] = do_js

        # Como rascunho, todos passam -- inclusive os que nascem
        # incompletos (campo sem referencia, imagem sem arquivo, QR sem
        # conteudo), que e como se desenha: larga na pagina, decide depois.
        validate_visual_schema(doc)
        # Contagem derivada do contrato, nao escrita a mao: um tipo novo
        # no schema passa a ser cobrado aqui automaticamente.
        assert len(do_js) == len(ELEMENT_TYPES)
        assert {el["type"] for el in do_js} == set(ELEMENT_TYPES)

        # Na publicacao, esses tres sao barrados.
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            validate_visual_schema(doc, para_publicar=True)

    def test_cada_elemento_nasce_com_id_proprio(self, node):
        ids = executar(
            node,
            "var d = Doc.documentoVazio();"
            "for (var i = 0; i < 50; i++) {"
            "  d = Doc.adicionar(d, Doc.criarElemento('text'));"
            "}"
            "console.log(JSON.stringify(d.elements.map(function (e) { return e.id; })));",
        )

        assert len(ids) == 50
        assert len(set(ids)) == 50

    def test_adicionar_poe_o_novo_elemento_por_cima(self, node):
        zs = executar(
            node,
            "var d = Doc.documentoVazio();"
            "d = Doc.adicionar(d, Doc.criarElemento('rect'));"
            "d = Doc.adicionar(d, Doc.criarElemento('text'));"
            "d = Doc.adicionar(d, Doc.criarElemento('line'));"
            "console.log(JSON.stringify(d.elements.map(function (e) { return e.z_index; })));",
        )

        assert zs == [1, 2, 3]

    def test_as_operacoes_nao_alteram_o_documento_recebido(self, node):
        """
        E o que faz o desfazer funcionar guardando referencias, sem clonar
        a cada tecla.
        """
        saida = executar(
            node,
            "var a = Doc.adicionar(Doc.documentoVazio(), Doc.criarElemento('text'));"
            "var id = a.elements[0].id;"
            "var b = Doc.atualizarGeometria(a, id, {x: 999});"
            "console.log(JSON.stringify({"
            "  original: a.elements[0].x,"
            "  novo: b.elements[0].x,"
            "  saoObjetosDiferentes: a !== b}));",
        )

        assert saida["original"] == 72
        assert saida["novo"] == 999
        assert saida["saoObjetosDiferentes"] is True

    def test_a_geometria_aceita_casas_decimais(self, node):
        saida = executar(
            node,
            "var d = Doc.adicionar(Doc.documentoVazio(), Doc.criarElemento('text'));"
            "var id = d.elements[0].id;"
            "d = Doc.atualizarGeometria(d, id, {x: 72.3456, y: 120.9876, width: 400.125});"
            "console.log(JSON.stringify(d.elements[0]));",
        )

        assert saida["x"] == 72.3456
        assert saida["y"] == 120.9876
        assert saida["width"] == 400.125

    def test_dimensao_negativa_e_travada_em_zero(self, node):
        saida = executar(
            node,
            "var d = Doc.adicionar(Doc.documentoVazio(), Doc.criarElemento('rect'));"
            "var id = d.elements[0].id;"
            "d = Doc.atualizarGeometria(d, id, {width: -50, height: -10});"
            "console.log(JSON.stringify(d.elements[0]));",
        )

        assert saida["width"] == 0
        assert saida["height"] == 0

    def test_duplicar_gera_id_novo_e_desloca(self, node):
        saida = executar(
            node,
            "var d = Doc.adicionar(Doc.documentoVazio(), Doc.criarElemento('text'));"
            "var r = Doc.duplicar(d, d.elements[0].id);"
            "console.log(JSON.stringify({"
            "  quantos: r.documento.elements.length,"
            "  idsDiferentes: r.documento.elements[0].id !== r.documento.elements[1].id,"
            "  dx: r.documento.elements[1].x - r.documento.elements[0].x,"
            "  conteudoIgual: r.documento.elements[1].properties.content ==="
            "    r.documento.elements[0].properties.content}));",
        )

        assert saida == {"quantos": 2, "idsDiferentes": True, "dx": 10, "conteudoIgual": True}

    def test_duplicar_faz_copia_profunda(self, node):
        """Mexer na copia nao pode alcancar o original."""
        saida = executar(
            node,
            "var d = Doc.adicionar(Doc.documentoVazio(), Doc.criarElemento('table'));"
            "var r = Doc.duplicar(d, d.elements[0].id);"
            "r.documento.elements[1].properties.columns[0].width = 999;"
            "console.log(JSON.stringify(r.documento.elements[0].properties.columns[0].width));",
        )

        assert saida == 120

    def test_remover_tira_so_o_pedido(self, node):
        saida = executar(
            node,
            "var d = Doc.documentoVazio();"
            "d = Doc.adicionar(d, Doc.criarElemento('text'));"
            "d = Doc.adicionar(d, Doc.criarElemento('rect'));"
            "var alvo = d.elements[0].id;"
            "d = Doc.remover(d, alvo);"
            "console.log(JSON.stringify({"
            "  restam: d.elements.length, tipo: d.elements[0].type}));",
        )

        assert saida == {"restam": 1, "tipo": "rect"}

    def test_trazer_para_frente_e_enviar_para_tras(self, node):
        saida = executar(
            node,
            "var d = Doc.documentoVazio();"
            "d = Doc.adicionar(d, Doc.criarElemento('rect'));"
            "d = Doc.adicionar(d, Doc.criarElemento('text'));"
            "var fundo = d.elements[0].id;"
            "d = Doc.trazerParaFrente(d, fundo);"
            "var z1 = Doc.encontrar(d, fundo).z_index;"
            "d = Doc.enviarParaTras(d, fundo);"
            "var z2 = Doc.encontrar(d, fundo).z_index;"
            "console.log(JSON.stringify([z1, z2]));",
        )

        assert saida[0] == 3
        assert saida[1] < 0

    def test_a_ordem_de_desenho_segue_o_z_index(self, node):
        saida = executar(
            node,
            "var base = {type: 'text', x: 0, y: 0, width: 1, height: 1, properties: {}};"
            "var d = Doc.documentoVazio();"
            "d.elements = ["
            "  Object.assign({}, base, {id: 'a', z_index: 5}),"
            "  Object.assign({}, base, {id: 'b', z_index: 1}),"
            "  Object.assign({}, base, {id: 'c', z_index: 3})];"
            "console.log(JSON.stringify(Doc.ordenadosParaDesenho(d)"
            "  .map(function (e) { return e.id; })));",
        )

        assert saida == ["b", "c", "a"]

    def test_tipo_desconhecido_nao_e_criado(self, node):
        saida = executar(
            node,
            "var erro = null;"
            "try { Doc.criarElemento('iframe'); } catch (e) { erro = e.message; }"
            "console.log(JSON.stringify(erro));",
        )

        assert "iframe" in saida


# ---------------------------------------------------------------------------
# 4. Serializacao
# ---------------------------------------------------------------------------


class TestSerializacao:
    def test_serializar_e_desserializar_devolve_o_mesmo(self, node):
        saida = executar(
            node,
            "var d = Doc.documentoVazio();"
            "d = Doc.adicionar(d, Doc.criarElemento('text'));"
            "d = Doc.adicionar(d, Doc.criarElemento('table'));"
            "var volta = Doc.desserializar(Doc.serializar(d));"
            "console.log(JSON.stringify({"
            "  iguais: JSON.stringify(Doc.ordenadosParaDesenho(volta)) ==="
            "    JSON.stringify(Doc.ordenadosParaDesenho(d)),"
            "  pagina: volta.page}));",
        )

        assert saida["iguais"] is True
        assert saida["pagina"]["width"] == A4_WIDTH_PT

    def test_o_json_serializado_passa_na_validacao_do_servidor(self, node):
        """
        O contrato dos dois lados e o mesmo. Se divergir, o editor
        produziria documentos que o servidor recusa -- exatamente o tipo
        de erro que so aparece no primeiro salvamento real.
        """
        texto = executar(
            node,
            "var d = Doc.documentoVazio();"
            "d = Doc.adicionar(d, Doc.criarElemento('text'));"
            "d = Doc.adicionar(d, Doc.criarElemento('rect'));"
            "d = Doc.adicionar(d, Doc.criarElemento('line'));"
            "d = Doc.adicionar(d, Doc.criarElemento('table'));"
            "console.log(JSON.stringify(JSON.parse(Doc.serializar(d))));",
        )

        from apps.doctemplates.visual_schema import validate_visual_schema

        validate_visual_schema(texto)

    def test_o_estado_da_interface_nao_vai_para_o_json(self, node):
        """Zoom, selecao e grade sao de quem esta olhando, nao do documento."""
        chaves = executar(
            node,
            "var d = Doc.adicionar(Doc.documentoVazio(), Doc.criarElemento('text'));"
            "console.log(JSON.stringify(Object.keys(JSON.parse(Doc.serializar(d)))));",
        )

        assert sorted(chaves) == ["elements", "page", "schema_version"]

    def test_desserializar_lixo_devolve_documento_vazio(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(Doc.desserializar('{}')));",
        )

        assert saida["elements"] == []
        assert saida["page"]["width"] == A4_WIDTH_PT


# ---------------------------------------------------------------------------
# 5. Desfazer e refazer
# ---------------------------------------------------------------------------


class TestHistorico:
    def test_desfazer_volta_ao_estado_anterior(self, node):
        saida = executar(
            node,
            "var d = Doc.documentoVazio();"
            "var h = Hist.criar(d);"
            "h = Hist.registrar(h, Doc.adicionar(d, Doc.criarElemento('text')));"
            "var depois = Hist.atual(h).elements.length;"
            "h = Hist.desfazer(h);"
            "console.log(JSON.stringify([depois, Hist.atual(h).elements.length]));",
        )

        assert saida == [1, 0]

    def test_refazer_traz_de_volta(self, node):
        saida = executar(
            node,
            "var d = Doc.documentoVazio();"
            "var h = Hist.criar(d);"
            "h = Hist.registrar(h, Doc.adicionar(d, Doc.criarElemento('text')));"
            "h = Hist.desfazer(h);"
            "h = Hist.refazer(h);"
            "console.log(JSON.stringify(Hist.atual(h).elements.length));",
        )

        assert saida == 1

    def test_nao_da_para_desfazer_alem_do_inicio(self, node):
        saida = executar(
            node,
            "var h = Hist.criar(Doc.documentoVazio());"
            "h = Hist.desfazer(h); h = Hist.desfazer(h);"
            "console.log(JSON.stringify({"
            "  indice: h.indice, pode: Hist.podeDesfazer(h)}));",
        )

        assert saida == {"indice": 0, "pode": False}

    def test_nao_da_para_refazer_alem_do_fim(self, node):
        saida = executar(
            node,
            "var h = Hist.criar(Doc.documentoVazio());"
            "h = Hist.refazer(h);"
            "console.log(JSON.stringify(Hist.podeRefazer(h)));",
        )

        assert saida is False

    def test_uma_acao_nova_descarta_o_ramo_refeito(self, node):
        """
        Depois de desfazer e fazer outra coisa, o ramo antigo deixa de
        existir -- comportamento que todo editor tem.
        """
        saida = executar(
            node,
            "var d = Doc.documentoVazio();"
            "var h = Hist.criar(d);"
            "h = Hist.registrar(h, Doc.adicionar(d, Doc.criarElemento('text')));"
            "h = Hist.registrar(h, Doc.adicionar(Hist.atual(h), Doc.criarElemento('rect')));"
            "h = Hist.desfazer(h);"
            "h = Hist.registrar(h, Doc.adicionar(Hist.atual(h), Doc.criarElemento('line')));"
            "console.log(JSON.stringify({"
            "  podeRefazer: Hist.podeRefazer(h),"
            "  tipos: Hist.atual(h).elements.map(function (e) { return e.type; })}));",
        )

        assert saida["podeRefazer"] is False
        assert saida["tipos"] == ["text", "line"]

    def test_o_historico_tem_limite(self, node):
        saida = executar(
            node,
            "var h = Hist.criar(Doc.documentoVazio(), 5);"
            "for (var i = 0; i < 20; i++) {"
            "  h = Hist.registrar(h, Doc.adicionar(Hist.atual(h), Doc.criarElemento('text')));"
            "}"
            "console.log(JSON.stringify({"
            "  guardados: h.estados.length,"
            "  elementos: Hist.atual(h).elements.length}));",
        )

        # O limite descarta o mais antigo, mas o estado ATUAL continua
        # completo -- desfazer fica limitado, o documento nao.
        assert saida["guardados"] == 5
        assert saida["elementos"] == 20

    def test_desfazer_muitas_vezes_chega_ao_inicio_do_que_foi_guardado(self, node):
        saida = executar(
            node,
            "var h = Hist.criar(Doc.documentoVazio());"
            "for (var i = 0; i < 10; i++) {"
            "  h = Hist.registrar(h, Doc.adicionar(Hist.atual(h), Doc.criarElemento('text')));"
            "}"
            "for (var j = 0; j < 100; j++) { h = Hist.desfazer(h); }"
            "console.log(JSON.stringify(Hist.atual(h).elements.length));",
        )

        assert saida == 0


# ---------------------------------------------------------------------------
# 6. Renderizacao (as partes puras)
# ---------------------------------------------------------------------------


class TestRenderizacao:
    def test_o_estilo_de_texto_acompanha_o_zoom(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Render.estiloDeTexto({font_size: 11}, 1).fontSize,"
            "Render.estiloDeTexto({font_size: 11}, 2).fontSize]));",
        )

        assert saida == ["11px", "22px"]

    def test_o_peso_da_fonte_vira_css(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Render.estiloDeTexto({font_weight: 'bold'}, 1).fontWeight,"
            "Render.estiloDeTexto({font_weight: 'regular'}, 1).fontWeight]));",
        )

        assert saida == ["700", "400"]

    def test_um_campo_sem_referencia_e_sinalizado(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Render.rotuloDeCampo({field: ''}, []),"
            "Render.rotuloDeCampo({field: 'guest_name'}, []),"
            "Render.rotuloDeCampo({field: 'guest_name'},"
            "  [{key: 'guest_name', label: 'Nome do convidado'}])]));",
        )

        assert "não escolhido" in saida[0]
        assert saida[1] == "{{ guest_name }}"
        assert saida[2] == "{{ Nome do convidado }}"

    def test_o_editor_nunca_recebe_o_valor_do_campo(self, node):
        """
        O valor so existe quando uma carta e gerada. O editor mostra a
        referencia -- guardar o valor congelaria o dado de uma pessoa
        dentro do modelo.
        """
        saida = executar(
            node,
            "var el = Doc.criarElemento('field');"
            "console.log(JSON.stringify(Object.keys(el.properties)));",
        )

        assert "field" in saida
        assert "value" not in saida
