"""
A identidade visual nova da Home.

A Home passou a seguir a referência "Home compacta": coluna estreita e
centrada, faixas de fundo alternadas, tipografia Manrope, cartões
discretos e uma fileira só de parceiros.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a alternância de fundos se perca.** Duas faixas iguais em
   sequência apagam a divisão entre as seções, e é ela que organiza a
   página inteira;
2. **Que a identidade pública vaze para o produto.** A tipografia e a
   coluna estreita valem em `body.publico` -- painel, assistente e
   perfil continuam como estão;
3. **Que o conteúdo volte a ser escrito no código.** Contador, passos,
   perguntas, parceiros e rodapé continuam vindo do banco e do CMS;
4. **Que o carrossel de parceiros volte.** A referência desenha uma
   fileira, e acima de quatro o "Ver todos" leva à página de parceiros;
5. **Que a seção de perguntas volte a trazer o que não é pergunta.**
6. **Que apareça link para lugar nenhum** -- `href="#"` ou vazio.
"""

import pathlib
import re

import pytest
from django.urls import reverse

from apps.content.models import (
    FaqItem,
    PageSection,
    PageSectionTranslation,
    Partner,
    SiteSettings,
)

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")
LAYOUT = pathlib.Path("static/css/layout.css")


@pytest.fixture
def secao_da_home(db):
    """
    Escreve o conteudo (e os interruptores) de UMA parte da Home.

    As partes ja nascem com o banco, semeadas pelas migrations; aqui so
    se troca o que o teste precisa olhar. Os campos estruturais
    (contador, botoes) sao colunas de `PageSection`; o resto e o JSON da
    traducao.
    """
    ESTRUTURAIS = {
        "contador_ativo": "counter_enabled",
        "contador_posicao": "counter_position",
        "contador_ao_vivo_ativo": "counter_live_enabled",
        "parceiros_ver_todos_ativo": "partners_view_all_enabled",
    }

    def _escrever(chave, **campos):
        secao = PageSection.objects.get(page__key="home", key=chave)
        colunas = []
        for nome, coluna in ESTRUTURAIS.items():
            if nome in campos:
                setattr(secao, coluna, campos.pop(nome))
                colunas.append(coluna)
        if colunas:
            secao.save(update_fields=[*colunas, "updated_at"])

        if campos:
            traducao, _criada = PageSectionTranslation.objects.get_or_create(
                section=secao, language="pt", defaults={"content": {}}
            )
            traducao.content = {**(traducao.content or {}), **campos}
            traducao.save(update_fields=["content", "updated_at"])
        return secao

    return _escrever


def criar_parceiros(quantos):
    for numero in range(1, quantos + 1):
        Partner.objects.create(
            name=f"Parceiro {numero}",
            url=f"https://parceiro{numero}.example.com",
            order=numero,
        )


def criar_perguntas(quantas=3):
    for numero in range(1, quantas + 1):
        FaqItem.objects.create(
            question=f"Pergunta {numero}?", answer=f"Resposta {numero}.", order=numero
        )


def corpo(client, url=HOME):
    return client.get(url).content.decode()


def secao(html, ancora):
    inicio = html.index(ancora)
    inicio = html.rindex("<section", 0, inicio)
    return html[inicio : html.index("</section>", inicio)]


# ===========================================================================
# 1. A casca: coluna, faixas e tipografia
# ===========================================================================


class TestACasca:
    def test_a_home_veste_a_identidade_publica(self, client):
        assert 'class="publico"' in corpo(client)

    def test_a_area_logada_nao_veste(self, auth_client):
        """
        A identidade nova é da vitrine. O painel continua com a
        tipografia e as medidas do produto.
        """
        html = auth_client.get(reverse("core:dashboard")).content.decode()

        assert 'class="publico"' not in html

    def test_a_coluna_publica_tem_a_largura_da_referencia(self):
        css = LAYOUT.read_text(encoding="utf-8")
        regra = css[css.index("body.publico .container,") :][:220]

        assert "max-width: 960px" in regra
        assert "padding-left: 24px" in regra

    def test_a_coluna_do_produto_nao_encolheu(self):
        """
        `.container` veste o site inteiro. Estreitá-lo mudaria o painel,
        o assistente e o perfil -- que não são desta rodada.
        """
        css = LAYOUT.read_text(encoding="utf-8")
        regra = css[css.index(".container { width: 100%;") :][:120]

        assert "max-width: 1280px" in regra

    def test_a_tipografia_publica_e_manrope(self):
        css = LAYOUT.read_text(encoding="utf-8")
        bloco = css[css.index("body.publico {") :][:400]

        assert "Manrope" in bloco

    def test_as_duas_familias_vem_no_mesmo_pedido(self):
        base = pathlib.Path("templates/base.html").read_text(encoding="utf-8")

        assert base.count("fonts.googleapis.com/css2") == 1
        assert "family=Inter" in base
        assert "family=Manrope" in base

    @pytest.mark.parametrize(
        "ancora,classe",
        [
            ("como-funciona", "home-secao-azul"),
            ("parceiros", "home-secao-branca"),
            ("faq", "home-secao-azul"),
        ],
    )
    def test_cada_secao_declara_a_sua_faixa(self, client, ancora, classe):
        criar_parceiros(3)
        criar_perguntas()

        assert classe in secao(corpo(client), f'id="{ancora}"')

    def test_as_faixas_alternam_e_nunca_se_repetem_seguidas(self, client):
        criar_parceiros(3)
        criar_perguntas()
        html = corpo(client)

        faixas = re.findall(r"home-secao home-secao-(\w+)", html)
        assert faixas, "nenhuma faixa desenhada"
        for anterior, seguinte in zip(faixas, faixas[1:], strict=False):
            if anterior == "branca" and seguinte == "branca":
                # Os selos ficam na mesma faixa branca do banner, de
                # propósito: é uma linha de apoio, não uma seção.
                continue
            assert anterior != seguinte, faixas


