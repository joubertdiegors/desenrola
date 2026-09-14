"""
Grava o layout estrutural dos oficiais EN, NL e PT (Etapa 3.6).

Mesmo padrao da 0011, que fez isso para o frances: a 0010 criou os
quatro modelos com `layout` vazio e o desenho vem depois. Aqui entram os
tres restantes, traduzidos do documento frances -- mesma estrutura,
mesmas clausulas, mesmos campos dinamicos.

SO GRAVA SE AINDA ESTIVER VAZIO
-------------------------------
Quem decide e `services.carta_convite.aplicar()`: se o modelo ja tiver
qualquer layout, esta migration nao faz nada. Um administrador pode ter
ajustado o documento antes desta atualizacao chegar, e semeadura nenhuma
tem o direito de apagar esse trabalho.

NAO ESCREVE ARQUIVO NENHUM
--------------------------
O elemento do logo nasce apontando para `asset_id: 0`. O binario e
anexado por `services.carta_convite.reconstruir()`, chamado pelo comando
`reconstruir_modelos_oficiais` -- e e o MESMO asset dos quatro idiomas,
nunca uma copia por idioma.
"""

from django.db import migrations

from apps.doctemplates.services import carta_convite

IDIOMAS = ("en", "nl", "pt")


def aplicar(apps, schema_editor):
    DocumentTemplate = apps.get_model("doctemplates", "DocumentTemplate")
    for idioma in IDIOMAS:
        carta_convite.aplicar(DocumentTemplate, idioma)


def desfazer(apps, schema_editor):
    """
    Devolve o layout ao vazio -- mas SO se ele ainda for exatamente o que
    esta migration escreveu. Se alguem editou o documento depois, o
    reverso nao destroi a edicao: prefere nao fazer nada.
    """
    DocumentTemplate = apps.get_model("doctemplates", "DocumentTemplate")
    for idioma in IDIOMAS:
        modelo = DocumentTemplate.objects.filter(
            slug=carta_convite.slug_do_modelo(idioma)
        ).first()
        if modelo is None or not modelo.layout:
            continue

        # O logo pode ter sido vinculado depois de gravado; comparar com o
        # mesmo asset evita achar que houve edicao onde nao houve.
        asset = 0
        for elemento in modelo.layout.get("elements", []):
            if elemento.get("id") == carta_convite.id_do_logo(idioma):
                asset = (elemento.get("properties", {}).get("source") or {}).get(
                    "asset_id", 0
                )

        if modelo.layout == carta_convite.layout(idioma, asset_do_logo=asset):
            DocumentTemplate.objects.filter(pk=modelo.pk).update(layout={})


class Migration(migrations.Migration):

    dependencies = [
        ("doctemplates", "0013_aposenta_visual_schema"),
    ]

    operations = [
        migrations.RunPython(aplicar, desfazer),
    ]
