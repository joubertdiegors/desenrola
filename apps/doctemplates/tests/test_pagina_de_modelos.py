"""
A tela de Modelos do Backoffice -- a que o arquivo de referencia desenha.

O QUE ESTA SUITE EXISTE PARA IMPEDIR
------------------------------------
1. **Que a tela mostre numero inventado.** Contagem do cabecalho,
   "N ativos" do rodape, elementos, campos do banco, copias e cartas:
   tudo sai do banco, e um numero que ninguem calcula e um numero que
   mente.
2. **Que apareca botao que nao faz nada.** Todo link tem destino real,
   todo formulario tem `action` que resolve, e o que so existe com
   JavaScript (as janelas) e declarado como tal. A referencia traz
   "Excluir" e "Importar": nao existem aqui, e nao viraram enfeite.
3. **Que um filtro minta.** Filtrar por "Ativos" nao pode trazer
   rascunho; filtrar por idioma nao pode trazer outro; e combinar dois
   filtros nao pode perder um deles.
4. **Que a tela abra para quem nao pode.** Ver e administrar sao
   permissoes diferentes -- e quem so ve nao pode enxergar o
   interruptor de ativacao nem o botao de criar.
5. **Que a previa seja uma maquete.** O `<iframe>` recebe o PDF que
   este modelo gera hoje, pelo mesmo renderer das cartas.
"""

import pathlib
import re

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.doctemplates.models import DocumentTemplate, DocumentType
from apps.doctemplates.services import ativacao, biblioteca
from apps.doctemplates.services.duplicacao import duplicar_modelo

pytestmark = pytest.mark.django_db

LISTA = reverse("backoffice:document_library")
SENHA = "senha-de-teste-123"
A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}

LAYOUT = {
    "version": 1,
    "elements": [
        {
            "id": "t1", "type": "text", "x": 50.0, "y": 60.0,
            "width": 400.0, "height": 20.0,
            "properties": {"content": {"kind": "text", "value": "Contrato"}},
        },
        {
            "id": "t2", "type": "text", "x": 50.0, "y": 100.0,
            "width": 400.0, "height": 20.0,
            "properties": {"content": {"kind": "field", "source": "convidado.nome"}},
        },
    ],
}


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


def permissao(app_label, codename):
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def criar_pessoa(email, nome, *codenames):
    User = get_user_model()
    pessoa = User.objects.create_user(email=email, password=SENHA, full_name=nome)
    pessoa.user_permissions.set([permissao(app, code) for app, code in codenames])
    return User.objects.get(pk=pessoa.pk)


@pytest.fixture
def administrador(db):
    return criar_pessoa(
        "admin@desenrola.be", "Ana Martins",
        ("core", "access_backoffice"),
        ("doctemplates", "view_documenttemplate"),
        ("doctemplates", "change_documenttemplate"),
    )


@pytest.fixture
def so_leitor(db):
    return criar_pessoa(
        "leitor@desenrola.be", "Luís Leitor",
        ("core", "access_backoffice"),
        ("doctemplates", "view_documenttemplate"),
    )


@pytest.fixture
def cliente(client, administrador):
    client.force_login(administrador)
    return client


@pytest.fixture
def tipo(db):
    return DocumentType.objects.create(code="contrato", name="Contrato", page=dict(A4))


@pytest.fixture
def oficiais(db):
    _, modelos = biblioteca.semear()
    return {m.language: m for m in modelos}


@pytest.fixture
def pronto(tipo):
    """Ligado e com desenho utilizável: a linha "Ativo"."""
    return DocumentTemplate.objects.create(
        type=tipo, name="Contrato pronto", slug="contrato-pronto", language="fr",
        layout=LAYOUT,
    )


@pytest.fixture
def rascunho(tipo):
    """Ligado e sem desenho: a linha "Rascunho"."""
    return DocumentTemplate.objects.create(
        type=tipo, name="Contrato em obras", slug="contrato-obras", language="pt",
    )


