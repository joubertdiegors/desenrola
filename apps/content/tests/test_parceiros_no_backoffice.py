"""
Parceiros: o cadastro inteiro dentro do Backoffice.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o produto volte a depender do Admin do Django.** Até a Etapa 11
   esta tela só mostrava e mandava quem quisesse cadastrar para lá;
2. **Que uma ação apareça para quem o servidor recusaria** -- ou, muito
   pior, que o servidor aceite de quem não pode. Cada rota tem a sua
   permissão, e cada uma é exercida contra quem não a tem;
3. **Que "ordenar" seja um botão que não muda nada.** `order` nasce 0
   para todo mundo e o desempate é o `pk`: trocar o número de dois
   empatados não moveria ninguém;
4. **Que apagar (ou trocar) um parceiro leve junto uma imagem
   compartilhada** -- e, desde o Bloco D, o oposto também: **que uma
   imagem que ninguém mais usa fique órfã** no disco e na Biblioteca;
5. **Que a Home deixe de refletir ordem e situação.**
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.content.models import Asset, Partner

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")
LISTA = reverse("backoffice:partners")
NOVO = reverse("backoffice:partner_new")


def _gif():
    return SimpleUploadedFile(
        "x.gif",
        b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
        b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
        content_type="image/gif",
    )


def _com_permissoes(*codenames, email="parceiros@mail.com"):
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


TODAS = ("view_partner", "add_partner", "change_partner", "delete_partner")


@pytest.fixture(autouse=True)
def _media_isolada(settings, tmp_path):
    """Sem isto a suíte gravaria um GIF no `media/` do repositório."""
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def administradora(db):
    """Vê, cadastra, edita e remove."""
    return _com_permissoes(*TODAS)


@pytest.fixture
def leitora(db):
    """Só vê."""
    return _com_permissoes("view_partner", email="leitora@mail.com")


@pytest.fixture
def cliente(administradora):
    c = Client()
    c.force_login(administradora)
    return c


@pytest.fixture
def cliente_leitora(leitora):
    c = Client()
    c.force_login(leitora)
    return c


def criar(nome, **campos):
    campos.setdefault("url", "https://exemplo.test/x")
    return Partner.objects.create(name=nome, **campos)


def nomes_na_ordem():
    return [p.name for p in Partner.objects.all()]


def _direcoes(corpo, parceiro):
    """As direcoes de ordem oferecidas para aquele parceiro, na ordem da tela."""
    import re

    acao = reverse("backoffice:partner_move", args=[parceiro.pk])
    bloco = re.findall(
        rf'<form[^>]*action="{re.escape(acao)}"[^>]*>(.*?)</form>', corpo, re.S
    )
    return [re.search(r'name="direcao" value="(\w+)"', f).group(1) for f in bloco]


# ===========================================================================
# 1. Acesso: cada rota tem a sua permissão
# ===========================================================================


def _rotas(parceiro):
    """(url, método, permissão exigida) de cada porta da tela."""
    return [
        (LISTA, "get", "view_partner"),
        (NOVO, "post", "add_partner"),
        (reverse("backoffice:partner_edit", args=[parceiro.pk]), "get", "view_partner"),
        (
            reverse("backoffice:partner_activation", args=[parceiro.pk]),
            "post",
            "change_partner",
        ),
        (reverse("backoffice:partner_move", args=[parceiro.pk]), "post", "change_partner"),
        (
            reverse("backoffice:partner_delete", args=[parceiro.pk]),
            "get",
            "delete_partner",
        ),
    ]


class TestAcesso:
    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(LISTA)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta["Location"]

    def test_usuario_comum_e_recusado(self, auth_client):
        assert auth_client.get(LISTA).status_code in (302, 403)

    def test_staff_sem_a_permissao_e_recusado(self, client, staff_user):
        """`access_backoffice` abre a porta do prédio, não a desta sala."""
        client.force_login(staff_user)

        assert client.get(LISTA).status_code == 403

    @pytest.mark.parametrize("indice", range(6))
    def test_cada_rota_recusa_quem_nao_tem_a_permissao_dela(self, client, indice):
        """
        A pessoa tem TODAS as permissões de parceiro MENOS a que aquela
        rota exige. Sem isto, bastaria `view_partner` para tudo passar e
        a separação seria decorativa.
        """
        parceiro = criar("Um")
        url, metodo, exigida = _rotas(parceiro)[indice]
        outras = [c for c in TODAS if c != exigida]
        pessoa = _com_permissoes(*outras, email=f"sem-{exigida}@mail.com")
        client.force_login(pessoa)

        resposta = getattr(client, metodo)(url)

        assert resposta.status_code == 403, f"{metodo.upper()} {url} passou sem {exigida}"

    @pytest.mark.parametrize("indice", range(6))
    def test_cada_rota_aceita_quem_tem_a_permissao_dela(self, cliente, indice):
        """O espelho do anterior: com a permissão, a porta abre."""
        parceiro = criar("Um")
        url, metodo, _exigida = _rotas(parceiro)[indice]

        resposta = getattr(cliente, metodo)(url)

        assert resposta.status_code in (200, 302), f"{metodo.upper()} {url} recusou"

    def test_quem_so_ve_nao_grava(self, cliente_leitora):
        """Abrir o cadastro é uma coisa; gravar é outra, e a checagem é no POST."""
        parceiro = criar("Um")
        url = reverse("backoffice:partner_edit", args=[parceiro.pk])

        assert cliente_leitora.get(url).status_code == 200
        assert cliente_leitora.post(url, {"name": "Outro", "order": 0}).status_code == 403
        assert Partner.objects.get(pk=parceiro.pk).name == "Um"

    def test_parceiro_inexistente_da_404(self, cliente):
        assert cliente.get(reverse("backoffice:partner_edit", args=[9999])).status_code == 404


class TestCSRF:
    """Todo POST desta tela passa pela checagem; nenhum é exceção."""

    @pytest.mark.parametrize("rota", ["partner_activation", "partner_move", "partner_delete"])
    def test_post_sem_token_e_recusado(self, administradora, rota):
        parceiro = criar("Um")
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(administradora)

        resposta = sem_token.post(reverse(f"backoffice:{rota}", args=[parceiro.pk]))

        assert resposta.status_code == 403

    def test_criar_sem_token_e_recusado(self, administradora):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(administradora)

        resposta = sem_token.post(NOVO, {"name": "Novo", "order": 0})

        assert resposta.status_code == 403
        assert not Partner.objects.filter(name="Novo").exists()

    def test_o_formulario_traz_o_token(self, cliente):
        assert "csrfmiddlewaretoken" in cliente.get(NOVO).content.decode()


# ===========================================================================
# 2. A lista
# ===========================================================================


class TestLista:
    def test_sem_parceiros_diz_que_nao_ha(self, cliente):
        corpo = cliente.get(LISTA).content.decode()

        assert "Nenhum parceiro cadastrado" in corpo

    def test_mostra_o_parceiro_do_banco(self, cliente):
        criar("Padaria Central", description="Pão de verdade")

        corpo = cliente.get(LISTA).content.decode()

        assert "Padaria Central" in corpo
        assert "Pão de verdade" in corpo

    def test_mostra_a_imagem_de_verdade(self, cliente):
        """A logomarca, e não uma etiqueta dizendo que existe."""
        imagem = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif(), alt_text="Marca")
        criar("Com imagem", logo=imagem)

        corpo = cliente.get(LISTA).content.decode()

        assert f'src="{imagem.file.url}"' in corpo
        assert 'alt="Marca"' in corpo

    def test_diz_quando_falta_imagem(self, cliente):
        """O nome do parceiro nao pode ser a frase testada, senao o teste
        passaria com ou sem a etiqueta."""
        criar("Padaria")

        corpo = cliente.get(LISTA).content.decode()

        assert "Sem imagem" in corpo
        assert "bo-parceiro-logo" not in corpo

    def test_diz_quem_aparece_e_quem_esta_oculto(self, cliente):
        criar("Visível")
        criar("Escondido", is_active=False)

        corpo = cliente.get(LISTA).content.decode()

        assert "Aparece" in corpo
        assert "Oculto" in corpo

    def test_nao_manda_mais_ninguem_para_o_admin_do_django(self, cliente):
        """
        A regressão que este bloco existe para impedir: a tela voltar a
        delegar o cadastro para fora do produto.
        """
        criar("Um")

        corpo = cliente.get(LISTA).content.decode()

        assert "/admin/" not in corpo
        assert "administração do Django" not in corpo

    def test_quem_so_ve_nao_recebe_acao_que_nao_pode(self, cliente_leitora):
        criar("Um")

        corpo = cliente_leitora.get(LISTA).content.decode()

        assert "Novo parceiro" not in corpo
        assert "Remover" not in corpo
        assert "Desativar" not in corpo

    def test_mais_parceiros_nao_custam_mais_consultas(self, cliente):
        """
        `select_related("logo")`: a lista mostra a imagem de cada linha, e
        sem isto cada parceiro custaria uma consulta a mais -- o N+1
        clássico, que só aparece quando o cadastro cresce.
        """
        for i in range(3):
            criar(f"P{i}", logo=Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif()))
        com_tres = _consultas(cliente)

        for i in range(3, 9):
            criar(f"P{i}", logo=Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif()))

        assert len(_consultas(cliente)) == len(com_tres)


def _consultas(cliente):
    """
    As consultas da lista que tocam parceiro OU imagem.

    `content_asset` e o ponto todo: sem `select_related("logo")` o N+1
    nao cai em `content_partner` -- a lista dele continua sendo uma
    consulta so --, cai em UMA CONSULTA DE IMAGEM POR LINHA. Filtrar so
    por parceiro faria o teste passar justamente no caso que ele existe
    para pegar.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as capturadas:
        cliente.get(LISTA)
    return [
        c
        for c in capturadas.captured_queries
        if "content_partner" in c["sql"] or "content_asset" in c["sql"]
    ]


