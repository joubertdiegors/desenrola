"""
Cartas geradas.

Letter e o registro de uma Carta Convite gerada por um usuario. Guarda:

  - os dados que o usuario preencheu (`data`);
  - uma copia congelada de tudo que influenciou o resultado (`snapshot`) —
    para que o documento continue reproduzivel mesmo que o usuario edite
    o perfil ou o modelo mude depois;
  - o vinculo protegido com a TemplateVersion exata usada (nunca apagavel
    enquanto existir uma Letter apontando para ela — ver
    apps/doctemplates/models.py).

Ainda NAO implementados nesta fase: o formulario real, a geracao do PDF e
o dashboard. Este modulo so estabelece a estrutura de dados e as regras de
propriedade/privacidade (quem pode ver o que).
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class LetterQuerySet(models.QuerySet):
    def visible_to(self, user):
        """
        Cartas que `user` pode ver: as suas proprias sempre; todas, se
        tiver a permissao `letters.view_all_letters` (superusuarios a tem
        automaticamente, por como o Django resolve `has_perm`).
        """
        if not user or not user.is_authenticated:
            return self.none()
        if user.has_perm("letters.view_all_letters"):
            return self
        return self.filter(user=user)


class Letter(TimeStampedModel):
    """Uma Carta Convite gerada (ou em geracao) por um usuario."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Rascunho")
        GENERATED = "generated", _("Gerada")
        COMPLETED = "completed", _("Concluída")
        CANCELLED = "cancelled", _("Cancelada")

    # Identificador publico: usado em URLs/links compartilhaveis, para nao
    # expor a sequencia do id interno nem permitir adivinhar outras cartas.
    uuid = models.UUIDField(
        _("identificador público"), default=uuid.uuid4, editable=False, unique=True
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="letters",
        verbose_name=_("usuário"),
    )
    template = models.ForeignKey(
        "doctemplates.LetterTemplate",
        on_delete=models.PROTECT,
        related_name="letters",
        verbose_name=_("modelo"),
    )
    template_version = models.ForeignKey(
        "doctemplates.TemplateVersion",
        on_delete=models.PROTECT,
        related_name="letters",
        verbose_name=_("versão do modelo"),
    )
    language = models.CharField(_("idioma"), max_length=8, choices=settings.LANGUAGES)

    # Numero/referencia legivel para o usuario (ex.: em e-mails, no nome do
    # arquivo). Gerado automaticamente se nao vier definido.
    reference = models.CharField(_("referência"), max_length=40, unique=True, editable=False)

    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.DRAFT
    )

    # Dados preenchidos pelo usuario no formulario (estrutura livre; o
    # schema efetivo vem de template_version.field_schema).
    data = models.JSONField(_("dados preenchidos"), default=dict, blank=True)

    # Copia congelada de tudo que influenciou a geracao (dados do usuario
    # no momento, configuracao da versao, etc.) — garante reprodutibilidade
    # historica mesmo que o perfil do usuario ou o modelo mudem depois.
    snapshot = models.JSONField(_("snapshot da geração"), default=dict, blank=True)

    generated_at = models.DateTimeField(_("gerada em"), null=True, blank=True)

    # Arquivo privado: nunca por mapeamento estatico publico (ver
    # config/settings/base.py, secao de midia). A entrega sera por view
    # autenticada, na fase da geracao real.
    pdf_file = models.FileField(
        _("arquivo PDF"), upload_to="letters/%Y/%m/", blank=True, null=True
    )
    pdf_sha256 = models.CharField(_("SHA-256 do PDF"), max_length=64, blank=True)

    objects = LetterQuerySet.as_manager()

    class Meta:
        verbose_name = _("carta")
        verbose_name_plural = _("cartas")
        ordering = ["-created_at"]
        permissions = [
            ("view_all_letters", "Pode visualizar cartas de todos os usuários"),
        ]

    def __str__(self):
        return self.reference or str(self.uuid)

    def save(self, *args, **kwargs):
        if self.template_version_id and not self.template_id:
            self.template = self.template_version.template
        if not self.reference:
            self.reference = self._build_reference()
        super().save(*args, **kwargs)

    def _build_reference(self):
        # `created_at` (auto_now_add) so existe apos o INSERT, entao usamos
        # a hora atual — e apenas um prefixo legivel, nao precisa ser
        # identico ao timestamp gravado.
        stamp = self.generated_at or timezone.now()
        return f"DSR-{stamp:%Y%m}-{str(self.uuid)[:8].upper()}"
