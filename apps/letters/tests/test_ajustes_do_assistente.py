"""
Cinco ajustes do assistente, numa rodada só.

O QUE HAVIA, E O QUE FICOU
--------------------------
ETAPA 2  A etiqueta "> 90 dias" era um rótulo técnico ao lado da
         duração. A REGRA fica (até 90 vale, acima não passa, e a frase
         explica); a etiqueta sai.
ETAPA 2/3  No celular, tocar no campo de data não abria calendário
         nenhum: o único ponto que abria era um alvo de 40px no canto.
ETAPA 3  A mensagem "Faltam dados no seu perfil" só trazia um link de
         texto no meio do parágrafo. Ganhou um botão, sem perder o link.
ETAPA 6  A revisão encostava nas bordas do cartão no celular.
CONCLUSÃO  O anel do selo verde sangrava para fora do cartão.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a etiqueta volte** -- com este nome ou outro equivalente;
2. **Que a regra dos 90 dias saia junto com a etiqueta;**
3. **Que o botão da etapa 3 vire um caminho escrito à mão;**
4. **Que ele apareça quando não falta nada** -- ou substitua o link;
5. **Que o calendário do celular volte a depender de um alvo de 40px,**
   ou de `showPicker()`, que o Safari antigo não tem;
6. **Que o transbordo do selo seja "resolvido" com `overflow: hidden`.**
"""

import datetime
import pathlib
import re

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.letters import services
from apps.letters.rules import MAX_STAY_DAYS

pytestmark = pytest.mark.django_db

WIZARD = pathlib.Path("templates/letters/wizard.html")
LAYOUT = pathlib.Path("static/css/layout.css")
COMPONENTS = pathlib.Path("static/css/components.css")
APP_JS = pathlib.Path("static/js/app.js")


@pytest.fixture(autouse=True)
def _modelos_oficiais_prontos(modelos_oficiais_prontos):
    """Sem eles o assistente recusa criar carta."""


@pytest.fixture(autouse=True)
def _nacionalidades(nacionalidade_factory):
    nacionalidade_factory("Brasileira")
    nacionalidade_factory("Belga")


@pytest.fixture
def draft(user):
    return services.start_draft(user, "fr")


CHEGADA = timezone.localdate() + datetime.timedelta(days=30)