# ===========================================================================
# 3. Cadastrar
# ===========================================================================


class TestCriar:
    def test_o_formulario_abre(self, cliente):
        corpo = cliente.get(NOVO).content.decode()

        assert "Novo parceiro" in corpo
        assert 'name="name"' in corpo
        assert 'name="url"' in corpo
        assert 'name="logo"' in corpo
        assert 'name="order"' in corpo

    def test_cadastra(self, cliente):
        resposta = cliente.post(
            NOVO,
            {
                "name": "Gráfica Nova",
                "description": "Impressos",
                "url": "https://grafica.test/",
                "is_active": "on",
                "order": 0,
            },
        )

        assert resposta.status_code == 302
        parceiro = Partner.objects.get(name="Gráfica Nova")
        assert parceiro.description == "Impressos"
        assert parceiro.url == "https://grafica.test/"
        assert parceiro.is_active

    def test_cadastra_com_imagem_da_biblioteca(self, cliente):
        imagem = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif())

        cliente.post(NOVO, {"name": "Com logo", "logo": imagem.pk, "order": 0})

        assert Partner.objects.get(name="Com logo").logo_id == imagem.pk

    def test_sem_nome_nao_cadastra(self, cliente):
        resposta = cliente.post(NOVO, {"name": "", "order": 0})

        assert resposta.status_code == 200
        assert not Partner.objects.exists()

    def test_endereco_invalido_nao_cadastra(self, cliente):
        resposta = cliente.post(NOVO, {"name": "X", "url": "javascript:alert(1)", "order": 0})

        assert resposta.status_code == 200
        assert not Partner.objects.exists()

    def test_a_biblioteca_nao_oferece_imagem_desativada(self, cliente):
        viva = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif(), alt_text="viva")
        morta = Asset.objects.create(
            kind=Asset.Kind.PARTNER, file=_gif(), alt_text="morta", is_active=False
        )

        corpo = cliente.get(NOVO).content.decode()

        assert f'<option value="{viva.pk}">' in corpo
        assert f'<option value="{morta.pk}">' not in corpo


