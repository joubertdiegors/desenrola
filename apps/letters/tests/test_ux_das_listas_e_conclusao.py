"""
Painel, Minhas cartas e a tela de conclusão, depois da revisão de UX.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o painel vazio ofereça duas portas para a mesma ação.** O
   estado vazio tinha um botão "Gerar Carta Convite" quarenta pixels
   abaixo do cartão de chamada que já oferece o mesmo;
2. **Que o contador volte.** "8 cartas" ao lado do título não dizia
   nada que a lista, logo abaixo, não dissesse melhor;
3. **Que o convite para gerar volte para o alto de Minhas cartas.**
   Aquela tela existe para CONSULTAR: o convite para começar outra vem
   depois da lista;
4. **Que a conclusão volte a encostar na esquerda.** A coluna vazia ao
   lado era o lugar de uma pré-visualização que saiu do projeto;
5. **Que o selo de "pronto" volte a ocupar a primeira tela inteira;**
6. **Que a tela chame "Dashboard" o que o resto do produto chama de
   "Início".**
"""

import datetime
import pathlib
import re

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.letters.models import Letter

pytestmark = pytest.mark.django_db

PAINEL = reverse("core:dashboard")
CARTAS = reverse("letters:history")
NOVA = reverse("letters:new")

LAYOUT = pathlib.Path("static/css/layout.css")


@pytest.fixture
def carta_pronta(user, modelos_oficiais_prontos):
    from apps.letters import services

    carta = services.start_draft(user, "fr")
    carta.data = {
        "guest_name": "Maria Santos da Silva",
        "stay_arrival": (timezone.localdate() + datetime.timedelta(days=30)).isoformat(),
        "stay_departure": (timezone.localdate() + datetime.timedelta(days=44)).isoformat(),
    }
    carta.status = Letter.Status.GENERATED
    carta.finalized_at = timezone.now()
    carta.generated_at = timezone.now()
    carta.save()
    return carta


def regra_do_celular(trecho):
    css = LAYOUT.read_text(encoding="utf-8")
    blocos = re.findall(r"@media \(max-width: 767px\) \{(.*?)\n\}", css, re.S)
    return "\n".join(b for b in blocos if trecho in b)


# ===========================================================================
# 1. O painel vazio
# ===========================================================================


class TestPainelVazio:
    def test_diz_uma_coisa_so(self, auth_client):
        html = auth_client.get(PAINEL).content.decode()

        assert "Você não tem cartas ainda." in html

    def test_ha_UM_convite_para_gerar_na_tela(self, auth_client):
        """
        O cartão de chamada, no alto, já é o convite. Um segundo botão
        quarenta pixels abaixo faz quem chega parar para escolher entre
        dois caminhos iguais.
        """
        html = auth_client.get(PAINEL).content.decode()

        assert html.count(f'href="{NOVA}"') == 1

    def test_o_cartao_de_chamada_continua_no_alto(self, auth_client):
        html = auth_client.get(PAINEL).content.decode()

        assert "hero-cta" in html
        assert html.index("hero-cta") < html.index("letters-vazio")

    def test_o_estado_vazio_perdeu_o_icone_e_o_paragrafo(self, auth_client):
        html = auth_client.get(PAINEL).content.decode()

        assert "letters-empty-icon" not in html
        assert "ela aparece aqui" not in html


# ===========================================================================
# 2. O painel com cartas
# ===========================================================================


class TestPainelComCartas:
    def test_a_lista_aparece(self, auth_client, carta_pronta):
        html = auth_client.get(PAINEL).content.decode()

        assert "Maria Santos da Silva" in html

    def test_o_contador_saiu(self, auth_client, carta_pronta):
        html = auth_client.get(PAINEL).content.decode()
        cabecalho = html[html.index('id="minhas-cartas"') :][:400]

        assert 'class="count"' not in cabecalho

    def test_o_atalho_para_o_historico_continua(self, auth_client, carta_pronta, user):
        """Quem tem mais cartas do que cabe no resumo precisa do caminho."""
        from apps.letters import presentation, services

        for _ in range(presentation.RECENT_LIMIT + 1):
            outra = services.start_draft(user, "fr")
            outra.status = Letter.Status.GENERATED
            outra.finalized_at = timezone.now()
            outra.save()

        html = auth_client.get(PAINEL).content.decode()

        assert CARTAS in html


# ===========================================================================
# 3. Minhas cartas
# ===========================================================================


