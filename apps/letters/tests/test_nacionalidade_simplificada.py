"""
Nacionalidade = um nome por idioma. Nada além disso.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
Que a complexidade volte. A nacionalidade já teve `guest_form` e
`host_form` -- duas formas gramaticais, uma por papel -- e chegou a ter
`guest_form_f`/`guest_form_m` e um campo de gênero no assistente. Tudo
isso saiu: a carta escreve o nome da nacionalidade no idioma DELA, e é
só.

Vários testes aqui são guardas de AUSÊNCIA. São chatos de propósito: é
mais fácil reintroduzir um campo "só para este caso" do que perceber,
meses depois, que a modelagem voltou a ter duas verdades.
"""

import datetime
import pathlib

import pytest
from django.urls import reverse

from apps.doctemplates.admin import NationalityAdmin
from apps.doctemplates.models import Nationality
from apps.letters import nationalities, services
from apps.letters.models import Letter

pytestmark = pytest.mark.django_db

RAIZ = pathlib.Path(__file__).resolve().parents[3]
IDIOMAS = ["fr", "nl", "en", "pt"]

# Os nomes que saíram da arquitetura. Se qualquer um reaparecer no
# código de produção, é regressão de modelagem.
APOSENTADOS = ("guest_form", "host_form", "guest_form_f", "guest_form_m", "guest_gender")


@pytest.fixture(autouse=True)
def _modelos_oficiais_prontos(modelos_oficiais_prontos):
    """Sem os oficiais com logo materializado não há carta nem PDF."""


@pytest.fixture
def brasileira(db):
    return Nationality.objects.create(
        code="BRA",
        order=1,
        name_pt="brasileira",
        name_fr="brésilienne",
        name_nl="Braziliaans",
        name_en="Brazilian",
    )


@pytest.fixture
def so_portugues(db):
    """Cadastro pela metade: só o português preenchido."""
    return Nationality.objects.create(
        code="XXX", order=2, name_pt="Exemplar", name_fr="", name_nl="", name_en=""
    )


# ===========================================================================
# 1. A forma do modelo
# ===========================================================================


class TestModelo:
    def test_tem_exatamente_os_campos_previstos(self):
        concretos = {
            f.name
            for f in Nationality._meta.get_fields()
            if getattr(f, "concrete", False)
        }

        assert concretos == {
            "id",
            "created_at",
            "updated_at",
            "code",
            "is_active",
            "order",
            "name_pt",
            "name_fr",
            "name_nl",
            "name_en",
        }

    @pytest.mark.parametrize("nome", APOSENTADOS)
    def test_os_campos_aposentados_nao_existem(self, nome):
        assert nome not in {f.name for f in Nationality._meta.get_fields()}

    def test_a_coluna_tambem_sumiu_do_banco(self, django_assert_num_queries):
        """
        `RemoveField` de verdade, não só o campo fora do modelo: uma
        coluna órfã voltaria a aparecer em qualquer `SELECT *`.
        """
        from django.db import connection

        with connection.cursor() as cursor:
            colunas = {
                c.name
                for c in connection.introspection.get_table_description(
                    cursor, Nationality._meta.db_table
                )
            }

        assert "guest_form" not in colunas
        assert "host_form" not in colunas


# ===========================================================================
# 2. A tradução, por idioma
# ===========================================================================


class TestTraducao:
    @pytest.mark.parametrize(
        "idioma, esperado",
        [
            ("pt", "brasileira"),
            ("fr", "brésilienne"),
            ("nl", "Braziliaans"),
            ("en", "Brazilian"),
        ],
    )
    def test_cada_idioma_devolve_o_seu_nome(self, brasileira, idioma, esperado):
        assert brasileira.display_name(idioma) == esperado
        assert nationalities.display_name("BRA", idioma) == esperado

    def test_idioma_sem_traducao_cai_no_portugues(self, so_portugues):
        """O fallback que o projeto já usava, mantido."""
        for idioma in IDIOMAS:
            assert nationalities.display_name("XXX", idioma) == "Exemplar"

    def test_idioma_desconhecido_tambem_cai_no_portugues(self, brasileira):
        """`language=None`, `"de"`, o que for: nada disso quebra."""
        assert nationalities.display_name("BRA", None) == "brasileira"
        assert nationalities.display_name("BRA", "de") == "brasileira"

    def test_sem_nome_nenhum_sobra_o_codigo(self, db):
        """
        Um documento oficial com o campo em branco seria pior do que um
        com o código.
        """
        Nationality.objects.create(
            code="ZZZ", order=9, name_pt="", name_fr="", name_nl="", name_en=""
        )

        assert nationalities.display_name("ZZZ", "fr") == "ZZZ"

    def test_valor_vazio_e_vazio(self):
        assert nationalities.display_name("", "fr") == ""
        assert nationalities.display_name(None, "fr") == ""

    def test_codigo_fora_do_cadastro_volta_como_esta(self):
        """
        Cartas anteriores ao cadastro guardaram o próprio texto em
        `data`. Não é um código: já é o texto final.
        """
        assert nationalities.display_name("Brésilienne", "fr") == "Brésilienne"


