"""
Ciclo de vida da carta: editabilidade, expiração e o estado que sai
disso.

CADA POLÍTICA, TRÊS MOMENTOS
----------------------------
Para toda política com prazo, a suíte pergunta nos três instantes que
importam: ANTES do limite, EXATAMENTE no limite e DEPOIS. O limite é
EXCLUSIVO -- vale enquanto `agora < limite` --, e é no "exatamente" que
essa convenção ou se confirma ou cai.

FUSO HORÁRIO
------------
O projeto roda em `Europe/Brussels` (config/settings/base.py). Um prazo
baseado em DATA (a viagem) vale até o fim daquele dia LOCAL, ou seja,
expira à meia-noite do dia seguinte em Bruxelas -- que em UTC é 22h ou
23h do próprio dia, conforme o horário de verão. Os testes de fuso
cobrem os dois lados dessa fronteira, em vez de assumir que local e UTC
coincidem (não coincidem nunca, aqui).

`now=` é injetado de propósito em toda pergunta: congelar o instante é o
que torna o teste determinístico e o que permite perguntar "e um
microssegundo antes?".
"""

import datetime
import zoneinfo

import pytest
from django.utils import timezone

from apps.letters import lifecycle
from apps.letters.models import Letter, LetterPolicy

pytestmark = pytest.mark.django_db

BRUXELAS = zoneinfo.ZoneInfo("Europe/Brussels")


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


@pytest.fixture
def config():
    """A política vigente, criada com os padrões na primeira leitura."""
    return lifecycle.policy()


def _instante(ano, mes, dia, hora=12, minuto=0):
    """Um instante aware no fuso do PROJETO (não em UTC)."""
    return datetime.datetime(ano, mes, dia, hora, minuto, tzinfo=BRUXELAS)


def finalizar(letter, *, em=None, viagem=None):
    """
    Leva a carta a FINALIZADA sem passar por HTTP: grava o instante da
    finalização e a data da viagem, que é o que as políticas leem.

    `snapshot` preenchido de propósito -- é de lá que
    `lifecycle.dados_da_carta` lê numa carta fechada, e usar o mesmo
    caminho do sistema evita um teste que passa por acidente.
    """
    viagem = viagem or datetime.date(2026, 10, 10)
    letter.status = Letter.Status.GENERATED
    letter.finalized_at = em or _instante(2026, 9, 1, 10)
    letter.snapshot = {"data": {"stay_arrival": viagem.isoformat()}}
    letter.save(update_fields=["status", "finalized_at", "snapshot", "updated_at"])
    return letter


@pytest.fixture
def carta(letter):
    """Uma carta finalizada em 01/09/2026 10:00, viagem em 10/10/2026."""
    return finalizar(letter)


# ===========================================================================
# A política em si
# ===========================================================================


class TestPolitica:
    def test_o_padrao_e_o_comportamento_de_antes_desta_etapa(self, config):
        """Instalar a novidade não muda nada até alguém configurar."""
        assert config.editability == LetterPolicy.Editability.NAO_EDITAVEL
        assert config.expiration == LetterPolicy.Expiration.NUNCA

    def test_e_um_registro_so(self, config):
        """Alterar é carregar, mudar e salvar -- nunca criar outro."""
        config.editability = LetterPolicy.Editability.POR_DIAS
        config.editability_amount = 2
        config.save()

        assert LetterPolicy.objects.count() == 1
        assert lifecycle.policy().editability == LetterPolicy.Editability.POR_DIAS

    def test_um_segundo_registro_falha_alto_em_vez_de_duplicar(self, config):
        """
        Salvar um objeto NOVO cairia num UPDATE da linha existente com
        `created_at` nulo. Falhar é o certo: duas políticas "vigentes"
        ao mesmo tempo seria pior do que um erro visível.
        """
        from django.db import IntegrityError, transaction

        outra = LetterPolicy(editability=LetterPolicy.Editability.POR_DIAS)

        with pytest.raises(IntegrityError), transaction.atomic():
            outra.save()

        assert LetterPolicy.objects.count() == 1

    @pytest.mark.parametrize(
        "regra",
        [
            LetterPolicy.Editability.POR_HORAS,
            LetterPolicy.Editability.POR_DIAS,
            LetterPolicy.Editability.ATE_X_DIAS_APOS_CRIACAO,
        ],
    )
    def test_politica_de_edicao_com_numero_exige_o_numero(self, config, regra):
        from django.core.exceptions import ValidationError

        config.editability = regra
        config.editability_amount = 0

        with pytest.raises(ValidationError):
            config.full_clean()

    @pytest.mark.parametrize(
        "regra",
        [
            LetterPolicy.Expiration.X_DIAS_ANTES_DA_VIAGEM,
            LetterPolicy.Expiration.X_DIAS_DEPOIS_DA_VIAGEM,
            LetterPolicy.Expiration.X_DIAS_APOS_CRIACAO,
        ],
    )
    def test_politica_de_expiracao_com_numero_exige_o_numero(self, config, regra):
        from django.core.exceptions import ValidationError

        config.expiration = regra
        config.expiration_amount = 0

        with pytest.raises(ValidationError):
            config.full_clean()

    def test_politica_sem_numero_nao_exige_numero(self, config):
        config.editability = LetterPolicy.Editability.ATE_DATA_VIAGEM
        config.expiration = LetterPolicy.Expiration.NA_DATA_DA_VIAGEM
        config.editability_amount = 0
        config.expiration_amount = 0

        config.full_clean()  # não deve levantar


