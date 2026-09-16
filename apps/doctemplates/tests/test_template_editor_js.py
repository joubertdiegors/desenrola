"""
A lógica do editor que vive no navegador (Etapa 3.2).

Os módulos de `static/js/template-editor/` foram escritos para funcionar
também no Node (`module.exports` quando existe, global quando não), então
aqui eles são `require()`-ados de verdade e exercitados com dados — não há
extração por regex nem conferência de string em HTML.

Três grupos:

  * GEOMETRIA — as contas de pt ↔ pixel, comparadas com o Python quando
    há equivalente;
  * ESTADO — criar, mover, redimensionar, duplicar, camadas, desfazer;
  * CANVAS — que cada tipo vira um nó com a posição e o conteúdo certos.

O DOM mínimo (`dom_stub.js`) já existe no projeto e é reutilizado: ele
implementa só o que um renderizador usa. Sem Node instalado tudo aqui é
pulado — a suíte do projeto é Python e não ganha dependência obrigatória
de outra ferramenta.
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
    "Canvas": "canvas.js",
    "Props": "properties.js",
    "Api": "api.js",
}


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


# ---------------------------------------------------------------------------
# 0. Os módulos carregam
# ---------------------------------------------------------------------------


def test_os_modulos_carregam_no_node(node):
    saida = executar(
        node,
        "console.log(JSON.stringify({"
        "geo: typeof Geo.paraDocumento,"
        "state: typeof State.criarElemento,"
        "canvas: typeof Canvas.desenharLayout,"
        "props: typeof Props.desenharPainel,"
        "api: typeof Api.salvar}));",
    )

    assert saida == {
        "geo": "function", "state": "function", "canvas": "function",
        "props": "function", "api": "function",
    }


@pytest.mark.parametrize("arquivo", sorted(p.name for p in JS.glob("*.js")))
def test_todo_javascript_tem_sintaxe_valida(node, arquivo):
    resultado = subprocess.run(
        [node, "--check", str(JS / arquivo)],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )

    assert resultado.returncode == 0, resultado.stderr


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

    def test_a_caixa_volta_intacta_do_zoom(self, node):
        caixa = {"x": 72.3456, "y": 120.9876, "width": 400.125, "height": 13.5}

        saida = executar(
            node,
            f"var c = {json.dumps(caixa)};"
            "console.log(JSON.stringify(Geo.caixaParaDocumento("
            "Geo.caixaParaTela(c, 0.37), 0.37)));",
        )

        assert saida == pytest.approx(caixa)

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

    def test_o_zoom_inicial_tem_piso_legivel(self, node):
        """
        "Caber" numa área estreita daria uma página de ~230px, com campos
        de 5px de altura: visível, inutilizável.
        """
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Geo.zoomParaCaber(280, 595.2756, 48),"
            "Geo.zoomInicial(280, 595.2756, 48)]));",
        )

        assert saida[0] < 0.5
        assert saida[1] == 0.5

    def test_dimensao_negativa_e_travada_em_zero(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Geo.dimensaoValida(-5), Geo.dimensaoValida(0),"
            "Geo.dimensaoValida(13.5), Geo.dimensaoValida(NaN)]));",
        )

        assert saida == [0, 0, 13.5, 0]

    def test_encaixar_com_passo_zero_nao_arredonda(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Geo.encaixar(72.3456, 0), Geo.encaixar(72.3456, 12),"
            "Geo.encaixar(80, 12)]));",
        )

        assert saida == [72.3456, 72, 84]


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

    def test_o_elemento_de_campo_passa_no_validador(self, node, catalogo):
        saida = executar(
            node,
            "console.log(JSON.stringify(State.criarElementoDeCampo("
            "CAT, 'anfitriao.cidade', 'x', {x: 10, y: 10})));",
            {"CAT": catalogo},
        )

        layout_schema.validate_layout({"version": 1, "elements": [saida]})

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

    def test_redimensionar_nunca_aceita_negativo(self, node, catalogo):
        saida = executar(
            node,
            "var l = State.adicionar(State.layoutVazio(1),"
            "  State.criarElemento(CAT, 'rectangle', 'a'), 1);"
            "l = State.redimensionar(l, 'a', -50, -10, 1);"
            "console.log(JSON.stringify(State.obter(l, 'a')));",
            {"CAT": catalogo},
        )

        assert saida["width"] == 0
        assert saida["height"] == 0

    def test_linha_pode_ter_altura_zero(self, node, catalogo):
        saida = executar(
            node,
            "console.log(JSON.stringify(State.criarElemento(CAT, 'line', 'a')));",
            {"CAT": catalogo},
        )

        assert saida["height"] == 0
        layout_schema.validate_layout({"version": 1, "elements": [saida]})

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

    def test_duplicar_faz_copia_profunda(self, node, catalogo):
        saida = executar(
            node,
            "var l = State.adicionar(State.layoutVazio(1),"
            "  State.criarElemento(CAT, 'text', 'a'), 1);"
            "var r = State.duplicar(l, 'a', 'b', 1);"
            "State.obter(r.layout, 'b').properties.padding.top = 99;"
            "console.log(JSON.stringify(State.obter(r.layout, 'a').properties.padding.top));",
            {"CAT": catalogo},
        )

        assert saida == 0

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

    def test_a_fila_pode_ser_reabastecida(self, node):
        saida = executar(
            node,
            "var f = State.criarFilaDeIds(['a']);"
            "var l = State.layoutVazio(1);"
            "State.proximoId(f, l);"
            "State.reabastecer(f, ['x', 'y']);"
            "console.log(JSON.stringify([State.proximoId(f, l), State.proximoId(f, l)]));",
        )

        assert saida == ["x", "y"]

    def test_o_javascript_nao_gera_identificadores(self):
        """
        Um gerador só para o sistema: o do servidor. Nenhum módulo pode
        inventar id com Math.random, uuid ou contador.
        """
        for arquivo in JS.glob("*.js"):
            texto = arquivo.read_text(encoding="utf-8")
            assert "Math.random" not in texto, arquivo.name
            assert "randomUUID" not in texto, arquivo.name

    def test_o_formato_bate_com_o_do_servico(self, node):
        do_servico = servico_de_layout.novo_id()

        assert len(do_servico) == 12
        assert do_servico.isalnum()


# ---------------------------------------------------------------------------
# 4. Camadas
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

    def test_a_ordem_da_lista_e_a_ordem_de_desenho(self, node, catalogo):
        saida = self._com_tres(
            node,
            "console.log(JSON.stringify(l.elements.map(function (e) { return e.id; })));",
            catalogo,
        )

        assert saida == ["a", "b", "c"]

    def test_nenhum_elemento_tem_z_index(self, node, catalogo):
        saida = self._com_tres(
            node,
            "console.log(JSON.stringify(l.elements.map(function (e) {"
            "  return Object.prototype.hasOwnProperty.call(e, 'z_index'); })));",
            catalogo,
        )

        assert saida == [False, False, False]

    @pytest.mark.parametrize(
        "operacao, alvo, esperado",
        [
            ("trazerParaFrente", "a", ["b", "c", "a"]),
            ("enviarParaTras", "c", ["c", "a", "b"]),
            ("moverParaFrente", "a", ["b", "a", "c"]),
            ("moverParaTras", "c", ["a", "c", "b"]),
            ("trazerParaFrente", "c", ["a", "b", "c"]),
            ("enviarParaTras", "a", ["a", "b", "c"]),
            ("moverParaFrente", "c", ["a", "b", "c"]),
            ("moverParaTras", "a", ["a", "b", "c"]),
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

    def test_reordenar_preserva_todos_os_elementos(self, node, catalogo):
        saida = self._com_tres(
            node,
            "l = State.trazerParaFrente(l, 'a', 1);"
            "l = State.enviarParaTras(l, 'b', 1);"
            "console.log(JSON.stringify(l.elements.map(function (e) { return e.id; }).sort()));",
            catalogo,
        )

        assert saida == ["a", "b", "c"]

    def test_reordenar_elemento_inexistente_nao_quebra(self, node, catalogo):
        saida = self._com_tres(
            node,
            "l = State.trazerParaFrente(l, 'fantasma', 1);"
            "console.log(JSON.stringify(l.elements.map(function (e) { return e.id; })));",
            catalogo,
        )

        assert saida == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# 5. Imutabilidade
# ---------------------------------------------------------------------------


class TestImutabilidade:
    @pytest.mark.parametrize(
        "operacao",
        [
            "State.adicionar(l, State.criarElemento(CAT, 'line', 'z'), 1)",
            "State.remover(l, 'a', 1)",
            "State.atualizar(l, 'a', {properties: {font_size: 20}}, 1)",
            "State.mover(l, 'a', 99, 99, 1)",
            "State.redimensionar(l, 'a', 5, 5, 1)",
            "State.duplicar(l, 'a', 'novo', 1).layout",
            "State.trazerParaFrente(l, 'a', 1)",
            "State.enviarParaTras(l, 'b', 1)",
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
            {"CAT": catalogo},
        )

        assert saida is True

    def test_alterar_o_resultado_nao_alcanca_a_entrada(self, node, catalogo):
        saida = executar(
            node,
            "var l = State.adicionar(State.layoutVazio(1),"
            "  State.criarElemento(CAT, 'text', 'a'), 1);"
            "var novo = State.atualizar(l, 'a', {x: 1}, 1);"
            "State.obter(novo, 'a').properties.content.value = 'mexido';"
            "console.log(JSON.stringify(State.obter(l, 'a').properties.content.value));",
            {"CAT": catalogo},
        )

        assert saida == ""


# ---------------------------------------------------------------------------
# 6. Desfazer e refazer
# ---------------------------------------------------------------------------


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

    def test_nao_da_para_desfazer_alem_do_inicio(self, node):
        saida = executar(
            node,
            "var h = State.criarHistorico(State.layoutVazio(1));"
            "h = State.desfazer(h); h = State.desfazer(h);"
            "console.log(JSON.stringify({i: h.indice, pode: State.podeDesfazer(h)}));",
        )

        assert saida == {"i": 0, "pode": False}

    def test_nao_da_para_refazer_alem_do_fim(self, node):
        saida = executar(
            node,
            "var h = State.criarHistorico(State.layoutVazio(1));"
            "console.log(JSON.stringify(State.podeRefazer(State.refazer(h))));",
        )

        assert saida is False

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

    def test_o_historico_tem_limite_mas_o_documento_nao(self, node, catalogo):
        saida = executar(
            node,
            "var h = State.criarHistorico(State.layoutVazio(1), 5);"
            "for (var i = 0; i < 20; i++) {"
            "  h = State.registrar(h, State.adicionar(State.atual(h),"
            "    State.criarElemento(CAT, 'text', 'e' + i), 1)); }"
            "console.log(JSON.stringify({guardados: h.estados.length,"
            "  elementos: State.atual(h).elements.length}));",
            {"CAT": catalogo},
        )

        assert saida == {"guardados": 5, "elementos": 20}


# ---------------------------------------------------------------------------
# 7. Canvas
# ---------------------------------------------------------------------------


class TestCanvas:
    def _desenhar(self, node, elementos, catalogo, extras=""):
        return executar(
            node,
            f"var doc = require({_caminho(DOM_STUB)!r});"
            "var alvo = doc.createElement('div');"
            "var campos = Canvas.indiceDeCampos(FONTES);"
            f"Canvas.desenharLayout(doc, alvo, {{version: 1, elements: ELS}}, "
            "{zoom: ZOOM, campos: campos, assets: [], selecionado: SEL, editavel: true});"
            + extras +
            "console.log(JSON.stringify(alvo.children.map(function (n) {"
            "  return {id: n.dataset.id, tipo: n.dataset.tipo,"
            "    left: parseFloat(n.style.left), top: parseFloat(n.style.top),"
            "    width: parseFloat(n.style.width), height: parseFloat(n.style.height),"
            "    classes: n.classList._classes, texto: n.textContent};"
            "})));",
            {
                "ELS": elementos,
                "FONTES": [
                    {
                        "code": "convidado", "label": "Convidado",
                        "fields": [
                            {"reference": "convidado.nome", "key": "nome",
                             "label": "Nome completo", "kind": "texto"}
                        ],
                    }
                ],
                "ZOOM": 1,
                "SEL": None,
                "CAT": catalogo,
            },
        )

    def test_todos_os_oito_tipos_sao_desenhados(self, node, catalogo):
        elementos = executar(
            node,
            "console.log(JSON.stringify(CAT.map(function (t, i) {"
            "  return State.criarElemento(CAT, t.code, 'id' + i, {x: 10, y: 20}); })));",
            {"CAT": catalogo},
        )

        desenhados = self._desenhar(node, elementos, catalogo)

        assert len(desenhados) == len(elements.codigos())
        assert {n["tipo"] for n in desenhados} == set(elements.codigos())

    def test_nenhum_tipo_cai_no_default(self, node, catalogo):
        """O `default` escreve o nome do tipo — sinal de tipo desconhecido."""
        elementos = executar(
            node,
            "console.log(JSON.stringify(CAT.map(function (t, i) {"
            "  return State.criarElemento(CAT, t.code, 'id' + i); })));",
            {"CAT": catalogo},
        )

        for no in self._desenhar(node, elementos, catalogo):
            assert no["texto"] != no["tipo"], no["tipo"]

    def test_as_coordenadas_viram_posicao_na_tela(self, node, catalogo):
        elemento = {
            "id": "a", "type": "text", "x": 72.3456, "y": 120.9876,
            "width": 400.125, "height": 13.5,
            "properties": {"content": {"kind": "text", "value": "x"}},
        }

        no = self._desenhar(node, [elemento], catalogo)[0]

        assert no["left"] == pytest.approx(72.3456)
        assert no["top"] == pytest.approx(120.9876)
        assert no["width"] == pytest.approx(400.125)

    def test_um_campo_aparece_com_rotulo_legivel(self, node, catalogo):
        """
        Apresentação: o dado gravado continua `{kind, source}` intacto.
        """
        elemento = {
            "id": "a", "type": "text", "x": 0, "y": 0, "width": 100, "height": 12,
            "properties": {"content": {"kind": "field", "source": "convidado.nome"}},
        }

        no = self._desenhar(node, [elemento], catalogo)[0]

        assert no["texto"] == "[Convidado · Nome completo]"

    def test_um_campo_sem_referencia_e_sinalizado(self, node, catalogo):
        elemento = {
            "id": "a", "type": "text", "x": 0, "y": 0, "width": 100, "height": 12,
            "properties": {"content": {"kind": "field", "source": ""}},
        }

        no = self._desenhar(node, [elemento], catalogo)[0]

        assert "is-incompleto" in no["classes"]

    def test_conteudo_misto_junta_os_trechos(self, node, catalogo):
        elemento = {
            "id": "a", "type": "rich_text", "x": 0, "y": 0, "width": 300, "height": 40,
            "properties": {"content": {"kind": "mixed", "parts": [
                {"kind": "text", "value": "Je soussigné "},
                {"kind": "field", "source": "convidado.nome"},
                {"kind": "text", "value": ", domicilié"},
            ]}},
        }

        no = self._desenhar(node, [elemento], catalogo)[0]

        assert no["texto"] == "Je soussigné [Convidado · Nome completo], domicilié"

    def test_a_ordem_de_insercao_e_a_ordem_da_lista(self, node, catalogo):
        elementos = [
            {"id": i, "type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10,
             "properties": {"border_width": 1}}
            for i in ("a", "b", "c")
        ]

        desenhados = self._desenhar(node, elementos, catalogo)

        assert [n["id"] for n in desenhados] == ["a", "b", "c"]

    def test_o_selecionado_ganha_marca_e_alcas(self, node, catalogo):
        elementos = [
            {"id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10,
             "properties": {"border_width": 1}}
        ]

        saida = executar(
            node,
            f"var doc = require({_caminho(DOM_STUB)!r});"
            "var alvo = doc.createElement('div');"
            f"Canvas.desenharLayout(doc, alvo, {{version: 1, elements: {json.dumps(elementos)}}},"
            "{zoom: 1, campos: {}, assets: [], selecionado: 'a', editavel: true});"
            "console.log(JSON.stringify({classes: alvo.children[0].classList._classes,"
            "  alcas: alvo.children[0].children.length}));",
        )

        assert "is-selecionado" in saida["classes"]
        assert saida["alcas"] == 8

    def test_em_leitura_nao_ha_alcas(self, node, catalogo):
        elementos = [
            {"id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10,
             "properties": {"border_width": 1}}
        ]

        saida = executar(
            node,
            f"var doc = require({_caminho(DOM_STUB)!r});"
            "var alvo = doc.createElement('div');"
            f"Canvas.desenharLayout(doc, alvo, {{version: 1, elements: {json.dumps(elementos)}}},"
            "{zoom: 1, campos: {}, assets: [], selecionado: 'a', editavel: false});"
            "console.log(JSON.stringify(alvo.children[0].children.length));",
        )

        assert saida == 0

    def test_a_tabela_desenha_as_celulas(self, node, catalogo):
        elemento = {
            "id": "t", "type": "table", "x": 0, "y": 0, "width": 300, "height": 40,
            "properties": {
                "columns": [{"width": 100}, {"width": 200}],
                "rows": [{"min_height": 18, "cells": [
                    {"content": {"kind": "text", "value": "Nome :"}},
                    {"content": {"kind": "field", "source": "convidado.nome"}},
                ]}],
            },
        }

        no = self._desenhar(node, [elemento], catalogo)[0]

        assert "Nome :" in no["texto"]
        assert "[Convidado · Nome completo]" in no["texto"]

    def test_a_celula_da_tabela_usa_a_fonte_do_documento(self, node):
        """
        Sem tamanho e altura de linha próprios a célula cai no padrão do
        navegador -- bem maior que os 11pt do documento -- e o texto
        ocupa mais linhas do que a `min_height` da linha prevê. A tabela
        cresce além da própria caixa e passa a sobrepor o que vem depois
        dela no documento: foi o que a validação manual do modelo FR
        encontrou no centro da página.
        """
        elemento = {
            "id": "t", "type": "table", "x": 0, "y": 0, "width": 300, "height": 40,
            "properties": {
                "columns": [{"width": 100}, {"width": 200}],
                "rows": [{"min_height": 18, "cells": [
                    {"content": {"kind": "text", "value": "Nome :"}},
                ]}],
                "font_size": 11,
                "line_height": 1.2,
            },
        }

        saida = executar(
            node,
            f"var doc = require({_caminho(DOM_STUB)!r});"
            "var alvo = doc.createElement('div');"
            f"Canvas.desenharLayout(doc, alvo, {{version: 1, elements: [{json.dumps(elemento)}]}},"
            "{zoom: 2, campos: {}, assets: [], selecionado: null, editavel: true});"
            "var td = alvo.children[0].children[0].children[1].children[0].children[0];"
            "console.log(JSON.stringify({fontSize: td.style.fontSize,"
            "  fontFamily: td.style.fontFamily, lineHeight: td.style.lineHeight}));",
        )

        assert saida["fontSize"] == "22px"
        assert "Liberation Sans" in saida["fontFamily"]
        assert saida["lineHeight"] == "1.2"

    def test_o_zoom_escala_tudo_igualmente(self, node, catalogo):
        elemento = {
            "id": "a", "type": "rectangle", "x": 50, "y": 100, "width": 200, "height": 40,
            "properties": {"border_width": 1},
        }

        saida = executar(
            node,
            f"var doc = require({_caminho(DOM_STUB)!r});"
            f"var els = [{json.dumps(elemento)}];"
            "var r = [1, 0.5].map(function (z) {"
            "  var alvo = doc.createElement('div');"
            "  Canvas.desenharLayout(doc, alvo, {version: 1, elements: els},"
            "    {zoom: z, campos: {}, assets: [], selecionado: null, editavel: true});"
            "  var n = alvo.children[0];"
            "  return [parseFloat(n.style.left), parseFloat(n.style.width)]; });"
            "console.log(JSON.stringify(r));",
        )

        assert saida[0] == [50, 200]
        assert saida[1] == [25, 100]

    def test_o_estilo_de_texto_acompanha_o_zoom(self, node):
        saida = executar(
            node,
            "console.log(JSON.stringify(["
            "Canvas.estiloDeTexto({font_size: 11}, 1).fontSize,"
            "Canvas.estiloDeTexto({font_size: 11}, 2).fontSize,"
            "Canvas.estiloDeTexto({font_weight: 'bold'}, 1).fontWeight,"
            "Canvas.estiloDeTexto({font_style: 'italic'}, 1).fontStyle]));",
        )

        assert saida == ["11px", "22px", "700", "italic"]


# ---------------------------------------------------------------------------
# 8. Comunicação com o servidor
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
        """
        `resposta.ok` é só o status HTTP; a decisão do servidor vem no
        corpo. Confundir os dois faria um erro passar por salvamento.
        """
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

    def test_o_csrf_vai_no_cabecalho(self, node):
        saida = executar(
            node,
            "var visto = null;"
            "global.fetch = function (url, opcoes) { visto = opcoes;"
            "  return Promise.resolve({ok: true, status: 200,"
            "    json: function () { return Promise.resolve({ok: true}); }}); };"
            "var doc = {querySelector: function () { return {value: 'TOKEN'}; }};"
            "Api.salvar(doc, '/x/', {version: 1, elements: []}).then(function () {"
            "  console.log(JSON.stringify({token: visto.headers['X-CSRFToken'],"
            "    metodo: visto.method, corpo: JSON.parse(visto.body)})); });",
        )

        assert saida["token"] == "TOKEN"
        assert saida["metodo"] == "POST"
        assert saida["corpo"] == {"layout": {"version": 1, "elements": []}}


# ---------------------------------------------------------------------------
# 6. Editores de estrutura: conteúdo misto e tabela (Bloco F)
# ---------------------------------------------------------------------------
#
# Até aqui os dois eram SOMENTE LEITURA -- o painel mostrava "3 trecho(s)"
# e "Linhas: 2", com o comentário de que editar era etapa seguinte. Esta é
# a etapa seguinte.
#
# O QUE ESTES TESTES EXISTEM PARA IMPEDIR
# ---------------------------------------
# 1. **Que a sequência vire uma string.** `texto + campo + texto` tem de
#    continuar sendo três trechos depois de editar qualquer um deles. Se
#    alguém trocar o editor por uma caixa de texto simples, os campos
#    perdem identidade e o documento passa a imprimir o texto literal;
# 2. **Que uma edição contamine o vizinho.** Mudar o peso de um trecho não
#    pode mexer no `source` de outro;
# 3. **Que a tabela fique inválida no meio do caminho.** O servidor cobra
#    uma célula por coluna em CADA linha: acrescentar coluna tem de
#    acrescentar célula em todas;
# 4. **Que o editor produza algo que o servidor recusa.** Por isso a saída
#    do JavaScript volta para `validate_layout` em Python.
#
# OS CONTROLES SÃO ACHADOS POR PAPEL, NÃO POR ÍNDICE
# --------------------------------------------------
# Um trecho de campo tem quatro seletores e um de texto tem três, então
# índice global depende do que veio antes. `trecho(i).campo` continua
# valendo quando a ordem mudar, e só falha quando o COMPORTAMENTO mudar.

# Ajudantes em JavaScript: acham um controle pelo papel que ele cumpre.
AJUDANTES_JS = """
function porPapelNoTrecho(dom, no, i) {
  var linha = dom.porClasse(no, 'te-trecho')[i];
  var selects = dom.porTag(linha, 'select');
  var inputs = dom.porTag(linha, 'input');
  return {
    tipo: selects[0],
    campo: selects.length === 4 ? selects[1] : null,
    peso: selects[selects.length - 2],
    estilo: selects[selects.length - 1],
    texto: inputs[0] || null,
    botao: function (titulo) {
      return dom.porTag(linha, 'button').filter(function (b) {
        return b.attrs.title === titulo;
      })[0];
    }
  };
}

