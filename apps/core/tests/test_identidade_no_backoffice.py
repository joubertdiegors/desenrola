"""
A identidade no rodapé do menu do Backoffice é a de quem está logado.

Até esta etapa a área administrativa mostrava um nome inventado
(`demo.ADMIN`, "Ana Martins · Administradora") para qualquer pessoa que
entrasse -- inclusive nas telas que já liam o banco de verdade. Era a
última mentira visível do Backoffice.

A identidade agora vem de `user`, pelo processador de contexto do
`django.contrib.auth`: uma fonte só, que nenhuma view pode esquecer de
preencher.

POR QUE NÃO USAR O `staff_user` DO CONFTEST AQUI
------------------------------------------------
Ele se chama "Ana Martins" -- o MESMO nome do dado fictício que esta
etapa removeu. Testar com ele não distinguiria "mostra a pessoa certa"
de "mostra a constante antiga": os dois passariam. Por isso a
administradora daqui tem nome próprio e inconfundível.

"Ana Martins" também segue aparecendo, legitimamente, como CONTEÚDO de
telas ainda ilustrativas (a lista de usuários, o "editado por" dos
modelos), que não foram tocadas nesta etapa. Por isso a asserção geral é
sobre o BLOCO DE IDENTIDADE; a página inteira só é cobrada nas telas que
já são reais.
"""

import re

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

# Todas as telas administrativas que usam a casca `backoffice/base.html`:
# a identidade tem de estar certa em TODAS, inclusive nas que ainda
# mostram conteúdo ilustrativo.
TELAS = [
    "backoffice:overview",
    "backoffice:document_library",
    "backoffice:letter_policy",
    "backoffice:appearance",
]

# As telas que já são REAIS -- nelas o nome inventado não tem por que
# existir em canto nenhum da página. As outras ainda renderizam
# conteúdo de demonstração que cita aquele nome (a lista fictícia de
# usuários, o "editado por" dos modelos), e essa parte não é escopo
# desta etapa.
TELAS_SEM_FICCAO = [
    "backoffice:document_library",
    "backoffice:letter_policy",
]


@pytest.fixture
def administradora(db, permissao_backoffice, permissoes_de_modelos, django_user_model):
    """
    Quem administra, com nome PRÓPRIO -- nada parecido com o dado
    fictício que esta etapa removeu (ver o cabeçalho do arquivo).

    Recebe também as permissões da biblioteca de modelos: entre as telas
    conferidas aqui está `backoffice:document_library`, que desde a etapa
    da biblioteca exige uma permissão própria.
    """
    pessoa = django_user_model.objects.create_user(
        email="beatriz@desenrola.be",
        password="senha-de-teste-123",
        full_name="Beatriz Nunes",
    )
    pessoa.user_permissions.add(permissao_backoffice, *permissoes_de_modelos)
    return django_user_model.objects.get(pk=pessoa.pk)


@pytest.fixture
def permissao_gerenciar(db):
    """A permissao que abre o gerenciador de usuarios."""
    from django.contrib.auth.models import Permission

    return Permission.objects.get(
        content_type__app_label="accounts", codename="manage_users"
    )


@pytest.fixture
def cliente_admin(client, administradora):
    client.force_login(administradora)
    return client


def bloco_de_identidade(html):
    """
    Só o rodapé do menu lateral (`.bo-aside-user`) -- é ali que a
    identidade da pessoa aparece. Olhar a página inteira confundiria com
    o conteúdo das telas.
    """
    achado = re.search(r'<div class="bo-aside-user">(.*?)</div>', html, re.S)
    assert achado, "o bloco de identidade sumiu do menu"
    return achado.group(1)


