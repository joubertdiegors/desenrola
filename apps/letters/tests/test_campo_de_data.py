"""
O campo de data: marcação, CSS e o contrato com o JavaScript.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
Que volte o defeito que ela nasceu corrigindo: **clicar num
`input[type=date]` não abre o seletor no Chrome nem no Edge**. Lá só o
`::-webkit-calendar-picker-indicator` abre, e ele ocupa uma fração do
canto direito. Enquanto o ícone era um `<span>` decorativo com o input de
data por cima, o clique quase sempre não fazia nada.

A correção tem três peças, e cada uma tem um teste aqui:

  1. o ícone é um `<button type="button">` que recebe o clique;
  2. o `<input type="date">` continua existindo (é onde o navegador
     ancora o calendário) mas sai do caminho do teclado;
  3. o indicador nativo cobre o input inteiro, no CSS.

O QUE ESTA SUÍTE **NÃO** PODE AFIRMAR
-------------------------------------
Que o calendário abriu. Isso é o navegador decidindo, e depende de
versão, de plataforma e da ativação do usuário -- não há teste de
servidor que responda por isso. Aqui se cobra o CONTRATO: a marcação que
o script espera, a regra que o Chromium precisa, e os caminhos de código
que o script mantém. A abertura em si se valida à mão.
"""

import datetime
import pathlib

import pytest
from django.urls import reverse
from freezegun import freeze_time

from apps.letters import services

pytestmark = pytest.mark.django_db

RAIZ = pathlib.Path(__file__).resolve().parents[3]
APP_JS = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")
COMPONENTS_CSS = (RAIZ / "static" / "css" / "components.css").read_text(encoding="utf-8")

# O RELOGIO DESTE MODULO E PARADO
#
# Todo teste daqui compara uma data que a APLICACAO calcula na requisicao
# com uma data que o TESTE ja conhece. Com o relogio real, uma suite longa
# que atravessasse a meia-noite faria a aplicacao responder "amanha" para
# um teste que tinha guardado "hoje" -- falha sem defeito nenhum.
#
# Congela o modulo INTEIRO, e nao so os testes que citam HOJE: CHEGADA e
# PARTIDA sao futuras em relacao a HOJE, e a regra de chegada nao
# retroativa as recusaria se o resto do modulo ficasse no relogio real.
#
# Meio-dia, e nao meia-noite: com TIME_ZONE = "Europe/Brussels" a
# conversao de fuso perto da meia-noite mudaria o DIA -- seria trocar uma
# dependencia do relogio por outra.
HOJE = datetime.date(2026, 3, 17)


@pytest.fixture(autouse=True)
def _relogio_parado():
    with freeze_time("2026-03-17 12:00:00"):
        yield

# O mínimo para a etapa 1 passar e a 2 abrir.
PASSO_1 = {
    "guest_name": "Maria Santos da Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "22/07/1990",
    "guest_passport": "YY0000",
}


@pytest.fixture(autouse=True)
def _modelos_oficiais_prontos(modelos_oficiais_prontos):
    """O assistente só monta o formulário com os modelos oficiais prontos."""


@pytest.fixture(autouse=True)
def _nacionalidade(nacionalidade_factory):
    nacionalidade_factory("Brasileira", name_fr="Brésilienne")


@pytest.fixture
def draft(user):
    return services.start_draft(user, "fr")


def _step(letter, numero):
    return reverse("letters:step", args=[letter.uuid, numero])


def _bloco_do_campo(html, chave):
    """O trecho de HTML em volta de um campo -- para não afirmar sobre a
    página inteira quando a pergunta é sobre um campo só."""
    inicio = html.index(chave)
    return html[max(0, inicio - 400) : inicio + 900]


# ===========================================================================
# 1. A marcação
# ===========================================================================


