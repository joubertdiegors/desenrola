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

  - Partner: os parceiros exibidos na Home. Entidade propria, e nao uma
    secao de conteudo, porque cada um tem ordem, imagem, endereco e
    situacao proprios — coisas que um bloco de texto nao guarda.

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
from django.core.validators import RegexValidator, URLValidator
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

    # -- integridade para reproducao historica (Etapa 3.5.1) --------------
    #
    # Dois consumidores referenciam um Asset de dentro de JSON, onde o
    # banco nao enxerga: o `layout` de um `doctemplates.DocumentTemplate`
    # e o `document_snapshot` de uma `letters.Letter` finalizada. Cada um
    # mantem uma tabela de vinculo com FK PROTECT para ca
    # (`template_references`, `letter_references`) -- e o PROTECT que
    # recusa a exclusao, em qualquer caminho: `delete()`, queryset, admin.
    #
    # O que o PROTECT nao cobre e a SUBSTITUICAO do arquivo: trocar o PNG
    # de um asset que uma carta finalizada usa mudaria o documento
    # historico em silencio. Por isso o `save()` abaixo recusa isso.

    def referenciado_por_carta_finalizada(self):
        """Ha uma Letter finalizada cujo snapshot depende deste asset?"""
        vinculos = getattr(self, "letter_references", None)
        return bool(self.pk and vinculos is not None and vinculos.exists())

    def referenciado_por_modelo(self):
        """Ha um DocumentTemplate cujo layout usa este asset?"""
        vinculos = getattr(self, "template_references", None)
        return bool(self.pk and vinculos is not None and vinculos.exists())

    def save(self, *args, **kwargs):
        if self.pk and self.referenciado_por_carta_finalizada():
            gravado = Asset.objects.filter(pk=self.pk).values_list("file", flat=True).first()
            if gravado is not None and gravado != self.file.name:
                # `FieldFile.save()` grava o arquivo NOVO no storage antes
                # de chegar aqui. Recusar e sair deixaria esse arquivo
                # orfao em MEDIA_ROOT a cada tentativa; apaga-lo so quando
                # foi de fato gravado (`_committed`) -- um upload apenas
                # atribuido ainda nao esta no disco, e apagar pelo nome
                # poderia atingir outro arquivo.
                if getattr(self.file, "_committed", False):
                    self.file.storage.delete(self.file.name)
                self.file.name = gravado
                raise AssetFileImmutableError(
                    "Este arquivo é usado por uma carta já finalizada e não pode ser "
                    "substituído. Crie um novo asset e aponte o modelo para ele."
                )
        super().save(*args, **kwargs)


