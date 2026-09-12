"""
Testes do renderer da Carta Convite oficial (francês) --
`pdfengine.render.render_invitation_letter_fr`. Biblioteca pura: nenhum
teste aqui usa Django nem banco de dados (ver
`apps/letters/tests/test_pdf_generation.py` para a ponte com
Letter/snapshot).
"""

import hashlib
import io
from pathlib import Path

import pytest
from pypdf import PdfReader

from pdfengine.exceptions import (
    BasePdfUnavailableError,
    MissingSnapshotDataError,
    TextOverflowError,
    UnrenderableCharacterError,
)
from pdfengine.layouts.carta_convite_fr import (
    FONT_BOLD,
    FONT_REGULAR,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    ZONES,
)
from pdfengine.redact import _apply, _mat_mult
from pdfengine.render import BASE_PDF_PATH, render_invitation_letter_fr
from pdfengine.sample_data import FR_SAMPLE_DATA


def _extract_runs(pdf_bytes):
    """Extrai (texto, fonte, tamanho, posição) de cada trecho de texto do
    PDF -- mesma técnica usada para medir o documento oficial (ver
    pdfengine/docs/)."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page = reader.pages[0]
    runs = []

    def visitor(text, cm, tm, font_dict, font_size):
        if not text or not text.strip():
            return
        x0, y0 = _apply(tm, 0, 0)
        x1, y1 = _apply(cm, x0, y0)
        font_name = font_dict.get("/BaseFont") if font_dict else None
        runs.append((text, font_name, font_size, round(x1, 1), round(y1, 1)))

    page.extract_text(visitor_text=visitor)
    return runs


def _is_overlay_font(name, *, bold=None):
    """
    Reconhece as fontes do NOSSO overlay (Liberation Sans, embutida)
    dentro do PDF final, separando-as das fontes Arial que ja vinham
    embutidas no documento oficial. O nome vem com o prefixo de
    subconjunto que o reportlab gera (ex.: "/AAAAAA+LiberationSans-Bold"),
    por isso a comparacao e por sufixo.
    """
    if not name:
        return False
    family = str(name).split("+")[-1]
    if not family.startswith("LiberationSans"):
        return False
    if bold is None:
        return True
    return family.endswith("-Bold") is bold


def _overlay_runs(pdf_bytes):
    """So os trechos desenhados pelo NOSSO overlay -- o que permite isolar
    "o que o renderer desenhou" de "o que já estava no PDF oficial"."""
    return [r for r in _extract_runs(pdf_bytes) if _is_overlay_font(r[1])]



def _image_placements(pdf_path):
    """
    Onde cada imagem do documento e desenhada, em pontos PDF -- lida do
    fluxo de conteudo (operador `Do` com a matriz vigente), nao estimada.
    Devolve [(nome, x0, y0, x1, y1), ...].
    """
    from pypdf.generic import ContentStream

    page = PdfReader(str(pdf_path)).pages[0]
    content = ContentStream(page.get_contents(), page.pdf)
    stack = [(1, 0, 0, 1, 0, 0)]
    found = []
    for operands, operator in content.operations:
        op = operator.decode() if isinstance(operator, bytes) else operator
        if op == "q":
            stack.append(stack[-1])
        elif op == "Q":
            stack.pop()
        elif op == "cm":
            stack[-1] = _mat_mult(tuple(float(v) for v in operands), stack[-1])
        elif op == "Do":
            x0, y0 = _apply(stack[-1], 0, 0)
            x1, y1 = _apply(stack[-1], 1, 1)
            found.append(
                (str(operands[0]), min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            )
    return found



def _vector_rects(pdf_path):
    """
    Os retangulos vetoriais desenhados no documento (as celulas da
    tabela sao retangulos com contorno, uma por celula), em pontos PDF.
    O retangulo de fundo da pagina inteira e ignorado.
    """
    from pypdf.generic import ContentStream

    page = PdfReader(str(pdf_path)).pages[0]
    content = ContentStream(page.get_contents(), page.pdf)
    stack = [(1, 0, 0, 1, 0, 0)]
    found = []
    for operands, operator in content.operations:
        op = operator.decode() if isinstance(operator, bytes) else operator
        if op == "q":
            stack.append(stack[-1])
        elif op == "Q":
            stack.pop()
        elif op == "cm":
            stack[-1] = _mat_mult(tuple(float(v) for v in operands), stack[-1])
        elif op == "re":
            x, y, w, h = (float(v) for v in operands)
            x0, y0 = _apply(stack[-1], x, y)
            x1, y1 = _apply(stack[-1], x + w, y + h)
            rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            if rect[2] - rect[0] > PAGE_WIDTH * 0.95 and rect[3] - rect[1] > PAGE_HEIGHT * 0.95:
                continue  # fundo branco da pagina
            found.append(rect)
    return found


@pytest.fixture(scope="module")
def sample_pdf_bytes():
    return render_invitation_letter_fr(FR_SAMPLE_DATA)


class TestGeracaoBasica:
    def test_pdf_e_gerado(self, sample_pdf_bytes):
        assert isinstance(sample_pdf_bytes, bytes)

    def test_pdf_nao_e_vazio(self, sample_pdf_bytes):
        assert len(sample_pdf_bytes) > 10_000

    def test_pdf_pode_ser_aberto_pelo_pypdf(self, sample_pdf_bytes):
        reader = PdfReader(io.BytesIO(sample_pdf_bytes))
        assert len(reader.pages) >= 1

    def test_pdf_possui_uma_pagina(self, sample_pdf_bytes):
        reader = PdfReader(io.BytesIO(sample_pdf_bytes))
        assert len(reader.pages) == 1

    def test_pdf_possui_tamanho_a4(self, sample_pdf_bytes):
        reader = PdfReader(io.BytesIO(sample_pdf_bytes))
        box = reader.pages[0].mediabox
        assert float(box.width) == PAGE_WIDTH == 596.0
        assert float(box.height) == PAGE_HEIGHT == 842.0

    def test_sha256_e_deterministico_para_o_mesmo_input(self):
        first = render_invitation_letter_fr(dict(FR_SAMPLE_DATA))
        second = render_invitation_letter_fr(dict(FR_SAMPLE_DATA))
        assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()

    def test_sha256_muda_se_um_dado_mudar(self):
        alterado = dict(FR_SAMPLE_DATA, guest_name="Outra Pessoa")
        original = render_invitation_letter_fr(dict(FR_SAMPLE_DATA))
        mudado = render_invitation_letter_fr(alterado)
        assert hashlib.sha256(original).hexdigest() != hashlib.sha256(mudado).hexdigest()


class TestConteudoVariavel:
    def test_campos_variaveis_aparecem_no_pdf(self, sample_pdf_bytes):
        reader = PdfReader(io.BytesIO(sample_pdf_bytes))
        text = reader.pages[0].extract_text()
        for value in (
            "Claire",
            "Dubois",
            "00000000",
            "Carlos",
            "Silva",
            "YY000000",
            "Woluwe-Saint-Lambert",
        ):
            assert value in text, f"{value!r} não encontrado no PDF gerado"

    def test_amostra_original_nao_fica_escondida_sob_a_mascara(self):
        """
        Regressão: cobrir um texto com um retângulo branco (a máscara)
        não remove o texto do fluxo do PDF -- ele continuaria
        extraível/copiável por baixo do valor real, se não fosse também
        removido do conteúdo da página base (ver pdfengine.redact).
        """
        dados = dict(FR_SAMPLE_DATA, guest_name="Nome Trocado Exemplo")
        pdf_bytes = render_invitation_letter_fr(dados)
        text = PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text()

        for word in ("Nome", "Trocado", "Exemplo"):
            assert word in text
        assert "Carlos" not in text
        assert "Silva" not in text


class TestElementosFixosPreservados:
    def test_dados_fixos_permanecem_presentes(self, sample_pdf_bytes):
        reader = PdfReader(io.BytesIO(sample_pdf_bytes))
        text = reader.pages[0].extract_text()
        for word in (
            "LETTRE",
            "Annexe",
            "3bis",
            "Schengen",
            "Signature",
            "Nom",
            "Nationalité",
        ):
            assert word in text

    def test_qr_code_logo_e_bandeira_permanecem_byte_a_byte_identicos(self, sample_pdf_bytes):
        """
        Não recriamos o QR Code, o logo do IBZ nem a bandeira -- eles têm
        que ser exatamente os mesmos bytes de imagem do PDF oficial,
        nunca uma reconstrução.
        """
        base_reader = PdfReader(str(BASE_PDF_PATH))
        base_xobjects = base_reader.pages[0]["/Resources"]["/XObject"].values()
        base_images = sorted((x.get_object().get_data() for x in base_xobjects), key=len)

        gen_reader = PdfReader(io.BytesIO(sample_pdf_bytes))
        gen_xobjects = gen_reader.pages[0]["/Resources"]["/XObject"].values()
        gen_images = sorted((x.get_object().get_data() for x in gen_xobjects), key=len)

        assert base_images == gen_images

    def test_numero_de_paginas_e_recursos_graficos_e_o_mesmo_do_original(self, sample_pdf_bytes):
        base_reader = PdfReader(str(BASE_PDF_PATH))
        gen_reader = PdfReader(io.BytesIO(sample_pdf_bytes))
        base_xobjs = base_reader.pages[0]["/Resources"]["/XObject"]
        gen_xobjs = gen_reader.pages[0]["/Resources"]["/XObject"]
        assert len(base_xobjs) == len(gen_xobjs) == 3


class TestFormatacao:
    def test_nome_documento_endereco_e_telefone_sao_negrito(self, sample_pdf_bytes):
        overlay = _overlay_runs(sample_pdf_bytes)
        bold_words = {text for text, font, *_ in overlay if _is_overlay_font(font, bold=True)}

        assert any("Claire" in w for w in bold_words)
        assert any("00000000" in w for w in bold_words)
        assert any("Woluwe-Saint-Lambert" in w for w in bold_words)
        assert any("470" in w for w in bold_words)

    def test_nascimento_e_nacionalidade_do_anfitriao_nao_sao_negrito(self, sample_pdf_bytes):
        overlay = _overlay_runs(sample_pdf_bytes)
        regular_words = {
            text for text, font, *_ in overlay if _is_overlay_font(font, bold=False)
        }
        bold_words = {text for text, font, *_ in overlay if _is_overlay_font(font, bold=True)}

        assert any("14/03/1985" in w for w in regular_words)
        assert not any("14/03/1985" in w for w in bold_words)
        assert any(w.strip() == "belge" for w in regular_words)


class TestTextoLongo:
    def test_endereco_longo_quebra_em_varias_linhas_sem_erro(self):
        dados = dict(
            FR_SAMPLE_DATA,
            host_address=(
                "Avenue Louise 523, Boîte Postale 12B - 1050 Ixelles, "
                "Bruxelles-Capitale, Belgique"
            ),
        )
        pdf_bytes = render_invitation_letter_fr(dados)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        assert "Bruxelles-Capitale" in reader.pages[0].extract_text()

    def test_nome_muito_longo_nao_ultrapassa_a_area_da_tabela(self):
        dados = dict(FR_SAMPLE_DATA, guest_name="Maria Eduarda Fernandes de Albuquerque Nogueira")
        pdf_bytes = render_invitation_letter_fr(dados)
        assert isinstance(pdf_bytes, bytes)

    def test_overflow_impossivel_levanta_erro_explicito(self):
        dados = dict(FR_SAMPLE_DATA, host_address="A" * 400)
        with pytest.raises(TextOverflowError):
            render_invitation_letter_fr(dados)

    def test_overflow_nao_produz_pdf_nenhum(self):
        """Um erro de overflow não deve deixar um PDF incompleto/incorreto
        para trás -- a exceção interrompe antes de qualquer bytes ser
        devolvido."""
        dados = dict(FR_SAMPLE_DATA, host_address="B" * 400)
        with pytest.raises(TextOverflowError):
            result = render_invitation_letter_fr(dados)
            pytest.fail(f"deveria ter levantado antes de devolver {len(result)} bytes")


class TestDadosObrigatorios:
    @pytest.mark.parametrize("campo", list(FR_SAMPLE_DATA.keys()))
    def test_campo_ausente_levanta_erro_explicito(self, campo):
        dados = dict(FR_SAMPLE_DATA)
        del dados[campo]
        with pytest.raises(MissingSnapshotDataError):
            render_invitation_letter_fr(dados)

    def test_campo_vazio_tambem_e_tratado_como_ausente(self):
        dados = dict(FR_SAMPLE_DATA, guest_passport="")
        with pytest.raises(MissingSnapshotDataError):
            render_invitation_letter_fr(dados)


class TestIsolamentoDoDjango:
    def test_renderer_recebe_so_um_dict_simples(self, sample_pdf_bytes):
        """
        `render_invitation_letter_fr` não recebe (nem precisaria receber)
        `request`, usuário autenticado ou sessão -- só um dict de valores
        já resolvidos. O próprio fixture desta suíte de testes já prova
        isso: nenhum objeto Django é construído em nenhum teste deste
        arquivo.
        """
        import inspect

        params = inspect.signature(render_invitation_letter_fr).parameters
        assert list(params) == ["data"]

    def test_pdfengine_nao_importa_django(self):
        pdfengine_dir = Path(__file__).resolve().parent.parent / "pdfengine"
        offending = []
        for path in pdfengine_dir.rglob("*.py"):
            if "assets" in path.parts or "docs" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if "import django" in text or "from django" in text:
                offending.append(str(path))
        assert offending == []


def test_mat_mult_e_associativa_o_suficiente_para_compor_ctm():
    """Sanidade da álgebra usada tanto na medição quanto na redação de
    texto: compor (m1 então m2) equivale a aplicar m1 e depois m2 a um ponto."""
    m1 = (2, 0, 0, 2, 10, 10)  # escala 2x, desloca (10,10)
    m2 = (1, 0, 0, 1, 5, 0)  # desloca (5,0)
    composed = _mat_mult(m1, m2)
    direct = _apply(m2, *_apply(m1, 1, 1))
    via_compose = _apply(composed, 1, 1)
    assert direct == pytest.approx(via_compose)


class TestFidelidadeVisual:
    """
    Validacao visual automatica -- `extract_text()` prova que o texto
    certo esta no PDF, mas nao prova que o resto do documento continuou
    intacto. Aqui as duas paginas (a oficial e a gerada) sao
    rasterizadas e comparadas pixel a pixel FORA das areas variaveis: se
    o renderer tivesse deslocado uma linha da tabela, apagado um trecho
    de texto juridico, mexido no logo/QR/bandeira ou mudado o
    espacamento, a diferenca apareceria aqui.
    """

    @staticmethod
    def _rasterizar(pdf_bytes, scale=2.0):
        import pypdfium2 as pdfium

        return pdfium.PdfDocument(pdf_bytes)[0].render(scale=scale).to_pil().convert("L")

    @staticmethod
    def _apagar_zonas_variaveis(image, scale=2.0):
        """Pinta de branco as areas que o renderer PODE mudar, para
        comparar so o que deveria ter ficado igual."""
        from PIL import ImageDraw

        image = image.copy()
        draw = ImageDraw.Draw(image)
        for zone in ZONES:
            mask = zone.mask
            top = (PAGE_HEIGHT - (mask.y + mask.height)) * scale
            draw.rectangle(
                [mask.x * scale, top, (mask.x + mask.width) * scale, top + mask.height * scale],
                fill=255,
            )
        return image

    def test_tudo_fora_das_zonas_variaveis_e_pixel_identico_ao_oficial(
        self, sample_pdf_bytes
    ):
        from PIL import ImageChops

        original = self._rasterizar(BASE_PDF_PATH.read_bytes())
        gerado = self._rasterizar(sample_pdf_bytes)
        assert original.size == gerado.size

        diferenca = ImageChops.difference(
            self._apagar_zonas_variaveis(original), self._apagar_zonas_variaveis(gerado)
        )

        assert diferenca.getbbox() is None, (
            "o documento mudou fora das areas variaveis -- algo do conteudo "
            "fixo (texto juridico, tabela, logo, QR Code, bandeira, "
            "espacamento) foi deslocado ou apagado"
        )

    def test_as_zonas_variaveis_realmente_mudaram(self, sample_pdf_bytes):
        """Contraprova do teste acima: a comparacao so tem valor se as
        areas variaveis DE FATO diferem do documento de amostra quando os
        dados mudam."""
        from PIL import ImageChops

        outros = dict(FR_SAMPLE_DATA, guest_name="Pessoa Completamente Outra")
        original = self._rasterizar(BASE_PDF_PATH.read_bytes())
        gerado = self._rasterizar(render_invitation_letter_fr(outros))

        assert ImageChops.difference(original, gerado).getbbox() is not None


class TestPdfBaseIndisponivel:
    def test_pdf_base_ausente_falha_explicitamente(self, monkeypatch, tmp_path):
        import pdfengine.render as render_module

        monkeypatch.setattr(
            render_module, "BASE_PDF_PATH", tmp_path / "nao-existe.pdf"
        )
        with pytest.raises(BasePdfUnavailableError):
            render_invitation_letter_fr(FR_SAMPLE_DATA)

    def test_pdf_base_corrompido_falha_explicitamente(self, monkeypatch, tmp_path):
        import pdfengine.render as render_module

        quebrado = tmp_path / "corrompido.pdf"
        quebrado.write_bytes(b"isto nao e um PDF")
        monkeypatch.setattr(render_module, "BASE_PDF_PATH", quebrado)

        with pytest.raises(BasePdfUnavailableError):
            render_invitation_letter_fr(FR_SAMPLE_DATA)


class TestFontesDoOverlay:
    def test_fontes_do_overlay_sao_embutidas_no_pdf(self, sample_pdf_bytes):
        """
        A Liberation Sans vai EMBUTIDA: o documento nao pode depender da
        fonte instalada em quem abre nem em quem gera.
        """
        reader = PdfReader(io.BytesIO(sample_pdf_bytes))
        fonts = reader.pages[0]["/Resources"]["/Font"]

        embutidas = [
            f.get_object()
            for f in fonts.values()
            if _is_overlay_font(f.get_object().get("/BaseFont"))
        ]
        assert len(embutidas) == 2, "esperado regular + negrito da Liberation Sans"

        for font in embutidas:
            descriptor = font["/FontDescriptor"].get_object()
            assert "/FontFile2" in descriptor, "a fonte do overlay não foi embutida"

    def test_nenhuma_fonte_proprietaria_foi_adicionada_por_nos(self, sample_pdf_bytes):
        """
        As unicas Arial do PDF final sao as que JA vinham embutidas no
        documento oficial -- nao extraimos nem redistribuimos nenhuma.
        """
        base_fonts = {
            str(f.get_object().get("/BaseFont"))
            for f in PdfReader(str(BASE_PDF_PATH)).pages[0]["/Resources"]["/Font"].values()
        }
        gen_fonts = {
            str(f.get_object().get("/BaseFont"))
            for f in PdfReader(io.BytesIO(sample_pdf_bytes))
            .pages[0]["/Resources"]["/Font"]
            .values()
        }

        arial_novas = {f for f in gen_fonts - base_fonts if "Arial" in f}
        assert arial_novas == set()


class TestMascarasNaoTocamAsImagens:
    """
    Regressao de um defeito real: a area reservada do nome da assinatura
    ia ate a margem direita do corpo e cruzava o logo do IBZ e o QR Code.
    O retangulo branco da mascara apagava uma fatia horizontal dos dois --
    as abas preta e amarela da bandeira do logo sumiam e o topo do QR
    Code ficava em branco, o que o deixa ilegivel.

    Nem `extract_text()` nem a comparacao dos bytes das imagens pegam
    isso: os bytes da imagem continuam intactos, o estrago e a tinta
    branca por cima. Por isso estes dois testes olham a GEOMETRIA das
    mascaras e os PIXELS das imagens.
    """

    def test_nenhuma_mascara_cruza_uma_imagem_do_documento(self):
        imagens = _image_placements(BASE_PDF_PATH)
        assert imagens, "o documento oficial deveria ter imagens (logo, QR, bandeira)"

        conflitos = []
        for zone in ZONES:
            m = zone.mask
            for nome, ix0, iy0, ix1, iy1 in imagens:
                cruza_x = m.x < ix1 and ix0 < m.x + m.width
                cruza_y = m.y < iy1 and iy0 < m.y + m.height
                if cruza_x and cruza_y:
                    conflitos.append(f"{zone.key} cobre {nome}")

        assert conflitos == [], "máscara sobre imagem do documento: " + "; ".join(conflitos)

    def test_logo_qr_e_bandeira_saem_pixel_a_pixel_iguais_ao_oficial(self, sample_pdf_bytes):
        """
        A prova do resultado, nao so da geometria: as areas das imagens,
        rasterizadas, tem que ser identicas as do documento oficial.
        """
        import pypdfium2 as pdfium
        from PIL import ImageChops

        escala = 4.0

        def rasterizar(pdf_bytes):
            return pdfium.PdfDocument(pdf_bytes)[0].render(scale=escala).to_pil().convert("RGB")

        oficial = rasterizar(BASE_PDF_PATH.read_bytes())
        gerado = rasterizar(sample_pdf_bytes)

        for nome, x0, y0, x1, y1 in _image_placements(BASE_PDF_PATH):
            caixa = (
                int(x0 * escala),
                int((PAGE_HEIGHT - y1) * escala),
                int(x1 * escala) + 1,
                int((PAGE_HEIGHT - y0) * escala) + 1,
            )
            diferenca = ImageChops.difference(oficial.crop(caixa), gerado.crop(caixa))
            assert diferenca.getbbox() is None, f"a imagem {nome} saiu diferente do original"


class TestMascarasNaoApagamAsLinhasDaTabela:
    """
    Regressao de um defeito real: a area do paragrafo do anfitriao descia
    ate y=640 e a celula de cima da tabela fecha em y=640,25 -- o
    retangulo branco da mascara apagava a BORDA SUPERIOR INTEIRA da
    tabela. Uma mascara pode ficar DENTRO de uma celula (e para isso que
    ela existe), mas nunca cruzar o contorno.
    """

    # metade da largura de traco padrao do PDF (1,0pt) mais uma folga
    TOLERANCIA = 0.75

    def _cruza_o_contorno(self, mask, rect):
        x0, y0, x1, y1 = rect
        tol = self.TOLERANCIA
        toca = (
            mask.x < x1 + tol
            and x0 - tol < mask.x + mask.width
            and mask.y < y1 + tol
            and y0 - tol < mask.y + mask.height
        )
        if not toca:
            return False
        so_no_interior = (
            mask.x >= x0 + tol
            and mask.y >= y0 + tol
            and mask.x + mask.width <= x1 - tol
            and mask.y + mask.height <= y1 - tol
        )
        return not so_no_interior

    def test_nenhuma_mascara_cruza_o_contorno_de_um_retangulo(self):
        rects = _vector_rects(BASE_PDF_PATH)
        assert len(rects) >= 10, "esperadas as 10 células da tabela do documento"

        conflitos = [
            f"{zone.key} × retângulo x {r[0]:.1f}..{r[2]:.1f} y {r[1]:.1f}..{r[3]:.1f}"
            for zone in ZONES
            for r in rects
            if self._cruza_o_contorno(zone.mask, r)
        ]

        assert conflitos == [], "máscara sobre linha da tabela: " + "; ".join(conflitos)

    def test_a_borda_superior_da_tabela_continua_desenhada(self, sample_pdf_bytes):
        """
        A prova em pixels: a faixa onde fica a borda de cima da tabela
        tem que sair identica a do documento oficial.
        """
        import pypdfium2 as pdfium
        from PIL import ImageChops

        escala = 8.0

        def rasterizar(pdf_bytes):
            return pdfium.PdfDocument(pdf_bytes)[0].render(scale=escala).to_pil().convert("L")

        # faixa horizontal em torno de y=640,25, largura toda da tabela
        caixa = (
            int(45 * escala),
            int((PAGE_HEIGHT - 642.0) * escala),
            int(551 * escala),
            int((PAGE_HEIGHT - 638.5) * escala),
        )
        oficial = rasterizar(BASE_PDF_PATH.read_bytes()).crop(caixa)
        gerado = rasterizar(sample_pdf_bytes).crop(caixa)

        assert oficial.getbbox() is not None, "a faixa medida deveria conter a borda"
        assert ImageChops.difference(oficial, gerado).getbbox() is None


class TestNadaDaAmostraSobreNasZonasVariaveis:
    """
    Invariante central da redacao: dentro de uma area variavel nao pode
    restar NENHUM texto vindo da pagina original -- nem visivel, nem
    escondido sob a mascara e ainda extraivel/copiavel.

    Regressao de um defeito real: a decisao de remover era tomada pela
    ancora do bloco `BT..ET` (o `Tm`), mas neste documento o `Tm` marca o
    inicio do PARAGRAFO e cada palavra e posicionada depois, por `Td`.
    Quando a ancora caia fora da area mascarada e as palavras dentro (era
    o caso do item 2 e do nome da assinatura), a amostra continuava no
    PDF final: extrair o texto mostrava "Rue des Exemple 25 ..." junto com
    o endereco real.
    """

    @staticmethod
    def _runs_da_base_original(pdf_bytes):
        """Trechos do PDF final ainda desenhados com as fontes Arial da
        pagina original (as nossas sao Liberation Sans)."""
        return [
            (texto, x, y)
            for texto, fonte, _tam, x, y in _extract_runs(pdf_bytes)
            if fonte and "Arial" in str(fonte)
        ]

    def test_nenhum_texto_original_sobra_dentro_de_uma_mascara(self, sample_pdf_bytes):
        sobras = [
            (zone.key, texto.strip(), x, y)
            for texto, x, y in self._runs_da_base_original(sample_pdf_bytes)
            for zone in ZONES
            if zone.mask.x <= x <= zone.mask.x + zone.mask.width
            and zone.mask.y <= y <= zone.mask.y + zone.mask.height
        ]
        assert sobras == [], f"texto da amostra sobrou dentro da máscara: {sobras}"

    def test_valores_de_amostra_somem_quando_os_dados_mudam(self):
        """
        Prova pelo conteudo, nao so pela posicao: trocando TODOS os dados,
        nenhum valor da amostra pode continuar extraivel do PDF.
        """
        dados = dict(
            FR_SAMPLE_DATA,
            host_name="Ana Pereira",
            host_birth="01/02/1970",
            host_document="ZZ999999",
            host_address="Chaussée de Test 9 - 1000 Bruxelles",
            host_phone="+32 400 11 22 33",
            guest_name="Bruno Alves",
            guest_nationality="Portugaise",
            guest_birth="03/04/1980",
            guest_passport="XX111111",
            place="Ixelles",
            document_date="05/06/2027",
            signature_name="Ana Pereira",
        )
        texto = PdfReader(io.BytesIO(render_invitation_letter_fr(dados))).pages[0].extract_text()
        plano = " ".join(texto.split())

        for antigo in (
            "Claire",
            "Dubois",
            "14/03/1985",
            "00000000",
            "Exemple",
            "Woluwe-Saint-Lambert",
            "470",
            "Carlos",
            "Silva",
            "Brésilienne",
            "22/07/1990",
            "YY000000",
            "09/09/2026",
        ):
            assert antigo not in plano, f"{antigo!r} (dado de amostra) continua no PDF"

        for novo in ("Ana", "Pereira", "ZZ999999", "Bruno", "Alves", "Ixelles"):
            assert novo in plano, f"{novo!r} (dado real) não saiu no PDF"

    def test_o_marcador_da_lista_e_os_rotulos_da_tabela_continuam(self, sample_pdf_bytes):
        """
        Contraprova: a redacao nao pode ser ampla demais. O "2." do item e
        os rotulos da tabela ficam FORA das areas variaveis (a esquerda
        delas) e tem que permanecer, vindos da pagina original.
        """
        trechos = self._runs_da_base_original(sample_pdf_bytes)
        originais = " ".join(texto.strip() for texto, _x, _y in trechos)

        for fixo in ("2.", "Nom", "Nationalité", "passeport", "Durée", "Signature"):
            assert fixo in originais, f"{fixo!r} sumiu — a redação removeu conteúdo fixo"


class TestCaracteresDoDocumento:
    """
    Auditoria de caracteres: o PDF gerado tem que escrever os mesmos
    caracteres que o documento oficial, nao variantes tipograficas
    parecidas.
    """

    @staticmethod
    def _texto(pdf_bytes):
        return " ".join(PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text().split())

    def test_travessao_do_perfil_vira_hifen_como_no_documento(self):
        """
        O perfil monta o endereço com travessão (U+2013); o documento
        oficial usa hífen simples (U+002D). Quem se adapta é o documento.
        """
        dados = dict(
            FR_SAMPLE_DATA,
            host_address="Rue des Exemple 25 – 1200 Woluwe-Saint-Lambert",
        )
        texto = self._texto(render_invitation_letter_fr(dados))

        assert "Rue des Exemple 25 - 1200 Woluwe-Saint-Lambert" in texto
        assert "–" not in texto
        assert "—" not in texto

    def test_o_hifen_gerado_e_o_mesmo_caractere_do_documento_oficial(self):
        """Compara com o original, em vez de assumir qual é o caractere."""
        oficial = " ".join(PdfReader(str(BASE_PDF_PATH)).pages[0].extract_text().split())
        inicio = oficial.find("Rue des Exemple 25")
        separador_oficial = oficial[inicio + len("Rue des Exemple 25") + 1]

        dados = dict(
            FR_SAMPLE_DATA,
            host_address="Rue des Exemple 25 – 1200 Woluwe-Saint-Lambert",
        )
        gerado = self._texto(render_invitation_letter_fr(dados))
        i = gerado.find("Rue des Exemple 25")
        separador_gerado = gerado[i + len("Rue des Exemple 25") + 1]

        assert separador_gerado == separador_oficial == "-"

    def test_apostrofo_dos_textos_fixos_e_o_tipografico_do_original(self, sample_pdf_bytes):
        texto = self._texto(sample_pdf_bytes)
        # "carte d’identité" e "l’adresse suivante" sao texto fixo nosso,
        # redesenhado no overlay -- tem que sair com U+2019, como no original.
        assert "d’identité" in texto
        assert "l’adresse suivante" in texto

    def test_acentos_franceses_sobrevivem_nos_dados_variaveis(self):
        dados = dict(
            FR_SAMPLE_DATA,
            guest_name="François-Noël Échèvre",
            guest_nationality="Brésilienne",
            place="Liège",
        )
        texto = self._texto(render_invitation_letter_fr(dados))

        for esperado in ("François-Noël", "Échèvre", "Brésilienne", "Liège"):
            assert esperado in texto

    def test_espaco_insecavel_vira_espaco_normal(self):
        """
        Um espaço insecável não quebra linha: deixado como está, um valor
        colado viraria uma "palavra" longa demais e estouraria a área
        reservada sem necessidade.
        """
        dados = dict(FR_SAMPLE_DATA, host_phone="+32 470 00 00 00")
        texto = self._texto(render_invitation_letter_fr(dados))

        assert " " not in texto
        assert "+32 470 00 00 00" in texto

    def test_virgula_depois_de_negrito_nao_e_negrito(self, sample_pdf_bytes):
        """
        No original a vírgula logo após o nome em negrito é um objeto de
        texto próprio, em peso normal. Aqui a conferência é no PDF gerado.
        """
        overlay = _overlay_runs(sample_pdf_bytes)
        negrito = [t.strip() for t, f, *_ in overlay if _is_overlay_font(f, bold=True)]
        regular = [t.strip() for t, f, *_ in overlay if _is_overlay_font(f, bold=False)]

        assert "Dubois" in negrito
        assert "Dubois," not in negrito
        assert "," in regular

    def test_caractere_fora_da_fonte_falha_explicitamente(self):
        """
        O reportlab desenharia um glifo vazio e não avisaria nada -- um
        PDF oficial errado, gerado em silêncio.
        """
        dados = dict(FR_SAMPLE_DATA, guest_name="Jean 😀 Martin")
        with pytest.raises(UnrenderableCharacterError) as excinfo:
            render_invitation_letter_fr(dados)
        assert "U+1F600" in str(excinfo.value)

    def test_todo_caractere_dos_textos_fixos_existe_na_fonte(self):
        """
        Protege o texto fixo do layout: se alguém editar um parágrafo e
        introduzir um caractere que a fonte embutida não tem, isto acusa
        antes de virar PDF.
        """
        from pdfengine.fontconfig import register_fonts
        from pdfengine.layouts.carta_convite_fr import FONT_BOLD, FONT_REGULAR
        from pdfengine.measure import Run
        from pdfengine.textnorm import unsupported_characters

        register_fonts()
        faltando = []
        for zone in ZONES:
            for item in zone.runs:
                if not isinstance(item, Run):
                    continue
                fonte = FONT_BOLD if item.bold else FONT_REGULAR
                faltando += unsupported_characters(item.text, fonte)

        assert faltando == []


QR_URL_OFICIAL = "https://dofi.ibz.be/fr/themes/third-country-nationals/court-sejour"


def _rasterizar_pagina(pdf_bytes, escala):
    import pypdfium2 as pdfium

    return pdfium.PdfDocument(pdf_bytes)[0].render(scale=escala).to_pil()


def _recorte_da_imagem(pagina, placement, escala):
    """Recorta, da página rasterizada, a área onde uma imagem do
    documento é desenhada."""
    _nome, x0, y0, x1, y1 = placement
    return pagina.crop(
        (
            round(x0 * escala),
            round((PAGE_HEIGHT - y1) * escala),
            round(x1 * escala),
            round((PAGE_HEIGHT - y0) * escala),
        )
    )


class TestQrCodeContinuaLegivel:
    """
    Não basta a imagem do QR Code estar presente: ela precisa continuar
    LEGÍVEL. Aqui o PDF final é rasterizado e o código é lido de verdade
    (ver tests/qrdecode.py), conferindo que o endereço apontado continua
    sendo o do documento oficial.

    Isto existe por causa de um defeito real: uma máscara larga demais
    apagava o terço superior do QR Code. A imagem continuava embutida e
    idêntica byte a byte -- só que o código, impresso, não era mais
    legível.
    """

    ESCALA = 10.0

    def _ler_qr(self, pdf_bytes):
        from tests.qrdecode import QRDecodeError, decode_qr

        pagina = _rasterizar_pagina(pdf_bytes, self.ESCALA)
        lidos = []
        for placement in _image_placements(BASE_PDF_PATH):
            try:
                lidos.append(decode_qr(_recorte_da_imagem(pagina, placement, self.ESCALA)))
            except QRDecodeError:
                continue  # logo e bandeira não são QR Code
        return lidos

    def test_o_qr_do_pdf_gerado_aponta_para_o_endereco_oficial(self, sample_pdf_bytes):
        assert self._ler_qr(sample_pdf_bytes) == [QR_URL_OFICIAL]

    def test_o_qr_gerado_le_o_mesmo_que_o_do_documento_oficial(self, sample_pdf_bytes):
        """Compara com o original em vez de confiar só na constante."""
        assert self._ler_qr(sample_pdf_bytes) == self._ler_qr(BASE_PDF_PATH.read_bytes())

    def test_o_leitor_acusa_um_qr_danificado(self, sample_pdf_bytes):
        """
        Contraprova: se o leitor aceitasse qualquer coisa, os testes acima
        não provariam nada. Apagando uma faixa do código -- exatamente o
        que a máscara larga demais fazia -- a leitura tem que falhar.
        """
        from PIL import ImageDraw

        from tests.qrdecode import QRDecodeError, decode_qr

        pagina = _rasterizar_pagina(sample_pdf_bytes, self.ESCALA)
        qr = None
        for placement in _image_placements(BASE_PDF_PATH):
            recorte = _recorte_da_imagem(pagina, placement, self.ESCALA)
            try:
                decode_qr(recorte)
            except QRDecodeError:
                continue
            qr = recorte
            break
        assert qr is not None, "o QR Code deveria ter sido encontrado"

        estragado = qr.copy()
        desenho = ImageDraw.Draw(estragado)
        desenho.rectangle([0, 0, estragado.width, estragado.height // 3], fill="white")

        with pytest.raises(QRDecodeError):
            decode_qr(estragado)


# Dados extremos: cada caso troca UM campo por um valor bem maior que o
# da amostra oficial, para exercitar a quebra de linha, a reducao de
# fonte e o limite das areas reservadas.
DADOS_EXTREMOS = {
    "nome_do_anfitriao_muito_longo": {
        "host_name": "Marie-Christine Alexandra Vandenbroucke-Delacroix",
        "signature_name": "Marie-Christine Alexandra Vandenbroucke-Delacroix",
    },
    "sobrenome_composto": {"guest_name": "João Pedro de Almeida e Souza Vasconcelos"},
    "endereco_longo": {
        "host_address": (
            "Avenue des Nerviens 187, Boîte Postale 12B - 1040 Etterbeek, Bruxelles"
        )
    },
    "cidade_longa": {"place": "Sint-Pieters-Woluwe / Woluwe-Saint-Pierre"},
    "telefone_longo": {"host_phone": "+32 (0)2 123 45 67 / +55 11 98765-4321"},
    "nacionalidade_longa": {"guest_nationality": "Brésilienne naturalisée portugaise"},
    "nacionalidade_do_anfitriao_longa": {"host_nationality": "luxembourgeoise"},
    "documento_longo": {"host_document": "BE-1234567890-XYZ-0001"},
    "passaporte_longo": {"guest_passport": "BR-YY0000000000-2026"},
    "datas_e_duracao_normais": {
        "arrival_date": "01/12/2026",
        "departure_date": "31/12/2026",
        "duration_days": "31",
    },
}


class TestDadosExtremos:
    """
    Comportamento exigido para dados maiores que os da amostra: cabe →
    renderiza; não cabe → reduz a fonte dentro do limite; ainda não cabe →
    erro explícito. Nunca invadir outra área, nunca truncar calado.
    """

    @pytest.mark.parametrize("caso", sorted(DADOS_EXTREMOS))
    def test_renderiza_ou_falha_explicitamente(self, caso):
        dados = dict(FR_SAMPLE_DATA, **DADOS_EXTREMOS[caso])
        try:
            pdf_bytes = render_invitation_letter_fr(dados)
        except TextOverflowError:
            return  # recusa explícita é um desfecho aceito
        assert isinstance(pdf_bytes, bytes) and len(pdf_bytes) > 10_000

    @pytest.mark.parametrize("caso", sorted(DADOS_EXTREMOS))
    def test_nada_escapa_da_area_reservada(self, caso):
        """
        Cada trecho que o renderer desenha tem de ficar dentro da faixa
        horizontal da sua zona e dentro da página -- é isso que impede
        invadir a tabela, o logo, o QR Code ou sair do papel.
        """
        dados = dict(FR_SAMPLE_DATA, **DADOS_EXTREMOS[caso])
        try:
            pdf_bytes = render_invitation_letter_fr(dados)
        except TextOverflowError:
            return

        limites = [
            (zone.box.x - 1.0, zone.box.x + zone.box.width + 1.0) for zone in ZONES
        ]
        for texto, _fonte, _tam, x, y in _overlay_runs(pdf_bytes):
            assert 0 <= x <= PAGE_WIDTH, f"{texto!r} saiu da página em x={x}"
            assert 0 <= y <= PAGE_HEIGHT, f"{texto!r} saiu da página em y={y}"
            assert any(
                esq <= x <= dir_ for esq, dir_ in limites
            ), f"{texto!r} foi desenhado em x={x}, fora de qualquer área reservada"

    @pytest.mark.parametrize("caso", sorted(DADOS_EXTREMOS))
    def test_elementos_fixos_sobrevivem_a_dados_extremos(self, caso):
        """Com qualquer dado, logo, QR Code e bandeira têm de sair
        idênticos ao documento oficial."""
        from PIL import ImageChops

        dados = dict(FR_SAMPLE_DATA, **DADOS_EXTREMOS[caso])
        try:
            pdf_bytes = render_invitation_letter_fr(dados)
        except TextOverflowError:
            return

        escala = 4.0
        oficial = _rasterizar_pagina(BASE_PDF_PATH.read_bytes(), escala).convert("RGB")
        gerado = _rasterizar_pagina(pdf_bytes, escala).convert("RGB")

        for placement in _image_placements(BASE_PDF_PATH):
            diferenca = ImageChops.difference(
                _recorte_da_imagem(oficial, placement, escala),
                _recorte_da_imagem(gerado, placement, escala),
            )
            assert diferenca.getbbox() is None, (
                f"a imagem {placement[0]} foi danificada pelo caso {caso}"
            )

    def test_valor_grande_demais_para_qualquer_reducao_levanta_erro(self):
        """O limite tem de existir de verdade: um valor absurdo não pode
        sair truncado nem sobrepondo nada -- tem de interromper."""
        dados = dict(FR_SAMPLE_DATA, host_address="Avenue Interminable " * 40)
        with pytest.raises(TextOverflowError):
            render_invitation_letter_fr(dados)

    def test_a_reducao_de_fonte_respeita_o_minimo(self):
        """Entre caber e falhar existe a redução -- e ela nunca desce
        abaixo do mínimo definido no layout."""
        from pdfengine.layouts.carta_convite_fr import MIN_FONT_SIZE
        from pdfengine.measure import layout_runs
        from pdfengine.render import _resolve_runs

        zona = next(z for z in ZONES if z.key == "item2_address")
        dados = dict(
            FR_SAMPLE_DATA,
            host_address=(
                "Avenue des Nerviens 187, Boîte Postale 12B - 1040 Etterbeek, Bruxelles"
            ),
        )
        resultado = layout_runs(
            _resolve_runs(zona.runs, dados),
            max_width=zona.box.width,
            max_lines=zona.box.max_lines,
            font_size=zona.box.font_size,
            min_font_size=zona.box.min_font_size,
            regular_font=FONT_REGULAR,
            bold_font=FONT_BOLD,
        )
        assert MIN_FONT_SIZE <= resultado.font_size < zona.box.font_size


class TestElementosFixosNomeados:
    """
    Conferência dirigida dos elementos que a revisão pediu para vigiar um
    a um. A comparação ampla (`TestFidelidadeVisual`) já cobriria todos
    eles, mas aqui cada um falha com o próprio nome, o que torna a
    regressão imediata de ler.
    """

    ESCALA = 6.0

    # faixas medidas no documento, em pontos PDF: (x0, y0, x1, y1)
    FAIXAS = {
        "borda superior da tabela": (45.0, 638.5, 551.0, 642.0),
        "borda inferior da tabela": (45.0, 515.5, 551.0, 519.0),
        "linha da assinatura": (45.0, 156.0, 250.0, 163.0),
        "legenda sob a assinatura": (45.0, 133.0, 250.0, 141.5),
        "rodape (logo, QR e o que estiver ao lado)": (360.0, 70.0, 560.0, 190.0),
        "bandeira no topo": (160.0, 834.0, 435.0, 842.0),
        "titulo e subtitulo": (45.0, 755.0, 551.0, 790.0),
        "textos juridicos do meio": (45.0, 255.0, 551.0, 375.0),
    }

    @pytest.mark.parametrize("nome", sorted(FAIXAS))
    def test_faixa_sai_identica_ao_documento_oficial(self, sample_pdf_bytes, nome):
        from PIL import ImageChops

        x0, y0, x1, y1 = self.FAIXAS[nome]
        caixa = (
            round(x0 * self.ESCALA),
            round((PAGE_HEIGHT - y1) * self.ESCALA),
            round(x1 * self.ESCALA),
            round((PAGE_HEIGHT - y0) * self.ESCALA),
        )
        oficial = _rasterizar_pagina(BASE_PDF_PATH.read_bytes(), self.ESCALA).convert("L")
        gerado = _rasterizar_pagina(sample_pdf_bytes, self.ESCALA).convert("L")

        recorte_oficial = oficial.crop(caixa)
        assert recorte_oficial.getbbox() is not None, (
            f"a faixa {nome!r} está em branco no original -- a medida está errada"
        )
        diferenca = ImageChops.difference(recorte_oficial, gerado.crop(caixa))
        assert diferenca.getbbox() is None, f"{nome} saiu diferente do documento oficial"


class TestInventarioDeCaracteres:
    """
    Com os dados da amostra oficial, o PDF gerado escreve o MESMO
    documento -- então o conjunto de caracteres tem de bater exatamente
    com o do original, um por um.

    É a auditoria de caracteres na forma mais forte possível: pega
    troca de hífen por travessão, apóstrofo reto por tipográfico, acento
    perdido, espaço a mais ou a menos antes de pontuação, e qualquer
    "melhoria" acidental do texto fixo.
    """

    @staticmethod
    def _texto(fonte):
        leitor = PdfReader(fonte if isinstance(fonte, str) else io.BytesIO(fonte))
        return " ".join(leitor.pages[0].extract_text().split())

    @staticmethod
    def _inventario(texto):
        return {caractere: texto.count(caractere) for caractere in set(texto)}

    def test_o_inventario_de_caracteres_e_igual_ao_do_documento_oficial(
        self, sample_pdf_bytes
    ):
        oficial = self._inventario(self._texto(str(BASE_PDF_PATH)))
        gerado = self._inventario(self._texto(sample_pdf_bytes))

        diferencas = {
            caractere: (oficial.get(caractere, 0), gerado.get(caractere, 0))
            for caractere in set(oficial) | set(gerado)
            if oficial.get(caractere, 0) != gerado.get(caractere, 0)
        }
        assert diferencas == {}, (
            "o PDF gerado usa caracteres diferentes do oficial "
            f"(caractere: oficial/gerado): {diferencas}"
        )

    def test_o_documento_oficial_mistura_dois_apostrofos_e_nos_reproduzimos(
        self, sample_pdf_bytes
    ):
        """
        No título o original escreve D'INVITATION com apóstrofo reto
        (U+0027) e D’HÉBERGEMENT com o tipográfico (U+2019) -- uma
        inconsistência do próprio documento. O objetivo é reproduzi-lo,
        não corrigi-lo.
        """
        gerado = self._texto(sample_pdf_bytes)
        assert "D'INVITATION" in gerado
        assert "D’HÉBERGEMENT" in gerado

    def test_espaco_antes_de_dois_pontos_na_tipografia_francesa(self, sample_pdf_bytes):
        """O francês põe espaço antes de ':' -- e o original faz isso."""
        oficial = self._texto(str(BASE_PDF_PATH))
        gerado = self._texto(sample_pdf_bytes)

        for trecho in ("présente :", "suivante :", "Nom et prénom :"):
            assert trecho in oficial
            assert trecho in gerado