class TestMarcacao:
    def test_o_input_date_nativo_continua_existindo(self, auth_client, draft):
        """
        Não é um campo de texto disfarçado, e não foi substituído por
        biblioteca: é o controle nativo, e é nele que o navegador ancora
        o calendário. Por isso não pode ser `display:none`.
        """
        html = auth_client.get(_step(draft, 1)).content.decode()

        assert '<input type="date" class="date-input-picker"' in html

    def test_o_icone_e_um_botao(self, auth_client, draft):
        html = auth_client.get(_step(draft, 1)).content.decode()
        bloco = _bloco_do_campo(html, "date-input-open")

        assert '<button type="button"' in bloco
        assert "date-input-open" in bloco

    def test_o_botao_nao_envia_o_formulario(self, auth_client, draft):
        """
        `type="button"` explícito: dentro de um `<form>`, um botão sem
        type é `submit` -- clicar no calendário enviaria a etapa pela
        metade.
        """
        html = auth_client.get(_step(draft, 1)).content.decode()
        inicio = html.index("date-input-open")
        abertura = html.rindex("<button", 0, inicio)

        assert html[abertura:].startswith('<button type="button"')

    def test_o_botao_tem_rotulo_acessivel(self, auth_client, draft):
        """O ícone é decorativo; quem tem nome é o botão."""
        html = auth_client.get(_step(draft, 1)).content.decode()
        bloco = _bloco_do_campo(html, "date-input-open")

        assert "aria-label=" in bloco
        assert 'class="ph ph-calendar-blank" aria-hidden="true"' in bloco

    def test_o_input_date_sai_do_caminho_do_teclado(self, auth_client, draft):
        """
        Quem carrega a interação de teclado é o botão (Enter e Espaço já
        disparam `click` num `<button>`). Deixar os dois focáveis seria
        uma parada de tabulação a mais para a mesma ação.
        """
        html = auth_client.get(_step(draft, 1)).content.decode()
        inicio = html.index("date-input-picker")
        picker = html[inicio : html.index("date-input-open", inicio)]

        assert 'tabindex="-1"' in picker

    def test_o_campo_digitavel_continua_ao_lado(self, auth_client, draft):
        """Calendário e digitação convivem -- um não substitui o outro."""
        html = auth_client.get(_step(draft, 1)).content.decode()

        assert "data-date-input" in html
        assert 'inputmode="numeric"' in html

    def test_o_perfil_usa_a_mesma_marcacao(self, auth_client):
        """
        A marcação é duplicada em `accounts/profile.html`. Se as duas
        cópias divergirem, o calendário do perfil volta a não abrir --
        e é este teste que avisa.
        """
        html = auth_client.get(reverse("accounts:profile")).content.decode()
        bloco = _bloco_do_campo(html, "date-input-open")

        assert '<input type="date" class="date-input-picker"' in html
        assert 'tabindex="-1"' in html[html.index("date-input-picker") :][:200]
        assert '<button type="button"' in bloco
        assert "aria-label=" in bloco


# ===========================================================================
# 2. O formato — o que se vê e o que se guarda
# ===========================================================================


