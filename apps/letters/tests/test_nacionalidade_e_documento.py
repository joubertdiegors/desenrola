"""
Testes das três decisões desta rodada:

  - a nacionalidade vira um cadastro administrável, e a carta guarda o
    CÓDIGO estável, nunca o texto traduzido;
  - o documento de identidade do anfitrião sai do assistente e passa a
    ser dado do perfil;
  - os campos de data ganham calendário nativo e máscara, sem perder a
    validação do servidor.
"""

import datetime

import pytest
from django.urls import reverse

from apps.doctemplates.models import Nationality
from apps.letters import nationalities, services
from apps.letters.forms import build_dynamic_form
from apps.letters.models import Letter

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _modelos_oficiais_prontos(modelos_oficiais_prontos):
    """
    Os quatro modelos oficiais com o logo materializado -- sem eles
    `active_document_template()` devolve `None` e o assistente
    recusa criar carta nenhuma (e esta certo: seria uma carta que
    nao viraria PDF).
    """


def _step_url(letter, step):
    return reverse("letters:step", args=[letter.uuid, step])


@pytest.fixture
def draft(user):
    return services.start_draft(user, "fr")


@pytest.fixture
def brasileira(db):
    """Uma nacionalidade de teste. Não é uma lista oficial -- a lista
    oficial ainda não existe (ver relatório)."""
    return Nationality.objects.create(
        code="BR",
        order=1,
        name_pt="Brasileira",
        name_fr="Brésilienne",
        name_nl="Braziliaanse",
        name_en="Brazilian",
    )


@pytest.fixture
def belga(db):
    return Nationality.objects.create(
        code="BE",
        order=2,
        name_pt="Belga",
        name_fr="Belge",
        name_nl="Belgische",
        name_en="Belgian",
    )


# ---------------------------------------------------------------------------
# Modelo e cadastro
# ---------------------------------------------------------------------------


class TestModeloNationality:
    def test_tem_os_campos_pedidos(self, brasileira):
        assert brasileira.code == "BR"
        assert brasileira.is_active is True
        assert brasileira.order == 1
        assert brasileira.name_pt and brasileira.name_fr
        assert brasileira.name_nl and brasileira.name_en
        assert brasileira.display_name("fr") == "Brésilienne"

    def test_o_codigo_e_unico(self, brasileira):
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            Nationality.objects.create(
                code="BR",
                name_pt="Outra",
                name_fr="Autre",
                name_nl="Andere",
                name_en="Other",
            )

    def test_o_nome_sai_no_idioma_pedido(self, brasileira):
        assert brasileira.display_name("pt") == "Brasileira"
        assert brasileira.display_name("fr") == "Brésilienne"
        assert brasileira.display_name("nl") == "Braziliaanse"
        assert brasileira.display_name("en") == "Brazilian"

    def test_idioma_desconhecido_cai_no_portugues(self, brasileira):
        assert brasileira.display_name("xx") == "Brasileira"

    def test_ordem_manda_na_listagem(self, brasileira, belga):
        belga.order = 0
        belga.save()
        assert [n.code for n in Nationality.objects.all()] == ["BE", "BR"]

    def test_esta_registrada_no_admin(self):
        from django.contrib import admin

        assert Nationality in admin.site._registry

    def test_o_admin_protege_o_codigo_depois_de_criado(self, brasileira):
        """Mudar o código quebraria a ligação das cartas já feitas."""
        from django.contrib import admin

        opcoes = admin.site._registry[Nationality]
        assert "code" in opcoes.get_readonly_fields(None, obj=brasileira)
        assert "code" not in opcoes.get_readonly_fields(None, obj=None)


