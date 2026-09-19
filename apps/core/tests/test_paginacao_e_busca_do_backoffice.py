"""
Paginação, quantidade por página e busca -- Usuários e Cartas (Rodada 17).

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a quantidade por página fuja da lista.** 10, 20, 30 ou 50; o
   que vier fora disso vale a padrão (20);
2. **Que trocar de página perca alguma coisa.** Busca, filtros e
   quantidade atravessam cada link de página;
3. **Que trocar filtro, busca ou quantidade deixe a pessoa numa página
   que não existe.** Os três voltam para a primeira;
4. **Que a busca de Cartas seja feita no navegador.** Ela filtra o
   QUERYSET: referência, nome e e-mail de quem criou, nome do convidado
   -- nos dados do rascunho e nos congelados da carta fechada --, junto
   com os outros filtros;
5. **Que as colunas novas mostrem outra coisa.** Telefone, endereço e
   cidade da pessoa; ida e volta da estadia; "—" quando não há.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.core import paginacao
from apps.letters import services
from apps.letters.models import Letter

pytestmark = pytest.mark.django_db

USUARIOS = reverse("backoffice:users")
CARTAS = reverse("backoffice:letters")


def _cliente(*permissoes):
    pessoa = get_user_model().objects.create_user(
        email="operadora-paginas@mail.com", password="x", full_name="Operadora"
    )
    for app_label, codename in (("core", "access_backoffice"), *permissoes):
        pessoa.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    c = Client()
    c.force_login(pessoa)
    return c


@pytest.fixture
def gerente():
    return _cliente(("accounts", "manage_users"))


@pytest.fixture
def supervisora():
    return _cliente(("letters", "view_all_letters"))


def _pessoas(quantas):
    for numero in range(quantas):
        get_user_model().objects.create_user(
            email=f"gente{numero:02d}@exemplo.be", password="x", full_name=f"Gente {numero:02d}"
        )


def _carta(pessoa, idioma="fr", convidado="", ida="", volta=""):
    carta = services.start_draft(pessoa, idioma)
    assert carta is not None
    carta.data = {**(carta.data or {}), "guest_name": convidado, "stay_arrival": ida,
                  "stay_departure": volta}
    carta.save(update_fields=["data"])
    return carta


def _consulta(url):
    return parse_qs(urlparse(url).query)


# ===========================================================================
# 1. O módulo
# ===========================================================================


class TestModulo:
    @pytest.mark.parametrize(
        "pedido,esperado",
        [("10", 10), ("20", 20), ("30", 30), ("50", 50), ("", 20), ("15", 20),
         ("1000", 20), ("-10", 20), ("dez", 20)],
    )
    def test_so_as_quantidades_da_lista(self, pedido, esperado):
        request = RequestFactory().get(USUARIOS, {"page_size": pedido})

        assert paginacao.tamanho_pedido(request) == esperado

    def test_o_link_da_pagina_preserva_tudo(self):
        request = RequestFactory().get(USUARIOS, {"q": "ana", "status": "ativos",
                                                  "page_size": "10", "page": "4"})

        consulta = _consulta(paginacao.url_da_pagina(request, "backoffice:users", 2))

        assert consulta == {"q": ["ana"], "status": ["ativos"], "page_size": ["10"],
                            "page": ["2"]}

    def test_a_primeira_pagina_nao_leva_page(self):
        request = RequestFactory().get(USUARIOS, {"q": "ana", "page": "3"})

        assert paginacao.url_da_pagina(request, "backoffice:users", 1) == f"{USUARIOS}?q=ana"

    def test_limpar_filtros_mantem_so_a_quantidade(self):
        request = RequestFactory().get(USUARIOS, {"q": "ana", "status": "ativos",
                                                  "page_size": "30", "page": "2"})

        assert paginacao.url_sem_filtros(request, "backoffice:users") == f"{USUARIOS}?page_size=30"


# ===========================================================================
# 2. Usuários
# ===========================================================================


class TestPaginacaoDeUsuarios:
    @pytest.mark.parametrize("tamanho", [10, 20, 30, 50])
    def test_a_quantidade_escolhida_e_a_da_pagina(self, gerente, tamanho):
        _pessoas(55)

        resposta = gerente.get(USUARIOS, {"page_size": tamanho})

        assert len(resposta.context["pessoas"]) == tamanho
        assert resposta.context["paginacao"]["tamanho"] == tamanho

    def test_sem_escolha_sao_20(self, gerente):
        _pessoas(30)

        assert len(gerente.get(USUARIOS).context["pessoas"]) == 20

    def test_mostrando_x_y_de_n(self, gerente):
        _pessoas(30)  # + a operadora = 31

        corpo = gerente.get(USUARIOS, {"page_size": 10, "page": 2}).content.decode()

        assert "Mostrando 11–20 de 31 registros" in corpo

    def test_as_paginas_preservam_busca_situacao_e_quantidade(self, gerente):
        _pessoas(30)

        paginas = gerente.get(
            USUARIOS, {"q": "Gente", "status": "ativos", "page_size": 10}
        ).context["paginacao"]["paginas"]
        segunda = next(p for p in paginas if p.get("numero") == 2)

        assert _consulta(segunda["url"]) == {"q": ["Gente"], "status": ["ativos"],
                                             "page_size": ["10"], "page": ["2"]}

    def test_trocar_a_quantidade_volta_para_a_primeira_pagina(self, gerente):
        _pessoas(30)

        opcoes = gerente.get(
            USUARIOS, {"q": "Gente", "page_size": 10, "page": 3}
        ).context["paginacao"]["tamanhos"]
        trinta = next(o for o in opcoes if o["valor"] == 30)

        assert _consulta(trinta["url"]) == {"q": ["Gente"], "page_size": ["30"]}

    def test_trocar_a_situacao_volta_para_a_primeira_e_mantem_a_quantidade(self, gerente):
        _pessoas(30)

        opcoes = gerente.get(
            USUARIOS, {"page_size": 10, "page": 2}
        ).context["filtros_situacao"]
        inativos = next(o for o in opcoes if o["valor"] == "inativos")

        assert _consulta(inativos["url"]) == {"page_size": ["10"], "status": ["inativos"]}

    def test_a_busca_leva_a_quantidade_escondida(self, gerente):
        corpo = gerente.get(USUARIOS, {"page_size": 30}).content.decode()
        busca = corpo[corpo.index('class="mod-busca"') :]
        busca = busca[: busca.index("</form>")]

        assert '<input type="hidden" name="page_size" value="30">' in busca
        assert 'name="page"' not in busca

    def test_o_menu_da_quantidade_oferece_as_quatro(self, gerente):
        corpo = gerente.get(USUARIOS).content.decode()

        for tamanho in (10, 20, 30, 50):
            assert f"{tamanho} por página" in corpo


class TestColunasDeUsuarios:
    def test_telefone_endereco_e_cidade(self, gerente):
        get_user_model().objects.create_user(
            email="completa@exemplo.be", password="x", full_name="Pessoa Completa",
            phone="+32 470 11 22 33", address_line1="Rue de la Loi 16",
            address_line2="Bloco B", city="Bruxelas",
        )

        corpo = gerente.get(USUARIOS, {"q": "completa"}).content.decode()

        assert "+32 470 11 22 33" in corpo
        assert 'title="Rue de la Loi 16, Bloco B"' in corpo
        assert ">Rue de la Loi 16, Bloco B<" in corpo
        assert ">Bruxelas<" in corpo

    def test_campo_vazio_e_um_traco(self, gerente):
        get_user_model().objects.create_user(
            email="vazia@exemplo.be", password="x", full_name="Pessoa Vazia"
        )

        corpo = gerente.get(USUARIOS, {"q": "vazia"}).content.decode()
        linha = corpo[corpo.index('<div class="mod-linha') :]

        # telefone, endereço, cidade e último acesso ("Nunca") sem valor
        assert linha.count('<span class="mod-nada">—</span>') >= 3


# ===========================================================================
# 3. Cartas: a busca
# ===========================================================================


@pytest.fixture
def cartas(modelos_oficiais_prontos, user, other_user):
    """
    `user` (Claire Dubois, no conftest) tem uma carta em FR e uma em PT;
    `other_user` (Rafael Costa) tem uma em FR.
    """
    return {
        "user_fr": _carta(user, "fr", "Convidado Alfa", "2026-10-01", "2026-10-11"),
        "user_pt": _carta(user, "pt", "Convidado Beta"),
        "outro_fr": _carta(other_user, "fr", "Convidada Gama"),
    }


def _referencias(resposta):
    return {card.reference for card in resposta.context["cards"]}


class TestBuscaDeCartas:
    def test_pela_referencia(self, supervisora, cartas):
        alvo = cartas["user_pt"]

        resposta = supervisora.get(CARTAS, {"q": alvo.reference[-8:].lower()})

        assert _referencias(resposta) == {alvo.reference}

    def test_pelo_nome_de_quem_criou(self, supervisora, cartas, user):
        resposta = supervisora.get(CARTAS, {"q": user.full_name.split()[0]})

        assert _referencias(resposta) >= {cartas["user_fr"].reference,
                                          cartas["user_pt"].reference}
        assert cartas["outro_fr"].reference not in _referencias(resposta)

    def test_pelo_email_de_quem_criou(self, supervisora, cartas, other_user):
        resposta = supervisora.get(CARTAS, {"q": other_user.email})

        assert _referencias(resposta) == {cartas["outro_fr"].reference}

    def test_pelo_nome_do_convidado_no_rascunho(self, supervisora, cartas):
        resposta = supervisora.get(CARTAS, {"q": "gama"})

        assert _referencias(resposta) == {cartas["outro_fr"].reference}

    def test_pelo_nome_do_convidado_na_carta_fechada(self, supervisora, cartas):
        """Fechada, a carta mostra os dados CONGELADOS -- e a busca olha lá."""
        fechada = cartas["user_pt"]
        Letter.objects.filter(pk=fechada.pk).update(
            snapshot={"data": {"guest_name": "Nome Congelado"}}
        )

        resposta = supervisora.get(CARTAS, {"q": "congelado"})

        assert _referencias(resposta) == {fechada.reference}

    def test_junto_com_o_filtro_de_idioma(self, supervisora, cartas, user):
        """"João" + FR: só as cartas em FR relacionadas a ele."""
        resposta = supervisora.get(
            CARTAS, {"q": user.full_name.split()[0], "language": "fr"}
        )

        assert _referencias(resposta) == {cartas["user_fr"].reference}

    def test_junto_com_o_filtro_de_usuario(self, supervisora, cartas, other_user):
        resposta = supervisora.get(CARTAS, {"q": "Convid", "user": other_user.pk})

        assert _referencias(resposta) == {cartas["outro_fr"].reference}

    def test_sem_resultado(self, supervisora, cartas):
        corpo = supervisora.get(CARTAS, {"q": "ninguem-assim"}).content.decode()

        assert "Nenhuma carta encontrada" in corpo

    def test_e_no_queryset(self, supervisora, cartas):
        """
        A busca vira `WHERE` na consulta das cartas -- não uma varredura
        em Python depois de carregar tudo.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as capturadas:
            supervisora.get(CARTAS, {"q": "gama"})

        das_cartas = [c["sql"] for c in capturadas if 'FROM "letters_letter"' in c["sql"]]
        assert any("LIKE" in sql and "reference" in sql for sql in das_cartas)

    def test_a_busca_leva_filtros_e_quantidade_escondidos(self, supervisora, cartas, user):
        corpo = supervisora.get(
            CARTAS,
            {"state": "rascunho", "language": "fr", "user": user.pk, "from": "2026-01-01",
             "to": "2026-12-31", "page_size": "30"},
        ).content.decode()
        busca = corpo[corpo.index('class="mod-busca"') :]
        busca = busca[: busca.index("</form>")]

        for nome, valor in (("state", "rascunho"), ("language", "fr"), ("user", user.pk),
                            ("from", "2026-01-01"), ("to", "2026-12-31"),
                            ("page_size", "30")):
            assert f'<input type="hidden" name="{nome}" value="{valor}">' in busca
        assert 'name="page"' not in busca


