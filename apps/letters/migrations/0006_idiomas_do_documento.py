"""
Os idiomas do documento viram configuração, e não mais uma constante.

O QUE ESTA MIGRATION CRIA
-------------------------
  * `DocumentLanguageSettings` -- um registro só (singleton) com os
    idiomas que o assistente oferece e o idioma em que uma carta nova
    nasce;

  * a linha desse registro, já semeada com os quatro idiomas oficiais e
    o padrão `en`;

  * `letters.change_documentlanguagesettings` para quem já administra.

INSTALAR NÃO MUDA NADA
----------------------
A semente reproduz exatamente o comportamento anterior: os quatro
idiomas continuam disponíveis e `en` continua sendo o padrão (era a
constante `services.IDIOMA_PADRAO_DA_CARTA`). O que muda é quem manda --
até aqui era o código, daqui em diante é a tela.

UMA SÓ PERMISSÃO
----------------
`default_permissions = ("change",)` no modelo: ver esta configuração
exige apenas `core.access_backoffice` -- uma regra que vale para todo
mundo pode ser lida por quem administra; alterá-la é outra coisa (mesma
decisão de `backoffice_letter_policy`). Criar `view`, `add` e `delete`
produziria três permissões que nada no produto confere.

POR QUE A PERMISSÃO É CRIADA AQUI
---------------------------------
O Django cria as permissões de um modelo no `post_migrate`, isto é,
DEPOIS de todas as migrations rodarem. Num banco novo ela ainda não
existe quando este código roda, e uma migration que só a procurasse não
acharia nada. Por isso é criada explicitamente, com o mesmo `codename` e
o mesmo `name` que o Django geraria -- quando o `post_migrate` chegar,
vai encontrá-la pronta e não fará nada. Mesma técnica de `content.0005`.

`accounts.manage_users`, e não `core.access_backoffice`: quem distribui
permissões é o topo da escada administrativa, e é de lá que as demais
pessoas recebem esta.
"""

import apps.letters.models
from django.db import migrations, models

SINGLETON_ID = 1

# Exatamente o que `django.contrib.auth.management.create_permissions`
# geraria a partir do `verbose_name` de `DocumentLanguageSettings`.
CODENAME = "change_documentlanguagesettings"
NOME_DA_PERMISSAO = "Can change idiomas do documento"


def semear_a_configuracao(apps_registry, schema_editor):
    """
    A configuração nasce com o comportamento de hoje: quatro idiomas,
    padrão `en`.

    `get_or_create`: rodar de novo não desfaz o que um administrador
    tiver mudado pela tela.
    """
    from django.conf import settings

    DocumentLanguageSettings = apps_registry.get_model("letters", "DocumentLanguageSettings")
    DocumentLanguageSettings.objects.get_or_create(
        pk=SINGLETON_ID,
        defaults={
            "available_document_languages": [code for code, _nome in settings.LANGUAGES],
            "default_letter_language": "en",
        },
    )


def apagar_a_configuracao(apps_registry, schema_editor):
    """O reverso; a tabela some com a CreateModel revertida."""
    DocumentLanguageSettings = apps_registry.get_model("letters", "DocumentLanguageSettings")
    DocumentLanguageSettings.objects.filter(pk=SINGLETON_ID).delete()


def conceder_a_quem_ja_administra(apps_registry, schema_editor):
    ContentType = apps_registry.get_model("contenttypes", "ContentType")
    Permission = apps_registry.get_model("auth", "Permission")
    User = apps_registry.get_model("accounts", "User")

    tipo, _criado = ContentType.objects.get_or_create(
        app_label="letters", model="documentlanguagesettings"
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


def revogar(apps_registry, schema_editor):
    """Tira a permissão de todo mundo; ela própria continua existindo."""
    Permission = apps_registry.get_model("auth", "Permission")
    for permissao in Permission.objects.filter(
        content_type__app_label="letters", codename=CODENAME
    ):
        permissao.user_set.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("letters", "0005_politica_e_ciclo_de_vida"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("accounts", "0004_user_birth_date_user_nationality"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentLanguageSettings",
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
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="atualizado em"),
                ),
                (
                    "available_document_languages",
                    models.JSONField(
                        default=apps.letters.models.idiomas_oficiais,
                        help_text="Os idiomas que o assistente oferece para uma carta nova.",
                        verbose_name="idiomas disponíveis",
                    ),
                ),
                (
                    "default_letter_language",
                    models.CharField(
                        choices=[
                            ("pt", "Portugues"),
                            ("fr", "Frances"),
                            ("nl", "Holandes"),
                            ("en", "Ingles"),
                        ],
                        default="en",
                        help_text="Precisa estar entre os idiomas disponíveis.",
                        max_length=8,
                        verbose_name="idioma padrão de novas cartas",
                    ),
                ),
            ],
            options={
                "verbose_name": "idiomas do documento",
                "verbose_name_plural": "idiomas do documento",
                "default_permissions": ("change",),
            },
        ),
        migrations.RunPython(semear_a_configuracao, apagar_a_configuracao),
        migrations.RunPython(conceder_a_quem_ja_administra, revogar),
    ]
