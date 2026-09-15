"""
Entrega as permissões de parceiros a quem já administra.

NÃO HÁ ALTERAÇÃO DE MODELO AQUI
-------------------------------
Nenhuma coluna nasce, muda ou some: `Partner` já tinha todos os campos
que a nova tela edita, e a permissão `delete` entrou pelo
`AlterModelOptions` da migration anterior. Esta é migration de DADOS --
existe só para distribuir as permissões.

AS PERMISSÕES TAMBÉM NÃO SÃO NOVAS
----------------------------------
São as quatro que o Django gera para o modelo e que a administração do
Django já cobrava neste cadastro. O que mudou é que agora existe uma
tela do PRODUTO que as cobra -- e sem esta migration o item "Parceiros"
abriria para quem administra, mas cadastrar, editar e remover
recusariam para todo mundo que não fosse superusuário.

`accounts.manage_users`, e não `core.access_backoffice`: quem distribui
permissões é o topo da escada administrativa, e é de lá que as demais
pessoas recebem estas. Mesma regra de `content.0005`, `content.0006` e
`letters.0006`.

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
# gera a partir do `verbose_name` de `Partner` ("parceiro").
PERMISSOES = (
    ("view_partner", "Can view parceiro"),
    ("add_partner", "Can add parceiro"),
    ("change_partner", "Can change parceiro"),
    ("delete_partner", "Can delete parceiro"),
)


def conceder_a_quem_ja_administra(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("accounts", "User")

    tipo, _criado = ContentType.objects.get_or_create(app_label="content", model="partner")
    criadas = [
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
        usuario.user_permissions.add(*criadas)


def revogar(apps, schema_editor):
    """Tira as permissões de todo mundo; elas próprias continuam existindo."""
    Permission = apps.get_model("auth", "Permission")
    for permissao in Permission.objects.filter(
        content_type__app_label="content",
        codename__in=[codename for codename, _nome in PERMISSOES],
    ):
        permissao.user_set.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0008_central_de_conteudo"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("accounts", "0004_user_birth_date_user_nationality"),
    ]

    operations = [
        migrations.RunPython(conceder_a_quem_ja_administra, revogar),
    ]
