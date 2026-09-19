"""
Testes de ContentBlock/ContentTranslation, Asset, Page/PageSection e
SiteSettings.
"""

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from apps.content.models import (
    Asset,
    ContentBlock,
    ContentTranslation,
    Page,
    PageSection,
    PageSectionTranslation,
    SiteSettings,
)

pytestmark = pytest.mark.django_db


def _gif(name="foto.gif"):
    """Um GIF 1x1 valido, minimo o bastante para o ImageField aceitar."""
    content = (
        b"GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04"
        b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    )
    return SimpleUploadedFile(name, content, content_type="image/gif")


@pytest.fixture
def content_block():
    return ContentBlock.objects.create(key="landing.hero.title", kind=ContentBlock.Kind.TEXT)


class TestContentBlock:
    def test_criacao(self, content_block):
        assert content_block.key == "landing.hero.title"
        assert content_block.kind == ContentBlock.Kind.TEXT
        assert content_block.is_active is True

    def test_identificador_e_unico(self, content_block):
        with pytest.raises(IntegrityError), transaction.atomic():
            ContentBlock.objects.create(key=content_block.key)

    def test_tipos_disponiveis(self):
        assert set(ContentBlock.Kind.values) == {"text", "rich_text", "image", "structured"}

    def test_pode_ficar_inativo(self, content_block):
        content_block.is_active = False
        content_block.save()
        content_block.refresh_from_db()
        assert content_block.is_active is False


class TestContentTranslation:
    def test_criacao(self, content_block):
        translation = ContentTranslation.objects.create(
            block=content_block, language="pt", content="Gere sua Carta Convite"
        )

        assert translation.block == content_block
        assert translation.content == "Gere sua Carta Convite"

    def test_suporta_os_quatro_idiomas(self, content_block):
        for code, text in [
            ("pt", "Texto em português"),
            ("fr", "Texte en français"),
            ("nl", "Tekst in het Nederlands"),
            ("en", "Text in English"),
        ]:
            translation = ContentTranslation.objects.create(
                block=content_block, language=code, content=text
            )
            assert translation.language == code

        assert content_block.translations.count() == 4

    def test_unicidade_entre_bloco_e_idioma(self, content_block):
        ContentTranslation.objects.create(block=content_block, language="pt", content="Um")

        with pytest.raises(IntegrityError), transaction.atomic():
            ContentTranslation.objects.create(block=content_block, language="pt", content="Dois")

    def test_mesmo_idioma_permitido_em_blocos_diferentes(self, content_block):
        outro_bloco = ContentBlock.objects.create(key="landing.hero.subtitle")

        ContentTranslation.objects.create(block=content_block, language="pt", content="Um")
        outra = ContentTranslation.objects.create(block=outro_bloco, language="pt", content="Dois")

        assert outra.pk is not None

    def test_excluir_bloco_remove_as_traducoes(self, content_block):
        ContentTranslation.objects.create(block=content_block, language="pt", content="Um")
        block_id = content_block.pk

        content_block.delete()

        assert ContentTranslation.objects.filter(block_id=block_id).count() == 0

    def test_bloco_de_imagem_pode_ter_asset_por_idioma(self, content_block):
        content_block.kind = ContentBlock.Kind.IMAGE
        content_block.save()
        asset = Asset.objects.create(kind=Asset.Kind.HOME, file=_gif())

        translation = ContentTranslation.objects.create(
            block=content_block, language="pt", asset=asset
        )

        assert translation.asset == asset

    def test_excluir_asset_nao_apaga_a_traducao(self, content_block):
        asset = Asset.objects.create(kind=Asset.Kind.HOME, file=_gif())
        translation = ContentTranslation.objects.create(
            block=content_block, language="pt", asset=asset
        )

        asset.delete()
        translation.refresh_from_db()

        assert translation.asset is None


# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------


class TestAsset:
    def test_criacao(self):
        asset = Asset.objects.create(
            key="site-logo", kind=Asset.Kind.LOGO, file=_gif(), alt_text="Desenrola"
        )

        assert asset.kind == Asset.Kind.LOGO
        assert asset.is_active is True
        assert asset.file.name.startswith("assets/")

    def test_tipos_disponiveis(self):
        assert set(Asset.Kind.values) == {
            "logo",
            "favicon",
            "home",
            "partner",
            "content",
            "other",
        }

    def test_chave_e_opcional(self):
        asset = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif())
        assert asset.key is None

    def test_varios_assets_sem_chave_sao_permitidos(self):
        Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif("a.gif"))
        outro = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif("b.gif"))

        assert outro.pk is not None

    def test_chave_e_unica_quando_definida(self):
        Asset.objects.create(key="site-logo", kind=Asset.Kind.LOGO, file=_gif("a.gif"))

        with pytest.raises(IntegrityError), transaction.atomic():
            Asset.objects.create(key="site-logo", kind=Asset.Kind.LOGO, file=_gif("b.gif"))

    def test_pode_ficar_inativo(self):
        asset = Asset.objects.create(kind=Asset.Kind.OTHER, file=_gif())
        asset.is_active = False
        asset.save()
        asset.refresh_from_db()
        assert asset.is_active is False


