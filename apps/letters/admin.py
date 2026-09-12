"""Administracao de cartas geradas."""

from django.contrib import admin

from .models import Letter


@admin.register(Letter)
class LetterAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "user",
        "template",
        "template_version",
        "language",
        "status",
        "generated_at",
    )
    list_filter = ("status", "language", "template")
    search_fields = ("reference", "user__email", "user__full_name", "uuid")
    ordering = ("-created_at",)
    autocomplete_fields = ("user", "template", "template_version")
    readonly_fields = ("uuid", "reference", "pdf_sha256", "created_at", "updated_at")
