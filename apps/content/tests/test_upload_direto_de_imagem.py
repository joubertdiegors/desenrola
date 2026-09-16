"""
Bloco D: upload de imagem direto no contexto -- Parceiros e Banners.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que cadastrar um parceiro ou configurar um banner exija passar
   pela Biblioteca Central primeiro.** O upload cria o `Asset` na hora,
   dentro do próprio formulário;
2. **Que substituir ou remover uma imagem deixe arquivo, `Asset` ou
   associação órfã para trás** -- mas só quando NADA mais a usa; uma
   imagem compartilhada nunca pode sumir por causa de outro registro;
3. **Que o navegador decida, sozinho, o que é uma imagem válida.** O
   atributo `accept` é só atalho de tela -- tamanho, formato real
   (Pillow) e MIME declarado são conferidos no servidor, sempre;
4. **Que a prévia crie um `Asset` a cada tecla.** Um upload ainda não
   salvo aparece na prévia como o arquivo em memória, nunca como um
   registro novo na Biblioteca;
5. **Que a Biblioteca Central pare de funcionar** depois que Parceiros
   e Banners deixaram de depender dela como etapa obrigatória.
"""

import io
import os

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.content.forms import FORMATOS_ACEITOS, TAMANHO_MAXIMO_DA_IMAGEM
from apps.content.models import Asset, PageSection, PageSectionTranslation, Partner

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media_isolada(settings, tmp_path):
    """Sem isto a suíte gravaria arquivos de teste no `media/` do repositório."""
    settings.MEDIA_ROOT = tmp_path


GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)

TODOS_OS_BANNERS_COM_IMAGEM = (
    "imagem_texto",
    "imagem_completa",
    "destaque",
    "assimetrico",
    "foto_ampla",
    "editorial",
)


def _gif(nome="upload.gif"):
    return SimpleUploadedFile(nome, GIF, content_type="image/gif")


def _nao_e_imagem(nome="fingido.png", content_type="image/png"):
    """Bytes que não abrem no Pillow, com nome e Content-Type de imagem."""
    return SimpleUploadedFile(nome, b"MZ\x90\x00isto-nao-e-uma-imagem", content_type=content_type)


def _svg(nome="vetor.svg"):
    conteudo = b'<svg onload="alert(1)"><script>alert(1)</script></svg>'
    return SimpleUploadedFile(nome, conteudo, content_type="image/svg+xml")


def _imagem_grande_demais(nome="grande.png"):
    """Um PNG de verdade, grande demais -- ruído aleatório não comprime."""
    from PIL import Image

    largura = altura = 1600
    dados = os.urandom(largura * altura * 3)
    img = Image.frombytes("RGB", (largura, altura), dados)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    conteudo = buffer.getvalue()
    assert len(conteudo) > TAMANHO_MAXIMO_DA_IMAGEM, "gerar de novo com mais ruído"
    return SimpleUploadedFile(nome, conteudo, content_type="image/png")


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
def editora_de_parceiros(db):
    return _pessoa(
        "editora-upload-parceiro@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_partner"),
        ("content", "add_partner"),
        ("content", "change_partner"),
        ("content", "delete_partner"),
    )


@pytest.fixture
def cliente_parceiros(editora_de_parceiros):
    c = Client()
    c.force_login(editora_de_parceiros)
    return c


@pytest.fixture
def editora_de_secoes(db):
    return _pessoa(
        "editora-upload-secao@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_pagesection"),
        ("content", "change_pagesection"),
    )


@pytest.fixture
def cliente_secoes(editora_de_secoes):
    c = Client()
    c.force_login(editora_de_secoes)
    return c


def hero():
    return PageSection.objects.get(page__key="home", key="hero")


def usar_desenho(desenho):
    PageSection.objects.filter(page__key="home", key="hero").update(layout=desenho)


def texto_do_hero():
    return PageSectionTranslation.objects.get(
        section__page__key="home", section__key="hero", language="pt"
    ).content


def url_do_editor_do_banner():
    return reverse("backoffice:content_section", args=[hero().pk])


def url_da_previa_do_banner():
    return reverse("backoffice:content_preview", args=[hero().pk])


def salvar_banner(cliente, **campos):
    dados = {"idioma": "pt", **texto_do_hero(), **campos}
    return cliente.post(url_do_editor_do_banner(), dados)


HOME = reverse("core:home")


# ===========================================================================
# 1. Parceiros -- upload direto, sem passar pela Biblioteca
# ===========================================================================