# ===========================================================================
# 3. A mesma tradução para todo mundo
# ===========================================================================


class TestMesmaFonte:
    def test_convidado_e_anfitriao_usam_a_mesma_traducao(self, brasileira):
        """
        Não há mais forma "do convidado" e forma "do anfitrião": a mesma
        nacionalidade, no mesmo idioma, dá o mesmo texto nos dois papéis.
        """
        resultado = nationalities.document_nationalities(
            {"guest_nationality": "BRA"}, host_code="BRA", language="fr"
        )

        assert resultado == {
            "guest_nationality": "brésilienne",
            "host_nationality": "brésilienne",
        }

    def test_a_tela_e_o_documento_leem_a_mesma_coisa(self, brasileira):
        """Uma fonte só: a revisão não pode discordar do papel."""
        do_documento = nationalities.document_nationalities(
            {"guest_nationality": "BRA"}, language="fr"
        )["guest_nationality"]
        da_tela = nationalities.display_name("BRA", "fr")

        assert do_documento == da_tela

    def test_o_resolvedor_nao_recebe_genero_nem_papel(self):
        """
        A assinatura é parte do contrato: um parâmetro de gênero ou de
        papel seria o começo da complexidade de volta.
        """
        import inspect

        assert list(inspect.signature(nationalities.document_nationalities).parameters) == [
            "data",
            "host_code",
            "language",
        ]
        assert list(inspect.signature(nationalities.display_name).parameters) == [
            "value",
            "language",
        ]


# ===========================================================================
# 4. Guardas de ausência
# ===========================================================================


class TestNadaDeFormasNemGenero:
    @pytest.mark.parametrize("nome", APOSENTADOS)
    def test_nao_aparecem_no_codigo_de_producao(self, nome):
        """
        Migrations ficam de fora: `0005` criou os campos e `0017` os
        removeu -- as duas precisam citá-los pelo nome.
        """
        alvos = [
            *RAIZ.glob("apps/**/*.py"),
            *RAIZ.glob("templates/**/*.html"),
            *RAIZ.glob("static/js/*.js"),
            RAIZ / "conftest.py",
        ]

        for caminho in alvos:
            relativo = caminho.relative_to(RAIZ).as_posix()
            if "/migrations/" in relativo or "/tests/" in relativo:
                continue
            assert nome not in caminho.read_text(encoding="utf-8"), relativo

    @pytest.mark.parametrize("idioma", IDIOMAS)
    def test_o_schema_oficial_nao_tem_campo_de_genero(self, idioma):
        modelo = services.official_document_template(idioma)
        chaves = {c["key"] for c in modelo.field_schema["fields"]}

        assert "guest_gender" not in chaves
        assert len(modelo.field_schema["fields"]) == 9

    def test_o_assistente_nao_pergunta_genero(self, auth_client, user, brasileira):
        """Etapa 1, no HTML de verdade."""
        carta = services.start_draft(user, "fr")
        html = auth_client.get(
            reverse("letters:step", args=[carta.uuid, 1])
        ).content.decode()

        assert "guest_gender" not in html
        assert "Gênero" not in html


# ===========================================================================
# 5. A tela de cadastro
# ===========================================================================