class TestIdentidadeReal:
    @pytest.mark.parametrize("tela", TELAS)
    def test_a_pessoa_ve_o_proprio_nome(self, cliente_admin, administradora, tela):
        identidade = bloco_de_identidade(cliente_admin.get(reverse(tela)).content.decode())

        assert administradora.full_name in identidade
        assert administradora.email in identidade

    @pytest.mark.parametrize("tela", TELAS)
    def test_a_identidade_nunca_e_o_nome_inventado(self, cliente_admin, tela):
        """
        O que o requisito cobra, na letra: o nome fictício não pode
        ser renderizado COMO IDENTIDADE da pessoa. Vale nas cinco
        telas, inclusive nas que ainda exibem conteúdo ilustrativo
        citando aquele nome noutro lugar da página.
        """
        identidade = bloco_de_identidade(cliente_admin.get(reverse(tela)).content.decode())

        assert "Ana Martins" not in identidade
        assert "Administradora" not in identidade

    @pytest.mark.parametrize("tela", TELAS_SEM_FICCAO)
    def test_nas_telas_reais_o_nome_inventado_sumiu_da_pagina(self, cliente_admin, tela):
        corpo = cliente_admin.get(reverse(tela)).content.decode()

        assert "Ana Martins" not in corpo
        assert "Administradora" not in corpo

    def test_as_iniciais_do_avatar_sao_as_da_pessoa(self, cliente_admin, administradora):
        identidade = bloco_de_identidade(
            cliente_admin.get(reverse("backoffice:overview")).content.decode()
        )

        assert administradora.get_initials() == "BN"
        assert "BN" in identidade
        assert "AM" not in identidade  # as iniciais do dado fictício

    def test_cada_pessoa_ve_a_sua_identidade(
        self, client, administradora, staff_user
    ):
        """Duas sessões, dois nomes -- nada é fixo no template."""
        client.force_login(administradora)
        primeira = bloco_de_identidade(
            client.get(reverse("backoffice:overview")).content.decode()
        )

        client.force_login(staff_user)
        segunda = bloco_de_identidade(
            client.get(reverse("backoffice:overview")).content.decode()
        )

        assert "Beatriz Nunes" in primeira
        assert "Beatriz Nunes" not in segunda
        assert staff_user.email in segunda

    def test_sem_nome_completo_cai_no_email(
        self, client, permissao_backoffice, django_user_model
    ):
        """
        `full_name` é obrigatório no formulário, mas nada impede um
        registro sem ele. A identidade não pode virar um espaço em
        branco.
        """
        anonima = django_user_model.objects.create_user(
            email="sem-nome@desenrola.be", password="x", full_name=""
        )
        anonima.user_permissions.add(permissao_backoffice)
        client.force_login(django_user_model.objects.get(pk=anonima.pk))

        identidade = bloco_de_identidade(
            client.get(reverse("backoffice:overview")).content.decode()
        )

        assert "sem-nome@desenrola.be" in identidade

    def test_a_supervisao_de_cartas_tambem_mostra_a_pessoa_certa(
        self, client, administradora, permissao_ver_todas
    ):
        """A tela mais real do Backoffice não podia ser a exceção."""
        administradora.user_permissions.add(permissao_ver_todas)
        client.force_login(administradora)

        corpo = client.get(reverse("backoffice:letters")).content.decode()

        assert "Beatriz Nunes" in bloco_de_identidade(corpo)
        assert "Ana Martins" not in corpo  # a tela toda já é real


class TestNadaDeIdentidadeFicticia:
    def test_demo_nao_tem_mais_a_identidade_inventada(self):
        from apps.core import demo

        assert not hasattr(demo, "ADMIN")

    def test_nenhuma_view_injeta_admin_user(self):
        """
        A identidade vem do processador de contexto, não de um dicionário
        passado view a view -- e é isso que impede que uma tela nova
        esqueça de preenchê-la e apareça sem nome.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        achados = []
        for arquivo in raiz.rglob("*.py"):
            if any(p in (".venv", "__pycache__", "tests") for p in arquivo.parts):
                continue
            if "admin_user" in arquivo.read_text(encoding="utf-8", errors="replace"):
                achados.append(arquivo.name)

        assert not achados, achados

    def test_a_tela_de_usuarios_virou_real(self, client, administradora, permissao_gerenciar):
        """
        Esta era a guarda de escopo da etapa da identidade: enquanto a
        lista de usuários fosse fictícia, ela cobrava que "Ana Martins"
        aparecesse ali. A etapa do gerenciador de usuários tornou a
        tela real -- o teste disparou, como projetado, e passou a
        cobrar o contrário: nenhum nome inventado, e a identidade de
        quem está logado.
        """
        administradora.user_permissions.add(permissao_gerenciar)
        client.force_login(administradora)

        corpo = client.get(reverse("backoffice:users")).content.decode()

        assert "Ana Martins" not in corpo
        assert "Beatriz Nunes" in bloco_de_identidade(corpo)
