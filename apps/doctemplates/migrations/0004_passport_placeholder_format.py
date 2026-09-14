"""
Histórico: republicava o field_schema com o placeholder do passaporte
no formato de exemplo ("YY0000").

O schema vive hoje em DocumentTemplate.field_schema, que substituiu a
estrutura versionada; mantemos a migration como no-op para preservar a
cadeia histórica do Django.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("doctemplates", "0003_official_template_per_language"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