# ===========================================================================
# 4. Editar
# ===========================================================================


class TestEditar:
    def test_abre_com_os_dados(self, cliente):
        parceiro = criar("Padaria", description="Pão")

        corpo = cliente.get(
            reverse("backoffice:partner_edit", args=[parceiro.pk])
        ).content.decode()

        assert 'value="Padaria"' in corpo
        assert "Pão" in corpo

    def test_altera(self, cliente):
        parceiro = criar("Antigo")

        cliente.post(
            reverse("backoffice:partner_edit", args=[parceiro.pk]),
            {"name": "Novo", "url": "https://novo.test/", "is_active": "on", "order": 3},
        )

        parceiro.refresh_from_db()
        assert parceiro.name == "Novo"
        assert parceiro.order == 3

    def test_tirar_a_imagem_apaga_o_asset_orfao(self, cliente):
        """
        Desde o Bloco D, desassociar limpa a imagem que ficou sem uso --
        `test_tirar_a_imagem_preserva_o_asset_compartilhado`, logo
        abaixo, cobre o caso em que outra coisa ainda a usa.
        """
        imagem = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif())
        parceiro = criar("Com logo", logo=imagem)

        cliente.post(
            reverse("backoffice:partner_edit", args=[parceiro.pk]),
            {"name": "Com logo", "logo": "", "order": 0},
        )

        parceiro.refresh_from_db()
        assert parceiro.logo_id is None
        assert not Asset.objects.filter(pk=imagem.pk).exists()

    def test_tirar_a_imagem_preserva_o_asset_compartilhado(self, cliente):
        """A biblioteca é compartilhada: uma imagem em uso alhures não some."""
        imagem = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif())
        parceiro = criar("Com logo", logo=imagem)
        criar("Outro parceiro com a mesma logo", logo=imagem)

        cliente.post(
            reverse("backoffice:partner_edit", args=[parceiro.pk]),
            {"name": "Com logo", "logo": "", "order": 0},
        )

        parceiro.refresh_from_db()
        assert parceiro.logo_id is None
        assert Asset.objects.filter(pk=imagem.pk).exists()


