"""
A ponte entre `content.SiteSettings` e os templates.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. que a configuração volte a ser um modelo que ninguém lê -- era esse o
   estado antes desta etapa;
2. que a ponte comece a **gravar** no banco. Ela roda em toda página
   pública, inclusive num GET anônimo, e um GET não cria linha;
3. que o contexto cresça sozinho. O que um template alcança é o que
   alguém pode publicar sem pensar, então cada campo entra junto com a
   tela que o apresenta -- nunca "por precaução";
4. que administrar a configuração deixe de exigir permissão.
"""

import dataclasses

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.content.context_processors import GlobaisDoSite, globais
from apps.content.models import Asset, SiteSettings

pytestmark = pytest.mark.django_db

ADMIN_SITESETTINGS = reverse("admin:content_sitesettings_changelist")


def _gif():
    """O menor GIF válido -- o mesmo truque de `test_models.py`."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        "x.gif",
        b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
        b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
        content_type="image/gif",
    )


@pytest.fixture
def configuracao(db):
    """A configuração vigente, com logo e favicon."""
    logo = Asset.objects.create(key="logo", kind=Asset.Kind.LOGO, file=_gif())
    favicon = Asset.objects.create(key="favicon", kind=Asset.Kind.FAVICON, file=_gif())
    registro = SiteSettings.load()
    registro.site_name = "Desenrola Bélgica"
    registro.logo = logo
    registro.favicon = favicon
    registro.save()
    return registro


# ===========================================================================
# 1. O que a ponte devolve
# ===========================================================================


class TestGlobais:
    def test_le_a_configuracao_gravada(self, configuracao):
        resultado = globais()

        assert resultado.name == "Desenrola Bélgica"
        assert resultado.logo == configuracao.logo
        assert resultado.favicon == configuracao.favicon

    def test_sem_registro_devolve_os_padroes_do_modelo(self):
        """
        Nada de valores inventados: são os `default` declarados no
        próprio modelo, que é o que o administrador veria ao abrir a tela
        pela primeira vez.
        """
        assert SiteSettings.objects.count() == 0

        resultado = globais()

        assert resultado.name == SiteSettings._meta.get_field("site_name").default
        assert resultado.logo is None
        assert resultado.favicon is None

    def test_sem_registro_nao_grava_nada(self):
        """
        Isto roda em toda página pública. Um GET anônimo não pode criar
        linha em banco -- nem por `get_or_create` bem-intencionado.
        """
        globais()

        assert SiteSettings.objects.count() == 0

    def test_configuracao_sem_imagens_nao_quebra(self):
        SiteSettings.load()

        resultado = globais()

        assert resultado.logo is None
        assert resultado.favicon is None


# ===========================================================================
# 2. O contexto não expõe o que não precisa
# ===========================================================================


class TestSuperficieExposta:
    def test_expoe_exatamente_os_campos_previstos(self):
        """
        Cresce por etapa, junto com a tela que apresenta cada campo. Se
        este teste falhar, alguém acrescentou um campo -- e deve ter
        acrescentado a tela junto.

        Etapa A: nome, logo, favicon. Etapa C: as duas cores do tema.
        Etapa F: contato e redes sociais, junto com a tela de Sistema
        que os administra e o rodapé que os mostra.
        """
        nomes = {campo.name for campo in dataclasses.fields(GlobaisDoSite)}

        assert nomes == {
            "name",
            "logo",
            "favicon",
            "primary_color",
            "success_color",
            "contact",
            "social",
        }

    def test_nao_e_o_modelo_inteiro(self, configuracao):
        """
        Passar o `SiteSettings` deixaria qualquer template chegar a
        qualquer coluna -- inclusive as que ainda não têm tela.

        Contato e redes passaram a ser expostos na Etapa F, mas como
        RETRATO (`contact`, `social`), não como as colunas do modelo: o
        template alcança o que a tela de Sistema publica, e nada mais.
        """
        resultado = globais()

        assert not isinstance(resultado, SiteSettings)
        for coluna in (
            "contact_email",
            "contact_phone",
            "contact_address",
            "social_links",
            "site_name",
            "theme_primary_color",
        ):
            assert not hasattr(resultado, coluna)

    def test_e_imutavel(self, configuracao):
        """Um template não reescreve a configuração do site."""
        resultado = globais()

        with pytest.raises(dataclasses.FrozenInstanceError):
            resultado.name = "Outro"


# ===========================================================================
# 3. Chega ao template, de verdade
# ===========================================================================


class TestIntegracao:
    def test_o_contexto_chega_a_uma_pagina_publica(self, client, configuracao):
        resposta = client.get(reverse("core:home"))

        assert resposta.context["site_config"].name == "Desenrola Bélgica"

    def test_o_contexto_chega_a_uma_pagina_logada(self, auth_client, configuracao):
        resposta = auth_client.get(reverse("core:dashboard"))

        assert resposta.context["site_config"].name == "Desenrola Bélgica"

    def test_o_nome_do_site_aparece_no_titulo(self, client, staff_user, configuracao):
        """
        A prova de ponta a ponta: o `<title>` do Backoffice recebe o nome
        que está no banco, e não um literal no template.
        """
        client.force_login(staff_user)

        html = client.get(reverse("backoffice:overview")).content.decode()

        assert "Desenrola Bélgica</title>" in html
        assert "· Desenrola</title>" not in html

    def test_o_titulo_de_reserva_do_base_tambem_vem_do_banco(self, configuracao):
        """
        Hoje toda tela define o próprio `{% block title %}`, então o
        padrão de `base.html` não é exercitado por nenhuma página -- mas
        é o valor que uma tela nova herda se não definir nada, e tem de
        ser o nome do banco, não um literal.
        """
        from django.template import Context, Template

        saida = Template(
            "{% extends 'base.html' %}"
        ).render(Context({"site_config": globais()}))

        assert "<title>Desenrola Bélgica</title>" in saida

    def test_sem_registro_a_pagina_continua_de_pe(self, client):
        """Instalação nova, banco sem configuração: nada quebra."""
        resposta = client.get(reverse("core:home"))

        assert resposta.status_code == 200
        assert resposta.context["site_config"].name


# ===========================================================================
# 4. Não custa nada onde não é usado
# ===========================================================================


class TestCusto:
    def test_uma_consulta_quando_o_template_usa(
        self, client, staff_user, configuracao, django_assert_num_queries
    ):
        """
        `select_related` em logo e favicon: sem ele, mostrar os dois
        custaria três consultas em vez de uma.
        """
        client.force_login(staff_user)

        with django_assert_num_queries(1):
            globais()

    def test_nenhuma_consulta_quando_o_template_nao_usa(
        self, client, configuracao, django_assert_num_queries
    ):
        """
        `SimpleLazyObject`: a página que define o próprio `<title>` e não
        toca em `site` não paga consulta nenhuma por causa desta ponte.
        """
        from apps.content.context_processors import site

        with django_assert_num_queries(0):
            contexto = site(request=None)
            assert "site_config" in contexto


# ===========================================================================
# 5. Nada de segredo no contexto
# ===========================================================================


class TestSegredos:
    def test_a_configuracao_de_email_nao_entra_no_contexto(self, client, configuracao):
        """
        `core.EmailSettings` guarda a senha SMTP cifrada. Nada dela pode
        chegar a um template -- e este teste é o guarda-corpo.
        """
        from apps.core import mail

        configuracao_de_email = mail.configuracao()
        configuracao_de_email.host = "smtp.exemplo.com"
        configuracao_de_email.username = "mail@mail.com"
        configuracao_de_email.definir_senha("senha-de-mentira")
        configuracao_de_email.save()

        resposta = client.get(reverse("core:home"))
        corpo = resposta.content.decode()

        assert "senha-de-mentira" not in corpo
        assert configuracao_de_email.password_encrypted not in corpo
        assert "site_config" in resposta.context
        assert not hasattr(resposta.context["site_config"], "password_encrypted")

    def test_o_contexto_nao_carrega_dados_de_usuario(self, client, configuracao):
        """A ponte é de configuração PÚBLICA. Nada de pessoas nela."""
        resultado = globais()

        assert not hasattr(resultado, "user")
        assert not hasattr(resultado, "updated_by")


# ===========================================================================
# 6. Administrar a configuração exige permissão
# ===========================================================================


def _pessoa(email, nome, **extras):
    return get_user_model().objects.create_user(
        email=email, password="x", full_name=nome, **extras
    )


class TestPermissoes:
    """
    A tela de `SiteSettings` é o Django Admin. Esta etapa não criou
    permissão nenhuma: usa as que o Django já gera para o modelo, e que
    já eram exigidas. Os testes existem porque "já existe" não é o mesmo
    que "está sendo conferido".
    """

    def test_anonimo_nao_entra(self, client):
        resposta = client.get(ADMIN_SITESETTINGS)

        assert resposta.status_code == 302
        assert "/admin/login/" in resposta.url

    def test_usuario_comum_nao_entra(self, client, user):
        client.force_login(user)

        resposta = client.get(ADMIN_SITESETTINGS)

        assert resposta.status_code == 302

    def test_staff_sem_a_permissao_e_recusado(self, client):
        """`is_staff` abre a porta do Admin, não a desta tela."""
        pessoa = _pessoa("staff@mail.com", "Íris Nunes", is_staff=True)
        client.force_login(pessoa)

        assert client.get(ADMIN_SITESETTINGS).status_code == 403

    def test_com_a_permissao_de_ver_entra(self, client):
        from django.contrib.auth.models import Permission

        pessoa = _pessoa("editora@mail.com", "Joana Reis", is_staff=True)
        pessoa.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="content", codename="view_sitesettings"
            )
        )
        client.force_login(get_user_model().objects.get(pk=pessoa.pk))

        assert client.get(ADMIN_SITESETTINGS).status_code == 200

    def test_superusuario_entra(self, client):
        chefe = get_user_model().objects.create_superuser(
            email="chefe@mail.com", password="x", full_name="Helena Braga"
        )
        client.force_login(chefe)

        assert client.get(ADMIN_SITESETTINGS).status_code == 200

    def test_a_ponte_nao_depende_de_permissao(self, client, configuracao):
        """
        Ler a configuração é público: é o nome do site, não um segredo.
        Quem não pode ADMINISTRAR continua vendo as páginas normalmente.
        """
        resposta = client.get(reverse("core:home"))

        assert resposta.status_code == 200
        assert resposta.context["site_config"].name == "Desenrola Bélgica"

    def test_a_ponte_nao_trouxe_permissao_propria(self):
        """
        O contexto global não confere nada: ele lê `SiteSettings` para
        todo mundo, inclusive para quem nem entrou -- por isso esta
        ponte não pediu permissão nenhuma.

        `content.change_sitesettings` está no catálogo desde a Etapa F,
        e não é dela: é a permissão que o Django já gerava para o
        modelo e que a administração do Django já cobrava. Quem a
        confere é a tela de Sistema (ver
        `apps/content/tests/test_sistema.py`), não este processador.
        """
        from apps.accounts import admin_permissions

        de_configuracao = {
            permissao.chave
            for permissao in admin_permissions.todas()
            if "sitesettings" in permissao.chave
        }

        assert de_configuracao == {"content.change_sitesettings"}
