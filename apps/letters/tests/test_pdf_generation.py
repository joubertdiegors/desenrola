"""
Testes da ponte entre Letter/snapshot (apps.letters) e o motor de PDF
(pdfengine): `apps.letters.pdf_generation` e `services.generate_pdf`.

Cobre o que so faz sentido testar com Django -- o snapshot real de uma
Letter finalizada, a origem da cidade do anfitriao e o armazenamento do
PDF. A geracao do PDF em si tem cobertura isolada em
tests/test_pdfengine_render_fr.py.
"""

import hashlib
import io

import pytest
from django.urls import reverse
from pypdf import PdfReader

from apps.letters import services
from apps.letters.models import Letter
from apps.letters.pdf_generation import (
    MissingSnapshotError,
    UnsupportedLanguageError,
    UnsupportedTemplateError,
    build_pdf_fields,
    render_letter_pdf,
)
from pdfengine.exceptions import MissingHostCityError, MissingSnapshotDataError
from pdfengine.render import render_invitation_letter_fr

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _nacionalidades_de_teste(nacionalidade_factory):
    """
    Nacionalidades usadas pelos payloads deste arquivo -- desde a decisão
    final da Fase 5/Etapa 3 o campo não aceita mais texto livre. Não é
    uma lista oficial (ver apps/letters/tests/test_nacionalidade_e_documento.py).
    """
    nacionalidade_factory("Brésilienne", guest_form="Brésilienne")

    nacionalidade_factory("belge", guest_form="Belge", host_form="belge")


def _step_url(letter, step):
    return reverse("letters:step", args=[letter.uuid, step])


VALID_STEP_1 = {
    "guest_name": "Carlos Eduardo Silva",
    "guest_nationality": "Brésilienne",
    "guest_birth_date": "22/07/1990",
    "guest_passport": "YY000000",
}
VALID_STEP_2 = {"stay_arrival": "10/10/2026", "stay_departure": "24/10/2026"}
VALID_STEP_3 = {
    "host_confirm": "on",
}
VALID_STEP_4 = {"notice_informal": "on", "notice_prise_en_charge": "on"}


def _carta_finalizada(auth_client, user):
    """Percorre o assistente REAL de ponta a ponta e devolve a carta ja
    finalizada (com o PDF gerado)."""
    auth_client.post(reverse("letters:new"), VALID_STEP_1)
    letter = Letter.objects.get(user=user)
    auth_client.post(_step_url(letter, 2), VALID_STEP_2)
    auth_client.post(_step_url(letter, 3), VALID_STEP_3)
    auth_client.post(_step_url(letter, 4), VALID_STEP_4)
    auth_client.post(_step_url(letter, 5), {"language": "fr"})
    auth_client.post(_step_url(letter, 6))
    letter.refresh_from_db()
    return letter


@pytest.fixture
def versao_oficial_fr(db):
    """A TemplateVersion publicada do modelo oficial FRANCES -- a de
    verdade, semeada pela migration, nao um modelo de teste generico."""
    from apps.doctemplates.models import TemplateVersion
    from apps.doctemplates.official_templates import official_slug

    return TemplateVersion.objects.get(
        template__slug=official_slug("fr"), status=TemplateVersion.Status.PUBLISHED
    )


