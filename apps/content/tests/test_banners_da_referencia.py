"""
Os quatro desenhos de banner vindos da referência visual do cliente.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o contador vire um número escrito à mão.** A referência
   desenha a etiqueta como "8 cartas geradas". Oito é o número que
   estava no arquivo de desenho, não o do sistema: o que sai na tela
   tem de vir de `letters.statistics.cartas_emitidas()`, e mudar quando
   uma carta é finalizada;
2. **Que um adorno vazio apareça mesmo assim.** Selo, palavra em
   destaque, segundo botão, passos e legenda nascem em branco. Em
   branco, nenhum deles é desenhado -- nem como pílula vazia, nem como
   botão sem texto;
3. **Que o segundo botão não leve a lugar nenhum.** `href="#"` é
   proibido no projeto: o botão secundário aponta para a tela de
   entrar, que existe;
4. **Que trocar de desenho apague texto.** Vale para os sete desenhos,
   não só para os três antigos;
5. **Que a numeração dos passos pule.** Preencher o 1º e o 3º tem de
   numerar "01" e "02" -- a numeração é da ordem do que foi escrito;
6. **Que texto caia sobre foto sem véu.** Só "Foto ampla" põe texto
   sobre a imagem, e só porque desenha a faixa que garante contraste.
"""

import pytest
from django.urls import reverse

from apps.content import section_schema
from apps.content.models import PageSection, PageSectionTranslation
from apps.content.templatetags.conteudo import passos_do_banner
from apps.letters import statistics

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")
LOGIN = reverse("accounts:login")

DESTAQUE = "destaque"
ASSIMETRICO = "assimetrico"
FOTO_AMPLA = "foto_ampla"
EDITORIAL = "editorial"

NOVOS = (DESTAQUE, ASSIMETRICO, FOTO_AMPLA, EDITORIAL)
ANTIGOS = ("imagem_texto", "imagem_completa", "somente_texto")


def usar(desenho):
    PageSection.objects.filter(page__key="home", key="hero").update(layout=desenho)


def escrever(**textos):
    """Acrescenta textos ao conteúdo gravado do banner, em português."""
    traducao = PageSectionTranslation.objects.get(
        section__page__key="home", section__key="hero", language="pt"
    )
    traducao.content = {**traducao.content, **textos}
    traducao.save(update_fields=["content"])
    return traducao


def conteudo():
    return PageSectionTranslation.objects.get(
        section__page__key="home", section__key="hero", language="pt"
    ).content


def area_do_banner(client):
    """
    Só a PRIMEIRA seção do `<main>` -- o Banner.

    Não o `<main>` inteiro: "Como funciona" também numera os passos
    dele (01, 02, 03), e uma busca por ">03<" na página toda acharia
    aquele número em vez deste.
    """
    html = client.get(HOME).content.decode()
    corpo = html[html.index("<main") : html.index("</main>")]
    fim = corpo.find("</section>")
    return corpo if fim == -1 else corpo[: fim + len("</section>")]


# ===========================================================================
# 1. Os quatro existem, e não desalojaram os três antigos
# ===========================================================================


class TestOsSeteDesenhos:
    def test_os_quatro_novos_estao_declarados(self):
        declaradas = {layout.chave for layout in section_schema.SECOES["hero"].layouts}

        assert set(NOVOS) <= declaradas

    def test_os_tres_antigos_continuam(self):
        declaradas = {layout.chave for layout in section_schema.SECOES["hero"].layouts}

        assert set(ANTIGOS) <= declaradas

    def test_o_padrao_nao_mudou(self):
        """O primeiro declarado é o que a Home sempre mostrou."""
        assert section_schema.SECOES["hero"].layouts[0].chave == "imagem_texto"

    @pytest.mark.parametrize("desenho", NOVOS)
    def test_cada_um_tem_template_proprio(self, desenho):
        from django.template.loader import get_template

        declarado = next(
            layout
            for layout in section_schema.SECOES["hero"].layouts
            if layout.chave == desenho
        )

        # Levanta TemplateDoesNotExist se o arquivo não existir.
        get_template(section_schema.template_do_desenho("hero", declarado))

    @pytest.mark.parametrize("desenho", NOVOS)
    def test_a_home_responde_em_cada_um(self, client, desenho):
        usar(desenho)

        assert client.get(HOME).status_code == 200

    def test_cada_desenho_tem_nome_e_descricao_proprios(self):
        """Dois desenhos com o mesmo nome na lista seriam impossíveis de escolher."""
        layouts = section_schema.SECOES["hero"].layouts
        nomes = [str(layout.nome) for layout in layouts]

        assert len(set(nomes)) == len(nomes)


