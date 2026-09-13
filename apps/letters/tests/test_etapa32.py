"""
Testes da Etapa 3.2 (ajustes de UI/UX): alinhamento da barra de navegação
e do dashboard, coluna de ações da tabela, duração da estadia atualizada
no navegador e o link "Editar meus dados" na etapa do anfitrião.

São ajustes visuais, mas cada um tem um contrato que dá para verificar
sem abrir o navegador: as classes de layout que o CSS espera, os
`data-` que o script lê, e a posição dos elementos no HTML. É isso que
está testado aqui -- a aparência final continua dependendo de olhar a
tela (ver relatório).
"""

import datetime
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.letters import services
from apps.letters.rules import MAX_STAY_DAYS, stay_duration_days

pytestmark = pytest.mark.django_db

RAIZ = Path(__file__).resolve().parents[3]
CSS = RAIZ / "static" / "css"
APP_JS = RAIZ / "static" / "js" / "app.js"

HOJE = timezone.localdate()
CHEGADA = HOJE + datetime.timedelta(days=30)
PARTIDA = CHEGADA + datetime.timedelta(days=14)


def _step_url(letter, step):
    return reverse("letters:step", args=[letter.uuid, step])


def _br(data):
    return data.strftime("%d/%m/%Y")


@pytest.fixture(autouse=True)
def _nacionalidade(nacionalidade_factory):
    nacionalidade_factory("Brasileira", guest_form="Brésilienne")


@pytest.fixture
def draft(user):
    return services.start_draft(user, "fr")


PASSO_1 = {
    "guest_name": "Maria Santos da Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "15/08/1990",
    "guest_passport": "YY0000",
}
PASSO_2 = {"stay_arrival": _br(CHEGADA), "stay_departure": _br(PARTIDA)}
PASSOS = {1: PASSO_1, 2: PASSO_2, 3: {"host_confirm": "on"}}


def _fill_until(client, letter, step):
    for n in range(1, step):
        client.post(_step_url(letter, n), PASSOS[n])


# ---------------------------------------------------------------------------
# 1. Barra de navegação da Home
# ---------------------------------------------------------------------------


class TestNavbarDaHome:
    def test_usa_o_container_padrao_do_projeto(self, client):
        """
        O mesmo `.container` do resto do site (max-width + margin auto) --
        não uma margem própria só para a barra.
        """
        html = client.get(reverse("core:home")).content.decode()

        assert 'class="nav-desktop site-nav container"' in html

    def test_todo_o_conteudo_fica_dentro_do_mesmo_container(self, client):
        """Logo, links, idioma e botões participam do mesmo alinhamento."""
        html = client.get(reverse("core:home")).content.decode()
        barra = html[html.index('class="nav-desktop site-nav container"') :]
        barra = barra[: barra.index("</nav>")]

        for pedaco in (
            "logo",
            "Como funciona",
            "Parceiros",
            "site-nav-lang",
            reverse("accounts:login"),
            reverse("accounts:signup"),
        ):
            assert pedaco in barra

    def test_o_espacador_empurra_o_lado_direito(self, client):
        """
        Sem isto tudo fica amontoado à esquerda, com a direita vazia --
        era exatamente o defeito relatado.
        """
        html = client.get(reverse("core:home")).content.decode()
        barra = html[html.index('class="nav-desktop site-nav container"') :]
        barra = barra[: barra.index("</nav>")]

        assert '<span class="push"></span>' in barra
        # o espaçador vem antes do bloco da direita
        assert barra.index("push") < barra.index(reverse("accounts:login"))

    def test_a_landing_usa_o_mesmo_container(self, client):
        """A barra alinha com as seções da página, não com a borda."""
        html = client.get(reverse("core:home")).content.decode()

        assert 'class="hero container"' in html
        assert 'class="section container"' in html

    def test_o_menu_do_celular_continua_intacto(self, client):
        html = client.get(reverse("core:home")).content.decode()

        assert 'class="nav-mobile"' in html
        assert "dropdown-item" in html


