"""
O ciclo de vida onde a pessoa encontra: dashboard, detalhe, PDF e a
porta do assistente.

`test_lifecycle.py` cobre as CONTAS (até quando edita, quando expira).
Aqui o que se cobra é o efeito delas no produto -- e, principalmente,
que a regra vale no SERVIDOR: esconder um botão nunca foi proteção, e
todo teste de bloqueio aqui vai pela URL direta, que é o que alguém
faria.

As cartas nascem pelo caminho real (HTTP, as seis etapas), não montadas
à mão: é o único jeito de o teste responder pelo fluxo que existe.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.letters import lifecycle
from apps.letters.models import Letter, LetterPolicy

pytestmark = pytest.mark.django_db

DASHBOARD = reverse("core:dashboard")


@pytest.fixture(autouse=True)
def _modelos_oficiais_prontos(modelos_oficiais_prontos):
    """Sem os modelos com logo materializado o assistente não cria carta."""


@pytest.fixture(autouse=True)
def _nacionalidade(nacionalidade_factory):
    nacionalidade_factory("Brasileira", name_fr="Brésilienne")


CHEGADA = timezone.localdate() + datetime.timedelta(days=30)
PASSOS = {
    1: {
        "guest_name": "Carlos Eduardo Silva",
        "guest_nationality": "Brasileira",
        "guest_birth_date": "22/07/1990",
        "guest_passport": "YY0000",
    },
    2: {
        "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
        "stay_departure": (CHEGADA + datetime.timedelta(days=14)).strftime("%d/%m/%Y"),
    },
    3: {"host_confirm": "on"},
    4: {"notice_informal": "on", "notice_prise_en_charge": "on"},
}


def _step(carta, n):
    return reverse("letters:step", args=[carta.uuid, n])


def criar_carta_finalizada(client, user):
    """Uma carta emitida pelo caminho real: as seis etapas, via HTTP."""
    client.post(reverse("letters:new"), PASSOS[1])
    carta = Letter.objects.get(user=user)
    for numero in (2, 3, 4):
        client.post(_step(carta, numero), PASSOS[numero])
    client.post(_step(carta, 5), {"language": "fr"})
    client.post(_step(carta, 6))
    carta.refresh_from_db()
    return carta


def criar_rascunho(client, user):
    client.post(reverse("letters:new"), PASSOS[1])
    return Letter.objects.get(user=user)


@pytest.fixture
def politica():
    return lifecycle.policy()


def _editavel_por_dias(politica, dias=7):
    politica.editability = LetterPolicy.Editability.POR_DIAS
    politica.editability_amount = dias
    politica.save()


def _expira_na_viagem(politica):
    politica.expiration = LetterPolicy.Expiration.NA_DATA_DA_VIAGEM
    politica.save()


def _viagem_no_passado(carta):
    """Joga a viagem para trás, para a carta já estar expirada agora."""
    passado = (timezone.localdate() - datetime.timedelta(days=10)).isoformat()
    carta.snapshot = {**carta.snapshot, "data": {**carta.snapshot["data"], "stay_arrival": passado}}
    carta.save(update_fields=["snapshot", "updated_at"])
    return carta


# ===========================================================================
# A finalização grava o marco zero
# ===========================================================================


class TestMarcoDaFinalizacao:
    def test_finalizar_grava_o_instante(self, auth_client, user):
        carta = criar_carta_finalizada(auth_client, user)

        assert carta.finalized_at is not None
        assert carta.status == Letter.Status.GENERATED

    def test_o_rascunho_ainda_nao_tem_o_marco(self, auth_client, user):
        carta = criar_rascunho(auth_client, user)

        assert carta.finalized_at is None

    def test_reeditar_e_finalizar_de_novo_NAO_estica_o_prazo(
        self, auth_client, user, politica
    ):
        """
        O buraco óbvio desta etapa: se o marco se movesse a cada
        finalização, bastaria reeditar uma vez por dia para ter prazo
        infinito. Ele é gravado uma vez e fica.
        """
        _editavel_por_dias(politica, dias=7)
        carta = criar_carta_finalizada(auth_client, user)
        marco_original = carta.finalized_at

        auth_client.post(_step(carta, 1), {**PASSOS[1], "guest_name": "Outro Nome"})
        auth_client.post(_step(carta, 6))
        carta.refresh_from_db()

        assert carta.finalized_at == marco_original
        assert carta.data["guest_name"] == "Outro Nome"


# ===========================================================================
# Editar uma carta finalizada
# ===========================================================================


class TestEdicaoDepoisDeFinalizar:
    def test_dentro_do_prazo_a_etapa_abre(self, auth_client, user, politica):
        _editavel_por_dias(politica, dias=7)
        carta = criar_carta_finalizada(auth_client, user)

        assert auth_client.get(_step(carta, 1)).status_code == 200

    def test_fora_do_prazo_a_URL_NAO_abre(self, auth_client, user, politica):
        """
        A política padrão é NÃO_EDITÁVEL. Digitar o endereço da etapa
        devolve a pessoa ao detalhe com um aviso -- não deixa editar.
        """
        carta = criar_carta_finalizada(auth_client, user)

        resposta = auth_client.get(_step(carta, 1), follow=True)

        assert resposta.redirect_chain[-1][0].endswith(f"/letters/{carta.uuid}/")
        assert "não pode mais ser editada" in resposta.content.decode()

    def test_fora_do_prazo_o_POST_tambem_e_recusado(self, auth_client, user):
        """Não basta recusar o GET: o envio direto também não passa."""
        carta = criar_carta_finalizada(auth_client, user)
        nome_original = carta.data["guest_name"]

        auth_client.post(_step(carta, 1), {**PASSOS[1], "guest_name": "Invasor"})

        carta.refresh_from_db()
        assert carta.data["guest_name"] == nome_original

    def test_prazo_vencido_entre_uma_visita_e_outra(self, auth_client, user, politica):
        """Abriu dentro do prazo; o prazo venceu; a próxima tentativa cai."""
        politica.editability = LetterPolicy.Editability.POR_HORAS
        politica.editability_amount = 1
        politica.save()
        carta = criar_carta_finalizada(auth_client, user)
        assert auth_client.get(_step(carta, 1)).status_code == 200

        Letter.objects.filter(pk=carta.pk).update(
            finalized_at=timezone.now() - datetime.timedelta(hours=2)
        )

        assert auth_client.get(_step(carta, 1), follow=True).redirect_chain

    def test_o_idioma_nao_muda_depois_de_emitido(self, auth_client, user, politica):
        """
        O modelo estrutural está congelado na carta; trocar o idioma
        trocaria o modelo, e `Letter.save()` recusa. A etapa 5 explica em
        vez de estourar.
        """
        _editavel_por_dias(politica)
        carta = criar_carta_finalizada(auth_client, user)

        tela = auth_client.get(_step(carta, 5))
        envio = auth_client.post(_step(carta, 5), {"language": "pt"}, follow=True)

        carta.refresh_from_db()
        assert tela.context["language_locked"] is True
        assert carta.language == "fr"
        assert "idioma não pode mais ser alterado" in envio.content.decode()

    def test_reeditar_regenera_o_pdf_com_os_dados_novos(self, auth_client, user, politica):
        from pypdf import PdfReader

        _editavel_por_dias(politica)
        carta = criar_carta_finalizada(auth_client, user)

        auth_client.post(_step(carta, 1), {**PASSOS[1], "guest_name": "Zoé Martin"})
        auth_client.post(_step(carta, 6))
        carta.refresh_from_db()

        with carta.pdf_file.open("rb") as arquivo:
            import io

            texto = PdfReader(io.BytesIO(arquivo.read())).pages[0].extract_text()
        assert "Zoé Martin" in texto
        assert "Carlos Eduardo Silva" not in texto


# ===========================================================================
# Expiração: o documento sai das mãos do usuário comum
# ===========================================================================


class TestCartaExpirada:
    def test_o_pdf_nao_e_entregue(self, auth_client, user, politica):
        _expira_na_viagem(politica)
        carta = _viagem_no_passado(criar_carta_finalizada(auth_client, user))

        resposta = auth_client.get(reverse("letters:pdf", args=[carta.uuid]), follow=True)

        assert "expirou" in resposta.content.decode()
        assert resposta.redirect_chain[-1][0].endswith(f"/letters/{carta.uuid}/")

    def test_o_detalhe_continua_abrindo_e_diz_que_expirou(self, auth_client, user, politica):
        """O registro é da pessoa: ela tem de poder ver o que aconteceu."""
        _expira_na_viagem(politica)
        carta = _viagem_no_passado(criar_carta_finalizada(auth_client, user))

        corpo = auth_client.get(reverse("letters:detail", args=[carta.uuid])).content.decode()

        assert "Carta expirada" in corpo
        assert reverse("letters:pdf", args=[carta.uuid]) not in corpo

    def test_o_dashboard_mostra_expirada_e_esconde_o_pdf(self, auth_client, user, politica):
        _expira_na_viagem(politica)
        carta = _viagem_no_passado(criar_carta_finalizada(auth_client, user))

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert "Expirada" in corpo
        assert reverse("letters:pdf", args=[carta.uuid]) not in corpo

    def test_quem_supervisiona_alcanca_a_carta_expirada(
        self, auth_client, user, client, other_user, permissao_ver_todas, politica
    ):
        """
        A expiração tira o documento do usuário comum, não do registro
        nem de quem responde por ele.
        """
        _expira_na_viagem(politica)
        carta = _viagem_no_passado(criar_carta_finalizada(auth_client, user))
        other_user.user_permissions.add(permissao_ver_todas)
        client.force_login(other_user)

        detalhe = client.get(reverse("letters:detail", args=[carta.uuid]))
        pdf = client.get(reverse("letters:pdf", args=[carta.uuid]))

        assert detalhe.status_code == 200
        assert pdf.status_code == 200
        assert pdf["Content-Type"] == "application/pdf"

    def test_sem_a_permissao_a_carta_alheia_continua_invisivel(
        self, auth_client, user, client, other_user, politica
    ):
        """O contrário do teste acima: supervisão é a permissão, não a curiosidade."""
        carta = criar_carta_finalizada(auth_client, user)
        client.force_login(other_user)

        assert client.get(reverse("letters:detail", args=[carta.uuid])).status_code == 404
        assert client.get(reverse("letters:pdf", args=[carta.uuid])).status_code == 404


# ===========================================================================
# O dashboard oferece a ação certa para cada estado
# ===========================================================================


class TestAcoesNoDashboard:
    def test_rascunho_oferece_continuar(self, auth_client, user):
        carta = criar_rascunho(auth_client, user)

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert "Continuar" in corpo
        assert reverse("letters:step", args=[carta.uuid, 2]) in corpo

    def test_finalizada_e_editavel_oferece_editar_e_pdf(self, auth_client, user, politica):
        _editavel_por_dias(politica)
        carta = criar_carta_finalizada(auth_client, user)

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert "Editar" in corpo
        assert reverse("letters:step", args=[carta.uuid, 1]) in corpo
        assert reverse("letters:pdf", args=[carta.uuid]) in corpo

    def test_finalizada_e_nao_editavel_oferece_so_o_pdf(self, auth_client, user):
        carta = criar_carta_finalizada(auth_client, user)

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert reverse("letters:pdf", args=[carta.uuid]) in corpo
        assert reverse("letters:step", args=[carta.uuid, 1]) not in corpo

    def test_expirada_nao_oferece_acao_nenhuma_sobre_o_documento(
        self, auth_client, user, politica
    ):
        _expira_na_viagem(politica)
        _editavel_por_dias(politica)
        politica.refresh_from_db()
        carta = _viagem_no_passado(criar_carta_finalizada(auth_client, user))

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert reverse("letters:pdf", args=[carta.uuid]) not in corpo
        assert "Expirada" in corpo

    def test_o_detalhe_mostra_o_prazo_de_edicao(self, auth_client, user, politica):
        _editavel_por_dias(politica)
        carta = criar_carta_finalizada(auth_client, user)

        corpo = auth_client.get(reverse("letters:detail", args=[carta.uuid])).content.decode()

        assert "Editável até" in corpo

    def test_o_detalhe_mostra_ate_quando_a_carta_vale(self, auth_client, user, politica):
        _expira_na_viagem(politica)
        carta = criar_carta_finalizada(auth_client, user)

        corpo = auth_client.get(reverse("letters:detail", args=[carta.uuid])).content.decode()

        assert "Válida até" in corpo


# ===========================================================================
# Propriedade: nada disso afrouxa o isolamento entre pessoas
# ===========================================================================


class TestPropriedade:
    def test_ninguem_edita_a_carta_de_outro_nem_dentro_do_prazo(
        self, auth_client, user, client, other_user, politica
    ):
        _editavel_por_dias(politica)
        carta = criar_carta_finalizada(auth_client, user)
        client.force_login(other_user)

        assert client.get(_step(carta, 1)).status_code == 404

    def test_a_permissao_de_supervisao_nao_da_direito_de_EDITAR(
        self, auth_client, user, client, other_user, permissao_ver_todas, politica
    ):
        """
        Ver e editar são coisas diferentes: `letters.view_all_letters`
        abre o detalhe e o PDF, e para por aí.
        """
        _editavel_por_dias(politica)
        carta = criar_carta_finalizada(auth_client, user)
        other_user.user_permissions.add(permissao_ver_todas)
        client.force_login(other_user)

        assert client.get(reverse("letters:detail", args=[carta.uuid])).status_code == 200
        assert client.get(_step(carta, 1)).status_code == 404
