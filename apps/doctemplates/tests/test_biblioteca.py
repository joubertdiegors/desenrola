"""
Biblioteca de modelos de documentos -- Etapa 1 da nova arquitetura.

Cobre os dois modelos novos (`DocumentType`, `DocumentTemplate`), as
regras de integridade em `save()`/`delete()` e a semeadura dos quatro
oficiais da Carta Convite.

A distincao que estes testes fixam, porque e facil de confundir:

  is_system -- o que o modelo E (oficial do Desenrola);
  is_locked -- o que se pode fazer com ele AGORA.

Um oficial nasce destravado e, mesmo assim, so aceita alteracoes
administrativas simples. Um comum travado nao aceita alteracao
estrutural. Um comum destravado aceita tudo.
"""

import copy

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.doctemplates.models import (
    DocumentTemplate,
    DocumentTemplateLockedError,
    DocumentType,
)
from apps.doctemplates.official_templates import CARTA_CONVITE_FIELD_SCHEMA
from apps.doctemplates.services import biblioteca

pytestmark = pytest.mark.django_db

A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}

LAYOUT_MINIMO = {
    "schema_version": 1,
    "page": {"width": 595.2756, "height": 841.8898, "unit": "pt", "origin": "top-left"},
    "elements": [],
}


@pytest.fixture
def tipo(db):
    return DocumentType.objects.create(
        code="contrato", name="Contrato", page=dict(A4), data_sources=["documento"]
    )


@pytest.fixture
def modelo(tipo):
    """Um modelo comum, editavel."""
    return DocumentTemplate.objects.create(
        type=tipo, name="Meu contrato", slug="meu-contrato", language="pt"
    )


@pytest.fixture
def modelo_travado(tipo):
    return DocumentTemplate.objects.create(
        type=tipo, name="Contrato fechado", slug="contrato-fechado", language="pt",
        is_locked=True, layout=copy.deepcopy(LAYOUT_MINIMO),
    )


@pytest.fixture
def modelo_sistema(tipo):
    return DocumentTemplate.objects.create(
        type=tipo, name="Contrato padrão", slug="contrato-padrao", language="pt",
        is_system=True, is_locked=False,
    )


def _salvar(modelo, **mudancas):
    for chave, valor in mudancas.items():
        setattr(modelo, chave, valor)
    modelo.save()
    modelo.refresh_from_db()
    return modelo


# ---------------------------------------------------------------------------
# DocumentType
# ---------------------------------------------------------------------------


class TestDocumentType:
    def test_criacao(self, tipo):
        assert tipo.pk
        assert tipo.is_active is True
        assert str(tipo) == "Contrato"

    def test_code_e_unico(self, tipo):
        with pytest.raises(IntegrityError):
            DocumentType.objects.create(code="contrato", name="Outro", page=dict(A4))

    def test_pagina_a4_em_pontos(self, tipo):
        assert tipo.page == {"width": 595.2756, "height": 841.8898, "unit": "pt"}

    def test_fontes_de_dados_sao_uma_lista(self, tipo):
        assert tipo.data_sources == ["documento"]

    def test_nao_pode_ser_apagado_com_modelos(self, tipo, modelo):
        """FK PROTECT: um tipo com modelos nao some por baixo deles."""
        with pytest.raises(ProtectedError):
            tipo.delete()


# ---------------------------------------------------------------------------
# DocumentTemplate -- criacao
# ---------------------------------------------------------------------------


