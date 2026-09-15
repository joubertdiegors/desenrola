"""
Os parceiros da Home viram um cadastro.

Até aqui eles eram quatro dicionários fixos em `apps/core/demo.py`, sem
imagem e com o link apontando para `#`. Agora são registros.

Só `CreateModel`: **nenhum parceiro é criado por esta migration.** Os
nomes que estavam no código ("JD-Print", "Confiar Viagens") eram dados de
apresentação, e semear registros a partir deles inventaria acordos
comerciais no banco de produção. A seção da Home simplesmente não
aparece até alguém cadastrar o primeiro.

Sem `delete_partner` nas permissões: parceiro se desativa, não se apaga.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0002_cms_assets_pages_settings'),
    ]

    operations = [
        migrations.CreateModel(
            name='Partner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='criado em')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='atualizado em')),
                ('name', models.CharField(max_length=150, verbose_name='nome')),
                ('description', models.TextField(blank=True, help_text='Uma linha sobre o serviço. Aparece abaixo do nome, na Home.', verbose_name='descrição')),
                ('url', models.URLField(blank=True, help_text='Para onde o cartão leva. Em branco, o cartão não é clicável.', verbose_name='endereço')),
                ('is_active', models.BooleanField(default=True, help_text='Só parceiros ativos aparecem na Home.', verbose_name='ativo')),
                ('order', models.PositiveIntegerField(default=0, help_text='Menor aparece primeiro.', verbose_name='ordem')),
                ('logo', models.ForeignKey(blank=True, help_text='Imagem do parceiro. Sem ela, o cartão aparece sem imagem.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='partners', to='content.asset', verbose_name='logomarca')),
            ],
            options={
                'verbose_name': 'parceiro',
                'verbose_name_plural': 'parceiros',
                'ordering': ['order', 'pk'],
                'default_permissions': ('add', 'change', 'view'),
            },
        ),
    ]
