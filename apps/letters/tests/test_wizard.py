"""
Testes do assistente real de Carta Convite (Fase 3): criacao (GET nao
grava, POST cria), selecao do modelo publicado POR IDIOMA, fluxo de 6
etapas, persistencia entre etapas, propriedade (CRÍTICO), validacao no
servidor, idioma/tradução dos campos, revisao e fechamento.
"""

import datetime
import uuid

import pytest
from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from apps.doctemplates.models import LetterTemplate
from apps.doctemplates.official_templates import official_slug
from apps.letters import services
from apps.letters.models import Letter

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _nacionalidades_de_teste(nacionalidade_factory):
    """
    Nacionalidades usadas pelos payloads deste arquivo -- desde a decisão
    final da Fase 5/Etapa 3 o campo não aceita mais texto livre. Não é
    uma lista oficial (ver apps/letters/tests/test_nacionalidade_e_documento.py).
    """
    nacionalidade_factory("Brasileira")

    nacionalidade_factory("Belga", host_form="belga")


def _step_url(letter, step):
    return reverse("letters:step", args=[letter.uuid, step])


VALID_STEP_1 = {
    "guest_name": "Maria Santos da Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "15/08/1990",
    "guest_passport": "FA123456",
}
VALID_STEP_2 = {"stay_arrival": "10/04/2025", "stay_departure": "25/04/2025"}
VALID_STEP_3 = {
    "host_nationality": "Belga",
    "host_birth_date": "03/06/1988",
    "host_confirm": "on",
}
VALID_STEP_4 = {"notice_informal": "on", "notice_prise_en_charge": "on"}


def _fill_until(client, letter, step):
    """
    Preenche as etapas ANTERIORES a `step`.

    Desde que os indicadores viraram navegaveis, o servidor so deixa
    avancar ate onde os dados sustentam (services.blocking_step_before):
    pedir a etapa 5 com a 2 em branco devolve a pessoa para a 2. Os testes
    que querem exercitar uma etapa adiante precisam, portanto, chegar la
    pelo caminho.
    """
    payloads = {1: VALID_STEP_1, 2: VALID_STEP_2, 3: VALID_STEP_3, 4: VALID_STEP_4}
    for n in range(1, min(step, 5)):
        client.post(_step_url(letter, n), payloads[n])


def _fill_all_steps(client, letter):
    client.post(_step_url(letter, 1), VALID_STEP_1)
    client.post(_step_url(letter, 2), VALID_STEP_2)
    client.post(_step_url(letter, 3), VALID_STEP_3)
    client.post(_step_url(letter, 4), VALID_STEP_4)
    client.post(_step_url(letter, 5), {"language": "fr"})


@pytest.fixture
def draft_letter(user):
    """
    Um rascunho em branco, criado pela camada de servico — o caminho HTTP
    de criacao tem cobertura propria em TestCriacao.
    """
    return services.start_draft(user, "pt")


# ---------------------------------------------------------------------------
# Criação: GET apresenta, POST cria
# ---------------------------------------------------------------------------


class TestCriacao:
    def test_get_apresenta_a_primeira_etapa_sem_criar_carta(self, auth_client):
        response = auth_client.get(reverse("letters:new"))

        assert response.status_code == 200
        assert response.context["step"] == 1
        assert not Letter.objects.exists()

    def test_get_repetido_nao_acumula_rascunhos(self, auth_client):
        auth_client.get(reverse("letters:new"))
        auth_client.get(reverse("letters:new"))
        auth_client.get(reverse("letters:new"))

        assert not Letter.objects.exists()

    def test_post_valido_cria_uma_unica_carta_em_rascunho(self, auth_client, user):
        response = auth_client.post(reverse("letters:new"), VALID_STEP_1)

        # `get()` já falha se tiver criado mais de uma.
        letter = Letter.objects.get(user=user)
        assert response.status_code == 302
        assert response.url == _step_url(letter, 2)
        assert letter.status == Letter.Status.DRAFT
        assert letter.data["guest_name"] == "Maria Santos da Silva"
        assert letter.data["guest_birth_date"] == "1990-08-15"

    def test_post_invalido_nao_cria_carta(self, auth_client):
        response = auth_client.post(reverse("letters:new"), {"guest_name": ""})

        assert response.status_code == 200
        assert response.context["form"].errors
        assert not Letter.objects.exists()

    def test_usuario_anonimo_nao_pode_iniciar_uma_carta(self, client):
        get_response = client.get(reverse("letters:new"))
        post_response = client.post(reverse("letters:new"), VALID_STEP_1)

        assert get_response.status_code == 302
        assert get_response.url.startswith(reverse("accounts:login"))
        assert post_response.status_code == 302
        assert not Letter.objects.exists()


