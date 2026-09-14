"""
Cria a permissão `core.access_backoffice`.

O modelo que a carrega (`core.BackofficeAccess`) é `managed = False`:
nenhuma tabela é criada, só a linha de `auth.Permission` -- ver o
docstring do modelo para o porquê.

QUEM JÁ ERA STAFF NÃO PERDE ACESSO
----------------------------------
Até aqui a porta do Backoffice era `is_staff`. Quem já tinha essa flag
recebe a permissão nova, para a atualização não trancar ninguém para
fora. Daqui em diante `is_staff` não abre mais nada sozinho: quem
entra é quem tem a permissão (ou é superusuário, que tem todas).
"""

from django.db import migrations, models


def conceder_a_quem_ja_era_staff(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    User = apps.get_model("accounts", "User")

    # `post_migrate` é quem cria as permissões, e ele só roda no fim do
    # `migrate` -- portanto DEPOIS desta função. Criar aqui pelo mesmo
    # caminho (get_or_create sobre o content type do modelo) deixa as
    # duas execuções idempotentes entre si.
    tipo, _criado = ContentType.objects.get_or_create(
        app_label="core", model="backofficeaccess"
    )
    permissao, _criada = Permission.objects.get_or_create(
        codename="access_backoffice",
        content_type=tipo,
        defaults={"name": "Pode acessar o Backoffice"},
    )

    for usuario in User.objects.filter(is_staff=True):
        usuario.user_permissions.add(permissao)


def revogar(apps, schema_editor):
    """Tira a permissão de todo mundo; a linha em si some com o modelo."""
    Permission = apps.get_model("auth", "Permission")
    permissao = Permission.objects.filter(
        codename="access_backoffice", content_type__app_label="core"
    ).first()
    if permissao is not None:
        permissao.user_permissions.clear()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BackofficeAccess",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
            ],
            options={
                "verbose_name": "acesso ao Backoffice",
                "verbose_name_plural": "acesso ao Backoffice",
                "permissions": [("access_backoffice", "Pode acessar o Backoffice")],
                "managed": False,
                "default_permissions": (),
            },
        ),
        migrations.RunPython(conceder_a_quem_ja_era_staff, revogar),
    ]