class TestUploadDeParceiro:
    def test_criar_com_upload_nao_precisa_da_biblioteca(self, cliente_parceiros):
        antes = Asset.objects.count()

        resposta = cliente_parceiros.post(
            reverse("backoffice:partner_new"),
            {
                "name": "Padaria Nova",
                "description": "",
                "url": "https://padaria.example.com",
                "is_active": "on",
                "order": 0,
                "logo_upload": _gif(),
            },
        )

        assert resposta.status_code == 302
        parceiro = Partner.objects.get(name="Padaria Nova")
        assert parceiro.logo_id is not None
        assert Asset.objects.count() == antes + 1
        assert parceiro.logo.kind == Asset.Kind.PARTNER

    def test_criar_sem_imagem_continua_funcionando(self, cliente_parceiros):
        resposta = cliente_parceiros.post(
            reverse("backoffice:partner_new"),
            {
                "name": "Sem Logo",
                "description": "",
                "url": "",
                "is_active": "on",
                "order": 0,
            },
        )

        assert resposta.status_code == 302
        assert Partner.objects.get(name="Sem Logo").logo_id is None

    def test_upload_vence_a_selecao_da_biblioteca(self, cliente_parceiros):
        """Enviar um arquivo novo substitui o que estava escolhido no seletor."""
        da_biblioteca = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif("velho.gif"))

        cliente_parceiros.post(
            reverse("backoffice:partner_new"),
            {
                "name": "Com os dois",
                "description": "",
                "url": "",
                "is_active": "on",
                "order": 0,
                "logo": da_biblioteca.pk,
                "logo_upload": _gif("novo.gif"),
            },
        )

        parceiro = Partner.objects.get(name="Com os dois")
        assert parceiro.logo_id != da_biblioteca.pk

    def test_substituir_a_imagem_limpa_a_anterior_orfa(self, cliente_parceiros):
        parceiro = Partner.objects.create(
            name="Com logo", logo=Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif())
        )
        antiga_pk = parceiro.logo_id

        cliente_parceiros.post(
            reverse("backoffice:partner_edit", args=[parceiro.pk]),
            {
                "name": "Com logo",
                "description": "",
                "url": "",
                "is_active": "on",
                "order": 0,
                "logo_upload": _gif("substituta.gif"),
            },
        )

        parceiro.refresh_from_db()
        assert parceiro.logo_id != antiga_pk
        assert not Asset.objects.filter(pk=antiga_pk).exists()

    def test_substituir_preserva_a_anterior_se_compartilhada(self, cliente_parceiros):
        compartilhada = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif())
        parceiro = Partner.objects.create(name="Com logo", logo=compartilhada)
        Partner.objects.create(name="Outro com a mesma", logo=compartilhada)

        cliente_parceiros.post(
            reverse("backoffice:partner_edit", args=[parceiro.pk]),
            {
                "name": "Com logo",
                "description": "",
                "url": "",
                "is_active": "on",
                "order": 0,
                "logo_upload": _gif("substituta.gif"),
            },
        )

        assert Asset.objects.filter(pk=compartilhada.pk).exists()

    def test_a_pagina_reflete_a_nova_imagem(self, cliente_parceiros, client):
        parceiro = Partner.objects.create(
            name="Com logo", url="https://x.example.com",
            logo=Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif("velho.gif")),
        )

        cliente_parceiros.post(
            reverse("backoffice:partner_edit", args=[parceiro.pk]),
            {
                "name": "Com logo",
                "description": "",
                "url": "https://x.example.com",
                "is_active": "on",
                "order": 0,
                "logo_upload": _gif("novo.gif"),
            },
        )

        parceiro.refresh_from_db()
        html = client.get(HOME).content.decode()
        assert parceiro.logo.file.url in html


# ===========================================================================
# 2. Banners -- upload direto, em todos os desenhos com imagem
# ===========================================================================