# ---------------------------------------------------------------------------
# Template/versão usados — um documento oficial por idioma
# ---------------------------------------------------------------------------


class TestSelecaoDeTemplate:
    def test_usa_a_versao_publicada_do_modelo_do_idioma(self, auth_client, user):
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        letter = Letter.objects.get(user=user)

        assert letter.language == "pt"
        assert letter.template.slug == official_slug("pt")
        assert letter.template_version.status == "published"

    @pytest.mark.parametrize("language", ["pt", "fr", "nl", "en"])
    def test_cada_idioma_usa_o_seu_proprio_documento(self, auth_client, user, language):
        auth_client.post(f"/{language}/letters/new/", VALID_STEP_1)
        letter = Letter.objects.get(user=user)

        assert letter.language == language
        assert letter.template.slug == official_slug(language)
        assert letter.template.language == language

    def test_nao_usa_uma_versao_em_rascunho_de_outro_template(
        self, auth_client, user, draft_version
    ):
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        letter = Letter.objects.get(user=user)

        assert letter.template_version_id != draft_version.pk
        assert letter.template_version.status == "published"

    def test_nao_aceita_versao_arbitraria_enviada_pelo_cliente(
        self, auth_client, draft_letter, published_version
    ):
        original_version_id = draft_letter.template_version_id

        auth_client.post(
            _step_url(draft_letter, 1),
            {**VALID_STEP_1, "template_version": published_version.pk, "template": 999},
        )

        draft_letter.refresh_from_db()
        assert draft_letter.template_version_id == original_version_id

    def test_idioma_sem_documento_publicado_nao_inicia_carta(self, auth_client):
        LetterTemplate.objects.filter(slug=official_slug("pt")).update(is_active=False)

        response = auth_client.get(reverse("letters:new"))

        assert response.status_code == 302
        assert response.url == reverse("core:dashboard")
        assert not Letter.objects.exists()

    def test_idioma_sem_documento_nao_cai_no_documento_de_outro_idioma(self, auth_client):
        LetterTemplate.objects.filter(slug=official_slug("nl")).update(is_active=False)

        response = auth_client.post("/nl/letters/new/", VALID_STEP_1)

        assert response.status_code == 302
        assert not Letter.objects.exists()


# ---------------------------------------------------------------------------
# Assistente: seis etapas, avançar, voltar, persistência
# ---------------------------------------------------------------------------


class TestAssistente:
    def test_etapa_1_comeca_vazia(self, auth_client, draft_letter):
        response = auth_client.get(_step_url(draft_letter, 1))

        assert response.status_code == 200
        assert response.context["form"].initial == {}

    def test_avancar_da_etapa_1_para_2(self, auth_client, draft_letter):
        response = auth_client.post(_step_url(draft_letter, 1), VALID_STEP_1)

        assert response.status_code == 302
        assert response.url == _step_url(draft_letter, 2)

    def test_dados_da_etapa_1_ficam_salvos_em_letter_data(self, auth_client, draft_letter):
        auth_client.post(_step_url(draft_letter, 1), VALID_STEP_1)

        draft_letter.refresh_from_db()
        assert draft_letter.data["guest_name"] == "Maria Santos da Silva"
        assert draft_letter.data["guest_birth_date"] == "1990-08-15"
        assert draft_letter.status == Letter.Status.DRAFT

    def test_voltar_para_etapa_anterior_preserva_dados(self, auth_client, draft_letter):
        auth_client.post(_step_url(draft_letter, 1), VALID_STEP_1)

        response = auth_client.get(_step_url(draft_letter, 1))

        assert response.context["form"].initial["guest_name"] == "Maria Santos da Silva"

    def test_reabrir_a_carta_reexibe_o_formulario_pre_preenchido(self, auth_client, draft_letter):
        auth_client.post(_step_url(draft_letter, 1), VALID_STEP_1)
        auth_client.post(_step_url(draft_letter, 2), VALID_STEP_2)

        response = auth_client.get(_step_url(draft_letter, 2))

        assert response.context["form"].initial["stay_arrival"] == datetime.date(2025, 4, 10)

    def test_etapa_3_mostra_dados_do_usuario_logado(self, auth_client, draft_letter, user):
        _fill_until(auth_client, draft_letter, 3)
        response = auth_client.get(_step_url(draft_letter, 3))

        html = response.content.decode()
        assert user.full_name in html
        assert user.phone in html

    def test_sair_no_meio_e_retomar_mantem_progresso(self, auth_client, draft_letter):
        auth_client.post(_step_url(draft_letter, 1), VALID_STEP_1)
        auth_client.post(_step_url(draft_letter, 2), VALID_STEP_2)

        draft_letter.refresh_from_db()
        assert draft_letter.data["guest_name"] == "Maria Santos da Silva"
        assert draft_letter.data["stay_arrival"] == "2025-04-10"
        assert draft_letter.status == Letter.Status.DRAFT

    def test_etapa_acima_do_intervalo_da_404(self, auth_client, draft_letter):
        response = auth_client.get(reverse("letters:step", args=[draft_letter.uuid, 7]))
        assert response.status_code == 404

    def test_etapa_zero_da_404(self, auth_client, draft_letter):
        response = auth_client.get(reverse("letters:step", args=[draft_letter.uuid, 0]))
        assert response.status_code == 404

    def test_carta_inexistente_da_404(self, auth_client):
        response = auth_client.get(reverse("letters:step", args=[uuid.uuid4(), 1]))
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Propriedade (CRÍTICO — seção 9)
# ---------------------------------------------------------------------------


