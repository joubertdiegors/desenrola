"""
Reatividade do botão "Próxima etapa" (`static/js/app.js`), fora do
navegador.

A validação manual encontrou: erro do servidor → botão desabilitado →
pessoa corrige o campo → botão continua desabilitado até um segundo
clique. A causa era o campo de chegada (válido, não tocado de novo)
reexibindo em ISO em vez de dd/mm/aaaa depois de um erro em OUTRO campo
da mesma etapa -- corrigido em `apps.letters.forms._RobustDateInput` e
removendo a conversão para ISO antes do envio (o pré-submit forçava
exatamente esse formato). Este teste cobre a METADE do lado do
navegador: dado que um campo obrigatório passa a estar preenchido e
válido, o botão reavalia sozinho no evento `input`, sem precisar de um
segundo clique -- o mesmo caminho (`document.addEventListener("input",
...)`) que reavalia depois de QUALQUER correção, data ou não.

`static/js/app.js` é lido com `require()` de verdade no Node (não há
`module.exports`: é um IIFE que só mexe em `document`/`window`, então o
stub em `wizard_dom_stub.js` faz as vezes dos dois antes do `require`).
Sem Node instalado, a suíte pula -- ela é Python e não ganha uma
dependência obrigatória de outra ferramenta.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
APP_JS = RAIZ / "static" / "js" / "app.js"
STUB = Path(__file__).parent / "wizard_dom_stub.js"


def _caminho(p):
    return str(p).replace("\\", "/")


@pytest.fixture(scope="module")
def node():
    caminho = shutil.which("node")
    if caminho is None:
        pytest.skip("Node não está instalado neste ambiente")
    return caminho


def _executar_cenario(node, corpo):
    """
    Carrega `app.js` com `document`/`window` stubados e roda `corpo`, que
    tem `Stub`, `chegada`, `partida`, `form` e `botao` prontos: os dois
    campos de data da etapa "Viagem", a chegada já válida (13/09/2026) e
    a partida vazia (obrigatório sem preencher -- o estado logo após um
    erro do servidor nessa etapa).
    """
    script = f"""
    global.window = global;
    var Stub = require({_caminho(STUB)!r});
    global.document = Stub.criarBarramentoDeEventos();
    require({_caminho(APP_JS)!r});

    var chegada = Stub.criarCampoDeData("stay_arrival", "13/09/2026");
    var partida = Stub.criarCampoDeData("stay_departure", "");
    var botao = Stub.criarBotaoDeEtapa();
    var form = Stub.criarFormularioDeEtapa("viagem", [chegada, partida], botao);
    chegada.form = form;
    partida.form = form;

    {corpo}
    """
    resultado = subprocess.run(
        [node, "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if resultado.returncode != 0:
        raise AssertionError(f"Node falhou:\n{resultado.stderr}")
    return resultado.stdout.strip()


class TestBotaoReavaliaSemSegundoClique:
    def test_campo_obrigatorio_vazio_deixa_o_botao_desabilitado(self, node):
        """O estado logo após o erro: partida obrigatória e vazia."""
        saida = _executar_cenario(
            node,
            'document.disparar("input", chegada);'
            'console.log(botao.classList.contains("is-disabled"));',
        )
        assert saida == "true"

    def test_corrigir_o_campo_habilita_o_botao_sem_segundo_clique(self, node):
        """
        A correção: a pessoa digita a partida. O MESMO evento "input" que
        o navegador dispara sozinho ao digitar já reavalia o botão --
        nenhuma chamada extra, nenhum segundo clique em "Avançar".
        """
        saida = _executar_cenario(
            node,
            'document.disparar("input", chegada);'  # estado inicial: desabilitado
            'partida.value = "20/09/2026";'
            'document.disparar("input", partida);'  # a correcao
            'console.log(botao.classList.contains("is-disabled"));',
        )
        assert saida == "false"

    def test_corrigir_com_data_invalida_mantem_o_botao_desabilitado(self, node):
        """Uma "correção" que não é uma data válida não engana o botão."""
        saida = _executar_cenario(
            node,
            'document.disparar("input", chegada);'
            'partida.value = "31/02/2026";'  # fevereiro nao tem dia 31
            'document.disparar("input", partida);'
            'console.log(botao.classList.contains("is-disabled"));',
        )
        assert saida == "true"

    def test_evento_change_tambem_reavalia(self, node):
        """O calendário nativo dispara `change`, não `input` -- os dois
        caminhos têm de reavaliar o botão."""
        saida = _executar_cenario(
            node,
            'document.disparar("input", chegada);'
            'partida.value = "20/09/2026";'
            'document.disparar("change", partida);'
            'console.log(botao.classList.contains("is-disabled"));',
        )
        assert saida == "false"

    def test_um_campo_em_iso_mantem_o_botao_desabilitado_mesmo_corrigindo_o_outro(
        self, node
    ):
        """
        Reproduz o mecanismo exato do bug relatado na validação manual:
        se ALGUM dia a chegada reexibir em ISO em vez de dd/mm/aaaa (o
        formato que este projeto reservou para persistência, nunca para
        tela -- ver `apps.letters.forms._RobustDateInput`), corrigir só a
        partida não é suficiente. `refreshStepButton` olha TODOS os
        campos obrigatórios a cada evento, não só o que mudou -- é por
        isso que a chegada continuar errada prende o botão mesmo depois
        da pessoa corrigir a partida.
        """
        saida = _executar_cenario(
            node,
            'chegada.value = "2026-09-13";'  # nunca deveria chegar assim (ver forms.py)
            'partida.value = "20/09/2026";'
            'document.disparar("input", partida);'
            'console.log(botao.classList.contains("is-disabled"));',
        )
        assert saida == "true"
