"""
Os dois comportamentos de tela que a revisão final de UX acrescentou --
rodados no Node, fora do navegador.

  1. **A máscara de telefone por país.** O número se formata conforme o
     país escolhido no seletor ao lado, e o exemplo do campo acompanha;
  2. **O aviso vivo da confirmação de senha.** Quem digita descobre que
     as senhas não batem ANTES de enviar, não depois de a página
     recarregar.

POR QUE ISTO É TESTADO, E NÃO SÓ A MARCAÇÃO
-------------------------------------------
Um teste de HTTP prova que o `data-telefone` está na página. Não prova
que digitar formata nada. Estes dois comportamentos são a razão de as
mudanças existirem -- e é o que quebra em silêncio numa refatoração do
`app.js`.

`static/js/app.js` é lido com `require()` de verdade: é um IIFE que só
mexe em `document`/`window`, então o stub faz as vezes dos dois antes do
`require` (mesma técnica de `letters/tests/test_app_js.py`). Sem Node
instalado, a suíte pula -- ela é Python e não ganha uma dependência
obrigatória de outra ferramenta.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
APP_JS = RAIZ / "static" / "js" / "app.js"
STUB = Path(__file__).parent / "ux_dom_stub.js"

# Os mesmos três países que o Python declara, com as mesmas máscaras
# (ver `accounts.telefone.PAISES`). Repetidos aqui de propósito: o teste
# tem de falhar se a máscara da Bélgica mudar sem ninguém perceber.
PAISES = [
    {"ddi": "+32", "mascara": "### ## ## ##", "exemplo": "470 00 00 00"},
    {"ddi": "+351", "mascara": "### ### ###", "exemplo": "912 345 678"},
    {"ddi": "+31", "mascara": "", "exemplo": "6 12345678"},
]


@pytest.fixture(scope="module")
def node():
    caminho = shutil.which("node")
    if caminho is None:
        pytest.skip("Node não está instalado neste ambiente")
    return caminho


def _caminho(p):
    return str(p).replace("\\", "/")


def executar(node, corpo, paises=None):
    script = f"""
    global.window = global;
    var Stub = require({_caminho(STUB)!r});
    global.document = Stub.criarDocumento();
    require({_caminho(APP_JS)!r});
    var PAISES = {json.dumps(paises or PAISES)};
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
    return json.loads(resultado.stdout)


# ===========================================================================
# 1. A máscara de telefone
# ===========================================================================


class TestMascaraDeTelefone:
    def test_formata_conforme_o_pais_escolhido(self, node):
        saida = executar(
            node,
            """
            var campo = Stub.criarCampoDeTelefone(PAISES, "+32", "");
            campo.numero.value = "470000000";
            document.disparar("input", campo.numero);
            console.log(JSON.stringify({ numero: campo.numero.value }));
            """,
        )

        assert saida["numero"] == "470 00 00 00"

    def test_cada_pais_tem_a_sua_forma(self, node):
        saida = executar(
            node,
            """
            var campo = Stub.criarCampoDeTelefone(PAISES, "+351", "");
            campo.numero.value = "912345678";
            document.disparar("input", campo.numero);
            console.log(JSON.stringify({ numero: campo.numero.value }));
            """,
        )

        assert saida["numero"] == "912 345 678"

    def test_trocar_de_pais_reformata_o_que_ja_estava_escrito(self, node):
        saida = executar(
            node,
            """
            var campo = Stub.criarCampoDeTelefone(PAISES, "+32", "470 00 00 00");
            campo.escolher("+351");
            document.disparar("change", campo.seletorPais);
            console.log(JSON.stringify({
              numero: campo.numero.value,
              exemplo: campo.numero.getAttribute("placeholder")
            }));
            """,
        )

        assert saida["numero"] == "470 000 000"
        assert saida["exemplo"] == "912 345 678"

    def test_pais_sem_mascara_nao_formata_nada(self, node):
        """
        Máscara errada atrapalha mais do que máscara nenhuma: onde o
        formato varia demais, o que a pessoa digitou fica como está.
        """
        saida = executar(
            node,
            """
            var campo = Stub.criarCampoDeTelefone(PAISES, "+31", "");
            campo.numero.value = "612345678";
            document.disparar("input", campo.numero);
            console.log(JSON.stringify({ numero: campo.numero.value }));
            """,
        )

        assert saida["numero"] == "612345678"

    def test_o_que_passa_do_tamanho_da_mascara_nao_e_cortado(self, node):
        """Cortar seria apagar o que a pessoa digitou."""
        saida = executar(
            node,
            """
            var campo = Stub.criarCampoDeTelefone(PAISES, "+32", "");
            campo.numero.value = "4701234567890";
            document.disparar("input", campo.numero);
            console.log(JSON.stringify({ numero: campo.numero.value }));
            """,
        )

        assert saida["numero"].startswith("470 12 34 56")
        assert saida["numero"].replace(" ", "").endswith("7890")

    def test_o_exemplo_do_pais_entra_no_campo(self, node):
        saida = executar(
            node,
            """
            var campo = Stub.criarCampoDeTelefone(PAISES, "+32", "");
            document.disparar("input", campo.numero);
            console.log(JSON.stringify({
              exemplo: campo.numero.getAttribute("placeholder")
            }));
            """,
        )

        assert saida["exemplo"] == "470 00 00 00"

    def test_campo_vazio_nao_ganha_formatacao_nenhuma(self, node):
        saida = executar(
            node,
            """
            var campo = Stub.criarCampoDeTelefone(PAISES, "+32", "");
            document.disparar("input", campo.numero);
            console.log(JSON.stringify({ numero: campo.numero.value }));
            """,
        )

        assert saida["numero"] == ""

    def test_o_que_a_pessoa_digita_com_pontuacao_e_reformatado(self, node):
        saida = executar(
            node,
            """
            var campo = Stub.criarCampoDeTelefone(PAISES, "+32", "");
            campo.numero.value = "(470) 12-34-56";
            document.disparar("input", campo.numero);
            console.log(JSON.stringify({ numero: campo.numero.value }));
            """,
        )

        assert saida["numero"] == "470 12 34 56"


