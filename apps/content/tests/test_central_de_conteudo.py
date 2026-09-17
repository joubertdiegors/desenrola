"""
A Central de Conteúdo: a página de cima para baixo, em linguagem humana.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que nome técnico chegue a quem administra.** "hero", "trust",
   "cta" continuam sendo as chaves em banco -- e só isso. A tela diz
   "Banner superior", "Destaques abaixo do Banner superior",
   "Mini Banner";
2. **Que a miniatura vire desenho paralelo.** Ela é a Home de verdade
   num `<iframe>`: mesmo parcial, mesmo contexto, mesmo CSS. Se alguém
   trocar por captura de tela ou por marcação própria, ela envelhece na
   primeira edição de texto;
3. **Que a miniatura mostre a parte errada.** Cada quadro aponta para a
   prévia da SUA parte;
4. **Que a prévia vire porta aberta.** Ela desenha conteúdo
   administrativo, inclusive de parte desativada -- exige a mesma
   permissão de ver o conteúdo;
5. **Que apareça botão sem função.**
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.content import section_schema
from apps.content.models import PageSection

pytestmark = pytest.mark.django_db

CENTRAL = reverse("backoffice:content")

# Os nomes que o produto decidiu apresentar, e a ordem dos grupos.
NOMES = {
    "navbar": "Barra superior",
    "hero": "Banner superior",
    "trust": "Destaques abaixo do Banner superior",
    "partners": "Nossos Parceiros",
    "how": "Como funciona",
    "faq": "Perguntas frequentes",
    "cta": "Mini Banner",
    "footer": "Rodapé",
}
GRUPOS = {
    "topo": ["navbar", "hero", "trust"],
    "meio": ["partners", "how", "faq"],
    "final": ["cta", "footer"],
}


def secao(chave):
    return PageSection.objects.get(page__key="home", key=chave)


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


@pytest.fixture
def com_parceiro(db):
    """
    A seção de parceiros só aparece quando há parceiro cadastrado -- e
    está certo: título e grade vazios seriam promessa não cumprida.
    Quem pergunta pelo DESENHO dela precisa de um.
    """
    from apps.content.models import Partner

    return Partner.objects.create(name="Parceiro de teste", is_active=True)


# ===========================================================================
# 1. Topo / Meio / Final
# ===========================================================================


class TestAgrupamento:
    def test_os_tres_grupos_aparecem_na_ordem_da_pagina(self, cliente):
        corpo = cliente.get(CENTRAL).content.decode()

        posicoes = [corpo.index(f"<h2>{nome}</h2>") for nome in ("Topo", "Meio", "Final")]

        assert posicoes == sorted(posicoes)

    @pytest.mark.parametrize(("grupo", "chaves"), GRUPOS.items())
    def test_cada_parte_esta_no_seu_grupo(self, cliente, grupo, chaves):
        resposta = cliente.get(CENTRAL)

        do_grupo = next(g for g in resposta.context["grupos"] if g["chave"] == grupo)
        assert [p["secao"].key for p in do_grupo["partes"]] == chaves

    def test_dentro_do_grupo_vale_a_ordem_da_pagina(self, cliente):
        resposta = cliente.get(CENTRAL)

        for grupo in resposta.context["grupos"]:
            ordens = [p["secao"].order for p in grupo["partes"]]
            assert ordens == sorted(ordens), grupo["chave"]

    def test_grupo_sem_parte_nao_vira_cabecalho_vazio(self, cliente):
        """Um título de grupo sem nada embaixo seria promessa vazia."""
        PageSection.objects.filter(page__key="home", key__in=["cta", "footer"]).delete()

        resposta = cliente.get(CENTRAL)

        assert [g["chave"] for g in resposta.context["grupos"]] == ["topo", "meio"]
        assert "<h2>Final</h2>" not in resposta.content.decode()

    def test_TODAS_as_partes_declaradas_aparecem(self, cliente):
        """
        TODAS, e não um número.

        Eram sete quando este teste nasceu, e viraram oito com as
        Perguntas frequentes. A regra é que a Central mostre tudo o que
        o schema declara -- a contagem do dia é consequência.
        """
        from apps.content import section_schema

        resposta = cliente.get(CENTRAL)

        mostradas = [
            p["secao"].key for g in resposta.context["grupos"] for p in g["partes"]
        ]

        assert set(mostradas) == set(section_schema.SECOES)
        assert set(mostradas) == set(NOMES)


# ===========================================================================
# 2. Linguagem humana
# ===========================================================================


class TestNomes:
    @pytest.mark.parametrize(("chave", "nome"), NOMES.items())
    def test_o_nome_apresentado_e_o_amigavel(self, cliente, chave, nome):
        corpo = cliente.get(CENTRAL).content.decode()

        assert f"<h3>{nome}</h3>" in corpo

    def test_nenhum_nome_tecnico_como_titulo(self, cliente):
        corpo = cliente.get(CENTRAL).content.decode()

        for tecnico in ("hero", "trust", "cta", "features", "PageSection", "layout key"):
            assert f"<h3>{tecnico}</h3>" not in corpo

    def test_a_tela_nao_fala_de_json_nem_de_schema(self, cliente):
        corpo = cliente.get(CENTRAL).content.decode()

        for jargao in ("JSON", "schema", "section_schema", "kind="):
            assert jargao not in corpo

    def test_cada_parte_tem_descricao(self, cliente):
        resposta = cliente.get(CENTRAL)

        for grupo in resposta.context["grupos"]:
            for parte in grupo["partes"]:
                assert str(parte["descricao"]).strip(), parte["secao"].key
                assert str(parte["descricao"]) in resposta.content.decode()

    def test_as_descricoes_sao_diferentes_entre_si(self, cliente):
        """Descrição repetida não explica nada."""
        resposta = cliente.get(CENTRAL)

        textos = [
            str(p["descricao"]) for g in resposta.context["grupos"] for p in g["partes"]
        ]
        assert len(set(textos)) == len(textos)


# ===========================================================================
# 3. A miniatura é a Home
# ===========================================================================


class TestMiniaturas:
    def test_ha_uma_miniatura_por_parte(self, cliente):
        corpo = cliente.get(CENTRAL).content.decode()

        assert corpo.count("bo-parte-miniatura") == len(NOMES)

    @pytest.mark.parametrize("chave", list(NOMES))
    def test_a_miniatura_aponta_para_a_previa_da_sua_parte(self, cliente, chave):
        corpo = cliente.get(CENTRAL).content.decode()
        esperado = reverse("backoffice:content_preview", args=[secao(chave).pk])

        assert f'src="{esperado}?viewport=miniatura"' in corpo

    def test_a_miniatura_pede_o_modo_miniatura(self, cliente):
        """
        O quadro tem 220px mas precisa mostrar o desenho de DESKTOP.
        `viewport=miniatura` é o único modo que força a largura de
        referência -- os três aparelhos do editor deixam o CSS responder
        à largura real do quadro.
        """
        corpo = cliente.get(CENTRAL).content.decode()

        assert corpo.count("?viewport=miniatura") == len(NOMES)
        for aparelho in ("desktop", "tablet", "mobile"):
            assert f"?viewport={aparelho}" not in corpo

    def test_nao_ha_captura_de_tela_nem_imagem_estatica(self, cliente):
        """
        A miniatura não pode ser um arquivo: ele envelheceria na
        primeira edição de texto.
        """
        corpo = cliente.get(CENTRAL).content.decode()
        quadros = re.findall(r'<div class="bo-parte-miniatura">(.*?)</div>', corpo, re.S)

        assert quadros
        for quadro in quadros:
            assert "<iframe" in quadro
            assert "<img" not in quadro

    @pytest.mark.parametrize(
        ("chave", "marca"),
        [
            ("navbar", "topo-publico-barra"),
            ("hero", 'class="hero container"'),
            ("trust", "home-selos"),
            ("partners", "partners-grid"),
            ("how", "how-grid"),
            ("cta", "home-cta"),
            ("footer", "site-footer"),
        ],
    )
    def test_a_previa_desenha_a_parte_certa(self, cliente, com_parceiro, chave, marca):
        url = reverse("backoffice:content_preview", args=[secao(chave).pk])

        corpo = cliente.get(url).content.decode()

        assert marca in corpo

    def test_a_previa_usa_o_css_do_site(self, cliente):
        """Mesmo CSS -- senão não é a Home, é uma imitação dela."""
        url = reverse("backoffice:content_preview", args=[secao("hero").pk])

        corpo = cliente.get(url).content.decode()

        for folha in ("css/base.css", "css/components.css", "css/layout.css"):
            assert folha in corpo

    def test_a_previa_acompanha_o_texto_do_cms(self, cliente):
        """
        A prova de que não há desenho paralelo: mudou o conteúdo, mudou
        a miniatura, sem nenhum passo de geração.
        """
        from apps.content.models import PageSectionTranslation

        traducao = PageSectionTranslation.objects.get(
            section=secao("cta"), language="pt"
        )
        traducao.content = {**traducao.content, "title": "Texto novo em folha"}
        traducao.save()

        url = reverse("backoffice:content_preview", args=[secao("cta").pk])

        assert "Texto novo em folha" in cliente.get(url).content.decode()

    def test_a_previa_acompanha_o_desenho_do_banner(self, cliente):
        url = reverse("backoffice:content_preview", args=[secao("hero").pk])

        assert 'class="hero container"' in cliente.get(url).content.decode()

        PageSection.objects.filter(page__key="home", key="hero").update(
            layout="somente_texto"
        )

        assert "hero-texto" in cliente.get(url).content.decode()

    def test_a_previa_desenha_ate_parte_desativada(self, cliente):
        """
        Quem administra precisa ver o que está prestes a religar. A Home
        pública continua sem mostrar -- são perguntas diferentes.
        """
        PageSection.objects.filter(page__key="home", key="cta").update(is_active=False)
        url = reverse("backoffice:content_preview", args=[secao("cta").pk])

        assert "home-cta" in cliente.get(url).content.decode()

    def test_parte_de_outra_pagina_nao_tem_previa(self, cliente):
        from apps.content.models import Page

        outra = Page.objects.create(key="outra", name="Outra")
        de_fora = PageSection.objects.create(
            page=outra, key="hero", kind=PageSection.Kind.HERO
        )

        url = reverse("backoffice:content_preview", args=[de_fora.pk])

        assert cliente.get(url).status_code == 404


# ===========================================================================
# 4. Ativo / inativo
# ===========================================================================


class TestSituacao:
    def test_mostra_ativo_e_inativo(self, cliente):
        PageSection.objects.filter(page__key="home", key="cta").update(is_active=False)

        corpo = cliente.get(CENTRAL).content.decode()

        assert "Ativo" in corpo
        assert "Inativo" in corpo

    def test_desativar_da_central_tira_da_home(self, cliente, client):
        cliente.post(
            reverse("backoffice:content_activation", args=[secao("cta").pk]),
            {"ativa": "0", "idioma": "pt"},
        )

        assert secao("cta").is_active is False
        assert "cta-banner" not in client.get(reverse("core:home")).content.decode()

    def test_a_parte_desligada_fica_evidente(self, cliente):
        PageSection.objects.filter(page__key="home", key="cta").update(is_active=False)

        corpo = cliente.get(CENTRAL).content.decode()

        assert "is-desligada" in corpo

    def test_desativar_nao_apaga_conteudo(self, cliente):
        from apps.content.models import PageSectionTranslation

        antes = PageSectionTranslation.objects.get(
            section=secao("cta"), language="pt"
        ).content

        cliente.post(
            reverse("backoffice:content_activation", args=[secao("cta").pk]),
            {"ativa": "0", "idioma": "pt"},
        )

        depois = PageSectionTranslation.objects.get(
            section=secao("cta"), language="pt"
        ).content
        assert depois == antes


# ===========================================================================
# 5. Permissões e ausência de botão morto
# ===========================================================================


class TestAcesso:
    def test_anonimo_nao_ve_a_central(self, client):
        resposta = client.get(CENTRAL)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_usuario_comum_e_recusado(self, auth_client):
        assert auth_client.get(CENTRAL).status_code == 403

    def test_a_previa_exige_a_mesma_permissao(self, client, auth_client, staff_user):
        url = reverse("backoffice:content_preview", args=[secao("hero").pk])

        assert auth_client.get(url).status_code == 403

        outro = Client()
        outro.force_login(staff_user)
        assert outro.get(url).status_code == 403

    def test_quem_so_ve_nao_recebe_botao_de_acao(self, client, db):
        leitora = _pessoa(
            "leitora@mail.com",
            ("core", "access_backoffice"),
            ("content", "view_pagesection"),
        )
        client.force_login(leitora)

        corpo = client.get(CENTRAL).content.decode()

        assert "Desativar" not in corpo
        assert "Ativar" not in corpo
        assert "não tem permissão para alterá-lo" in corpo

    def test_nenhum_botao_sem_funcao(self, cliente):
        """
        Todo botão desta tela ou envia um formulário, ou é um link com
        destino. Nenhum `<button type="button">` solto.
        """
        corpo = cliente.get(CENTRAL).content.decode()
        miolo = corpo[corpo.index("bo_main") if "bo_main" in corpo else 0 :]

        assert 'type="button"' not in miolo.split("</main>")[0]

    def test_nenhum_link_morto(self, cliente):
        corpo = cliente.get(CENTRAL).content.decode()

        assert 'href="#"' not in corpo


# ===========================================================================
# 6. A Home pública não mudou
# ===========================================================================


class TestHomeIntacta:
    def test_as_partes_continuam_na_ordem(self, client, com_parceiro):
        corpo = client.get(reverse("core:home")).content.decode()
        miolo = corpo[corpo.index("<main") : corpo.index("</main>")]

        # A ordem da referencia visual: banner, selos, Como funciona,
        # Parceiros, Mini Banner. "Como funciona" passou a vir ANTES de
        # Parceiros -- e o que faz a alternancia de fundos cair certa.
        na_ordem = (
            'class="hero container"',
            "home-selos",
            "how-grid",
            "partners-grid",
            "home-cta",
        )
        posicoes = [miolo.index(marca) for marca in na_ordem]
        assert posicoes == sorted(posicoes)

    def test_parte_desativada_nao_deixa_espaco_vazio(self, client):
        """Some o elemento inteiro, não só o texto dentro dele."""
        PageSection.objects.filter(page__key="home", key="trust").update(is_active=False)

        miolo = client.get(reverse("core:home")).content.decode()

        assert "home-selos" not in miolo

    def test_a_declaracao_cobre_todas_as_partes_da_home(self):
        """
        Uma parte sem declaração apareceria na Central como "não sei
        editar". Hoje não há nenhuma.
        """
        for parte in PageSection.objects.filter(page__key="home"):
            assert section_schema.secao_declarada(parte) is not None, parte.key
