"""
Nossos Parceiros: uma fileira de quatro, o botão do cartão e o "Ver todos".

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que uma segunda fileira nasça.** A referência visual desenha UMA
   linha: acima de quatro parceiros a Home mostra os quatro primeiros e
   o "Ver todos" leva à página com todos eles;
2. **Que o carrossel volte.** Ele rolava de lado e mostrava os demais
   ali mesmo -- a referência não o tem, e a página de parceiros faz o
   papel dele;
3. **Que a posição do botão vire coordenada livre.** Só as nove de
   `PageSection.Posicao9` -- a MESMA classe do contador do banner;
4. **Que "Ver todos" vire um link morto.** O destino padrão é a página
   de parceiros, que existe; o CMS pode trocá-lo, mas não precisa
   preenchê-lo;
5. **Que a prévia do Backoffice desenhe uma composição diferente da
   Home pública.**
"""

import pathlib

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.content.models import PageSection, PageSectionTranslation, Partner

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")

POSICOES = (
    "superior-esquerda",
    "superior-centro",
    "superior-direita",
    "centro-esquerda",
    "centro",
    "centro-direita",
    "inferior-esquerda",
    "inferior-centro",
    "inferior-direita",
)


def secao():
    return PageSection.objects.get(page__key="home", key="partners")


def traducao():
    return PageSectionTranslation.objects.get(
        section__page__key="home", section__key="partners", language="pt"
    )


def escrever(**textos):
    t = traducao()
    t.content = {**t.content, **textos}
    t.save(update_fields=["content"])
    return t


def criar(quantos, com_url=True):
    for numero in range(1, quantos + 1):
        Partner.objects.create(
            name=f"Parceiro {numero}",
            url=f"https://parceiro{numero}.example.com" if com_url else "",
            order=numero,
        )


def corpo(client):
    html = client.get(HOME).content.decode()
    return html[html.index("<main") : html.index("</main>")]


def secao_dos_parceiros(client):
    html = corpo(client)
    if 'id="parceiros"' not in html:
        return ""
    inicio = html.index('id="parceiros"')
    return html[inicio : html.index("</section>", inicio)]


def url_da_previa():
    return reverse("backoffice:content_preview", args=[secao().pk])


def url_do_editor():
    return reverse("backoffice:content_section", args=[secao().pk])


def _pessoa(email, *permissoes):
    pessoa = get_user_model().objects.create_user(
        email=email, password="x", full_name="Clara Dias"
    )
    for app_label, codename in permissoes:
        pessoa.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return get_user_model().objects.get(pk=pessoa.pk)


@pytest.fixture
def editora(db):
    return _pessoa(
        "editora-parceiros@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_pagesection"),
        ("content", "change_pagesection"),
    )


@pytest.fixture
def leitora(db):
    return _pessoa(
        "leitora-parceiros@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_pagesection"),
    )


@pytest.fixture
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


def _payload_do_editor(**extra):
    """Um POST completo -- mesma convenção de `test_contador_do_banner.py`."""
    base = {
        "idioma": "pt",
        **traducao().content,
        "parceiros_ver_todos_ativo": "on",
    }
    base.update(extra)
    return base


# ===========================================================================
# 1. Quantidade -- 0, 1, 4, 5 e muitos
# ===========================================================================


class TestQuantidades:
    def test_zero_parceiros_a_secao_some(self, client):
        assert 'id="parceiros"' not in corpo(client)

    @pytest.mark.parametrize("quantos", [1, 2, 3, 4])
    def test_ate_quatro_aparecem_todos(self, client, quantos):
        criar(quantos)

        html = secao_dos_parceiros(client)

        assert "partners-grid" in html
        assert html.count("partner-item") == quantos

    @pytest.mark.parametrize("quantos", [5, 9, 12])
    def test_acima_de_quatro_a_home_mostra_quatro(self, client, quantos):
        criar(quantos)

        html = secao_dos_parceiros(client)

        assert html.count("partner-item") == 4

    def test_os_quatro_sao_os_PRIMEIROS_da_ordem(self, client):
        criar(6)

        html = secao_dos_parceiros(client)

        assert "Parceiro 1" in html
        assert "Parceiro 5" not in html


# ===========================================================================
# 2. Nunca uma segunda fileira, nunca um carrossel
# ===========================================================================


