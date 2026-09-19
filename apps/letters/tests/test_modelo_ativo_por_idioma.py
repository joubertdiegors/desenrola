"""
O assistente usa o modelo ATIVO do idioma -- qualquer que ele seja.

O BUG QUE ESTA SUITE FECHA
--------------------------
A resolucao do documento era pelo SLUG do oficial (`carta-convite-fr`).
Consequencia que so aparecia no uso real: o administrador preparava um
frances novo, ativava, desativava o oficial -- e o assistente passava a
dizer "Ainda nao disponivel", como se o idioma inteiro tivesse sumido.
A biblioteca mostrava um frances ativo; a carta nao saia. A tela e o
sistema discordavam.

Agora quem responde e `doctemplates.services.ativacao`: cada idioma tem
UM modelo ativo, oficial ou copia, e e ele que emite a carta.

AS TRES RESPOSTAS, QUE SAO DIFERENTES
-------------------------------------
  * ha um ativo e ele esta pronto   -> emite com ELE;
  * ha modelos, nenhum ativo/pronto -> `None`: "ainda nao disponivel",
                                       e NENHUMA carta e criada;
  * o idioma nao tem modelo nenhum  -> excecao: e erro de
                                       infraestrutura, a semeadura
                                       sempre cria os quatro oficiais.

O outro lado da regra -- o interruptor, a troca e o indice do banco --
esta em `apps/doctemplates/tests/test_ativacao.py`.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.doctemplates.models import DocumentTemplate
from apps.doctemplates.services import ativacao
from apps.doctemplates.services.biblioteca import slug_oficial
from apps.doctemplates.services.duplicacao import duplicar_modelo
from apps.letters import services
from apps.letters.models import DefaultDocumentTemplateMissingError, Letter

pytestmark = pytest.mark.django_db

IDIOMAS = ("pt", "fr", "nl", "en")

DADOS_ETAPA_1 = {
    "guest_name": "Maria Santos da Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "15/08/1990",
    "guest_passport": "FA123456",
}
CHEGADA = timezone.localdate() + datetime.timedelta(days=30)
PARTIDA = CHEGADA + datetime.timedelta(days=15)


@pytest.fixture(autouse=True)
def _modelos_oficiais_prontos(modelos_oficiais_prontos):
    """Os quatro oficiais com o logo materializado -- o estado pós-deploy."""


@pytest.fixture(autouse=True)
def _nacionalidades(nacionalidade_factory):
    nacionalidade_factory("Brasileira")


def oficial(idioma):
    return DocumentTemplate.objects.get(slug=slug_oficial(idioma))


def copia_pronta(idioma, nome="Revisado"):
    """
    Uma cópia do oficial daquele idioma: mesmo desenho, mesmo logo,
    mesmos campos -- e INATIVA, como toda cópia nasce.
    """
    return duplicar_modelo(oficial(idioma), f"{nome} {idioma.upper()}")


def _passo(carta, numero):
    return reverse("letters:step", args=[carta.uuid, numero])


def _ate_a_etapa_5(client, carta):
    client.post(_passo(carta, 1), DADOS_ETAPA_1)
    client.post(_passo(carta, 2), {
        "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
        "stay_departure": PARTIDA.strftime("%d/%m/%Y"),
    })
    client.post(_passo(carta, 3), {"host_confirm": "on"})
    client.post(_passo(carta, 4), {"notice_informal": "on", "notice_prise_en_charge": "on"})


# ===========================================================================
# 1. A resolucao: o ATIVO, e nao o oficial
# ===========================================================================


class TestQualModeloOAssistenteUsa:
    @pytest.mark.parametrize("idioma", IDIOMAS)
    def test_com_so_o_oficial_ativo_e_ele_que_emite(self, idioma):
        assert services.active_document_template(idioma) == oficial(idioma)

    @pytest.mark.parametrize("idioma", IDIOMAS)
    def test_ativar_uma_copia_passa_a_emitir_pela_copia(self, idioma):
        copia = copia_pronta(idioma)

        ativacao.ativar(copia)

        assert services.active_document_template(idioma) == copia

    @pytest.mark.parametrize("idioma", IDIOMAS)
    def test_desativar_o_oficial_com_outra_ativa_nao_derruba_o_idioma(self, idioma):
        """
        O BUG, por extenso: com outra ativa, desativar o oficial é uma
        troca -- não o fim do idioma.
        """
        copia = copia_pronta(idioma)
        ativacao.ativar(copia)  # já desativa o oficial

        assert oficial(idioma).is_active is False
        assert services.active_document_template(idioma) == copia
        assert idioma in services.available_languages()

    def test_sem_nenhum_ativo_o_idioma_fica_indisponivel(self):
        ativacao.desativar(oficial("fr"))

        assert services.active_document_template("fr") is None
        assert "fr" not in services.available_languages()

    def test_sem_nenhum_ativo_nao_levanta_excecao(self):
        """
        "Nenhum ativo" é uma decisão administrativa legítima, não um
        banco quebrado: o assistente avisa, e não explode.
        """
        ativacao.desativar(oficial("fr"))

        assert services.active_document_template("fr") is None  # não levanta

    def test_idioma_sem_modelo_nenhum_continua_sendo_erro_de_infraestrutura(self):
        DocumentTemplate.objects.filter(language="fr").delete()

        with pytest.raises(DefaultDocumentTemplateMissingError, match=slug_oficial("fr")):
            services.active_document_template("fr")

    def test_a_ativa_precisa_estar_PRONTA_e_nao_so_ativa(self):
        """
        Ativa mas sem desenho não é documento: emitir com ela daria uma
        carta que falharia na finalização.
        """
        copia = copia_pronta("fr")
        DocumentTemplate.objects.filter(pk=copia.pk).update(layout={})
        ativacao.ativar(DocumentTemplate.objects.get(pk=copia.pk))

        assert services.active_document_template("fr") is None
        assert "fr" not in services.available_languages()

    def test_trocar_o_frances_nao_toca_nos_outros_idiomas(self):
        ativacao.ativar(copia_pronta("fr"))

        for idioma in ("pt", "nl", "en"):
            assert services.active_document_template(idioma) == oficial(idioma)


# ===========================================================================
# 2. A carta nasce ligada ao ativo
# ===========================================================================


class TestACartaNasceLigadaAoAtivo:
    def test_start_draft_usa_a_copia_ativa(self, user):
        copia = copia_pronta("fr")
        ativacao.ativar(copia)

        carta = services.start_draft(user, "fr")

        assert carta.document_template_id == copia.pk

    def test_sem_ativo_nenhuma_carta_e_criada(self, user):
        ativacao.desativar(oficial("en"))

        assert services.start_draft(user, "en") is None
        assert not Letter.objects.filter(user=user).exists()

    def test_trocar_de_idioma_na_etapa_5_pega_o_ativo_daquele_idioma(self, user):
        copia = copia_pronta("nl")
        ativacao.ativar(copia)
        carta = services.start_draft(user, "en")

        assert services.change_language(carta, "nl") is True

        carta.refresh_from_db()
        assert carta.document_template_id == copia.pk

    def test_trocar_para_um_idioma_sem_ativo_e_recusado(self, user):
        carta = services.start_draft(user, "en")
        ativacao.desativar(oficial("nl"))

        assert services.change_language(carta, "nl") is False

        carta.refresh_from_db()
        assert carta.language == "en"

    def test_a_troca_de_modelo_nao_alcanca_cartas_ja_criadas(self, user):
        """
        Uma carta já escrita continua apontando para o modelo com que
        nasceu: ativar outro vale para carta NOVA.
        """
        carta = services.start_draft(user, "fr")
        antes = carta.document_template_id

        ativacao.ativar(copia_pronta("fr"))

        carta.refresh_from_db()
        assert carta.document_template_id == antes


# ===========================================================================
# 3. Na tela do assistente
# ===========================================================================


class TestNaTelaDoAssistente:
    def test_a_etapa_5_marca_como_indisponivel_o_idioma_sem_ativo(
        self, auth_client, user
    ):
        auth_client.post(reverse("letters:new"), DADOS_ETAPA_1)
        carta = Letter.objects.get(user=user)
        _ate_a_etapa_5(auth_client, carta)
        ativacao.desativar(oficial("nl"))

        resposta = auth_client.get(_passo(carta, 5))

        por_codigo = {i["code"]: i for i in resposta.context["language_options"]}
        assert por_codigo["nl"]["available"] is False
        assert por_codigo["fr"]["available"] is True

    def test_a_etapa_5_volta_a_oferecer_o_idioma_quando_outra_e_ativada(
        self, auth_client, user
    ):
        """A tela e o sistema concordando -- que é o que faltava."""
        auth_client.post(reverse("letters:new"), DADOS_ETAPA_1)
        carta = Letter.objects.get(user=user)
        _ate_a_etapa_5(auth_client, carta)
        ativacao.ativar(copia_pronta("nl"))  # troca: o oficial NL sai

        resposta = auth_client.get(_passo(carta, 5))

        por_codigo = {i["code"]: i for i in resposta.context["language_options"]}
        assert por_codigo["nl"]["available"] is True
        assert "Ainda não disponível" not in resposta.content.decode()

    def test_a_carta_nova_sai_pela_copia_ativa(self, auth_client, user):
        # A carta nova nasce no idioma padrao (frances, desde a Rodada 18).
        copia = copia_pronta(services.idioma_padrao_da_carta())
        ativacao.ativar(copia)

        auth_client.post(reverse("letters:new"), DADOS_ETAPA_1)

        assert Letter.objects.get(user=user).document_template_id == copia.pk

    def test_sem_ativo_a_tela_de_carta_nova_avisa_e_nao_cria(self, auth_client, user):
        ativacao.desativar(oficial(services.idioma_padrao_da_carta()))

        resposta = auth_client.post(reverse("letters:new"), DADOS_ETAPA_1, follow=True)

        assert resposta.redirect_chain[-1][0] == reverse("core:dashboard")
        assert [str(m) for m in resposta.context["messages"]]
        assert not Letter.objects.filter(user=user).exists()