class TestPropriedade:
    def test_usuario_b_nao_acessa_carta_de_a(self, draft_letter, other_user, client):
        client.force_login(other_user)

        response = client.get(_step_url(draft_letter, 1))

        assert response.status_code == 404

    def test_usuario_b_nao_edita_carta_de_a(self, draft_letter, other_user, client):
        client.force_login(other_user)

        response = client.post(_step_url(draft_letter, 1), VALID_STEP_1)

        assert response.status_code == 404
        draft_letter.refresh_from_db()
        assert draft_letter.data == {}

    def test_uuid_de_a_nao_funciona_para_staff_com_visao_global(
        self, draft_letter, django_user_model, client
    ):
        """
        `visible_to()` (leitura/supervisão) é uma regra diferente da edição
        do assistente: mesmo um usuário com `view_all_letters` não pode
        EDITAR a carta de outra pessoa por aqui — só o dono edita.
        """
        gerente = django_user_model.objects.create_user(
            email="gerente@desenrola.be", password="senha-forte-123", full_name="Gerente Geral"
        )
        grupo = Group.objects.create(name="Gerente")
        grupo.permissions.add(
            Permission.objects.get(content_type__app_label="letters", codename="view_all_letters")
        )
        gerente.groups.add(grupo)
        client.force_login(gerente)

        response = client.get(_step_url(draft_letter, 1))

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Validação no servidor (seção 10)
# ---------------------------------------------------------------------------


class TestValidacao:
    def test_etapa_1_recusa_campos_obrigatorios_vazios(self, auth_client, draft_letter):
        response = auth_client.post(_step_url(draft_letter, 1), {})

        assert response.status_code == 200
        assert response.context["form"].errors
        draft_letter.refresh_from_db()
        assert draft_letter.data == {}

    def test_etapa_2_recusa_partida_antes_da_chegada(self, auth_client, draft_letter):
        _fill_until(auth_client, draft_letter, 2)
        response = auth_client.post(
            _step_url(draft_letter, 2),
            {"stay_arrival": "20/04/2025", "stay_departure": "10/04/2025"},
        )

        assert response.status_code == 200
        assert response.context["form"].errors

    def test_etapa_3_exige_confirmar_a_caixa(self, auth_client, draft_letter):
        _fill_until(auth_client, draft_letter, 3)
        dados = {k: v for k, v in VALID_STEP_3.items() if k != "host_confirm"}

        response = auth_client.post(_step_url(draft_letter, 3), dados)

        assert response.status_code == 200
        assert "host_confirm" in response.context["form"].errors

    def test_etapa_4_exige_os_dois_avisos_marcados(self, auth_client, draft_letter):
        _fill_until(auth_client, draft_letter, 4)
        response = auth_client.post(_step_url(draft_letter, 4), {"notice_informal": "on"})

        assert response.status_code == 200
        assert "notice_prise_en_charge" in response.context["form"].errors

    def test_validacao_ignora_o_required_do_html_e_recusa_no_servidor(
        self, auth_client, draft_letter
    ):
        """Simula um POST que não passa pelo formulário renderizado (ex.: via curl)."""
        response = auth_client.post(_step_url(draft_letter, 1), {"guest_name": ""})

        assert response.status_code == 200
        assert response.context["form"].errors["guest_name"]


# ---------------------------------------------------------------------------
# Idioma da carta e tradução dos campos (seções 3 e 12)
# ---------------------------------------------------------------------------


