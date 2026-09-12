"""Testes de LetterTemplate e TemplateVersion."""

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.doctemplates.models import LetterTemplate, TemplateVersion, TemplateVersionImmutableError
from apps.doctemplates.schema import FIELD_TYPE_CHOICES

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# LetterTemplate
# ---------------------------------------------------------------------------


class TestLetterTemplate:
    def test_criacao(self, letter_template):
        assert letter_template.name == "Carta Convite — curta duração"
        assert letter_template.language == "fr"
        assert letter_template.is_active is True

    def test_identificador_e_unico(self, letter_template):
        with pytest.raises(IntegrityError), transaction.atomic():
            LetterTemplate.objects.create(
                name="Outro nome",
                slug=letter_template.slug,
                language="en",
            )

    def test_idioma_usa_os_quatro_idiomas_do_site(self):
        for code in ("pt", "fr", "nl", "en"):
            template = LetterTemplate.objects.create(
                name=f"Carta {code}", slug=f"carta-{code}", language=code
            )
            assert template.language == code

    def test_pode_ficar_inativo(self, letter_template):
        letter_template.is_active = False
        letter_template.save()
        letter_template.refresh_from_db()
        assert letter_template.is_active is False

    def test_sem_versao_publicada_retorna_none(self, letter_template):
        assert letter_template.published_version is None

    def test_published_version_pega_a_mais_recente_publicada(self, letter_template):
        v1 = TemplateVersion.objects.create(template=letter_template, version_number=1)
        v1.publish()
        v2 = v1.create_next_version()
        v2.publish()

        assert letter_template.published_version == v2


# ---------------------------------------------------------------------------
# TemplateVersion
# ---------------------------------------------------------------------------


class TestTemplateVersionCriacao:
    def test_criacao_em_rascunho(self, draft_version):
        assert draft_version.status == TemplateVersion.Status.DRAFT
        assert draft_version.version_number == 1
        assert draft_version.published_at is None

    def test_relacionamento_com_template(self, draft_version, letter_template):
        assert draft_version.template == letter_template
        assert draft_version in letter_template.versions.all()

    def test_numero_de_versao_e_unico_por_template(self, letter_template, draft_version):
        with pytest.raises(IntegrityError), transaction.atomic():
            TemplateVersion.objects.create(template=letter_template, version_number=1)

    def test_templates_diferentes_podem_ter_a_mesma_numeracao(self, draft_version):
        outro_template = LetterTemplate.objects.create(
            name="Outra carta", slug="outra-carta", language="en"
        )
        outra_versao = TemplateVersion.objects.create(template=outro_template, version_number=1)

        assert outra_versao.version_number == draft_version.version_number == 1


class TestTemplateVersionPublicacao:
    def test_publicar_marca_status_e_data(self, draft_version):
        assert draft_version.published_at is None

        draft_version.publish()

        assert draft_version.status == TemplateVersion.Status.PUBLISHED
        assert draft_version.published_at is not None

    def test_nao_pode_publicar_versao_que_ja_nao_esta_em_rascunho(self, published_version):
        with pytest.raises(TemplateVersionImmutableError):
            published_version.publish()

    def test_criar_proxima_versao_a_partir_de_uma_anterior(self, published_version):
        nova = published_version.create_next_version()

        assert nova.version_number == published_version.version_number + 1
        assert nova.status == TemplateVersion.Status.DRAFT
        assert nova.field_schema == published_version.field_schema
        # Copia independente: mudar a nova nao deve afetar a original.
        nova.field_schema["fields"].append("novo_campo")
        assert "novo_campo" not in published_version.field_schema["fields"]


class TestTemplateVersionImutabilidade:
    def test_versao_publicada_nao_aceita_mudanca_no_schema(self, published_version):
        published_version.field_schema = {"fields": ["outro_campo"]}

        with pytest.raises(TemplateVersionImmutableError):
            published_version.save()

    def test_versao_publicada_nao_aceita_mudanca_no_snapshot(self, published_version):
        published_version.snapshot = {"algo": "novo"}

        with pytest.raises(TemplateVersionImmutableError):
            published_version.save()

    def test_versao_publicada_nao_aceita_trocar_de_template(self, published_version):
        outro_template = LetterTemplate.objects.create(
            name="Outra carta", slug="outra-carta-2", language="en"
        )
        published_version.template = outro_template

        with pytest.raises(TemplateVersionImmutableError):
            published_version.save()

    def test_versao_publicada_aceita_mudar_apenas_o_status(self, published_version):
        """Desativar uma versao publicada e uma transicao de ciclo de vida,
        nao uma alteracao estrutural — deve continuar permitida."""
        published_version.status = TemplateVersion.Status.INACTIVE

        published_version.save()
        published_version.refresh_from_db()

        assert published_version.status == TemplateVersion.Status.INACTIVE
        # O schema gravado continua o mesmo de quando foi publicada.
        assert published_version.field_schema == {"fields": ["nome_convidado", "passaporte"]}

    def test_versao_publicada_nao_pode_ser_excluida(self, published_version):
        with pytest.raises(TemplateVersionImmutableError):
            published_version.delete()

        assert TemplateVersion.objects.filter(pk=published_version.pk).exists()

    def test_versao_em_rascunho_pode_ser_excluida(self, draft_version):
        pk = draft_version.pk
        draft_version.delete()

        assert not TemplateVersion.objects.filter(pk=pk).exists()