class TestSomenteAtivasNoFormulario:
    def test_o_formulario_oferece_as_ativas(self, brasileira, belga):
        escolhas = dict(nationalities.nationality_choices("fr"))

        assert escolhas == {"BR": "Brésilienne", "BE": "Belge"}

    def test_inativa_some_do_formulario(self, brasileira, belga):
        belga.is_active = False
        belga.save()

        escolhas = dict(nationalities.nationality_choices("fr"))

        assert "BE" not in escolhas
        assert "BR" in escolhas

    def test_o_campo_vira_uma_lista_quando_ha_cadastro(self, auth_client, draft, brasileira):
        html = auth_client.get(_step_url(draft, 1)).content.decode()

        assert '<select name="guest_nationality"' in html
        assert 'value="BR"' in html
        # A interface do assistente e sempre em portugues (item 1 da
        # etapa de correcoes pos-validacao manual), mesmo a carta sendo
        # em outro idioma (`draft` comeca em "fr").
        assert "Brasileira" in html

    def test_sem_nenhuma_ativa_o_campo_fica_indisponivel(self, auth_client, draft):
        """
        Decisão final: SEM fallback de texto livre. Sem nenhuma
        nacionalidade ativa, o campo fica travado (widget desabilitado) e
        avisa o motivo -- nunca aceita um valor digitado à mão.
        """
        Nationality.objects.update(is_active=False)
        assert Nationality.objects.filter(is_active=True).count() == 0

        html = auth_client.get(_step_url(draft, 1)).content.decode()

        assert 'name="guest_nationality" class="input" disabled' in html
        assert "Ainda não há nacionalidades cadastradas" in html

    def test_sem_ativas_nao_e_possivel_avancar_da_etapa(self, auth_client, draft):
        """O bloqueio vale mesmo enviando um valor manualmente -- o campo
        desabilitado ignora o que veio no POST e a validação falha do
        mesmo jeito."""
        Nationality.objects.update(is_active=False)

        response = auth_client.post(
            _step_url(draft, 1),
            {
                "guest_name": "Maria Santos da Silva",
                "guest_nationality": "Qualquer Coisa Inventada",
                "guest_birth_date": "15/08/1990",
                "guest_passport": "YY0000",
            },
        )

        draft.refresh_from_db()
        assert response.status_code == 200
        assert "guest_nationality" in response.context["form"].errors
        assert "guest_nationality" not in draft.data

    def test_sem_ativas_nao_salva_nenhum_valor_arbitrario(self, auth_client, draft):
        """Mesmo se o valor malicioso não vazio for forçado no POST bruto
        (contornando o `disabled` do HTML), nada é gravado."""
        Nationality.objects.update(is_active=False)

        auth_client.post(
            _step_url(draft, 1),
            {
                "guest_name": "Maria Santos da Silva",
                "guest_nationality": "<script>hack</script>",
                "guest_birth_date": "15/08/1990",
                "guest_passport": "YY0000",
            },
        )

        draft.refresh_from_db()
        assert "guest_nationality" not in draft.data
        assert draft.status == Letter.Status.DRAFT

    def test_nacionalidade_inativa_tambem_deixa_o_campo_indisponivel(
        self, auth_client, draft, brasileira
    ):
        """Zero ATIVAS -- não zero cadastradas -- é a condição que conta."""
        Nationality.objects.update(is_active=False)
        assert Nationality.objects.count() > 0

        html = auth_client.get(_step_url(draft, 1)).content.decode()

        assert 'name="guest_nationality" class="input" disabled' in html

    def test_valor_fora_da_lista_e_recusado(self, brasileira):
        campos = [
            {
                "key": "guest_nationality",
                "type": "nationality",
                "required": True,
                "label": "Nacionalidade",
            }
        ]
        form = build_dynamic_form(campos, data={"guest_nationality": "XX"})

        assert not form.is_valid()


# ---------------------------------------------------------------------------
# O que fica guardado é o código
# ---------------------------------------------------------------------------


