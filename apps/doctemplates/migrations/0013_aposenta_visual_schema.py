"""
Aposenta o `visual_schema` de TemplateVersion (Etapa 3.5.3).

O campo so existia para o editor visual da 4.2A/4.2C, removido nesta
mesma etapa junto com a tela `/backoffice/documentos/`. O desenho do
documento vive agora em `DocumentTemplate.layout`, sob o contrato de
`layout_schema.py`.

A 0008 (que criou o campo) fica no historico de proposito: a 0009 depende
dela, e bancos ja migrados registram sua aplicacao. Remover por cima, com
esta, e o que faz uma instalacao limpa e um banco existente chegarem ao
mesmo estado.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('doctemplates', '0012_vinculo_de_assets_do_modelo'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='templateversion',
            name='visual_schema',
        ),
    ]