# ===========================================================================
# 2. O aviso da confirmação de senha
# ===========================================================================


class TestConfirmacaoDeSenha:
    def test_senhas_iguais_avisam_que_conferem(self, node):
        saida = executar(
            node,
            """
            var par = Stub.criarParDeSenhas(document, "id_password1");
            par.senha.value = "Correto-Cavalo-7";
            par.confirmacao.value = "Correto-Cavalo-7";
            document.disparar("input", par.confirmacao);
            console.log(JSON.stringify({
              texto: par.aviso.textContent,
              classe: par.aviso.className,
              invalido: par.confirmacao.getAttribute("aria-invalid")
            }));
            """,
        )

        assert saida["texto"] == "As senhas conferem."
        assert saida["classe"] == "field-ok"
        assert saida["invalido"] is None

    def test_senhas_diferentes_avisam_que_nao_coincidem(self, node):
        saida = executar(
            node,
            """
            var par = Stub.criarParDeSenhas(document, "id_password1");
            par.senha.value = "Correto-Cavalo-7";
            par.confirmacao.value = "Correto-Cavalo-8";
            document.disparar("input", par.confirmacao);
            console.log(JSON.stringify({
              texto: par.aviso.textContent,
              classe: par.aviso.className,
              invalido: par.confirmacao.getAttribute("aria-invalid")
            }));
            """,
        )

        assert saida["texto"] == "As senhas nao coincidem."
        assert saida["classe"] == "field-error"
        assert saida["invalido"] == "true"

    def test_confirmacao_vazia_nao_avisa_nada(self, node):
        """Ninguém precisa ser corrigido antes de começar a digitar."""
        saida = executar(
            node,
            """
            var par = Stub.criarParDeSenhas(document, "id_password1");
            par.senha.value = "Correto-Cavalo-7";
            par.confirmacao.value = "";
            document.disparar("input", par.confirmacao);
            console.log(JSON.stringify({
              texto: par.aviso.textContent,
              invalido: par.confirmacao.getAttribute("aria-invalid")
            }));
            """,
        )

        assert saida["texto"] == ""
        assert saida["invalido"] is None

    def test_corrigir_a_PRIMEIRA_senha_tambem_atualiza_o_aviso(self, node):
        """
        Era o defeito clássico: a pessoa confirma, depois volta e muda a
        senha original -- e o aviso ficava mentindo até ela tocar de
        novo na confirmação.
        """
        saida = executar(
            node,
            """
            var par = Stub.criarParDeSenhas(document, "id_password1");
            par.senha.value = "Correto-Cavalo-7";
            par.confirmacao.value = "Correto-Cavalo-7";
            document.disparar("input", par.confirmacao);
            var antes = par.aviso.className;

            par.senha.value = "Outra-Senha-9";
            document.disparar("input", par.senha);
            console.log(JSON.stringify({ antes: antes, depois: par.aviso.className }));
            """,
        )

        assert saida["antes"] == "field-ok"
        assert saida["depois"] == "field-error"

    def test_mudar_a_primeira_senha_sem_confirmacao_escrita_nao_avisa(self, node):
        saida = executar(
            node,
            """
            var par = Stub.criarParDeSenhas(document, "id_password1");
            par.senha.value = "Correto-Cavalo-7";
            document.disparar("input", par.senha);
            console.log(JSON.stringify({ texto: par.aviso.textContent }));
            """,
        )

        assert saida["texto"] == ""