class AssetFileImmutableError(RuntimeError):
    """
    Tentativa de trocar o arquivo de um Asset do qual uma carta finalizada
    depende. Erro de uso indevido, nao de formulario -- vale para qualquer
    caminho que chame `save()`, no mesmo espirito de
    `DocumentTemplateLockedError` e `DocumentSnapshotImmutableError`.
    """


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
        NAVBAR = "navbar", _("Barra superior")
        HERO = "hero", _("Destaque (hero)")
        TEXT = "text", _("Texto")
        IMAGE_TEXT = "image_text", _("Imagem e texto")
        FEATURES = "features", _("Destaques / recursos")
        PARTNERS = "partners", _("Parceiros")
        FAQ = "faq", _("Perguntas frequentes")
        CTA = "cta", _("Chamada para ação")
        BANNER = "banner", _("Banner")
        CONTACT = "contact", _("Contato")
        FOOTER = "footer", _("Rodapé")

    class Posicao9(models.TextChoices):
        """
        As nove posições fixas para um elemento flutuando sobre outro --
        hoje o contador do banner e o botão de cada cartão de parceiro.

        NOVE, E NÃO COORDENADAS LIVRES
        -------------------------------
        Um `x`/`y` digitado pelo administrador é CSS arbitrário por
        outro nome: sairia da tela em qualquer combinação de conteúdo e
        produziria posições que ninguém testou. Nove pontos fixos são
        fáceis de entender ("canto superior esquerdo"), fáceis de testar
        (são só nove) e impossíveis de sair da caixa que os contém.

        UMA LISTA SÓ, REUSADA
        ----------------------
        O contador do banner e o botão do parceiro não têm nada em
        comum a não ser "um elemento sobre outro" -- e é exatamente por
        isso que a mesma lista serve aos dois: a pergunta que ela
        responde é sempre a mesma, o que muda é ONDE ela é feita. Ver
        `static/css/layout.css`, as classes `.pos-*`, que os dois
        consomem.
        """

        SUPERIOR_ESQUERDA = "superior-esquerda", _("Superior esquerda")
        SUPERIOR_CENTRO = "superior-centro", _("Superior centro")
        SUPERIOR_DIREITA = "superior-direita", _("Superior direita")
        CENTRO_ESQUERDA = "centro-esquerda", _("Centro esquerda")
        CENTRO = "centro", _("Centro")
        CENTRO_DIREITA = "centro-direita", _("Centro direita")
        INFERIOR_ESQUERDA = "inferior-esquerda", _("Inferior esquerda")
        INFERIOR_CENTRO = "inferior-centro", _("Inferior centro")
        INFERIOR_DIREITA = "inferior-direita", _("Inferior direita")

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
    # QUAL desenho, separado de QUAL conteudo.
    #
    # Vazio significa "o desenho unico desta secao" -- a maioria so tem
    # um. O banner tem tres (ver `content.section_schema.LAYOUTS`), e
    # trocar entre eles NAO apaga o texto: o conteudo mora na traducao,
    # nao aqui. E o que permite experimentar um desenho e voltar atras.
    layout = models.CharField(
        _("desenho"),
        max_length=40,
        blank=True,
        default="",
        help_text=_("Qual variação visual esta seção usa. Vazio = a única que existe."),
    )
    # A imagem da parte, quando ela tem uma (hoje: o banner superior).
    #
    # FK, e nao um id dentro do JSON da traducao: referencia de dentro de
    # JSON o banco nao enxerga -- e o proprio `Asset` explica o custo
    # disso, que e manter uma tabela de vinculo so para o PROTECT
    # funcionar. Aqui nao ha esse custo.
    #
    # Na SECAO, e nao na traducao: imagem nao e texto, e trocar o idioma
    # do conteudo nao troca a fotografia do banner.
    #
    # SET_NULL: apagar uma imagem da biblioteca nao derruba a Home -- o
    # banner volta a moldura vazia, que e um estado valido.
    image = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="page_sections",
        verbose_name=_("imagem"),
        help_text=_("A imagem desta parte. Sem ela, aparece a moldura vazia."),
    )
    is_active = models.BooleanField(_("ativa"), default=True)

    # -- Contador do banner (Bloco A) --------------------------------------
    #
    # ESTRUTURAL, E NÃO CONTEÚDO: valem para a seção inteira, em
    # qualquer idioma -- mesma razão de `layout`/`image` logo acima.
    # Só a seção "hero" os usa hoje (`section_schema.SECOES["hero"].contador`
    # é quem decide se o formulário oferece estes campos), mas a coluna
    # é genérica: qualquer seção futura que precise de um contador ganha
    # o recurso só declarando `contador=True`.
    #
    # O NÚMERO NUNCA MORA AQUI
    # ------------------------
    # Só a ativação, a posição e o rótulo/indicador (este dois últimos
    # em `PageSectionTranslation.content`, como texto comum). O número
    # em si vem sempre de `apps.letters.statistics.cartas_emitidas()` --
    # nunca escrito, nunca gravado, nunca duplicado.
    counter_enabled = models.BooleanField(
        _("contador ativo"),
        default=True,
        help_text=_("Mostra o número real de cartas já emitidas sobre o banner."),
    )
    counter_position = models.CharField(
        _("posição do contador"),
        max_length=20,
        choices=Posicao9.choices,
        default=Posicao9.SUPERIOR_ESQUERDA,
    )
    counter_live_enabled = models.BooleanField(
        _("indicador \"ao vivo\" ativo"),
        default=True,
        help_text=_("Mostra a nota de atualização ao lado do contador."),
    )

    # -- Botão e carrossel de "Nossos parceiros" (Bloco B) -----------------
    #
    # Mesma razão de existir das colunas do contador: estrutural, não
    # traduzível, e só usada pela seção "partners" -- mas genérica o
    # bastante para não precisar de uma segunda tabela.
    partners_button_position = models.CharField(
        _("posição do botão no cartão"),
        max_length=20,
        choices=Posicao9.choices,
        default=Posicao9.INFERIOR_CENTRO,
    )
    partners_carousel_enabled = models.BooleanField(
        _("carrossel ativo"),
        default=True,
        help_text=_(
            "Com mais de 4 parceiros ativos, exibe os demais rolando na "
            "horizontal em vez de criar uma segunda fileira. Desativado, a "
            "seção mostra só os 4 primeiros e o botão \"Ver todos\"."
        ),
    )
    partners_carousel_controls_enabled = models.BooleanField(
        _("setas do carrossel ativas"), default=True
    )
    partners_view_all_enabled = models.BooleanField(
        _("botão \"Ver todos\" ativo"),
        default=True,
        help_text=_(
            "Só aparece quando também há um destino configurado nos textos "
            "da seção -- sem destino, o botão continua oculto."
        ),
    )

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


