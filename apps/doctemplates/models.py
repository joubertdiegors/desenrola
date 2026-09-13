"""
Modelos de documento e suas versoes.

Dois modelos, com uma separacao deliberada:

  - LetterTemplate e o "produto" logico (ex.: "Carta Convite — curta
    duracao, frances"). E editavel livremente enquanto nao tem versao
    publicada: nome, identificador, descricao, idioma, se esta ativo.

  - TemplateVersion e o "documento de verdade": a configuracao de campos
    que efetivamente gera as cartas. Uma vez publicada, e imutavel — isso
    e o que garante que uma carta gerada ha um ano continue reproduzivel
    exatamente como foi gerada, mesmo que o modelo evolua depois.

Cada LetterTemplate pode ter varias TemplateVersion; cada Letter (app
letters) se liga a uma TemplateVersion especifica, nunca ao LetterTemplate
diretamente para fins de reproducao — o vinculo com o "produto" serve so
para agrupar/listar.

Ainda NAO implementados nesta fase: o editor visual dos campos, o mapa de
posicoes no PDF oficial e a geracao do documento. Este modulo so estabelece
a estrutura de dados.
"""

import copy

from django.conf import settings
from django.db import models
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

from .layout_schema import validate_layout
from .schema import validate_field_schema
from .visual_schema import validate_visual_schema


class TemplateVersionImmutableError(RuntimeError):
    """
    Levantado ao tentar alterar dados estruturais de uma versao publicada,
    ou ao tentar excluir uma versao publicada.

    E um erro de programacao/uso indevido (nao uma ValidationError de
    formulario): a regra vale sempre, inclusive para codigo que grava
    direto no banco via `.save()`/`.delete()`, sem passar por um form.
    """


class LetterTemplate(TimeStampedModel):
    """
    Um modelo de Carta Convite (o "produto"), num idioma especifico.

    Diferentes idiomas da mesma carta oficial sao registros separados
    (ex.: "carta-convite-curta-duracao-fr" e "...-en"), porque o documento
    oficial em si muda de layout/texto por idioma — nao e uma traducao de
    string, e um PDF diferente.
    """

    name = models.CharField(_("nome"), max_length=150)
    slug = models.SlugField(_("identificador interno"), max_length=80, unique=True)
    description = models.TextField(_("descrição"), blank=True)
    language = models.CharField(_("idioma"), max_length=8, choices=settings.LANGUAGES)
    is_active = models.BooleanField(_("ativo"), default=True)

    # Schema de referencia dos campos do formulario. E o ponto de partida
    # para a proxima versao (ver TemplateVersion.field_schema); a versao
    # publicada e que vale de verdade para gerar cartas.
    default_field_schema = models.JSONField(
        _("schema padrão dos campos"),
        default=dict,
        blank=True,
        help_text=_(
            "Estrutura de referência dos campos do formulário, usada como ponto "
            "de partida ao criar uma nova versão. Editada pelo futuro editor visual."
        ),
    )

    class Meta:
        verbose_name = _("modelo de carta")
        verbose_name_plural = _("modelos de carta")
        ordering = ["name", "language"]

    def __str__(self):
        return f"{self.name} ({self.get_language_display()})"

    def clean(self):
        super().clean()
        validate_field_schema(self.default_field_schema)

    @property
    def published_version(self):
        """A versao publicada em uso, ou None se nao houver nenhuma."""
        return self.versions.filter(status=TemplateVersion.Status.PUBLISHED).order_by(
            "-version_number"
        ).first()

    @property
    def latest_version(self):
        """A versao mais recente, publicada ou nao."""
        return self.versions.order_by("-version_number").first()


