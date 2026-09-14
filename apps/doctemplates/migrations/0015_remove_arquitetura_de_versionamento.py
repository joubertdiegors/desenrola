"""
Remove `LetterTemplate` e `TemplateVersion` do banco.

E o ultimo passo da migracao para a arquitetura final:

    DocumentType -> DocumentTemplate -> Letter -> snapshot -> PDF

Depende de `letters.0004`, que ja tirou os dois FKs de `Letter` e
vinculou cada carta ao seu `DocumentTemplate`: sem isso o PROTECT
impediria a exclusao -- corretamente.

As migrations que criaram e semearam estes modelos continuam no
historico (0001 os cria, 0002-0007 foram neutralizadas): a cadeia do
Django e sequencial e bancos ja migrados tem o registro delas. Numa
instalacao limpa as tabelas nascem e sao derrubadas aqui, no mesmo
`migrate` -- o estado final e o mesmo dos dois lados.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("doctemplates", "0014_layout_carta_convite_en_nl_pt"),
        ("letters", "0004_letter_usa_document_template"),
    ]

    operations = [
        # A ordem importa: TemplateVersion tem FK para LetterTemplate.
        #
        # `DeleteModel` direto, sem `RemoveField` antes: a versao tem uma
        # UniqueConstraint sobre `template`, e no SQLite tirar o campo
        # primeiro faria o rebuild da tabela tentar recriar a constraint
        # sobre uma coluna que ja nao existe.
        migrations.DeleteModel(name="TemplateVersion"),
        migrations.DeleteModel(name="LetterTemplate"),
    ]
