"""
Testes da Etapa 3 da Fase 5: navegação, confirmação e as regras da etapa
de viagem.

O ponto central é que a navegação livre entre as etapas não pode virar
uma porta para furar a validação: os indicadores viram atalho, mas quem
decide até onde se pode ir é sempre o servidor.
"""

import datetime

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from apps.letters import services
from apps.letters.models import Letter
from apps.letters.rules import MAX_STAY_DAYS, stay_duration_days

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _modelos_oficiais_prontos(modelos_oficiais_prontos):
    """
    Os quatro modelos oficiais com o logo materializado -- sem eles
    `official_document_template()` devolve `None` e o assistente
    recusa criar carta nenhuma (e esta certo: seria uma carta que
    nao viraria PDF).
    """


@pytest.fixture(autouse=True)
def _nacionalidades_de_teste(nacionalidade_factory):
    """
    Nacionalidades usadas pelos payloads deste arquivo -- desde a decisão
    final da Fase 5/Etapa 3 o campo não aceita mais texto livre. Não é
    uma lista oficial (ver apps/letters/tests/test_nacionalidade_e_documento.py).
    """
    nacionalidade_factory("Brasileira")

    nacionalidade_factory("Belga")


def _step_url(letter, step):
    return reverse("letters:step", args=[letter.uuid, step])


VALID_STEP_1 = {
    "guest_name": "Maria Santos da Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "15/08/1990",
    "guest_passport": "YY0000",
}
# Datas relativas a hoje: a chegada nao pode ser no passado, entao uma
# data fixa no codigo venceria com o tempo. O intervalo de 15 dias
# (inclusivo) e o mesmo do documento oficial.
CHEGADA = timezone.localdate() + datetime.timedelta(days=30)
PARTIDA = CHEGADA + datetime.timedelta(days=14)
VALID_STEP_2 = {
    "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
    "stay_departure": PARTIDA.strftime("%d/%m/%Y"),
}
VALID_STEP_3 = {
    "host_confirm": "on",
}
VALID_STEP_4 = {"notice_informal": "on", "notice_prise_en_charge": "on"}
PAYLOADS = {1: VALID_STEP_1, 2: VALID_STEP_2, 3: VALID_STEP_3, 4: VALID_STEP_4}


@pytest.fixture
def draft(user):
    return services.start_draft(user, "fr")


def _fill_until(client, letter, step):
    for n in range(1, min(step, 5)):
        client.post(_step_url(letter, n), PAYLOADS[n])


# ---------------------------------------------------------------------------
# Home e logout
# ---------------------------------------------------------------------------


class TestHomeELogout:
    @pytest.mark.django_db  # a Home le o conteudo do CMS desde a Etapa B
    def test_anonimo_continua_na_home(self, client):
        response = client.get(reverse("core:home"))

        assert response.status_code == 200
        # `landing_stat` era o numero fixo do `demo`. Agora a Home recebe
        # a contagem real das cartas emitidas (apps.letters.statistics).
        assert response.context["cartas_emitidas"] == 0

    def test_autenticado_na_home_vai_para_o_dashboard(self, auth_client):
        response = auth_client.get(reverse("core:home"))

        assert response.status_code == 302
        assert response.url == reverse("core:dashboard")

    def test_logout_volta_para_a_home(self, auth_client):
        response = auth_client.post(reverse("accounts:logout"))

        assert response.status_code == 302
        assert response.url == reverse("core:home")

    def test_depois_do_logout_a_home_abre_normalmente(self, auth_client):
        """Sem sessão não há redirecionamento -- nada de laço entre home e
        dashboard."""
        auth_client.post(reverse("accounts:logout"))

        response = auth_client.get(reverse("core:home"))

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Indicadores navegáveis e bloqueio de bypass
# ---------------------------------------------------------------------------