# ---------------------------------------------------------------------------
# Page / PageSection / PageSectionTranslation
# ---------------------------------------------------------------------------


@pytest.fixture
def pagina():
    """
    Uma página qualquer, para testar o MODELO.

    Não usa a chave "home": essa é a Home de verdade, semeada pela
    migration `content.0004`, e criar outra com o mesmo identificador
    esbarraria na restrição de unicidade.
    """
    return Page.objects.create(key="pagina-de-teste", name="Página de teste")


class TestPage:
    def test_criacao(self, pagina):
        assert pagina.key == "pagina-de-teste"
        assert pagina.is_active is True

    def test_identificador_e_unico(self, pagina):
        with pytest.raises(IntegrityError), transaction.atomic():
            Page.objects.create(key="pagina-de-teste", name="Outra")

    def test_pode_ficar_inativa(self, pagina):
        pagina.is_active = False
        pagina.save()
        pagina.refresh_from_db()
        assert pagina.is_active is False


class TestPageSection:
    def test_criacao(self, pagina):
        section = PageSection.objects.create(page=pagina, kind=PageSection.Kind.HERO, order=1)

        assert section.page == pagina
        assert section in pagina.sections.all()

    def test_tipos_disponiveis(self):
        assert set(PageSection.Kind.values) == {
            "navbar",
            "hero",
            "text",
            "image_text",
            "features",
            "partners",
            "faq",
            "cta",
            "banner",
            "contact",
            "footer",
        }

    def test_secoes_sao_ordenadas_pelo_campo_order(self, pagina):
        terceira = PageSection.objects.create(page=pagina, kind=PageSection.Kind.FAQ, order=30)
        primeira = PageSection.objects.create(page=pagina, kind=PageSection.Kind.HERO, order=10)
        segunda = PageSection.objects.create(
            page=pagina, kind=PageSection.Kind.FEATURES, order=20
        )

        assert list(pagina.sections.all()) == [primeira, segunda, terceira]

    def test_reordenar_e_so_mudar_o_campo_order(self, pagina):
        primeira = PageSection.objects.create(page=pagina, kind=PageSection.Kind.HERO, order=10)
        segunda = PageSection.objects.create(
            page=pagina, kind=PageSection.Kind.FEATURES, order=20
        )

        primeira.order, segunda.order = segunda.order, primeira.order
        primeira.save()
        segunda.save()

        assert list(pagina.sections.values_list("pk", flat=True)) == [segunda.pk, primeira.pk]

    def test_pode_desativar_uma_secao_sem_remover(self, pagina):
        section = PageSection.objects.create(page=pagina, kind=PageSection.Kind.BANNER)

        section.is_active = False
        section.save()
        section.refresh_from_db()

        assert section.is_active is False
        assert PageSection.objects.filter(pk=section.pk).exists()

    def test_excluir_pagina_remove_as_secoes(self, pagina):
        section = PageSection.objects.create(page=pagina, kind=PageSection.Kind.HERO)
        section_id = section.pk

        pagina.delete()

        assert not PageSection.objects.filter(pk=section_id).exists()


class TestPageSectionTranslation:
    @pytest.fixture
    def hero_section(self, pagina):
        return PageSection.objects.create(page=pagina, kind=PageSection.Kind.HERO, order=1)

    def test_criacao(self, hero_section):
        translation = PageSectionTranslation.objects.create(
            section=hero_section,
            language="pt",
            content={"title": "Gere sua Carta Convite", "cta_label": "Criar minha conta"},
        )

        assert translation.content["title"] == "Gere sua Carta Convite"

    def test_suporta_os_quatro_idiomas(self, hero_section):
        for code in ("pt", "fr", "nl", "en"):
            PageSectionTranslation.objects.create(
                section=hero_section, language=code, content={"title": code}
            )

        assert hero_section.translations.count() == 4

    def test_unicidade_entre_secao_e_idioma(self, hero_section):
        PageSectionTranslation.objects.create(section=hero_section, language="pt", content={})

        with pytest.raises(IntegrityError), transaction.atomic():
            PageSectionTranslation.objects.create(section=hero_section, language="pt", content={})

    def test_conteudo_deve_ser_um_objeto(self, hero_section):
        translation = PageSectionTranslation(
            section=hero_section, language="pt", content="texto solto"
        )

        with pytest.raises(ValidationError):
            translation.full_clean()

    def test_excluir_secao_remove_as_traducoes(self, hero_section):
        PageSectionTranslation.objects.create(section=hero_section, language="pt", content={})
        section_id = hero_section.pk

        hero_section.delete()

        assert PageSectionTranslation.objects.filter(section_id=section_id).count() == 0


