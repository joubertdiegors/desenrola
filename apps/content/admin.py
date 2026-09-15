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
    Partner,
    SiteSettings,
)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    """
    Espelha as regras de integridade do Asset (ver `Asset.save()` e as
    FKs PROTECT de `template_references`/`letter_references`): o que o
    modelo vai recusar nem aparece como opcao. A regra de verdade continua
    no modelo e no ORM -- isto e so para o administrador nao tentar o que
    seria recusado.
    """

    list_display = ("__str__", "kind", "key", "is_active", "em_uso", "updated_at")
    list_filter = ("kind", "is_active")
    search_fields = ("key", "alt_text")
    ordering = ("kind", "key")

    @admin.display(description=_("em uso por"), boolean=False)
    def em_uso(self, obj):
        usos = []
        if obj.referenciado_por_modelo():
            usos.append(str(_("modelo")))
        if obj.referenciado_por_carta_finalizada():
            usos.append(str(_("carta finalizada")))
        return ", ".join(usos) or "—"

    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.referenciado_por_carta_finalizada():
            # O arquivo e o que uma carta finalizada reproduz; `save()`
            # recusaria a troca de qualquer jeito.
            campos.append("file")
        return campos

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (
            obj.referenciado_por_modelo() or obj.referenciado_por_carta_finalizada()
        ):
            return False
        return super().has_delete_permission(request, obj)


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


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    """
    Gestao dos parceiros da Home.

    SEM EXCLUSAO, de proposito: desativar tira o parceiro da Home na
    hora e mantem o registro de que houve acordo. E a mesma decisao ja
    tomada em modelos e usuarios -- e aqui nem existe a permissao
    `delete_partner` (ver `Partner.Meta`), entao o bloqueio nao depende
    so desta tela.
    """

    list_display = ("name", "order", "is_active", "logo", "url", "updated_at")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("order", "pk")
    autocomplete_fields = ("logo",)
    fieldsets = (
        (None, {"fields": ("name", "description")}),
        (
            _("Como aparece na Home"),
            {
                "fields": ("logo", "url", "order", "is_active"),
                "description": _(
                    "Sem logomarca, o cartao aparece sem imagem. Sem endereco, "
                    "ele nao e clicavel. So parceiros ativos aparecem."
                ),
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        return False
