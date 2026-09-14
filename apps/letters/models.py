"""
Cartas geradas.

Letter e o registro de uma Carta Convite gerada por um usuario. Guarda:

  - os dados que o usuario preencheu (`data`);
  - uma copia congelada de tudo que influenciou o resultado (`snapshot`) —
    para que o documento continue reproduzivel mesmo que o usuario edite
    o perfil ou o modelo mude depois;
  - o vinculo protegido com o `DocumentTemplate` usado (nunca apagavel
    enquanto existir uma Letter apontando para ele — ver
    apps/doctemplates/models.py).
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class DocumentSnapshotImmutableError(RuntimeError):
    """
    A carta ja capturou o modelo estrutural (`DocumentTemplate`) que vai
    gerar o documento: a partir dai, `document_template`,
    `document_snapshot` e `document_snapshot_hash` nao podem mais mudar.

    Levantado por `Letter.save()` -- vale para qualquer caminho de codigo
    que tente reescrever esses tres campos, nao so a view de
    finalizacao. E erro de uso indevido (RuntimeError), no mesmo espirito
    de `DocumentTemplateLockedError` em apps.doctemplates.models.
    """


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
    language = models.CharField(_("idioma"), max_length=8, choices=settings.LANGUAGES)

    # Numero/referencia legivel para o usuario (ex.: em e-mails, no nome do
    # arquivo). Gerado automaticamente se nao vier definido.
    reference = models.CharField(_("referência"), max_length=40, unique=True, editable=False)

    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.DRAFT
    )

    # Dados preenchidos pelo usuario no formulario (estrutura livre; o
    # schema efetivo vem de document_template.field_schema).
    data = models.JSONField(_("dados preenchidos"), default=dict, blank=True)

    # Copia congelada de tudo que influenciou a geracao (dados do usuario
    # no momento, configuracao da versao, etc.) — garante reprodutibilidade
    # historica mesmo que o perfil do usuario ou o modelo mudem depois.
    snapshot = models.JSONField(_("snapshot da geração"), default=dict, blank=True)

    # O modelo oficial que esta carta usa. Resolvido pelo IDIOMA, em
    # `services.official_document_template()` -- nunca escolhido pelo
    # cliente.
    #
    # Pode ser trocado enquanto a carta ainda nao tem snapshot capturado
    # (trocar o idioma na etapa 5 troca o modelo junto). A partir do
    # momento em que `document_snapshot_hash` deixa de estar vazio -- o
    # que acontece na finalizacao, via
    # `services.capture_document_template_snapshot()` -- os tres campos
    # ficam congelados: `save()` recusa qualquer tentativa de mudar
    # qualquer um deles (`DocumentSnapshotImmutableError`).
    document_template = models.ForeignKey(
        "doctemplates.DocumentTemplate",
        on_delete=models.PROTECT,
        related_name="letters",
        verbose_name=_("modelo"),
    )
    # Copia profunda e congelada de tudo que o renderer generico
    # (apps.doctemplates.services.pdf) precisa para reproduzir o
    # documento -- field_schema, layout, a pagina do tipo de documento e
    # o idioma do modelo. Ver apps.doctemplates.services.snapshot.
    document_snapshot = models.JSONField(
        _("snapshot do modelo estrutural"), default=dict, blank=True
    )
    # SHA-256 do conteudo ESTRUTURAL de `document_snapshot` (sem o
    # "captured_at"), em JSON canonico -- permite conferir depois que o
    # snapshot nao foi alterado, sem comparar o dict inteiro.
    document_snapshot_hash = models.CharField(
        _("hash do snapshot estrutural"), max_length=64, blank=True
    )

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
        if not self.reference:
            self.reference = self._build_reference()
        if self.pk:
            self._recusar_reescrita_do_snapshot_estrutural()
        super().save(*args, **kwargs)

    def _recusar_reescrita_do_snapshot_estrutural(self):
        """
        A regra vale pelo que esta GRAVADO, nao pelo que se esta tentando
        gravar -- mesmo padrao de `DocumentTemplate.save()`. So passa a
        valer quando `document_snapshot_hash` ja estiver preenchido: ate
        la (rascunho, sem snapshot capturado) `document_template` pode
        ser trocado livremente.
        """
        anterior = (
            Letter.objects.filter(pk=self.pk)
            .values("document_template_id", "document_snapshot", "document_snapshot_hash")
            .first()
        )
        if not anterior or not anterior["document_snapshot_hash"]:
            return
        mudou = (
            anterior["document_template_id"] != self.document_template_id
            or anterior["document_snapshot"] != self.document_snapshot
            or anterior["document_snapshot_hash"] != self.document_snapshot_hash
        )
        if mudou:
            raise DocumentSnapshotImmutableError(
                "Esta carta já capturou um modelo estrutural; document_template, "
                "document_snapshot e document_snapshot_hash não podem mais ser "
                "alterados."
            )

    def _build_reference(self):
        # `created_at` (auto_now_add) so existe apos o INSERT, entao usamos
        # a hora atual — e apenas um prefixo legivel, nao precisa ser
        # identico ao timestamp gravado.
        stamp = self.generated_at or timezone.now()
        return f"DSR-{stamp:%Y%m}-{str(self.uuid)[:8].upper()}"


class DocumentSnapshotAssetMissingError(RuntimeError):
    """
    O layout que estava sendo congelado referencia um `content.Asset`
    que nao existe. Capturar assim produziria uma carta irreproduzivel
    desde o nascimento -- melhor recusar a finalizacao agora do que
    descobrir na geracao do PDF.
    """


class MissingDocumentSnapshotError(RuntimeError):
    """
    `render_letter()` foi chamada numa carta sem `document_snapshot`.

    E erro de programacao: o snapshot e capturado na finalizacao, antes
    de qualquer geracao de PDF. Chegar aqui significa ter pulado esse
    passo.
    """


class LetterRenderError(RuntimeError):
    """
    O renderer generico (apps.doctemplates.services.pdf) nao conseguiu
    produzir o PDF a partir do `document_snapshot`: campo sem valor,
    asset ausente, pagina invalida, fonte sem face embutida, layout
    corrompido, etc.

    Um tipo SO, que embrulha qualquer erro daquele modulo
    (`__cause__` guarda a causa original) -- para `views._finalize()`
    conhecer um unico tipo de excecao do pipeline novo, em vez de se
    acoplar a toda a taxonomia de erros de `services.pdf`.
    """


class DefaultDocumentTemplateMissingError(RuntimeError):
    """
    O modelo estrutural oficial do idioma pedido nao existe ou esta
    inativo -- levantado por `services.official_document_template()`.

    A migration de semeadura (`doctemplates.0010`) sempre cria os quatro
    oficiais (`carta-convite-fr/nl/en/pt`), todos ativos: chegar aqui
    significa banco fora do estado esperado (semeadura nao rodou, ou um
    administrador desativou/apagou o registro por engano), nao "aquele
    idioma ainda nao tem conteudo pronto" -- esse segundo caso e tratado
    a parte, sem levantar (ver o docstring da funcao).

    `services.start_draft()` resolve o modelo ANTES de criar a `Letter`:
    se isto for levantado, nenhuma carta chega a existir -- nunca uma
    parcialmente criada, presa sem `document_template` por um bug de
    infraestrutura.
    """


class LetterAsset(models.Model):
    """
    Vinculo entre uma carta finalizada e cada `content.Asset` que o seu
    `document_snapshot` precisa para ser reproduzido (Etapa 3.5.1,
    integridade de assets).

    O snapshot congela o LAYOUT, mas o layout so guarda `asset_id` --
    os bytes da imagem continuam num unico lugar, o Asset. Duplicar o
    arquivo em cada carta seria a solucao facil e errada; a certa e
    garantir que o Asset original nao possa sumir nem mudar: a FK
    `asset` e PROTECT (exclusao recusada pelo ORM em qualquer caminho) e
    `Asset.save()` recusa trocar o arquivo enquanto houver uma linha aqui.

    Criado em `services.capture_document_template_snapshot()`, na MESMA
    transacao do snapshot; apagado junto com a carta (CASCADE). Nunca
    editado a mao.
    """

    letter = models.ForeignKey(
        Letter,
        on_delete=models.CASCADE,
        related_name="asset_links",
        verbose_name=_("carta"),
    )
    asset = models.ForeignKey(
        "content.Asset",
        on_delete=models.PROTECT,
        related_name="letter_references",
        verbose_name=_("imagem"),
    )

    class Meta:
        verbose_name = _("imagem usada por carta")
        verbose_name_plural = _("imagens usadas por cartas")
        constraints = [
            models.UniqueConstraint(fields=["letter", "asset"], name="uniq_letter_asset")
        ]

    def __str__(self):
        return f"{self.letter_id} -> asset #{self.asset_id}"
