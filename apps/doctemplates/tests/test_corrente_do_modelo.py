"""
A corrente inteira de um modelo: oficial → duplicar → editar → salvar → PDF.

POR QUE ESTA SUÍTE EXISTE
-------------------------
Cada elo já tinha teste próprio -- `test_duplicacao.py` prova a
independência da cópia, `test_template_editor_js.py` prova que o editor
preserva a sequência, `test_pdf_renderer.py` prova que o layout vira
PDF. O que faltava era a CORRENTE: percorrer os quatro de ponta a ponta,
pelas rotas de verdade, com o documento oficial de verdade.

É esse o critério de aceite do Bloco F -- "modelo oficial → duplicar →
modelo independente → editar → salvar → gerar PDF, sem alterar o modelo
original". Um elo pode estar certo sozinho e a corrente estar partida.

O DOCUMENTO É O REAL
--------------------
A Carta Convite francesa: 23 elementos, 4 deles com conteúdo misto (um
com 15 trechos alternando texto e campo) e uma tabela de 2 colunas por 5
linhas. É exatamente a estrutura que o Bloco F tornou editável, e é o
documento que o produto entrega.
"""

import copy
import io
import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from pypdf import PdfReader

from apps.doctemplates.models import DocumentTemplate
from apps.doctemplates.services import dados_de_exemplo, pdf

pytestmark = pytest.mark.django_db

# Os valores que o documento precisa para desenhar os campos.
#
# Vem de `dados_de_exemplo`, que e o mesmo lugar de onde saem a previa e
# o teste de integracao do renderer. Escrever a mao uma lista de campos
# aqui seria inventar referencias -- e foi exatamente o que aconteceu na
# primeira versao deste arquivo: nove nomes que nao existem no registro
# de fontes, e o renderer recusou, com razao.
DADOS = dados_de_exemplo.para("carta-convite-fr")


def texto_do_pdf(dados):
    return PdfReader(io.BytesIO(dados)).pages[0].extract_text()


@pytest.fixture
def administradora(db):
    """Quem pode ver a biblioteca, duplicar e salvar no editor."""
    pessoa = get_user_model().objects.create_user(
        email="modelos@mail.com", password="x", full_name="Clara Dias"
    )
    pessoa.user_permissions.add(
        Permission.objects.get(content_type__app_label="core", codename="access_backoffice")
    )
    for codename in ("view_documenttemplate", "change_documenttemplate"):
        pessoa.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="doctemplates", codename=codename
            )
        )
    return get_user_model().objects.get(pk=pessoa.pk)


@pytest.fixture
def cliente(administradora):
    c = Client()
    c.force_login(administradora)
    return c


@pytest.fixture
def oficial(modelos_oficiais_prontos):
    """A Carta Convite francesa -- o documento oficial do produto."""
    return DocumentTemplate.objects.get(is_system=True, language="fr")


def misto_com_mais_trechos(layout):
    """O elemento de conteúdo misto com a sequência mais longa."""
    candidatos = [
        elemento
        for elemento in layout["elements"]
        if (elemento.get("properties") or {}).get("content", {}).get("kind") == "mixed"
    ]
    return max(candidatos, key=lambda e: len(e["properties"]["content"]["parts"]))


def a_tabela(layout):
    return next(e for e in layout["elements"] if e["type"] == "table")


def duplicar(cliente, modelo, nome="Minha cópia"):
    """
    Duplica pela rota de verdade, e CONFERE que nasceu.

    Só olhar o status não bastaria: sem `name` a view redireciona com uma
    mensagem de erro -- 302, igual ao sucesso -- e nenhuma cópia é
    criada. Foi assim que a primeira versão destes testes passou pela
    asserção e quebrou três linhas depois.
    """
    quantas = DocumentTemplate.objects.filter(duplicated_from=modelo).count()
    resposta = cliente.post(
        reverse("backoffice:document_library_duplicate", args=[modelo.pk]),
        {"name": nome},
    )
    assert resposta.status_code == 302, resposta.status_code
    copias = DocumentTemplate.objects.filter(duplicated_from=modelo)
    assert copias.count() == quantas + 1, "a duplicação não criou cópia nenhuma"
    return copias.order_by("-pk").first()


def salvar(cliente, modelo, layout):
    return cliente.post(
        reverse("backoffice:template_editor_save", args=[modelo.pk]),
        data=json.dumps({"layout": layout}),
        content_type="application/json",
    )


# ===========================================================================
# 1. A corrente, de ponta a ponta
# ===========================================================================


