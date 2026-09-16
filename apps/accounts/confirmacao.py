"""
A confirmação de e-mail: o link que prova que o endereço é de quem diz.

POR QUE ISTO EXISTE
-------------------
Até aqui qualquer endereço digitado no cadastro virava conta. Um erro de
digitação (`gmial.com`) deixava a pessoa sem nenhum caminho de volta --
a recuperação de senha mandaria o link para o endereço errado. E um
endereço de outra pessoa virava uma conta em nome dela.

O TOKEN É O DO DJANGO, COM OUTRO CONTEÚDO
-----------------------------------------
`PasswordResetTokenGenerator` já resolve o problema difícil: assina com
a `SECRET_KEY`, carrega o instante da emissão e expira sozinho. Nada
aqui inventa criptografia -- só se troca O QUE ENTRA NO HASH:

  pk                 de quem é o link;
  email              trocar o endereço invalida o link do anterior;
  email_verified_at  confirmar invalida o link -- ele vale UMA vez.

É exatamente a mesma técnica do token de senha (que usa a senha e o
`last_login` pelo mesmo motivo), aplicada aos campos que importam aqui.

QUEM NÃO CONFIRMA NÃO PERDE A CONTA
-----------------------------------
Confirmar não é exigência para entrar nem para gerar carta -- isso
trancaria fora todo mundo que já tem conta, e não foi o que se pediu.
O que muda é que a conta não confirmada é VISÍVEL: um aviso na área
logada, com o botão de reenviar, e uma marca na ficha do Backoffice.

O PRAZO
-------
`PASSWORD_RESET_TIMEOUT` -- três dias, o mesmo do link de senha. Um
segundo ajuste para a mesma ideia ("quanto vale um link que mandamos
por e-mail") seria uma decisão a mais para manter em dia.
"""

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.content.context_processors import globais


class GeradorDeTokenDeEmail(PasswordResetTokenGenerator):
    """
    O token do link de confirmação.

    `_make_hash_value` é o único ponto que muda: a assinatura, o prazo e
    a comparação em tempo constante continuam sendo os do Django.
    """

    def _make_hash_value(self, user, timestamp):
        confirmado = "" if user.email_verified_at is None else user.email_verified_at
        return f"{user.pk}{user.email}{confirmado}{timestamp}"


token_de_email = GeradorDeTokenDeEmail()


def _endereco_da_logomarca(request, site):
    """
    O endereço ABSOLUTO da logomarca, ou vazio.

    Absoluto porque um e-mail não tem página de origem: `/media/...` não
    resolve em lugar nenhum dentro do cliente de e-mail. Vazio quando não
    há logomarca -- o template cai na marca escrita, como o site faz.
    """
    if not (site and site.logo and site.logo.file):
        return ""
    return request.build_absolute_uri(site.logo.file.url)


def uma_linha(texto):
    """
    O assunto, achatado numa linha só.

    Quebra de linha num cabeçalho de e-mail é INJEÇÃO DE CABEÇALHO: quem
    controlasse o texto poderia acrescentar um `Bcc:`. O Django recusa a
    mensagem inteira quando encontra uma, o que transformaria um
    template com uma linha a mais numa falha de envio silenciosa.

    O template de assunto de hoje já é uma linha só. Isto é o cinto de
    segurança para o dia em que alguém puser um `{% comment %}` nele --
    e é função própria, e não três caracteres dentro de `enviar`, para
    poder ser testado.
    """
    return "".join((texto or "").splitlines()).strip()


def contexto(request, user):
    """
    O que os três templates do e-mail leem.

    Montado AQUI, com request, e não por processador de contexto: o
    corpo é renderizado por `render_to_string`, onde processador de
    contexto não roda -- é a mesma armadilha do e-mail de recuperação,
    e a mesma saída.
    """
    site = globais()
    return {
        "user": user,
        "email": user.email,
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": token_de_email.make_token(user),
        "protocol": "https" if request.is_secure() else "http",
        "domain": request.get_host(),
        "nome_do_site": site.name,
        "cor_principal": site.primary_color,
        "logo_url": _endereco_da_logomarca(request, site),
    }


def enviar(request, user):
    """
    Manda o convite de confirmação. Devolve se saiu.

    `fail_silently=True` de propósito: o cadastro NÃO pode quebrar
    porque o servidor de e-mail está fora do ar. A conta já existe, a
    pessoa já está dentro, e o botão de reenviar continua ali. Uma
    exceção aqui transformaria uma indisponibilidade de e-mail numa tela
    de erro depois de a conta ter sido criada -- o pior dos dois mundos.
    """
    if not user.email or user.email_confirmado:
        return False

    dados = contexto(request, user)
    assunto = uma_linha(
        render_to_string("accounts/email_confirmation_subject.txt", dados)
    )
    texto = render_to_string("accounts/email_confirmation_email.txt", dados)

    mensagem = EmailMultiAlternatives(assunto, texto, to=[user.email])
    mensagem.attach_alternative(
        render_to_string("accounts/email_confirmation_email.html", dados), "text/html"
    )
    return bool(mensagem.send(fail_silently=True))


def confirmar(user):
    """
    Marca o endereço como confirmado. Devolve se mudou alguma coisa.

    Confirmar duas vezes não é erro -- é o link aberto de novo, ou o
    pré-carregador do cliente de e-mail passando por ele. O segundo
    acesso não reescreve a data: a primeira confirmação é a que vale, e
    reescrevê-la invalidaria o token de um jeito difícil de explicar.
    """
    if user.email_confirmado:
        return False
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at"])
    return True


def esquecer(user):
    """
    Desfaz a confirmação -- chamado quando o e-mail da conta muda.

    Sem isto, trocar o endereço herdaria a confirmação do anterior, e a
    marca de "confirmado" passaria a dizer algo falso.
    """
    if user.email_verified_at is None:
        return False
    user.email_verified_at = None
    user.save(update_fields=["email_verified_at"])
    return True
