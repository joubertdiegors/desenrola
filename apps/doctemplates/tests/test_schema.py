"""
Testes do contrato de traducao do field_schema: validacao das traducoes e
das opcoes, e a resolucao de texto por idioma com fallback seguro.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.doctemplates.official_templates import CARTA_CONVITE_FIELD_SCHEMA
from apps.doctemplates.schema import (
    resolve_field_text,
    resolve_label,
    resolve_options,
    validate_field_schema,
)

CAMPO_TRADUZIDO = {
    "key": "guest_name",
    "type": "text",
    "required": True,
    "label": "Nome completo",
    "placeholder": "Nome completo",
    "help_text": "Como no passaporte.",
    "translations": {
        "fr": {"label": "Nom complet", "placeholder": "Nom complet"},
        "nl": {"label": "Volledige naam"},
        "en": {"label": "Full name", "help_text": "As in the passport."},
    },
}


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------


class TestValidacaoDeTraducoes:
    def test_schema_com_traducoes_e_valido(self):
        validate_field_schema({"fields": [CAMPO_TRADUZIDO]})

    def test_traducao_que_nao_e_objeto_e_invalida(self):
        campo = {**CAMPO_TRADUZIDO, "translations": ["fr"]}
        with pytest.raises(ValidationError):
            validate_field_schema({"fields": [campo]})

    def test_idioma_desconhecido_e_invalido(self):
        campo = {**CAMPO_TRADUZIDO, "translations": {"de": {"label": "Name"}}}
        with pytest.raises(ValidationError):
            validate_field_schema({"fields": [campo]})

    def test_texto_desconhecido_na_traducao_e_invalido(self):
        campo = {**CAMPO_TRADUZIDO, "translations": {"fr": {"titulo": "Nom"}}}
        with pytest.raises(ValidationError):
            validate_field_schema({"fields": [campo]})

    def test_texto_que_nao_e_string_e_invalido(self):
        campo = {**CAMPO_TRADUZIDO, "translations": {"fr": {"label": 42}}}
        with pytest.raises(ValidationError):
            validate_field_schema({"fields": [campo]})


class TestValidacaoDeOpcoes:
    def test_opcoes_como_texto_continuam_validas(self):
        campo = {"key": "pais", "type": "select", "options": ["Bélgica", "Brasil"]}
        validate_field_schema({"fields": [campo]})

    def test_opcoes_como_objeto_traduzivel_sao_validas(self):
        campo = {
            "key": "pais",
            "type": "select",
            "options": [
                {"value": "be", "label": "Bélgica", "translations": {"fr": "Belgique"}},
                {"value": "br", "label": "Brasil", "translations": {"en": "Brazil"}},
            ],
        }
        validate_field_schema({"fields": [campo]})

    def test_opcao_sem_value_e_invalida(self):
        campo = {"key": "pais", "type": "select", "options": [{"label": "Bélgica"}]}
        with pytest.raises(ValidationError):
            validate_field_schema({"fields": [campo]})

    def test_opcao_com_idioma_desconhecido_e_invalida(self):
        campo = {
            "key": "pais",
            "type": "select",
            "options": [{"value": "be", "translations": {"de": "Belgien"}}],
        }
        with pytest.raises(ValidationError):
            validate_field_schema({"fields": [campo]})

    def test_options_que_nao_e_lista_e_invalido(self):
        campo = {"key": "pais", "type": "select", "options": {"be": "Bélgica"}}
        with pytest.raises(ValidationError):
            validate_field_schema({"fields": [campo]})


# ---------------------------------------------------------------------------
# Resolução por idioma
# ---------------------------------------------------------------------------


class TestResolucaoDeTexto:
    @pytest.mark.parametrize(
        ("language", "esperado"),
        [
            ("pt", "Nome completo"),
            ("fr", "Nom complet"),
            ("nl", "Volledige naam"),
            ("en", "Full name"),
        ],
    )
    def test_rotulo_nos_quatro_idiomas(self, language, esperado):
        assert resolve_label(CAMPO_TRADUZIDO, language) == esperado

    def test_texto_sem_traducao_volta_ao_original(self):
        # "nl" só traduz o label: placeholder e ajuda caem no texto de origem.
        assert resolve_field_text(CAMPO_TRADUZIDO, "nl", "placeholder") == "Nome completo"
        assert resolve_field_text(CAMPO_TRADUZIDO, "nl", "help_text") == "Como no passaporte."

    def test_idioma_desconhecido_volta_ao_original(self):
        assert resolve_label(CAMPO_TRADUZIDO, "de") == "Nome completo"

    def test_campo_sem_traducoes_usa_o_texto_de_origem(self):
        campo = {"key": "x", "type": "text", "label": "Rótulo"}
        assert resolve_label(campo, "fr") == "Rótulo"

    def test_campo_sem_rotulo_nenhum_cai_na_chave(self):
        assert resolve_label({"key": "x", "type": "text"}, "fr") == "x"

    def test_texto_inexistente_devolve_vazio(self):
        assert resolve_field_text({"key": "x", "type": "text"}, "fr", "help_text") == ""


class TestResolucaoDeOpcoes:
    OPCOES = {
        "key": "pais",
        "type": "select",
        "options": [
            {"value": "be", "label": "Bélgica", "translations": {"fr": "Belgique"}},
            {"value": "br", "label": "Brasil", "translations": {"en": "Brazil"}},
        ],
    }

    def test_valor_nao_muda_com_o_idioma(self):
        """O valor gravado em Letter.data é estável: trocar o idioma da
        carta não invalida o que já foi respondido."""
        valores_pt = [value for value, _label in resolve_options(self.OPCOES, "pt")]
        valores_fr = [value for value, _label in resolve_options(self.OPCOES, "fr")]

        assert valores_pt == valores_fr == ["be", "br"]

    def test_rotulo_traduzido_quando_existe(self):
        assert dict(resolve_options(self.OPCOES, "fr"))["be"] == "Belgique"
        assert dict(resolve_options(self.OPCOES, "en"))["br"] == "Brazil"

    def test_rotulo_volta_ao_original_sem_traducao(self):
        assert dict(resolve_options(self.OPCOES, "nl"))["be"] == "Bélgica"

    def test_opcoes_em_texto_simples_viram_valor_e_rotulo_iguais(self):
        campo = {"key": "pais", "type": "select", "options": ["Bélgica"]}
        assert resolve_options(campo, "fr") == [("Bélgica", "Bélgica")]


# ---------------------------------------------------------------------------
# O schema oficial semeado
# ---------------------------------------------------------------------------


class TestSchemaOficial:
    def test_e_valido_pelo_contrato(self):
        validate_field_schema(CARTA_CONVITE_FIELD_SCHEMA)

    @pytest.mark.parametrize("language", ["pt", "fr", "nl", "en"])
    def test_todo_campo_tem_rotulo_em_qualquer_idioma(self, language):
        for field in CARTA_CONVITE_FIELD_SCHEMA["fields"]:
            assert resolve_label(field, language)

    def test_declaracoes_do_usuario_ficam_sem_traducao_de_proposito(self):
        """
        Texto jurídico não é inventado: as três caixas que o usuário aceita
        não têm `translations` até o cliente fornecer as versões oficiais.
        """
        declaracoes = {"host_confirm", "notice_informal", "notice_prise_en_charge"}
        for field in CARTA_CONVITE_FIELD_SCHEMA["fields"]:
            if field["key"] in declaracoes:
                assert "translations" not in field
            else:
                assert set(field["translations"]) == {"fr", "nl", "en"}
