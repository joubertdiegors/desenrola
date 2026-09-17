"""
Um modelo ATIVO por (tipo, idioma) -- a regra passa a ser do banco.

POR QUE ESTA MIGRATION TEM DUAS PARTES
--------------------------------------
O indice parcial sozinho nao entraria: ate aqui NADA impedia dois
modelos ativos do mesmo idioma, e a duplicacao criava a copia JA ATIVA
(`services/duplicacao.py`, corrigido nesta mesma etapa). Qualquer banco
com uma copia duplicada tem hoje dois ativos em frances, ou em
portugues, e o `CREATE UNIQUE INDEX` falharia no meio do deploy.

Por isso a primeira operacao ESCOLHE um ativo por (tipo, idioma) e
desativa os demais, e so a segunda cria o indice.

QUAL DELES FICA ATIVO
---------------------
Nesta ordem, e por um motivo cada:

  1. o OFICIAL (`is_system`), se estiver ativo -- e o documento que o
     produto entrega, e era o unico que o assistente usava antes desta
     etapa: manter outro no lugar dele mudaria, em silencio, qual
     documento sai na proxima carta;
  2. faltando oficial ativo, o de `updated_at` mais recente -- o mais
     provavel de ser aquele em que alguem estava trabalhando;
  3. empatando, o de `pk` menor, so para o resultado ser deterministico
     (duas execucoes do mesmo banco dao o mesmo).

Os desativados NAO sao apagados nem alterados de outra forma: continuam
inteiros, e o administrador pode reativar o que quiser -- agora pela
troca, que desativa o outro.

REVERSIVEL
----------
Desfazer remove o indice. As desativacoes NAO sao desfeitas: nao ha
como saber quais linhas eram ativas antes sem guardar um estado que
esta migration nao guarda, e reativar tudo recriaria exatamente o
estado ambiguo que ela existe para resolver.
"""

from django.db import migrations, models


def escolher_um_ativo_por_idioma(apps, schema_editor):
    DocumentTemplate = apps.get_model("doctemplates", "DocumentTemplate")

    ativos = DocumentTemplate.objects.filter(is_active=True).order_by(
        "type_id", "language", "-is_system", "-updated_at", "pk"
    )
    visto = set()
    a_desativar = []
    for modelo in ativos:
        chave = (modelo.type_id, modelo.language)
        if chave in visto:
            a_desativar.append(modelo.pk)
        else:
            visto.add(chave)

    if a_desativar:
        DocumentTemplate.objects.filter(pk__in=a_desativar).update(is_active=False)


def nada_a_desfazer(apps, schema_editor):
    """Ver "REVERSIVEL" no cabecalho: a escolha nao se desfaz."""


class Migration(migrations.Migration):

    dependencies = [
        ("doctemplates", "0018_exemplo_do_passaporte"),
    ]

    operations = [
        migrations.RunPython(escolher_um_ativo_por_idioma, nada_a_desfazer),
        migrations.AddConstraint(
            model_name="documenttemplate",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("type", "language"),
                name="uniq_documenttemplate_ativo_por_idioma",
            ),
        ),
    ]
