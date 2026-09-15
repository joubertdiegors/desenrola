"""
As cores, a logomarca e o favicon do CMS chegam ao site.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **A volta do `localStorage`.** A aparência era decidida por um script
   que lia o navegador de quem estava mexendo -- a escolha do
   administrador não saía da máquina dele. Há testes que afirmam a
   ausência do mecanismo, e não só a presença do novo;
2. **Injeção de CSS.** As duas cores são interpoladas dentro de um
   `<style>`, onde o escape do template não protege: um `}` no valor
   fecharia a regra. Toda cor passa por `HEX_COLOR_VALIDATOR` no caminho
   de saída;
3. **Uma segunda lista de cores.** Tudo deriva de `--p` e `--s` por
   `color-mix`; se alguém reintroduzir valores fixos, a cor configurada
   deixa de valer em parte do site;
4. **Página sem identidade.** Banco vazio, logo ausente, favicon
   ausente: tudo continua de pé com o padrão do produto.
"""

import pathlib

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.content.context_processors import globais
from apps.content.models import Asset, SiteSettings

pytestmark = pytest.mark.django_db

RAIZ = pathlib.Path(__file__).resolve().parents[3]
HOME = reverse("core:home")

PADRAO_PRIMARIA = SiteSettings._meta.get_field("theme_primary_color").default
PADRAO_SUCESSO = SiteSettings._meta.get_field("theme_success_color").default

# Telas de todas as cascas do produto: publica, autenticada e
# administrativa. Se a cor chega nas três, chega em todas.
TELAS_PUBLICAS = [HOME, reverse("accounts:login"), reverse("accounts:signup")]


def _gif():
    return SimpleUploadedFile(
        "x.gif",
        b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
        b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
        content_type="image/gif",
    )


@pytest.fixture
def configuracao(db):
    return SiteSettings.load()


def _com_cores(primaria="#6b3fd6", sucesso="#0f8f8a"):
    registro = SiteSettings.load()
    registro.theme_primary_color = primaria
    registro.theme_success_color = sucesso
    registro.save()
    return registro


# ===========================================================================
# 1. As cores no SiteSettings
# ===========================================================================


class TestCoresNoModelo:
    def test_os_padroes_sao_os_do_projeto(self):
        registro = SiteSettings.load()

        assert registro.theme_primary_color == PADRAO_PRIMARIA
        assert registro.theme_success_color == PADRAO_SUCESSO

    def test_sem_registro_valem_os_padroes(self):
        assert SiteSettings.objects.count() == 0

        resultado = globais()

        assert resultado.primary_color == PADRAO_PRIMARIA
        assert resultado.success_color == PADRAO_SUCESSO

    def test_a_cor_cadastrada_e_a_que_sai(self):
        _com_cores("#6b3fd6", "#0f8f8a")

        resultado = globais()

        assert resultado.primary_color == "#6b3fd6"
        assert resultado.success_color == "#0f8f8a"

    @pytest.mark.parametrize("invalida", ["vermelho", "#FFF", "#12345", "rgb(0,0,0)"])
    def test_o_formulario_recusa_o_que_nao_e_hexadecimal(self, invalida):
        """A validação que já existia no modelo, conferida."""
        registro = SiteSettings.load()
        registro.theme_primary_color = invalida

        with pytest.raises(ValidationError):
            registro.full_clean()


# ===========================================================================
# 2. As cores chegam à página
# ===========================================================================


class TestCoresNaPagina:
    @pytest.mark.parametrize("url", TELAS_PUBLICAS)
    def test_a_cor_sai_em_variavel_css(self, client, url):
        html = client.get(url).content.decode()

        assert f"--p:{PADRAO_PRIMARIA}" in html
        assert f"--s:{PADRAO_SUCESSO}" in html

    def test_mudar_no_banco_muda_a_pagina(self, client):
        antes = client.get(HOME).content.decode()
        _com_cores("#6b3fd6", "#0f8f8a")
        depois = client.get(HOME).content.decode()

        assert "--p:#1a5fd6" in antes
        assert "--p:#6b3fd6" in depois
        assert "--s:#0f8f8a" in depois

    def test_a_cor_vem_depois_das_folhas_de_estilo(self, client):
        """
        `base.css` declara as mesmas variáveis em `:root`. Com a mesma
        especificidade, quem vem por último vence -- se o `<style>`
        subir para antes dos `<link>`, a cor configurada deixa de valer.
        """
        html = client.get(HOME).content.decode()

        assert html.index("css/base.css") < html.index("--p:")
        assert html.index("css/layout.css") < html.index("--p:")

    def test_a_barra_do_navegador_acompanha(self, client):
        _com_cores("#6b3fd6")

        html = client.get(HOME).content.decode()

        assert '<meta name="theme-color" content="#6b3fd6">' in html

    def test_a_cor_chega_ao_backoffice(self, client, staff_user):
        _com_cores("#6b3fd6")
        client.force_login(staff_user)

        html = client.get(reverse("backoffice:overview")).content.decode()

        assert "--p:#6b3fd6" in html

    def test_tudo_deriva_das_duas_variaveis(self):
        """
        `--navy`, `--p10`, `--p20` e os componentes saem de `--p`/`--s`
        por `color-mix`. Se alguém reintroduzir valores fixos, a cor
        configurada passa a valer só em parte do site.
        """
        base = (RAIZ / "static" / "css" / "base.css").read_text(encoding="utf-8")

        for derivada in ("--navy", "--p10", "--p20"):
            inicio = base.index(f"{derivada}:")
            assert "var(--p)" in base[inicio : inicio + 80]


