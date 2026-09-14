"""
Idioma do documento (Fase 5 / Etapa 4.2, revisto na 3.6).

  * o idioma PADRAO de uma carta nova e `en`, explicito, sem relacao com
    o idioma da interface;

  * cada idioma usa o SEU `DocumentTemplate` oficial -- nunca o de outro
    idioma como substituto;

  * desde a Etapa 3.6 os quatro tem layout, entao os quatro geram PDF.
    Ate ali so o frances gerava, e este arquivo protegia o comportamento
    seguro do vazio.
"""

import datetime
import hashlib
import io

import pytest
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from apps.doctemplates.services.biblioteca import slug_oficial
from apps.letters import services
from apps.letters.models import Letter

pytestmark = pytest.mark.django_db

IDIOMAS_DO_SITE = ["pt", "fr", "nl", "en"]


@pytest.fixture(autouse=True)
def _nacionalidades(nacionalidade_factory):
    nacionalidade_factory("Brasileira", guest_form="Brésilienne")


@pytest.fixture(autouse=True)
def _oficiais(modelos_oficiais_prontos):
    """Os quatro modelos com o logo materializado -- sem isso o
    assistente recusa criar a carta, corretamente."""


# --- Percorrer o assistente pelo caminho real ------------------------------
#
# O servidor so deixa avancar ate onde os dados sustentam, entao chegar a
# etapa 5 ou a finalizacao exige passar pelas anteriores.

CHEGADA = timezone.localdate() + datetime.timedelta(days=30)
PASSO_1 = {
    "guest_name": "Carlos Eduardo Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "22/07/1990",
    "guest_passport": "YY0000",
}
PASSOS = {
    1: PASSO_1,
    2: {
        "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
        "stay_departure": (CHEGADA + datetime.timedelta(days=14)).strftime("%d/%m/%Y"),
    },
    3: {"host_confirm": "on"},
    4: {"notice_informal": "on", "notice_prise_en_charge": "on"},
}


def _step_url(letter, step):
    return reverse("letters:step", args=[letter.uuid, step])


def _ate_a_etapa_do_idioma(client, letter):
    for numero in (1, 2, 3, 4):
        client.post(_step_url(letter, numero), PASSOS[numero])


def _finaliza(client, user, idioma):
    """Cria, preenche, escolhe `idioma` e finaliza. Devolve a resposta."""
    client.post(reverse("letters:new"), PASSO_1)
    letter = Letter.objects.get(user=user)
    _ate_a_etapa_do_idioma(client, letter)
    client.post(_step_url(letter, 5), {"language": idioma})
    return client.post(_step_url(letter, 6))


def _carta_finalizada_em(client, user, idioma):
    _finaliza(client, user, idioma)
    return Letter.objects.get(user=user)


@pytest.fixture
def snapshot_fr(auth_client, user):
    """
    Um snapshot REAL, produzido pela finalizacao de uma carta de verdade
    -- nao um dicionario escrito a mao, que poderia divergir do formato
    que o sistema grava.
    """
    return _carta_finalizada_em(auth_client, user, "fr").snapshot


# ---------------------------------------------------------------------------
# 1. O idioma padrao de uma carta nova
# ---------------------------------------------------------------------------


