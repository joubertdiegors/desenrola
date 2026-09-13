"""
Duplicacao de modelos da biblioteca (Etapa 2).

O que estes testes protegem, em ordem de importancia:

  1. a ORIGEM nao muda em nada -- nem quando e oficial, nem quando esta
     travada; duplicar so le;
  2. a copia e INDEPENDENTE: alterar estruturas aninhadas dela nao alcanca
     a origem (copia profunda, nao rasa);
  3. a copia nasce comum e destravada, com linhagem e autor registrados;
  4. slugs nunca colidem nem sobrescrevem ninguem.
"""

import copy

import pytest
from django.core.exceptions import ValidationError

from apps.doctemplates.models import DocumentTemplate, DocumentType
from apps.doctemplates.services import biblioteca
from apps.doctemplates.services.duplicacao import duplicar_modelo, slug_unico

pytestmark = pytest.mark.django_db

A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}

LAYOUT = {
    "schema_version": 1,
    "page": {"width": 595.2756, "height": 841.8898, "unit": "pt", "origin": "top-left"},
    "elements": [
        {
            "id": "t1", "type": "text", "x": 72.0, "y": 100.0, "width": 200.0,
            "height": 14.0, "z_index": 1, "properties": {"content": "Título"},
        },
        {
            "id": "tb", "type": "table", "x": 50.0, "y": 200.0, "width": 400.0,
            "height": 60.0, "z_index": 2,
            "properties": {
                "columns": [{"width": 100, "align": "left"}, {"width": 300, "align": "left"}],
                "rows": [{"min_height": 20, "cells": [{"content": "a"}, {"content": "b"}]}],
            },
        },
    ],
}

SCHEMA = {
    "fields": [
        {"key": "nome", "type": "text", "required": True, "order": 1, "section": "s",
         "label": "Nome", "translations": {"fr": {"label": "Nom"}}},
        {"key": "data", "type": "date", "required": False, "order": 2, "section": "s",
         "label": "Data"},
    ]
}


@pytest.fixture
def tipo(db):
    return DocumentType.objects.create(code="contrato", name="Contrato", page=dict(A4))


@pytest.fixture
def origem(tipo):
    return DocumentTemplate.objects.create(
        type=tipo, name="Contrato base", slug="contrato-base", language="fr",
        description="Descrição original", field_schema=copy.deepcopy(SCHEMA),
        layout=copy.deepcopy(LAYOUT),
    )


def _retrato(modelo):
    """Todos os campos gravados, para comparar antes/depois."""
    return DocumentTemplate.objects.filter(pk=modelo.pk).values().first()


# ---------------------------------------------------------------------------
# 1. A copia nasce certa
# ---------------------------------------------------------------------------


class TestCopia:
    def test_duplicar_modelo_normal(self, origem, user):
        copia = duplicar_modelo(origem, "Minha Carta Convite", created_by=user)

        assert copia.pk and copia.pk != origem.pk
        assert copia.name == "Minha Carta Convite"
        assert copia.slug == "minha-carta-convite"

    def test_nasce_comum_destravada_e_ativa(self, origem):
        copia = duplicar_modelo(origem, "Cópia")

        assert copia.is_system is False
        assert copia.is_locked is False
        assert copia.is_active is True

    def test_linhagem_e_autor(self, origem, user):
        copia = duplicar_modelo(origem, "Cópia", created_by=user)

        assert copia.duplicated_from == origem
        assert copia.created_by == user
        assert list(origem.duplicates.all()) == [copia]

    def test_autor_e_opcional(self, origem):
        assert duplicar_modelo(origem, "Cópia").created_by is None

    def test_preserva_tipo_idioma_e_descricao(self, origem, tipo):
        copia = duplicar_modelo(origem, "Cópia")

        assert copia.type == tipo
        assert copia.language == "fr"
        assert copia.description == "Descrição original"

    def test_preserva_field_schema_e_layout(self, origem):
        copia = duplicar_modelo(origem, "Cópia")
        copia.refresh_from_db()

        assert copia.field_schema == SCHEMA
        assert copia.layout == LAYOUT

    def test_a_copia_e_editavel_estruturalmente(self, origem):
        """O sentido de duplicar: poder mexer no que na origem nao se pode."""
        copia = duplicar_modelo(origem, "Cópia")
        copia.layout["elements"][0]["x"] = 99.0
        copia.language = "nl"
        copia.save()
        copia.refresh_from_db()

        assert copia.layout["elements"][0]["x"] == 99.0
        assert copia.language == "nl"


