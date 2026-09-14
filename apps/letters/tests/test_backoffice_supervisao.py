"""
Supervisão de cartas no Backoffice: a listagem e o detalhe, lendo o
banco de verdade.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. que a tela volte a mostrar dados fictícios -- há teste que procura os
   nomes da demonstração antiga no HTML;
2. que a porta afrouxe -- cada checagem de permissão é feita pela URL
   direta, nunca pela ausência de um link;
3. que a expiração vaze para o lado errado -- o supervisor alcança a
   carta expirada, o dono não.

As cartas nascem pelo fluxo real (HTTP, as seis etapas): é o único jeito
de o teste responder pelo sistema que existe.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.letters import lifecycle
from apps.letters.models import Letter, LetterPolicy

pytestmark = pytest.mark.django_db

LISTA = reverse("backoffice:letters")


@pytest.fixture(autouse=True)
def _modelos_oficiais_prontos(modelos_oficiais_prontos):
    """Sem os modelos com logo materializado o assistente não cria carta."""


@pytest.fixture(autouse=True)
def _nacionalidade(nacionalidade_factory):
    nacionalidade_factory("Brasileira", name_fr="Brésilienne")


CHEGADA = timezone.localdate() + datetime.timedelta(days=30)
PASSOS = {
    1: {
        "guest_name": "Carlos Eduardo Silva",
        "guest_nationality": "Brasileira",
        "guest_birth_date": "22/07/1990",
        "guest_passport": "YY0000",
    },
    2: {
        "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
        "stay_departure": (CHEGADA + datetime.timedelta(days=14)).strftime("%d/%m/%Y"),
    },
    3: {"host_confirm": "on"},
    4: {"notice_informal": "on", "notice_prise_en_charge": "on"},
}


def _step(carta, n):
    return reverse("letters:step", args=[carta.uuid, n])


def finalizar_carta(client, user, *, idioma="fr"):
    """Uma carta emitida pelo caminho real, no idioma pedido."""
    client.post(reverse("letters:new"), PASSOS[1])
    carta = Letter.objects.filter(user=user).order_by("-pk").first()
    for numero in (2, 3, 4):
        client.post(_step(carta, numero), PASSOS[numero])
    client.post(_step(carta, 5), {"language": idioma})
    client.post(_step(carta, 6))
    carta.refresh_from_db()
    return carta


def criar_rascunho(client, user):
    client.post(reverse("letters:new"), PASSOS[1])
    return Letter.objects.filter(user=user).order_by("-pk").first()


def expirar(carta):
    """Joga a viagem para trás; com a política NA_DATA_DA_VIAGEM, expira."""
    config = lifecycle.policy()
    config.expiration = LetterPolicy.Expiration.NA_DATA_DA_VIAGEM
    config.save()
    passado = (timezone.localdate() - datetime.timedelta(days=10)).isoformat()
    carta.snapshot = {**carta.snapshot, "data": {**carta.snapshot["data"], "stay_arrival": passado}}
    carta.save(update_fields=["snapshot", "updated_at"])
    return carta


@pytest.fixture
def outra_pessoa(db, nacionalidade_do_perfil):
    """
    Um segundo usuário com o perfil COMPLETO -- e não o `other_user`
    do conftest, que nasce sem endereço/documento de propósito (serve
    a testes de isolamento) e por isso não consegue finalizar carta
    nenhuma: a etapa do anfitrião o barra, corretamente.

    Aqui o que se testa é a supervisão enxergando cartas de OUTRA
    pessoa -- então essa pessoa precisa conseguir emitir uma.
    """
    import datetime

    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="rafael@exemplo.com",
        password="senha-de-teste-123",
        full_name="Rafael Costa",
        phone="+32 470 11 11 11",
        document_number="11111111",
        birth_date=datetime.date(1990, 5, 20),
        nationality=nacionalidade_do_perfil,
        address_line1="Rue du Test 10",
        postal_code="1000",
        city="Bruxelles",
    )


@pytest.fixture
def cliente_outra_pessoa(outra_pessoa):
    """Sessão própria da segunda pessoa, separada da do `client`."""
    from django.test import Client

    cliente = Client()
    cliente.force_login(outra_pessoa)
    return cliente


@pytest.fixture
def supervisor(staff_user, permissao_ver_todas):
    """Entra no Backoffice E vê as cartas de todos."""
    staff_user.user_permissions.add(permissao_ver_todas)
    from django.contrib.auth import get_user_model

    return get_user_model().objects.get(pk=staff_user.pk)


@pytest.fixture
def cliente_supervisor(supervisor):
    """
    Um cliente PRÓPRIO, e não o `client` compartilhado.

    `auth_client` é o mesmo objeto `client`: logar o supervisor nele
    deslogaria o usuário comum no meio do teste, e as cartas passariam
    a nascer para a pessoa errada. Dois papéis, duas sessões.
    """
    from django.test import Client

    cliente = Client()
    cliente.force_login(supervisor)
    return cliente


# ===========================================================================
# Permissões
# ===========================================================================


class TestPermissoes:
    def test_usuario_comum_nao_entra(self, auth_client):
        assert auth_client.get(LISTA).status_code == 403

    def test_quem_so_entra_no_backoffice_NAO_ve_as_cartas(self, client, staff_user):
        """
        `core.access_backoffice` abre a área administrativa; ver o
        documento das pessoas exige a segunda permissão. São decisões
        separadas de propósito.
        """
        client.force_login(staff_user)

        assert client.get(LISTA).status_code == 403

    def test_com_as_duas_permissoes_entra(self, cliente_supervisor):
        assert cliente_supervisor.get(LISTA).status_code == 200

    def test_view_all_letters_sem_backoffice_nao_entra(
        self, client, user, permissao_ver_todas
    ):
        """A permissão de supervisão sozinha não abre a porta do Backoffice."""
        user.user_permissions.add(permissao_ver_todas)
        client.force_login(user)

        assert client.get(LISTA).status_code == 403

    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(LISTA)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_superusuario_entra(self, client, django_user_model):
        chefe = django_user_model.objects.create_superuser(
            email="chefe@desenrola.be", password="x", full_name="Chefe"
        )
        client.force_login(chefe)

        assert client.get(LISTA).status_code == 200

    def test_o_detalhe_tem_a_mesma_porta(self, auth_client, client, user, supervisor):
        """Não basta proteger a lista: o detalhe é acessível por URL própria."""
        carta = finalizar_carta(auth_client, user)
        url = reverse("backoffice:letter_detail", args=[carta.uuid])

        assert auth_client.get(url).status_code == 403

        client.force_login(supervisor)
        assert client.get(url).status_code == 200


# ===========================================================================
# A listagem lê o banco
# ===========================================================================


class TestListagemReal:
    def test_mostra_as_cartas_que_existem(self, auth_client, user, cliente_supervisor):
        carta = finalizar_carta(auth_client, user)

        corpo = cliente_supervisor.get(LISTA).content.decode()

        assert carta.reference in corpo
        assert user.email in corpo or user.full_name in corpo
        assert "Carlos Eduardo Silva" in corpo

    def test_mostra_cartas_de_QUALQUER_usuario(
        self, auth_client, user, cliente_outra_pessoa, outra_pessoa, cliente_supervisor
    ):
        minha = finalizar_carta(auth_client, user)
        alheia = finalizar_carta(cliente_outra_pessoa, outra_pessoa)

        corpo = cliente_supervisor.get(LISTA).content.decode()

        assert minha.reference in corpo
        assert alheia.reference in corpo

    def test_o_total_conta_as_cartas_do_banco(self, auth_client, user, cliente_supervisor):
        finalizar_carta(auth_client, user)
        criar_rascunho(auth_client, user)

        contexto = cliente_supervisor.get(LISTA).context

        assert contexto["total"] == Letter.objects.count() == 2

    def test_a_lista_vazia_nao_quebra(self, cliente_supervisor):
        resposta = cliente_supervisor.get(LISTA)

        assert resposta.status_code == 200
        assert "Nenhuma carta encontrada" in resposta.content.decode()

    def test_os_tres_estados_aparecem_com_o_rotulo_certo(
        self, auth_client, user, cliente_supervisor
    ):
        criar_rascunho(auth_client, user)
        finalizar_carta(auth_client, user)
        expirar(finalizar_carta(auth_client, user))

        corpo = cliente_supervisor.get(LISTA).content.decode()

        assert "Rascunho" in corpo
        assert "Finalizada" in corpo
        assert "Expirada" in corpo

    def test_a_data_de_finalizacao_aparece_so_para_quem_tem(
        self, auth_client, user, cliente_supervisor
    ):
        rascunho = criar_rascunho(auth_client, user)
        carta = finalizar_carta(auth_client, user)

        contexto = cliente_supervisor.get(LISTA).context
        por_uuid = {c.uuid: c for c in contexto["cards"]}

        assert por_uuid[carta.uuid].letter.finalized_at is not None
        assert por_uuid[rascunho.uuid].letter.finalized_at is None

    def test_as_cartas_de_outra_pessoa_realmente_finalizam(
        self, cliente_outra_pessoa, outra_pessoa
    ):
        """
        Guarda do próprio teste: se a segunda pessoa deixar de
        conseguir emitir (perfil incompleto, por exemplo), os testes
        de "carta alheia" passariam a comparar rascunhos sem perceber.
        """
        carta = finalizar_carta(cliente_outra_pessoa, outra_pessoa, idioma="pt")

        assert carta.status == Letter.Status.GENERATED
        assert carta.language == "pt"

    def test_a_tela_NAO_oferece_acao_de_edicao(self, auth_client, user, cliente_supervisor):
        """Ver não é editar: nenhum link para o assistente sai daqui."""
        carta = finalizar_carta(auth_client, user)

        corpo = cliente_supervisor.get(LISTA).content.decode()

        assert reverse("letters:step", args=[carta.uuid, 1]) not in corpo


# ===========================================================================
# Nada de dados fictícios
# ===========================================================================


class TestSemDadosFicticios:
    def test_o_modulo_de_demonstracao_nao_tem_mais_a_lista_falsa(self):
        from apps.core import demo

        assert not hasattr(demo, "ALL_LETTERS")

    def test_a_tela_nao_mostra_os_nomes_da_demonstracao(self, cliente_supervisor):
        """
        Os nomes que a lista fictícia usava. Se algum voltar a aparecer,
        é porque a tela voltou a inventar dados.
        """
        corpo = cliente_supervisor.get(LISTA).content.decode()

        for inventado in ("João Pedro Alves", "Carta-Convite-Maria-Santos.pdf"):
            assert inventado not in corpo

    def test_a_view_consulta_o_modelo(self, auth_client, user, cliente_supervisor):
        """Some do banco, some da tela -- prova que a fonte é o banco."""
        carta = finalizar_carta(auth_client, user)
        assert carta.reference in cliente_supervisor.get(LISTA).content.decode()

        Letter.objects.filter(pk=carta.pk).delete()

        assert carta.reference not in cliente_supervisor.get(LISTA).content.decode()


# ===========================================================================
# Filtros
# ===========================================================================


class TestFiltros:
    def test_por_estado(self, auth_client, user, cliente_supervisor):
        rascunho = criar_rascunho(auth_client, user)
        finalizada = finalizar_carta(auth_client, user)

        corpo = cliente_supervisor.get(LISTA, {"state": lifecycle.RASCUNHO}).content.decode()

        assert rascunho.reference in corpo
        assert finalizada.reference not in corpo

    def test_por_estado_expirada(self, auth_client, user, cliente_supervisor):
        """Estado DERIVADO: não existe coluna, e mesmo assim filtra."""
        expirada = expirar(finalizar_carta(auth_client, user))
        valida = finalizar_carta(auth_client, user)

        corpo = cliente_supervisor.get(LISTA, {"state": lifecycle.EXPIRADA}).content.decode()

        assert expirada.reference in corpo
        assert valida.reference not in corpo

    def test_por_idioma(self, auth_client, user, cliente_supervisor):
        francesa = finalizar_carta(auth_client, user, idioma="fr")
        portuguesa = finalizar_carta(auth_client, user, idioma="pt")

        corpo = cliente_supervisor.get(LISTA, {"language": "pt"}).content.decode()

        assert portuguesa.reference in corpo
        assert francesa.reference not in corpo

    def test_por_usuario(
        self, auth_client, user, cliente_outra_pessoa, outra_pessoa, cliente_supervisor
    ):
        minha = finalizar_carta(auth_client, user)
        alheia = finalizar_carta(cliente_outra_pessoa, outra_pessoa)

        corpo = cliente_supervisor.get(LISTA, {"user": str(outra_pessoa.pk)}).content.decode()

        assert alheia.reference in corpo
        assert minha.reference not in corpo

    def test_por_periodo_da_viagem(self, auth_client, user, cliente_supervisor):
        carta = finalizar_carta(auth_client, user)
        depois = (CHEGADA + datetime.timedelta(days=1)).isoformat()

        dentro = cliente_supervisor.get(LISTA, {"from": CHEGADA.isoformat()}).content.decode()
        fora = cliente_supervisor.get(LISTA, {"from": depois}).content.decode()

        assert carta.reference in dentro
        assert carta.reference not in fora

    def test_filtros_combinam(
        self, auth_client, user, cliente_outra_pessoa, outra_pessoa, cliente_supervisor
    ):
        minha = finalizar_carta(auth_client, user, idioma="pt")
        alheia_pt = finalizar_carta(cliente_outra_pessoa, outra_pessoa, idioma="pt")
        alheia_fr = finalizar_carta(cliente_outra_pessoa, outra_pessoa, idioma="fr")

        corpo = cliente_supervisor.get(
            LISTA, {"user": str(outra_pessoa.pk), "language": "pt"}
        ).content.decode()

        assert alheia_pt.reference in corpo
        assert alheia_fr.reference not in corpo
        assert minha.reference not in corpo

    def test_filtro_invalido_nao_quebra(self, auth_client, user, cliente_supervisor):
        """Querystring é entrada do cliente: lixo não pode derrubar a tela."""
        finalizar_carta(auth_client, user)

        resposta = cliente_supervisor.get(
            LISTA, {"user": "abc", "from": "ontem", "state": "inexistente"}
        )

        assert resposta.status_code == 200

    def test_sem_filtro_mostra_tudo(self, auth_client, user, cliente_supervisor):
        criar_rascunho(auth_client, user)
        finalizar_carta(auth_client, user)

        assert cliente_supervisor.get(LISTA).context["total"] == 2


# ===========================================================================
# Detalhe
# ===========================================================================


class TestDetalhe:
    def test_o_supervisor_abre_a_carta_de_outro_usuario(
        self, auth_client, user, cliente_supervisor
    ):
        carta = finalizar_carta(auth_client, user)

        corpo = cliente_supervisor.get(
            reverse("backoffice:letter_detail", args=[carta.uuid])
        ).content.decode()

        assert carta.reference in corpo
        assert user.email in corpo
        assert "Carlos Eduardo Silva" in corpo

    def test_mostra_modelo_idioma_e_politica(self, auth_client, user, cliente_supervisor):
        carta = finalizar_carta(auth_client, user)

        contexto = cliente_supervisor.get(
            reverse("backoffice:letter_detail", args=[carta.uuid])
        ).context

        assert contexto["carta"].document_template.slug == "carta-convite-fr"
        assert contexto["dono"] == user
        assert contexto["politica"] == lifecycle.policy()
        assert contexto["card"].state == lifecycle.FINALIZADA

    def test_mostra_os_dados_preenchidos_com_os_rotulos_do_schema(
        self, auth_client, user, cliente_supervisor
    ):
        carta = finalizar_carta(auth_client, user)

        corpo = cliente_supervisor.get(
            reverse("backoffice:letter_detail", args=[carta.uuid])
        ).content.decode()

        assert "Nome completo do convidado" in corpo
        assert "YY0000" in corpo

    def test_carta_expirada_abre_e_diz_que_expirou(
        self, auth_client, user, cliente_supervisor
    ):
        carta = expirar(finalizar_carta(auth_client, user))

        resposta = cliente_supervisor.get(
            reverse("backoffice:letter_detail", args=[carta.uuid])
        )

        assert resposta.status_code == 200
        assert resposta.context["card"].is_expired is True
        assert "Expirada" in resposta.content.decode()

    def test_uuid_inexistente_da_404(self, cliente_supervisor):
        import uuid as uuid_lib

        url = reverse("backoffice:letter_detail", args=[uuid_lib.uuid4()])

        assert cliente_supervisor.get(url).status_code == 404

    def test_nenhuma_acao_de_edicao_no_detalhe(self, auth_client, user, cliente_supervisor):
        carta = finalizar_carta(auth_client, user)

        corpo = cliente_supervisor.get(
            reverse("backoffice:letter_detail", args=[carta.uuid])
        ).content.decode()

        assert reverse("letters:step", args=[carta.uuid, 1]) not in corpo
        assert "Editar" not in corpo


# ===========================================================================
# O PDF: o supervisor alcança; o dono expirado, não
# ===========================================================================


class TestPdfNaSupervisao:
    def test_supervisor_baixa_o_pdf_de_carta_expirada(
        self, auth_client, user, cliente_supervisor
    ):
        carta = expirar(finalizar_carta(auth_client, user))

        resposta = cliente_supervisor.get(reverse("letters:pdf", args=[carta.uuid]))

        assert resposta.status_code == 200
        assert resposta["Content-Type"] == "application/pdf"

    def test_o_dono_continua_bloqueado_na_mesma_carta(self, auth_client, user):
        """A supervisão não afrouxa a regra para o usuário comum."""
        carta = expirar(finalizar_carta(auth_client, user))

        resposta = auth_client.get(reverse("letters:pdf", args=[carta.uuid]), follow=True)

        assert "expirou" in resposta.content.decode()

    def test_o_detalhe_administrativo_oferece_o_pdf_da_expirada(
        self, auth_client, user, cliente_supervisor
    ):
        carta = expirar(finalizar_carta(auth_client, user))

        resposta = cliente_supervisor.get(
            reverse("backoffice:letter_detail", args=[carta.uuid])
        )

        assert resposta.context["pode_baixar_pdf"] is True
        assert reverse("letters:pdf", args=[carta.uuid]) in resposta.content.decode()

    def test_rascunho_nao_oferece_pdf(self, auth_client, user, cliente_supervisor):
        rascunho = criar_rascunho(auth_client, user)

        resposta = cliente_supervisor.get(
            reverse("backoffice:letter_detail", args=[rascunho.uuid])
        )

        assert resposta.context["pode_baixar_pdf"] is False
        assert "ainda não tem PDF gerado" in resposta.content.decode()

    def test_usuario_comum_nao_baixa_pdf_alheio(
        self, auth_client, user, client, other_user
    ):
        """O isolamento entre pessoas não muda nada com esta etapa."""
        carta = finalizar_carta(auth_client, user)
        client.force_login(other_user)

        assert client.get(reverse("letters:pdf", args=[carta.uuid])).status_code == 404


# ===========================================================================
# A regra de autorização mora num lugar só
# ===========================================================================


class TestAutorizacaoCentralizada:
    def test_can_user_download_pdf_responde_pelos_dois_lados(
        self, auth_client, user, supervisor
    ):
        carta = expirar(finalizar_carta(auth_client, user))

        assert lifecycle.can_user_download_pdf(user, carta) is False
        assert lifecycle.can_user_download_pdf(supervisor, carta) is True

    def test_sem_pdf_ninguem_baixa_nem_o_supervisor(
        self, auth_client, user, supervisor
    ):
        rascunho = criar_rascunho(auth_client, user)

        assert lifecycle.can_user_download_pdf(supervisor, rascunho) is False

    def test_nenhuma_view_decide_pela_string_da_permissao(self):
        """
        Quem DECIDE pergunta a `lifecycle.supervisiona()`; a string
        `"letters.view_all_letters"` só aparece onde ela é um DADO.

        Três lugares são legítimos, e cada um por um motivo diferente:

          * `lifecycle.py`   -- a constante, o dono da string;
          * `models.py`      -- `visible_to()`, a mesma regra aplicada no
                                banco (um queryset não chama serviço);
          * `admin_permissions.py` -- o catálogo do Backoffice, que
                                LISTA permissões como dado, sem decidir
                                nada com elas.

        Qualquer quarto lugar é uma segunda decisão escondida, e é isto
        que este teste existe para pegar: a lista abaixo é explícita de
        propósito -- um arquivo novo faz o teste falhar e obriga alguém a
        justificar, em vez de o número subir em silêncio.
        """
        import pathlib
        import re

        # Por CAMINHO, não por nome de arquivo: "models.py" existe em
        # todo app, e liberar pelo basename deixaria a guarda cega para
        # uma cópia em qualquer outro models.py do projeto.
        permitidos = {
            "apps/letters/lifecycle.py": "a constante SUPERVISION_PERM",
            "apps/letters/models.py": "o queryset visible_to()",
            "apps/accounts/admin_permissions.py": "o catálogo (dado, não decisão)",
        }

        raiz = pathlib.Path(__file__).resolve().parents[3]
        intrusos = []
        for arquivo in raiz.rglob("*.py"):
            if any(p in (".venv", "__pycache__", "tests", "migrations") for p in arquivo.parts):
                continue
            if arquivo.relative_to(raiz).as_posix() in permitidos:
                continue
            for numero, linha in enumerate(
                arquivo.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if re.search(r'["\']letters\.view_all_letters["\']', linha):
                    caminho = arquivo.relative_to(raiz).as_posix()
                    intrusos.append(f"{caminho}:{numero}: {linha.strip()[:70]}")

        assert not intrusos, intrusos