# ===========================================================================
# Editabilidade
# ===========================================================================


class TestEdicaoNaoEditavel:
    def test_carta_finalizada_nunca_e_editavel(self, carta, config):
        config.editability = LetterPolicy.Editability.NAO_EDITAVEL
        config.save()

        assert lifecycle.is_letter_editable(carta) is False
        assert lifecycle.letter_editable_until(carta) is None

    def test_o_rascunho_continua_editavel(self, letter, config):
        """A política vale para carta FINALIZADA; rascunho edita sempre."""
        config.editability = LetterPolicy.Editability.NAO_EDITAVEL
        config.save()

        assert letter.status == Letter.Status.DRAFT
        assert lifecycle.is_letter_editable(letter) is True


class TestEdicaoPorHoras:
    @pytest.fixture(autouse=True)
    def _politica(self, config):
        config.editability = LetterPolicy.Editability.POR_HORAS
        config.editability_amount = 24
        config.save()

    def test_o_limite_e_24h_depois_da_finalizacao(self, carta):
        assert lifecycle.letter_editable_until(carta) == _instante(2026, 9, 2, 10)

    def test_antes_do_limite_edita(self, carta):
        assert lifecycle.is_letter_editable(carta, now=_instante(2026, 9, 2, 9, 59)) is True

    def test_exatamente_no_limite_nao_edita_mais(self, carta):
        """O limite é exclusivo: no instante exato já acabou."""
        assert lifecycle.is_letter_editable(carta, now=_instante(2026, 9, 2, 10)) is False

    def test_um_microssegundo_antes_do_limite_ainda_edita(self, carta):
        quase = _instante(2026, 9, 2, 10) - datetime.timedelta(microseconds=1)

        assert lifecycle.is_letter_editable(carta, now=quase) is True

    def test_depois_do_limite_nao_edita(self, carta):
        assert lifecycle.is_letter_editable(carta, now=_instante(2026, 9, 3)) is False


class TestEdicaoPorDias:
    @pytest.fixture(autouse=True)
    def _politica(self, config):
        config.editability = LetterPolicy.Editability.POR_DIAS
        config.editability_amount = 3
        config.save()

    def test_o_limite_e_3_dias_depois_da_finalizacao(self, carta):
        assert lifecycle.letter_editable_until(carta) == _instante(2026, 9, 4, 10)

    def test_antes(self, carta):
        assert lifecycle.is_letter_editable(carta, now=_instante(2026, 9, 3)) is True

    def test_exatamente_no_limite(self, carta):
        assert lifecycle.is_letter_editable(carta, now=_instante(2026, 9, 4, 10)) is False

    def test_depois(self, carta):
        assert lifecycle.is_letter_editable(carta, now=_instante(2026, 9, 5)) is False


