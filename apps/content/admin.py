"""Administracao de conteudo, paginas, imagens e configuracoes do site."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Asset,
    ContentBlock,
    ContentTranslation,
    Page,
    PageSection,
    PageSectionTranslation,
    SiteSettings,
)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("__str__", "kind", "key", "is_active", "updated_at")
    list_filter = ("kind", "is_active")
    search_fields = ("key", "alt_text")
    ordering = ("kind", "key")


class ContentTranslationInline(admin.TabularInline):
    model = ContentTranslation
    extra = 1
    fields = ("language", "content", "asset")
    autocomplete_fields = ("asset",)


@admin.register(ContentBlock)
class ContentBlockAdmin(admin.ModelAdmin):
    list_display = ("key", "kind", "is_active", "translation_count", "updated_at")
    list_filter = ("kind", "is_active")
    search_fields = ("key",)
    ordering = ("key",)
    inlines = [ContentTranslationInline]

    @admin.display(description=_("traduções"))
    def translation_count(self, obj):
        return obj.translations.count()


@admin.register(ContentTranslation)
class ContentTranslationAdmin(admin.ModelAdmin):
    list_display = ("block", "language", "asset", "updated_at")
    list_filter = ("language",)
    search_fields = ("block__key", "content")
    ordering = ("block", "language")
    autocomplete_fields = ("block", "asset")


class PageSectionTranslationInline(admin.TabularInline):
    model = PageSectionTranslation
    extra = 1
    fields = ("language", "content")


class PageSectionInline(admin.TabularInline):
    model = PageSection
    extra = 0
    fields = ("kind", "order", "is_active", "key")
    ordering = ("order",)
    show_change_link = True


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "is_active", "section_count", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("key", "name")
    ordering = ("key",)
    inlines = [PageSectionInline]

    @admin.display(description=_("seções"))
    def section_count(self, obj):
        return obj.sections.count()


@admin.register(PageSection)
class PageSectionAdmin(admin.ModelAdmin):
    list_display = ("page", "kind", "order", "is_active", "key")
    list_filter = ("page", "kind", "is_active")
    search_fields = ("key", "page__key")
    ordering = ("page", "order")
    autocomplete_fields = ("page",)
    inlines = [PageSectionTranslationInline]


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Registro unico: o admin nao oferece 'adicionar' outra instancia."""

    list_display = ("site_name", "contact_email", "theme_primary_color", "updated_at")
    autocomplete_fields = ("logo", "favicon")
    fieldsets = (
        (None, {"fields": ("site_name",)}),
        (
            _("Contato"),
            {"fields": ("contact_email", "contact_phone", "contact_address")},
        ),
        (
            _("Identidade visual"),
            {"fields": ("logo", "favicon", "theme_primary_color", "theme_success_color")},
        ),
        (_("Redes sociais"), {"fields": ("social_links",)}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
