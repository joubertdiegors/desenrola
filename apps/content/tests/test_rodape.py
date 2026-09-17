"""
O rodapé como conteúdo rico: o que se escreve no Backoffice é o que o
site desenha -- passando por uma lista fechada.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que HTML cru do editor chegue à página.** `<script>`, `on*`,
   `javascript:`, `<iframe>`, `style` com `url(`: nada disso sobrevive
   ao sanitizador -- nem gravado, nem desenhado;
2. **Que o rodapé vire uma segunda fonte de verdade.** Nome, contato,
   redes e páginas legais entram por ATALHOS; o HTML padrão não grava
   dado nenhum;
3. **Que um link leve a lugar nenhum.** Página legal sem texto, e-mail
   em branco: o `<a>` inteiro sai;
4. **Que a prévia mostre um rodapé diferente do público.** Os dois
   passam pelo mesmo parcial e pelo mesmo renderizador;
5. **Que a tela perca o editor, o interruptor ou a prévia** -- ou ganhe
   um controle que não faz nada;
6. **Que o antigo sistema de blocos volte pela porta dos fundos.**
"""

import datetime
import pathlib

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.content import rodape
from apps.content.models import (
    ContentBlock,
    ContentTranslation,
    PageSection,
    PageSectionTranslation,
    SiteSettings,
)

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")
RAIZ = pathlib.Path(__file__).resolve().parents[3]


def config():
    return SiteSettings.load()


def secao():
    return PageSection.objects.get(page__key="home", key="footer")


def traducao():
    t, _criada = PageSectionTranslation.objects.get_or_create(
        section=secao(), language="pt", defaults={"content": {}}
    )
    return t


def escrever(html):
    t = traducao()
    t.content = {**(t.content or {}), "html": html}
    t.save(update_fields=["content"])
    return t


def publicar_privacidade():
    bloco, _criado = ContentBlock.objects.get_or_create(
        key="legal.privacy_policy", defaults={"kind": ContentBlock.Kind.TEXT}
    )
    ContentTranslation.objects.update_or_create(
        block=bloco, language="pt", defaults={"content": "Texto da política."}
    )


def rodape_html(client, url=HOME):
    html = client.get(url).content.decode()
    if 'class="site-footer"' not in html:
        return ""
    inicio = html.index('class="site-footer"')
    return html[inicio : html.index("</footer>", inicio)]


def url_do_editor():
    return reverse("backoffice:content_section", args=[secao().pk])


def url_da_previa():
    return reverse("backoffice:content_preview", args=[secao().pk])


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
        "editora-rodape@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_pagesection"),
        ("content", "change_pagesection"),
    )


@pytest.fixture
def leitora(db):
    return _pessoa(
        "leitora-rodape@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_pagesection"),
    )


@pytest.fixture
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


def _payload(html):
    return {"idioma": "pt", "html": html}


# ===========================================================================
# 1. O sanitizador: a lista fechada
# ===========================================================================