class TestIdioma:
    @pytest.fixture(autouse=True)
    def _chega_na_etapa_do_idioma(self, auth_client, draft_letter):
        """A etapa 5 só é alcançável com as etapas 1-4 preenchidas."""
        _fill_until(auth_client, draft_letter, 5)

    def test_idioma_invalido_e_recusado(self, auth_client, draft_letter):
        response = auth_client.post(_step_url(draft_letter, 5), {"language": "xx"})

        assert response.status_code == 200
        draft_letter.refresh_from_db()
        assert draft_letter.language == "pt"

    def test_trocar_o_idioma_troca_o_documento_oficial(self, auth_client, draft_letter):
        response = auth_client.post(_step_url(draft_letter, 5), {"language": "fr"})

        draft_letter.refresh_from_db()
        assert response.status_code == 302
        assert draft_letter.language == "fr"
        assert draft_letter.template.slug == official_slug("fr")
        assert draft_letter.template_version.template.language == "fr"
        assert draft_letter.template_version.status == "published"

    def test_trocar_o_idioma_preserva_os_dados_ja_preenchidos(self, auth_client, draft_letter):
        auth_client.post(_step_url(draft_letter, 1), VALID_STEP_1)

        auth_client.post(_step_url(draft_letter, 5), {"language": "en"})

        draft_letter.refresh_from_db()
        assert draft_letter.language == "en"
        assert draft_letter.data["guest_name"] == "Maria Santos da Silva"

    @pytest.mark.parametrize(
        ("language", "esperado"),
        [
            ("pt", "Data de nascimento"),
            ("fr", "Date de naissance"),
            ("nl", "Geboortedatum"),
            ("en", "Date of birth"),
        ],
    )
    def test_rotulos_do_formulario_nos_quatro_idiomas(
        self, auth_client, draft_letter, language, esperado
    ):
        auth_client.post(_step_url(draft_letter, 5), {"language": language})

        response = auth_client.get(_step_url(draft_letter, 1))

        assert response.context["form"]["guest_birth_date"].label == esperado
        assert esperado in response.content.decode()

    @pytest.mark.parametrize(
        ("language", "placeholder", "ajuda"),
        [
            ("pt", "Nome completo", "Digite exatamente como aparece no passaporte."),
            ("fr", "Nom complet", "Saisissez exactement comme indiqué sur le passeport."),
            ("nl", "Volledige naam", "Neem exact over zoals vermeld in het paspoort."),
            ("en", "Full name", "Enter exactly as it appears in the passport."),
        ],
    )
    def test_placeholder_e_ajuda_no_idioma_da_carta(
        self, auth_client, draft_letter, language, placeholder, ajuda
    ):
        auth_client.post(_step_url(draft_letter, 5), {"language": language})

        response = auth_client.get(_step_url(draft_letter, 1))
        campo = response.context["form"]["guest_name"]

        assert campo.field.widget.attrs["placeholder"] == placeholder
        assert campo.help_text == ajuda

    def test_texto_sem_traducao_volta_ao_original(self, auth_client, draft_letter):
        """
        As declarações que o usuário aceita ficam sem tradução de
        propósito (texto jurídico não inventado): em qualquer idioma elas
        caem no texto original fornecido pelo projeto.
        """
        auth_client.post(_step_url(draft_letter, 5), {"language": "en"})

        response = auth_client.get(_step_url(draft_letter, 4))
        rotulo = response.context["form"]["notice_informal"].label

        assert rotulo.startswith("Declaro estar ciente")

    def test_revisao_mostra_rotulos_no_idioma_da_carta(self, auth_client, draft_letter):
        _fill_all_steps(auth_client, draft_letter)  # termina em "fr"

        response = auth_client.get(_step_url(draft_letter, 6))
        rotulos = [
            item["label"]
            for secao in response.context["review_sections"]
            for item in secao["items"]
        ]

        assert "Date de naissance" in rotulos
        assert "Nom complet de l'invité" in rotulos

    def test_idioma_sem_documento_publicado_nao_pode_ser_escolhido(
        self, auth_client, draft_letter
    ):
        LetterTemplate.objects.filter(slug=official_slug("nl")).update(is_active=False)

        response = auth_client.post(_step_url(draft_letter, 5), {"language": "nl"})

        draft_letter.refresh_from_db()
        assert response.status_code == 200
        assert draft_letter.language == "pt"
        assert draft_letter.template.slug == official_slug("pt")

    def test_etapa_5_marca_idioma_sem_documento_como_indisponivel(
        self, auth_client, draft_letter
    ):
        LetterTemplate.objects.filter(slug=official_slug("nl")).update(is_active=False)

        response = auth_client.get(_step_url(draft_letter, 5))
        opcoes = {lang["code"]: lang["available"] for lang in response.context["language_options"]}

        assert opcoes == {"pt": True, "fr": True, "nl": False, "en": True}


