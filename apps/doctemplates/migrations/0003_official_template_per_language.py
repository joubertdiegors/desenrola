"""
Histórico: criava um modelo oficial por idioma de settings.LANGUAGES,
renomeando para o sufixo "-fr" o registro único semeado pela 0002.

Essa estrutura foi substituída pela arquitetura DocumentTemplate;
mantemos a migration como no-op para preservar a cadeia histórica do
Django.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("doctemplates", "0002_seed_official_template"),
        ("letters", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