# ===========================================================================
# 5. Situação
# ===========================================================================


class TestSituacao:
    def test_desativa_e_some_da_home(self, cliente, client):
        parceiro = criar("Padaria")
        assert "Padaria" in client.get(HOME).content.decode()

        cliente.post(
            reverse("backoffice:partner_activation", args=[parceiro.pk]), {"ativo": "0"}
        )

        parceiro.refresh_from_db()
        assert not parceiro.is_active
        assert "Padaria" not in client.get(HOME).content.decode()

    def test_ativa_e_volta_para_a_home(self, cliente, client):
        parceiro = criar("Padaria", is_active=False)

        cliente.post(
            reverse("backoffice:partner_activation", args=[parceiro.pk]), {"ativo": "1"}
        )

        parceiro.refresh_from_db()
        assert parceiro.is_active
        assert "Padaria" in client.get(HOME).content.decode()

    def test_nao_apaga_nada(self, cliente):
        parceiro = criar("Padaria")

        cliente.post(
            reverse("backoffice:partner_activation", args=[parceiro.pk]), {"ativo": "0"}
        )

        assert Partner.objects.filter(pk=parceiro.pk).exists()

    def test_get_nao_muda_situacao(self, cliente):
        """Mudança de estado por GET seria acionável por um link qualquer."""
        parceiro = criar("Padaria")

        resposta = cliente.get(reverse("backoffice:partner_activation", args=[parceiro.pk]))

        assert resposta.status_code == 405
        assert Partner.objects.get(pk=parceiro.pk).is_active


# ===========================================================================
# 6. Ordem
# ===========================================================================


class TestOrdem:
    def test_sobe(self, cliente):
        criar("A")
        criar("B")
        c = criar("C")

        cliente.post(reverse("backoffice:partner_move", args=[c.pk]), {"direcao": "subir"})

        assert nomes_na_ordem() == ["A", "C", "B"]

    def test_desce(self, cliente):
        a = criar("A")
        criar("B")
        criar("C")

        cliente.post(reverse("backoffice:partner_move", args=[a.pk]), {"direcao": "descer"})

        assert nomes_na_ordem() == ["B", "A", "C"]

    def test_funciona_mesmo_com_todos_empatados_em_zero(self, cliente):
        """
        O caso real: `order` nasce 0 para todo mundo. Trocar o número de
        dois empatados não moveria ninguém -- por isso a view renumera
        pela posição.
        """
        criar("A")
        criar("B")
        c = criar("C")
        assert {p.order for p in Partner.objects.all()} == {0}

        cliente.post(reverse("backoffice:partner_move", args=[c.pk]), {"direcao": "subir"})

        assert nomes_na_ordem() == ["A", "C", "B"]
        assert [p.order for p in Partner.objects.all()] == [1, 2, 3]

    def test_o_primeiro_nao_sobe(self, cliente):
        a = criar("A")
        criar("B")

        cliente.post(reverse("backoffice:partner_move", args=[a.pk]), {"direcao": "subir"})

        assert nomes_na_ordem() == ["A", "B"]

    def test_o_ultimo_nao_desce(self, cliente):
        criar("A")
        b = criar("B")

        cliente.post(reverse("backoffice:partner_move", args=[b.pk]), {"direcao": "descer"})

        assert nomes_na_ordem() == ["A", "B"]

    def test_a_lista_nao_oferece_subir_no_primeiro_nem_descer_no_ultimo(self, cliente):
        """
        Contar os formularios nao bastaria: as pontas teriam um cada de
        qualquer jeito, e o teste passaria com a logica invertida. O que
        importa e QUAL direcao cada ponta recebe.
        """
        a = criar("A")
        criar("B")
        c = criar("C")

        corpo = cliente.get(LISTA).content.decode()

        assert _direcoes(corpo, a) == ["descer"]
        assert _direcoes(corpo, c) == ["subir"]

    def test_a_linha_do_meio_sobe_e_desce(self, cliente):
        criar("A")
        b = criar("B")
        criar("C")

        assert _direcoes(cliente.get(LISTA).content.decode(), b) == ["subir", "descer"]

    def test_a_home_respeita_a_ordem(self, cliente, client):
        criar("Primeira", order=1)
        criar("Segunda", order=2)

        corpo = client.get(HOME).content.decode()

        assert corpo.index("Primeira") < corpo.index("Segunda")

    def test_mudar_a_ordem_muda_a_home(self, cliente, client):
        criar("Primeira")
        segunda = criar("Segunda")

        cliente.post(
            reverse("backoffice:partner_move", args=[segunda.pk]), {"direcao": "subir"}
        )
        corpo = client.get(HOME).content.decode()

        assert corpo.index("Segunda") < corpo.index("Primeira")


