"""
Integração Letter -> renderer genérico (Etapa 3.5.2).

O fluxo que a Etapa 3.5.1 deixou pronto, mas inerte, passa a funcionar de
verdade aqui:

    Letter -> document_snapshot -> contexto com os dados reais -> renderer
    genérico (Etapa 3.4) -> PDF

O ponto central de TODOS os testes abaixo: o renderer novo nunca consulta
o `DocumentTemplate` atual para reproduzir uma carta já finalizada. Tudo
o que ele usa -- layout, página, idioma, e os ids dos assets -- vem do
`document_snapshot`, congelado uma vez na finalização (Etapa 3.5.1) e
protegido por `LetterAsset`/`DocumentTemplateAsset` contra alteração por
baixo.

DUAS CAMADAS DE TESTE
---------------------
A maior parte constrói a carta "finalizada" DIRETAMENTE (sem HTTP): monta
`data`/`snapshot` como `_finalize()` faria e chama
`capture_document_template_snapshot()` -- mais rápido, e isola o que está
sendo testado. Duas classes no fim (`TestFluxoHttpCompleto` e
`TestPontaAPontaComORendererNovo`) percorrem o assistente real via HTTP,
que é o pedido explícito do "TESTE PRINCIPAL".

Extração de texto e linhas justificadas: `pypdf.extract_text()` às vezes
prende (ou não) a pontuação à palavra anterior dependendo do espaçamento
de justificação -- o PRÓPRIO PDF oficial mostra essa mesma
inconsistência. Por isso os testes conferem trechos que não atravessam
essa fronteira, nunca uma frase inteira como uma string só.
"""

import datetime
import io

import pytest
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from apps.content.models import Asset
from apps.doctemplates.models import DocumentTemplate, DocumentTemplateAsset, DocumentType
from apps.doctemplates.services import carta_convite
from apps.letters import services
from apps.letters.models import Letter, LetterAsset, LetterRenderError

pytestmark = pytest.mark.django_db

A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}

# Os mesmos valores de exemplo do documento oficial (Etapa 3.4), para que
# o texto extraído seja conferível contra algo conhecido.
DADOS_CONVIDADO = {
    "guest_name": "Carlos Eduardo Silva",
    "guest_nationality": "brasileira",
    "guest_birth_date": "1990-07-22",
    "guest_passport": "YY000000",
}
CHEGADA = "2026-10-10"
PARTIDA = "2026-10-24"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _nacionalidades(nacionalidade_factory):
    nacionalidade_factory("brasileira", guest_form="Brésilienne")


@pytest.fixture
def fr_modelo(modelos_oficiais_prontos):
    """
    O modelo oficial FR, com o logo materializado.

    Vem dos QUATRO oficiais (e não só do francês) porque o assistente
    nasce em `IDIOMA_PADRAO_DA_CARTA` e só troca para "fr" na etapa 5:
    os testes que percorrem o fluxo HTTP precisam do modelo do idioma
    inicial pronto também.
    """
    return DocumentTemplate.objects.get(slug=carta_convite.slug_do_modelo("fr"))


def _finalizar_direto(letter, modelo, *, dados_extra=None):
    """
    Leva `letter` a COMPLETED e captura o snapshot estrutural, sem HTTP --
    exatamente os dois passos que `views._finalize()` executa, na mesma
    ordem: primeiro o snapshot ANTIGO (`build_snapshot`), depois o
    estrutural (`capture_document_template_snapshot`).
    """
    letter.data = {**DADOS_CONVIDADO, "stay_arrival": CHEGADA, "stay_departure": PARTIDA,
                   **(dados_extra or {})}
    letter.save(update_fields=["data", "updated_at"])
    letter.snapshot = services.build_snapshot(letter, letter.user)
    letter.status = Letter.Status.COMPLETED
    letter.save(update_fields=["snapshot", "status", "updated_at"])
    services.capture_document_template_snapshot(letter, modelo)
    return letter


@pytest.fixture
def carta_fr(letter, fr_modelo):
    """Uma carta com o snapshot do modelo oficial FR já capturado, ainda sem PDF."""
    return _finalizar_direto(letter, fr_modelo)


def texto_do(pdf_bytes):
    return PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text()


# ===========================================================================
# 1-6. O renderer genérico é usado, com dados e assets reais
# ===========================================================================


