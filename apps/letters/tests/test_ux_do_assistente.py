"""
O assistente, depois da revisão final de UX.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que sair do assistente custe o que estava digitado.** O botão de
   sair ficava na barra do alto e era um LINK: levava embora a etapa em
   curso sem avisar. Agora ele grava antes de sair;
2. **Que sair vire uma armadilha.** Etapa incompleta também sai -- com
   a mensagem dizendo que ela não foi gravada;
3. **Que a duração da estadia só avise quando já é tarde.** A caixa
   responde em cor, verde e vermelha, pela MESMA regra dos 90 dias que
   o servidor aplica;
4. **Que a cor seja a única pista.** Quem não distingue verde de
   vermelho continua lendo o número, o selo e o aviso em texto;
5. **Que escolher o idioma exija rolar a tela.** Os quatro aparecem
   juntos, com bandeira e nome -- sem as quatro frases de descrição que
   diziam a mesma coisa;
6. **Que o exemplo do passaporte sugira um número curto demais.**
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.letters.models import Letter

pytestmark = pytest.mark.django_db

# Datas relativas a hoje: a chegada nao pode ser no passado, entao uma
# data fixa no codigo venceria com o tempo.
CHEGADA = timezone.localdate() + datetime.timedelta(days=30)
PARTIDA = CHEGADA + datetime.timedelta(days=14)

# O que cada etapa precisa receber para dar por preenchida. Sao os
# mesmos de `test_navegacao`, e servem para CHEGAR na etapa que se quer
# olhar: o assistente devolve quem pula etapa para a primeira que falta
# (`services.blocking_step_before`), e um GET direto na etapa 5 sem
# passar pelas anteriores responde 302 com corpo vazio.
ETAPA_1 = {
    "guest_name": "Maria Santos da Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "15/08/1990",
    "guest_passport": "BE123456",
}
ETAPA_2 = {
    "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
    "stay_departure": PARTIDA.strftime("%d/%m/%Y"),
}
ETAPA_3 = {"host_confirm": "on"}
ETAPA_4 = {"notice_informal": "on", "notice_prise_en_charge": "on"}
ETAPAS = {1: ETAPA_1, 2: ETAPA_2, 3: ETAPA_3, 4: ETAPA_4}


@pytest.fixture(autouse=True)
def _nacionalidades(nacionalidade_factory):
    """O campo de nacionalidade nao aceita texto livre desde a Etapa 3."""
    nacionalidade_factory("Brasileira")


@pytest.fixture
def perfil_completo(user, nacionalidade_do_perfil):
    """
    A etapa do anfitriao exige o perfil preenchido -- sem isso ela nao
    deixa avancar, e as etapas 4, 5 e 6 ficam inalcancaveis.
    """
    user.birth_date = datetime.date(1990, 5, 10)
    user.document_number = "BE0123456"
    user.address_line1 = "Rue des Exemple 25"
    user.postal_code = "1200"
    user.city = "Bruxelas"
    user.phone = "+32 470 00 00 00"
    user.nationality = nacionalidade_do_perfil
    user.save()
    return user


def url(carta, etapa):
    return reverse("letters:step", kwargs={"letter_uuid": carta.uuid, "step": etapa})


@pytest.fixture
def draft(user, modelos_oficiais_prontos):
    from apps.letters import services

    return services.start_draft(user, "fr")


def preencher_ate(auth_client, carta, etapa):
    """Anda pelo assistente ate a etapa pedida, pela tela."""
    for numero in range(1, min(etapa, 5)):
        auth_client.post(url(carta, numero), ETAPAS[numero])


def html_da_etapa(auth_client, carta, etapa):
    preencher_ate(auth_client, carta, etapa)
    resposta = auth_client.get(url(carta, etapa))
    assert resposta.status_code == 200, (
        f"a etapa {etapa} redirecionou -- falta preencher alguma anterior"
    )
    return resposta.content.decode()


# ===========================================================================
# 1. "Salvar e sair"
# ===========================================================================


@pytest.mark.usefixtures("perfil_completo")
class TestSalvarESair:
    def test_a_barra_do_assistente_nao_tem_mais_botao_de_sair(self, auth_client, draft):
        """
        Ele ficava longe da ação e saía SEM gravar o que estava na tela.
        """
        html = html_da_etapa(auth_client, draft, 1)
        cabecalho = html[: html.index("<main")]

        assert "ph-x" not in cabecalho

    @pytest.mark.parametrize("etapa", (1, 2, 3, 4, 5))
    def test_toda_etapa_de_edicao_tem_o_botao(self, auth_client, draft, etapa):
        html = html_da_etapa(auth_client, draft, etapa)

        assert 'name="salvar_e_sair"' in html

    def test_e_um_submit_e_nao_um_link(self, auth_client, draft):
        """Um link levaria embora o que estava digitado."""
        html = html_da_etapa(auth_client, draft, 1)
        onde = html.index('name="salvar_e_sair"')

        assert 'type="submit"' in html[onde - 200 : onde]

    def test_grava_a_etapa_e_sai(self, auth_client, draft):
        resposta = auth_client.post(url(draft, 1), {**ETAPA_1, "salvar_e_sair": "1"})
        draft.refresh_from_db()

        assert resposta.status_code == 302
        assert reverse("letters:detail", kwargs={"letter_uuid": draft.uuid}) in resposta.url
        assert draft.data.get("guest_name") == ETAPA_1["guest_name"]

    def test_etapa_incompleta_sai_do_mesmo_jeito(self, auth_client, draft):
        """Botão de saída que prende quem clicou é pior do que botão nenhum."""
        resposta = auth_client.post(url(draft, 1), {"salvar_e_sair": "1"})

        assert resposta.status_code == 302
        assert reverse("letters:detail", kwargs={"letter_uuid": draft.uuid}) in resposta.url

    def test_etapa_incompleta_avisa_que_nao_gravou(self, auth_client, draft):
        resposta = auth_client.post(
            url(draft, 1), {"salvar_e_sair": "1"}, follow=True
        )
        textos = [str(m) for m in resposta.context["messages"]]

        assert any("não foi gravada" in t for t in textos), textos

    def test_etapa_incompleta_nao_grava_nada(self, auth_client, draft):
        auth_client.post(url(draft, 1), {"guest_name": "Meia", "salvar_e_sair": "1"})
        draft.refresh_from_db()

        assert "guest_name" not in draft.data

    def test_sem_o_botao_o_fluxo_normal_nao_muda(self, auth_client, draft):
        """Sem `salvar_e_sair`, a etapa válida continua avançando."""
        resposta = auth_client.post(url(draft, 1), ETAPA_1)

        assert resposta.url == url(draft, 2)

    def test_na_etapa_de_idioma_tambem_grava_e_sai(self, auth_client, draft):
        preencher_ate(auth_client, draft, 5)

        resposta = auth_client.post(
            url(draft, 5), {"language": "pt", "salvar_e_sair": "1"}
        )
        draft.refresh_from_db()

        assert resposta.status_code == 302
        assert draft.language == "pt"

    def test_a_revisao_oferece_sair_sem_prometer_salvar(self, auth_client, draft):
        """Na etapa 6 não há o que gravar -- então o botão não promete."""
        html = html_da_etapa(auth_client, draft, 6)

        assert 'name="salvar_e_sair"' not in html
        assert reverse("letters:detail", kwargs={"letter_uuid": draft.uuid}) in html


# ===========================================================================
# 2. A duração responde em cor
# ===========================================================================


class TestDuracaoEmCor:
    def _preencher_viagem(self, auth_client, draft, dias):
        partida = CHEGADA + datetime.timedelta(days=dias - 1)
        auth_client.post(url(draft, 1), ETAPA_1)
        auth_client.post(
            url(draft, 2),
            {
                "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
                "stay_departure": partida.strftime("%d/%m/%Y"),
            },
        )
        return auth_client.get(url(draft, 2)).content.decode()

    def test_dentro_do_prazo_fica_verde(self, auth_client, draft):
        html = self._preencher_viagem(auth_client, draft, 15)

        assert "duration-box" in html
        assert "is-ok" in html
        assert "is-invalid" not in html[html.index("duration-box") - 60 :][:200]

    def test_sem_datas_a_caixa_nao_tem_cor_nenhuma(self, auth_client, draft):
        auth_client.post(url(draft, 1), ETAPA_1)
        html = auth_client.get(url(draft, 2)).content.decode()
        onde = html.index("duration-box")

        assert "is-ok" not in html[onde - 60 : onde + 40]
        assert "is-invalid" not in html[onde - 60 : onde + 40]

    def test_a_cor_nao_e_a_unica_pista(self, auth_client, draft):
        """Quem não distingue verde de vermelho lê o número, escrito."""
        html = self._preencher_viagem(auth_client, draft, 15)

        assert "15 dias" in html

    def test_o_limite_vem_da_regra_do_servidor(self, auth_client, draft):
        """
        Não é um 90 escrito no template: sai de `apps/letters/rules.py`,
        pela mesma constante que recusa a estadia longa demais.
        """
        from apps.letters import rules

        auth_client.post(url(draft, 1), ETAPA_1)
        html = auth_client.get(url(draft, 2)).content.decode()

        assert f'data-max-stay="{rules.MAX_STAY_DAYS}"' in html


# ===========================================================================
# 3. O idioma em botões visuais
# ===========================================================================


@pytest.mark.usefixtures("perfil_completo")
class TestIdiomaVisual:
    def test_os_quatro_ficam_numa_grade(self, auth_client, draft):
        html = html_da_etapa(auth_client, draft, 5)

        assert "lang-grid" in html
        assert html.count("lang-card") >= 4

    def test_cada_botao_tem_bandeira_e_nome(self, auth_client, draft):
        html = html_da_etapa(auth_client, draft, 5)

        assert "lang-flag" in html
        assert "lang-card-name" in html

    def test_a_descricao_repetida_saiu(self, auth_client, draft):
        """
        Quatro frases dizendo a mesma coisa com outras palavras -- e
        eram elas que empurravam o quarto idioma para fora da tela do
        celular.
        """
        html = html_da_etapa(auth_client, draft, 5)

        assert "lang-card-text" not in html

    def test_o_idioma_indisponivel_continua_dizendo_que_esta(self, auth_client, draft):
        """Essa frase INFORMA -- não há como deduzi-la da bandeira."""
        from apps.doctemplates.models import DocumentTemplate

        DocumentTemplate.objects.filter(is_system=True, language="nl").update(
            is_active=False
        )

        html = html_da_etapa(auth_client, draft, 5)

        assert "Ainda não disponível" in html
        assert "is-unavailable" in html

    def test_escolher_continua_funcionando(self, auth_client, draft):
        preencher_ate(auth_client, draft, 5)

        auth_client.post(url(draft, 5), {"language": "pt"})
        draft.refresh_from_db()

        assert draft.language == "pt"

    def test_o_escolhido_chega_marcado(self, auth_client, draft):
        html = html_da_etapa(auth_client, draft, 5)
        onde = html.index('value="fr"')

        assert "checked" in html[onde : onde + 60]


# ===========================================================================
# 4. O exemplo do passaporte
# ===========================================================================


class TestExemploDoPassaporte:
    def test_tem_duas_letras_e_seis_digitos(self, auth_client, draft):
        html = html_da_etapa(auth_client, draft, 1)

        assert 'placeholder="YY123456"' in html

    def test_o_exemplo_antigo_saiu(self, auth_client, draft):
        html = html_da_etapa(auth_client, draft, 1)

        assert "YY0000" not in html

    def test_o_schema_no_banco_acompanhou(self, modelos_oficiais_prontos):
        """
        Não bastava mudar o módulo: `semear_carta_convite` usa
        `get_or_create`, então um banco já instalado continuaria com o
        exemplo antigo. Por isso a mudança entrou por migração.
        """
        from apps.doctemplates.models import DocumentTemplate

        conferidos = 0
        for modelo in DocumentTemplate.objects.filter(is_system=True):
            # Nem todo modelo de sistema é uma Carta Convite, e um
            # `field_schema` de outra forma não tem campo nenhum para
            # conferir -- ignorá-lo é diferente de não conferir nada, e
            # é por isso que o contador existe no fim.
            bruto = (modelo.field_schema or {}).get("fields") or []
            campos = [c for c in bruto if isinstance(c, dict)]
            campo = next((c for c in campos if c.get("key") == "guest_passport"), None)
            if campo is None:
                continue
            assert campo["placeholder"] == "YY123456", modelo.slug
            conferidos += 1

        assert conferidos, "nenhum modelo oficial trouxe o campo do passaporte"

    def test_o_passaporte_nao_e_campo_numerico(self, auth_client, draft):
        """Passaporte tem letras -- `type="number"` as comeria."""
        html = html_da_etapa(auth_client, draft, 1)
        onde = html.index('name="guest_passport"')

        assert 'type="number"' not in html[onde - 200 : onde + 200]

    def test_o_passaporte_com_letras_e_zero_a_esquerda_e_aceito(self, auth_client, draft):
        """
        Duas letras e um zero logo depois: é o que `type="number"`
        comeria.
        """
        auth_client.post(url(draft, 1), {**ETAPA_1, "guest_passport": "BE0123456"})
        draft.refresh_from_db()

        assert draft.data.get("guest_passport") == "BE0123456"


# ===========================================================================
# 5. A etapa do anfitrião, no celular
# ===========================================================================


@pytest.mark.usefixtures("perfil_completo")
class TestEtapaDoAnfitriaoNoCelular:
    def _regra(self, trecho):
        import pathlib
        import re

        css = pathlib.Path("static/css/layout.css").read_text(encoding="utf-8")
        blocos = re.findall(r"@media \(max-width: 767px\) \{(.*?)\n\}", css, re.S)
        return "\n".join(b for b in blocos if trecho in b)

    def test_os_dados_de_leitura_deitam(self):
        """
        Eram uma parede de caixas cinzentas de 48px, uma embaixo da
        outra. Deitados, a etapa inteira cabe na tela.
        """
        regra = self._regra(".input.is-readonly")

        assert "flex-direction: row" in regra
        assert "text-align: right" in regra

    def test_continuam_sendo_so_leitura(self, auth_client, draft):
        """O desenho mudou; a regra não: estes dados vêm do perfil."""
        html = html_da_etapa(auth_client, draft, 3)

        assert "is-readonly" in html
        assert 'name="full_name"' not in html


# ===========================================================================
# 6. Nada disso quebrou o assistente
# ===========================================================================


@pytest.mark.usefixtures("perfil_completo")
class TestOAssistenteContinuaInteiro:
    @pytest.mark.parametrize("etapa", (1, 2, 3, 4, 5, 6))
    def test_toda_etapa_responde(self, auth_client, draft, etapa):
        preencher_ate(auth_client, draft, etapa)

        assert auth_client.get(url(draft, etapa)).status_code == 200

    def test_o_rascunho_continua_sendo_do_dono(self, client, other_user, draft):
        client.force_login(other_user)

        resposta = client.get(url(draft, 1))

        assert resposta.status_code in (302, 403, 404)

    def test_o_caminho_inteiro_continua_chegando_na_revisao(self, auth_client, draft):
        """Nada disto quebrou o assistente de ponta a ponta."""
        preencher_ate(auth_client, draft, 5)
        auth_client.post(url(draft, 5), {"language": "fr"})

        resposta = auth_client.get(url(draft, 6))

        assert resposta.status_code == 200
        assert Letter.objects.filter(pk=draft.pk).exists()