@pytest.fixture
def inativo(tipo):
    return DocumentTemplate.objects.create(
        type=tipo, name="Contrato antigo", slug="contrato-antigo", language="fr",
        layout=LAYOUT, is_active=False,
    )


def corpo(resposta):
    return resposta.content.decode()


def linhas(resposta):
    """Os slugs das linhas desenhadas, na ordem em que aparecem."""
    return [m.slug for m in resposta.context["modelos"]]


# ===========================================================================
# 1. A tela abre e conta o que existe
# ===========================================================================


class TestOCabecalhoEORodape:
    def test_a_tela_abre(self, cliente, oficiais):
        resposta = cliente.get(LISTA)

        assert resposta.status_code == 200
        assert "backoffice/document_library.html" in [
            t.name for t in resposta.templates
        ]

    def test_o_total_e_o_numero_de_modelos_encontrados(
        self, cliente, oficiais, pronto, rascunho, inativo
    ):
        resposta = cliente.get(LISTA)

        assert resposta.context["total"] == DocumentTemplate.objects.count()

    def test_o_total_acompanha_o_filtro(self, cliente, oficiais, pronto, inativo):
        resposta = cliente.get(LISTA, {"situacao": "inativo"})

        assert resposta.context["total"] == len(linhas(resposta))
        assert linhas(resposta) == [inativo.slug]

    def test_ativos_conta_so_os_prontos(self, cliente, oficiais, pronto, rascunho):
        """
        Os oficiais recém-semeados têm desenho mas ainda não têm o logo
        materializado: são rascunho, e não podem entrar na conta de
        "ativos" -- seria a tela dizendo que há documento pronto onde
        não há.
        """
        resposta = cliente.get(LISTA)

        assert resposta.context["ativos"] == 1

    def test_a_ultima_alteracao_e_a_mais_recente(self, cliente, oficiais, pronto):
        resposta = cliente.get(LISTA)

        assert resposta.context["ultima_alteracao"] == max(
            m.updated_at for m in DocumentTemplate.objects.all()
        )

    def test_a_pagina_diz_para_que_serve(self, cliente, oficiais):
        """A descrição do cabeçalho enuncia a regra do ativo único."""
        html = corpo(cliente.get(LISTA))

        assert "Cada idioma usa um modelo por vez" in html


# ===========================================================================
# 2. Cada linha leva dado de verdade
# ===========================================================================


class TestOQueCadaLinhaMostra:
    def test_a_situacao_de_cada_linha_e_a_calculada(
        self, cliente, oficiais, pronto, rascunho, inativo
    ):
        resposta = cliente.get(LISTA)

        por_slug = {m.slug: m.situacao for m in resposta.context["modelos"]}
        assert por_slug[pronto.slug] == ativacao.ATIVO
        assert por_slug[rascunho.slug] == ativacao.RASCUNHO
        assert por_slug[inativo.slug] == ativacao.INATIVO

    def test_as_tres_palavras_aparecem_escritas(
        self, cliente, oficiais, pronto, rascunho, inativo
    ):
        html = corpo(cliente.get(LISTA))

        assert ">Ativo</span>" in html
        assert ">Rascunho</span>" in html
        assert ">Inativo</span>" in html

    def test_elementos_e_campos_saem_do_layout(self, cliente, pronto):
        resposta = cliente.get(LISTA, {"q": pronto.slug})

        linha = resposta.context["modelos"][0]
        assert linha.elementos == 2
        assert linha.campos == 1  # só `convidado.nome` vem do banco

    def test_a_versao_e_a_do_contrato_do_layout(self, cliente, pronto):
        resposta = cliente.get(LISTA, {"q": pronto.slug})

        assert resposta.context["modelos"][0].versao == LAYOUT["version"]

    def test_um_modelo_sem_desenho_nao_oferece_previa(self, cliente, rascunho):
        """O botão de visualizar só existe quando há o que mostrar."""
        resposta = cliente.get(LISTA, {"q": rascunho.slug})

        assert resposta.context["modelos"][0].tem_desenho is False
        assert 'data-abrir="mod-previa"' not in corpo(resposta)

    def test_a_linha_com_desenho_oferece_previa_apontando_para_o_pdf(
        self, cliente, pronto
    ):
        resposta = cliente.get(LISTA, {"q": pronto.slug})

        assert reverse("backoffice:document_preview", args=[pronto.pk]) in corpo(
            resposta
        )

    def test_a_contagem_de_copias_e_de_cartas_vem_anotada(self, cliente, pronto):
        duplicar_modelo(pronto, "Cópia A")
        duplicar_modelo(pronto, "Cópia B")

        resposta = cliente.get(LISTA, {"q": "contrato-pronto"})

        linha = resposta.context["modelos"][0]
        assert linha.copias == 2
        assert linha.cartas == 0

    def test_a_data_relativa_e_escrita_em_palavras(self, cliente, pronto):
        resposta = cliente.get(LISTA, {"q": pronto.slug})

        assert resposta.context["modelos"][0].relativo == "hoje"


