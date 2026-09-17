"""
Fase 5 / Etapa 4.1 -- a interface e so em portugues.

A decisao de produto separa duas coisas que antes andavam juntas:

  * o idioma da INTERFACE, agora fixo em portugues para toda a gente;
  * o idioma da CARTA, que continua com pt/fr/nl/en e continua sendo
    escolhido na etapa 5 do assistente.

Metade destes testes protege a primeira. A outra metade existe para
provar que a segunda NAO foi afetada -- e o risco real desta etapa, ja
que `settings.LANGUAGES` alimenta as duas.
"""

import datetime
from pathlib import Path

import polib
import pytest
from django.conf import settings
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.middleware import IDIOMA_DA_INTERFACE, caminho_em_portugues
from apps.doctemplates.services.biblioteca import slug_oficial
from apps.letters import services

RAIZ = Path(__file__).resolve().parents[3]
CATALOGO_PO = RAIZ / "locale" / "pt" / "LC_MESSAGES" / "django.po"
CATALOGO_MO = CATALOGO_PO.with_suffix(".mo")

IDIOMAS_DO_SITE = ["pt", "fr", "nl", "en"]
OUTROS_IDIOMAS = ["fr", "nl", "en"]

# Marcas de HTML dos tres componentes de escolha de idioma da interface.
# Se qualquer uma reaparecer numa pagina, o seletor voltou.
MARCAS_DE_SELETOR = ("site-nav-lang", "lang-dropdown", "auth-lang", "lang-choice")


@pytest.fixture(autouse=True)
def _nacionalidade(nacionalidade_factory):
    nacionalidade_factory("Brasileira", name_fr="Brésilienne")


@pytest.fixture
def draft(user, modelos_oficiais_prontos):
    return services.start_draft(user, "pt")


CHEGADA = timezone.localdate() + datetime.timedelta(days=30)
PASSOS = {
    1: {
        "guest_name": "Maria Santos da Silva",
        "guest_nationality": "Brasileira",
        "guest_birth_date": "15/08/1990",
        "guest_passport": "YY0000",
    },
    2: {
        "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
        "stay_departure": (CHEGADA + datetime.timedelta(days=14)).strftime("%d/%m/%Y"),
    },
    3: {"host_confirm": "on"},
    4: {"notice_informal": "on", "notice_prise_en_charge": "on"},
}


def _ate_a_etapa_do_idioma(client, letter):
    """
    O assistente so deixa chegar a etapa 5 com as anteriores preenchidas.
    Sem isto, um GET na etapa 5 devolve a pessoa para a primeira pendente.
    """
    for numero in (1, 2, 3, 4):
        client.post(reverse("letters:step", args=[letter.uuid, numero]), PASSOS[numero])


# ---------------------------------------------------------------------------
# 1. A interface responde em portugues venha o pedido de onde vier
# ---------------------------------------------------------------------------


class TestInterfaceSempreEmPortugues:
    @pytest.mark.parametrize("idioma", IDIOMAS_DO_SITE)
    def test_a_home_sai_em_portugues_em_qualquer_prefixo(self, idioma):
        html = Client().get(f"/{idioma}/", follow=True).content.decode()

        assert "Como funciona" in html
        assert "Criar minha conta" in html

    @pytest.mark.parametrize("idioma", OUTROS_IDIOMAS)
    def test_prefixo_de_outro_idioma_vai_para_portugues(self, idioma):
        response = Client().get(f"/{idioma}/")

        assert response.status_code == 302
        assert response.url == "/pt/"

    def test_a_raiz_continua_indo_para_o_prefixo_padrao(self):
        response = Client().get("/")

        assert response.status_code == 302
        assert response.url == "/pt/"

    def test_a_pagina_declara_portugues_para_o_navegador(self):
        html = Client().get("/pt/").content.decode()

        assert '<html lang="pt">' in html

    def test_accept_language_do_navegador_nao_manda(self):
        """Um navegador configurado em frances continua vendo portugues."""
        html = Client(HTTP_ACCEPT_LANGUAGE="fr-BE,fr;q=0.9").get(
            "/pt/", follow=True
        ).content.decode()

        assert "Como funciona" in html
        assert '<html lang="pt">' in html


