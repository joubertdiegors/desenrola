"""
Envio de e-mail conforme o que o Backoffice tem cadastrado.

O DESENHO EM UMA FRASE
----------------------
`EMAIL_BACKEND` do projeto é o `ConfiguredEmailBackend` daqui: a cada
envio ele olha `core.EmailSettings` e, se houver configuração ATIVA,
fala SMTP com ela; se não houver, entrega ao backend de reserva do
ambiente (console em desenvolvimento, `EMAIL_URL` em produção).

Assim `send_mail()` e a recuperação de senha continuam sendo o código
de sempre -- ninguém precisa saber que existe configuração no banco --
e o interruptor do Backoffice passa a significar alguma coisa de fato.

O QUE NUNCA SAI DAQUI
---------------------
A senha. Ela é lida na hora de montar a conexão e some com ela. As
mensagens de erro são traduzidas de exceções para frases (`_motivo`):
um `str(erro)` cru de `smtplib` carrega a resposta do servidor, que
pode repetir o usuário -- e acabaria num log ou na tela.
"""

import logging
import smtplib
import ssl

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.mail.backends.base import BaseEmailBackend
from django.utils.translation import gettext_lazy as _

from .models import EmailSettings

logger = logging.getLogger(__name__)

BACKEND_SMTP = "django.core.mail.backends.smtp.EmailBackend"

ASSUNTO_DO_TESTE = _("Teste de envio — Desenrola")
CORPO_DO_TESTE = _(
    "Se você está lendo isto, a configuração de e-mail do Desenrola está "
    "funcionando.\n\n"
    "Esta mensagem foi disparada pelo Backoffice, na tela de configuração "
    "de e-mail."
)


def configuracao():
    """
    A configuração de e-mail (registro único), criando-a na primeira vez.

    Mesmo padrão de `letters.lifecycle.policy()`: quem precisa da
    configuração pede aqui, e nunca constrói um `EmailSettings()` novo.
    """
    objeto, _criado = EmailSettings.objects.get_or_create(pk=EmailSettings.SINGLETON_ID)
    return objeto


def conexao(config, **kwargs):
    """
    Uma conexão SMTP montada a partir de `config`.

    `username`/`password` vão como STRING VAZIA quando não há -- e não
    como `None`. No backend do Django `None` não quer dizer "não
    autentique": quer dizer "use `settings.EMAIL_HOST_USER`". Em
    produção, onde `EMAIL_URL` existe como reserva, isso faria esta
    conexão pegar em silêncio a credencial do ambiente. Vazio é o que
    de fato pula o `login()`.
    """
    return get_connection(
        backend=BACKEND_SMTP,
        host=config.host,
        port=config.port,
        username=config.username,
        password=config.senha() or "",
        use_tls=config.security == EmailSettings.Security.TLS,
        use_ssl=config.security == EmailSettings.Security.SSL,
        timeout=EmailSettings.TEMPO_LIMITE,
        **kwargs,
    )


def _reserva(fail_silently):
    """
    O backend para onde as mensagens vão sem configuração ativa.

    A guarda contra apontar para si mesmo não é paranoia: `dev.py` e
    `prod.py` definem esta variável, e um valor copiado por engano faria
    o backend chamar a si próprio até estourar a pilha -- em produção,
    no meio de um envio.
    """
    caminho = getattr(settings, "EMAIL_FALLBACK_BACKEND", "") or BACKEND_SMTP
    if caminho.endswith("ConfiguredEmailBackend"):
        raise ValueError(
            "EMAIL_FALLBACK_BACKEND nao pode ser o proprio ConfiguredEmailBackend."
        )
    return get_connection(backend=caminho, fail_silently=fail_silently)