# ---------------------------------------------------------------------------
# SiteSettings
# ---------------------------------------------------------------------------


class TestSiteSettings:
    def test_load_cria_com_os_padroes(self):
        settings_obj = SiteSettings.load()

        assert settings_obj.pk == SiteSettings.SINGLETON_ID
        assert settings_obj.site_name == "Desenrola"
        assert settings_obj.theme_primary_color == "#1a5fd6"

    def test_load_e_idempotente(self):
        primeira = SiteSettings.load()
        segunda = SiteSettings.load()

        assert primeira.pk == segunda.pk
        assert SiteSettings.objects.count() == 1

    def test_qualquer_instancia_salva_usa_o_mesmo_id(self):
        primeira = SiteSettings.objects.create(site_name="Primeiro nome")

        assert primeira.pk == SiteSettings.SINGLETON_ID
        assert SiteSettings.load().site_name == "Primeiro nome"

    def test_criar_uma_segunda_vez_falha_em_vez_de_corromper_o_registro(self):
        """
        `.objects.create()` duas vezes e uso indevido do singleton — o
        jeito correto de obter/criar o registro e `load()`. Falhar alto
        e claro (PK duplicada) e melhor do que sobrescrever silenciosamente
        o registro existente com dados parciais.
        """
        SiteSettings.objects.create(site_name="Primeiro nome")

        with pytest.raises(IntegrityError), transaction.atomic():
            SiteSettings.objects.create(site_name="Segundo nome")

        assert SiteSettings.objects.get().site_name == "Primeiro nome"

    def test_pode_guardar_logo_e_favicon(self):
        logo = Asset.objects.create(key="site-logo", kind=Asset.Kind.LOGO, file=_gif("logo.gif"))
        favicon = Asset.objects.create(
            key="site-favicon", kind=Asset.Kind.FAVICON, file=_gif("favicon.gif")
        )

        settings_obj = SiteSettings.load()
        settings_obj.logo = logo
        settings_obj.favicon = favicon
        settings_obj.save()
        settings_obj.refresh_from_db()

        assert settings_obj.logo == logo
        assert settings_obj.favicon == favicon

    def test_excluir_asset_do_logo_nao_quebra_as_configuracoes(self):
        logo = Asset.objects.create(key="site-logo", kind=Asset.Kind.LOGO, file=_gif())
        settings_obj = SiteSettings.load()
        settings_obj.logo = logo
        settings_obj.save()

        logo.delete()
        settings_obj.refresh_from_db()

        assert settings_obj.logo is None

    def test_redes_sociais_ficam_em_jsonb(self):
        settings_obj = SiteSettings.load()
        settings_obj.social_links = {"instagram": "https://instagram.com/desenrola"}
        settings_obj.save()
        settings_obj.refresh_from_db()

        assert settings_obj.social_links == {"instagram": "https://instagram.com/desenrola"}

    def test_cor_invalida_e_recusada(self):
        settings_obj = SiteSettings.load()
        settings_obj.theme_primary_color = "azul"

        with pytest.raises(ValidationError):
            settings_obj.full_clean()

    def test_redes_sociais_devem_ser_texto_para_texto(self):
        settings_obj = SiteSettings.load()
        settings_obj.social_links = {"instagram": 123}

        with pytest.raises(ValidationError):
            settings_obj.full_clean()


# ---------------------------------------------------------------------------
# Permissoes (CRUD padrao do Django, sem codinomes extras nestes modelos)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("app_label", "model_name"),
    [
        ("content", "asset"),
        ("content", "page"),
        ("content", "pagesection"),
        ("content", "sitesettings"),
    ],
)
def test_permissoes_padrao_existem(app_label, model_name):
    for action in ("add", "change", "delete", "view"):
        assert Permission.objects.filter(
            content_type__app_label=app_label, codename=f"{action}_{model_name}"
        ).exists()