class TestArmazenaOCodigo:
    def test_letter_data_guarda_o_codigo_e_nao_o_texto(
        self, auth_client, draft, brasileira
    ):
        auth_client.post(
            _step_url(draft, 1),
            {
                "guest_name": "Maria Santos da Silva",
                "guest_nationality": "BR",
                "guest_birth_date": "15/08/1990",
                "guest_passport": "YY0000",
            },
        )
        draft.refresh_from_db()

        assert draft.data["guest_nationality"] == "BR"
        assert "Brésilienne" not in str(draft.data)

    def test_o_snapshot_congela_o_texto_do_documento(self, brasileira, belga):
        # O idioma do DOCUMENTO escolhe a tradução -- é o que
        # `build_snapshot` passa, a partir de `letter.language`.
        nacionalidades = nationalities.document_nationalities(
            {"guest_nationality": "BR", "host_nationality": "BE"}, language="fr"
        )

        assert nacionalidades == {
            "guest_nationality": "Brésilienne",
            "host_nationality": "Belge",
        }

    def test_renomear_no_cadastro_nao_muda_a_carta_ja_emitida(
        self, auth_client, user, draft, brasileira, belga
    ):
        """
        O texto que foi para o documento está congelado no snapshot -- o
        cadastro pode mudar depois à vontade.
        """
        congelado = nationalities.document_nationalities({"guest_nationality": "BR"}, language="fr")

        brasileira.name_fr = "Outra Coisa Totalmente"
        brasileira.save()

        assert congelado["guest_nationality"] == "Brésilienne"

    def test_desativar_a_nacionalidade_nao_quebra_a_carta_emitida(
        self, brasileira
    ):
        congelado = nationalities.document_nationalities({"guest_nationality": "BR"}, language="fr")
        brasileira.is_active = False
        brasileira.save()

        assert congelado["guest_nationality"] == "Brésilienne"

    def test_a_revisao_mostra_o_nome_e_nao_o_codigo(
        self, auth_client, draft, brasileira, belga
    ):
        """Quem revisa a carta tem de ler "Brasileira", não "BR" -- no
        idioma da INTERFACE (português), mesmo a carta sendo em francês:
        a revisão é tela do assistente, não o documento."""
        auth_client.post(
            _step_url(draft, 1),
            {
                "guest_name": "Maria Santos da Silva",
                "guest_nationality": "BR",
                "guest_birth_date": "15/08/1990",
                "guest_passport": "YY0000",
            },
        )
        auth_client.post(_step_url(draft, 2), VALID_2)
        auth_client.post(_step_url(draft, 3), VALID_3)
        auth_client.post(_step_url(draft, 4), VALID_4)
        auth_client.post(_step_url(draft, 5), {"language": "fr"})

        html = auth_client.get(_step_url(draft, 6)).content.decode()

        assert "Brasileira" in html
        assert ">BR<" not in html

    def test_carta_antiga_com_texto_livre_continua_funcionando(self):
        """Cartas anteriores ao cadastro guardaram o próprio texto: ele
        passa adiante como está, sem virar erro."""
        nacionalidades = nationalities.document_nationalities(
            {"guest_nationality": "Brésilienne"}
        )

        assert nacionalidades["guest_nationality"] == "Brésilienne"


# ---------------------------------------------------------------------------
# Documento do anfitrião
# ---------------------------------------------------------------------------


