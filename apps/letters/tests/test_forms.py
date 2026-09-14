"""
Testes do formulario dinamico: `apps.letters.forms` transforma uma lista
de definicoes do field_schema num `forms.Form` real, sem hardcode de
campo nenhum -- so o TIPO decide o campo Django gerado.
"""

import datetime

import pytest
from django.utils import timezone

from apps.letters.forms import build_dynamic_form, deserialize_initial, serialize_cleaned_data


def _field(**overrides):
    base = {"key": "campo", "type": "text", "label": "Campo", "required": True}
    base.update(overrides)
    return base


class TestConstrucaoPorTipo:
    def test_text_obrigatorio_recusa_vazio(self):
        form = build_dynamic_form([_field(type="text")], data={})
        assert not form.is_valid()
        assert "campo" in form.errors

    def test_text_aceita_valor(self):
        form = build_dynamic_form([_field(type="text")], data={"campo": "Maria"})
        assert form.is_valid()
        assert form.cleaned_data["campo"] == "Maria"

    def test_textarea_aceita_texto_longo(self):
        form = build_dynamic_form([_field(type="textarea")], data={"campo": "Linha 1\nLinha 2"})
        assert form.is_valid()

    def test_email_recusa_formato_invalido(self):
        form = build_dynamic_form([_field(type="email")], data={"campo": "nao-e-email"})
        assert not form.is_valid()

    def test_email_aceita_formato_valido(self):
        form = build_dynamic_form([_field(type="email")], data={"campo": "a@b.com"})
        assert form.is_valid()

    def test_number_recusa_texto(self):
        form = build_dynamic_form([_field(type="number")], data={"campo": "abc"})
        assert not form.is_valid()

    def test_number_aceita_inteiro(self):
        form = build_dynamic_form([_field(type="number")], data={"campo": "42"})
        assert form.is_valid()
        assert form.cleaned_data["campo"] == 42

    def test_phone_recusa_formato_invalido(self):
        form = build_dynamic_form([_field(type="phone")], data={"campo": "###"})
        assert not form.is_valid()

    def test_phone_aceita_formato_valido(self):
        form = build_dynamic_form([_field(type="phone")], data={"campo": "+32 470 00 00 00"})
        assert form.is_valid()

    def test_select_exige_uma_das_opcoes(self):
        form = build_dynamic_form(
            [_field(type="select", options=["Brasileira", "Belga"])], data={"campo": "Francesa"}
        )
        assert not form.is_valid()

    def test_select_aceita_opcao_valida(self):
        form = build_dynamic_form(
            [_field(type="select", options=["Brasileira", "Belga"])], data={"campo": "Belga"}
        )
        assert form.is_valid()

    def test_radio_aceita_opcao_valida(self):
        form = build_dynamic_form(
            [_field(type="radio", options=["Sim", "Não"])], data={"campo": "Sim"}
        )
        assert form.is_valid()

    def test_checkbox_obrigatorio_recusa_desmarcado(self):
        form = build_dynamic_form([_field(type="checkbox")], data={})
        assert not form.is_valid()

    def test_checkbox_aceita_marcado(self):
        form = build_dynamic_form([_field(type="checkbox")], data={"campo": "on"})
        assert form.is_valid()
        assert form.cleaned_data["campo"] is True

    def test_campo_nao_obrigatorio_aceita_vazio(self):
        form = build_dynamic_form([_field(type="text", required=False)], data={})
        assert form.is_valid()

    def test_tipo_desconhecido_levanta_erro(self):
        with pytest.raises(ValueError):
            build_dynamic_form([_field(type="url")], data={})


class TestCampoData:
    def test_aceita_formato_dd_mm_aaaa(self):
        form = build_dynamic_form([_field(type="date")], data={"campo": "10/04/2025"})
        assert form.is_valid()
        assert form.cleaned_data["campo"] == datetime.date(2025, 4, 10)

    def test_aceita_formato_iso_para_revalidacao(self):
        """
        Necessario para `services.validate_all_steps` revalidar o que ja
        esta salvo em Letter.data (gravado em ISO por
        `serialize_cleaned_data`), sem que o usuario tenha digitado nada.
        """
        form = build_dynamic_form([_field(type="date")], data={"campo": "2025-04-10"})
        assert form.is_valid()
        assert form.cleaned_data["campo"] == datetime.date(2025, 4, 10)

    def test_recusa_formato_invalido(self):
        form = build_dynamic_form([_field(type="date")], data={"campo": "2025/04/10"})
        assert not form.is_valid()

    def test_13_09_2026_e_13_de_setembro_nao_9_de_setembro(self):
        """13/09/2026: dia 13, mes 09 -- se dia e mes fossem trocados,
        13 nao existe como mes e o valor teria de ser recusado, nao virar
        setembro."""
        form = build_dynamic_form([_field(type="date")], data={"campo": "13/09/2026"})
        assert form.is_valid(), form.errors
        assert form.cleaned_data["campo"] == datetime.date(2026, 9, 13)

    def test_09_12_2026_e_9_de_dezembro_nao_12_de_setembro(self):
        """09/12/2026: dia 9, mes 12 -- o caso ambiguo por excelencia.
        Trocado, viraria 12/09 (12 de setembro); o certo e 9 de dezembro."""
        form = build_dynamic_form([_field(type="date")], data={"campo": "09/12/2026"})
        assert form.is_valid(), form.errors
        assert form.cleaned_data["campo"] == datetime.date(2026, 12, 9)

    @pytest.mark.parametrize(
        "valor",
        [
            "31/02/2026",  # fevereiro nao tem dia 31
            "32/01/2026",  # dia inexistente
            "13/13/2026",  # mes 13 nao existe -- so faz sentido se fosse dia
            "00/09/2026",
            "13/00/2026",
            "13/09/226",  # ano incompleto
            "",
        ],
    )
    def test_datas_invalidas_sao_recusadas(self, valor):
        form = build_dynamic_form([_field(type="date")], data={"campo": valor})
        assert not form.is_valid()

    def test_submissao_armazena_a_data_correta_nao_invertida(self):
        """O que `serialize_cleaned_data` grava (o que vai para
        `Letter.data`) tem de ser o mesmo dia e mes que a pessoa digitou,
        em ISO -- nunca com dia e mes trocados de lugar."""
        form = build_dynamic_form([_field(type="date")], data={"campo": "13/09/2026"})
        assert form.is_valid(), form.errors

        armazenado = serialize_cleaned_data(form.cleaned_data)

        assert armazenado["campo"] == "2026-09-13"


