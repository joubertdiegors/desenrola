"""
Usuario customizado do Desenrola.

O User e customizado desde a primeira migracao de proposito: trocar o modelo
de usuario depois que o banco ja tem dados e uma migracao de alto risco.

Regras vindas dos requisitos:
  - e-mail obrigatorio e unico (e usado como credencial de login);
  - nome completo obrigatorio;
  - telefone opcional;
  - endereco completo opcional.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Manager que cria usuarios por e-mail, nao por username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError(_("O e-mail e obrigatorio."))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Um superusuario precisa ter is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Um superusuario precisa ter is_superuser=True."))

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Usuario do sistema, identificado pelo e-mail."""

    # --- Credenciais -------------------------------------------------------
    email = models.EmailField(_("e-mail"), unique=True)

    # --- Dados pessoais ----------------------------------------------------
    full_name = models.CharField(_("nome completo"), max_length=150)
    phone = models.CharField(_("telefone"), max_length=32, blank=True)

    # --- Endereco (opcional) ----------------------------------------------
    address_line1 = models.CharField(_("endereco"), max_length=255, blank=True)
    address_line2 = models.CharField(_("complemento"), max_length=255, blank=True)
    postal_code = models.CharField(_("codigo postal"), max_length=20, blank=True)
    city = models.CharField(_("cidade"), max_length=120, blank=True)
    state = models.CharField(_("estado / provincia"), max_length=120, blank=True)
    country = models.CharField(_("pais"), max_length=120, blank=True)

    # --- Controle ----------------------------------------------------------
    is_active = models.BooleanField(_("ativo"), default=True)
    is_staff = models.BooleanField(
        _("acesso a administracao"),
        default=False,
        help_text=_("Define se o usuario pode acessar a area administrativa."),
    )
    date_joined = models.DateTimeField(_("cadastrado em"), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = _("usuario")
        verbose_name_plural = _("usuarios")
        ordering = ["full_name", "email"]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        """Primeiro nome, usado em saudacoes da interface."""
        return self.full_name.split(" ")[0] if self.full_name else self.email
