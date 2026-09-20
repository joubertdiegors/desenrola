"""
A confirmação de telefone: o código que prova a posse do número.

POR QUE ISTO EXISTE
-------------------
A política "exigir confirmação de e-mail e telefone" (Wizzard › Validação
para gerar carta convite) precisa de uma confirmação DE VERDADE. Telefone
preenchido não é telefone confirmado: qualquer número digitado -- errado,
inventado ou de outra pessoa -- preencheria o campo. O que confirma é um
código enviado AO APARELHO e digitado de volta.

A MESMA FORMA DA CONFIRMAÇÃO DE E-MAIL, COM A FERRAMENTA CERTA
--------------------------------------------------------------
No e-mail o segredo é um link assinado (`accounts.confirmacao`), porque
um e-mail comporta um link. Um SMS, não: ali cabe um código curto, que a
pessoa lê e digita. Isso troca o problema de "assinar" por "guardar sem
poder ler de volta" -- e por isso o código vive num registro próprio
(`ConfirmacaoDeTelefone`), guardado como HASH, com prazo, limite de
tentativas e espera entre envios.

O QUE TORNA O CÓDIGO CURTO SEGURO
---------------------------------
Seis dígitos são um milhão de combinações. Sozinho, isso seria pouco --
o que o protege são os três limites:

  PRAZO        dez minutos; depois disso o código morre sozinho;
  TENTATIVAS   cinco erros e o código morre, obrigando novo envio;
  ESPERA       um minuto entre envios, para não virar máquina de SMS.

Os três juntos deixam a adivinhação inviável (cinco tentativas em dez
minutos, por envio) e protegem a conta do dono do número contra alguém
que o use para gerar mensagens.

O CÓDIGO MORRE AO SER USADO
---------------------------
Confirmar apaga o registro e grava a data em `User.phone_verified_at`. O
mesmo código não vale duas vezes, e trocar o telefone no Perfil apaga a
confirmação (`esquecer`) -- herdar a confirmação do número anterior faria
a marca dizer algo falso, exatamente como no e-mail.
"""

import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts import sms
from apps.accounts.models import ConfirmacaoDeTelefone

DIGITOS = 6
VALIDADE = timedelta(minutes=10)
MAX_TENTATIVAS = 5
ESPERA_ENTRE_ENVIOS = timedelta(seconds=60)


# ---------------------------------------------------------------------------
# O que pode dar errado -- nomes, e não strings soltas pelas views
# ---------------------------------------------------------------------------

ENVIADO = "enviado"
SEM_TELEFONE = "sem_telefone"
JA_CONFIRMADO = "ja_confirmado"
MUITO_CEDO = "muito_cedo"
FALHA_NO_ENVIO = "falha_no_envio"

CONFIRMADO = "confirmado"
SEM_CODIGO = "sem_codigo"
EXPIRADO = "expirado"
TENTATIVAS_ESGOTADAS = "tentativas_esgotadas"
CODIGO_ERRADO = "codigo_errado"
TELEFONE_MUDOU = "telefone_mudou"


def _novo_codigo():
    """Seis dígitos sorteados por `secrets` -- nunca por `random`."""
    return f"{secrets.randbelow(10**DIGITOS):0{DIGITOS}d}"


def _mensagem(codigo, nome_do_site):
    return _(
        "%(site)s: seu código de confirmação é %(codigo)s. "
        "Ele vale por 10 minutos."
    ) % {"site": nome_do_site, "codigo": codigo}


def pode_enviar(user, agora=None):
    """
    Já se pode (re)enviar um código para esta conta?

    Falso enquanto a espera entre envios não passar -- é o que impede
    que o botão de reenviar vire um disparador de SMS.
    """
    registro = ConfirmacaoDeTelefone.objects.filter(user=user).first()
    if registro is None:
        return True
    agora = agora or timezone.now()
    return agora - registro.sent_at >= ESPERA_ENTRE_ENVIOS


def enviar(user, nome_do_site=""):
    """
    Gera um código novo, guarda o hash dele e manda para o telefone da
    conta. Devolve um dos nomes do módulo (`ENVIADO`, `MUITO_CEDO`...).

    Cada envio SUBSTITUI o código anterior: dois códigos válidos ao
    mesmo tempo dobrariam a superfície de adivinhação sem servir para
    nada -- quem pediu de novo vai usar o último que chegou.
    """
    if user.telefone_confirmado:
        return JA_CONFIRMADO
    if not user.phone:
        return SEM_TELEFONE
    if not pode_enviar(user):
        return MUITO_CEDO

    codigo = _novo_codigo()
    agora = timezone.now()
    ConfirmacaoDeTelefone.objects.update_or_create(
        user=user,
        defaults={
            "phone": user.phone,
            "code_hash": make_password(codigo),
            "sent_at": agora,
            "expires_at": agora + VALIDADE,
            "attempts": 0,
        },
    )
    if not sms.enviar(user.phone, _mensagem(codigo, nome_do_site)):
        return FALHA_NO_ENVIO
    return ENVIADO


def conferir(user, codigo):
    """
    Confere o código digitado. Devolve um dos nomes do módulo.

    Confirmar apaga o registro: o código é de uso único, e o que fica é
    a data em `User.phone_verified_at`.
    """
    if user.telefone_confirmado:
        return JA_CONFIRMADO

    registro = ConfirmacaoDeTelefone.objects.filter(user=user).first()
    if registro is None:
        return SEM_CODIGO
    if registro.phone != user.phone:
        # O código provaria a posse do número ANTERIOR.
        registro.delete()
        return TELEFONE_MUDOU
    if registro.expirado:
        registro.delete()
        return EXPIRADO
    if registro.attempts >= MAX_TENTATIVAS:
        registro.delete()
        return TENTATIVAS_ESGOTADAS

    if not check_password((codigo or "").strip(), registro.code_hash):
        registro.attempts += 1
        registro.save(update_fields=["attempts"])
        if registro.attempts >= MAX_TENTATIVAS:
            registro.delete()
            return TENTATIVAS_ESGOTADAS
        return CODIGO_ERRADO

    registro.delete()
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at"])
    return CONFIRMADO


def esquecer(user):
    """
    Desfaz a confirmação -- chamado quando o telefone da conta muda.

    Apaga também o código pendente: ele valia para o número anterior.
    """
    ConfirmacaoDeTelefone.objects.filter(user=user).delete()
    if user.phone_verified_at is None:
        return False
    user.phone_verified_at = None
    user.save(update_fields=["phone_verified_at"])
    return True
