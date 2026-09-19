"""
Os documentos legais passam a "Blocos estruturados" (Rodada 22).

O QUE MUDA
----------
1. `ContentBlock.kind` ganha a opção `structured` -- só isso muda no
   ESQUEMA (é um `choices` novo, não uma coluna nova);
2. Os blocos `legal.terms_of_use` e `legal.privacy_policy`, em
   QUALQUER idioma que já tenha texto, são convertidos: o HTML/texto
   de hoje vira uma lista de blocos (`apps.content.blocos.
   migrar_html_para_blocos`), gravada como JSON no MESMO campo
   `content`. Os dois blocos passam a `kind="structured"`.

NADA SE PERDE
-------------
A conversão é a mesma que o editor faria na primeira gravação -- só
que feita aqui, uma vez, para todo mundo, em vez de na hora em que
alguém abrir o editor pela primeira vez depois do deploy. Um HTML que
o conversor não reconheça vira um bloco `html` só, com o conteúdo
intacto (ver o cabeçalho de `apps.content.blocos`).

A VOLTA
-------
Reversível: cada tradução convertida volta a ser o HTML de antes
(`apps.content.blocos.renderizar_blocos`, sem o `mark_safe` -- aqui é
só o texto gravado), e o `kind` volta a `rich_text`. Uma tradução que
já estivesse vazia continua vazia nos dois sentidos.
"""

import json

from django.db import migrations, models

CHAVES = ("legal.terms_of_use", "legal.privacy_policy")


def _para_blocos(apps, schema_editor):
    from apps.content import blocos as blocos_svc
    from apps.content import rodape

    ContentBlock = apps.get_model("content", "ContentBlock")
    ContentTranslation = apps.get_model("content", "ContentTranslation")

    for chave in CHAVES:
        bloco = ContentBlock.objects.filter(key=chave).first()
        if bloco is None or bloco.kind == "structured":
            continue
        veio_de_rico = bloco.kind == "rich_text"
        mudou = False
        for traducao in ContentTranslation.objects.filter(block=bloco):
            bruto = (traducao.content or "").strip()
            if not bruto:
                continue
            if veio_de_rico:
                html_de_antes = bruto
            else:
                # Texto simples: o mesmo `texto_simples_como_html` de
                # `services.py`, sem importar o módulo (migration
                # histórica -- usa só `django.utils.html.linebreaks`).
                from django.utils.html import linebreaks

                html_de_antes = rodape.sanitizar_documento(linebreaks(bruto, autoescape=True))
            lista = blocos_svc.migrar_html_para_blocos(html_de_antes)
            traducao.content = json.dumps(lista, ensure_ascii=False)
            traducao.save(update_fields=["content", "updated_at"])
            mudou = True
        if mudou:
            bloco.kind = "structured"
            bloco.save(update_fields=["kind", "updated_at"])


def _de_volta_ao_html(apps, schema_editor):
    from apps.content import blocos as blocos_svc

    ContentBlock = apps.get_model("content", "ContentBlock")
    ContentTranslation = apps.get_model("content", "ContentTranslation")

    for chave in CHAVES:
        bloco = ContentBlock.objects.filter(key=chave).first()
        if bloco is None or bloco.kind != "structured":
            continue
        for traducao in ContentTranslation.objects.filter(block=bloco):
            bruto = (traducao.content or "").strip()
            if not bruto:
                continue
            try:
                lista = json.loads(bruto)
            except ValueError:
                continue
            if not isinstance(lista, list):
                continue
            traducao.content = blocos_svc.renderizar_blocos(lista)
            traducao.save(update_fields=["content", "updated_at"])
        bloco.kind = "rich_text"
        bloco.save(update_fields=["kind", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0014_valor_inicial_do_contador"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contentblock",
            name="kind",
            field=models.CharField(
                choices=[
                    ("text", "Texto simples"),
                    ("rich_text", "Texto formatado"),
                    ("image", "Imagem"),
                    ("structured", "Blocos estruturados"),
                ],
                default="text",
                max_length=20,
                verbose_name="tipo",
            ),
        ),
        migrations.RunPython(_para_blocos, _de_volta_ao_html),
    ]
