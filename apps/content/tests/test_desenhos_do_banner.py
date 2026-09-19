"""
Os três desenhos do Banner superior.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que trocar o desenho apague conteúdo.** O desenho é FORMA; o texto
   é o mesmo `PageSection`. Ir e voltar entre os três tem de devolver
   tudo inteiro -- é o que permite experimentar sem medo;
2. **Que um valor estranho na coluna derrube a Home.** Vazio,
   desconhecido ou inválido cai no desenho padrão, que é o que a página
   sempre teve;
3. **Que "Imagem completa" ponha texto sobre a imagem.** Texto sobre
   foto arbitrária é ilegível na metade dos casos -- este desenho existe
   justamente para quando a imagem fala sozinha;
4. **Que "Somente texto" deixe um buraco onde a imagem estava.** A
   moldura não é escondida com CSS: ela não é desenhada;
5. **Que o desenho padrão deixe de ser o que a Home sempre mostrou.**
"""

import pytest
from django.urls import reverse

from apps.content import section_schema
from apps.content.models import PageSection, PageSectionTranslation

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")

IMAGEM_TEXTO = "imagem_texto"
IMAGEM_COMPLETA = "imagem_completa"
SOMENTE_TEXTO = "somente_texto"


def banner():
    return PageSection.objects.get(page__key="home", key="hero")


def usar(desenho):
    """Troca o desenho do banner -- só o desenho."""
    PageSection.objects.filter(page__key="home", key="hero").update(layout=desenho)


def conteudo():
    return PageSectionTranslation.objects.get(
        section__page__key="home", section__key="hero", language="pt"
    ).content


def corpo(client):
    return client.get(HOME).content.decode()


def area_do_banner(client):
    """
    Só o que a página DESENHA, sem o `<head>`.

    O `<title>` traz `secoes.hero.title` em qualquer desenho -- e é
    certo que traga: a aba precisa de um nome mesmo quando o banner não
    mostra o título. Perguntar "o título aparece?" sobre o documento
    inteiro responderia sempre sim.
    """
    html = corpo(client)
    return html[html.index("<main") : html.index("</main>")]


# ===========================================================================
# 1. O desenho padrão continua sendo o que a Home sempre teve
# ===========================================================================


class TestPadrao:
    def test_a_home_nasce_com_imagem_e_texto(self):
        assert banner().layout == IMAGEM_TEXTO

    def test_o_primeiro_declarado_e_o_padrao(self):
        """A queda é sempre para o primeiro -- e ele é o desenho atual."""
        declarada = section_schema.SECOES["hero"]

        assert declarada.layouts[0].chave == IMAGEM_TEXTO

    def test_desenha_a_marcacao_de_sempre(self, client):
        html = corpo(client)

        for marca in (
            '<section class="hero container">',
            "banner-contador-valor",
            "hero-art",
            "hero-lead",
            "hero-actions",
        ):
            assert marca in html, marca


# ===========================================================================
# 2. O fallback
# ===========================================================================


class TestQuedaSegura:
    @pytest.mark.parametrize("estranho", ["", "inventado", "HERO", "../etc/passwd", "1"])
    def test_valor_estranho_cai_no_padrao(self, estranho):
        alvo = section_schema.template_do_desenho("hero", estranho)

        assert alvo == "core/secoes/banner_imagem_texto.html"

    @pytest.mark.parametrize("estranho", ["", "inventado", "../etc/passwd"])
    def test_a_home_nao_quebra_com_valor_estranho(self, client, estranho):
        usar(estranho)

        resposta = client.get(HOME)

        assert resposta.status_code == 200
        assert '<section class="hero container">' in resposta.content.decode()

    def test_secao_sem_desenho_declarado_nao_resolve_template(self):
        """Só o Banner tem desenhos hoje; as outras não inventam um."""
        assert section_schema.template_do_desenho("how", "") is None


# ===========================================================================
# 3. Imagem completa
# ===========================================================================


class TestImagemCompleta:
    def test_desenha_a_area_de_imagem(self, client):
        usar(IMAGEM_COMPLETA)

        html = corpo(client)

        assert 'class="hero-cheio' in html
        assert "img-slot" in html

    def test_nao_poe_titulo_nem_chamada_sobre_a_imagem(self, client):
        usar(IMAGEM_COMPLETA)

        desenhado = area_do_banner(client)
        titulo = conteudo()["title"]

        assert titulo not in desenhado
        assert "hero-lead" not in desenhado

    def test_desenha_o_contador(self, client):
        """
        O contador continua aparecendo com este desenho -- desde a
        Rodada 21 ele é uma faixa própria ANTES do banner (nunca mais
        sobre a imagem), então nem precisa ser "a única coisa que pode
        sair sobre a foto": não sai nada mais sobre nenhuma foto.
        """
        usar(IMAGEM_COMPLETA)

        assert "banner-contador-valor" in corpo(client)

    def test_o_botao_fica_abaixo_e_so_se_houver(self, client):
        usar(IMAGEM_COMPLETA)

        assert "hero-cheio-acao" in corpo(client)

        traducao = PageSectionTranslation.objects.get(
            section__page__key="home", section__key="hero", language="pt"
        )
        traducao.content = {**traducao.content, "cta": ""}
        traducao.save()

        assert "hero-cheio-acao" not in corpo(client)