class TestAdministracao:
    def test_o_formulario_mostra_so_codigo_situacao_ordem_e_os_quatro_nomes(self):
        campos = [
            campo
            for _titulo, opcoes in NationalityAdmin.fieldsets
            for campo in opcoes["fields"]
        ]

        assert campos == [
            "code",
            "is_active",
            "order",
            "name_pt",
            "name_fr",
            "name_nl",
            "name_en",
        ]

    def test_nao_ha_mais_secao_de_formas(self):
        titulos = [str(titulo) for titulo, _opcoes in NationalityAdmin.fieldsets]

        assert not any("orma" in (titulo or "") for titulo in titulos)

    def test_a_listagem_mostra_as_quatro_traducoes(self):
        assert NationalityAdmin.list_display == (
            "code",
            "name_pt",
            "name_fr",
            "name_nl",
            "name_en",
            "order",
            "is_active",
        )

    def test_a_tela_renderiza_com_os_campos_certos(self, client, brasileira):
        from django.contrib.auth import get_user_model

        chefe = get_user_model().objects.create_superuser(
            email="chefe@mail.com", password="x", full_name="Helena Braga"
        )
        client.force_login(chefe)

        html = client.get(
            reverse("admin:doctemplates_nationality_change", args=[brasileira.pk])
        ).content.decode()

        for campo in ("name_pt", "name_fr", "name_nl", "name_en"):
            assert f'name="{campo}"' in html
        # `code` é somente leitura ao editar (`get_readonly_fields`): sai
        # como texto, não como campo -- mas tem de estar na tela.
        assert brasileira.code in html
        for aposentado in APOSENTADOS:
            assert f'name="{aposentado}"' not in html


# ===========================================================================
# 6. O caminho inteiro, até o PDF
# ===========================================================================

CHEGADA = datetime.date(2027, 3, 10)

PASSOS = {
    1: {
        "guest_name": "Carlos Eduardo Silva",
        "guest_nationality": "BRA",
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


def _carta(client, user, idioma):
    client.post(reverse("letters:new"), PASSOS[1])
    carta = Letter.objects.filter(user=user).order_by("-pk").first()
    for numero in (2, 3, 4):
        client.post(reverse("letters:step", args=[carta.uuid, numero]), PASSOS[numero])
    client.post(reverse("letters:step", args=[carta.uuid, 5]), {"language": idioma})
    client.post(reverse("letters:step", args=[carta.uuid, 6]))
    carta.refresh_from_db()
    return carta


def _texto(carta):
    import io

    from pypdf import PdfReader

    with carta.pdf_file.open("rb") as fh:
        pagina = PdfReader(io.BytesIO(fh.read())).pages[0]
    return " ".join(pagina.extract_text().split())


class TestAteOPdf:
    @pytest.mark.parametrize(
        "idioma, esperado",
        [
            ("fr", "brésilienne"),
            ("nl", "Braziliaans"),
            ("en", "Brazilian"),
            ("pt", "brasileira"),
        ],
    )
    def test_o_pdf_sai_nos_quatro_idiomas_com_a_traducao_certa(
        self, auth_client, user, brasileira, idioma, esperado
    ):
        carta = _carta(auth_client, user, idioma)

        assert carta.pdf_file
        assert carta.snapshot["nationalities"]["guest_nationality"] == esperado
        assert esperado in _texto(carta)

    def test_o_anfitriao_sai_no_idioma_do_documento(self, auth_client, user, brasileira):
        """
        A nacionalidade do perfil ("belge") em quatro documentos: cada um
        escreve o nome no idioma dele.
        """
        esperados = {"fr": "Belge", "nl": "Belgische", "en": "Belgian", "pt": "Belga"}

        for idioma, esperado in esperados.items():
            carta = _carta(auth_client, user, idioma)

            assert carta.snapshot["nationalities"]["host_nationality"] == esperado

    def test_o_snapshot_congela_o_texto(self, auth_client, user, brasileira):
        """Renomear depois não reescreve o documento emitido."""
        carta = _carta(auth_client, user, "fr")

        brasileira.name_fr = "Outra Coisa"
        brasileira.save()
        carta.refresh_from_db()

        assert carta.snapshot["nationalities"]["guest_nationality"] == "brésilienne"

    def test_a_carta_guarda_o_codigo_e_nao_o_texto(self, auth_client, user, brasileira):
        carta = _carta(auth_client, user, "fr")

        assert carta.data["guest_nationality"] == "BRA"
        assert "brésilienne" not in str(carta.data)

    @pytest.mark.parametrize("idioma", IDIOMAS)
    def test_os_quatro_modelos_oficiais_continuam_de_pe(self, idioma):
        modelo = services.official_document_template(idioma)

        assert modelo is not None
        assert modelo.is_system is True
        assert modelo.is_active is True
        assert modelo.language == idioma