class TestIdiomaPadraoDaCarta:
    def test_uma_carta_nova_nasce_em_ingles(self, auth_client, user):
        auth_client.post(reverse("letters:new"), PASSO_1)

        letter = Letter.objects.get(user=user)
        assert letter.language == "en"

    def test_o_documento_da_carta_nova_e_o_ingles(self, auth_client, user):
        auth_client.post(reverse("letters:new"), PASSO_1)

        letter = Letter.objects.get(user=user)
        assert letter.document_template.slug == slug_oficial("en")
        assert letter.document_template.language == "en"
        assert letter.document_template.is_system is True

    def test_o_padrao_e_explicito_e_nao_o_idioma_da_interface(self):
        """
        A interface e portuguesa (Etapa 4.1) e o padrao da carta e
        ingles: sao decisoes separadas, e uma nao pode voltar a derivar
        da outra.
        """
        from django.conf import settings

        assert services.IDIOMA_PADRAO_DA_CARTA == "en"
        assert settings.LANGUAGE_CODE == "pt"
        assert services.IDIOMA_PADRAO_DA_CARTA != settings.LANGUAGE_CODE

    def test_o_padrao_e_um_idioma_valido_do_site(self):
        assert services.IDIOMA_PADRAO_DA_CARTA in services.valid_language_codes()

    def test_a_interface_nao_muda_mais_o_idioma_da_carta(self, auth_client, user):
        """
        Ate a Etapa 4.1 o rascunho nascia no idioma da navegacao. Chegar
        por uma URL de outro idioma nao pode mais mudar nada.
        """
        auth_client.post("/fr/letters/new/", PASSO_1, follow=True)

        letter = Letter.objects.get(user=user)
        assert letter.language == "en"

    def test_a_pessoa_continua_podendo_trocar_na_etapa_5(self, auth_client, user):
        auth_client.post(reverse("letters:new"), PASSO_1)
        letter = Letter.objects.get(user=user)
        _ate_a_etapa_do_idioma(auth_client, letter)

        auth_client.post(_step_url(letter, 5), {"language": "fr"})

        letter.refresh_from_db()
        assert letter.language == "fr"


# ---------------------------------------------------------------------------
# 2. Cada idioma usa exclusivamente o seu proprio documento
# ---------------------------------------------------------------------------


class TestCadaIdiomaUsaOSeuDocumento:
    @pytest.mark.parametrize("idioma", IDIOMAS_DO_SITE)
    def test_o_modelo_oficial_e_o_daquele_idioma(self, idioma):
        modelo = services.official_document_template(idioma)

        assert modelo is not None
        assert modelo.slug == slug_oficial(idioma)
        assert modelo.language == idioma

    @pytest.mark.parametrize("idioma", ["pt", "nl", "en"])
    def test_nenhum_idioma_aponta_para_o_documento_frances(self, idioma):
        """PT, NL e EN nunca podem cair no modelo FR."""
        modelo = services.official_document_template(idioma)

        assert modelo.slug != slug_oficial("fr")
        assert modelo.language != "fr"

    @pytest.mark.parametrize("idioma", IDIOMAS_DO_SITE)
    def test_trocar_o_idioma_troca_o_documento(self, auth_client, user, idioma):
        auth_client.post(reverse("letters:new"), PASSO_1)
        letter = Letter.objects.get(user=user)
        _ate_a_etapa_do_idioma(auth_client, letter)

        auth_client.post(_step_url(letter, 5), {"language": idioma})

        letter.refresh_from_db()
        assert letter.language == idioma
        assert letter.document_template == services.official_document_template(idioma)

    def test_sem_modelo_pronto_a_troca_e_recusada(self, auth_client, user):
        """
        Sem desenho naquele idioma, a etapa 5 recusa -- em vez de servir
        o documento de outro idioma.
        """
        from apps.doctemplates.models import DocumentTemplate

        auth_client.post(reverse("letters:new"), PASSO_1)
        letter = Letter.objects.get(user=user)
        _ate_a_etapa_do_idioma(auth_client, letter)
        DocumentTemplate.objects.filter(slug=slug_oficial("nl")).update(layout={})

        auth_client.post(_step_url(letter, 5), {"language": "nl"})

        letter.refresh_from_db()
        assert letter.language == "en"
        assert letter.document_template.slug == slug_oficial("en")


# ---------------------------------------------------------------------------
# 3. Os quatro idiomas geram PDF (Etapa 3.6)
# ---------------------------------------------------------------------------