class TestFormato:
    def test_o_campo_visivel_e_dd_mm_aaaa(self, auth_client, draft):
        html = auth_client.get(_step(draft, 1)).content.decode()

        assert 'placeholder="DD/MM/AAAA"' in html
        assert 'maxlength="10"' in html

    def test_um_valor_ja_gravado_reaparece_em_dd_mm_aaaa(self, auth_client, draft):
        """
        O banco guarda ISO; a tela mostra dd/mm/aaaa. É o
        `_RobustDateInput` que garante isso -- inclusive quando o valor
        vinculado é a string de um POST, e não um `date`.
        """
        services.save_step_data(
            draft, 1, {"guest_birth_date": datetime.date(1990, 7, 22)}
        )

        html = auth_client.get(_step(draft, 1)).content.decode()

        assert 'value="22/07/1990"' in html
        assert 'value="1990-07-22"' not in html

    def test_o_que_fica_guardado_continua_iso(self, auth_client, draft):
        services.save_step_data(
            draft, 1, {"guest_birth_date": datetime.date(1990, 7, 22)}
        )
        draft.refresh_from_db()

        assert draft.data["guest_birth_date"] == "1990-07-22"

    def test_o_servidor_aceita_dd_mm_aaaa_enviado_pelo_campo(self, auth_client, draft):
        """Sem JavaScript o campo é digitado e enviado como está."""
        auth_client.post(
            _step(draft, 1),
            {
                "guest_name": "Maria Santos da Silva",
                "guest_nationality": "Brasileira",
                "guest_birth_date": "22/07/1990",
                "guest_passport": "YY0000",
            },
        )
        draft.refresh_from_db()

        assert draft.data["guest_birth_date"] == "1990-07-22"

    def test_a_data_minima_vai_junto_onde_ha_regra(self, auth_client, draft):
        """
        É o que o calendário nativo usa para fechar os dias anteriores.
        A regra de verdade continua no servidor.
        """
        auth_client.post(_step(draft, 1), PASSO_1)  # a etapa 2 exige a 1 válida

        html = auth_client.get(_step(draft, 2)).content.decode()

        assert f'data-date-min="{HOJE.isoformat()}"' in html

    def test_e_nao_vai_onde_nao_ha(self, auth_client, draft):
        """Data de nascimento é o oposto: só pode ser no passado."""
        html = auth_client.get(_step(draft, 1)).content.decode()
        bloco = _bloco_do_campo(html, "guest_birth_date")

        assert "data-date-min" not in bloco


# ===========================================================================
# 3. O CSS que o Chromium precisa
# ===========================================================================


class TestCss:
    def test_o_indicador_nativo_cobre_o_input_inteiro(self):
        """
        A regra que faltava, e que é a causa do defeito original: sem
        ela o `::-webkit-calendar-picker-indicator` ocupa uma fração do
        canto direito, e é o único ponto do input que abre o seletor no
        Chrome e no Edge.
        """
        assert ".date-input-picker::-webkit-calendar-picker-indicator" in COMPONENTS_CSS

        inicio = COMPONENTS_CSS.index("::-webkit-calendar-picker-indicator")
        regra = COMPONENTS_CSS[inicio : COMPONENTS_CSS.index("}", inicio)]

        assert "position: absolute" in regra
        assert "inset: 0" in regra
        assert "width: 100%" in regra
        assert "height: 100%" in regra
        assert "opacity: 0" in regra
        assert "cursor: pointer" in regra

    def test_o_botao_fica_por_cima_do_input_de_data(self):
        """
        Se o input de data voltar a ficar por cima, ele engole o clique e
        o botão nunca dispara -- exatamente o defeito de antes.
        """
        picker = COMPONENTS_CSS[
            COMPONENTS_CSS.index(".date-input .date-input-picker {") :
        ]
        picker = picker[: picker.index("}")]
        botao = COMPONENTS_CSS[COMPONENTS_CSS.index(".date-input .date-input-open {") :]
        botao = botao[: botao.index("}")]

        assert "z-index: 1" in picker
        assert "z-index: 2" in botao

    def test_o_input_de_data_nao_pode_ser_escondido(self):
        """
        `display:none` tiraria do navegador o elemento ao qual ele ancora
        o calendário. Transparente sim, ausente não.
        """
        picker = COMPONENTS_CSS[
            COMPONENTS_CSS.index(".date-input .date-input-picker {") :
        ]
        picker = picker[: picker.index("}")]

        assert "opacity: 0" in picker
        assert "display: none" not in picker
        assert "visibility: hidden" not in picker

    def test_o_foco_do_botao_continua_visivel(self):
        """Estilo de foco acessível não se remove."""
        assert ".date-input .date-input-open:focus-visible" in COMPONENTS_CSS

        inicio = COMPONENTS_CSS.index(".date-input .date-input-open:focus-visible")
        regra = COMPONENTS_CSS[inicio : COMPONENTS_CSS.index("}", inicio)]

        assert "outline:" in regra


