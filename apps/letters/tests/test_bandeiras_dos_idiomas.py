"""
As bandeiras dos idiomas, agora administráveis.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que trocar uma bandeira exija mexer no CSS.** Antes elas eram
   `background` de `.lang-flag-fr`, `.lang-flag-pt` e afins -- três
   faixas de cor desenhadas à mão. Quem administra não edita CSS;
2. **Que nasça um segundo sistema de imagens.** A bandeira enviada é um
   `content.Asset` como qualquer outra imagem do site, com a MESMA
   validação e a MESMA limpeza de órfãs;
3. **Que a bandeira padrão se perca.** Sem imagem enviada, o assistente
   continua desenhando a de sempre -- instalar a novidade não muda nada
   para ninguém;
4. **Que um SVG com `<script>` vire bandeira.** O arquivo passa pelo
   Pillow e pela lista de formatos, como todo upload do projeto;
5. **Que a tela aceite um idioma que o produto não tem.** O código vem
   pela URL, e URL é coisa do cliente;
6. **Que apagar uma bandeira apague a imagem de outra pessoa.** A órfã
   só some quando NADA mais a usa.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.content.models import Asset, PageSection
from apps.letters import services
from apps.letters.models import LanguageFlag

pytestmark = pytest.mark.django_db

TELA = reverse("backoffice:languages")


@pytest.fixture(autouse=True)
def _media_isolada(settings, tmp_path):
    """Sem isto a suíte gravaria arquivos de teste no `media/` do repositório."""
    settings.MEDIA_ROOT = tmp_path


GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def _gif(nome="bandeira.gif"):
    return SimpleUploadedFile(nome, GIF, content_type="image/gif")


def _svg(nome="bandeira.svg"):
    conteudo = b'<svg onload="alert(1)"><script>alert(1)</script></svg>'
    return SimpleUploadedFile(nome, conteudo, content_type="image/svg+xml")


def _nao_e_imagem():
    return SimpleUploadedFile("fingida.png", b"MZ\x90\x00nao-sou-imagem", content_type="image/png")


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
        "editora-bandeiras@mail.com",
        ("core", "access_backoffice"),
        ("letters", "change_documentlanguagesettings"),
    )


@pytest.fixture
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


def url(codigo):
    return reverse("backoffice:language_flag", args=[codigo])


def enviar(cliente, codigo="fr", arquivo=None):
    return cliente.post(url(codigo), {"bandeira": arquivo or _gif()}, follow=True)


# ===========================================================================
# 1. O estado inicial
# ===========================================================================


class TestSemNadaEnviado:
    def test_nao_ha_bandeira_cadastrada_ao_instalar(self):
        """A novidade nasce vazia: quem não enviar nada não vê mudança."""
        assert LanguageFlag.objects.count() == 0

    def test_o_assistente_continua_com_a_bandeira_desenhada(self):
        """
        `flag_url` vazia é o sinal de "desenhe a de sempre" -- o
        template escolhe o `<span>` com a classe CSS.
        """
        meta = services.meta_do_idioma("fr")

        assert meta["flag_url"] == ""
        assert meta["flag"] == "lang-flag-fr"

    def test_a_tela_lista_os_quatro_idiomas_mesmo_sem_imagem(self, cliente):
        """
        A lista vem de `settings.LANGUAGES`, não da tabela: é justamente
        no idioma sem linha que alguém vai querer enviar a primeira.
        """
        html = cliente.get(TELA).content.decode()

        for codigo in ("pt", "fr", "nl", "en"):
            assert url(codigo) in html


# ===========================================================================
# 2. Enviar
# ===========================================================================


class TestEnviar:
    def test_o_envio_cria_um_asset_da_biblioteca(self, cliente):
        """Não existe modelo de imagem paralelo: é o `Asset` de sempre."""
        antes = Asset.objects.count()

        enviar(cliente)

        assert Asset.objects.count() == antes + 1
        assert LanguageFlag.objects.get(language="fr").asset is not None

    def test_o_assistente_passa_a_usar_a_imagem(self, cliente):
        enviar(cliente)

        meta = services.meta_do_idioma("fr")

        assert meta["flag_url"], "a etapa 5 continuaria desenhando a padrão"
        assert meta["flag_url"].endswith(".gif")

    def test_so_o_idioma_enviado_muda(self, cliente):
        enviar(cliente, "fr")

        assert services.meta_do_idioma("fr")["flag_url"]
        assert services.meta_do_idioma("pt")["flag_url"] == ""

    def test_enviar_de_novo_substitui_e_nao_acumula(self, cliente):
        enviar(cliente)
        primeira = LanguageFlag.objects.get(language="fr").asset_id

        enviar(cliente)
        segunda = LanguageFlag.objects.get(language="fr").asset_id

        assert segunda != primeira
        assert LanguageFlag.objects.filter(language="fr").count() == 1
        assert not Asset.objects.filter(pk=primeira).exists(), "a antiga ficou órfã"

    def test_sem_arquivo_avisa_em_vez_de_gravar_vazio(self, cliente):
        resposta = cliente.post(url("fr"), {}, follow=True)

        assert resposta.status_code == 200
        assert not LanguageFlag.objects.filter(language="fr", asset__isnull=False).exists()


# ===========================================================================
# 3. O arquivo é conferido no servidor
# ===========================================================================


class TestOArquivoEConferido:
    def test_svg_com_script_e_recusado(self, cliente):
        """
        SVG é XML executável. A lista de formatos não o inclui, e este
        teste existe para que ninguém a "melhore" incluindo.
        """
        enviar(cliente, arquivo=_svg())

        assert Asset.objects.count() == 0
        assert services.meta_do_idioma("fr")["flag_url"] == ""

    def test_arquivo_que_nao_abre_no_pillow_e_recusado(self, cliente):
        """Nome e Content-Type de imagem não bastam."""
        enviar(cliente, arquivo=_nao_e_imagem())

        assert Asset.objects.count() == 0

    def test_a_view_usa_o_validador_compartilhado(self):
        """
        Não é uma segunda regra de tamanho/formato escrita aqui: é a
        MESMA função de todo upload do projeto. Se alguém trocá-la por
        uma cópia, este teste cai.
        """
        import inspect

        from apps.letters.backoffice_views import backoffice_language_flag

        fonte = inspect.getsource(backoffice_language_flag)

        assert "_validar_arquivo_de_imagem" in fonte


# ===========================================================================
# 4. Remover
# ===========================================================================


class TestRemover:
    def test_remover_devolve_a_bandeira_padrao(self, cliente):
        enviar(cliente)

        cliente.post(url("fr"), {"remover": "1"}, follow=True)

        assert services.meta_do_idioma("fr")["flag_url"] == ""

    def test_remover_apaga_a_imagem_orfa(self, cliente):
        enviar(cliente)
        imagem = LanguageFlag.objects.get(language="fr").asset_id

        cliente.post(url("fr"), {"remover": "1"}, follow=True)

        assert not Asset.objects.filter(pk=imagem).exists()

    def test_remover_nao_apaga_imagem_que_outro_registro_usa(self, cliente):
        """
        A MESMA verificação da Biblioteca decide aqui. Uma imagem que um
        banner também usa não pode sumir porque a bandeira deixou de
        apontar para ela.
        """
        enviar(cliente)
        imagem = LanguageFlag.objects.get(language="fr").asset
        secao = PageSection.objects.first()
        assert secao is not None
        secao.image = imagem
        secao.save(update_fields=["image"])

        cliente.post(url("fr"), {"remover": "1"}, follow=True)

        assert Asset.objects.filter(pk=imagem.pk).exists()

    def test_a_biblioteca_conta_a_bandeira_como_uso(self, cliente):
        """
        Quem for apagar a imagem pela Biblioteca precisa saber que ela é
        a bandeira de um idioma ANTES de tentar.
        """
        from apps.content.backoffice_views import _onde_esta_em_uso

        enviar(cliente)
        imagem = LanguageFlag.objects.get(language="fr").asset

        assert _onde_esta_em_uso(imagem)


# ===========================================================================
# 5. Quem pode
# ===========================================================================


class TestPermissao:
    def test_sem_a_permissao_nao_envia(self, db):
        pessoa = _pessoa("curiosa-bandeiras@mail.com", ("core", "access_backoffice"))
        c = Client()
        c.force_login(pessoa)

        resposta = c.post(url("fr"), {"bandeira": _gif()})

        assert resposta.status_code == 403
        assert Asset.objects.count() == 0

    def test_anonimo_nao_envia(self, client):
        resposta = client.post(url("fr"), {"bandeira": _gif()})

        assert resposta.status_code in (302, 403)
        assert Asset.objects.count() == 0

    def test_sem_permissao_a_tela_nao_oferece_o_envio(self, db):
        pessoa = _pessoa("curiosa2-bandeiras@mail.com", ("core", "access_backoffice"))
        c = Client()
        c.force_login(pessoa)

        html = c.get(TELA).content.decode()

        assert url("fr") not in html

    def test_get_nao_muda_nada(self, cliente):
        """A troca é uma ação: só POST."""
        resposta = cliente.get(url("fr"))

        assert resposta.status_code == 405


# ===========================================================================
# 6. O código do idioma vem do cliente
# ===========================================================================


class TestOCodigoEConferido:
    def test_idioma_que_o_produto_nao_tem_e_recusado(self, cliente):
        resposta = cliente.post(url("de"), {"bandeira": _gif()})

        assert resposta.status_code == 404
        assert Asset.objects.count() == 0
        assert LanguageFlag.objects.count() == 0


# ===========================================================================
# 7. A tela
# ===========================================================================


class TestATela:
    def test_a_imagem_enviada_aparece_na_tela(self, cliente):
        enviar(cliente)

        html = cliente.get(TELA).content.decode()

        assert services.meta_do_idioma("fr")["flag_url"] in html

    def test_a_tela_nao_esta_dentro_do_formulario_de_idiomas(self, cliente):
        """
        Formulário dentro de formulário não existe em HTML: o envio da
        bandeira ficaria inerte, ou levaria o POST para a URL errada.
        """
        html = cliente.get(TELA).content.decode()
        fim_do_form = html.index("</form>", html.index("Salvar idiomas"))

        assert html.index(url("fr")) > fim_do_form
