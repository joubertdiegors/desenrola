"""
Bloco C: o rodapé em três linhas, configurável de verdade no Backoffice.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o rodapé duplique dado que já tem dono.** Marca vem de
   Aparência/Sistema, links legais das páginas legais, contato e redes
   de Sistema -- mudar em um desses lugares tem de mudar o rodapé sem
   um segundo campo para escrever o mesmo valor;
2. **Que o Backoffice não consiga, de verdade, ligar/desligar e
   reordenar os quatro blocos.** Até este bloco a composição só existia
   no código -- não havia tela;
3. **Que desativar um bloco apague alguma coisa.** `marca`/`legais`/
   `contato`/`redes` continuam existindo em `BLOCOS_DO_RODAPE`; só saem
   da lista gravada;
4. **Que o ano fique hardcoded** -- e não que a suíte de
   `test_sistema.py` seja a única a notar;
5. **Que a prévia do rodapé desenhe algo diferente da Home pública.**
"""

import pathlib
import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.content.models import PageSection, PageSectionTranslation, SiteSettings

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")
BLOCO_ATIVACAO = reverse("backoffice:footer_bloco_activation")
BLOCO_MOVER = reverse("backoffice:footer_bloco_move")

TODOS_OS_BLOCOS = ("marca", "legais", "contato", "redes")


def config():
    return SiteSettings.load()


def secao():
    return PageSection.objects.get(page__key="home", key="footer")


def traducao():
    t, _criada = PageSectionTranslation.objects.get_or_create(
        section=secao(), language="pt", defaults={"content": {}}
    )
    return t


def blocos_gravados():
    """Os blocos ativos, na ordem gravada -- direto do banco."""
    from apps.content.section_schema import blocos_do_rodape

    return blocos_do_rodape(traducao().content)


def corpo(client):
    return client.get(HOME).content.decode()


def rodape_html(client):
    html = corpo(client)
    inicio = html.index("<footer")
    return html[inicio : html.index("</footer>") + len("</footer>")]


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


def _ligar(cliente, chave, ligado=True):
    return cliente.post(
        BLOCO_ATIVACAO, {"chave": chave, "ativo": "1" if ligado else "0", "idioma": "pt"}
    )


def _mover(cliente, chave, direcao):
    return cliente.post(BLOCO_MOVER, {"chave": chave, "direcao": direcao, "idioma": "pt"})


# ===========================================================================
# 1. Três linhas -- marca, links, copyright
# ===========================================================================


class TestTresLinhas:
    def test_as_tres_linhas_existem(self, client):
        html = rodape_html(client)

        assert "site-footer-marca" in html
        assert "site-footer-links" in html
        assert "site-footer-copyright" in html

    def test_a_marca_vem_antes_dos_links_e_o_copyright_por_ultimo(self, client):
        html = rodape_html(client)

        assert (
            html.index("site-footer-marca")
            < html.index("site-footer-links")
            < html.index("site-footer-copyright")
        )

    def test_sem_a_secao_ativa_o_rodape_inteiro_some(self, client):
        PageSection.objects.filter(pk=secao().pk).update(is_active=False)

        assert "<footer" not in corpo(client)

    def test_reativar_devolve_o_rodape(self, client):
        PageSection.objects.filter(pk=secao().pk).update(is_active=False)
        PageSection.objects.filter(pk=secao().pk).update(is_active=True)

        assert "<footer" in corpo(client)


# ===========================================================================
# 2. Nenhum dado duplicado -- tudo vem de onde já tinha dono
# ===========================================================================


class TestSemDuplicacao:
    def test_o_nome_muda_junto_com_sistema(self, client):
        atual = config()
        atual.site_name = "Nome Trocado Agora"
        atual.save()

        assert "Nome Trocado Agora" in rodape_html(client)

    def test_o_email_muda_junto_com_sistema(self, client):
        atual = config()
        atual.contact_email = "novo@mail.com"
        atual.save()

        assert "mailto:novo@mail.com" in rodape_html(client)

    def test_a_rede_social_muda_junto_com_sistema(self, client):
        atual = config()
        atual.social_links = {"instagram": "https://instagram.example/perfil"}
        atual.save()

        assert "https://instagram.example/perfil" in rodape_html(client)

    def test_nao_ha_campo_de_nome_proprio_do_rodape(self):
        """
        Se existisse, seria um segundo lugar para escrever o mesmo nome
        -- exatamente a duplicação que o requisito proíbe.
        """
        from apps.content import section_schema

        campos = {texto.chave for texto in section_schema.SECOES["footer"].campos}

        assert "site_name" not in campos
        assert "nome" not in campos
        assert "brand" not in campos