class TestRendererGenericoUsado:
    def test_gera_pdf_pelo_renderer_generico(self, carta_fr):
        """1. Letter com DocumentTemplate FR gera PDF pelo novo renderer."""
        dados = services.render_letter(carta_fr)

        assert dados[:5] == b"%PDF-"

    def test_uma_pagina_a4(self, carta_fr):
        """2. PDF possui uma página A4."""
        pagina = PdfReader(io.BytesIO(services.render_letter(carta_fr))).pages[0]

        assert float(pagina.mediabox.width) == pytest.approx(595.2756, abs=0.001)
        assert float(pagina.mediabox.height) == pytest.approx(841.8898, abs=0.001)

    def test_texto_real_extraivel(self, carta_fr):
        """3. PDF contém texto real extraível (não é página rasterizada)."""
        texto = texto_do(services.render_letter(carta_fr))

        assert len(texto) > 500
        assert "LETTRE D'INVITATION" in texto

    def test_contem_os_dados_reais_da_letter(self, carta_fr):
        """4. PDF contém os dados reais da Letter."""
        texto = texto_do(services.render_letter(carta_fr))

        for valor in ("Claire Dubois", "Carlos Eduardo Silva", "Brésilienne", "YY000000"):
            assert valor in texto

    def test_os_dados_vem_da_letter_e_nao_estao_fixos(self, letter, fr_modelo):
        """O mesmo modelo, com dados diferentes, produz textos diferentes."""
        outro_convidado = {**DADOS_CONVIDADO, "guest_name": "Zoé Martin"}
        outra = _finalizar_direto(letter, fr_modelo, dados_extra=outro_convidado)

        texto = texto_do(services.render_letter(outra))

        assert "Zoé Martin" in texto
        assert "Carlos Eduardo Silva" not in texto

    def test_contem_o_qr_real(self, carta_fr):
        """5. PDF contém o QR real (vetorial, não a imagem original colada)."""
        documento = PdfReader(io.BytesIO(services.render_letter(carta_fr)))
        recursos = documento.pages[0]["/Resources"]
        imagens = [
            x.get_object() for x in (recursos.get("/XObject") or {}).values()
            if x.get_object().get("/Subtype") == "/Image"
        ]

        # só o logo é imagem; o QR é desenhado, não colado.
        assert len(imagens) == 1

    def test_usa_asset_atraves_do_snapshot(self, carta_fr):
        """6. PDF usa Asset através do snapshot (o logo aparece como XObject)."""
        documento = PdfReader(io.BytesIO(services.render_letter(carta_fr)))

        assert "/XObject" in documento.pages[0]["/Resources"]

    def test_o_pdf_sai_do_renderer_estrutural(self, carta_fr, monkeypatch):
        """
        12. O renderer genérico é o ÚNICO caminho até o arquivo.

        Antes existia um segundo pipeline (`apps.letters.pdf_generation`
        -> `pdfengine.render`) e este teste provava que uma carta com
        snapshot não caía nele. Aquele pipeline não existe mais -- o
        que continua valendo é a outra metade da afirmação, agora
        conferida de frente: se `services.pdf.render_layout` não for
        chamado, nenhum PDF é produzido.
        """
        from apps.doctemplates.services import pdf as document_pdf

        chamadas = []
        original = document_pdf.render_layout

        def _espiao(*args, **kwargs):
            chamadas.append(True)
            return original(*args, **kwargs)

        monkeypatch.setattr("apps.doctemplates.services.pdf.render_layout", _espiao)

        services.generate_pdf(carta_fr)

        assert chamadas, "generate_pdf não passou pelo renderer estrutural"
        carta_fr.refresh_from_db()
        assert carta_fr.status == Letter.Status.GENERATED


# ===========================================================================
# 7-10. Independência do DocumentTemplate atual
# ===========================================================================


def conteudo_do(pdf_bytes):
    """
    O CONTENT STREAM (os operadores de desenho), não o arquivo inteiro.

    O reportlab grava `/CreationDate` com o instante real de cada
    chamada -- então dois PDFs do MESMO conteúdo, gerados em momentos
    diferentes, nunca são bytes idênticos, e comparar o arquivo inteiro
    teria um falso negativo por causa de um metadado que nada tem a ver
    com o que o documento diz. O content stream, em compensação, é
    determinístico: mesmo layout/contexto/assets produz os MESMOS
    operadores de desenho, sempre.
    """
    return PdfReader(io.BytesIO(pdf_bytes)).pages[0].get_contents().get_data()


