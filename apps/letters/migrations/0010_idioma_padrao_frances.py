"""
A carta nova passa a nascer em FRANCÊS (Rodada 18).

O QUE MUDA
----------
  * o padrão de fábrica de `DocumentLanguageSettings.default_letter_language`
    (`IDIOMA_PADRAO_DA_CARTA`), de "en" para "fr" -- vale para uma
    instalação nova;
  * a configuração JÁ GRAVADA, que a 0006 semeou com "en": passa a "fr".

O QUE NÃO MUDA
--------------
A interface (sempre em português), a lista de idiomas oferecidos e as
cartas que já existem. A pessoa continua escolhendo outro idioma na
etapa 5.

SÓ SE AINDA ESTIVER NO PADRÃO ANTIGO
------------------------------------
A configuração é editável em Backoffice › Idiomas. Se alguém já escolheu
outro idioma padrão ("pt", "nl"), a escolha fica. E "fr" só entra se
estiver entre os oferecidos -- a regra de `clean()`: o padrão tem de ser
um dos idiomas disponíveis.

A VOLTA
-------
Reversível: "fr" volta a "en", com a mesma condição.
"""

from django.db import migrations, models

SINGLETON_ID = 1


def _trocar(apps, de, para):
    DocumentLanguageSettings = apps.get_model("letters", "DocumentLanguageSettings")
    config = DocumentLanguageSettings.objects.filter(pk=SINGLETON_ID).first()
    if config is None or config.default_letter_language != de:
        return
    if para not in (config.available_document_languages or []):
        return
    DocumentLanguageSettings.objects.filter(pk=SINGLETON_ID).update(default_letter_language=para)


def para_frances(apps, schema_editor):
    _trocar(apps, "en", "fr")


def de_volta_ao_ingles(apps, schema_editor):
    _trocar(apps, "fr", "en")


class Migration(migrations.Migration):

    dependencies = [
        ('letters', '0009_bandeiras_dos_idiomas'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentlanguagesettings',
            name='default_letter_language',
            field=models.CharField(choices=[('pt', 'Portugues'), ('fr', 'Frances'), ('nl', 'Holandes'), ('en', 'Ingles')], default='fr', help_text='Precisa estar entre os idiomas disponíveis.', max_length=8, verbose_name='idioma padrão de novas cartas'),
        ),
        migrations.RunPython(para_frances, de_volta_ao_ingles),
    ]