def sem_comentarios(css):
    """
    O CSS sem os comentários -- que aqui EXPLICAM por que certa regra não
    está lá, e fariam uma busca literal encontrar exatamente o que ela
    procura provar ausente.
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _br(data):
    return data.strftime("%d/%m/%Y")


def _url(letter, step):
    return reverse("letters:step", args=[letter.uuid, step])


def datas(dias):
    """Um intervalo de `dias` dias, contagem inclusiva."""
    return {
        "stay_arrival": _br(CHEGADA),
        "stay_departure": _br(CHEGADA + datetime.timedelta(days=dias - 1)),
    }


ETAPA_1 = {
    "guest_name": "Maria Santos da Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "15/08/1990",
    "guest_passport": "BE123456",
}


def _ate_a_etapa_2(client, letter):
    client.post(_url(letter, 1), ETAPA_1)


# ===========================================================================
# 1. Etapa 2 · a etiqueta saiu, a regra ficou
# ===========================================================================


class TestEtiquetaDeDuracao:
    def test_a_etiqueta_nao_existe_mais_na_marcacao(self):
        marcacao = WIZARD.read_text(encoding="utf-8")

        assert "data-duration-over" not in marcacao
        assert "&gt; 90" not in marcacao
        assert "> {{ max_stay_days }}" not in marcacao

    def test_o_javascript_tambem_nao_a_desenha(self):
        """
        Era o navegador que acendia a etiqueta ao digitar; sem isto ela
        voltaria a aparecer sem passar pelo servidor.
        """
        js = APP_JS.read_text(encoding="utf-8")

        assert "data-duration-over" not in js
        assert "durationOver" not in js

    def test_nenhuma_etiqueta_equivalente_ficou_no_lugar(self, auth_client, draft):
        """
        Trocar "> 90 dias" por "Excede o limite" dentro de um `tag` seria
        a mesma etiqueta com outro nome.
        """
        _ate_a_etapa_2(auth_client, draft)

        html = auth_client.post(_url(draft, 2), datas(MAX_STAY_DAYS + 1)).content.decode()
        caixa = html[html.index("data-duration-box") : html.index("data-duration-warning")]

        assert "tag" not in caixa

    @pytest.mark.parametrize("dias", [1, 90])
    def test_ate_noventa_dias_continua_valendo(self, auth_client, draft, dias):
        _ate_a_etapa_2(auth_client, draft)

        resposta = auth_client.post(_url(draft, 2), datas(dias))

        draft.refresh_from_db()
        assert resposta.status_code == 302
        assert draft.data["stay_arrival"] == CHEGADA.isoformat()

    def test_noventa_e_um_dias_nao_passa(self, auth_client, draft):
        _ate_a_etapa_2(auth_client, draft)

        resposta = auth_client.post(_url(draft, 2), datas(91))

        draft.refresh_from_db()
        assert resposta.status_code == 200
        assert "stay_departure" in resposta.context["form"].errors
        assert "stay_departure" not in draft.data

    @pytest.mark.parametrize("dias", [1, 90, 91])
    def test_a_duracao_continua_sendo_contada_e_mostrada(self, auth_client, draft, dias):
        _ate_a_etapa_2(auth_client, draft)

        resposta = auth_client.post(_url(draft, 2), datas(dias))
        if resposta.status_code == 302:
            resposta = auth_client.get(_url(draft, 2))

        assert resposta.context["duration_days"] == dias
        assert f"{dias} dia" in resposta.content.decode()

    def test_acima_do_limite_a_caixa_fica_vermelha_e_explica(self, auth_client, draft):
        _ate_a_etapa_2(auth_client, draft)

        html = auth_client.post(_url(draft, 2), datas(91)).content.decode()
        caixa = html[html.index("data-duration-box") - 120 : html.index("data-duration-box")]

        assert "is-invalid" in caixa
        assert f"não pode ultrapassar {MAX_STAY_DAYS} dias" in html


# ===========================================================================
# 2. O calendário no celular
# ===========================================================================


class TestCalendarioNoCelular:
    def test_o_campo_inteiro_abre_o_seletor_no_toque(self):
        css = COMPONENTS.read_text(encoding="utf-8")
        bloco = css[css.index("@media (pointer: coarse)") :][:320]

        assert ".date-input-picker" in bloco
        assert "width: 100%" in bloco
        assert "height: 100%" in bloco

    def test_a_regra_olha_o_dedo_e_nao_a_largura(self):
        """
        `max-width` deixaria de fora o tablet largo e pegaria o desktop
        estreito, que é para digitar.
        """
        css = COMPONENTS.read_text(encoding="utf-8")

        assert "@media (pointer: coarse)" in css

    def test_no_desktop_o_campo_continua_para_digitar(self):
        """
        A regra do toque mora DENTRO da media query: fora dela o seletor
        continua sendo o alvo de 34px no canto, e o campo aceita texto.
        """
        css = COMPONENTS.read_text(encoding="utf-8")
        antes = css[: css.index("@media (pointer: coarse)")]
        regra = antes[antes.index(".date-input .date-input-picker {") :]
        regra = regra[: regra.index("}")]

        assert "width: 34px" in regra
        assert "right: 6px" in regra

    def test_nao_ha_calendario_escrito_em_javascript(self):
        """
        O nativo funciona; um calendário próprio seria um segundo
        sistema para uma coisa que o sistema operacional já faz melhor.
        """
        js = APP_JS.read_text(encoding="utf-8")

        assert "createCalendar" not in js
        assert "datepicker" not in js.lower()

    def test_o_caminho_do_celular_nao_depende_de_showPicker(self):
        """
        `showPicker()` não existe no Safari do iOS antes da 16 -- era
        exatamente ali que o toque emudecia.
        """
        css = COMPONENTS.read_text(encoding="utf-8")
        bloco = css[css.index("@media (pointer: coarse)") :][:320]

        assert "showPicker" not in bloco

    def test_a_validacao_do_servidor_continua_de_pe(self, auth_client, draft):
        """Abrir o calendário é conforto; o limite é regra."""
        _ate_a_etapa_2(auth_client, draft)

        resposta = auth_client.post(
            _url(draft, 2), {"stay_arrival": "31/02/2026", "stay_departure": "01/03/2026"}
        )

        assert resposta.status_code == 200
        assert resposta.context["form"].errors


# ===========================================================================
# 3. Etapa 3 · o botão de completar o perfil
# ===========================================================================


class TestBotaoDeCompletarPerfil:
    @pytest.fixture
    def sem_perfil(self, user):
        """Um anfitrião a quem faltam dados obrigatórios."""
        user.phone = ""
        user.address_line1 = ""
        user.save()
        return user

    def _etapa3(self, client, letter):
        client.post(_url(letter, 1), ETAPA_1)
        client.post(_url(letter, 2), datas(15))
        return client.get(_url(letter, 3)).content.decode()

    def test_o_botao_aparece_quando_faltam_dados(self, auth_client, draft, sem_perfil):
        html = self._etapa3(auth_client, draft)

        assert "notice-acao" in html
        assert "Completar perfil" in html

    def test_o_botao_nao_substitui_o_link_que_ja_havia(self, auth_client, draft, sem_perfil):
        """
        Quem já conhecia o caminho "Editar meus dados" continua com ele:
        o botão é um atalho a mais, não uma troca.
        """
        html = self._etapa3(auth_client, draft)

        assert "host-edit-link" in html
        assert "Editar meus dados" in html

    def test_o_botao_some_quando_nao_falta_nada(self, auth_client, draft, user):
        html = self._etapa3(auth_client, draft)

        assert "notice-acao" not in html
        assert "Completar perfil" not in html

    def test_a_rota_vem_do_django_e_nao_de_um_caminho_escrito(self):
        marcacao = WIZARD.read_text(encoding="utf-8")
        bloco = marcacao[
            marcacao.index('id="perfil-incompleto"') : marcacao.index(
                'id="perfil-incompleto"'
            )
            + 900
        ]

        assert "{{ profile_url }}" in bloco
        assert "/perfil" not in bloco
        assert "/accounts/" not in bloco

    def test_o_botao_devolve_a_pessoa_para_esta_mesma_etapa(
        self, auth_client, draft, sem_perfil
    ):
        html = self._etapa3(auth_client, draft)
        trecho = html[html.index('id="perfil-incompleto"') :]
        trecho = trecho[: trecho.index("</div>")]

        assert "next=" in trecho
        assert "etapa" in trecho or "step" in trecho

    def test_o_botao_e_legivel_por_quem_nao_ve(self, auth_client, draft, sem_perfil):
        """O ícone é decorativo; o texto é que diz o que o botão faz."""
        html = self._etapa3(auth_client, draft)
        botao = html[html.index("notice-acao") :]
        botao = botao[: botao.index("</a>")]

        assert 'aria-hidden="true"' in botao
        assert "Completar perfil" in botao

    def test_a_mensagem_e_o_botao_cabem_lado_a_lado_sem_transbordar(self):
        """
        `flex-wrap` e uma base flexível no texto: em 375px o botão cai
        para a linha de baixo em vez de espremer a frase.
        """
        css = COMPONENTS.read_text(encoding="utf-8")
        bloco = css[css.index(".notice-com-acao") :][:400]

        assert "flex-wrap: wrap" in bloco
        assert "flex: 1 1" in bloco


# ===========================================================================
# 4. Etapa 6 · a revisão no celular
# ===========================================================================


class TestRevisaoNoCelular:
    def test_os_blocos_ganharam_respiro_lateral(self):
        css = LAYOUT.read_text(encoding="utf-8")
        celular = css[css.index("@media (max-width: 767px)", css.index(".review-grid")) :]
        regra = celular[celular.index(".review-block {") :][:120]

        assert "padding: 18px 16px" in regra

    def test_no_desktop_o_espacamento_nao_mudou(self):
        css = LAYOUT.read_text(encoding="utf-8")
        regra = css[css.index(".review-block {") :][:120]

        assert "padding: 20px 24px" in regra

    def test_rotulo_em_cima_e_valor_embaixo_no_celular(self):
        """Em 375px duas colunas deixavam o valor com cinco letras por linha."""
        css = LAYOUT.read_text(encoding="utf-8")
        celular = css[css.index("@media (max-width: 767px)", css.index(".review-grid")) :]
        regra = celular[celular.index(".review-dl {") :][:160]

        assert "grid-template-columns: minmax(0, 1fr)" in regra

    def test_o_conteudo_da_revisao_nao_mudou(self, auth_client, draft, user):
        """Ajuste de espaçamento não é ajuste de conteúdo."""
        auth_client.post(_url(draft, 1), ETAPA_1)
        auth_client.post(_url(draft, 2), datas(15))
        auth_client.post(_url(draft, 3), {"host_confirm": "on"})
        auth_client.post(
            _url(draft, 4), {"notice_informal": "on", "notice_prise_en_charge": "on"}
        )
        auth_client.post(_url(draft, 5), {"language": "fr"})

        html = auth_client.get(_url(draft, 6)).content.decode()

        assert "Maria Santos da Silva" in html
        assert "review-grid" in html


# ===========================================================================
# 5. Conclusão · o selo dentro do cartão
# ===========================================================================


class TestSeloDaConclusao:
    def test_o_cartao_tem_respiro_para_o_anel_no_celular(self):
        css = LAYOUT.read_text(encoding="utf-8")
        celular = css[css.index("@media (max-width: 767px)", css.index(".done-wrap")) :]
        regra = celular[celular.index(".done-card {") :][:140]

        assert "padding: 14px 0 0" in regra

    def test_o_anel_cabe_no_respiro(self):
        """
        6px de anel dentro de 14px de folga. Se alguém aumentar o anel
        sem aumentar a folga, o selo volta a sangrar.
        """
        css = LAYOUT.read_text(encoding="utf-8")
        celular = css[css.index("@media (max-width: 767px)", css.index(".done-wrap")) :]
        regra = celular[celular.index(".done-icon {") :][:220]

        assert "0 0 0 6px" in regra

    def test_nao_se_escondeu_o_transbordo(self):
        """
        `overflow: hidden` cortaria o anel em vez de dar lugar a ele --
        e o selo ficaria com um lado reto.
        """
        css = sem_comentarios(LAYOUT.read_text(encoding="utf-8"))
        celular = css[css.index("@media (max-width: 767px)", css.index(".done-wrap")) :]
        bloco = celular[: celular.index("\n}")]

        assert "overflow" not in bloco

    def test_no_desktop_o_cartao_continua_como_estava(self):
        css = LAYOUT.read_text(encoding="utf-8")
        regra = css[css.index(".done-card {") :][:140]

        assert "padding: 36px" in regra
