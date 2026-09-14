"""
Grava o layout estrutural do modelo oficial frances (Etapa 3.3).

A 0010 criou os quatro oficiais com `layout` vazio -- o seu proprio
docstring ja dizia que o desenho viria depois, com o FR reconstruido do
PDF oficial. E o que esta migration faz, sem tocar naquela.

SO GRAVA SE AINDA ESTIVER VAZIO
-------------------------------
Quem decide e `services.carta_convite.aplicar()`: se o modelo ja tiver
qualquer layout, esta migration nao faz nada. Um administrador pode ter
ajustado o documento antes desta atualizacao chegar, e semeadura nenhuma
tem o direito de apagar esse trabalho.

NAO ESCREVE ARQUIVO NENHUM
--------------------------
O elemento do logo nasce apontando para `asset_id: 0` -- existe, mas
ainda sem binario. Criar o `content.Asset` exige gravar em MEDIA_ROOT, e
migration que escreve em disco quebra em armazenamento remoto ou
sistema de arquivos somente-leitura, alem de deixar uma copia do PNG por
execucao da suite. O binario e anexado por
`services.carta_convite.reconstruir()`.
"""

from django.db import migrations

from apps.doctemplates.services import carta_convite


def aplicar(apps, schema_editor):
    DocumentTemplate = apps.get_model("doctemplates", "DocumentTemplate")
    carta_convite.aplicar(DocumentTemplate, "fr")


def desfazer(apps, schema_editor):
    """
    Devolve o layout ao vazio -- mas SO se ele ainda for exatamente o que
    esta migration escreveu. Se alguem editou o documento depois, o
    reverso nao destroi a edicao: prefere nao fazer nada.
    """
    DocumentTemplate = apps.get_model("doctemplates", "DocumentTemplate")
    modelo = DocumentTemplate.objects.filter(
        slug=carta_convite.slug_do_modelo("fr")
    ).first()
    if modelo is None or not modelo.layout:
        return

    # O logo pode ter sido vinculado depois de gravado; comparar com o
    # mesmo asset evita achar que houve edicao onde nao houve.
    asset = 0
    for elemento in modelo.layout.get("elements", []):
        if elemento.get("id") == carta_convite.id_do_logo("fr"):
            asset = (elemento.get("properties", {}).get("source") or {}).get("asset_id", 0)

    if modelo.layout == carta_convite.layout("fr", asset_do_logo=asset):
        DocumentTemplate.objects.filter(pk=modelo.pk).update(layout={})


class Migration(migrations.Migration):

    dependencies = [
        ("doctemplates", "0010_semear_biblioteca_carta_convite"),
    ]

    operations = [
        migrations.RunPython(aplicar, desfazer),
    ]
