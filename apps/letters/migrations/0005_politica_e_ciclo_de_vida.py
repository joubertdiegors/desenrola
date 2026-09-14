"""
Ciclo de vida da carta: a política administrativa e o marco zero dos
prazos.

Duas coisas:

  * `LetterPolicy` -- um registro só (singleton) com as duas políticas
    configuráveis no Backoffice. Os padrões (`NAO_EDITAVEL` + `NUNCA`)
    reproduzem exatamente o comportamento anterior a esta etapa: aplicar
    a migration não muda nada para ninguém.

  * `Letter.finalized_at` -- quando a carta foi finalizada pela primeira
    vez. É de onde saem os prazos de edição (ver
    `apps.letters.lifecycle`).

O BACKFILL
----------
Cartas já finalizadas não têm esse instante gravado em lugar nenhum com
precisão. O melhor registro disponível, em ordem: `generated_at` (existe
sempre que o PDF foi gerado) e, na falta dele, `updated_at`. Rascunho
não recebe nada -- ainda não foi finalizado.

Aproximar é correto aqui: o campo só serve para contar prazo a partir da
finalização, e as duas fontes são do mesmo momento do fluxo (o
fechamento). Deixar vazio seria pior: a carta ficaria sem prazo
calculável para sempre.
"""

from django.db import migrations, models


def marcar_finalizacao_das_cartas_existentes(apps, schema_editor):
    Letter = apps.get_model("letters", "Letter")

    for carta in Letter.objects.exclude(status="draft").filter(finalized_at__isnull=True):
        Letter.objects.filter(pk=carta.pk).update(
            finalized_at=carta.generated_at or carta.updated_at
        )


def desmarcar(apps, schema_editor):
    """O reverso apenas esvazia; a coluna some com a AddField revertida."""
    Letter = apps.get_model("letters", "Letter")
    Letter.objects.update(finalized_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ("letters", "0004_letter_usa_document_template"),
    ]

    operations = [
        migrations.CreateModel(
            name="LetterPolicy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="atualizado em"),
                ),
                (
                    "editability",
                    models.CharField(
                        choices=[
                            ("nao_editavel", "Não pode ser editada"),
                            ("por_horas", "Por algumas horas após finalizar"),
                            ("por_dias", "Por alguns dias após finalizar"),
                            ("ate_data_viagem", "Até a data da viagem"),
                            ("ate_x_dias_apos_criacao", "Até X dias após a criação"),
                        ],
                        default="nao_editavel",
                        max_length=32,
                        verbose_name="edição após finalizar",
                    ),
                ),
                (
                    "editability_amount",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Horas ou dias, conforme a política escolhida.",
                        verbose_name="quantidade (edição)",
                    ),
                ),
                (
                    "expiration",
                    models.CharField(
                        choices=[
                            ("nunca", "Nunca expira"),
                            ("na_data_da_viagem", "Na data da viagem"),
                            ("x_dias_antes_da_viagem", "X dias antes da viagem"),
                            ("x_dias_depois_da_viagem", "X dias depois da viagem"),
                            ("x_dias_apos_criacao", "X dias após a criação"),
                        ],
                        default="nunca",
                        max_length=32,
                        verbose_name="expiração",
                    ),
                ),
                (
                    "expiration_amount",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Dias, conforme a política escolhida.",
                        verbose_name="quantidade (expiração)",
                    ),
                ),
            ],
            options={
                "verbose_name": "política das cartas",
                "verbose_name_plural": "política das cartas",
            },
        ),
        migrations.AddField(
            model_name="letter",
            name="finalized_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="finalizada em"),
        ),
        migrations.RunPython(marcar_finalizacao_das_cartas_existentes, desmarcar),
    ]