# As redes sociais que o site sabe apresentar.
#
# UMA LISTA, E NAO UMA COLUNA POR REDE: `social_links` continua sendo um
# unico campo. O que esta tupla acrescenta e o CONJUNTO CONHECIDO -- os
# nomes que o rodape sabe rotular e desenhar. Uma chave fora daqui nao
# tem rotulo nem icone: guardar uma seria guardar algo que nenhuma
# pagina consegue mostrar, e um dado que nunca aparece e um erro
# silencioso, nao um recurso.
#
# Acrescentar uma rede e acrescentar uma linha aqui (e o icone
# correspondente no rodape). Nao ha nenhuma outra lista para manter em
# dia.
REDES_SOCIAIS = (
    ("facebook", _("Facebook"), "ph-facebook-logo"),
    ("instagram", _("Instagram"), "ph-instagram-logo"),
)

# So http e https. `javascript:` num href e execucao de codigo na pagina
# de quem visita, e o autoescape do template NAO protege contra isso --
# o valor esta dentro do atributo, nao no texto.
URL_SOCIAL_VALIDATOR = URLValidator(schemes=["http", "https"])


def nome_da_rede(chave):
    """O rotulo da rede, ou `None` se ninguem a declarou."""
    for declarada, nome, _icone in REDES_SOCIAIS:
        if declarada == chave:
            return nome
    return None


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

    # {"facebook": "https://...", "instagram": "https://..."} — um campo
    # so, em vez de uma coluna por rede. As chaves aceitas sao as de
    # `REDES_SOCIAIS`; o `clean()` confere isso e o esquema da URL.
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
            if nome_da_rede(network) is None:
                raise ValidationError(
                    {
                        "social_links": _(
                            "Rede social desconhecida: \"%(rede)s\". O site só sabe "
                            "apresentar: %(conhecidas)s."
                        )
                        % {
                            "rede": network,
                            "conhecidas": ", ".join(
                                str(nome) for _chave, nome, _icone in REDES_SOCIAIS
                            ),
                        }
                    }
                )
            # Vazio significa "nao configurada" -- e um estado legitimo, e
            # o rodape simplesmente nao desenha o link.
            if not url:
                continue
            try:
                URL_SOCIAL_VALIDATOR(url)
            except ValidationError:
                raise ValidationError(
                    {
                        "social_links": _(
                            "O endereço de %(rede)s precisa ser uma URL http:// ou https://."
                        )
                        % {"rede": nome_da_rede(network)}
                    }
                ) from None

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


class PartnerQuerySet(models.QuerySet):
    def publicados(self):
        """Os que aparecem na Home: ativos, na ordem definida."""
        return self.filter(is_active=True).select_related("logo")


