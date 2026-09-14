"""
Concede as permissões de modelos a quem já administrava.

POR QUE ESTA MIGRATION É NECESSÁRIA
-----------------------------------
A biblioteca de modelos passou a exigir
`doctemplates.view_documenttemplate` para ver e
`change_documenttemplate` para administrar. Até aqui bastava
`core.access_backoffice`: quem já entrava na biblioteca perderia o
acesso a uma tela que usava, na simples aplicação da atualização.

Nenhuma permissão é CRIADA aqui -- as duas são as que o Django gera
sozinho para `DocumentTemplate`, e já existem. Esta migration só as
ATRIBUI a quem tem `core.access_backoffice`, exatamente como
`core.0001` fez com quem era `is_staff`.

Daqui em diante a concessão é pela tela de usuários do Backoffice.
"""

from django.db import migrations


def conceder_a_quem_ja_administra(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("accounts", "User")

    de_modelos = list(
        Permission.objects.filter(
            content_type__app_label="doctemplates",
            codename__in=("view_documenttemplate", "change_documenttemplate"),
        )
    )
    if not de_modelos:
        # `post_migrate` cria as permissões no fim do `migrate`; num banco
        # novo elas ainda não existem aqui, e também não há usuário nenhum
        # para receber. Nada a fazer.
        return

    do_backoffice = Permission.objects.filter(
        content_type__app_label="core", codename="access_backoffice"
    ).first()
    if do_backoffice is None:
        return

    for usuario in User.objects.filter(user_permissions=do_backoffice).distinct():
        usuario.user_permissions.add(*de_modelos)


def revogar(apps, schema_editor):
    """Tira as duas de todo mundo; as permissões em si continuam existindo."""
    Permission = apps.get_model("auth", "Permission")
    for permissao in Permission.objects.filter(
        content_type__app_label="doctemplates",
        codename__in=("view_documenttemplate", "change_documenttemplate"),
    ):
        permissao.user_set.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("doctemplates", "0015_remove_arquitetura_de_versionamento"),
        ("core", "0001_permissao_de_backoffice"),
        ("accounts", "0004_user_birth_date_user_nationality"),
    ]

    operations = [
        migrations.RunPython(conceder_a_quem_ja_administra, revogar),
    ]