# ===========================================================================
# 7. Remover
# ===========================================================================


class TestRemover:
    def test_o_get_so_pergunta(self, cliente):
        parceiro = criar("Padaria")

        corpo = cliente.get(
            reverse("backoffice:partner_delete", args=[parceiro.pk])
        ).content.decode()

        assert "Padaria" in corpo
        assert "não tem volta" in corpo
        assert Partner.objects.filter(pk=parceiro.pk).exists()

    def test_a_confirmacao_oferece_desativar_como_alternativa(self, cliente):
        parceiro = criar("Padaria")

        corpo = cliente.get(
            reverse("backoffice:partner_delete", args=[parceiro.pk])
        ).content.decode()

        assert "desative-o" in corpo
        assert reverse("backoffice:partner_activation", args=[parceiro.pk]) in corpo

    def test_o_post_apaga(self, cliente):
        parceiro = criar("Padaria")

        resposta = cliente.post(reverse("backoffice:partner_delete", args=[parceiro.pk]))

        assert resposta.status_code == 302
        assert not Partner.objects.filter(pk=parceiro.pk).exists()

    def test_apagar_leva_a_imagem_junto_quando_ela_fica_orfa(self, cliente):
        """
        Desde o Bloco D: sem mais ninguém usando, a imagem some com o
        parceiro -- nem arquivo nem registro de `Asset` ficam para trás.
        """
        imagem = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif())
        parceiro = criar("Padaria", logo=imagem)

        cliente.post(reverse("backoffice:partner_delete", args=[parceiro.pk]))

        assert not Asset.objects.filter(pk=imagem.pk).exists()

    def test_apagar_nao_leva_a_imagem_junto_quando_compartilhada(self, cliente):
        """A biblioteca é compartilhada: a imagem pode estar em uso alhures."""
        imagem = Asset.objects.create(kind=Asset.Kind.PARTNER, file=_gif())
        parceiro = criar("Padaria", logo=imagem)
        criar("Confeitaria", logo=imagem)

        cliente.post(reverse("backoffice:partner_delete", args=[parceiro.pk]))

        assert Asset.objects.filter(pk=imagem.pk).exists()

    def test_apagado_some_da_home(self, cliente, client):
        parceiro = criar("Padaria")

        cliente.post(reverse("backoffice:partner_delete", args=[parceiro.pk]))

        assert "Padaria" not in client.get(HOME).content.decode()


# ===========================================================================
# 8. O modelo e o catálogo
# ===========================================================================


class TestModelo:
    def test_a_imagem_continua_sendo_um_asset(self):
        """
        Nada de `ImageField` no parceiro: a imagem mora na biblioteca, que
        é onde está a proteção contra trocar arquivo do qual uma carta
        finalizada depende.
        """
        from django.db import models

        campos = {c.name: c for c in Partner._meta.get_fields()}

        assert isinstance(campos["logo"], models.ForeignKey)
        assert campos["logo"].related_model is Asset
        assert not any(
            isinstance(c, models.ImageField) for c in Partner._meta.get_fields()
        )

    def test_as_quatro_permissoes_existem(self):
        assert set(Partner._meta.default_permissions) == {"add", "change", "delete", "view"}


