"""
Fase 5 / Etapa 4.2 -- idioma do documento.

DUAS PARTES, e so uma foi entregue:

  * o idioma PADRAO de uma carta nova passou a ser `en`, explicito, sem
    relacao com o idioma da interface -- isto esta implementado e coberto
    aqui;

  * os renderers oficiais de PT/NL/EN -- BLOQUEADOS. O repositorio so tem
    o PDF oficial frances (`pdfengine/assets/fr/`). Sem os arquivos
    oficiais dos outros tres idiomas nao ha como medir coordenadas, e
    inventar um layout aproximado foi explicitamente proibido.

Enquanto os renderers nao existem, o que estes testes protegem e o
comportamento SEGURO do vazio: um idioma sem renderer falha alto e
claro, nunca entrega um PDF de outro idioma. Quando os modelos oficiais
chegarem, `TestEnquantoNaoHaRenderer` e o lugar a atualizar -- e falhar
nele sera justamente o sinal de que o idioma passou a ser suportado.
"""

import datetime
import hashlib
import io

import pytest
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from apps.doctemplates.models import TemplateVersion
from apps.doctemplates.official_templates import official_slug
from apps.letters import services
from apps.letters.models import Letter
from apps.letters.pdf_generation import RENDERERS, UnsupportedLanguageError, render_letter_pdf

pytestmark = pytest.mark.django_db

IDIOMAS_DO_SITE = ["pt", "fr", "nl", "en"]
# Os idiomas que ainda nao tem documento oficial implementado.
SEM_RENDERER = ["pt", "nl", "en"]


@pytest.fixture(autouse=True)
def _nacionalidades(nacionalidade_factory):
    nacionalidade_factory("Brasileira", guest_form="Brésilienne")


def _versao_oficial(idioma):
    return TemplateVersion.objects.get(
        template__slug=official_slug(idioma), status=TemplateVersion.Status.PUBLISHED
    )


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
        assert letter.template.slug == official_slug("en")
        assert letter.template.language == "en"
        assert letter.template_version.status == "published"

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
    def test_o_modelo_publicado_e_o_daquele_idioma(self, idioma):
        versao = services.get_template_version_for_language(idioma)

        assert versao is not None
        assert versao.template.slug == official_slug(idioma)
        assert versao.template.language == idioma

    @pytest.mark.parametrize("idioma", SEM_RENDERER)
    def test_nenhum_idioma_aponta_para_o_documento_frances(self, idioma):
        """PT, NL e EN nunca podem cair no modelo FR."""
        versao = services.get_template_version_for_language(idioma)

        assert versao.template.slug != official_slug("fr")
        assert versao.template.language != "fr"

    @pytest.mark.parametrize("idioma", IDIOMAS_DO_SITE)
    def test_trocar_o_idioma_troca_o_documento(self, auth_client, user, idioma):
        auth_client.post(reverse("letters:new"), PASSO_1)
        letter = Letter.objects.get(user=user)
        _ate_a_etapa_do_idioma(auth_client, letter)

        auth_client.post(_step_url(letter, 5), {"language": idioma})

        letter.refresh_from_db()
        assert letter.language == idioma
        assert letter.template_version == _versao_oficial(idioma)

    def test_sem_documento_publicado_a_troca_e_recusada(self, auth_client, user):
        """
        Nao existindo modelo ativo naquele idioma, a etapa 5 recusa --
        em vez de servir o documento de outro idioma.
        """
        from apps.doctemplates.models import LetterTemplate

        auth_client.post(reverse("letters:new"), PASSO_1)
        letter = Letter.objects.get(user=user)
        _ate_a_etapa_do_idioma(auth_client, letter)
        LetterTemplate.objects.filter(slug=official_slug("nl")).update(is_active=False)

        auth_client.post(_step_url(letter, 5), {"language": "nl"})

        letter.refresh_from_db()
        assert letter.language == "en"
        assert letter.template.slug == official_slug("en")


# ---------------------------------------------------------------------------
# 3. O PDF frances -- o unico implementado -- nao pode ter regredido
# ---------------------------------------------------------------------------


