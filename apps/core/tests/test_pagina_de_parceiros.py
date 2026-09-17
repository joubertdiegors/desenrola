"""
A página pública com todos os parceiros.

Ela existe porque a Home mostra no máximo quatro: o "Ver todos" precisa
de um lugar de verdade para levar.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o "Ver todos" vire um link morto.** O destino é uma página que
   responde, com os parceiros que o banco tem;
2. **Que nasça um segundo cadastro de parceiros.** São os MESMOS
   `content.Partner`, na mesma ordem, com o mesmo cartão da Home;
3. **Que a página anuncie uma lista vazia.** Sem parceiro publicado ela
   responde 404, como a seção da Home some;
4. **Que ela precise de login ou de Django Admin.** É pública e sai do
   CMS, como o resto da vitrine;
5. **Que ela fique fora da identidade visual nova.**
"""

import pytest
from django.urls import reverse

from apps.content.models import Partner

pytestmark = pytest.mark.django_db

PARCEIROS = reverse("core:parceiros")
HOME = reverse("core:home")


def criar(quantos, ativos=True):
    for numero in range(1, quantos + 1):
        Partner.objects.create(
            name=f"Parceiro {numero}",
            url=f"https://parceiro{numero}.example.com",
            order=numero,
            is_active=ativos,
        )


def corpo(client, url=PARCEIROS):
    return client.get(url).content.decode()


# ===========================================================================
# 1. A página responde, e com o que o banco tem
# ===========================================================================


class TestAPagina:
    def test_lista_todos_os_parceiros_publicados(self, client):
        criar(7)

        html = corpo(client)

        assert html.count('class="partner-item"') == 7

    def test_a_home_continua_mostrando_so_quatro(self, client):
        """É a diferença entre as duas: uma fileira lá, a lista inteira aqui."""
        criar(7)

        home = client.get(HOME).content.decode()
        inicio = home.index('id="parceiros"')
        secao = home[inicio : home.index("</section>", inicio)]

        assert secao.count('class="partner-item"') == 4
        assert corpo(client).count('class="partner-item"') == 7

    def test_respeita_a_ordem_cadastrada(self, client):
        Partner.objects.create(name="Segundo", order=2, url="https://b.example.com")
        Partner.objects.create(name="Primeiro", order=1, url="https://a.example.com")

        html = corpo(client)

        assert html.index("Primeiro") < html.index("Segundo")

    def test_parceiro_desativado_nao_aparece(self, client):
        criar(2)
        Partner.objects.create(name="Fora do ar", order=9, is_active=False)

        assert "Fora do ar" not in corpo(client)

    def test_sem_parceiro_publicado_responde_404(self, client):
        """Lista vazia anunciada como "nossos parceiros" é pior do que página nenhuma."""
        assert client.get(PARCEIROS).status_code == 404

    def test_e_publica(self, client):
        criar(1)

        assert client.get(PARCEIROS).status_code == 200

    def test_quem_esta_logado_tambem_alcanca(self, auth_client):
        """
        A Home manda quem está logado para o painel; esta página não --
        ela é conteúdo, não porta de entrada.
        """
        criar(1)

        assert auth_client.get(PARCEIROS).status_code == 200


# ===========================================================================
# 2. Os mesmos dados, o mesmo cartão
# ===========================================================================


class TestMesmosDados:
    def test_usa_o_cartao_da_home(self, client):
        criar(2)

        assert corpo(client).count("partner-card") >= 2

    def test_um_parceiro_sem_endereco_nao_vira_link(self, client):
        Partner.objects.create(name="Sem site", order=1, url="")

        html = corpo(client)
        inicio = html.index("partner-card-completo")
        cartao = html[inicio : html.index("</article>", inicio)]

        assert "href=" not in cartao
        assert "partner-card-link" not in cartao

    def test_o_titulo_vem_da_mesma_secao_do_cms(self, client):
        criar(1)

        assert "Nossos parceiros" in corpo(client)


# ===========================================================================
# 3. A casca
# ===========================================================================


class TestACasca:
    def test_veste_a_identidade_publica(self, client):
        criar(1)

        assert 'class="publico"' in corpo(client)

    def test_traz_a_barra_e_o_rodape(self, client):
        criar(1)

        html = corpo(client)
        assert "topo-publico" in html
        assert "site-footer" in html

    def test_o_ver_todos_da_home_aponta_para_ca(self, client):
        criar(6)

        home = client.get(HOME).content.decode()

        assert f'href="{PARCEIROS}"' in home

    def test_nao_ha_link_para_lugar_nenhum(self, client):
        criar(3)

        html = corpo(client)
        assert 'href="#"' not in html
        assert 'href=""' not in html