class TestCampoDataReexibicao:
    """
    A reexibicao apos um erro em OUTRO campo da mesma etapa: e aqui que a
    validacao manual encontrou "2026-09-13" no lugar de "13/09/2026" --
    o `DateInput` padrao do Django so reformata um `date` de verdade
    (`initial=`), nunca uma string ja vinculada (o que chega de volta
    depois de um POST). `_RobustDateInput` cobre os dois casos.
    """

    def _campo_renderizado(self, form, chave="campo"):
        return str(form[chave])

    def test_valor_vinculado_em_dd_mm_aaaa_reexibe_sem_alteracao(self):
        form = build_dynamic_form([_field(type="date")], data={"campo": "13/09/2026"})

        assert 'value="13/09/2026"' in self._campo_renderizado(form)

    def test_valor_vinculado_em_iso_reexibe_em_dd_mm_aaaa(self):
        """
        O caso central do bug: um valor que chegue vinculado em ISO (o
        formato que `DATE_INPUT_FORMATS` tambem aceita, usado por
        `validate_all_steps` para revalidar `Letter.data`) tem de
        aparecer em dd/mm/aaaa na tela -- nunca no formato em que
        chegou.
        """
        form = build_dynamic_form([_field(type="date")], data={"campo": "2026-09-13"})

        html = self._campo_renderizado(form)
        assert 'value="13/09/2026"' in html
        assert "2026-09-13" not in html

    def test_erro_em_outro_campo_da_mesma_etapa_nao_corrompe_a_data_valida(self):
        """
        Reproduz o bug relatado na validacao manual: numa etapa com dois
        campos de data, uma chegada valida ao lado de uma partida que
        fere a regra de negocio (antes da chegada) nao pode fazer a
        chegada -- que a pessoa digitou certo -- reexibir errada.

        Datas RELATIVAS a hoje, nao fixas: `stay_arrival` esta em
        `NOT_IN_THE_PAST`, entao uma data fixa no codigo venceria com o
        tempo e o erro cairia na chegada em vez da partida.
        """
        chegada = timezone.localdate() + datetime.timedelta(days=30)
        partida = chegada - datetime.timedelta(days=5)
        campos = [
            _field(key="stay_arrival", type="date", label="Chegada"),
            _field(key="stay_departure", type="date", label="Partida"),
        ]
        form = build_dynamic_form(
            campos,
            data={
                "stay_arrival": chegada.strftime("%d/%m/%Y"),
                "stay_departure": partida.strftime("%d/%m/%Y"),
            },
        )

        assert not form.is_valid()
        assert "stay_departure" in form.errors

        esperado = f'value="{chegada.strftime("%d/%m/%Y")}"'
        assert esperado in self._campo_renderizado(form, "stay_arrival")


