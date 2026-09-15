"""
A barra superior e o rodapé viram seções de verdade.

O QUE MUDA NO ESQUEMA
---------------------
  * `PageSection.layout` -- QUAL desenho a seção usa, separado de QUAL
    conteúdo ela tem. É o que permite o Banner superior ter três
    variações sem que trocar de uma para outra apague o texto;

  * `PageSection.Kind` ganha `navbar` e `footer`;

  * `MenuItem` -- os itens da barra superior, com texto, destino, ordem
    e ativação próprios;

  * `Partner` passa a aceitar exclusão (a Central de Conteúdo removeu a
    dependência do Django Admin; até aqui nem ele podia apagar).

O QUE A SEMENTE FAZ
-------------------
Reproduz EXATAMENTE o que a Home já mostra hoje, para que aplicar esta
migration não mude nada para ninguém:

  * a seção da barra superior, com os dois rótulos de botão que o
    template traz escritos;
  * os dois itens de menu que existem no template ("Como funciona" e
    "Parceiros"), com as mesmas âncoras;
  * a seção do rodapé, com o rótulo do contato;
  * o Banner superior marcado com o desenho que ele já tem
    (`imagem_texto`).

Tudo por `get_or_create`: rodar de novo não desfaz o que um
administrador tiver mudado pela tela.

O QUE ELA NÃO DUPLICA
---------------------
Logotipo, nome do site, cores, redes sociais e páginas legais continuam
onde estavam (`SiteSettings` e `ContentBlock`). A barra e o rodapé
controlam COMPOSIÇÃO e NAVEGAÇÃO, não identidade.
"""

import django.core.validators
from django.db import migrations, models


CHAVE_DA_PAGINA = "home"

# (chave, tipo, ordem, layout, conteúdo em português)
SECOES_NOVAS = (
    (
        "navbar",
        "navbar",
        0,
        "",
        {
            "login_label": "Fazer login",
            "signup_label": "Criar minha conta",
        },
    ),
    (
        "footer",
        "footer",
        6,
        "",
        {
            "contato_label": "Contato",
        },
    ),
)

# Os dois itens que o template já trazia escritos.
ITENS_DO_MENU = (
    ("Como funciona", "#como-funciona", 1),
    ("Parceiros", "#parceiros", 2),
)

# O Banner superior já tem um desenho; é este.
LAYOUT_DO_BANNER = "imagem_texto"


def semear(apps, schema_editor):
    Page = apps.get_model("content", "Page")
    PageSection = apps.get_model("content", "PageSection")
    PageSectionTranslation = apps.get_model("content", "PageSectionTranslation")
    MenuItem = apps.get_model("content", "MenuItem")

    from django.conf import settings

    pagina = Page.objects.filter(key=CHAVE_DA_PAGINA).first()
    if pagina is None:
        # Banco em que `content.0004` ainda não rodou. Nada a semear.
        return

    for chave, tipo, ordem, layout, conteudo in SECOES_NOVAS:
        secao, _criada = PageSection.objects.get_or_create(
            page=pagina,
            key=chave,
            defaults={"kind": tipo, "order": ordem, "layout": layout, "is_active": True},
        )
        PageSectionTranslation.objects.get_or_create(
            section=secao,
            language=settings.LANGUAGE_CODE,
            defaults={"content": conteudo},
        )

    for texto, destino, ordem in ITENS_DO_MENU:
        MenuItem.objects.get_or_create(
            destination=destino,
            defaults={"label": texto, "order": ordem, "is_active": True},
        )

    PageSection.objects.filter(page=pagina, key="hero", layout="").update(
        layout=LAYOUT_DO_BANNER
    )


def remover(apps, schema_editor):
    """
    Tira o que a semente pôs. As colunas somem com as operações de
    esquema revertidas; aqui só saem as LINHAS.
    """
    PageSection = apps.get_model("content", "PageSection")
    MenuItem = apps.get_model("content", "MenuItem")

    PageSection.objects.filter(
        page__key=CHAVE_DA_PAGINA, key__in=[chave for chave, *_r in SECOES_NOVAS]
    ).delete()
    MenuItem.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0007_paginas_legais'),
    ]

    operations = [
        migrations.CreateModel(
            name='MenuItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='criado em')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='atualizado em')),
                ('label', models.CharField(max_length=60, verbose_name='texto')),
                ('destination', models.CharField(help_text='#ancora, /caminho do site ou endereço http(s).', max_length=200, validators=[django.core.validators.RegexValidator(message='O destino deve ser uma âncora (#como-funciona), um caminho do site (/pt/...) ou um endereço http:// ou https://.', regex='^(#[\\w-]+|/[\\w\\-/.]*|https?://\\S+)$')], verbose_name='destino')),
                ('is_active', models.BooleanField(default=True, verbose_name='ativo')),
                ('order', models.PositiveIntegerField(default=0, help_text='Menor aparece primeiro.', verbose_name='ordem')),
            ],
            options={
                'verbose_name': 'item do menu',
                'verbose_name_plural': 'itens do menu',
                'ordering': ['order', 'pk'],
                'default_permissions': (),
            },
        ),
        migrations.AlterModelOptions(
            name='partner',
            options={'default_permissions': ('add', 'change', 'delete', 'view'), 'ordering': ['order', 'pk'], 'verbose_name': 'parceiro', 'verbose_name_plural': 'parceiros'},
        ),
        migrations.AddField(
            model_name='pagesection',
            name='layout',
            field=models.CharField(blank=True, default='', help_text='Qual variação visual esta seção usa. Vazio = a única que existe.', max_length=40, verbose_name='desenho'),
        ),
        migrations.AlterField(
            model_name='pagesection',
            name='kind',
            field=models.CharField(choices=[('navbar', 'Barra superior'), ('hero', 'Destaque (hero)'), ('text', 'Texto'), ('image_text', 'Imagem e texto'), ('features', 'Destaques / recursos'), ('partners', 'Parceiros'), ('faq', 'Perguntas frequentes'), ('cta', 'Chamada para ação'), ('banner', 'Banner'), ('contact', 'Contato'), ('footer', 'Rodapé')], max_length=20, verbose_name='tipo'),
        ),
        migrations.RunPython(semear, remover),
    ]
