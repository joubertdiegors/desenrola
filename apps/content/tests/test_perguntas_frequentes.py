"""
A seção de Perguntas frequentes: na Home e no Backoffice.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a quantidade de perguntas seja fixa.** Foi o pedido explícito:
   uma, cinco ou quinze, todas saem na página. Acrescentar, remover,
   ativar e reordenar tem de funcionar de verdade, pelo produto;
2. **Que a sanfona dependa de JavaScript.** É `<details>`/`<summary>`
   nativo: com o JavaScript desligado ela continua abrindo, e o teclado
   e o leitor de tela continuam funcionando -- porque nunca deixaram de
   funcionar;
3. **Que a seção apareça vazia.** Sem pergunta ativa, some inteira, e o
   item `#faq` do menu some junto;
4. **Que o botão de contato apareça sem endereço.** Sem e-mail em
   Sistema, `mailto:` não abriria nada;
5. **Que a resposta digitada vire HTML na página.** Texto simples,
   escapado, com quebras de linha respeitadas;
6. **Que apagar uma pergunta não avise que a resposta vai junto.**
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.content.models import FaqItem, PageSection, SiteSettings

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")
NOVA = reverse("backoffice:faq_item_new")


def _com_permissoes(*codenames, email="editora@mail.com"):
    """Uma pessoa do Backoffice com exatamente as permissões pedidas."""
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
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


@pytest.fixture
def cliente_leitora(db):
    """Quem só pode VER a Central -- não pode gravar nada."""
    c = Client()
    c.force_login(_com_permissoes("view_pagesection", email="leitora@mail.com"))
    return c


def criar(quantas=1, **extras):
    itens = []
    for numero in range(1, quantas + 1):
        itens.append(
            FaqItem.objects.create(
                question=f"Pergunta {numero}?",
                answer=f"Resposta {numero}.",
                order=numero,
                **extras,
            )
        )
    return itens


def area(client):
    html = client.get(HOME).content.decode()
    return html[html.index("<main") : html.index("</main>")]


def secao(client):
    html = area(client)
    if 'id="faq"' not in html:
        return ""
    inicio = html.index('id="faq"')
    return html[inicio : html.index("</section>", inicio)]


def url_do_editor():
    parte = PageSection.objects.get(page__key="home", key="faq")
    return reverse("backoffice:content_section", args=[parte.pk])


# ===========================================================================
# 1. A quantidade não é fixa
# ===========================================================================


class TestQuantidadeLivre:
    @pytest.mark.parametrize("quantas", (1, 2, 3, 5, 12))
    def test_desenha_todas_as_cadastradas(self, client, quantas):
        criar(quantas)

        assert secao(client).count("<details") == quantas

    def test_a_ordem_e_a_cadastrada(self, client):
        FaqItem.objects.create(question="Segunda?", answer="B.", order=2)
        FaqItem.objects.create(question="Primeira?", answer="A.", order=1)

        html = secao(client)

        assert html.index("Primeira?") < html.index("Segunda?")

    def test_a_desativada_nao_aparece(self, client):
        criar(2)
        FaqItem.objects.filter(question="Pergunta 2?").update(is_active=False)

        html = secao(client)

        assert "Pergunta 1?" in html
        assert "Pergunta 2?" not in html

    def test_a_desativada_continua_cadastrada(self, client):
        """Desativar não é apagar."""
        criar(1)
        FaqItem.objects.all().update(is_active=False)

        client.get(HOME)

        assert FaqItem.objects.count() == 1


# ===========================================================================
# 2. Sem pergunta, a seção inteira some
# ===========================================================================


class TestSemPergunta:
    def test_a_secao_nao_aparece(self, client):
        assert 'id="faq"' not in area(client)

    def test_nem_o_titulo_sozinho(self, client):
        assert "faq-lista" not in area(client)

    def test_o_item_do_menu_some_junto(self, client):
        from apps.content.models import MenuItem

        MenuItem.objects.create(label="Dúvidas", destination="#faq", order=9)

        assert 'href="#faq"' not in client.get(HOME).content.decode()

    def test_com_pergunta_o_item_do_menu_volta(self, client):
        from apps.content.models import MenuItem

        MenuItem.objects.create(label="Dúvidas", destination="#faq", order=9)
        criar(1)

        assert 'href="#faq"' in client.get(HOME).content.decode()

    def test_a_secao_desativada_tambem_tira_o_item_do_menu(self, client):
        from apps.content.models import MenuItem

        MenuItem.objects.create(label="Dúvidas", destination="#faq", order=9)
        criar(1)
        PageSection.objects.filter(page__key="home", key="faq").update(is_active=False)

        assert 'href="#faq"' not in client.get(HOME).content.decode()


# ===========================================================================
# 3. A sanfona funciona sem JavaScript
# ===========================================================================


class TestSanfonaNativa:
    def test_usa_details_e_summary(self, client):
        criar(1)

        html = secao(client)

        assert "<details" in html
        assert "<summary" in html

    def test_uma_aberta_de_cada_vez(self, client):
        """`name` é o que o navegador usa para fechar as outras."""
        criar(3)

        assert secao(client).count('name="faq"') == 3

    def test_nao_ha_javascript_na_secao(self, client):
        criar(2)

        html = secao(client)

        assert "<script" not in html
        assert "onclick" not in html

    def test_a_pergunta_e_a_resposta_ficam_dentro_do_details(self, client):
        criar(1)

        html = secao(client)
        bloco = html[html.index("<details") : html.index("</details>")]

        assert "Pergunta 1?" in bloco
        assert "Resposta 1." in bloco

    def test_o_sinal_nao_e_lido_por_leitor_de_tela(self, client):
        """O "+" é decoração: quem lê a tela já sabe que é uma sanfona."""
        criar(1)

        assert '<span class="faq-sinal" aria-hidden="true"></span>' in secao(client)


# ===========================================================================
# 4. O bloco de contato
# ===========================================================================


class TestBlocoDeContato:
    def _com_email(self, endereco="suporte@exemplo.test"):
        config = SiteSettings.load()
        config.contact_email = endereco
        config.save(update_fields=["contact_email"])

    def test_sem_email_cadastrado_o_bloco_nao_aparece(self, client):
        criar(1)

        assert "faq-contato" not in secao(client)

    def test_com_email_o_bloco_aparece_com_mailto(self, client):
        criar(1)
        self._com_email()

        html = secao(client)

        assert "faq-contato" in html
        assert 'href="mailto:suporte@exemplo.test"' in html

    def test_o_bloco_fica_depois_das_perguntas_no_html(self, client):
        """
        A ordem do HTML é a do celular (desenho 2a). No desktop a grade
        o traz de volta para a coluna da esquerda, por área nomeada.
        """
        criar(1)
        self._com_email()

        html = secao(client)

        assert html.index("faq-lista") < html.index("faq-contato")

    def test_sem_titulo_o_bloco_nao_aparece(self, client):
        from apps.content.models import PageSectionTranslation

        criar(1)
        self._com_email()
        traducao = PageSectionTranslation.objects.get(
            section__page__key="home", section__key="faq", language="pt"
        )
        traducao.content = {**traducao.content, "cta_title": ""}
        traducao.save(update_fields=["content"])

        assert "faq-contato" not in secao(client)


# ===========================================================================
# 5. A resposta é texto, não HTML
# ===========================================================================


class TestRespostaEscapada:
    def test_html_digitado_sai_escapado(self, client):
        FaqItem.objects.create(
            question="E isto?", answer="<script>alert(1)</script>", order=1
        )

        html = secao(client)

        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_a_quebra_de_linha_vira_paragrafo(self, client):
        FaqItem.objects.create(
            question="Dois parágrafos?", answer="Primeiro.\n\nSegundo.", order=1
        )

        html = secao(client)

        assert html.count("<p>") >= 2


# ===========================================================================
# 6. O cadastro no Backoffice
# ===========================================================================


class TestCadastroNoBackoffice:
    def test_a_secao_tem_cadastro_proprio_no_editor(self, cliente):
        html = cliente.get(url_do_editor()).content.decode()

        assert "As perguntas" in html
        assert reverse("backoffice:faq_item_new") in html

    def test_acrescentar(self, cliente):
        resposta = cliente.post(
            NOVA,
            {"question": "Quanto custa?", "answer": "Depende do plano.", "order": 1},
        )

        assert resposta.status_code == 302
        assert FaqItem.objects.filter(question="Quanto custa?").exists()

    def test_editar(self, cliente):
        pergunta = criar(1)[0]
        cliente.post(
            reverse("backoffice:faq_item_edit", args=[pergunta.pk]),
            {"question": "Nova pergunta?", "answer": "Nova resposta.", "order": 1},
        )

        pergunta.refresh_from_db()
        assert pergunta.question == "Nova pergunta?"

    def test_desativar(self, cliente):
        pergunta = criar(1)[0]
        cliente.post(
            reverse("backoffice:faq_item_activation", args=[pergunta.pk]), {"ativo": "0"}
        )

        pergunta.refresh_from_db()
        assert pergunta.is_active is False

    def test_reativar(self, cliente):
        pergunta = criar(1, is_active=False)[0]
        cliente.post(
            reverse("backoffice:faq_item_activation", args=[pergunta.pk]), {"ativo": "1"}
        )

        pergunta.refresh_from_db()
        assert pergunta.is_active is True

    def test_reordenar_muda_a_ordem_de_verdade(self, cliente):
        """
        `order` nasce empatado: trocar dois números não moveria ninguém.
        O que vale é a POSIÇÃO depois da ação.
        """
        FaqItem.objects.create(question="A?", answer="a", order=0)
        segunda = FaqItem.objects.create(question="B?", answer="b", order=0)
        cliente.post(
            reverse("backoffice:faq_item_move", args=[segunda.pk]), {"direcao": "subir"}
        )

        assert [p.question for p in FaqItem.objects.all()] == ["B?", "A?"]

    def test_descer_move_para_baixo(self, cliente):
        primeira = FaqItem.objects.create(question="A?", answer="a", order=0)
        FaqItem.objects.create(question="B?", answer="b", order=0)
        cliente.post(
            reverse("backoffice:faq_item_move", args=[primeira.pk]), {"direcao": "descer"}
        )

        assert [p.question for p in FaqItem.objects.all()] == ["B?", "A?"]

    def test_apagar_pede_confirmacao_e_mostra_a_resposta(self, cliente):
        pergunta = FaqItem.objects.create(
            question="Some?", answer="Esta resposta some junto.", order=1
        )
        html = cliente.get(
            reverse("backoffice:faq_item_delete", args=[pergunta.pk])
        ).content.decode()

        assert FaqItem.objects.count() == 1
        assert "Esta resposta some junto." in html

    def test_apagar_de_verdade(self, cliente):
        pergunta = criar(1)[0]
        cliente.post(reverse("backoffice:faq_item_delete", args=[pergunta.pk]))

        assert FaqItem.objects.count() == 0

    def test_pergunta_sem_resposta_e_recusada(self, cliente):
        cliente.post(NOVA, {"question": "Só a pergunta?", "answer": "  ", "order": 1})

        assert FaqItem.objects.count() == 0

    def test_resposta_sem_pergunta_e_recusada(self, cliente):
        cliente.post(NOVA, {"question": "   ", "answer": "Só a resposta.", "order": 1})

        assert FaqItem.objects.count() == 0


# ===========================================================================
# 7. Quem não pode, não faz
# ===========================================================================


class TestPermissao:
    ACOES = ("faq_item_activation", "faq_item_move", "faq_item_delete")

    def test_visitante_nao_abre_a_tela(self, client):
        resposta = client.get(NOVA)

        assert resposta.status_code in (302, 403)

    def test_usuario_comum_nao_abre_a_tela(self, auth_client):
        resposta = auth_client.get(NOVA)

        assert resposta.status_code in (302, 403)

    @pytest.mark.parametrize("acao", ACOES)
    def test_usuario_comum_nao_executa_acao(self, auth_client, acao):
        pergunta = criar(1)[0]

        resposta = auth_client.post(reverse(f"backoffice:{acao}", args=[pergunta.pk]))

        assert resposta.status_code in (302, 403)
        assert FaqItem.objects.filter(pk=pergunta.pk, is_active=True).exists()


# ===========================================================================
# 8. A âncora está declarada
# ===========================================================================


class TestAncora:
    def test_faq_e_uma_ancora_conhecida(self):
        from apps.content.services import ANCORAS_DA_HOME

        assert ANCORAS_DA_HOME["#faq"] == "faq"

    def test_o_formulario_do_menu_aceita_faq(self):
        from apps.content.forms import FormularioDeItemDoMenu

        form = FormularioDeItemDoMenu(
            {"label": "Dúvidas", "destination": "#faq", "is_active": True, "order": 1}
        )

        assert form.is_valid(), form.errors

    def test_a_secao_desenha_o_id_da_ancora(self, client):
        criar(1)

        assert 'id="faq"' in area(client)


class TestSoVer:
    """
    Quem tem `view_pagesection` mas não `change_pagesection` abre a tela
    e não grava nada. A checagem é no servidor, não no botão.
    """

    def test_abre_a_tela_de_edicao(self, cliente_leitora):
        pergunta = criar(1)[0]

        resposta = cliente_leitora.get(
            reverse("backoffice:faq_item_edit", args=[pergunta.pk])
        )

        assert resposta.status_code == 200

    def test_nao_grava(self, cliente_leitora):
        pergunta = criar(1)[0]

        resposta = cliente_leitora.post(
            reverse("backoffice:faq_item_edit", args=[pergunta.pk]),
            {"question": "Mudou?", "answer": "Mudou.", "order": 1},
        )

        pergunta.refresh_from_db()
        assert resposta.status_code == 403
        assert pergunta.question == "Pergunta 1?"

    def test_nao_ve_o_botao_de_nova_pergunta(self, cliente_leitora):
        html = cliente_leitora.get(url_do_editor()).content.decode()

        assert reverse("backoffice:faq_item_new") not in html


# ===========================================================================
# 9. A prévia e a lista, na tela de quem administra
# ===========================================================================


class TestNaTelaDeQuemAdministra:
    """
    Os dois defeitos que só a inspeção visual encontrou.

    Nenhum teste de HTTP os pegaria: o primeiro era um `<iframe>`
    apontando para um 404 -- a página em volta respondia 200 e o quadro
    vinha vazio, sem erro nenhum na tela. O segundo era a lista de
    perguntas quebrando LETRA POR LETRA, porque cinco botões de ação
    pediam a largura deles antes de o texto pedir a sua.
    """

    def test_a_previa_da_secao_responde(self, cliente):
        criar(1)
        parte = PageSection.objects.get(page__key="home", key="faq")

        resposta = cliente.get(
            reverse("backoffice:content_preview", args=[parte.pk])
        )

        assert resposta.status_code == 200, "o iframe da prévia apontava para um 404"
        assert "Pergunta 1?" in resposta.content.decode()

    def test_a_previa_da_secao_responde_ao_POST(self, cliente):
        """
        É o POST que o painel usa ENQUANTO SE DIGITA.

        O `GET` desenha o que está salvo; o `POST` desenha o que está na
        tela, sem gravar (ver `backoffice_content_preview`). Guardar só
        o `GET` deixaria metade da prévia sem trava -- e é a metade que
        a pessoa usa o tempo todo.
        """
        criar(1)
        parte = PageSection.objects.get(page__key="home", key="faq")

        resposta = cliente.post(
            reverse("backoffice:content_preview", args=[parte.pk]),
            {"title": "Título ainda não salvo", "lead": "Apoio ainda não salvo"},
        )
        corpo = resposta.content.decode()

        assert resposta.status_code == 200
        assert "Título ainda não salvo" in corpo
        # E o que NÃO foi digitado continua vindo do banco.
        assert "Pergunta 1?" in corpo

    def test_o_POST_da_previa_nao_grava_nada(self, cliente):
        """A prévia mostra; quem grava é o botão de salvar."""
        from apps.content.models import PageSectionTranslation

        criar(1)
        parte = PageSection.objects.get(page__key="home", key="faq")
        antes = PageSectionTranslation.objects.get(section=parte, language="pt").content

        cliente.post(
            reverse("backoffice:content_preview", args=[parte.pk]),
            {"title": "Título ainda não salvo"},
        )

        depois = PageSectionTranslation.objects.get(section=parte, language="pt").content
        assert depois == antes

    @pytest.mark.parametrize("metodo", ("get", "post"))
    def test_TODA_parte_da_home_tem_previa(self, cliente, metodo):
        """
        A regra, e não o caso: uma parte nova sem prévia declarada
        aparece como quadro vazio na Central, e nada avisa.
        """
        for parte in PageSection.objects.filter(page__key="home"):
            resposta = getattr(cliente, metodo)(
                reverse("backoffice:content_preview", args=[parte.pk])
            )

            assert resposta.status_code == 200, f"{parte.key} ({metodo})"

    @pytest.mark.parametrize(
        "largura", ("desktop", "tablet", "mobile", "miniatura", "inventada")
    )
    def test_a_previa_responde_em_toda_largura_pedida(self, cliente, largura):
        """
        As três larguras do painel, mais a da miniatura -- e uma
        inventada, que tem de cair no padrão em vez de derrubar o quadro.
        """
        criar(1)
        parte = PageSection.objects.get(page__key="home", key="faq")

        resposta = cliente.get(
            reverse("backoffice:content_preview", args=[parte.pk]),
            {"viewport": largura},
        )

        assert resposta.status_code == 200

    def test_a_previa_do_faq_nao_e_uma_pagina_paralela(self):
        """
        Ela usa o MESMO parcial que a Home inclui. Uma segunda
        implementação visual envelheceria no primeiro ajuste.
        """
        from apps.content import section_schema

        assert section_schema.PARCIAIS["faq"] == "core/secoes/faq.html"

    def test_quem_nao_pode_nao_ve_a_previa(self, client, auth_client):
        """A prévia é do Backoffice, e cobra a mesma permissão dele."""
        parte = PageSection.objects.get(page__key="home", key="faq")
        endereco = reverse("backoffice:content_preview", args=[parte.pk])

        assert client.get(endereco).status_code in (302, 403)

    def test_a_linha_da_lista_quebra_em_vez_de_espremer_o_texto(self):
        import pathlib

        css = pathlib.Path("static/css/layout.css").read_text(encoding="utf-8")
        onde = css.index(".bo-item-do-menu {")
        bloco = css[onde : onde + 400]

        assert "flex-wrap: wrap" in bloco
        assert "flex: 1 1 240px" in css[onde : onde + 900]

    def test_so_o_destino_do_menu_quebra_letra_por_letra(self):
        """
        `break-all` é para um endereço sem espaços. Numa pergunta, ele
        produz uma coluna de letras.
        """
        import pathlib

        css = pathlib.Path("static/css/layout.css").read_text(encoding="utf-8")
        onde = css.index(".bo-item-do-menu-texto span {")

        assert "word-break: break-all" not in css[onde : onde + 120]
        assert ".bo-item-do-menu-destino { word-break: break-all; }" in css