class TestNavegacaoEntreEtapas:
    def test_voltar_para_uma_etapa_anterior_e_livre(self, auth_client, draft):
        _fill_until(auth_client, draft, 4)

        response = auth_client.get(_step_url(draft, 1))

        assert response.status_code == 200
        assert response.context["step"] == 1

    def test_indicadores_alcancaveis_viram_link(self, auth_client, draft):
        _fill_until(auth_client, draft, 4)

        html = auth_client.get(_step_url(draft, 3)).content.decode()

        # etapas já cumpridas viram atalho
        assert f'href="{_step_url(draft, 1)}"' in html
        assert f'href="{_step_url(draft, 2)}"' in html

    def test_indicador_de_etapa_inalcancavel_nao_e_link(self, auth_client, draft):
        """Com só a etapa 1 preenchida, a 5 não pode ser oferecida."""
        _fill_until(auth_client, draft, 2)

        html = auth_client.get(_step_url(draft, 2)).content.decode()

        assert f'href="{_step_url(draft, 5)}"' not in html

    @pytest.mark.parametrize("alvo", [3, 4, 5, 6])
    def test_pular_etapa_pela_url_devolve_para_a_primeira_pendente(
        self, auth_client, draft, alvo
    ):
        """Bypass por URL: pedir uma etapa adiante com a 1 em branco
        devolve para a 1, tenha a pessoa passado por lá ou não."""
        response = auth_client.get(_step_url(draft, alvo))

        assert response.status_code == 302
        assert response.url == _step_url(draft, 1)

    def test_bypass_por_post_tambem_e_recusado(self, auth_client, draft):
        """Mandar o POST direto na etapa 4 não grava nada: o servidor
        devolve antes de olhar os dados."""
        response = auth_client.post(_step_url(draft, 4), VALID_STEP_4)

        draft.refresh_from_db()
        assert response.status_code == 302
        assert response.url == _step_url(draft, 1)
        assert "notice_informal" not in draft.data

    def test_a_primeira_etapa_pendente_e_a_que_falta_de_verdade(self, auth_client, draft):
        """Com 1 e 2 preenchidas, saltar para a 6 devolve para a 3."""
        _fill_until(auth_client, draft, 3)

        response = auth_client.get(_step_url(draft, 6))

        assert response.url == _step_url(draft, 3)

    def test_com_tudo_preenchido_todas_as_etapas_sao_alcancaveis(self, auth_client, draft):
        _fill_until(auth_client, draft, 5)
        auth_client.post(_step_url(draft, 5), {"language": "fr"})
        draft.refresh_from_db()

        assert services.reachable_steps(draft) == {1, 2, 3, 4, 5, 6}

    def test_ninguem_navega_no_rascunho_de_outro(self, client, user, other_user):
        alheio = services.start_draft(other_user, "fr")
        client.force_login(user)

        assert client.get(_step_url(alheio, 1)).status_code == 404


# ---------------------------------------------------------------------------
# Duração da estadia
# ---------------------------------------------------------------------------


class TestDuracaoDaEstadia:
    def test_a_conta_e_a_mesma_do_documento_oficial(self):
        """10/10/2026 a 24/10/2026 são 15 dias -- contagem inclusiva, como
        o PDF oficial declara."""
        assert (
            stay_duration_days(datetime.date(2026, 10, 10), datetime.date(2026, 10, 24)) == 15
        )

    def test_mesmo_dia_conta_um_dia(self):
        dia = datetime.date(2026, 10, 10)
        assert stay_duration_days(dia, dia) == 1

    def test_partida_antes_da_chegada_nao_tem_duracao(self):
        assert (
            stay_duration_days(datetime.date(2026, 10, 24), datetime.date(2026, 10, 10)) is None
        )

    def test_a_etapa_de_viagem_mostra_a_duracao(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)
        auth_client.post(_step_url(draft, 2), VALID_STEP_2)

        response = auth_client.get(_step_url(draft, 2))

        assert response.context["duration_days"] == 15
        assert "15 dias" in response.content.decode()

    def test_duracao_dentro_do_limite_nao_e_destacada(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)
        auth_client.post(_step_url(draft, 2), VALID_STEP_2)

        response = auth_client.get(_step_url(draft, 2))

        assert response.context["duration_exceeded"] is False
        assert "duration-box span-2 is-invalid" not in response.content.decode()


