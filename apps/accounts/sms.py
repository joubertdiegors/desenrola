"""
A saída de SMS do projeto -- hoje um registro no log, amanhã um provedor.

POR QUE EXISTE UMA CAMADA AQUI
------------------------------
A confirmação de telefone (`accounts.confirmacao_de_telefone`) precisa
entregar um código AO APARELHO -- é isso que prova a posse do número. O
projeto ainda não tem contrato com provedor de SMS, e inventar um agora
seria decidir por quem paga a conta.

A saída é a MESMA do e-mail antes de existir a tela de SMTP: uma função
única (`enviar`), um backend trocável por configuração, e um padrão que
apenas ESCREVE a mensagem no log do servidor. O fluxo inteiro funciona
em desenvolvimento e homologação; ligar um provedor de verdade é trocar
`SMS_BACKEND` -- nenhuma linha de quem chama muda.

O QUE ISTO NÃO FAZ
------------------
Não finge ter enviado. `enviar` devolve se a entrega foi aceita pelo
backend, e o backend de log deixa claro, no próprio log, que a mensagem
não saiu para nenhuma operadora. Enquanto não houver provedor
configurado, a política "exigir confirmação de e-mail e telefone" só
deve ser ligada por quem tem acesso ao log -- está escrito na tela do
Backoffice.
"""

import logging

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

PADRAO = "apps.accounts.sms.BackendDeLog"


class BackendDeSms:
    """O contrato: receber número e texto, dizer se a entrega foi aceita."""

    def enviar(self, numero, mensagem):  # pragma: no cover - interface
        raise NotImplementedError


class BackendDeLog(BackendDeSms):
    """
    Escreve no log do servidor, como o backend de console do e-mail.

    É o padrão de desenvolvimento e o comportamento de reserva: o código
    existe, é verificável e chega a quem lê o log -- e nunca a uma
    operadora.
    """

    def enviar(self, numero, mensagem):
        # WARNING, e nao INFO: e o nivel que aparece no console do
        # desenvolvimento (onde o logging padrao do Django descarta
        # INFO de loggers do projeto) E no log de producao. Um codigo
        # que nao chegou a operadora nenhuma e, de fato, um aviso.
        logger.warning("SMS (nao enviado a operadora nenhuma) para %s: %s", numero, mensagem)
        return True


def backend():
    """O backend configurado em `settings.SMS_BACKEND`, ou o de log."""
    return import_string(getattr(settings, "SMS_BACKEND", PADRAO))()


def enviar(numero, mensagem):
    """
    Manda `mensagem` para `numero`. Devolve se a entrega foi aceita.

    Nunca levanta: uma indisponibilidade do provedor não pode virar tela
    de erro no meio de uma confirmação -- é a mesma decisão de
    `confirmacao.enviar` para o e-mail. Quem chama decide o que dizer
    quando o retorno é falso, e o botão de reenviar continua ali.
    """
    if not numero:
        return False
    try:
        return bool(backend().enviar(numero, mensagem))
    except Exception:  # noqa: BLE001 -- um provedor fora do ar não derruba a tela
        logger.exception("Falha ao enviar SMS para %s", numero)
        return False
