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


def _sem_comentarios(texto):
    """
    O código executável, sem comentários. Os cabeçalhos DESCREVEM a
    separação em relação ao editor anterior e citam os arquivos dele —
    procurar no texto cru acusaria a própria documentação.
    """
    import re

    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return re.sub(r"^\s*//.*$", "", texto, flags=re.M)


def test_nao_depende_do_editor_anterior():
    """Arquivos próprios: nenhum módulo carrega ou usa os da 4.2C."""
    antigos = ("EditorRender", "EditorDocument", "EditorHistory",
               "EditorGeometry", "js/editor/")

    for arquivo in JS.glob("*.js"):
        codigo = _sem_comentarios(arquivo.read_text(encoding="utf-8"))
        for nome in antigos:
            assert nome not in codigo, f"{arquivo.name} usa {nome}"


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