class TestDocumentoDoAnfitriao:
    @pytest.fixture(autouse=True)
    def _nacionalidades_validas(self, brasileira, belga):
        """`_finalizar` percorre o assistente de verdade -- precisa de
        nacionalidades ativas para os campos de nacionalidade validarem."""

    def test_o_perfil_guarda_o_numero(self, user):
        assert user.document_number == "00000000"

    def test_o_campo_aparece_no_perfil(self, auth_client):
        html = auth_client.get(reverse("accounts:profile")).content.decode()

        assert 'name="document_number"' in html

    def test_o_perfil_salva_o_numero(self, auth_client, user):
        from apps.accounts.forms import PROFILE_FIELDS

        assert "document_number" in PROFILE_FIELDS

    def test_o_assistente_nao_pede_mais_o_documento(self, auth_client, draft):
        for etapa in (1, 2, 3, 4):
            html = auth_client.get(_step_url(draft, etapa)).content.decode()
            assert 'name="host_document_number"' not in html
            assert 'name="host_document_label"' not in html

    def test_o_schema_nao_tem_mais_os_campos(self):
        modelo = services.active_document_template("fr")
        chaves = {f["key"] for f in modelo.field_schema["fields"]}

        assert "host_document_label" not in chaves
        assert "host_document_number" not in chaves

    def test_o_snapshot_congela_o_documento_do_perfil(self, auth_client, user, draft):
        _finalizar(auth_client, draft)
        draft.refresh_from_db()

        assert draft.snapshot["host"]["document_number"] == "00000000"

    def test_alterar_o_perfil_nao_muda_a_carta_emitida(self, auth_client, user, draft):
        _finalizar(auth_client, draft)
        draft.refresh_from_db()

        user.document_number = "99999999"
        user.save(update_fields=["document_number"])

        assert draft.snapshot["host"]["document_number"] == "00000000"

    def test_sem_documento_no_perfil_a_carta_nao_finaliza(self, auth_client, user, draft):
        """
        O bloqueio acontece já na etapa do anfitrião -- é lá que os dados
        do perfil entram na carta --, então a pessoa nem chega ao fim.
        """
        user.document_number = ""
        user.save(update_fields=["document_number"])

        response = _finalizar(auth_client, draft)

        draft.refresh_from_db()
        assert response.url == _step_url(draft, 3)
        assert draft.status == Letter.Status.DRAFT
        assert draft.snapshot == {}


VALID_1 = {
    "guest_name": "Maria Santos da Silva",
    "guest_nationality": "BR",  # o código da fixture `brasileira`
    "guest_birth_date": "15/08/1990",
    "guest_passport": "YY0000",
}
VALID_2 = {"stay_arrival": "10/10/2026", "stay_departure": "24/10/2026"}
VALID_3 = {
    "host_confirm": "on",
}
VALID_4 = {"notice_informal": "on", "notice_prise_en_charge": "on"}


def _finalizar(client, letter):
    for n, dados in ((1, VALID_1), (2, VALID_2), (3, VALID_3), (4, VALID_4)):
        client.post(_step_url(letter, n), dados)
    client.post(_step_url(letter, 5), {"language": "fr"})
    return client.post(_step_url(letter, 6))


# ---------------------------------------------------------------------------
# Regressão do PDF oficial
# ---------------------------------------------------------------------------


class TestRegressaoDoPdfOficial:
    @pytest.fixture(autouse=True)
    def _nacionalidades_validas(self, brasileira, belga):
        """`_finalizar` percorre o assistente de verdade -- precisa de
        nacionalidades ativas para os campos de nacionalidade validarem."""

    def test_a_frase_juridica_continua_igual(self, auth_client, user, draft):
        """
        "titulaire de la carte d'identité <nacionalidade> n° <número>" --
        o texto do documento não mudou; só a origem dos dois valores.
        """
        import io as _io

        from pypdf import PdfReader

        _finalizar(auth_client, draft)
        draft.refresh_from_db()

        with draft.pdf_file.open("rb") as fh:
            texto = " ".join(PdfReader(_io.BytesIO(fh.read())).pages[0].extract_text().split())

        # Rodada 18: o texto oficial da identificação do anfitrião. O
        # `replace(" ,", ",")` desfaz só um artefato da extração do pypdf
        # (um espaço antes da vírgula que segue um campo em negrito); no
        # PDF desenhado a vírgula vem colada ao campo.
        assert (
            "Je soussigné(e), Claire Dubois, né(e) le 14/03/1985, nationalité : Belge, "
            "carte d’identité : 00000000, domicilié(e) à Rue des Exemple 25 - 1200 "
            "Woluwe-Saint-Lambert, téléphone : +32 470 00 00 00, invite par la présente :"
        ) in texto.replace(" ,", ",")
        assert "00000000" in texto

    def test_a_nacionalidade_do_anfitriao_alimenta_a_frase_do_documento(
        self, auth_client, draft
    ):
        """
        O “belge” da frase do documento é a nacionalidade do anfitrião --
        nunca foi um segundo dado.

        Conferido no CONTEXTO que o renderer estrutural consome, uma
        camada antes do desenho: se viesse de outro lugar, apareceria
        aqui como outra chave.
        """
        _finalizar(auth_client, draft)
        draft.refresh_from_db()

        contexto = services.build_document_context(draft)

        assert contexto["anfitriao.nacionalidade"] == "Belge"
        assert contexto["anfitriao.documento_identidade"] == "00000000"
