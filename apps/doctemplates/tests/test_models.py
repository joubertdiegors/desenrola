"""
O contrato do `field_schema` cobrado pelo MODELO.

`test_schema.py` cobre a funcao de validacao isolada; aqui o que importa
e que `DocumentTemplate.full_clean()` de fato a chama -- um schema
invalido tem de ser recusado ao gravar, nao so quando alguem se lembrar
de validar a mao.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.doctemplates.models import DocumentTemplate, DocumentType
from apps.doctemplates.schema import FIELD_TYPE_CHOICES

pytestmark = pytest.mark.django_db


@pytest.fixture
def modelo():
    tipo = DocumentType.objects.create(
        code="contrato-de-teste",
        name="Contrato",
        page={"width": 595.2756, "height": 841.8898, "unit": "pt"},
        data_sources=["documento", "convidado"],
    )
    return DocumentTemplate(
        type=tipo, name="Modelo de teste", slug="modelo-de-teste", language="pt"
    )


class TestFieldSchemaContrato:
    VALIDO = {
        "fields": [
            {
                "key": "nome_convidado",
                "type": "text",
                "label": "Nome completo",
                "required": True,
                "order": 1,
            },
            {
                "key": "nacionalidade",
                "type": "select",
                "label": "Nacionalidade",
                "options": ["Brasileira", "Belga"],
            },
        ]
    }

    def test_schema_vazio_e_valido(self, modelo):
        modelo.field_schema = {}
        modelo.full_clean()

    def test_schema_no_formato_documentado_e_valido(self, modelo):
        modelo.field_schema = self.VALIDO
        modelo.full_clean()

    def test_schema_que_nao_e_um_objeto_e_invalido(self, modelo):
        modelo.field_schema = ["nome_convidado"]
        with pytest.raises(ValidationError):
            modelo.full_clean()

    def test_campo_sem_key_e_invalido(self, modelo):
        modelo.field_schema = {"fields": [{"type": "text"}]}
        with pytest.raises(ValidationError):
            modelo.full_clean()

    def test_chave_duplicada_e_invalida(self, modelo):
        modelo.field_schema = {
            "fields": [
                {"key": "nome", "type": "text"},
                {"key": "nome", "type": "email"},
            ]
        }
        with pytest.raises(ValidationError):
            modelo.full_clean()

    def test_tipo_invalido_e_recusado(self, modelo):
        modelo.field_schema = {"fields": [{"key": "nome", "type": "url"}]}
        with pytest.raises(ValidationError):
            modelo.full_clean()

    @pytest.mark.parametrize("tipo", list(FIELD_TYPE_CHOICES))
    def test_todos_os_tipos_previstos_sao_aceitos(self, modelo, tipo):
        field = {"key": "campo", "type": tipo}
        if tipo in ("select", "radio"):
            field["options"] = ["a", "b"]
        modelo.field_schema = {"fields": [field]}
        modelo.full_clean()

    def test_select_sem_options_e_invalido(self, modelo):
        modelo.field_schema = {"fields": [{"key": "pais", "type": "select"}]}
        with pytest.raises(ValidationError):
            modelo.full_clean()

    def test_radio_sem_options_e_invalido(self, modelo):
        modelo.field_schema = {"fields": [{"key": "sexo", "type": "radio"}]}
        with pytest.raises(ValidationError):
            modelo.full_clean()
