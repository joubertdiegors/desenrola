"""
Conteudo e configuracao editaveis do site.

Tres camadas, cada uma resolvendo um problema diferente — de proposito
separadas, para nao virar um CMS generico:

  - Asset: um arquivo de imagem reaproveitavel (logo, favicon, foto da
    Home, foto de parceiro, imagem de conteudo). Um so modelo, com um
    campo `kind` para categorizar, em vez de um campo de imagem
    duplicado em cada lugar que precisa de uma.

  - ContentBlock / ContentTranslation: um texto (ou imagem simples)
    isolado, identificado por uma chave (ex.: "footer.text",
    "legal.terms_of_use"), traduzido nos quatro idiomas. Serve para
    textos legais, mensagens do sistema, conteudo de e-mail, rodape —
    qualquer coisa que nao precise de ordem nem de estrutura propria.

  - Page / PageSection / PageSectionTranslation: a Home (e futuras
    paginas) como uma lista ORDENADA de secoes tipadas (hero, features,
    parceiros, faq...), cada uma ativavel/desativavel e com conteudo
    proprio por idioma. E o que ContentBlock sozinho nao cobre.

  - SiteSettings: um unico registro (singleton) com os valores
    escalares e NAO traduziveis do site — nome, contato, cores, redes
    sociais, logo/favicon. Textos traduziveis (rodape, textos legais)
    ficam no ContentBlock, nao aqui.

Importante (secao 6 do pedido): isto e conteudo/configuracao EDITAVEL
PELO ADMINISTRADOR, guardado no banco. E diferente da traducao de
interface do Django (gettext, em locale/), que continua no codigo e
depende de deploy. `settings.LANGUAGES` e a fonte unica dos idiomas em
ambos os casos — nenhum modelo aqui duplica essa lista.

Ainda NAO implementada a interface visual do editor (Home, campos,
imagens) — so a estrutura de dados, como pedido nesta revisao.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#[0-9a-fA-F]{6}$",
    message=_("Informe uma cor em hexadecimal, no formato #rrggbb."),
)


class Asset(TimeStampedModel):
    """
    Uma imagem administravel: logo, favicon, foto da Home, foto de
    parceiro ou imagem de conteudo. `key` e opcional — so os assets que
    precisam ser localizados por nome fixo (ex.: o logo atual) usam um;
    os demais (ex.: a foto de um parceiro especifico) sao referenciados
    por FK de onde forem usados.
    """

    class Kind(models.TextChoices):
        LOGO = "logo", _("Logomarca")
        FAVICON = "favicon", _("Favicon")
        HOME = "home", _("Imagem da Home")
        PARTNER = "partner", _("Imagem de parceiro")
        CONTENT = "content", _("Imagem de conteúdo")
        OTHER = "other", _("Outro")

    key = models.SlugField(
        _("identificador"), max_length=100, unique=True, blank=True, null=True
    )
    kind = models.CharField(_("tipo"), max_length=20, choices=Kind.choices, default=Kind.OTHER)
    file = models.ImageField(_("arquivo"), upload_to="assets/%Y/%m/")
    alt_text = models.CharField(_("texto alternativo"), max_length=255, blank=True)
    is_active = models.BooleanField(_("ativo"), default=True)

    class Meta:
        verbose_name = _("imagem")
        verbose_name_plural = _("imagens")
        ordering = ["kind", "key"]

    def __str__(self):
        return self.key or f"{self.get_kind_display()} #{self.pk}"


class ContentBlock(TimeStampedModel):
    """Um slot de conteudo editavel (ex.: 'landing.hero.title')."""

    class Kind(models.TextChoices):
        TEXT = "text", _("Texto simples")
        RICH_TEXT = "rich_text", _("Texto formatado")
        IMAGE = "image", _("Imagem")

    key = models.SlugField(_("identificador"), max_length=100, unique=True)
    kind = models.CharField(_("tipo"), max_length=20, choices=Kind.choices, default=Kind.TEXT)
    is_active = models.BooleanField(_("ativo"), default=True)

    class Meta:
        verbose_name = _("bloco de conteúdo")
        verbose_name_plural = _("blocos de conteúdo")
        ordering = ["key"]

    def __str__(self):
        return self.key


class ContentTranslation(TimeStampedModel):
    """
    O conteudo de um ContentBlock, num dos quatro idiomas do site.

    `content` vale para texto/texto formatado; `asset` vale quando o
    bloco e do tipo imagem (o mesmo bloco pode ter uma foto diferente
    por idioma, ex.: uma imagem com texto embutido).
    """

    block = models.ForeignKey(
        ContentBlock,
        on_delete=models.CASCADE,
        related_name="translations",
        verbose_name=_("bloco"),
    )
    language = models.CharField(_("idioma"), max_length=8, choices=settings.LANGUAGES)
    content = models.TextField(_("conteúdo"), blank=True)
    asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="content_translations",
        verbose_name=_("imagem"),
    )

    class Meta:
        verbose_name = _("tradução de conteúdo")
        verbose_name_plural = _("traduções de conteúdo")
        ordering = ["block", "language"]
        constraints = [
            models.UniqueConstraint(
                fields=["block", "language"],
                name="content_unique_translation_per_language",
            ),
        ]

    def __str__(self):
        return f"{self.block.key} ({self.language})"


class Page(TimeStampedModel):
    """
    Uma pagina editavel do site (a Home primeiro; a estrutura ja
    suporta outras paginas no futuro, sem alteracao de modelo).
    """

    key = models.SlugField(_("identificador"), max_length=60, unique=True)
    name = models.CharField(_("nome"), max_length=150, help_text=_("Uso interno, no backoffice."))
    is_active = models.BooleanField(_("ativa"), default=True)

    class Meta:
        verbose_name = _("página")
        verbose_name_plural = _("páginas")
        ordering = ["key"]

    def __str__(self):
        return self.name


class PageSection(TimeStampedModel):
    """
    Uma secao de uma Page, com tipo, ordem e ativacao proprios. O
    conteudo (texto por idioma) fica em PageSectionTranslation — o
    formato interno de `content` la varia por `kind` e nao e imposto
    aqui, pois o editor visual (fase futura) e quem vai definir a forma
    exata de cada tipo de secao.
    """

    class Kind(models.TextChoices):
        HERO = "hero", _("Destaque (hero)")
        TEXT = "text", _("Texto")
        IMAGE_TEXT = "image_text", _("Imagem e texto")
        FEATURES = "features", _("Destaques / recursos")
        PARTNERS = "partners", _("Parceiros")
        FAQ = "faq", _("Perguntas frequentes")
        CTA = "cta", _("Chamada para ação")
        BANNER = "banner", _("Banner")
        CONTACT = "contact", _("Contato")

    page = models.ForeignKey(
        Page, on_delete=models.CASCADE, related_name="sections", verbose_name=_("página")
    )
    key = models.SlugField(
        _("identificador"),
        max_length=80,
        blank=True,
        help_text=_("Opcional; útil para referenciar a seção a partir de um link interno."),
    )
    kind = models.CharField(_("tipo"), max_length=20, choices=Kind.choices)
    order = models.PositiveIntegerField(
        _("ordem"),
        default=0,
        help_text=_("Posição na página. Não precisa ser sequencial nem única."),
    )
    is_active = models.BooleanField(_("ativa"), default=True)

    class Meta:
        verbose_name = _("seção de página")
        verbose_name_plural = _("seções de página")
        ordering = ["page", "order", "id"]

    def __str__(self):
        return f"{self.page.key} · {self.get_kind_display()} (#{self.order})"


class PageSectionTranslation(TimeStampedModel):
    """O conteudo de uma PageSection, num dos quatro idiomas do site."""

    section = models.ForeignKey(
        PageSection,
        on_delete=models.CASCADE,
        related_name="translations",
        verbose_name=_("seção"),
    )
    language = models.CharField(_("idioma"), max_length=8, choices=settings.LANGUAGES)
    content = models.JSONField(
        _("conteúdo"),
        default=dict,
        blank=True,
        help_text=_("Estrutura livre, definida pelo tipo da seção (título, texto, botão...)."),
    )

    class Meta:
        verbose_name = _("tradução de seção")
        verbose_name_plural = _("traduções de seção")
        ordering = ["section", "language"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "language"],
                name="content_unique_section_translation_per_language",
            ),
        ]

    def __str__(self):
        return f"{self.section} ({self.language})"

    def clean(self):
        super().clean()
        if self.content is not None and not isinstance(self.content, dict):
            raise ValidationError(
                {"content": _("O conteúdo da seção deve ser um objeto (JSON).")}
            )


class SiteSettings(TimeStampedModel):
    """
    Configuracoes gerais do site — um unico registro (singleton).

    So valores escalares e NAO traduziveis ficam aqui (nome do site,
    contato, cores, redes sociais, logo/favicon). Texto traduzivel
    (rodape, textos legais) continua no ContentBlock — colocar aqui
    duplicaria o mecanismo de traducao que ja existe.
    """

    SINGLETON_ID = 1

    site_name = models.CharField(_("nome do site"), max_length=150, default="Desenrola")
    contact_email = models.EmailField(_("e-mail de contato"), blank=True)
    contact_phone = models.CharField(_("telefone de contato"), max_length=32, blank=True)
    contact_address = models.TextField(_("endereço"), blank=True)

    logo = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("logomarca"),
    )
    favicon = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("favicon"),
    )

    # {"facebook": "https://...", "instagram": "https://...", ...} — lista
    # de redes abertas, sem precisar de uma coluna por rede social.
    social_links = models.JSONField(_("redes sociais"), default=dict, blank=True)

    # Persistem de verdade a escolha de cor que o backoffice de Aparencia
    # (fase visual) so guardava no navegador de quem estava editando.
    theme_primary_color = models.CharField(
        _("cor principal"),
        max_length=7,
        default="#1a5fd6",
        validators=[HEX_COLOR_VALIDATOR],
    )
    theme_success_color = models.CharField(
        _("cor de sucesso"),
        max_length=7,
        default="#17a34a",
        validators=[HEX_COLOR_VALIDATOR],
    )

    class Meta:
        verbose_name = _("configurações do site")
        verbose_name_plural = _("configurações do site")

    def __str__(self):
        return str(_("Configurações do site"))

    def clean(self):
        super().clean()
        if not isinstance(self.social_links, dict):
            raise ValidationError({"social_links": _("Redes sociais deve ser um objeto (JSON).")})
        for network, url in self.social_links.items():
            if not isinstance(network, str) or not isinstance(url, str):
                raise ValidationError(
                    {
                        "social_links": _(
                            "Cada rede social deve mapear um nome a uma URL, ambos texto."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        # Singleton: sempre o mesmo id, para nunca existir mais de uma
        # configuracao "vigente" ao mesmo tempo. Isso faz `.save()` num
        # objeto ja carregado do banco atualizar a linha certa; chamar
        # `.objects.create()` uma segunda vez continua falhando alto e
        # claro (IntegrityError de PK duplicada) em vez de corromper os
        # dados — a forma correta de obter/criar o registro e `load()`.
        self.pk = self.SINGLETON_ID
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Devolve a configuracao vigente, criando com os padroes se necessario."""
        obj, _created = cls.objects.get_or_create(pk=cls.SINGLETON_ID)
        return obj