# ===========================================================================
# 2. O contador é o número do sistema -- nunca o do arquivo de desenho
# ===========================================================================


class TestContadorReal:
    """
    A referência escreve "8 cartas geradas". Oito é desenho, não dado.
    """

    @pytest.mark.parametrize("desenho", (DESTAQUE, ASSIMETRICO))
    def test_mostra_a_contagem_do_sistema(self, client, desenho, letter):
        usar(desenho)
        escrever(badge_label="cartas já geradas")
        letter.finalized_at = letter.created_at
        letter.save(update_fields=["finalized_at"])
        statistics.esquecer_a_contagem()

        html = area_do_banner(client)

        assert statistics.cartas_emitidas() == 1
        assert '<span class="banner-contador-valor">1</span>' in html

    @pytest.mark.parametrize("desenho", (DESTAQUE, ASSIMETRICO))
    def test_sem_carta_nenhuma_mostra_zero(self, client, desenho):
        usar(desenho)
        escrever(badge_label="cartas já geradas")
        statistics.esquecer_a_contagem()

        html = area_do_banner(client)

        assert '<span class="banner-contador-valor">0</span>' in html

    @pytest.mark.parametrize("desenho", NOVOS)
    def test_o_numero_do_arquivo_de_desenho_nao_esta_em_lugar_nenhum(
        self, client, desenho
    ):
        """
        "8 cartas" é o texto da referência. Se ele aparecer, alguém
        copiou o desenho junto com o dado.
        """
        usar(desenho)
        escrever(badge_label="cartas já geradas", badge_note="Atualizado em tempo real")

        html = area_do_banner(client)

        assert "8 cartas" not in html

    def test_sem_rotulo_a_etiqueta_do_contador_nao_aparece(self, client):
        """Um número solto, sem dizer o que conta, não informa nada."""
        usar(DESTAQUE)
        escrever(badge_label="")

        html = area_do_banner(client)

        assert "banner-contador-valor" not in html
        assert "banner-contador" not in html


# ===========================================================================
# 3. Adorno em branco não é desenhado
# ===========================================================================


class TestAdornoVazio:
    def test_sem_selo_nao_sai_pilula_vazia(self, client):
        usar(DESTAQUE)
        escrever(kicker="")

        assert "hero-kicker" not in area_do_banner(client)

    def test_com_selo_sai_a_pilula(self, client):
        usar(DESTAQUE)
        escrever(kicker="Feito para quem mora na Bélgica")

        html = area_do_banner(client)

        assert "hero-kicker" in html
        assert "Feito para quem mora na Bélgica" in html

    def test_sem_palavra_em_destaque_o_titulo_sai_inteiro_e_sem_span(self, client):
        usar(DESTAQUE)
        escrever(title="Carta convite pronta", title_realce="")

        html = area_do_banner(client)

        assert "Carta convite pronta" in html
        assert "hero-realce" not in html

    def test_a_palavra_em_destaque_sai_depois_do_titulo(self, client):
        usar(DESTAQUE)
        escrever(title="Carta convite", title_realce="em minutos")

        html = area_do_banner(client)

        assert 'Carta convite <span class="hero-realce">em minutos</span>' in html

    def test_sem_texto_o_botao_secundario_nao_existe(self, client):
        usar(DESTAQUE)
        escrever(cta_secundario="")

        html = area_do_banner(client)

        assert "btn-secondary" not in html

    def test_sem_legenda_a_foto_nao_ganha_figcaption(self, client):
        usar(EDITORIAL)
        escrever(art_legenda="")

        assert "<figcaption>" not in area_do_banner(client)

    def test_com_legenda_a_foto_ganha_figcaption(self, client):
        usar(EDITORIAL)
        escrever(art_legenda="Bruxelas · Antuérpia · Gante")

        html = area_do_banner(client)

        assert "<figcaption>Bruxelas · Antuérpia · Gante</figcaption>" in html


# ===========================================================================
# 4. Nenhum botão leva a lugar nenhum
# ===========================================================================


class TestBotoesComDestino:
    def test_o_botao_secundario_vai_para_entrar(self, client):
        usar(DESTAQUE)
        escrever(cta_secundario="Já tenho conta")

        html = area_do_banner(client)

        assert f'href="{LOGIN}"' in html
        assert "Já tenho conta" in html

    @pytest.mark.parametrize("desenho", NOVOS)
    def test_nenhum_desenho_usa_ancora_morta(self, client, desenho):
        usar(desenho)
        escrever(
            kicker="Selo",
            cta_secundario="Entrar",
            art_legenda="Legenda",
            passo1_title="Passo",
        )

        assert 'href="#"' not in area_do_banner(client)


