"""
O contador do Banner e o botão/carrossel de "Nossos parceiros" ganham
onde ser configurados.

O QUE MUDA
----------
Sete colunas novas em `PageSection`, todas estruturais (não
traduzíveis) -- mesma razão de `layout`/`image` já existirem como
colunas em vez de conteúdo: valem para a seção inteira, em qualquer
idioma.

  * `counter_enabled`, `counter_position`, `counter_live_enabled` --
    Bloco A. Só a seção "hero" os lê hoje.
  * `partners_button_position`, `partners_carousel_enabled`,
    `partners_carousel_controls_enabled`, `partners_view_all_enabled`
    -- Bloco B. Só a seção "partners" os lê hoje.

NENHUM DADO SE PERDE
---------------------
Todas com `default=`, aplicado às linhas existentes pelo próprio
Django -- e os valores escolhidos preservam o que a Home já mostrava:
o contador já aparecia (com `badge_label` preenchido na semente),
então `counter_enabled=True`; o botão de cada parceiro já ficava
ancorado embaixo do cartão, e "inferior-centro" é o ponto mais próximo
disso no novo sistema de nove posições.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0012_perguntas_frequentes'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagesection',
            name='counter_enabled',
            field=models.BooleanField(default=True, help_text='Mostra o número real de cartas já emitidas sobre o banner.', verbose_name='contador ativo'),
        ),
        migrations.AddField(
            model_name='pagesection',
            name='counter_live_enabled',
            field=models.BooleanField(default=True, help_text='Mostra a nota de atualização ao lado do contador.', verbose_name='indicador "ao vivo" ativo'),
        ),
        migrations.AddField(
            model_name='pagesection',
            name='counter_position',
            field=models.CharField(choices=[('superior-esquerda', 'Superior esquerda'), ('superior-centro', 'Superior centro'), ('superior-direita', 'Superior direita'), ('centro-esquerda', 'Centro esquerda'), ('centro', 'Centro'), ('centro-direita', 'Centro direita'), ('inferior-esquerda', 'Inferior esquerda'), ('inferior-centro', 'Inferior centro'), ('inferior-direita', 'Inferior direita')], default='superior-esquerda', max_length=20, verbose_name='posição do contador'),
        ),
        migrations.AddField(
            model_name='pagesection',
            name='partners_button_position',
            field=models.CharField(choices=[('superior-esquerda', 'Superior esquerda'), ('superior-centro', 'Superior centro'), ('superior-direita', 'Superior direita'), ('centro-esquerda', 'Centro esquerda'), ('centro', 'Centro'), ('centro-direita', 'Centro direita'), ('inferior-esquerda', 'Inferior esquerda'), ('inferior-centro', 'Inferior centro'), ('inferior-direita', 'Inferior direita')], default='inferior-centro', max_length=20, verbose_name='posição do botão no cartão'),
        ),
        migrations.AddField(
            model_name='pagesection',
            name='partners_carousel_controls_enabled',
            field=models.BooleanField(default=True, verbose_name='setas do carrossel ativas'),
        ),
        migrations.AddField(
            model_name='pagesection',
            name='partners_carousel_enabled',
            field=models.BooleanField(default=True, help_text='Com mais de 4 parceiros ativos, exibe os demais rolando na horizontal em vez de criar uma segunda fileira. Desativado, a seção mostra só os 4 primeiros e o botão "Ver todos".', verbose_name='carrossel ativo'),
        ),
        migrations.AddField(
            model_name='pagesection',
            name='partners_view_all_enabled',
            field=models.BooleanField(default=True, help_text='Só aparece quando também há um destino configurado nos textos da seção -- sem destino, o botão continua oculto.', verbose_name='botão "Ver todos" ativo'),
        ),
    ]
