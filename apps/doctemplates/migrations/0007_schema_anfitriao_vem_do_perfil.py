"""
Histórico: republicava o field_schema sem `host_nationality` e
`host_birth_date`, que passaram a vir do perfil do usuário.

O schema vive hoje em DocumentTemplate.field_schema, que substituiu a
estrutura versionada; mantemos a migration como no-op para preservar a
cadeia histórica do Django.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("doctemplates", "0006_schema_sem_documento_do_anfitriao"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
