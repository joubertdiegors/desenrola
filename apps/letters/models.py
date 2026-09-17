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
from django.core.exceptions import ValidationError
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

    # Quando a carta foi finalizada pela PRIMEIRA vez. E o marco zero das
    # politicas de ciclo de vida (apps.letters.lifecycle) -- por isso nao
    # se move: reeditar e finalizar de novo NAO reinicia o prazo, senao
    # bastaria reeditar uma vez para ter prazo infinito.
    #
    # Nao confundir com `snapshot["finalized_at"]`, que e a data impressa
    # no documento e acompanha cada nova versao dele.
    finalized_at = models.DateTimeField(_("finalizada em"), null=True, blank=True)

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


# ===========================================================================
# Politica administrativa do ciclo de vida
# ===========================================================================


class LetterPolicy(TimeStampedModel):
    """
    As duas regras de negocio do ciclo de vida da carta, configuradas no
    Backoffice -- um unico registro (singleton), no mesmo padrao de
    `content.SiteSettings`.

    EDITABILIDADE e EXPIRACAO sao INDEPENDENTES: uma carta pode expirar
    sem nunca ter sido editavel, ou continuar editavel depois de expirar
    (configuracao possivel, ainda que incomum). Cada pergunta tem a sua
    politica e a sua quantidade.

    NO BANCO, NAO NO CODIGO
    -----------------------
    Sao decisoes de negocio que mudam sem deploy. O calculo fica em
    `apps.letters.lifecycle`; aqui so moram os VALORES.

    ESCOPO
    ------
    Hoje a politica e GLOBAL: um registro vale para todas as cartas.
    Quando for preciso variar por tipo/modelo de documento, o caminho e
    acrescentar uma FK opcional para `DocumentTemplate` com
    `unique` e resolver "o do modelo, senao o global" em
    `lifecycle.policy_for()` -- as duas unicas mudancas necessarias.
    Nao ha coluna especulativa aqui enquanto nao houver essa tela.

    PADRAO = O COMPORTAMENTO DE HOJE
    --------------------------------
    `NAO_EDITAVEL` + `NUNCA`: e exatamente o que o sistema fazia antes
    desta etapa. Instalar a novidade nao muda nada para ninguem ate um
    administrador escolher outra coisa.
    """

    SINGLETON_ID = 1

    class Editability(models.TextChoices):
        NAO_EDITAVEL = "nao_editavel", _("Não pode ser editada")
        POR_HORAS = "por_horas", _("Por algumas horas após finalizar")
        POR_DIAS = "por_dias", _("Por alguns dias após finalizar")
        ATE_DATA_VIAGEM = "ate_data_viagem", _("Até a data da viagem")
        ATE_X_DIAS_APOS_CRIACAO = "ate_x_dias_apos_criacao", _("Até X dias após a criação")

    class Expiration(models.TextChoices):
        NUNCA = "nunca", _("Nunca expira")
        NA_DATA_DA_VIAGEM = "na_data_da_viagem", _("Na data da viagem")
        X_DIAS_ANTES_DA_VIAGEM = "x_dias_antes_da_viagem", _("X dias antes da viagem")
        X_DIAS_DEPOIS_DA_VIAGEM = "x_dias_depois_da_viagem", _("X dias depois da viagem")
        X_DIAS_APOS_CRIACAO = "x_dias_apos_criacao", _("X dias após a criação")

    # As politicas que precisam de um numero para significar alguma coisa.
    EDITABILIDADE_COM_QUANTIDADE = frozenset(
        {
            Editability.POR_HORAS,
            Editability.POR_DIAS,
            Editability.ATE_X_DIAS_APOS_CRIACAO,
        }
    )
    EXPIRACAO_COM_QUANTIDADE = frozenset(
        {
            Expiration.X_DIAS_ANTES_DA_VIAGEM,
            Expiration.X_DIAS_DEPOIS_DA_VIAGEM,
            Expiration.X_DIAS_APOS_CRIACAO,
        }
    )

    editability = models.CharField(
        _("edição após finalizar"),
        max_length=32,
        choices=Editability.choices,
        default=Editability.NAO_EDITAVEL,
    )
    editability_amount = models.PositiveIntegerField(
        _("quantidade (edição)"),
        default=0,
        help_text=_("Horas ou dias, conforme a política escolhida."),
    )

    expiration = models.CharField(
        _("expiração"),
        max_length=32,
        choices=Expiration.choices,
        default=Expiration.NUNCA,
    )
    expiration_amount = models.PositiveIntegerField(
        _("quantidade (expiração)"),
        default=0,
        help_text=_("Dias, conforme a política escolhida."),
    )

    class Meta:
        verbose_name = _("política das cartas")
        verbose_name_plural = _("política das cartas")

    def __str__(self):
        return str(_("Política das cartas"))

    def clean(self):
        super().clean()
        erros = {}
        if self.editability in self.EDITABILIDADE_COM_QUANTIDADE and not self.editability_amount:
            erros["editability_amount"] = _(
                "Informe um número maior que zero para esta política de edição."
            )
        if self.expiration in self.EXPIRACAO_COM_QUANTIDADE and not self.expiration_amount:
            erros["expiration_amount"] = _(
                "Informe um número maior que zero para esta política de expiração."
            )
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        # Singleton: sempre o mesmo id, para nunca haver duas politicas
        # "vigentes" ao mesmo tempo (mesma decisao de SiteSettings).
        #
        # A forma certa de obter o registro e `lifecycle.policy()`:
        # carregar, alterar, salvar. Construir um SEGUNDO objeto e
        # salva-lo nao cria linha nova nem sobrescreve em silencio --
        # falha alto (IntegrityError), porque o UPDATE resultante
        # levaria `created_at` nulo para a linha existente.
        self.pk = self.SINGLETON_ID
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Idiomas do documento
# ---------------------------------------------------------------------------
#
# ATENCAO: "idioma" aqui e o idioma da CARTA, nunca o da interface. A
# interface e so portuguesa desde a Etapa 4.1 e continua sendo (ver
# `apps.core.middleware.InterfaceEmPortuguesMiddleware`). Sao duas
# decisoes separadas, e uma nunca deve virar padrao da outra.