# ---------------------------------------------------------------------------
# 2. Origens especiais: oficial, travada, copia de copia
# ---------------------------------------------------------------------------


class TestOrigens:
    def test_duplicar_modelo_do_sistema(self, db, user):
        biblioteca.semear()
        oficial = DocumentTemplate.objects.get(slug="carta-convite-fr")

        copia = duplicar_modelo(oficial, "Meu modelo FR", created_by=user)

        assert copia.is_system is False
        assert copia.duplicated_from == oficial
        assert copia.field_schema == oficial.field_schema
        assert copia.language == "fr"

    def test_duplicar_modelo_travado(self, origem):
        origem.is_locked = True
        origem.save()

        copia = duplicar_modelo(origem, "Destravada")

        assert copia.is_locked is False
        assert copia.layout == LAYOUT

    def test_duplicar_modelo_do_sistema_travado(self, db):
        biblioteca.semear()
        oficial = DocumentTemplate.objects.get(slug="carta-convite-pt")
        oficial.is_locked = True
        oficial.save()

        copia = duplicar_modelo(oficial, "Cópia do oficial travado")

        assert (copia.is_system, copia.is_locked) == (False, False)

    def test_duplicar_uma_copia(self, origem, user):
        primeira = duplicar_modelo(origem, "Primeira", created_by=user)
        segunda = duplicar_modelo(primeira, "Segunda", created_by=user)

        assert segunda.duplicated_from == primeira
        assert primeira.duplicated_from == origem
        assert segunda.layout == LAYOUT
        assert segunda.pk not in (primeira.pk, origem.pk)


# ---------------------------------------------------------------------------
# 3. Independencia: copia profunda de verdade
# ---------------------------------------------------------------------------


class TestIndependencia:
    def test_os_dicionarios_nao_sao_os_mesmos_objetos(self, origem):
        copia = duplicar_modelo(origem, "Cópia")

        assert copia.field_schema is not origem.field_schema
        assert copia.layout is not origem.layout
        # e nem por dentro:
        assert copia.layout["elements"] is not origem.layout["elements"]
        assert copia.field_schema["fields"] is not origem.field_schema["fields"]

    def test_alterar_campo_aninhado_da_copia_nao_altera_a_origem(self, origem):
        copia = duplicar_modelo(origem, "Cópia")

        copia.field_schema["fields"][0]["translations"]["fr"]["label"] = "MUDOU"
        copia.field_schema["fields"].append({"key": "extra"})
        copia.save()

        origem.refresh_from_db()
        assert origem.field_schema == SCHEMA
        assert origem.field_schema["fields"][0]["translations"]["fr"]["label"] == "Nom"

    def test_alterar_layout_aninhado_da_copia_nao_altera_a_origem(self, origem):
        copia = duplicar_modelo(origem, "Cópia")

        copia.layout["elements"][1]["properties"]["rows"][0]["cells"][0]["content"] = "X"
        copia.layout["elements"][0]["properties"]["content"] = "Outro"
        copia.layout["elements"].pop()
        copia.save()

        origem.refresh_from_db()
        assert origem.layout == LAYOUT

    def test_alterar_a_origem_depois_nao_alcanca_a_copia(self, origem):
        copia = duplicar_modelo(origem, "Cópia")

        origem.layout["elements"][0]["properties"]["content"] = "Alterado na origem"
        origem.description = "Nova descrição"
        origem.save()

        copia.refresh_from_db()
        assert copia.layout == LAYOUT
        assert copia.description == "Descrição original"

    def test_em_memoria_tambem_sao_independentes(self, origem):
        """Sem passar pelo banco: o objeto devolvido ja e uma copia profunda."""
        copia = duplicar_modelo(origem, "Cópia")

        copia.layout["elements"][0]["x"] = -1
        assert origem.layout["elements"][0]["x"] == 72.0


# ---------------------------------------------------------------------------
# 4. A origem nao muda em NADA
# ---------------------------------------------------------------------------


