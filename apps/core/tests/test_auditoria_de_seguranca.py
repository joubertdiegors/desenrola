"""
Auditoria de segurança: as regras que não podem ser afrouxadas sem que
alguém repare.

POR QUE VARREDURA DE CÓDIGO, E NÃO SÓ TESTE DE COMPORTAMENTO
------------------------------------------------------------
Um `|safe` acrescentado amanhã não quebra teste nenhum -- ele só abre uma
porta. Metade desta suíte procura PADRÕES no código-fonte, e a lista do
que é permitido é escrita à mão: acrescentar um caso exige mexer no
teste, o que é a forma mais barata de obrigar alguém a justificar.

A outra metade exercita o comportamento: cabeçalho de resposta, escape
de HTML, senha não exibida.

O ACHADO QUE MOTIVOU O CABEÇALHO
--------------------------------
Em produção o projeto manda `X_FRAME_OPTIONS = "DENY"`, que proíbe
QUALQUER enquadramento -- inclusive o de mesma origem. A miniatura da
Central e o quadro do editor vivem dentro de `<iframe>`: apareceriam
vazios no ar, e em lugar nenhum antes, porque a suíte roda com as
configurações de desenvolvimento.
"""

import pathlib
import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, override_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db

CODIGO = [pathlib.Path("apps"), pathlib.Path("config")]
TEMPLATES = pathlib.Path("templates")


def arquivos(raizes, sufixo, pular_testes=True):
    for raiz in raizes:
        for caminho in raiz.rglob(f"*{sufixo}"):
            partes = caminho.parts
            if pular_testes and ("tests" in partes or "migrations" in partes):
                continue
            yield caminho, caminho.read_text(encoding="utf-8")


@pytest.fixture
def administradora(db):
    pessoa = get_user_model().objects.create_user(
        email="seguranca@mail.com", password="x" * 12, full_name="Clara Dias"
    )
    pessoa.user_permissions.set(
        Permission.objects.filter(
            content_type__app_label__in=("core", "accounts", "content", "letters",
                                         "doctemplates")
        )
    )
    return get_user_model().objects.get(pk=pessoa.pk)


@pytest.fixture
def cliente(administradora):
    c = Client()
    c.force_login(administradora)
    return c


def secao(chave="hero"):
    from apps.content.models import PageSection

    return PageSection.objects.get(page__key="home", key=chave)


# ===========================================================================
# 1. Enquadramento (clickjacking)
# ===========================================================================


class TestEnquadramento:
    @override_settings(X_FRAME_OPTIONS="DENY")
    def test_a_previa_aceita_ser_enquadrada_pela_propria_origem(self, cliente):
        """
        Sem isto, a miniatura da Central e o quadro do editor apareceriam
        VAZIOS em produção -- e em lugar nenhum antes, porque em
        desenvolvimento `DENY` não está ligado.
        """
        resposta = cliente.get(
            reverse("backoffice:content_preview", args=[secao().pk])
        )

        assert resposta.headers.get("X-Frame-Options") == "SAMEORIGIN"

    @override_settings(X_FRAME_OPTIONS="DENY")
    @pytest.mark.parametrize(
        "nome",
        ["core:home", "backoffice:content", "backoffice:overview", "accounts:login"],
    )
    def test_o_resto_do_site_continua_recusando(self, cliente, nome):
        """
        A exceção é de UMA view. Afrouxar o site inteiro para fazer a
        prévia funcionar seria trocar uma defesa por uma conveniência.
        """
        resposta = cliente.get(reverse(nome))

        assert resposta.headers.get("X-Frame-Options") == "DENY", nome

    def test_a_producao_pede_DENY(self):
        texto = pathlib.Path("config/settings/prod.py").read_text(encoding="utf-8")

        assert 'X_FRAME_OPTIONS = "DENY"' in texto


# ===========================================================================
# 2. HTML: nada do usuário chega cru à página
# ===========================================================================