class TestSanitizador:
    @pytest.mark.parametrize(
        "veneno",
        [
            "<script>alert(1)</script>",
            '<img src="x" onerror="alert(1)">',
            '<a href="javascript:alert(1)">x</a>',
            '<a href="java\tscript:alert(1)">x</a>',
            '<a href="data:text/html,x">x</a>',
            '<p onclick="alert(1)">x</p>',
            '<div style="background:url(javascript:alert(1))">x</div>',
            '<iframe src="https://x"></iframe>',
            '<svg onload="alert(1)"><path d="M1 1"/></svg>',
            "<style>body{display:none}</style>",
            '<a href="https://x" target="_blank" rel="opener">x</a>',
        ],
    )
    def test_nada_executavel_sobrevive(self, veneno):
        limpo = rodape.sanitizar(veneno)

        for marca in ("script", "onerror", "onclick", "onload", "javascript:", "data:",
                      "iframe", "url(", "<style", 'rel="opener"'):
            assert marca not in limpo, (veneno, limpo)

    def test_o_que_o_editor_produz_passa_inteiro(self):
        marcacao = (
            '<h3 style="text-align:center">Marca</h3>'
            '<p style="text-align:center"><a href="https://x.example" target="_blank" '
            'rel="noopener noreferrer">Site</a> <a href="/pt/parceiros/">Parceiros</a></p>'
            '<ul><li><strong>a</strong> <em>b</em> <u>c</u></li></ul>'
            '<blockquote>d</blockquote><hr>'
            '<p><font size="2">© 2026</font></p>'
        )

        assert rodape.sanitizar(marcacao) == marcacao

    def test_e_idempotente(self):
        sujo = '<p style="text-align:center;color:red">a &amp; b</p><b>aberto'
        uma = rodape.sanitizar(sujo)

        assert rodape.sanitizar(uma) == uma

    def test_tag_desconhecida_some_e_o_texto_fica(self):
        assert rodape.sanitizar("<marquee>fica</marquee>") == "fica"

    def test_nova_aba_exige_noopener(self):
        limpo = rodape.sanitizar('<a href="https://x" target="_blank">x</a>')

        assert 'rel="noopener noreferrer"' in limpo

    def test_so_estilos_da_lista(self):
        limpo = rodape.sanitizar(
            '<p style="text-align:center;position:fixed;color:#10275c;top:0">x</p>'
        )

        assert "text-align:center" in limpo
        assert "color:#10275c" in limpo
        assert "position" not in limpo
        assert "top:" not in limpo

    def test_os_atalhos_passam_como_endereco_de_link(self):
        assert '<a href="{url_termos}">' in rodape.sanitizar('<a href="{url_termos}">T</a>')
        assert 'href="mailto:{email_contato}"' in rodape.sanitizar(
            '<a href="mailto:{email_contato}">C</a>'
        )

    def test_texto_e_escapado(self):
        assert rodape.sanitizar("a < b & c") == "a &lt; b &amp; c"

    def test_tamanho_maximo(self):
        assert len(rodape.sanitizar("x" * 100_000)) <= rodape.TAMANHO_MAXIMO

    def test_o_padrao_e_estavel_sob_o_sanitizador(self):
        assert rodape.sanitizar(rodape.HTML_PADRAO) == rodape.HTML_PADRAO


# ===========================================================================
# 2. Os atalhos: nada duplicado
# ===========================================================================


class TestAtalhos:
    def test_o_padrao_nao_grava_dado_nenhum(self):
        """Nome, e-mail, ano: só atalhos. O dado continua em Sistema."""
        assert "Desenrola" not in rodape.HTML_PADRAO
        assert "@" not in rodape.HTML_PADRAO.replace("{email_contato}", "")
        assert str(datetime.date.today().year) not in rodape.HTML_PADRAO
        assert "{nome_do_site}" in rodape.HTML_PADRAO
        assert "{ano}" in rodape.HTML_PADRAO

    def test_o_nome_muda_junto_com_sistema(self, client):
        atual = config()
        atual.site_name = "Outro Nome"
        atual.save()

        html = rodape_html(client)

        assert "Outro Nome" in html
        assert "{nome_do_site}" not in html

    def test_o_email_muda_junto_com_sistema(self, client):
        atual = config()
        atual.contact_email = "novo@exemplo.test"
        atual.save()

        assert 'href="mailto:novo@exemplo.test"' in rodape_html(client)

    def test_o_ano_e_do_servidor(self, client):
        assert f"© {datetime.date.today().year}" in rodape_html(client)

    def test_o_menu_e_o_da_barra_superior(self, client):
        """Os mesmos itens, com a Home na frente da âncora."""
        from apps.content.models import MenuItem

        item = MenuItem.objects.filter(is_active=True).first()
        assert item is not None
        html = rodape_html(client)

        assert item.label in html
        assert f'href="{HOME}#' in html or f'href="{item.destination}"' in html

    def test_o_link_legal_aparece_so_com_texto_publicado(self, client):
        escrever('<p><a href="{url_privacidade}">Privacidade</a> <a href="/pt/">Início</a></p>')

        sem = rodape_html(client)
        publicar_privacidade()
        com = rodape_html(client)

        assert "Privacidade" not in sem
        assert "Início" in sem
        assert reverse("core:legal_privacidade") in com
        assert "Privacidade" in com

    def test_sem_email_o_link_de_contato_sai_inteiro(self, client):
        atual = config()
        atual.contact_email = ""
        atual.save()
        escrever('<p><a href="mailto:{email_contato}">Contato</a> <a href="/pt/">Início</a></p>')

        html = rodape_html(client)

        assert "Contato" not in html
        assert 'href="mailto:"' not in html
        assert "Início" in html

    def test_as_redes_vem_de_sistema(self, client):
        atual = config()
        atual.social_links = {"instagram": "https://instagram.com/x"}
        atual.save()
        escrever("<p>{redes_sociais}</p>")

        html = rodape_html(client)

        assert 'href="https://instagram.com/x"' in html
        assert "ph-instagram-logo" in html
        assert 'rel="noopener noreferrer"' in html

    def test_atalho_desconhecido_nao_vira_texto(self, client):
        escrever("<p>{isto_nao_existe} fica</p>")

        html = rodape_html(client)

        assert "{isto_nao_existe}" not in html
        assert "fica" in html

    def test_nao_ha_campo_de_nome_proprio_do_rodape(self):
        """O CMS oferece um conteúdo rico -- e nenhum campo de nome ou e-mail."""
        from apps.content.section_schema import SECOES, TextoRico

        campos = SECOES["footer"].campos
        assert len(campos) == 1
        assert isinstance(campos[0], TextoRico)
        assert campos[0].chave == "html"


