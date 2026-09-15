"""
A pré-visualização no editor de uma parte da Home.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a prévia grave.** Ela mostra o que está DIGITADO; a página
   pública só muda quando alguém salva. Uma prévia que persiste é uma
   publicação acidental;
2. **Que o navegador escolha template.** Ele manda, no máximo, o
   desenho e a largura -- os dois passam por lista fechada. Nenhum
   caminho de arquivo atravessa;
3. **Que "responsivo" vire desenho encolhido.** Os três modos estreitam
   o quadro; dentro de um `<iframe>` a largura do elemento é a largura
   de referência das media queries, então o CSS responde de verdade;
4. **Que a prévia vire rota pública.** Ela desenha conteúdo
   administrativo, inclusive de parte desativada;
5. **Que a prévia e o salvamento discordem.** Os dois montam o conteúdo
   com o MESMO método -- montagens diferentes fariam a prévia mentir;
6. **Que apareça botão sem função.** Sem JavaScript os controles de
   largura não são desenhados.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.content.backoffice_views import PADRAO_DO_VIEWPORT, VIEWPORTS
from apps.content.models import PageSection, PageSectionTranslation

pytestmark = pytest.mark.django_db


def secao(chave="hero"):
    return PageSection.objects.get(page__key="home", key=chave)


def traducao(chave="hero"):
    return PageSectionTranslation.objects.get(section=secao(chave), language="pt")


def url_da_previa(chave="hero"):
    return reverse("backoffice:content_preview", args=[secao(chave).pk])


def url_do_editor(chave="hero"):
    return reverse("backoffice:content_section", args=[secao(chave).pk])


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
        "editora@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_pagesection"),
        ("content", "change_pagesection"),
    )


@pytest.fixture
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


# ===========================================================================
# 1. A porta
# ===========================================================================


class TestAcesso:
    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(url_da_previa())

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_usuario_comum_e_recusado(self, auth_client):
        assert auth_client.get(url_da_previa()).status_code == 403

    def test_backoffice_sozinho_nao_basta(self, client, staff_user):
        client.force_login(staff_user)

        assert client.get(url_da_previa()).status_code == 403

    def test_quem_pode_ver_o_conteudo_ve_a_previa(self, client, db):
        leitora = _pessoa(
            "leitora@mail.com",
            ("core", "access_backoffice"),
            ("content", "view_pagesection"),
        )
        client.force_login(leitora)

        assert client.get(url_da_previa()).status_code == 200

    def test_o_post_tambem_exige_permissao(self, auth_client):
        """Desenhar o não salvo é a mesma pergunta, pelo outro verbo."""
        assert auth_client.post(url_da_previa(), {"title": "x"}).status_code == 403

    def test_sem_csrf_o_post_e_recusado(self, editora):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(editora)

        assert sem_token.post(url_da_previa(), {"title": "x"}).status_code == 403


# ===========================================================================
# 2. A prévia NÃO grava
# ===========================================================================


class TestNaoGrava:
    def test_o_texto_digitado_aparece_sem_ser_salvo(self, cliente):
        antes = dict(traducao().content)

        corpo = cliente.post(
            url_da_previa(), {**antes, "title": "Ainda não salvo"}
        ).content.decode()

        assert "Ainda não salvo" in corpo
        assert traducao().content == antes

    def test_o_desenho_proposto_aparece_sem_ser_salvo(self, cliente):
        corpo = cliente.post(
            url_da_previa(), {**traducao().content, "layout": "somente_texto"}
        ).content.decode()

        assert "hero-texto" in corpo
        assert secao().layout == "imagem_texto"

    def test_a_home_publica_nao_muda(self, cliente, client):
        cliente.post(url_da_previa(), {**traducao().content, "title": "Ainda não salvo"})

        corpo = client.get(reverse("core:home")).content.decode()

        assert "Ainda não salvo" not in corpo

    def test_formulario_invalido_nao_derruba_a_previa(self, cliente):
        """Quem valida é a tela de edição; a prévia continua desenhando."""
        resposta = cliente.post(url_da_previa(), {"title": "x" * 20000})

        assert resposta.status_code == 200
        assert 'class="hero container"' in resposta.content.decode()


# ===========================================================================
# 3. É a Home real
# ===========================================================================


class TestRenderizacaoReal:
    def test_usa_o_css_do_site(self, cliente):
        corpo = cliente.get(url_da_previa()).content.decode()

        for folha in ("css/base.css", "css/components.css", "css/layout.css"):
            assert folha in corpo

    @pytest.mark.parametrize(
        ("chave", "marca"),
        [
            ("navbar", "nav-desktop"),
            ("hero", 'class="hero container"'),
            ("trust", "trust-bar"),
            ("how", "how-grid"),
            ("cta", "cta-banner"),
            ("footer", "site-footer"),
        ],
    )
    def test_desenha_o_parcial_da_parte(self, cliente, chave, marca):
        assert marca in cliente.get(url_da_previa(chave)).content.decode()

    def test_a_previa_e_o_salvamento_montam_o_mesmo_conteudo(self, cliente):
        """
        Se as duas montagens divergirem, a prévia mente. Salvar o MESMO
        formulário tem de produzir o que a prévia mostrou.
        """
        dados = {**traducao().content, "title": "Mesmo texto nos dois"}

        da_previa = cliente.post(url_da_previa(), dados).content.decode()
        cliente.post(url_do_editor(), {**dados, "idioma": "pt"})

        assert "Mesmo texto nos dois" in da_previa
        assert traducao().content["title"] == "Mesmo texto nos dois"

    def test_desenha_parte_desativada(self, cliente):
        PageSection.objects.filter(page__key="home", key="cta").update(is_active=False)

        assert "cta-banner" in cliente.get(url_da_previa("cta")).content.decode()


# ===========================================================================
# 4. Desktop / Tablet / Celular
# ===========================================================================


class TestViewports:
    def test_os_tres_estao_declarados(self):
        for nome in ("desktop", "tablet", "mobile"):
            assert nome in VIEWPORTS

    def test_as_larguras_caem_dos_dois_lados_da_media_query(self):
        """
        O CSS do projeto corta em 767px. Se os três ficassem do mesmo
        lado, trocar de aparelho não mostraria diferença nenhuma.
        """
        assert VIEWPORTS["desktop"] > 767
        assert VIEWPORTS["tablet"] > 767
        assert VIEWPORTS["mobile"] < 767

    @pytest.mark.parametrize("nome", ["desktop", "tablet", "mobile"])
    def test_cada_um_responde(self, cliente, nome):
        resposta = cliente.get(f"{url_da_previa()}?viewport={nome}")

        assert resposta.status_code == 200
        assert f'data-viewport="{nome}"' in resposta.content.decode()

    @pytest.mark.parametrize("nome", ["desktop", "tablet", "mobile"])
    def test_o_aparelho_nao_forca_largura_de_referencia(self, cliente, nome):
        """
        A largura tem de vir do QUADRO, não de um `<meta>` fixo -- senão
        o CSS responderia sempre à mesma largura e a simulação seria
        desenho encolhido.
        """
        corpo = cliente.get(f"{url_da_previa()}?viewport={nome}").content.decode()

        assert "width=1280" not in corpo
        assert "width=device-width" in corpo

    def test_so_a_miniatura_forca_a_largura(self, cliente):
        """
        A miniatura é o caso oposto: quadro de 220px mostrando o desenho
        de desktop.
        """
        corpo = cliente.get(f"{url_da_previa()}?viewport=miniatura").content.decode()

        assert "width=1280" in corpo

    def test_o_editor_oferece_os_tres(self, cliente):
        corpo = cliente.get(url_do_editor()).content.decode()

        for rotulo in ("Desktop", "Tablet", "Celular"):
            assert f">{rotulo}<" in corpo

    def test_o_palco_leva_o_aparelho_escolhido(self, cliente):
        corpo = cliente.get(url_do_editor()).content.decode()

        assert 'class="bo-previa-palco" data-viewport="desktop"' in corpo


# ===========================================================================
# 5. Nada arbitrário vindo do navegador
# ===========================================================================


class TestNadaArbitrario:
    @pytest.mark.parametrize(
        "lixo",
        ["", "inventado", "../../etc/passwd", "backoffice/base.html", "MOBILE", "1280"],
    )
    def test_largura_desconhecida_cai_no_padrao(self, cliente, lixo):
        corpo = cliente.get(f"{url_da_previa()}?viewport={lixo}").content.decode()

        assert f'data-viewport="{PADRAO_DO_VIEWPORT}"' in corpo

    @pytest.mark.parametrize(
        "lixo",
        [
            "../../../etc/passwd",
            "backoffice/base.html",
            "core/secoes/../../base.html",
            "inventado",
            "",
        ],
    )
    def test_desenho_desconhecido_cai_no_padrao(self, cliente, lixo):
        resposta = cliente.post(
            url_da_previa(), {**traducao().content, "layout": lixo}
        )

        assert resposta.status_code == 200
        assert 'class="hero container"' in resposta.content.decode()

    def test_nao_ha_parametro_de_template(self, cliente):
        """
        O template não é escolhido pelo cliente em hipótese nenhuma --
        nem por nome, nem por caminho.
        """
        resposta = cliente.get(
            f"{url_da_previa()}?parcial=backoffice/base.html&template=base.html"
        )

        assert resposta.status_code == 200
        assert "bo-aside" not in resposta.content.decode()

    def test_parte_de_outra_pagina_nao_tem_previa(self, cliente):
        from apps.content.models import Page

        outra = Page.objects.create(key="outra", name="Outra")
        de_fora = PageSection.objects.create(
            page=outra, key="hero", kind=PageSection.Kind.HERO
        )

        url = reverse("backoffice:content_preview", args=[de_fora.pk])

        assert cliente.get(url).status_code == 404


# ===========================================================================
# 6. A tela do editor
# ===========================================================================


class TestEditor:
    def test_tem_campos_e_previa_lado_a_lado(self, cliente):
        corpo = cliente.get(url_do_editor()).content.decode()

        assert "bo-editor-campos" in corpo
        assert "bo-editor-previa" in corpo

    def test_o_quadro_comeca_no_que_esta_salvo(self, cliente):
        """
        Sem JavaScript o `src` é um GET comum -- a tela continua útil.
        """
        corpo = cliente.get(url_do_editor()).content.decode()

        assert f'src="{url_da_previa()}?viewport=desktop"' in corpo

    def test_o_formulario_aponta_para_a_previa(self, cliente):
        corpo = cliente.get(url_do_editor()).content.decode()

        assert f'data-previa="{url_da_previa()}"' in corpo

    def test_da_para_voltar_para_a_central(self, cliente):
        corpo = cliente.get(url_do_editor()).content.decode()

        assert reverse("backoffice:content") in corpo

    def test_nenhum_link_morto(self, cliente):
        for url in (url_do_editor(), reverse("backoffice:content")):
            assert 'href="#"' not in cliente.get(url).content.decode()

    def test_os_botoes_de_largura_so_existem_com_script(self, cliente):
        """
        Eles dependem de JavaScript para fazer alguma coisa. O CSS os
        esconde até o script se anunciar (`js-ligado`) -- botão inerte é
        pior do que botão nenhum.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        css = (raiz / "static" / "css" / "layout.css").read_text(encoding="utf-8")

        assert ".bo-previa-head nav { display: none; }" in css
        assert ".js-ligado .bo-previa-head nav { display: flex; }" in css

        script = (raiz / "static" / "js" / "previa-do-conteudo.js").read_text(
            encoding="utf-8"
        )
        assert 'classList.add("js-ligado")' in script

    def test_o_script_nao_monta_html(self, cliente):
        """
        Quem desenha é o servidor. Montar marcação no navegador seria a
        segunda implementação visual que este projeto recusa.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        script = (raiz / "static" / "js" / "previa-do-conteudo.js").read_text(
            encoding="utf-8"
        )

        assert "innerHTML" not in script
        assert "createElement" not in script
        assert "srcdoc" in script
