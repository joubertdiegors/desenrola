"""
Entrega as permissões de conteúdo a quem já administra.

POR QUE ESTA MIGRATION É NECESSÁRIA
-----------------------------------
A tela de Conteúdo do site passou a exigir `content.view_pagesection`
para ver e `change_pagesection` para gravar. Sem ninguém as tendo, o
item do menu ficaria invisível para todo mundo que não fosse
superusuário -- inclusive para quem administra o produto todos os dias.

`accounts.manage_users`, e não `core.access_backoffice`: quem distribui
permissões é o topo da escada administrativa, e é de lá que as demais
pessoas recebem esta. Mesma regra de `core.0002`.

POR QUE AS PERMISSÕES SÃO CRIADAS AQUI
--------------------------------------
O Django cria as permissões de um modelo no `post_migrate`, isto é,
DEPOIS de todas as migrations rodarem. Num banco novo elas ainda não
existem quando este código roda, e uma migration que só as procurasse
não acharia nada. Por isso são criadas explicitamente, com o mesmo
`codename` e o mesmo `name` que o Django geraria -- quando o
`post_migrate` chegar, vai encontrá-las prontas e não fará nada.
"""

from django.db import migrations

# Exatamente o que `django.contrib.auth.management.create_permissions`
# geraria a partir do `verbose_name` de `PageSection`.
PERMISSOES = (
    ("view_pagesection", "Can view seção de página"),
    ("change_pagesection", "Can change seção de página"),
)


def conceder_a_quem_ja_administra(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("accounts", "User")

    tipo, _criado = ContentType.objects.get_or_create(
        app_label="content", model="pagesection"
    )
    de_conteudo = [
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
        # `has_perm` de qualquer jeito.
        return

    for usuario in User.objects.filter(user_permissions=gerencia).distinct():
        usuario.user_permissions.add(*de_conteudo)


def revogar(apps, schema_editor):
    """Tira as duas de todo mundo; as permissões continuam existindo."""
    Permission = apps.get_model("auth", "Permission")
    for permissao in Permission.objects.filter(
        content_type__app_label="content",
        codename__in=[codename for codename, _nome in PERMISSOES],
    ):
        permissao.user_set.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0004_conteudo_da_home"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("accounts", "0004_user_birth_date_user_nationality"),
    ]

    operations = [
        migrations.RunPython(conceder_a_quem_ja_administra, revogar),
    ]