# ===========================================================================
# 3. Os filtros
# ===========================================================================


class TestFiltros:
    def test_busca_por_nome(self, cliente, oficiais, pronto, rascunho):
        resposta = cliente.get(LISTA, {"q": "em obras"})

        assert linhas(resposta) == [rascunho.slug]

    def test_busca_por_identificador(self, cliente, oficiais, pronto):
        resposta = cliente.get(LISTA, {"q": "contrato-pronto"})

        assert linhas(resposta) == [pronto.slug]

    def test_busca_sem_resultado_mostra_o_estado_vazio(self, cliente, oficiais):
        resposta = cliente.get(LISTA, {"q": "isto-nao-existe"})

        assert linhas(resposta) == []
        assert "Nenhum modelo corresponde aos filtros" in corpo(resposta)

    @pytest.mark.parametrize(
        ("situacao", "esperado"),
        [("ativo", "pronto"), ("rascunho", "rascunho"), ("inativo", "inativo")],
    )
    def test_cada_situacao_traz_so_a_sua(
        self, cliente, pronto, rascunho, inativo, situacao, esperado
    ):
        esperados = {"pronto": pronto, "rascunho": rascunho, "inativo": inativo}

        resposta = cliente.get(LISTA, {"situacao": situacao})

        assert esperados[esperado].slug in linhas(resposta)
        for chave, modelo in esperados.items():
            if chave != esperado:
                assert modelo.slug not in linhas(resposta)

    def test_situacao_desconhecida_nao_filtra_nada(self, cliente, pronto, inativo):
        """Um valor inventado na URL não pode esvaziar a tela sem explicar."""
        resposta = cliente.get(LISTA, {"situacao": "lixo"})

        assert {pronto.slug, inativo.slug} <= set(linhas(resposta))
        assert resposta.context["filtros"]["situacao"] == ""

    def test_filtro_por_idioma(self, cliente, oficiais, pronto, rascunho):
        resposta = cliente.get(LISTA, {"language": "pt"})

        assert all(
            m.language == "pt" for m in resposta.context["modelos"]
        )
        assert rascunho.slug in linhas(resposta)

    def test_filtro_por_natureza(self, cliente, oficiais, pronto):
        oficiais_vistos = cliente.get(LISTA, {"system": "1"})
        comuns = cliente.get(LISTA, {"system": "0"})

        assert all(m.is_system for m in oficiais_vistos.context["modelos"])
        assert pronto.slug in linhas(comuns)
        assert pronto.slug not in linhas(oficiais_vistos)

    def test_dois_filtros_combinam(self, cliente, oficiais, pronto, inativo):
        resposta = cliente.get(LISTA, {"language": "fr", "situacao": "inativo"})

        assert linhas(resposta) == [inativo.slug]

    def test_buscar_preserva_o_filtro_que_ja_estava(self, cliente, pronto, inativo):
        """A busca é o único formulário: ela leva os demais escondidos."""
        html = corpo(cliente.get(LISTA, {"situacao": "inativo"}))

        assert '<input type="hidden" name="situacao" value="inativo">' in html

    def test_cada_link_de_filtro_preserva_os_outros(self, cliente, pronto):
        resposta = cliente.get(LISTA, {"language": "fr", "q": "contrato"})

        for opcao in resposta.context["filtros_situacao"]:
            assert "language=fr" in opcao["url"]
            assert "q=contrato" in opcao["url"]

    def test_trocar_de_filtro_volta_para_a_primeira_pagina(self, cliente, pronto):
        resposta = cliente.get(LISTA, {"page": "2"})

        for opcao in resposta.context["filtros_situacao"]:
            assert "page=" not in opcao["url"]

    def test_limpar_filtros_aparece_so_quando_ha_filtro(self, cliente, pronto):
        sem = cliente.get(LISTA)
        com = cliente.get(LISTA, {"language": "fr"})

        assert sem.context["tem_filtro"] is False
        assert com.context["tem_filtro"] is True
        assert "Limpar filtros" not in corpo(sem)
        assert "Limpar filtros" in corpo(com)

    def test_a_pilula_mostra_o_valor_em_vigor(self, cliente, pronto):
        resposta = cliente.get(LISTA, {"language": "fr"})

        rotulos = dict(DocumentTemplate._meta.get_field("language").choices)
        idioma = resposta.context["filtros_pilula"][0]
        assert idioma["escolhido"] is True
        assert idioma["atual"] == str(rotulos["fr"])

    def test_a_pilula_sem_escolha_mostra_o_padrao(self, cliente, pronto):
        resposta = cliente.get(LISTA)

        idioma = resposta.context["filtros_pilula"][0]
        assert idioma["escolhido"] is False
        assert idioma["atual"] == "Todos"