class TestUploadDeBanner:
    @pytest.mark.parametrize("desenho", TODOS_OS_BANNERS_COM_IMAGEM)
    def test_upload_funciona_em_todos_os_desenhos_com_imagem(
        self, cliente_secoes, client, desenho
    ):
        usar_desenho(desenho)

        resposta = salvar_banner(cliente_secoes, layout=desenho, imagem_upload=_gif())

        assert resposta.status_code == 302
        assert hero().image_id is not None

    def test_somente_texto_nao_exige_imagem(self, cliente_secoes):
        usar_desenho("somente_texto")

        resposta = salvar_banner(cliente_secoes, layout="somente_texto")

        assert resposta.status_code == 302

    def test_somente_texto_aceita_upload_mesmo_sem_desenhar(self, cliente_secoes):
        """O dado é gravado -- trocar de desenho nunca apaga imagem."""
        usar_desenho("somente_texto")

        salvar_banner(cliente_secoes, layout="somente_texto", imagem_upload=_gif())

        assert hero().image_id is not None

    def test_substituir_limpa_a_imagem_anterior_orfa(self, cliente_secoes):
        antiga = Asset.objects.create(kind=Asset.Kind.HOME, file=_gif("velho.gif"))
        PageSection.objects.filter(pk=hero().pk).update(image=antiga)

        salvar_banner(cliente_secoes, layout="imagem_texto", imagem_upload=_gif("novo.gif"))

        assert hero().image_id != antiga.pk
        assert not Asset.objects.filter(pk=antiga.pk).exists()

    def test_substituir_preserva_a_imagem_compartilhada(self, cliente_secoes):
        compartilhada = Asset.objects.create(kind=Asset.Kind.HOME, file=_gif())
        PageSection.objects.filter(pk=hero().pk).update(image=compartilhada)
        Partner.objects.create(name="Usa a mesma", logo=compartilhada, url="https://x.example.com")

        salvar_banner(cliente_secoes, layout="imagem_texto", imagem_upload=_gif("novo.gif"))

        assert Asset.objects.filter(pk=compartilhada.pk).exists()

    def test_a_home_reflete_a_imagem_enviada(self, cliente_secoes, client):
        usar_desenho("imagem_texto")

        salvar_banner(cliente_secoes, layout="imagem_texto", imagem_upload=_gif())

        html = client.get(HOME).content.decode()
        assert hero().image.file.url in html


# ===========================================================================
# 3. Segurança -- o servidor confere, nunca o `accept` do navegador
# ===========================================================================


class TestSeguranca:
    def test_arquivo_que_nao_e_imagem_e_recusado(self, cliente_parceiros):
        resposta = cliente_parceiros.post(
            reverse("backoffice:partner_new"),
            {
                "name": "Malicioso",
                "url": "",
                "is_active": "on",
                "order": 0,
                "logo_upload": _nao_e_imagem(),
            },
        )

        assert resposta.status_code == 200
        assert not Partner.objects.filter(name="Malicioso").exists()

    def test_svg_e_recusado(self, cliente_parceiros):
        """SVG pode trazer `<script>` -- não é bitmap, o Pillow não o abre."""
        resposta = cliente_parceiros.post(
            reverse("backoffice:partner_new"),
            {
                "name": "Com SVG",
                "url": "",
                "is_active": "on",
                "order": 0,
                "logo_upload": _svg(),
            },
        )

        assert resposta.status_code == 200
        assert not Partner.objects.filter(name="Com SVG").exists()

    def test_arquivo_grande_demais_e_recusado(self, cliente_parceiros):
        resposta = cliente_parceiros.post(
            reverse("backoffice:partner_new"),
            {
                "name": "Grande demais",
                "url": "",
                "is_active": "on",
                "order": 0,
                "logo_upload": _imagem_grande_demais(),
            },
        )

        assert resposta.status_code == 200
        assert not Partner.objects.filter(name="Grande demais").exists()

    def test_o_content_type_declarado_nao_e_suficiente(self, cliente_parceiros):
        """`accept="image/*"` é só atalho de tela -- o Pillow abre os bytes de verdade."""
        arquivo = _nao_e_imagem(content_type="image/png")

        resposta = cliente_parceiros.post(
            reverse("backoffice:partner_new"),
            {
                "name": "MIME fingido",
                "url": "",
                "is_active": "on",
                "order": 0,
                "logo_upload": arquivo,
            },
        )

        assert not Partner.objects.filter(name="MIME fingido").exists()
        assert resposta.status_code == 200

    def test_mesma_validacao_vale_para_banner(self, cliente_secoes):
        resposta = salvar_banner(cliente_secoes, layout="imagem_texto", imagem_upload=_svg())

        assert hero().image_id is None
        assert resposta.status_code == 200

    def test_formatos_aceitos_sao_os_documentados(self):
        assert set(FORMATOS_ACEITOS) == {"PNG", "JPEG", "GIF", "WEBP"}

    def test_upload_de_parceiro_exige_permissao(self, client):
        sem_permissao = _pessoa("sem-permissao@mail.com", ("core", "access_backoffice"))
        c = Client()
        c.force_login(sem_permissao)

        resposta = c.post(
            reverse("backoffice:partner_new"),
            {"name": "X", "url": "", "is_active": "on", "order": 0, "logo_upload": _gif()},
        )

        assert resposta.status_code == 403
        assert not Partner.objects.filter(name="X").exists()

    def test_upload_de_parceiro_exige_csrf(self, editora_de_parceiros):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(editora_de_parceiros)

        resposta = sem_token.post(
            reverse("backoffice:partner_new"),
            {"name": "Sem CSRF", "url": "", "is_active": "on", "order": 0, "logo_upload": _gif()},
        )

        assert resposta.status_code == 403
        assert not Partner.objects.filter(name="Sem CSRF").exists()

    def test_upload_de_banner_exige_csrf(self, editora_de_secoes):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(editora_de_secoes)

        sem_token.post(
            url_do_editor_do_banner(),
            {"idioma": "pt", **texto_do_hero(), "layout": "imagem_texto", "imagem_upload": _gif()},
        )

        assert hero().image_id is None


