"""
Assets protegidos pelo lado da CARTA (Etapa 3.5.1, integridade).

`Letter.document_snapshot` congela o layout, mas o layout so guarda
`asset_id`: a imagem em si continua no `content.Asset`. Estes testes
provam que, uma vez finalizada a carta, esse Asset nao pode mais sumir
(`LetterAsset`, FK PROTECT) nem ter o arquivo trocado (`Asset.save()`)
-- por mais que o modelo original mude, aponte para outra imagem ou seja
editado livremente. E provam o ponto final: a carta continua sendo
REPRODUZIDA a partir do snapshot depois de tudo isso.
"""

import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from pypdf import PdfReader

from apps.content.admin import AssetAdmin
from apps.content.models import Asset, AssetFileImmutableError
from apps.doctemplates.models import DocumentTemplate, DocumentTemplateAsset, DocumentType
from apps.doctemplates.services import pdf
from apps.letters import services
from apps.letters.models import DocumentSnapshotAssetMissingError, Letter, LetterAsset

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
    return DocumentType.objects.create(code="carta-assets-letter", name="Carta", page=dict(A4))


@pytest.fixture
def modelo(tipo, asset):
    return DocumentTemplate.objects.create(
        type=tipo, name="Com imagem", slug="com-imagem-letter", language="fr",
        layout=layout_com_imagem(asset.pk),
    )


@pytest.fixture
def finalizada(letter, modelo):
    """A carta com o snapshot do `modelo` já capturado."""
    services.capture_document_template_snapshot(letter, modelo)
    letter.refresh_from_db()
    return letter


def _renderizar_do_snapshot(carta):
    """Reproduz a carta SÓ a partir do que está congelado nela."""
    estrutura = carta.document_snapshot
    dados, relatorio = pdf.render_layout(
        estrutura["layout"],
        estrutura["type"]["page"],
        pdf.Contexto({}, estrito=False),
        assets=pdf.carregar_assets(estrutura["layout"]),
    )
    return dados, relatorio


# ===========================================================================
# 1. A captura cria os vinculos
# ===========================================================================


class TestCapturaVinculaOsAssets:
    def test_a_captura_cria_um_vinculo_por_asset_do_layout(self, finalizada, asset):
        vinculos = list(
            LetterAsset.objects.filter(letter=finalizada).values_list("asset_id", flat=True)
        )

        assert vinculos == [asset.pk]

    def test_layout_sem_imagem_nao_cria_vinculo(self, letter, tipo):
        modelo = DocumentTemplate.objects.create(
            type=tipo, name="Só texto", slug="so-texto", language="fr", layout=LAYOUT_SEM_IMAGEM,
        )

        services.capture_document_template_snapshot(letter, modelo)

        assert not LetterAsset.objects.filter(letter=letter).exists()

    def test_asset_zero_e_ignorado(self, letter, tipo):
        modelo = DocumentTemplate.objects.create(
            type=tipo, name="Sem escolha", slug="sem-escolha", language="fr",
            layout=layout_com_imagem(0),
        )

        services.capture_document_template_snapshot(letter, modelo)

        assert not LetterAsset.objects.filter(letter=letter).exists()

    def test_asset_inexistente_recusa_a_finalizacao(self, letter, tipo):
        """Uma carta que já nasce irreproduzível não pode ser finalizada."""
        modelo = DocumentTemplate.objects.create(
            type=tipo, name="Órfão", slug="orfao-letter", language="fr",
            layout=layout_com_imagem(999_999),
        )

        with pytest.raises(DocumentSnapshotAssetMissingError, match="999999"):
            services.capture_document_template_snapshot(letter, modelo)

    def test_a_recusa_nao_deixa_snapshot_nem_vinculo_parcial(self, letter, tipo):
        modelo = DocumentTemplate.objects.create(
            type=tipo, name="Órfão", slug="orfao-letter-2", language="fr",
            layout=layout_com_imagem(999_999),
        )

        with pytest.raises(DocumentSnapshotAssetMissingError):
            services.capture_document_template_snapshot(letter, modelo)

        letter.refresh_from_db()
        assert letter.document_snapshot == {}
        assert letter.document_snapshot_hash == ""
        assert not LetterAsset.objects.filter(letter=letter).exists()

    def test_o_conteudo_do_snapshot_nao_mudou_com_a_protecao(self, finalizada, modelo):
        """A tabela de vínculo é paralela; o snapshot continua o mesmo."""
        assert set(finalizada.document_snapshot) == {
            "id", "slug", "name", "language", "is_system", "is_locked",
            "duplicated_from_id", "type", "field_schema", "layout", "captured_at",
        }
        assert finalizada.document_snapshot["layout"] == modelo.layout


# ===========================================================================
# 2. Exclusao recusada enquanto uma carta finalizada depender do asset
# ===========================================================================


