"""
O comando `reconstruir_modelos_oficiais` (Etapa 3.3).

O passo de deploy que materializa o que a migration deliberadamente NAO
materializa:

    migrate                        -> layout no banco, zero arquivos
    reconstruir_modelos_oficiais   -> assets em MEDIA_ROOT
    collectstatic

O que estes testes protegem de verdade e a separacao entre os dois. E
facil "resolver" o logo mandando a migration gravar o arquivo -- e ai ela
grava um por banco de teste criado, que foi exatamente como a
arquitetura anterior acumulou mais de mil PNGs em `media/assets/`.

MEDIA_ROOT
----------
Todo teste que materializa arquivo aponta `settings.MEDIA_ROOT` para um
`tmp_path`. Sem isso a suite escreveria no `media/` do repositorio a cada
execucao.
"""

import pytest
from django.core.management import call_command

from apps.content.models import Asset
from apps.doctemplates.layout_schema import validate_layout
from apps.doctemplates.models import DocumentTemplate
from apps.doctemplates.services import modelo_fr

pytestmark = pytest.mark.django_db

SLUG_FR = "carta-convite-fr"
OUTROS_OFICIAIS = ["carta-convite-nl", "carta-convite-en", "carta-convite-pt"]
COMANDO = "reconstruir_modelos_oficiais"


@pytest.fixture
def media(tmp_path, settings):
    """MEDIA_ROOT proprio: os testes nunca sujam o `media/` do projeto."""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def rodar(**opcoes):
    """Executa o comando e devolve o que ele imprimiu."""
    import io

    saida = io.StringIO()
    call_command(COMANDO, stdout=saida, **opcoes)
    return saida.getvalue()


def modelo_fr_do_banco():
    return DocumentTemplate.objects.get(slug=SLUG_FR)


def logo_do_layout(modelo):
    for elemento in modelo.layout["elements"]:
        if elemento["id"] == modelo_fr.ID_DO_LOGO:
            return elemento
    raise AssertionError("o layout não tem o elemento do logo")


def pngs_em(caminho):
    return sorted(p.name for p in caminho.rglob("*.png"))


# ===========================================================================
# 1. Primeira execução: instalação limpa
# ===========================================================================


class TestPrimeiraExecucao:
    def test_o_comando_existe_e_roda(self, media):
        assert "Reconstruindo os modelos oficiais" in rodar()

    def test_parte_de_media_root_vazio(self, media):
        """O cenário do teste é mesmo uma instalação limpa."""
        assert pngs_em(media) == []

        rodar()

        assert len(pngs_em(media)) == 1

    def test_o_fr_fica_com_os_23_elementos(self, media):
        rodar()

        assert len(modelo_fr_do_banco().layout["elements"]) == 23

    def test_o_layout_continua_valido(self, media):
        rodar()

        validate_layout(modelo_fr_do_banco().layout)

    def test_cria_o_asset_do_logo(self, media):
        assert Asset.objects.filter(key=modelo_fr.LOGO_CHAVE_DO_ASSET).count() == 0

        rodar()

        asset = Asset.objects.get(key=modelo_fr.LOGO_CHAVE_DO_ASSET)
        assert asset.is_active is True

    def test_o_arquivo_fisico_do_asset_existe(self, media):
        rodar()

        asset = Asset.objects.get(key=modelo_fr.LOGO_CHAVE_DO_ASSET)
        arquivo = media / asset.file.name
        assert arquivo.is_file()
        assert arquivo.stat().st_size > 0

    def test_o_arquivo_e_um_png_de_verdade(self, media):
        rodar()

        asset = Asset.objects.get(key=modelo_fr.LOGO_CHAVE_DO_ASSET)
        with open(media / asset.file.name, "rb") as fh:
            assert fh.read(8) == b"\x89PNG\r\n\x1a\n"

    def test_o_layout_aponta_para_o_asset_criado(self, media):
        rodar()

        asset = Asset.objects.get(key=modelo_fr.LOGO_CHAVE_DO_ASSET)
        origem = logo_do_layout(modelo_fr_do_banco())["properties"]["source"]
        assert origem == {"kind": "asset", "asset_id": asset.pk}

    def test_o_relato_diz_o_que_foi_feito(self, media):
        saida = rodar()

        assert SLUG_FR in saida
        assert "criado" in saida
        assert "23 elementos" in saida
        assert "Pronto" in saida


# ===========================================================================
# 2. Segunda execução: idempotência
# ===========================================================================


