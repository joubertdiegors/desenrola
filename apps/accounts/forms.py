"""
Formularios de conta.

Os formularios nativos do Django assumem um campo `username`. Como o
Desenrola autentica por e-mail, todos aqui apontam para o nosso modelo.

  - UserCreationForm / UserChangeForm: usados pelo Django Admin;
  - SignupForm: cadastro publico (cria o usuario com senha validada);
  - LoginForm: e-mail + senha, com mensagens no tom da interface;
  - ProfileForm: edicao dos dados do proprio usuario.

A troca de senha e a recuperacao usam os formularios nativos
(PasswordChangeForm, PasswordResetForm, SetPasswordForm).
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, BaseUserCreationForm
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm
from django.contrib.auth.forms import SetPasswordForm as DjangoSetPasswordForm
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm
from django.utils.translation import gettext_lazy as _

from .models import User

# Campos que o usuario edita no cadastro e no perfil.
PROFILE_FIELDS = (
    "full_name",
    "email",
    "phone",
    "birth_date",
    "nationality",
    "document_number",
    "address_line1",
    "postal_code",
    "city",
)

# Texto aprovado no layout para a confirmacao de senha. O catalogo `pt` do
# Django diz "palavra-passe"; os demais textos de validacao de senha ainda
# vem dele ate o catalogo do projeto (locale/pt) sobrescreve-los.
PASSWORD_MISMATCH = _("As senhas não coincidem.")


def _normalize_email(email):
    """E-mail sempre em minusculas: evita contas duplicadas por caixa."""
    return email.strip().lower()


class UserCreationForm(BaseUserCreationForm):
    """Criacao de usuario no admin, usando e-mail como credencial."""

    class Meta:
        model = User
        fields = ("email", "full_name")


class UserChangeForm(DjangoUserChangeForm):
    """Edicao de usuario no admin."""

    class Meta:
        model = User
        fields = "__all__"


class SignupForm(BaseUserCreationForm):
    """
    Cadastro publico.

    Herda a validacao de senha do Django (confirmacao, validadores de
    AUTH_PASSWORD_VALIDATORS) e guarda a senha com hash.
    """

    terms = forms.BooleanField(
        required=True,
        error_messages={
            "required": _("É preciso aceitar os Termos de uso e a Política de privacidade.")
        },
    )
    error_messages = {"password_mismatch": PASSWORD_MISMATCH}

    class Meta:
        model = User
        fields = PROFILE_FIELDS

    def clean_email(self):
        email = _normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("Já existe uma conta com este e-mail."))
        return email


class PasswordChangeForm(DjangoPasswordChangeForm):
    """Troca de senha no perfil (exige a senha atual)."""

    error_messages = {
        **DjangoPasswordChangeForm.error_messages,
        "password_mismatch": PASSWORD_MISMATCH,
        "password_incorrect": _("Senha atual incorreta."),
    }


class SetPasswordForm(DjangoSetPasswordForm):
    """Nova senha a partir do link de recuperacao."""

    error_messages = {
        **DjangoSetPasswordForm.error_messages,
        "password_mismatch": PASSWORD_MISMATCH,
    }


class LoginForm(AuthenticationForm):
    """E-mail + senha. O campo `username` e o e-mail (USERNAME_FIELD)."""

    error_messages = {
        "invalid_login": _("E-mail ou senha incorretos."),
        "inactive": _("Esta conta está desativada."),
    }


class ProfileForm(forms.ModelForm):
    """Dados pessoais do proprio usuario (nunca de outro)."""

    class Meta:
        model = User
        fields = PROFILE_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Data de nascimento: mesma convencao do assistente -- a pessoa ve
        # e digita dd/mm/aaaa, o banco guarda ISO. O `data-date-input`
        # liga a mascara e o calendario nativo (static/js/app.js).
        nascimento = self.fields["birth_date"]
        nascimento.input_formats = ["%d/%m/%Y", "%Y-%m-%d"]
        nascimento.widget = forms.DateInput(
            format="%d/%m/%Y",
            attrs={
                "class": "input",
                "placeholder": "DD/MM/AAAA",
                "inputmode": "numeric",
                "autocomplete": "bday",
                "maxlength": "10",
                "data-date-input": "",
            },
        )

        # Nacionalidade: so as ativas do cadastro administravel. Nunca
        # texto livre -- e dela que sai a forma gramatical impressa no
        # documento oficial.
        from apps.doctemplates.models import Nationality

        nacionalidade = self.fields["nationality"]
        nacionalidade.queryset = Nationality.objects.active()
        nacionalidade.empty_label = "---------"
        nacionalidade.widget.attrs.setdefault("class", "input")

    def clean_email(self):
        email = _normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Já existe uma conta com este e-mail."))
        return email