class Partner(TimeStampedModel):
    """
    Um parceiro exibido na secao "Nossos parceiros" da Home.

    DESATIVAR E O CAMINHO; APAGAR EXISTE PARA O ERRO
    -----------------------------------------------
    Desativar (`is_active=False`) tira o parceiro da Home na hora e
    mantem o registro para quem precisar saber com quem ja houve acordo
    -- e o que a tela sugere. Apagar existe desde a Etapa 11, para quem
    foi cadastrado errado, e passa por uma confirmacao propria no
    Backoffice (`content.delete_partner`).

    A IMAGEM E UM `Asset`
    ---------------------
    Nao ha `ImageField` aqui. O logo aponta para `content.Asset`, que e
    onde toda imagem administravel do projeto mora -- inclusive com a
    protecao contra substituir arquivo do qual uma carta finalizada
    dependa. `Asset.Kind.PARTNER` existe desde a primeira migration do
    app, a espera deste momento.

    Sem logo, a Home mostra o cartao sem imagem: um parceiro recem
    cadastrado nao pode derrubar a pagina.
    """

    name = models.CharField(_("nome"), max_length=150)
    description = models.TextField(
        _("descrição"),
        blank=True,
        help_text=_("Uma linha sobre o serviço. Aparece abaixo do nome, na Home."),
    )
    logo = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partners",
        verbose_name=_("logomarca"),
        help_text=_("Imagem do parceiro. Sem ela, o cartão aparece sem imagem."),
    )
    url = models.URLField(
        _("endereço"),
        blank=True,
        help_text=_("Para onde o cartão leva. Em branco, o cartão não é clicável."),
    )
    is_active = models.BooleanField(
        _("ativo"),
        default=True,
        help_text=_("Só parceiros ativos aparecem na Home."),
    )
    order = models.PositiveIntegerField(
        _("ordem"), default=0, help_text=_("Menor aparece primeiro.")
    )

    objects = PartnerQuerySet.as_manager()

    class Meta:
        # Sem `delete`: a exclusao nao faz parte do fluxo (ver o docstring).
        # Uma permissao que nao controla nada e ruido no catalogo.
        # `delete` entra na Etapa 11: a Central de Conteudo passou a
        # permitir remover um parceiro, e ate aqui nem o Django Admin
        # podia. Desativar continua sendo o caminho recomendado -- apagar
        # e para quem entrou errado.
        default_permissions = ("add", "change", "delete", "view")
        verbose_name = _("parceiro")
        verbose_name_plural = _("parceiros")
        # `pk` desempata: dois parceiros com a mesma ordem trocariam de
        # lugar entre uma visita e outra sem isto.
        ordering = ["order", "pk"]

    def __str__(self):
        return self.name


# Um destino de menu: ancora interna (`#como-funciona`), caminho do
# proprio site (`/pt/...`) ou endereco http(s). Nada de `javascript:` --
# o valor termina dentro de um `href`, onde o autoescape NAO protege.
DESTINO_DO_MENU = RegexValidator(
    regex=r"^(#[\w-]+|/[\w\-/.]*|https?://\S+)$",
    message=_(
        "O destino deve ser uma âncora (#como-funciona), um caminho do site "
        "(/pt/...) ou um endereço http:// ou https://."
    ),
)

# O destino do botão "Ver todos os parceiros" -- MESMA forma de
# `DESTINO_DO_MENU`, SEM a âncora.
#
# Uma âncora levaria a algum lugar DENTRO da própria Home -- e a seção
# de parceiros já está na Home; um botão "ver todos" que aponta para
# ela mesma é circular, não um destino. Só caminho do site ou endereço
# externo fazem sentido aqui.
DESTINO_EXTERNO_OU_CAMINHO = RegexValidator(
    regex=r"^(/[\w\-/.]*|https?://\S+)$",
    message=_(
        "O destino deve ser um caminho do site (/pt/...) ou um endereço "
        "http:// ou https://."
    ),
)


class MenuItemQuerySet(models.QuerySet):
    def publicados(self):
        """Os que aparecem na barra: ativos, na ordem definida."""
        return self.filter(is_active=True)