class TestProtecaoHistoricaDeExclusao:
    def test_asset_de_carta_finalizada_nao_pode_ser_excluido(self, finalizada, asset):
        with pytest.raises(ProtectedError):
            asset.delete()

        assert Asset.objects.filter(pk=asset.pk).exists()

    def test_nem_por_queryset(self, finalizada, asset):
        with pytest.raises(ProtectedError):
            Asset.objects.filter(pk=asset.pk).delete()

    def test_continua_protegido_depois_que_o_modelo_troca_de_imagem(
        self, finalizada, modelo, asset, outro_asset
    ):
        """
        O modelo seguiu em frente (e soltou o vínculo dele), mas a carta
        finalizada ainda precisa do asset antigo: a exclusão continua
        recusada.
        """
        modelo.layout = layout_com_imagem(outro_asset.pk)
        modelo.save()
        assert not DocumentTemplateAsset.objects.filter(asset=asset).exists()

        with pytest.raises(ProtectedError):
            asset.delete()

    def test_continua_protegido_depois_que_o_modelo_e_excluido(self, finalizada, modelo, asset):
        # O modelo em si segue protegido pelo PROTECT de Letter.document_template;
        # o cenário testado é o vínculo modelo->asset sumir e o da carta ficar.
        DocumentTemplateAsset.objects.filter(template=modelo).delete()

        with pytest.raises(ProtectedError):
            asset.delete()

    def test_excluir_a_carta_solta_o_asset(self, finalizada, modelo, asset):
        modelo.layout = LAYOUT_SEM_IMAGEM
        modelo.save()
        finalizada.delete()

        assert not LetterAsset.objects.filter(asset=asset).exists()
        asset.delete()  # não deve levantar


# ===========================================================================
# 3. Trocar o modelo nao quebra cartas antigas
# ===========================================================================


class TestModeloMudaCartaNao:
    def test_o_snapshot_da_carta_nao_muda(self, finalizada, modelo, asset, outro_asset):
        antes = finalizada.document_snapshot

        modelo.layout = layout_com_imagem(outro_asset.pk)
        modelo.save()

        finalizada.refresh_from_db()
        assert finalizada.document_snapshot == antes
        assert finalizada.document_snapshot["layout"]["elements"][0]["properties"]["source"] == {
            "kind": "asset", "asset_id": asset.pk,
        }

    def test_o_asset_antigo_continua_disponivel(self, finalizada, modelo, asset, outro_asset):
        modelo.layout = layout_com_imagem(outro_asset.pk)
        modelo.save()

        asset.refresh_from_db()
        with asset.file.open("rb") as arquivo:
            assert arquivo.read(8) == b"\x89PNG\r\n\x1a\n"

    def test_a_carta_continua_reproduzivel_depois_da_troca(
        self, finalizada, modelo, asset, outro_asset
    ):
        modelo.layout = layout_com_imagem(outro_asset.pk)
        modelo.save()

        dados, relatorio = _renderizar_do_snapshot(finalizada)

        assert relatorio["desenhados"] == 1
        recursos = PdfReader(io.BytesIO(dados)).pages[0]["/Resources"]
        assert "/XObject" in recursos

    def test_a_carta_continua_reproduzivel_depois_que_o_modelo_perde_a_imagem(
        self, finalizada, modelo
    ):
        modelo.layout = LAYOUT_SEM_IMAGEM
        modelo.save()

        _dados_modelo, relatorio_modelo = pdf.render_template(modelo, {})
        _dados_carta, relatorio_carta = _renderizar_do_snapshot(finalizada)

        assert relatorio_modelo["por_tipo"].get("image", 0) == 0
        assert relatorio_carta["por_tipo"]["image"] == 1

    def test_a_reproducao_usa_o_arquivo_original(self, finalizada, asset):
        """Os bytes que entram no PDF são exatamente os do Asset congelado."""
        assets = pdf.carregar_assets(finalizada.document_snapshot["layout"])

        with asset.file.open("rb") as arquivo:
            assert assets[asset.pk] == arquivo.read()


# ===========================================================================
# 4. Substituir o arquivo de um asset historico e recusado
# ===========================================================================