class TestEdicaoAteADataDaViagem:
    @pytest.fixture(autouse=True)
    def _politica(self, config):
        config.editability = LetterPolicy.Editability.ATE_DATA_VIAGEM
        config.save()

    def test_o_limite_e_o_fim_do_dia_da_viagem(self, carta):
        """Vale o dia INTEIRO da viagem: acaba à meia-noite seguinte."""
        assert lifecycle.letter_editable_until(carta) == _instante(2026, 10, 11, 0, 0)

    def test_antes(self, carta):
        assert lifecycle.is_letter_editable(carta, now=_instante(2026, 10, 1)) is True

    def test_no_proprio_dia_da_viagem_ainda_edita(self, carta):
        assert lifecycle.is_letter_editable(carta, now=_instante(2026, 10, 10, 23, 59)) is True

    def test_exatamente_no_limite(self, carta):
        assert lifecycle.is_letter_editable(carta, now=_instante(2026, 10, 11, 0, 0)) is False

    def test_depois(self, carta):
        assert lifecycle.is_letter_editable(carta, now=_instante(2026, 10, 12)) is False

    def test_sem_data_de_viagem_nao_edita(self, letter):
        """
        Prazo que não se consegue calcular não vira permissão: a resposta
        segura é NÃO.
        """
        letter.status = Letter.Status.GENERATED
        letter.finalized_at = timezone.now()
        letter.snapshot = {"data": {}}
        letter.save()

        assert lifecycle.letter_editable_until(letter) is None
        assert lifecycle.is_letter_editable(letter) is False


class TestEdicaoAteXDiasAposCriacao:
    @pytest.fixture(autouse=True)
    def _politica(self, config):
        config.editability = LetterPolicy.Editability.ATE_X_DIAS_APOS_CRIACAO
        config.editability_amount = 7
        config.save()

    def test_o_limite_conta_da_CRIACAO_e_nao_da_finalizacao(self, carta):
        """
        A carta foi criada agora (fixture) e "finalizada" numa data
        futura de mentira -- então os dois marcos são bem diferentes, e o
        teste falharia se a conta usasse o marco errado.
        """
        esperado = carta.created_at + datetime.timedelta(days=7)

        assert lifecycle.letter_editable_until(carta) == esperado

    def test_antes(self, carta):
        agora = carta.created_at + datetime.timedelta(days=6)

        assert lifecycle.is_letter_editable(carta, now=agora) is True

    def test_exatamente_no_limite(self, carta):
        agora = carta.created_at + datetime.timedelta(days=7)

        assert lifecycle.is_letter_editable(carta, now=agora) is False

    def test_depois(self, carta):
        agora = carta.created_at + datetime.timedelta(days=8)

        assert lifecycle.is_letter_editable(carta, now=agora) is False


# ===========================================================================
# Expiração
# ===========================================================================


class TestExpiracaoNunca:
    def test_nunca_expira(self, carta, config):
        config.expiration = LetterPolicy.Expiration.NUNCA
        config.save()

        assert lifecycle.letter_expires_at(carta) is None
        assert lifecycle.is_letter_expired(carta, now=_instante(2099, 1, 1)) is False


class TestExpiracaoNaDataDaViagem:
    @pytest.fixture(autouse=True)
    def _politica(self, config):
        config.expiration = LetterPolicy.Expiration.NA_DATA_DA_VIAGEM
        config.save()

    def test_o_limite_e_o_fim_do_dia_da_viagem(self, carta):
        assert lifecycle.letter_expires_at(carta) == _instante(2026, 10, 11, 0, 0)

    def test_antes(self, carta):
        assert lifecycle.is_letter_expired(carta, now=_instante(2026, 10, 9)) is False

    def test_no_proprio_dia_da_viagem_ainda_vale(self, carta):
        """A carta serve PARA a viagem: tem de valer no dia dela."""
        assert lifecycle.is_letter_expired(carta, now=_instante(2026, 10, 10, 23, 59)) is False

    def test_exatamente_no_limite(self, carta):
        assert lifecycle.is_letter_expired(carta, now=_instante(2026, 10, 11, 0, 0)) is True

    def test_depois(self, carta):
        assert lifecycle.is_letter_expired(carta, now=_instante(2026, 10, 12)) is True


class TestExpiracaoXDiasAntesDaViagem:
    @pytest.fixture(autouse=True)
    def _politica(self, config):
        config.expiration = LetterPolicy.Expiration.X_DIAS_ANTES_DA_VIAGEM
        config.expiration_amount = 5
        config.save()

    def test_o_limite_e_o_fim_do_dia_cinco_dias_antes(self, carta):
        # viagem 10/10 -> 05/10 é o último dia válido -> acaba em 06/10 00:00
        assert lifecycle.letter_expires_at(carta) == _instante(2026, 10, 6, 0, 0)

    def test_antes(self, carta):
        assert lifecycle.is_letter_expired(carta, now=_instante(2026, 10, 5, 12)) is False

    def test_exatamente_no_limite(self, carta):
        assert lifecycle.is_letter_expired(carta, now=_instante(2026, 10, 6, 0, 0)) is True

    def test_depois(self, carta):
        assert lifecycle.is_letter_expired(carta, now=_instante(2026, 10, 7)) is True


