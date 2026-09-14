"""
Testes da Etapa 3.1: calendário no celular, chegada não retroativa, dados
do anfitrião vindos do perfil, estado do botão "Próxima etapa" e bloqueio
por perfil incompleto.

O fio condutor é o de sempre: o navegador ajuda, o servidor decide. Toda
regra testada aqui tem uma verificação que passa por HTTP, não só pelo
HTML renderizado.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.doctemplates.models import Nationality
from apps.letters import services

pytestmark = pytest.mark.django_db


def conteudo_do(pdf_bytes):
    """
    O CONTENT STREAM da primeira pagina -- os operadores de desenho --
    e nao o arquivo inteiro. Ver o docstring da funcao homonima em
    `test_render_letter.py`.
    """
    import io

    from pypdf import PdfReader

    return PdfReader(io.BytesIO(pdf_bytes)).pages[0].get_contents().get_data()


@pytest.fixture(autouse=True)
def _modelos_oficiais_prontos(modelos_oficiais_prontos):
    """
    Os quatro modelos oficiais com o logo materializado -- sem eles
    `official_document_template()` devolve `None` e o assistente
    recusa criar carta nenhuma (e esta certo: seria uma carta que
    nao viraria PDF).
    """

HOJE = timezone.localdate()
CHEGADA = HOJE + datetime.timedelta(days=30)
PARTIDA = CHEGADA + datetime.timedelta(days=14)


def _step_url(letter, step):
    return reverse("letters:step", args=[letter.uuid, step])


def _br(data):
    return data.strftime("%d/%m/%Y")


@pytest.fixture(autouse=True)
def _nacionalidade_do_convidado(nacionalidade_factory):
    nacionalidade_factory("Brasileira", guest_form="Brésilienne")


@pytest.fixture
def draft(user):
    return services.start_draft(user, "fr")


PASSO_1 = {
    "guest_name": "Maria Santos da Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "15/08/1990",
    "guest_passport": "YY0000",
}
PASSO_2 = {"stay_arrival": _br(CHEGADA), "stay_departure": _br(PARTIDA)}
PASSO_3 = {"host_confirm": "on"}
PASSO_4 = {"notice_informal": "on", "notice_prise_en_charge": "on"}
PASSOS = {1: PASSO_1, 2: PASSO_2, 3: PASSO_3, 4: PASSO_4}


def _fill_until(client, letter, step):
    for n in range(1, min(step, 5)):
        client.post(_step_url(letter, n), PASSOS[n])


def _finalizar(client, letter):
    for n in (1, 2, 3, 4):
        client.post(_step_url(letter, n), PASSOS[n])
    client.post(_step_url(letter, 5), {"language": "fr"})
    return client.post(_step_url(letter, 6))


# ---------------------------------------------------------------------------
# 1. Calendário nativo (celular incluído)
# ---------------------------------------------------------------------------


class TestCalendarioNativo:
    def test_o_seletor_e_um_input_date_de_verdade(self, auth_client, draft):
        """Não é um campo de texto disfarçado: é o controle nativo."""
        html = auth_client.get(_step_url(draft, 1)).content.decode()

        assert '<input type="date" class="date-input-picker"' in html

    def test_o_seletor_e_tocavel_e_alcancavel_pelo_teclado(self, auth_client, draft):
        """
        No celular o que abre o calendário é o toque no próprio
        `input[type=date]` -- `showPicker()` não existe no Safari do iOS.
        Então ele não pode estar escondido de quem toca nem de quem
        navega por teclado.
        """
        html = auth_client.get(_step_url(draft, 1)).content.decode()
        inicio = html.index("date-input-picker")
        trecho = html[inicio : html.index("date-input-open", inicio)]

        assert 'tabindex="-1"' not in trecho
        assert "aria-hidden" not in trecho
        assert "aria-label" in trecho

    def test_o_campo_digitavel_continua_ao_lado(self, auth_client, draft):
        """Calendário e digitação convivem -- um não substitui o outro."""
        html = auth_client.get(_step_url(draft, 1)).content.decode()

        assert "data-date-input" in html
        assert 'inputmode="numeric"' in html
        assert 'placeholder="DD/MM/AAAA"' in html

    def test_o_perfil_usa_o_mesmo_campo_de_data(self, auth_client):
        html = auth_client.get(reverse("accounts:profile")).content.decode()

        assert '<input type="date" class="date-input-picker"' in html
        assert "data-date-input" in html


# ---------------------------------------------------------------------------
# 2. Chegada não pode ser no passado
# ---------------------------------------------------------------------------


class TestChegadaNaoRetroativa:
    def test_o_campo_leva_a_data_minima_para_o_calendario(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        html = auth_client.get(_step_url(draft, 2)).content.decode()

        assert f'data-date-min="{HOJE.isoformat()}"' in html

    def test_chegada_de_ontem_e_recusada(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)
        ontem = HOJE - datetime.timedelta(days=1)

        response = auth_client.post(
            _step_url(draft, 2),
            {"stay_arrival": _br(ontem), "stay_departure": _br(PARTIDA)},
        )

        draft.refresh_from_db()
        assert response.status_code == 200
        assert "stay_arrival" in response.context["form"].errors
        assert "stay_arrival" not in draft.data

    def test_chegada_hoje_e_aceita(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        response = auth_client.post(
            _step_url(draft, 2),
            {"stay_arrival": _br(HOJE), "stay_departure": _br(HOJE)},
        )

        draft.refresh_from_db()
        assert response.status_code == 302
        assert draft.data["stay_arrival"] == HOJE.isoformat()

    def test_post_direto_nao_contorna_a_regra(self, auth_client, draft):
        """Sem passar pela tela: a validação é do servidor."""
        _fill_until(auth_client, draft, 2)
        antigo = HOJE - datetime.timedelta(days=365)

        auth_client.post(
            _step_url(draft, 2),
            {"stay_arrival": antigo.isoformat(), "stay_departure": PARTIDA.isoformat()},
        )

        draft.refresh_from_db()
        assert "stay_arrival" not in draft.data

    def test_a_mensagem_explica_o_motivo(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)
        ontem = HOJE - datetime.timedelta(days=1)

        html = auth_client.post(
            _step_url(draft, 2),
            {"stay_arrival": _br(ontem), "stay_departure": _br(PARTIDA)},
        ).content.decode()

        assert "não pode ser anterior a hoje" in html

    def test_as_regras_de_partida_continuam_valendo(self, auth_client, draft):
        """Chegada futura, mas partida antes dela: continua recusado."""
        _fill_until(auth_client, draft, 2)

        response = auth_client.post(
            _step_url(draft, 2),
            {"stay_arrival": _br(PARTIDA), "stay_departure": _br(CHEGADA)},
        )

        assert "stay_departure" in response.context["form"].errors

    def test_o_limite_de_90_dias_continua_valendo(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        response = auth_client.post(
            _step_url(draft, 2),
            {
                "stay_arrival": _br(CHEGADA),
                "stay_departure": _br(CHEGADA + datetime.timedelta(days=90)),
            },
        )

        assert "stay_departure" in response.context["form"].errors

    def test_nascimento_pode_ser_no_passado(self, auth_client, draft):
        """A regra é só da chegada -- data de nascimento é o oposto."""
        html = auth_client.get(_step_url(draft, 1)).content.decode()
        inicio = html.index("guest_birth_date")
        trecho = html[max(0, inicio - 500) : inicio + 500]

        assert "data-date-min" not in trecho


# ---------------------------------------------------------------------------
# 3. Dados do anfitrião vêm do perfil
# ---------------------------------------------------------------------------


class TestDadosDoAnfitriaoNoPerfil:
    def test_o_perfil_guarda_nascimento_e_nacionalidade(self, user):
        assert user.birth_date == datetime.date(1985, 3, 14)
        assert user.nationality.code == "belge"

    def test_a_nacionalidade_e_uma_referencia_e_nao_texto(self, user):
        assert isinstance(user.nationality, Nationality)

    def test_o_perfil_edita_os_dois_campos(self, auth_client):
        from apps.accounts.forms import PROFILE_FIELDS

        html = auth_client.get(reverse("accounts:profile")).content.decode()

        assert "birth_date" in PROFILE_FIELDS
        assert "nationality" in PROFILE_FIELDS
        assert 'name="birth_date"' in html
        assert 'name="nationality"' in html

    def test_a_nacionalidade_do_perfil_so_oferece_as_ativas(self, auth_client, user):
        from apps.accounts.forms import ProfileForm

        inativa = Nationality.objects.create(
            code="XX",
            name_pt="Inativa",
            name_fr="Inactive",
            name_nl="Inactief",
            name_en="Inactive",
            guest_form="Inactive",
            host_form="inactive",
            is_active=False,
        )

        opcoes = list(ProfileForm(instance=user).fields["nationality"].queryset)

        assert inativa not in opcoes
        assert user.nationality in opcoes

    @pytest.mark.parametrize(
        "campo", ["host_nationality", "host_birth_date", "host_document_number"]
    )
    def test_o_assistente_nao_pede_mais_esses_dados(self, auth_client, draft, campo):
        _fill_until(auth_client, draft, 3)

        html = auth_client.get(_step_url(draft, 3)).content.decode()

        assert f'name="{campo}"' not in html

    def test_o_schema_nao_tem_mais_esses_campos(self):
        modelo = services.official_document_template("fr")
        chaves = {f["key"] for f in modelo.field_schema["fields"]}

        assert "host_nationality" not in chaves
        assert "host_birth_date" not in chaves
        # A declaração é um ato daquela carta, não um dado da pessoa: fica.
        assert "host_confirm" in chaves

    def test_a_etapa_mostra_os_dados_do_perfil(self, auth_client, draft, user):
        _fill_until(auth_client, draft, 3)

        html = auth_client.get(_step_url(draft, 3)).content.decode()

        assert "14/03/1985" in html
        assert str(user.nationality) in html
        assert user.document_number in html

    def test_o_snapshot_congela_nascimento_e_nacionalidade(self, auth_client, draft):
        _finalizar(auth_client, draft)
        draft.refresh_from_db()

        assert draft.snapshot["host"]["birth_date"] == "1985-03-14"
        assert draft.snapshot["nationalities"]["host_nationality"] == "belge"

    def test_mudar_o_perfil_depois_nao_altera_a_carta_emitida(self, auth_client, draft, user):
        """
        O DESENHO do documento, não os bytes do arquivo: o reportlab
        grava um `/ID` novo (derivado do instante) a cada chamada,
        então dois arquivos do mesmo documento nunca são byte a byte
        iguais. O content stream -- os operadores de desenho -- é
        determinístico, e é ele que diz se a carta mudou. Mesmo
        critério de `test_render_letter.py`.
        """
        _finalizar(auth_client, draft)
        draft.refresh_from_db()
        conteudo_antes = conteudo_do(draft.pdf_file.read())

        outra = Nationality.objects.create(
            code="FR",
            name_pt="Francesa",
            name_fr="Française",
            name_nl="Franse",
            name_en="French",
            guest_form="Française",
            host_form="française",
        )
        user.nationality = outra
        user.birth_date = datetime.date(1990, 1, 1)
        user.save()

        services.generate_pdf(draft)
        draft.refresh_from_db()

        assert draft.snapshot["host"]["birth_date"] == "1985-03-14"
        assert draft.snapshot["nationalities"]["host_nationality"] == "belge"
        assert conteudo_do(draft.pdf_file.read()) == conteudo_antes

    def test_a_carta_gerada_imprime_os_dados_do_perfil(self, auth_client, draft):
        import io as _io

        from pypdf import PdfReader

        _finalizar(auth_client, draft)
        draft.refresh_from_db()

        with draft.pdf_file.open("rb") as fh:
            texto = " ".join(PdfReader(_io.BytesIO(fh.read())).pages[0].extract_text().split())

        assert "14/03/1985" in texto
        assert "titulaire de la carte d’identité belge" in texto
        assert "00000000" in texto


# ---------------------------------------------------------------------------
# 4. Perfil incompleto bloqueia a etapa do anfitrião
# ---------------------------------------------------------------------------


class TestPerfilIncompletoNaEtapaDoAnfitriao:
    def _sem(self, user, **campos):
        for campo, valor in campos.items():
            setattr(user, campo, valor)
        user.save()

    @pytest.mark.parametrize(
        "campos,rotulo",
        [
            ({"birth_date": None}, "data de nascimento"),
            ({"nationality": None}, "nacionalidade"),
            ({"document_number": ""}, "número do documento"),
            ({"city": ""}, "cidade"),
        ],
    )
    def test_a_etapa_diz_o_que_falta(self, auth_client, draft, user, campos, rotulo):
        _fill_until(auth_client, draft, 3)
        self._sem(user, **campos)

        html = auth_client.get(_step_url(draft, 3)).content.decode()

        assert "Faltam dados no seu perfil" in html
        assert rotulo in html

    def test_o_modal_oferece_atualizar_o_perfil_e_voltar(self, auth_client, draft, user):
        _fill_until(auth_client, draft, 3)
        self._sem(user, birth_date=None)

        html = auth_client.get(_step_url(draft, 3)).content.decode()

        assert 'id="dlg-perfil"' in html
        assert "Atualizar meu perfil" in html
        # o link volta para esta mesma etapa depois de salvar
        assert "next=" in html
        assert "step/3" in html

    def test_o_backend_recusa_o_post_mesmo_sem_passar_pela_tela(
        self, auth_client, draft, user
    ):
        _fill_until(auth_client, draft, 3)
        self._sem(user, nationality=None)

        response = auth_client.post(_step_url(draft, 3), PASSO_3)

        draft.refresh_from_db()
        assert response.status_code == 302
        assert response.url == _step_url(draft, 3)
        assert "host_confirm" not in draft.data

    def test_com_o_perfil_completo_a_etapa_avanca(self, auth_client, draft):
        _fill_until(auth_client, draft, 3)

        response = auth_client.post(_step_url(draft, 3), PASSO_3)

        draft.refresh_from_db()
        assert response.status_code == 302
        assert response.url == _step_url(draft, 4)
        assert draft.data["host_confirm"] is True

    def test_sem_o_modal_quando_esta_tudo_certo(self, auth_client, draft):
        _fill_until(auth_client, draft, 3)

        html = auth_client.get(_step_url(draft, 3)).content.decode()

        assert 'id="dlg-perfil"' not in html
        assert "Faltam dados no seu perfil" not in html

    def test_depois_de_salvar_o_perfil_volta_para_a_etapa(self, auth_client, draft, user):
        """O `?next=` leva a pessoa de volta para onde parou."""
        self._sem(user, birth_date=None)
        volta = _step_url(draft, 3)

        response = auth_client.post(
            reverse("accounts:profile"),
            {
                "action": "dados",
                "next": volta,
                "full_name": user.full_name,
                "email": user.email,
                "phone": user.phone,
                "birth_date": "14/03/1985",
                "nationality": user.nationality_id,
                "document_number": user.document_number,
                "address_line1": user.address_line1,
                "postal_code": user.postal_code,
                "city": user.city,
            },
        )

        user.refresh_from_db()
        assert user.birth_date == datetime.date(1985, 3, 14)
        assert response.url == volta

    def test_next_para_fora_do_site_e_ignorado(self, auth_client, user):
        """Um destino externo aqui seria um redirecionamento aberto."""
        response = auth_client.post(
            reverse("accounts:profile"),
            {
                "action": "dados",
                "next": "https://exemplo-malicioso.test/",
                "full_name": user.full_name,
                "email": user.email,
                "phone": user.phone,
                "birth_date": "14/03/1985",
                "nationality": user.nationality_id,
                "document_number": user.document_number,
                "address_line1": user.address_line1,
                "postal_code": user.postal_code,
                "city": user.city,
            },
        )

        assert "exemplo-malicioso" not in response.url


# ---------------------------------------------------------------------------
# 5. Botão "Próxima etapa"
# ---------------------------------------------------------------------------


class TestBotaoAvancar:
    @pytest.mark.parametrize("etapa", [1, 2, 3, 4, 5])
    def test_o_botao_e_marcado_para_o_script(self, auth_client, draft, etapa):
        _fill_until(auth_client, draft, etapa)

        html = auth_client.get(_step_url(draft, etapa)).content.decode()

        assert "data-step-submit" in html

    @pytest.mark.parametrize("etapa", [1, 2, 4, 5])
    def test_o_botao_nunca_usa_o_atributo_disabled(self, auth_client, draft, etapa):
        """
        O botão fica com CARA de desabilitado, mas continua clicável: um
        `disabled` de verdade impediria o envio e, com ele, as mensagens
        de erro do servidor.
        """
        _fill_until(auth_client, draft, etapa)

        html = auth_client.get(_step_url(draft, etapa)).content.decode()
        inicio = html.index("data-step-submit")
        botao = html[max(0, inicio - 200) : inicio]

        assert " disabled" not in botao

    def test_enviar_vazio_devolve_os_erros_de_cada_campo(self, auth_client, draft):
        """É por isso que o botão não é `disabled` de verdade."""
        response = auth_client.post(_step_url(draft, 1), {})

        assert response.status_code == 200
        erros = response.context["form"].errors
        for campo in ("guest_name", "guest_nationality", "guest_birth_date", "guest_passport"):
            assert campo in erros

    def test_os_campos_obrigatorios_sao_marcados_no_html(self, auth_client, draft):
        """É de `[required]` que o script parte para saber o que falta."""
        html = auth_client.get(_step_url(draft, 1)).content.decode()

        assert html.count("required") >= 4
