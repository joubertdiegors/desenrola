"""
O banner superior com imagem real, e a escolha do desenho.

O BURACO QUE ESTE BLOCO FECHOU
------------------------------
Os três desenhos do banner existiam desde o Passo 4.3, a Home os
desenhava e a pré-visualização já aceitava um desenho proposto por POST
-- mas NENHUMA TELA oferecia a escolha. Trocar de desenho só era
possível pelo Admin do Django ou por migration. E imagem não havia: os
dois desenhos com imagem mostravam uma moldura tracejada.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que desenho e imagem voltem para o JSON da tradução.** São da
   PARTE, não de um idioma: escolher em português não pode deixar o
   francês com outro desenho;
2. **Que a moldura vazia suma quando não há imagem.** Sem imagem
   escolhida, o banner tem de ficar exatamente como estava;
3. **Que trocar de desenho apague dado.** "Somente texto" não lê a
   imagem, mas ela continua guardada e volta inteira;
4. **Que apagar a imagem da biblioteca derrube a Home** (SET_NULL);
5. **Que a pré-visualização minta** -- ela mostra a imagem e o desenho
   propostos, sem gravar nada.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.content import section_schema
from apps.content.models import Asset, PageSection

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")

GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)

# O que o formulário do banner manda quando alguém salva: todos os
# textos declarados, para nenhum ser apagado sem querer.
TEXTOS = {
    "title": "Título",
    "lead": "Chamada",
    "cta": "Começar",
    "badge_label": "cartas emitidas",
    "badge_note": "ao vivo",
    "login_prompt": "Já tem conta?",
    "login_link": "Entrar",
    "art_caption": "legenda da imagem",
}


def _gif(nome="banner.gif"):
    return SimpleUploadedFile(nome, GIF, content_type="image/gif")


def _com_permissoes(*codenames, email="editora@mail.com"):
    pessoa = get_user_model().objects.create_user(
        email=email, password="x", full_name="Clara Dias"
    )
    pessoa.user_permissions.add(
        Permission.objects.get(content_type__app_label="core", codename="access_backoffice")
    )
    for codename in codenames:
        pessoa.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename=codename)
        )
    return get_user_model().objects.get(pk=pessoa.pk)


@pytest.fixture(autouse=True)
def _media_isolada(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def editora(db):
    return _com_permissoes("view_pagesection", "change_pagesection")


@pytest.fixture
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


@pytest.fixture
def imagem(db):
    return Asset.objects.create(kind=Asset.Kind.HOME, file=_gif(), alt_text="Fachada")


def secao(chave):
    return PageSection.objects.get(page__key="home", key=chave)


def url_do_editor(chave="hero"):
    return reverse("backoffice:content_section", args=[secao(chave).pk])


def salvar(cliente, chave="hero", **campos):
    dados = {"idioma": "pt", **TEXTOS, **campos}
    return cliente.post(url_do_editor(chave), dados)


def home(client):
    return client.get(HOME).content.decode()


# ===========================================================================
# 1. O editor oferece as duas escolhas -- e só onde há o que escolher
# ===========================================================================


class TestOEditorOferece:
    def test_o_banner_oferece_desenho_e_imagem(self, cliente):
        corpo = cliente.get(url_do_editor()).content.decode()

        assert 'name="layout"' in corpo
        assert 'name="imagem"' in corpo
        assert "Desenho e imagem" in corpo

    def test_os_tres_desenhos_sao_oferecidos(self, cliente):
        corpo = cliente.get(url_do_editor()).content.decode()

        for layout in section_schema.SECOES["hero"].layouts:
            assert f'value="{layout.chave}"' in corpo

    def test_o_desenho_gravado_vem_marcado(self, cliente):
        alvo = secao("hero")
        alvo.layout = "somente_texto"
        alvo.save(update_fields=["layout"])

        corpo = cliente.get(url_do_editor()).content.decode()

        assert '<option value="somente_texto" selected>' in corpo

    @pytest.mark.parametrize("chave", ["trust", "partners", "how", "cta"])
    def test_parte_sem_desenho_nem_imagem_nao_oferece_nada(self, cliente, chave):
        """
        Um seletor de uma opção só, ou um campo de imagem numa parte que
        não tem imagem, seria ruído na tela.
        """
        corpo = cliente.get(url_do_editor(chave)).content.decode()

        assert 'name="layout"' not in corpo
        assert 'name="imagem"' not in corpo
        assert "Desenho e imagem" not in corpo

    def test_imagem_desativada_nao_e_oferecida(self, cliente, imagem):
        morta = Asset.objects.create(kind=Asset.Kind.HOME, file=_gif("m.gif"), is_active=False)

        corpo = cliente.get(url_do_editor()).content.decode()

        assert f'<option value="{imagem.pk}">' in corpo
        assert f'<option value="{morta.pk}">' not in corpo


# ===========================================================================
# 2. Salvar grava na SEÇÃO, não na tradução
# ===========================================================================


class TestSalvar:
    def test_grava_o_desenho(self, cliente):
        salvar(cliente, layout="imagem_completa")

        assert secao("hero").layout == "imagem_completa"

    def test_grava_a_imagem(self, cliente, imagem):
        salvar(cliente, layout="imagem_texto", imagem=imagem.pk)

        assert secao("hero").image_id == imagem.pk

    def test_tira_a_imagem_sem_apagar_o_asset(self, cliente, imagem):
        salvar(cliente, layout="imagem_texto", imagem=imagem.pk)

        salvar(cliente, layout="imagem_texto", imagem="")

        assert secao("hero").image_id is None
        assert Asset.objects.filter(pk=imagem.pk).exists()

    def test_o_desenho_nao_vai_para_o_json_da_traducao(self, cliente, imagem):
        """
        Se fossem para o JSON, escolher em português deixaria o francês
        com outro desenho -- e a Home mudaria de forma ao trocar de
        idioma, que não é o que ninguém pediu.
        """
        salvar(cliente, layout="imagem_completa", imagem=imagem.pk)

        traducao = secao("hero").translations.get(language="pt")
        assert "layout" not in traducao.content
        assert "imagem" not in traducao.content

    def test_escolher_em_um_idioma_vale_em_todos(self, cliente, imagem):
        alvo = secao("hero")
        alvo.translations.create(language="fr", content={"title": "Titre"})

        cliente.post(
            f"{url_do_editor()}?idioma=fr",
            {"idioma": "fr", "title": "Titre", "layout": "imagem_completa",
             "imagem": imagem.pk},
        )

        alvo.refresh_from_db()
        assert alvo.layout == "imagem_completa"
        assert alvo.image_id == imagem.pk

    def test_desenho_inventado_nao_e_gravado(self, cliente):
        """A lista é fechada: o navegador não escolhe template."""
        antes = secao("hero").layout

        resposta = salvar(cliente, layout="../../etc/passwd")

        assert resposta.status_code == 200
        assert secao("hero").layout == antes

    def test_imagem_inexistente_nao_e_gravada(self, cliente):
        resposta = salvar(cliente, layout="imagem_texto", imagem=9999)

        assert resposta.status_code == 200
        assert secao("hero").image_id is None


# ===========================================================================
# 3. A Home desenha a imagem de verdade
# ===========================================================================


class TestAHomeDesenha:
    def test_sem_imagem_continua_a_moldura_vazia(self, client):
        """O estado em que o banner esteve até aqui, e que continua válido."""
        corpo = home(client)

        assert "img-slot" in corpo
        assert 'class="hero-image"' not in corpo

    def test_com_imagem_sai_a_imagem(self, client, imagem):
        alvo = secao("hero")
        alvo.image = imagem
        alvo.save(update_fields=["image"])

        corpo = home(client)

        assert f'src="{imagem.file.url}"' in corpo
        assert 'class="hero-image"' in corpo
        assert "img-slot" not in corpo

    def test_o_texto_alternativo_vem_do_asset(self, client, imagem):
        alvo = secao("hero")
        alvo.image = imagem
        alvo.save(update_fields=["image"])

        assert 'alt="Fachada"' in home(client)

    def test_sem_alt_no_asset_cai_na_legenda_do_cms(self, client):
        sem_alt = Asset.objects.create(kind=Asset.Kind.HOME, file=_gif(), alt_text="")
        alvo = secao("hero")
        alvo.image = sem_alt
        alvo.save(update_fields=["image"])

        corpo = home(client)

        assert 'alt=""' not in corpo
        assert "img-slot" not in corpo

    @pytest.mark.parametrize(
        ("desenho", "marca"),
        [("imagem_texto", "hero-art"), ("imagem_completa", "hero-cheio-art")],
    )
    def test_os_dois_desenhos_com_imagem_a_desenham(self, client, imagem, desenho, marca):
        alvo = secao("hero")
        alvo.layout = desenho
        alvo.image = imagem
        alvo.save(update_fields=["layout", "image"])

        corpo = home(client)

        assert marca in corpo
        assert f'src="{imagem.file.url}"' in corpo

    def test_somente_texto_nao_desenha_a_imagem_mas_a_guarda(self, client, imagem):
        """Trocar de desenho nunca apaga dado."""
        alvo = secao("hero")
        alvo.layout = "somente_texto"
        alvo.image = imagem
        alvo.save(update_fields=["layout", "image"])

        corpo = home(client)

        assert imagem.file.url not in corpo
        assert secao("hero").image_id == imagem.pk

    def test_voltar_o_desenho_traz_a_imagem_de_volta(self, client, imagem):
        alvo = secao("hero")
        alvo.layout = "somente_texto"
        alvo.image = imagem
        alvo.save(update_fields=["layout", "image"])
        assert imagem.file.url not in home(client)

        alvo.layout = "imagem_texto"
        alvo.save(update_fields=["layout"])

        assert imagem.file.url in home(client)

    def test_apagar_a_imagem_nao_derruba_a_home(self, client, imagem):
        alvo = secao("hero")
        alvo.image = imagem
        alvo.save(update_fields=["image"])
        imagem.delete()

        resposta = client.get(HOME)

        assert resposta.status_code == 200
        assert "img-slot" in resposta.content.decode()

    def test_mais_partes_com_imagem_nao_custam_mais_consultas(self, client, imagem):
        """
        `select_related("image")`: sem ele, CADA parte com imagem custaria
        uma consulta a mais -- e a Home é a página mais visitada do site.

        Contar consultas que mencionam `content_asset` não mediria isso:
        três já mencionam por JOIN (as seções, os parceiros e o
        `SiteSettings`, que guarda logotipo e favicon). O que
        `select_related` garante é que o número NÃO CRESÇA.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        # Aquecimento: o contador de cartas (`letters.statistics`) guarda
        # o numero em cache por dez minutos, e so a PRIMEIRA visita faz o
        # COUNT. Sem isto, a comparacao mediria o cache.
        client.get(HOME)

        with CaptureQueriesContext(connection) as sem_imagem:
            client.get(HOME)

        for chave in ("hero", "trust", "how", "cta"):
            parte = secao(chave)
            parte.image = imagem
            parte.save(update_fields=["image"])

        with CaptureQueriesContext(connection) as com_imagem:
            client.get(HOME)

        assert len(com_imagem.captured_queries) == len(sem_imagem.captured_queries)


