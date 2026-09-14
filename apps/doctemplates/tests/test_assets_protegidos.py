"""
Assets protegidos pelo lado do MODELO (Etapa 3.5.1, integridade).

O layout de um `DocumentTemplate` referencia imagens por `asset_id`
dentro de JSON. `DocumentTemplateAsset` torna isso visivel ao banco, com
FK PROTECT -- e e sincronizada do layout a cada gravacao. O que estes
testes protegem: um asset em uso por um modelo nao pode ser apagado; um
modelo continua livre para trocar de imagem; e o asset que ficou para
tras volta a ser excluivel quando nada mais depende dele.

O lado da CARTA (o snapshot congelado e a imutabilidade do arquivo) esta
em `apps.letters.tests.test_letter_assets`.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError
from PIL import Image

from apps.content.admin import AssetAdmin
from apps.content.models import Asset
from apps.doctemplates import layout_schema
from apps.doctemplates.models import DocumentTemplate, DocumentTemplateAsset, DocumentType
from apps.doctemplates.services import pdf

pytestmark = pytest.mark.django_db

A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}


def _png(nome="imagem.png", cor=(10, 20, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), cor).save(buffer, format="PNG")
    return SimpleUploadedFile(nome, buffer.getvalue(), content_type="image/png")


def layout_com_imagem(asset_id):
    return {
        "version": 1,
        "elements": [
            {
                "id": "logo",
                "type": "image",
                "x": 10.0, "y": 10.0, "width": 40.0, "height": 40.0,
                "properties": {
                    "source": {"kind": "asset", "asset_id": asset_id},
                    "fit": "contain",
                    "preserve_aspect_ratio": True,
                },
            }
        ],
    }


LAYOUT_SEM_IMAGEM = {
    "version": 1,
    "elements": [
        {
            "id": "t", "type": "text", "x": 10.0, "y": 10.0, "width": 100.0, "height": 15.0,
            "properties": {"content": {"kind": "text", "value": "só texto"}},
        }
    ],
}


@pytest.fixture
def media(tmp_path, settings):
    """MEDIA_ROOT próprio: nenhum PNG de teste vai para o `media/` do projeto."""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def asset(media):
    return Asset.objects.create(kind=Asset.Kind.CONTENT, file=_png("a.png"), alt_text="a")


@pytest.fixture
def outro_asset(media):
    return Asset.objects.create(
        kind=Asset.Kind.CONTENT, file=_png("b.png", (200, 0, 0)), alt_text="b"
    )


@pytest.fixture
def tipo():
    return DocumentType.objects.create(code="carta-assets", name="Carta", page=dict(A4))


@pytest.fixture
def modelo(tipo, asset):
    return DocumentTemplate.objects.create(
        type=tipo, name="Com imagem", slug="com-imagem", language="fr",
        layout=layout_com_imagem(asset.pk),
    )


# ===========================================================================
# 1. Descobrir os assets de um layout
# ===========================================================================


class TestAssetsReferenciados:
    def test_encontra_a_imagem(self, asset):
        assert layout_schema.assets_referenciados(layout_com_imagem(asset.pk)) == {asset.pk}

    def test_zero_e_ainda_nao_escolhido_e_nao_conta(self):
        assert layout_schema.assets_referenciados(layout_com_imagem(0)) == set()

    def test_layout_vazio(self):
        assert layout_schema.assets_referenciados({}) == set()
        assert layout_schema.assets_referenciados(LAYOUT_SEM_IMAGEM) == set()

    def test_booleano_nao_e_id(self):
        assert layout_schema.assets_referenciados(layout_com_imagem(True)) == set()

    def test_encontra_dentro_de_celula_de_tabela(self):
        layout = {"version": 1, "elements": [{
            "id": "tab", "type": "table", "x": 0, "y": 0, "width": 100, "height": 20,
            "properties": {
                "columns": [{"width": 100.0}],
                "rows": [{"min_height": 20.0, "cells": [
                    {"content": {"kind": "asset", "asset_id": 42}},
                ]}],
            },
        }]}

        assert layout_schema.assets_referenciados(layout) == {42}

    def test_encontra_dentro_de_conteudo_misto(self):
        layout = {"version": 1, "elements": [{
            "id": "r", "type": "rich_text", "x": 0, "y": 0, "width": 100, "height": 20,
            "properties": {"content": {"kind": "mixed", "parts": [
                {"kind": "text", "value": "x"},
                {"kind": "asset", "asset_id": 7},
            ]}},
        }]}

        assert layout_schema.assets_referenciados(layout) == {7}


# ===========================================================================
# 2. O vinculo acompanha o layout
# ===========================================================================


class TestVinculoComOModelo:
    def test_criar_o_modelo_cria_o_vinculo(self, modelo, asset):
        assert DocumentTemplateAsset.objects.filter(template=modelo, asset=asset).exists()

    def test_um_asset_usado_por_modelo_e_usado_normalmente(self, modelo):
        """Nada da proteção atrapalha o uso: o PDF sai com a imagem."""
        _dados, relatorio = pdf.render_template(modelo, {})

        assert relatorio["por_tipo"]["image"] == 1
        assert relatorio["desenhados"] == 1

    def test_trocar_a_imagem_move_o_vinculo(self, modelo, asset, outro_asset):
        modelo.layout = layout_com_imagem(outro_asset.pk)
        modelo.save()

        vinculados = set(
            DocumentTemplateAsset.objects.filter(template=modelo).values_list("asset_id", flat=True)
        )
        assert vinculados == {outro_asset.pk}

    def test_remover_a_imagem_remove_o_vinculo(self, modelo):
        modelo.layout = LAYOUT_SEM_IMAGEM
        modelo.save()

        assert not DocumentTemplateAsset.objects.filter(template=modelo).exists()

    def test_save_com_update_fields_tambem_sincroniza(self, modelo, outro_asset):
        modelo.layout = layout_com_imagem(outro_asset.pk)
        modelo.save(update_fields=["layout", "updated_at"])

        assert DocumentTemplateAsset.objects.filter(template=modelo, asset=outro_asset).exists()

    def test_asset_inexistente_no_layout_nao_gera_vinculo_nem_erro(self, tipo):
        """
        Um id órfão é recusado depois, na geração (`AssetAusenteError`) --
        não aqui, para não quebrar a edição normal de um modelo.
        """
        modelo = DocumentTemplate.objects.create(
            type=tipo, name="Órfão", slug="orfao", language="fr",
            layout=layout_com_imagem(999_999),
        )

        assert not DocumentTemplateAsset.objects.filter(template=modelo).exists()

    def test_o_vinculo_e_unico_por_par(self, modelo, asset):
        modelo.save()
        modelo.save()

        assert DocumentTemplateAsset.objects.filter(template=modelo, asset=asset).count() == 1

    def test_o_oficial_fr_fica_vinculado_ao_logo(self, media):
        """`vincular_logo()` grava por `update()`; o vínculo tem de vir junto."""
        from apps.doctemplates.services import carta_convite

        carta_convite.reconstruir(DocumentTemplate, Asset, "fr")

        logo = Asset.objects.get(key=carta_convite.LOGO_CHAVE_DO_ASSET)
        fr = DocumentTemplate.objects.get(slug=carta_convite.slug_do_modelo("fr"))
        assert DocumentTemplateAsset.objects.filter(template=fr, asset=logo).exists()


# ===========================================================================
# 3. Exclusao recusada enquanto um modelo depende do asset
# ===========================================================================


class TestProtecaoDeExclusao:
    def test_asset_usado_por_modelo_nao_pode_ser_excluido(self, modelo, asset):
        with pytest.raises(ProtectedError):
            asset.delete()

        assert Asset.objects.filter(pk=asset.pk).exists()

    def test_nem_por_queryset(self, modelo, asset):
        """`queryset.delete()` -- o caminho do bulk do admin -- também é recusado."""
        with pytest.raises(ProtectedError):
            Asset.objects.filter(pk=asset.pk).delete()

        assert Asset.objects.filter(pk=asset.pk).exists()

    def test_o_modelo_continua_inteiro_depois_da_tentativa(self, modelo, asset):
        with pytest.raises(ProtectedError):
            asset.delete()

        modelo.refresh_from_db()
        assert layout_schema.assets_referenciados(modelo.layout) == {asset.pk}
        _dados, relatorio = pdf.render_template(modelo, {})
        assert relatorio["desenhados"] == 1

    def test_depois_de_trocar_a_imagem_o_asset_antigo_volta_a_ser_excluivel(
        self, modelo, asset, outro_asset
    ):
        modelo.layout = layout_com_imagem(outro_asset.pk)
        modelo.save()

        asset.delete()  # não deve levantar

        assert not Asset.objects.filter(pk=asset.pk).exists()

    def test_o_asset_novo_passa_a_ser_protegido(self, modelo, asset, outro_asset):
        modelo.layout = layout_com_imagem(outro_asset.pk)
        modelo.save()

        with pytest.raises(ProtectedError):
            outro_asset.delete()

    def test_asset_nao_utilizado_continua_excluivel(self, outro_asset):
        outro_asset.delete()

        assert not Asset.objects.filter(pk=outro_asset.pk).exists()

    def test_excluir_o_modelo_solta_o_asset(self, modelo, asset):
        modelo.delete()

        assert not DocumentTemplateAsset.objects.filter(asset=asset).exists()
        asset.delete()  # não deve levantar


# ===========================================================================
# 4. Substituir o arquivo: livre enquanto so um modelo usa
# ===========================================================================


class TestSubstituicaoDoArquivo:
    def test_asset_usado_so_por_modelo_pode_trocar_de_arquivo(self, modelo, asset):
        """
        Editar a imagem de um modelo é edição normal -- nenhuma carta
        finalizada depende dela ainda. (Quando depender, ver o teste do
        lado da carta.)
        """
        nome_antes = asset.file.name

        asset.file.save("nova.png", _png("nova.png", (0, 0, 200)), save=True)

        asset.refresh_from_db()
        assert asset.file.name != nome_antes

    def test_asset_nao_utilizado_pode_trocar_de_arquivo(self, outro_asset):
        outro_asset.file.save("outra.png", _png("outra.png"), save=True)

        assert outro_asset.file.name.endswith(".png")


# ===========================================================================
# 5. O admin espelha as regras
# ===========================================================================


class TestAdmin:
    @pytest.fixture
    def admin_site(self):
        from django.contrib.admin.sites import AdminSite

        return AssetAdmin(Asset, AdminSite())

    @pytest.fixture
    def pedido(self, rf, staff_user):
        request = rf.get("/admin/")
        request.user = staff_user
        return request

    def test_asset_em_uso_por_modelo_nao_pode_ser_apagado_pelo_admin(
        self, admin_site, pedido, modelo, asset, staff_user
    ):
        staff_user.is_superuser = True
        staff_user.save()

        assert admin_site.has_delete_permission(pedido, asset) is False

    def test_asset_livre_pode_ser_apagado_pelo_admin(
        self, admin_site, pedido, outro_asset, staff_user
    ):
        staff_user.is_superuser = True
        staff_user.save()

        assert admin_site.has_delete_permission(pedido, outro_asset) is True

    def test_arquivo_continua_editavel_quando_so_um_modelo_usa(
        self, admin_site, pedido, modelo, asset
    ):
        assert "file" not in admin_site.get_readonly_fields(pedido, asset)

    def test_coluna_em_uso(self, admin_site, modelo, asset, outro_asset):
        assert "modelo" in admin_site.em_uso(asset)
        assert admin_site.em_uso(outro_asset) == "—"
