"""Testes do modelo Letter: estrutura, propriedade e privacidade."""

import uuid as uuid_module

import pytest
from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.letters.models import Letter

pytestmark = pytest.mark.django_db


@pytest.fixture
def letter(user, published_version):
    return Letter.objects.create(
        user=user,
        template=published_version.template,
        template_version=published_version,
        language="fr",
        data={"convidado": "Maria Santos da Silva"},
        snapshot={"anfitriao": {"nome": user.full_name}},
    )


class TestLetterCriacao:
    def test_uuid_e_gerado_e_unico(self, letter):
        assert isinstance(letter.uuid, uuid_module.UUID)

        outro = Letter.objects.exclude(pk=letter.pk).first()
        assert outro is None or outro.uuid != letter.uuid

    def test_relacionamento_com_usuario(self, letter, user):
        assert letter.user == user
        assert letter in user.letters.all()

    def test_dados_preenchidos_ficam_em_jsonb(self, letter):
        letter.refresh_from_db()
        assert letter.data == {"convidado": "Maria Santos da Silva"}

    def test_snapshot_fica_em_jsonb_e_independente_dos_dados_atuais(self, letter, user):
        letter.refresh_from_db()
        assert letter.snapshot == {"anfitriao": {"nome": user.full_name}}

        # Mudar o perfil do usuario depois nao deve alterar o snapshot ja
        # gravado: e exatamente isso que garante a reproducao historica.
        user.full_name = "Nome Totalmente Diferente"
        user.save()
        letter.refresh_from_db()
        assert letter.snapshot == {"anfitriao": {"nome": "Claire Dubois"}}

    def test_template_e_derivado_da_template_version_quando_nao_informado(
        self, user, published_version
    ):
        letter = Letter.objects.create(
            user=user, template_version=published_version, language="fr"
        )

        assert letter.template_id == published_version.template_id

    def test_referencia_e_gerada_e_unica(self, letter, user, published_version):
        assert letter.reference.startswith("DSR-")

        outra = Letter.objects.create(
            user=user, template_version=published_version, language="fr"
        )
        assert outra.reference != letter.reference

    def test_status_padrao_e_rascunho(self, letter):
        assert letter.status == Letter.Status.DRAFT

    def test_estados_disponiveis(self):
        assert set(Letter.Status.values) == {"draft", "generated", "completed", "cancelled"}

    def test_created_at_e_updated_at_sao_preenchidos(self, letter):
        assert letter.created_at is not None
        assert letter.updated_at is not None


class TestLetterVinculoComVersao:
    def test_nao_pode_excluir_template_version_com_carta_historica(self, letter, published_version):
        with pytest.raises(ProtectedError):
            published_version.delete()

    def test_carta_permanece_vinculada_a_versao_exata(
        self, user, letter_template, draft_version
    ):
        from apps.doctemplates.models import TemplateVersion

        draft_version.publish()
        letter_v1 = Letter.objects.create(
            user=user, template_version=draft_version, language="fr"
        )

        v2 = draft_version.create_next_version()
        v2.field_schema = {"fields": ["novo_campo"]}
        v2.publish()

        letter_v1.refresh_from_db()
        assert letter_v1.template_version_id == draft_version.pk
        assert letter_v1.template_version.version_number == 1
        assert TemplateVersion.objects.get(pk=letter_v1.template_version_id).field_schema == {
            "fields": ["nome_convidado", "passaporte"]
        }


# ---------------------------------------------------------------------------
# Privacidade / ownership
# ---------------------------------------------------------------------------


class TestLetterPrivacidade:
    def test_usuario_a_nao_ve_carta_do_usuario_b(self, user, other_user, published_version):
        carta_de_a = Letter.objects.create(
            user=user, template_version=published_version, language="fr"
        )
        Letter.objects.create(user=other_user, template_version=published_version, language="en")

        visiveis_para_a = Letter.objects.visible_to(user)

        assert list(visiveis_para_a) == [carta_de_a]

    def test_usuario_b_nao_ve_carta_do_usuario_a(self, user, other_user, published_version):
        Letter.objects.create(user=user, template_version=published_version, language="fr")
        carta_de_b = Letter.objects.create(
            user=other_user, template_version=published_version, language="en"
        )

        visiveis_para_b = Letter.objects.visible_to(other_user)

        assert list(visiveis_para_b) == [carta_de_b]

    def test_usuario_anonimo_nao_ve_nenhuma_carta(self, letter):
        from django.contrib.auth.models import AnonymousUser

        assert list(Letter.objects.visible_to(AnonymousUser())) == []

    def test_staff_sem_permissao_nao_ve_cartas_de_outros(
        self, staff_user, user, published_version
    ):
        Letter.objects.create(user=user, template_version=published_version, language="fr")

        # is_staff sozinho nao concede acesso administrativo: e a
        # permissao granular que decide (ver secao de permissoes).
        assert list(Letter.objects.visible_to(staff_user)) == []

    def test_usuario_com_permissao_view_all_letters_ve_tudo(
        self, user, other_user, published_version, django_user_model
    ):
        gerente = django_user_model.objects.create_user(
            email="gerente@desenrola.be", password="senha-forte-123", full_name="Gerente Geral"
        )
        carta_a = Letter.objects.create(
            user=user, template_version=published_version, language="fr"
        )
        carta_b = Letter.objects.create(
            user=other_user, template_version=published_version, language="en"
        )

        grupo = Group.objects.create(name="Gerente")
        grupo.permissions.add(
            Permission.objects.get(content_type__app_label="letters", codename="view_all_letters")
        )
        gerente.groups.add(grupo)

        visiveis = set(Letter.objects.visible_to(gerente))
        assert visiveis == {carta_a, carta_b}

    def test_superusuario_ve_tudo_mesmo_sem_permissao_explicita(
        self, user, other_user, published_version, django_user_model
    ):
        superuser = django_user_model.objects.create_superuser(
            email="root@desenrola.be", password="senha-forte-123", full_name="Root"
        )
        carta_a = Letter.objects.create(
            user=user, template_version=published_version, language="fr"
        )
        carta_b = Letter.objects.create(
            user=other_user, template_version=published_version, language="en"
        )

        visiveis = set(Letter.objects.visible_to(superuser))
        assert visiveis == {carta_a, carta_b}


class TestLetterPermissaoDeclarada:
    def test_permissao_view_all_letters_existe(self):
        assert Permission.objects.filter(
            content_type__app_label="letters", codename="view_all_letters"
        ).exists()


class TestLetterUnicidade:
    def test_uuid_nao_pode_ser_duplicado(self, user, published_version, letter):
        duplicado = Letter(
            uuid=letter.uuid,
            user=user,
            template_version=published_version,
            language="fr",
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            duplicado.save()