class TestCookieAntigoDeIdioma:
    """
    Quem trocou de idioma antes desta etapa carrega `django_language` no
    navegador. Ele nao pode continuar a mandar -- nem a voltar.
    """

    def _cliente_com_cookie(self, valor):
        client = Client()
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = valor
        return client

    def test_o_cookie_antigo_nao_escolhe_o_idioma(self):
        response = self._cliente_com_cookie("fr").get("/")

        assert response.url == "/pt/"

    def test_o_cookie_antigo_e_apagado_na_resposta(self):
        response = self._cliente_com_cookie("fr").get("/pt/")

        cookie = response.cookies.get(settings.LANGUAGE_COOKIE_NAME)
        assert cookie is not None, "o cookie devia ter sido apagado"
        assert cookie.value == ""

    def test_sem_cookie_nao_ha_nada_a_apagar(self):
        response = Client().get("/pt/")

        assert settings.LANGUAGE_COOKIE_NAME not in response.cookies

    def test_a_rota_de_troca_continua_existindo_mas_nao_muda_a_interface(self):
        """
        `set_language` fica registrada (a infraestrutura e preservada),
        mas ninguem a alcanca pela interface -- e mesmo um POST direto
        nao consegue mudar o idioma: o destino volta para /pt/ e o cookie
        que ela gravou e apagado no pedido seguinte.
        """
        client = Client()
        client.get("/pt/")

        destino = client.post(
            reverse("set_language"), {"language": "fr", "next": "/pt/"}
        )
        assert destino.status_code == 302

        html = client.get(destino.url, follow=True).content.decode()
        assert "Como funciona" in html
        assert '<html lang="pt">' in html


class TestRedirecionamentoNaoQuebraNada:
    def test_a_query_string_sobrevive(self):
        response = Client().get("/fr/accounts/login/?next=/fr/accounts/profile/")

        assert response.url == "/pt/accounts/login/?next=/fr/accounts/profile/"

    def test_um_next_em_outro_idioma_acaba_em_portugues(self, client, user):
        """
        O `next` guardado num link antigo aponta para /fr/. Seguir a
        cadeia toda tem de terminar no destino em portugues, sem 404.
        """
        client.force_login(user)

        response = client.get("/fr/accounts/profile/", follow=True)

        assert response.status_code == 200
        assert response.redirect_chain[-1][0] == "/pt/accounts/profile/"

    def test_um_envio_nao_perde_o_conteudo_no_caminho(self, auth_client, user):
        """
        Um 302 sobre um POST vira GET e o corpo se perde -- quem tivesse
        uma pagina em /fr/ aberta antes desta mudanca perderia o que
        digitou ao enviar. O 307 repete o envio inteiro em /pt/.
        """
        response = auth_client.post(
            "/fr/letters/new/", PASSOS[1], follow=True
        )

        assert response.redirect_chain[0] == ("/pt/letters/new/", 307)
        assert response.status_code in (200, 302)

    def test_um_get_usa_o_redirecionamento_comum(self):
        response = Client().get("/fr/")

        assert response.status_code == 302

    def test_a_sonda_de_saude_fica_fora_disto(self):
        response = Client().get("/healthz/")

        assert response.status_code == 200

    @pytest.mark.parametrize(
        "caminho, esperado",
        [
            ("/fr/letters/new/", "/pt/letters/new/"),
            ("/nl/", "/pt/"),
            ("/en", "/pt/"),
            ("/pt/letters/new/", None),
            ("/healthz/", None),
            ("/i18n/setlang/", None),
            # Nao e prefixo de idioma: nao pode ser mexido.
            ("/admin/", None),
            ("/pt-br/", None),
        ],
    )
    def test_so_prefixos_de_idioma_sao_trocados(self, caminho, esperado):
        assert caminho_em_portugues(caminho) == esperado

    def test_a_troca_sempre_termina(self):
        """Um caminho ja em portugues nao pode pedir outra troca."""
        destino = caminho_em_portugues("/fr/letters/new/")

        assert caminho_em_portugues(destino) is None


# ---------------------------------------------------------------------------
# 2. Mensagens geradas pelo Django tambem saem em portugues
# ---------------------------------------------------------------------------