# Onde `|safe`, `mark_safe` e `autoescape off` são aceitos -- e por quê.
# A lista está VAZIA de propósito: o projeto não tem nenhum caso. Um
# acréscimo aqui exige que alguém escreva a razão ao lado.
# Onde `mark_safe` e' aceito no PYTHON -- e por que. Um so lugar, e ele
# sanitiza antes: ver o cabecalho de `apps/content/rodape.py`.
MARCA_SEGURO_PERMITIDO = {
    "apps/content/rodape.py",
}

ESCAPE_DESLIGADO_PERMITIDO = {
    # O corpo de TEXTO do e-mail de recuperação: texto puro não
    # interpreta marcação, então desligar o escape ali é inofensivo -- e
    # necessário, porque o link não pode sair com `&amp;`.
    "templates/accounts/password_reset_email.txt",
}


class TestNadaDeHtmlCru:
    @pytest.mark.parametrize("padrao", ["|safe", "mark_safe", "autoescape off"])
    def test_nenhum_template_desliga_o_escape(self, padrao):
        culpados = []
        for caminho, texto in arquivos([TEMPLATES], ".html", pular_testes=False):
            relativo = caminho.as_posix()
            if relativo in ESCAPE_DESLIGADO_PERMITIDO:
                continue
            # Em comentário de template não conta: o projeto EXPLICA por
            # que não usa, e a explicação não é uso.
            sem_comentario = re.sub(
                r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", texto, flags=re.S
            )
            if padrao in sem_comentario:
                culpados.append(relativo)

        assert not culpados, f"{padrao} em: {culpados}"

    def test_nenhum_python_marca_html_como_seguro(self):
        """
        A UNICA excecao e' `content/rodape.py`: o rodape e' conteudo rico
        escrito no Backoffice, e o que recebe `mark_safe` la e' o
        resultado de `sanitizar` -- uma lista fechada de tags e
        atributos. O cabecalho daquele modulo explica; a suite do rodape
        (`content/tests/test_rodape.py`) prova que a lista fecha.
        """
        culpados = [
            caminho.as_posix()
            for caminho, texto in arquivos(CODIGO, ".py")
            if ("mark_safe" in texto or "SafeString(" in texto)
            and caminho.as_posix() not in MARCA_SEGURO_PERMITIDO
        ]

        assert not culpados

    def test_o_nome_de_quem_se_cadastra_e_escapado(self, client, db):
        """O nome vem do cadastro da própria pessoa -- é entrada de usuário."""
        quem = get_user_model().objects.create_user(
            email="x@mail.com", password="x" * 12,
            full_name="<script>alert(1)</script>",
        )
        client.force_login(quem)

        corpo = client.get(reverse("core:dashboard")).content.decode()

        assert "<script>alert(1)</script>" not in corpo
        assert "&lt;script&gt;" in corpo

    def test_o_texto_legal_nao_aceita_html(self, client, db):
        """
        A página legal converte quebras de linha e ESCAPA todo o resto:
        é texto do cliente, não marcação.
        """
        from apps.content.models import ContentBlock, ContentTranslation

        bloco, _ = ContentBlock.objects.get_or_create(
            key="legal.terms_of_use", defaults={"kind": ContentBlock.Kind.TEXT}
        )
        ContentTranslation.objects.update_or_create(
            block=bloco, language="pt",
            defaults={"content": "<script>alert(1)</script>\nSegunda linha."},
        )

        corpo = client.get(reverse("core:legal_termos")).content.decode()

        assert "<script>alert(1)</script>" not in corpo
        assert "&lt;script&gt;" in corpo
        assert "<br>" in corpo  # a quebra de linha, essa sim, vira marcação


# ===========================================================================
# 3. O navegador não escolhe arquivo
# ===========================================================================