class TestCorrente:
    def test_oficial_duplicar_editar_salvar_gerar(self, cliente, oficial):
        """
        O caminho inteiro, pelas rotas de verdade.

        Muda-se UM trecho de texto do conteúdo misto e UMA célula da
        tabela -- as duas coisas que o Bloco F tornou editáveis -- e
        exige-se que o PDF da cópia mostre o texto novo enquanto o do
        oficial continua mostrando o antigo.
        """
        antes = copy.deepcopy(oficial.layout)

        copia = duplicar(cliente, oficial)

        layout = copy.deepcopy(copia.layout)
        misto = misto_com_mais_trechos(layout)
        quantos = len(misto["properties"]["content"]["parts"])
        misto["properties"]["content"]["parts"][0]["value"] = "DECLARAÇÃO EDITADA: "
        a_tabela(layout)["properties"]["rows"][0]["cells"][0]["content"]["value"] = (
            "CÉLULA EDITADA"
        )

        resposta = salvar(cliente, copia, layout)
        assert resposta.status_code == 200, resposta.content[:400]

        copia.refresh_from_db()
        oficial.refresh_from_db()

        # 1. a cópia guardou a edição, sem perder a estrutura
        salvo = misto_com_mais_trechos(copia.layout)
        assert len(salvo["properties"]["content"]["parts"]) == quantos
        assert salvo["properties"]["content"]["parts"][0]["value"] == "DECLARAÇÃO EDITADA: "

        # 2. o original não foi tocado
        assert oficial.layout == antes

        # 3. os dois PDFs, e cada um com o seu texto
        pdf_da_copia, _ = pdf.render_template(copia, DADOS)
        pdf_do_oficial, _ = pdf.render_template(oficial, DADOS)

        assert "DECLARAÇÃO EDITADA:" in texto_do_pdf(pdf_da_copia)
        assert "CÉLULA EDITADA" in texto_do_pdf(pdf_da_copia)
        assert "DECLARAÇÃO EDITADA:" not in texto_do_pdf(pdf_do_oficial)
        assert "CÉLULA EDITADA" not in texto_do_pdf(pdf_do_oficial)

    def test_os_campos_dinamicos_sobrevivem_a_edicao(self, cliente, oficial):
        """
        O defeito que o Bloco F existe para impedir: editar o texto de um
        trecho e os CAMPOS virarem texto literal. Depois de salvar, cada
        `source` continua no lugar -- e o PDF continua imprimindo o VALOR
        do campo, não o nome dele.
        """
        copia = duplicar(cliente, oficial)
        layout = copy.deepcopy(copia.layout)
        misto = misto_com_mais_trechos(layout)
        fontes_antes = [
            p["source"] for p in misto["properties"]["content"]["parts"]
            if p["kind"] == "field"
        ]
        assert fontes_antes, "o documento oficial precisa ter campo no misto"
        misto["properties"]["content"]["parts"][0]["value"] = "Eu, "

        salvar(cliente, copia, layout)
        copia.refresh_from_db()

        salvo = misto_com_mais_trechos(copia.layout)
        fontes_depois = [
            p["source"] for p in salvo["properties"]["content"]["parts"]
            if p["kind"] == "field"
        ]
        assert fontes_depois == fontes_antes

        texto = texto_do_pdf(pdf.render_template(copia, DADOS)[0])
        assert "Claire Dubois" in texto
        assert "convidado.nome" not in texto

    def test_a_formatacao_do_trecho_sobrevive_a_edicao(self, cliente, oficial):
        """Peso e estilo por trecho são parte do dado, não enfeite."""
        copia = duplicar(cliente, oficial)
        layout = copy.deepcopy(copia.layout)
        misto = misto_com_mais_trechos(layout)
        partes = misto["properties"]["content"]["parts"]
        partes[1]["font_weight"] = "bold"
        partes[0]["value"] = "Eu, "

        salvar(cliente, copia, layout)
        copia.refresh_from_db()

        salvo = misto_com_mais_trechos(copia.layout)["properties"]["content"]["parts"]
        assert salvo[1]["font_weight"] == "bold"
        assert salvo[0]["value"] == "Eu, "

    def test_a_tabela_mantem_uma_celula_por_coluna(self, cliente, oficial):
        """A invariante que o validador cobra, depois de ida e volta."""
        copia = duplicar(cliente, oficial)
        layout = copy.deepcopy(copia.layout)
        tabela = a_tabela(layout)
        colunas = len(tabela["properties"]["columns"])

        # Acrescenta coluna como o editor faz: uma célula em cada linha.
        tabela["properties"]["columns"].append({"width": 40, "align": "left"})
        for linha in tabela["properties"]["rows"]:
            linha["cells"].append(
                {"content": {"kind": "text", "value": "novo"}, "align": "left", "bold": False}
            )

        resposta = salvar(cliente, copia, layout)
        assert resposta.status_code == 200

        copia.refresh_from_db()
        salva = a_tabela(copia.layout)["properties"]
        assert len(salva["columns"]) == colunas + 1
        assert all(len(linha["cells"]) == colunas + 1 for linha in salva["rows"])

    def test_tabela_com_celula_a_menos_e_recusada(self, cliente, oficial):
        """
        O servidor é a autoridade: um layout que quebre a invariante não
        entra, mesmo vindo de um cliente que diz estar certo.
        """
        copia = duplicar(cliente, oficial)
        layout = copy.deepcopy(copia.layout)
        tabela = a_tabela(layout)
        tabela["properties"]["columns"].append({"width": 40, "align": "left"})
        # ... e NÃO acrescenta a célula em cada linha.

        antes = copy.deepcopy(copia.layout)
        resposta = salvar(cliente, copia, layout)

        assert resposta.status_code == 400
        copia.refresh_from_db()
        assert copia.layout == antes


