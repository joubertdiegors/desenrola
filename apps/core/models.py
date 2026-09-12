"""Modelos base compartilhados por todos os apps do projeto."""

from django.db import models
from django.utils.translation import gettext_lazy as _


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