class TestIndependenciaDoDocumentTemplateAtual:
    def test_alterar_o_documenttemplate_depois_nao_altera_o_pdf(self, carta_fr, fr_modelo):
        """7. Alterar DocumentTemplate depois da finalização não altera o PDF."""
        antes = services.render_letter(carta_fr)

        DocumentTemplate.objects.filter(pk=fr_modelo.pk).update(
            name="Nome mudou depois da finalização"
        )

        depois = services.render_letter(carta_fr)
        assert conteudo_do(depois) == conteudo_do(antes)

    def test_trocar_o_layout_nao_altera_o_pdf_da_letter(self, carta_fr, fr_modelo):
        """
        8. Trocar o layout do template não altera o PDF da Letter.

        `fr_modelo` é `is_system`: seu próprio `save()` já recusaria
        mudar o layout por esse caminho (regra da Etapa 1). Uma alteração
        administrativa de verdade num modelo oficial passa por
        `queryset.update()` -- o mesmo caminho que
        `services/carta_convite.py` usa para o mesmíssimo motivo. É esse
        caminho que este teste simula.
        """
        antes = services.render_letter(carta_fr)

        DocumentTemplate.objects.filter(pk=fr_modelo.pk).update(
            layout={"version": 1, "elements": []}
        )

        depois = services.render_letter(carta_fr)
        assert conteudo_do(depois) == conteudo_do(antes)
        # o modelo em si mudou de verdade -- a carta é que ficou imune.
        assert DocumentTemplate.objects.get(pk=fr_modelo.pk).layout == {
            "version": 1, "elements": [],
        }

    def test_desativar_o_template_nao_impede_a_renderizacao(self, carta_fr, fr_modelo):
        """9. Remover/desativar o template não impede a renderização (parte 1: desativar)."""
        fr_modelo.is_active = False
        fr_modelo.save()

        dados = services.render_letter(carta_fr)
        assert dados[:5] == b"%PDF-"

    def test_o_template_nao_pode_ser_removido_enquanto_a_carta_existir(self, letter):
        """
        9. "Remover" o template é literalmente impedido (PROTECT, Etapa
        3.5.1) enquanto esta carta o referenciar -- a forma mais forte de
        "não impede a renderização": nem chega a faltar.

        Um modelo COMUM (não `is_system`) de propósito: `fr_modelo` já
        recusaria a exclusão por ser oficial (regra da Etapa 1) -- aqui o
        que se testa é a proteção NOVA (3.5.1), por a carta o referenciar,
        isolada da proteção antiga.
        """
        from django.db.models import ProtectedError

        tipo = DocumentType.objects.create(code="tipo-comum-3-5-2", name="Tipo", page=dict(A4))
        comum = DocumentTemplate.objects.create(
            type=tipo, name="Modelo comum", slug="modelo-comum-3-5-2", language="fr",
            layout={"version": 1, "elements": []},
        )
        carta = _finalizar_direto(letter, comum)

        with pytest.raises(ProtectedError):
            comum.delete()

        assert services.render_letter(carta)[:5] == b"%PDF-"

    def test_asset_historico_continua_funcionando(self, carta_fr, fr_modelo):
        """10. Asset histórico continua funcionando mesmo após o template mudar de imagem."""
        from apps.doctemplates.models import sincronizar_assets_do_modelo

        logo_original = Asset.objects.get(key=carta_convite.LOGO_CHAVE_DO_ASSET)

        # o template segue em frente e solta o vínculo com o logo original.
        # `update()` pula `save()` -- e com ele a sincronização dos
        # vínculos -- então, como `services/carta_convite.py` já faz para
        # este mesmo modelo `is_system`, a sincronização é chamada à
        # parte.
        DocumentTemplate.objects.filter(pk=fr_modelo.pk).update(
            layout={"version": 1, "elements": []}
        )
        fr_modelo.refresh_from_db()
        sincronizar_assets_do_modelo(DocumentTemplate, fr_modelo)
        assert not DocumentTemplateAsset.objects.filter(
            template=fr_modelo, asset=logo_original
        ).exists()

        # a carta -- que ainda o referencia via LetterAsset -- renderiza normalmente.
        documento = PdfReader(io.BytesIO(services.render_letter(carta_fr)))
        assert "/XObject" in documento.pages[0]["/Resources"]
        assert LetterAsset.objects.filter(letter=carta_fr, asset=logo_original).exists()