# ===========================================================================
# 3. O público
# ===========================================================================


class TestPublico:
    def test_sem_nada_gravado_sai_o_padrao(self, client):
        html = rodape_html(client)

        assert "<h3" in html
        assert "©" in html
        assert "{" not in html.split('class="site-footer"')[-1]

    def test_o_que_foi_gravado_e_o_que_sai(self, client):
        escrever('<h4>Coluna</h4><p><a href="/pt/parceiros/">Parceiros</a></p>')

        html = rodape_html(client)

        assert "<h4>Coluna</h4>" in html
        assert 'href="/pt/parceiros/"' in html

    def test_o_banco_nao_e_confiavel(self, client):
        """Gravado por fora do editor, o veneno passa pelo sanitizador de novo."""
        traducao().content = {"html": '<script>alert(1)</script><p onclick="x">ok</p>'}
        traducao().save()
        t = traducao()
        t.content = {"html": '<script>alert(1)</script><p onclick="x">ok</p>'}
        t.save(update_fields=["content"])

        html = rodape_html(client)

        assert "<script" not in html
        assert "onclick" not in html
        assert "<p>ok</p>" in html

    def test_sem_a_secao_ativa_o_rodape_inteiro_some(self, client):
        PageSection.objects.filter(pk=secao().pk).update(is_active=False)

        assert rodape_html(client) == ""

    def test_aparece_na_pagina_de_parceiros_e_nas_legais(self, client):
        from apps.content.models import Partner

        Partner.objects.create(name="P", url="https://p.example")
        publicar_privacidade()

        assert "<h3" in rodape_html(client, reverse("core:parceiros"))
        assert "<h3" in rodape_html(client, reverse("core:legal_privacidade"))

    def test_nenhum_link_ficticio(self, client):
        html = rodape_html(client)

        assert 'href="#"' not in html
        assert 'href=""' not in html


# ===========================================================================
# 4. A tela de edição
# ===========================================================================


