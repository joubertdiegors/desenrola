"""
Um olho por campo de senha -- e um só.

O SINTOMA E A CAUSA
-------------------
Na tela de criar conta apareciam DOIS olhos dentro do campo de senha,
mas só depois de começar a digitar. Não havia nada duplicado no DOM: o
segundo era o controle NATIVO de revelar senha que Edge e Chromium
desenham dentro de `input[type=password]` assim que há texto
(`::-ms-reveal`). O do projeto é o outro -- um `<button>` com
`aria-pressed`, rótulo traduzido e alvo de toque.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a correção seja um remendo numa tela só.** A regra é do
   ELEMENTO: vale em cadastro, login, perfil e redefinição, em qualquer
   campo de senha que venha a existir;
2. **Que sobre mais de um controle nosso por campo** -- o erro que
   alguém cometeria "consertando" pela marcação;
3. **Que o controle nativo volte** por uma regra escrita de novo sem o
   `::-ms-reveal`;
4. **Que a acessibilidade do nosso se perca** no caminho: esconder o
   nativo só se justifica porque o nosso é melhor.
"""

import pathlib
import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

COMPONENTS = pathlib.Path("static/css/components.css")

# Toda tela do produto que pede senha, e como chegar nela.
TELAS_COM_SENHA = ["accounts:signup", "accounts:login"]


@pytest.fixture
def logada(db):
    pessoa = get_user_model().objects.create_user(
        email="olho@mail.com", password="senha-longa-123", full_name="Clara Dias"
    )
    c = Client()
    c.force_login(pessoa)
    return c


def campos_de_senha(html):
    return re.findall(r'<input[^>]*type="password"[^>]*>', html)


def botoes_de_olho(html):
    return re.findall(r"data-pw-toggle", html)


# ===========================================================================
# 1. A causa: o controle do navegador está escondido
# ===========================================================================


class TestOControleNativoEstaEscondido:
    def test_a_regra_do_edge_existe(self):
        css = COMPONENTS.read_text(encoding="utf-8")

        assert 'input[type="password"]::-ms-reveal' in css
        assert 'input[type="password"]::-ms-clear' in css

    def test_a_regra_do_webkit_existe(self):
        """Safari e Chrome desenham os botões de preenchimento no mesmo lugar."""
        css = COMPONENTS.read_text(encoding="utf-8")

        assert 'input[type="password"]::-webkit-credentials-auto-fill-button' in css
        assert 'input[type="password"]::-webkit-strong-password-auto-fill-button' in css

    def test_a_regra_e_do_elemento_e_nao_de_uma_tela(self):
        """
        Um seletor preso a `.signup` ou `#id_password1` consertaria uma
        tela e deixaria as outras com dois olhos.
        """
        css = COMPONENTS.read_text(encoding="utf-8")
        onde = css.index("::-ms-reveal")
        linha = css[css.rindex("\n", 0, onde) + 1 : onde]

        assert linha.strip() == 'input[type="password"]'

    def test_o_nativo_some_de_verdade_e_nao_so_fica_transparente(self):
        """
        `opacity: 0` deixaria o clique acontecendo num botão invisível
        sobre o nosso.
        """
        css = COMPONENTS.read_text(encoding="utf-8")
        bloco = css[css.index("::-ms-reveal") : css.index("::-ms-reveal") + 200]

        assert "display: none" in bloco


# ===========================================================================
# 2. Um controle nosso por campo, em toda tela
# ===========================================================================


class TestUmControleNossoPorCampo:
    @pytest.mark.parametrize("rota", TELAS_COM_SENHA)
    def test_cada_campo_tem_exatamente_um_olho(self, client, rota):
        html = client.get(reverse(rota)).content.decode()

        assert len(campos_de_senha(html)) == len(botoes_de_olho(html))

    def test_o_cadastro_tem_dois_campos_e_dois_olhos(self, client):
        """Senha e confirmação: um controle para cada, nunca dois no mesmo."""
        html = client.get(reverse("accounts:signup")).content.decode()

        assert len(campos_de_senha(html)) == 2
        assert len(botoes_de_olho(html)) == 2

    def test_o_perfil_tem_tres_campos_e_tres_olhos(self, logada):
        """Senha atual, nova e confirmação."""
        html = logada.get(reverse("accounts:profile")).content.decode()

        assert len(campos_de_senha(html)) == 3
        assert len(botoes_de_olho(html)) == 3

    def test_nenhum_template_do_projeto_tem_olho_sobrando(self):
        """
        A varredura cobre TODOS os templates, e não só as telas que esta
        suíte abre -- a redefinição de senha, por exemplo, só existe com
        um token válido e ficaria de fora de uma verificação feita por
        requisição.

        A conta é "nunca mais olhos do que campos": um campo sem controle
        nenhum (é o caso da confirmação em `password_reset_confirm.html`,
        tela de um fluxo já homologado e fora desta rodada) não é o
        problema que esta suíte persegue. Dois controles no mesmo campo
        é.
        """
        for caminho in sorted(pathlib.Path("templates").rglob("*.html")):
            texto = caminho.read_text(encoding="utf-8")
            senhas = texto.count('type="password"')
            olhos = texto.count("data-pw-toggle ")
            assert olhos <= senhas, caminho

    def test_com_erro_de_validacao_continua_um_por_campo(self, client):
        """
        O sintoma aparecia DEPOIS de digitar; reexibir o formulário com
        erro é o caminho mais próximo disso no servidor.
        """
        html = client.post(
            reverse("accounts:signup"),
            {"full_name": "Clara", "email": "x@y.com", "password1": "a", "password2": "b"},
        ).content.decode()

        assert len(campos_de_senha(html)) == len(botoes_de_olho(html))

    def test_a_troca_de_senha_com_erro_continua_um_por_campo(self, logada):
        html = logada.post(
            reverse("accounts:profile"),
            {
                "form": "password",
                "old_password": "errada",
                "new_password1": "nova-senha-123",
                "new_password2": "outra-coisa",
            },
        ).content.decode()

        assert len(campos_de_senha(html)) == len(botoes_de_olho(html))


# ===========================================================================
# 3. O nosso continua sendo melhor do que o nativo
# ===========================================================================


class TestONossoEMelhor:
    @pytest.mark.parametrize("rota", TELAS_COM_SENHA)
    def test_todo_olho_diz_o_que_faz_e_em_que_estado_esta(self, client, rota):
        html = client.get(reverse(rota)).content.decode()

        for botao in re.findall(r"<button[^>]*data-pw-toggle[^>]*>", html):
            assert "aria-label=" in botao
            assert 'aria-pressed="false"' in botao

    def test_o_javascript_nao_cria_botao_nenhum(self):
        """
        `app.js` trabalha por DELEGAÇÃO: um ouvinte no documento. Rodar a
        inicialização duas vezes não pode produzir um segundo botão --
        não há nada a produzir.
        """
        js = pathlib.Path("static/js/app.js").read_text(encoding="utf-8")
        trecho = js[js.index("Mostrar/ocultar senha") : js.index("Interruptor")]

        assert "createElement" not in trecho
        assert "insertAdjacent" not in trecho
        assert "innerHTML" not in trecho

    def test_o_alvo_de_toque_do_nosso_botao_e_grande_o_bastante(self):
        css = COMPONENTS.read_text(encoding="utf-8")
        bloco = css[css.index(".pw-toggle {") : css.index(".pw-toggle:hover")]

        assert "width: 40px" in bloco
        assert "height: 40px" in bloco
