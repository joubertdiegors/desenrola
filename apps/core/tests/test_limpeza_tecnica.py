"""
Limpeza técnica: os arames que impedem o lixo de voltar.

POR QUE ISTO E TESTE, E NAO UMA FAXINA DE UMA VEZ
------------------------------------------------
Template órfão, rota sem uso e dependência instalada à toa não quebram
nada -- por isso se acumulam. Uma faxina manual limpa hoje e não diz
nada sobre amanhã. Estes testes falham no dia em que o lixo aparece.

AS LISTAS DE EXCEÇÃO SÃO ESCRITAS À MÃO
---------------------------------------
Cada uma com a razão ao lado. Acrescentar um caso exige mexer no teste,
que é a forma mais barata de obrigar alguém a justificar -- e de deixar
a justificativa registrada onde ela será lida.
"""

import pathlib
import re

import pytest

RAIZ = pathlib.Path(".")
TEMPLATES = RAIZ / "templates"


def _texto_do_projeto():
    """Todo o código e marcação do projeto, num só bloco."""
    pedacos = []
    for pasta in ("apps", "templates", "config", "static", "pdfengine"):
        raiz = RAIZ / pasta
        if not raiz.exists():
            continue
        for sufixo in ("*.py", "*.html", "*.js", "*.css", "*.txt"):
            for caminho in raiz.rglob(sufixo):
                if "__pycache__" in caminho.parts:
                    continue
                pedacos.append(caminho.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(pedacos)


# ===========================================================================
# 1. Dependências
# ===========================================================================

# Pacotes que NINGUÉM importa, e nem deveria -- e por quê.
INDIRETOS = {
    # Driver de banco: quem o usa é o Django, pela `DATABASE_URL`.
    "psycopg[binary]": "driver do PostgreSQL, usado pelo Django",
    # Plugin do pytest: carregado por configuração, nunca importado.
    "pytest-django": "plugin do pytest, carregado por configuração",
    # Ferramenta de linha de comando.
    "ruff": "ferramenta de linha de comando",
    # Aplicativo do Django, carregado por STRING em INSTALLED_APPS e
    # MIDDLEWARE (ver `config/settings/dev.py`) -- nunca por `import`.
    "django-debug-toolbar": "aplicativo do Django, carregado por string em dev.py",
}

# Nome no requirements -> módulo que se importa.
MODULO_DE = {
    "Django": "django",
    "django-environ": "environ",
    "Pillow": "PIL",
    "django-debug-toolbar": "debug_toolbar",
    "factory-boy": "factory",
}


def _declaradas():
    for arquivo in ("base.txt", "dev.txt", "prod.txt"):
        caminho = RAIZ / "requirements" / arquivo
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith(("#", "-r")):
                continue
            yield re.split(r"[=<>]", linha)[0].strip(), arquivo


class TestDependencias:
    def test_toda_dependencia_declarada_e_usada(self):
        """
        Instalar o que ninguém usa custa tempo de deploy e uma superfície
        a mais para manter em dia. `factory-boy` ficou assim: declarado e
        nunca importado -- as ocorrências de "factory" no projeto eram
        `dataclasses.field(default_factory=...)` e uma fixture própria.
        """
        texto = _texto_do_projeto()
        sem_uso = []

        for nome, arquivo in _declaradas():
            if nome in INDIRETOS:
                continue
            modulo = MODULO_DE.get(nome, nome.replace("-", "_"))
            usado = re.search(rf"\b(import {modulo}\b|from {modulo}[\. ])", texto)
            if not usado:
                sem_uso.append(f"{nome} ({arquivo})")

        assert not sem_uso, (
            f"declarado e nunca importado: {sem_uso} -- ou use, ou tire, ou "
            "explique em INDIRETOS"
        )

    def test_toda_excecao_tem_razao_escrita(self):
        for nome, razao in INDIRETOS.items():
            assert len(razao) > 10, nome

    def test_as_versoes_sao_fixadas(self):
        """
        Sem `==`, um `pip install` de amanhã traz outra versão -- e o
        deploy passa a depender de que dia é.
        """
        soltas = []
        for arquivo in ("base.txt", "dev.txt", "prod.txt"):
            caminho = RAIZ / "requirements" / arquivo
            for linha in caminho.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if not linha or linha.startswith(("#", "-r")):
                    continue
                if "==" not in linha:
                    soltas.append(f"{arquivo}: {linha}")

        assert not soltas, soltas


# ===========================================================================
# 2. Órfãos
# ===========================================================================

# Templates que nenhum código cita pelo nome -- e por quê.
TEMPLATES_SEM_CITACAO = {
    # Alcançados por caminho MONTADO em `content.section_schema`
    # (`PASTA_DOS_DESENHOS` + a chave do desenho), então o nome do arquivo
    # não aparece escrito em lugar nenhum.
    "core/secoes/banner_imagem_completa.html": "desenho do banner, resolvido por section_schema",
    "core/secoes/banner_somente_texto.html": "desenho do banner, resolvido por section_schema",
    # Guardados de propósito: "ocultar não é apagar -- a interface
    # multilíngue tem de poder voltar" (decisão da Etapa 4.1, com teste
    # próprio em `test_etapa41`).
    "components/language_selector.html": "seletor de idioma guardado para poder voltar",
    "components/auth_lang.html": "seletor de idioma guardado para poder voltar",
    "components/language_seg.html": "seletor de idioma guardado para poder voltar",
}


class TestSemOrfaos:
    def test_nenhum_template_orfao(self):
        """
        `paper_letter.html` era um: um mock visual dos dois primeiros
        commits, que ninguém renderizava -- e que carregava nome, endereço
        e telefone de aparência real em código versionado.
        """
        texto = _texto_do_projeto()
        orfaos = []

        for caminho in TEMPLATES.rglob("*.html"):
            relativo = caminho.relative_to(TEMPLATES).as_posix()
            if relativo in TEMPLATES_SEM_CITACAO:
                continue
            if relativo not in texto:
                orfaos.append(relativo)

        assert not orfaos, (
            f"template que ninguém cita: {orfaos} -- ou use, ou remova, ou "
            "explique em TEMPLATES_SEM_CITACAO"
        )

    def test_os_desenhos_do_banner_existem_mesmo(self):
        """
        A lista de exceção não pode virar esconderijo: o que ela dispensa
        de citação tem de existir, e de ser alcançável.
        """
        from apps.content import section_schema

        for layout in section_schema.SECOES["hero"].layouts:
            caminho = section_schema.template_do_desenho("hero", layout.chave)
            assert (TEMPLATES / caminho).exists(), caminho

    def test_toda_excecao_de_template_tem_razao_escrita(self):
        for nome, razao in TEMPLATES_SEM_CITACAO.items():
            assert len(razao) > 15, nome

    @pytest.mark.django_db
    def test_nenhuma_rota_nomeada_sem_uso(self):
        """Rota que ninguém referencia é porta sem porteiro e sem visita."""
        from django.urls import get_resolver
        from django.urls.resolvers import URLPattern, URLResolver

        def andar(resolver, ns=None):
            for padrao in resolver.url_patterns:
                if isinstance(padrao, URLResolver):
                    yield from andar(padrao, padrao.namespace or ns)
                elif isinstance(padrao, URLPattern) and padrao.name:
                    yield f"{ns}:{padrao.name}" if ns else padrao.name

        texto = _texto_do_projeto()
        sem_uso = []
        for nome in sorted(set(andar(get_resolver()))):
            if nome.startswith("admin:"):
                continue
            curto = nome.split(":")[-1]
            if any(
                f"{aspas}{alvo}{aspas}" in texto
                for alvo in (nome, curto)
                for aspas in ("'", '"')
            ):
                continue
            sem_uso.append(nome)

        assert not sem_uso, sem_uso


# ===========================================================================
# 3. Nada de dado real em código versionado
# ===========================================================================


class TestSemDadoReal:
    @pytest.mark.parametrize(
        "termo",
        [
            "Ricardo Costa",  # o nome do cliente
            "+32 470 12 34 56",  # telefone que parecia real
            "Rue de l'Europe 123",  # endereço que parecia real
        ],
    )
    def test_nenhum_arquivo_do_projeto_traz(self, termo):
        """
        Estavam todos em `paper_letter.html`, o mock removido. Os testes
        usam nomes fictícios, e isso é outra coisa: ali o dado é
        declaradamente de mentira e não vai para tela nenhuma.
        """
        culpados = []
        for pasta in ("apps", "templates", "config", "static", "pdfengine"):
            raiz = RAIZ / pasta
            if not raiz.exists():
                continue
            for caminho in raiz.rglob("*"):
                if (
                    not caminho.is_file()
                    or "__pycache__" in caminho.parts
                    or caminho.suffix in (".pyc", ".pdf", ".png", ".gif", ".ttf")
                ):
                    continue
                if "tests" in caminho.parts:
                    continue
                if termo in caminho.read_text(encoding="utf-8", errors="replace"):
                    culpados.append(caminho.as_posix())

        assert not culpados, culpados


# ===========================================================================
# 4. Nenhum marcador de trabalho inacabado
# ===========================================================================


class TestSemMarcadorDeTrabalho:
    @pytest.mark.parametrize("marcador", ["FIXME", "XXX", "HACK"])
    def test_nenhum_marcador_no_codigo(self, marcador):
        culpados = []
        for pasta in ("apps", "templates", "config", "static"):
            for sufixo in ("*.py", "*.html", "*.js", "*.css"):
                for caminho in (RAIZ / pasta).rglob(sufixo):
                    if "__pycache__" in caminho.parts or "tests" in caminho.parts:
                        continue
                    if marcador in caminho.read_text(encoding="utf-8", errors="replace"):
                        culpados.append(caminho.as_posix())

        assert not culpados, culpados

    def test_nenhum_TODO_em_ingles(self):
        """
        O projeto escreve em português, onde "todo" é palavra comum -- por
        isso a busca é por `TODO ` em MAIÚSCULAS seguido de espaço, que é
        como o marcador em inglês aparece. Um título como "TODO FILTRO NO
        BANCO" se lia como marcador sem ser, e foi reescrito.
        """
        culpados = []
        padrao = re.compile(r"\bTODO\b[: ]")
        for pasta in ("apps", "templates", "config", "static"):
            for sufixo in ("*.py", "*.html", "*.js", "*.css"):
                for caminho in (RAIZ / pasta).rglob(sufixo):
                    if "__pycache__" in caminho.parts or "tests" in caminho.parts:
                        continue
                    texto = caminho.read_text(encoding="utf-8", errors="replace")
                    for linha in texto.splitlines():
                        # "TODO MUNDO", "TODO O FILTRO" e afins são
                        # português; o marcador vem sozinho ou com dois
                        # pontos.
                        if padrao.search(linha) and not re.search(
                            r"\bTODO (MUNDO|O |A |OS |AS |ARQUIVO|CONTEUDO|CONTEÚDO)",
                            linha,
                        ):
                            culpados.append(f"{caminho.as_posix()}: {linha.strip()[:60]}")

        assert not culpados, culpados


# ===========================================================================
# 5. Migrations
# ===========================================================================


class TestMigrations:
    def test_nenhuma_numeracao_repetida(self):
        """
        Duas migrations com o mesmo número são um merge mal resolvido, e
        o Django aplica uma ordem que ninguém escolheu.
        """
        for pasta in RAIZ.glob("apps/*/migrations"):
            numeros = [
                arquivo.name.split("_")[0]
                for arquivo in pasta.glob("0*.py")
            ]
            assert len(numeros) == len(set(numeros)), pasta.as_posix()

    def test_toda_migration_DE_DADOS_tem_docstring(self):
        """
        Só as de DADOS -- as que têm `RunPython`.

        Uma migration de esquema se explica sozinha pela lista de
        operações: `AddField`, `AlterField` e `CreateModel` dizem o que
        fazem. Uma de dados não: o que está lá é código, roda uma vez,
        meses depois, num banco que ninguém está olhando -- e a intenção
        não aparece em lugar nenhum se não for escrita.

        Exigir docstring nas de esquema seria pedir texto onde não há o
        que acrescentar.
        """
        sem_explicacao = []
        for caminho in RAIZ.glob("apps/*/migrations/0*.py"):
            texto = caminho.read_text(encoding="utf-8")
            if "RunPython" not in texto:
                continue
            if not texto.lstrip().startswith(('"""', "'''")):
                sem_explicacao.append(caminho.as_posix())

        assert not sem_explicacao, f"migration de dados sem explicação: {sem_explicacao}"