class TestArquivoHistoricoImutavel:
    def test_trocar_o_arquivo_pelo_campo_e_recusado(self, finalizada, asset):
        nome_gravado = Asset.objects.get(pk=asset.pk).file.name

        with pytest.raises(AssetFileImmutableError):
            asset.file.save("troca.png", _png("troca.png", (0, 0, 200)), save=True)

        assert Asset.objects.get(pk=asset.pk).file.name == nome_gravado

    def test_trocar_o_arquivo_por_atribuicao_e_recusado(self, finalizada, asset):
        asset.file = _png("outra.png")

        with pytest.raises(AssetFileImmutableError):
            asset.save()

    def test_o_conteudo_original_continua_no_disco(self, finalizada, asset):
        with asset.file.open("rb") as arquivo:
            original = arquivo.read()

        with pytest.raises(AssetFileImmutableError):
            asset.file.save("troca.png", _png("troca.png", (0, 0, 200)), save=True)

        asset = Asset.objects.get(pk=asset.pk)
        with asset.file.open("rb") as arquivo:
            assert arquivo.read() == original

    def test_a_recusa_nao_deixa_arquivo_orfao_em_media(self, finalizada, asset, media):
        """
        `FieldFile.save()` grava o novo arquivo ANTES de `save()` recusar.
        A recusa tem de apagar esse arquivo, senão cada tentativa deixaria
        um PNG perdido em MEDIA_ROOT.
        """
        antes = sorted(p.name for p in media.rglob("*.png"))

        with pytest.raises(AssetFileImmutableError):
            asset.file.save("troca.png", _png("troca.png", (0, 0, 200)), save=True)

        assert sorted(p.name for p in media.rglob("*.png")) == antes
        assert asset.file.name == Asset.objects.get(pk=asset.pk).file.name

    def test_editar_outros_campos_continua_permitido(self, finalizada, asset):
        asset.alt_text = "Legenda nova"
        asset.is_active = False
        asset.save()  # não deve levantar

        asset.refresh_from_db()
        assert asset.alt_text == "Legenda nova"

    def test_regravar_sem_trocar_o_arquivo_e_permitido(self, finalizada, asset):
        asset.save()  # idempotente

    def test_desativar_o_asset_nao_quebra_a_reproducao(self, finalizada, asset):
        asset.is_active = False
        asset.save()

        _dados, relatorio = _renderizar_do_snapshot(finalizada)

        assert relatorio["desenhados"] == 1

    def test_o_admin_torna_o_arquivo_somente_leitura(self, finalizada, asset, rf, staff_user):
        from django.contrib.admin.sites import AdminSite

        admin_site = AssetAdmin(Asset, AdminSite())
        request = rf.get("/admin/")
        request.user = staff_user

        assert "file" in admin_site.get_readonly_fields(request, asset)
        assert admin_site.has_delete_permission(request, asset) is False
        assert "carta finalizada" in admin_site.em_uso(asset)


# ===========================================================================
# 5. Rascunho: nada congelado, nada protegido pela carta
# ===========================================================================


class TestRascunho:
    def test_rascunho_com_modelo_escolhido_nao_cria_vinculo(self, letter, modelo):
        letter.document_template = modelo
        letter.save(update_fields=["document_template", "updated_at"])

        assert not LetterAsset.objects.filter(letter=letter).exists()

    def test_no_rascunho_o_asset_so_e_protegido_pelo_modelo(
        self, letter, modelo, asset, outro_asset
    ):
        letter.document_template = modelo
        letter.save(update_fields=["document_template", "updated_at"])

        modelo.layout = layout_com_imagem(outro_asset.pk)
        modelo.save()

        asset.delete()  # o rascunho não segura o asset antigo

        assert not Asset.objects.filter(pk=asset.pk).exists()

    def test_o_rascunho_pode_trocar_o_arquivo_do_asset(self, letter, modelo, asset):
        letter.document_template = modelo
        letter.save(update_fields=["document_template", "updated_at"])

        asset.file.save("nova.png", _png("nova.png"), save=True)  # não deve levantar

    def test_carta_da_arquitetura_antiga_nao_tem_vinculo(self, letter):
        assert not LetterAsset.objects.filter(letter=letter).exists()


# ===========================================================================
# 6. Ponta a ponta: a finalizacao real cria os vinculos
# ===========================================================================


CHEGADA = timezone.localdate() + datetime.timedelta(days=30)
PASSO_1 = {
    "guest_name": "Carlos Eduardo Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "22/07/1990",
    "guest_passport": "YY0000",
}
PASSOS = {
    1: PASSO_1,
    2: {
        "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
        "stay_departure": (CHEGADA + datetime.timedelta(days=14)).strftime("%d/%m/%Y"),
    },
    3: {"host_confirm": "on"},
    4: {"notice_informal": "on", "notice_prise_en_charge": "on"},
}


def _step_url(carta, step):
    return reverse("letters:step", args=[carta.uuid, step])


class TestFinalizacaoReal:
    @pytest.fixture(autouse=True)
    def _nacionalidade(self, nacionalidade_factory):
        nacionalidade_factory("Brasileira", guest_form="Brésilienne")

    def test_finalizar_pelo_assistente_vincula_o_asset(
        self, auth_client, user, modelos_oficiais_prontos
    ):
        """
        Pelo caminho REAL, sem anexar modelo nenhum à mão: o modelo sai
        do idioma escolhido na etapa 5, e o asset conferido aqui é o que
        o layout oficial de verdade usa (o logo do IBZ).
        """
        from apps.doctemplates.services import carta_convite

        logo = Asset.objects.get(key=carta_convite.LOGO_CHAVE_DO_ASSET)
        client = auth_client
        client.post(reverse("letters:new"), PASSO_1)
        carta = Letter.objects.get(user=user)

        for numero in (1, 2, 3, 4):
            client.post(_step_url(carta, numero), PASSOS[numero])
        client.post(_step_url(carta, 5), {"language": "fr"})
        client.post(_step_url(carta, 6))

        carta.refresh_from_db()
        assert carta.document_template.slug == carta_convite.slug_do_modelo("fr")
        assert LetterAsset.objects.filter(letter=carta, asset=logo).exists()
        with pytest.raises(ProtectedError):
            logo.delete()
