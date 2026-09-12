"""
Formularios de usuario para a area administrativa.

As formularios nativos do Django assumem um campo `username`. Como o
Desenrola autentica por e-mail, precisamos ligar os formularios do admin ao
nosso modelo. Os formularios publicos (cadastro, login, recuperacao de senha)
serao implementados em fase posterior.
"""

from django.contrib.auth.forms import BaseUserCreationForm
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm

from .models import User


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