# ===========================================================================
# 4. Somente texto
# ===========================================================================


class TestSomenteTexto:
    def test_nao_desenha_imagem_nem_espaco_para_ela(self, client):
        usar(SOMENTE_TEXTO)

        html = corpo(client)

        assert "img-slot" not in html
        assert "hero-art" not in html
        assert "hero-cheio" not in html

    def test_desenha_o_texto(self, client):
        usar(SOMENTE_TEXTO)

        html = corpo(client)
        gravado = conteudo()

        assert gravado["title"] in html
        assert gravado["lead"] in html
        assert gravado["cta"] in html

    def test_usa_a_composicao_propria(self, client):
        usar(SOMENTE_TEXTO)

        assert 'class="hero-texto' in corpo(client)


# ===========================================================================
# 5. Trocar de desenho não apaga nada
# ===========================================================================


class TestTrocarNaoApaga:
    def test_ir_e_voltar_devolve_tudo(self, client):
        """
        A regra central do Passo 4.3: o desenho é FORMA, o conteúdo é o
        mesmo registro.
        """
        antes = conteudo()

        usar(IMAGEM_COMPLETA)
        client.get(HOME)
        usar(SOMENTE_TEXTO)
        client.get(HOME)
        usar(IMAGEM_TEXTO)

        assert conteudo() == antes

    @pytest.mark.parametrize("desenho", [IMAGEM_COMPLETA, SOMENTE_TEXTO])
    def test_o_texto_continua_gravado_no_desenho_que_nao_o_le(self, desenho):
        antes = conteudo()

        usar(desenho)

        gravado = conteudo()
        assert gravado == antes
        assert gravado["title"]
        assert gravado["art_caption"]

    def test_voltar_traz_o_titulo_de_volta_a_pagina(self, client):
        titulo = conteudo()["title"]

        usar(IMAGEM_COMPLETA)
        assert titulo not in area_do_banner(client)

        usar(IMAGEM_TEXTO)
        assert titulo in area_do_banner(client)


# ===========================================================================
# 6. A ativação continua valendo, em qualquer desenho
# ===========================================================================


class TestAtivacao:
    @pytest.mark.parametrize(
        "desenho", [IMAGEM_TEXTO, IMAGEM_COMPLETA, SOMENTE_TEXTO]
    )
    def test_banner_desativado_nao_aparece(self, client, desenho):
        usar(desenho)
        PageSection.objects.filter(page__key="home", key="hero").update(is_active=False)

        html = corpo(client)

        assert "hero container" not in html
        assert "hero-cheio" not in html
        assert "hero-texto" not in html

    def test_desativar_nao_apaga_o_desenho_escolhido(self):
        usar(SOMENTE_TEXTO)
        PageSection.objects.filter(page__key="home", key="hero").update(is_active=False)

        assert banner().layout == SOMENTE_TEXTO


# ===========================================================================
# 7. Os três desenhos estão declarados e têm template
# ===========================================================================


class TestDeclaracao:
    def test_os_tres_continuam_declarados(self):
        """
        A lista CRESCEU: os quatro desenhos da referência visual do
        cliente entraram ao lado destes (ver
        `test_banners_da_referencia`). O que este teste guarda é que
        nenhum dos três originais saiu no caminho -- trocar de desenho
        tem de continuar podendo voltar para qualquer um deles.
        """
        chaves = [layout.chave for layout in section_schema.SECOES["hero"].layouts]

        assert set(chaves) >= {IMAGEM_TEXTO, IMAGEM_COMPLETA, SOMENTE_TEXTO}
        assert len(set(chaves)) == len(chaves)

    def test_cada_desenho_tem_o_seu_template(self):
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        for layout in section_schema.SECOES["hero"].layouts:
            caminho = section_schema.template_do_desenho("hero", layout.chave)
            assert (raiz / "templates" / caminho).exists(), caminho

    def test_cada_desenho_tem_nome_e_explicacao_para_quem_administra(self):
        for layout in section_schema.SECOES["hero"].layouts:
            assert str(layout.nome).strip()
            assert str(layout.descricao).strip()
            # Nada de nome técnico como rótulo.
            assert "hero" not in str(layout.nome).lower()