# ===========================================================================
# 11. Carta sem snapshot estrutural
# ===========================================================================


class TestCartaSemSnapshot:
    """
    Enquanto existiu um segundo pipeline, uma carta sem
    `document_snapshot` caía nele e gerava assim mesmo. Não existe
    mais segundo pipeline: sem snapshot não há o que renderizar, e o
    certo é parar -- alto, e sem gravar nada.
    """

    def test_render_letter_recusa_carta_sem_snapshot(self, letter):
        from apps.letters.models import MissingDocumentSnapshotError

        with pytest.raises(MissingDocumentSnapshotError):
            services.render_letter(letter)

    def test_generate_pdf_nao_marca_generated_sem_snapshot(self, letter):
        from apps.letters.models import MissingDocumentSnapshotError

        letter.data = {**DADOS_CONVIDADO, "stay_arrival": CHEGADA, "stay_departure": PARTIDA}
        letter.snapshot = services.build_snapshot(letter, letter.user)
        letter.status = Letter.Status.COMPLETED
        letter.save(update_fields=["data", "snapshot", "status", "updated_at"])

        with pytest.raises(MissingDocumentSnapshotError):
            services.generate_pdf(letter)

        letter.refresh_from_db()
        assert letter.status == Letter.Status.COMPLETED
        assert not letter.pdf_file


# ===========================================================================
# 13-15. Regeneração e integridade do estado
# ===========================================================================


class TestRegeneracaoEEstado:
    def test_regeneracao_usa_o_snapshot_e_nao_o_template_atual(self, carta_fr, fr_modelo):
        """13. Regeneração usa snapshot -- não o DocumentTemplate atual."""
        services.generate_pdf(carta_fr)
        carta_fr.refresh_from_db()
        primeiro_conteudo = conteudo_do(carta_fr.pdf_file.read())

        # o "administrador" muda o modelo de verdade entre as duas gerações
        # (via queryset.update() -- fr_modelo é is_system, ver os testes acima).
        DocumentTemplate.objects.filter(pk=fr_modelo.pk).update(
            layout={"version": 1, "elements": []}
        )

        services.generate_pdf(carta_fr)  # a regeneração
        carta_fr.refresh_from_db()

        assert conteudo_do(carta_fr.pdf_file.read()) == primeiro_conteudo

    def test_estado_generated_permanece_correto(self, carta_fr):
        """14. Estado GENERATED permanece correto após a geração."""
        services.generate_pdf(carta_fr)
        carta_fr.refresh_from_db()

        assert carta_fr.status == Letter.Status.GENERATED
        assert carta_fr.pdf_file.name
        assert carta_fr.pdf_sha256
        assert carta_fr.generated_at is not None

    def test_falha_de_renderizacao_nao_deixa_estado_generated_incorreto(
        self, carta_fr, monkeypatch
    ):
        """
        15. Falha de renderização não deixa estado GENERATED incorreto.

        `PaginaInvalidaError` é um dos erros REAIS que `render_letter()`
        embrulha em `LetterRenderError` -- não um `RuntimeError` genérico,
        que não faz parte da taxonomia conhecida do renderer e por isso
        não seria (nem deveria ser) convertido silenciosamente.
        """
        from apps.doctemplates.services import pdf as document_pdf

        def _explode(*args, **kwargs):
            raise document_pdf.PaginaInvalidaError("página simulada como inválida")

        monkeypatch.setattr("apps.doctemplates.services.pdf.render_layout", _explode)

        with pytest.raises(LetterRenderError):
            services.generate_pdf(carta_fr)

        carta_fr.refresh_from_db()
        assert carta_fr.status == Letter.Status.COMPLETED  # não virou GENERATED
        assert not carta_fr.pdf_file
        assert carta_fr.pdf_sha256 == ""
        assert carta_fr.generated_at is None

    def test_falha_de_renderizacao_nao_altera_o_snapshot(self, carta_fr, monkeypatch):
        from apps.doctemplates.services import pdf as document_pdf

        antes = carta_fr.document_snapshot_hash

        monkeypatch.setattr(
            "apps.doctemplates.services.pdf.render_layout",
            lambda *a, **k: (_ for _ in ()).throw(
                document_pdf.PaginaInvalidaError("simulado")
            ),
        )
        with pytest.raises(LetterRenderError):
            services.generate_pdf(carta_fr)

        carta_fr.refresh_from_db()
        assert carta_fr.document_snapshot_hash == antes