class TestOsQuatroGeramPdf:
    """
    Ate a Etapa 3.6 so o frances tinha documento, e esta secao protegia o
    comportamento seguro do vazio: falhar alto em vez de entregar um PDF
    no idioma errado. Com os quatro modelos desenhados, o que se protege
    agora e o oposto -- todos geram, cada um no seu idioma.
    """

    @pytest.mark.parametrize("idioma", IDIOMAS_DO_SITE)
    def test_a_carta_sai_gerada_com_arquivo(self, auth_client, user, idioma):
        letter = _carta_finalizada_em(auth_client, user, idioma)

        assert letter.status == Letter.Status.GENERATED
        assert letter.pdf_file
        assert letter.pdf_file.size > 0
        assert letter.generated_at is not None

    @pytest.mark.parametrize("idioma", IDIOMAS_DO_SITE)
    def test_o_pdf_tem_uma_pagina_e_texto_real(self, auth_client, user, idioma):
        letter = _carta_finalizada_em(auth_client, user, idioma)

        with letter.pdf_file.open("rb") as arquivo:
            documento = PdfReader(io.BytesIO(arquivo.read()))

        assert len(documento.pages) == 1
        assert len(documento.pages[0].extract_text()) > 800

    def test_o_sha256_corresponde_ao_arquivo_guardado(self, auth_client, user):
        letter = _carta_finalizada_em(auth_client, user, "fr")

        with letter.pdf_file.open("rb") as arquivo:
            gravado = hashlib.sha256(arquivo.read()).hexdigest()

        assert letter.pdf_sha256 == gravado

    @pytest.mark.parametrize("idioma", IDIOMAS_DO_SITE)
    def test_os_dados_variaveis_aparecem_no_pdf(self, auth_client, user, idioma):
        letter = _carta_finalizada_em(auth_client, user, idioma)

        with letter.pdf_file.open("rb") as arquivo:
            bruto = PdfReader(io.BytesIO(arquivo.read())).pages[0].extract_text()
        # `extract_text` devolve cada palavra numa linha; o que importa
        # aqui e que o valor esteja no PDF, nao como o pypdf o quebra.
        texto = " ".join(bruto.split())

        assert letter.snapshot["data"]["guest_name"] in texto
        assert letter.snapshot["host"]["full_name"] in texto
        assert letter.snapshot["data"]["guest_passport"] in texto

    @pytest.mark.parametrize("idioma", IDIOMAS_DO_SITE)
    def test_cada_carta_congela_o_seu_proprio_modelo(self, auth_client, user, idioma):
        """Nunca o documento de outro idioma como substituto."""
        letter = _carta_finalizada_em(auth_client, user, idioma)

        assert letter.document_snapshot["language"] == idioma
        assert letter.document_template.slug == slug_oficial(idioma)


# ---------------------------------------------------------------------------
# 5. Trocar o idioma antes de finalizar muda o documento gerado
# ---------------------------------------------------------------------------


class TestTrocaDeIdiomaAntesDeFinalizar:
    def test_trocar_para_frances_muda_o_documento_gerado(self, auth_client, user):
        """A carta nasce em ingles; trocar antes de finalizar tem de
        mudar o documento de destino."""
        auth_client.post(reverse("letters:new"), PASSO_1)
        letter = Letter.objects.get(user=user)
        _ate_a_etapa_do_idioma(auth_client, letter)
        auth_client.post(_step_url(letter, 5), {"language": "fr"})

        auth_client.post(_step_url(letter, 6))

        letter.refresh_from_db()
        assert letter.language == "fr"
        assert letter.status == Letter.Status.GENERATED
        assert letter.pdf_file

    def test_o_snapshot_congela_o_idioma_escolhido(self, auth_client, user):
        letter = _carta_finalizada_em(auth_client, user, "fr")

        assert letter.snapshot["language"] == "fr"
        assert letter.snapshot["document_template_slug"] == slug_oficial("fr")


# ---------------------------------------------------------------------------
# 6. A interface continua exclusivamente em portugues (Etapa 4.1)
# ---------------------------------------------------------------------------


class TestInterfaceNaoRegrediu:
    def test_a_etapa_do_idioma_e_apresentada_em_portugues(self, auth_client, user):
        auth_client.post(reverse("letters:new"), PASSO_1)
        letter = Letter.objects.get(user=user)
        _ate_a_etapa_do_idioma(auth_client, letter)

        html = auth_client.get(_step_url(letter, 5)).content.decode()

        assert "Próxima etapa" in html
        assert '<html lang="pt">' in html

    def test_os_quatro_idiomas_continuam_oferecidos(self, auth_client, user):
        auth_client.post(reverse("letters:new"), PASSO_1)
        letter = Letter.objects.get(user=user)
        _ate_a_etapa_do_idioma(auth_client, letter)

        resposta = auth_client.get(_step_url(letter, 5))

        codigos = [lang["code"] for lang in resposta.context["language_options"]]
        assert codigos == IDIOMAS_DO_SITE
