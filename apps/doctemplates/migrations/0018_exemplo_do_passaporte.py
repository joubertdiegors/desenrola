"""
O exemplo do campo de passaporte passa a ter a forma certa.

O QUE MUDA
----------
`"YY0000"` vira `"YY123456"` no `field_schema` dos modelos oficiais da
Carta Convite. Duas letras e seis dígitos é a forma do passaporte belga
e da maioria dos europeus; o exemplo anterior tinha quatro dígitos e
sugeria um número mais curto do que o real.

JÁ HOUVE UMA ASSIM
------------------
`0004_passport_placeholder_format` fez esta mesma troca no tempo do
schema versionado, e hoje é no-op -- aquela estrutura saiu. Esta faz o
mesmo trabalho na estrutura de agora (`DocumentTemplate.field_schema`).

POR QUE UMA MIGRATION, E NÃO SÓ MUDAR O MÓDULO
----------------------------------------------
`biblioteca.semear_carta_convite` usa `get_or_create`: num banco em que
os modelos oficiais já existem, mudar
`official_templates.CARTA_CONVITE_FIELD_SCHEMA` não alcança linha
nenhuma. Quem já tem o produto instalado continuaria vendo o exemplo
antigo para sempre.

E O MODELO DE SISTEMA NÃO ACEITA ISSO -- FORA DE UMA MIGRATION
--------------------------------------------------------------
`DocumentTemplate.save()` recusa alterar `field_schema` num modelo com
`is_system=True` (`DocumentTemplateLockedError`), e é uma trava certa:
ninguém deve reescrever o schema oficial pela aplicação. Aqui ela não
se aplica porque `apps.get_model()` devolve o modelo HISTÓRICO, sem os
métodos da classe -- é justamente por isso que uma migration é o lugar
certo para esta correção, e não um comando ou um `post_migrate`.

O QUE ELA NÃO TOCA
------------------
Só o campo `guest_passport`, e só quando o `placeholder` dele ainda é o
valor antigo. Um modelo cujo exemplo alguém já tenha ajustado fica como
está -- a migration corrige o que veio da semente, não o que foi
decidido depois.

A VOLTA
-------
Reversível: devolve o valor antigo, com a mesma condição.
"""

from django.db import migrations

CAMPO = "guest_passport"
ANTIGO = "YY0000"
NOVO = "YY123456"


def _trocar(apps, de, para):
    DocumentTemplate = apps.get_model("doctemplates", "DocumentTemplate")

    for modelo in DocumentTemplate.objects.filter(is_system=True):
        schema = modelo.field_schema
        # O schema gravado e UM DICIONARIO com a chave "fields" -- nao a
        # lista de campos direto. A primeira versao desta migration leu
        # como lista e nao alcancava linha nenhuma: rodava, dizia nada e
        # deixava o exemplo antigo no banco de quem ja tinha o produto
        # instalado. Um teste sobre o banco SEMEADO nao pegaria isso,
        # porque la o schema vem do modulo, ja corrigido.
        campos = (schema or {}).get("fields") if isinstance(schema, dict) else None
        if not isinstance(campos, list):
            continue

        mudou = False
        for campo in campos:
            if not isinstance(campo, dict):
                continue
            if campo.get("key") == CAMPO and campo.get("placeholder") == de:
                campo["placeholder"] = para
                mudou = True

        if mudou:
            modelo.field_schema = schema
            modelo.save(update_fields=["field_schema"])


def frente(apps, schema_editor):
    _trocar(apps, ANTIGO, NOVO)


def tras(apps, schema_editor):
    _trocar(apps, NOVO, ANTIGO)


class Migration(migrations.Migration):
    dependencies = [
        ("doctemplates", "0017_nacionalidade_so_com_traducoes"),
    ]

    operations = [
        migrations.RunPython(frente, tras),
    ]
