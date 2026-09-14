"""
Cria a configuração de envio de e-mail e a entrega a quem já administra.

POR QUE HÁ UM `RunPython` AQUI
------------------------------
`core.EmailSettings` nasce com duas permissões (`view` e `change`), e
sem ninguém as tendo a tela nova seria invisível para todo mundo que
não fosse superusuário -- inclusive para quem administra o produto
todos os dias. Quem administra os administradores (`accounts.manage_users`)
recebe as duas na atualização; daí em diante a concessão é pela tela de
usuários do Backoffice, como qualquer outra.

`manage_users`, e não `core.access_backoffice`: entrar no Backoffice é
uma coisa; guardar a senha de um servidor de e-mail é o degrau mais
alto desta área, e não deve vir junto com a porta de entrada.

POR QUE AS PERMISSÕES SÃO CRIADAS AQUI
--------------------------------------
O Django cria as permissões de um modelo no `post_migrate`, isto é,
DEPOIS de todas as migrations rodarem. Uma migration que só as
procurasse não acharia nada -- nem num banco novo, nem num que já
existe. Por isso elas são criadas explicitamente, com o mesmo
`codename` e o mesmo `name` que o Django geraria: quando o
`post_migrate` chegar, vai encontrá-las prontas e não fará nada.
"""

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Exatamente o que `django.contrib.auth.management.create_permissions`
# geraria a partir do `verbose_name` do modelo. Diferente daqui, ficaria
# uma permissão com nome estranho na tela do Django Admin.
PERMISSOES = (
    ("view_emailsettings", "Can view configuração de e-mail"),
    ("change_emailsettings", "Can change configuração de e-mail"),
)


def conceder_a_quem_ja_administra(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("accounts", "User")

    tipo, _criado = ContentType.objects.get_or_create(
        app_label="core", model="emailsettings"
    )
    de_email = [
        Permission.objects.get_or_create(
            content_type=tipo, codename=codename, defaults={"name": nome}
        )[0]
        for codename, nome in PERMISSOES
    ]

    gerencia = Permission.objects.filter(
        content_type__app_label="accounts", codename="manage_users"
    ).first()
    if gerencia is None:
        # Banco novo: ninguém para receber. O superusuário passa por
        # `has_perm` de qualquer jeito e configura o e-mail no primeiro
        # acesso.
        return

    for usuario in User.objects.filter(user_permissions=gerencia).distinct():
        usuario.user_permissions.add(*de_email)


def revogar(apps, schema_editor):
    """Tira as duas de todo mundo. As permissões somem junto com a tabela."""
    Permission = apps.get_model("auth", "Permission")
    for permissao in Permission.objects.filter(
        content_type__app_label="core",
        codename__in=[codename for codename, _nome in PERMISSOES],
    ):
        permissao.user_set.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_permissao_de_backoffice"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="criado em"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="atualizado em"),
                ),
                (
                    "security",
                    models.CharField(
                        choices=[
                            ("nenhuma", "Nenhuma — sem criptografia"),
                            ("tls", "STARTTLS — normalmente porta 587"),
                            ("ssl", "SSL/TLS direto — normalmente porta 465"),
                        ],
                        default="tls",
                        max_length=8,
                        verbose_name="segurança da conexão",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Desligado, as mensagens seguem para o destino de "
                            "reserva do ambiente."
                        ),
                        verbose_name="envio ativo",
                    ),
                ),
                (
                    "host",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="servidor SMTP"
                    ),
                ),
                (
                    "port",
                    models.PositiveIntegerField(
                        default=587,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(65535),
                        ],
                        verbose_name="porta",
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="usuário"
                    ),
                ),
                (
                    "password_encrypted",
                    models.TextField(
                        blank=True, editable=False, verbose_name="senha (cifrada)"
                    ),
                ),
                (
                    "from_email",
                    models.EmailField(
                        blank=True, max_length=254, verbose_name="remetente"
                    ),
                ),
                (
                    "from_name",
                    models.CharField(
                        blank=True, max_length=150, verbose_name="nome do remetente"
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="alterada por",
                    ),
                ),
            ],
            options={
                "verbose_name": "configuração de e-mail",
                "verbose_name_plural": "configuração de e-mail",
                "default_permissions": ("view", "change"),
            },
        ),
        migrations.RunPython(conceder_a_quem_ja_administra, revogar),
    ]
