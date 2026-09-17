"""
A lógica do editor que vive no navegador (Etapa 3.2; editor rico na 3.7).

Os módulos de `static/js/template-editor/` foram escritos para funcionar
também no Node (`module.exports` quando existe, global quando não), então
aqui eles são `require()`-ados de verdade e exercitados com dados — não há
extração por regex nem conferência de string em HTML.

Os grupos:

  * GEOMETRIA — as contas de pt ↔ pixel, comparadas com o Python quando
    há equivalente;
  * ESTADO — criar, mover, redimensionar, duplicar, camadas, desfazer;
  * TRECHOS (runs.js) — o conteúdo estrutural ida e volta do DOM, e o
    que o navegador produz ao formatar;
  * DOCUMENTO (document.js) — refluxo, inserir/remover, dividir/juntar,
    listas, margens, faixa, páginas, campos usados;
  * CANVAS — que cada tipo vira um nó com a posição e o conteúdo certos;
  * PAINÉIS — campos do banco, campos no documento, barra contextual.

O que sai do JavaScript volta para `validate_layout` em Python sempre que
o resultado é um layout: o editor não pode produzir o que o servidor
recusa.

O DOM mínimo (`dom_stub.js`) implementa só o que os módulos usam. Sem
Node instalado tudo aqui é pulado — a suíte do projeto é Python e não
ganha dependência obrigatória de outra ferramenta.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from apps.doctemplates import elements, layout_schema
from apps.doctemplates.services import layout as servico_de_layout

RAIZ = Path(__file__).resolve().parents[3]
JS = RAIZ / "static" / "js" / "template-editor"
DOM_STUB = Path(__file__).parent / "dom_stub.js"

MODULOS = {
    "Geo": "geometry.js",
    "State": "state.js",
    "Runs": "runs.js",
    "Doc": "document.js",
    "Canvas": "canvas.js",
    "Panels": "panels.js",
    "Api": "api.js",
}

A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}

FONTES = [
    {
        "code": "convidado", "label": "Convidado", "color": "#0f9d70",
        "fields": [
            {"reference": "convidado.nome", "key": "nome", "label": "Nome completo",
             "kind": "texto"},
        ],
    },
    {
        "code": "anfitriao", "label": "Anfitrião", "color": "#8a5cf6",
        "fields": [
            {"reference": "anfitriao.nome", "key": "nome", "label": "Nome completo",
             "kind": "texto"},
            {"reference": "anfitriao.cidade", "key": "cidade", "label": "Cidade",
             "kind": "texto"},
        ],
    },
]


def _caminho(p):
    return str(p).replace("\\", "/")


@pytest.fixture(scope="module")
def node():
    caminho = shutil.which("node")
    if caminho is None:
        pytest.skip("Node não está instalado neste ambiente")
    return caminho


@pytest.fixture(scope="module")
def catalogo():
    """O registro de tipos, como o servidor o entrega à página."""
    return elements.para_o_editor()


def executar(node, corpo, extras=None):
    """
    Roda `corpo` no Node com os módulos do editor carregados e devolve o
    que o script imprimir como JSON.
    """
    requires = "\n".join(
        f"var {nome} = require({_caminho(JS / arquivo)!r});"
        for nome, arquivo in MODULOS.items()
    )
    requires += f"\nvar dom = require({_caminho(DOM_STUB)!r});"
    declaracoes = "\n".join(
        f"var {nome} = {json.dumps(valor)};" for nome, valor in (extras or {}).items()
    )
    resultado = subprocess.run(
        [node, "-e", requires + "\n" + declaracoes + "\n" + corpo],
        capture_output=True,
        text=True,
        # O Node escreve UTF-8. Sem dizer isto, o Python decodifica com o
        # locale do Windows e todo acento vira lixo.
        encoding="utf-8",
        timeout=30,
    )
    if resultado.returncode != 0:
        raise AssertionError(f"Node falhou:\n{resultado.stderr}")
    return json.loads(resultado.stdout)


def texto(valor, **estilo):
    return {"kind": "text", "value": valor, **estilo}


def campo(referencia, **estilo):
    return {"kind": "field", "source": referencia, **estilo}


def bloco_de_texto(identificador, y, valor="x", altura=13.5, x=50.0, largura=400.0, **props):
    return {
        "id": identificador, "type": "text", "x": x, "y": y, "width": largura,
        "height": altura,
        "properties": {"content": texto(valor), "font_size": 11, "line_height": 1.25, **props},
    }


def layout(*elementos):
    return {"version": 1, "elements": list(elementos)}


# ---------------------------------------------------------------------------
# 0. Os módulos carregam
# ---------------------------------------------------------------------------


def test_os_modulos_carregam_no_node(node):
    saida = executar(
        node,
        "console.log(JSON.stringify({"
        "geo: typeof Geo.paraDocumento,"
        "state: typeof State.criarElemento,"
        "runs: typeof Runs.serializar,"
        "doc: typeof Doc.ajustarAltura,"
        "canvas: typeof Canvas.desenharLayout,"
        "panels: typeof Panels.montarCampos,"
        "api: typeof Api.salvar}));",
    )

    assert saida == {
        "geo": "function", "state": "function", "runs": "function", "doc": "function",
        "canvas": "function", "panels": "function", "api": "function",
    }


@pytest.mark.parametrize("arquivo", sorted(p.name for p in JS.glob("*.js")))
def test_todo_javascript_tem_sintaxe_valida(node, arquivo):
    resultado = subprocess.run(
        [node, "--check", str(JS / arquivo)],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )

    assert resultado.returncode == 0, resultado.stderr


def test_o_painel_de_propriedades_antigo_saiu():
    """A barra de ferramentas e a barra contextual o substituem."""
    assert not (JS / "properties.js").exists()


# ---------------------------------------------------------------------------
# 1. Geometria: pt ↔ pixel
# ---------------------------------------------------------------------------


class TestGeometria:
    def test_ida_e_volta_devolve_o_original(self, node):
        valores = [0, 49.6, 72.3456, 400.125, 841.8898, -12.5]

        saida = executar(
            node,
            "var vs = " + json.dumps(valores) + ";"
            "console.log(JSON.stringify(vs.map(function (v) {"
            "  return Geo.paraDocumento(Geo.paraTela(v, 1.75), 1.75);"
            "})));",
        )

        assert saida == pytest.approx(valores)

    @pytest.mark.parametrize("zoom", [0.25, 0.5, 1.0, 2.0, 4.0])
    def test_a_escala_multiplica_tudo_igualmente(self, node, zoom):
        caixa = {"x": 49.6, "y": 120.0, "width": 400.125, "height": 13.5}

        saida = executar(
            node,
            f"var c = {json.dumps(caixa)};"
            f"console.log(JSON.stringify(Geo.caixaParaTela(c, {zoom})));",
        )

        for chave, valor in caixa.items():
            assert saida[chave] == pytest.approx(valor * zoom)

    def test_o_zoom_fica_dentro_dos_limites(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify([Geo.limitarZoom(99), Geo.limitarZoom(0.01),"
            "Geo.limitarZoom(1), Geo.ZOOM_MINIMO, Geo.ZOOM_MAXIMO]));",
        )

        assert saida == [4, 0.25, 1, 0.25, 4]

    def test_zoom_zero_nao_passa_despercebido(self, node):
        saida = executar(
            node,
            "var erro = null;"
            "try { Geo.paraDocumento(10, 0); } catch (e) { erro = e.message; }"
            "console.log(JSON.stringify(erro));",
        )

        assert "zoom" in saida

    def test_ajustar_nunca_amplia_acima_do_tamanho_real(self, node):
        saida = executar(
            node, "console.log(JSON.stringify(Geo.zoomParaCaber(5000, 595.2756, 48)));"
        )

        assert saida == 1

    def test_a_folha_tem_os_794px_do_design_a_cem_por_cento(self, node):
        """1pt = 96/72 px: a folha A4 do design tem 794px de largura."""
        saida = executar(
            node, "console.log(JSON.stringify(Math.round(595.2756 * Canvas.PX_POR_PT)));"
        )

        assert saida == 794

    def test_dimensao_negativa_e_travada_em_zero(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Geo.dimensaoValida(-5), Geo.dimensaoValida(0),"
            "Geo.dimensaoValida(13.5), Geo.dimensaoValida(NaN)]));",
        )

        assert saida == [0, 0, 13.5, 0]


# ---------------------------------------------------------------------------
# 2. Estado: elementos
# ---------------------------------------------------------------------------


class TestElementos:
    def test_todo_tipo_do_registro_produz_elemento_valido(self, node, catalogo):
        """
        Um padrão que o validador do servidor recusasse daria um elemento
        impossível de salvar assim que criado.
        """
        saida = executar(
            node,
            "console.log(JSON.stringify(CAT.map(function (t, i) {"
            "  return State.criarElemento(CAT, t.code, 'id' + i, {x: 10, y: 20});"
            "})));",
            {"CAT": catalogo},
        )

        assert len(saida) == len(elements.codigos())
        layout_schema.validate_layout({"version": 1, "elements": saida})

    def test_tipo_desconhecido_e_recusado(self, node, catalogo):
        saida = executar(
            node,
            "var erro = null;"
            "try { State.criarElemento(CAT, 'video', 'x'); } catch (e) { erro = e.message; }"
            "console.log(JSON.stringify(erro));",
            {"CAT": catalogo},
        )

        assert "video" in saida

    def test_os_padroes_vem_do_registro_do_servidor(self, node, catalogo):
        """Sem uma segunda tabela de padrões escrita em JavaScript."""
        saida = executar(
            node,
            "console.log(JSON.stringify(State.criarElemento(CAT, 'text', 'x').properties));",
            {"CAT": catalogo},
        )

        do_servidor = elements.tipo("text").padroes()
        assert set(saida) == set(do_servidor)
        assert saida["font_size"] == do_servidor["font_size"]
        assert saida["block_style"] == "p"

    def test_elementos_nao_compartilham_memoria(self, node, catalogo):
        saida = executar(
            node,
            "var a = State.criarElemento(CAT, 'text', 'a');"
            "var b = State.criarElemento(CAT, 'text', 'b');"
            "a.properties.padding.top = 99;"
            "console.log(JSON.stringify(b.properties.padding.top));",
            {"CAT": catalogo},
        )

        assert saida == 0

    def test_um_campo_dinamico_e_estrutural(self, node, catalogo):
        """
        Nunca "{{convidado.nome}}" dentro de uma string: o que se grava é
        `{kind: "field", source: ...}`.
        """
        saida = executar(
            node,
            "console.log(JSON.stringify(State.criarElementoDeCampo("
            "CAT, 'convidado.nome', 'x').properties.content));",
            {"CAT": catalogo},
        )

        assert saida == {"kind": "field", "source": "convidado.nome"}

    def test_adicionar_obter_e_remover(self, node, catalogo):
        saida = executar(
            node,
            "var l = State.layoutVazio(1);"
            "l = State.adicionar(l, State.criarElemento(CAT, 'text', 'a'), 1);"
            "l = State.adicionar(l, State.criarElemento(CAT, 'line', 'b'), 1);"
            "var achou = State.obter(l, 'a') !== null;"
            "l = State.remover(l, 'a', 1);"
            "console.log(JSON.stringify({achou: achou,"
            "  restam: l.elements.map(function (e) { return e.id; }),"
            "  sumiu: State.obter(l, 'a') === null}));",
            {"CAT": catalogo},
        )

        assert saida == {"achou": True, "restam": ["b"], "sumiu": True}

    def test_atualizar_mescla_as_propriedades(self, node, catalogo):
        """Mudar a cor não pode apagar o tamanho da fonte."""
        saida = executar(
            node,
            "var l = State.adicionar(State.layoutVazio(1),"
            "  State.criarElemento(CAT, 'text', 'a'), 1);"
            "l = State.atualizar(l, 'a', {properties: {color: '#ff0000'}}, 1);"
            "console.log(JSON.stringify(State.obter(l, 'a').properties));",
            {"CAT": catalogo},
        )

        assert saida["color"] == "#ff0000"
        assert saida["font_size"] == 11
        assert "content" in saida

    def test_atualizar_nao_troca_o_id(self, node, catalogo):
        saida = executar(
            node,
            "var l = State.adicionar(State.layoutVazio(1),"
            "  State.criarElemento(CAT, 'text', 'a'), 1);"
            "l = State.atualizar(l, 'a', {id: 'outro', x: 5}, 1);"
            "console.log(JSON.stringify(l.elements.map(function (e) {"
            "  return [e.id, e.x]; })));",
            {"CAT": catalogo},
        )

        assert saida == [["a", 5]]

    def test_mover_e_redimensionar_guardam_pontos(self, node, catalogo):
        saida = executar(
            node,
            "var l = State.adicionar(State.layoutVazio(1),"
            "  State.criarElemento(CAT, 'text', 'a'), 1);"
            "l = State.mover(l, 'a', 72.3456, 120.9876, 1);"
            "l = State.redimensionar(l, 'a', 400.125, 13.5, 1);"
            "console.log(JSON.stringify(State.obter(l, 'a')));",
            {"CAT": catalogo},
        )

        assert (saida["x"], saida["y"]) == (72.3456, 120.9876)
        assert (saida["width"], saida["height"]) == (400.125, 13.5)

    def test_duplicar_usa_o_id_do_servidor_e_desloca(self, node, catalogo):
        saida = executar(
            node,
            "var l = State.adicionar(State.layoutVazio(1),"
            "  State.criarElemento(CAT, 'text', 'a'), 1);"
            "var r = State.duplicar(l, 'a', 'vindo-do-servidor', 1);"
            "console.log(JSON.stringify({id: r.id,"
            "  ids: r.layout.elements.map(function (e) { return e.id; }),"
            "  dx: State.obter(r.layout, r.id).x - State.obter(r.layout, 'a').x}));",
            {"CAT": catalogo},
        )

        assert saida["id"] == "vindo-do-servidor"
        assert saida["ids"] == ["a", "vindo-do-servidor"]
        assert saida["dx"] == 10

    def test_duplicar_sem_id_novo_nao_faz_nada(self, node, catalogo):
        """Sem id do servidor não se inventa um no navegador."""
        saida = executar(
            node,
            "var l = State.adicionar(State.layoutVazio(1),"
            "  State.criarElemento(CAT, 'text', 'a'), 1);"
            "var r = State.duplicar(l, 'a', null, 1);"
            "console.log(JSON.stringify({id: r.id, quantos: r.layout.elements.length}));",
            {"CAT": catalogo},
        )

        assert saida == {"id": None, "quantos": 1}

    def test_as_opcoes_do_documento_sobrevivem_a_normalizacao(self, node):
        saida = executar(
            node,
            "var l = State.normalizar({version: 1, elements: [],"
            "  document: {margin: 70.87, page_numbers: true}}, 1);"
            "console.log(JSON.stringify(l.document));",
        )

        assert saida == {"margin": 70.87, "page_numbers": True}


# ---------------------------------------------------------------------------
# 3. Identificadores vindos do servidor
# ---------------------------------------------------------------------------


class TestIdentificadores:
    def test_a_fila_entrega_na_ordem_e_sem_repetir(self, node):
        saida = executar(
            node,
            "var f = State.criarFilaDeIds(['a', 'b', 'c']);"
            "var l = State.layoutVazio(1);"
            "console.log(JSON.stringify(["
            "State.proximoId(f, l), State.proximoId(f, l), State.proximoId(f, l),"
            "State.proximoId(f, l)]));",
        )

        assert saida == ["a", "b", "c", None]

    def test_um_id_ja_usado_no_layout_e_pulado(self, node, catalogo):
        saida = executar(
            node,
            "var l = State.adicionar(State.layoutVazio(1),"
            "  State.criarElemento(CAT, 'text', 'a'), 1);"
            "var f = State.criarFilaDeIds(['a', 'b']);"
            "console.log(JSON.stringify(State.proximoId(f, l)));",
            {"CAT": catalogo},
        )

        assert saida == "b"

    def test_o_javascript_nao_gera_identificadores(self):
        """
        Um gerador só para o sistema: o do servidor. Nenhum módulo pode
        inventar id com Math.random, uuid ou contador.
        """
        for arquivo in JS.glob("*.js"):
            texto_js = arquivo.read_text(encoding="utf-8")
            assert "Math.random" not in texto_js, arquivo.name
            assert "randomUUID" not in texto_js, arquivo.name

    def test_o_formato_bate_com_o_do_servico(self, node):
        do_servico = servico_de_layout.novo_id()

        assert len(do_servico) == 12
        assert do_servico.isalnum()


# ---------------------------------------------------------------------------
# 4. Camadas, imutabilidade e histórico
# ---------------------------------------------------------------------------


class TestCamadas:
    def _com_tres(self, node, corpo, catalogo):
        return executar(
            node,
            "var l = State.layoutVazio(1);"
            "['a','b','c'].forEach(function (id) {"
            "  l = State.adicionar(l, State.criarElemento(CAT, 'text', id), 1); });"
            + corpo,
            {"CAT": catalogo},
        )

    @pytest.mark.parametrize(
        "operacao, alvo, esperado",
        [
            ("trazerParaFrente", "a", ["b", "c", "a"]),
            ("enviarParaTras", "c", ["c", "a", "b"]),
            ("moverParaFrente", "a", ["b", "a", "c"]),
            ("moverParaTras", "c", ["a", "c", "b"]),
        ],
    )
    def test_as_quatro_operacoes(self, node, catalogo, operacao, alvo, esperado):
        saida = self._com_tres(
            node,
            f"l = State.{operacao}(l, '{alvo}', 1);"
            "console.log(JSON.stringify(l.elements.map(function (e) { return e.id; })));",
            catalogo,
        )

        assert saida == esperado

    def test_nenhum_elemento_tem_z_index(self, node, catalogo):
        saida = self._com_tres(
            node,
            "console.log(JSON.stringify(l.elements.map(function (e) {"
            "  return Object.prototype.hasOwnProperty.call(e, 'z_index'); })));",
            catalogo,
        )

        assert saida == [False, False, False]


class TestImutabilidade:
    @pytest.mark.parametrize(
        "operacao",
        [
            "State.adicionar(l, State.criarElemento(CAT, 'line', 'z'), 1)",
            "State.remover(l, 'a', 1)",
            "State.atualizar(l, 'a', {properties: {font_size: 20}}, 1)",
            "State.mover(l, 'a', 99, 99, 1)",
            "State.duplicar(l, 'a', 'novo', 1).layout",
            "State.trazerParaFrente(l, 'a', 1)",
            "Doc.ajustarAltura(l, 'a', 99)",
            "Doc.inserirDepois(l, 'a', State.criarElemento(CAT, 'text', 'n'))",
            "Doc.remover(l, 'a')",
            "Doc.alternarLista(l, 'a', 'numerada')",
            "Doc.dividirBloco(l, 'a', 0, 'n').layout",
            "Doc.aplicarMargem(l, PAGINA, 60)",
        ],
    )
    def test_nenhuma_operacao_altera_o_original(self, node, catalogo, operacao):
        saida = executar(
            node,
            "var l = State.layoutVazio(1);"
            "['a','b'].forEach(function (id) {"
            "  l = State.adicionar(l, State.criarElemento(CAT, 'text', id), 1); });"
            "var antes = JSON.stringify(l);"
            f"{operacao};"
            "console.log(JSON.stringify(antes === JSON.stringify(l)));",
            {"CAT": catalogo, "PAGINA": A4},
        )

        assert saida is True


class TestHistorico:
    def test_desfazer_e_refazer(self, node, catalogo):
        saida = executar(
            node,
            "var l = State.layoutVazio(1);"
            "var h = State.criarHistorico(l);"
            "h = State.registrar(h, State.adicionar(l, State.criarElemento(CAT,'text','a'), 1));"
            "var depois = State.atual(h).elements.length;"
            "h = State.desfazer(h);"
            "var desfeito = State.atual(h).elements.length;"
            "h = State.refazer(h);"
            "console.log(JSON.stringify([depois, desfeito, State.atual(h).elements.length]));",
            {"CAT": catalogo},
        )

        assert saida == [1, 0, 1]

    def test_uma_acao_nova_descarta_o_ramo_refeito(self, node, catalogo):
        saida = executar(
            node,
            "var l = State.layoutVazio(1);"
            "var h = State.criarHistorico(l);"
            "h = State.registrar(h, State.adicionar(l, State.criarElemento(CAT,'text','a'), 1));"
            "h = State.registrar(h, State.adicionar(State.atual(h),"
            "  State.criarElemento(CAT,'line','b'), 1));"
            "h = State.desfazer(h);"
            "h = State.registrar(h, State.adicionar(State.atual(h),"
            "  State.criarElemento(CAT,'rectangle','c'), 1));"
            "console.log(JSON.stringify({pode: State.podeRefazer(h),"
            "  ids: State.atual(h).elements.map(function (e) { return e.id; })}));",
            {"CAT": catalogo},
        )

        assert saida["pode"] is False
        assert saida["ids"] == ["a", "c"]

    def test_substituir_junta_teclas_no_mesmo_passo(self, node, catalogo):
        """
        Digitar "abc" é um passo de desfazer, não três: `substituir`
        troca o estado atual em vez de empilhar outro.
        """
        saida = executar(
            node,
            "var l = State.layoutVazio(1);"
            "var h = State.criarHistorico(l);"
            "h = State.registrar(h, State.adicionar(l, State.criarElemento(CAT,'text','a'), 1));"
            "h = State.substituir(h, State.atualizar(State.atual(h), 'a', {x: 1}, 1));"
            "h = State.substituir(h, State.atualizar(State.atual(h), 'a', {x: 2}, 1));"
            "var x = State.obter(State.atual(h), 'a').x;"
            "h = State.desfazer(h);"
            "console.log(JSON.stringify({passos: h.estados.length, x: x,"
            "  depois: State.atual(h).elements.length}));",
            {"CAT": catalogo},
        )

        assert saida == {"passos": 2, "x": 2, "depois": 0}


# ---------------------------------------------------------------------------
# 5. Trechos: o conteúdo estrutural ida e volta do DOM
# ---------------------------------------------------------------------------

MISTO = {
    "kind": "mixed",
    "parts": [
        texto("Je soussigné "),
        campo("anfitriao.nome", font_weight="bold"),
        texto(", né le\nlinha 2", color="#cc0000", font_size=14),
    ],
}


class TestTrechos:
    def test_ida_e_volta_pelo_dom_devolve_o_mesmo_conteudo(self, node):
        saida = executar(
            node,
            "var alvo = dom.createElement('div');"
            "Runs.desenhar(dom, alvo, BLOCO, {rotulos: {'anfitriao.nome': 'Anfitrião · Nome'},"
            "  escala: 1.2});"
            "console.log(JSON.stringify({tela: alvo.textContent,"
            "  volta: Runs.blocoDe(Runs.serializar(alvo, {escala: 1.2}))}));",
            {"BLOCO": MISTO},
        )

        assert saida["tela"] == "Je soussigné [Anfitrião · Nome], né lelinha 2"
        assert saida["volta"] == MISTO
        layout_schema.validar_conteudo(saida["volta"], "c", permite_misto=True)

    def test_com_dados_de_exemplo_o_chip_mostra_o_valor_e_continua_campo(self, node):
        saida = executar(
            node,
            "var alvo = dom.createElement('div');"
            "Runs.desenhar(dom, alvo, BLOCO, {rotulos: {}, exemplo: {'anfitriao.nome': 'Claire'},"
            "  escala: 1});"
            "console.log(JSON.stringify({tela: alvo.textContent,"
            "  campos: Runs.serializar(alvo, {}).filter(function (t) {"
            "    return t.kind === 'field'; }).map(function (t) { return t.source; })}));",
            {"BLOCO": MISTO},
        )

        assert "Claire" in saida["tela"]
        assert saida["campos"] == ["anfitriao.nome"]

    def test_o_que_o_navegador_produz_ao_formatar_e_lido(self, node):
        """<b>, <i>, <u>, <strike>, <font>, <a>, span com estilo, <br>."""
        saida = executar(
            node,
            "var raiz = dom.createElement('div');"
            "var b = dom.createElement('b'); b.textContent = 'forte'; raiz.appendChild(b);"
            "var i = dom.createElement('i'); i.textContent = ' curvo'; raiz.appendChild(i);"
            "var u = dom.createElement('u'); u.textContent = ' sub'; raiz.appendChild(u);"
            "var s = dom.createElement('strike'); s.textContent = ' riscado'; raiz.appendChild(s);"
            "var f = dom.createElement('font'); f.setAttribute('color', 'rgb(180, 38, 42)');"
            "f.setAttribute('size', '5'); f.textContent = ' grande'; raiz.appendChild(f);"
            "var a = dom.createElement('a'); a.setAttribute('href', 'https://exemplo.be');"
            "a.textContent = ' link'; raiz.appendChild(a);"
            "var sp = dom.createElement('span'); sp.style.backgroundColor = 'rgb(255, 246, 201)';"
            "sp.style.fontFamily = '\"Times New Roman\", serif'; sp.textContent = ' realce';"
            "raiz.appendChild(sp);"
            "raiz.appendChild(dom.createElement('br'));"
            "raiz.appendChild(dom.createTextNode('nova linha'));"
            "console.log(JSON.stringify(Runs.serializar(raiz, {escala: 1})));",
        )

        assert saida == [
            texto("forte", font_weight="bold"),
            texto(" curvo", font_style="italic"),
            texto(" sub", text_decoration="underline"),
            texto(" riscado", text_decoration="line-through"),
            texto(" grande", font_size=14, color="#b4262a"),
            texto(" link", link="https://exemplo.be"),
            texto(" realce", highlight="#fff6c9", font_family="Times"),
            texto("\nnova linha"),
        ]
        layout_schema.validar_conteudo(
            {"kind": "mixed", "parts": saida}, "c", permite_misto=True
        )

    @pytest.mark.parametrize(
        "href", ["javascript:alert(1)", "java\nscript:alert(1)", "data:text/html,x", "/relativo"]
    )
    def test_um_link_perigoso_ou_relativo_vira_texto_sem_link(self, node, href):
        saida = executar(
            node,
            "var raiz = dom.createElement('div');"
            "var a = dom.createElement('a'); a.setAttribute('href', HREF);"
            "a.textContent = 'clique'; raiz.appendChild(a);"
            "console.log(JSON.stringify(Runs.serializar(raiz, {})));",
            {"HREF": href},
        )

        assert saida == [texto("clique")]

    def test_o_br_final_do_navegador_nao_e_conteudo(self, node):
        saida = executar(
            node,
            "var raiz = dom.createElement('div');"
            "raiz.appendChild(dom.createTextNode('fim'));"
            "raiz.appendChild(dom.createElement('br'));"
            "console.log(JSON.stringify(Runs.serializar(raiz, {})));",
        )

        assert saida == [texto("fim")]

    def test_estilo_igual_ao_do_elemento_nao_e_repetido_no_trecho(self, node):
        saida = executar(
            node,
            "var raiz = dom.createElement('div');"
            "var b = dom.createElement('b'); b.textContent = 'ja era negrito'; raiz.appendChild(b);"
            "console.log(JSON.stringify(Runs.serializar(raiz, {base: {font_weight: 'bold'}})));",
        )

        assert saida == [texto("ja era negrito")]

    def test_texto_com_marcacao_colada_e_texto(self, node):
        """Um `<script>` escrito no bloco é o TEXTO "<script>" -- e o
        próprio elemento script, se aparecer no DOM, é ignorado."""
        saida = executar(
            node,
            "var raiz = dom.createElement('div');"
            "raiz.appendChild(dom.createTextNode('<script>alert(1)</script>'));"
            "var sc = dom.createElement('script'); sc.textContent = 'alert(2)';"
            "raiz.appendChild(sc);"
            "console.log(JSON.stringify(Runs.serializar(raiz, {})));",
        )

        assert saida == [texto("<script>alert(1)</script>")]

    def test_dividir_e_juntar_sao_inversas(self, node):
        saida = executar(
            node,
            "var t = Runs.trechosDe(BLOCO);"
            "var d = Runs.dividir(t, 14);"
            "console.log(JSON.stringify({comprimento: Runs.comprimento(t), antes: d[0],"
            "  depois: d[1], junto: Runs.blocoDe(Runs.juntar(d[0], d[1]))}));",
            {"BLOCO": MISTO},
        )

        # 13 letras + 1 posição do campo = 14
        assert saida["comprimento"] == 13 + 1 + len(", né le\nlinha 2")
        assert saida["antes"] == [
            texto("Je soussigné "), campo("anfitriao.nome", font_weight="bold"),
        ]
        assert saida["depois"] == [texto(", né le\nlinha 2", color="#cc0000", font_size=14)]
        assert saida["junto"] == MISTO

    def test_um_campo_e_indivisivel(self, node):
        saida = executar(
            node,
            "var t = [Runs.texto('ab'), Runs.campo('convidado.nome'), Runs.texto('cd')];"
            "console.log(JSON.stringify([Runs.dividir(t, 2), Runs.dividir(t, 3)]));",
        )

        assert saida[0] == [[texto("ab")], [campo("convidado.nome"), texto("cd")]]
        assert saida[1] == [[texto("ab"), campo("convidado.nome")], [texto("cd")]]

    def test_aplicar_estilo_num_intervalo_nao_toca_no_resto(self, node):
        saida = executar(
            node,
            "var t = [Runs.texto('Je soussigné ')];"
            "console.log(JSON.stringify(Runs.aplicarEstilo(t, 3, 9, {color: '#cc0000'})));",
        )

        assert saida == [
            texto("Je "), texto("soussi", color="#cc0000"), texto("gné "),
        ]

    def test_limpar_estilo_deixa_so_texto_e_campos(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(Runs.blocoDe(Runs.limparEstilo(Runs.trechosDe(BLOCO)))));",
            {"BLOCO": MISTO},
        )

        assert saida == {
            "kind": "mixed",
            "parts": [texto("Je soussigné "), campo("anfitriao.nome"), texto(", né le\nlinha 2")],
        }

    def test_bloco_de_normaliza_para_a_forma_mais_simples(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Runs.blocoDe([Runs.texto('a'), Runs.texto('b')]),"
            "Runs.blocoDe([Runs.campo('convidado.nome')]),"
            "Runs.blocoDe([]),"
            "Runs.blocoDe([Runs.texto('a', {font_weight: 'bold'})])]));",
        )

        assert saida == [
            texto("ab"), campo("convidado.nome"), texto(""),
            {"kind": "mixed", "parts": [texto("a", font_weight="bold")]},
        ]

    def test_cores_e_familias_do_navegador_viram_o_vocabulario_do_layout(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Runs.normalizarCor('rgb(21, 24, 31)'), Runs.normalizarCor('#abc'),"
            "Runs.normalizarCor('rgba(0, 0, 0, 0)'), Runs.normalizarCor('red'),"
            "Runs.familiaDeCss('\"Times New Roman\", serif'), Runs.familiaDeCss('Courier New'),"
            "Runs.familiaDeCss('Arial'), Runs.tamanhoDeFont('4')]));",
        )

        assert saida == ["#15181f", "#aabbcc", None, None, "Times", "Courier", "LiberationSans", 12]

    def test_as_familias_do_editor_sao_as_do_registro(self, node):
        saida = executar(node, "console.log(JSON.stringify(Object.keys(Runs.FAMILIAS_CSS)));")

        assert set(saida) == set(elements.FONT_FAMILIES)

    def test_as_chaves_de_estilo_sao_as_do_contrato(self, node):
        saida = executar(node, "console.log(JSON.stringify(Runs.ESTILOS));")

        assert set(saida) == set(layout_schema.ESTILO_DO_TRECHO)


# ---------------------------------------------------------------------------
# 6. Documento: refluxo, blocos, listas, margens, faixa, páginas
# ---------------------------------------------------------------------------

TRES = layout(
    bloco_de_texto("a", 100.0, "um"),
    bloco_de_texto("m", 120.0, "1.", x=30.0, largura=15.0),
    bloco_de_texto("b", 120.0, "dois"),
    bloco_de_texto("c", 140.0, "tres"),
)


def _doc(node, corpo, extras=None):
    return executar(
        node, "var L = LAYOUT;" + corpo, {"LAYOUT": TRES, "PAGINA": A4, **(extras or {})}
    )


class TestRefluxo:
    def test_um_bloco_que_cresce_empurra_o_que_esta_abaixo(self, node):
        saida = _doc(
            node,
            "var l = Doc.ajustarAltura(L, 'a', 27);"
            "console.log(JSON.stringify(l.elements.map(function (e) { return [e.id, e.y, "
            "e.height]; })));",
        )

        assert saida == [
            ["a", 100.0, 27], ["m", 133.5, 13.5], ["b", 133.5, 13.5], ["c", 153.5, 13.5],
        ]
        layout_schema.validate_layout(
            _doc(node, "console.log(JSON.stringify(Doc.ajustarAltura(L, 'a', 27)));")
        )

    def test_o_que_esta_ao_lado_nao_se_mexe(self, node):
        """O marcador "1." ao lado do item b não desce quando b cresce."""
        saida = _doc(
            node,
            "var l = Doc.ajustarAltura(L, 'b', 40);"
            "console.log(JSON.stringify([State.obter(l, 'm').y, State.obter(l, 'c').y]));",
        )

        assert saida == [120.0, 166.5]

    def test_encolher_puxa_o_que_esta_abaixo(self, node):
        saida = _doc(
            node,
            "var l = Doc.ajustarAltura(L, 'a', 7);"
            "console.log(JSON.stringify(State.obter(l, 'b').y));",
        )

        assert saida == 113.5

    def test_meio_ponto_nao_e_mudanca(self, node):
        saida = _doc(node, "console.log(JSON.stringify(Doc.ajustarAltura(L, 'a', 13.8) === L));")

        assert saida is True

    def test_inserir_depois_abre_espaco(self, node):
        saida = _doc(
            node,
            "var novo = Doc.novoBlocoDeTexto('n', State.obter(L, 'a'), {kind: 'text', value: "
            "'novo'});"
            "var l = Doc.inserirDepois(L, 'a', novo);"
            "console.log(JSON.stringify({novo: State.obter(l, 'n'), b: State.obter(l, 'b').y, l: "
            "l}));",
        )

        assert saida["novo"]["y"] == 100.0 + 13.5 + 6
        assert saida["novo"]["x"] == 50.0
        assert saida["novo"]["width"] == 400.0
        assert saida["b"] == 120.0 + saida["novo"]["height"] + 6
        layout_schema.validate_layout(saida["l"])

    def test_remover_fecha_o_buraco(self, node):
        saida = _doc(
            node,
            "var l = Doc.remover(L, 'a');"
            "console.log(JSON.stringify(l.elements.map(function (e) { return [e.id, e.y]; })));",
        )

        assert saida == [["m", 100.0], ["b", 100.0], ["c", 120.0]]


class TestBlocos:
    def test_dividir_no_cursor_cria_o_bloco_de_baixo(self, node):
        saida = _doc(
            node,
            "var r = Doc.dividirBloco(L, 'b', 2, 'n');"
            "console.log(JSON.stringify({id: r.id,"
            "  b: State.obter(r.layout, 'b').properties.content,"
            "  n: State.obter(r.layout, 'n'), c: State.obter(r.layout, 'c').y, l: r.layout}));",
        )

        assert saida["id"] == "n"
        assert saida["b"] == texto("do")
        assert saida["n"]["properties"]["content"] == texto("is")
        assert saida["n"]["y"] == 133.5
        assert saida["c"] > 140.0
        layout_schema.validate_layout(saida["l"])

    def test_dividir_um_item_numerado_continua_a_lista(self, node):
        saida = _doc(
            node,
            "var l = Doc.alternarLista(L, 'a', 'numerada');"
            "var r = Doc.dividirBloco(l, 'a', 1, 'n');"
            "console.log(JSON.stringify([State.obter(r.layout, 'a').properties.list_marker,"
            "  State.obter(r.layout, 'n').properties.list_marker]));",
        )

        assert saida == ["1.", "2."]

    def test_juntar_com_o_anterior_leva_o_texto_e_o_cursor(self, node):
        saida = _doc(
            node,
            "var r = Doc.juntarComAnterior(L, 'c');"
            "console.log(JSON.stringify({id: r.id, posicao: r.posicao,"
            "  b: State.obter(r.layout, 'b').properties.content,"
            "  sumiu: State.obter(r.layout, 'c') === null}));",
        )

        assert saida == {"id": "b", "posicao": 4, "b": texto("doistres"), "sumiu": True}

    def test_gravar_conteudo_misto_num_text_o_promove_a_rich_text(self, node):
        saida = _doc(
            node,
            "var l = Doc.gravarConteudo(L, 'a', [Runs.texto('x'), Runs.campo('convidado.nome')]);"
            "console.log(JSON.stringify({tipo: State.obter(l, 'a').type, l: l}));",
        )

        assert saida["tipo"] == "rich_text"
        layout_schema.validate_layout(saida["l"])

    def test_estilo_do_bloco(self, node):
        saida = _doc(
            node,
            "var l = Doc.aplicarEstiloDoBloco(L, 'a', 'h1');"
            "var p = State.obter(l, 'a').properties;"
            "var antigo = {properties: {font_size: 14, font_weight: 'bold', align: 'center'}};"
            "console.log(JSON.stringify({p: [p.font_size, p.font_weight, p.align, p.block_style],"
            "  lido: Doc.estiloDoBloco(State.obter(l, 'a')), antigo: Doc.estiloDoBloco(antigo),"
            "  volta: Doc.estiloDoBloco(State.obter(Doc.aplicarEstiloDoBloco(l, 'a', 'p'), 'a')), "
            "l: l}));",
        )

        assert saida["p"] == [14, "bold", "center", "h1"]
        assert saida["lido"] == "h1"
        assert saida["antigo"] == "h1"
        assert saida["volta"] == "p"
        layout_schema.validate_layout(saida["l"])


class TestListas:
    def test_ligar_e_desligar_a_lista(self, node):
        saida = _doc(
            node,
            "var l = Doc.alternarLista(L, 'a', 'marcadores');"
            "var p = State.obter(l, 'a').properties;"
            "var d = State.obter(Doc.alternarLista(l, 'a', 'marcadores'), 'a').properties;"
            "console.log(JSON.stringify([[p.list_marker, p.indent], [d.list_marker, d.indent], "
            "l]));",
        )

        assert saida[0] == ["•", 18]
        assert saida[1] == ["", 0]
        layout_schema.validate_layout(saida[2])

    def test_a_numeracao_segue_a_ordem_de_leitura(self, node):
        saida = _doc(
            node,
            "var l = L;"
            "['c', 'a', 'b'].forEach(function (id) { l = Doc.alternarLista(l, id, 'numerada'); });"
            "console.log(JSON.stringify(['a', 'b', 'c'].map(function (id) {"
            "  return State.obter(l, id).properties.list_marker; })));",
        )

        assert saida == ["1.", "2.", "3."]

    def test_um_bloco_de_outra_coluna_nao_interrompe_a_sequencia(self, node):
        """O "1." solto de um documento antigo, em x=30, fica de fora."""
        saida = _doc(
            node,
            "var l = Doc.alternarLista(Doc.alternarLista(L, 'a', 'numerada'), 'b', 'numerada');"
            "console.log(JSON.stringify([State.obter(l, 'a').properties.list_marker,"
            "  State.obter(l, 'b').properties.list_marker,"
            "  State.obter(l, 'm').properties.list_marker || '']));",
        )

        assert saida == ["1.", "2.", ""]

    def test_remover_um_item_renumera(self, node):
        saida = _doc(
            node,
            "var l = L;"
            "['a', 'b', 'c'].forEach(function (id) { l = Doc.alternarLista(l, id, 'numerada'); });"
            "l = Doc.renumerar(Doc.remover(l, 'a'));"
            "console.log(JSON.stringify([State.obter(l, 'b').properties.list_marker,"
            "  State.obter(l, 'c').properties.list_marker]));",
        )

        assert saida == ["1.", "2."]

    def test_o_recuo_nunca_engole_a_caixa(self, node):
        """
        Um bloco estreito (o marcador "2." do documento oficial tem 18pt)
        não pode receber um recuo de 18pt: o texto ficaria sem largura e
        o renderer não desenharia nada. O editor não chega a gravar
        isso; o renderer tem a mesma guarda, do outro lado.
        """
        estreito = bloco_de_texto("estreito", 100.0, "2.", largura=18.0)

        saida = executar(
            node,
            "var l = Doc.alternarLista({version: 1, elements: [EL]}, 'estreito', 'numerada');"
            "var recuado = Doc.recuar(l, 'estreito', 3);"
            "console.log(JSON.stringify({"
            "  lista: State.obter(l, 'estreito').properties.indent,"
            "  recuado: State.obter(recuado, 'estreito').properties.indent,"
            "  marcador: State.obter(l, 'estreito').properties.list_marker}));",
            {"EL": estreito},
        )

        assert saida["lista"] == 6
        assert saida["recuado"] == 6
        assert saida["marcador"] == "1."

    def test_recuo_em_passos_e_nunca_negativo(self, node):
        saida = _doc(
            node,
            "var l = Doc.recuar(Doc.recuar(L, 'a', 1), 'a', 1);"
            "var dois = State.obter(l, 'a').properties.indent;"
            "var zero = State.obter(Doc.recuar(Doc.recuar(Doc.recuar(l, 'a', -1), 'a', -1), 'a', "
            "-1), 'a').properties.indent;"
            "console.log(JSON.stringify([dois, zero]));",
        )

        assert saida == [36, 0]


class TestMargensFaixaEPaginas:
    def test_a_margem_e_lida_do_documento_ou_deduzida(self, node):
        saida = _doc(
            node,
            "console.log(JSON.stringify([Doc.margem(L),"
            "  Doc.margem(Doc.comOpcoes(L, {margin: 70.87}))]));",
        )

        assert saida == [30.0, 70.87]

    def test_trocar_a_margem_desliza_e_encolhe_quem_encosta(self, node):
        cheio = layout(
            bloco_de_texto("t", 60.0, x=49.6, largura=595.2756 - 2 * 49.6),
            bloco_de_texto("meio", 90.0, x=85.6, largura=100.0),
        )
        saida = executar(
            node,
            "var l = Doc.aplicarMargem(L, PAGINA, 70.87);"
            "console.log(JSON.stringify({t: State.obter(l, 't'), meio: State.obter(l, 'meio'),"
            "  margem: Doc.margem(l), l: l}));",
            {"L": cheio, "PAGINA": A4},
        )

        assert saida["t"]["x"] == pytest.approx(70.87)
        assert saida["t"]["y"] == pytest.approx(60.0 + 70.87 - 49.6)
        assert saida["t"]["width"] == pytest.approx(595.2756 - 2 * 70.87)
        assert saida["meio"]["x"] == pytest.approx(85.6 + 70.87 - 49.6)
        assert saida["meio"]["width"] == 100.0
        assert saida["margem"] == 70.87
        layout_schema.validate_layout(saida["l"])

    def test_a_faixa_e_reconhecida_pelo_desenho_e_ligada_ou_desligada(self, node):
        medidas = {"x": 168.7224, "width": 258.0, "height": 5.25,
                   "colors": ["#000000", "#FFD966", "#FF0000"]}
        saida = _doc(
            node,
            "var com = Doc.alternarFaixa(L, true, MEDIDAS, ['f0', 'f1', 'f2']);"
            "var sem = Doc.alternarFaixa(com, false, MEDIDAS, []);"
            "console.log(JSON.stringify({antes: Doc.faixa(L, MEDIDAS.colors),"
            "  ids: Doc.faixa(com, MEDIDAS.colors), primeiro: com.elements[0].id,"
            "  depois: Doc.faixa(sem, MEDIDAS.colors), quantos: sem.elements.length, com: com}));",
            {"MEDIDAS": medidas},
        )

        assert saida["antes"] == []
        assert saida["ids"] == ["f0", "f1", "f2"]
        assert saida["primeiro"] == "f0"
        assert saida["depois"] == []
        assert saida["quantos"] == 4
        layout_schema.validate_layout(saida["com"])

    def test_a_quebra_de_pagina_manda_o_resto_para_a_pagina_seguinte(self, node):
        saida = _doc(
            node,
            "var l = Doc.inserirQuebra(L, 'a', 'q', PAGINA, 70);"
            "var b = State.obter(l, 'b');"
            "console.log(JSON.stringify({paginas: Doc.totalDePaginas(l), b: b.y,"
            "  paginaDeB: Doc.paginaDe(l, b), paginaDeA: Doc.paginaDe(l, State.obter(l, 'a')),"
            "  quebra: State.obter(l, 'q'), l: l}));",
        )

        assert saida["paginas"] == 2
        assert saida["b"] == pytest.approx(841.8898 + 70)
        assert saida["paginaDeB"] == 1
        assert saida["paginaDeA"] == 0
        assert saida["quebra"]["type"] == "page_break"
        assert saida["quebra"]["width"] == pytest.approx(595.2756)
        layout_schema.validate_layout(saida["l"])

    def test_remover_a_quebra_traz_o_resto_de_volta(self, node):
        saida = _doc(
            node,
            "var l = Doc.removerQuebra(Doc.inserirQuebra(L, 'a', 'q', PAGINA, 70), 'q');"
            "console.log(JSON.stringify({paginas: Doc.totalDePaginas(l),"
            "  b: State.obter(l, 'b').y, c: State.obter(l, 'c').y}));",
        )

        assert saida["paginas"] == 1
        assert saida["b"] == pytest.approx(100.0 + 13.5 + 6, abs=0.02)
        assert saida["c"] - saida["b"] == pytest.approx(20.0)

    def test_a_regra_de_pagina_e_a_do_renderer(self, node):
        """
        Mesma conta no navegador e em `services.pdf.distribuir_por_pagina`:
        um elemento cai na página k quando há k quebras acima dele.
        """
        from apps.doctemplates.services import pdf

        documento = _doc(
            node,
            "console.log(JSON.stringify(Doc.inserirQuebra(Doc.inserirQuebra(L, 'a', 'q1', PAGINA, "
            "70),"
            "  'b', 'q2', PAGINA, 70)));",
        )
        do_js = _doc(
            node,
            "console.log(JSON.stringify(L.elements.map(function (e) {"
            "  return [e.id, Doc.paginaDe(L, e)]; })));",
            {"LAYOUT": documento},
        )

        paginas = pdf.distribuir_por_pagina(documento, A4["height"])
        do_python = {
            e["id"]: indice for indice, (_d, nesta) in enumerate(paginas) for e in nesta
        }
        assert dict(do_js) == do_python
        assert len(paginas) == 3


class TestCamposUsados:
    def test_conta_cada_ocorrencia_e_lista_cada_campo_uma_vez(self, node):
        documento = layout(
            {"id": "r", "type": "rich_text", "x": 0, "y": 0, "width": 100, "height": 10,
             "properties": {"content": MISTO}},
            {"id": "t", "type": "table", "x": 0, "y": 20, "width": 100, "height": 10,
             "properties": {"columns": [{"width": 50}], "rows": [{"min_height": 10, "cells": [
                 {"content": campo("anfitriao.nome")}]}]}},
            {"id": "q", "type": "qr_code", "x": 0, "y": 40, "width": 10, "height": 10,
             "properties": {"source": campo("convidado.nome")}},
        )
        saida = executar(
            node, "console.log(JSON.stringify(Doc.usosDeCampos(L)));", {"L": documento}
        )

        assert saida == {
            "total": 3,
            "porReferencia": {"anfitriao.nome": 2, "convidado.nome": 1},
            "ordem": ["anfitriao.nome", "convidado.nome"],
        }
        assert set(saida["porReferencia"]) == layout_schema.referencias_usadas(documento)

    def test_as_linhas_visuais_agrupam_o_que_esta_lado_a_lado(self, node):
        saida = _doc(
            node,
            "console.log(JSON.stringify(Doc.linhasVisuais(L).map(function (linha) {"
            "  return linha.elementos.map(function (e) { return e.id; }); })));",
        )

        assert saida == [["a"], ["m", "b"], ["c"]]

    def test_meio_ponto_de_sobra_entre_duas_linhas_nao_e_lado_a_lado(self, node):
        """Duas linhas medidas a 13,5pt de passo com caixas de 13,5pt +
        ascent: o pé de uma passa 0,5pt do topo da seguinte."""
        documento = layout(
            bloco_de_texto("um", 361.1, altura=13.5),
            bloco_de_texto("dois", 374.1, altura=13.5),
        )
        saida = executar(
            node,
            "console.log(JSON.stringify(Doc.linhasVisuais(L).length));", {"L": documento},
        )

        assert saida == 2


# ---------------------------------------------------------------------------
# 7. Canvas
# ---------------------------------------------------------------------------


class TestCanvas:
    def _desenhar(self, node, elementos, extras="", opcoes=None):
        o = {"escala": 1, "campos": {}, "assets": [], "selecionado": None, "editavel": True}
        o.update(opcoes or {})
        return executar(
            node,
            "var alvo = dom.createElement('div');"
            "var campos = Canvas.indiceDeCampos(FONTES);"
            "var opcoes = OPCOES; opcoes.campos = campos; opcoes.pagina = PAGINA;"
            "Canvas.desenharLayout(dom, alvo, {version: 1, elements: ELS}, opcoes);"
            "var camada = {children: []};"
            "alvo.children.forEach(function (folha) {"
            "  camada.children = camada.children.concat(folha.children[0].children); });"
            + extras +
            "console.log(JSON.stringify(camada.children.map(function (n) {"
            "  return {id: n.dataset.id, tipo: n.dataset.tipo,"
            "    left: parseFloat(n.style.left), top: parseFloat(n.style.top),"
            "    width: parseFloat(n.style.width), classes: n.classList._classes,"
            "    texto: n.textContent};"
            "})));",
            {"ELS": elementos, "FONTES": FONTES, "OPCOES": o, "PAGINA": A4},
        )

    def test_todos_os_tipos_sao_desenhados(self, node, catalogo):
        elementos = executar(
            node,
            "console.log(JSON.stringify(CAT.map(function (t, i) {"
            "  return State.criarElemento(CAT, t.code, 'id' + i, {x: 10, y: 20}); })));",
            {"CAT": catalogo},
        )

        desenhados = self._desenhar(node, elementos)

        assert {n["tipo"] for n in desenhados} == set(elements.codigos())
        for no in desenhados:
            assert no["texto"] != no["tipo"], no["tipo"]

    def test_as_coordenadas_viram_posicao_na_tela(self, node):
        no = self._desenhar(node, [bloco_de_texto("a", 120.9876, x=72.3456, largura=400.125)])[0]

        assert no["left"] == pytest.approx(72.3456)
        assert no["top"] == pytest.approx(120.9876)
        assert no["width"] == pytest.approx(400.125)

    def test_a_escala_multiplica_a_geometria(self, node):
        no = self._desenhar(
            node, [bloco_de_texto("a", 100.0, x=50.0, largura=200.0)], opcoes={"escala": 0.5}
        )[0]

        assert (no["left"], no["top"], no["width"]) == (25, 50, 100)

    def test_um_campo_aparece_com_rotulo_legivel(self, node):
        elemento = bloco_de_texto("a", 0)
        elemento["properties"]["content"] = campo("convidado.nome")

        no = self._desenhar(node, [elemento])[0]

        assert no["texto"] == "[Convidado · Nome completo]"

    def test_um_campo_sem_referencia_e_sinalizado(self, node):
        elemento = bloco_de_texto("a", 0)
        elemento["properties"]["content"] = campo("")

        no = self._desenhar(node, [elemento])[0]

        assert "is-incompleto" in no["classes"]

    def test_o_marcador_de_lista_e_desenhado_fora_do_bloco_editavel(self, node):
        elemento = bloco_de_texto("a", 0, "item", list_marker="2.", indent=18)

        saida = executar(
            node,
            "var alvo = dom.createElement('div');"
            f"Canvas.desenharLayout(dom, alvo, {{version: 1, elements: [{json.dumps(elemento)}]}},"
            "  {escala: 1, campos: {}, assets: [], editavel: true, pagina: PAGINA});"
            "var no = alvo.children[0].children[0].children[0];"
            "var marcador = dom.porClasse(no, 'te-marcador')[0];"
            "var bloco = dom.porClasse(no, 'te-bloco')[0];"
            "console.log(JSON.stringify({marcador: marcador.textContent,"
            "  editavel: marcador.getAttribute('contenteditable'),"
            "  bloco: bloco.textContent, recuo: bloco.style.paddingLeft}));",
            {"PAGINA": A4},
        )

        assert saida == {"marcador": "2.", "editavel": "false", "bloco": "item", "recuo": "18px"}

    def test_o_bloco_e_editavel_so_em_edicao(self, node):
        elemento = bloco_de_texto("a", 0)
        for editavel in (True, False):
            saida = executar(
                node,
                "var alvo = dom.createElement('div');"
                "Canvas.desenharLayout(dom, alvo, {version: 1, elements: [EL]},"
                "  {escala: 1, campos: {}, assets: [], editavel: EDITAVEL, pagina: PAGINA});"
                "console.log(JSON.stringify(dom.porClasse(alvo, "
                "'te-bloco')[0].getAttribute('contenteditable')));",
                {"PAGINA": A4, "EL": elemento, "EDITAVEL": editavel},
            )
            assert saida == ("true" if editavel else "false")

    def test_a_quebra_de_pagina_abre_uma_segunda_folha(self, node):
        documento = _doc(
            node, "console.log(JSON.stringify(Doc.inserirQuebra(L, 'a', 'q', PAGINA, 70)));"
        )
        saida = executar(
            node,
            "var alvo = dom.createElement('div');"
            "Canvas.desenharLayout(dom, alvo, L, {escala: 1, campos: {}, assets: [],"
            "  editavel: true, pagina: PAGINA});"
            "console.log(JSON.stringify(alvo.children.map(function (folha) {"
            "  return folha.children[0].children.map(function (n) {"
            "    return [n.dataset.id, parseFloat(n.style.top)]; }); })));",
            {"L": documento, "PAGINA": A4},
        )

        assert len(saida) == 2
        assert saida[0][0] == ["a", 100.0]
        assert ["q", pytest.approx(113.51, abs=0.01)] in saida[0]
        assert saida[1][0] == ["m", pytest.approx(70.0)]

    def test_o_selecionado_grafico_ganha_marca_e_alcas(self, node):
        elementos = [
            {"id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10,
             "properties": {"border_width": 1}}
        ]

        saida = executar(
            node,
            "var alvo = dom.createElement('div');"
            f"Canvas.desenharLayout(dom, alvo, {{version: 1, elements: {json.dumps(elementos)}}},"
            "{escala: 1, campos: {}, assets: [], selecionado: 'a', editavel: true, pagina: "
            "PAGINA});"
            "var no = alvo.children[0].children[0].children[0];"
            "console.log(JSON.stringify({classes: no.classList._classes,"
            "  alcas: dom.porClasse(no, 'te-alca').length}));",
            {"PAGINA": A4},
        )

        assert "is-selecionado" in saida["classes"]
        assert saida["alcas"] == 8

    def test_a_tabela_desenha_celulas_editaveis(self, node):
        elemento = {
            "id": "t", "type": "table", "x": 0, "y": 0, "width": 300, "height": 40,
            "properties": {
                "columns": [{"width": 100}, {"width": 200}],
                "rows": [{"min_height": 18, "cells": [
                    {"content": texto("Nome :"), "bold": True},
                    {"content": campo("convidado.nome")},
                ]}],
                "font_size": 11, "line_height": 1.2,
            },
        }

        saida = executar(
            node,
            "var alvo = dom.createElement('div');"
            f"Canvas.desenharLayout(dom, alvo, {{version: 1, elements: [{json.dumps(elemento)}]}},"
            "{escala: 2, campos: Canvas.indiceDeCampos(FONTES), assets: [], editavel: true,"
            "  pagina: PAGINA});"
            "var celulas = dom.porClasse(alvo, 'te-celula');"
            "console.log(JSON.stringify(celulas.map(function (c) {"
            "  return {texto: c.textContent, linha: c.dataset.linha, celula: c.dataset.celula,"
            "    editavel: c.getAttribute('contenteditable'), fontSize: c.style.fontSize,"
            "    peso: c.style.fontWeight, fonte: c.style.fontFamily}; })));",
            {"FONTES": FONTES, "PAGINA": A4},
        )

        assert [c["texto"] for c in saida] == ["Nome :", "[Convidado · Nome completo]"]
        assert [(c["linha"], c["celula"]) for c in saida] == [("0", "0"), ("0", "1")]
        assert all(c["editavel"] == "true" for c in saida)
        assert saida[0]["fontSize"] == "22px"
        assert saida[0]["peso"] == "700"
        assert "Liberation Sans" in saida[0]["fonte"]

    def test_o_modo_fluxo_agrupa_em_linhas_de_leitura(self, node):
        saida = executar(
            node,
            "var alvo = dom.createElement('div');"
            "Canvas.desenharLayout(dom, alvo, L, {escala: 1.4, campos: {}, assets: [],"
            "  editavel: true, pagina: PAGINA, modo: 'fluxo'});"
            "console.log(JSON.stringify(alvo.children.map(function (linha) {"
            "  return linha.children.map(function (n) { return [n.dataset.id, n.style.position]; "
            "});"
            "})));",
            {"L": TRES, "PAGINA": A4},
        )

        assert saida == [
            [["a", "relative"]], [["m", "relative"], ["b", "relative"]], [["c", "relative"]],
        ]

    def test_o_estilo_de_texto_acompanha_a_escala(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Canvas.estiloDeTexto({font_size: 11}, 1).fontSize,"
            "Canvas.estiloDeTexto({font_size: 11}, 2).fontSize,"
            "Canvas.estiloDeTexto({font_weight: 'bold'}, 1).fontWeight,"
            "Canvas.estiloDeTexto({font_family: 'Times'}, 1).fontFamily]));",
        )

        assert saida[:3] == ["11px", "22px", "700"]
        assert "Times" in saida[3]


# ---------------------------------------------------------------------------
# 8. Painéis
# ---------------------------------------------------------------------------


class TestPaineis:
    def test_os_campos_do_banco_vem_do_registro_com_a_cor_do_grupo(self, node):
        saida = executar(
            node,
            "var alvo = dom.createElement('div');"
            "Panels.montarCampos(dom, alvo, FONTES, {});"
            "console.log(JSON.stringify({grupos: dom.porClasse(alvo, 'te-grp').map(function (g) {"
            "    return [g.textContent, dom.porClasse(g, 'te-ponto')[0].style.background]; }),"
            "  campos: dom.porClasse(alvo, 'te-fld').map(function (f) { return f.dataset.ref; "
            "})}));",
            {"FONTES": FONTES},
        )

        assert saida["grupos"] == [["Convidado▾", "#0f9d70"], ["Anfitrião▾", "#8a5cf6"]]
        assert saida["campos"] == ["convidado.nome", "anfitriao.nome", "anfitriao.cidade"]

    def test_clicar_num_campo_insere_a_referencia(self, node):
        saida = executar(
            node,
            "var alvo = dom.createElement('div'); var inserido = null;"
            "Panels.montarCampos(dom, alvo, FONTES, {aoInserir: function (r) { inserido = r; }});"
            "dom.porClasse(alvo, 'te-fld')[2].disparar('click');"
            "console.log(JSON.stringify(inserido));",
            {"FONTES": FONTES},
        )

        assert saida == "anfitriao.cidade"

    def test_o_filtro_esconde_o_que_nao_bate_e_abre_o_resto(self, node):
        saida = executar(
            node,
            "var alvo = dom.createElement('div');"
            "Panels.montarCampos(dom, alvo, FONTES, {filtro: 'cidade', abertos: {anfitriao: "
            "false}});"
            "var nada = dom.createElement('div');"
            "Panels.montarCampos(dom, nada, FONTES, {filtro: 'zzz'});"
            "console.log(JSON.stringify({campos: dom.porClasse(alvo, 'te-fld').map(function (f) {"
            "    return f.dataset.ref; }), vazio: dom.porClasse(nada, 'te-vazio').length}));",
            {"FONTES": FONTES},
        )

        assert saida == {"campos": ["anfitriao.cidade"], "vazio": 1}

    def test_em_leitura_os_campos_nao_inserem(self, node):
        saida = executar(
            node,
            "var alvo = dom.createElement('div');"
            "Panels.montarCampos(dom, alvo, FONTES, {editavel: false});"
            "console.log(JSON.stringify(dom.porClasse(alvo, 'te-fld').every(function (f) {"
            "  return f.disabled; })));",
            {"FONTES": FONTES},
        )

        assert saida is True

    def test_campos_no_documento_conta_os_usos(self, node):
        documento = layout(
            {"id": "r", "type": "rich_text", "x": 0, "y": 0, "width": 100, "height": 10,
             "properties": {"content": {"kind": "mixed", "parts": [
                 campo("anfitriao.nome"), texto(" e "), campo("anfitriao.nome"),
                 campo("convidado.nome")]}}},
        )
        saida = executar(
            node,
            "var alvo = dom.createElement('div');"
            "Panels.montarUsos(dom, alvo, L, FONTES, {});"
            "console.log(JSON.stringify({contagem: dom.porClasse(alvo, "
            "'te-usos-contagem')[0].textContent,"
            "  chips: dom.porClasse(alvo, 'te-chip').map(function (c) {"
            "    return [c.textContent, dom.porClasse(c, 'te-ponto')[0].style.background]; })}));",
            {"L": documento, "FONTES": FONTES},
        )

        assert saida["contagem"] == "3 usos"
        assert saida["chips"] == [["Nome completo", "#8a5cf6"], ["Nome completo", "#0f9d70"]]

    def test_a_barra_contextual_da_imagem_troca_o_asset(self, node):
        elemento = {"id": "i", "type": "image", "x": 0, "y": 0, "width": 50, "height": 50,
                    "properties": {"source": {"kind": "asset", "asset_id": 0}, "fit": "contain",
                                   "preserve_aspect_ratio": True}}
        saida = executar(
            node,
            "var alvo = dom.createElement('div'); var mudou = null;"
            "Panels.montarBarraDoElemento(dom, alvo, EL, {assets: [{id: 7, label: 'Logo'}],"
            "  editavel: true, aoAlterar: function (p) { mudou = p; }});"
            "var s = dom.porTag(alvo, 'select')[0]; s.value = '7'; s.disparar('change');"
            "console.log(JSON.stringify({mudou: mudou, escondida: alvo.hidden,"
            "  botoes: dom.porTag(alvo, 'button').map(function (b) { return b.textContent; })}));",
            {"EL": elemento},
        )

        assert saida["mudou"] == {"source": {"kind": "asset", "asset_id": 7}}
        assert saida["escondida"] is False
        assert "Apagar" in saida["botoes"]

    def test_a_barra_da_tabela_oferece_linhas_e_colunas(self, node):
        elemento = {"id": "t", "type": "table", "x": 0, "y": 0, "width": 50, "height": 50,
                    "properties": {"columns": [{"width": 50}], "rows": []}}
        saida = executar(
            node,
            "var alvo = dom.createElement('div'); var acoes = [];"
            "Panels.montarBarraDoElemento(dom, alvo, EL, {editavel: true,"
            "  aoAcao: function (a) { acoes.push(a); }});"
            "dom.porTag(alvo, 'button').forEach(function (b) { b.disparar('click'); });"
            "console.log(JSON.stringify(acoes));",
            {"EL": elemento},
        )

        assert saida == [
            "tabela-mais-linha", "tabela-menos-linha", "tabela-mais-coluna", "tabela-menos-coluna",
            "frente", "tras", "remover",
        ]

    def test_a_quebra_so_oferece_remover_e_o_texto_nao_tem_barra(self, node):
        saida = executar(
            node,
            "var q = dom.createElement('div');"
            "Panels.montarBarraDoElemento(dom, q, {id: 'q', type: 'page_break', properties: {}},"
            "  {editavel: true});"
            "var t = dom.createElement('div');"
            "Panels.montarBarraDoElemento(dom, t, T, {editavel: true});"
            "console.log(JSON.stringify({quebra: dom.porTag(q, 'button').map(function (b) {"
            "  return b.textContent; }), texto: t.hidden}));",
            {"T": bloco_de_texto("a", 0)},
        )

        assert saida == {"quebra": ["Remover quebra"], "texto": True}

    def test_a_barra_de_ferramentas_reflete_o_bloco_ativo(self, node):
        elemento = bloco_de_texto("a", 0, align="justify", list_marker="1.", indent=18,
                                  font_size=14, font_weight="bold")
        saida = executar(
            node,
            "function no(tag) { var n = dom.createElement(tag); return n; }"
            "var nos = {estilo: no('select'), fonte: no('select'), tamanho: no('select'),"
            "  entrelinha: no('select'), negrito: no('button'), italico: no('button'),"
            "  sublinhado: no('button'), riscado: no('button'), alinhar_left: no('button'),"
            "  alinhar_center: no('button'), alinhar_right: no('button'),"
            "  alinhar_justify: no('button'), listaMarcadores: no('button'),"
            "  listaNumerada: no('button'), soDeBloco: [no('select')]};"
            "['tamanho', 'fonte', 'entrelinha'].forEach(function (k) {"
            "  var op = no('option'); op.value = k === 'fonte' ? 'LiberationSans' : '11';"
            "  nos[k].appendChild(op); });"
            "Panels.refletir(nos, {bloco: EL, selecao: {bold: true, font_size: 14}, editavel: "
            "true});"
            "var ativos = ['negrito', 'italico', 'alinhar_justify', 'alinhar_left', "
            "'listaNumerada',"
            "  'listaMarcadores'].map(function (k) { return nos[k].classList.contains('is-ativo'); "
            "});"
            "var estilo = nos.estilo.value, tamanho = nos.tamanho.value,"
            "  extra = nos.tamanho.options.length;"
            "Panels.refletir(nos, {bloco: null, selecao: {}, editavel: true});"
            "console.log(JSON.stringify({ativos: ativos, estilo: estilo,"
            "  tamanho: tamanho, extra: extra,"
            "  desabilitado: nos.soDeBloco[0].disabled}));",
            {"EL": elemento},
        )

        assert saida["ativos"] == [True, False, True, False, True, False]
        assert saida["estilo"] == "h1"
        assert saida["tamanho"] == "14"
        assert saida["extra"] == 2
        assert saida["desabilitado"] is True


# ---------------------------------------------------------------------------
# 9. Comunicação com o servidor
# ---------------------------------------------------------------------------


class TestApi:
    def test_a_mensagem_de_erro_prefere_a_do_servidor(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Api.mensagemDeErro({dados: {error: 'Layout inválido.'}}),"
            "Api.mensagemDeErro({status: 409, dados: {}}),"
            "Api.mensagemDeErro(null)]));",
        )

        assert saida[0] == "Layout inválido."
        assert "409" in saida[1]
        assert saida[2]

    def test_uma_resposta_ok_do_http_com_ok_falso_nao_e_sucesso(self, node):
        saida = executar(
            node,
            "var origem = {ok: true, status: 200,"
            "  json: function () { return Promise.resolve({ok: false, error: 'x'}); }};"
            "global.fetch = function () { return Promise.resolve(origem); };"
            "var doc = {querySelector: function () { return {value: 't'}; }};"
            "Api.salvar(doc, '/x/', {version: 1, elements: []}).then(function (r) {"
            "  console.log(JSON.stringify({ok: r.ok, erro: Api.mensagemDeErro(r)})); });",
        )

        assert saida["ok"] is False
        assert saida["erro"] == "x"

    def test_falha_de_rede_nao_vira_sucesso(self, node):
        saida = executar(
            node,
            "global.fetch = function () { return Promise.reject(new Error('offline')); };"
            "var doc = {querySelector: function () { return {value: 't'}; }};"
            "Api.salvar(doc, '/x/', {}).then(function (r) {"
            "  console.log(JSON.stringify({ok: r.ok, erro: Api.mensagemDeErro(r)})); });",
        )

        assert saida["ok"] is False
        assert "rede" in saida["erro"].lower()

    def test_o_csrf_vai_no_cabecalho_e_o_idioma_no_corpo(self, node):
        saida = executar(
            node,
            "var visto = null;"
            "global.fetch = function (url, opcoes) { visto = opcoes;"
            "  return Promise.resolve({ok: true, status: 200,"
            "    json: function () { return Promise.resolve({ok: true}); }}); };"
            "var doc = {querySelector: function () { return {value: 'TOKEN'}; }};"
            "Api.salvar(doc, '/x/', {version: 1, elements: []}, {language: 'fr'}).then(function () "
            "{"
            "  console.log(JSON.stringify({token: visto.headers['X-CSRFToken'],"
            "    metodo: visto.method, corpo: JSON.parse(visto.body)})); });",
        )

        assert saida["token"] == "TOKEN"
        assert saida["metodo"] == "POST"
        assert saida["corpo"] == {"layout": {"version": 1, "elements": []}, "language": "fr"}