class TestMensagensDoDjango:
    def test_campo_obrigatorio_em_portugues(self, client):
        html = client.post(reverse("accounts:signup"), {}).content.decode()

        assert "obrigatório" in html
        assert "This field is required" not in html
        assert "Ce champ est obligatoire" not in html
        assert "Dit veld is verplicht" not in html

    @pytest.mark.parametrize("idioma", OUTROS_IDIOMAS)
    def test_nem_mesmo_por_uma_url_de_outro_idioma(self, idioma):
        """
        O POST em /fr/ e redirecionado; seguir a cadeia tem de chegar a
        uma pagina em portugues, nunca com a mensagem do Django em
        frances ou neerlandes.
        """
        html = Client().get(f"/{idioma}/accounts/signup/", follow=True).content.decode()

        assert "Criar minha conta" in html or "Cadastro" in html
        assert "obligatoire" not in html
        assert "verplicht" not in html

    def test_senha_curta_em_portugues(self):
        """
        Era a unica mensagem do Django que ainda saia em ingles (achado
        da auditoria da Etapa 4.0).
        """
        with pytest.raises(ValidationError) as erro:
            password_validation.validate_password("abc")

        mensagens = " ".join(erro.value.messages)
        assert "muito curta" in mensagens
        assert "too short" not in mensagens

    def test_os_erros_de_senha_falam_a_mesma_lingua(self):
        """
        O catalogo `pt` do Django e de Portugal ("palavra-passe"); o resto
        da interface diz "senha". Os erros de uma mesma lista nao podem
        misturar as duas.
        """
        with pytest.raises(ValidationError) as erro:
            password_validation.validate_password("123")

        mensagens = " ".join(erro.value.messages)
        assert "palavra-passe" not in mensagens
        assert mensagens.count("senha") >= 3

    def test_a_senha_curta_aparece_em_portugues_no_cadastro(self, client):
        html = client.post(
            reverse("accounts:signup"),
            {
                "full_name": "Maria Santos",
                "email": "maria@exemplo.com",
                "password1": "abc",
                "password2": "abc",
                "terms": "on",
            },
        ).content.decode()

        assert "muito curta" in html
        assert "too short" not in html


class TestCatalogoDeMensagens:
    """
    O .mo e versionado porque nao ha passo de build que o gere. Estes
    testes avisam quem editar o .po e esquecer de recompilar.
    """

    def test_o_catalogo_compilado_existe(self):
        assert CATALOGO_MO.exists(), (
            f"{CATALOGO_MO} nao existe. Rode: python scripts/compile_messages.py"
        )

    def test_o_compilado_esta_em_dia_com_a_fonte(self):
        po = {e.msgid: (e.msgstr, e.msgstr_plural) for e in polib.pofile(str(CATALOGO_PO))}
        mo = {e.msgid: (e.msgstr, e.msgstr_plural) for e in polib.mofile(str(CATALOGO_MO))}

        assert po == mo, "o .po mudou sem recompilar: python scripts/compile_messages.py"

    def test_o_catalogo_so_cobre_mensagens_do_django(self):
        """
        Este catalogo nao e para traduzir o site -- os nossos textos ja
        nascem em portugues. Uma entrada nossa aqui seria sinal de que a
        regra se perdeu.
        """
        nossos_textos = ("Carta Convite", "Desenrola", "anfitri", "convidado")

        for entrada in polib.pofile(str(CATALOGO_PO)):
            assert not any(t in entrada.msgid for t in nossos_textos), entrada.msgid


# ---------------------------------------------------------------------------
# 3. Nenhuma tela oferece escolha de idioma da interface
# ---------------------------------------------------------------------------


class TestSeletorDeIdiomaSumiu:
    ROTAS_PUBLICAS = [
        "core:home",
        "accounts:login",
        "accounts:signup",
        "accounts:password_reset",
    ]

    @pytest.mark.parametrize("rota", ROTAS_PUBLICAS)
    def test_telas_publicas_nao_tem_seletor(self, client, rota):
        html = client.get(reverse(rota)).content.decode()

        for marca in MARCAS_DE_SELETOR:
            assert marca not in html, f"{rota} ainda mostra o seletor ({marca})"

    @pytest.mark.parametrize("rota", ["core:dashboard", "accounts:profile"])
    def test_telas_da_area_logada_nao_tem_seletor(self, auth_client, rota):
        html = auth_client.get(reverse(rota)).content.decode()

        for marca in MARCAS_DE_SELETOR:
            assert marca not in html, f"{rota} ainda mostra o seletor ({marca})"

    def test_o_rodape_da_landing_nao_tem_seletor(self, client):
        html = client.get(reverse("core:home")).content.decode()

        assert "footer-lang" not in html

    def test_nenhuma_tela_aponta_para_a_troca_de_idioma(self, client, auth_client):
        url_de_troca = reverse("set_language")
        paginas = [
            client.get(reverse("core:home")),
            client.get(reverse("accounts:login")),
            auth_client.get(reverse("accounts:profile")),
        ]

        for pagina in paginas:
            assert url_de_troca not in pagina.content.decode()