# ===========================================================================
# 3. Nada de injeção pelo `<style>`
# ===========================================================================


class TestInjecao:
    @pytest.mark.parametrize(
        "malicioso",
        [
            "} body{display:none} .x{",
            "#1a5fd6;} html{--p:red}",
            "red",
            "</style><script>alert(1)</script>",
            "",
        ],
    )
    def test_valor_invalido_no_banco_nao_chega_a_pagina(self, client, malicioso):
        """
        O validador do modelo só roda em `full_clean()`; um `save()`
        programático passa por cima. Por isso a conferência se repete no
        caminho de saída -- e o que não for `#rrggbb` cai no padrão.
        """
        registro = SiteSettings.load()
        registro.theme_primary_color = malicioso
        registro.save(update_fields=["theme_primary_color"])

        html = client.get(HOME).content.decode()

        assert f"--p:{PADRAO_PRIMARIA}" in html
        assert "display:none" not in html
        assert "<script>alert(1)</script>" not in html

    def test_a_pagina_nao_quebra_com_cor_invalida(self, client):
        registro = SiteSettings.load()
        registro.theme_primary_color = "lixo"
        registro.save(update_fields=["theme_primary_color"])

        assert client.get(HOME).status_code == 200


# ===========================================================================
# 4. A logomarca
# ===========================================================================


class TestLogo:
    def test_sem_logo_sai_a_marca_desenhada(self, client):
        html = client.get(HOME).content.decode()

        assert 'class="logo' in html
        assert "logo-kicker" in html
        assert "<img class=\"logo-img" not in html

    def test_com_logo_sai_a_imagem(self, client):
        imagem = Asset.objects.create(
            key="logo", kind=Asset.Kind.LOGO, file=_gif(), alt_text="Desenrola"
        )
        registro = SiteSettings.load()
        registro.logo = imagem
        registro.save()

        html = client.get(HOME).content.decode()

        assert f'src="{imagem.file.url}"' in html
        assert 'alt="Desenrola"' in html
        assert "logo-kicker" not in html

    def test_a_imagem_tem_texto_alternativo_mesmo_sem_alt_cadastrado(self, client):
        """Cai no nome do site -- logotipo sem nome acessível é um link mudo."""
        imagem = Asset.objects.create(key="logo", kind=Asset.Kind.LOGO, file=_gif())
        registro = SiteSettings.load()
        registro.logo = imagem
        registro.save()

        html = client.get(HOME).content.decode()

        assert f'alt="{registro.site_name}"' in html

    def test_o_nome_do_site_aparece_na_marca_desenhada(self, client):
        registro = SiteSettings.load()
        registro.site_name = "Outro Nome"
        registro.save()

        html = client.get(HOME).content.decode()

        assert "Outro Nome</span>" in html

    def test_a_mesma_marca_em_todas_as_cascas(self, auth_client, staff_user):
        """
        Público, autenticado e administrativo usam o mesmo componente.

        `Client` próprio para o anônimo: a fixture `auth_client` É o
        `client`, já autenticado -- e a Home redireciona quem está
        logado, devolvendo corpo vazio.
        """
        from django.test import Client

        imagem = Asset.objects.create(key="logo", kind=Asset.Kind.LOGO, file=_gif())
        registro = SiteSettings.load()
        registro.logo = imagem
        registro.save()

        publica = Client().get(HOME).content.decode()
        logada = auth_client.get(reverse("core:dashboard")).content.decode()
        administrativo = Client()
        administrativo.force_login(staff_user)
        admin = administrativo.get(reverse("backoffice:overview")).content.decode()

        for html in (publica, logada, admin):
            assert f'src="{imagem.file.url}"' in html


# ===========================================================================
# 5. O favicon
# ===========================================================================


