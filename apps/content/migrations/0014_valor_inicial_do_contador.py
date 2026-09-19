"""
O contador do Banner ganha o "Valor inicial do contador".

O QUE MUDA
----------
Uma coluna nova em `PageSection`, ao lado das três do contador
(`counter_enabled`, `counter_position`, `counter_live_enabled`) e pela
mesma razão: é estrutural, vale para a seção inteira, em qualquer
idioma. Só a seção "hero" a oferece no formulário.

NENHUM NÚMERO MUDA AO MIGRAR
----------------------------
`default=0` nas linhas existentes: o número da Home continua o mesmo
até alguém informar um valor inicial. Daí em diante a Home mostra
valor inicial + `letters.statistics.cartas_emitidas()`.
"""


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0013_pagesection_contador_e_carrossel'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagesection',
            name='counter_initial_value',
            field=models.PositiveIntegerField(default=0, help_text='Somado às cartas emitidas de verdade: a Home mostra valor inicial + cartas emitidas.', verbose_name='valor inicial do contador'),
        ),
    ]