class TestNadaDeCaminhoDoNavegador:
    def test_os_dois_includes_dinamicos_vem_de_lista_fechada(self):
        """
        `{% include variavel %}` é a porta clássica para ler arquivo
        arbitrário. O projeto tem dois, e os dois resolvem por
        `section_schema` -- que só devolve nomes declarados.
        """
        dinamicos = []
        for caminho, texto in arquivos([TEMPLATES], ".html", pular_testes=False):
            for achado in re.findall(r"{%\s*include\s+([a-z_][\w.]*)\s*%}", texto):
                dinamicos.append((caminho.as_posix(), achado))

        assert sorted(dinamicos) == [
            ("templates/backoffice/content_preview.html", "parcial"),
            ("templates/core/home.html", "template_do_banner"),
        ]

    @pytest.mark.parametrize(
        "inventado",
        ["../../etc/passwd", "admin/base.html", "{{x}}", "nao_existe"],
    )
    def test_desenho_inventado_nao_vira_caminho(self, inventado):
        from apps.content import section_schema

        parcial = section_schema.parcial_da_secao("hero", inventado)

        assert parcial == section_schema.parcial_da_secao("hero", "imagem_texto")

    def test_parte_desconhecida_nao_tem_parcial(self):
        from apps.content import section_schema

        assert section_schema.parcial_da_secao("../../etc/passwd") is None

    def test_nenhum_arquivo_e_aberto_a_partir_do_pedido(self):
        """
        Nenhum `open()` nem `Path()` montado com dado do navegador. A
        busca é grosseira de propósito: qualquer linha que junte as duas
        coisas merece ser olhada por uma pessoa.
        """
        suspeitas = []
        for caminho, texto in arquivos(CODIGO, ".py"):
            for numero, linha in enumerate(texto.splitlines(), 1):
                abre = "open(" in linha or "Path(" in linha
                do_pedido = "request." in linha or "POST" in linha or "GET[" in linha
                if abre and do_pedido:
                    suspeitas.append(f"{caminho.as_posix()}:{numero}")

        assert not suspeitas, suspeitas


# ===========================================================================
# 4. Banco: nada de SQL montado à mão
# ===========================================================================


class TestNadaDeSqlCru:
    @pytest.mark.parametrize("padrao", [".raw(", "cursor.execute", "RunSQL"])
    def test_nenhum_sql_cru_no_codigo(self, padrao):
        culpados = [
            caminho.as_posix()
            for caminho, texto in arquivos(CODIGO, ".py")
            if padrao in texto
        ]

        assert not culpados, f"{padrao} em: {culpados}"

    def test_nem_nas_migrations(self):
        culpados = [
            caminho.as_posix()
            for caminho in pathlib.Path("apps").rglob("migrations/*.py")
            if "RunSQL" in caminho.read_text(encoding="utf-8")
        ]

        assert not culpados


# ===========================================================================
# 5. Segredos
# ===========================================================================