class TestTelaDeEdicao:
    def test_a_tela_traz_o_editor_rico(self, cliente):
        corpo = cliente.get(url_do_editor()).content.decode()

        assert "data-editor-rico" in corpo
        assert 'name="html"' in corpo
        assert "editor-rico.js" in corpo

    def test_o_campo_nasce_com_o_padrao(self, cliente):
        """Uma área vazia ao lado de uma prévia cheia confundiria."""
        corpo = cliente.get(url_do_editor()).content.decode()

        assert "{nome_do_site}" in corpo

    def test_os_atalhos_sao_oferecidos(self, cliente):
        corpo = cliente.get(url_do_editor()).content.decode()

        for atalho, _explicacao in rodape.ATALHOS:
            assert f'data-atalho="{atalho}"' in corpo

    def test_os_blocos_antigos_nao_existem_mais(self, cliente):
        corpo = cliente.get(url_do_editor()).content.decode()

        assert "Blocos do rodapé" not in corpo
        assert "footer_bloco" not in corpo

    def test_salvar_grava_sanitizado(self, cliente):
        cliente.post(
            url_do_editor(),
            _payload('<p onclick="x">Olá</p><script>alert(1)</script>'),
        )

        gravado = traducao().content["html"]
        assert gravado == "<p>Olá</p>"

    def test_salvar_reflete_no_site(self, cliente, client):
        cliente.post(url_do_editor(), _payload("<h3>Rodapé novo</h3>"))

        assert "Rodapé novo" in rodape_html(client)

    def test_quem_so_ve_nao_grava(self, leitora):
        c = Client()
        c.force_login(leitora)

        resposta = c.post(url_do_editor(), _payload("<p>invadido</p>"))

        assert resposta.status_code == 403
        assert "invadido" not in (traducao().content.get("html") or "")

    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(url_do_editor())

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_o_interruptor_da_secao_continua_valendo(self, cliente, client):
        """Ativo/inativo do rodapé inteiro é o da parte, como sempre."""
        PageSection.objects.filter(pk=secao().pk).update(is_active=False)

        assert rodape_html(client) == ""
        assert "data-editor-rico" in cliente.get(url_do_editor()).content.decode()


# ===========================================================================
# 5. A prévia
# ===========================================================================


class TestPrevia:
    def test_a_previa_usa_o_parcial_publico(self, cliente):
        corpo = cliente.get(url_da_previa()).content.decode()

        assert 'class="site-footer"' in corpo
        assert "site-footer-conteudo" in corpo
        assert 'class="bo-previa publico"' in corpo

    def test_a_previa_mostra_o_digitado_sem_gravar(self, cliente):
        corpo = cliente.post(url_da_previa(), _payload("<h3>Só na prévia</h3>")).content.decode()

        assert "Só na prévia" in corpo
        assert "Só na prévia" not in (traducao().content.get("html") or "")

    def test_a_previa_tambem_sanitiza(self, cliente):
        corpo = cliente.post(
            url_da_previa(), _payload('<p onclick="x">a</p><script>b</script>')
        ).content.decode()

        assert "onclick" not in corpo
        assert "<script>b" not in corpo

    def test_a_previa_troca_os_atalhos(self, cliente):
        corpo = cliente.post(url_da_previa(), _payload("<p>{nome_do_site}</p>")).content.decode()

        assert "{nome_do_site}" not in corpo
        assert config().site_name in corpo

    @pytest.mark.parametrize("nome", ["desktop", "tablet", "mobile"])
    def test_as_tres_larguras_respondem(self, cliente, nome):
        resposta = cliente.get(f"{url_da_previa()}?viewport={nome}")

        assert resposta.status_code == 200
        assert f'data-viewport="{nome}"' in resposta.content.decode()


# ===========================================================================
# 6. Acessibilidade e o desenho
# ===========================================================================


class TestAcessibilidade:
    def test_links_do_rodape_tem_altura_minima_de_toque(self):
        css = (RAIZ / "static" / "css" / "layout.css").read_text(encoding="utf-8")

        assert "min-height: 40px" in css.split(".site-footer-conteudo a {")[1].split("}")[0]

    def test_icones_de_rede_social_tem_area_de_toque_quadrada(self):
        css = (RAIZ / "static" / "css" / "layout.css").read_text(encoding="utf-8")
        regra = css.split(".site-footer-social {")[1].split("}")[0]

        assert "min-width: 40px" in regra
        assert "min-height: 40px" in regra

    def test_o_rodape_e_a_coluna_centrada_da_referencia(self):
        css = (RAIZ / "static" / "css" / "layout.css").read_text(encoding="utf-8")
        regra = css.split(".site-footer-conteudo {")[1].split("}")[0]

        assert "align-items: center" in regra
        assert "text-align: center" in regra

    def test_o_unico_mark_safe_do_projeto_esta_no_renderizador(self):
        """O sanitizador é a proteção; `mark_safe` só entra depois dele."""
        fonte = (RAIZ / "apps" / "content" / "rodape.py").read_text(encoding="utf-8")

        assert fonte.count("mark_safe(") == 1
        assert fonte.index("def sanitizar") < fonte.index("mark_safe(")
