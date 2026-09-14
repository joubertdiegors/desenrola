"""
Histórico: republicava o field_schema sem os campos de documento do
anfitrião, com as nacionalidades passando a vir do cadastro.

O schema vive hoje em DocumentTemplate.field_schema, que substituiu a
estrutura versionada; mantemos a migration como no-op para preservar a
cadeia histórica do Django.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("doctemplates", "0005_nationality"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