class TestPdfFrances:
    def test_o_frances_gera_o_pdf(self, snapshot_fr):
        pdf = render_letter_pdf(
            template_version=_versao_oficial("fr"), snapshot=snapshot_fr
        )

        assert pdf.startswith(b"%PDF-")
        assert len(PdfReader(io.BytesIO(pdf)).pages) == 1

    def test_o_pdf_fica_mesmo_anexado_a_carta(self, auth_client, user):
        letter = _carta_finalizada_em(auth_client, user, "fr")

        assert letter.status == Letter.Status.GENERATED
        assert letter.pdf_file
        assert letter.pdf_file.size > 0
        assert letter.generated_at is not None

    def test_o_sha256_corresponde_ao_arquivo_guardado(self, auth_client, user):
        letter = _carta_finalizada_em(auth_client, user, "fr")

        with letter.pdf_file.open("rb") as arquivo:
            gravado = hashlib.sha256(arquivo.read()).hexdigest()

        assert letter.pdf_sha256 == gravado

    def test_os_dados_variaveis_aparecem_no_pdf(self, snapshot_fr):
        pdf = render_letter_pdf(
            template_version=_versao_oficial("fr"), snapshot=snapshot_fr
        )

        # `extract_text` devolve cada palavra numa linha; o que importa
        # aqui e que o valor esteja no PDF, nao como o pypdf o quebra.
        texto = " ".join(PdfReader(io.BytesIO(pdf)).pages[0].extract_text().split())

        assert snapshot_fr["data"]["guest_name"] in texto
        assert snapshot_fr["host"]["full_name"] in texto
        assert snapshot_fr["data"]["guest_passport"] in texto


# ---------------------------------------------------------------------------
# 4. Enquanto PT/NL/EN nao tem renderer: falhar alto, nunca improvisar
# ---------------------------------------------------------------------------


class TestEnquantoNaoHaRenderer:
    """
    ATUALIZAR QUANDO OS MODELOS OFICIAIS CHEGAREM. Estes testes descrevem
    uma ausencia, nao um objetivo: quando o renderer de um idioma for
    implementado, o teste daquele idioma passa a falhar -- e e esse o
    sinal de que a Etapa 4.2 avancou.
    """

    def test_hoje_so_o_frances_tem_renderer(self):
        assert set(RENDERERS) == {"fr"}

    @pytest.mark.parametrize("idioma", SEM_RENDERER)
    def test_um_idioma_sem_renderer_falha_de_forma_explicita(self, idioma, snapshot_fr):
        snapshot = {**snapshot_fr, "language": idioma}

        with pytest.raises(UnsupportedLanguageError) as erro:
            render_letter_pdf(
                template_version=_versao_oficial(idioma), snapshot=snapshot
            )

        assert idioma in str(erro.value)

    @pytest.mark.parametrize("idioma", SEM_RENDERER)
    def test_nunca_devolve_o_pdf_frances_no_lugar(self, idioma, snapshot_fr):
        """
        O ponto central da etapa: preferir o erro a um documento no
        idioma errado. Um PDF frances entregue como se fosse portugues
        seria pior do que nenhum PDF.
        """
        snapshot = {**snapshot_fr, "language": idioma}

        with pytest.raises(UnsupportedLanguageError):
            render_letter_pdf(
                template_version=_versao_oficial(idioma), snapshot=snapshot
            )

    @pytest.mark.parametrize("idioma", SEM_RENDERER)
    def test_a_carta_fica_registrada_mas_sem_pdf(self, auth_client, user, idioma):
        """
        A falha nao pode parecer sucesso: a carta e registrada (nao se
        perde o preenchimento), mas sem arquivo, sem checksum e sem o
        status GENERATED.
        """
        letter = _carta_finalizada_em(auth_client, user, idioma)

        assert letter.status == Letter.Status.COMPLETED
        assert not letter.pdf_file
        assert letter.pdf_sha256 == ""
        assert letter.generated_at is None

    @pytest.mark.parametrize("idioma", SEM_RENDERER)
    def test_a_pessoa_e_avisada_do_motivo_real(self, auth_client, user, idioma):
        from django.contrib.messages import get_messages

        resposta = _finaliza(auth_client, user, idioma)
        textos = " ".join(str(m) for m in get_messages(resposta.wsgi_request))

        assert "francês" in textos


# ---------------------------------------------------------------------------
# 5. Trocar o idioma antes de finalizar muda o documento gerado
# ---------------------------------------------------------------------------


class TestTrocaDeIdiomaAntesDeFinalizar:
    def test_trocar_para_frances_passa_a_gerar_o_pdf(self, auth_client, user):
        """
        A carta nasce em ingles (sem renderer). Trocar para frances antes
        de finalizar tem de mudar o documento de destino -- e ai o PDF
        sai.
        """
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
        assert letter.snapshot["template_slug"] == official_slug("fr")


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
