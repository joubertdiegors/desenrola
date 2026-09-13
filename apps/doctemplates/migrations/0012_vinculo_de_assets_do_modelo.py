"""
Vinculo explicito modelo -> asset (Etapa 3.5.1, integridade de assets).

O `layout` de um DocumentTemplate referencia imagens por `asset_id`
dentro de JSON, onde o banco nao enxerga. Esta tabela torna a referencia
visivel ao ORM, com FK PROTECT: apagar um `content.Asset` que um modelo
usa passa a ser recusado -- por `delete()`, por queryset e pelo admin.

A tabela e DERIVADA do layout (`sincronizar_assets_do_modelo`). O passo
de dados abaixo a preenche para os modelos que ja existem; dai em diante
cada `save()` a mantem. Reverso: apagar a tabela basta -- nenhum dado de
modelo e alterado por esta migration.
"""

import django.db.models.deletion
from django.db import migrations, models


def sincronizar_modelos_existentes(apps, schema_editor):
    from apps.doctemplates.models import sincronizar_assets_do_modelo

    DocumentTemplate = apps.get_model("doctemplates", "DocumentTemplate")
    for modelo in DocumentTemplate.objects.all().iterator():
        sincronizar_assets_do_modelo(DocumentTemplate, modelo)


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0002_cms_assets_pages_settings"),
        ("doctemplates", "0011_layout_carta_convite_fr"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentTemplateAsset",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="template_references",
                        to="content.asset",
                        verbose_name="imagem",
                    ),
                ),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asset_links",
                        to="doctemplates.documenttemplate",
                        verbose_name="modelo",
                    ),
                ),
            ],
            options={
                "verbose_name": "imagem usada por modelo",
                "verbose_name_plural": "imagens usadas por modelos",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("template", "asset"), name="uniq_documenttemplate_asset"
                    )
                ],
            },
        ),
        migrations.RunPython(sincronizar_modelos_existentes, migrations.RunPython.noop),
    ]
