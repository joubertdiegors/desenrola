"""Testes do modelo de usuario customizado."""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

User = get_user_model()


@pytest.mark.django_db
class TestUserManager:
    def test_cria_usuario_comum(self):
        user = User.objects.create_user(
            email="ana@exemplo.be",
            password="senha-forte-123",
            full_name="Ana Souza",
        )

        assert user.email == "ana@exemplo.be"
        assert user.full_name == "Ana Souza"
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.check_password("senha-forte-123")

    def test_cria_superusuario(self):
        admin = User.objects.create_superuser(
            email="admin@exemplo.be",
            password="senha-forte-123",
            full_name="Admin Geral",
        )

        assert admin.is_staff is True
        assert admin.is_superuser is True

    def test_email_e_obrigatorio(self):
        with pytest.raises(ValueError):
            User.objects.create_user(email="", password="x", full_name="Sem Email")

    def test_email_e_normalizado(self):
        user = User.objects.create_user(
            email="Maria@EXEMPLO.BE",
            password="senha-forte-123",
            full_name="Maria Lima",
        )

        # O Django normaliza apenas o dominio; a parte local preserva o caso.
        assert user.email == "Maria@exemplo.be"

    def test_email_e_unico(self):
        User.objects.create_user(
            email="dup@exemplo.be", password="senha-forte-123", full_name="Um"
        )

        with pytest.raises(IntegrityError):
            User.objects.create_user(
                email="dup@exemplo.be", password="senha-forte-123", full_name="Dois"
            )

    def test_superusuario_exige_flags(self):
        with pytest.raises(ValueError):
            User.objects.create_superuser(
                email="x@exemplo.be",
                password="senha-forte-123",
                full_name="X",
                is_staff=False,
            )


@pytest.mark.django_db
class TestUser:
    def test_login_e_por_email(self):
        assert User.USERNAME_FIELD == "email"

    def test_campos_opcionais_aceitam_vazio(self):
        """Telefone e endereco sao opcionais, conforme os requisitos."""
        user = User.objects.create_user(
            email="opcional@exemplo.be",
            password="senha-forte-123",
            full_name="Sem Extras",
        )
        user.full_clean()  # nao deve levantar ValidationError

        assert user.phone == ""
        assert user.address_line1 == ""
        assert user.country == ""

    def test_str_retorna_email(self):
        user = User(email="str@exemplo.be", full_name="Teste Str")
        assert str(user) == "str@exemplo.be"

    def test_get_short_name(self):
        user = User(email="curto@exemplo.be", full_name="Joao Pedro Silva")
        assert user.get_short_name() == "Joao"


@pytest.mark.django_db
class TestUserPermissoes:
    def test_permissao_manage_users_existe(self):
        from django.contrib.auth.models import Permission

        assert Permission.objects.filter(
            content_type__app_label="accounts", codename="manage_users"
        ).exists()

    def test_usuario_comum_nao_tem_a_permissao_por_padrao(self):
        user = User.objects.create_user(
            email="comum@exemplo.be", password="senha-forte-123", full_name="Usuario Comum"
        )
        assert not user.has_perm("accounts.manage_users")

    def test_usuario_com_grupo_ganha_a_permissao(self):
        from django.contrib.auth.models import Group, Permission

        user = User.objects.create_user(
            email="gerente@desenrola.be", password="senha-forte-123", full_name="Gerente"
        )
        grupo = Group.objects.create(name="Gerente de usuários")
        grupo.permissions.add(
            Permission.objects.get(content_type__app_label="accounts", codename="manage_users")
        )
        user.groups.add(grupo)

        assert user.has_perm("accounts.manage_users")

    def test_superusuario_tem_a_permissao_automaticamente(self):
        admin = User.objects.create_superuser(
            email="root2@desenrola.be", password="senha-forte-123", full_name="Root"
        )
        assert admin.has_perm("accounts.manage_users")