# ---------------------------------------------------------------------------
# 2. Alinhamento do dashboard
# ---------------------------------------------------------------------------


class TestAlinhamentoDoDashboard:
    def test_o_conteudo_fica_dentro_do_container(self, auth_client):
        html = auth_client.get(reverse("core:dashboard")).content.decode()

        assert '<div class="container">' in html
        assert html.index('<div class="container">') < html.index('class="dash"')

    def test_o_dashboard_nao_tem_largura_propria(self):
        """
        Regressão: `.dash` tinha `max-width: 1000px` sem centralização, o
        que deixava o conteúdo numa faixa estreita encostada à esquerda do
        container de 1280px. A largura tem de vir do container.
        """
        css = (CSS / "layout.css").read_text(encoding="utf-8")
        regra = re.search(r"^\.dash \{[^}]*\}", css, re.M).group(0)

        assert "max-width" not in regra

    def test_o_padding_lateral_acompanha_o_da_barra(self):
        """É o que faz a saudação nascer na mesma coluna que o logo."""
        layout = (CSS / "layout.css").read_text(encoding="utf-8")
        componentes = (CSS / "components.css").read_text(encoding="utf-8")

        dash = re.search(r"^\.dash \{[^}]*\}", layout, re.M).group(0)
        nav = re.search(r"^\.nav-desktop \{[^}]*\}", componentes, re.M).group(0)

        assert "48px" in dash
        assert "48px" in nav


# ---------------------------------------------------------------------------
# 3. Coluna de ações da tabela
# ---------------------------------------------------------------------------


class TestColunaDeAcoes:
    def _carta(self, user, status, com_pdf=False):
        from django.core.files.base import ContentFile


        letter = services.start_draft(user, "fr")
        letter.status = status
        if com_pdf:
            letter.pdf_file.save("x.pdf", ContentFile(b"%PDF-1.4"), save=False)
        letter.save()
        return letter

    def test_a_coluna_tem_a_mesma_moldura_em_toda_linha(self, auth_client, user):
        from apps.letters.models import Letter

        self._carta(user, Letter.Status.GENERATED, com_pdf=True)
        self._carta(user, Letter.Status.COMPLETED)
        self._carta(user, Letter.Status.DRAFT)

        html = auth_client.get(reverse("core:dashboard")).content.decode()
        celulas = re.findall(r'<td class="cell-actions">(.*?)</td>', html, re.S)

        assert len(celulas) == 3
        for celula in celulas:
            assert 'class="letter-actions"' in celula

    def test_a_gerada_mostra_ver_pdf_e_o_botao_de_icone(self, auth_client, user):
        from apps.letters.models import Letter

        letter = self._carta(user, Letter.Status.GENERATED, com_pdf=True)

        html = auth_client.get(reverse("core:dashboard")).content.decode()
        celula = re.search(r'<td class="cell-actions">(.*?)</td>', html, re.S).group(1)

        assert "btn-success" in celula
        assert reverse("letters:pdf", args=[letter.uuid]) in celula
        assert "btn-icon-sm" in celula

    def test_a_concluida_mostra_so_o_botao_de_icone(self, auth_client, user):
        from apps.letters.models import Letter

        self._carta(user, Letter.Status.COMPLETED)

        html = auth_client.get(reverse("core:dashboard")).content.decode()
        celula = re.search(r'<td class="cell-actions">(.*?)</td>', html, re.S).group(1)

        assert "btn-icon-sm" in celula
        assert "btn-success" not in celula

    def test_o_rascunho_mostra_continuar(self, auth_client, user):
        from apps.letters.models import Letter

        self._carta(user, Letter.Status.DRAFT)

        html = auth_client.get(reverse("core:dashboard")).content.decode()
        celula = re.search(r'<td class="cell-actions">(.*?)</td>', html, re.S).group(1)

        assert "Continuar" in celula

    def test_o_botao_de_icone_e_quadrado(self):
        """
        A regra geral da tabela dá `padding: 0 12px` a todo botão, o que
        deixaria o botão de ícone mais largo que alto. Ele precisa da sua
        própria medida.
        """
        css = (CSS / "layout.css").read_text(encoding="utf-8")
        regra = re.search(r"^\.letters-table td \.btn-icon-sm \{[^}]*\}", css, re.M).group(0)

        assert "width: 38px" in regra
        assert "min-height: 38px" in regra
        assert "padding: 0" in regra

    def test_as_acoes_ficam_a_direita_e_centralizadas(self):
        css = (CSS / "layout.css").read_text(encoding="utf-8")
        regra = re.search(r"^\.letter-actions \{[^}]*\}", css, re.M).group(0)

        assert "display: flex" in regra
        assert "align-items: center" in regra
        assert "justify-content: flex-end" in regra
        assert "gap" in regra