class TestMinhasCartas:
    def test_nao_ha_contador(self, auth_client, carta_pronta):
        html = auth_client.get(CARTAS).content.decode()

        assert 'class="count"' not in html

    def test_o_convite_para_gerar_vem_DEPOIS_da_lista(self, auth_client, carta_pronta):
        """
        Esta tela existe para consultar. Quem chega aqui vem procurar
        uma carta, não começar outra.
        """
        html = auth_client.get(CARTAS).content.decode()

        assert "letters-nova" in html
        assert html.index("letters-table") < html.index("letters-nova")

    def test_ha_um_so_convite(self, auth_client, carta_pronta):
        html = auth_client.get(CARTAS).content.decode()

        assert html.count(f'href="{NOVA}"') == 1

    def test_o_convite_serve_no_desktop_e_no_celular(self, auth_client, carta_pronta):
        """
        Eram DOIS botões, um `d-only` e outro `m-only`. Agora é um só,
        e o CSS o faz de largura inteira no celular.
        """
        html = auth_client.get(CARTAS).content.decode()
        # SO o bloco do convite: uma janela de N caracteres alcançaria a
        # barra do celular, que é `m-only` por natureza -- e o teste
        # passaria a falhar por causa de outra coisa.
        onde = html.index("letters-nova")
        bloco = html[onde : html.index("</div>", onde)]

        assert "d-only" not in bloco
        assert "m-only" not in bloco
        assert ".letters-nova .btn { width: 100%" in regra_do_celular(".letters-nova")

    def test_sem_carta_nenhuma_o_vazio_COMPLETO_continua(self, auth_client):
        """
        Aqui não há outro botão na tela -- o convite precisa estar em
        algum lugar, e o estado vazio é esse lugar.
        """
        html = auth_client.get(CARTAS).content.decode()

        assert "letters-empty" in html
        assert f'href="{NOVA}"' in html

    def test_a_paginacao_continua_depois_do_convite(self, auth_client, user, carta_pronta):
        from apps.letters import services
        from apps.letters.views import POR_PAGINA

        for _ in range(POR_PAGINA):
            outra = services.start_draft(user, "fr")
            outra.status = Letter.Status.GENERATED
            outra.finalized_at = timezone.now()
            outra.save()

        html = auth_client.get(CARTAS).content.decode()

        assert "bo-paginacao" in html
        assert html.index("letters-nova") < html.index("bo-paginacao")


# ===========================================================================
# 4. A conclusão
# ===========================================================================


class TestConclusao:
    def test_o_cartao_fica_centrado(self):
        """
        Eram duas colunas -- 460px para o cartão e `1fr` para uma
        pré-visualização que saiu do projeto no Bloco L. A coluna vazia
        ficou, e o cartão encostado à esquerda com meia tela em branco.
        """
        css = LAYOUT.read_text(encoding="utf-8")
        inicio = css.index(".done-wrap {")
        bloco = css[inicio : css.index("}", inicio)]

        assert "margin: 0 auto" in bloco
        assert "grid-template-columns" not in bloco

    def test_o_selo_encolheu(self):
        css = LAYOUT.read_text(encoding="utf-8")
        inicio = css.index(".done-icon {")
        bloco = css[inicio : css.index("}", inicio)]
        largura = int(re.search(r"width: (\d+)px", bloco).group(1))

        assert largura <= 64, f"{largura}px -- o selo voltou a crescer"

    def test_no_celular_ele_encolhe_mais_ainda(self):
        """
        Ele era MAIOR no celular (88px contra 84), e empurrava a
        referência e o botão de baixar para fora da primeira tela.
        """
        regra = regra_do_celular(".done-icon")
        largura = int(re.search(r"\.done-icon \{ width: (\d+)px", regra).group(1))

        assert largura <= 52

    def test_o_botao_de_voltar_usa_o_nome_do_produto(self, auth_client, carta_pronta):
        """
        "Dashboard" é palavra de quem constrói. O resto do produto --
        barra superior, barra do celular -- chama aquela tela de
        "Início".
        """
        html = auth_client.get(
            reverse("letters:detail", kwargs={"letter_uuid": carta_pronta.uuid})
        ).content.decode()

        assert "Voltar ao início" in html
        assert ">Dashboard<" not in html

    def test_ele_continua_levando_ao_inicio(self, auth_client, carta_pronta):
        html = auth_client.get(
            reverse("letters:detail", kwargs={"letter_uuid": carta_pronta.uuid})
        ).content.decode()

        assert PAINEL in html

    def test_os_dados_da_carta_continuam_todos(self, auth_client, carta_pronta):
        """O desenho mudou; a informação não."""
        html = auth_client.get(
            reverse("letters:detail", kwargs={"letter_uuid": carta_pronta.uuid})
        ).content.decode()

        assert carta_pronta.reference in html
        assert "Maria Santos da Silva" in html
        assert "Français" in html

    def test_nada_se_mete_entre_a_barra_e_a_confirmacao(self, auth_client, carta_pronta):
        """
        A tela começa pela própria confirmação. O aviso de e-mail não
        confirmado -- que a casca da área logada desenha nas outras
        telas -- não entra aqui: ele ficaria ACIMA da faixa azul,
        empurrando para baixo o que a pessoa acabou de pedir.
        """
        html = auth_client.get(
            reverse("letters:detail", kwargs={"letter_uuid": carta_pronta.uuid})
        ).content.decode()

        assert "aviso-do-email" not in html
        assert 'class="messages"' not in html

    def test_o_aviso_de_email_continua_nas_outras_telas(self, auth_client, carta_pronta):
        """A remoção é DESTA tela, e de mais nenhuma."""
        for rota in (PAINEL, CARTAS):
            assert "aviso-do-email" in auth_client.get(rota).content.decode(), rota