class TestValidacaoCruzadaViagem:
    FIELDS = [
        _field(key="stay_arrival", type="date", label="Chegada"),
        _field(key="stay_departure", type="date", label="Partida"),
    ]

    # Datas relativas a hoje: a chegada nao pode ser no passado, entao uma
    # data fixa no codigo venceria com o tempo.
    CHEGADA = timezone.localdate() + datetime.timedelta(days=30)

    def _br(self, data):
        return data.strftime("%d/%m/%Y")

    def _viagem(self, *, chegada=None, dias=None, partida=None):
        chegada = chegada or self.CHEGADA
        if partida is None:
            partida = chegada + datetime.timedelta(days=dias or 0)
        return {
            "stay_arrival": self._br(chegada),
            "stay_departure": self._br(partida),
        }

    def test_partida_antes_da_chegada_e_invalida(self):
        form = build_dynamic_form(
            self.FIELDS,
            data=self._viagem(partida=self.CHEGADA - datetime.timedelta(days=5)),
        )
        assert not form.is_valid()
        assert "stay_departure" in form.errors

    def test_partida_no_mesmo_dia_da_chegada_e_valida(self):
        """
        Chegar e partir no mesmo dia é uma estadia de 1 dia -- válida.
        (Antes era recusada; a regra passou a ser chegada <= partida.)
        """
        form = build_dynamic_form(self.FIELDS, data=self._viagem(dias=0))
        assert form.is_valid(), form.errors

    def test_chegada_no_passado_e_recusada(self):
        """A carta convida para uma viagem que ainda vai acontecer."""
        ontem = timezone.localdate() - datetime.timedelta(days=1)
        form = build_dynamic_form(
            self.FIELDS, data=self._viagem(chegada=ontem, dias=10)
        )
        assert not form.is_valid()
        assert "stay_arrival" in form.errors

    def test_chegada_hoje_e_valida(self):
        hoje = timezone.localdate()
        form = build_dynamic_form(self.FIELDS, data=self._viagem(chegada=hoje, dias=5))
        assert form.is_valid(), form.errors

    def test_estadia_de_ate_90_dias_e_valida(self):
        form = build_dynamic_form(self.FIELDS, data=self._viagem(dias=89))
        assert form.is_valid(), form.errors

    def test_estadia_acima_de_90_dias_e_recusada(self):
        """O limite da carta de curta duração vive no formulário, não só
        no template -- é o que impede contornar mandando o POST direto."""
        form = build_dynamic_form(self.FIELDS, data=self._viagem(dias=90))
        assert not form.is_valid()
        assert "stay_departure" in form.errors
        assert "90" in str(form.errors["stay_departure"])

    def test_partida_depois_da_chegada_e_valida(self):
        form = build_dynamic_form(self.FIELDS, data=self._viagem(dias=15))
        assert form.is_valid(), form.errors


class TestIdiomaDosCampos:
    CAMPO = _field(
        key="guest_name",
        label="Nome completo",
        placeholder="Nome completo",
        help_text="Como no passaporte.",
        translations={
            "fr": {"label": "Nom complet", "placeholder": "Nom complet"},
            "nl": {"label": "Volledige naam"},
            "en": {"label": "Full name", "help_text": "As in the passport."},
        },
    )

    @pytest.mark.parametrize(
        ("language", "esperado"),
        [
            ("pt", "Nome completo"),
            ("fr", "Nom complet"),
            ("nl", "Volledige naam"),
            ("en", "Full name"),
        ],
    )
    def test_rotulo_no_idioma_pedido(self, language, esperado):
        form = build_dynamic_form([self.CAMPO], language=language)
        assert form["guest_name"].label == esperado

    def test_placeholder_e_ajuda_seguem_o_idioma(self):
        form = build_dynamic_form([self.CAMPO], language="en")
        assert form["guest_name"].help_text == "As in the passport."
        # "en" não traduz o placeholder: volta ao texto de origem.
        assert form["guest_name"].field.widget.attrs["placeholder"] == "Nome completo"

    def test_sem_idioma_usa_o_texto_de_origem(self):
        form = build_dynamic_form([self.CAMPO])
        assert form["guest_name"].label == "Nome completo"

    def test_opcoes_sao_traduzidas_mas_o_valor_nao_muda(self):
        campo = _field(
            type="select",
            options=[
                {"value": "be", "label": "Bélgica", "translations": {"fr": "Belgique"}},
                {"value": "br", "label": "Brasil"},
            ],
        )

        form_fr = build_dynamic_form([campo], data={"campo": "be"}, language="fr")
        rotulos = dict(form_fr["campo"].field.choices)

        assert form_fr.is_valid()
        assert form_fr.cleaned_data["campo"] == "be"
        assert rotulos["be"] == "Belgique"
        # Sem tradução em francês, a opção volta ao rótulo de origem.
        assert rotulos["br"] == "Brasil"

    def test_valor_de_opcao_continua_valido_em_outro_idioma(self):
        """Trocar o idioma da carta não invalida o que já foi respondido."""
        campo = _field(
            type="select",
            options=[{"value": "be", "label": "Bélgica", "translations": {"nl": "België"}}],
        )

        form = build_dynamic_form([campo], data={"campo": "be"}, language="nl")

        assert form.is_valid()
        assert form.cleaned_data["campo"] == "be"


class TestSerializacao:
    def test_serialize_converte_data_para_iso(self):
        result = serialize_cleaned_data({"nascimento": datetime.date(1990, 8, 15), "nome": "Ana"})
        assert result == {"nascimento": "1990-08-15", "nome": "Ana"}

    def test_deserialize_converte_iso_para_data(self):
        fields = [_field(key="nascimento", type="date")]
        initial = deserialize_initial(fields, {"nascimento": "1990-08-15"})
        assert initial == {"nascimento": datetime.date(1990, 8, 15)}

    def test_deserialize_ignora_chave_ausente(self):
        fields = [_field(key="nascimento", type="date")]
        assert deserialize_initial(fields, {}) == {}