# ===========================================================================
# 2. A barra superior
# ===========================================================================


class TestBarraSuperior:
    def test_ha_uma_barra_para_desktop_e_outra_para_celular(self, client):
        html = corpo(client)

        assert 'class="topo-publico-barra d-only"' in html
        assert 'class="topo-publico-barra m-only"' in html

    def test_o_celular_tem_o_botao_de_menu(self, client):
        html = corpo(client)

        assert "topo-publico-hamburguer" in html

    def test_os_destinos_continuam_vindo_do_sistema(self, client):
        html = corpo(client)

        assert reverse("accounts:login") in html
        assert reverse("accounts:signup") in html

    def test_nenhum_link_para_lugar_nenhum(self, client):
        criar_parceiros(3)
        criar_perguntas()
        html = corpo(client)

        assert 'href="#"' not in html
        assert 'href=""' not in html


# ===========================================================================
# 3. O contador
# ===========================================================================


class TestContador:
    def test_a_capsula_traz_o_numero_real(self, client, secao_da_home):
        """O número sai de `letters.statistics`, nunca de um texto."""
        secao_da_home("hero", contador_ativo=True, badge_label="cartas geradas")

        html = corpo(client)
        pilula = html[html.index("banner-contador") : html.index("banner-contador") + 400]

        assert "banner-contador-valor" in pilula
        assert "cartas geradas" in pilula

    def test_nao_ha_numero_escrito_no_template(self):
        marcacao = pathlib.Path(
            "templates/core/secoes/_banner_contador.html"
        ).read_text(encoding="utf-8")

        assert "cartas_emitidas" in marcacao
        assert not re.search(r">\s*\d+\s+cartas", marcacao)

    def test_desligado_no_backoffice_a_capsula_nao_existe(self, client, secao_da_home):
        secao_da_home("hero", contador_ativo=False, badge_label="cartas geradas")

        assert "banner-contador" not in corpo(client)


# ===========================================================================
# 4. Como funciona
# ===========================================================================


class TestComoFunciona:
    def test_o_titulo_vira_chapeu_e_o_apoio_vira_titulo(self, client, secao_da_home):
        secao_da_home("how", title="Como funciona", lead="Três passos, e só.")

        bloco = secao(corpo(client), 'id="como-funciona"')
        assert "home-chapeu" in bloco
        assert "Como funciona" in bloco
        assert "<h2>Três passos, e só.</h2>" in bloco

    def test_cada_passo_e_numerado_pela_posicao(self, client, secao_da_home):
        secao_da_home(
            "how",
            cards=[
                {"title": "Preencha", "text": "a"},
                {"title": "Escolha", "text": "b"},
                {"title": "Receba", "text": "c"},
            ],
        )

        bloco = secao(corpo(client), 'id="como-funciona"')
        assert re.findall(r'how-card-numero">(\d\d)<', bloco) == ["01", "02", "03"]

    def test_a_numeracao_escrita_no_texto_nao_se_repete(self, client, secao_da_home):
        """
        O passo já é numerado pelo desenho: "01  1. Preencha" seria o
        mesmo número duas vezes.
        """
        secao_da_home("how", cards=[{"title": "1. Preencha", "text": "a"}])

        bloco = secao(corpo(client), 'id="como-funciona"')
        assert "1. Preencha" not in bloco
        assert "Preencha" in bloco

    def test_o_texto_dos_passos_continua_vindo_do_cms(self, client, secao_da_home):
        secao_da_home("how", cards=[{"title": "Passo do cliente", "text": "Texto dele."}])

        bloco = secao(corpo(client), 'id="como-funciona"')
        assert "Passo do cliente" in bloco
        assert "Texto dele." in bloco


# ===========================================================================
# 5. Parceiros: uma fileira, e o resto numa página
# ===========================================================================