# ---------------------------------------------------------------------------
# 4. Duração da estadia atualizada no navegador
# ---------------------------------------------------------------------------


class TestDuracaoAoVivo:
    def test_a_caixa_leva_o_que_o_script_precisa(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        html = auth_client.get(_step_url(draft, 2)).content.decode()

        assert "data-duration-box" in html
        assert "data-duration-value" in html
        assert f'data-max-stay="{MAX_STAY_DAYS}"' in html
        # os textos saem traduzidos do template: o script não conhece idioma
        assert 'data-unit-one="dia"' in html
        assert 'data-unit-many="dias"' in html

    def test_sem_datas_a_caixa_vem_escondida(self, auth_client, draft):
        """Escondida, e não ausente: é assim que o script pode mostrá-la
        sem recarregar a página."""
        _fill_until(auth_client, draft, 2)

        html = auth_client.get(_step_url(draft, 2)).content.decode()
        caixa = html[html.index("data-duration-box") :]
        caixa = caixa[: caixa.index(">")]

        assert "hidden" in caixa

    def test_com_datas_a_caixa_aparece_com_o_numero(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)
        auth_client.post(_step_url(draft, 2), PASSO_2)

        response = auth_client.get(_step_url(draft, 2))
        html = response.content.decode()
        caixa = html[html.index("data-duration-box") :]
        abertura = caixa[: caixa.index(">")]

        assert "hidden" not in abertura
        assert response.context["duration_days"] == 15
        assert "15 dias" in html

    def test_o_aviso_de_limite_so_aparece_quando_passa(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        dentro = auth_client.post(_step_url(draft, 2), PASSO_2).status_code
        assert dentro == 302  # avançou: dentro do limite

        html = auth_client.post(
            _step_url(draft, 2),
            {
                "stay_arrival": _br(CHEGADA),
                "stay_departure": _br(CHEGADA + datetime.timedelta(days=MAX_STAY_DAYS)),
            },
        ).content.decode()
        aviso = html[html.index("data-duration-warning") :]
        aviso = aviso[: aviso.index(">")]

        assert "hidden" not in aviso
        assert "tag-error" in html

    @pytest.mark.parametrize(
        "chegada,partida",
        [
            ("", ""),
            ("10/10/2026", ""),
            ("", "24/10/2026"),
            ("31/02/2026", "24/10/2026"),
            ("abc", "24/10/2026"),
        ],
    )
    def test_dados_incompletos_ou_invalidos_nao_mostram_duracao(
        self, auth_client, draft, chegada, partida
    ):
        """Melhor não mostrar nada do que mostrar um número errado."""
        _fill_until(auth_client, draft, 2)

        response = auth_client.post(
            _step_url(draft, 2), {"stay_arrival": chegada, "stay_departure": partida}
        )

        assert response.context["duration_days"] is None

    def test_partida_antes_da_chegada_nao_tem_duracao(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        response = auth_client.post(
            _step_url(draft, 2),
            {"stay_arrival": _br(PARTIDA), "stay_departure": _br(CHEGADA)},
        )

        assert response.context["duration_days"] is None

    def test_o_script_atualiza_nos_mesmos_eventos_de_digitacao_e_calendario(self):
        """
        A duração precisa acompanhar tanto quem digita quanto quem escolhe
        no calendário -- e escolher no calendário escreve o valor por
        código, o que não dispara `input` sozinho.
        """
        js = APP_JS.read_text(encoding="utf-8")

        assert "refreshDuration" in js
        assert js.count("refreshDuration(event.target.form)") == 2  # input e change
        assert 'dispatchEvent(new Event("input"' in js


class TestDuracaoNoNavegadorBateComOServidor:
    """
    A conta do navegador e a do servidor têm de dar o mesmo número -- é a
    mesma regra (`apps/letters/rules.py`), só escrita duas vezes.

    Este teste roda a função do `app.js` no Node e compara com o Python.
    Sem Node instalado ele é pulado: a suíte do projeto é Python, e não
    vamos torná-la dependente de outra ferramenta.
    """

    CASOS = [
        ("2026-10-10", "2026-10-24"),  # o caso do documento oficial: 15 dias
        ("2026-10-10", "2026-10-10"),  # mesmo dia: 1 dia
        ("2026-01-01", "2026-03-31"),  # 90 dias
        ("2026-01-01", "2026-04-01"),  # 91 dias
        ("2026-02-28", "2026-03-01"),  # virada de mês
        ("2026-12-31", "2027-01-01"),  # virada de ano
        ("2026-10-24", "2026-10-10"),  # partida antes: sem duração
    ]

    def test_o_javascript_da_o_mesmo_numero_que_o_python(self):
        node = shutil.which("node")
        if node is None:
            pytest.skip("Node não está instalado neste ambiente")

        js = APP_JS.read_text(encoding="utf-8")
        corpo = re.search(
            r"function stayDurationDays\(isoChegada, isoPartida\) \{.*?\n  \}", js, re.S
        )
        assert corpo, "stayDurationDays não encontrada em app.js"

        script = (
            "var MS_POR_DIA = 24 * 60 * 60 * 1000;\n"
            + corpo.group(0)
            + "\nvar casos = "
            + json.dumps(self.CASOS)
            + ";\n"
            + "console.log(JSON.stringify("
            + "casos.map(function (c) { return stayDurationDays(c[0], c[1]); })));"
        )
        saida = subprocess.run(
            [node, "-e", script], capture_output=True, text=True, timeout=30, check=True
        )
        do_js = json.loads(saida.stdout)

        do_python = [
            stay_duration_days(
                datetime.date.fromisoformat(chegada), datetime.date.fromisoformat(partida)
            )
            for chegada, partida in self.CASOS
        ]

        assert do_js == do_python
        assert do_python[0] == 15  # a regra do documento oficial, explícita


# ---------------------------------------------------------------------------
# 5. Etapa do anfitrião: link "Editar meus dados"
# ---------------------------------------------------------------------------


class TestLinkEditarMeusDados:
    def test_o_aviso_do_topo_e_so_informativo(self, auth_client, draft):
        """O link saiu da mensagem explicativa."""
        _fill_until(auth_client, draft, 3)

        html = auth_client.get(_step_url(draft, 3)).content.decode()
        aviso = html[html.index('class="notice"') :]
        aviso = aviso[: aviso.index("</div>")]

        assert "<a " not in aviso
        assert "obtidos do seu perfil" in aviso

    def test_o_link_aparece_depois_dos_dados_e_antes_da_confirmacao(
        self, auth_client, draft
    ):
        _fill_until(auth_client, draft, 3)

        html = auth_client.get(_step_url(draft, 3)).content.decode()

        documento = html.index("Número do documento de identidade")
        link = html.index("Editar meus dados")
        confirmacao = html.index('name="host_confirm"')

        assert documento < link < confirmacao

    def test_o_link_leva_ao_perfil_e_volta_para_a_etapa(self, auth_client, draft):
        _fill_until(auth_client, draft, 3)

        html = auth_client.get(_step_url(draft, 3)).content.decode()
        trecho = html[html.index("host-edit-link") : html.index("Editar meus dados")]

        assert reverse("accounts:profile") in trecho
        assert "next=" in trecho
        assert _step_url(draft, 3) in trecho

    def test_o_link_explica_por_que_existe(self, auth_client, draft):
        _fill_until(auth_client, draft, 3)

        html = auth_client.get(_step_url(draft, 3)).content.decode()

        assert "Alguma informação está incorreta" in html

    def test_o_retorno_continua_protegido_pelo_mecanismo_existente(
        self, auth_client, draft, user
    ):
        """
        Nada de segurança nova aqui: quem valida o `next` continua sendo o
        `_safe_next` de accounts. Um destino externo é ignorado.
        """
        response = auth_client.post(
            reverse("accounts:profile"),
            {
                "action": "dados",
                "next": "https://exemplo-malicioso.test/",
                "full_name": user.full_name,
                "email": user.email,
                "phone": user.phone,
                "birth_date": "14/03/1985",
                "nationality": user.nationality_id,
                "document_number": user.document_number,
                "address_line1": user.address_line1,
                "postal_code": user.postal_code,
                "city": user.city,
            },
        )

        assert "exemplo-malicioso" not in response.url

    def test_o_retorno_para_a_etapa_funciona(self, auth_client, draft, user):
        volta = _step_url(draft, 3)

        response = auth_client.post(
            reverse("accounts:profile"),
            {
                "action": "dados",
                "next": volta,
                "full_name": user.full_name,
                "email": user.email,
                "phone": user.phone,
                "birth_date": "14/03/1985",
                "nationality": user.nationality_id,
                "document_number": user.document_number,
                "address_line1": user.address_line1,
                "postal_code": user.postal_code,
                "city": user.city,
            },
        )

        assert response.url == volta


# ---------------------------------------------------------------------------
# 6. O que NÃO pode ter mudado
# ---------------------------------------------------------------------------


class TestNadaDeRegressao:
    def test_a_etiqueta_de_dentro_do_limite_sumiu(self, auth_client, draft):
        """Era só indicação visual -- a regra continua (ver abaixo)."""
        _fill_until(auth_client, draft, 2)
        auth_client.post(_step_url(draft, 2), PASSO_2)

        html = auth_client.get(_step_url(draft, 2)).content.decode()

        assert "≤" not in html
        assert "&le;" not in html
        assert "tag-success" not in html

    def test_mas_a_regra_de_90_dias_continua_de_pe(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        response = auth_client.post(
            _step_url(draft, 2),
            {
                "stay_arrival": _br(CHEGADA),
                "stay_departure": _br(CHEGADA + datetime.timedelta(days=MAX_STAY_DAYS)),
            },
        )

        draft.refresh_from_db()
        assert "stay_departure" in response.context["form"].errors
        assert "stay_departure" not in draft.data

    def test_o_aviso_escrito_sobre_o_limite_continua(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        html = auth_client.get(_step_url(draft, 2)).content.decode()

        assert "90 dias" in html

    def test_o_calendario_nativo_da_etapa_31_continua(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        html = auth_client.get(_step_url(draft, 2)).content.decode()

        assert '<input type="date" class="date-input-picker"' in html
        assert "data-date-input" in html
        assert f'data-date-min="{HOJE.isoformat()}"' in html

    def test_o_botao_avancar_continua_marcado(self, auth_client, draft):
        _fill_until(auth_client, draft, 2)

        html = auth_client.get(_step_url(draft, 2)).content.decode()

        assert "data-step-submit" in html

    def test_a_home_continua_redirecionando_quem_esta_logado(self, auth_client):
        response = auth_client.get(reverse("core:home"))

        assert response.status_code == 302
        assert response.url == reverse("core:dashboard")

    def test_a_home_anonima_continua_abrindo(self):
        response = Client().get(reverse("core:home"))

        assert response.status_code == 200