# ===========================================================================
# 4. O contrato com o JavaScript
# ===========================================================================


class TestContratoDoScript:
    """
    O comportamento fica no navegador, mas o CONTRATO entre a marcação e
    o script é conferível aqui: as classes que ele escuta, os `data-*`
    que ele lê, e os caminhos de código que ele mantém.
    """

    def _corpo(self, nome):
        """O corpo de uma função de `app.js`, até a próxima do mesmo nível."""
        inicio = APP_JS.index(nome)
        return APP_JS[inicio : APP_JS.index("\n  }", inicio)]

    def test_o_script_escuta_o_clique_no_botao(self):
        assert 'closest(".date-input-open")' in APP_JS

    def test_o_clique_tenta_o_showPicker(self):
        assert "showPicker()" in APP_JS

    def test_o_showPicker_e_verificado_antes_de_ser_chamado(self):
        """Não existe no Safari do iOS até a 15 nem em navegadores antigos."""
        assert 'typeof picker.showPicker === "function"' in APP_JS

    def test_o_showPicker_e_chamado_dentro_de_try_catch(self):
        """
        Ele exige ativação do usuário e pode recusar mesmo dentro de um
        clique (num iframe sem permissão, por exemplo). Recusar não pode
        derrubar a página.
        """
        # Do `if` que checa o suporte ate a chamada: o `try` tem de estar
        # no meio. Uma janela de tamanho fixo nao serve -- o comentário
        # entre os dois pode crescer.
        guarda = APP_JS.index('typeof picker.showPicker === "function"')
        chamada = APP_JS.index("picker.showPicker();", guarda)

        assert "try {" in APP_JS[guarda:chamada]

    def test_ha_caminho_alternativo_quando_o_showPicker_nao_existe(self):
        """
        Sem `showPicker()`, levar o foco ao próprio campo de data é o que
        abre a roda do sistema no iOS.
        """
        trecho = APP_JS[APP_JS.index('closest(".date-input-open")') :][:1800]

        assert "picker.focus()" in trecho

    def test_a_sincronizacao_campo_para_picker_continua(self):
        """
        Antes de abrir, o seletor recebe a data que já está digitada
        (convertida para ISO) e a data mínima do campo.
        """
        corpo = self._corpo("function prepararPicker(")

        assert "toIso(input.value)" in corpo
        assert 'getAttribute("data-date-min")' in corpo
        assert "picker.min = min" in corpo

    def test_a_sincronizacao_picker_para_campo_continua(self):
        """
        Ao escolher no calendário, o campo visível volta a dd/mm/aaaa --
        e o script avisa a página, senão a duração e o botão da etapa
        ficariam com o estado antigo.
        """
        inicio = APP_JS.index('matches(".date-input-picker")')
        trecho = APP_JS[inicio : inicio + 700]

        assert "fromIso(picker.value)" in trecho
        assert 'dispatchEvent(new Event("input"' in trecho

    def test_o_pointerdown_nao_assume_que_o_alvo_tem_closest(self):
        """
        `pointerdown` dispara com alvos que nem sempre são Element. Sem a
        guarda, uma exceção derrubaria o resto do tratamento.
        """
        inicio = APP_JS.index('addEventListener("pointerdown"')
        trecho = APP_JS[inicio : inicio + 400]

        assert "event.target.closest && event.target.closest" in trecho

    def test_a_mascara_continua_no_campo_visivel(self):
        assert 'matches("[data-date-input]")' in APP_JS
        assert "function maskDate(" in APP_JS

    def test_o_script_nao_carrega_biblioteca_de_calendario(self):
        """
        A decisão é usar o seletor NATIVO. Nenhuma dependência externa
        entrou por aqui.
        """
        for nome in ("flatpickr", "datepicker", "pikaday", "air-datepicker"):
            assert nome not in APP_JS.lower()
