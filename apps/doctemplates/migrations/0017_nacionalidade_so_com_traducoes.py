"""
Nacionalidade passa a ser apenas um nome por idioma.

`guest_form` e `host_form` saem. Eram as duas formas gramaticais que o
documento francês usava ("Nationalité : Brésilienne" e "de nationalité
belge"); a modelagem agora é mais simples -- a carta escreve o nome da
nacionalidade no idioma DELA (`name_pt`/`name_fr`/`name_nl`/`name_en`),
e só isso.

ESTA MIGRATION É DESTRUTIVA, E NÃO HÁ COMO NÃO SER
-----------------------------------------------
`RemoveField` APAGA as duas colunas. O que estiver escrito nelas some,
e reverter esta migration devolve as colunas VAZIAS -- os textos não
voltam. Quem precisar deles depois desta atualização tem de tê-los
guardado antes.

Em compensação, nada mais é perdido: `code`, `name_pt`, `name_fr`,
`name_nl`, `name_en`, `order` e `is_active` ficam intocados. As cartas
JÁ EMITIDAS também não mudam: o texto que foi impresso está congelado no
`snapshot` de cada uma, e o documento nunca mais consulta o cadastro.

NENHUM `RunPython`
------------------
Seria possível copiar `guest_form` para `name_fr`, e seria errado:
`guest_form` guardava a forma FEMININA do substantivo francês
("Brésilienne"), que não é necessariamente o nome da nacionalidade que
se quer mostrar, e `host_form` guardava o adjetivo em minúscula
("belge"). Converter automaticamente escreveria, em cima de traduções
existentes, um texto que ninguém revisou -- num documento oficial. Quem
cadastra as nacionalidades confere os quatro nomes pelo admin.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('doctemplates', '0016_permissoes_de_modelos'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='nationality',
            name='guest_form',
        ),
        migrations.RemoveField(
            model_name='nationality',
            name='host_form',
        ),
    ]
