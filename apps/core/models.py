"""Modelos base compartilhados por todos os apps do projeto."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class BackofficeAccess(models.Model):
    """
    Portador da permissao de entrar no Backoffice. NAO tem tabela.

    O Backoffice e uma area do produto, nao um registro: nao ha o que
    guardar. Mas o Django so sabe criar permissao pendurada num modelo,
    entao este existe apenas para declarar `access_backoffice` --
    `managed = False` (nenhuma tabela, nenhuma coluna) e
    `default_permissions = ()` (sem add/change/delete/view, que nao
    significariam nada aqui).

    POR QUE UMA PERMISSAO, E NAO `is_staff`
    ---------------------------------------
    `is_staff` e a flag do Django Admin, que este projeto nao usa como
    backoffice. Uma permissao de verdade entra no mesmo sistema que ja
    guarda `letters.view_all_letters`: da para conceder por grupo,
    aparece na administracao de usuarios e pode ser retirada de alguem
    sem mexer em mais nada. Superusuario continua passando por tudo, por
    como `has_perm` funciona.

    Quem ja era `is_staff` recebeu a permissao na migration que a criou
    (`core.0001`), para ninguem perder acesso na atualizacao.
    """

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [("access_backoffice", _("Pode acessar o Backoffice"))]
        verbose_name = _("acesso ao Backoffice")
        verbose_name_plural = _("acesso ao Backoffice")


class TimeStampedModel(models.Model):
    """
    Base abstrata com marcas de tempo.

    Todo modelo persistente do projeto deve herdar daqui, para que
    auditoria e ordenacao por data sejam uniformes em todo o sistema.
    """

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        abstract = True
