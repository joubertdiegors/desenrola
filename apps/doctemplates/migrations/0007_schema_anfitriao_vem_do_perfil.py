"""
Publica o field_schema vigente: a etapa do anfitriao deixa de pedir
`host_nationality` e `host_birth_date`.

Os dois viraram dados do PERFIL (accounts.User.nationality e
.birth_date), pela mesma razao do numero do documento, removido na 0006:
sao dados da pessoa, nao da viagem -- ela informa uma vez e toda carta
seguinte ja os traz. Na etapa do anfitriao resta apenas a declaracao
(`host_confirm`), que e um ato daquela carta especifica.

O texto do documento NAO muda: os mesmos valores continuam sendo
impressos, so que lidos do perfil congelado no snapshot.

Como versao publicada e imutavel, isto entra criando a PROXIMA versao
publicada e desativando a anterior; as cartas ja emitidas seguem na
versao com que foram feitas.
"""

import importlib

from django.db import migrations

# O modulo da 0003 comeca com digito, entao nao da para importar pelo
# `import` normal -- e so por isso que esta linha existe.
etapa_anterior = importlib.import_module(
    "apps.doctemplates.migrations.0003_official_template_per_language"
)


def publicar_schema_vigente(apps, schema_editor):
    etapa_anterior.seed_official_templates(apps, schema_editor)


def nada_a_desfazer(apps, schema_editor):
    """
    Reverter nao apaga a versao publicada: ela pode ja estar em uso por
    uma carta, e a anterior continua guardada de qualquer forma.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("doctemplates", "0006_schema_sem_documento_do_anfitriao"),
    ]

    operations = [
        migrations.RunPython(publicar_schema_vigente, nada_a_desfazer),
    ]
