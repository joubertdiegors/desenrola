"""
A biblioteca de imagens, administrável pelo Backoffice.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o upload aceite o que não é imagem.** Um executável renomeado
   para `.png` é a tentativa mais banal que existe, e `ImageField`
   sozinho já a recusa -- mas só enquanto ninguém trocar o campo;
2. **Que o SVG entre.** Não é bitmap e pode trazer `<script>` dentro:
   servi-lo do nosso domínio seria XSS com as nossas credenciais;
3. **Que a tela estoure 500 numa recusa legítima.** Trocar o arquivo de
   uma imagem que uma carta finalizada usa é recusado pelo modelo, e
   apagar imagem de um modelo é recusado pelo banco. As duas coisas
   precisam chegar como texto em português, não como traceback;
4. **Que o menu ofereça uma porta fechada** -- o item só aparece para
   quem tem a permissão que a tela cobra;
5. **Que apagar uma imagem derrube a página inicial.** A parte perde a
   imagem (SET_NULL) e volta à moldura vazia; não quebra.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.content.forms import FORMATOS_ACEITOS, TAMANHO_MAXIMO_DA_IMAGEM
from apps.content.models import Asset, PageSection, Partner

pytestmark = pytest.mark.django_db

LISTA = reverse("backoffice:assets")
NOVA = reverse("backoffice:asset_new")

GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _envio(nome="marca.gif", conteudo=GIF, tipo="image/gif"):
    return SimpleUploadedFile(nome, conteudo, content_type=tipo)


def _gif():
    return _envio()


def _com_permissoes(*codenames, email="imagens@mail.com"):
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


TODAS = ("view_asset", "add_asset", "change_asset", "delete_asset")


@pytest.fixture(autouse=True)
def _media_isolada(settings, tmp_path):
    """Sem isto a suíte gravaria os envios no `media/` do repositório."""
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def administradora(db):
    return _com_permissoes(*TODAS)


@pytest.fixture
def leitora(db):
    return _com_permissoes("view_asset", email="leitora@mail.com")


@pytest.fixture
def cliente(administradora):
    c = Client()
    c.force_login(administradora)
    return c


@pytest.fixture
def cliente_leitora(leitora):
    c = Client()
    c.force_login(leitora)
    return c


def criar_imagem(**campos):
    campos.setdefault("kind", Asset.Kind.HOME)
    campos.setdefault("file", _gif())
    return Asset.objects.create(**campos)


# ===========================================================================
# 1. Acesso
# ===========================================================================


def _rotas(imagem):
    return [
        (LISTA, "get", "view_asset"),
        (NOVA, "post", "add_asset"),
        (reverse("backoffice:asset_edit", args=[imagem.pk]), "get", "view_asset"),
        (reverse("backoffice:asset_activation", args=[imagem.pk]), "post", "change_asset"),
        (reverse("backoffice:asset_delete", args=[imagem.pk]), "get", "delete_asset"),
    ]


class TestAcesso:
    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(LISTA)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta["Location"]

    def test_usuario_comum_e_recusado(self, auth_client):
        assert auth_client.get(LISTA).status_code in (302, 403)

    def test_staff_sem_a_permissao_e_recusado(self, client, staff_user):
        client.force_login(staff_user)

        assert client.get(LISTA).status_code == 403

    @pytest.mark.parametrize("indice", range(5))
    def test_cada_rota_recusa_quem_nao_tem_a_permissao_dela(self, client, indice):
        imagem = criar_imagem()
        url, metodo, exigida = _rotas(imagem)[indice]
        pessoa = _com_permissoes(
            *[c for c in TODAS if c != exigida], email=f"sem-{exigida}@mail.com"
        )
        client.force_login(pessoa)

        assert getattr(client, metodo)(url).status_code == 403, f"{metodo} {url}"

    def test_quem_so_ve_nao_grava(self, cliente_leitora):
        imagem = criar_imagem(alt_text="antes")
        url = reverse("backoffice:asset_edit", args=[imagem.pk])

        assert cliente_leitora.get(url).status_code == 200
        assert cliente_leitora.post(url, {"kind": Asset.Kind.HOME}).status_code == 403
        assert Asset.objects.get(pk=imagem.pk).alt_text == "antes"

    def test_imagem_inexistente_da_404(self, cliente):
        assert cliente.get(reverse("backoffice:asset_edit", args=[9999])).status_code == 404


class TestMenuLateral:
    def test_o_item_aparece_para_quem_tem_a_permissao(self, cliente):
        corpo = cliente.get(LISTA).content.decode()

        assert reverse("backoffice:assets") in corpo

    def test_o_item_nao_aparece_para_quem_nao_tem(self, client, staff_user):
        """Oferecer uma porta que bate na cara é pior do que não a oferecer."""
        client.force_login(staff_user)

        corpo = client.get(reverse("backoffice:overview")).content.decode()

        assert reverse("backoffice:assets") not in corpo

    def test_o_item_de_parceiros_tambem_e_filtrado(self, client, staff_user):
        """
        A mesma regra: desde a Etapa 11 a tela de Parceiros cobra
        `content.view_partner`, e o link ficou sem filtro por um momento.
        """
        client.force_login(staff_user)

        corpo = client.get(reverse("backoffice:overview")).content.decode()

        assert reverse("backoffice:partners") not in corpo


class TestCSRF:
    @pytest.mark.parametrize("rota", ["asset_activation", "asset_delete"])
    def test_post_sem_token_e_recusado(self, administradora, rota):
        imagem = criar_imagem()
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(administradora)

        assert sem_token.post(
            reverse(f"backoffice:{rota}", args=[imagem.pk])
        ).status_code == 403

    def test_enviar_sem_token_e_recusado(self, administradora):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(administradora)

        resposta = sem_token.post(NOVA, {"file": _gif(), "kind": Asset.Kind.HOME})

        assert resposta.status_code == 403
        assert not Asset.objects.exists()


# ===========================================================================
# 2. Envio -- e o que ele recusa
# ===========================================================================


class TestEnvio:
    def test_o_formulario_e_multipart(self, cliente):
        """
        Sem `enctype`, o navegador manda só o NOME do arquivo e o campo
        chega vazio no servidor, sem erro nenhum. É a falha mais
        silenciosa que um formulário de upload pode ter.
        """
        corpo = cliente.get(NOVA).content.decode()

        assert 'enctype="multipart/form-data"' in corpo

    def test_envia(self, cliente):
        resposta = cliente.post(
            NOVA,
            {"file": _gif(), "kind": Asset.Kind.PARTNER, "alt_text": "Marca", "is_active": "on"},
        )

        assert resposta.status_code == 302
        imagem = Asset.objects.get()
        assert imagem.alt_text == "Marca"
        assert imagem.kind == Asset.Kind.PARTNER
        assert imagem.file.name.endswith(".gif")

    def test_recusa_o_que_nao_e_imagem(self, cliente):
        """Um executável renomeado para .png: o Pillow não consegue abrir."""
        resposta = cliente.post(
            NOVA,
            {
                "file": _envio("virus.png", b"MZ\x90\x00 isto nao e imagem", "image/png"),
                "kind": Asset.Kind.OTHER,
            },
        )

        assert resposta.status_code == 200
        assert not Asset.objects.exists()

    def test_recusa_svg(self, cliente):
        """
        SVG não é bitmap e pode trazer `<script>` dentro. Servi-lo do
        nosso domínio seria XSS com as nossas credenciais.
        """
        resposta = cliente.post(
            NOVA,
            {"file": _envio("x.svg", SVG, "image/svg+xml"), "kind": Asset.Kind.OTHER},
        )

        assert resposta.status_code == 200
        assert not Asset.objects.exists()

    def test_recusa_arquivo_grande_demais(self, cliente):
        """
        Um GIF de verdade, grande de verdade.

        Forjar `.size` no objeto de envio nao funciona: o cliente de
        teste RECODIFICA o corpo multipart e o servidor mede o que
        chegou -- o teste passaria a medir a mentira, nao a regra. O
        preenchimento vai DEPOIS do terminador `;`, onde um leitor de GIF
        para de ler: continua sendo imagem valida, so grande.
        """
        resposta = cliente.post(
            NOVA,
            {
                "file": _envio("grande.gif", GIF + b"\x00" * TAMANHO_MAXIMO_DA_IMAGEM),
                "kind": Asset.Kind.OTHER,
            },
        )

        assert resposta.status_code == 200
        assert not Asset.objects.exists()
        assert "limite" in resposta.content.decode()

    def test_aceita_o_que_esta_dentro_do_limite(self, cliente):
        """O espelho: sem isto o teste acima passaria com um limite de zero."""
        resposta = cliente.post(
            NOVA,
            {
                "file": _envio("ok.gif", GIF + b"\x00" * 1024),
                "kind": Asset.Kind.OTHER,
            },
        )

        assert resposta.status_code == 302
        assert Asset.objects.count() == 1

    def test_sem_arquivo_nao_envia(self, cliente):
        resposta = cliente.post(NOVA, {"kind": Asset.Kind.OTHER})

        assert resposta.status_code == 200
        assert not Asset.objects.exists()

    def test_recusa_formato_valido_que_nao_esta_na_lista(self):
        """
        Um BMP: imagem de verdade, o Pillow abre sem reclamar -- e mesmo
        assim fora da lista.

        Os outros dois testes de recusa (executável e SVG) são pegos pelo
        `ImageField` sozinho, antes de a lista ser consultada. Sem este
        caso, apagar `FORMATOS_ACEITOS` inteira não quebraria teste
        nenhum, e a lista estaria ali sem conferir nada.
        """
        import io

        from PIL import Image

        from apps.content.forms import FormularioDeImagem

        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(buffer, "BMP")

        form = FormularioDeImagem(
            data={"kind": Asset.Kind.OTHER},
            files={"file": _envio("x.bmp", buffer.getvalue(), "image/bmp")},
        )

        assert not form.is_valid()
        assert "file" in form.errors
        assert "BMP" in str(form.errors["file"])

    def test_aceita_um_formato_da_lista(self):
        """O espelho: sem ele, o teste acima passaria recusando tudo."""
        import io

        from PIL import Image

        from apps.content.forms import FormularioDeImagem

        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(buffer, "PNG")

        form = FormularioDeImagem(
            data={"kind": Asset.Kind.OTHER},
            files={"file": _envio("x.png", buffer.getvalue(), "image/png")},
        )

        assert form.is_valid(), form.errors

    def test_os_formatos_aceitos_sao_bitmap(self):
        """SVG fora, e de propósito -- ver o docstring do módulo."""
        assert "SVG" not in FORMATOS_ACEITOS
        assert set(FORMATOS_ACEITOS) == {"PNG", "JPEG", "GIF", "WEBP"}


# ===========================================================================
# 3. A lista
# ===========================================================================


class TestLista:
    def test_sem_imagens_diz_que_nao_ha(self, cliente):
        assert "Nenhuma imagem enviada" in cliente.get(LISTA).content.decode()

    def test_mostra_a_imagem_e_o_texto_alternativo(self, cliente):
        imagem = criar_imagem(alt_text="Fachada")

        corpo = cliente.get(LISTA).content.decode()

        assert f'src="{imagem.file.url}"' in corpo
        assert "Fachada" in corpo

    def test_diz_quando_a_imagem_nao_esta_em_uso(self, cliente):
        criar_imagem()

        assert "Não está em uso" in cliente.get(LISTA).content.decode()

    def test_diz_que_esta_em_uso_por_um_parceiro(self, cliente):
        imagem = criar_imagem()
        Partner.objects.create(name="Padaria", logo=imagem)

        assert "um parceiro" in cliente.get(LISTA).content.decode()

    def test_diz_que_esta_em_uso_pela_pagina_inicial(self, cliente):
        imagem = criar_imagem()
        hero = PageSection.objects.get(page__key="home", key="hero")
        hero.image = imagem
        hero.save(update_fields=["image"])

        assert "uma parte da página inicial" in cliente.get(LISTA).content.decode()

    def test_quem_so_ve_nao_recebe_acao_que_nao_pode(self, cliente_leitora):
        criar_imagem()

        corpo = cliente_leitora.get(LISTA).content.decode()

        assert "Nova imagem" not in corpo
        assert "Remover" not in corpo
        assert "Desativar" not in corpo


# ===========================================================================
# 4. Alterar -- e a recusa do modelo
# ===========================================================================


class TestAlterar:
    def test_muda_o_texto_alternativo(self, cliente):
        imagem = criar_imagem(alt_text="antes")

        cliente.post(
            reverse("backoffice:asset_edit", args=[imagem.pk]),
            {"kind": Asset.Kind.HOME, "alt_text": "depois", "is_active": "on"},
        )

        imagem.refresh_from_db()
        assert imagem.alt_text == "depois"

    def test_nao_trocar_o_arquivo_mantem_o_que_esta_la(self, cliente):
        imagem = criar_imagem()
        antes = imagem.file.name

        cliente.post(
            reverse("backoffice:asset_edit", args=[imagem.pk]),
            {"kind": Asset.Kind.HOME, "alt_text": "x", "is_active": "on"},
        )

        imagem.refresh_from_db()
        assert imagem.file.name == antes

    def test_troca_o_arquivo(self, cliente):
        imagem = criar_imagem()
        antes = imagem.file.name

        cliente.post(
            reverse("backoffice:asset_edit", args=[imagem.pk]),
            {"file": _envio("outra.gif"), "kind": Asset.Kind.HOME, "is_active": "on"},
        )

        imagem.refresh_from_db()
        assert imagem.file.name != antes

    def test_recusa_trocar_o_arquivo_de_carta_finalizada(self, cliente, letter):
        """
        Trocar o arquivo mudaria um documento histórico em silêncio. O
        modelo recusa -- e a tela tem de EXPLICAR, não estourar 500.
        """
        from apps.letters.models import LetterAsset

        imagem = criar_imagem()
        LetterAsset.objects.create(letter=letter, asset=imagem)
        antes = imagem.file.name

        resposta = cliente.post(
            reverse("backoffice:asset_edit", args=[imagem.pk]),
            {"file": _envio("outra.gif"), "kind": Asset.Kind.HOME, "is_active": "on"},
        )

        assert resposta.status_code == 200
        assert "carta já finalizada" in resposta.content.decode()
        imagem.refresh_from_db()
        assert imagem.file.name == antes

    def test_o_aviso_de_uso_aparece_na_edicao(self, cliente):
        imagem = criar_imagem()
        Partner.objects.create(name="Padaria", logo=imagem)

        corpo = cliente.get(
            reverse("backoffice:asset_edit", args=[imagem.pk])
        ).content.decode()

        assert "está em uso em" in corpo


class TestSituacao:
    def test_desativa_e_deixa_de_ser_oferecida(self, cliente):
        imagem = criar_imagem()

        cliente.post(
            reverse("backoffice:asset_activation", args=[imagem.pk]), {"ativa": "0"}
        )

        imagem.refresh_from_db()
        assert not imagem.is_active

    def test_desativar_nao_tira_de_onde_ja_foi_escolhida(self, cliente, client):
        """
        Desativar é sobre OFERECER, não sobre publicar. Tirar do ar o que
        já está publicado é decisão de cada tela, não desta.
        """
        imagem = criar_imagem(alt_text="Fachada")
        hero = PageSection.objects.get(page__key="home", key="hero")
        hero.image = imagem
        hero.save(update_fields=["image"])

        cliente.post(
            reverse("backoffice:asset_activation", args=[imagem.pk]), {"ativa": "0"}
        )

        assert imagem.file.url in client.get(reverse("core:home")).content.decode()

    def test_get_nao_muda_situacao(self, cliente):
        imagem = criar_imagem()

        resposta = cliente.get(reverse("backoffice:asset_activation", args=[imagem.pk]))

        assert resposta.status_code == 405
        assert Asset.objects.get(pk=imagem.pk).is_active


# ===========================================================================
# 5. Remover -- e a recusa do banco
# ===========================================================================


class TestRemover:
    def test_o_get_so_pergunta(self, cliente):
        imagem = criar_imagem()

        corpo = cliente.get(
            reverse("backoffice:asset_delete", args=[imagem.pk])
        ).content.decode()

        assert "não tem volta" in corpo
        assert Asset.objects.filter(pk=imagem.pk).exists()

    def test_o_post_apaga(self, cliente):
        imagem = criar_imagem()

        cliente.post(reverse("backoffice:asset_delete", args=[imagem.pk]))

        assert not Asset.objects.filter(pk=imagem.pk).exists()

    def test_recusa_apagar_imagem_de_carta_finalizada(self, cliente, letter):
        """O PROTECT é do banco; a tela traduz a recusa, não a inventa."""
        from apps.letters.models import LetterAsset

        imagem = criar_imagem()
        LetterAsset.objects.create(letter=letter, asset=imagem)

        resposta = cliente.post(
            reverse("backoffice:asset_delete", args=[imagem.pk]), follow=True
        )

        assert Asset.objects.filter(pk=imagem.pk).exists()
        assert "não pode ser apagada" in resposta.content.decode()

    def test_apagar_nao_derruba_a_pagina_inicial(self, cliente, client):
        """SET_NULL: a parte volta à moldura vazia, que é um estado válido."""
        imagem = criar_imagem()
        hero = PageSection.objects.get(page__key="home", key="hero")
        hero.image = imagem
        hero.save(update_fields=["image"])

        cliente.post(reverse("backoffice:asset_delete", args=[imagem.pk]))

        resposta = client.get(reverse("core:home"))
        assert resposta.status_code == 200
        assert "img-slot" in resposta.content.decode()
        hero.refresh_from_db()
        assert hero.image_id is None

    def test_apagar_nao_derruba_o_parceiro(self, cliente, client):
        imagem = criar_imagem()
        parceiro = Partner.objects.create(name="Padaria", logo=imagem)

        cliente.post(reverse("backoffice:asset_delete", args=[imagem.pk]))

        parceiro.refresh_from_db()
        assert parceiro.logo_id is None
        assert client.get(reverse("core:home")).status_code == 200


# ===========================================================================
# 6. O catálogo de permissões
# ===========================================================================


class TestCatalogo:
    def test_as_quatro_estao_no_catalogo(self):
        from apps.accounts import admin_permissions

        chaves = {permissao.chave for permissao in admin_permissions.todas()}

        for codename in TODAS:
            assert f"content.{codename}" in chaves

    def test_a_tela_de_usuarios_as_oferece(self, client, administradora):
        gerencia = Permission.objects.get(
            content_type__app_label="accounts", codename="manage_users"
        )
        administradora.user_permissions.add(gerencia)
        pessoa = get_user_model().objects.get(pk=administradora.pk)
        client.force_login(pessoa)

        corpo = client.get(
            reverse("backoffice:user_detail", args=[pessoa.pk])
        ).content.decode()

        assert "Enviar imagens" in corpo
        assert "Remover imagens" in corpo


# ===========================================================================
# 7. O celular
# ===========================================================================


class TestCelular:
    """Mesma correção da tela de Parceiros -- ver o docstring de lá."""

    def test_a_tabela_e_so_do_desktop(self, cliente):
        criar_imagem()

        assert 'class="card table-wrap d-only"' in cliente.get(LISTA).content.decode()

    def test_ha_uma_lista_para_o_celular(self, cliente):
        criar_imagem(alt_text="Fachada")

        corpo = cliente.get(LISTA).content.decode()

        assert 'class="list m-only"' in corpo
        assert corpo.count("Fachada") >= 2

    def test_a_edicao_oferece_as_acoes_que_a_lista_movel_nao_tem(self, cliente):
        imagem = criar_imagem()

        corpo = cliente.get(
            reverse("backoffice:asset_edit", args=[imagem.pk])
        ).content.decode()

        assert reverse("backoffice:asset_activation", args=[imagem.pk]) in corpo
        assert reverse("backoffice:asset_delete", args=[imagem.pk]) in corpo

    def test_o_envio_novo_nao_oferece_acao_de_registro(self, cliente):
        corpo = cliente.get(NOVA).content.decode()

        assert "Desativar" not in corpo
        assert "Remover" not in corpo
