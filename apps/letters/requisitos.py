"""
Quem pode gerar uma Carta Convite -- a pergunta, num lugar só.

A REGRA
-------
O Backoffice (Wizzard › Validação para gerar carta convite) escolhe uma
de três políticas, gravadas em `letters.LetterPolicy`:

  NENHUMA            qualquer conta gera -- o comportamento de sempre;
  EMAIL              é preciso ter o e-mail confirmado;
  EMAIL_E_TELEFONE   é preciso ter e-mail e telefone confirmados.

O padrão é `NENHUMA`: ligar a barreira é uma decisão explícita de quem
administra, e até lá nada muda para ninguém.

UM LUGAR SÓ, TRÊS CONSUMIDORES
------------------------------
A mesma resposta serve ao servidor (`exige_requisitos_para_gerar`, que
tranca as rotas do assistente), à interface (a etiqueta de template
`{% requisitos_de_geracao %}`, que desabilita o botão e mostra o aviso) e
aos testes. Repetir `if user.email_confirmado` por view e por template
seria a mesma regra em cinco lugares, envelhecendo em cinco direções.

O QUE ESTA REGRA NÃO FAZ
------------------------
Não impede entrar, ver o painel, abrir o histórico nem baixar uma carta
já gerada: o que ela protege é a GERAÇÃO. E não olha `bool(user.phone)`
em lugar nenhum -- telefone preenchido não é telefone confirmado (ver
`accounts.confirmacao_de_telefone`).

SUPERUSUÁRIO NÃO TEM PASSE LIVRE
--------------------------------
A política vale para toda conta que gera carta, inclusive a de quem
administra: é uma regra de negócio sobre os dados da própria conta, e não
uma permissão. Um administrador destrancado veria o assistente funcionar
enquanto todo o resto do mundo está bloqueado -- e concluiria que a
barreira não está valendo. O Backoffice continua intocado: quem
administra muda a política na tela de sempre, com a permissão de sempre.
"""

from dataclasses import dataclass
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from apps.letters import lifecycle
from apps.letters.models import LetterPolicy

# O destino de quem esbarra na barreira: a tela que tem o botão, o aviso
# e o caminho para confirmar.
DESTINO_DO_BLOQUEIO = "core:dashboard"


@dataclass(frozen=True)
class Requisitos:
    """
    O que falta para ESTA conta gerar uma carta, segundo a política
    vigente. Objeto pequeno de propósito: template não faz conta.
    """

    politica: str
    falta_email: bool
    falta_telefone: bool

    @property
    def pode_gerar(self):
        return not (self.falta_email or self.falta_telefone)

    @property
    def mensagem(self):
        """
        A frase em vermelho, dizendo exatamente o que falta -- vazia
        quando não falta nada.
        """
        if self.falta_email and self.falta_telefone:
            return _("Confirme seu e-mail e seu telefone para gerar a carta convite.")
        if self.falta_email:
            return _("Confirme seu e-mail para gerar a carta convite.")
        if self.falta_telefone:
            return _("Confirme seu telefone para gerar a carta convite.")
        return ""

    @property
    def exige_telefone(self):
        """A política em vigor pede telefone? (a tela decide o que oferecer)"""
        return self.politica == LetterPolicy.GenerationRequirement.EMAIL_E_TELEFONE


LIBERADO = Requisitos(
    politica=LetterPolicy.GenerationRequirement.NENHUMA,
    falta_email=False,
    falta_telefone=False,
)


def requisitos_para_gerar(user):
    """
    Os requisitos pendentes de `user`, já cruzados com a política.

    Visitante anônimo recebe `LIBERADO`: quem tranca o assistente para
    quem não entrou é o `login_required` de sempre, e não esta regra --
    dois guardas para a mesma porta se contradizem um dia.
    """
    if user is None or not user.is_authenticated:
        return LIBERADO

    politica = lifecycle.policy().generation_requirement
    exige_email = politica in (
        LetterPolicy.GenerationRequirement.EMAIL,
        LetterPolicy.GenerationRequirement.EMAIL_E_TELEFONE,
    )
    exige_telefone = politica == LetterPolicy.GenerationRequirement.EMAIL_E_TELEFONE

    return Requisitos(
        politica=politica,
        falta_email=exige_email and not user.email_confirmado,
        falta_telefone=exige_telefone and not user.telefone_confirmado,
    )


def exige_requisitos_para_gerar(view):
    """
    Tranca uma rota do assistente no SERVIDOR.

    Esconder o botão não protege nada -- a URL continua sendo digitável,
    e é por ela que alguém tentaria. Sem os requisitos, a pessoa volta ao
    painel com a mesma frase que o aviso mostra: o bloqueio explica-se
    sozinho, em vez de parecer um erro.

    Fica DEPOIS de `login_required` na pilha de decoradores, para que
    quem não entrou veja a tela de login, e não uma mensagem sobre
    confirmar e-mail.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        pendentes = requisitos_para_gerar(request.user)
        if not pendentes.pode_gerar:
            messages.error(request, pendentes.mensagem)
            return redirect(DESTINO_DO_BLOQUEIO)
        return view(request, *args, **kwargs)

    return wrapper
