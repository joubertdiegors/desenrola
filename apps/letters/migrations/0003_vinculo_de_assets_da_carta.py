"""
Vinculo explicito carta finalizada -> asset (Etapa 3.5.1, integridade).

`Letter.document_snapshot` congela o layout, mas o layout so guarda
`asset_id`: os bytes da imagem continuam no `content.Asset`. Esta tabela
e o que impede esse Asset de sumir (FK PROTECT) ou de ter o arquivo
trocado (`Asset.save()` consulta `letter_references`) enquanto uma carta
finalizada depender dele -- sem duplicar arquivo nenhum por carta.

O passo de dados preenche a tabela para cartas que ja tenham snapshot
(nenhuma existe antes desta etapa, mas o passo e idempotente e barato).
Dai em diante quem cria as linhas e `services.capture_document_template_
snapshot()`, na mesma transacao do snapshot.
"""

import django.db.models.deletion
from django.db import migrations, models


def vincular_cartas_existentes(apps, schema_editor):
    from apps.doctemplates.layout_schema import assets_referenciados

    Letter = apps.get_model("letters", "Letter")
    LetterAsset = apps.get_model("letters", "LetterAsset")
    Asset = apps.get_model("content", "Asset")

    cartas = Letter.objects.exclude(document_snapshot_hash="").iterator()
    for carta in cartas:
        layout = (carta.document_snapshot or {}).get("layout") or {}
        necessarios = assets_referenciados(layout)
        if not necessarios:
            continue
        existentes = Asset.objects.filter(pk__in=necessarios).values_list("pk", flat=True)
        for asset_id in existentes:
            LetterAsset.objects.get_or_create(letter_id=carta.pk, asset_id=asset_id)


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0002_cms_assets_pages_settings"),
        ("letters", "0002_snapshot_do_documenttemplate"),
    ]

    operations = [
        migrations.CreateModel(
            name="LetterAsset",
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
                        related_name="letter_references",
                        to="content.asset",
                        verbose_name="imagem",
                    ),
                ),
                (
                    "letter",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asset_links",
                        to="letters.letter",
                        verbose_name="carta",
                    ),
                ),
            ],
            options={
                "verbose_name": "imagem usada por carta",
                "verbose_name_plural": "imagens usadas por cartas",
                "constraints": [
                    models.UniqueConstraint(fields=("letter", "asset"), name="uniq_letter_asset")
                ],
            },
        ),
        migrations.RunPython(vincular_cartas_existentes, migrations.RunPython.noop),
    ]