class TestDocumentTemplateCriacao:
    def test_criacao_nasce_comum_destravado_e_ativo(self, modelo):
        assert modelo.is_system is False
        assert modelo.is_locked is False
        assert modelo.is_active is True
        assert modelo.field_schema == {}
        assert modelo.layout == {}

    def test_relacionamento_com_o_tipo(self, modelo, tipo):
        assert modelo.type == tipo
        assert list(tipo.templates.all()) == [modelo]

    def test_slug_e_unico(self, modelo, tipo):
        with pytest.raises(IntegrityError):
            DocumentTemplate.objects.create(
                type=tipo, name="Outro", slug="meu-contrato", language="fr"
            )

    @pytest.mark.parametrize("idioma", ["pt", "fr", "nl", "en"])
    def test_aceita_os_idiomas_do_site(self, tipo, idioma):
        m = DocumentTemplate.objects.create(
            type=tipo, name="x", slug=f"x-{idioma}", language=idioma
        )
        m.full_clean()

    def test_idioma_fora_da_lista_e_recusado_na_validacao(self, tipo):
        m = DocumentTemplate(type=tipo, name="x", slug="x-de", language="de")
        with pytest.raises(ValidationError):
            m.full_clean()

    def test_modelo_sistema_pode_estar_destravado(self, modelo_sistema):
        assert modelo_sistema.is_system is True
        assert modelo_sistema.is_locked is False

    def test_modelo_sistema_pode_estar_travado(self, tipo):
        m = DocumentTemplate.objects.create(
            type=tipo, name="y", slug="y", language="pt", is_system=True, is_locked=True
        )
        assert (m.is_system, m.is_locked) == (True, True)

    def test_duplicated_from_aceita_outro_modelo(self, modelo, tipo):
        copia = DocumentTemplate.objects.create(
            type=tipo, name="Cópia", slug="copia", language="pt", duplicated_from=modelo
        )
        assert copia.duplicated_from == modelo
        assert list(modelo.duplicates.all()) == [copia]

    def test_apagar_a_origem_nao_arrasta_a_copia(self, modelo, tipo):
        copia = DocumentTemplate.objects.create(
            type=tipo, name="Cópia", slug="copia", language="pt", duplicated_from=modelo
        )
        modelo.delete()
        copia.refresh_from_db()
        assert copia.duplicated_from is None

    def test_created_by_e_opcional_e_nao_arrasta(self, tipo, user):
        m = DocumentTemplate.objects.create(
            type=tipo, name="z", slug="z", language="pt", created_by=user
        )
        user.delete()
        m.refresh_from_db()
        assert m.created_by is None

    def test_clean_valida_os_dois_contratos(self, modelo):
        modelo.field_schema = {"fields": "não é lista"}
        with pytest.raises(ValidationError):
            modelo.full_clean()
        modelo.field_schema = {}
        modelo.layout = {"schema_version": 99}
        with pytest.raises(ValidationError):
            modelo.full_clean()


# ---------------------------------------------------------------------------
# Regras: modelo comum destravado
# ---------------------------------------------------------------------------


class TestModeloComumEditavel:
    def test_pode_alterar_tudo(self, modelo, tipo):
        outro_tipo = DocumentType.objects.create(code="declaracao", name="Declaração", page=A4)
        _salvar(
            modelo,
            name="Novo nome", slug="novo-slug", language="fr", type=outro_tipo,
            field_schema={"fields": []}, layout=copy.deepcopy(LAYOUT_MINIMO),
            description="d", is_active=False,
        )
        assert modelo.slug == "novo-slug"
        assert modelo.language == "fr"
        assert modelo.type == outro_tipo
        assert modelo.layout["elements"] == []

    def test_pode_ser_apagado(self, modelo):
        modelo.delete()
        assert not DocumentTemplate.objects.filter(slug="meu-contrato").exists()

    def test_pode_ser_travado_e_destravado(self, modelo):
        _salvar(modelo, is_locked=True)
        assert modelo.is_locked
        _salvar(modelo, is_locked=False)
        assert not modelo.is_locked


# ---------------------------------------------------------------------------
# Regras: modelo travado
# ---------------------------------------------------------------------------