class TestIdempotencia:
    def test_nao_cria_um_segundo_asset(self, media):
        rodar()
        rodar()

        assert Asset.objects.filter(key=modelo_fr.LOGO_CHAVE_DO_ASSET).count() == 1

    def test_nao_duplica_o_arquivo(self, media):
        """
        `FileField.save()` acrescenta um sufixo quando o nome existe --
        é assim que se acumulam cópias. Duas execuções têm de deixar um
        arquivo só.
        """
        rodar()
        depois_da_primeira = pngs_em(media)

        rodar()

        assert pngs_em(media) == depois_da_primeira
        assert len(pngs_em(media)) == 1

    def test_o_layout_nao_muda(self, media):
        rodar()
        primeiro = modelo_fr_do_banco().layout

        rodar()

        assert modelo_fr_do_banco().layout == primeiro

    def test_o_asset_continua_o_mesmo(self, media):
        rodar()
        antes = Asset.objects.get(key=modelo_fr.LOGO_CHAVE_DO_ASSET)

        rodar()

        depois = Asset.objects.get(key=modelo_fr.LOGO_CHAVE_DO_ASSET)
        assert depois.pk == antes.pk
        assert depois.file.name == antes.file.name

    def test_a_segunda_execucao_relata_reaproveitamento(self, media):
        rodar()

        saida = rodar()

        assert "reaproveitado" in saida
        assert "criado" not in saida

    def test_tres_execucoes_seguem_com_um_arquivo(self, media):
        rodar()
        rodar()
        rodar()

        assert len(pngs_em(media)) == 1
        assert Asset.objects.filter(key=modelo_fr.LOGO_CHAVE_DO_ASSET).count() == 1


# ===========================================================================
# 3. Quando o asset já existe
# ===========================================================================


class TestAssetJaExistente:
    def test_reaproveita_um_asset_criado_antes(self, media):
        """
        Um administrador pode ter substituído o arquivo. O comando
        reaproveita o registro e NUNCA troca o arquivo dele.
        """
        asset, criado = modelo_fr.garantir_asset_do_logo(Asset)
        assert criado is True
        nome_original = asset.file.name

        rodar()

        asset.refresh_from_db()
        assert asset.file.name == nome_original
        assert Asset.objects.filter(key=modelo_fr.LOGO_CHAVE_DO_ASSET).count() == 1

    def test_vincula_o_asset_existente_ao_layout(self, media):
        asset, _criado = modelo_fr.garantir_asset_do_logo(Asset)

        rodar()

        origem = logo_do_layout(modelo_fr_do_banco())["properties"]["source"]
        assert origem["asset_id"] == asset.pk

    def test_corrige_um_layout_que_aponta_para_o_asset_errado(self, media):
        modelo_fr.vincular_logo(DocumentTemplate, 9999)

        rodar()

        asset = Asset.objects.get(key=modelo_fr.LOGO_CHAVE_DO_ASSET)
        origem = logo_do_layout(modelo_fr_do_banco())["properties"]["source"]
        assert origem["asset_id"] == asset.pk

    def test_nao_sobrescreve_um_layout_editado(self, media):
        """Nenhum passo de deploy apaga trabalho de administrador."""
        DocumentTemplate.objects.filter(slug=SLUG_FR).update(
            layout={"version": 1, "elements": []}
        )

        rodar()

        assert modelo_fr_do_banco().layout["elements"] == []


# ===========================================================================
# 4. O que o comando NÃO pode tocar
# ===========================================================================


class TestLimites:
    def test_os_outros_tres_idiomas_ficam_intactos(self, media):
        antes = {
            slug: DocumentTemplate.objects.get(slug=slug).layout
            for slug in OUTROS_OFICIAIS
        }

        rodar()

        for slug in OUTROS_OFICIAIS:
            assert DocumentTemplate.objects.get(slug=slug).layout == antes[slug]
            assert DocumentTemplate.objects.get(slug=slug).layout == {}

    def test_nao_cria_asset_para_os_outros_idiomas(self, media):
        rodar()

        assert Asset.objects.count() == 1

    def test_nao_destrava_nem_desoficializa_o_fr(self, media):
        rodar()

        modelo = modelo_fr_do_banco()
        assert modelo.is_system is True
        assert modelo.is_locked is False
        assert modelo.is_active is True

    def test_nao_mexe_no_field_schema(self, media):
        antes = modelo_fr_do_banco().field_schema

        rodar()

        assert modelo_fr_do_banco().field_schema == antes

    def test_nao_escreve_em_media_letters(self, media):
        (media / "letters").mkdir()

        rodar()

        assert list((media / "letters").iterdir()) == []

    def test_o_asset_vai_para_assets_e_nao_para_letters(self, media):
        rodar()

        asset = Asset.objects.get(key=modelo_fr.LOGO_CHAVE_DO_ASSET)
        assert asset.file.name.startswith("assets/")
        assert "letters" not in asset.file.name

    def test_nao_cria_modelo_novo(self, media):
        antes = DocumentTemplate.objects.count()

        rodar()

        assert DocumentTemplate.objects.count() == antes


