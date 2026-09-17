"""
As duas declaracoes da etapa 4, saindo do codigo para o banco.

O TEXTO E O MESMO, AS CHAVES SAO AS MESMAS
------------------------------------------
`notice_informal` e `notice_prise_en_charge` vinham de constantes
Python em `doctemplates.official_templates`, dentro do `field_schema`
do modelo oficial. Nada muda para quem ja aceitou: a chave gravada em
`Letter.data` continua identica, e o texto que entra aqui e copia fiel
do que estava no codigo.

O QUE MUDA E QUEM PODE MEXER
----------------------------
Dali em diante o texto e cadastro (`letters.LetterNotice`), editavel no
Backoffice -- sem migration, sem depender de um `field_schema` que o
proprio modelo recusa alterar depois da primeira carta emitida.

O `field_schema` continua declarando os dois campos: e ele que descreve
a ESTRUTURA do documento e o que as cartas antigas ja gravaram. O que
mudou e so a fonte que o assistente le na etapa 4 (ver
`letters.services.fields_for_section`).

Reversivel: desfazer apaga as duas declaracoes semeadas aqui. Quem
reverte esta migration esta revertendo a ETAPA -- com o codigo de volta,
`fields_for_section` torna a ler o `field_schema`, que nunca deixou de
existir. Revertida so a migration, com o codigo novo no lugar, a etapa 4
fica sem caixas: e o mesmo estado de quem apagar todas as declaracoes
pelo Backoffice, e nao um erro.
"""

from django.db import migrations

# Copia literal das constantes de `doctemplates.official_templates` na
# data desta migration. Nao importamos de la de proposito: migration
# congela dado, e um `import` faria o passado mudar junto com o codigo.
NOTICE_INFORMAL = (
    "Declaro estar ciente de que a Carta Convite é um documento de caráter "
    "informal e, por si só, não possui força jurídica, não garante a "
    "concessão de visto nem a entrada ou permanência no Espaço Schengen. "
    "Estou ciente de que emitir uma Carta Convite envolve responsabilidade "
    "e que as informações nela declaradas devem ser verdadeiras, completas "
    "e corresponder à realidade da visita e da hospedagem."
)

NOTICE_PRISE_EN_CHARGE = (
    "Declaro estar ciente de que a Carta Convite não deve ser confundida "
    "com a “Prise en Charge” (Annexe 3bis). A Carta Convite serve para "
    "formalizar uma intenção de convite e/ou hospedagem, enquanto a Prise "
    "en Charge é um compromisso formal de responsabilidade financeira "
    "sujeito às condições e formalidades previstas pela legislação belga."
)

DECLARACOES = (
    ("notice_informal", NOTICE_INFORMAL, 1),
    ("notice_prise_en_charge", NOTICE_PRISE_EN_CHARGE, 2),
)


def semear(apps, schema_editor):
    LetterNotice = apps.get_model("letters", "LetterNotice")
    for chave, texto, ordem in DECLARACOES:
        # `get_or_create`, e nao `create`: rodar de novo (ou sobre um
        # banco que ja tenha a declaracao) nao pode duplicar nem
        # sobrescrever um texto que alguem ja editou no Backoffice.
        LetterNotice.objects.get_or_create(
            key=chave,
            defaults={"text": texto, "order": ordem, "is_active": True},
        )


def desfazer(apps, schema_editor):
    LetterNotice = apps.get_model("letters", "LetterNotice")
    LetterNotice.objects.filter(key__in=[chave for chave, _t, _o in DECLARACOES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("letters", "0007_declaracoes_do_assistente"),
    ]

    operations = [
        migrations.RunPython(semear, desfazer),
    ]