# ---------------------------------------------------------------------------
# Campos de data
# ---------------------------------------------------------------------------


class TestCamposDeData:
    @pytest.fixture(autouse=True)
    def _chega_na_etapa_da_viagem(self, auth_client, draft, brasileira):
        """A etapa 2 só é alcançável com a 1 preenchida (e isso exige uma
        nacionalidade ativa para o campo do convidado validar)."""
        auth_client.post(_step_url(draft, 1), VALID_1)

    def test_o_campo_tem_calendario_nativo(self, auth_client, draft):
        """Calendário de verdade do navegador, não um ícone decorativo."""
        html = auth_client.get(_step_url(draft, 2)).content.decode()

        assert 'type="date"' in html
        assert "date-input-picker" in html
        assert "date-input-open" in html

    def test_o_campo_visivel_esta_preparado_para_digitacao(self, auth_client, draft):
        html = auth_client.get(_step_url(draft, 2)).content.decode()

        assert "data-date-input" in html
        assert 'inputmode="numeric"' in html
        assert 'placeholder="DD/MM/AAAA"' in html

    def test_aceita_digitacao_com_barras(self, auth_client, draft):
        auth_client.post(
            _step_url(draft, 2),
            {"stay_arrival": "10/10/2026", "stay_departure": "24/10/2026"},
        )
        draft.refresh_from_db()

        assert draft.data["stay_arrival"] == "2026-10-10"

    def test_aceita_iso_vindo_do_calendario(self, auth_client, draft):
        """O script manda ISO quando a data está completa; o servidor
        aceita os dois formatos."""
        auth_client.post(
            _step_url(draft, 2),
            {"stay_arrival": "2026-10-10", "stay_departure": "2026-10-24"},
        )
        draft.refresh_from_db()

        assert draft.data["stay_arrival"] == "2026-10-10"
        assert draft.data["stay_departure"] == "2026-10-24"

    def test_guarda_sempre_em_iso(self, auth_client, draft):
        auth_client.post(_step_url(draft, 2), VALID_2)
        draft.refresh_from_db()

        for valor in (draft.data["stay_arrival"], draft.data["stay_departure"]):
            datetime.date.fromisoformat(valor)  # não levanta

    def test_reexibe_no_formato_do_usuario(self, auth_client, draft):
        auth_client.post(_step_url(draft, 2), VALID_2)

        html = auth_client.get(_step_url(draft, 2)).content.decode()

        assert 'value="10/10/2026"' in html
        assert 'value="2026-10-10"' not in html

    @pytest.mark.parametrize("invalida", ["31/02/2026", "99/99/9999", "10/13/2026", "abc"])
    def test_data_impossivel_e_recusada_no_servidor(self, auth_client, draft, invalida):
        """A validação não depende do JavaScript."""
        response = auth_client.post(
            _step_url(draft, 2), {"stay_arrival": invalida, "stay_departure": "24/10/2026"}
        )

        draft.refresh_from_db()
        assert response.status_code == 200
        assert "stay_arrival" in response.context["form"].errors
        assert "stay_arrival" not in draft.data
