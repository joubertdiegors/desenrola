"""
Histórico "Minhas cartas" e as ações de cada carta.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. que o histórico mostre carta de outra pessoa -- nem para quem
   supervisiona: esta é a área PESSOAL;
2. que o painel e o histórico ofereçam ações diferentes para o mesmo
   estado (os dois usam o mesmo include);
3. que "Baixar" volte a servir o PDF inline, sem `attachment`;
4. que o painel volte a mostrar a data de última alteração no lugar da
   data de criação.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.letters import lifecycle, presentation
from apps.letters.models import Letter, LetterPolicy

pytestmark = pytest.mark.django_db

DASHBOARD = reverse("core:dashboard")
HISTORICO = reverse("letters:history")


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


def criar_rascunho(client, user):
    client.post(reverse("letters:new"), PASSOS[1])
    return Letter.objects.filter(user=user).order_by("-pk").first()


def finalizar(client, user):
    carta = criar_rascunho(client, user)
    for numero in (2, 3, 4):
        client.post(_step(carta, numero), PASSOS[numero])
    client.post(_step(carta, 5), {"language": "fr"})
    client.post(_step(carta, 6))
    carta.refresh_from_db()
    return carta


def _sem_recado(resposta):
    return [str(m) for m in resposta.context["messages"]]


def expirar(carta):
    config = lifecycle.policy()
    config.expiration = LetterPolicy.Expiration.NA_DATA_DA_VIAGEM
    config.save()
    passado = (timezone.localdate() - datetime.timedelta(days=10)).isoformat()
    carta.snapshot = {**carta.snapshot, "data": {**carta.snapshot["data"], "stay_arrival": passado}}
    carta.save(update_fields=["snapshot", "updated_at"])
    return carta


# ===========================================================================
# Finalizar não deixa recado repetido
# ===========================================================================


class TestSemRecadoRepetido:
    """
    Finalizar levava a uma faixa "Carta Convite gerada com sucesso." em
    cima da tela que diz, em letras garrafais e com selo verde,
    exatamente isso.

    A mensagem saiu da ORIGEM (`letters.views`), e não do template: uma
    mensagem enfileirada que ninguém desenha não some -- ela espera a
    próxima tela e aparece lá, fora de contexto. O segundo teste é
    justamente sobre isso.
    """

    def test_a_tela_da_carta_nao_traz_recado(self, auth_client, user):
        carta = criar_rascunho(auth_client, user)
        for numero in (2, 3, 4):
            auth_client.post(_step(carta, numero), PASSOS[numero])
        auth_client.post(_step(carta, 5), {"language": "fr"})

        resposta = auth_client.post(_step(carta, 6), follow=True)

        carta.refresh_from_db()
        assert carta.status == Letter.Status.GENERATED
        assert resposta.redirect_chain[-1][0] == reverse("letters:detail", args=[carta.uuid])
        assert _sem_recado(resposta) == []

    def test_e_nao_sobra_recado_para_a_tela_seguinte(self, auth_client, user):
        finalizar(auth_client, user)

        seguinte = auth_client.get(reverse("core:dashboard"))

        assert _sem_recado(seguinte) == []


# ===========================================================================
# O histórico
# ===========================================================================


class TestHistorico:
    def test_exige_login(self, client):
        resposta = client.get(HISTORICO)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_mostra_todas_as_cartas_da_pessoa(self, auth_client, user):
        uma = finalizar(auth_client, user)
        outra = criar_rascunho(auth_client, user)

        corpo = auth_client.get(HISTORICO).content.decode()

        assert uma.data["guest_name"] in corpo
        assert reverse("letters:detail", args=[uma.uuid]) in corpo
        assert reverse("letters:detail", args=[outra.uuid]) in corpo

    def test_passa_do_limite_do_painel(self, auth_client, user):
        """
        O painel mostra 5; o histórico mostra todas. É a razão de a tela
        existir.

        O 5 vai escrito aqui, e não só como `RECENT_LIMIT`: comparar a
        constante com ela mesma passaria com qualquer valor.
        """
        assert presentation.RECENT_LIMIT == 5

        for _ in range(7):
            criar_rascunho(auth_client, user)

        painel = auth_client.get(DASHBOARD).context
        historico = auth_client.get(HISTORICO).context

        assert len(painel["cards"]) == 5
        assert painel["letters_total"] == 7
        assert len(historico["cards"]) == 7

    def test_lista_vazia_nao_quebra(self, auth_client):
        resposta = auth_client.get(HISTORICO)

        assert resposta.status_code == 200
        assert "ainda não tem cartas" in resposta.content.decode()

    def test_sempre_oferece_gerar_uma_carta(self, auth_client, user):
        """
        Com lista ou sem lista: quem chega aqui pelo menu tem de poder
        começar uma carta sem voltar ao painel.
        """
        vazio = auth_client.get(HISTORICO).content.decode()
        criar_rascunho(auth_client, user)
        cheio = auth_client.get(HISTORICO).content.decode()

        for corpo in (vazio, cheio):
            assert f'href="{reverse("letters:new")}"' in corpo

    def test_ordenado_da_mais_nova_para_a_mais_antiga(self, auth_client, user):
        primeira = criar_rascunho(auth_client, user)
        segunda = criar_rascunho(auth_client, user)

        cards = auth_client.get(HISTORICO).context["cards"]

        assert [c.uuid for c in cards] == [segunda.uuid, primeira.uuid]

    def test_mexer_numa_carta_antiga_nao_a_joga_para_o_topo(self, auth_client, user):
        """
        A ordem é a da CRIAÇÃO. Mexer numa carta antiga toca
        `updated_at`, e antes isso a fazia pular para o começo da lista
        -- com a data de criação exibida ao lado, parecia desordenada.
        """
        antiga = criar_rascunho(auth_client, user)
        nova = criar_rascunho(auth_client, user)

        antiga.save()  # `auto_now` toca updated_at

        cards = auth_client.get(HISTORICO).context["cards"]

        assert [c.uuid for c in cards] == [nova.uuid, antiga.uuid]


class TestPaginacao:
    def test_pagina_quando_passa_do_limite(self, auth_client, user):
        from apps.letters.views import POR_PAGINA

        for _ in range(POR_PAGINA + 3):
            criar_rascunho(auth_client, user)

        primeira = auth_client.get(HISTORICO)
        segunda = auth_client.get(HISTORICO, {"page": 2})

        assert len(primeira.context["cards"]) == POR_PAGINA
        assert primeira.context["total"] == POR_PAGINA + 3
        assert segunda.context["pagina"].number == 2
        assert len(segunda.context["cards"]) == 3

    def test_nenhuma_carta_aparece_duas_vezes(self, auth_client, user):
        from apps.letters.views import POR_PAGINA

        for _ in range(POR_PAGINA + 3):
            criar_rascunho(auth_client, user)

        primeira = {c.uuid for c in auth_client.get(HISTORICO).context["cards"]}
        segunda = {c.uuid for c in auth_client.get(HISTORICO, {"page": 2}).context["cards"]}

        assert not primeira & segunda
        assert len(primeira | segunda) == POR_PAGINA + 3

    def test_pagina_invalida_nao_quebra(self, auth_client, user):
        """Querystring é entrada do cliente: lixo cai na primeira página."""
        criar_rascunho(auth_client, user)

        assert auth_client.get(HISTORICO, {"page": "abc"}).status_code == 200
        assert auth_client.get(HISTORICO, {"page": "999"}).status_code == 200

    def test_sem_paginacao_quando_cabe_tudo(self, auth_client, user):
        criar_rascunho(auth_client, user)

        assert auth_client.get(HISTORICO).context["pagina"].has_other_pages() is False


# ===========================================================================
# Isolamento entre pessoas
# ===========================================================================


class TestIsolamento:
    def test_nao_mostra_carta_de_outra_pessoa(self, auth_client, user, client, other_user):
        minha = finalizar(auth_client, user)
        client.force_login(other_user)

        corpo = client.get(HISTORICO).content.decode()

        assert str(minha.uuid) not in corpo
        assert minha.data["guest_name"] not in corpo

    def test_nem_quem_supervisiona_ve_carta_alheia_aqui(
        self, auth_client, user, client, other_user, permissao_ver_todas
    ):
        """
        `letters.view_all_letters` serve à supervisão, no Backoffice.
        Esta é a área PESSOAL -- e nela cada um vê só as suas.
        """
        minha = finalizar(auth_client, user)
        other_user.user_permissions.add(permissao_ver_todas)
        client.force_login(other_user)

        contexto = client.get(HISTORICO).context

        assert contexto["total"] == 0
        assert str(minha.uuid) not in client.get(HISTORICO).content.decode()


# ===========================================================================
# A data exibida
# ===========================================================================


class TestDataDeCriacao:
    def test_o_painel_mostra_a_data_de_criacao(self, auth_client, user):
        """
        Era `updated_at`: numa carta reeditada, a data mudava. O que a
        pessoa procura é quando ela fez a carta.
        """
        carta = finalizar(auth_client, user)
        Letter.objects.filter(pk=carta.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=40)
        )
        carta.refresh_from_db()

        corpo = auth_client.get(DASHBOARD).content.decode()

        # `timezone.localtime`: o template mostra a data no fuso do
        # projeto (Europe/Brussels) e `created_at` esta em UTC. Comparar
        # com o UTC cru só funciona parte do dia -- entre 22h e meia-noite
        # UTC as duas datas divergem, e o teste falhava conforme a hora
        # em que a suíte rodasse.
        local = timezone.localtime(carta.created_at)
        assert local.strftime("%d/%m/%Y") in corpo
        assert timezone.localtime(carta.updated_at).strftime("%d/%m/%Y") not in corpo

    def test_o_historico_mostra_a_data_de_criacao(self, auth_client, user):
        carta = finalizar(auth_client, user)
        Letter.objects.filter(pk=carta.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=40)
        )
        carta.refresh_from_db()

        corpo = auth_client.get(HISTORICO).content.decode()

        # A data exibida e a LOCAL -- ver o teste do painel, acima.
        assert timezone.localtime(carta.created_at).strftime("%d/%m/%Y") in corpo

    def test_o_rotulo_da_coluna_diz_criada_em(self, auth_client, user):
        criar_rascunho(auth_client, user)

        assert "Criada em" in auth_client.get(DASHBOARD).content.decode()


# ===========================================================================
# Baixar o PDF
# ===========================================================================


class TestBaixarPdf:
    def test_a_rota_de_download_manda_anexar(self, auth_client, user):
        carta = finalizar(auth_client, user)

        resposta = auth_client.get(reverse("letters:pdf_download", args=[carta.uuid]))

        assert resposta.status_code == 200
        assert resposta["Content-Type"] == "application/pdf"
        assert resposta["Content-Disposition"].startswith("attachment")
        assert f"{carta.reference}.pdf" in resposta["Content-Disposition"]

    def test_ver_pdf_continua_exibindo_sem_baixar(self, auth_client, user):
        carta = finalizar(auth_client, user)

        resposta = auth_client.get(reverse("letters:pdf", args=[carta.uuid]))

        assert resposta["Content-Disposition"].startswith("inline")

    def test_os_dois_entregam_o_mesmo_arquivo(self, auth_client, user):
        carta = finalizar(auth_client, user)

        ver = auth_client.get(reverse("letters:pdf", args=[carta.uuid]))
        baixar = auth_client.get(reverse("letters:pdf_download", args=[carta.uuid]))

        assert b"".join(ver.streaming_content) == b"".join(baixar.streaming_content)

    def test_o_download_respeita_a_expiracao(self, auth_client, user):
        """A rota nova passa pelas MESMAS guardas -- é a mesma view."""
        carta = expirar(finalizar(auth_client, user))

        resposta = auth_client.get(
            reverse("letters:pdf_download", args=[carta.uuid]), follow=True
        )

        assert "expirou" in resposta.content.decode()

    def test_o_download_respeita_a_propriedade(self, auth_client, user, client, other_user):
        carta = finalizar(auth_client, user)
        client.force_login(other_user)

        resposta = client.get(reverse("letters:pdf_download", args=[carta.uuid]))

        assert resposta.status_code == 404

    def test_o_download_exige_login(self, client, auth_client, user):
        carta = finalizar(auth_client, user)
        client.logout()

        resposta = client.get(reverse("letters:pdf_download", args=[carta.uuid]))

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url


# ===========================================================================
# As ações em cada tela
# ===========================================================================


class TestAcoes:
    def test_o_detalhe_oferece_as_cinco_acoes(self, auth_client, user):
        carta = finalizar(auth_client, user)

        corpo = auth_client.get(reverse("letters:detail", args=[carta.uuid])).content.decode()

        assert reverse("letters:pdf", args=[carta.uuid]) in corpo
        assert reverse("letters:pdf_download", args=[carta.uuid]) in corpo
        assert "js-print-pdf" in corpo
        assert "js-share-pdf" in corpo
        assert "js-share-whatsapp" in corpo

    def test_as_listas_ficam_compactas(self, auth_client, user):
        """
        Painel e histórico mostram Ver PDF e Editar; baixar, imprimir e
        compartilhar ficam no detalhe -- cinco botões por linha viram
        ruído.
        """
        carta = finalizar(auth_client, user)

        painel = auth_client.get(DASHBOARD).content.decode()
        historico = auth_client.get(HISTORICO).content.decode()

        for corpo in (painel, historico):
            assert reverse("letters:pdf", args=[carta.uuid]) in corpo
            assert "js-share-whatsapp" not in corpo

    def test_rascunho_oferece_continuar_nas_tres_telas(self, auth_client, user):
        rascunho = criar_rascunho(auth_client, user)
        card = presentation.build_card(rascunho)
        url = reverse("letters:step", args=[rascunho.uuid, card.resume_step])

        painel = auth_client.get(DASHBOARD).content.decode()
        historico = auth_client.get(HISTORICO).content.decode()
        detalhe = auth_client.get(
            reverse("letters:detail", args=[rascunho.uuid])
        ).content.decode()

        for corpo in (painel, historico, detalhe):
            assert "Continuar" in corpo
            assert url in corpo

    def test_rascunho_nao_oferece_pdf(self, auth_client, user):
        rascunho = criar_rascunho(auth_client, user)

        corpo = auth_client.get(HISTORICO).content.decode()

        assert reverse("letters:pdf", args=[rascunho.uuid]) not in corpo

    def test_expirada_nao_oferece_nem_ver_nem_baixar(self, auth_client, user):
        carta = expirar(finalizar(auth_client, user))

        historico = auth_client.get(HISTORICO).content.decode()
        detalhe = auth_client.get(
            reverse("letters:detail", args=[carta.uuid])
        ).content.decode()

        for corpo in (historico, detalhe):
            assert reverse("letters:pdf", args=[carta.uuid]) not in corpo
            assert reverse("letters:pdf_download", args=[carta.uuid]) not in corpo

    def test_o_painel_aponta_para_o_historico_quando_ha_mais(self, auth_client, user):
        for _ in range(presentation.RECENT_LIMIT + 1):
            criar_rascunho(auth_client, user)

        corpo = auth_client.get(DASHBOARD).content.decode()

        # `/letters/` é prefixo de `/letters/new/`: sem o `href=` o teste
        # passaria pelo botão de criar carta e não provaria nada.
        assert f'href="{HISTORICO}"' in corpo
        assert "Ver todas" in corpo

    def test_o_painel_nao_aponta_quando_tudo_cabe(self, auth_client, user):
        criar_rascunho(auth_client, user)

        corpo = auth_client.get(DASHBOARD).content.decode()

        assert "Ver todas" not in corpo

    def test_o_menu_leva_ao_historico(self, auth_client, user):
        """O histórico tem de ser alcançável sem passar pelo painel."""
        corpo = auth_client.get(DASHBOARD).content.decode()

        assert f'href="{HISTORICO}"' in corpo
        assert "Minhas cartas" in corpo


# ===========================================================================
# O JavaScript de imprimir, compartilhar e WhatsApp
# ===========================================================================


class TestJavaScript:
    """
    O comportamento fica no navegador, mas o CONTRATO entre o template e
    o script é conferível aqui: as classes que o script escuta, os
    `data-*` que ele lê, e o fato de que sem JavaScript os links ainda
    levam ao PDF.
    """

    @pytest.fixture
    def corpo(self, auth_client, user):
        carta = finalizar(auth_client, user)
        return auth_client.get(
            reverse("letters:detail", args=[carta.uuid])
        ).content.decode(), carta

    def test_o_botao_imprimir_carrega_a_url_do_pdf(self, corpo):
        html, carta = corpo
        url = reverse("letters:pdf", args=[carta.uuid])

        # O gancho e a URL, e nao a lista inteira de classes: na tela
        # da carta o mesmo botao ganha a cápsula só-ícone da referência
        # (`done-acao-icone`).
        assert "js-print-pdf" in html
        assert f'href="{url}"' in html
        assert f'data-pdf-url="{url}"' in html

    def test_os_botoes_de_compartilhar_tem_os_dados_que_o_script_le(self, corpo):
        html, carta = corpo

        for classe in ("js-share-pdf", "js-share-whatsapp"):
            assert classe in html
        assert f'data-filename="{carta.reference}.pdf"' in html
        assert "data-text=" in html
        assert f'data-download-url="{reverse("letters:pdf_download", args=[carta.uuid])}"' in html

    def test_os_botoes_tem_onde_avisar_que_baixaram(self, corpo):
        """
        No caminho alternativo o arquivo baixa em vez de abrir a folha de
        compartilhamento. Sem aviso, o clique parece não ter feito nada
        -- o script troca o texto do botão, e para isso precisa do
        `js-rotulo` e do `data-aviso`.
        """
        html, _carta = corpo

        assert html.count('<span class="js-rotulo">') == 2
        assert html.count("data-aviso=") == 2
        assert "anexe" in html

    def test_sem_javascript_os_botoes_ainda_levam_ao_pdf(self, corpo):
        """
        Melhoria progressiva: o `href` dos dois aponta para a rota de
        download. Sem JavaScript, clicar baixa o arquivo -- que é o que a
        pessoa queria enviar de todo jeito.
        """
        html, carta = corpo
        baixar = reverse("letters:pdf_download", args=[carta.uuid])

        for classe in ("js-share-pdf", "js-share-whatsapp"):
            trecho = html[html.index(classe) - 200 : html.index(classe) + 400]
            assert f'href="{baixar}"' in trecho

    def test_o_script_escuta_as_tres_classes(self):
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        script = (raiz / "static" / "js" / "app.js").read_text(encoding="utf-8")

        for classe in (".js-print-pdf", ".js-share-pdf", ".js-share-whatsapp"):
            assert f'closest("{classe}")' in script

    def test_o_script_busca_o_pdf_com_a_sessao(self):
        """
        O PDF é privado: sem `credentials`, o `fetch` viria sem cookie e
        o servidor responderia com a tela de login em vez do arquivo.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        script = (raiz / "static" / "js" / "app.js").read_text(encoding="utf-8")

        assert 'credentials: "same-origin"' in script

    def test_o_script_decide_o_caminho_antes_de_ir_ao_servidor(self):
        """
        O bloqueador de pop-up só deixa `window.open` passar enquanto o
        clique ainda vale, e esse gesto não sobrevive a uma ida ao
        servidor. Por isso a pergunta "este navegador compartilha
        arquivo?" vem ANTES do `fetch` do PDF: invertendo os dois, o
        WhatsApp deixaria de abrir em todo navegador sem Web Share.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        script = (raiz / "static" / "js" / "app.js").read_text(encoding="utf-8")

        inicio = script.index("function compartilhar(")
        corpo = script[inicio : script.index("document.addEventListener", inicio)]

        assert corpo.index("aceitaCompartilharPdf()") < corpo.index("pdfComoArquivo(")

    def test_o_script_nao_inventa_link_publico_para_a_carta(self):
        """
        Compartilhar manda o ARQUIVO. Mandar a URL da carta não serviria
        de nada: ela exige login, e quem recebesse cairia na tela de
        entrar.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        script = (raiz / "static" / "js" / "app.js").read_text(encoding="utf-8")

        assert "navigator.share({ url" not in script
        assert "url: window.location" not in script