class TestSegredos:
    def test_as_chaves_vem_do_ambiente(self):
        texto = pathlib.Path("config/settings/base.py").read_text(encoding="utf-8")

        assert 'SECRET_KEY = env("SECRET_KEY")' in texto
        assert 'EMAIL_SECRET_KEY = env("EMAIL_SECRET_KEY"' in texto

    def test_a_secret_key_nao_tem_valor_padrao(self):
        """
        Um padrão faria uma produção mal configurada subir com a chave
        que está no repositório -- e sessões assináveis por qualquer um
        que leia o código.
        """
        texto = pathlib.Path("config/settings/base.py").read_text(encoding="utf-8")

        assert 'SECRET_KEY = env("SECRET_KEY", default=' not in texto

    def test_nenhum_segredo_escrito_no_codigo(self):
        padrao = re.compile(
            r"(password|senha|secret|token|api_?key)\s*=\s*['\"][^'\"\s]{8,}['\"]",
            re.I,
        )
        culpados = []
        for caminho, texto in arquivos(CODIGO, ".py"):
            for numero, linha in enumerate(texto.splitlines(), 1):
                if padrao.search(linha) and "env(" not in linha:
                    culpados.append(f"{caminho.as_posix()}:{numero}")

        assert not culpados, culpados

    def test_a_senha_do_smtp_nunca_e_exibida(self, cliente):
        """
        Ela é guardada cifrada e o sistema precisa REAPRESENTÁ-LA ao
        servidor -- por isso é legível pelo código. Isso não a torna
        exibível.
        """
        from apps.core import mail

        config = mail.configuracao()
        # `definir_senha()`, e nao uma atribuicao qualquer: a primeira
        # versao deste teste punha o valor num atributo que nao existe,
        # entao nada era gravado e a asercao passava por nao haver o que
        # encontrar. Mutacao serve para isto.
        config.definir_senha("senha-secreta-do-smtp")
        config.host = "smtp.exemplo.test"
        config.save()
        assert config.senha() == "senha-secreta-do-smtp", "a senha nao foi gravada"

        corpo = cliente.get(reverse("backoffice:email_settings")).content.decode()

        assert "senha-secreta-do-smtp" not in corpo
        # Nem o texto cifrado: ele volta a ser senha com a chave certa.
        assert config.password_encrypted not in corpo

    def test_o_log_de_falha_de_email_nao_conta_nada(self):
        """
        Só a classe do erro, o host e a porta. Nunca `str(erro)`, que
        costuma trazer o usuário -- e às vezes a senha.
        """
        texto = pathlib.Path("apps/core/mail.py").read_text(encoding="utf-8")
        # As linhas da chamada, e não `split(")")`: a própria string de
        # formato tem um parêntese, e o recorte parava nele.
        linhas = texto.splitlines()
        inicio = next(i for i, linha in enumerate(linhas) if "logger.warning(" in linha)
        trecho = "\n".join(linhas[inicio : inicio + 8])

        assert "type(erro).__name__" in trecho
        assert "str(erro)" not in trecho
        assert "senha" not in trecho.lower()


# ===========================================================================
# 6. Envio de arquivo
# ===========================================================================


class TestUpload:
    def test_so_quem_valida_formato_e_tamanho_aceita_arquivo(self):
        """
        Um `FileField` num formulário qualquer é um caminho de upload sem
        as conferências de formato e tamanho.

        A lista é uma ALLOWLIST, não um teto de um item: o Bloco D
        acrescentou upload direto em Parceiros e Banners
        (`FormularioDeParceiro.logo_upload`), e cada um chama
        `_validar_arquivo_de_imagem` -- a MESMA função de
        `FormularioDeImagem.clean_file()` -- no seu `clean_<campo>()`.
        Um nome novo aqui só é seguro se também aparecer em
        `test_todo_upload_direto_usa_o_mesmo_validador`, logo abaixo.
        """
        from django import forms

        import apps.accounts.forms
        import apps.content.forms
        import apps.core.forms
        import apps.letters.forms

        modulos = (
            apps.accounts.forms,
            apps.content.forms,
            apps.core.forms,
            apps.letters.forms,
        )
        com_arquivo = []
        for modulo in modulos:
            for nome in dir(modulo):
                classe = getattr(modulo, nome)
                if not (isinstance(classe, type) and issubclass(classe, forms.BaseForm)):
                    continue
                declarados = getattr(classe, "base_fields", {})
                for campo, objeto in declarados.items():
                    if isinstance(objeto, forms.FileField):
                        com_arquivo.append(f"{modulo.__name__}.{nome}.{campo}")

        assert com_arquivo == [
            "apps.content.forms.FormularioDeImagem.file",
            "apps.content.forms.FormularioDeParceiro.logo_upload",
        ], com_arquivo

    def test_todo_upload_direto_usa_o_mesmo_validador(self):
        """
        `FormularioDeSecao.imagem_upload` (Banners) não aparece no teste
        acima -- é um campo montado em `__init__`, não em `base_fields`
        -- mas passa pela mesma função, e é isso que este teste confere
        diretamente no código-fonte, em vez de depender de introspecção
        de classe.
        """
        import inspect

        from apps.content import forms as content_forms

        for nome_da_classe, nome_do_campo in (
            ("FormularioDeImagem", "clean_file"),
            ("FormularioDeParceiro", "clean_logo_upload"),
            ("FormularioDeSecao", "clean_imagem_upload"),
        ):
            classe = getattr(content_forms, nome_da_classe)
            metodo = getattr(classe, nome_do_campo)
            assert "_validar_arquivo_de_imagem" in inspect.getsource(metodo)

    def test_o_upload_confere_formato_e_tamanho(self):
        from apps.content.forms import FORMATOS_ACEITOS, TAMANHO_MAXIMO_DA_IMAGEM

        assert "SVG" not in FORMATOS_ACEITOS
        assert TAMANHO_MAXIMO_DA_IMAGEM <= 5 * 1024 * 1024


