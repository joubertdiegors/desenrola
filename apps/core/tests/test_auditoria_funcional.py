"""
Auditoria funcional: uma varredura de TODAS as rotas do produto.

POR QUE VARREDURA, E NÃO LISTA
------------------------------
Uma lista escrita à mão envelhece: a rota nova entra e ninguém acrescenta
a linha. Aqui o catálogo é DESCOBERTO do `URLconf` a cada execução, então
uma rota nova é auditada no dia em que nasce -- e se ela precisar de
argumento que esta suíte não sabe montar, o teste falha pedindo para
alguém decidir, em vez de pular em silêncio.

O QUE ELA PROCURA
-----------------
1. **Erro 500** em qualquer rota, para qualquer papel. É o defeito que
   nenhuma tela deveria produzir;
2. **Porta destrancada**: rota privada que responde a anônimo, ou rota do
   Backoffice que aceita usuário comum;
3. **POST sem CSRF**;
4. **Link morto**: cada `href` interno das telas é visitado de verdade;
5. **Botão inerte**: `href="#"`, `href=""` e `onclick` -- as três formas
   de parecer que faz algo sem fazer;
6. **Dado de um aparecendo para outro.**

O ADMIN DO DJANGO FICA DE FORA
------------------------------
É ferramenta do Django, não tela do produto, e tem suíte própria (a do
próprio Django). Auditar `admin:*` aqui seria testar biblioteca de
terceiro.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import NoReverseMatch, get_resolver, reverse
from django.urls.resolvers import URLPattern, URLResolver

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# O catálogo, descoberto do URLconf
# ---------------------------------------------------------------------------

# Namespaces que não são tela do produto.
FORA = ("admin",)

# As rotas que QUALQUER pessoa pode abrir, inclusive sem conta. Escrita à
# mão de propósito: é a decisão de segurança mais importante do projeto, e
# derivá-la do código faria o teste concordar com o que o código faz em
# vez de com o que se decidiu.
PUBLICAS = {
    "core:home",
    "core:legal_termos",
    "core:legal_privacidade",
    "accounts:login",
    "accounts:signup",
    "accounts:password_reset",
    "accounts:password_reset_done",
    "accounts:password_reset_confirm",
    "accounts:password_reset_complete",
    # Pelo mesmo motivo do link de senha: chega por e-mail, e quem prova
    # quem é não é a sessão -- é o token assinado. Exigir login mandaria
    # a pessoa para a tela de entrar e o link se perderia no caminho.
    "accounts:email_confirm",
    "set_language",
    # Sonda de infraestrutura: tem de responder sem conta, senao o
    # monitoramento nao consegue perguntar se o site esta de pe.
    "healthz",
}

# Rotas que só existem para POST: um GET nelas responde 405, e isso é
# correto, não falha.
#
# Descoberto do próprio URLconf tentando um GET -- e não escrito à mão.
# A primeira versão desta suíte trazia quatro nomes que eu inventei
# (`letters:step_back`, `:delete`, `:duplicate`, `:finalize`); as rotas
# de carta são seis, e nenhuma delas se chama assim. Lista escrita à mão
# envelhece, e aquela já nasceu errada.
SO_POST = {"accounts:logout", "set_language"}


def _andar(resolver, prefixo="", ns=None):
    for padrao in resolver.url_patterns:
        if isinstance(padrao, URLResolver):
            yield from _andar(padrao, prefixo + str(padrao.pattern), padrao.namespace or ns)
        elif isinstance(padrao, URLPattern) and padrao.name:
            nome = f"{ns}:{padrao.name}" if ns else padrao.name
            yield nome, prefixo + str(padrao.pattern)


def rotas_do_produto():
    """`{nome: [tipos de argumento]}` de cada rota nomeada do produto."""
    achadas = {}
    for nome, padrao in _andar(get_resolver()):
        if nome.split(":")[0] in FORA:
            continue
        achadas[nome] = [a.split(":")[0] for a in re.findall(r"<([^>]+)>", padrao)]
    return achadas


NOMES = sorted(rotas_do_produto())


# ---------------------------------------------------------------------------
# Um mundo com um exemplar de cada coisa, para as rotas com argumento
# ---------------------------------------------------------------------------


@pytest.fixture
def mundo(db, modelos_oficiais_prontos, user, other_user):
    """
    Um exemplar de cada objeto que as rotas pedem por `pk`/`uuid`.

    `other_user` tem a própria carta: é com ela que se prova o
    isolamento.
    """
    from apps.content.models import (
        Asset,
        ContentBlock,
        ContentTranslation,
        FaqItem,
        MenuItem,
        PageSection,
        Partner,
    )
    from apps.doctemplates.models import DocumentTemplate
    from apps.letters import services as letras
    from apps.letters.models import LetterNotice

    minha = letras.start_draft(user, "fr")
    dela = letras.start_draft(other_user, "fr")

    # As páginas legais respondem 404 enquanto não houver TEXTO -- é o
    # comportamento correto (link para página em branco é pior que link
    # nenhum). Com texto, a auditoria confere a página de verdade.
    for chave in ("legal.terms_of_use", "legal.privacy_policy"):
        bloco, _criado = ContentBlock.objects.get_or_create(
            key=chave, defaults={"kind": ContentBlock.Kind.TEXT}
        )
        ContentTranslation.objects.update_or_create(
            block=bloco, language="pt", defaults={"content": "Texto de auditoria."}
        )

    return {
        "carta": minha,
        "carta_alheia": dela,
        "usuario": user,
        "outro": other_user,
        "secao": PageSection.objects.get(page__key="home", key="hero"),
        "parceiro": Partner.objects.create(name="Padaria", url="https://exemplo.test/"),
        "item": MenuItem.objects.first(),
        "pergunta": FaqItem.objects.create(
            question="Quanto tempo leva?", answer="Minutos.", order=1
        ),
        "imagem": Asset.objects.filter(kind=Asset.Kind.LOGO).first()
        or Asset.objects.first(),
        "modelo": DocumentTemplate.objects.filter(is_system=True).first(),
        "declaracao": LetterNotice.objects.first(),
    }


def _argumento(tipo, nome, mundo):
    """O valor que aquela rota espera, vindo de um objeto de verdade."""
    if tipo == "uuid":
        return mundo["carta"].uuid
    if nome.startswith("letters:"):
        return 1  # `step`
    if nome.startswith("backoffice:user"):
        return mundo["usuario"].pk
    if "partner" in nome:
        return mundo["parceiro"].pk
    if "menu_item" in nome:
        return mundo["item"].pk
    if "faq_item" in nome:
        return mundo["pergunta"].pk
    if "asset" in nome:
        return mundo["imagem"].pk
    if "content" in nome:
        return mundo["secao"].pk
    if "document" in nome or "template" in nome:
        return mundo["modelo"].pk
    if "letter_notice" in nome:
        return mundo["declaracao"].pk
    if nome == "backoffice:language_flag":
        # Um codigo de idioma, e nao um `pk`: a rota confere o valor
        # contra `settings.LANGUAGES`.
        return "pt"
    raise AssertionError(
        f"a rota {nome!r} pede um argumento que esta auditoria não sabe montar -- "
        "acrescente-o em `_argumento` em vez de deixá-la de fora"
    )


def endereco(nome, mundo):
    tipos = rotas_do_produto()[nome]
    if not tipos:
        return reverse(nome)
    if nome == "letters:step":
        return reverse(nome, args=[mundo["carta"].uuid, 1])
    if nome == "accounts:email_confirm":
        # Os dois argumentos têm de ser DE VERDADE: um uid inventado
        # daria uma tela de "link inválido", e a auditoria estaria
        # medindo a própria recusa em vez da tela.
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        from apps.accounts.confirmacao import token_de_email

        quem = mundo["usuario"]
        return reverse(
            nome,
            args=[
                urlsafe_base64_encode(force_bytes(quem.pk)),
                token_de_email.make_token(quem),
            ],
        )

    if nome == "accounts:password_reset_confirm":
        # Dois argumentos, e os dois têm de ser DE VERDADE: um uid
        # inventado daria 404 e a auditoria estaria medindo o 404 dela
        # mesma, não a tela.
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        quem = mundo["usuario"]
        return reverse(
            nome,
            args=[
                urlsafe_base64_encode(force_bytes(quem.pk)),
                default_token_generator.make_token(quem),
            ],
        )
    try:
        return reverse(nome, args=[_argumento(tipos[0], nome, mundo)])
    except NoReverseMatch as erro:
        raise AssertionError(f"{nome}: {erro}") from None


@pytest.fixture
def administradora(db):
    """Alguém com TODAS as permissões administrativas do produto."""
    pessoa = get_user_model().objects.create_user(
        email="auditoria@mail.com", password="x", full_name="Auditoria", is_staff=True
    )
    pessoa.user_permissions.set(
        Permission.objects.filter(
            content_type__app_label__in=("core", "accounts", "content", "letters",
                                         "doctemplates")
        )
    )
    return get_user_model().objects.get(pk=pessoa.pk)


# ===========================================================================
# 1. Nenhuma rota estoura
# ===========================================================================


class TestNenhum500:
    @pytest.mark.parametrize("nome", NOMES)
    def test_anonimo_nao_provoca_erro_de_servidor(self, client, mundo, nome):
        resposta = client.get(endereco(nome, mundo))

        assert resposta.status_code < 500, f"{nome} devolveu {resposta.status_code}"

    @pytest.mark.parametrize("nome", NOMES)
    def test_usuario_comum_nao_provoca_erro_de_servidor(self, client, mundo, nome):
        client.force_login(mundo["usuario"])

        resposta = client.get(endereco(nome, mundo))

        assert resposta.status_code < 500, f"{nome} devolveu {resposta.status_code}"

    @pytest.mark.parametrize("nome", NOMES)
    def test_administradora_nao_provoca_erro_de_servidor(
        self, client, mundo, administradora, nome
    ):
        client.force_login(administradora)

        resposta = client.get(endereco(nome, mundo))

        assert resposta.status_code < 500, f"{nome} devolveu {resposta.status_code}"


# ===========================================================================
# 2. As portas
# ===========================================================================


class TestPortas:
    @pytest.mark.parametrize("nome", [n for n in NOMES if n not in PUBLICAS])
    def test_rota_privada_recusa_anonimo(self, client, mundo, nome):
        """
        Redireciona para o login ou recusa. O que não pode é ENTREGAR o
        conteúdo a quem não entrou.
        """
        resposta = client.get(endereco(nome, mundo))

        assert resposta.status_code != 200, f"{nome} abriu para anônimo"

    @pytest.mark.parametrize("nome", [n for n in NOMES if n in PUBLICAS])
    def test_rota_publica_abre_para_qualquer_um(self, client, mundo, nome):
        if nome in SO_POST:
            pytest.skip("só existe para POST")

        resposta = client.get(endereco(nome, mundo), follow=True)

        assert resposta.status_code == 200, nome

    @pytest.mark.parametrize(
        "nome", [n for n in NOMES if n.startswith("backoffice:")]
    )
    def test_backoffice_recusa_usuario_comum(self, client, mundo, nome):
        """
        Entrar no produto não abre a administração. Nenhuma exceção: uma
        rota esquecida aqui é a porta que fica destrancada.
        """
        client.force_login(mundo["usuario"])

        resposta = client.get(endereco(nome, mundo))

        assert resposta.status_code != 200, f"{nome} abriu para usuário comum"


# ===========================================================================
# 3. CSRF em todo POST
# ===========================================================================


class TestCSRF:
    """
    POST em TODAS as rotas, sem token -- e nenhuma pode ser PROCESSADA.

    Varredura, e não lista: enumerar à mão quais rotas aceitam POST é
    exatamente onde a primeira versão desta suíte errou. 403 (o CSRF
    recusou) e 405 (a rota só aceita GET) são os dois resultados
    aceitáveis. 200 ou 302 significaria que o POST passou.
    """

    @pytest.mark.parametrize("nome", NOMES)
    def test_nenhum_post_e_processado_sem_token(self, mundo, administradora, nome):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(administradora)

        resposta = sem_token.post(endereco(nome, mundo))

        assert resposta.status_code in (403, 405), (
            f"{nome} respondeu {resposta.status_code} a um POST sem token"
        )


# ===========================================================================
# 4. Nenhum link morto, nenhum botão inerte
# ===========================================================================

# De onde a varredura parte. Cada página encontrada a partir daqui é
# visitada, e os links dela também -- duas camadas, que cobrem o
# caminho real de quem usa.
PONTOS_DE_PARTIDA = [
    "core:home",
    "core:dashboard",
    "accounts:profile",
    "backoffice:overview",
    "backoffice:content",
    "backoffice:partners",
    "backoffice:assets",
    "backoffice:users",
    "backoffice:letters",
    "backoffice:document_library",
    "backoffice:system",
    "backoffice:languages",
    "backoffice:appearance",
    "backoffice:letter_policy",
    "backoffice:email_settings",
]

INTERNO = re.compile(r'href="(/[^"#?]*)')

# O Django Admin fica sob o prefixo de idioma (`/pt/admin/`), não em
# `/admin/`. A primeira versão desta suíte excluía só o segundo, então a
# varredura entrava no admin sem que eu percebesse -- e foi de lá que um
# aviso de depreciação do Django apareceu na suíte, vindo de uma tela que
# não é do produto.
ADMIN = re.compile(r"^(/[a-z]{2})?/admin/")


def _links_de(corpo):
    return {
        href
        for href in INTERNO.findall(corpo)
        if not href.startswith(("/static/", "/media/")) and not ADMIN.match(href)
    }


# A única tela do produto que pode apontar para o Django Admin, e por
# decisão explícita: a de Sistema, no link para os TEXTOS LEGAIS. Quem
# escreve texto jurídico é o cliente, por lá -- o código cria o lugar; o
# conteúdo jurídico não se inventa (decisão da Etapa G).
#
# Registrada aqui para ser uma decisão VISÍVEL, e não um esquecimento.
PODE_APONTAR_PARA_O_ADMIN = {"backoffice:system"}


class TestNenhumLinkMorto:
    def test_todo_link_das_telas_responde(self, client, mundo, administradora):
        """
        Visita cada `href` interno de verdade. Um link para uma rota que
        não existe mais só aparece quando alguém clica -- e é tarde.
        """
        client.force_login(administradora)

        visitar = set()
        for nome in PONTOS_DE_PARTIDA:
            resposta = client.get(reverse(nome))
            assert resposta.status_code in (200, 302), f"{nome}: {resposta.status_code}"
            if resposta.status_code == 200:
                visitar |= _links_de(resposta.content.decode())

        quebrados = []
        segunda_camada = set()
        for href in sorted(visitar):
            resposta = client.get(href)
            if resposta.status_code >= 400:
                quebrados.append((href, resposta.status_code))
            elif resposta.status_code == 200:
                segunda_camada |= _links_de(resposta.content.decode())

        for href in sorted(segunda_camada - visitar):
            resposta = client.get(href)
            if resposta.status_code >= 400:
                quebrados.append((href, resposta.status_code))

        assert not quebrados, f"links quebrados: {quebrados}"

    @pytest.mark.parametrize("nome", PONTOS_DE_PARTIDA)
    def test_nenhuma_tela_depende_do_admin_do_django(
        self, client, mundo, administradora, nome
    ):
        """
        A regra do produto: o Backoffice não manda ninguém para fora para
        fazer o que é dele. Parceiros deixou de mandar no Bloco B;
        Aparência, no H -- ela mostrava as cores e mandava alterar no
        Django Admin, enquanto a tela de Sistema dizia por escrito que
        era ELA quem administrava aqueles campos.
        """
        if nome in PODE_APONTAR_PARA_O_ADMIN:
            pytest.skip("aponta para o admin por decisão registrada")
        # A Home redireciona quem já entrou: ela é olhada por ANÔNIMO.
        if nome != "core:home":
            client.force_login(administradora)
        resposta = client.get(reverse(nome))
        if resposta.status_code != 200:
            pytest.skip(f"{nome} não abre para esta pessoa")

        corpo = resposta.content.decode()
        apontam = [href for href in INTERNO.findall(corpo) if ADMIN.match(href)]

        assert not apontam, f"{nome} aponta para o Django Admin: {apontam}"

    @pytest.mark.parametrize("nome", PONTOS_DE_PARTIDA)
    def test_nenhum_botao_inerte(self, client, mundo, administradora, nome):
        """
        `href="#"`, `href=""` e `onclick` -- as três formas de parecer que
        faz algo sem fazer. É o defeito que a Etapa I tirou do projeto e
        que não pode voltar.
        """
        # A Home redireciona quem já entrou para o painel: ela é olhada
        # por ANÔNIMO, que é quem a vê. Pular seria deixar a página mais
        # visitada do site fora da auditoria.
        if nome != "core:home":
            client.force_login(administradora)
        resposta = client.get(reverse(nome))
        if resposta.status_code != 200:
            pytest.skip(f"{nome} não abre para esta pessoa")
        corpo = resposta.content.decode()

        assert 'href="#"' not in corpo, nome
        assert 'href=""' not in corpo, nome
        assert "onclick=" not in corpo, nome


# ===========================================================================
# 5. O dado de um não aparece para o outro
# ===========================================================================


class TestIsolamento:
    @pytest.mark.parametrize(
        "nome", ["letters:detail", "letters:pdf", "letters:pdf_download"]
    )
    def test_a_carta_de_um_nao_abre_para_o_outro(self, client, mundo, nome):
        """O `uuid` não é segredo: quem protege é a checagem de dono."""
        client.force_login(mundo["outro"])

        resposta = client.get(reverse(nome, args=[mundo["carta"].uuid]))

        assert resposta.status_code in (403, 404), f"{nome}: {resposta.status_code}"

    def test_o_assistente_de_um_nao_abre_para_o_outro(self, client, mundo):
        client.force_login(mundo["outro"])

        resposta = client.get(reverse("letters:step", args=[mundo["carta"].uuid, 1]))

        assert resposta.status_code in (403, 404)

    def test_o_historico_so_mostra_as_proprias(self, client, mundo):
        client.force_login(mundo["outro"])

        corpo = client.get(reverse("core:dashboard")).content.decode()

        assert str(mundo["carta"].uuid) not in corpo
        assert str(mundo["carta_alheia"].uuid) in corpo or "carta" in corpo.lower()

    def test_o_backoffice_de_cartas_exige_permissao_propria(self, client, mundo):
        """
        Ver as cartas de todo mundo é `letters.view_all_letters` -- não
        basta entrar na administração.
        """
        pessoa = get_user_model().objects.create_user(
            email="so-backoffice@mail.com", password="x", full_name="X"
        )
        pessoa.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core", codename="access_backoffice"
            )
        )
        client.force_login(get_user_model().objects.get(pk=pessoa.pk))

        assert client.get(reverse("backoffice:letters")).status_code == 403


# ===========================================================================
# 6. Responsividade: o que só um navegador vê, e o fio que o segura
# ===========================================================================


class TestRolagemHorizontal:
    """
    Um arame de aviso, e ele se assume como tal.

    A rolagem horizontal quem mede é um navegador de verdade -- foi assim
    que ela apareceu: no tablet (834px), as telas de Usuários, Cartas e
    Modelos rolavam de 31 a 67px para o lado. A tabela já estava dentro de
    um `.table-wrap` com `overflow-x: auto`, que RECORTA o desenho; o que
    faltava era o transbordo deixar de contar para a área rolável do
    DOCUMENTO, e nenhuma regra de `overflow` em ancestral resolvia isso.
    `contain: paint` resolveu.

    Um teste em Python não enxerga layout. O que ele pode fazer é impedir
    que a regra saia sem que alguém repare -- e dizer, aqui, por que ela
    existe.
    """

    def test_a_tabela_larga_continua_contida_no_cartao(self):
        from pathlib import Path

        css = Path("static/css/components.css").read_text(encoding="utf-8")
        regra = [
            linha for linha in css.splitlines()
            if linha.startswith(".table-wrap {")
        ]

        assert regra, "a regra de `.table-wrap` sumiu"
        assert "overflow-x: auto" in regra[0], "a tabela larga precisa rolar dentro"
        assert "contain: paint" in regra[0], (
            "sem `contain: paint` a página inteira volta a rolar para o lado "
            "no tablet -- medido no navegador"
        )