class TestPerfilSemSecaoDeIdioma:
    def test_nao_ha_secao_de_idioma(self, auth_client):
        html = auth_client.get(reverse("accounts:profile")).content.decode()

        assert 'id="idioma"' not in html
        assert "secao=idioma" not in html

    def test_o_select_falso_de_idioma_da_carta_sumiu(self, auth_client):
        """
        Estava fora de qualquer <form>, sem nada no backend a ler ou
        gravar, e ainda omitia o neerlandes.
        """
        html = auth_client.get(reverse("accounts:profile")).content.decode()

        assert "letter_language" not in html
        assert "p_letter_lang" not in html

    def test_o_menu_do_celular_nao_anuncia_o_idioma_atual(self, auth_client):
        html = auth_client.get(reverse("accounts:profile")).content.decode()

        assert "ph-globe" not in html

    def test_um_link_antigo_para_a_secao_nao_da_erro(self, auth_client):
        """Quem tinha ?secao=idioma guardado abre o perfil, nao um 404."""
        response = auth_client.get(reverse("accounts:profile") + "?secao=idioma")

        assert response.status_code == 200

    def test_as_outras_secoes_continuam(self, auth_client):
        html = auth_client.get(reverse("accounts:profile")).content.decode()

        assert 'id="dados"' in html
        assert 'id="senha"' in html
        assert 'id="comunicacoes"' in html


# ---------------------------------------------------------------------------
# 4. A infraestrutura de i18n continua de pe
# ---------------------------------------------------------------------------


class TestInfraestruturaPreservada:
    def test_os_quatro_idiomas_continuam_configurados(self):
        """
        NAO reduzir esta lista: ela alimenta `Letter.language`,
        `DocumentTemplate.language` e as opcoes da etapa 5 -- ou seja, o
        idioma do DOCUMENTO, que nao mudou nesta etapa.
        """
        assert [codigo for codigo, _nome in settings.LANGUAGES] == IDIOMAS_DO_SITE

    def test_a_rota_de_troca_de_idioma_continua_registrada(self):
        assert reverse("set_language") == "/i18n/setlang/"

    def test_i18n_patterns_continua_prefixando(self):
        assert reverse("core:home") == "/pt/"
        assert reverse("accounts:login") == "/pt/accounts/login/"

    def test_o_middleware_vem_antes_do_locale(self):
        ordem = settings.MIDDLEWARE
        nosso = ordem.index("apps.core.middleware.InterfaceEmPortuguesMiddleware")
        locale = ordem.index("django.middleware.locale.LocaleMiddleware")

        assert nosso < locale, "so antes do LocaleMiddleware o cookie pode ser ignorado"

    def test_os_componentes_ficaram_no_projeto(self):
        """Ocultar nao e apagar: a interface multilingue tem de poder voltar."""
        for nome in ("language_selector", "auth_lang", "language_seg"):
            assert (RAIZ / "templates" / "components" / f"{nome}.html").exists()

    def test_os_componentes_nao_sao_incluidos_em_lugar_nenhum(self):
        templates = list((RAIZ / "templates").rglob("*.html"))
        componentes = {"language_selector.html", "auth_lang.html", "language_seg.html"}

        for caminho in templates:
            if caminho.name in componentes:
                continue
            texto = caminho.read_text(encoding="utf-8")
            for componente in componentes:
                assert f'include "components/{componente}"' not in texto, caminho

    def test_o_idioma_da_interface_e_o_padrao_do_projeto(self):
        assert IDIOMA_DA_INTERFACE == settings.LANGUAGE_CODE == "pt"


# ---------------------------------------------------------------------------
# 5. O idioma da CARTA continua intacto -- o risco real desta etapa
# ---------------------------------------------------------------------------


