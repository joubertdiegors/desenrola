"""
O atalho do Backoffice na barra superior da área logada.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. que o atalho apareça para quem levaria 403 ao clicar -- uma porta que
   bate na cara de quem a abre;
2. que alguém confunda esconder o link com proteger a rota: todo teste
   de bloqueio aqui vai pela URL DIRETA, que é o que uma pessoa faria;
3. que o atalho exista só no painel. Ele está na barra, então tem de
   valer em toda a área logada -- painel, histórico e perfil.

`perms.core.access_backoffice` cobre superusuário sozinho, por como
`has_perm` funciona. Há um teste para isso porque é exatamente o tipo de
coisa que um refactor "explícito" quebra ao trocar `perms` por uma
consulta manual de permissões.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

pytestmark = pytest.mark.django_db

BACKOFFICE = reverse("backoffice:overview")

# As telas da área logada que usam a barra superior.
TELAS_COM_BARRA = [
    reverse("core:dashboard"),
    reverse("letters:history"),
    reverse("accounts:profile"),
]


def _link_do_atalho(corpo):
    """O trecho da barra em volta do atalho, ou None se ele não está lá."""
    if "nav-backoffice" not in corpo:
        return None
    inicio = corpo.index("nav-backoffice")
    return corpo[max(0, inicio - 300) : inicio + 300]


# ===========================================================================
# 1. Quem vê
# ===========================================================================


class TestQuemVe:
    @pytest.mark.parametrize("url", TELAS_COM_BARRA)
    def test_com_a_permissao_o_atalho_aparece(self, client, staff_user, url):
        """A barra é a mesma em toda a área logada -- o atalho também."""
        client.force_login(staff_user)

        corpo = client.get(url).content.decode()

        assert _link_do_atalho(corpo) is not None

    @pytest.mark.parametrize("url", TELAS_COM_BARRA)
    def test_sem_a_permissao_o_atalho_nao_aparece(self, auth_client, url):
        corpo = auth_client.get(url).content.decode()

        assert _link_do_atalho(corpo) is None
        assert BACKOFFICE not in corpo

    def test_superusuario_ve_sem_precisar_da_permissao_atribuida(self, client):
        """
        `has_perm` devolve True para superusuário sem consultar a tabela.
        Trocar `perms` por uma consulta manual quebraria isto em silêncio.
        """
        chefe = get_user_model().objects.create_superuser(
            email="chefe@mail.com", password="x", full_name="Helena Braga"
        )
        assert chefe.user_permissions.count() == 0
        client.force_login(chefe)

        corpo = client.get(reverse("core:dashboard")).content.decode()

        assert _link_do_atalho(corpo) is not None

    def test_is_staff_sozinho_nao_faz_o_atalho_aparecer(self, client, staff_sem_backoffice):
        """
        `is_staff` é a flag do Django Admin. Quem abre esta porta é a
        permissão, e só ela.
        """
        client.force_login(staff_sem_backoffice)

        corpo = client.get(reverse("core:dashboard")).content.decode()

        assert _link_do_atalho(corpo) is None

    def test_anonimo_nao_ve(self, client):
        """
        A barra nem chega a ser renderizada: a landing é outra casca e as
        telas da área logada exigem login.
        """
        corpo = client.get(reverse("core:home")).content.decode()

        assert _link_do_atalho(corpo) is None
        assert BACKOFFICE not in corpo

    def test_perder_a_permissao_tira_o_atalho_na_hora(
        self, client, staff_user, permissao_backoffice
    ):
        """Sem cache velho: a barra reflete a permissão de agora."""
        client.force_login(staff_user)
        assert _link_do_atalho(client.get(reverse("core:dashboard")).content.decode())

        staff_user.user_permissions.remove(permissao_backoffice)
        client.force_login(get_user_model().objects.get(pk=staff_user.pk))

        corpo = client.get(reverse("core:dashboard")).content.decode()

        assert _link_do_atalho(corpo) is None


# ===========================================================================
# 2. Para onde aponta
# ===========================================================================


class TestDestino:
    def test_aponta_para_a_rota_nomeada_do_backoffice(self, client, staff_user):
        client.force_login(staff_user)

        trecho = _link_do_atalho(client.get(reverse("core:dashboard")).content.decode())

        assert f'href="{BACKOFFICE}"' in trecho

    def test_a_url_vem_do_roteador_e_nao_esta_escrita_a_mao(self):
        """
        Se a rota mudar de endereço, o `{% url %}` acompanha. Este teste
        prova que o endereço não foi copiado para dentro do template.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        nav = (raiz / "templates" / "components" / "app_nav.html").read_text(encoding="utf-8")

        assert "{% url 'backoffice:overview' %}" in nav
        assert "/backoffice/" not in nav

    def test_o_atalho_leva_de_fato_ao_backoffice(self, client, staff_user):
        """Seguir o link abre a tela, e não um 404 nem um 403."""
        client.force_login(staff_user)

        assert client.get(BACKOFFICE).status_code == 200