function botaoPorTexto(dom, no, texto) {
  return dom.porTag(no, 'button').filter(function (b) {
    return b.textContent === texto;
  })[0];
}

function porPapelNaCelula(dom, no, iLinha, iCelula) {
  var bloco = dom.porClasse(no, 'te-linha')[iLinha];
  var celula = dom.porClasse(bloco, 'te-celula')[iCelula];
  var selects = dom.porTag(celula, 'select');
  var inputs = dom.porTag(celula, 'input');
  // O conteudo da celula passa por `controleDeConteudo`, que usa
  // `textarea` para texto -- nao `input`, como o trecho de `mixed`.
  var areas = dom.porTag(celula, 'textarea');
  return {
    texto: areas[0] || inputs.filter(function (e) {
      return e.type !== 'checkbox'; })[0] || null,
    campo: selects.length > 1 ? selects[0] : null,
    alinhamento: selects[selects.length - 1],
    negrito: inputs.filter(function (e) { return e.type === 'checkbox'; })[0]
  };
}

function botaoDaLinha(dom, no, iLinha, titulo) {
  var bloco = dom.porClasse(no, 'te-linha')[iLinha];
  return dom.porTag(bloco, 'button').filter(function (b) {
    return b.attrs.title === titulo;
  })[0];
}

