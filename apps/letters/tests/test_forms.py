"""
Testes do formulario dinamico: `apps.letters.forms` transforma uma lista
de definicoes do field_schema num `forms.Form` real, sem hardcode de
campo nenhum -- so o TIPO decide o campo Django gerado.
"""

import datetime

import pytest

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


class TestValidacaoCruzadaViagem:
    FIELDS = [
        _field(key="stay_arrival", type="date", label="Chegada"),
        _field(key="stay_departure", type="date", label="Partida"),
    ]

    def test_partida_antes_da_chegada_e_invalida(self):
        form = build_dynamic_form(
            self.FIELDS, data={"stay_arrival": "10/04/2025", "stay_departure": "05/04/2025"}
        )
        assert not form.is_valid()
        assert "stay_departure" in form.errors

    def test_partida_igual_a_chegada_e_invalida(self):
        form = build_dynamic_form(
            self.FIELDS, data={"stay_arrival": "10/04/2025", "stay_departure": "10/04/2025"}
        )
        assert not form.is_valid()

    def test_partida_depois_da_chegada_e_valida(self):
        form = build_dynamic_form(
            self.FIELDS, data={"stay_arrival": "10/04/2025", "stay_departure": "25/04/2025"}
        )
        assert form.is_valid()


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
