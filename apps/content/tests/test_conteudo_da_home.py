"""
O conteúdo da Home, editável no Backoffice.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a tela vire um editor de JSON.** Os campos vêm de
   `section_schema`: se alguém trocar isso por um `Textarea` com o
   objeto dentro, os testes de campo caem;
2. **Que salvar apague o que a tela não mostra.** O ícone de cada cartão
   não é editável -- é desenho -- e tem de atravessar um salvamento
   intacto;
3. **Que se invente tradução.** Idioma sem texto é um estado legítimo, e
   a Home cai no idioma padrão em vez de mostrar vazio. Nada é
   fabricado, e não há porcentagem de tradução;
4. **Que o idioma venha do cliente sem conferência.** `?idioma=` acaba
   num filtro de banco e num rótulo de tela;
5. **Que uma seção a mais custe uma consulta a mais.**
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.content import section_schema, services
from apps.content.models import Page, PageSection, PageSectionTranslation, Partner

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")
LISTA = reverse("backoffice:content")


def secao(chave):
    return PageSection.objects.get(page__key="home", key=chave)


def url_da_secao(chave, idioma=None):
    url = reverse("backoffice:content_section", args=[secao(chave).pk])
    return f"{url}?idioma={idioma}" if idioma else url


def texto(chave, idioma="pt"):
    """O conteúdo gravado daquela seção, naquele idioma."""
    traducao = secao(chave).translations.filter(language=idioma).first()
    return traducao.content if traducao else {}


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


@pytest.fixture
def editora(db):
    """Vê e edita o conteúdo."""
    return _com_permissoes("view_pagesection", "change_pagesection")


@pytest.fixture
def leitora(db):
    """Vê, mas não edita."""
    return _com_permissoes("view_pagesection", email="leitora@mail.com")


@pytest.fixture
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


# ===========================================================================
# 1. A declaração dos campos
# ===========================================================================


class TestDeclaracao:
    def test_toda_secao_da_home_sabe_o_que_editar(self):
        for atual in PageSection.objects.filter(page__key="home"):
            assert section_schema.editavel(atual), atual.key

    def test_as_duas_secoes_do_mesmo_tipo_tem_campos_diferentes(self):
        """
        `trust` e `how` são as duas `features`, e não mostram os mesmos
        textos. Declarar por tipo obrigaria a inventar a união das duas.
        """
        assert secao("trust").kind == secao("how").kind == "features"

        de_trust = {c.chave for c in section_schema.campos_da_secao(secao("trust"))}
        de_how = {c.chave for c in section_schema.campos_da_secao(secao("how"))}

        assert de_trust != de_how

    def test_a_tela_nao_mostra_nome_tecnico(self):
        """
        Quem administra lê "Banner superior", não "hero". Os nomes
        técnicos continuam sendo as chaves em banco -- e só isso.
        """
        for chave, esperado in (
            ("hero", "Banner superior"),
            ("trust", "Destaques abaixo do Banner superior"),
            ("cta", "Mini Banner"),
            ("navbar", "Barra superior"),
            ("footer", "Rodapé"),
        ):
            assert str(section_schema.nome_amigavel(secao(chave))) == esperado

    def test_declara_exatamente_o_que_o_template_le(self):
        """
        Se a declaração e o template divergirem, a tela oferece um campo
        que a página ignora -- ou esconde um que ela mostra.

        A varredura cobre TODOS os templates públicos, e não só a Home:
        desde a Etapa 11 a barra superior e o rodapé também leem
        `secoes.`. E, para o Banner, o campo pode estar em qualquer um
        dos desenhos -- basta que algum deles o declare.
        """
        import pathlib
        import re

        raiz = pathlib.Path(__file__).resolve().parents[3]
        arquivos = [
            raiz / "templates" / "core" / "home.html",
            raiz / "templates" / "components" / "site_nav.html",
            raiz / "templates" / "components" / "site_footer.html",
        ]
        arquivos += list((raiz / "templates" / "core" / "secoes").glob("*.html"))

        lidas = set()
        for caminho in arquivos:
            if caminho.exists():
                lidas |= set(
                    re.findall(r"secoes\.(\w+)\.(\w+)", caminho.read_text(encoding="utf-8"))
                )

        assert lidas, "nenhum template lê `secoes.` -- a varredura quebrou"

        for chave_da_secao, chave_do_campo in lidas:
            declarada = section_schema.SECOES.get(chave_da_secao)
            assert declarada is not None, chave_da_secao

            declarados = {campo.chave for campo in declarada.campos}
            for layout in declarada.layouts:
                declarados |= {campo.chave for campo in layout.campos}

            assert chave_do_campo in declarados, f"{chave_da_secao}.{chave_do_campo}"

    def test_o_icone_nao_e_editavel(self):
        """Desenho, não conteúdo."""
        for chave in ("trust", "how"):
            lista = section_schema.campos_da_secao(secao(chave))[-1]
            assert "icon" not in {c.chave for c in lista.campos}

    def test_secao_sem_declaracao_nao_e_editavel(self):
        pagina = Page.objects.get(key="home")
        estranha = PageSection.objects.create(
            # `contact`, e nao `faq`: desde as Perguntas frequentes, `faq`
            # e chave DECLARADA -- e `secao_declarada` cai no tipo quando
            # nao acha a chave, entao esta secao passaria a ser editavel.
            page=pagina, key="inventada", kind=PageSection.Kind.CONTACT, order=99
        )

        assert section_schema.editavel(estranha) is False


# ===========================================================================
# 2. O serviço que a Home usa
# ===========================================================================


class TestServico:
    def test_devolve_as_secoes_pela_chave(self):
        """
        A barra superior e o rodapé deixaram de ser marcação fixa na
        Etapa 11 e viraram seções de verdade, com ativação e conteúdo
        próprios; as Perguntas frequentes entraram na revisão final.
        """
        conteudo = services.secoes_da_pagina("home")

        assert set(conteudo) == {
            "navbar",
            "hero",
            "trust",
            "partners",
            "how",
            "faq",
            "cta",
            "footer",
        }

    def test_secao_inativa_nao_entra(self):
        PageSection.objects.filter(page__key="home", key="cta").update(is_active=False)

        assert "cta" not in services.secoes_da_pagina("home")

    def test_idioma_sem_traducao_cai_no_padrao(self):
        conteudo = services.secoes_da_pagina("home", language="nl")

        assert conteudo["hero"]["title"] == texto("hero")["title"]

    def test_a_traducao_do_idioma_ganha(self):
        PageSectionTranslation.objects.create(
            section=secao("hero"), language="nl", content={"title": "Nederlands"}
        )

        conteudo = services.secoes_da_pagina("home", language="nl")

        assert conteudo["hero"]["title"] == "Nederlands"

    def test_pagina_inexistente_devolve_vazio(self):
        assert services.secoes_da_pagina("nao-existe") == {}

    def test_pagina_inativa_devolve_vazio(self):
        Page.objects.filter(key="home").update(is_active=False)

        assert services.secoes_da_pagina("home") == {}

    def test_conteudo_que_nao_e_objeto_vira_vazio(self):
        """JSON é livre: pode chegar uma lista. A Home não pode quebrar."""
        traducao = secao("hero").translations.get(language="pt")
        traducao.content = ["isto", "nao", "e", "um", "objeto"]
        traducao.save()

        assert services.secoes_da_pagina("home")["hero"] == {}

    def test_mais_secoes_nao_custam_mais_consultas(self):
        pagina = Page.objects.get(key="home")

        def consultas():
            with CaptureQueriesContext(connection) as capturadas:
                services.secoes_da_pagina("home")
            return len(capturadas)

        poucas = consultas()
        for indice in range(6):
            nova = PageSection.objects.create(
                page=pagina, key=f"extra{indice}", kind=PageSection.Kind.TEXT, order=50 + indice
            )
            PageSectionTranslation.objects.create(
                section=nova, language="pt", content={"title": "x"}
            )

        assert consultas() == poucas


# ===========================================================================
# 3. A porta do Backoffice
# ===========================================================================


class TestAcesso:
    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(LISTA)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_usuario_comum_e_recusado(self, auth_client):
        assert auth_client.get(LISTA).status_code == 403

    def test_backoffice_sozinho_nao_basta(self, client, staff_user):
        """Entrar na área administrativa é uma coisa; ver o conteúdo é outra."""
        client.force_login(staff_user)

        assert client.get(LISTA).status_code == 403

    def test_quem_pode_ver_entra(self, client, leitora):
        client.force_login(leitora)

        assert client.get(LISTA).status_code == 200

    def test_quem_so_ve_nao_grava(self, client, leitora):
        """A URL continua digitável -- a recusa é no servidor."""
        client.force_login(leitora)

        resposta = client.post(url_da_secao("hero"), {"title": "Invadido", "idioma": "pt"})

        assert resposta.status_code == 403
        assert texto("hero")["title"] != "Invadido"

    def test_quem_so_ve_nao_oculta_secao(self, client, leitora):
        client.force_login(leitora)
        url = reverse("backoffice:content_activation", args=[secao("cta").pk])

        resposta = client.post(url, {"ativa": "0"})

        assert resposta.status_code == 403
        assert secao("cta").is_active is True

    def test_o_menu_so_oferece_a_quem_pode_ver(self, client, leitora, staff_user):
        client.force_login(staff_user)
        sem = client.get(reverse("backoffice:overview")).content.decode()
        client.force_login(leitora)
        com = client.get(reverse("backoffice:overview")).content.decode()

        assert f'href="{LISTA}"' not in sem
        assert f'href="{LISTA}"' in com

    def test_sem_csrf_nao_grava(self, editora):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(editora)

        resposta = sem_token.post(url_da_secao("hero"), {"title": "Invadido"})

        assert resposta.status_code == 403
        assert texto("hero")["title"] != "Invadido"

    def test_get_nao_altera_a_situacao(self, cliente):
        url = reverse("backoffice:content_activation", args=[secao("cta").pk])

        assert cliente.get(url).status_code == 405


# ===========================================================================
# 4. A edição
# ===========================================================================


class TestEdicao:
    def test_a_lista_mostra_as_secoes(self, cliente):
        """
        Até a Etapa 11 a Central listava a CHAVE de cada seção
        ("hero", "trust", "cta"). Agora mostra o nome que quem
        administra entende -- e a chave técnica ficou onde sempre
        deveria estar: só no banco.

        A cobertura completa da Central está em
        `test_central_de_conteudo.py`; aqui fica a garantia de que a
        tela de edição continua alcançável a partir dela.
        """
        corpo = cliente.get(LISTA).content.decode()

        for nome in (
            "Banner superior",
            "Destaques abaixo do Banner superior",
            "Nossos Parceiros",
            "Como funciona",
            "Mini Banner",
        ):
            assert nome in corpo

    def test_o_formulario_tem_campos_e_nao_json(self, cliente):
        corpo = cliente.get(url_da_secao("hero")).content.decode()

        assert 'name="title"' in corpo
        assert 'name="lead"' in corpo
        assert "badge_label" in corpo
        # Nada de um campo com o objeto inteiro dentro.
        assert 'name="content"' not in corpo

    def test_salvar_altera_a_home(self, cliente, client):
        cliente.post(
            url_da_secao("hero"),
            {**texto("hero"), "idioma": "pt", "title": "Novo título"},
        )

        assert texto("hero")["title"] == "Novo título"
        assert "Novo título" in client.get(HOME).content.decode()

    def test_salvar_preserva_o_que_a_tela_nao_mostra(self, cliente):
        """
        O ícone de cada cartão não é editável. Um salvamento não pode
        apagá-lo.
        """
        antes = [card["icon"] for card in texto("how")["cards"]]

        cliente.post(
            url_da_secao("how"),
            {
                "idioma": "pt",
                "title": "Como funciona?",
                "lead": "Veja como é simples.",
                "cards__0__title": "1. Outro",
                "cards__0__text": "Descrição.",
                "cards__1__title": "2. Outro",
                "cards__1__text": "Descrição.",
                "cards__2__title": "3. Outro",
                "cards__2__text": "Descrição.",
            },
        )

        depois = texto("how")["cards"]
        assert [card["icon"] for card in depois] == antes
        assert depois[0]["title"] == "1. Outro"

    def test_campo_vazio_e_aceito(self, cliente):
        """Apagar um texto é decisão editorial, não erro de preenchimento."""
        cliente.post(
            url_da_secao("hero"), {**texto("hero"), "idioma": "pt", "badge_note": ""}
        )

        assert texto("hero")["badge_note"] == ""

    def test_secao_sem_declaracao_nao_abre(self, cliente):
        pagina = Page.objects.get(key="home")
        estranha = PageSection.objects.create(
            # `contact`, e nao `faq`: desde as Perguntas frequentes, `faq`
            # e chave DECLARADA -- e `secao_declarada` cai no tipo quando
            # nao acha a chave, entao esta secao passaria a ser editavel.
            page=pagina, key="inventada", kind=PageSection.Kind.CONTACT, order=99
        )

        resposta = cliente.get(
            reverse("backoffice:content_section", args=[estranha.pk]), follow=True
        )

        assert "não tem campos definidos" in resposta.content.decode()

    def test_secao_de_outra_pagina_nao_abre(self, cliente):
        """O `pk` vem do cliente: a seção é procurada DENTRO da Home."""
        outra = Page.objects.create(key="outra", name="Outra")
        de_fora = PageSection.objects.create(
            page=outra, key="hero", kind=PageSection.Kind.HERO
        )

        resposta = cliente.get(reverse("backoffice:content_section", args=[de_fora.pk]))

        assert resposta.status_code == 404

    def test_secao_de_outra_pagina_nao_muda_de_situacao(self, cliente):
        outra = Page.objects.create(key="outra", name="Outra")
        de_fora = PageSection.objects.create(
            page=outra, key="cta", kind=PageSection.Kind.CTA
        )

        resposta = cliente.post(
            reverse("backoffice:content_activation", args=[de_fora.pk]), {"ativa": "0"}
        )

        assert resposta.status_code == 404
        de_fora.refresh_from_db()
        assert de_fora.is_active is True


# ===========================================================================
# 5. Os quatro idiomas
# ===========================================================================


class TestIdiomas:
    def test_a_tela_oferece_os_quatro(self, cliente):
        corpo = cliente.get(LISTA).content.decode()

        for codigo in ("pt", "fr", "nl", "en"):
            assert f"?idioma={codigo}" in corpo

    def test_gravar_em_outro_idioma_cria_a_traducao(self, cliente):
        assert secao("hero").translations.filter(language="fr").count() == 0

        cliente.post(
            url_da_secao("hero", "fr"),
            {"idioma": "fr", "title": "Générez votre lettre", "lead": ""},
        )

        assert texto("hero", "fr")["title"] == "Générez votre lettre"

    def test_gravar_num_idioma_nao_mexe_no_outro(self, cliente):
        antes = texto("hero")["title"]

        cliente.post(url_da_secao("hero", "fr"), {"idioma": "fr", "title": "Français"})

        assert texto("hero")["title"] == antes
        assert texto("hero", "fr")["title"] == "Français"

    def test_a_tela_diz_quando_falta_traducao(self, cliente):
        corpo = cliente.get(url_da_secao("hero", "nl")).content.decode()

        assert "ainda não tem texto neste idioma" in corpo

    def test_falta_de_traducao_aparece_como_falta(self, cliente):
        """
        Sem texto em neerlandês, a lista diz que falta -- não mostra o
        texto português no lugar, nem calcula quanto está traduzido.
        """
        quantas = PageSection.objects.filter(page__key="home").count()
        corpo = cliente.get(f"{LISTA}?idioma=nl").content.decode()

        assert corpo.count("Sem tradução") == quantas
        assert "Preenchida" not in corpo
        assert texto("hero")["title"] not in corpo

    @pytest.mark.parametrize("lixo", ["de", "'; DROP TABLE", "", "PT"])
    def test_idioma_invalido_cai_no_padrao(self, cliente, lixo):
        """`?idioma=` é entrada do cliente e acaba num filtro de banco."""
        resposta = cliente.get(f"{LISTA}?idioma={lixo}")

        assert resposta.status_code == 200
        assert resposta.context["idioma"] == "pt"


# ===========================================================================
# 6. Mostrar e ocultar
# ===========================================================================


class TestSituacao:
    def test_ocultar_tira_da_home(self, cliente, client):
        cliente.post(
            reverse("backoffice:content_activation", args=[secao("cta").pk]),
            {"ativa": "0", "idioma": "pt"},
        )

        assert secao("cta").is_active is False
        assert "Facilite a visita" not in client.get(HOME).content.decode()

    def test_mostrar_traz_de_volta(self, cliente, client):
        PageSection.objects.filter(page__key="home", key="cta").update(is_active=False)

        cliente.post(
            reverse("backoffice:content_activation", args=[secao("cta").pk]),
            {"ativa": "1", "idioma": "pt"},
        )

        assert secao("cta").is_active is True
        assert "Facilite a visita" in client.get(HOME).content.decode()

    def test_ocultar_nao_apaga_o_texto(self, cliente):
        antes = texto("cta")

        cliente.post(
            reverse("backoffice:content_activation", args=[secao("cta").pk]),
            {"ativa": "0", "idioma": "pt"},
        )

        assert texto("cta") == antes


# ===========================================================================
# 7. A Home pública continua inteira
# ===========================================================================


class TestHomePublica:
    def test_o_texto_vem_do_cms(self, client):
        traducao = secao("cta").translations.get(language="pt")
        traducao.content = {**traducao.content, "title": "Texto do banco"}
        traducao.save()

        assert "Texto do banco" in client.get(HOME).content.decode()

    @pytest.mark.parametrize("prefixo", ["/fr/", "/nl/", "/en/"])
    def test_os_prefixos_de_idioma_continuam_atendidos(self, client, prefixo):
        """
        A interface é só em português desde a Etapa 4.1: os outros
        prefixos são trazidos para /pt/ pelo middleware. O conteúdo em
        quatro idiomas fica pronto no CMS para o dia em que isso mudar.
        """
        resposta = client.get(prefixo, follow=True)

        assert resposta.status_code == 200
        assert resposta.redirect_chain[-1][0] == "/pt/"

    def test_sem_conteudo_a_home_nao_quebra(self, client):
        PageSectionTranslation.objects.filter(section__page__key="home").delete()

        resposta = client.get(HOME)

        assert resposta.status_code == 200

    def test_os_parceiros_continuam_vindo_do_proprio_modelo(self, client):
        Partner.objects.create(name="JD-Print")

        corpo = client.get(HOME).content.decode()

        assert "JD-Print" in corpo
        assert "Nossos parceiros" in corpo

    def test_o_contador_continua_independente(self, client):
        corpo = client.get(HOME).content.decode()

        assert '<span class="banner-contador-valor">0</span>' in corpo

    def test_o_conteudo_e_escapado(self, client, cliente):
        """Texto de administrador continua sendo texto, não marcação."""
        cliente.post(
            url_da_secao("cta"),
            {**texto("cta"), "idioma": "pt", "title": "<script>alert(1)</script>"},
        )

        corpo = client.get(HOME).content.decode()

        assert "<script>alert(1)</script>" not in corpo
        assert "&lt;script&gt;" in corpo

    def test_o_orcamento_de_consultas_da_home_nao_cresce(self, client):
        """Uma seção a mais não pode custar uma consulta a mais."""
        from django.core.cache import cache

        pagina = Page.objects.get(key="home")

        def consultas():
            cache.clear()
            with CaptureQueriesContext(connection) as capturadas:
                client.get(HOME)
            return len(capturadas)

        poucas = consultas()
        for indice in range(5):
            nova = PageSection.objects.create(
                page=pagina, key=f"extra{indice}", kind=PageSection.Kind.TEXT, order=60 + indice
            )
            PageSectionTranslation.objects.create(
                section=nova, language="pt", content={"title": "x"}
            )

        assert consultas() == poucas


# ===========================================================================
# 8. As permissões no catálogo
# ===========================================================================


class TestCatalogo:
    def test_as_duas_estao_no_catalogo(self):
        """
        Entram agora porque agora existe tela que as confere -- que é a
        regra escrita no próprio catálogo.
        """
        from apps.accounts import admin_permissions

        chaves = {permissao.chave for permissao in admin_permissions.todas()}

        assert "content.view_pagesection" in chaves
        assert "content.change_pagesection" in chaves

    def test_a_tela_de_usuarios_as_oferece(self, client, editora):
        gerencia = Permission.objects.get(
            content_type__app_label="accounts", codename="manage_users"
        )
        editora.user_permissions.add(gerencia)
        editora = get_user_model().objects.get(pk=editora.pk)
        client.force_login(editora)

        corpo = client.get(
            reverse("backoffice:user_detail", args=[editora.pk])
        ).content.decode()

        assert "Editar o conteúdo do site" in corpo