class TestParceiros:
    @pytest.mark.parametrize("quantos", [1, 2, 3, 4])
    def test_ate_quatro_aparecem_todos(self, client, quantos):
        criar_parceiros(quantos)

        bloco = secao(corpo(client), 'id="parceiros"')
        assert bloco.count('class="partner-item"') == quantos

    @pytest.mark.parametrize("quantos", [5, 6, 9])
    def test_acima_de_quatro_a_home_mostra_quatro(self, client, quantos):
        criar_parceiros(quantos)

        bloco = secao(corpo(client), 'id="parceiros"')
        assert bloco.count('class="partner-item"') == 4

    def test_acima_de_quatro_o_ver_todos_leva_a_pagina_real(self, client):
        criar_parceiros(6)

        bloco = secao(corpo(client), 'id="parceiros"')
        assert reverse("core:parceiros") in bloco

    def test_com_quatro_ou_menos_nao_ha_ver_todos(self, client):
        criar_parceiros(4)

        bloco = secao(corpo(client), 'id="parceiros"')
        assert reverse("core:parceiros") not in bloco

    def test_nao_ha_carrossel_nem_barra_de_rolagem(self, client):
        criar_parceiros(9)

        bloco = secao(corpo(client), 'id="parceiros"')
        assert "carrossel" not in bloco
        assert "overflow" not in bloco

    def test_o_carrossel_saiu_do_projeto(self):
        """O script e o CSS do carrossel não podem voltar por engano."""
        assert not pathlib.Path("static/js/carrossel-de-parceiros.js").exists()
        assert "partners-carrossel" not in LAYOUT.read_text(encoding="utf-8")

    def test_a_grade_encolhe_com_poucos_parceiros(self, client):
        criar_parceiros(2)

        bloco = secao(corpo(client), 'id="parceiros"')
        assert "partners-grid-2" in bloco

    def test_sem_parceiro_a_secao_inteira_some(self, client):
        assert 'id="parceiros"' not in corpo(client)


# ===========================================================================
# 6. Perguntas frequentes: só pergunta e resposta
# ===========================================================================


class TestPerguntas:
    def test_a_secao_traz_o_titulo_e_as_perguntas(self, client):
        criar_perguntas(2)

        bloco = secao(corpo(client), 'id="faq"')
        assert "faq-titulo" in bloco
        assert bloco.count("faq-item") == 2

    def test_nao_ha_texto_de_apoio_nem_bloco_de_contato(self, client, secao_da_home):
        criar_perguntas()
        secao_da_home(
            "faq",
            title="Perguntas frequentes",
            lead="Apoio que a referência não desenha.",
            cta_title="Não encontrou?",
            cta_text="Fale com a gente.",
            cta="Falar com o suporte",
        )

        bloco = secao(corpo(client), 'id="faq"')
        assert "Apoio que a referência não desenha." not in bloco
        assert "Não encontrou?" not in bloco
        assert "Falar com o suporte" not in bloco

    def test_a_sanfona_continua_sendo_nativa(self, client):
        criar_perguntas(1)

        bloco = secao(corpo(client), 'id="faq"')
        assert "<details" in bloco
        assert "<summary" in bloco

    def test_as_perguntas_continuam_vindo_do_cadastro(self, client):
        FaqItem.objects.create(question="Do cliente?", answer="Do cliente.", order=1)

        bloco = secao(corpo(client), 'id="faq"')
        assert "Do cliente?" in bloco

    def test_pergunta_desativada_nao_aparece(self, client):
        FaqItem.objects.create(question="Ativa?", answer="Sim.", order=1)
        FaqItem.objects.create(
            question="Desativada?", answer="Não.", order=2, is_active=False
        )

        bloco = secao(corpo(client), 'id="faq"')
        assert "Desativada?" not in bloco

    def test_sem_pergunta_a_secao_inteira_some(self, client):
        assert 'id="faq"' not in corpo(client)


# ===========================================================================
# 7. Mini Banner e rodapé
# ===========================================================================


class TestFinalDaPagina:
    def test_o_mini_banner_e_uma_faixa_com_gradiente(self, client):
        html = corpo(client)

        assert "home-secao-gradiente" in html

    def test_o_botao_do_mini_banner_leva_ao_cadastro(self, client, secao_da_home):
        secao_da_home("cta", title="Facilite", text="Simples.", button="Começar agora")

        html = corpo(client)
        assert "home-cta-botao" in html
        assert reverse("accounts:signup") in html

    def test_o_rodape_e_centrado_em_tres_linhas(self, client):
        html = corpo(client)
        rodape = html[html.index('class="site-footer"') :]

        # Marca (h3), a linha de links e o copyright -- o conteúdo padrão
        # do rodapé rico, escrito só com atalhos (ver `content.rodape`).
        assert "<h3" in rodape
        assert "<p" in rodape
        assert "©" in rodape
        # Sem texto legal publicado e sem e-mail cadastrado, os links
        # correspondentes SAEM inteiros -- nunca um link para o nada.
        assert 'href=""' not in rodape
        assert 'href="mailto:"' not in rodape

    def test_a_marca_do_rodape_e_o_nome_do_sistema(self, client):
        nome = SiteSettings.load().site_name
        html = corpo(client)
        rodape = html[html.index('class="site-footer"') :]

        assert nome in rodape

    def test_o_ano_do_copyright_e_do_servidor(self, client):
        import datetime

        html = corpo(client)
        rodape = html[html.index("©") :][:200]

        assert str(datetime.date.today().year) in rodape
