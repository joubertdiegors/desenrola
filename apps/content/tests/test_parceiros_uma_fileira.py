"""
Bloco B: só imagem e botão, carrossel acima de quatro, "Ver todos".

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que uma segunda fileira nasça.** Acima de quatro parceiros, o
   requisito é claro: carrossel horizontal, nunca mais uma fileira --
   com o carrossel desligado, a composição CONTINUA travada em quatro,
   e o resto só existe atrás do carrossel ou do "Ver todos";
2. **Que a posição do botão vire coordenada livre.** Só as nove de
   `PageSection.Posicao9` -- a MESMA classe do contador do banner;
3. **Que o carrossel dependa só do arraste do mouse.** A trilha é
   focável (teclado) e rola por toque/roda do mouse por CSS puro, antes
   de qualquer script;
4. **Que "Ver todos" apareça sem destino, ou com poucos parceiros.** Só
   surge com mais de quatro, o interruptor ligado E um destino real
   escrito na seção;
5. **Que a animação do carrossel ignore `prefers-reduced-motion`;**
6. **Que a prévia do Backoffice desenhe uma composição diferente da
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
        "parceiros_posicao_botao": secao().partners_button_position,
        "parceiros_carrossel_ativo": "on",
        "parceiros_carrossel_controles_ativo": "on",
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

    def test_um_parceiro_grade_sem_carrossel(self, client):
        criar(1)

        html = secao_dos_parceiros(client)

        assert "partners-grid" in html
        assert "partners-carrossel" not in html

    def test_quatro_parceiros_grade_sem_carrossel(self, client):
        criar(4)

        html = secao_dos_parceiros(client)

        assert 'class="partners-grid"' in html
        assert "partners-carrossel" not in html

    def test_cinco_parceiros_vira_carrossel(self, client):
        criar(5)

        html = secao_dos_parceiros(client)

        assert "partners-carrossel" in html

    def test_muitos_parceiros_continuam_todos_no_carrossel(self, client):
        criar(12)

        html = secao_dos_parceiros(client)

        assert html.count("partner-item") == 12


# ===========================================================================
# 2. Nunca uma segunda fileira
# ===========================================================================


class TestSemSegundaFileira:
    def test_carrossel_ligado_a_grade_nao_e_desenhada(self, client):
        criar(6)

        html = secao_dos_parceiros(client)

        assert "partners-grid" not in html

    def test_carrossel_desligado_trava_em_quatro(self, client):
        criar(9)
        PageSection.objects.filter(pk=secao().pk).update(partners_carousel_enabled=False)

        html = secao_dos_parceiros(client)

        assert html.count("partner-item") == 4
        assert 'class="partners-grid"' in html
        assert "partners-carrossel" not in html

    def test_carrossel_desligado_mostra_o_ver_todos(self, client):
        criar(9)
        PageSection.objects.filter(pk=secao().pk).update(partners_carousel_enabled=False)
        escrever(ver_todos_label="Ver todos os parceiros", ver_todos_destino="/parceiros/")

        assert "parceiros-rodape" in secao_dos_parceiros(client)


# ===========================================================================
# 3. O botão -- as nove posições fechadas
# ===========================================================================


class TestPosicaoDoBotao:
    def test_o_padrao_e_inferior_centro(self, client):
        assert secao().partners_button_position == "inferior-centro"
        criar(1)

        assert "pos-inferior-centro" in secao_dos_parceiros(client)

    @pytest.mark.parametrize("posicao", POSICOES)
    def test_cada_uma_das_nove_aparece_no_botao(self, client, posicao):
        criar(1)
        PageSection.objects.filter(pk=secao().pk).update(partners_button_position=posicao)

        html = secao_dos_parceiros(client)

        assert f'partner-botao btn btn-primary pos-{posicao}"' in html

    @pytest.mark.parametrize("posicao", POSICOES)
    def test_o_backoffice_grava_a_posicao_escolhida(self, cliente, posicao):
        cliente.post(url_do_editor(), _payload_do_editor(parceiros_posicao_botao=posicao))

        assert secao().partners_button_position == posicao

    def test_valor_fora_do_conjunto_e_recusado(self, cliente):
        cliente.post(
            url_do_editor(),
            _payload_do_editor(parceiros_posicao_botao="direita-solta-33px"),
        )

        assert secao().partners_button_position != "direita-solta-33px"

    def test_a_mesma_classe_do_contador_do_banner(self):
        """
        Uma segunda tabela de posições seria exatamente a duplicação que
        o projeto proíbe -- a classe `.pos-<posição>` isolada (a que o
        botão do parceiro usa) só é DEFINIDA uma vez; o mobile do
        contador só a referencia, combinada com `.banner-contador`.
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
    def test_aparece_com_mais_de_quatro_e_destino_configurado(self, client):
        criar(5)
        escrever(ver_todos_label="Ver todos os parceiros", ver_todos_destino="/parceiros/")

        html = secao_dos_parceiros(client)

        assert "parceiros-rodape" in html
        assert "Ver todos os parceiros" in html
        assert 'href="/parceiros/"' in html

    def test_sem_destino_nao_aparece_mesmo_com_rotulo(self, client):
        criar(5)
        escrever(ver_todos_label="Ver todos os parceiros", ver_todos_destino="")

        assert "parceiros-rodape" not in secao_dos_parceiros(client)

    def test_desligado_no_backoffice_nao_aparece(self, client):
        criar(5)
        escrever(ver_todos_label="Ver todos", ver_todos_destino="/parceiros/")
        PageSection.objects.filter(pk=secao().pk).update(partners_view_all_enabled=False)

        assert "parceiros-rodape" not in secao_dos_parceiros(client)

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

        assert "partners-carrossel" not in html
        assert html.count("partner-item") == 4

    def test_parceiro_sem_imagem_mostra_a_moldura_vazia(self, client):
        criar(1)

        html = secao_dos_parceiros(client)

        assert "img-slot" in html
        assert "partner-botao" in html