class TestModeloTravado:
    @pytest.mark.parametrize(
        "campo, valor",
        [
            # Um elemento a mais: tem de DIFERIR do que a fixture gravou.
            ("layout", LAYOUT_MINIMO | {"elements": [{
                "id": "t1", "type": "text", "x": 1.0, "y": 1.0, "width": 10.0,
                "height": 5.0, "z_index": 1, "properties": {"content": "x"},
            }]}),
            ("field_schema", {"fields": []}),
            ("language", "fr"),
            ("slug", "outro"),
        ],
    )
    def test_nao_altera_estrutura(self, modelo_travado, campo, valor):
        setattr(modelo_travado, campo, valor)
        with pytest.raises(DocumentTemplateLockedError, match="travado"):
            modelo_travado.save()

    def test_nao_altera_o_tipo(self, modelo_travado):
        outro = DocumentType.objects.create(code="outro", name="Outro", page=A4)
        modelo_travado.type = outro
        with pytest.raises(DocumentTemplateLockedError):
            modelo_travado.save()

    def test_nao_pode_ser_apagado(self, modelo_travado):
        with pytest.raises(DocumentTemplateLockedError):
            modelo_travado.delete()
        assert DocumentTemplate.objects.filter(pk=modelo_travado.pk).exists()

    def test_aceita_o_administrativo_simples(self, modelo_travado):
        _salvar(modelo_travado, description="nova", is_active=False, name="Renomeado")
        assert (modelo_travado.description, modelo_travado.is_active) == ("nova", False)

    def test_pode_ser_destravado(self, modelo_travado):
        _salvar(modelo_travado, is_locked=False)
        assert modelo_travado.is_locked is False

    def test_a_regra_vale_pelo_estado_gravado(self, modelo_travado):
        """Destravar e mudar o layout na MESMA gravacao nao passa."""
        modelo_travado.is_locked = False
        modelo_travado.layout = copy.deepcopy(LAYOUT_MINIMO) | {"elements": []}
        modelo_travado.field_schema = {"fields": []}
        with pytest.raises(DocumentTemplateLockedError):
            modelo_travado.save()

    def test_o_banco_fica_intacto_depois_da_recusa(self, modelo_travado):
        antes = copy.deepcopy(modelo_travado.layout)
        modelo_travado.layout = {}
        with pytest.raises(DocumentTemplateLockedError):
            modelo_travado.save()
        modelo_travado.refresh_from_db()
        assert modelo_travado.layout == antes


# ---------------------------------------------------------------------------
# Regras: modelo do sistema (mesmo destravado)
# ---------------------------------------------------------------------------


class TestModeloDoSistema:
    @pytest.mark.parametrize(
        "campo, valor",
        [
            ("layout", copy.deepcopy(LAYOUT_MINIMO)),
            ("field_schema", {"fields": []}),
            ("language", "fr"),
            ("slug", "outro"),
            ("name", "Outro nome"),
            ("is_system", False),
        ],
    )
    def test_destravado_ainda_recusa_alteracao_estrutural(self, modelo_sistema, campo, valor):
        assert modelo_sistema.is_locked is False
        setattr(modelo_sistema, campo, valor)
        with pytest.raises(DocumentTemplateLockedError, match="sistema"):
            modelo_sistema.save()

    def test_nao_altera_o_tipo(self, modelo_sistema):
        outro = DocumentType.objects.create(code="outro", name="Outro", page=A4)
        modelo_sistema.type = outro
        with pytest.raises(DocumentTemplateLockedError):
            modelo_sistema.save()

    def test_aceita_description_e_is_active(self, modelo_sistema):
        _salvar(modelo_sistema, description="Aprovado em revisão", is_active=False)
        assert modelo_sistema.description == "Aprovado em revisão"
        assert modelo_sistema.is_active is False

    def test_pode_ser_travado_pelo_administrador(self, modelo_sistema):
        _salvar(modelo_sistema, is_locked=True)
        assert modelo_sistema.is_locked is True

    def test_nao_pode_ser_apagado(self, modelo_sistema):
        with pytest.raises(DocumentTemplateLockedError, match="sistema"):
            modelo_sistema.delete()