function botaoDaColuna(dom, no, iColuna, titulo) {
  var bloco = dom.porClasse(no, 'te-coluna')[iColuna];
  return dom.porTag(bloco, 'button').filter(function (b) {
    return b.attrs.title === titulo;
  })[0];
}
"""


CONTEXTO_MISTO = {
    "editavel": True,
    "catalogo": [
        {
            "code": "rich_text",
            "properties": [
                {"name": "font_weight", "options": ["regular", "bold"]},
                {"name": "font_style", "options": ["normal", "italic"]},
            ],
        }
    ],
    "referencias": [
        {"reference": "convidado.nome", "label": "Nome do convidado"},
        {"reference": "anfitriao.cidade", "label": "Cidade do anfitrião"},
    ],
}

FRASE = [
    {"kind": "text", "value": "Je soussigné "},
    {"kind": "field", "source": "anfitriao.cidade", "font_weight": "bold"},
    {"kind": "text", "value": ", domicilié à "},
]


def _misto(node, acao, partes=None, editavel=True):
    """Monta o editor de sequência, executa `acao` e devolve o estado."""
    contexto = dict(CONTEXTO_MISTO, editavel=editavel)
    return executar(
        node,
        f"var dom = require({_caminho(DOM_STUB)!r});"
        + AJUDANTES_JS +
        "var doc = {createElement: dom.createElement};"
        "var saiu = null;"
        "var no = Props.controleDeMisto(doc, {label: 'Conteúdo'},"
        "  {kind: 'mixed', parts: PARTES}, function (v) { saiu = v; }, CONTEXTO);"
        "var trecho = function (i) { return porPapelNoTrecho(dom, no, i); };"
        "var botao = function (t) { return botaoPorTexto(dom, no, t); };"
        + acao +
        "console.log(JSON.stringify({saiu: saiu,"
        "  trechos: dom.porClasse(no, 'te-trecho').length,"
        "  botoes: dom.porTag(no, 'button').map(function (b) {"
        "    return b.attrs.title || b.textContent; }),"
        "  desabilitados: dom.porTag(no, 'select').concat(dom.porTag(no, 'input'))"
        "    .filter(function (e) { return e.disabled; }).length}));",
        {"CONTEXTO": contexto, "PARTES": FRASE if partes is None else partes},
    )


class TestConteudoMisto:
    def test_cada_trecho_vira_uma_linha_e_nao_uma_contagem(self, node):
        saida = _misto(node, "")

        assert saida["trechos"] == 3

    def test_editar_um_texto_nao_funde_a_sequencia(self, node):
        """
        O defeito que uma caixa de texto simples causaria: três trechos
        virariam uma string e o campo perderia identidade.
        """
        saida = _misto(
            node,
            "trecho(0).texto.value = 'Je soussignée ';"
            "trecho(0).texto.disparar('change');",
        )

        assert saida["saiu"]["kind"] == "mixed"
        assert saida["saiu"]["parts"] == [
            {"kind": "text", "value": "Je soussignée "},
            {"kind": "field", "source": "anfitriao.cidade", "font_weight": "bold"},
            {"kind": "text", "value": ", domicilié à "},
        ]

    def test_trocar_o_campo_nao_toca_nos_textos(self, node):
        saida = _misto(
            node,
            "trecho(1).campo.value = 'convidado.nome';"
            "trecho(1).campo.disparar('change');",
        )
        partes = saida["saiu"]["parts"]

        assert partes[1] == {
            "kind": "field", "source": "convidado.nome", "font_weight": "bold"
        }
        assert partes[0]["value"] == "Je soussigné "
        assert partes[2]["value"] == ", domicilié à "

    def test_a_enfase_de_um_trecho_nao_alcanca_os_outros(self, node):
        """Negritar o primeiro trecho não pode mexer no campo do segundo."""
        saida = _misto(
            node, "trecho(0).peso.value = 'bold'; trecho(0).peso.disparar('change');"
        )
        partes = saida["saiu"]["parts"]

        assert partes[0] == {
            "kind": "text", "value": "Je soussigné ", "font_weight": "bold"
        }
        assert partes[1]["source"] == "anfitriao.cidade"
        assert partes[1]["font_weight"] == "bold"

    def test_herdar_apaga_a_chave_em_vez_de_gravar_um_valor(self, node):
        """
        Herdar é a AUSÊNCIA da chave -- é o que `layout_schema` diz. Gravar
        `font_weight: "herda"` seria inventar um valor que o validador
        recusa.
        """
        saida = _misto(node, "trecho(1).peso.value = ''; trecho(1).peso.disparar('change');")

        assert "font_weight" not in saida["saiu"]["parts"][1]
        assert saida["saiu"]["parts"][1]["source"] == "anfitriao.cidade"

    def test_converter_texto_em_campo_preserva_a_enfase(self, node):
        saida = _misto(
            node,
            "trecho(0).tipo.value = 'field'; trecho(0).tipo.disparar('change');",
            partes=[{"kind": "text", "value": "oi", "font_style": "italic"}],
        )

        assert saida["saiu"]["parts"][0] == {
            "kind": "field", "source": "", "font_style": "italic"
        }

    def test_converter_campo_em_texto_larga_a_referencia(self, node):
        """
        Um texto livre não é referência, e uma referência não é texto para
        se ler: o valor não atravessa a conversão.
        """
        saida = _misto(
            node,
            "trecho(0).tipo.value = 'text'; trecho(0).tipo.disparar('change');",
            partes=[{"kind": "field", "source": "convidado.nome"}],
        )

        assert saida["saiu"]["parts"][0] == {"kind": "text", "value": ""}

    def test_subir_troca_a_ordem_sem_perder_nada(self, node):
        saida = _misto(node, "trecho(1).botao('Subir').disparar('click');")
        partes = saida["saiu"]["parts"]

        assert [p["kind"] for p in partes] == ["field", "text", "text"]
        assert partes[0] == {
            "kind": "field", "source": "anfitriao.cidade", "font_weight": "bold"
        }
        assert partes[1]["value"] == "Je soussigné "

    def test_descer_troca_a_ordem(self, node):
        saida = _misto(node, "trecho(0).botao('Descer').disparar('click');")

        assert [
            p.get("value", p.get("source")) for p in saida["saiu"]["parts"]
        ] == ["anfitriao.cidade", "Je soussigné ", ", domicilié à "]

    def test_remover_tira_so_aquele(self, node):
        saida = _misto(node, "trecho(1).botao('Remover').disparar('click');")

        assert [p["kind"] for p in saida["saiu"]["parts"]] == ["text", "text"]
        assert saida["saiu"]["parts"][0]["value"] == "Je soussigné "
        assert saida["saiu"]["parts"][1]["value"] == ", domicilié à "

    def test_o_primeiro_nao_sobe_e_o_ultimo_nao_desce(self, node):
        """Botão que não faz nada é o que este projeto tira de tela."""
        saida = _misto(node, "")

        acoes = [b for b in saida["botoes"] if b in ("Subir", "Descer", "Remover")]
        assert acoes == [
            "Descer", "Remover",
            "Subir", "Descer", "Remover",
            "Subir", "Remover",
        ]

    @pytest.mark.parametrize(("rotulo", "esperado"), [("+ Texto", "text"), ("+ Campo", "field")])
    def test_da_para_acrescentar_trecho(self, node, rotulo, esperado):
        saida = _misto(node, f"botao({rotulo!r}).disparar('click');")

        assert len(saida["saiu"]["parts"]) == 4
        assert saida["saiu"]["parts"][3]["kind"] == esperado

    def test_em_leitura_nao_ha_acao_nem_campo_habilitado(self, node):
        saida = _misto(node, "", editavel=False)

        assert saida["botoes"] == []
        assert saida["desabilitados"] > 0

    def test_o_que_o_editor_produz_passa_no_validador_do_servidor(self, node, catalogo):
        """
        A prova final: o JavaScript não pode produzir algo que o servidor
        recuse. A saída volta para `validate_layout` em Python.
        """
        saida = _misto(
            node, "trecho(0).texto.value = 'Eu, '; trecho(0).texto.disparar('change');"
        )
        elemento = executar(
            node,
            "console.log(JSON.stringify(State.criarElemento(CAT, 'rich_text', 'a')));",
            {"CAT": catalogo},
        )
        elemento["properties"]["content"] = saida["saiu"]

        layout_schema.validate_layout({"version": 1, "elements": [elemento]})


# ---------------------------------------------------------------------------
# Tabela
# ---------------------------------------------------------------------------

TABELA = {
    "columns": [{"width": 100, "align": "left"}, {"width": 60, "align": "right"}],
    "rows": [
        {
            "min_height": 0,
            "cells": [
                {"content": {"kind": "text", "value": "Nome"}, "align": "left", "bold": True},
                {
                    "content": {"kind": "field", "source": "convidado.nome"},
                    "align": "right",
                    "bold": False,
                },
            ],
        },
        {
            "min_height": 12,
            "cells": [
                {"content": {"kind": "text", "value": "Cidade"}, "align": "left", "bold": False},
                {
                    "content": {"kind": "text", "value": "Bruxelas"},
                    "align": "right",
                    "bold": False,
                },
            ],
        },
    ],
}

CONTEXTO_TABELA = {
    "editavel": True,
    "catalogo": [
        {
            "code": "table",
            "properties": [{"name": "align", "options": ["left", "center", "right"]}],
        }
    ],
    "referencias": [
        {"reference": "convidado.nome", "label": "Nome"},
        {"reference": "anfitriao.cidade", "label": "Cidade"},
    ],
}


def _tabela(node, qual, acao, propriedades=None, editavel=True):
    props = TABELA if propriedades is None else propriedades
    contexto = dict(CONTEXTO_TABELA, editavel=editavel)
    valor = "PROPS.rows" if qual == "linhas" else "PROPS.columns"
    funcao = "controleDeLinhas" if qual == "linhas" else "controleDeColunas"
    return executar(
        node,
        f"var dom = require({_caminho(DOM_STUB)!r});"
        + AJUDANTES_JS +
        "var doc = {createElement: dom.createElement};"
        "var saiu = null;"
        "var CTX = Object.assign({}, CONTEXTO, {elemento: {properties: PROPS},"
        "  aoAlterarPropriedades: function (p) { saiu = p; }});"
        f"var no = Props.{funcao}(doc, {{label: 'X'}}, {valor}, CTX);"
        "var celula = function (l, c) { return porPapelNaCelula(dom, no, l, c); };"
        "var acaoDaLinha = function (l, t) { return botaoDaLinha(dom, no, l, t); };"
        "var acaoDaColuna = function (c, t) { return botaoDaColuna(dom, no, c, t); };"
        "var botao = function (t) { return botaoPorTexto(dom, no, t); };"
        + acao +
        "console.log(JSON.stringify({saiu: saiu,"
        "  celulas: dom.porClasse(no, 'te-celula').length,"
        "  colunas: dom.porClasse(no, 'te-coluna').length,"
        "  botoes: dom.porTag(no, 'button').map(function (b) {"
        "    return b.attrs.title || b.textContent; })}));",
        {"CONTEXTO": contexto, "PROPS": props},
    )


class TestTabela:
    def test_cada_celula_vira_um_editor_e_nao_uma_contagem(self, node):
        saida = _tabela(node, "linhas", "")

        assert saida["celulas"] == 4

    def test_editar_uma_celula_nao_toca_nas_outras(self, node):
        saida = _tabela(
            node, "linhas",
            "celula(0, 0).texto.value = 'Convidado';"
            "celula(0, 0).texto.disparar('change');",
        )
        linhas = saida["saiu"]["rows"]

        assert linhas[0]["cells"][0]["content"] == {"kind": "text", "value": "Convidado"}
        assert linhas[0]["cells"][0]["bold"] is True
        assert linhas[0]["cells"][1]["content"] == {
            "kind": "field", "source": "convidado.nome"
        }
        assert linhas[1]["cells"][1]["content"]["value"] == "Bruxelas"

    def test_uma_celula_aceita_campo_dinamico(self, node):
        """
        O conteúdo da célula passa pelo MESMO controle do resto do painel,
        então campo dentro de célula funciona sem código novo -- que é o
        que o contrato do servidor já permitia.
        """
        saida = _tabela(
            node, "linhas",
            "celula(0, 1).campo.value = 'anfitriao.cidade';"
            "celula(0, 1).campo.disparar('change');",
        )

        assert saida["saiu"]["rows"][0]["cells"][1]["content"] == {
            "kind": "field", "source": "anfitriao.cidade"
        }
        assert saida["saiu"]["rows"][0]["cells"][0]["content"]["value"] == "Nome"

    def test_o_negrito_da_celula_e_editavel(self, node):
        saida = _tabela(
            node, "linhas",
            "celula(0, 0).negrito.checked = false;"
            "celula(0, 0).negrito.disparar('change');",
        )

        assert saida["saiu"]["rows"][0]["cells"][0]["bold"] is False
        assert saida["saiu"]["rows"][0]["cells"][1]["bold"] is False

    def test_o_alinhamento_da_celula_e_editavel(self, node):
        saida = _tabela(
            node, "linhas",
            "celula(1, 0).alinhamento.value = 'center';"
            "celula(1, 0).alinhamento.disparar('change');",
        )

        assert saida["saiu"]["rows"][1]["cells"][0]["align"] == "center"
        assert saida["saiu"]["rows"][0]["cells"][0]["align"] == "left"

    def test_subir_linha_reordena(self, node):
        saida = _tabela(node, "linhas", "acaoDaLinha(1, 'Subir linha').disparar('click');")
        linhas = saida["saiu"]["rows"]

        assert linhas[0]["cells"][0]["content"]["value"] == "Cidade"
        assert linhas[1]["cells"][0]["content"]["value"] == "Nome"
        assert linhas[1]["cells"][1]["content"]["source"] == "convidado.nome"

    def test_acrescentar_linha_cria_uma_celula_por_coluna(self, node):
        saida = _tabela(node, "linhas", "botao('+ Linha').disparar('click');")
        linhas = saida["saiu"]["rows"]

        assert len(linhas) == 3
        assert len(linhas[2]["cells"]) == 2

    def test_remover_linha_tira_so_aquela(self, node):
        saida = _tabela(node, "linhas", "acaoDaLinha(0, 'Remover linha').disparar('click');")
        linhas = saida["saiu"]["rows"]

        assert len(linhas) == 1
        assert linhas[0]["cells"][0]["content"]["value"] == "Cidade"

    def test_acrescentar_coluna_acrescenta_celula_em_toda_linha(self, node):
        """
        A invariante que `layout_schema` cobra: uma célula por coluna em
        CADA linha. Sem isto o layout ficaria inválido e o salvamento
        seria recusado -- depois de a pessoa já ter mexido.
        """
        saida = _tabela(node, "colunas", "botao('+ Coluna').disparar('click');")

        assert len(saida["saiu"]["columns"]) == 3
        assert [len(linha["cells"]) for linha in saida["saiu"]["rows"]] == [3, 3]

    def test_remover_coluna_remove_a_celula_correspondente(self, node):
        saida = _tabela(
            node, "colunas", "acaoDaColuna(0, 'Remover coluna').disparar('click');"
        )
        linhas = saida["saiu"]["rows"]

        assert len(saida["saiu"]["columns"]) == 1
        assert [len(linha["cells"]) for linha in linhas] == [1, 1]
        # A que ficou é a SEGUNDA célula -- removeu-se a primeira coluna.
        assert linhas[0]["cells"][0]["content"]["source"] == "convidado.nome"
        assert linhas[1]["cells"][0]["content"]["value"] == "Bruxelas"

    def test_a_largura_da_coluna_e_editavel(self, node):
        saida = _tabela(
            node, "colunas",
            "var n = dom.porTag(dom.porClasse(no, 'te-coluna')[0], 'input')[0];"
            "n.value = '150'; n.disparar('change');",
        )

        assert saida["saiu"]["columns"][0]["width"] == 150
        assert saida["saiu"]["columns"][1]["width"] == 60

    def test_a_ultima_coluna_nao_pode_ser_removida(self, node):
        """Tabela sem coluna nenhuma não tem o que mostrar."""
        uma_so = {
            "columns": [{"width": 100, "align": "left"}],
            "rows": [
                {
                    "min_height": 0,
                    "cells": [
                        {
                            "content": {"kind": "text", "value": "x"},
                            "align": "left",
                            "bold": False,
                        }
                    ],
                }
            ],
        }
        saida = _tabela(node, "colunas", "", propriedades=uma_so)

        assert "Remover coluna" not in saida["botoes"]

    def test_em_leitura_nao_ha_acao(self, node):
        saida = _tabela(node, "linhas", "", editavel=False)

        assert saida["botoes"] == []

    def test_o_que_o_editor_produz_passa_no_validador_do_servidor(self, node, catalogo):
        saida = _tabela(node, "colunas", "botao('+ Coluna').disparar('click');")

        elemento = executar(
            node,
            "console.log(JSON.stringify(State.criarElemento(CAT, 'table', 'a')));",
            {"CAT": catalogo},
        )
        elemento["properties"]["columns"] = saida["saiu"]["columns"]
        elemento["properties"]["rows"] = saida["saiu"]["rows"]

        layout_schema.validate_layout({"version": 1, "elements": [elemento]})