# ===========================================================================
# 6. Controles do carrossel -- setas e configuração
# ===========================================================================


class TestControlesDoCarrossel:
    def test_setas_aparecem_por_padrao(self, client):
        criar(6)

        assert "partners-seta" in secao_dos_parceiros(client)

    def test_setas_desligadas_no_backoffice_somem(self, client):
        criar(6)
        PageSection.objects.filter(pk=secao().pk).update(
            partners_carousel_controls_enabled=False
        )

        assert "partners-seta" not in secao_dos_parceiros(client)

    def test_a_trilha_e_focavel_pelo_teclado(self, client):
        """Sem isso, quem navega só pelo teclado não alcança o resto."""
        criar(6)

        html = secao_dos_parceiros(client)

        assert 'id="parceiros-trilho"' in html
        assert 'tabindex="0"' in html

    def test_o_backoffice_liga_e_desliga_o_carrossel(self, cliente):
        criar(9)

        cliente.post(url_do_editor(), _payload_do_editor(parceiros_carrossel_ativo=""))
        assert secao().partners_carousel_enabled is False

        cliente.post(url_do_editor(), _payload_do_editor(parceiros_carrossel_ativo="on"))
        assert secao().partners_carousel_enabled is True

    def test_o_backoffice_liga_e_desliga_as_setas(self, cliente):
        cliente.post(
            url_do_editor(), _payload_do_editor(parceiros_carrossel_controles_ativo="")
        )
        assert secao().partners_carousel_controls_enabled is False

        cliente.post(
            url_do_editor(), _payload_do_editor(parceiros_carrossel_controles_ativo="on")
        )
        assert secao().partners_carousel_controls_enabled is True


# ===========================================================================
# 7. Sem overflow horizontal -- o scroll fica preso à trilha
# ===========================================================================


class TestSemOverflowHorizontal:
    def test_a_trilha_contem_o_proprio_scroll(self):
        raiz = pathlib.Path(__file__).resolve().parents[3]
        css = (raiz / "static" / "css" / "layout.css").read_text(encoding="utf-8")
        inicio = css.index("overflow-x: auto;")
        regra = css[inicio : css.index("}", inicio)]

        # Sem `min-width: 0`, um item flexivel recusa encolher e a
        # pagina toda -- nao so a trilha -- e' que ganharia a barra
        # horizontal.
        assert "min-width: 0" in regra

    def test_respeita_movimento_reduzido(self):
        raiz = pathlib.Path(__file__).resolve().parents[3]
        css = (raiz / "static" / "css" / "layout.css").read_text(encoding="utf-8")

        assert "prefers-reduced-motion: reduce" in css
        indice = css.index("prefers-reduced-motion: reduce")
        bloco = css[indice : indice + 200]
        assert ".partners-carrossel" in bloco

    def test_o_script_respeita_o_mesmo_ajuste_no_clique(self):
        raiz = pathlib.Path(__file__).resolve().parents[3]
        script = (raiz / "static" / "js" / "carrossel-de-parceiros.js").read_text(
            encoding="utf-8"
        )

        assert "prefers-reduced-motion" in script

    def test_o_script_nao_monta_html(self):
        raiz = pathlib.Path(__file__).resolve().parents[3]
        script = (raiz / "static" / "js" / "carrossel-de-parceiros.js").read_text(
            encoding="utf-8"
        )

        assert "innerHTML" not in script
        assert "createElement" not in script


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
    def test_a_previa_mostra_o_carrossel_com_cinco(self, cliente):
        criar(5)

        html = cliente.get(url_da_previa()).content.decode()

        assert "partners-carrossel" in html

    def test_a_previa_mostra_a_grade_com_quatro(self, cliente):
        criar(4)

        html = cliente.get(url_da_previa()).content.decode()

        assert 'class="partners-grid"' in html

    def test_a_previa_reflete_a_posicao_ainda_nao_salva(self, cliente):
        criar(1)

        html = cliente.post(
            url_da_previa(),
            _payload_do_editor(parceiros_posicao_botao="superior-direita"),
        ).content.decode()

        assert 'pos-superior-direita"' in html
        assert secao().partners_button_position != "superior-direita"

    def test_a_previa_reflete_o_carrossel_desligado_sem_salvar(self, cliente):
        criar(9)

        html = cliente.post(
            url_da_previa(), _payload_do_editor(parceiros_carrossel_ativo="")
        ).content.decode()

        assert "partners-carrossel" not in html
        assert secao().partners_carousel_enabled is True

    def test_previa_e_salvamento_desenham_a_mesma_composicao(self, cliente):
        criar(6)
        dados = _payload_do_editor(parceiros_posicao_botao="centro")

        da_previa = cliente.post(url_da_previa(), dados).content.decode()
        cliente.post(url_do_editor(), dados)

        assert 'pos-centro"' in da_previa
        assert secao().partners_button_position == "centro"