# ===========================================================================
# 4. Cartas: paginação
# ===========================================================================


class TestPaginacaoDeCartas:
    @pytest.fixture
    def muitas(self, modelos_oficiais_prontos, user):
        for numero in range(25):
            _carta(user, "fr", f"Visitante {numero}")

    @pytest.mark.parametrize("tamanho", [10, 20])
    def test_a_quantidade_escolhida_e_a_da_pagina(self, supervisora, muitas, tamanho):
        resposta = supervisora.get(CARTAS, {"page_size": tamanho})

        assert len(resposta.context["cards"]) == tamanho

    def test_a_ultima_pagina_tem_o_resto(self, supervisora, muitas):
        resposta = supervisora.get(CARTAS, {"page_size": 10, "page": 3})

        assert len(resposta.context["cards"]) == 5
        assert "Mostrando 21–25 de 25 registros" in resposta.content.decode()

    def test_as_paginas_preservam_busca_filtros_e_quantidade(self, supervisora, muitas):
        paginas = supervisora.get(
            CARTAS, {"q": "Visitante", "language": "fr", "state": "rascunho", "page_size": 10}
        ).context["paginacao"]["paginas"]
        terceira = next(p for p in paginas if p.get("numero") == 3)

        assert _consulta(terceira["url"]) == {
            "q": ["Visitante"], "language": ["fr"], "state": ["rascunho"],
            "page_size": ["10"], "page": ["3"],
        }

    def test_filtro_a_partir_de_uma_pagina_volta_para_a_primeira(self, supervisora, muitas):
        resposta = supervisora.get(CARTAS, {"q": "Visitante", "page_size": 10, "page": 2})
        rascunho = next(o for o in resposta.context["filtros_estado"]
                        if o["valor"] == "rascunho")

        assert _consulta(rascunho["url"]) == {"q": ["Visitante"], "page_size": ["10"],
                                              "state": ["rascunho"]}

    def test_proxima_e_anterior(self, supervisora, muitas):
        paginacao_ = supervisora.get(CARTAS, {"page_size": 10, "page": 2}).context["paginacao"]

        assert _consulta(paginacao_["url_anterior"]) == {"page_size": ["10"]}
        assert _consulta(paginacao_["url_proxima"]) == {"page_size": ["10"], "page": ["3"]}

    def test_pagina_fora_do_intervalo_cai_na_ultima(self, supervisora, muitas):
        resposta = supervisora.get(CARTAS, {"page_size": 10, "page": 99})

        assert resposta.context["pagina"].number == 3


# ===========================================================================
# 5. Cartas: as colunas
# ===========================================================================


class TestColunasDeCartas:
    def test_criada_por_para_e_as_datas(self, supervisora, cartas, user):
        corpo = supervisora.get(CARTAS, {"q": "Alfa"}).content.decode()
        linha = corpo[corpo.index('<div class="mod-linha') :]

        assert (user.full_name or user.email) in linha
        assert ">Convidado Alfa<" in linha
        assert ">01/10/2026<" in linha
        assert ">11/10/2026<" in linha

    def test_sem_data_e_um_traco(self, supervisora, cartas):
        corpo = supervisora.get(CARTAS, {"q": "Beta"}).content.decode()
        linha = corpo[corpo.index('<div class="mod-linha') :]
        ida = linha[linha.index("Data de ida</span>") :]

        assert ida[: ida.index("</div>")].count('<span class="mod-nada">—</span>') == 1

    def test_a_referencia_tem_o_valor_inteiro_no_title(self, supervisora, cartas):
        alvo = cartas["user_fr"]

        corpo = supervisora.get(CARTAS).content.decode()

        assert f'title="{alvo.reference}">{alvo.reference}</a>' in corpo