class ConfiguredEmailBackend(BaseEmailBackend):
    """
    O backend de e-mail do projeto: delega para o SMTP do Backoffice ou
    para a reserva do ambiente.

    A decisão é tomada A CADA ENVIO, não na inicialização: mudar a
    configuração na tela passa a valer na mensagem seguinte, sem
    reiniciar a aplicação -- que é o ponto de ter isto no banco.
    """

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        config = configuracao()
        if not config.pronta_para_enviar():
            return _reserva(self.fail_silently).send_messages(email_messages)

        self._aplicar_remetente(config, email_messages)
        return conexao(config, fail_silently=self.fail_silently).send_messages(email_messages)

    @staticmethod
    def _aplicar_remetente(config, email_messages):
        """
        Troca o remetente PADRÃO pelo que está cadastrado.

        Só quem não escolheu: mensagem que define o próprio `from_email`
        pediu aquele endereço de propósito e continua com ele. O que se
        substitui é o `DEFAULT_FROM_EMAIL` das settings, que é o valor
        de quem não opinou.
        """
        remetente = config.remetente()
        if not remetente:
            return
        padrao = settings.DEFAULT_FROM_EMAIL
        for mensagem in email_messages:
            if not mensagem.from_email or mensagem.from_email == padrao:
                mensagem.from_email = remetente


# ---------------------------------------------------------------------------
# O teste de envio
# ---------------------------------------------------------------------------


def _motivo(erro):
    """
    Uma frase que explica a falha SEM repetir credencial nenhuma.

    Traduz a exceção em vez de mostrá-la: `str(erro)` de `smtplib` traz
    a resposta do servidor, que costuma incluir o usuário -- e daqui o
    texto vai para a tela e para o log.
    """
    if isinstance(erro, smtplib.SMTPAuthenticationError):
        return _("O servidor recusou o usuário ou a senha.")
    if isinstance(erro, smtplib.SMTPSenderRefused):
        return _("O servidor recusou o remetente configurado.")
    if isinstance(erro, smtplib.SMTPRecipientsRefused):
        return _("O servidor recusou o endereço de destino.")
    if isinstance(erro, ssl.SSLError):
        return _("Falha no TLS/SSL. Confira a opção de segurança e a porta.")
    if isinstance(erro, smtplib.SMTPNotSupportedError):
        return _("O servidor não aceita esta opção de segurança nesta porta.")
    # Antes do OSError, e não depois: `smtplib.SMTPException` HERDA de
    # `OSError`, e na ordem inversa toda falha do protocolo virava
    # "não foi possível conectar" -- que manda o administrador conferir
    # o host quando o problema era outro.
    if isinstance(erro, smtplib.SMTPException):
        return _("O servidor de e-mail recusou a mensagem.")
    if isinstance(erro, (TimeoutError, ConnectionError, OSError)):
        return _("Não foi possível conectar ao servidor. Confira o endereço e a porta.")
    return _("Falha inesperada ao enviar. Confira os dados e tente de novo.")


def enviar_teste(config, destino):
    """
    Manda uma mensagem de teste para `destino`.

    Devolve `(ok, motivo)`: `motivo` é `None` quando deu certo e uma
    frase pronta para a tela quando não deu.

    Usa a configuração RECÉM-SALVA, ativa ou não: testar antes de ligar
    é justamente a ordem certa de fazer as coisas.
    """
    try:
        with conexao(config) as ligacao:
            EmailMessage(
                subject=str(ASSUNTO_DO_TESTE),
                body=str(CORPO_DO_TESTE),
                from_email=config.remetente() or None,
                to=[destino],
                connection=ligacao,
            ).send(fail_silently=False)
    except Exception as erro:  # noqa: BLE001 -- qualquer falha vira uma frase
        # Só a classe e o servidor. Nunca `str(erro)`, nunca usuário,
        # nunca senha.
        logger.warning(
            "Falha no teste de envio de e-mail: %s (host=%s porta=%s)",
            type(erro).__name__,
            config.host,
            config.port,
        )
        return False, _motivo(erro)
    return True, None
