"""
Documentos legais no Backoffice (Sistema › Documentos legais).

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a tela abra ou grave sem a permissão de sempre.** Abrir exige
   `content.view_contentblock`; salvar, `content.change_contentblock` --
   as mesmas que o Django Admin cobrava destes blocos;
2. **Que abrir o editor altere o documento.** O texto simples de hoje é
   MOSTRADO como parágrafos; só "Salvar documento" grava;
3. **Que HTML perigoso chegue ao banco.** Script, `on*`, `javascript:`,
   imagem de fora: tudo sai no formulário, antes de gravar -- e de novo
   ao desenhar (ver `test_paginas_legais.py`);
4. **Que a primeira gravação quebre outro idioma.** O bloco passa a
   "Texto formatado" e as traduções em texto simples são convertidas
   junto, com o mesmo `linebreaks` que a página já aplicava;
5. **Que um editor esvaziado publique uma página em branco.** Grava "",
   e a página volta a responder 404;
6. **Que o rodapé perca a lista dele.** A lista dos documentos
   (`h2`, `img`) é outra; a do rodapé continua a de antes.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.content import rodape, services
from apps.content.models import ContentBlock, ContentTranslation

pytestmark = pytest.mark.django_db

TELA = reverse("backoffice:legal_documents")
TERMOS = reverse("core:legal_termos")
CHAVE_TERMOS = "legal.terms_of_use"
CHAVE_PRIVACIDADE = "legal.privacy_policy"


def _pessoa(email, *permissoes):
    pessoa = get_user_model().objects.create_user(
        email=email, password="x", full_name="Clara Dias"
    )
    for app_label, codename in permissoes:
        pessoa.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return get_user_model().objects.get(pk=pessoa.pk)


def _cliente(pessoa):
    c = Client()
    c.force_login(pessoa)
    return c


@pytest.fixture
def leitora(db):
    return _pessoa(
        "leitora-legais@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_contentblock"),
    )


@pytest.fixture
def editora(db):
    return _pessoa(
        "editora-legais@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_contentblock"),
        ("content", "change_contentblock"),
    )


@pytest.fixture
def cliente(editora):
    return _cliente(editora)


def publicar_simples(chave, texto, idioma="pt"):
    """O estado de hoje: texto simples, escrito pelo Django Admin."""
    bloco = ContentBlock.objects.get(key=chave)
    ContentTranslation.objects.update_or_create(
        block=bloco, language=idioma, defaults={"content": texto}
    )


def salvar(cliente, texto, documento="termos-de-uso", idioma="pt", **extra):
    return cliente.post(
        TELA, {"documento": documento, "idioma": idioma, "texto": texto, **extra}
    )


def gravado(chave=CHAVE_TERMOS, idioma="pt"):
    return ContentTranslation.objects.get(block__key=chave, language=idioma).content


# ===========================================================================
# 1. Quem abre, quem grava
# ===========================================================================


class TestAcesso:
    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(TELA)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_usuario_comum_nao_entra(self, auth_client):
        assert auth_client.get(TELA).status_code in (302, 403)

    def test_backoffice_sem_a_permissao_nao_entra(self, client, staff_user):
        client.force_login(staff_user)

        assert client.get(TELA).status_code == 403

    def test_quem_so_ve_le_sem_formulario(self, leitora):
        publicar_simples(CHAVE_TERMOS, "Primeira cláusula.")

        resposta = _cliente(leitora).get(TELA)
        corpo = resposta.content.decode()

        assert resposta.status_code == 200
        assert "Primeira cláusula." in corpo
        assert 'name="texto"' not in corpo
        assert "Salvar documento" not in corpo

    def test_quem_so_ve_nao_grava(self, leitora):
        publicar_simples(CHAVE_TERMOS, "Original.")

        resposta = salvar(_cliente(leitora), "<p>Trocado.</p>")

        assert resposta.status_code == 403
        assert gravado() == "Original."

    def test_post_sem_token_e_recusado(self, editora):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(editora)

        resposta = salvar(sem_token, "<p>Sem token.</p>")

        assert resposta.status_code == 403
        assert not ContentTranslation.objects.filter(block__key=CHAVE_TERMOS).exists()

    def test_as_duas_permissoes_estao_no_catalogo(self):
        from apps.accounts import admin_permissions

        chaves = {p.chave for p in admin_permissions.todas()}

        assert "content.view_contentblock" in chaves
        assert "content.change_contentblock" in chaves

    def test_o_menu_so_oferece_a_quem_abre(self, client, staff_user, leitora):
        client.force_login(staff_user)
        sem = client.get(reverse("backoffice:overview")).content.decode()
        com = _cliente(leitora).get(reverse("backoffice:overview")).content.decode()

        assert TELA not in sem
        assert f'href="{TELA}"' in com


# ===========================================================================
# 2. Abrir não muda nada
# ===========================================================================


class TestAbrir:
    def test_o_texto_simples_abre_como_paragrafos(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Linha <um>\nLinha dois\n\nSegundo")

        form = cliente.get(TELA).context["form"]

        assert form["texto"].value() == (
            "<p>Linha &lt;um&gt;<br>Linha dois</p>\n\n<p>Segundo</p>"
        )

    def test_abrir_nao_grava_nem_converte(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Linha um\nLinha dois")

        cliente.get(TELA)

        assert gravado() == "Linha um\nLinha dois"
        assert ContentBlock.objects.get(key=CHAVE_TERMOS).kind == ContentBlock.Kind.TEXT

    def test_o_seletor_escolhe_o_documento(self, cliente):
        publicar_simples(CHAVE_PRIVACIDADE, "Política vigente.")

        resposta = cliente.get(TELA, {"documento": "privacidade"})

        assert resposta.context["documento"]["slug"] == "privacidade"
        assert "Política vigente." in resposta.context["form"]["texto"].value()

    def test_documento_desconhecido_cai_no_primeiro(self, cliente):
        resposta = cliente.get(TELA, {"documento": "../../etc", "idioma": "xx"})

        assert resposta.context["documento"]["slug"] == "termos-de-uso"
        assert resposta.context["idioma"] == "pt"

    def test_idioma_sem_texto_abre_vazio_e_avisa(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Só em português.")

        resposta = cliente.get(TELA, {"idioma": "fr"})

        assert resposta.context["form"]["texto"].value() == ""
        assert "a página mostra o texto do idioma padrão" in resposta.content.decode()

    def test_o_editor_e_o_do_rodape_no_modo_documento(self, cliente):
        corpo = cliente.get(TELA).content.decode()

        assert "data-editor-rico" in corpo
        assert "js/editor-rico.js" in corpo
        assert '<option value="H2">' in corpo
        assert 'data-comando="imagens"' in corpo
        # Os desenhos inline são do rodapé: a lista dos documentos não os aceita.
        assert 'data-comando="icones"' not in corpo

    def test_o_seletor_de_imagens_oferece_so_a_biblioteca(self, cliente, settings, tmp_path):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.content.models import Asset

        settings.MEDIA_ROOT = tmp_path
        gif = (
            b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
            b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        )
        viva = Asset.objects.create(
            kind=Asset.Kind.CONTENT,
            file=SimpleUploadedFile("viva.gif", gif, content_type="image/gif"),
            alt_text="Selo",
        )
        morta = Asset.objects.create(
            kind=Asset.Kind.CONTENT,
            file=SimpleUploadedFile("morta.gif", gif, content_type="image/gif"),
            is_active=False,
        )

        corpo = cliente.get(TELA).content.decode()

        assert f'data-imagem-src="{viva.file.url}"' in corpo
        assert morta.file.url not in corpo


# ===========================================================================
# 3. Gravar: a lista fechada decide
# ===========================================================================


class TestGravar:
    def test_grava_o_html_permitido(self, cliente):
        salvar(
            cliente,
            '<h2>1. Objeto</h2><p style="text-align:center">Texto <em>leve</em>.</p>'
            '<ol><li>um</li></ol><p><a href="https://exemplo.test/">site</a></p>',
        )

        assert gravado() == (
            '<h2>1. Objeto</h2><p style="text-align:center">Texto <em>leve</em>.</p>'
            '<ol><li>um</li></ol><p><a href="https://exemplo.test/">site</a></p>'
        )
        assert ContentBlock.objects.get(key=CHAVE_TERMOS).kind == ContentBlock.Kind.RICH_TEXT

    def test_o_perigoso_nao_chega_ao_banco(self, cliente):
        salvar(
            cliente,
            '<p onclick="x()">Oi</p><script>alert(1)</script><iframe src="/"></iframe>'
            '<a href="javascript:alert(1)">a</a><img src="https://fora.test/p.png" alt="p">'
            '<img src="data:image/png;base64,AAAA"><a href="{url_termos}">atalho</a>',
        )

        texto = gravado()
        assert texto == "<p>Oi</p><a>a</a><a>atalho</a>"

    def test_a_imagem_da_biblioteca_passa(self, cliente):
        imagem = '<p><img src="/media/assets/2026/09/selo.png" alt="Selo" width="120"></p>'

        salvar(cliente, imagem)

        assert gravado() == imagem

    def test_editor_vazio_grava_sem_texto_e_tira_a_pagina(self, cliente):
        salvar(cliente, "<p>Publicado.</p>")
        assert cliente.get(TERMOS).status_code == 200

        resposta = salvar(cliente, "<p><br></p>")

        assert resposta.status_code == 302
        assert gravado() == ""
        assert cliente.get(TERMOS).status_code == 404

    def test_volta_para_o_mesmo_documento_e_idioma(self, cliente):
        resposta = salvar(cliente, "<p>Tekst.</p>", documento="privacidade", idioma="nl")

        assert resposta.url == f"{TELA}?documento=privacidade&idioma=nl"
        assert gravado(CHAVE_PRIVACIDADE, "nl") == "<p>Tekst.</p>"

    def test_texto_grande_demais_e_recusado_com_aviso(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Original.")
        enorme = "<p>" + ("a" * rodape.TAMANHO_MAXIMO_DO_DOCUMENTO) + "</p>"

        resposta = salvar(cliente, enorme)

        assert resposta.status_code == 200
        assert resposta.context["form"].errors["texto"]
        assert gravado() == "Original."

    def test_a_primeira_gravacao_converte_os_outros_idiomas(self, cliente):
        """
        O bloco inteiro vira "Texto formatado"; a tradução francesa, que
        estava em texto simples, é convertida com o mesmo `linebreaks` --
        a página em francês continua mostrando o mesmo texto.
        """
        publicar_simples(CHAVE_TERMOS, "Texte <un>\nligne deux", idioma="fr")

        salvar(cliente, "<p>Português.</p>")

        assert gravado(idioma="fr") == "<p>Texte &lt;un&gt;<br>ligne deux</p>"
        francesa = services.documento_legal(CHAVE_TERMOS, "fr")
        assert francesa.rico is True
        assert francesa.texto == "<p>Texte &lt;un&gt;<br>ligne deux</p>"

    def test_o_bloco_apagado_volta_a_existir(self, cliente):
        ContentBlock.objects.filter(key=CHAVE_TERMOS).delete()

        salvar(cliente, "<p>De novo.</p>")

        bloco = ContentBlock.objects.get(key=CHAVE_TERMOS)
        assert bloco.kind == ContentBlock.Kind.RICH_TEXT
        assert gravado() == "<p>De novo.</p>"


# ===========================================================================
# 4. As duas listas: a do documento e a do rodapé
# ===========================================================================


class TestAsDuasListas:
    def test_o_rodape_continua_sem_titulo_de_documento_e_sem_imagem(self):
        limpo = rodape.sanitizar('<h2>T</h2><img src="/media/assets/a.png"><h3>Ok</h3>')

        assert limpo == "T<h3>Ok</h3>"

    def test_o_rodape_continua_com_os_atalhos(self):
        assert rodape.sanitizar('<a href="{url_termos}">T</a>') == '<a href="{url_termos}">T</a>'

    def test_o_documento_nao_aceita_desenho_inline(self):
        assert rodape.sanitizar_documento('<svg><path d="M0 0"/></svg><p>x</p>') == "<p>x</p>"

    @pytest.mark.parametrize(
        "endereco",
        [
            "https://fora.test/a.png",
            "//fora.test/a.png",
            "/media/assets/../../segredo.png",
            "/media/assets//a.png",
            "/media/letters/carta.pdf",
            "/media/assets/a.svg",
            "data:image/png;base64,AAAA",
            "javascript:alert(1)",
        ],
    )
    def test_imagem_fora_da_biblioteca_sai_inteira(self, endereco):
        assert rodape.sanitizar_documento(f'<p><img src="{endereco}" alt="x"></p>') == "<p></p>"

    def test_e_idempotente(self):
        uma = rodape.sanitizar_documento(
            '<h2 style="text-align:right">A</h2><img src="/media/assets/a.png" alt="b">'
        )

        assert rodape.sanitizar_documento(uma) == uma

    def test_o_unico_ponto_que_marca_como_seguro_continua_um(self):
        import pathlib

        fonte = pathlib.Path("apps/content/rodape.py").read_text(encoding="utf-8")

        assert fonte.count("mark_safe(") == 1
        assert "renderizar_documento" in fonte