def idiomas_oficiais():
    """
    Os codigos de idioma que uma Carta Convite pode ter.

    Vem de `settings.LANGUAGES` -- a lista-mae, que tambem alimenta
    `Letter.language`, `DocumentTemplate.language` e os quatro modelos
    oficiais de `doctemplates.services.biblioteca.MODELOS_OFICIAIS`.
    Nao ha segunda lista: acrescentar um idioma ao produto e acrescentar
    la, e nao aqui.

    E funcao (e nao constante) porque e o `default` de um campo: precisa
    ser avaliada no momento em que uma linha nasce, nao no import.
    """
    return [code for code, _label in settings.LANGUAGES]


# O idioma em que uma carta nova nasce quando ninguem configurou nada.
#
# E uma DECISAO DE PRODUTO explicita, nao um reflexo do idioma da
# interface: ate a Etapa 4.1 o rascunho nascia no idioma em que a pessoa
# navegava, o que deixou de fazer sentido quando a interface passou a ser
# so portuguesa. A pessoa continua trocando o idioma do documento na
# etapa 5.
#
# A partir da Etapa E isto e o PADRAO DE FABRICA, nao mais a palavra
# final: quem decide e `DocumentLanguageSettings`, e este valor e com o
# que ela nasce. Continua sendo a resposta quando nao ha configuracao
# alguma -- instalacao nova, ou banco em estado inesperado.
IDIOMA_PADRAO_DA_CARTA = "en"


