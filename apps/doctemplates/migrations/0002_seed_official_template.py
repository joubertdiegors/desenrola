"""
Semeia o LetterTemplate/TemplateVersion oficiais da Carta Convite (curta
duração), usados pelo assistente real (apps.letters).

Idempotente: usa `get_or_create` pelo slug e so cria a versao 1 se o
template ainda nao tiver nenhuma — rodar esta migracao de novo (ex.: apos
um `migrate` repetido) nao duplica nada. Nao mexe em migracoes anteriores.
"""

from django.db import migrations
from django.utils import timezone

from apps.doctemplates.official_templates import (
    CARTA_CONVITE_FIELD_SCHEMA,
    CARTA_CONVITE_LANGUAGE,
    CARTA_CONVITE_NAME,
    CARTA_CONVITE_SLUG,
)


def seed_official_template(apps, schema_editor):
    LetterTemplate = apps.get_model("doctemplates", "LetterTemplate")
    TemplateVersion = apps.get_model("doctemplates", "TemplateVersion")

    template, _created = LetterTemplate.objects.get_or_create(
        slug=CARTA_CONVITE_SLUG,
        defaults={
            "name": CARTA_CONVITE_NAME,
            "description": (
                "Modelo oficial da Carta Convite para estadias de curta duração "
                "(até 90 dias), usado pelo assistente de geração."
            ),
            "language": CARTA_CONVITE_LANGUAGE,
            "is_active": True,
            "default_field_schema": CARTA_CONVITE_FIELD_SCHEMA,
        },
    )

    if not template.versions.exists():
        TemplateVersion.objects.create(
            template=template,
            version_number=1,
            status="published",
            field_schema=CARTA_CONVITE_FIELD_SCHEMA,
            published_at=timezone.now(),
        )


def unseed_official_template(apps, schema_editor):
    LetterTemplate = apps.get_model("doctemplates", "LetterTemplate")

    try:
        template = LetterTemplate.objects.get(slug=CARTA_CONVITE_SLUG)
    except LetterTemplate.DoesNotExist:
        return

    # So remove se nenhuma carta real depender desta versao — nunca apaga
    # historico (o mesmo espirito do TemplateVersionImmutableError/PROTECT
    # em apps/letters/models.py, aqui reaplicado no caminho reverso). O
    # modelo historico nao tem o TemplateVersionImmutableError (metodos
    # customizados nao existem em modelos historicos), entao apagar a
    # versao publicada aqui e seguro so porque ja garantimos, na linha
    # acima, que nenhuma Letter a usa.
    if not template.letters.exists():
        template.versions.all().delete()
        template.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("doctemplates", "0001_initial"),
        # Necessaria para que o modelo historico de LetterTemplate, nesta
        # migracao, ja exponha o related_name reverso `letters` (usado no
        # reverse desta migracao, `unseed_official_template`).
        ("letters", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_official_template, unseed_official_template),
    ]