class TestLimiteDeNoventaDias:
    ACIMA = {
        "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
        "stay_departure": (CHEGADA + datetime.timedelta(days=90)).strftime("%d/%m/%Y"),
    }  # 91 dias (contagem inclusiva)
    NO_LIMITE = {
        "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
        "stay_departure": (CHEGADA + datetime.timedelta(days=89)).strftime("%d/%m/%Y"),
    }  # 90 dias

    def test_exatamente_noventa_dias_passa(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        response = auth_client.post(_step_url(draft, 2), self.NO_LIMITE)

        draft.refresh_from_db()
        assert response.status_code == 302
        assert (
            draft.data["stay_departure"]
            == (CHEGADA + datetime.timedelta(days=89)).isoformat()
        )

    def test_acima_de_noventa_dias_nao_avanca(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        response = auth_client.post(_step_url(draft, 2), self.ACIMA)

        draft.refresh_from_db()
        assert response.status_code == 200  # fica na própria etapa
        assert "stay_departure" in response.context["form"].errors
        assert "stay_departure" not in draft.data

    def test_acima_de_noventa_dias_avisa_e_destaca_em_vermelho(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        html = auth_client.post(_step_url(draft, 2), self.ACIMA).content.decode()

        assert "is-invalid" in html
        assert "tag-error" in html
        assert f"não pode ultrapassar {MAX_STAY_DAYS} dias" in html

    def test_o_limite_vale_tambem_no_backend(self, auth_client, draft):
        """
        Contorno por HTTP: gravar as datas longas direto em Letter.data e
        tentar seguir. A revalidação do servidor barra do mesmo jeito.
        """
        _fill_until(auth_client, draft, 2)
        draft.refresh_from_db()
        draft.data = dict(
            draft.data,
            stay_arrival=CHEGADA.isoformat(),
            stay_departure=(CHEGADA + datetime.timedelta(days=90)).isoformat(),
        )
        draft.save(update_fields=["data"])

        response = auth_client.get(_step_url(draft, 5))

        assert response.status_code == 302
        assert response.url == _step_url(draft, 2)

    def test_estadia_longa_nunca_chega_a_virar_carta(self, auth_client, draft):
        _fill_until(auth_client, draft, 5)
        draft.refresh_from_db()
        draft.data = dict(
            draft.data,
            stay_arrival=CHEGADA.isoformat(),
            stay_departure=(CHEGADA + datetime.timedelta(days=90)).isoformat(),
        )
        draft.save(update_fields=["data"])

        auth_client.post(_step_url(draft, 6))

        draft.refresh_from_db()
        assert draft.status == Letter.Status.DRAFT
        assert draft.snapshot == {}


# ---------------------------------------------------------------------------
# Confirmação depois de gerar
# ---------------------------------------------------------------------------


class TestConfirmacao:
    def _finalizar(self, client, letter):
        _fill_until(client, letter, 5)
        client.post(_step_url(letter, 5), {"language": "fr"})
        return client.post(_step_url(letter, 6))

    def test_finalizar_leva_para_a_pagina_da_carta_e_nao_para_o_dashboard(
        self, auth_client, draft, user
    ):
        user.city = "Woluwe-Saint-Lambert"
        user.save(update_fields=["city"])

        response = self._finalizar(auth_client, draft)

        assert response.status_code == 302
        assert response.url == reverse("letters:detail", args=[draft.uuid])
        assert response.url != reverse("core:dashboard")

    def test_a_confirmacao_mostra_referencia_e_acoes(self, auth_client, draft, user):
        user.city = "Woluwe-Saint-Lambert"
        user.save(update_fields=["city"])
        self._finalizar(auth_client, draft)
        draft.refresh_from_db()

        html = auth_client.get(reverse("letters:detail", args=[draft.uuid])).content.decode()

        assert draft.reference in html
        assert reverse("letters:pdf", args=[draft.uuid]) in html
        assert "Sua Carta Convite está pronta!" in html

    def test_a_confirmacao_preserva_o_uuid_da_carta(self, auth_client, draft, user):
        user.city = "Woluwe-Saint-Lambert"
        user.save(update_fields=["city"])

        response = self._finalizar(auth_client, draft)

        assert str(draft.uuid) in response.url

    def test_perfil_incompleto_para_na_etapa_do_anfitriao(self, auth_client, draft, user):
        """
        Perfil sem cidade: a pessoa é barrada já na etapa do anfitrião --
        e não lá no fim, depois de preencher tudo. A carta não é
        finalizada nem chega a uma confirmação falsa.
        """
        user.city = ""
        user.save(update_fields=["city"])

        response = self._finalizar(auth_client, draft)

        draft.refresh_from_db()
        assert response.url == _step_url(draft, 3)
        assert draft.status == Letter.Status.DRAFT
        assert draft.snapshot == {}


class TestAcoesDoPdf:
    @pytest.fixture
    def carta_gerada(self, user):
        letter = services.start_draft(user, "fr")
        letter.pdf_file.save("x.pdf", ContentFile(b"%PDF-1.4"), save=False)
        letter.status = Letter.Status.GENERATED
        letter.save()
        return letter

    def test_ver_pdf_abre_em_nova_aba(self, auth_client, carta_gerada):
        for url in (
            reverse("letters:detail", args=[carta_gerada.uuid]),
            reverse("core:dashboard"),
        ):
            html = auth_client.get(url).content.decode()
            pdf_url = reverse("letters:pdf", args=[carta_gerada.uuid])
            trecho = html[html.index(pdf_url) - 200 : html.index(pdf_url) + 200]
            assert 'target="_blank"' in trecho
            assert 'rel="noopener"' in trecho

    def test_imprimir_usa_o_pdf_real_da_carta(self, auth_client, carta_gerada):
        """Nada de documento alternativo: a ação de imprimir aponta para o
        mesmo arquivo que "Ver PDF"."""
        html = auth_client.get(
            reverse("letters:detail", args=[carta_gerada.uuid])
        ).content.decode()

        pdf_url = reverse("letters:pdf", args=[carta_gerada.uuid])
        assert "js-print-pdf" in html
        assert f'data-pdf-url="{pdf_url}"' in html

    def test_compartilhar_e_whatsapp_ficam_no_detalhe(self, auth_client, carta_gerada):
        """
        As ações de envio existem, mas só na tela da carta: nas LISTAS,
        cinco botões por linha viram ruído -- lá ficam Ver PDF e Editar, e
        o resto fica a um clique de distância.
        """
        detalhe = auth_client.get(
            reverse("letters:detail", args=[carta_gerada.uuid])
        ).content.decode()
        painel = auth_client.get(reverse("core:dashboard")).content.decode()

        assert "js-share-pdf" in detalhe
        assert "js-share-whatsapp" in detalhe
        assert "js-share-pdf" not in painel
        assert "js-share-whatsapp" not in painel


# ---------------------------------------------------------------------------
# Campo do passaporte
# ---------------------------------------------------------------------------


class TestPlaceholderDoPassaporte:
    def test_o_placeholder_e_o_formato_de_exemplo(self, auth_client, draft):
        """
        O placeholder mostra o FORMATO esperado ("YY0000"), não repete o
        rótulo do campo.
        """
        html = auth_client.get(_step_url(draft, 1)).content.decode()

        assert 'placeholder="YY0000"' in html

    @pytest.mark.parametrize("idioma", ["pt", "fr", "nl", "en"])
    def test_o_formato_e_o_mesmo_em_todos_os_idiomas(self, idioma):
        """Formato não se traduz -- o rótulo sim, o exemplo não."""
        from apps.doctemplates.schema import resolve_field_text
        from apps.letters import services as svc

        modelo = svc.official_document_template(idioma)
        campo = next(
            f for f in modelo.field_schema["fields"] if f["key"] == "guest_passport"
        )
        assert resolve_field_text(campo, idioma, "placeholder") == "YY0000"

    def test_o_schema_gravado_no_banco_ja_tem_o_novo_placeholder(self):
        """
        Não basta mudar a constante: o assistente lê o `field_schema`
        gravado no `DocumentTemplate` oficial -- por isso a mudança
        entrou por migração.
        """
        from apps.letters import services as svc

        modelo = svc.official_document_template("fr")
        campo = next(
            f for f in modelo.field_schema["fields"] if f["key"] == "guest_passport"
        )
        assert campo["placeholder"] == "YY0000"