class TestFavicon:
    def test_sem_favicon_fica_o_padrao(self, client):
        html = client.get(HOME).content.decode()

        assert "img/favicon.svg" in html

    def test_com_favicon_sai_o_cadastrado(self, client):
        imagem = Asset.objects.create(key="fav", kind=Asset.Kind.FAVICON, file=_gif())
        registro = SiteSettings.load()
        registro.favicon = imagem
        registro.save()

        html = client.get(HOME).content.decode()

        assert f'<link rel="icon" href="{imagem.file.url}">' in html
        assert "img/favicon.svg" not in html

    def test_o_favicon_cadastrado_nao_leva_type_fixo(self, client):
        """
        O arquivo pode ser PNG, SVG ou ICO. Anunciar `image/svg+xml` para
        um PNG faria o navegador recusar o ícone.
        """
        imagem = Asset.objects.create(key="fav", kind=Asset.Kind.FAVICON, file=_gif())
        registro = SiteSettings.load()
        registro.favicon = imagem
        registro.save()

        html = client.get(HOME).content.decode()
        inicio = html.index('<link rel="icon"')

        assert "type=" not in html[inicio : html.index(">", inicio)]


# ===========================================================================
# 6. O mecanismo antigo não voltou
# ===========================================================================


class TestSemLocalStorage:
    def test_o_arquivo_de_tema_nao_existe_mais(self):
        assert not (RAIZ / "static" / "js" / "theme.js").exists()

    @pytest.mark.parametrize("url", TELAS_PUBLICAS)
    def test_nenhuma_pagina_le_o_navegador_para_decidir_a_cor(self, client, url):
        html = client.get(url).content.decode()

        assert "localStorage" not in html
        assert "desenrola.theme" not in html
        assert "theme.js" not in html

    def test_as_classes_de_tema_sairam_do_css(self):
        """
        `.t-roxo`, `.s-teal`: eram aplicadas ao `<html>` pelo script. Sem
        ninguém para aplicá-las, seriam CSS morto -- e um convite a
        alguém reativar o mecanismo.
        """
        base = (RAIZ / "static" / "css" / "base.css").read_text(encoding="utf-8")

        for classe in (".t-roxo {", ".t-verde {", ".s-teal {", ".s-ambar {"):
            assert classe not in base

    def test_o_site_do_django_nao_sombreia_a_nossa_configuracao(self, client):
        """
        `LoginView` e `LogoutView` do Django poem um `site` PROPRIO no
        contexto (o objeto de `django.contrib.sites`). Enquanto a nossa
        chave se chamava `site`, a da view vencia e a tela de entrar
        ficava sem cor -- em silencio. Por isso a nossa e `site_config`.
        """
        html = client.get(reverse("accounts:login")).content.decode()

        assert f"--p:{PADRAO_PRIMARIA}" in html

    def test_a_cor_nao_depende_de_javascript(self, client):
        """
        Vem renderizada do servidor: sem script, sem espera e sem piscada
        entre o primeiro paint e a cor certa.
        """
        _com_cores("#6b3fd6")

        html = client.get(HOME).content.decode()
        cabecalho = html[: html.index("</head>")]

        assert "--p:#6b3fd6" in cabecalho
        assert "<script" not in cabecalho


# ===========================================================================
# 7. A tela de Aparência do Backoffice
# ===========================================================================


class TestTelaDeAparencia:
    @pytest.fixture
    def html(self, client, staff_user):
        _com_cores("#6b3fd6", "#0f8f8a")
        client.force_login(staff_user)
        return client.get(reverse("backoffice:appearance")).content.decode()

    def test_mostra_as_cores_publicadas(self, html):
        assert "#6b3fd6" in html
        assert "#0f8f8a" in html

    def test_diz_onde_se_edita(self, html):
        """
        Não finge gerenciar o que não gerencia: aponta para o Django
        Admin, que é onde a edição acontece nesta etapa.
        """
        assert reverse("admin:content_sitesettings_changelist") in html

    def test_nao_oferece_mais_botoes_que_nao_publicam(self, html):
        assert "data-theme-primary" not in html
        assert "data-theme-success" not in html

    def test_exige_o_backoffice(self, client, user):
        client.force_login(user)

        assert client.get(reverse("backoffice:appearance")).status_code == 403

    def test_esta_tela_continua_sem_editar_nada(self):
        """
        A tela de aparência não tem formulário nem rota de gravação:
        quem edita cor, logo e favicon é o Django Admin.

        O catálogo ganhou `content.change_sitesettings` na Etapa F, mas
        por causa da tela de SISTEMA -- que de fato a confere. Aparência
        continua sem criar permissão própria, e é isso que se afirma
        aqui: nenhuma permissão do catálogo aponta para esta view.
        """
        from apps.accounts import admin_permissions

        apontam_para_aparencia = [
            permissao.chave
            for permissao in admin_permissions.todas()
            if "appearance" in permissao.aplicada_em
        ]

        assert apontam_para_aparencia == []

    def test_esta_tela_nao_aceita_gravacao(self, client, staff_user):
        """Somente leitura: um POST aqui não tem o que fazer."""
        client.force_login(staff_user)

        resposta = client.post(reverse("backoffice:appearance"), {"site_name": "Invadido"})

        assert resposta.status_code == 200
        assert SiteSettings.load().site_name != "Invadido"