# ===========================================================================
# 5. Trocar de desenho não apaga texto -- agora com sete
# ===========================================================================


class TestTrocaNaoApaga:
    def test_passar_pelos_sete_devolve_tudo_inteiro(self, client):
        original = dict(conteudo())
        escrever(
            kicker="Selo",
            title_realce="realce",
            cta_secundario="Entrar",
            selo_1="Multi-idioma",
            passo1_title="Preencha",
            art_legenda="Bruxelas",
        )
        depois_de_escrever = dict(conteudo())

        for desenho in (*ANTIGOS, *NOVOS, *ANTIGOS):
            usar(desenho)
            client.get(HOME)

        assert conteudo() == depois_de_escrever
        assert original.items() <= conteudo().items()

    def test_o_texto_principal_ja_chega_escrito_no_desenho_novo(self, client):
        """
        `title`, `lead` e `cta` são os mesmos nomes dos desenhos antigos:
        quem trocar não encontra um banner em branco.
        """
        usar(DESTAQUE)

        html = area_do_banner(client)

        assert conteudo()["title"] in html


# ===========================================================================
# 6. Os passos do "Editorial" numeram o que foi escrito
# ===========================================================================


class TestPassosDoEditorial:
    def test_o_passo_vazio_nao_e_desenhado(self, client):
        usar(EDITORIAL)
        escrever(
            passo1_title="Preencha",
            passo1_text="",
            passo2_title="",
            passo2_text="",
            passo3_title="",
            passo3_text="",
        )

        html = area_do_banner(client)

        assert html.count('class="hero-passo"') == 1

    def test_a_numeracao_nao_pula(self, client):
        """Primeiro e terceiro preenchidos saem como 01 e 02."""
        usar(EDITORIAL)
        escrever(
            passo1_title="Preencha",
            passo2_title="",
            passo2_text="",
            passo3_title="Assine",
        )

        html = area_do_banner(client)

        assert ">01<" in html
        assert ">02<" in html
        assert ">03<" not in html

    def test_os_tres_saem_quando_os_tres_estao_escritos(self, client):
        usar(EDITORIAL)
        escrever(passo1_title="Um", passo2_title="Dois", passo3_title="Três")

        html = area_do_banner(client)

        for numero in (">01<", ">02<", ">03<"):
            assert numero in html

    def test_sem_passo_nenhum_a_lista_sai_vazia_e_nao_quebra(self, client):
        usar(EDITORIAL)

        html = area_do_banner(client)

        assert "hero-passo-numero" not in html
        assert "hero-editorial" in html

    def test_o_filtro_ignora_conteudo_que_nao_e_dicionario(self):
        """Conteúdo estranho no banco não pode derrubar a Home."""
        assert passos_do_banner(None) == []
        assert passos_do_banner("texto solto") == []

    def test_o_filtro_aceita_passo_so_com_titulo(self):
        escritos = passos_do_banner({"passo1_title": "Preencha", "passo1_text": ""})

        assert escritos == [{"title": "Preencha", "text": ""}]

    def test_o_filtro_ignora_espaco_em_branco(self):
        assert passos_do_banner({"passo1_title": "   ", "passo1_text": "  "}) == []


# ===========================================================================
# 7. Texto sobre foto só onde há véu
# ===========================================================================


class TestTextoSobreFoto:
    def test_foto_ampla_desenha_o_veu(self, client):
        usar(FOTO_AMPLA)

        assert "hero-amplo-veu" in area_do_banner(client)

    def test_imagem_completa_continua_sem_titulo_por_cima(self, client):
        """O desenho sem véu continua sem texto -- nada aqui o mudou."""
        usar("imagem_completa")

        html = area_do_banner(client)

        assert "<h1>" not in html

    def test_assimetrico_tem_veu_e_o_texto_fica_fora_da_foto(self, client):
        usar(ASSIMETRICO)

        html = area_do_banner(client)

        assert "hero-assimetrico-veu" in html
        assert html.index("hero-assimetrico-texto") < html.index("hero-assimetrico-art")


# ===========================================================================
# 8. A imagem escolhida vale para os desenhos novos também
# ===========================================================================


class TestImagem:
    @pytest.mark.parametrize("desenho", NOVOS)
    def test_sem_imagem_sai_a_moldura_vazia(self, client, desenho):
        usar(desenho)

        assert "img-slot" in area_do_banner(client)

    @pytest.mark.parametrize("desenho", NOVOS)
    def test_a_moldura_vazia_nao_e_lida_por_leitor_de_tela(self, client, desenho):
        usar(desenho)

        html = area_do_banner(client)

        assert '<div class="img-slot" aria-hidden="true">' in html