class DocumentLanguageSettings(TimeStampedModel):
    """
    Quais idiomas uma carta NOVA pode ter, e em qual ela nasce -- um
    unico registro (singleton), no mesmo padrao de `LetterPolicy` e
    `content.SiteSettings`.

    O QUE ESTA CONFIGURACAO DECIDE, E O QUE NAO DECIDE
    --------------------------------------------------
    Decide apenas o que o assistente OFERECE. Nao apaga modelo oficial,
    nao altera carta existente e nao mexe em nada ja gerado: tirar um
    idioma daqui e parar de oferece-lo daqui para a frente, nada mais.
    Uma carta ja escrita naquele idioma continua abrindo, continua
    gerando PDF e continua com o mesmo documento oficial vinculado --
    `Letter.document_template` e uma FK resolvida uma vez, na criacao,
    e nunca reconsultada por idioma.

    POR QUE SINGLETON, E NAO UMA LINHA POR IDIOMA
    ---------------------------------------------
    As duas regras desta configuracao sao sobre o CONJUNTO, nao sobre um
    idioma isolado: "tem de sobrar pelo menos um" e "o padrao tem de
    estar entre os disponiveis". Uma tabela com quatro linhas nao
    consegue afirmar nenhuma das duas no `clean()` de uma linha -- cada
    uma so enxerga a si mesma, e a regra teria de viver so no
    formulario. Aqui as duas moram no `clean()` do registro, e valem
    para qualquer caminho de codigo, como em `LetterPolicy.clean()`.

    O JSON NAO E LIVRE
    ------------------
    `available_document_languages` e uma lista de codigos de um conjunto
    FECHADO de quatro, conferida inteira no `clean()`: nada de desconhecido,
    nada repetido, nunca vazia. Nao e conteudo arbitrario -- e um
    conjunto de enum, guardado na unica forma que o Django oferece para
    conjuntos sem inventar uma tabela de apoio.
    """

    SINGLETON_ID = 1

    available_document_languages = models.JSONField(
        _("idiomas disponíveis"),
        default=idiomas_oficiais,
        help_text=_("Os idiomas que o assistente oferece para uma carta nova."),
    )
    default_letter_language = models.CharField(
        _("idioma padrão de novas cartas"),
        max_length=8,
        choices=settings.LANGUAGES,
        default=IDIOMA_PADRAO_DA_CARTA,
        help_text=_("Precisa estar entre os idiomas disponíveis."),
    )

    class Meta:
        verbose_name = _("idiomas do documento")
        verbose_name_plural = _("idiomas do documento")
        # So a permissao que o produto de fato confere. Ver esta
        # configuracao exige apenas `core.access_backoffice` -- uma regra
        # que vale para todo mundo pode ser lida por quem administra;
        # altera-la e outra coisa (mesma decisao de
        # `backoffice_letter_policy`). `view`, `add` e `delete` seriam
        # tres permissoes que nada confere.
        default_permissions = ("change",)

    def __str__(self):
        return str(_("Idiomas do documento"))

    def clean(self):
        super().clean()
        oficiais = idiomas_oficiais()
        codigos = self.available_document_languages

        if not isinstance(codigos, list) or not all(isinstance(c, str) for c in codigos):
            raise ValidationError(
                {
                    "available_document_languages": _(
                        "Os idiomas disponíveis devem ser uma lista de códigos."
                    )
                }
            )

        desconhecidos = [c for c in codigos if c not in oficiais]
        if desconhecidos:
            raise ValidationError(
                {
                    "available_document_languages": _(
                        "Idioma desconhecido: %(codigos)s."
                    )
                    % {"codigos": ", ".join(sorted(desconhecidos))}
                }
            )

        if len(set(codigos)) != len(codigos):
            raise ValidationError(
                {
                    "available_document_languages": _(
                        "Há idioma repetido na lista de disponíveis."
                    )
                }
            )

        if not codigos:
            raise ValidationError(
                {
                    "available_document_languages": _(
                        "Pelo menos um idioma precisa ficar disponível: sem nenhum, "
                        "não seria possível gerar carta nova."
                    )
                }
            )

        if self.default_letter_language not in codigos:
            raise ValidationError(
                {
                    "default_letter_language": _(
                        "O idioma padrão precisa estar entre os idiomas disponíveis."
                    )
                }
            )

    def save(self, *args, **kwargs):
        # Singleton: sempre o mesmo id, pela mesma razao de `LetterPolicy`
        # e `content.SiteSettings` -- nunca duas configuracoes "vigentes".
        # A forma certa de obter o registro e
        # `apps.letters.services.configuracao_de_idiomas()`.
        self.pk = self.SINGLETON_ID
        super().save(*args, **kwargs)