# ===========================================================================
# 4. A prévia nunca cria um Asset
# ===========================================================================


class TestPreviaNaoGrava:
    def test_a_previa_mostra_o_upload_sem_criar_asset(self, cliente_secoes):
        antes = Asset.objects.count()

        html = cliente_secoes.post(
            url_da_previa_do_banner(),
            {**texto_do_hero(), "layout": "imagem_texto", "imagem_upload": _gif()},
        ).content.decode()

        assert "data:image/gif;base64," in html
        assert Asset.objects.count() == antes
        assert hero().image_id is None

    def test_a_previa_com_upload_invalido_nao_derruba_a_tela(self, cliente_secoes):
        resposta = cliente_secoes.post(
            url_da_previa_do_banner(),
            {**texto_do_hero(), "layout": "imagem_texto", "imagem_upload": _svg()},
        )

        assert resposta.status_code == 200


# ===========================================================================
# 5. A tela de confirmação de exclusão diz a verdade sobre a imagem
# ===========================================================================


class TestConfirmacaoDeExclusao:
    def test_avisa_que_a_imagem_orfa_sera_removida(self, cliente_parceiros):
        parceiro = Partner.objects.create(
            name="Só este usa",
            logo=Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif()),
        )

        html = cliente_parceiros.get(
            reverse("backoffice:partner_delete", args=[parceiro.pk])
        ).content.decode()

        assert "será removida" in html

    def test_avisa_que_a_imagem_compartilhada_permanece(self, cliente_parceiros):
        compartilhada = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif())
        parceiro = Partner.objects.create(name="Um dos dois", logo=compartilhada)
        Partner.objects.create(name="O outro", logo=compartilhada)

        html = cliente_parceiros.get(
            reverse("backoffice:partner_delete", args=[parceiro.pk])
        ).content.decode()

        assert "continua na biblioteca" in html


# ===========================================================================
# 6. Regressão -- o que já funcionava continua funcionando
# ===========================================================================


class TestRegressao:
    def test_biblioteca_central_continua_no_ar(self, cliente_parceiros):
        """
        `cliente_parceiros` só tem permissão de Parceiros -- a Biblioteca
        exige `content.view_asset`, testado à parte em
        `test_biblioteca_de_imagens.py`. Aqui só confirmamos que a rota
        continua existindo, sem depender deste bloco para nada.
        """
        assert reverse("backoffice:assets").endswith("/backoffice/imagens/")

    def test_partner_form_continua_aceitando_selecao_da_biblioteca(self, cliente_parceiros):
        """D.5: quem quiser reaproveitar uma imagem cadastrada ainda pode."""
        da_biblioteca = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif())

        cliente_parceiros.post(
            reverse("backoffice:partner_new"),
            {
                "name": "Reaproveitado",
                "url": "",
                "is_active": "on",
                "order": 0,
                "logo": da_biblioteca.pk,
            },
        )

        assert Partner.objects.get(name="Reaproveitado").logo_id == da_biblioteca.pk

    def test_banner_form_continua_aceitando_selecao_da_biblioteca(self, cliente_secoes):
        da_biblioteca = Asset.objects.create(kind=Asset.Kind.HOME, file=_gif())

        salvar_banner(cliente_secoes, layout="imagem_texto", imagem=da_biblioteca.pk)

        assert hero().image_id == da_biblioteca.pk

    def test_crud_de_parceiro_sem_imagem_nenhuma_continua_intacto(self, cliente_parceiros):
        resposta = cliente_parceiros.post(
            reverse("backoffice:partner_new"),
            {"name": "Sem nada de imagem", "url": "", "is_active": "on", "order": 0},
        )

        assert resposta.status_code == 302
        assert Partner.objects.filter(name="Sem nada de imagem").exists()
