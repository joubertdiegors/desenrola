"""
Integracao com a nova arquitetura de modelos na Letter (Etapa 3.5.1).

Tres campos novos, todos opcionais -- toda Letter existente continua com
`document_template=None`, `document_snapshot={}` e
`document_snapshot_hash=""`, exatamente como antes desta migration.
Nenhum dado e migrado nem alterado.

`document_template` e PROTECT pelo mesmo motivo de `Letter.template`/
`Letter.template_version`: uma vez que uma carta referencie um
`DocumentTemplate`, ele nao pode ser apagado por baixo dela.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('doctemplates', '0011_layout_carta_convite_fr'),
        ('letters', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='letter',
            name='document_snapshot',
            field=models.JSONField(blank=True, default=dict, verbose_name='snapshot do modelo estrutural'),
        ),
        migrations.AddField(
            model_name='letter',
            name='document_snapshot_hash',
            field=models.CharField(blank=True, max_length=64, verbose_name='hash do snapshot estrutural'),
        ),
        migrations.AddField(
            model_name='letter',
            name='document_template',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='letters', to='doctemplates.documenttemplate', verbose_name='modelo estrutural'),
        ),
    ]