class MenuItem(TimeStampedModel):
    """
    Um item da barra superior do site.

    POR QUE UM MODELO, E NAO UMA LISTA DENTRO DO JSON DA SECAO
    ----------------------------------------------------------
    Os itens precisam ser ACRESCENTADOS, REMOVIDOS e REORDENADOS. O
    editor declarativo de secao (`content.forms.FormularioDeSecao`) edita
    os textos dos itens que EXISTEM -- de proposito, porque para os
    cartoes da Home a quantidade e desenho, nao conteudo. Aqui e o
    contrario: a quantidade E a decisao.

    Mesma forma de `Partner`, que ja e o precedente do projeto para "uma
    lista de coisas com ordem e ativacao propria".

    O QUE ELE NAO GUARDA
    --------------------
    Nada de identidade: logotipo, nome do site e cores continuam em
    `SiteSettings`, e os botoes de entrar/criar conta continuam sendo
    estrutura do produto. Este modelo guarda a NAVEGACAO, e so ela.
    """

    label = models.CharField(_("texto"), max_length=60)
    destination = models.CharField(
        _("destino"),
        max_length=200,
        validators=[DESTINO_DO_MENU],
        help_text=_("#ancora, /caminho do site ou endereço http(s)."),
    )
    is_active = models.BooleanField(_("ativo"), default=True)
    order = models.PositiveIntegerField(
        _("ordem"), default=0, help_text=_("Menor aparece primeiro.")
    )

    objects = MenuItemQuerySet.as_manager()

    class Meta:
        verbose_name = _("item do menu")
        verbose_name_plural = _("itens do menu")
        ordering = ["order", "pk"]
        # A Central de Conteudo inteira e governada por
        # `content.change_pagesection`, que ja esta no catalogo. Criar
        # add/change/delete/view aqui seria criar quatro permissoes que
        # nada confere.
        default_permissions = ()

    def __str__(self):
        return self.label


class FaqItemQuerySet(models.QuerySet):
    def publicadas(self):
        """As perguntas que a Home mostra: ativas, na ordem definida."""
        return self.filter(is_active=True)


class FaqItem(TimeStampedModel):
    """
    Uma pergunta frequente da Home.

    POR QUE UM MODELO, E NAO UMA LISTA DENTRO DO JSON DA SECAO
    ----------------------------------------------------------
    Mesma razao de `MenuItem` e `Partner`: a QUANTIDADE e a decisao. O
    editor declarativo de secao edita os textos dos itens que ja
    existem -- nele nao ha como acrescentar nem remover um --, e uma
    secao de perguntas frequentes existe justamente para crescer.

    O QUE ELE NAO GUARDA
    --------------------
    Titulo e chamada da secao continuam sendo texto da `PageSection`,
    como em qualquer outra parte da Home. Aqui ficam so as perguntas.

    E O IDIOMA?
    -----------
    Pergunta e resposta sao campos simples, sem tabela de traducao --
    exatamente como `Partner.name`/`description` e `MenuItem.label`, que
    sao o precedente do projeto para cadastro administrado no produto.
    Num site de quatro idiomas isso e uma limitacao conhecida, e esta
    registrada no relatorio: resolve-la e dar tabela de traducao aos
    TRES cadastros de uma vez, nao inventar um formato so para este.
    """

    question = models.CharField(_("pergunta"), max_length=200)
    answer = models.TextField(
        _("resposta"),
        help_text=_("Texto simples. Quebras de linha são respeitadas."),
    )
    is_active = models.BooleanField(_("ativa"), default=True)
    order = models.PositiveIntegerField(
        _("ordem"), default=0, help_text=_("Menor aparece primeiro.")
    )

    objects = FaqItemQuerySet.as_manager()

    class Meta:
        verbose_name = _("pergunta frequente")
        verbose_name_plural = _("perguntas frequentes")
        ordering = ["order", "pk"]
        # Governada por `content.change_pagesection`, como o resto da
        # Central de Conteudo -- ver a mesma decisao em `MenuItem`.
        default_permissions = ()

    def __str__(self):
        return self.question
