"""
Um modelo oficial da Carta Convite por idioma de settings.LANGUAGES.

A migracao 0002 semeou um unico template ("carta-convite-curta-duracao",
frances). Aqui esse registro vira "carta-convite-curta-duracao-fr" e os
outros tres idiomas ganham o seu — cada um com uma TemplateVersion
publicada, todos com a MESMA configuracao de campos (mesmas chaves), que
e o que permite trocar o idioma da carta sem invalidar o preenchimento.

Idempotente e respeitosa com a imutabilidade: nunca altera o field_schema
de uma versao ja publicada. Se o schema vigente mudou, cria a PROXIMA
versao publicada e marca a anterior como inativa (mudanca de status e a
unica alteracao que uma versao publicada aceita — ver
TemplateVersion.save()).
"""

from django.conf import settings
from django.db import migrations
from django.db.models import Max
from django.utils import timezone

from apps.doctemplates.official_templates import (
    CARTA_CONVITE_DESCRIPTION,
    CARTA_CONVITE_FIELD_SCHEMA,
    CARTA_CONVITE_NAME,
    CARTA_CONVITE_SLUG_PREFIX,
    official_slug,
)

LEGACY_SLUG = CARTA_CONVITE_SLUG_PREFIX
LEGACY_LANGUAGE = "fr"


def _ensure_published_version(TemplateVersion, template):
    """
    Garante uma versao publicada com o schema vigente, sem nunca mexer
    numa versao ja publicada: se a publicada atual tem outro schema, ela
    e desativada e uma nova versao publicada e criada em seguida.
    """
    published = (
        template.versions.filter(status="published").order_by("-version_number").first()
    )
    if published is not None and published.field_schema == CARTA_CONVITE_FIELD_SCHEMA:
        return

    if published is not None:
        published.status = "inactive"
        published.save(update_fields=["status"])

    next_number = (
        template.versions.aggregate(Max("version_number"))["version_number__max"] or 0
    ) + 1
    TemplateVersion.objects.create(
        template=template,
        version_number=next_number,
        status="published",
        field_schema=CARTA_CONVITE_FIELD_SCHEMA,
        published_at=timezone.now(),
    )


def seed_official_templates(apps, schema_editor):
    LetterTemplate = apps.get_model("doctemplates", "LetterTemplate")
    TemplateVersion = apps.get_model("doctemplates", "TemplateVersion")

    # O template de 0002 passa a ser explicitamente o do frances.
    target_slug = official_slug(LEGACY_LANGUAGE)
    if not LetterTemplate.objects.filter(slug=target_slug).exists():
        LetterTemplate.objects.filter(slug=LEGACY_SLUG).update(slug=target_slug)

    for language, _label in settings.LANGUAGES:
        template, _created = LetterTemplate.objects.get_or_create(
            slug=official_slug(language),
            defaults={
                "name": CARTA_CONVITE_NAME,
                "description": CARTA_CONVITE_DESCRIPTION,
                "language": language,
                "is_active": True,
                "default_field_schema": CARTA_CONVITE_FIELD_SCHEMA,
            },
        )
        # `default_field_schema` e so o ponto de partida de novas versoes
        # (editavel a qualquer momento) — pode acompanhar o vigente.
        if template.default_field_schema != CARTA_CONVITE_FIELD_SCHEMA:
            template.default_field_schema = CARTA_CONVITE_FIELD_SCHEMA
            template.save(update_fields=["default_field_schema"])

        _ensure_published_version(TemplateVersion, template)


def unseed_official_templates(apps, schema_editor):
    """
    Desfaz o que da para desfazer com seguranca: remove os templates por
    idioma que nenhuma carta usa e devolve o do frances ao slug de 0002,
    para que a reversao de 0002 consiga limpar o resto.
    """
    LetterTemplate = apps.get_model("doctemplates", "LetterTemplate")

    for language, _label in settings.LANGUAGES:
        if language == LEGACY_LANGUAGE:
            continue
        template = LetterTemplate.objects.filter(slug=official_slug(language)).first()
        if template is not None and not template.letters.exists():
            template.versions.all().delete()
            template.delete()

    if not LetterTemplate.objects.filter(slug=LEGACY_SLUG).exists():
        LetterTemplate.objects.filter(slug=official_slug(LEGACY_LANGUAGE)).update(
            slug=LEGACY_SLUG
        )


class Migration(migrations.Migration):
    dependencies = [
        ("doctemplates", "0002_seed_official_template"),
        ("letters", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_official_templates, unseed_official_templates),
    ]