class TestIdiomaDaCartaNaoFoiAfetado:
    def test_a_etapa_5_continua_oferecendo_os_quatro_idiomas(self, auth_client, draft):
        _ate_a_etapa_do_idioma(auth_client, draft)

        response = auth_client.get(
            reverse("letters:step", args=[draft.uuid, services.LANGUAGE_STEP])
        )

        codigos = [lang["code"] for lang in response.context["language_options"]]
        assert codigos == IDIOMAS_DO_SITE

    def test_os_quatro_aparecem_no_html_da_etapa_5(self, auth_client, draft):
        _ate_a_etapa_do_idioma(auth_client, draft)

        html = auth_client.get(
            reverse("letters:step", args=[draft.uuid, services.LANGUAGE_STEP])
        ).content.decode()

        for nome in ("Português", "Français", "Nederlands", "English"):
            assert nome in html

    @pytest.mark.parametrize("idioma", IDIOMAS_DO_SITE)
    def test_escolher_o_idioma_continua_gravando_na_carta(
        self, auth_client, draft, idioma
    ):
        _ate_a_etapa_do_idioma(auth_client, draft)

        auth_client.post(
            reverse("letters:step", args=[draft.uuid, services.LANGUAGE_STEP]),
            {"language": idioma},
        )

        draft.refresh_from_db()
        assert draft.language == idioma
        assert draft.document_template.slug == slug_oficial(idioma)

    def test_os_rotulos_do_assistente_ficam_em_portugues_mesmo_trocando_a_carta(
        self, auth_client, draft
    ):
        """
        Revisto na etapa de correções pós-validação manual (posterior a
        esta): a Etapa 4.1 deixava o rótulo seguir o idioma da carta de
        propósito ("descreve o que vai para o documento oficial"), mas a
        validação manual mostrou que isso lia como a interface tendo
        vazado para inglês/francês/neerlandês -- o rótulo é texto do
        ASSISTENTE, não o documento em si (que continua saindo no idioma
        certo, pelo renderer -- ver apps.doctemplates.services.pdf). O
        idioma da carta em si não foi afetado: os quatro continuam
        disponíveis e gravando corretamente (ver os outros testes desta
        classe).
        """
        services.change_language(draft, "fr")

        html = auth_client.get(
            reverse("letters:step", args=[draft.uuid, services.FIRST_STEP])
        ).content.decode()

        assert "Data de nascimento" in html
        assert "Número do passaporte" in html
        assert "Date de naissance" not in html
        # E a moldura da pagina continua em portugues.
        assert "Próxima etapa" in html
        assert '<html lang="pt">' in html

    def test_trocar_o_idioma_nao_perde_o_que_ja_foi_preenchido(self, auth_client, draft):
        auth_client.post(
            reverse("letters:step", args=[draft.uuid, services.FIRST_STEP]),
            {
                "guest_name": "Maria Santos da Silva",
                "guest_nationality": "Brasileira",
                "guest_birth_date": "15/08/1990",
                "guest_passport": "YY0000",
            },
        )

        services.change_language(draft, "nl")

        draft.refresh_from_db()
        assert draft.data["guest_name"] == "Maria Santos da Silva"
        assert draft.data["guest_nationality"] == "Brasileira"

    def test_os_quatro_documentos_oficiais_continuam_disponiveis(self, modelos_oficiais_prontos):
        for idioma in IDIOMAS_DO_SITE:
            assert services.active_document_template(idioma) is not None


# ---------------------------------------------------------------------------
# 6. Nao voltar atras: nenhum texto de outro idioma na moldura
# ---------------------------------------------------------------------------


class TestNadaDeRegressao:
    def test_o_middleware_nao_mexe_em_metodos_nao_seguros_em_portugues(
        self, auth_client, user, modelos_oficiais_prontos
    ):
        """Um POST em /pt/ passa direto, sem redirecionamento."""
        response = auth_client.post(reverse("letters:new"), {})

        assert response.status_code == 200

    def test_o_login_continua_levando_ao_painel(self, client, user):
        from conftest import SENHA

        response = client.post(
            reverse("accounts:login"), {"username": user.email, "password": SENHA}
        )

        assert response.status_code == 302
        assert response.url == reverse("core:dashboard")

    def test_o_javascript_nao_ficou_com_referencia_a_idioma(self):
        texto = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")

        assert "setlang" not in texto

    def test_nenhum_template_ficou_com_tag_de_idioma_orfa(self):
        """
        `get_current_language` sem uso e restos de um seletor removido
        pela metade.
        """
        orfas = []
        for caminho in (RAIZ / "templates").rglob("*.html"):
            if caminho.name in ("language_selector.html", "auth_lang.html", "language_seg.html"):
                continue
            texto = caminho.read_text(encoding="utf-8")
            if "get_current_language" in texto or "get_available_languages" in texto:
                orfas.append(caminho.name)

        assert orfas == []
