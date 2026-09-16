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

import datetime

from django import forms
from django.contrib.auth.forms import AuthenticationForm, BaseUserCreationForm
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm
from django.contrib.auth.forms import SetPasswordForm as DjangoSetPasswordForm
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm
from django.utils.translation import gettext_lazy as _

from .models import User
from .telefone import CampoDeTelefone

# Os dois formatos que o campo de nascimento aceita na entrada -- mesma
# convencao do assistente (apps/letters/forms.py).
BIRTH_DATE_INPUT_FORMATS = ["%d/%m/%Y", "%Y-%m-%d"]


class _RobustDateInput(forms.DateInput):
    """
    Reexibe em dd/mm/aaaa qualquer valor já vinculado reconhecível, não
    só um `date` de verdade -- mesmo problema e mesma solução do widget
    homônimo em `apps.letters.forms`: um valor vinculado a partir de um
    POST é uma string, e o `DateInput` padrão só reformata um `date`
    real, nunca uma string já vinculada. Sem isto, um erro no e-mail (por
    exemplo) reexibia a data de nascimento do jeito que chegasse no
    corpo do POST, não necessariamente em dd/mm/aaaa.
    """

    def format_value(self, value):
        if isinstance(value, str) and value:
            for input_format in BIRTH_DATE_INPUT_FORMATS:
                try:
                    parsed = datetime.datetime.strptime(value, input_format).date()
                except ValueError:
                    continue
                return parsed.strftime(self.format or "%d/%m/%Y")
        return super().format_value(value)

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

# O placeholder do e-mail. Um so, nas duas telas que o pedem: nada de
# uma tela sugerir um formato e a outra sugerir outro.
EXEMPLO_DE_EMAIL = "seuemail@email.com"

# Campos que sao TEXTO no banco e teclado numerico na tela.
#
# Nunca `type="number"`: codigo postal, documento e passaporte podem
# comecar por zero, conter letras ou vir com formatacao, e o navegador
# descarta tudo isso num campo numerico -- alem de oferecer setinhas de
# incremento, que nao significam nada num documento.
CAMPOS_DE_TEXTO_COM_TECLADO_NUMERICO = {
    "postal_code": "1000",
}

# O que cada campo do perfil sugere quando esta vazio.
PLACEHOLDERS_DO_PERFIL = {
    "full_name": _("Nome e sobrenome, como no documento"),
    "document_number": _("Número do documento de identidade"),
    "address_line1": _("Rua, número, complemento"),
    "city": _("Bruxelas"),
}


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
    # O MESMO campo do perfil: seletor de país + número. Antes o `+32`
    # era um `<span>` desenhado ao lado, e quem tinha telefone de outro
    # país não conseguia gravar o próprio número.
    phone = CampoDeTelefone(label=_("telefone"))
    error_messages = {"password_mismatch": PASSWORD_MISMATCH}

    class Meta:
        model = User
        fields = PROFILE_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.setdefault("placeholder", EXEMPLO_DE_EMAIL)

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

    # O mesmo campo do cadastro -- uma solução de telefone no projeto,
    # não uma por tela.
    phone = CampoDeTelefone(label=_("telefone"))

    class Meta:
        model = User
        fields = PROFILE_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Data de nascimento: mesma convencao do assistente -- a pessoa ve
        # e digita dd/mm/aaaa, o banco guarda ISO. O `data-date-input`
        # liga a mascara e o calendario nativo (static/js/app.js).
        nascimento = self.fields["birth_date"]
        nascimento.input_formats = BIRTH_DATE_INPUT_FORMATS
        nascimento.widget = _RobustDateInput(
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

        self.fields["email"].widget.attrs.setdefault("placeholder", EXEMPLO_DE_EMAIL)

        # Os campos que NÃO podem virar número: um código postal belga
        # começa por zero em boa parte do país, e `type="number"` o
        # comeria. `inputmode` abre o teclado numérico no celular sem
        # nenhum desses efeitos.
        for nome, exemplo in CAMPOS_DE_TEXTO_COM_TECLADO_NUMERICO.items():
            if nome in self.fields:
                self.fields[nome].widget.attrs.setdefault("inputmode", "numeric")
                self.fields[nome].widget.attrs.setdefault("placeholder", exemplo)

        for nome, exemplo in PLACEHOLDERS_DO_PERFIL.items():
            if nome in self.fields:
                self.fields[nome].widget.attrs.setdefault("placeholder", exemplo)

        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "input")

    def clean_email(self):
        email = _normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Já existe uma conta com este e-mail."))
        return email