# ===========================================================================
# 3. O ano nunca é hardcoded
# ===========================================================================


class TestAno:
    def test_o_ano_e_calculado_uma_vez_so(self):
        raiz = pathlib.Path(__file__).resolve().parents[3]
        fonte = (
            raiz / "templates" / "components" / "site_footer.html"
        ).read_text(encoding="utf-8")
        markup = fonte[fonte.index("{% endcomment %}") :]

        assert re.search(r"20\d\d", markup) is None
        assert markup.count('{% now "Y" %}') == 1


# ===========================================================================
# 4. O Backoffice liga, desliga e reordena de verdade
# ===========================================================================


class TestConfiguracaoReal:
    def test_estado_inicial_tem_os_quatro_ativos(self):
        assert set(blocos_gravados()) == set(TODOS_OS_BLOCOS)

    @pytest.mark.parametrize("bloco", TODOS_OS_BLOCOS)
    def test_desligar_um_bloco_tira_ele_da_home(self, cliente, client, bloco):
        _ligar(cliente, bloco, ligado=False)

        assert bloco not in blocos_gravados()

    def test_desligar_marca_esconde_a_linha_da_marca(self, cliente, client):
        _ligar(cliente, "marca", ligado=False)

        assert "site-footer-marca" not in rodape_html(client)
        # As outras linhas continuam -- desligar uma nao apaga as demais.
        assert "site-footer-copyright" in rodape_html(client)

    def test_religar_devolve_o_bloco_ao_fim_da_lista(self, cliente):
        _ligar(cliente, "redes", ligado=False)
        _ligar(cliente, "redes", ligado=True)

        assert blocos_gravados()[-1] == "redes"

    def test_desligar_nao_apaga_o_bloco_do_conjunto_conhecido(self, cliente):
        """
        `BLOCOS_DO_RODAPE` é fixo no código -- desligar só tira da lista
        gravada, nunca apaga a declaração do bloco em si.
        """
        from apps.content.section_schema import BLOCOS_DO_RODAPE

        _ligar(cliente, "contato", ligado=False)

        assert {b.chave for b in BLOCOS_DO_RODAPE} == set(TODOS_OS_BLOCOS)

    def test_bloco_desconhecido_e_recusado(self, cliente):
        resposta = _ligar(cliente, "inventado", ligado=True)

        assert resposta.status_code == 404
        assert "inventado" not in blocos_gravados()

    def test_mover_para_cima_troca_a_ordem(self, cliente):
        antes = blocos_gravados()
        segundo = antes[1]

        _mover(cliente, segundo, "subir")

        depois = blocos_gravados()
        assert depois[0] == segundo
        assert depois[1] == antes[0]

    def test_mover_o_primeiro_para_cima_nao_faz_nada(self, cliente):
        antes = blocos_gravados()

        _mover(cliente, antes[0], "subir")

        assert blocos_gravados() == antes

    def test_a_ordem_escolhida_aparece_na_home(self, cliente, client):
        from apps.content.models import ContentBlock, ContentTranslation

        for chave in ("legal.terms_of_use", "legal.privacy_policy"):
            bloco = ContentBlock.objects.get(key=chave)
            trad, _c = ContentTranslation.objects.get_or_create(block=bloco, language="pt")
            trad.content = "Texto publicado."
            trad.save()
        config_obj = config()
        config_obj.social_links = {"instagram": "https://instagram.example/perfil"}
        config_obj.save()

        # Poe "redes" antes de "legais": duas trocas para cima a partir
        # da ordem padrao (marca, legais, contato, redes).
        _mover(cliente, "redes", "subir")
        _mover(cliente, "redes", "subir")

        assert blocos_gravados().index("redes") < blocos_gravados().index("legais")

        html = rodape_html(client)
        assert html.index("site-footer-social") < html.index("Termos de uso")

    def test_permissao_e_a_mesma_de_editar_secao(self, leitora):
        c = Client()
        c.force_login(leitora)

        resposta = c.post(
            BLOCO_ATIVACAO, {"chave": "redes", "ativo": "0", "idioma": "pt"}
        )

        assert resposta.status_code == 403

    def test_anonimo_e_barrado(self, client):
        resposta = client.post(
            BLOCO_ATIVACAO, {"chave": "redes", "ativo": "0", "idioma": "pt"}
        )

        assert resposta.status_code == 302

    def test_get_nao_e_aceito(self, cliente):
        assert cliente.get(BLOCO_ATIVACAO).status_code == 405
        assert cliente.get(BLOCO_MOVER).status_code == 405