# ===========================================================================
# 4. A pré-visualização mostra o proposto, sem gravar
# ===========================================================================


class TestPrevia:
    def test_mostra_a_imagem_proposta_antes_de_salvar(self, cliente, imagem):
        resposta = cliente.post(
            reverse("backoffice:content_preview", args=[secao("hero").pk]),
            {**TEXTOS, "layout": "imagem_texto", "imagem": imagem.pk},
        )

        assert imagem.file.url in resposta.content.decode()
        assert secao("hero").image_id is None

    def test_mostra_o_desenho_proposto_com_a_imagem(self, cliente, imagem):
        resposta = cliente.post(
            reverse("backoffice:content_preview", args=[secao("hero").pk]),
            {**TEXTOS, "layout": "imagem_completa", "imagem": imagem.pk},
        )

        corpo = resposta.content.decode()
        assert "hero-cheio" in corpo
        assert imagem.file.url in corpo
        assert secao("hero").layout != "imagem_completa"

    def test_tirar_a_imagem_na_previa_mostra_a_moldura(self, cliente, imagem):
        alvo = secao("hero")
        alvo.image = imagem
        alvo.save(update_fields=["image"])

        resposta = cliente.post(
            reverse("backoffice:content_preview", args=[alvo.pk]),
            {**TEXTOS, "layout": "imagem_texto", "imagem": ""},
        )

        corpo = resposta.content.decode()
        assert imagem.file.url not in corpo
        assert "img-slot" in corpo
        assert secao("hero").image_id == imagem.pk

    def test_o_get_continua_mostrando_o_que_esta_salvo(self, cliente, imagem):
        alvo = secao("hero")
        alvo.image = imagem
        alvo.save(update_fields=["image"])

        resposta = cliente.get(
            reverse("backoffice:content_preview", args=[alvo.pk])
        )

        assert imagem.file.url in resposta.content.decode()


# ===========================================================================
# 5. A declaração
# ===========================================================================


class TestDeclaracao:
    def test_so_o_banner_declara_imagem(self):
        com_imagem = {
            chave for chave, s in section_schema.SECOES.items() if s.imagem
        }

        assert com_imagem == {"hero"}

    def test_a_imagem_e_da_secao_e_nao_da_traducao(self):
        """
        Uma FK, não um id dentro do JSON: referência guardada em JSON o
        banco não enxerga -- e o próprio `Asset` explica o preço disso.
        """
        from django.db import models

        campo = PageSection._meta.get_field("image")

        assert isinstance(campo, models.ForeignKey)
        assert campo.related_model is Asset
        assert campo.remote_field.on_delete is models.SET_NULL
