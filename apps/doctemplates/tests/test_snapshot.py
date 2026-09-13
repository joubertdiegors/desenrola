"""
Snapshot estrutural de um DocumentTemplate (Etapa 3.5.1).

Este arquivo testa so a camada PURA -- `build_snapshot()` e
`compute_hash()`, sem `Letter` nenhuma envolvida. A integracao com a
carta (captura na finalizacao, imutabilidade, concorrencia) esta em
`apps.letters.tests.test_document_snapshot`, porque e la que a Letter
entra em cena.
"""

import pytest

from apps.doctemplates.models import DocumentTemplate, DocumentType
from apps.doctemplates.services import snapshot

pytestmark = pytest.mark.django_db


@pytest.fixture
def tipo():
    return DocumentType.objects.create(
        code="carta-de-teste",
        name="Carta de teste",
        page={"width": 595.2756, "height": 841.8898, "unit": "pt"},
    )


@pytest.fixture
def modelo(tipo):
    return DocumentTemplate.objects.create(
        type=tipo,
        name="Modelo de teste",
        slug="modelo-de-teste",
        language="fr",
        field_schema={"fields": [{"key": "guest_name", "type": "text"}]},
        layout={
            "version": 1,
            "elements": [
                {
                    "id": "e1",
                    "type": "text",
                    "x": 10.0,
                    "y": 20.0,
                    "width": 100.0,
                    "height": 15.0,
                    "properties": {"content": {"kind": "text", "value": "Olá"}},
                }
            ],
        },
    )


# ===========================================================================
# 1. O conteúdo do snapshot
# ===========================================================================