# ===========================================================================
# 4. Nada de botao que nao faz nada
# ===========================================================================


class TestNadaDeEnfeite:
    def test_todo_link_tem_destino(self, cliente, oficiais, pronto, rascunho):
        """
        `href="#"` só é aceito onde o JavaScript preenche o destino ao
        abrir a janela (`data-campo-href`) -- e esses estão dentro de
        `<dialog>`, que sem JavaScript nem abre.
        """
        html = corpo(cliente.get(LISTA))

        vazios = [
            trecho
            for trecho in re.findall(r"<a\b[^>]*>", html)
            if re.search(r'href="(#|)"', trecho) and "data-campo-href" not in trecho
        ]
        assert vazios == []

    def test_todo_formulario_posta_para_uma_rota_de_verdade(
        self, cliente, oficiais, pronto
    ):
        html = corpo(cliente.get(LISTA))

        acoes = re.findall(r'<form\b[^>]*action="([^"]*)"', html)
        assert acoes, "a tela tem formulários"
        assert all(acao.startswith("/") for acao in acoes)

    def test_todo_formulario_leva_csrf(self, cliente, oficiais, pronto):
        html = corpo(cliente.get(LISTA))

        for formulario in re.findall(r"<form\b.*?</form>", html, re.S):
            if 'method="post"' in formulario:
                assert "csrfmiddlewaretoken" in formulario

    def test_a_tela_nao_oferece_excluir_nem_importar(self, cliente, oficiais, pronto):
        """
        A referência traz os dois. Não existem na arquitetura: um modelo
        com cartas é protegido contra apagamento, e importar não é
        funcionalidade do produto. Botão que não faz nada é pior do que
        botão nenhum.
        """
        html = corpo(cliente.get(LISTA))

        assert "Excluir" not in html
        assert "Importar" not in html

    def test_a_janela_de_detalhes_avisa_que_nao_ha_historico_por_pessoa(
        self, cliente, pronto
    ):
        html = corpo(cliente.get(LISTA))

        assert "Um histórico alteração por alteração ainda não existe." in html

    def test_novo_modelo_aponta_para_a_duplicacao_de_uma_base_real(
        self, cliente, oficiais
    ):
        """
        Criar é copiar um modelo que já funciona: o formulário já nasce
        apontando para a rota de duplicação, com ou sem JavaScript.
        """
        resposta = cliente.get(LISTA)

        bases = resposta.context["bases"]
        assert bases, "há modelos oficiais para servir de base"
        assert reverse(
            "backoffice:document_library_duplicate", args=[bases[0].pk]
        ) in corpo(resposta)

    def test_nenhum_link_nasce_apontando_para_lugar_nenhum(
        self, cliente, oficiais, pronto
    ):
        """
        A mesma regra da auditoria funcional do projeto, aqui do lado
        para falhar primeiro nesta tela: `href="#"`, `href=""` e
        `onclick` sao as tres formas de parecer que faz algo sem fazer.
        As ancoras que o JavaScript preenche ao abrir a janela nascem
        SEM `href` -- sem `href` um `<a>` nao e link nem recebe foco --
        e so viram link quando tem destino.
        """
        html = corpo(cliente.get(LISTA))

        assert 'href="#"' not in html
        assert 'href=""' not in html
        assert "onclick=" not in html
        for ancora in re.findall(r"<a[^>]*data-campo-href[^>]*>", html):
            assert "href=" not in ancora

    def test_o_que_nasce_escondido_fica_escondido(self, cliente, pronto):
        """
        `hidden` so esconde se a folha de estilo deixar: as pilulas e os
        botoes declaram `display: inline-flex`, que ganha do `[hidden]`
        do navegador. Sem a regra, a pilula "Oficial" apareceria em
        modelo que nao e oficial -- a janela mentindo.
        """
        folha = (
            pathlib.Path(settings.BASE_DIR) / "static" / "css" / "biblioteca-modelos.css"
        ).read_text(encoding="utf-8")

        assert "[hidden]" in folha
        assert 'data-campo="oficial" hidden' in corpo(cliente.get(LISTA))

    def test_o_javascript_da_tela_e_carregado(self, cliente, pronto):
        assert "js/biblioteca-modelos.js" in corpo(cliente.get(LISTA))


