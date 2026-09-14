"""
Gerenciador de usuários e permissões do Backoffice.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. que a porta afrouxe -- toda checagem é feita pela URL direta, nunca
   pela ausência de um link no menu;
2. que alguém escale privilégio pela própria tela -- conceder a outro
   uma permissão que não se tem;
3. que alguém se tranque para fora -- retirar de si o acesso
   administrativo, ou desativar a própria conta;
4. que uma alteração passe por GET, sem CSRF;
5. que a tela volte a mostrar gente inventada.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

pytestmark = pytest.mark.django_db

LISTA = reverse("backoffice:users")
SENHA = "senha-de-teste-123"


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


def permissao(app_label, codename):
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


@pytest.fixture
def perm_backoffice(db):
    return permissao("core", "access_backoffice")


@pytest.fixture
def perm_gerenciar(db):
    return permissao("accounts", "manage_users")


@pytest.fixture
def perm_ver_cartas(db):
    return permissao("letters", "view_all_letters")


def criar(email, nome, *perms, ativo=True, superusuario=False):
    User = get_user_model()
    if superusuario:
        pessoa = User.objects.create_superuser(email=email, password=SENHA, full_name=nome)
    else:
        pessoa = User.objects.create_user(email=email, password=SENHA, full_name=nome)
    pessoa.is_active = ativo
    pessoa.save(update_fields=["is_active"])
    if perms:
        pessoa.user_permissions.set(perms)
    return User.objects.get(pk=pessoa.pk)


@pytest.fixture
def operador(perm_backoffice, perm_gerenciar):
    """Quem administra: entra no Backoffice e gerencia usuários."""
    return criar("operador@desenrola.be", "Olívia Ramos", perm_backoffice, perm_gerenciar)


@pytest.fixture
def cliente(client, operador):
    client.force_login(operador)
    return client


@pytest.fixture
def alvo(db):
    """Uma pessoa comum, sem permissão nenhuma."""
    return criar("alvo@exemplo.be", "Tiago Alves")


def url_detalhe(pessoa):
    return reverse("backoffice:user_detail", args=[pessoa.pk])


def url_permissoes(pessoa):
    return reverse("backoffice:user_permissions", args=[pessoa.pk])


def url_situacao(pessoa):
    return reverse("backoffice:user_activation", args=[pessoa.pk])


def tem(pessoa, chave):
    """Relê do banco: `has_perm` guarda cache no objeto em memória."""
    User = get_user_model()
    return User.objects.get(pk=pessoa.pk).has_perm(chave)


# ===========================================================================
# 1-3, 17. Permissões de acesso
# ===========================================================================


class TestAcesso:
    def test_usuario_comum_nao_acessa(self, client, alvo):
        client.force_login(alvo)

        assert client.get(LISTA).status_code == 403

    def test_backoffice_sem_manage_users_nao_acessa(self, client, perm_backoffice):
        """
        Entrar na área administrativa e mexer em quem pode o quê são
        decisões separadas.
        """
        pessoa = criar("so-backoffice@desenrola.be", "Sem Gerência", perm_backoffice)
        client.force_login(pessoa)

        assert client.get(LISTA).status_code == 403

    def test_manage_users_sem_backoffice_nao_acessa(self, client, perm_gerenciar):
        """A permissão da seção sozinha não abre a porta do Backoffice."""
        pessoa = criar("so-gerencia@desenrola.be", "Sem Backoffice", perm_gerenciar)
        client.force_login(pessoa)

        assert client.get(LISTA).status_code == 403

    def test_com_as_duas_acessa(self, cliente):
        assert cliente.get(LISTA).status_code == 200

    def test_superusuario_acessa(self, client):
        chefe = criar("chefe@desenrola.be", "Chefe", superusuario=True)
        client.force_login(chefe)

        assert client.get(LISTA).status_code == 200

    def test_anonimo_vai_para_o_login(self, client, alvo):
        resposta = client.get(LISTA)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    @pytest.mark.parametrize("rota", ["user_detail", "user_permissions", "user_activation"])
    def test_acesso_direto_a_cada_url_sem_autorizacao(self, client, alvo, rota):
        """
        Não basta proteger a lista: cada URL é alcançável por conta
        própria, e é o que alguém tentaria.
        """
        client.force_login(alvo)
        url = reverse(f"backoffice:{rota}", args=[alvo.pk])

        resposta = client.post(url) if rota != "user_detail" else client.get(url)

        assert resposta.status_code == 403

    def test_o_menu_so_mostra_usuarios_para_quem_gerencia(
        self, client, cliente, perm_backoffice
    ):
        com_gerencia = cliente.get(reverse("backoffice:overview")).content.decode()

        sem = criar("sem@desenrola.be", "Sem Gerência", perm_backoffice)
        client.force_login(sem)
        sem_gerencia = client.get(reverse("backoffice:overview")).content.decode()

        assert LISTA in com_gerencia
        assert LISTA not in sem_gerencia


# ===========================================================================
# 4-6, 18. Listagem, busca, paginação
# ===========================================================================


class TestListagem:
    def test_mostra_as_pessoas_do_banco(self, cliente, alvo, operador):
        corpo = cliente.get(LISTA).content.decode()

        assert alvo.full_name in corpo
        assert alvo.email in corpo
        assert operador.email in corpo

    def test_nao_mostra_dado_sensivel(self, cliente, alvo):
        """Nem o hash da senha, nem documento, nem endereço."""
        alvo.document_number = "99988877766"
        alvo.address_line1 = "Rue Secreta 1"
        alvo.save()

        corpo = cliente.get(LISTA).content.decode()

        assert alvo.password not in corpo
        assert "99988877766" not in corpo
        assert "Rue Secreta" not in corpo

    def test_busca_por_nome(self, cliente, alvo):
        criar("outra@exemplo.be", "Fernanda Lima")

        corpo = cliente.get(LISTA, {"q": "Fernanda"}).content.decode()

        assert "Fernanda Lima" in corpo
        assert alvo.email not in corpo

    def test_busca_por_email(self, cliente, alvo):
        criar("procurada@exemplo.be", "Outra Pessoa")

        corpo = cliente.get(LISTA, {"q": "procurada@"}).content.decode()

        assert "procurada@exemplo.be" in corpo
        assert alvo.email not in corpo

    def test_busca_ignora_maiusculas(self, cliente, alvo):
        corpo = cliente.get(LISTA, {"q": "tiago"}).content.decode()

        assert alvo.email in corpo

    def test_busca_sem_resultado(self, cliente, alvo):
        corpo = cliente.get(LISTA, {"q": "ninguem-com-esse-nome"}).content.decode()

        assert "Nenhum usuário encontrado" in corpo

    def test_filtro_por_situacao(self, cliente, alvo):
        inativa = criar("inativa@exemplo.be", "Pessoa Inativa", ativo=False)

        so_ativos = cliente.get(LISTA, {"status": "ativos"}).content.decode()
        so_inativos = cliente.get(LISTA, {"status": "inativos"}).content.decode()

        assert alvo.email in so_ativos and inativa.email not in so_ativos
        assert inativa.email in so_inativos and alvo.email not in so_inativos

    def test_paginacao(self, cliente, operador):
        from apps.accounts.backoffice_views import POR_PAGINA

        for numero in range(POR_PAGINA + 5):
            criar(f"pessoa{numero:03d}@exemplo.be", f"Pessoa {numero:03d}")

        primeira = cliente.get(LISTA)
        segunda = cliente.get(LISTA, {"page": 2})

        assert len(primeira.context["pessoas"]) == POR_PAGINA
        assert primeira.context["total"] == POR_PAGINA + 6  # +5 pessoas +1 operador
        assert segunda.context["pagina"].number == 2
        assert len(segunda.context["pessoas"]) == 6

    def test_a_paginacao_respeita_a_busca(self, cliente):
        for numero in range(3):
            criar(f"filtrada{numero}@exemplo.be", f"Filtrada {numero}")

        resposta = cliente.get(LISTA, {"q": "Filtrada"})

        assert resposta.context["total"] == 3

    def test_mostra_quem_acessa_o_backoffice(self, cliente, alvo, perm_backoffice):
        """A permissão é a DA LINHA, não a de quem está olhando."""
        alvo.user_permissions.add(perm_backoffice)

        linhas = {
            linha["pessoa"].pk: linha for linha in cliente.get(LISTA).context["pessoas"]
        }

        assert linhas[alvo.pk]["acessa_backoffice"] is True

    def test_mostra_quem_ve_todas_as_cartas(self, cliente, alvo, perm_ver_cartas):
        alvo.user_permissions.add(perm_ver_cartas)

        linhas = {
            linha["pessoa"].pk: linha for linha in cliente.get(LISTA).context["pessoas"]
        }

        assert linhas[alvo.pk]["ve_todas_as_cartas"] is True
        assert linhas[alvo.pk]["acessa_backoffice"] is False


# ===========================================================================
# 7, 18. Detalhe
# ===========================================================================


class TestDetalhe:
    def test_mostra_os_dados_da_pessoa(self, cliente, alvo):
        alvo.phone = "+32 470 12 34 56"
        alvo.save()

        corpo = cliente.get(url_detalhe(alvo)).content.decode()

        assert alvo.full_name in corpo
        assert alvo.email in corpo
        assert "+32 470 12 34 56" in corpo

    def test_nao_mostra_dado_sensivel(self, cliente, alvo):
        corpo = cliente.get(url_detalhe(alvo)).content.decode()

        assert alvo.password not in corpo

    def test_nao_oferece_troca_de_senha(self, cliente, alvo):
        """Senha é assunto do dono da conta, não do administrador."""
        corpo = cliente.get(url_detalhe(alvo)).content.decode()

        assert 'type="password"' not in corpo

    def test_mostra_o_catalogo_de_permissoes(self, cliente, alvo):
        contexto = cliente.get(url_detalhe(alvo)).context

        chaves = {
            item["permissao"].chave
            for grupo in contexto["grupos"]
            for item in grupo["itens"]
        }
        assert "core.access_backoffice" in chaves
        assert "accounts.manage_users" in chaves
        assert "letters.view_all_letters" in chaves

    def test_nao_mostra_permissoes_tecnicas_do_django(self, cliente, alvo):
        """
        A tela não é um CRUD de `auth_permission`: só entra o que o
        produto realmente verifica.
        """
        corpo = cliente.get(url_detalhe(alvo)).content.decode()

        for tecnica in ("add_logentry", "delete_session", "change_contenttype"):
            assert tecnica not in corpo

    def test_usuario_inexistente_da_404(self, cliente):
        url = reverse("backoffice:user_detail", args=[999999])

        assert cliente.get(url).status_code == 404


# ===========================================================================
# 8-11, 15. Conceder e retirar permissões
# ===========================================================================


class TestPermissoes:
    def test_concede_acesso_ao_backoffice(self, cliente, alvo):
        assert tem(alvo, "core.access_backoffice") is False

        cliente.post(url_permissoes(alvo), {"permissoes": ["core.access_backoffice"]})

        assert tem(alvo, "core.access_backoffice") is True

    def test_retira_acesso_ao_backoffice(self, cliente, alvo, perm_backoffice):
        alvo.user_permissions.add(perm_backoffice)

        cliente.post(url_permissoes(alvo), {"permissoes": []})

        assert tem(alvo, "core.access_backoffice") is False

    def test_concede_ver_todas_as_cartas(self, cliente, alvo, operador, perm_ver_cartas):
        operador.user_permissions.add(perm_ver_cartas)

        cliente.post(url_permissoes(alvo), {"permissoes": ["letters.view_all_letters"]})

        assert tem(alvo, "letters.view_all_letters") is True

    def test_retira_ver_todas_as_cartas(self, cliente, alvo, operador, perm_ver_cartas):
        operador.user_permissions.add(perm_ver_cartas)
        alvo.user_permissions.add(perm_ver_cartas)

        cliente.post(url_permissoes(alvo), {"permissoes": []})

        assert tem(alvo, "letters.view_all_letters") is False

    def test_concede_varias_de_uma_vez(self, cliente, alvo, operador, perm_ver_cartas):
        operador.user_permissions.add(perm_ver_cartas)

        cliente.post(
            url_permissoes(alvo),
            {"permissoes": ["core.access_backoffice", "letters.view_all_letters"]},
        )

        assert tem(alvo, "core.access_backoffice") is True
        assert tem(alvo, "letters.view_all_letters") is True

    def test_GET_nao_altera_nada(self, cliente, alvo):
        """
        A URL de alteração só responde a POST (`require_POST`): um GET
        devolve 405 e não toca no banco.
        """
        resposta = cliente.get(url_permissoes(alvo))

        assert resposta.status_code == 405
        assert tem(alvo, "core.access_backoffice") is False

    def test_sem_csrf_nao_altera(self, operador, alvo):
        """
        O middleware de CSRF recusa o POST sem token: 403 e nada muda.
        `enforce_csrf_checks` liga a checagem que o cliente de teste
        normalmente dispensa.
        """
        from django.test import Client

        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(operador)

        resposta = cliente.post(
            url_permissoes(alvo), {"permissoes": ["core.access_backoffice"]}
        )

        assert resposta.status_code == 403
        assert tem(alvo, "core.access_backoffice") is False


# ===========================================================================
# 16. Escalada de privilégio
# ===========================================================================


class TestEscaladaDePrivilegio:
    def test_nao_concede_o_que_nao_tem(self, cliente, alvo):
        """
        O operador não tem `letters.view_all_letters`. Mesmo enviando a
        chave num POST forjado, ela não é concedida -- o formulário do
        servidor nem tem campo para ela.
        """
        cliente.post(url_permissoes(alvo), {"permissoes": ["letters.view_all_letters"]})

        assert tem(alvo, "letters.view_all_letters") is False

    def test_nao_retira_o_que_nao_tem(self, cliente, alvo, perm_ver_cartas):
        """
        O outro lado: não podendo conceder, também não pode retirar --
        senão bastaria retirar de todo mundo para ficar sozinho com o
        acesso.
        """
        alvo.user_permissions.add(perm_ver_cartas)

        cliente.post(url_permissoes(alvo), {"permissoes": []})

        assert tem(alvo, "letters.view_all_letters") is True

    def test_a_caixa_que_ele_nao_pode_conceder_vem_travada(self, cliente, alvo):
        contexto = cliente.get(url_detalhe(alvo)).context

        por_chave = {
            item["permissao"].chave: item
            for grupo in contexto["grupos"]
            for item in grupo["itens"]
        }
        assert por_chave["core.access_backoffice"]["editavel"] is True
        assert por_chave["letters.view_all_letters"]["editavel"] is False

    def test_superusuario_concede_tudo(self, client, alvo):
        chefe = criar("chefe@desenrola.be", "Chefe", superusuario=True)
        client.force_login(chefe)

        client.post(
            url_permissoes(alvo),
            {"permissoes": ["core.access_backoffice", "letters.view_all_letters"]},
        )

        assert tem(alvo, "letters.view_all_letters") is True

    def test_nao_mexe_em_superusuario(self, cliente, perm_backoffice):
        """
        Superusuário tem tudo implicitamente; marcar caixas nele não
        significaria nada, e desativá-lo seria uma porta de negação de
        serviço aberta a quem só tem `manage_users`.
        """
        chefe = criar("chefe@desenrola.be", "Chefe", superusuario=True)

        permissoes = cliente.post(url_permissoes(chefe), {"permissoes": []})
        situacao = cliente.post(url_situacao(chefe), {"ativo": "0"})

        assert permissoes.status_code == 403
        assert situacao.status_code == 403
        assert get_user_model().objects.get(pk=chefe.pk).is_active is True

    def test_superusuario_mexe_em_superusuario(self, client):
        chefe = criar("chefe@desenrola.be", "Chefe", superusuario=True)
        outro = criar("outro-chefe@desenrola.be", "Outro Chefe", superusuario=True)
        client.force_login(chefe)

        client.post(url_situacao(outro), {"ativo": "0"})

        assert get_user_model().objects.get(pk=outro.pk).is_active is False


# ===========================================================================
# Auto-trancamento
# ===========================================================================


class TestNaoSeTrancarParaFora:
    def test_nao_retira_de_si_o_acesso_ao_backoffice(self, cliente, operador):
        cliente.post(url_permissoes(operador), {"permissoes": ["accounts.manage_users"]})

        assert tem(operador, "core.access_backoffice") is True

    def test_nao_retira_de_si_o_gerenciamento_de_usuarios(self, cliente, operador):
        cliente.post(url_permissoes(operador), {"permissoes": ["core.access_backoffice"]})

        assert tem(operador, "accounts.manage_users") is True

    def test_avisa_por_que_recusou(self, cliente, operador):
        resposta = cliente.post(url_permissoes(operador), {"permissoes": []}, follow=True)

        assert "não pode retirar de si mesmo" in resposta.content.decode()

    def test_pode_retirar_de_si_o_que_nao_tranca_a_porta(
        self, cliente, operador, perm_ver_cartas
    ):
        """A trava vale só para o que deixaria a pessoa sem administração."""
        operador.user_permissions.add(perm_ver_cartas)

        cliente.post(
            url_permissoes(operador),
            {"permissoes": ["core.access_backoffice", "accounts.manage_users"]},
        )

        assert tem(operador, "letters.view_all_letters") is False
        assert tem(operador, "core.access_backoffice") is True

    def test_nao_desativa_a_propria_conta(self, cliente, operador):
        resposta = cliente.post(url_situacao(operador), {"ativo": "0"}, follow=True)

        assert get_user_model().objects.get(pk=operador.pk).is_active is True
        assert "não pode desativar a sua própria conta" in resposta.content.decode()

    def test_outra_pessoa_pode_retirar_a_permissao(
        self, client, operador, perm_backoffice, perm_gerenciar
    ):
        """
        A trava é contra o acidente consigo mesmo, não contra a
        administração: outra pessoa com a permissão consegue.
        """
        colega = criar("colega@desenrola.be", "Colega", perm_backoffice, perm_gerenciar)
        client.force_login(colega)

        client.post(url_permissoes(operador), {"permissoes": ["accounts.manage_users"]})

        assert tem(operador, "core.access_backoffice") is False


# ===========================================================================
# 12-13. Ativação e desativação
# ===========================================================================


class TestAtivacao:
    def test_desativa(self, cliente, alvo):
        cliente.post(url_situacao(alvo), {"ativo": "0"})

        assert get_user_model().objects.get(pk=alvo.pk).is_active is False

    def test_ativa_de_novo(self, cliente, alvo):
        alvo.is_active = False
        alvo.save(update_fields=["is_active"])

        cliente.post(url_situacao(alvo), {"ativo": "1"})

        assert get_user_model().objects.get(pk=alvo.pk).is_active is True

    def test_GET_nao_altera(self, cliente, alvo):
        resposta = cliente.get(url_situacao(alvo))

        assert resposta.status_code == 405
        assert get_user_model().objects.get(pk=alvo.pk).is_active is True

    def test_desativado_nao_autentica(self, client, alvo):
        """A regra de verdade: sem conseguir entrar, não adianta nada."""
        assert client.login(email=alvo.email, password=SENHA) is True
        client.logout()

        alvo.is_active = False
        alvo.save(update_fields=["is_active"])

        assert client.login(email=alvo.email, password=SENHA) is False

    def test_desativado_nao_passa_pelo_formulario_de_login(self, cliente, alvo):
        """
        Sessão PRÓPRIA, e não o `client` compartilhado: `cliente` já
        está logado como o operador, e a LoginView do projeto tem
        `redirect_authenticated_user = True` -- o teste passaria pelo
        motivo errado.
        """
        from django.test import Client

        cliente.post(url_situacao(alvo), {"ativo": "0"})
        deslogado = Client()

        resposta = deslogado.post(
            reverse("accounts:login"), {"username": alvo.email, "password": SENHA}
        )

        assert resposta.status_code == 200  # ficou na tela de login
        assert resposta.wsgi_request.user.is_authenticated is False

    def test_desativar_nao_apaga_nem_as_cartas_nem_a_pessoa(self, cliente, alvo):
        """Desativar preserva tudo -- é por isso que não se apaga ninguém."""
        User = get_user_model()

        cliente.post(url_situacao(alvo), {"ativo": "0"})

        assert User.objects.filter(pk=alvo.pk).exists()
        assert User.objects.get(pk=alvo.pk).email == alvo.email

    def test_nao_ha_como_apagar_alguem(self, cliente, alvo):
        """Nenhuma rota de exclusão existe -- de propósito."""
        from django.urls import NoReverseMatch

        with pytest.raises(NoReverseMatch):
            reverse("backoffice:user_delete", args=[alvo.pk])

        corpo = cliente.get(url_detalhe(alvo)).content.decode()
        assert "Excluir" not in corpo


# ===========================================================================
# Nada de dados fictícios
# ===========================================================================


class TestSemDadosFicticios:
    def test_demo_nao_tem_mais_a_lista_falsa(self):
        from apps.core import demo

        assert not hasattr(demo, "ADMIN_USERS")
        assert not hasattr(demo, "PERMISSIONS")
        assert not hasattr(demo, "STATS")

    def test_a_tela_nao_mostra_os_nomes_inventados(self, cliente):
        corpo = cliente.get(LISTA).content.decode()

        for inventado in ("Ana Martins", "Níveis de acesso", "Convidar usuário"):
            assert inventado not in corpo

    def test_a_view_consulta_o_banco(self, cliente, alvo):
        """Some do banco, some da tela."""
        assert alvo.email in cliente.get(LISTA).content.decode()

        get_user_model().objects.filter(pk=alvo.pk).delete()

        assert alvo.email not in cliente.get(LISTA).content.decode()


# ===========================================================================
# 19-20. Regressão do que já existia
# ===========================================================================


class TestRegressao:
    def test_o_acesso_ao_backoffice_continua_valendo(self, client, perm_backoffice):
        """
        Quem tem só `access_backoffice` continua entrando na ÁREA.

        A biblioteca de modelos saiu desta asserção de propósito: desde a
        etapa da biblioteca ela exige
        `doctemplates.view_documenttemplate`, e a visão geral passou a ser
        a tela que qualquer pessoa do Backoffice abre.
        """
        pessoa = criar("so-backoffice@desenrola.be", "Sem Gerência", perm_backoffice)
        client.force_login(pessoa)

        assert client.get(reverse("backoffice:overview")).status_code == 200
        assert client.get(reverse("backoffice:appearance")).status_code == 200

    def test_o_atalho_no_painel_continua_pela_mesma_regra(
        self, client, perm_backoffice, alvo
    ):
        pessoa = criar("so-backoffice@desenrola.be", "Sem Gerência", perm_backoffice)

        client.force_login(pessoa)
        com = client.get(reverse("core:dashboard")).content.decode()
        client.force_login(alvo)
        sem = client.get(reverse("core:dashboard")).content.decode()

        assert reverse("backoffice:overview") in com
        assert reverse("backoffice:overview") not in sem

    def test_a_supervisao_de_cartas_continua_pela_sua_propria_permissao(
        self, cliente, operador, perm_ver_cartas
    ):
        """
        `manage_users` não dá acesso às cartas, e conceder
        `view_all_letters` pela tela nova abre a supervisão de verdade.
        """
        assert cliente.get(reverse("backoffice:letters")).status_code == 403

        operador.user_permissions.add(perm_ver_cartas)

        assert cliente.get(reverse("backoffice:letters")).status_code == 200

    def test_a_visao_geral_mostra_numeros_reais(self, cliente, alvo):
        contexto = cliente.get(reverse("backoffice:overview")).context

        valores = {str(n["rotulo"]): n["valor"] for n in contexto["numeros"]}
        assert valores["Usuários ativos"] == get_user_model().objects.filter(
            is_active=True
        ).count()
