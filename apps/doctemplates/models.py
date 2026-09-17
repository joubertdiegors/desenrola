"""
Modelos da biblioteca de documentos.

    DocumentType          o tipo (a pagina, as fontes de dados)
      -> DocumentTemplate o modelo em si: field_schema, layout, assets
           -> Letter      (app letters) aponta para um, e congela o
                          snapshot dele na finalizacao

Nao ha versionamento: um modelo e um registro. Editar um modelo comum e
editar o proprio registro; os oficiais (`is_system`) sao protegidos e se
editam por DUPLICACAO, que cria um DocumentTemplate independente.

`Nationality` mora aqui por ser o vocabulario que o field_schema oferece
nos campos de nacionalidade.
"""


from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

from .layout_schema import assets_referenciados, validate_layout
from .schema import validate_field_schema


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

    UMA TRADUCAO POR IDIOMA, E SO ISSO
    ----------------------------------
    A nacionalidade e um nome em quatro idiomas. O documento escreve o
    nome no idioma DELE:

        carta em frances   -> `name_fr`
        carta em portugues -> `name_pt`

    Nao ha forma por papel (convidado/anfitriao) nem por genero. A mesma
    traducao serve a tela e ao documento, e quem a escolhe e
    `display_name()` -- um lugar so, para a tela e para o papel nao
    poderem discordar.
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

    objects = NationalityQuerySet.as_manager()

    class Meta:
        verbose_name = _("nacionalidade")
        verbose_name_plural = _("nacionalidades")
        ordering = ["order", "name_pt"]

    def __str__(self):
        return self.name_pt or self.code

    def display_name(self, language=None):
        """
        O nome no idioma pedido -- para a tela E para o documento.

        Idioma sem traducao cai no portugues; sem nenhum nome, no codigo.
        Nunca devolve vazio para uma nacionalidade que existe: um
        documento oficial com o campo em branco seria pior do que um com
        o codigo.
        """
        return getattr(self, f"name_{language}", "") or self.name_pt or self.code


# ===========================================================================
# Biblioteca de modelos de documentos (nova arquitetura -- Etapa 1)
# ===========================================================================
#
# Substituiu o par LetterTemplate + TemplateVersion, removido do banco:
# e a unica arquitetura de documentos do produto.
#
# A ideia central mudou: nao ha mais "versao publicada imutavel". Um modelo
# e um registro so, editado e salvo diretamente. A reprodutibilidade de um
# documento emitido nao depende do modelo: e garantida pelo snapshot
# congelado na propria carta (`Letter.document_snapshot`).
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
    # (ver layout_schema.py). Ex.: A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}.
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

    UM ATIVO POR IDIOMA
    -------------------
    Dentro de um tipo de documento, cada idioma tem no MAXIMO um modelo
    ativo -- e ele que o assistente usa para emitir a carta naquele
    idioma. A troca (ativar outro do mesmo idioma desativa o anterior)
    e `services.ativacao.ativar()`; a garantia de que nunca existam
    dois e o indice parcial declarado em `Meta.constraints`, que vale
    para QUALQUER caminho de escrita -- view, shell, admin ou migration.

    Inativo nao e apagado: o modelo continua existindo, editavel e
    duplicavel. So esta fora de uso.
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
    # Contrato de apps.doctemplates.layout_schema (o desenho da pagina).
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
        constraints = [
            # A regra do ativo unico, no banco. Indice PARCIAL: so as
            # linhas ativas entram nele, entao quantos modelos inativos
            # o mesmo idioma tiver, continua valendo.
            models.UniqueConstraint(
                fields=["type", "language"],
                condition=models.Q(is_active=True),
                name="uniq_documenttemplate_ativo_por_idioma",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_language_display()})"

    def clean(self):
        super().clean()
        validate_field_schema(self.field_schema)
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
        # Os vinculos com os assets do layout acompanham cada gravacao:
        # e o que mantem o PROTECT de `DocumentTemplateAsset` fiel ao que
        # o desenho referencia HOJE (ver `sincronizar_assets_do_modelo`).
        sincronizar_assets_do_modelo(type(self), self)

    def delete(self, *args, **kwargs):
        if self.is_locked:
            raise DocumentTemplateLockedError("Um modelo travado não pode ser excluído.")
        if self.is_system:
            raise DocumentTemplateLockedError("Um modelo do sistema não pode ser excluído.")
        # Dependencias protegidas (documentos que apontem para este modelo,
        # em etapa posterior) ficam por conta do PROTECT das FKs.
        return super().delete(*args, **kwargs)