# ===========================================================================
# 5. Quem ve, quem administra, quem nao entra
# ===========================================================================


class TestPermissoes:
    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(LISTA)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_usuario_comum_e_recusado(self, client, db):
        client.force_login(criar_pessoa("ze@exemplo.be", "Zé"))

        assert client.get(LISTA).status_code == 403

    def test_quem_so_ve_entra(self, client, so_leitor, pronto):
        client.force_login(so_leitor)

        assert client.get(LISTA).status_code == 200

    def test_quem_so_ve_nao_enxerga_o_interruptor(self, client, so_leitor, pronto):
        client.force_login(so_leitor)

        html = corpo(client.get(LISTA))

        assert "Ativar para este idioma" not in html
        assert "Desativar" not in html
        assert "Novo modelo" not in html
        assert reverse("backoffice:document_library_activation", args=[pronto.pk]) not in html

    def test_quem_administra_enxerga(self, cliente, pronto):
        html = corpo(cliente.get(LISTA))

        assert "Novo modelo" in html
        assert reverse("backoffice:document_library_activation", args=[pronto.pk]) in html

    def test_o_interruptor_de_cada_linha_propoe_o_oposto(
        self, cliente, pronto, inativo
    ):
        html = corpo(cliente.get(LISTA))

        assert "Desativar" in html  # para o ativo
        assert "Ativar para este idioma" in html  # para o inativo


# ===========================================================================
# 6. A previa e o documento de verdade
# ===========================================================================


