"""
Entrega a permissão de configurações do site a quem já administra.

NÃO HÁ ALTERAÇÃO DE MODELO AQUI
-------------------------------
Nenhuma coluna nasce, muda ou some nesta etapa: a tela de Sistema
administra campos que `SiteSettings` já tinha desde a primeira migration
do app (`site_name`, `contact_email`, `contact_phone`, `contact_address`,
`social_links`). Esta migration existe só para DISTRIBUIR a permissão --
é migration de dados, não de esquema.

A PERMISSÃO TAMBÉM NÃO É NOVA
-----------------------------
`content.change_sitesettings` é a que o Django gera para o modelo e que
a administração do Django já cobrava neste mesmo cadastro. A tela de
Sistema passa a cobrá-la também. Sem esta migration, o item do menu
abriria para quem administra, mas o botão de salvar recusaria para todo
mundo que não fosse superusuário -- inclusive para quem cuida do produto
todos os dias.

`accounts.manage_users`, e não `core.access_backoffice`: quem distribui
permissões é o topo da escada administrativa, e é de lá que as demais
pessoas recebem esta. Mesma regra de `content.0005` e `letters.0006`.

POR QUE A PERMISSÃO É CRIADA AQUI
---------------------------------
O Django cria as permissões de um modelo no `post_migrate`, isto é,
DEPOIS de todas as migrations rodarem. Num banco novo ela ainda não
existe quando este código roda, e uma migration que só a procurasse não
acharia nada. Por isso é criada explicitamente, com o mesmo `codename` e
o mesmo `name` que o Django geraria -- quando o `post_migrate` chegar,
vai encontrá-la pronta e não fará nada.
"""

from django.db import migrations

CODENAME = "change_sitesettings"
# Exatamente o que `django.contrib.auth.management.create_permissions`
# gera a partir do `verbose_name` de `SiteSettings`.
NOME_DA_PERMISSAO = "Can change configurações do site"


def conceder_a_quem_ja_administra(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("accounts", "User")

    tipo, _criado = ContentType.objects.get_or_create(
        app_label="content", model="sitesettings"
    )
    permissao, _criada = Permission.objects.get_or_create(
        content_type=tipo, codename=CODENAME, defaults={"name": NOME_DA_PERMISSAO}
    )

    gerencia = Permission.objects.filter(
        content_type__app_label="accounts", codename="manage_users"
    ).first()
    if gerencia is None:
        # Banco novo: ninguém para receber. O superusuário passa por
        # `has_perm` de qualquer jeito.
        return

    for usuario in User.objects.filter(user_permissions=gerencia).distinct():
        usuario.user_permissions.add(permissao)


def revogar(apps, schema_editor):
    """Tira a permissão de todo mundo; ela própria continua existindo."""
    Permission = apps.get_model("auth", "Permission")
    for permissao in Permission.objects.filter(
        content_type__app_label="content", codename=CODENAME
    ):
        permissao.user_set.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0005_permissoes_de_conteudo"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("accounts", "0004_user_birth_date_user_nationality"),
    ]

    operations = [
        migrations.RunPython(conceder_a_quem_ja_administra, revogar),
    ]