class DocumentTemplateAsset(models.Model):
    """
    Vinculo explicito entre um modelo e cada `content.Asset` que o seu
    `layout` referencia (Etapa 3.5.1, integridade de assets).

    O layout guarda `{"kind": "asset", "asset_id": N}` dentro de JSON, e o
    banco nao enxerga isso: sem esta tabela, apagar o Asset pelo admin
    deixaria o modelo apontando para uma imagem que nao existe mais. Com
    ela, a FK `asset` e PROTECT -- o ORM recusa a exclusao, seja por
    `delete()`, por `queryset.delete()` ou pelo bulk do admin.

    E DERIVADA do layout, nunca editada a mao: `sincronizar_assets_do_
    modelo()` a recompoe a cada gravacao. Trocar o modelo para outro
    asset solta o vinculo antigo e cria o novo -- e ai o asset antigo
    volta a ser excluivel, a menos que uma carta finalizada ainda dependa
    dele (`letters.LetterAsset`).
    """

    template = models.ForeignKey(
        DocumentTemplate,
        on_delete=models.CASCADE,
        related_name="asset_links",
        verbose_name=_("modelo"),
    )
    asset = models.ForeignKey(
        "content.Asset",
        on_delete=models.PROTECT,
        related_name="template_references",
        verbose_name=_("imagem"),
    )

    class Meta:
        verbose_name = _("imagem usada por modelo")
        verbose_name_plural = _("imagens usadas por modelos")
        constraints = [
            models.UniqueConstraint(
                fields=["template", "asset"], name="uniq_documenttemplate_asset"
            )
        ]

    def __str__(self):
        return f"{self.template_id} -> asset #{self.asset_id}"


def sincronizar_assets_do_modelo(DocumentTemplate, modelo):
    """
    Deixa `DocumentTemplateAsset` igual ao que `modelo.layout` referencia.

    Recebe a CLASSE do modelo para funcionar tambem com o modelo
    historico das migrations (`apps.get_model()`), que e por onde
    `services.carta_convite.aplicar()`/`vincular_logo()` passam. Num estado
    historico anterior a existencia da tabela de vinculos, nao ha o que
    sincronizar -- e a funcao simplesmente nao faz nada.

    Um `asset_id` que nao existe no banco NAO gera vinculo nem erro: o
    editor grava `0` para "ainda nao escolhido", e um id orfao e recusado
    depois, na geracao do PDF (`AssetAusenteError`) -- nao aqui, para nao
    quebrar a edicao normal de um modelo.
    """
    registro = DocumentTemplate._meta.apps
    try:
        Vinculo = registro.get_model("doctemplates", "DocumentTemplateAsset")
        Asset = registro.get_model("content", "Asset")
    except LookupError:
        return

    desejados = assets_referenciados(modelo.layout or {})
    existentes = set(Asset.objects.filter(pk__in=desejados).values_list("pk", flat=True))
    atuais = set(Vinculo.objects.filter(template_id=modelo.pk).values_list("asset_id", flat=True))

    a_remover = atuais - existentes
    if a_remover:
        Vinculo.objects.filter(template_id=modelo.pk, asset_id__in=a_remover).delete()
    for asset_id in existentes - atuais:
        Vinculo.objects.get_or_create(template_id=modelo.pk, asset_id=asset_id)
