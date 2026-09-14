"""Administracao da biblioteca de documentos."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import DocumentTemplate, DocumentType, Nationality


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


# ---------------------------------------------------------------------------
# Biblioteca de modelos (nova arquitetura -- Etapa 1)
# ---------------------------------------------------------------------------


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "order", "template_count", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")
    ordering = ("order", "name")
    prepopulated_fields = {"code": ("name",)}
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description=_("modelos"))
    def template_count(self, obj):
        return obj.templates.count()


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    """
    Espelha as regras de `DocumentTemplate.save()`: o que o modelo nao
    aceita mudar aparece como somente leitura. A regra de verdade continua
    no modelo -- isto e so para o administrador nao tentar o que vai ser
    recusado.
    """

    list_display = (
        "name", "type", "language", "is_system", "is_locked",
        "is_active", "created_by", "created_at", "updated_at",
    )
    list_filter = ("type", "language", "is_system", "is_locked", "is_active")
    search_fields = ("name", "slug", "description")
    ordering = ("type", "-is_system", "language", "name")
    autocomplete_fields = ("type", "duplicated_from", "created_by")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("type", "name", "slug", "language", "description")}),
        (_("Estado"), {"fields": ("is_system", "is_locked", "is_active")}),
        (_("Origem"), {"fields": ("duplicated_from", "created_by")}),
        (_("Conteúdo"), {"fields": ("field_schema", "layout")}),
        (_("Datas"), {"fields": ("created_at", "updated_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        campos = list(self.readonly_fields)
        if obj is None:
            return campos
        if obj.is_locked:
            # Travado: tudo somente leitura, menos o proprio `is_locked`
            # (destravar e legitimo) e o administrativo simples.
            editaveis = {"is_locked", "description", "is_active"}
            campos += [
                f.name for f in obj._meta.concrete_fields
                if f.name not in editaveis and f.name not in campos and f.name != "id"
            ]
        elif obj.is_system:
            campos += [
                f.name for f in obj._meta.concrete_fields
                if f.name not in DocumentTemplate.SYSTEM_MUTABLE_FIELDS
                and f.name not in campos and f.name != "id"
            ]
        return campos

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (obj.is_locked or obj.is_system):
            return False
        return super().has_delete_permission(request, obj)
