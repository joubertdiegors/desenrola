"""
Publica o field_schema vigente: o placeholder do numero do passaporte
passou a ser o formato de exemplo "YY0000" (antes repetia o proprio
rotulo, "Número do passaporte", que nao ajudava ninguem).

Por que uma migracao para isso: o schema que o assistente usa nao e a
constante em `official_templates.py` -- e a copia gravada na
TemplateVersion publicada. Como versao publicada e imutavel, a mudanca
entra criando a PROXIMA versao publicada e desativando a anterior. As
cartas ja emitidas continuam apontando para a versao com que foram
feitas, que e o ponto da imutabilidade.

Reaproveita a mesma rotina de 0003, que ja e idempotente e so cria versao
nova quando o schema realmente mudou.
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
    uma carta, e a anterior continua guardada de qualquer forma. Voltar o
    texto do placeholder e assunto de uma nova versao, nunca de apagar
    uma existente.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("doctemplates", "0003_official_template_per_language"),
    ]

    operations = [
        migrations.RunPython(publicar_schema_vigente, nada_a_desfazer),
    ]