# ===========================================================================
# 16. O fluxo HTTP comum (sem escolha de modelo) continua igual
# ===========================================================================


class TestFluxoHttpCompleto:
    @pytest.fixture(autouse=True)
    def _oficiais(self, modelos_oficiais_prontos):
        """O assistente só cria a carta com o modelo do idioma pronto."""

    def _step_url(self, carta, step):
        return reverse("letters:step", args=[carta.uuid, step])

    def _passos(self):
        chegada = timezone.localdate() + datetime.timedelta(days=30)
        return {
            1: {
                "guest_name": "Carlos Eduardo Silva", "guest_nationality": "brasileira",
                "guest_birth_date": "22/07/1990", "guest_passport": "YY000000",
            },
            2: {
                "stay_arrival": chegada.strftime("%d/%m/%Y"),
                "stay_departure": (chegada + datetime.timedelta(days=14)).strftime("%d/%m/%Y"),
            },
            3: {"host_confirm": "on"},
            4: {"notice_informal": "on", "notice_prise_en_charge": "on"},
        }

    def test_o_assistente_sozinho_ja_captura_o_modelo_estrutural(
        self, auth_client, user
    ):
        """
        16. Nenhuma tela escolhe um DocumentTemplate -- e nem precisa:
        o modelo vem do IDIOMA, e a finalização captura o snapshot
        estrutural sem que ninguém tenha de anexar nada à mão.
        """
        client = auth_client
        passos = self._passos()
        client.post(reverse("letters:new"), passos[1])
        carta = Letter.objects.get(user=user)

        for numero in (2, 3, 4):
            client.post(self._step_url(carta, numero), passos[numero])
        client.post(self._step_url(carta, 5), {"language": "fr"})
        resposta = client.post(self._step_url(carta, 6))

        carta.refresh_from_db()
        assert resposta.status_code == 302
        assert carta.status == Letter.Status.GENERATED
        assert carta.document_template.slug == carta_convite.slug_do_modelo("fr")
        assert carta.document_snapshot_hash != ""
        assert carta.pdf_file


# ===========================================================================
# TESTE PRINCIPAL -- ponta a ponta com o renderer novo
# ===========================================================================