class TestUmaFileiraSo:
    @pytest.mark.parametrize("quantos", [5, 9, 12])
    def test_a_grade_continua_sendo_uma_grade_de_quatro(self, client, quantos):
        criar(quantos)

        html = secao_dos_parceiros(client)

        assert 'class="partners-grid"' in html
        assert html.count("partner-item") == 4

    def test_nao_ha_carrossel_nem_barra_de_rolagem(self, client):
        criar(12)

        html = secao_dos_parceiros(client)

        assert "carrossel" not in html
        assert "overflow" not in html

    def test_acima_de_quatro_o_ver_todos_leva_a_pagina_de_parceiros(self, client):
        criar(9)

        html = secao_dos_parceiros(client)

        assert reverse("core:parceiros") in html


# ===========================================================================
# 3. O cartão da Home é só a imagem
# ===========================================================================


class TestCartaoSoImagem:
    """
    O cartão da Home é um bloco 4:3 com a imagem e uma cápsula num
    canto -- o desenho do arquivo "Home 2.0". Nome e descrição
    continuam só na PÁGINA de parceiros, para onde o "Ver todos" leva.
    """

    def test_o_botao_aparece_sobre_o_cartao(self, client):
        criar(2)

        html = secao_dos_parceiros(client)

        assert "partner-botao" in html
        assert "pos-inferior-centro" in html

    def test_o_botao_e_um_span_e_nao_uma_segunda_ancora(self, client):
        """
        O cartão INTEIRO já é o link: uma âncora dentro de outra não
        existe em HTML, e um `href="#"` para disfarçar seria um botão
        que não leva a lugar nenhum.
        """
        criar(1)

        html = secao_dos_parceiros(client)

        assert '<span class="partner-botao' in html
        assert 'href="#"' not in html

    def test_sem_texto_no_cms_o_botao_nao_existe(self, client):
        criar(1)
        escrever(cta="")

        assert "partner-botao" not in secao_dos_parceiros(client)

    def test_o_texto_do_botao_vem_do_cms(self, client):
        criar(1)
        escrever(cta="Ver parceiro")

        assert "Ver parceiro" in secao_dos_parceiros(client)

    def test_o_cartao_inteiro_e_o_link_com_o_nome_no_aria_label(self, client):
        criar(1)

        html = secao_dos_parceiros(client)

        assert 'class="partner-card" href="https://parceiro1.example.com"' in html
        assert 'aria-label="Parceiro 1"' in html

    def test_o_backoffice_oferece_a_posicao_do_botao(self, cliente):
        """
        O botão voltou ao cartão, e com ele o controle: a coluna
        `partners_button_position` nunca saiu do modelo, então o que
        estava gravado continua valendo.
        """
        corpo = cliente.get(url_do_editor()).content.decode()

        assert 'name="parceiros_posicao_botao"' in corpo

    def test_a_mesma_classe_do_contador_do_banner(self):
        """
        As nove posições continuam definidas UMA vez -- o contador do
        banner e o botão do cartão usam as mesmas. O afastamento da
        borda é um parâmetro (`--pos-respiro`), não uma segunda tabela:
        o cartão é pequeno e pede 8px onde a faixa pede 24px.
        """
        import re

        raiz = pathlib.Path(__file__).resolve().parents[3]
        css = (raiz / "static" / "css" / "layout.css").read_text(encoding="utf-8")

        for posicao in POSICOES:
            isolada = re.findall(rf"(?<![\w-])\.pos-{posicao} \{{", css)
            assert len(isolada) == 1, posicao


# ===========================================================================
# 4. "Ver todos"
# ===========================================================================


