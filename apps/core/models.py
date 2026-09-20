"""Modelos base compartilhados por todos os apps do projeto."""

from email.utils import formataddr

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core import crypto


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


class EmailSettings(TimeStampedModel):
    """
    Como o sistema envia e-mail -- um único registro (singleton), no
    mesmo padrão de `content.SiteSettings` e `letters.LetterPolicy`.

    NO BANCO, NÃO NO `.env`
    -----------------------
    O servidor de e-mail muda sem deploy: troca de provedor, senha de
    aplicativo revogada, porta bloqueada pelo provedor de hospedagem.
    Quem administra o produto precisa resolver isso pela tela, não
    pedindo a alguém que edite um arquivo no servidor e reinicie a
    aplicação.

    A `EMAIL_URL` do ambiente continua existindo como REDE DE SEGURANÇA
    (ver `config.settings.prod`): é para onde as mensagens vão enquanto
    não houver configuração ativa aqui.

    A SENHA
    -------
    Guardada cifrada (`apps.core.crypto`), nunca em texto puro e nunca
    devolvida a uma tela. Não é hash: o sistema precisa REAPRESENTÁ-LA
    ao servidor SMTP a cada conexão, então tem de conseguir lê-la de
    volta. O que um hash resolveria -- conferir uma senha digitada --
    não é o problema aqui.

    Quem quiser trocá-la digita a nova; quem não quiser deixa o campo
    em branco e a guardada continua. Não existe caminho que a mostre.
    """

    SINGLETON_ID = 1

    # Quanto esperar o servidor SMTP, em segundos. Curto de propósito:
    # esta conexão acontece DENTRO de uma requisição (o teste de envio,
    # a recuperação de senha), e um host errado não pode prender o
    # processo até o navegador desistir.
    TEMPO_LIMITE = 10

    class Security(models.TextChoices):
        NENHUMA = "nenhuma", _("Nenhuma — sem criptografia")
        TLS = "tls", _("STARTTLS — normalmente porta 587")
        SSL = "ssl", _("SSL/TLS direto — normalmente porta 465")

    # Um campo só, e não dois booleanos: TLS e SSL são exclusivos, e
    # duas caixas deixariam existir o estado "as duas marcadas", que o
    # Django rejeita só na hora de conectar.
    security = models.CharField(
        _("segurança da conexão"),
        max_length=8,
        choices=Security.choices,
        default=Security.TLS,
    )

    is_active = models.BooleanField(
        _("envio ativo"),
        default=False,
        help_text=_("Desligado, as mensagens seguem para o destino de reserva do ambiente."),
    )

    host = models.CharField(_("servidor SMTP"), max_length=255, blank=True)
    port = models.PositiveIntegerField(
        _("porta"),
        default=587,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
    )
    username = models.CharField(_("usuário"), max_length=255, blank=True)

    # `editable=False` mantém a coluna fora de qualquer ModelForm: não
    # existe formulário que a exiba porque não existe campo para exibir.
    # A senha entra por `definir_senha()` e sai por `senha()`.
    password_encrypted = models.TextField(_("senha (cifrada)"), blank=True, editable=False)

    from_email = models.EmailField(_("remetente"), blank=True)
    from_name = models.CharField(_("nome do remetente"), max_length=150, blank=True)

    # A CÓPIA OCULTA
    # --------------
    # Um endereço que recebe, em BCC, TODA mensagem que o site manda --
    # confirmação de e-mail, recuperação de senha, o que vier depois.
    # Serve de arquivo: quem administra o produto consegue ver o que
    # saiu sem pedir ao destinatário.
    #
    # Em branco (o padrão) não existe cópia nenhuma. Não é o mesmo que
    # `username` ou `from_email`: não entra em `pronta_para_enviar()`,
    # porque um e-mail sem cópia oculta é um e-mail perfeitamente
    # válido.
    #
    # Quem aplica é `apps.core.mail`, no ponto único de envio. Aqui só
    # fica o endereço. O Django escreve `To:` e `Cc:` no cabeçalho e
    # NUNCA `Bcc:` -- é isso que faz a cópia ser oculta de verdade, e
    # não uma convenção nossa.
    bcc_email = models.EmailField(_("enviar cópia oculta para"), blank=True)

    # Quem mexeu por último. `SET_NULL` porque a configuração sobrevive
    # à conta de quem a cadastrou -- apagar a pessoa não pode derrubar o
    # envio de e-mail do sistema inteiro.
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("alterada por"),
    )

    class Meta:
        # Sem `add` nem `delete`: é um registro só, que sempre existe.
        # Uma permissão de "adicionar configuração de e-mail" não
        # controlaria nada.
        default_permissions = ("view", "change")
        verbose_name = _("configuração de e-mail")
        verbose_name_plural = _("configuração de e-mail")

    def __str__(self):
        # Constante de propósito: este texto vai para logs, para o
        # histórico do admin e para mensagens de erro. Nada de host,
        # usuário ou remetente aqui.
        return str(_("Configuração de e-mail"))

    def save(self, *args, **kwargs):
        # Singleton: sempre o mesmo id, para nunca haver duas
        # configurações "vigentes" (mesma decisão de `SiteSettings` e de
        # `LetterPolicy`). Obtenha o registro por `mail.configuracao()`.
        self.pk = self.SINGLETON_ID
        super().save(*args, **kwargs)

    # --- a senha ----------------------------------------------------------
    def definir_senha(self, valor):
        """Guarda a senha cifrada. Valor vazio APAGA a senha guardada."""
        self.password_encrypted = crypto.cifrar(valor) if valor else ""

    def senha(self):
        """
        A senha em texto puro, ou `None` se não houver -- ou se a chave
        do ambiente mudou e o que está guardado virou ilegível.

        Só `apps.core.mail` chama isto, na hora de abrir a conexão.
        Nenhuma view, nenhum template, nenhum log.
        """
        return crypto.decifrar(self.password_encrypted)

    @property
    def tem_senha(self):
        """Há alguma senha guardada? (Não diz qual -- e é só isso que as telas precisam saber.)"""
        return bool(self.password_encrypted)

    @property
    def senha_ilegivel(self):
        """
        Há senha guardada, mas ela não decifra mais.

        Acontece quando a chave do ambiente muda. A tela avisa e pede
        uma nova; o dado não "sumiu", só deixou de ser legível.
        """
        return self.tem_senha and self.senha() is None

    # --- o remetente ------------------------------------------------------
    def remetente(self):
        """
        O `From` das mensagens: "Nome <endereco>", ou só o endereço se
        não houver nome. Vazio quando nem o endereço foi cadastrado.
        """
        if not self.from_email:
            return ""
        if not self.from_name:
            return self.from_email
        return formataddr((self.from_name, self.from_email))

    def pronta_para_enviar(self):
        """
        Dá para abrir uma conexão SMTP com isto agora?

        Ligada, com servidor e com remetente. A senha NÃO entra na
        conta: há relays internos que não pedem autenticação, e exigi-la
        aqui impediria uma configuração legítima.
        """
        return bool(self.is_active and self.host and self.from_email)

    def clean(self):
        super().clean()
        erros = {}
        if self.is_active:
            # Ligar sem isto criaria uma configuração que parece pronta
            # e falha em toda mensagem -- inclusive na recuperação de
            # senha de quem está trancado para fora.
            if not self.host:
                erros["host"] = _("Informe o servidor SMTP para ativar o envio.")
            if not self.from_email:
                erros["from_email"] = _("Informe o remetente para ativar o envio.")
        if self.username and not self.password_encrypted:
            erros["username"] = _(
                "Com usuário preenchido é preciso haver uma senha cadastrada."
            )
        if erros:
            raise ValidationError(erros)
