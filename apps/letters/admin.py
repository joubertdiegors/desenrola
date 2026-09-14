"""Administracao de cartas geradas."""

from django.contrib import admin

from .models import Letter


@admin.register(Letter)
class LetterAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "user",
        "document_template",
        "language",
        "status",
        "generated_at",
    )
    list_filter = ("status", "language", "document_template")
    search_fields = ("reference", "user__email", "user__full_name", "uuid")
    ordering = ("-created_at",)
    autocomplete_fields = ("user", "document_template")
    readonly_fields = ("uuid", "reference", "pdf_sha256", "created_at", "updated_at")