class LetterNoticeQuerySet(models.QuerySet):
    def publicadas(self):
        """As declaracoes que a etapa 4 mostra: ativas, na ordem definida."""
        return self.filter(is_active=True)


class LetterNotice(TimeStampedModel):
    """
    Uma declaracao que o usuario aceita na etapa 4 do assistente.

    POR QUE SAIU DO `field_schema`
    ------------------------------
    Os dois textos nasceram como constantes Python dentro do
    `field_schema` do modelo oficial (`doctemplates.official_templates`).
    Ali eles eram inalcancaveis para quem administra: o `field_schema` e
    estrutura do DOCUMENTO -- `DocumentTemplate.save()` recusa altera-lo
    depois que existe carta emitida, justamente para a reproducao
    historica continuar valendo --, e mudar um texto juridico nao pode
    depender de uma migration.

    Aqui eles sao CADASTRO, no mesmo formato que o projeto ja usa para
    `content.FaqItem`, `content.MenuItem` e `content.Partner`: texto,
    ativo e ordem, administrados no Backoffice.

    O QUE ESTE MODELO NAO DECIDE
    ----------------------------
    Nada sobre o PDF. Estas declaracoes sao aceites de ciencia, exibidos
    e gravados em `Letter.data` -- o documento gerado nao as imprime (a
    declaracao do anfitriao que sai no PDF e outra coisa, montada em
    `doctemplates.services.carta_convite`). Desativar uma aqui nao muda
    nenhuma carta ja emitida.

    A CHAVE E ESTAVEL
    -----------------
    `key` e o nome com que a resposta fica gravada em `Letter.data`, e
    por isso nao acompanha o texto: reescrever a declaracao mantem o
    historico das cartas que ja a aceitaram. As duas chaves originais
    (`notice_informal`, `notice_prise_en_charge`) continuam sendo as
    mesmas depois da migracao.
    """

    key = models.SlugField(
        _("identificador"),
        max_length=60,
        unique=True,
        help_text=_(
            "Nome interno com que a resposta fica gravada na carta. "
            "Não muda quando o texto muda."
        ),
    )
    text = models.TextField(
        _("texto da declaração"),
        help_text=_("Texto simples, na primeira pessoa (\"Declaro estar ciente...\")."),
    )
    is_active = models.BooleanField(
        _("ativa"),
        default=True,
        help_text=_("Só declarações ativas aparecem no assistente."),
    )
    order = models.PositiveIntegerField(
        _("ordem"), default=0, help_text=_("Menor aparece primeiro.")
    )

    objects = LetterNoticeQuerySet.as_manager()

    class Meta:
        verbose_name = _("declaração do assistente")
        verbose_name_plural = _("declarações do assistente")
        # `pk` desempata: duas declaracoes com a mesma ordem trocariam de
        # lugar entre uma visita e outra sem isto.
        ordering = ["order", "pk"]

    def __str__(self):
        return self.key

    def como_campo(self):
        """
        A declaracao no formato que o assistente entende -- o mesmo dict
        que `field_schema` produz para um checkbox.

        E aqui que os dois mundos se encontram: o formulario dinamico
        (`letters.forms.build_dynamic_form`), a validacao e a revisao da
        etapa 6 continuam recebendo a mesma estrutura de sempre, sem
        saber que a origem mudou.
        """
        return {
            "key": self.key,
            "type": "checkbox",
            "required": True,
            "order": self.order,
            "section": "avisos",
            "full_width": True,
            "label": self.text,
        }
