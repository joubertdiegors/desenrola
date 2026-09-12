"""Administracao de usuarios."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .forms import UserChangeForm, UserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    list_display = ("email", "full_name", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser", "groups")
    search_fields = ("email", "full_name", "phone")
    ordering = ("full_name", "email")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Dados pessoais"), {"fields": ("full_name", "phone", "document_number")}),
        (
            _("Endereco"),
            {
                "fields": (
                    "address_line1",
                    "address_line2",
                    "postal_code",
                    "city",
                    "state",
                    "country",
                ),
            },
        ),
        (
            _("Permissoes"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Datas"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "password1", "password2"),
            },
        ),
    )