# ===========================================================================
# 2. O oficial travado continua intocável
# ===========================================================================


class TestOficialIntocavel:
    """
    Rodada 19: destravado, o oficial se edita direto no editor; o
    intocável é o oficial TRAVADO.
    """

    @pytest.fixture
    def travado(self, oficial):
        DocumentTemplate.objects.filter(pk=oficial.pk).update(is_locked=True)
        oficial.refresh_from_db()
        return oficial

    def test_o_editor_nao_salva_num_modelo_oficial_travado(self, cliente, travado):
        """
        409, e não 400 nem 403: o pedido está bem formado e a pessoa tem
        permissão -- o que impede é o ESTADO do modelo. É o código certo
        para "este recurso não aceita isto agora", e a aplicação já o
        usava; a primeira versão deste teste é que esperava menos.
        """
        antes = copy.deepcopy(travado.layout)
        layout = copy.deepcopy(travado.layout)
        layout["elements"][0]["x"] = 999

        resposta = salvar(cliente, travado, layout)

        assert resposta.status_code == 409
        travado.refresh_from_db()
        assert travado.layout == antes

    def test_o_editor_abre_o_oficial_travado_em_leitura(self, cliente, travado):
        corpo = cliente.get(
            reverse("backoffice:template_editor", args=[travado.pk])
        ).content.decode()

        assert "está travado" in corpo

    def test_editar_a_copia_nao_alcanca_o_oficial_nem_outra_copia(self, cliente, oficial):
        """Duas cópias do mesmo original são independentes entre si."""
        uma = duplicar(cliente, oficial, "Cópia um")
        outra = duplicar(cliente, oficial, "Cópia dois")

        layout = copy.deepcopy(uma.layout)
        misto_com_mais_trechos(layout)["properties"]["content"]["parts"][0]["value"] = "X"
        salvar(cliente, uma, layout)

        uma.refresh_from_db()
        outra.refresh_from_db()
        oficial.refresh_from_db()

        assert misto_com_mais_trechos(uma.layout)["properties"]["content"]["parts"][0][
            "value"
        ] == "X"
        assert misto_com_mais_trechos(outra.layout)["properties"]["content"]["parts"][0][
            "value"
        ] != "X"
        assert misto_com_mais_trechos(oficial.layout)["properties"]["content"]["parts"][0][
            "value"
        ] != "X"


# ===========================================================================
# 3. O PDF continua vindo do pipeline estruturado
# ===========================================================================


class TestPipelineDoPdf:
    def test_o_pdf_e_desenhado_a_partir_do_layout(self, oficial):
        """
        Nada de PDF de fundo, máscara ou overlay: o documento é DESENHADO
        a partir dos elementos, e o relatório diz quantos.
        """
        dados, relatorio = pdf.render_template(oficial, DADOS)

        assert relatorio["elementos"] == len(oficial.layout["elements"])
        assert dados[:4] == b"%PDF"

    def test_o_pdf_da_copia_editada_tem_o_mesmo_numero_de_elementos(self, cliente, oficial):
        copia = duplicar(cliente, oficial)
        layout = copy.deepcopy(copia.layout)
        misto_com_mais_trechos(layout)["properties"]["content"]["parts"][0]["value"] = "Eu, "
        salvar(cliente, copia, layout)
        copia.refresh_from_db()

        _dados, relatorio = pdf.render_template(copia, DADOS)

        assert relatorio["elementos"] == len(oficial.layout["elements"])

    def test_os_dados_nao_ficam_gravados_no_modelo(self, oficial):
        """O mesmo modelo serve a todas as cartas."""
        antes = copy.deepcopy(oficial.layout)

        pdf.render_template(oficial, DADOS)

        oficial.refresh_from_db()
        assert oficial.layout == antes
