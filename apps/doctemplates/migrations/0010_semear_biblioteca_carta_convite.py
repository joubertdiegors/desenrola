"""
Semeia a biblioteca de modelos: o tipo "Carta Convite" e os quatro
modelos oficiais (fr, nl, en, pt), com o schema vigente e layout vazio.

A logica mora em `apps.doctemplates.services.biblioteca`, que recebe as
classes de modelo por parametro -- aqui entram as HISTORICAS, de
`apps.get_model()`. Idempotente: procurar por slug antes de criar, e
nunca mexer no que ja existe.

Nao toca em LetterTemplate/TemplateVersion nem em Letter: a arquitetura
antiga continua em uso ate o cutover.
"""

from django.db import migrations

from apps.doctemplates.services.biblioteca import (
    CODIGO_CARTA_CONVITE,
    MODELOS_OFICIAIS,
    semear_carta_convite,
)


def semear(apps, schema_editor):
    DocumentType = apps.get_model("doctemplates", "DocumentType")
    DocumentTemplate = apps.get_model("doctemplates", "DocumentTemplate")
    semear_carta_convite(DocumentType, DocumentTemplate)


def desfazer(apps, schema_editor):
    """
    Remove os quatro oficiais e o tipo -- so se ninguem depender deles.
    Os modelos historicos nao passam por `DocumentTemplate.delete()`, entao
    a guarda de `is_system` nao se aplica aqui: reverter uma migration e
    uma decisao explicita de quem a roda.
    """
    DocumentType = apps.get_model("doctemplates", "DocumentType")
    DocumentTemplate = apps.get_model("doctemplates", "DocumentTemplate")
    DocumentTemplate.objects.filter(
        slug__in=[slug for _lang, slug, _nome in MODELOS_OFICIAIS], is_system=True
    ).delete()
    DocumentType.objects.filter(code=CODIGO_CARTA_CONVITE, templates__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("doctemplates", "0009_biblioteca_de_modelos"),
    ]

    operations = [
        migrations.RunPython(semear, desfazer),
    ]