class TestTemplateVersionPreservacaoHistorica:
    def test_nao_pode_excluir_versao_usada_por_carta(self, published_version, user):
        from django.db.models import ProtectedError

        from apps.letters.models import Letter

        Letter.objects.create(
            user=user,
            template=published_version.template,
            template_version=published_version,
            language="fr",
        )

        with pytest.raises(ProtectedError):
            published_version.delete()

        # A carta continua vinculada a versao exata usada na geracao.
        letter = Letter.objects.get(user=user)
        assert letter.template_version_id == published_version.pk


# ---------------------------------------------------------------------------
# Permissoes
# ---------------------------------------------------------------------------


def test_permissao_publish_templateversion_existe():
    assert Permission.objects.filter(
        content_type__app_label="doctemplates",
        codename="publish_templateversion",
    ).exists()


def test_usuario_com_grupo_ganha_a_permissao(user):
    from django.contrib.auth.models import Group

    grupo = Group.objects.create(name="Gerente de modelos")
    permissao = Permission.objects.get(
        content_type__app_label="doctemplates", codename="publish_templateversion"
    )
    grupo.permissions.add(permissao)
    user.groups.add(grupo)

    assert user.has_perm("doctemplates.publish_templateversion")


# ---------------------------------------------------------------------------
# Contrato do field_schema (secao 3 do pedido: campos administraveis, sem
# ficar hardcoded no HTML). A validacao roda em clean()/full_clean(), nao
# em save() — dados antigos (ex.: a fixture `draft_version`, que usa uma
# lista simples de nomes) continuam gravando normalmente.
# ---------------------------------------------------------------------------


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

    def test_schema_vazio_e_valido(self, letter_template):
        letter_template.default_field_schema = {}
        letter_template.full_clean()

    def test_schema_no_formato_documentado_e_valido(self, draft_version):
        draft_version.field_schema = self.VALIDO
        draft_version.full_clean()

    def test_schema_que_nao_e_um_objeto_e_invalido(self, draft_version):
        draft_version.field_schema = ["nome_convidado"]
        with pytest.raises(ValidationError):
            draft_version.full_clean()

    def test_campo_sem_key_e_invalido(self, draft_version):
        draft_version.field_schema = {"fields": [{"type": "text"}]}
        with pytest.raises(ValidationError):
            draft_version.full_clean()

    def test_chave_duplicada_e_invalida(self, draft_version):
        draft_version.field_schema = {
            "fields": [
                {"key": "nome", "type": "text"},
                {"key": "nome", "type": "email"},
            ]
        }
        with pytest.raises(ValidationError):
            draft_version.full_clean()

    def test_tipo_invalido_e_recusado(self, draft_version):
        draft_version.field_schema = {"fields": [{"key": "nome", "type": "url"}]}
        with pytest.raises(ValidationError):
            draft_version.full_clean()

    @pytest.mark.parametrize("tipo", list(FIELD_TYPE_CHOICES))
    def test_todos_os_tipos_previstos_sao_aceitos(self, draft_version, tipo):
        field = {"key": "campo", "type": tipo}
        if tipo in ("select", "radio"):
            field["options"] = ["a", "b"]
        draft_version.field_schema = {"fields": [field]}
        draft_version.full_clean()

    def test_select_sem_options_e_invalido(self, draft_version):
        draft_version.field_schema = {"fields": [{"key": "pais", "type": "select"}]}
        with pytest.raises(ValidationError):
            draft_version.full_clean()

    def test_radio_sem_options_e_invalido(self, draft_version):
        draft_version.field_schema = {"fields": [{"key": "sexo", "type": "radio"}]}
        with pytest.raises(ValidationError):
            draft_version.full_clean()

    def test_lettertemplate_tambem_valida_o_default_field_schema(self, letter_template):
        letter_template.default_field_schema = {"fields": [{"key": "x", "type": "invalido"}]}
        with pytest.raises(ValidationError):
            letter_template.full_clean()