# ===========================================================================
# 3. A porta continua no servidor
# ===========================================================================


class TestProtecaoNoServidor:
    def test_quem_nao_ve_o_atalho_tambem_nao_entra_pela_url(self, auth_client):
        """Esconder o link nunca foi proteção -- a URL é digitável."""
        assert auth_client.get(BACKOFFICE).status_code == 403

    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(BACKOFFICE)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_is_staff_sozinho_e_recusado(self, client, staff_sem_backoffice):
        client.force_login(staff_sem_backoffice)

        assert client.get(BACKOFFICE).status_code == 403


# ===========================================================================
# 4. A barra continua sendo a mesma
# ===========================================================================


class TestSemRegressaoNaNavegacao:
    def test_os_destinos_de_sempre_continuam_na_barra(self, client, staff_user):
        """O atalho ENTRA na barra; não substitui nada."""
        client.force_login(staff_user)

        corpo = client.get(reverse("core:dashboard")).content.decode()

        assert f'href="{reverse("core:dashboard")}"' in corpo
        assert f'href="{reverse("letters:history")}"' in corpo
        assert f'href="{reverse("accounts:profile")}"' in corpo
        assert f'action="{reverse("accounts:logout")}"' in corpo

    def test_nao_ha_uma_segunda_barra(self, client, staff_user):
        """Uma navegação principal, não duas."""
        client.force_login(staff_user)

        corpo = client.get(reverse("core:dashboard")).content.decode()

        assert corpo.count('class="nav-desktop app-nav container"') == 1
        assert corpo.count("nav-backoffice") == 1

    def test_a_barra_inferior_do_celular_nao_mudou(self, client, staff_user):
        """
        Os três destinos do celular continuam três. O atalho mora na
        barra de cima, e mexer aqui mudaria a navegação principal.
        """
        client.force_login(staff_user)

        corpo = client.get(reverse("core:dashboard")).content.decode()
        inicio = corpo.index('class="tabbar')
        tabbar = corpo[inicio : corpo.index("</nav>", inicio)]

        assert tabbar.count("<a href=") == 3
        assert "nav-backoffice" not in tabbar

    def test_o_painel_nao_tem_mais_atalho_proprio(self, client, staff_user):
        """
        O cartão `dash-backoffice` saiu do corpo do painel: o acesso ao
        Backoffice é um só, e é o da barra. Se o cartão voltar, voltam
        dois caminhos para a mesma porta.
        """
        client.force_login(staff_user)

        corpo = client.get(reverse("core:dashboard")).content.decode()

        assert "dash-backoffice" not in corpo
        assert corpo.count(reverse("backoffice:overview")) == 1


# ===========================================================================
# 5. Responsivo e acessível
# ===========================================================================


class TestApresentacao:
    def test_o_rotulo_so_aparece_no_desktop(self, client, staff_user):
        """
        No celular a barra tem logotipo, atalho e avatar: o rótulo
        escrito empurraria a linha. Fica só o ícone.
        """
        client.force_login(staff_user)

        trecho = _link_do_atalho(client.get(reverse("core:dashboard")).content.decode())

        assert '<span class="d-only">' in trecho

    def test_tem_nome_acessivel_mesmo_sem_o_rotulo_visivel(self, client, staff_user):
        """
        No celular sobra só o ícone, que é decorativo. Sem `aria-label` o
        link seria anunciado sem nome.
        """
        client.force_login(staff_user)

        trecho = _link_do_atalho(client.get(reverse("core:dashboard")).content.decode())

        assert "aria-label=" in trecho
        assert 'aria-hidden="true"' in trecho

    def test_usa_os_componentes_que_ja_existem(self, client, staff_user):
        """
        Botão do sistema (`btn btn-text`) e ícone Phosphor -- nenhuma
        dependência nova, nenhum componente paralelo.
        """
        client.force_login(staff_user)

        trecho = _link_do_atalho(client.get(reverse("core:dashboard")).content.decode())

        assert "btn btn-text" in trecho
        assert "ph ph-gear" in trecho

    def test_o_atalho_nao_encolhe_na_barra(self):
        """
        `flex: none` numa barra em flex: sem isso o botão cederia espaço
        antes do logotipo, e a área de toque mudaria de tamanho conforme
        o nome da pessoa.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        css = (raiz / "static" / "css" / "layout.css").read_text(encoding="utf-8")

        assert ".app-nav .nav-backoffice { flex: none; }" in css

    def test_o_atalho_nao_carrega_largura_fixa_que_estoure_a_barra(self):
        """
        Nada de `min-width` nem largura em px: a barra do celular tem
        ~360px úteis, e uma medida fixa aqui seria a origem de rolagem
        horizontal.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        css = (raiz / "static" / "css" / "layout.css").read_text(encoding="utf-8")
        inicio = css.index(".app-nav .nav-backoffice")
        regra = css[inicio : css.index("}", inicio)]

        assert "min-width" not in regra
        assert "px" not in regra