class TestPrevia:
    def url(self, modelo):
        return reverse("backoffice:document_preview", args=[modelo.pk])

    def test_devolve_um_pdf(self, cliente, pronto):
        resposta = cliente.get(self.url(pronto))

        assert resposta.status_code == 200
        assert resposta["Content-Type"] == "application/pdf"
        assert resposta.content[:5] == b"%PDF-"

    def test_o_arquivo_e_mostrado_no_lugar_e_nao_baixado(self, cliente, pronto):
        resposta = cliente.get(self.url(pronto))

        assert resposta["Content-Disposition"].startswith("inline;")

    def test_o_documento_pode_ser_enquadrado_pela_propria_tela(self, cliente, pronto):
        """
        A janela mostra o PDF num `<iframe>` da própria página. Com o
        `X-Frame-Options: DENY` do resto do site, o navegador recusa
        desenhar o quadro e a janela abre vazia -- botão que abre nada.
        SAMEORIGIN libera só a própria aplicação.
        """
        resposta = cliente.get(self.url(pronto))

        assert resposta["X-Frame-Options"] == "SAMEORIGIN"

    def test_o_resto_da_tela_continua_recusando_ser_enquadrado(self, cliente, pronto):
        """A liberação é DESTA resposta, e de mais nenhuma."""
        assert cliente.get(LISTA)["X-Frame-Options"] == "DENY"

    def test_com_exemplo_o_documento_muda(self, cliente, pronto):
        vazio = cliente.get(self.url(pronto)).content
        exemplo = cliente.get(self.url(pronto), {"exemplo": "1"}).content

        assert vazio != exemplo

    def test_modelo_sem_desenho_e_404(self, cliente, rascunho):
        assert cliente.get(self.url(rascunho)).status_code == 404

    def test_modelo_que_nao_desenha_explica_em_texto(self, cliente, tipo):
        """
        Um layout que aponta para uma imagem inexistente não pode virar
        500 dentro do `<iframe>`: a resposta é 409 com o motivo em
        palavras -- que é o mesmo "Rascunho" da lista, dito por extenso.
        """
        quebrado = DocumentTemplate.objects.create(
            type=tipo, name="Sem logo", slug="sem-logo", language="nl",
            layout={
                "version": 1,
                "elements": [{
                    "id": "img", "type": "image", "x": 10.0, "y": 10.0,
                    "width": 50.0, "height": 50.0,
                    "properties": {"source": {"kind": "asset", "asset_id": 987654}},
                }],
            },
        )

        resposta = cliente.get(self.url(quebrado))

        assert resposta.status_code == 409
        assert resposta["Content-Type"].startswith("text/plain")
        assert "ainda não pode ser desenhado" in resposta.content.decode()

    def test_quem_so_ve_pode_visualizar(self, client, so_leitor, pronto):
        """É o mesmo documento que a tela já descreve, com dados fictícios."""
        client.force_login(so_leitor)

        assert client.get(self.url(pronto)).status_code == 200

    def test_usuario_comum_nao_visualiza(self, client, db, pronto):
        client.force_login(criar_pessoa("ze@exemplo.be", "Zé"))

        assert client.get(self.url(pronto)).status_code == 403

    def test_anonimo_nao_visualiza(self, client, pronto):
        resposta = client.get(self.url(pronto))

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    def test_modelo_inexistente_e_404(self, cliente):
        assert cliente.get(
            reverse("backoffice:document_preview", args=[999999])
        ).status_code == 404

    def test_a_previa_nao_grava_nada(self, cliente, pronto):
        antes = DocumentTemplate.objects.get(pk=pronto.pk).updated_at

        cliente.get(self.url(pronto), {"exemplo": "1"})

        assert DocumentTemplate.objects.get(pk=pronto.pk).updated_at == antes


# ===========================================================================
# 7. Segurança
# ===========================================================================


PAYLOAD = '"><img src=x onerror=alert(1)><script>alert(2)</script>'


