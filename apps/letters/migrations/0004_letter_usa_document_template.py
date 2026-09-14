"""
A Letter passa a apontar SO para `DocumentTemplate`.

Fim da arquitetura de versionamento: saem `template` (LetterTemplate) e
`template_version` (TemplateVersion), e `document_template` -- que nascia
opcional, enquanto as duas arquiteturas conviviam -- vira obrigatorio.

O BACKFILL
----------
Cartas gravadas antes disto nao tem `document_template`. Cada uma recebe
o modelo oficial do SEU idioma, que e exatamente o que a resolucao por
idioma faria hoje (`services.official_document_template`). Carta sem
idioma (rascunho abandonado na primeira etapa) cai no idioma padrao.

Se faltar o modelo oficial de algum idioma, a migration PARA em vez de
inventar um vinculo: banco sem a biblioteca semeada e estado inesperado,
nao um caso a contornar.
"""

from django.db import migrations, models
import django.db.models.deletion

# O idioma em que toda carta nova comeca (services.IDIOMA_PADRAO_DA_CARTA).
# Copiado, nao importado: migration nao deve seguir constante de aplicacao
# que pode mudar depois.
IDIOMA_PADRAO = "en"


def _slug_oficial(language):
    return f"carta-convite-{language}"


def vincular_o_modelo_oficial(apps, schema_editor):
    Letter = apps.get_model("letters", "Letter")
    DocumentTemplate = apps.get_model("doctemplates", "DocumentTemplate")

    pendentes = Letter.objects.filter(document_template__isnull=True)
    if not pendentes.exists():
        return

    por_slug = {}
    for carta in pendentes:
        slug = _slug_oficial(carta.language or IDIOMA_PADRAO)
        if slug not in por_slug:
            modelo = DocumentTemplate.objects.filter(slug=slug).first()
            if modelo is None:
                raise RuntimeError(
                    f'O modelo oficial "{slug}" não existe: a biblioteca de '
                    "modelos não foi semeada, e a carta "
                    f"{carta.pk} não tem a que ser vinculada."
                )
            por_slug[slug] = modelo
        Letter.objects.filter(pk=carta.pk).update(document_template=por_slug[slug])


def desvincular(apps, schema_editor):
    """O reverso apenas devolve o campo ao vazio; os FKs antigos voltam
    pela propria AlterField/AddField revertida, sem dado para recompor."""
    Letter = apps.get_model("letters", "Letter")
    Letter.objects.update(document_template=None)


class Migration(migrations.Migration):

    dependencies = [
        ("letters", "0003_vinculo_de_assets_da_carta"),
        # O backfill le DocumentTemplate ja com os quatro oficiais
        # desenhados (0014 gravou EN/NL/PT).
        ("doctemplates", "0014_layout_carta_convite_en_nl_pt"),
    ]

    operations = [
        migrations.RunPython(vincular_o_modelo_oficial, desvincular),
        migrations.AlterField(
            model_name="letter",
            name="document_template",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="letters",
                to="doctemplates.documenttemplate",
                verbose_name="modelo",
            ),
        ),
        migrations.RemoveField(model_name="letter", name="template"),
        migrations.RemoveField(model_name="letter", name="template_version"),
    ]