@pytest.fixture
def snapshot_completo():
    """Um snapshot no formato real de `services.build_snapshot`."""
    return {
        "data": {
            "guest_name": "Carlos Eduardo Silva",
            "guest_nationality": "Brésilienne",
            "guest_birth_date": "1990-07-22",
            "guest_passport": "YY000000",
            "stay_arrival": "2026-10-10",
            "stay_departure": "2026-10-24",
            "host_confirm": True,
            "notice_informal": True,
            "notice_prise_en_charge": True,
        },
        "language": "fr",
        "template_slug": "carta-convite-curta-duracao-fr",
        "template_version_number": 1,
        "host": {
            "full_name": "Claire Dubois",
            "phone": "+32 470 00 00 00",
            "address": "Rue des Exemple 25 - 1200 Woluwe-Saint-Lambert",
            "city": "Woluwe-Saint-Lambert",
            "document_number": "00000000",
            "birth_date": "1985-03-14",
        },
        # formas já resolvidas no fechamento (ver nationalities.document_forms)
        "nationalities": {
            "guest_nationality": "Brésilienne",
            "host_nationality": "belge",
        },
        "finalized_at": "2026-09-09T10:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# A cidade e um dado ESTRUTURADO do perfil, separado do endereco
# ---------------------------------------------------------------------------


class TestCidadeEstruturadaNoPerfil:
    def test_user_ja_tem_campo_city_proprio(self, user):
        """
        A cidade nao precisou ser criada: o User ja a guardava num campo
        proprio (apps/accounts/models.py). Nenhuma migration nova foi
        necessaria para a decisao de negocio desta etapa.
        """
        assert hasattr(user, "city")
        assert user.city == "Woluwe-Saint-Lambert"

    def test_cidade_e_separada_do_endereco(self, user):
        """O endereco continua no seu proprio campo; a cidade nao e um
        pedaco de texto dentro dele."""
        assert user.address_line1 == "Rue des Exemple 25"
        assert user.city == "Woluwe-Saint-Lambert"
        assert user.city not in user.address_line1

    def test_cidade_e_editavel_no_perfil(self):
        from apps.accounts.forms import PROFILE_FIELDS, ProfileForm

        assert "city" in PROFILE_FIELDS
        assert "city" in ProfileForm().fields


# ---------------------------------------------------------------------------
# A cidade entra no snapshot, e e de la que sai o `place` do PDF
# ---------------------------------------------------------------------------


class TestCidadeNoSnapshot:
    def test_snapshot_congela_a_cidade_separadamente(self, auth_client, user):
        letter = _carta_finalizada(auth_client, user)

        assert letter.snapshot["host"]["city"] == "Woluwe-Saint-Lambert"
        # e o endereco completo continua la, sem se confundir com ela
        assert letter.snapshot["host"]["address"].startswith("Rue des Exemple 25")

    def test_place_do_pdf_vem_da_cidade_do_snapshot(self, snapshot_completo):
        snapshot_completo["host"]["city"] = "Gand"
        fields = build_pdf_fields(snapshot_completo)
        assert fields["place"] == "Gand"

    def test_place_nao_vem_do_endereco(self, snapshot_completo):
        """O endereco cita uma cidade diferente da do campo `city`: o
        fecho tem que seguir o campo estruturado, nunca o texto do
        endereco."""
        snapshot_completo["host"]["address"] = "Avenue Louise 1 – 1050 Bruxelles"
        snapshot_completo["host"]["city"] = "Woluwe-Saint-Lambert"

        fields = build_pdf_fields(snapshot_completo)

        assert fields["place"] == "Woluwe-Saint-Lambert"

    def test_endereco_longo_nao_e_usado_para_descobrir_a_cidade(self, snapshot_completo):
        """Sem `city`, um endereco cheio de nomes de lugar continua nao
        servindo de fonte: falha em vez de adivinhar."""
        snapshot_completo["host"]["address"] = (
            "Avenue Louise 523, Boîte 12B – 1050 Ixelles, Bruxelles-Capitale, Belgique"
        )
        snapshot_completo["host"]["city"] = ""

        with pytest.raises(MissingHostCityError):
            build_pdf_fields(snapshot_completo)


# ---------------------------------------------------------------------------
# `document_place` nao existe como campo do formulario
# ---------------------------------------------------------------------------


class TestDocumentPlaceNaoEhCampoDoFormulario:
    def test_field_schema_oficial_nao_tem_document_place(self):
        """
        Nem na definicao de origem, nem nas versoes publicadas de cada
        idioma que a migration semeia: o local do fecho nao e um campo
        configuravel da carta.
        """
        from apps.doctemplates.models import TemplateVersion
        from apps.doctemplates.official_templates import (
            CARTA_CONVITE_FIELD_SCHEMA,
            CARTA_CONVITE_SLUG_PREFIX,
        )

        schemas = [CARTA_CONVITE_FIELD_SCHEMA]
        schemas += list(
            TemplateVersion.objects.filter(
                template__slug__startswith=CARTA_CONVITE_SLUG_PREFIX
            ).values_list("field_schema", flat=True)
        )
        assert len(schemas) > 1, "as versões oficiais por idioma deveriam existir"

        for schema in schemas:
            keys = {field["key"] for field in schema["fields"]}
            assert "document_place" not in keys
            assert "place" not in keys

    def test_assistente_nunca_pede_o_local(self, auth_client, user):
        """Nenhuma etapa do assistente apresenta um campo de local/cidade
        da carta -- o dado vem do perfil."""
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        letter = Letter.objects.get(user=user)

        for step in (1, 2, 3, 4):
            html = auth_client.get(_step_url(letter, step)).content.decode()
            assert 'name="document_place"' not in html
            assert 'name="place"' not in html

    def test_dados_da_carta_nao_guardam_local(self, auth_client, user):
        letter = _carta_finalizada(auth_client, user)
        assert "document_place" not in letter.data
        assert "place" not in letter.data


# ---------------------------------------------------------------------------
# Carta real finalizada gera, guarda e marca o PDF
# ---------------------------------------------------------------------------


class TestCartaRealGeraPdf:
    def test_carta_finalizada_gera_pdf(self, auth_client, user):
        letter = _carta_finalizada(auth_client, user)

        assert letter.pdf_file
        assert letter.pdf_file.size > 10_000

    def test_pdf_e_salvo_em_pdf_file(self, auth_client, user):
        letter = _carta_finalizada(auth_client, user)

        with letter.pdf_file.open("rb") as fh:
            content = fh.read()
        assert content.startswith(b"%PDF")

    def test_sha256_e_salvo_e_confere_com_o_arquivo(self, auth_client, user):
        letter = _carta_finalizada(auth_client, user)

        with letter.pdf_file.open("rb") as fh:
            content = fh.read()
        assert letter.pdf_sha256 == hashlib.sha256(content).hexdigest()

    def test_status_vira_generated_e_marca_o_instante(self, auth_client, user):
        letter = _carta_finalizada(auth_client, user)

        assert letter.status == Letter.Status.GENERATED
        assert letter.generated_at is not None

    def test_cidade_aparece_no_pdf_gerado(self, auth_client, user):
        letter = _carta_finalizada(auth_client, user)

        with letter.pdf_file.open("rb") as fh:
            text = PdfReader(io.BytesIO(fh.read())).pages[0].extract_text()

        assert "Woluwe-Saint-Lambert" in text
        assert "Fait" in text

    def test_carta_real_reproduz_os_dados_do_documento_oficial(self, auth_client, user):
        """
        O perfil da fixture e os dados do assistente sao os MESMOS do
        documento oficial, entao o PDF de uma carta real tem que trazer
        exatamente os mesmos valores -- inclusive a duracao inclusiva
        ("15 jours" para 10/10 a 24/10, como no original).
        """
        letter = _carta_finalizada(auth_client, user)

        with letter.pdf_file.open("rb") as fh:
            text = PdfReader(io.BytesIO(fh.read())).pages[0].extract_text()
        sem_espacos = " ".join(text.split())

        for esperado in (
            "Claire Dubois",
            "14/03/1985",
            "Carlos Eduardo Silva",
            "Brésilienne",
            "22/07/1990",
            "YY000000",
            "10/10/2026",
            "24/10/2026",
            "(15 jours)",
            "Woluwe-Saint-Lambert",
        ):
            assert esperado in sem_espacos, f"{esperado!r} não saiu no PDF da carta real"

    def test_pdf_gerado_continua_a4_com_uma_pagina(self, auth_client, user):
        letter = _carta_finalizada(auth_client, user)

        with letter.pdf_file.open("rb") as fh:
            reader = PdfReader(io.BytesIO(fh.read()))

        assert len(reader.pages) == 1
        assert float(reader.pages[0].mediabox.width) == 596.0
        assert float(reader.pages[0].mediabox.height) == 842.0

    def test_status_so_vira_generated_apos_geracao_bem_sucedida(
        self, auth_client, user, monkeypatch
    ):
        """Se a geracao falhar, a carta fica registrada (COMPLETED) mas
        NAO e marcada como gerada nem ganha arquivo."""
        from apps.letters import services as services_module

        def explode(letter):
            raise MissingSnapshotDataError("falha simulada na geração")

        monkeypatch.setattr(services_module, "generate_pdf", explode)

        letter = _carta_finalizada(auth_client, user)

        assert letter.status == Letter.Status.COMPLETED
        assert not letter.pdf_file
        assert letter.pdf_sha256 == ""
        assert letter.generated_at is None


class TestPerfilIncompletoBarraAFinalizacao:
    """
    Sem a cidade, a carta NAO e finalizada -- em vez de congelar um
    snapshot sem ela e deixar a carta presa (o snapshot e imutavel: o PDF
    continuaria impossivel mesmo depois de o usuario corrigir o perfil).
    """

    def _preencher_ate_a_revisao(self, auth_client, user):
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        letter = Letter.objects.get(user=user)
        auth_client.post(_step_url(letter, 2), VALID_STEP_2)
        auth_client.post(_step_url(letter, 3), VALID_STEP_3)
        auth_client.post(_step_url(letter, 4), VALID_STEP_4)
        auth_client.post(_step_url(letter, 5), {"language": "fr"})
        return letter

    def test_sem_cidade_a_carta_nao_e_finalizada(self, auth_client, user):
        letter = self._preencher_ate_a_revisao(auth_client, user)
        user.city = ""
        user.save(update_fields=["city"])

        response = auth_client.post(_step_url(letter, 6))

        letter.refresh_from_db()
        assert response.status_code == 302
        assert response["Location"].endswith(reverse("accounts:profile"))
        assert letter.status == Letter.Status.DRAFT
        assert letter.snapshot == {}
        assert not letter.pdf_file

    def test_a_mensagem_diz_o_que_falta(self, auth_client, user):
        from django.contrib.messages import get_messages

        letter = self._preencher_ate_a_revisao(auth_client, user)
        user.city = ""
        user.save(update_fields=["city"])

        response = auth_client.post(_step_url(letter, 6))
        textos = " ".join(str(m) for m in get_messages(response.wsgi_request))

        assert "cidade" in textos.lower()

    def test_com_o_perfil_corrigido_a_carta_finaliza(self, auth_client, user):
        letter = self._preencher_ate_a_revisao(auth_client, user)
        user.city = ""
        user.save(update_fields=["city"])
        auth_client.post(_step_url(letter, 6))

        user.city = "Gand"
        user.save(update_fields=["city"])
        auth_client.post(_step_url(letter, 6))

        letter.refresh_from_db()
        assert letter.status == Letter.Status.GENERATED
        assert letter.snapshot["host"]["city"] == "Gand"

    def test_nada_falta_com_o_perfil_completo(self, user):
        assert services.missing_host_profile_fields(user) == []


class TestIdiomaSemDocumentoOficialNoAssistente:
    """
    Escolher um idioma que ainda nao tem documento oficial nao e uma
    falha do sistema -- a carta fica registrada e o aviso diz o motivo
    real, em vez de sugerir que algo quebrou.
    """

    def test_idioma_sem_pdf_oficial_registra_a_carta_sem_gerar(self, auth_client, user):
        from django.contrib.messages import get_messages

        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        letter = Letter.objects.get(user=user)
        auth_client.post(_step_url(letter, 2), VALID_STEP_2)
        auth_client.post(_step_url(letter, 3), VALID_STEP_3)
        auth_client.post(_step_url(letter, 4), VALID_STEP_4)
        auth_client.post(_step_url(letter, 5), {"language": "nl"})

        response = auth_client.post(_step_url(letter, 6))
        textos = " ".join(str(m) for m in get_messages(response.wsgi_request))

        letter.refresh_from_db()
        assert letter.status == Letter.Status.COMPLETED
        assert not letter.pdf_file
        assert letter.pdf_sha256 == ""
        assert "francês" in textos


# ---------------------------------------------------------------------------
# O PDF historico nao muda quando o perfil muda
# ---------------------------------------------------------------------------


class TestReproducaoHistorica:
    def test_alterar_a_cidade_do_perfil_nao_altera_a_carta_ja_emitida(
        self, auth_client, user
    ):
        letter = _carta_finalizada(auth_client, user)
        antes = letter.pdf_sha256

        user.city = "Brussels"
        user.full_name = "Outro Nome Qualquer"
        user.save()

        # regerar a MESMA carta: a fonte e o snapshot, nao o perfil atual
        services.generate_pdf(letter)
        letter.refresh_from_db()

        assert letter.snapshot["host"]["city"] == "Woluwe-Saint-Lambert"
        assert letter.pdf_sha256 == antes

        with letter.pdf_file.open("rb") as fh:
            text = PdfReader(io.BytesIO(fh.read())).pages[0].extract_text()
        assert "Woluwe-Saint-Lambert" in text
        assert "Brussels" not in text
        assert "Outro" not in text

    def test_build_pdf_fields_nao_busca_dado_ao_vivo_do_usuario(
        self, snapshot_completo, user
    ):
        user.full_name = "Nome Totalmente Diferente Depois"
        user.city = "Anvers"
        user.save()

        fields = build_pdf_fields(snapshot_completo)

        assert fields["host_name"] == "Claire Dubois"
        assert fields["place"] == "Woluwe-Saint-Lambert"


# ---------------------------------------------------------------------------
# Erros explicitos
# ---------------------------------------------------------------------------


class TestErrosExplicitos:
    def test_ausencia_de_cidade_impede_a_geracao(self, snapshot_completo):
        del snapshot_completo["host"]["city"]
        with pytest.raises(MissingHostCityError):
            build_pdf_fields(snapshot_completo)

    def test_cidade_so_com_espacos_tambem_impede(self, snapshot_completo):
        snapshot_completo["host"]["city"] = "   "
        with pytest.raises(MissingHostCityError):
            build_pdf_fields(snapshot_completo)

    def test_erro_de_cidade_explica_o_que_fazer(self, snapshot_completo):
        snapshot_completo["host"]["city"] = ""
        with pytest.raises(MissingHostCityError) as excinfo:
            build_pdf_fields(snapshot_completo)
        assert "cidade" in str(excinfo.value).lower()

    def test_sem_cidade_o_fecho_nunca_sai_vazio(self, snapshot_completo):
        """
        Garantia do RESULTADO, nao so do erro: nao existe caminho que
        produza um fecho sem cidade.
        """
        snapshot_completo["host"]["city"] = ""
        with pytest.raises(MissingHostCityError):
            render_invitation_letter_fr(build_pdf_fields(snapshot_completo))

    @pytest.mark.parametrize(
        "remocao",
        [
            lambda s: s["data"].pop("guest_name"),
            lambda s: s["host"].pop("birth_date"),
            lambda s: s["host"].pop("full_name"),
            lambda s: s.pop("finalized_at"),
        ],
    )
    def test_campo_ausente_no_snapshot_levanta_erro_explicito(
        self, snapshot_completo, remocao
    ):
        remocao(snapshot_completo)
        with pytest.raises(MissingSnapshotDataError):
            build_pdf_fields(snapshot_completo)

    def test_erro_nao_inventa_valor_nenhum(self, snapshot_completo):
        del snapshot_completo["data"]["guest_passport"]
        with pytest.raises(MissingSnapshotDataError) as excinfo:
            build_pdf_fields(snapshot_completo)
        assert "guest_passport" in str(excinfo.value) or "obrigatório" in str(excinfo.value)

    def test_snapshot_ausente_falha_explicitamente(self, versao_oficial_fr):
        with pytest.raises(MissingSnapshotError):
            render_letter_pdf(template_version=versao_oficial_fr, snapshot={})

    def test_idioma_sem_renderer_falha_explicitamente(self, snapshot_completo, db):
        """Os outros idiomas tem modelo oficial publicado (Fase 3), mas
        ainda nao tem PDF oficial -- entao a geracao recusa, em vez de
        cair no documento frances."""
        from apps.doctemplates.models import TemplateVersion
        from apps.doctemplates.official_templates import official_slug

        versao_nl = TemplateVersion.objects.get(
            template__slug=official_slug("nl"), status=TemplateVersion.Status.PUBLISHED
        )

        with pytest.raises(UnsupportedLanguageError):
            render_letter_pdf(template_version=versao_nl, snapshot=snapshot_completo)

    def test_modelo_que_nao_e_a_carta_convite_falha_explicitamente(
        self, snapshot_completo, letter_template, draft_version
    ):
        """Um modelo diferente (outro tipo de documento) nao pode ser
        desenhado com o layout da Carta Convite."""
        draft_version.publish()

        with pytest.raises(UnsupportedTemplateError):
            render_letter_pdf(template_version=draft_version, snapshot=snapshot_completo)


# ---------------------------------------------------------------------------
# Campos derivados e assinatura da API
# ---------------------------------------------------------------------------


class TestBuildPdfFields:
    def test_resolve_todos_os_campos_exigidos_pelo_renderer(self, snapshot_completo):
        pdf_bytes = render_invitation_letter_fr(build_pdf_fields(snapshot_completo))
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000

    def test_datas_saem_formatadas_dd_mm_aaaa(self, snapshot_completo):
        fields = build_pdf_fields(snapshot_completo)
        assert fields["guest_birth"] == "22/07/1990"
        assert fields["arrival_date"] == "10/10/2026"
        assert fields["departure_date"] == "24/10/2026"
        assert fields["host_birth"] == "14/03/1985"

    def test_document_date_vem_do_instante_de_finalizacao(self, snapshot_completo):
        """A data do documento e a data de emissao congelada no snapshot
        -- nunca a data de hoje."""
        fields = build_pdf_fields(snapshot_completo)
        assert fields["document_date"] == "09/09/2026"

    def test_document_date_acompanha_o_snapshot_e_nao_o_relogio(self, snapshot_completo):
        snapshot_completo["finalized_at"] = "2024-01-31T23:00:00+00:00"
        fields = build_pdf_fields(snapshot_completo)
        assert fields["document_date"] == "31/01/2024"

    def test_duration_days_e_computado_nao_armazenado(self, snapshot_completo):
        """
        Contagem INCLUSIVA, como no documento oficial: de 10/10 a 24/10
        sao 15 dias (nao 14). E recalculada a cada geracao, nunca lida de
        um campo guardado.
        """
        fields = build_pdf_fields(snapshot_completo)
        assert fields["duration_days"] == "15"

    def test_duration_days_de_um_unico_dia_conta_um(self, snapshot_completo):
        snapshot_completo["data"]["stay_departure"] = snapshot_completo["data"]["stay_arrival"]
        assert build_pdf_fields(snapshot_completo)["duration_days"] == "1"

    def test_signature_name_reaproveita_o_nome_do_anfitriao(self, snapshot_completo):
        fields = build_pdf_fields(snapshot_completo)
        assert fields["signature_name"] == fields["host_name"] == "Claire Dubois"


class TestRenderLetterPdf:
    def test_idioma_frances_gera_o_pdf(self, snapshot_completo, versao_oficial_fr):
        pdf_bytes = render_letter_pdf(
            template_version=versao_oficial_fr, snapshot=snapshot_completo
        )
        assert isinstance(pdf_bytes, bytes)

    def test_nao_recebe_request_nem_usuario(self):
        """A assinatura só aceita `template_version` e `snapshot` --
        nenhum objeto de request/sessão/usuário é necessário."""
        import inspect

        params = list(inspect.signature(render_letter_pdf).parameters)
        assert params == ["template_version", "snapshot"]


class TestEnderecoNoDocumentoUsaOHifenDoOriginal:
    """
    O perfil monta o endereço com travessão (U+2013) -- convenção de
    exibição do próprio perfil. O documento oficial escreve o endereço
    com hífen simples. Quem se adapta é o documento: `User` fica como
    está e a normalização acontece na camada do PDF.
    """

    def test_get_address_display_continua_com_travessao(self, user):
        """A semântica do perfil não foi alterada."""
        assert "–" in user.get_address_display()

    def test_snapshot_guarda_o_endereco_como_o_perfil_mostra(self, auth_client, user):
        letter = _carta_finalizada(auth_client, user)
        assert "–" in letter.snapshot["host"]["address"]

    def test_o_pdf_da_carta_real_sai_com_hifen(self, auth_client, user):
        letter = _carta_finalizada(auth_client, user)

        with letter.pdf_file.open("rb") as fh:
            texto = " ".join(
                PdfReader(io.BytesIO(fh.read())).pages[0].extract_text().split()
            )

        assert "Rue des Exemple 25 - 1200 Woluwe-Saint-Lambert" in texto
        assert "–" not in texto
        assert "—" not in texto


class TestFalhaNaGeracaoNaoDeixaRastro:
    """
    Se a geração falhar, a carta não pode ficar com arquivo pela metade,
    SHA de outra coisa ou marcada como gerada.
    """

    def test_geracao_que_falha_nao_grava_nada(self, auth_client, user):
        letter = _carta_finalizada(auth_client, user)

        # volta a carta ao estado anterior e estraga o snapshot
        letter.pdf_file.delete(save=False)
        letter.pdf_sha256 = ""
        letter.generated_at = None
        letter.status = Letter.Status.COMPLETED
        letter.snapshot["host"]["city"] = ""
        letter.save()

        with pytest.raises(MissingHostCityError):
            services.generate_pdf(letter)

        letter.refresh_from_db()
        assert not letter.pdf_file
        assert letter.pdf_sha256 == ""
        assert letter.generated_at is None
        assert letter.status == Letter.Status.COMPLETED

    def test_falha_nao_substitui_um_pdf_ja_gerado(self, auth_client, user):
        """Uma regeração que falha não pode apagar nem trocar o PDF que
        já existia."""
        letter = _carta_finalizada(auth_client, user)
        sha_bom = letter.pdf_sha256
        nome_bom = letter.pdf_file.name

        letter.snapshot["host"]["city"] = ""
        letter.save(update_fields=["snapshot"])

        with pytest.raises(MissingHostCityError):
            services.generate_pdf(letter)

        letter.refresh_from_db()
        assert letter.pdf_sha256 == sha_bom
        assert letter.pdf_file.name == nome_bom
        assert letter.status == Letter.Status.GENERATED