class TestSeguranca:
    def test_nome_com_marcacao_nao_vira_marcacao(self, cliente, tipo):
        """
        Quem nomeia um modelo é um administrador -- e nem ele pode
        injetar HTML na tela de outro. O nome volta em três lugares:
        texto da linha, atributo `data-*` das janelas e título do
        menu. Os três saem escapados.
        """
        DocumentTemplate.objects.create(
            type=tipo, name=PAYLOAD, slug="malicioso", language="fr", layout=LAYOUT,
        )

        html = corpo(cliente.get(LISTA, {"q": "malicioso"}))

        assert "<img src=x" not in html
        assert "<script>alert(2)</script>" not in html
        assert "&lt;img src=x" in html  # aparece, escapado, como texto

    def test_identificador_com_marcacao_nao_vira_marcacao(self, cliente, tipo):
        DocumentTemplate.objects.create(
            type=tipo, name="Nome normal", slug='x"><img src=y>', language="nl",
        )

        html = corpo(cliente.get(LISTA))

        assert '<img src=y>' not in html

    def test_a_busca_nao_reflete_marcacao(self, cliente, pronto):
        """O que a pessoa digitou volta no campo -- como valor, não como tag."""
        html = corpo(cliente.get(LISTA, {"q": PAYLOAD}))

        assert "<img src=x" not in html
        assert "<script>alert(2)</script>" not in html

    def test_a_janela_recebe_os_dados_por_atributo_e_nao_por_html(
        self, cliente, pronto
    ):
        """
        As janelas são preenchidas a partir de `data-*` (o JavaScript
        usa `textContent`). Nenhum trecho de HTML é montado com dado do
        banco -- é o que impede que um nome vire marcação ao abrir.
        """
        html = corpo(cliente.get(LISTA))
        caminho = (
            pathlib.Path(settings.BASE_DIR) / "static" / "js" / "biblioteca-modelos.js"
        )

        # O `.` importa: o arquivo FALA de innerHTML no comentário de
        # topo ("NADA DE innerHTML"); o que não pode existir é a
        # escrita, `algo.innerHTML = ...`.
        assert "data-nome=" in html
        assert not re.search(
            r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write",
            caminho.read_text(encoding="utf-8"),
        )

    def test_o_endereco_de_filtro_nao_aceita_marcacao(self, cliente, pronto):
        """Os filtros remontam a querystring: ela volta escapada."""
        html = corpo(cliente.get(LISTA, {"language": PAYLOAD}))

        assert "<img src=x" not in html

    def test_ativar_por_get_nao_funciona_nem_com_permissao(self, cliente, pronto):
        """Mudar estado só por POST -- uma imagem num e-mail não ativa nada."""
        resposta = cliente.get(
            reverse("backoffice:document_library_activation", args=[pronto.pk])
        )

        assert resposta.status_code == 405

    def test_sem_csrf_nao_ativa(self, client, administrador, pronto):
        """O token não é enfeite: sem ele o servidor recusa."""
        client.force_login(administrador)
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(administrador)

        resposta = sem_token.post(
            reverse("backoffice:document_library_activation", args=[pronto.pk]),
            {"ativo": "0"},
        )

        assert resposta.status_code == 403
        assert DocumentTemplate.objects.get(pk=pronto.pk).is_active is True

    def test_sem_csrf_nao_duplica(self, administrador, pronto):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(administrador)

        resposta = sem_token.post(
            reverse("backoffice:document_library_duplicate", args=[pronto.pk]),
            {"name": "Tentativa"},
        )

        assert resposta.status_code == 403
        assert not DocumentTemplate.objects.filter(name="Tentativa").exists()

    def test_a_previa_nao_aceita_id_de_outro_lugar(self, cliente, pronto):
        """
        O identificador vem da URL e é resolvido no banco: não há
        caminho de arquivo, e nada que pareça um vem do cliente.
        """
        for lixo in ("../../etc/passwd", "1 OR 1=1", "%2e%2e%2f"):
            resposta = cliente.get(f"/pt/backoffice/modelos/{lixo}/documento.pdf")
            assert resposta.status_code in (404, 301, 302)


# ===========================================================================
# 8. A lista inteira sem uma consulta por linha
# ===========================================================================


class TestCusto:
    def test_a_tela_nao_faz_uma_consulta_por_modelo(
        self, cliente, oficiais, django_assert_max_num_queries
    ):
        """
        Situação, cópias e cartas saem de anotação e de uma consulta só
        de assets. Dobrar o número de linhas não pode dobrar o número
        de consultas.
        """
        for numero in range(12):
            DocumentTemplate.objects.create(
                type=oficiais["fr"].type, name=f"Extra {numero}",
                slug=f"extra-{numero}", language="fr", is_active=False, layout=LAYOUT,
            )

        with django_assert_max_num_queries(14):
            cliente.get(LISTA)
