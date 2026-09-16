"""
A confirmação de e-mail ganha onde ser gravada.

O QUE MUDA
----------
`User.email_verified_at` -- QUANDO o endereço foi confirmado. Nulo para
toda conta que já existe, e é o estado certo: ninguém confirmou nada
ainda, porque até esta migration não havia como confirmar.

POR QUE UMA DATA, E NÃO UM BOOLEANO
-----------------------------------
A data responde as duas perguntas ("confirmou?" e "quando?") pelo mesmo
preço, e é ela que entra no hash do token de confirmação (ver
`accounts.confirmacao`): é por isso que o link vale UMA vez. Com um
booleano o token continuaria válido depois de usado, porque `True` é
sempre `True`.

NINGUÉM É TRANCADO FORA
-----------------------
Nada aqui exige confirmação para entrar ou gerar carta. O que a coluna
liga é o aviso na área logada e a marca na ficha do Backoffice.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_user_birth_date_user_nationality"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_verified_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="e-mail confirmado em"
            ),
        ),
    ]