class TestExpiracaoXDiasDepoisDaViagem:
    @pytest.fixture(autouse=True)
    def _politica(self, config):
        config.expiration = LetterPolicy.Expiration.X_DIAS_DEPOIS_DA_VIAGEM
        config.expiration_amount = 30
        config.save()

    def test_o_limite_e_o_fim_do_dia_trinta_dias_depois(self, carta):
        assert lifecycle.letter_expires_at(carta) == _instante(2026, 11, 10, 0, 0)

    def test_antes(self, carta):
        assert lifecycle.is_letter_expired(carta, now=_instante(2026, 11, 9, 23)) is False

    def test_exatamente_no_limite(self, carta):
        assert lifecycle.is_letter_expired(carta, now=_instante(2026, 11, 10, 0, 0)) is True

    def test_depois(self, carta):
        assert lifecycle.is_letter_expired(carta, now=_instante(2026, 12, 1)) is True


class TestExpiracaoXDiasAposCriacao:
    @pytest.fixture(autouse=True)
    def _politica(self, config):
        config.expiration = LetterPolicy.Expiration.X_DIAS_APOS_CRIACAO
        config.expiration_amount = 90
        config.save()

    def test_o_limite_conta_da_criacao(self, carta):
        assert lifecycle.letter_expires_at(carta) == carta.created_at + datetime.timedelta(days=90)

    def test_antes(self, carta):
        assert (
            lifecycle.is_letter_expired(
                carta, now=carta.created_at + datetime.timedelta(days=89)
            )
            is False
        )

    def test_exatamente_no_limite(self, carta):
        assert (
            lifecycle.is_letter_expired(carta, now=carta.created_at + datetime.timedelta(days=90))
            is True
        )

    def test_depois(self, carta):
        assert (
            lifecycle.is_letter_expired(carta, now=carta.created_at + datetime.timedelta(days=91))
            is True
        )


class TestExpiracaoCasosDeBorda:
    def test_rascunho_nunca_expira(self, letter, config):
        """Sem documento emitido não há validade a perder."""
        config.expiration = LetterPolicy.Expiration.X_DIAS_APOS_CRIACAO
        config.expiration_amount = 1
        config.save()

        assert lifecycle.is_letter_expired(letter, now=_instante(2099, 1, 1)) is False

    def test_sem_data_de_viagem_nao_expira(self, letter, config):
        """
        Na dúvida, a carta VALE: tirar da pessoa o próprio documento por
        causa de um dado ausente seria o pior dos dois erros.
        """
        config.expiration = LetterPolicy.Expiration.NA_DATA_DA_VIAGEM
        config.save()
        letter.status = Letter.Status.GENERATED
        letter.snapshot = {"data": {}}
        letter.save()

        assert lifecycle.letter_expires_at(letter) is None
        assert lifecycle.is_letter_expired(letter, now=_instante(2099, 1, 1)) is False

    def test_data_de_viagem_ilegivel_nao_derruba(self, carta, config):
        config.expiration = LetterPolicy.Expiration.NA_DATA_DA_VIAGEM
        config.save()
        carta.snapshot = {"data": {"stay_arrival": "10 de outubro"}}
        carta.save()

        assert lifecycle.travel_date(carta) is None
        assert lifecycle.letter_expires_at(carta) is None


# ===========================================================================
# As duas políticas são independentes
# ===========================================================================


class TestIndependenciaDasPoliticas:
    def test_pode_expirar_sem_nunca_ter_sido_editavel(self, carta, config):
        config.editability = LetterPolicy.Editability.NAO_EDITAVEL
        config.expiration = LetterPolicy.Expiration.NA_DATA_DA_VIAGEM
        config.save()
        depois = _instante(2026, 10, 12)

        assert lifecycle.is_letter_editable(carta, now=depois) is False
        assert lifecycle.is_letter_expired(carta, now=depois) is True

    def test_pode_ser_editavel_e_nao_expirar(self, carta, config):
        config.editability = LetterPolicy.Editability.POR_DIAS
        config.editability_amount = 5
        config.expiration = LetterPolicy.Expiration.NUNCA
        config.save()
        agora = _instante(2026, 9, 2)

        assert lifecycle.is_letter_editable(carta, now=agora) is True
        assert lifecycle.is_letter_expired(carta, now=agora) is False


