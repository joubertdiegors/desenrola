"""
A seção "Nossos Parceiros" no modelo 2a, o escolhido pelo cliente.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a grade fique presa em quatro colunas.** A quantidade de
   parceiros vem do banco e muda. Com dois cadastrados, quatro colunas
   deixariam metade da fileira vazia -- a grade tem de acompanhar;
2. **Que apareça um "Ver todos" sem para onde ir.** Na referência ele
   já é opcional; aqui não existe página de listagem, então ele não é
   desenhado;
3. **Que a logomarca seja recortada.** O cartão da referência recorta
   FOTOGRAFIAS. O que está cadastrado aqui é logomarca, e cortá-la
   cortaria o nome da empresa;
4. **Que um cartão sem endereço mostre um botão morto.** Sem `url`, o
   cartão não é link e não ganha botão;
5. **Que o Mini Banner perca o botão no celular.** Ele era escondido
   por CSS -- uma chamada para ação sem a ação;
6. **Que a seção apareça vazia.** Sem nenhum parceiro ativo, some
   inteira, com o item do menu junto.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.content.models import Asset, Partner

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")

# O menor GIF válido -- o teste precisa de um arquivo de imagem de
# verdade, não do conteúdo dele.
GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@pytest.fixture
def imagem_de_parceiro(db):
    return Asset.objects.create(
        kind=Asset.Kind.PARTNER,
        file=SimpleUploadedFile("parceiro.gif", GIF, content_type="image/gif"),
        alt_text="Logomarca do parceiro",
    )


def criar(quantos, com_url=True):
    for numero in range(1, quantos + 1):
        Partner.objects.create(
            name=f"Parceiro {numero}",
            url=f"https://parceiro{numero}.example.com" if com_url else "",
            order=numero,
        )


def area(client):
    html = client.get(HOME).content.decode()
    return html[html.index("<main") : html.index("</main>")]


def secao_dos_parceiros(client):
    html = area(client)
    if 'id="parceiros"' not in html:
        return ""
    inicio = html.index('id="parceiros"')
    return html[inicio : html.index("</section>", inicio)]


# ===========================================================================
# 1. A grade acompanha quantos parceiros existem
# ===========================================================================


class TestGradeDinamica:
    @pytest.mark.parametrize("quantos", (1, 2, 3))
    def test_menos_de_quatro_encolhe_a_grade(self, client, quantos):
        criar(quantos)

        html = secao_dos_parceiros(client)

        assert f"partners-grid-{quantos}" in html

    @pytest.mark.parametrize("quantos", (4, 5, 9))
    def test_quatro_ou_mais_usa_a_grade_cheia(self, client, quantos):
        criar(quantos)

        html = secao_dos_parceiros(client)

        assert 'class="partners-grid"' in html

    def test_a_contagem_vem_do_banco(self, client):
        """Desativar um parceiro muda a grade -- o número não está escrito."""
        criar(3)
        Partner.objects.filter(name="Parceiro 3").update(is_active=False)

        html = secao_dos_parceiros(client)

        assert "partners-grid-2" in html
        assert "Parceiro 3" not in html

    @pytest.mark.parametrize("quantos", (1, 2, 3, 4, 7))
    def test_todos_os_ativos_sao_desenhados(self, client, quantos):
        criar(quantos)

        html = secao_dos_parceiros(client)

        assert html.count("partner-card") == quantos


# ===========================================================================
# 2. Sem parceiro, a seção inteira some
# ===========================================================================


class TestSemParceiro:
    def test_a_secao_nao_aparece(self, client):
        assert 'id="parceiros"' not in area(client)

    def test_nem_o_cabecalho_sozinho(self, client):
        assert "parceiros-cabeca" not in area(client)

    def test_o_item_do_menu_some_junto(self, client):
        """A âncora levaria a uma seção que não está na página."""
        assert 'href="#parceiros"' not in client.get(HOME).content.decode()


# ===========================================================================
# 3. O cabeçalho do modelo 2a
# ===========================================================================


class TestCabecalho:
    def test_titulo_e_apoio_ficam_num_bloco_proprio(self, client):
        criar(2)

        html = secao_dos_parceiros(client)

        assert "parceiros-cabeca" in html
        assert html.index("parceiros-cabeca") < html.index("partners-grid")

    def test_nao_ha_link_ver_todos(self, client):
        """Não existe página de listagem: o link não é desenhado."""
        criar(4)

        html = secao_dos_parceiros(client)

        assert "Ver todos" not in html

    def test_sem_texto_de_apoio_o_paragrafo_nao_sai(self, client):
        from apps.content.models import PageSectionTranslation

        criar(2)
        traducao = PageSectionTranslation.objects.get(
            section__page__key="home", section__key="partners", language="pt"
        )
        traducao.content = {**traducao.content, "lead": ""}
        traducao.save(update_fields=["content"])

        html = secao_dos_parceiros(client)

        assert "section-lead" not in html


# ===========================================================================
# 4. O cartão
# ===========================================================================


class TestCartao:
    def test_o_botao_ocupa_a_largura_inteira(self, client):
        criar(2)

        html = secao_dos_parceiros(client)

        assert "btn btn-primary btn-block" in html

    def test_o_botao_fica_depois_do_nome(self, client):
        """Na referência ele é ancorado no pé do cartão."""
        criar(1)

        html = secao_dos_parceiros(client)

        assert html.index("<h3>") < html.index("btn-block")

    def test_sem_endereco_nao_ha_botao_nem_link(self, client):
        criar(2, com_url=False)

        html = secao_dos_parceiros(client)

        assert "btn-block" not in html
        assert "href=" not in html

    def test_a_logomarca_nao_e_recortada(self):
        """`contain` no CSS -- `cover` cortaria o nome da empresa."""
        css = (
            __import__("pathlib")
            .Path("static/css/layout.css")
            .read_text(encoding="utf-8")
        )
        regra = css[css.index("img.partner-image") : css.index("img.partner-image") + 120]

        assert "contain" in regra
        assert "cover" not in regra

    def test_a_imagem_tem_veu(self, client):
        criar(1)

        assert "partner-veu" in secao_dos_parceiros(client)

    def test_o_veu_nao_e_lido_por_leitor_de_tela(self, client):
        criar(1)

        assert '<span class="partner-veu" aria-hidden="true"></span>' in secao_dos_parceiros(
            client
        )

    def test_a_logomarca_cadastrada_aparece(self, client, imagem_de_parceiro):
        Partner.objects.create(
            name="Com logo", url="https://x.example.com", logo=imagem_de_parceiro, order=1
        )

        html = secao_dos_parceiros(client)

        assert "img-slot" not in html
        assert 'class="partner-image"' in html

    def test_o_link_externo_abre_em_outra_aba_com_noopener(self, client):
        criar(1)

        html = secao_dos_parceiros(client)

        assert 'target="_blank"' in html
        assert 'rel="noopener"' in html


# ===========================================================================
# 5. O Mini Banner no celular
# ===========================================================================


class TestMiniBanner:
    def _regra_do_celular(self):
        import pathlib
        import re

        css = pathlib.Path("static/css/layout.css").read_text(encoding="utf-8")
        blocos = re.findall(r"@media \(max-width: 767px\) \{(.*?)\n\}", css, re.S)
        return "\n".join(bloco for bloco in blocos if ".cta-banner" in bloco)

    def test_o_botao_nao_e_mais_escondido(self):
        regra = self._regra_do_celular()

        assert ".cta-banner .btn { display: none; }" not in regra

    def test_o_botao_ocupa_a_largura_inteira(self):
        assert ".cta-banner .btn { width: 100%" in self._regra_do_celular()

    def test_a_faixa_sangra_ate_as_bordas(self):
        """
        -20px cancela o `padding` lateral de `.section`; qualquer outro
        valor sobra ou falta, e sobrar faz a página rolar de lado.
        """
        regra = self._regra_do_celular()

        assert "margin: 22px -20px 26px;" in regra
        assert "border-radius: 0;" in regra

    def test_o_botao_continua_no_html(self, client):
        html = area(client)

        assert "cta-banner" in html
        assert html.count("cta-banner") >= 2