# ---------------------------------------------------------------------------
# Semeadura dos quatro oficiais
# ---------------------------------------------------------------------------


class TestSemeaduraCartaConvite:
    """A migration 0010 ja rodou no banco de teste: os quatro estao la."""

    SLUGS = ["carta-convite-fr", "carta-convite-nl", "carta-convite-en", "carta-convite-pt"]

    def test_o_tipo_carta_convite_existe_em_a4(self):
        tipo = DocumentType.objects.get(code="carta-convite")
        assert tipo.name == "Carta Convite"
        assert tipo.page == A4
        assert tipo.data_sources == ["documento", "convidado", "anfitriao", "calculado"]
        assert tipo.is_active

    def test_existem_exatamente_quatro_oficiais(self):
        oficiais = DocumentTemplate.objects.filter(type__code="carta-convite", is_system=True)
        assert oficiais.count() == 4
        assert sorted(oficiais.values_list("slug", flat=True)) == sorted(self.SLUGS)

    @pytest.mark.parametrize(
        "slug, idioma, nome",
        [
            ("carta-convite-fr", "fr", "Carta Convite — Français"),
            ("carta-convite-nl", "nl", "Carta Convite — Nederlands"),
            ("carta-convite-en", "en", "Carta Convite — English"),
            ("carta-convite-pt", "pt", "Carta Convite — Português"),
        ],
    )
    def test_cada_oficial(self, slug, idioma, nome):
        m = DocumentTemplate.objects.get(slug=slug)
        assert m.language == idioma
        assert m.name == nome
        assert m.is_system is True
        assert m.is_locked is False
        assert m.is_active is True
        assert m.layout == {}
        assert m.field_schema == CARTA_CONVITE_FIELD_SCHEMA
        assert m.duplicated_from is None
        assert m.created_by is None

    def test_o_schema_e_o_mesmo_da_versao_publicada_antiga(self):
        """Nenhum conteudo novo: e exatamente o schema vigente do legado."""
        from apps.doctemplates.models import LetterTemplate
        from apps.doctemplates.official_templates import official_slug

        for idioma in ("fr", "nl", "en", "pt"):
            novo = DocumentTemplate.objects.get(slug=biblioteca.slug_oficial(idioma))
            antigo = LetterTemplate.objects.get(slug=official_slug(idioma)).published_version
            assert novo.field_schema == antigo.field_schema

    def test_executar_de_novo_nao_duplica(self):
        antes = DocumentTemplate.objects.count()
        biblioteca.semear()
        biblioteca.semear()
        assert DocumentTemplate.objects.count() == antes
        assert DocumentType.objects.filter(code="carta-convite").count() == 1

    def test_executar_de_novo_nao_desfaz_o_que_o_administrador_fez(self):
        m = DocumentTemplate.objects.get(slug="carta-convite-fr")
        _salvar(m, description="Aprovado", is_locked=True)

        biblioteca.semear()

        m.refresh_from_db()
        assert m.description == "Aprovado"
        assert m.is_locked is True

    def test_o_schema_semeado_nao_compartilha_memoria_com_o_modulo(self):
        m = DocumentTemplate.objects.get(slug="carta-convite-en")
        m.field_schema["fields"].append({"key": "intruso"})
        assert not any(f.get("key") == "intruso" for f in CARTA_CONVITE_FIELD_SCHEMA["fields"])

    def test_slug_oficial_recusa_idioma_desconhecido(self):
        with pytest.raises(ValueError):
            biblioteca.slug_oficial("de")

    def test_o_legado_continua_intocado(self):
        from apps.doctemplates.models import LetterTemplate, TemplateVersion

        assert LetterTemplate.objects.count() == 4
        assert TemplateVersion.objects.filter(status="published").count() == 4