class TemplateVersion(TimeStampedModel):
    """
    Uma versao imutavel (uma vez publicada) de um LetterTemplate.

    Regras de negocio, aplicadas em save()/delete() — nao so em forms,
    porque precisam valer para qualquer caminho de codigo:

      - uma versao publicada nao pode ter campos estruturais alterados
        (template, numero, field_schema, snapshot); mudar o status (ex.:
        publicada -> inativa) continua permitido;
      - uma versao publicada nao pode ser excluida;
      - uma versao usada por alguma Letter nao pode ser excluida de jeito
        nenhum, publicada ou nao — isso vem do on_delete=PROTECT em
        Letter.template_version (apps/letters/models.py), nao daqui.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Rascunho")
        PUBLISHED = "published", _("Publicada")
        INACTIVE = "inactive", _("Inativa")

    # Campos que uma versao publicada nao pode mais alterar. `visual_schema`
    # entra aqui pelo mesmo motivo que `field_schema`: mover um elemento
    # numa versao ja publicada mudaria retroativamente o documento de
    # cartas ja emitidas.
    STRUCTURAL_FIELDS = (
        "template_id",
        "version_number",
        "field_schema",
        "snapshot",
        "visual_schema",
    )

    template = models.ForeignKey(
        LetterTemplate,
        on_delete=models.PROTECT,
        related_name="versions",
        verbose_name=_("modelo"),
    )
    version_number = models.PositiveIntegerField(_("número da versão"))
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.DRAFT
    )

    # Configuracao efetiva dos campos desta versao (o que o formulario e a
    # geracao usam de verdade).
    field_schema = models.JSONField(_("configuração dos campos"), default=dict, blank=True)

    # Copia do necessario para reproduzir o documento no futuro (ex.: texto
    # legal vigente, referencia do PDF base) independente do que acontecer
    # com o LetterTemplate depois.
    snapshot = models.JSONField(_("snapshot de reprodução"), default=dict, blank=True)

    # O DESENHO da pagina: onde cada elemento fica, em pontos. Separado de
    # `field_schema` de proposito -- um responde "o que a pessoa preenche",
    # o outro "onde isso aparece no papel". Tem ciclos de vida distintos:
    # reposicionar um rotulo nao mexe no formulario, e acrescentar um campo
    # ao formulario nao obriga a desenha-lo.
    #
    # Vazio (`{}`) e valido e e o estado de toda versao criada antes do
    # editor visual existir. Contrato completo em `visual_schema.py`.
    visual_schema = models.JSONField(
        _("modelo visual"),
        default=dict,
        blank=True,
        help_text=_(
            "Posições e estilos dos elementos do documento, em pontos. "
            "Editado pelo editor visual do backoffice."
        ),
    )

    published_at = models.DateTimeField(_("publicada em"), null=True, blank=True)

    class Meta:
        verbose_name = _("versão de modelo")
        verbose_name_plural = _("versões de modelo")
        ordering = ["template", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "version_number"],
                name="doctemplates_unique_version_per_template",
            ),
        ]
        permissions = [
            ("publish_templateversion", "Pode publicar uma versão de modelo"),
        ]

    def __str__(self):
        return f"{self.template.name} · v{self.version_number} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        validate_field_schema(self.field_schema)
        # Sem `field_keys`/`asset_ids`: aqui so a estrutura e cobrada. A
        # checagem de que cada campo referenciado existe de verdade e de
        # que cada imagem esta ativa depende do banco e roda na view que
        # salva o editor, onde o custo da consulta se justifica.
        validate_visual_schema(self.visual_schema)

    def save(self, *args, **kwargs):
        if self.pk:
            previous = (
                TemplateVersion.objects.filter(pk=self.pk)
                .values("status", *self.STRUCTURAL_FIELDS)
                .first()
            )
            if previous and previous["status"] == self.Status.PUBLISHED:
                changed = [
                    field
                    for field in self.STRUCTURAL_FIELDS
                    if previous[field] != getattr(self, field)
                ]
                if changed:
                    raise TemplateVersionImmutableError(
                        "Uma versão publicada é imutável — não é possível alterar: "
                        + ", ".join(changed)
                    )

        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Se ha cartas vinculadas, deixa o on_delete=PROTECT de
        # Letter.template_version fazer o trabalho (ProtectedError) —  e a
        # regra mais especifica ("nao apagar versao usada por historico").
        # So bloqueamos aqui o caso que o PROTECT nao cobre: uma versao
        # publicada sem nenhuma carta ainda, que continua imutavel mesmo
        # assim.
        if self.status == self.Status.PUBLISHED and not self.letters.exists():
            raise TemplateVersionImmutableError("Uma versão publicada não pode ser excluída.")
        return super().delete(*args, **kwargs)

    def publish(self):
        """Publica esta versao (so a partir de rascunho); marca published_at."""
        if self.status != self.Status.DRAFT:
            raise TemplateVersionImmutableError(
                "Só uma versão em rascunho pode ser publicada."
            )
        self.status = self.Status.PUBLISHED
        self.save()

    def create_next_version(self, **overrides):
        """
        Cria a proxima versao (em rascunho) a partir desta, herdando o
        field_schema por padrao. Nao publica automaticamente.
        """
        next_number = (
            self.template.versions.aggregate(Max("version_number"))["version_number__max"] or 0
        ) + 1
        defaults = {
            "template": self.template,
            "version_number": next_number,
            "status": TemplateVersion.Status.DRAFT,
            "field_schema": copy.deepcopy(self.field_schema),
            # O layout tambem e herdado: a proxima versao quase sempre
            # comeca como um ajuste da anterior, nao de uma pagina em
            # branco. `deepcopy` para que editar o rascunho nunca toque no
            # JSON da versao de origem.
            "visual_schema": copy.deepcopy(self.visual_schema),
            "snapshot": {},
        }
        defaults.update(overrides)
        return TemplateVersion.objects.create(**defaults)


class NationalityQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Nationality(TimeStampedModel):
    """
    Uma nacionalidade que o assistente oferece nos campos de nacionalidade.

    Por que existe: o campo era texto livre, e texto livre num documento
    oficial vira erro de digitacao e forma gramatical errada. Aqui a
    lista e administravel (Django Admin) e o que fica guardado em
    `Letter.data` e o CODIGO -- estavel -- nunca o texto traduzido. Assim,
    renomear "Brésilienne" no cadastro nao reescreve o passado: o texto
    que foi para a carta ja esta congelado no snapshot dela.

    As duas formas gramaticais existem porque o documento oficial escreve
    a mesma nacionalidade de dois jeitos:

        "de nationalité belge"          -> `host_form`
        "Nationalité : Brésilienne"     -> `guest_form`

    LIMITE CONHECIDO: hoje essas duas formas sao as do documento oficial,
    que so existe em frances. Quando outro idioma ganhar documento
    proprio, elas precisarao virar uma forma por idioma.
    """

    code = models.CharField(
        _("código"),
        max_length=16,
        unique=True,
        help_text=_(
            "Identificador estável, gravado na carta. Não mude depois de "
            "existirem cartas usando-o."
        ),
    )
    is_active = models.BooleanField(
        _("ativa"),
        default=True,
        help_text=_("Só nacionalidades ativas aparecem no formulário."),
    )
    order = models.PositiveIntegerField(
        _("ordem"), default=0, help_text=_("Menor aparece primeiro.")
    )

    name_pt = models.CharField(_("nome (pt)"), max_length=120)
    name_fr = models.CharField(_("nome (fr)"), max_length=120)
    name_nl = models.CharField(_("nome (nl)"), max_length=120)
    name_en = models.CharField(_("nome (en)"), max_length=120)

    guest_form = models.CharField(
        _("forma no documento — convidado"),
        max_length=120,
        help_text=_('Como sai na tabela do documento. Ex.: "Brésilienne".'),
    )
    host_form = models.CharField(
        _("forma no documento — anfitrião"),
        max_length=120,
        help_text=_('Como sai no texto do documento. Ex.: "belge".'),
    )

    objects = NationalityQuerySet.as_manager()

    class Meta:
        verbose_name = _("nacionalidade")
        verbose_name_plural = _("nacionalidades")
        ordering = ["order", "name_pt"]

    def __str__(self):
        return self.name_pt or self.code

    def display_name(self, language=None):
        """O nome no idioma pedido, caindo no portugues se faltar."""
        return getattr(self, f"name_{language}", "") or self.name_pt or self.code


# ===========================================================================
# Biblioteca de modelos de documentos (nova arquitetura -- Etapa 1)
# ===========================================================================
#
# Substitui, conceitualmente, o par LetterTemplate + TemplateVersion. Os dois
# modelos antigos continuam existindo ate o cutover (nada aqui os toca): a
# geracao de cartas, o assistente e o editor atual seguem lendo deles.
#
# A ideia central mudou: nao ha mais "versao publicada imutavel". Um modelo
# e um registro so, editado e salvo diretamente. A reprodutibilidade de um
# documento emitido deixa de depender do modelo e passa a ser garantida no
# snapshot do proprio documento (etapa posterior).
#
# Dois conceitos que NAO se confundem:
#
#   is_system  -- e um modelo oficial do sistema (os quatro da Carta
#                 Convite). Diz de onde o modelo veio e o que ele e.
#   is_locked  -- esta, neste momento, fechado para edicao. Diz o que se
#                 pode fazer com ele agora.
#
# Um modelo oficial nasce DESTRAVADO (is_locked=False) e so e travado
# depois que o administrador aprovar visualmente que esta correto. Nenhuma
# regra aqui trava um modelo sozinha.


class DocumentTemplateLockedError(RuntimeError):
    """
    Tentativa de alterar ou apagar o que um modelo, no seu estado atual,
    nao permite. E erro de uso indevido, nao ValidationError de formulario:
    a regra vale para qualquer caminho de codigo que chame `.save()` ou
    `.delete()`.
    """


class DocumentType(TimeStampedModel):
    """
    Um TIPO de documento da biblioteca (Carta Convite, Contrato, ...).

    Agrupa os modelos e declara o que eles tem em comum: o tamanho da
    pagina e quais fontes de dados podem aparecer no editor. Nao carrega
    conteudo -- isso e dos modelos.
    """

    code = models.SlugField(_("código"), max_length=60, unique=True)
    name = models.CharField(_("nome"), max_length=120)
    description = models.TextField(_("descrição"), blank=True)
    is_active = models.BooleanField(_("ativo"), default=True)

    # Tamanho da pagina em PONTOS, o mesmo sistema do `layout` dos modelos
    # (ver visual_schema.py). Ex.: A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}.
    page = models.JSONField(_("página"), default=dict)

    # Codigos das fontes de dados que os modelos deste tipo podem usar
    # (ex.: ["documento", "convidado", "anfitriao", "calculado"]). O
    # registro que da significado a cada codigo e etapa posterior; aqui
    # so a lista, para o dado ja existir onde vai ser lido.
    data_sources = models.JSONField(_("fontes de dados"), default=list, blank=True)

    order = models.PositiveIntegerField(_("ordem"), default=0)

    class Meta:
        verbose_name = _("tipo de documento")
        verbose_name_plural = _("tipos de documento")
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class DocumentTemplate(TimeStampedModel):
    """
    Um MODELO da biblioteca: um documento A4 completo, descrito por
    `field_schema` (o que o formulario pergunta) e `layout` (como a pagina
    e desenhada). Um registro so; edita-se e salva-se diretamente.
    """

    # O que um modelo TRAVADO nao pode mais mudar. `is_locked` em si nao
    # entra: destravar e uma acao administrativa legitima (interface em
    # etapa posterior).
    STRUCTURAL_FIELDS = ("type_id", "language", "slug", "field_schema", "layout")

    # O que um modelo OFICIAL (is_system) aceita alterar, travado ou nao:
    # so o administrativo simples. Tudo o resto e recusado -- inclusive
    # `name`, que e a identidade do modelo oficial, e `is_system`, para um
    # oficial nao virar "comum" por um clique. `is_locked` entra porque e
    # exatamente o que o administrador fara com um oficial quando o
    # aprovar.
    SYSTEM_MUTABLE_FIELDS = ("description", "is_active", "is_locked")

    type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        related_name="templates",
        verbose_name=_("tipo"),
    )
    name = models.CharField(_("nome"), max_length=150)
    slug = models.SlugField(_("identificador"), max_length=80, unique=True)
    language = models.CharField(_("idioma"), max_length=8, choices=settings.LANGUAGES)
    description = models.TextField(_("descrição"), blank=True)

    is_system = models.BooleanField(
        _("modelo do sistema"),
        default=False,
        help_text=_("Modelo oficial do Desenrola. Serve de base; não é apagado."),
    )
    is_locked = models.BooleanField(
        _("travado"),
        default=False,
        help_text=_("Fechado para edição neste momento."),
    )

    # Linhagem: de qual modelo este foi duplicado. SET_NULL de proposito:
    # apagar a origem nao pode arrastar a copia, que e independente.
    duplicated_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicates",
        verbose_name=_("duplicado de"),
    )

    # Contrato de apps.doctemplates.schema (o formulario do assistente).
    field_schema = models.JSONField(_("configuração dos campos"), default=dict, blank=True)
    # Contrato de apps.doctemplates.visual_schema (o desenho da pagina).
    layout = models.JSONField(_("layout"), default=dict, blank=True)

    is_active = models.BooleanField(_("ativo"), default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_templates",
        verbose_name=_("criado por"),
    )

    class Meta:
        verbose_name = _("modelo de documento")
        verbose_name_plural = _("modelos de documento")
        ordering = ["type", "-is_system", "language", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_language_display()})"

    def clean(self):
        super().clean()
        validate_field_schema(self.field_schema)
        # Contrato NOVO (`layout_schema`), nao o `visual_schema` do
        # legado: sao arquiteturas diferentes convivendo. Ver o cabecalho
        # de layout_schema.py para a comparacao dos dois formatos.
        validate_layout(self.layout)

    # -- regras de integridade -------------------------------------------

    def _campos_alterados(self, campos):
        """Quais dos `campos` diferem do que esta gravado no banco."""
        gravado = DocumentTemplate.objects.filter(pk=self.pk).values(*campos).first()
        if gravado is None:
            return []
        return [campo for campo in campos if gravado[campo] != getattr(self, campo)]

    def save(self, *args, **kwargs):
        if self.pk:
            anterior = (
                DocumentTemplate.objects.filter(pk=self.pk)
                .values("is_system", "is_locked")
                .first()
            )
            if anterior:
                # A regra vale pelo estado GRAVADO, nao pelo que se esta
                # tentando gravar -- senao bastaria mudar `is_locked` e o
                # layout na mesma chamada.
                if anterior["is_locked"]:
                    alterados = self._campos_alterados(self.STRUCTURAL_FIELDS)
                    if alterados:
                        raise DocumentTemplateLockedError(
                            "Modelo travado: não é possível alterar " + ", ".join(alterados)
                        )
                if anterior["is_system"]:
                    todos = [
                        f.attname
                        for f in self._meta.concrete_fields
                        if f.attname not in ("id", "created_at", "updated_at")
                    ]
                    proibidos = [c for c in todos if c not in self.SYSTEM_MUTABLE_FIELDS]
                    alterados = self._campos_alterados(proibidos)
                    if alterados:
                        raise DocumentTemplateLockedError(
                            "Modelo do sistema: só description, is_active e is_locked "
                            "podem mudar; tentou alterar " + ", ".join(alterados)
                        )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_locked:
            raise DocumentTemplateLockedError("Um modelo travado não pode ser excluído.")
        if self.is_system:
            raise DocumentTemplateLockedError("Um modelo do sistema não pode ser excluído.")
        # Dependencias protegidas (documentos que apontem para este modelo,
        # em etapa posterior) ficam por conta do PROTECT das FKs.
        return super().delete(*args, **kwargs)
