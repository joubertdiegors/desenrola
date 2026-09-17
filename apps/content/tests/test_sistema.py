"""
As configurações globais do site, agora administráveis.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que `javascript:` chegue a um `href`.** A URL de uma rede social
   termina dentro de um atributo, onde o autoescape do template NÃO
   protege. Três camadas conferem o esquema -- formulário, `clean()` do
   modelo e processador de contexto -- e esta suíte testa as três, porque
   cada uma cobre um caminho que as outras não cobrem;
2. **Que a tela vire um editor de JSON.** `social_links` é um campo só,
   mas quem administra digita um endereço por rede, com rótulo;
3. **Que apareça link vazio.** Contato em branco não pode virar um
   "Contato" que não leva a lugar nenhum, nem rede sem endereço virar
   ícone morto;
4. **Que se duplique o que já tem tela.** Cor, logo, favicon, SMTP e
   idiomas do documento têm as suas; aqui só há ponteiro para elas;
5. **Que se inventem links legais.** Não há página de Termos nem de
   Privacidade -- e a tela diz isso, em vez de oferecer um campo que só
   poderia receber um endereço inventado;
6. **Que mudar o nome no Backoffice não mude o site.**
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from apps.content.context_processors import globais
from apps.content.models import REDES_SOCIAIS, SiteSettings

pytestmark = pytest.mark.django_db

TELA = reverse("backoffice:system")
HOME = reverse("core:home")

# O payload mínimo de um POST válido: o nome é o único obrigatório.
BASE = {"site_name": "Desenrola", "contact_email": "", "contact_phone": "", "contact_address": ""}


def config():
    return SiteSettings.load()


@pytest.fixture
def editora(db):
    """Entra no Backoffice E pode mudar as configurações."""
    pessoa = get_user_model().objects.create_user(
        email="editora@mail.com", password="x", full_name="Clara Dias"
    )
    for app_label, codename in (
        ("core", "access_backoffice"),
        ("content", "change_sitesettings"),
    ):
        pessoa.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return get_user_model().objects.get(pk=pessoa.pk)


@pytest.fixture
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


# ===========================================================================
# 1. O modelo continua sendo a fonte de verdade
# ===========================================================================


class TestConfiguracao:
    def test_os_campos_ja_existiam(self):
        """
        Esta etapa não criou coluna nenhuma: administra o que
        `SiteSettings` guarda desde a primeira migration do app.
        """
        colunas = {campo.name for campo in SiteSettings._meta.get_fields()}

        for campo in (
            "site_name",
            "contact_email",
            "contact_phone",
            "contact_address",
            "social_links",
        ):
            assert campo in colunas

    def test_os_padroes_de_um_registro_novo(self):
        atual = config()

        assert atual.site_name == "Desenrola"
        assert atual.contact_email == ""
        assert atual.contact_phone == ""
        assert atual.contact_address == ""
        assert atual.social_links == {}

    def test_persiste_o_que_foi_gravado(self):
        atual = config()
        atual.site_name = "Outro nome"
        atual.contact_email = "contato@mail.com"
        atual.contact_phone = "+32 000 00 00 00"
        atual.contact_address = "Rua de Exemplo, 1"
        atual.save()

        atual.refresh_from_db()
        assert atual.site_name == "Outro nome"
        assert atual.contact_email == "contato@mail.com"

    def test_vazio_e_um_estado_legitimo(self):
        """Contato em branco não é erro -- é "não configurado"."""
        atual = config()
        atual.contact_email = ""
        atual.contact_phone = ""
        atual.contact_address = ""

        atual.full_clean()  # não levanta


# ===========================================================================
# 2. As redes sociais
# ===========================================================================


class TestRedesNoModelo:
    def test_o_formato_guardado_e_rede_para_url(self):
        atual = config()
        atual.social_links = {"instagram": "https://exemplo.test/perfil"}
        atual.full_clean()
        atual.save()

        atual.refresh_from_db()
        assert atual.social_links == {"instagram": "https://exemplo.test/perfil"}

    @pytest.mark.parametrize(
        "perigosa",
        [
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "  javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox(1)",
            "file:///etc/passwd",
        ],
    )
    def test_esquema_perigoso_e_recusado(self, perigosa):
        """A URL termina num `href`: o autoescape não protege ali."""
        atual = config()
        atual.social_links = {"facebook": perigosa}

        with pytest.raises(ValidationError) as erro:
            atual.full_clean()

        assert "social_links" in erro.value.error_dict

    def test_url_sem_esquema_e_recusada(self):
        atual = config()
        atual.social_links = {"facebook": "exemplo.test/pagina"}

        with pytest.raises(ValidationError):
            atual.full_clean()

    def test_rede_desconhecida_e_recusada(self):
        """
        Uma chave que ninguém declarou não tem rótulo nem ícone: guardá-la
        seria guardar um dado que nenhuma página consegue mostrar.
        """
        atual = config()
        atual.social_links = {"orkut": "https://exemplo.test/perfil"}

        with pytest.raises(ValidationError) as erro:
            atual.full_clean()

        assert "social_links" in erro.value.error_dict

    def test_valor_que_nao_e_texto_continua_recusado(self):
        atual = config()
        atual.social_links = {"instagram": 123}

        with pytest.raises(ValidationError):
            atual.full_clean()


class TestRedesNoContexto:
    def test_so_saem_as_configuradas(self):
        atual = config()
        atual.social_links = {"facebook": "https://exemplo.test/pagina"}
        atual.save()

        redes = globais().social

        assert [rede.chave for rede in redes] == ["facebook"]

    def test_saem_na_ordem_declarada(self):
        atual = config()
        atual.social_links = {
            "instagram": "https://exemplo.test/i",
            "facebook": "https://exemplo.test/f",
        }
        atual.save()

        assert [rede.chave for rede in globais().social] == [
            chave for chave, _nome, _icone in REDES_SOCIAIS
        ]

    @pytest.mark.parametrize(
        "torta",
        [
            {"facebook": "javascript:alert(1)"},
            {"facebook": ""},
            {"facebook": None},
            {"facebook": 7},
            {"orkut": "https://exemplo.test/x"},
            ["facebook"],
            "facebook",
        ],
    )
    def test_o_que_estiver_torto_no_banco_nao_chega_a_pagina(self, torta):
        """
        `clean()` impede gravar isso pela tela. Um `update()` cru não
        passa por ele -- e a página não pode confiar em quem escreveu a
        linha.

        `config()` antes do `update()` não é enfeite: sem a linha criada,
        o `update()` não atinge nada, `globais()` cai nos padrões do
        modelo e o teste passaria sem nunca ter exercitado a defesa.
        """
        config()
        SiteSettings.objects.all().update(social_links=torta)

        assert globais().social == ()

    def test_uma_linha_torta_nao_derruba_a_pagina(self, client):
        config()
        SiteSettings.objects.all().update(social_links={"facebook": "javascript:alert(1)"})

        resposta = client.get(HOME)

        assert resposta.status_code == 200
        assert "javascript:alert(1)" not in resposta.content.decode()


# ===========================================================================
# 3. A porta do Backoffice
# ===========================================================================


class TestAcesso:
    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(TELA)

        assert resposta.status_code == 302
        assert resposta.url.startswith(reverse("accounts:login"))

    def test_usuario_comum_e_recusado(self, auth_client):
        assert auth_client.get(TELA).status_code == 403

    def test_quem_entra_no_backoffice_pode_VER(self, client, staff_user):
        client.force_login(staff_user)

        resposta = client.get(TELA)

        assert resposta.status_code == 200
        assert resposta.context["pode_editar"] is False

    def test_quem_so_ve_nao_grava(self, client, staff_user):
        """A URL continua digitável -- a recusa é no servidor."""
        client.force_login(staff_user)

        resposta = client.post(TELA, {**BASE, "site_name": "Invadido"})

        assert resposta.status_code == 403
        assert config().site_name != "Invadido"

    def test_a_tela_avisa_quem_nao_pode_editar(self, client, staff_user):
        client.force_login(staff_user)

        corpo = client.get(TELA).content.decode()

        assert "não tem permissão para alterá-las" in corpo
        assert "Salvar configurações" not in corpo

    def test_sem_csrf_nao_grava(self, editora):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(editora)

        resposta = sem_token.post(TELA, {**BASE, "site_name": "Invadido"})

        assert resposta.status_code == 403
        assert config().site_name != "Invadido"

    def test_a_permissao_nao_e_nova(self):
        """
        `content.change_sitesettings` é a que o Django já gerava para o
        modelo e que a administração do Django já cobrava. Reutilizar em
        vez de inventar é o que evita duas respostas para "quem pode
        mudar isto".
        """
        from apps.core.views import SITE_SETTINGS_PERM

        assert SITE_SETTINGS_PERM == "content.change_sitesettings"
        assert Permission.objects.filter(
            content_type__app_label="content", codename="change_sitesettings"
        ).exists()

    def test_a_permissao_esta_no_catalogo(self):
        from apps.accounts import admin_permissions

        chaves = {permissao.chave for permissao in admin_permissions.todas()}

        assert "content.change_sitesettings" in chaves


# ===========================================================================
# 4. A tela
# ===========================================================================


class TestTela:
    def test_a_rota_nao_e_mais_o_placeholder(self):
        from apps.core import views

        assert resolve(TELA).func is views.backoffice_system

    def test_o_menu_aponta_para_a_tela_real(self, client, staff_user):
        client.force_login(staff_user)

        corpo = client.get(reverse("backoffice:overview")).content.decode()

        assert f'href="{TELA}"' in corpo
        assert f'href="{TELA}#sistema"' not in corpo

    def test_tem_um_campo_por_rede_e_nao_json(self, cliente):
        corpo = cliente.get(TELA).content.decode()

        for chave, _nome, _icone in REDES_SOCIAIS:
            assert f'name="social__{chave}"' in corpo
        assert 'name="social_links"' not in corpo

    def test_salvar_identidade_e_contato(self, cliente):
        cliente.post(
            TELA,
            {
                "site_name": "Desenrola Bélgica",
                "contact_email": "contato@mail.com",
                "contact_phone": "+32 000 00 00 00",
                "contact_address": "Rua de Exemplo, 1",
            },
        )

        atual = config()
        assert atual.site_name == "Desenrola Bélgica"
        assert atual.contact_email == "contato@mail.com"
        assert atual.contact_phone == "+32 000 00 00 00"
        assert atual.contact_address == "Rua de Exemplo, 1"

    def test_salvar_uma_rede_preserva_o_formato(self, cliente):
        cliente.post(TELA, {**BASE, "social__facebook": "https://exemplo.test/pagina"})

        assert config().social_links == {"facebook": "https://exemplo.test/pagina"}

    def test_rede_em_branco_sai_do_dicionario(self, cliente):
        """Guardar `""` obrigaria o rodapé a distinguir vazio de ausente."""
        cliente.post(TELA, {**BASE, "social__facebook": "https://exemplo.test/p"})
        assert "facebook" in config().social_links

        cliente.post(TELA, {**BASE, "social__facebook": ""})

        assert config().social_links == {}

    def test_nome_em_branco_e_recusado(self, cliente):
        resposta = cliente.post(TELA, {**BASE, "site_name": ""})

        assert resposta.status_code == 200
        assert config().site_name == "Desenrola"

    def test_email_invalido_e_recusado(self, cliente):
        resposta = cliente.post(TELA, {**BASE, "contact_email": "isto não é e-mail"})

        assert resposta.status_code == 200
        assert config().contact_email == ""

    @pytest.mark.parametrize(
        "perigosa",
        [
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "data:text/html,x",
            "vbscript:msgbox(1)",
            "não é uma url",
        ],
    )
    def test_url_perigosa_ou_invalida_e_recusada_na_tela(self, cliente, perigosa):
        resposta = cliente.post(TELA, {**BASE, "social__facebook": perigosa})

        assert resposta.status_code == 200
        assert config().social_links == {}

    def test_endereco_sem_esquema_ganha_https(self, cliente):
        """
        Digitar "exemplo.test/perfil" grava "https://exemplo.test/perfil".

        É conveniência, e é SEGURA: o esquema completado é sempre
        `https`, nunca o que a pessoa teria escrito. O modelo, esse,
        continua exigindo o esquema -- quem escreve por código não ganha
        o benefício da dúvida (ver
        `TestRedesNoModelo::test_url_sem_esquema_e_recusada`).
        """
        cliente.post(TELA, {**BASE, "social__facebook": "exemplo.test/perfil"})

        assert config().social_links == {"facebook": "https://exemplo.test/perfil"}

    def test_um_campo_invalido_nao_grava_os_outros(self, cliente):
        """Formulário inválido não escreve nada -- nem a metade certa."""
        cliente.post(
            TELA,
            {
                **BASE,
                "site_name": "Novo nome",
                "social__facebook": "javascript:alert(1)",
            },
        )

        assert config().site_name == "Desenrola"

    def test_nao_duplica_as_outras_telas(self, cliente):
        """
        Cor, logo, SMTP e idiomas têm tela própria; aqui só ponteiro.

        A pergunta é sobre os campos do FORMULÁRIO, e não sobre o HTML:
        esta tela desenha campo por campo, então um campo a mais no
        `Meta.fields` não apareceria na página -- ficaria escondido,
        aceitando POST sem ninguém ver. O HTML é conferido depois, para
        o caso de alguém escrevê-lo direto no template.
        """
        resposta = cliente.get(TELA)
        campos = set(resposta.context["form"].fields)

        for duplicado in (
            "theme_primary_color",
            "theme_success_color",
            "logo",
            "favicon",
            "host",
            "port",
            "password",
            "available_document_languages",
            "default_letter_language",
        ):
            assert duplicado not in campos

        corpo = resposta.content.decode()
        for duplicado in (
            "theme_primary_color",
            'name="logo"',
            'name="favicon"',
            'name="host"',
            'name="password"',
            "default_letter_language",
        ):
            assert duplicado not in corpo

    def test_aponta_para_as_telas_que_administram_o_resto(self, cliente):
        """
        A assertiva é sobre o CARTÃO, não sobre a página: o menu lateral e
        a barra inferior do celular aparecem em toda tela do Backoffice e
        já trazem estes links -- procurar na página inteira passaria por
        causa deles, com ou sem o cartão. Daí a fatia ter FIM, e não só
        começo.
        """
        corpo = cliente.get(TELA).content.decode()
        inicio = corpo.index("Configurado em outras telas")
        cartao = corpo[inicio : corpo.index("Documentos legais", inicio)]

        for url in (
            reverse("backoffice:appearance"),
            reverse("backoffice:languages"),
            reverse("backoffice:email_settings"),
        ):
            assert f'href="{url}"' in cartao

    def test_mostra_o_estado_dos_documentos_legais_sem_edita_los(self, cliente):
        """
        Até a Etapa F esta tela dizia que não havia links legais, porque
        não havia mesmo. A Etapa G criou as duas páginas, e o cartão
        passou a mostrar o ESTADO de cada documento.

        O que não mudou, e é o que esta asserção guarda: aqui não se
        edita texto legal. Não há formulário paralelo -- o texto é
        escrito na administração do Django.
        """
        corpo = cliente.get(TELA).content.decode()
        inicio = corpo.index("Documentos legais")
        cartao = corpo[inicio:]

        assert "Sem texto" in cartao
        assert "<form" not in cartao
        assert 'name="legal.terms_of_use"' not in corpo

    def test_nao_ha_infraestrutura_inventada(self, cliente):
        corpo = cliente.get(TELA).content.decode()

        for inventado in ("Backup", "Retenção de dados", "registro de atividade"):
            assert inventado not in corpo

    def test_a_tela_ilustrativa_deixou_de_existir(self):
        """
        Até a Etapa H o cartão de Sistema tinha saído de uma tela que
        ainda existia. Na Etapa I a tela inteira saiu: era rota órfã --
        fora de todo menu -- servindo uma maquete que duplicava esta.

        A pergunta passou a ser sobre a ROTA, que é afirmação mais forte
        do que "aquele cartão não aparece mais".
        """
        from django.urls import NoReverseMatch

        with pytest.raises(NoReverseMatch):
            reverse("backoffice:templates")


# ===========================================================================
# 5. O site público
# ===========================================================================


def _escrever_rodape(html):
    """Grava um conteúdo de rodapé para o teste olhar um atalho específico."""
    from apps.content.models import PageSection, PageSectionTranslation

    secao = PageSection.objects.get(page__key="home", key="footer")
    t, _criada = PageSectionTranslation.objects.get_or_create(
        section=secao, language="pt", defaults={"content": {}}
    )
    t.content = {**(t.content or {}), "html": html}
    t.save(update_fields=["content"])


class TestSitePublico:
    def test_o_nome_vem_do_cms(self, client, cliente):
        cliente.post(TELA, {**BASE, "site_name": "Desenrola Bélgica"})

        corpo = client.get(HOME).content.decode()

        assert "Desenrola Bélgica" in corpo

    def test_o_nome_chega_ao_titulo_das_paginas_logadas(self, auth_client):
        """
        Onze títulos traziam o nome escrito à mão: trocar no Backoffice
        mudava o cabeçalho e não mudava a aba.
        """
        atual = config()
        atual.site_name = "Outro Nome"
        atual.save()

        corpo = auth_client.get(reverse("core:dashboard")).content.decode()

        assert "<title>" in corpo
        assert "Outro Nome" in corpo
        assert "· Desenrola<" not in corpo

    def test_o_contato_vem_do_cms(self, client):
        """
        O rodapé é conteúdo rico e cita o contato por ATALHOS
        (`{telefone}`, `{endereco}`, `mailto:{email_contato}`): o dado
        continua em Sistema, e muda aqui quando muda lá.
        """
        atual = config()
        atual.contact_email = "contato@mail.com"
        atual.contact_phone = "+32 000 00 00 00"
        atual.contact_address = "Rua de Exemplo, 1"
        atual.save()
        _escrever_rodape(
            '<p><a href="mailto:{email_contato}">Contato</a> {telefone} {endereco}</p>'
        )

        corpo = client.get(HOME).content.decode()

        assert "mailto:contato@mail.com" in corpo
        assert "+32 000 00 00 00" in corpo
        assert "Rua de Exemplo, 1" in corpo

    def test_sem_contato_nao_ha_link_vazio(self, client):
        corpo = client.get(HOME).content.decode()

        assert "mailto:" not in corpo
        assert "site-footer-contato" not in corpo

    def test_as_redes_vem_do_cms(self, client):
        atual = config()
        atual.social_links = {"instagram": "https://exemplo.test/perfil"}
        atual.save()
        _escrever_rodape("<p>{redes_sociais}</p>")

        corpo = client.get(HOME).content.decode()

        assert "https://exemplo.test/perfil" in corpo
        assert "ph-instagram-logo" in corpo

    def test_rede_nao_configurada_nao_vira_icone_morto(self, client):
        atual = config()
        atual.social_links = {"instagram": "https://exemplo.test/perfil"}
        atual.save()
        _escrever_rodape("<p>{redes_sociais}</p>")

        corpo = client.get(HOME).content.decode()

        assert "ph-facebook-logo" not in corpo

    def test_sem_rede_nenhuma_o_rodape_nao_quebra(self, client):
        corpo = client.get(HOME).content.decode()

        assert "site-footer-social" not in corpo
        assert "site-footer" in corpo

    def test_o_ano_do_rodape_e_do_servidor(self, client):
        """
        Estava "2026" escrito no código, em dois lugares. O ano corrente
        não é decisão editorial -- não vira configuração.
        """
        corpo = client.get(HOME).content.decode()
        ano = str(datetime.date.today().year)

        assert f"&copy; {ano}" in corpo or f"© {ano}" in corpo

    def test_nenhum_ano_escrito_no_rodape(self):
        """
        O teste acima sozinho não serve de guarda: enquanto o ano fixo
        coincidir com o corrente, ele passa dos dois jeitos. Aqui a
        pergunta é sobre a FONTE -- nenhum ano literal no template --, e
        ela já falha hoje se alguém reescrever o valor à mão.
        """
        import pathlib
        import re

        raiz = pathlib.Path(__file__).resolve().parents[3]
        fonte = (raiz / "templates" / "components" / "site_footer.html").read_text(
            encoding="utf-8"
        )
        # O bloco de comentário explica a decisão e cita o ano antigo.
        markup = fonte[fonte.index("{% endcomment %}") :]

        assert re.search(r"20\d\d", markup) is None
        # O ano entra pelo atalho `{ano}` do conteúdo rico, resolvido
        # pelo servidor (`content.rodape.valores_dos_atalhos`) -- nem o
        # template nem o HTML padrão trazem um ano escrito.
        from apps.content import rodape

        assert re.search(r"20\d\d", rodape.HTML_PADRAO) is None
        assert "{ano}" in rodape.HTML_PADRAO

    def test_o_nome_do_rodape_movel_vem_do_cms(self, client):
        atual = config()
        atual.site_name = "Outro Nome"
        atual.save()

        corpo = client.get(HOME).content.decode()

        rodape = corpo[corpo.index("©") :][:200]
        assert "Outro Nome" in rodape

    def test_sem_documento_publicado_o_rodape_nao_traz_link_legal(self, client):
        """
        Até a Etapa F os dois links existiam apontando para `#`. A Etapa
        G trocou a regra: sem texto publicado, o link não existe -- e em
        nenhuma hipótese vira um endereço inventado.

        A cobertura completa das páginas legais está em
        `apps/content/tests/test_paginas_legais.py`.
        """
        corpo = client.get(HOME).content.decode()

        assert 'href="#"' not in corpo
        assert "termos-de-uso" not in corpo
        assert "/legal/" not in corpo

    def test_a_aparencia_continua_funcionando(self, client):
        """Regressão da Etapa C: as cores continuam saindo no `<style>`."""
        atual = config()
        atual.theme_primary_color = "#0f8f8a"
        atual.save()

        corpo = client.get(HOME).content.decode()

        assert "--p:#0f8f8a" in corpo

    def test_o_conteudo_e_escapado(self, client, cliente):
        cliente.post(TELA, {**BASE, "site_name": "<script>alert(1)</script>"})

        corpo = client.get(HOME).content.decode()

        assert "<script>alert(1)</script>" not in corpo
        assert "&lt;script&gt;" in corpo


# ===========================================================================
# 6. O custo
# ===========================================================================


class TestCusto:
    def test_o_rodape_nao_custa_consulta_a_mais(self, client):
        """
        Contato e redes vêm do MESMO registro que o nome e as cores. Ler
        mais campos do retrato não pode virar mais uma ida ao banco.
        """
        from django.core.cache import cache

        def consultas():
            cache.clear()
            with CaptureQueriesContext(connection) as capturadas:
                client.get(HOME)
            return len([c for c in capturadas if "sitesettings" in c["sql"]])

        sem_nada = consultas()

        atual = config()
        atual.contact_email = "contato@mail.com"
        atual.contact_phone = "+32 000 00 00 00"
        atual.contact_address = "Rua de Exemplo, 1"
        atual.social_links = {
            "facebook": "https://exemplo.test/f",
            "instagram": "https://exemplo.test/i",
        }
        atual.save()

        assert consultas() == sem_nada == 1

    def test_continua_preguicoso(self, client, auth_client):
        """
        Uma página que não toca em `site_config` não paga consulta
        nenhuma por causa desta ponte -- comportamento da Etapa A, que
        acrescentar campos não pode ter desfeito.
        """
        with CaptureQueriesContext(connection) as capturadas:
            auth_client.get("/healthz/")

        assert [c for c in capturadas if "sitesettings" in c["sql"]] == []
