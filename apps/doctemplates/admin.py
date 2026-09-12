"""Administracao de modelos de documento e suas versoes."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import LetterTemplate, Nationality, TemplateVersion


class TemplateVersionInline(admin.TabularInline):
    model = TemplateVersion
    extra = 0
    fields = ("version_number", "status", "published_at", "created_at")
    readonly_fields = ("published_at", "created_at")
    show_change_link = True
    can_delete = False
    ordering = ("-version_number",)


@admin.register(LetterTemplate)
class LetterTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "language", "is_active", "version_count", "updated_at")
    list_filter = ("language", "is_active")
    search_fields = ("name", "slug", "description")
    ordering = ("name", "language")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = [TemplateVersionInline]

    @admin.display(description=_("versões"))
    def version_count(self, obj):
        return obj.versions.count()


@admin.register(TemplateVersion)
class TemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("template", "version_number", "status", "published_at", "updated_at")
    list_filter = ("status", "template")
    search_fields = ("template__name", "template__slug")
    ordering = ("template", "-version_number")
    autocomplete_fields = ("template",)
    readonly_fields = ("published_at", "created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        """Uma vez publicada, os campos estruturais somem da tela de edicao
        (a regra de verdade fica em TemplateVersion.save(); isso e so para
        nao deixar o administrador tentar algo que vai ser recusado)."""
        fields = list(self.readonly_fields)
        if obj and obj.status == TemplateVersion.Status.PUBLISHED:
            fields += ["template", "version_number", "field_schema", "snapshot"]
        return fields


@admin.register(Nationality)
class NationalityAdmin(admin.ModelAdmin):
    """
    Cadastro das nacionalidades oferecidas no assistente.

    `code` fica somente-leitura depois de criado: e ele que vai gravado em
    Letter.data, entao muda-lo quebraria a ligacao das cartas ja feitas.
    """

    list_display = ("code", "name_pt", "guest_form", "host_form", "order", "is_active")
    list_filter = ("is_active",)
    list_editable = ("order", "is_active")
    search_fields = ("code", "name_pt", "name_fr", "name_nl", "name_en")
    ordering = ("order", "name_pt")
    fieldsets = (
        (None, {"fields": ("code", "is_active", "order")}),
        (_("Nomes na interface"), {"fields": ("name_pt", "name_fr", "name_nl", "name_en")}),
        (
            _("Formas usadas no documento"),
            {
                "fields": ("guest_form", "host_form"),
                "description": _(
                    "O documento oficial escreve a mesma nacionalidade de dois "
                    "jeitos: “Nationalité : Brésilienne” (convidado) e "
                    "“de nationalité belge” (anfitrião)."
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        return ("code",) if obj else ()
