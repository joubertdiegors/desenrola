"""
O banner superior passa a ter imagem de verdade.

UMA COLUNA, NENHUM DADO
-----------------------
`PageSection.image` nasce nula em todas as seções: nenhuma tem imagem
escolhida ainda, e a Home continua desenhando a moldura vazia
exatamente como antes. Escolher a imagem é ato de quem administra, não
da migration -- não há imagem de demonstração a semear aqui.

POR QUE FK, E NÃO UM ID NO JSON
-------------------------------
Referência guardada dentro de JSON o banco não enxerga, e o próprio
`Asset` explica o preço disso: uma tabela de vínculo só para o PROTECT
funcionar (é o que `template_references` e `letter_references` fazem).
Uma FK comum não cobra esse preço.

SET_NULL: apagar uma imagem da biblioteca não pode derrubar a página
inicial. A parte volta à moldura vazia, que é um estado válido.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0009_permissoes_de_parceiros'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagesection',
            name='image',
            field=models.ForeignKey(blank=True, help_text='A imagem desta parte. Sem ela, aparece a moldura vazia.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='page_sections', to='content.asset', verbose_name='imagem'),
        ),
    ]
