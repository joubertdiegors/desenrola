"""
Histórico: semeava o LetterTemplate e a TemplateVersion oficiais da
Carta Convite (versão 1, publicada).

Essa estrutura foi substituída pela arquitetura DocumentTemplate;
mantemos a migration como no-op para preservar a cadeia histórica do
Django.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("doctemplates", "0001_initial"),
        ("letters", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