class TestOrigemImutavel:
    def test_todos_os_campos_da_origem_ficam_iguais(self, origem, user):
        antes = _retrato(origem)

        duplicar_modelo(origem, "Cópia", created_by=user)

        assert _retrato(origem) == antes

    def test_origem_oficial_travada_fica_igual(self, db, user):
        biblioteca.semear()
        oficial = DocumentTemplate.objects.get(slug="carta-convite-en")
        oficial.is_locked = True
        oficial.save()
        antes = _retrato(oficial)

        duplicar_modelo(oficial, "Cópia", created_by=user)

        assert _retrato(oficial) == antes
        assert oficial.is_system and oficial.is_locked

    def test_o_objeto_em_memoria_da_origem_nao_e_tocado(self, origem):
        atributos_antes = {
            k: copy.deepcopy(v) for k, v in vars(origem).items() if not k.startswith("_")
        }

        duplicar_modelo(origem, "Cópia")

        atributos_depois = {
            k: v for k, v in vars(origem).items() if not k.startswith("_")
        }
        assert atributos_depois == atributos_antes


# ---------------------------------------------------------------------------
# 5. Slugs
# ---------------------------------------------------------------------------


class TestSlug:
    def test_slug_deriva_do_nome(self, origem):
        assert duplicar_modelo(origem, "Minha Carta Convite").slug == "minha-carta-convite"

    def test_acentos_e_simbolos_sao_normalizados(self, origem):
        assert duplicar_modelo(origem, "Declaração — Ação nº 1").slug == "declaracao-acao-no-1"

    def test_colisao_gera_sufixo_numerico_crescente(self, origem):
        a = duplicar_modelo(origem, "Cópia")
        b = duplicar_modelo(origem, "Cópia")
        c = duplicar_modelo(origem, "Cópia")

        assert (a.slug, b.slug, c.slug) == ("copia", "copia-2", "copia-3")

    def test_colisao_com_slug_ja_existente_de_outro_modelo(self, origem):
        """O slug base ja e de alguem: a copia nao o toma."""
        copia = duplicar_modelo(origem, "Contrato base")

        assert copia.slug == "contrato-base-2"
        origem.refresh_from_db()
        assert origem.slug == "contrato-base"

    def test_o_primeiro_buraco_e_reaproveitado(self, origem, tipo):
        DocumentTemplate.objects.create(type=tipo, name="x", slug="copia", language="pt")
        DocumentTemplate.objects.create(type=tipo, name="y", slug="copia-3", language="pt")

        assert duplicar_modelo(origem, "Cópia").slug == "copia-2"

    def test_prefixo_parecido_nao_confunde(self, origem, tipo):
        """`copia-nova` existe; `Cópia` ainda pode virar `copia`."""
        DocumentTemplate.objects.create(type=tipo, name="z", slug="copia-nova", language="pt")

        assert duplicar_modelo(origem, "Cópia").slug == "copia"

    def test_nome_longo_cabe_no_campo_com_sufixo(self, origem):
        # Cabe no `name` (150) mas a slug passaria do `slug` (80): tem de
        # ser truncada, e ainda sobrar espaco para o sufixo "-2".
        nome = "Modelo " + "x" * 120
        a = duplicar_modelo(origem, nome)
        b = duplicar_modelo(origem, nome)

        limite = DocumentTemplate._meta.get_field("slug").max_length
        assert len(a.slug) <= limite and len(b.slug) <= limite
        assert a.slug != b.slug

    def test_slug_unico_sem_nome_devolve_vazio(self, db):
        assert slug_unico("") == ""
        assert slug_unico("!!!") == ""

    def test_multiplas_duplicacoes_nao_sobrescrevem_nenhuma_anterior(self, origem):
        copias = [duplicar_modelo(origem, "Repetida") for _ in range(5)]

        slugs = [c.slug for c in copias]
        assert len(set(slugs)) == 5
        assert DocumentTemplate.objects.filter(pk__in=[c.pk for c in copias]).count() == 5
        for copia in copias:
            copia.refresh_from_db()
            assert copia.name == "Repetida"


# ---------------------------------------------------------------------------
# 6. Validacao e transacao
# ---------------------------------------------------------------------------


class TestValidacao:
    @pytest.mark.parametrize("nome", ["", "   ", "!!!"])
    def test_nome_invalido_e_recusado_pela_validacao_do_modelo(self, origem, nome):
        antes = DocumentTemplate.objects.count()

        with pytest.raises(ValidationError):
            duplicar_modelo(origem, nome)

        assert DocumentTemplate.objects.count() == antes

    def test_nada_fica_gravado_quando_a_validacao_falha(self, origem):
        origem.layout = {"schema_version": 99}  # invalido, so em memoria
        antes = DocumentTemplate.objects.count()

        with pytest.raises(ValidationError):
            duplicar_modelo(origem, "Cópia")

        assert DocumentTemplate.objects.count() == antes