# ===========================================================================
# 5. A separação migration / comando
# ===========================================================================


class TestSeparacaoComAMigration:
    def test_a_migration_nao_escreveu_em_media(self, media):
        """
        Antes de rodar o comando -- ou seja, logo depois do `migrate` que
        montou o banco de teste -- MEDIA_ROOT está vazio e não há Asset
        nenhum. É esta a separação que o comando existe para manter.
        """
        assert pngs_em(media) == []
        assert Asset.objects.count() == 0

    def test_mas_a_migration_ja_deixou_o_layout_pronto(self, media):
        modelo = modelo_fr_do_banco()

        assert len(modelo.layout["elements"]) == 23
        validate_layout(modelo.layout)

    def test_antes_do_comando_o_logo_aponta_para_lugar_nenhum(self, media):
        origem = logo_do_layout(modelo_fr_do_banco())["properties"]["source"]

        assert origem == {"kind": "asset", "asset_id": 0}

    def test_o_comando_e_que_fecha_a_lacuna(self, media):
        antes = logo_do_layout(modelo_fr_do_banco())["properties"]["source"]

        rodar()

        depois = logo_do_layout(modelo_fr_do_banco())["properties"]["source"]
        assert antes["asset_id"] == 0
        assert depois["asset_id"] > 0

    def test_o_comando_nao_duplica_a_logica_do_servico(self):
        """
        O comando orquestra e relata; quem reconstrói é o serviço. Se a
        montagem do layout aparecesse aqui, haveria duas versões do
        documento oficial para divergirem.
        """
        import inspect

        from apps.doctemplates.management.commands import (
            reconstruir_modelos_oficiais as comando,
        )

        codigo = inspect.getsource(comando)

        assert "modelo_fr.reconstruir" in codigo
        for proibido in ("fr-titulo", "fr-tabela", "MARGEM_ESQUERDA", "extrair_logo"):
            assert proibido not in codigo


# ===========================================================================
# 6. O relato não pode derrubar o comando
# ===========================================================================


class TestSimboloDoRelato:
    """
    Regressão: o "✓" derrubava o comando no console cp1252 do Windows,
    com UnicodeEncodeError -- e DEPOIS de já ter criado o asset. Os
    testes não pegavam porque `call_command(stdout=StringIO())` não passa
    pelo codificador do terminal; só a execução real pela CLI pegou.
    """

    def comando(self, codificacao):
        import io

        from apps.doctemplates.management.commands.reconstruir_modelos_oficiais import (
            Command,
        )

        class Fluxo(io.StringIO):
            encoding = codificacao

        instancia = Command()
        instancia.stdout = Fluxo()
        return instancia

    def test_terminal_utf8_usa_o_simbolo(self):
        assert self.comando("utf-8")._simbolo() == "✓"

    @pytest.mark.parametrize("codificacao", ["cp1252", "ascii", "latin-1"])
    def test_terminal_sem_o_glifo_cai_para_ascii(self, codificacao):
        assert self.comando(codificacao)._simbolo() == "OK"

    def test_codificacao_desconhecida_nao_explode(self):
        assert self.comando("nao-existe-essa-codificacao")._simbolo() == "OK"

    def test_sem_atributo_encoding_nao_explode(self):
        assert self.comando(None)._simbolo() == "OK"

    def test_o_relato_inteiro_cabe_em_cp1252(self, media):
        """Nenhuma outra linha do relato pode ter glifo fora da página."""
        rodar().encode("cp1252")


# ===========================================================================
# 7. Origem do binário
# ===========================================================================


class TestOrigemDoBinario:
    def test_o_pdf_de_origem_e_o_versionado_no_repositorio(self):
        caminho = modelo_fr.CAMINHO_DO_PDF

        assert caminho.is_file()
        assert caminho.name == "Modelo-Carta-Convite-FR.pdf"
        assert caminho.parent.parts[-3:] == ("pdfengine", "assets", "fr")

    def test_o_binario_gerado_confere_com_o_extraido_do_pdf(self, media):
        rodar()

        asset = Asset.objects.get(key=modelo_fr.LOGO_CHAVE_DO_ASSET)
        with open(media / asset.file.name, "rb") as fh:
            gravado = fh.read()

        assert gravado == modelo_fr.extrair_logo_ibz()

    def test_o_comando_nao_le_nada_de_fora_do_repositorio(self, media):
        """
        Nenhum caminho absoluto de máquina de desenvolvimento: a única
        origem é o PDF versionado.
        """
        import inspect

        from apps.doctemplates.management.commands import (
            reconstruir_modelos_oficiais as comando,
        )

        codigo = inspect.getsource(comando) + inspect.getsource(modelo_fr)

        assert "C:\\" not in codigo
        assert "/home/" not in codigo
        assert "D:/" not in codigo or "D:/Site" not in codigo