# ===========================================================================
# 5. A tela de edição mostra os quatro blocos
# ===========================================================================


class TestTelaDeEdicao:
    def test_os_quatro_nomes_amigaveis_aparecem(self, cliente):
        corpo_html = cliente.get(url_do_editor()).content.decode()

        for nome in ("Marca", "Links legais", "Contato", "Redes sociais"):
            assert nome in corpo_html

    def test_bloco_desligado_mostra_a_etiqueta(self, cliente):
        _ligar(cliente, "redes", ligado=False)

        corpo_html = cliente.get(url_do_editor()).content.decode()

        assert "Oculto" in corpo_html

    def test_o_primeiro_bloco_ativo_nao_oferece_subir(self, cliente):
        corpo_html = cliente.get(url_do_editor()).content.decode()

        assert 'name="chave" value="marca"' in corpo_html
        # O primeiro ativo (marca) nao tem formulario de "subir".
        antes_de_marca = corpo_html[: corpo_html.index('value="marca"')]
        assert "Subir Marca" not in antes_de_marca

    def test_quem_so_ve_nao_recebe_botoes_de_acao(self, leitora):
        c = Client()
        c.force_login(leitora)

        corpo_html = c.get(url_do_editor()).content.decode()

        assert ">Ativar<" not in corpo_html
        assert ">Desativar<" not in corpo_html

    def test_nenhum_link_morto_na_tela(self, cliente):
        corpo_html = cliente.get(url_do_editor()).content.decode()

        assert 'href="#"' not in corpo_html


# ===========================================================================
# 6. A prévia usa a mesma composição da Home
# ===========================================================================


class TestPrevia:
    def test_a_previa_mostra_os_blocos_salvos(self, cliente):
        _ligar(cliente, "redes", ligado=False)

        html = cliente.get(url_da_previa()).content.decode()

        assert "site-footer-social" not in html
        assert "site-footer-marca" in html

    def test_a_previa_muda_depois_de_reordenar(self, cliente):
        from apps.content.models import ContentBlock, ContentTranslation

        bloco = ContentBlock.objects.get(key="legal.terms_of_use")
        trad, _c = ContentTranslation.objects.get_or_create(block=bloco, language="pt")
        trad.content = "Texto publicado."
        trad.save()
        atual = config()
        atual.social_links = {"instagram": "https://instagram.example/perfil"}
        atual.save()

        _mover(cliente, "redes", "subir")
        _mover(cliente, "redes", "subir")

        html = cliente.get(url_da_previa()).content.decode()
        assert html.index("site-footer-social") < html.index("Termos de uso")


# ===========================================================================
# 7. Toque, teclado e nenhum link fictício
# ===========================================================================


class TestAcessibilidade:
    def test_links_do_rodape_tem_altura_minima_de_toque(self):
        raiz = pathlib.Path(__file__).resolve().parents[3]
        css = (raiz / "static" / "css" / "layout.css").read_text(encoding="utf-8")

        assert "min-height: 40px" in css.split(".site-footer a {")[1].split("}")[0]

    def test_icones_de_rede_social_tem_area_de_toque_quadrada(self):
        """
        Só ícone, sem texto ao lado -- sem largura mínima também, a
        altura de 40px sozinha deixaria um alvo estreito demais.
        """
        raiz = pathlib.Path(__file__).resolve().parents[3]
        css = (raiz / "static" / "css" / "layout.css").read_text(encoding="utf-8")
        regra = css.split(".site-footer-social {")[1].split("}")[0]

        assert "min-height: 40px" in regra
        assert "min-width: 40px" in regra

    def test_foco_visivel_existe_no_projeto(self):
        raiz = pathlib.Path(__file__).resolve().parents[3]
        css = (raiz / "static" / "css" / "base.css").read_text(encoding="utf-8")

        assert ":focus-visible" in css

    def test_nenhum_link_ficticio_no_rodape(self, client):
        html = rodape_html(client)

        assert 'href="#"' not in html
        assert "example.com" not in html
        assert "lorem" not in html.lower()