class TestPontaAPontaComORendererNovo:
    """
    wizard -> finalização -> snapshot -> geração -> PDF, inteiro pelo
    caminho real: o modelo estrutural sai do idioma escolhido na etapa
    5, sem nenhum passo manual. Confirma que o arquivo final foi
    produzido pelo renderer estrutural.
    """

    def _step_url(self, carta, step):
        return reverse("letters:step", args=[carta.uuid, step])

    def test_ponta_a_ponta(self, auth_client, user, fr_modelo):
        client = auth_client
        chegada = timezone.localdate() + datetime.timedelta(days=30)

        # 1. wizard: cria o rascunho
        client.post(reverse("letters:new"), {
            "guest_name": "Carlos Eduardo Silva", "guest_nationality": "brasileira",
            "guest_birth_date": "22/07/1990", "guest_passport": "YY000000",
        })
        carta = Letter.objects.get(user=user)

        client.post(self._step_url(carta, 2), {
            "stay_arrival": chegada.strftime("%d/%m/%Y"),
            "stay_departure": (chegada + datetime.timedelta(days=14)).strftime("%d/%m/%Y"),
        })
        client.post(self._step_url(carta, 3), {"host_confirm": "on"})
        client.post(self._step_url(carta, 4), {
            "notice_informal": "on", "notice_prise_en_charge": "on",
        })
        client.post(self._step_url(carta, 5), {"language": "fr"})

        # 2. finalização
        resposta = client.post(self._step_url(carta, 6))
        assert resposta.status_code == 302

        carta.refresh_from_db()

        # 3. snapshot -- o modelo saiu do idioma, ninguém o anexou à mão.
        assert carta.document_template_id == fr_modelo.pk
        assert carta.document_snapshot_hash != ""
        assert carta.document_snapshot["layout"] == carta_convite.layout(
            "fr",
            asset_do_logo=Asset.objects.get(key=carta_convite.LOGO_CHAVE_DO_ASSET).pk,
        )

        # 4. geração
        assert carta.status == Letter.Status.GENERATED
        assert carta.pdf_file

        # 5. o PDF final
        with carta.pdf_file.open("rb") as arquivo:
            conteudo = arquivo.read()
        documento = PdfReader(io.BytesIO(conteudo))
        assert len(documento.pages) == 1
        texto = documento.pages[0].extract_text()
        assert "Carlos Eduardo Silva" in texto
        assert "Claire Dubois" in texto

        # confirma que foi o renderer NOVO: só uma imagem (o logo), o QR
        # é vetorial -- a assinatura do pipeline da Etapa 3.4.
        imagens = [
            x.get_object() for x in documento.pages[0]["/Resources"]["/XObject"].values()
            if x.get_object().get("/Subtype") == "/Image"
        ]
        assert len(imagens) == 1

    def test_a_view_de_pdf_entrega_o_arquivo(self, auth_client, user, fr_modelo):
        """O caminho de entrega (`letters:pdf`) devolve o arquivo gerado."""
        client = auth_client
        chegada = timezone.localdate() + datetime.timedelta(days=30)
        client.post(reverse("letters:new"), {
            "guest_name": "Carlos Eduardo Silva", "guest_nationality": "brasileira",
            "guest_birth_date": "22/07/1990", "guest_passport": "YY000000",
        })
        carta = Letter.objects.get(user=user)
        client.post(self._step_url(carta, 2), {
            "stay_arrival": chegada.strftime("%d/%m/%Y"),
            "stay_departure": (chegada + datetime.timedelta(days=14)).strftime("%d/%m/%Y"),
        })
        client.post(self._step_url(carta, 3), {"host_confirm": "on"})
        client.post(self._step_url(carta, 4), {
            "notice_informal": "on", "notice_prise_en_charge": "on",
        })
        client.post(self._step_url(carta, 5), {"language": "fr"})
        client.post(self._step_url(carta, 6))
        carta.refresh_from_db()

        resposta = client.get(reverse("letters:pdf", args=[carta.uuid]))

        assert resposta.status_code == 200
        assert resposta["Content-Type"] == "application/pdf"


# ===========================================================================
# Comparação visual com o documento oficial
# ===========================================================================


class TestComparacaoVisualComOOficial:
    """
    Não exige fidelidade pixel-perfect -- a Etapa 3.4 já mediu isso contra
    o renderer genérico diretamente. O que importa aqui é mais simples:
    o fluxo REAL (Letter -> snapshot -> render_letter) produz um
    documento reconhecível como a Carta Convite oficial, com os dados
    certos nos lugares certos.
    """

    def test_a_carta_real_e_visualmente_proxima_do_oficial(self, carta_fr, tmp_path):
        import pypdfium2 as pdfium
        from PIL import ImageChops

        caminho_oficial = carta_convite.CAMINHO_DO_PDF
        gerado = services.render_letter(carta_fr)

        def rasterizar(dados):
            documento = pdfium.PdfDocument(dados)
            try:
                return documento[0].render(scale=1.5).to_pil().convert("L")
            finally:
                documento.close()

        img_gerado = rasterizar(gerado)
        img_oficial = rasterizar(caminho_oficial.read_bytes())

        largura = min(img_gerado.width, img_oficial.width)
        altura = min(img_gerado.height, img_oficial.height)
        img_gerado = img_gerado.crop((0, 0, largura, altura))
        img_oficial = img_oficial.crop((0, 0, largura, altura))

        diferenca = ImageChops.difference(img_gerado, img_oficial)
        historograma = diferenca.histogram()
        total = largura * altura
        media = sum(i * c for i, c in enumerate(historograma)) / total

        # limiar generoso: o objetivo é provar "documento reconhecível",
        # não a fidelidade de pixel já estabelecida na Etapa 3.4.
        assert media < 40.0, f"diferença média por pixel muito alta: {media:.2f}/255"

        # imagens gravadas para conferência visual manual, se necessário.
        img_gerado.save(tmp_path / "gerado.png")
        img_oficial.save(tmp_path / "oficial.png")