# ===========================================================================
# 7. Acesso por objeto
# ===========================================================================


class TestAcessoPorObjeto:
    def test_uma_secao_de_outra_pagina_nao_abre_no_editor(self, cliente, db):
        """
        O `pk` é buscado DENTRO da página conhecida: um id de outra
        página não abre a tela, mesmo sendo um id válido.
        """
        from apps.content.models import Page, PageSection

        outra = Page.objects.create(key="outra", is_active=True)
        forasteira = PageSection.objects.create(page=outra, kind="text", order=1)

        for nome in ("content_section", "content_preview", "content_activation"):
            metodo = "post" if nome.endswith("activation") else "get"
            resposta = getattr(cliente, metodo)(
                reverse(f"backoffice:{nome}", args=[forasteira.pk])
            )
            assert resposta.status_code == 404, nome

    def test_um_id_que_nao_existe_da_404(self, cliente):
        for nome in ("partner_edit", "asset_edit", "menu_item_edit", "content_section"):
            assert cliente.get(
                reverse(f"backoffice:{nome}", args=[999999])
            ).status_code == 404, nome


# ===========================================================================
# 8. Postura de produção
# ===========================================================================


class TestPosturaDeProducao:
    @pytest.mark.parametrize(
        "linha",
        [
            "DEBUG = False",
            "SECURE_SSL_REDIRECT = True",
            "SESSION_COOKIE_SECURE = True",
            "CSRF_COOKIE_SECURE = True",
            "SECURE_HSTS_INCLUDE_SUBDOMAINS = True",
            "SECURE_CONTENT_TYPE_NOSNIFF = True",
        ],
    )
    def test_o_arquivo_de_producao_tem(self, linha):
        texto = pathlib.Path("config/settings/prod.py").read_text(encoding="utf-8")

        assert linha in texto

    def test_o_hsts_vale_pelo_menos_um_ano(self):
        texto = pathlib.Path("config/settings/prod.py").read_text(encoding="utf-8")
        achado = re.search(r"SECURE_HSTS_SECONDS = (\d+)", texto)

        assert achado
        assert int(achado.group(1)) >= 31536000

    def test_producao_recusa_banco_que_nao_seja_postgres(self):
        """Uma produção em SQLite perde dado sob concorrência."""
        texto = pathlib.Path("config/settings/prod.py").read_text(encoding="utf-8")

        assert "ImproperlyConfigured" in texto
        assert "postgresql" in texto.lower()

    def test_as_permissoes_do_backoffice_sao_conferidas_no_servidor(self):
        """
        Esconder o botão não é proteção. Toda view administrativa passa
        por `backoffice_required` ou `exige_permissao`.
        """
        texto = pathlib.Path("apps/core/views.py").read_text(encoding="utf-8")

        assert "def backoffice_required" in texto
        assert "raise PermissionDenied" in texto