class TestVerTodos:
    def test_aparece_com_mais_de_quatro(self, client):
        criar(5)

        html = secao_dos_parceiros(client)

        assert "home-link-forte" in html
        assert reverse("core:parceiros") in html

    def test_nao_aparece_com_quatro_ou_menos(self, client):
        criar(4)

        assert "home-link-forte" not in secao_dos_parceiros(client)

    def test_sem_destino_escrito_ele_vai_para_a_pagina_de_parceiros(self, client):
        """
        O botão não depende mais de um destino digitado: a página de
        parceiros existe, e é para lá que ele vai por padrão.
        """
        criar(5)
        escrever(ver_todos_label="", ver_todos_destino="")

        html = secao_dos_parceiros(client)

        assert reverse("core:parceiros") in html
        assert "Ver todos" in html

    def test_o_cms_pode_trocar_o_texto_e_o_destino(self, client):
        criar(5)
        escrever(ver_todos_label="Conheça todos", ver_todos_destino="/outro-lugar/")

        html = secao_dos_parceiros(client)

        assert "Conheça todos" in html
        assert 'href="/outro-lugar/"' in html

    def test_desligado_no_backoffice_nao_aparece(self, client):
        criar(5)
        PageSection.objects.filter(pk=secao().pk).update(partners_view_all_enabled=False)

        assert "home-link-forte" not in secao_dos_parceiros(client)

    def test_o_backoffice_liga_e_desliga(self, cliente):
        escrever(ver_todos_label="Ver todos", ver_todos_destino="/parceiros/")

        cliente.post(url_do_editor(), _payload_do_editor(parceiros_ver_todos_ativo=""))
        assert secao().partners_view_all_enabled is False

        cliente.post(url_do_editor(), _payload_do_editor(parceiros_ver_todos_ativo="on"))
        assert secao().partners_view_all_enabled is True

    def test_nunca_uma_ancora_para_dentro_da_propria_secao(self, cliente):
        """
        Um "Ver todos" apontando de volta para "#parceiros" seria
        circular -- por isso o destino usa um validador sem âncora.
        """
        resposta = cliente.post(
            url_do_editor(), _payload_do_editor(ver_todos_destino="#parceiros")
        )

        assert resposta.status_code == 200
        assert traducao().content.get("ver_todos_destino") != "#parceiros"


# ===========================================================================
# 5. Parceiro inativo e sem imagem
# ===========================================================================


class TestCasosDoParceiro:
    def test_parceiro_inativo_nao_conta_para_o_total(self, client):
        criar(5)
        Partner.objects.filter(name="Parceiro 5").update(is_active=False)

        html = secao_dos_parceiros(client)

        assert html.count("partner-item") == 4
        assert "Parceiro 5" not in html

    def test_parceiro_sem_imagem_mostra_a_moldura_vazia(self, client):
        criar(1)

        html = secao_dos_parceiros(client)

        assert "img-slot" in html


# ===========================================================================
# 8. Permissão -- a mesma tela de qualquer outra seção
# ===========================================================================


class TestPermissao:
    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(url_do_editor())

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_quem_so_ve_nao_pode_gravar(self, leitora):
        c = Client()
        c.force_login(leitora)

        resposta = c.post(url_do_editor(), _payload_do_editor(title="Outro título"))

        assert resposta.status_code == 403


# ===========================================================================
# 9. A prévia usa a mesma composição da Home
# ===========================================================================


class TestPrevia:
    def test_a_previa_para_em_quatro_como_a_home(self, cliente):
        criar(9)

        html = cliente.get(url_da_previa()).content.decode()

        assert html.count("partner-item") == 4
        assert "carrossel" not in html

    def test_a_previa_mostra_a_grade_com_quatro(self, cliente):
        criar(4)

        html = cliente.get(url_da_previa()).content.decode()

        assert 'class="partners-grid"' in html

    def test_a_previa_reflete_o_titulo_ainda_nao_salvo(self, cliente):
        criar(1)

        html = cliente.post(
            url_da_previa(), _payload_do_editor(title="Título só da prévia")
        ).content.decode()

        assert "Título só da prévia" in html
        assert traducao().content.get("title") != "Título só da prévia"

    def test_a_previa_reflete_o_ver_todos_desligado_sem_salvar(self, cliente):
        criar(9)

        html = cliente.post(
            url_da_previa(), _payload_do_editor(parceiros_ver_todos_ativo="")
        ).content.decode()

        assert "home-link-forte" not in html
        assert secao().partners_view_all_enabled is True

    def test_previa_e_salvamento_desenham_a_mesma_composicao(self, cliente):
        criar(6)
        dados = _payload_do_editor(title="Parceiros de confiança")

        da_previa = cliente.post(url_da_previa(), dados).content.decode()
        cliente.post(url_do_editor(), dados)

        assert "Parceiros de confiança" in da_previa
        assert traducao().content.get("title") == "Parceiros de confiança"