class TestConteudoDoSnapshot:
    def test_contem_o_field_schema(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        assert estrutura["field_schema"] == modelo.field_schema

    def test_contem_o_layout(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        assert estrutura["layout"] == modelo.layout

    def test_contem_a_pagina_do_tipo_de_documento(self, modelo, tipo):
        estrutura = snapshot.build_snapshot(modelo)

        assert estrutura["type"]["page"] == tipo.page

    def test_contem_o_idioma(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        assert estrutura["language"] == "fr"

    def test_contem_a_identificacao_do_modelo(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        assert estrutura["id"] == modelo.pk
        assert estrutura["slug"] == "modelo-de-teste"
        assert estrutura["name"] == "Modelo de teste"

    def test_contem_o_tipo_de_documento(self, modelo, tipo):
        estrutura = snapshot.build_snapshot(modelo)

        assert estrutura["type"]["code"] == tipo.code
        assert estrutura["type"]["name"] == tipo.name

    def test_contem_is_system_e_is_locked(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        assert estrutura["is_system"] is False
        assert estrutura["is_locked"] is False

    def test_contem_a_linhagem(self, tipo, modelo):
        copia = DocumentTemplate.objects.create(
            type=tipo, name="Cópia", slug="copia-de-teste", language="fr",
            duplicated_from=modelo,
        )

        estrutura = snapshot.build_snapshot(copia)

        assert estrutura["duplicated_from_id"] == modelo.pk

    def test_contem_o_instante_da_captura(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        assert estrutura["captured_at"]

    def test_o_instante_pode_ser_informado_explicitamente(self, modelo):
        import datetime

        quando = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

        estrutura = snapshot.build_snapshot(modelo, captured_at=quando)

        assert estrutura["captured_at"] == quando.isoformat()


# ===========================================================================
# 2. Cópia profunda
# ===========================================================================


class TestCopiaProfunda:
    def test_o_layout_do_snapshot_nao_e_o_mesmo_objeto(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        assert estrutura["layout"] is not modelo.layout
        assert estrutura["layout"]["elements"] is not modelo.layout["elements"]

    def test_alterar_o_layout_original_depois_nao_afeta_o_snapshot(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        modelo.layout["elements"].append({"id": "invasor", "type": "line"})

        assert len(estrutura["layout"]["elements"]) == 1

    def test_alterar_o_field_schema_original_depois_nao_afeta_o_snapshot(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        modelo.field_schema["fields"].append({"key": "novo", "type": "text"})

        assert len(estrutura["field_schema"]["fields"]) == 1

    def test_alterar_o_snapshot_devolvido_nao_afeta_o_modelo_original(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        estrutura["layout"]["elements"][0]["properties"]["content"]["value"] = "Adulterado"

        assert modelo.layout["elements"][0]["properties"]["content"]["value"] == "Olá"

    def test_alterar_a_pagina_do_tipo_depois_nao_afeta_o_snapshot(self, modelo, tipo):
        estrutura = snapshot.build_snapshot(modelo)

        tipo.page["width"] = 999.0

        assert estrutura["type"]["page"]["width"] == 595.2756

    def test_nao_grava_nem_altera_o_modelo_original(self, modelo):
        antes = DocumentTemplate.objects.get(pk=modelo.pk)

        snapshot.build_snapshot(modelo)

        depois = DocumentTemplate.objects.get(pk=modelo.pk)
        assert depois.updated_at == antes.updated_at
        assert depois.layout == antes.layout


# ===========================================================================
# 3. Hash determinístico
# ===========================================================================


class TestHash:
    def test_e_uma_string_hexadecimal_sha256(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        resultado = snapshot.compute_hash(estrutura)

        assert len(resultado) == 64
        assert all(c in "0123456789abcdef" for c in resultado)

    def test_e_deterministico_para_o_mesmo_conteudo(self, modelo):
        estrutura = snapshot.build_snapshot(modelo)

        primeiro = snapshot.compute_hash(estrutura)
        segundo = snapshot.compute_hash(estrutura)

        assert primeiro == segundo

    def test_duas_capturas_do_mesmo_modelo_tem_o_mesmo_hash(self, modelo):
        """
        Sem alteração nenhuma no modelo entre as duas capturas, o hash é
        igual -- mesmo com `captured_at` diferente em cada uma.
        """
        primeira = snapshot.build_snapshot(modelo)
        segunda = snapshot.build_snapshot(modelo)

        assert primeira["captured_at"] != ""
        assert snapshot.compute_hash(primeira) == snapshot.compute_hash(segunda)

    def test_muda_quando_o_layout_muda(self, modelo):
        antes = snapshot.compute_hash(snapshot.build_snapshot(modelo))

        modelo.layout["elements"][0]["x"] = 999.0
        depois = snapshot.compute_hash(snapshot.build_snapshot(modelo))

        assert antes != depois

    def test_muda_quando_o_field_schema_muda(self, modelo):
        antes = snapshot.compute_hash(snapshot.build_snapshot(modelo))

        modelo.field_schema["fields"][0]["type"] = "date"
        depois = snapshot.compute_hash(snapshot.build_snapshot(modelo))

        assert antes != depois

    def test_muda_quando_o_idioma_muda(self, modelo):
        antes = snapshot.compute_hash(snapshot.build_snapshot(modelo))

        modelo.language = "nl"
        depois = snapshot.compute_hash(snapshot.build_snapshot(modelo))

        assert antes != depois

    def test_muda_quando_a_pagina_muda(self, modelo, tipo):
        antes = snapshot.compute_hash(snapshot.build_snapshot(modelo))

        tipo.page["width"] = 300.0
        depois = snapshot.compute_hash(snapshot.build_snapshot(modelo))

        assert antes != depois

    def test_nao_muda_por_ordem_de_chaves_no_nivel_superior(self):
        um = {"b": 2, "a": 1, "captured_at": "x"}
        outro = {"a": 1, "captured_at": "x", "b": 2}

        assert snapshot.compute_hash(um) == snapshot.compute_hash(outro)

    def test_nao_muda_por_ordem_de_chaves_aninhadas(self):
        um = {"layout": {"version": 1, "elements": []}, "field_schema": {"fields": []}}
        outro = {"field_schema": {"fields": []}, "layout": {"elements": [], "version": 1}}

        assert snapshot.compute_hash(um) == snapshot.compute_hash(outro)

    def test_nao_muda_por_ordem_de_chaves_dentro_de_uma_lista_de_dicts(self):
        elemento_a = {"id": "e1", "type": "text", "x": 1}
        elemento_b = {"x": 1, "type": "text", "id": "e1"}

        um = {"layout": {"elements": [elemento_a]}}
        outro = {"layout": {"elements": [elemento_b]}}

        assert snapshot.compute_hash(um) == snapshot.compute_hash(outro)

    def test_captured_at_nao_entra_na_conta(self):
        um = {"x": 1, "captured_at": "2026-01-01T00:00:00"}
        outro = {"x": 1, "captured_at": "2030-12-31T23:59:59"}

        assert snapshot.compute_hash(um) == snapshot.compute_hash(outro)

    def test_conteudo_diferente_sem_captured_at_da_hash_diferente(self):
        um = {"x": 1}
        outro = {"x": 2}

        assert snapshot.compute_hash(um) != snapshot.compute_hash(outro)


class TestJsonCanonico:
    def test_chaves_saem_ordenadas(self):
        bruto = snapshot.canonical_json({"b": 1, "a": 2})

        assert bruto == '{"a":2,"b":1}'

    def test_e_compacto_sem_espacos(self):
        bruto = snapshot.canonical_json({"a": [1, 2, 3]})

        assert " " not in bruto

    def test_preserva_acentos(self):
        bruto = snapshot.canonical_json({"nome": "Café à la carte"})

        assert "Café à la carte" in bruto