# ===========================================================================
# O estado que sai disso
# ===========================================================================


class TestEstado:
    def test_rascunho(self, letter):
        assert lifecycle.letter_state(letter) == lifecycle.RASCUNHO

    def test_finalizada(self, carta, config):
        config.expiration = LetterPolicy.Expiration.NUNCA
        config.save()

        assert lifecycle.letter_state(carta) == lifecycle.FINALIZADA

    def test_expirada(self, carta, config):
        config.expiration = LetterPolicy.Expiration.NA_DATA_DA_VIAGEM
        config.save()

        assert lifecycle.letter_state(carta, now=_instante(2026, 12, 1)) == lifecycle.EXPIRADA

    def test_cancelada_nao_vira_finalizada_por_engano(self, carta):
        carta.status = Letter.Status.CANCELLED
        carta.save()

        assert lifecycle.letter_state(carta) == lifecycle.CANCELADA
        assert lifecycle.is_letter_editable(carta) is False

    def test_expirada_tem_precedencia_sobre_finalizada(self, carta, config):
        """O status no banco continua "gerada"; o ESTADO é expirada."""
        config.expiration = LetterPolicy.Expiration.NA_DATA_DA_VIAGEM
        config.save()

        assert carta.status == Letter.Status.GENERATED
        assert lifecycle.letter_state(carta, now=_instante(2026, 12, 1)) == lifecycle.EXPIRADA


# ===========================================================================
# Fuso horário
# ===========================================================================


class TestFusoHorario:
    """
    O projeto roda em Europe/Brussels. Um prazo por DATA acaba à
    meia-noite LOCAL -- que nunca é meia-noite UTC. Se alguém trocar as
    contas para UTC, é aqui que quebra.
    """

    @pytest.fixture(autouse=True)
    def _politica(self, config):
        config.expiration = LetterPolicy.Expiration.NA_DATA_DA_VIAGEM
        config.save()

    def test_o_limite_e_meia_noite_em_bruxelas_nao_em_utc(self, carta):
        limite = lifecycle.letter_expires_at(carta)

        local = limite.astimezone(BRUXELAS)
        assert (local.hour, local.minute) == (0, 0)
        assert local.date() == datetime.date(2026, 10, 11)
        # Outubro ainda é horário de verão na Bélgica (UTC+2).
        assert limite.astimezone(datetime.UTC).hour == 22

    def test_no_verao_europeu_a_carta_ainda_vale_as_23h_utc(self, carta):
        """
        23:00 UTC de 10/10 já é 01:00 do dia 11 em Bruxelas: passou da
        meia-noite local, então expirou -- mesmo sendo "ainda dia 10"
        em UTC. É exatamente a confusão que este teste existe para pegar.
        """
        vinte_e_tres_utc = datetime.datetime(
            2026, 10, 10, 23, 0, tzinfo=datetime.UTC
        )

        assert lifecycle.is_letter_expired(carta, now=vinte_e_tres_utc) is True

    def test_as_21h_utc_do_dia_da_viagem_ainda_vale(self, carta):
        """21:00 UTC = 23:00 em Bruxelas, ainda dentro do dia da viagem."""
        vinte_e_uma_utc = datetime.datetime(
            2026, 10, 10, 21, 0, tzinfo=datetime.UTC
        )

        assert lifecycle.is_letter_expired(carta, now=vinte_e_uma_utc) is False

    def test_no_inverno_o_deslocamento_muda_e_a_conta_acompanha(self, letter):
        """
        Em janeiro a Bélgica está em UTC+1, não +2. O limite continua
        sendo meia-noite LOCAL -- ou seja, 23:00 UTC do dia anterior.
        """
        carta = finalizar(letter, viagem=datetime.date(2027, 1, 15))

        limite = lifecycle.letter_expires_at(carta)

        assert limite.astimezone(BRUXELAS).hour == 0
        assert limite.astimezone(datetime.UTC).hour == 23
        assert limite.astimezone(datetime.UTC).date() == datetime.date(2027, 1, 15)