class TestCatalogo:
    def test_as_quatro_estao_no_catalogo(self):
        """
        Entram agora porque agora existe tela que as confere -- que é a
        regra escrita no próprio catálogo.
        """
        from apps.accounts import admin_permissions

        chaves = {permissao.chave for permissao in admin_permissions.todas()}

        for codename in TODAS:
            assert f"content.{codename}" in chaves

    def test_a_tela_de_usuarios_as_oferece(self, client, administradora):
        gerencia = Permission.objects.get(
            content_type__app_label="accounts", codename="manage_users"
        )
        administradora.user_permissions.add(gerencia)
        pessoa = get_user_model().objects.get(pk=administradora.pk)
        client.force_login(pessoa)

        corpo = client.get(
            reverse("backoffice:user_detail", args=[pessoa.pk])
        ).content.decode()

        assert "Cadastrar parceiros" in corpo
        assert "Remover parceiros" in corpo


# ===========================================================================
# 9. O celular
# ===========================================================================


class TestCelular:
    """
    A tela tinha SÓ a tabela, e seis colunas não cabem em 390px -- a
    página inteira rolava para o lado. Até a Rodada 15 a saída era uma
    tabela no desktop e uma lista à parte no celular; desde então a tela
    usa o desenho da tabela de Modelos, em que a MESMA linha vira cartão
    abaixo de 1180px -- com as ações junto, sem uma segunda marcação.
    """

    def test_uma_marcacao_so_no_desenho_de_modelos(self, cliente):
        criar("Padaria")

        corpo = cliente.get(LISTA).content.decode()

        assert 'class="mod-tabela mod-tabela-lista mod-tabela-parceiros"' in corpo
        assert 'class="card table-wrap d-only"' not in corpo
        assert 'class="list m-only"' not in corpo

    def test_a_linha_vira_cartao_no_celular(self, cliente):
        """A regra que faz a linha virar cartão, na folha de Modelos."""
        import pathlib

        css = pathlib.Path("static/css/biblioteca-modelos.css").read_text(encoding="utf-8")
        cartao = css[css.index(".mod-celulas-meio { display: contents; }") :]

        assert "@media (max-width: 1180px)" in cartao
        assert ".mod-tabela-lista .mod-linha {" in cartao

    def test_no_celular_as_acoes_estao_na_propria_linha(self, cliente):
        """
        A lista antiga do celular só levava à edição. A linha única traz
        as ações dela junto -- subir, descer, editar e o menu.
        """
        a = criar("Primeira", order=1)
        criar("Segunda", order=2)

        corpo = cliente.get(LISTA).content.decode()

        assert _direcoes(corpo, a) == ["descer"]
        assert reverse("backoffice:partner_activation", args=[a.pk]) in corpo
        assert reverse("backoffice:partner_delete", args=[a.pk]) in corpo

    def test_a_lista_do_celular_leva_a_edicao(self, cliente):
        parceiro = criar("Padaria")

        corpo = cliente.get(LISTA).content.decode()

        assert reverse("backoffice:partner_edit", args=[parceiro.pk]) in corpo

    def test_a_edicao_oferece_as_acoes_que_a_lista_movel_nao_tem(self, cliente):
        """
        No celular a lista leva para a edição -- e é lá que precisam
        estar ativar/desativar e remover. Sem isso, trocar a situação de
        um parceiro pelo telefone seria impossível.
        """
        parceiro = criar("Padaria")

        corpo = cliente.get(
            reverse("backoffice:partner_edit", args=[parceiro.pk])
        ).content.decode()

        assert reverse("backoffice:partner_activation", args=[parceiro.pk]) in corpo
        assert reverse("backoffice:partner_delete", args=[parceiro.pk]) in corpo

    def test_o_cadastro_novo_nao_oferece_acao_de_registro(self, cliente):
        """
        Não há o que desativar nem remover antes de existir -- o botão
        de ação do REGISTRO, não o campo "Remover a imagem atual" do
        formulário (Bloco D), que é sobre a imagem, não sobre o
        parceiro, e nem aparece sem um parceiro já salvo com logo.
        """
        corpo = cliente.get(NOVO).content.decode()

        assert "Desativar" not in corpo
        assert ">Remover<" not in corpo
        assert "Remover a imagem atual" not in corpo
