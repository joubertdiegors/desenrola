"""
Testes do dashboard real (Fase 5): o que a pessoa vê são as cartas DELA,
vindas do banco.

A privacidade é o ponto central: o dashboard pessoal usa
`filter(user=...)`, e não `Letter.objects.visible_to()` -- quem tem a
permissão de supervisão continua vendo só as próprias cartas aqui.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.letters import presentation, services
from apps.letters.models import Letter

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

    nacionalidade_factory("Belga", host_form="belga")


DASHBOARD = reverse("core:dashboard")


def _criar_carta(user, *, status=Letter.Status.DRAFT, data=None, language="fr"):
    letter = services.start_draft(user, language)
    if data is not None:
        letter.data = data
    letter.status = status
    letter.save()
    return letter


DADOS_COMPLETOS = {
    "guest_name": "Maria Santos da Silva",
    "stay_arrival": "2026-10-10",
    "stay_departure": "2026-10-24",
}


# ---------------------------------------------------------------------------
# Acesso
# ---------------------------------------------------------------------------


def test_dashboard_exige_login(client):
    response = client.get(DASHBOARD)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={DASHBOARD}"


def test_dashboard_abre_para_usuario_logado(auth_client):
    response = auth_client.get(DASHBOARD)

    assert response.status_code == 200
    assert "Olá, Claire" in response.content.decode()


# ---------------------------------------------------------------------------
# Privacidade
# ---------------------------------------------------------------------------


class TestSoAsProprias:
    def test_lista_somente_as_cartas_do_usuario(self, auth_client, user, other_user):
        minha = _criar_carta(user, data={"guest_name": "Convidada Minha"})
        alheia = _criar_carta(other_user, data={"guest_name": "Convidado Alheio"})

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert "Convidada Minha" in corpo
        assert "Convidado Alheio" not in corpo
        assert str(minha.uuid) in corpo
        assert str(alheia.uuid) not in corpo

    def test_permissao_de_ver_todas_nao_muda_o_dashboard_pessoal(
        self, client, user, other_user, permissao_ver_todas
    ):
        """
        `letters.view_all_letters` é para uma tela de supervisão. A área
        pessoal continua sendo pessoal.
        """
        user.user_permissions.add(permissao_ver_todas)
        client.force_login(user)
        _criar_carta(user, data={"guest_name": "Convidada Minha"})
        _criar_carta(other_user, data={"guest_name": "Convidado Alheio"})

        corpo = client.get(DASHBOARD).content.decode()

        assert "Convidada Minha" in corpo
        assert "Convidado Alheio" not in corpo

    def test_contador_conta_somente_as_proprias(self, auth_client, user, other_user):
        for _ in range(3):
            _criar_carta(user)
        _criar_carta(other_user)

        contexto = auth_client.get(DASHBOARD).context

        assert contexto["letters_total"] == 3


# ---------------------------------------------------------------------------
# Lista: limite, ordem e contador
# ---------------------------------------------------------------------------


class TestListagem:
    def test_mostra_no_maximo_cinco_cartas(self, auth_client, user):
        for i in range(7):
            _criar_carta(user, data={"guest_name": f"Convidado {i}"})

        contexto = auth_client.get(DASHBOARD).context

        assert len(contexto["cards"]) == presentation.RECENT_LIMIT == 5

    def test_contador_mostra_o_total_e_nao_o_que_coube_na_lista(self, auth_client, user):
        for i in range(7):
            _criar_carta(user, data={"guest_name": f"Convidado {i}"})

        contexto = auth_client.get(DASHBOARD).context

        assert contexto["letters_total"] == 7
        assert len(contexto["cards"]) == 5

    def test_ordena_da_mais_recentemente_mexida_para_a_mais_antiga(self, auth_client, user):
        antiga = _criar_carta(user, data={"guest_name": "Antiga"})
        recente = _criar_carta(user, data={"guest_name": "Recente"})

        # mexer na antiga a coloca na frente
        antiga.data = {"guest_name": "Antiga"}
        antiga.save()

        cards = auth_client.get(DASHBOARD).context["cards"]

        assert [c.uuid for c in cards] == [antiga.uuid, recente.uuid]

    def test_estado_vazio_quando_nao_ha_cartas(self, auth_client):
        response = auth_client.get(DASHBOARD)
        corpo = response.content.decode()

        assert response.context["letters_total"] == 0
        assert response.context["cards"] == []
        assert "Você ainda não tem cartas" in corpo
        # a ação de sair do estado vazio tem de estar ali
        assert reverse("letters:new") in corpo

    def test_com_cartas_o_estado_vazio_some(self, auth_client, user):
        _criar_carta(user, data={"guest_name": "Alguém"})

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert "Você ainda não tem cartas" not in corpo


# ---------------------------------------------------------------------------
# Conteúdo de cada carta
# ---------------------------------------------------------------------------


class TestConteudoDaCarta:
    def test_mostra_convidado_periodo_idioma_e_data(self, auth_client, user):
        _criar_carta(user, data=DADOS_COMPLETOS, language="fr")

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert "Maria Santos da Silva" in corpo
        assert "10/10/2026" in corpo
        assert "24/10/2026" in corpo
        assert "Français" in corpo

    def test_carta_sem_convidado_preenchido_nao_inventa_nome(self, auth_client, user):
        _criar_carta(user, data={})

        cards = auth_client.get(DASHBOARD).context["cards"]

        assert cards[0].guest_name == ""
        assert cards[0].arrival is None
        assert cards[0].has_period is False

    def test_carta_fechada_mostra_os_dados_do_snapshot(self, auth_client, user):
        """
        Depois de fechada, a tela mostra o que virou documento -- não o
        que estiver em `data` agora.
        """
        letter = _criar_carta(user, status=Letter.Status.GENERATED, data={"guest_name": "Antigo"})
        letter.snapshot = {"data": {"guest_name": "Congelado no snapshot"}}
        letter.save(update_fields=["snapshot"])

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert "Congelado no snapshot" in corpo
        assert "Antigo" not in corpo

    def test_referencia_real_aparece_no_detalhe(self, auth_client, user):
        letter = _criar_carta(user, data=DADOS_COMPLETOS)

        corpo = auth_client.get(reverse("letters:detail", args=[letter.uuid])).content.decode()

        assert letter.reference in corpo
        assert letter.reference.startswith("DSR-")


# ---------------------------------------------------------------------------
# Estados
# ---------------------------------------------------------------------------


class TestEstados:
    @pytest.mark.parametrize(
        "status,rotulo",
        [
            (Letter.Status.DRAFT, "Rascunho"),
            (Letter.Status.COMPLETED, "Concluída"),
            (Letter.Status.GENERATED, "Gerada"),
            (Letter.Status.CANCELLED, "Cancelada"),
        ],
    )
    def test_cada_status_aparece_com_o_seu_rotulo(self, auth_client, user, status, rotulo):
        _criar_carta(user, status=status, data=DADOS_COMPLETOS)

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert rotulo in corpo

    def test_cada_status_tem_etiqueta_visualmente_distinta(self, auth_client, user):
        classes = {}
        for status in Letter.Status:
            Letter.objects.filter(user=user).delete()
            _criar_carta(user, status=status, data=DADOS_COMPLETOS)
            corpo = auth_client.get(DASHBOARD).content.decode()
            classes[status] = {
                cls
                for cls in ("tag-success", "tag-primary", "tag-warning", "tag-neutral")
                if f"tag {cls}" in corpo
            }

        usadas = [next(iter(v)) for v in classes.values()]
        assert len(set(usadas)) == 4, f"estados sem cor própria: {classes}"

    def test_gerada_com_pdf_oferece_ver_pdf(self, auth_client, user):
        from django.core.files.base import ContentFile

        letter = _criar_carta(user, status=Letter.Status.GENERATED, data=DADOS_COMPLETOS)
        letter.pdf_file.save("x.pdf", ContentFile(b"%PDF-1.4"), save=True)

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert reverse("letters:pdf", args=[letter.uuid]) in corpo
        assert "Ver PDF" in corpo

    def test_concluida_sem_pdf_nao_oferece_ver_pdf(self, auth_client, user):
        """COMPLETED é registrada mas sem documento: não pode prometer um
        PDF que não existe."""
        letter = _criar_carta(user, status=Letter.Status.COMPLETED, data=DADOS_COMPLETOS)

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert not letter.pdf_file
        assert reverse("letters:pdf", args=[letter.uuid]) not in corpo

    def test_cancelada_nao_oferece_continuar_nem_gerar(self, auth_client, user):
        letter = _criar_carta(user, status=Letter.Status.CANCELLED, data=DADOS_COMPLETOS)

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert "Continuar" not in corpo
        assert reverse("letters:pdf", args=[letter.uuid]) not in corpo


# ---------------------------------------------------------------------------
# Continuar rascunho
# ---------------------------------------------------------------------------


class TestContinuarRascunho:
    def test_continuar_aponta_para_a_uuid_e_nao_para_uma_carta_nova(self, auth_client, user):
        letter = _criar_carta(user, data=DADOS_COMPLETOS)

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert str(letter.uuid) in corpo
        assert "Continuar" in corpo

    def test_rascunho_em_branco_retoma_na_primeira_etapa(self, auth_client, user):
        letter = _criar_carta(user, data={})

        card = auth_client.get(DASHBOARD).context["cards"][0]

        assert card.resume_step == services.FIRST_STEP
        assert reverse("letters:step", args=[letter.uuid, 1]) in (
            auth_client.get(DASHBOARD).content.decode()
        )

    def test_retoma_na_primeira_etapa_ainda_incompleta(self, auth_client, user):
        """Etapa 1 preenchida, etapa 2 não: retoma na 2."""
        letter = _criar_carta(
            user,
            data={
                "guest_name": "Maria Santos da Silva",
                "guest_nationality": "Brasileira",
                "guest_birth_date": "1990-08-15",
                "guest_passport": "FA123456",
            },
        )

        card = auth_client.get(DASHBOARD).context["cards"][0]

        assert card.resume_step == 2
        assert reverse("letters:step", args=[letter.uuid, 2]) in (
            auth_client.get(DASHBOARD).content.decode()
        )

    def test_rascunho_completo_retoma_na_revisao(self, auth_client, user):
        letter = _criar_carta(user)
        letter.data = {
            "guest_name": "Maria Santos da Silva",
            "guest_nationality": "Brasileira",
            "guest_birth_date": "1990-08-15",
            "guest_passport": "FA123456",
            "stay_arrival": (
                timezone.localdate() + datetime.timedelta(days=30)
            ).isoformat(),
            "stay_departure": (
                timezone.localdate() + datetime.timedelta(days=45)
            ).isoformat(),
            "host_confirm": True,
            "notice_informal": True,
            "notice_prise_en_charge": True,
        }
        letter.save(update_fields=["data"])

        card = auth_client.get(DASHBOARD).context["cards"][0]

        assert card.resume_step == services.REVIEW_STEP

    def test_ninguem_continua_o_rascunho_de_outro(self, client, user, other_user):
        alheio = _criar_carta(other_user, data=DADOS_COMPLETOS)
        client.force_login(user)

        response = client.get(reverse("letters:step", args=[alheio.uuid, 1]))

        assert response.status_code == 404

    def test_carta_que_nao_e_rascunho_nao_tem_etapa_para_retomar(self, auth_client, user):
        _criar_carta(user, status=Letter.Status.GENERATED, data=DADOS_COMPLETOS)

        card = auth_client.get(DASHBOARD).context["cards"][0]

        assert card.resume_step is None


# ---------------------------------------------------------------------------
# Sem mock
# ---------------------------------------------------------------------------


class TestSemDadosFicticios:
    def test_a_view_do_dashboard_nao_usa_o_modulo_demo(self):
        import inspect

        from apps.core import views

        fonte = inspect.getsource(views.dashboard)
        assert "demo" not in fonte

    def test_o_modulo_demo_nao_tem_mais_lista_de_cartas_do_dashboard(self):
        from apps.core import demo

        assert not hasattr(demo, "LETTERS")
        assert not hasattr(demo, "get_letter")

    def test_nenhum_nome_ficticio_aparece_no_dashboard(self, auth_client, user):
        """Os nomes dos layouts de referência não podem mais vazar."""
        _criar_carta(user, data={"guest_name": "Convidada Real"})

        corpo = auth_client.get(DASHBOARD).content.decode()

        for ficticio in ("João Pedro Alves", "Ana Beatriz Rocha", "Carta-Convite-"):
            assert ficticio not in corpo

    def test_datas_vem_do_banco_e_nao_de_texto_fixo(self, auth_client, user):
        letter = _criar_carta(user, data=DADOS_COMPLETOS)

        corpo = auth_client.get(DASHBOARD).content.decode()

        esperado = letter.updated_at.astimezone().strftime("%d/%m/%Y")
        assert esperado in corpo
        assert isinstance(letter.updated_at, datetime.datetime)


class TestConsultas:
    def test_listar_mais_cartas_nao_multiplica_as_consultas(
        self, auth_client, user, django_assert_max_num_queries
    ):
        """
        O cartao precisa do field_schema da versao do modelo (para saber
        em que etapa o rascunho parou). Sem `select_related` isso viraria
        uma consulta por carta -- este teste trava esse regresso.
        """
        for i in range(presentation.RECENT_LIMIT):
            _criar_carta(user, data={"guest_name": f"Convidado {i}"})

        auth_client.get(DASHBOARD)  # aquece sessao/usuario

        with django_assert_max_num_queries(8):
            auth_client.get(DASHBOARD)
