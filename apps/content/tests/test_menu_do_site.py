"""
A barra superior do site, administrável pelo Backoffice.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a barra volte a ser escrita no template.** Até a Etapa 11 os
   dois links eram literais em `site_nav.html`, com um `{% if %}` para
   esconder "Parceiros" quando não houvesse nenhum;
2. **Que exista item morto.** Uma âncora que a Home não desenha
   (`#promoções`) passava no validador e virava link para lugar nenhum
   -- em duas frentes: o formulário recusa criar, e a Home esconde o que
   já esteja gravado;
3. **Que a barra dependa do Admin do Django**;
4. **Que "ordenar" seja um botão que não muda nada** -- `order` nasce 0
   para todos e o desempate é o `pk`;
5. **Que o celular perca os itens.** A barra tem duas formas, e as duas
   leem o mesmo cadastro.

O CADASTRO VEM SEMEADO
----------------------
A migration `content.0008` cria dois itens: "Como funciona"
(`#como-funciona`) e "Parceiros" (`#parceiros`). Os testes contam com
isso -- é o estado real de qualquer banco do projeto.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.content.forms import FormularioDeItemDoMenu
from apps.content.models import MenuItem, PageSection, Partner

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")
NOVO = reverse("backoffice:menu_item_new")


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
    return _com_permissoes("view_pagesection", "change_pagesection")


@pytest.fixture
def leitora(db):
    return _com_permissoes("view_pagesection", email="leitora@mail.com")


@pytest.fixture
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


@pytest.fixture
def cliente_leitora(leitora):
    c = Client()
    c.force_login(leitora)
    return c


def secao(chave):
    return PageSection.objects.get(page__key="home", key=chave)


def url_da_navbar():
    return reverse("backoffice:content_section", args=[secao("navbar").pk])


def item(destino):
    return MenuItem.objects.get(destination=destino)


def barra(client):
    """O HTML da barra superior, nas duas formas (desktop e celular)."""
    return client.get(HOME).content.decode()


def rotulos_na_barra(client):
    """Os rótulos que a barra de fato mostra, na ordem, sem repetir."""
    corpo = barra(client)
    vistos = []
    for registro in MenuItem.objects.all():
        marca = f'class="nav-link" href="{registro.destination}">{registro.label}<'
        if marca in corpo:
            vistos.append((corpo.index(marca), registro.label))
    return [rotulo for _posicao, rotulo in sorted(vistos)]


@pytest.fixture
def com_parceiro(db):
    """A seção de parceiros só entra na Home quando há parceiro."""
    return Partner.objects.create(name="Padaria", url="https://exemplo.test/")


# ===========================================================================
# 1. Âncora morta -- o defeito que este bloco fecha
# ===========================================================================


class TestAncoraMorta:
    def test_ancora_que_a_home_nao_desenha_nao_aparece(self, client, com_parceiro):
        """
        `#promocoes` não existe em parte nenhuma da página. Até a Etapa 11
        ele caía no caso "âncora desconhecida" e aparecia na barra levando
        a lugar nenhum.
        """
        MenuItem.objects.create(label="Promoções", destination="#promocoes", order=9)

        assert "Promoções" not in barra(client)

    def test_a_ancora_de_parceiros_some_quando_nao_ha_parceiro(self, client):
        assert Partner.objects.count() == 0

        assert "#parceiros" not in barra(client)

    def test_a_ancora_de_parceiros_volta_quando_ha_parceiro(self, client, com_parceiro):
        assert "#parceiros" in barra(client)

    def test_a_ancora_some_quando_a_parte_esta_desativada(self, client):
        how = secao("how")
        how.is_active = False
        how.save(update_fields=["is_active"])

        assert "#como-funciona" not in barra(client)

    def test_caminho_do_site_passa_sempre(self, client):
        """O servidor não sabe o que existe do outro lado; fingir seria pior."""
        MenuItem.objects.create(label="Ajuda", destination="/pt/ajuda/", order=9)

        assert "/pt/ajuda/" in barra(client)

    def test_endereco_externo_passa_sempre(self, client):
        MenuItem.objects.create(label="Blog", destination="https://blog.test/", order=9)

        assert "https://blog.test/" in barra(client)


class TestFormularioRecusaAncoraMorta:
    def test_recusa_ancora_que_nao_existe(self):
        form = FormularioDeItemDoMenu(
            data={"label": "Promoções", "destination": "#promocoes", "order": 0}
        )

        assert not form.is_valid()
        assert "destination" in form.errors

    @pytest.mark.parametrize("destino", ["#como-funciona", "#parceiros"])
    def test_aceita_as_ancoras_reais(self, destino):
        form = FormularioDeItemDoMenu(
            data={"label": "X", "destination": destino, "order": 0}
        )

        assert form.is_valid(), form.errors

    @pytest.mark.parametrize(
        "destino", ["/pt/ajuda/", "https://blog.test/", "http://blog.test/"]
    )
    def test_aceita_caminho_e_endereco(self, destino):
        form = FormularioDeItemDoMenu(
            data={"label": "X", "destination": destino, "order": 0}
        )

        assert form.is_valid(), form.errors

    @pytest.mark.parametrize(
        "destino", ["javascript:alert(1)", "data:text/html,x", "ftp://x.test/"]
    )
    def test_recusa_o_que_nao_e_destino(self, destino):
        """O valor termina dentro de um `href`, onde o autoescape não protege."""
        form = FormularioDeItemDoMenu(
            data={"label": "X", "destination": destino, "order": 0}
        )

        assert not form.is_valid()


# ===========================================================================
# 2. Acesso
# ===========================================================================


def _rotas(registro):
    return [
        (NOVO, "post"),
        (reverse("backoffice:menu_item_activation", args=[registro.pk]), "post"),
        (reverse("backoffice:menu_item_move", args=[registro.pk]), "post"),
        (reverse("backoffice:menu_item_delete", args=[registro.pk]), "get"),
    ]


class TestAcesso:
    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(NOVO)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta["Location"]

    def test_usuario_comum_e_recusado(self, auth_client):
        assert auth_client.get(NOVO).status_code in (302, 403)

    def test_staff_sem_a_permissao_e_recusado(self, client, staff_user):
        client.force_login(staff_user)

        assert client.get(NOVO).status_code == 403

    @pytest.mark.parametrize("indice", range(4))
    def test_quem_so_ve_nao_muda_nada(self, cliente_leitora, indice):
        """
        `view_pagesection` abre a Central; mexer na barra exige
        `change_pagesection`, e a checagem é no servidor.
        """
        url, metodo = _rotas(item("#parceiros"))[indice]

        assert getattr(cliente_leitora, metodo)(url).status_code == 403

    def test_quem_so_ve_abre_o_item_mas_nao_grava(self, cliente_leitora):
        registro = item("#parceiros")
        url = reverse("backoffice:menu_item_edit", args=[registro.pk])

        assert cliente_leitora.get(url).status_code == 200
        assert cliente_leitora.post(
            url, {"label": "Outro", "destination": "#parceiros", "order": 0}
        ).status_code == 403
        assert item("#parceiros").label == "Parceiros"

    def test_item_inexistente_da_404(self, cliente):
        assert cliente.get(
            reverse("backoffice:menu_item_edit", args=[9999])
        ).status_code == 404


class TestCSRF:
    @pytest.mark.parametrize(
        "rota", ["menu_item_activation", "menu_item_move", "menu_item_delete"]
    )
    def test_post_sem_token_e_recusado(self, editora, rota):
        registro = item("#parceiros")
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(editora)

        assert sem_token.post(
            reverse(f"backoffice:{rota}", args=[registro.pk])
        ).status_code == 403

    def test_criar_sem_token_e_recusado(self, editora):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(editora)

        resposta = sem_token.post(
            NOVO, {"label": "Novo", "destination": "/pt/x/", "order": 0}
        )

        assert resposta.status_code == 403
        assert not MenuItem.objects.filter(label="Novo").exists()


# ===========================================================================
# 3. O cadastro
# ===========================================================================


class TestCriar:
    def test_o_formulario_abre(self, cliente):
        corpo = cliente.get(NOVO).content.decode()

        assert 'name="label"' in corpo
        assert 'name="destination"' in corpo
        assert 'name="order"' in corpo

    def test_oferece_as_ancoras_reais(self, cliente):
        """Um `datalist` com as partes que a Home de fato desenha."""
        corpo = cliente.get(NOVO).content.decode()

        assert '<option value="#como-funciona">' in corpo
        assert '<option value="#parceiros">' in corpo

    def test_acrescenta_e_aparece_na_barra(self, cliente, client):
        cliente.post(
            NOVO,
            {"label": "Ajuda", "destination": "/pt/ajuda/", "is_active": "on", "order": 9},
        )

        assert MenuItem.objects.filter(label="Ajuda").exists()
        assert "Ajuda" in barra(client)

    def test_ancora_morta_nao_e_cadastrada(self, cliente):
        resposta = cliente.post(
            NOVO, {"label": "Promoções", "destination": "#promocoes", "order": 9}
        )

        assert resposta.status_code == 200
        assert not MenuItem.objects.filter(label="Promoções").exists()


class TestEditar:
    def test_abre_com_os_dados(self, cliente):
        registro = item("#parceiros")

        corpo = cliente.get(
            reverse("backoffice:menu_item_edit", args=[registro.pk])
        ).content.decode()

        assert 'value="Parceiros"' in corpo
        assert 'value="#parceiros"' in corpo

    def test_muda_o_rotulo_e_a_barra_acompanha(self, cliente, client, com_parceiro):
        registro = item("#parceiros")

        cliente.post(
            reverse("backoffice:menu_item_edit", args=[registro.pk]),
            {"label": "Nossos parceiros", "destination": "#parceiros", "is_active": "on",
             "order": 2},
        )

        assert "Nossos parceiros" in barra(client)

    def test_muda_o_destino(self, cliente):
        registro = item("#parceiros")

        cliente.post(
            reverse("backoffice:menu_item_edit", args=[registro.pk]),
            {"label": "Parceiros", "destination": "/pt/parceiros/", "is_active": "on",
             "order": 2},
        )

        registro.refresh_from_db()
        assert registro.destination == "/pt/parceiros/"


class TestSituacao:
    def test_desativa_e_some_da_barra(self, cliente, client):
        registro = item("#como-funciona")
        assert 'href="#como-funciona"' in barra(client)

        cliente.post(
            reverse("backoffice:menu_item_activation", args=[registro.pk]), {"ativo": "0"}
        )

        registro.refresh_from_db()
        assert not registro.is_active
        # O LINK da barra, e nao o texto: "Como funciona" tambem e o
        # titulo da secao `how` na propria Home.
        assert 'href="#como-funciona"' not in barra(client)

    def test_ativa_e_volta(self, cliente, client):
        registro = item("#como-funciona")
        registro.is_active = False
        registro.save(update_fields=["is_active"])

        cliente.post(
            reverse("backoffice:menu_item_activation", args=[registro.pk]), {"ativo": "1"}
        )

        assert 'href="#como-funciona"' in barra(client)

    def test_nao_apaga(self, cliente):
        registro = item("#como-funciona")

        cliente.post(
            reverse("backoffice:menu_item_activation", args=[registro.pk]), {"ativo": "0"}
        )

        assert MenuItem.objects.filter(pk=registro.pk).exists()

    def test_get_nao_muda_situacao(self, cliente):
        registro = item("#como-funciona")

        resposta = cliente.get(
            reverse("backoffice:menu_item_activation", args=[registro.pk])
        )

        assert resposta.status_code == 405
        assert MenuItem.objects.get(pk=registro.pk).is_active


class TestRemover:
    def test_o_get_so_pergunta(self, cliente):
        registro = item("#como-funciona")

        corpo = cliente.get(
            reverse("backoffice:menu_item_delete", args=[registro.pk])
        ).content.decode()

        assert "Como funciona" in corpo
        assert "não tem volta" in corpo
        assert MenuItem.objects.filter(pk=registro.pk).exists()

    def test_o_post_apaga_e_some_da_barra(self, cliente, client):
        registro = item("#como-funciona")

        cliente.post(reverse("backoffice:menu_item_delete", args=[registro.pk]))

        assert not MenuItem.objects.filter(pk=registro.pk).exists()
        assert 'href="#como-funciona"' not in barra(client)


class TestOrdem:
    def test_sobe_e_a_barra_acompanha(self, cliente, client, com_parceiro):
        assert rotulos_na_barra(client) == ["Como funciona", "Parceiros"]

        cliente.post(
            reverse("backoffice:menu_item_move", args=[item("#parceiros").pk]),
            {"direcao": "subir"},
        )

        assert rotulos_na_barra(client) == ["Parceiros", "Como funciona"]

    def test_desce(self, cliente, client, com_parceiro):
        cliente.post(
            reverse("backoffice:menu_item_move", args=[item("#como-funciona").pk]),
            {"direcao": "descer"},
        )

        assert rotulos_na_barra(client) == ["Parceiros", "Como funciona"]

    def test_funciona_com_todos_empatados_em_zero(self, cliente, client, com_parceiro):
        """O caso real de qualquer cadastro feito pela tela sem mexer na ordem."""
        MenuItem.objects.all().update(order=0)

        cliente.post(
            reverse("backoffice:menu_item_move", args=[item("#parceiros").pk]),
            {"direcao": "subir"},
        )

        assert rotulos_na_barra(client) == ["Parceiros", "Como funciona"]
        assert [i.order for i in MenuItem.objects.all()] == [1, 2]

    def test_o_primeiro_nao_sobe(self, cliente, client, com_parceiro):
        cliente.post(
            reverse("backoffice:menu_item_move", args=[item("#como-funciona").pk]),
            {"direcao": "subir"},
        )

        assert rotulos_na_barra(client) == ["Como funciona", "Parceiros"]

    def test_o_ultimo_nao_desce(self, cliente, client, com_parceiro):
        cliente.post(
            reverse("backoffice:menu_item_move", args=[item("#parceiros").pk]),
            {"direcao": "descer"},
        )

        assert rotulos_na_barra(client) == ["Como funciona", "Parceiros"]


# ===========================================================================
# 4. A tela: dentro do editor da Barra superior
# ===========================================================================


class TestEditorDaBarra:
    def test_a_barra_mostra_os_itens(self, cliente):
        corpo = cliente.get(url_da_navbar()).content.decode()

        assert "Itens do menu" in corpo
        assert "Como funciona" in corpo
        assert "#parceiros" in corpo

    def test_oferece_acrescentar_e_remover(self, cliente):
        corpo = cliente.get(url_da_navbar()).content.decode()

        assert reverse("backoffice:menu_item_new") in corpo
        assert reverse(
            "backoffice:menu_item_delete", args=[item("#parceiros").pk]
        ) in corpo

    def test_quem_so_ve_nao_recebe_acao_que_nao_pode(self, cliente_leitora):
        corpo = cliente_leitora.get(url_da_navbar()).content.decode()

        assert "Novo item" not in corpo
        assert reverse("backoffice:menu_item_new") not in corpo
        assert "Remover" not in corpo

    def test_a_secao_de_parceiros_leva_ao_cadastro_deles(self, db):
        """
        O link só para quem pode entrar: a tela de Parceiros cobra
        `content.view_partner`, que quem edita conteúdo não tem por
        padrão.
        """
        quem_pode = Client()
        quem_pode.force_login(
            _com_permissoes(
                "view_pagesection", "change_pagesection", "view_partner",
                email="tambem-parceiros@mail.com",
            )
        )

        corpo = quem_pode.get(
            reverse("backoffice:content_section", args=[secao("partners").pk])
        ).content.decode()

        assert reverse("backoffice:partners") in corpo

    def test_quem_nao_pode_ver_parceiros_nao_recebe_o_link(self, cliente):
        """O espelho: oferecer a porta a quem levaria um 403 é promessa quebrada."""
        corpo = cliente.get(
            reverse("backoffice:content_section", args=[secao("partners").pk])
        ).content.decode()

        assert "Os parceiros" in corpo
        assert "Abrir o cadastro" not in corpo

    def test_secao_sem_cadastro_nao_mostra_nenhum(self, cliente):
        corpo = cliente.get(
            reverse("backoffice:content_section", args=[secao("how").pk])
        ).content.decode()

        assert "Itens do menu" not in corpo
        # O cartao do cadastro de parceiros, e nao a URL: o menu lateral
        # do Backoffice tem um link para Parceiros em TODA tela.
        assert "Abrir o cadastro" not in corpo

    def test_o_titulo_nao_vaza_chave_tecnica(self, cliente):
        """
        A tela mostrava `secao.key` -- "navbar", "cta", "how". Chave
        técnica na interface é vazamento de implementação para quem
        administra.
        """
        corpo = cliente.get(url_da_navbar()).content.decode()

        assert "<h1>Barra superior</h1>" in corpo
        assert "<h1>navbar</h1>" not in corpo


# ===========================================================================
# 5. As duas formas da barra
# ===========================================================================


class TestCelular:
    def test_o_item_aparece_nas_duas_formas(self, client, com_parceiro):
        """
        A barra tem uma versão de desktop e um dropdown de celular, e as
        duas leem o mesmo cadastro. Um item que só existisse numa delas
        seria um item que some ao girar o aparelho.
        """
        corpo = barra(client)

        assert corpo.count('href="#como-funciona"') == 2

    def test_item_desativado_some_das_duas(self, client):
        registro = item("#como-funciona")
        registro.is_active = False
        registro.save(update_fields=["is_active"])

        assert 'href="#como-funciona"' not in barra(client)

    def test_sem_item_nenhum_a_barra_continua_de_pe(self, client):
        """Marca e botões de conta são estrutura do produto, não cadastro."""
        MenuItem.objects.all().delete()

        corpo = barra(client)

        assert "nav-desktop" in corpo
        assert reverse("accounts:login") in corpo
