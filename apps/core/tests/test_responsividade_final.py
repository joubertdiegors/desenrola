"""
As regras de responsividade que a inspeção num navegador de verdade
encontrou -- e que nenhuma medida de overflow denunciaria.

POR QUE ESTE ARQUIVO LÊ CSS
---------------------------
Um teste de HTTP não vê largura de coluna. O que ele PODE guardar é a
regra que a produziu: se alguém voltar a pôr três colunas de cartão num
celular, ou a esconder um botão por CSS, o teste cai e diz por quê. É
uma trava sobre uma decisão tomada olhando a tela, não uma medição.

A CONTA DE 95 PIXELS
--------------------
390px de tela, menos 2×20px de respiro lateral da seção, dividido por
três colunas com 8px de intervalo, menos 2×8px de `padding` do cartão:
sobram 95px de largura útil. É a medida do arquivo de referência "Home
2.0" (2b), que desenha os três passos lado a lado no celular com
cartão compacto: ícone de 30px acima do título e tipografia de 12px.

Antes esta trava guardava o oposto -- uma coluna --, decidido quando o
cartão tinha 10px de respiro e texto de 15,5px, e três colunas deixavam
sete caracteres por linha. O que continua valendo é o motivo da trava:
mexer nessas medidas sem olhar a tela derruba o teste.
"""

import pathlib
import re

import pytest

LAYOUT = pathlib.Path("static/css/layout.css")
CELULAR = r"@media \(max-width: 767px\) \{(.*?)\n\}"


def regras_do_celular(trecho):
    """Os blocos de celular que falam do seletor pedido, juntos."""
    css = LAYOUT.read_text(encoding="utf-8")
    blocos = re.findall(CELULAR, css, re.S)
    return "\n".join(bloco for bloco in blocos if trecho in bloco)


class TestComoFuncionaNoCelular:
    """
    Os três passos ficam lado a lado no celular -- compactos, como a
    referência 2b desenha.
    """

    def test_as_tres_colunas_continuam(self):
        """A grade do desktop vale no celular; o que muda são as medidas."""
        regra = regras_do_celular(".how-grid")

        # O bloco do celular NAO redefine as colunas do "Como funciona":
        # so aperta o intervalo. As tres do desktop seguem valendo.
        assert ".how-grid { grid-template-columns" not in regra
        assert ".how-grid { gap: 8px" in regra

    def test_o_cartao_encolhe_em_vez_de_deitar(self):
        regra = regras_do_celular(".how-card {")

        assert "padding: 14px 8px 16px" in regra
        assert "flex-direction: row" not in regra

    def test_o_icone_sobe_para_cima_do_titulo(self):
        """
        Lado a lado, ícone e título não caberiam em 95px: no celular a
        referência empilha os dois.
        """
        regra = regras_do_celular(".how-card-topo")

        assert "flex-direction: column" in regra

    def test_a_tipografia_encolhe_junto(self):
        regra = regras_do_celular(".how-card-topo b")

        assert "font-size: 12.5px" in regra

    def test_o_texto_tem_um_bloco_proprio(self):
        """Sem ele, a descrição colaria no título."""
        template = pathlib.Path("templates/core/secoes/how.html").read_text(
            encoding="utf-8"
        )

        assert 'class="how-card-texto"' in template
        assert template.index("how-card-numero") < template.index("how-card-texto")


class TestPaginaNaoRolaDeLado:
    """
    O que a inspeção no navegador mediu, guardado como regra.

    Cada item aqui é um lugar onde um elemento sai da caixa de propósito
    -- e o que impede a página de rolar de lado é sempre o recorte do
    pai, nunca a sorte.
    """

    def test_o_mini_banner_nao_tem_nada_fora_da_caixa(self):
        """
        Havia um globo gigante de enfeite, posicionado 30px FORA da
        borda direita -- e só um `overflow: hidden` segurava a página.
        A faixa da referência não tem enfeite nenhum: nada sai da caixa,
        então não há nada para recortar.
        """
        css = LAYOUT.read_text(encoding="utf-8")
        bloco = css[css.index(".home-secao-gradiente {") : css.index(".home-cta-botao")]

        assert "position: absolute" not in bloco
        assert "cta-banner-deco" not in css

    def test_a_foto_que_sangra_e_recortada_pela_secao(self):
        """
        No desenho "Assimétrico" a foto é posicionada fora da grade.
        """
        css = LAYOUT.read_text(encoding="utf-8")
        # A partir da DECLARACAO, e nao da primeira aparicao do nome: a
        # identidade publica ajusta o respiro lateral do desenho mais
        # acima no arquivo, e o recorte mora aqui embaixo.
        inicio = css.index(".hero-assimetrico {")
        bloco = css[inicio : css.index(".hero-assimetrico-grade {", inicio)]

        assert "overflow: hidden;" in bloco

    @pytest.mark.parametrize(
        "seletor", (".table-wrap",)
    )
    def test_a_tabela_larga_continua_contida(self, seletor):
        """
        A trava do Bloco F: sem `contain: paint`, a tabela do editor
        empurrava a página inteira no tablet.
        """
        css = pathlib.Path("static/css/components.css").read_text(encoding="utf-8")
        bloco = css[css.index(seletor) : css.index(seletor) + 200]

        assert "contain: paint" in bloco