# ---------------------------------------------------------------------------
# Revisão (seção 13)
# ---------------------------------------------------------------------------


class TestRevisao:
    def test_revisao_mostra_todos_os_dados_preenchidos(self, auth_client, draft_letter):
        _fill_all_steps(auth_client, draft_letter)

        response = auth_client.get(_step_url(draft_letter, 6))
        html = response.content.decode()

        assert response.status_code == 200
        assert "Maria Santos da Silva" in html
        assert "FA123456" in html
        # o documento de identidade saiu do assistente: agora vem do perfil
        assert "592-0000000-00" not in html

    def test_revisao_permite_voltar_a_uma_etapa_especifica(self, auth_client, draft_letter):
        _fill_all_steps(auth_client, draft_letter)

        response = auth_client.get(_step_url(draft_letter, 6))
        html = response.content.decode()

        assert _step_url(draft_letter, 1) in html
        assert _step_url(draft_letter, 5) in html

    def test_revisao_nao_altera_dados(self, auth_client, draft_letter):
        _fill_all_steps(auth_client, draft_letter)
        before = dict(Letter.objects.get(pk=draft_letter.pk).data)

        auth_client.get(_step_url(draft_letter, 6))

        draft_letter.refresh_from_db()
        assert draft_letter.data == before


# ---------------------------------------------------------------------------
# Fechamento (seção 14)
# ---------------------------------------------------------------------------


class TestFinalizacao:
    def test_finalizar_com_tudo_preenchido_gera_a_carta(self, auth_client, draft_letter):
        """
        Com o PDF gerado (Fase 4), o fechamento vai ate GENERATED. O
        COMPLETED intermediario ainda existe: e o estado em que a carta
        fica se a geracao do PDF falhar (ver
        `test_finalizar_sem_cidade_no_perfil_nao_finaliza`).
        """
        _fill_all_steps(auth_client, draft_letter)

        response = auth_client.post(_step_url(draft_letter, 6))

        draft_letter.refresh_from_db()
        assert response.status_code == 302
        assert draft_letter.status == Letter.Status.GENERATED

    def test_finalizar_cria_snapshot(self, auth_client, draft_letter, user):
        _fill_all_steps(auth_client, draft_letter)

        auth_client.post(_step_url(draft_letter, 6))

        draft_letter.refresh_from_db()
        assert draft_letter.snapshot["host"]["full_name"] == user.full_name
        assert draft_letter.snapshot["language"] == "fr"
        assert draft_letter.snapshot["template_slug"] == official_slug("fr")
        assert draft_letter.snapshot["data"]["guest_name"] == "Maria Santos da Silva"

    def test_finalizar_gera_e_guarda_o_pdf(self, auth_client, draft_letter):
        _fill_all_steps(auth_client, draft_letter)

        auth_client.post(_step_url(draft_letter, 6))

        draft_letter.refresh_from_db()
        assert draft_letter.pdf_file
        assert len(draft_letter.pdf_sha256) == 64
        assert draft_letter.generated_at is not None

    def test_nao_finaliza_com_etapa_obrigatoria_incompleta(self, auth_client, draft_letter):
        auth_client.post(_step_url(draft_letter, 1), VALID_STEP_1)
        auth_client.post(_step_url(draft_letter, 2), VALID_STEP_2)
        # Etapas 3 e 4 ficam sem preencher.

        response = auth_client.post(_step_url(draft_letter, 6))

        draft_letter.refresh_from_db()
        assert response.status_code == 302
        assert draft_letter.status == Letter.Status.DRAFT

    def test_nao_finaliza_com_idioma_invalido(self, auth_client, draft_letter):
        """Rede de segurança: mesmo com os dados completos, um idioma fora
        de settings.LANGUAGES no banco impede o fechamento."""
        _fill_all_steps(auth_client, draft_letter)
        Letter.objects.filter(pk=draft_letter.pk).update(language="")

        response = auth_client.post(_step_url(draft_letter, 6))

        draft_letter.refresh_from_db()
        assert response.status_code == 302
        assert response.url == _step_url(draft_letter, services.LANGUAGE_STEP)
        assert draft_letter.status == Letter.Status.DRAFT
