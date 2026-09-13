"""
Idioma da interface.

DECISAO DE PRODUTO (Fase 5, Etapa 4.1): a interface do site e sempre em
portugues, para todo mundo. O idioma da CARTA continua independente e
continua oferecendo pt/fr/nl/en na etapa 5 do assistente -- sao coisas
diferentes e este modulo nao toca na segunda.

A infraestrutura de i18n fica INTACTA (settings.LANGUAGES com os quatro
idiomas, LocaleMiddleware, i18n_patterns, LOCALE_PATHS, a rota
set_language): o que muda e so o que a interface expoe e resolve.

POR QUE UM MIDDLEWARE, E NAO translation.activate() nas views
-------------------------------------------------------------
O idioma da interface e decidido pelo LocaleMiddleware a partir de tres
fontes -- prefixo da URL, cookie `django_language` e Accept-Language do
navegador. Corrigir isso view a view seria espalhar a mesma regra por
dezenas de lugares e esquecer algum. Aqui ha um ponto unico, ANTES do
LocaleMiddleware, que fecha as tres portas de uma vez:

  1. URL com prefixo de outro idioma  -> redireciona para o /pt/ equivalente;
  2. cookie `django_language` antigo  -> ignorado no pedido e apagado na resposta;
  3. Accept-Language do navegador     -> ignorado.

Sem nenhuma das tres, o LocaleMiddleware so pode concluir "pt" (pelo
prefixo /pt/ ou por settings.LANGUAGE_CODE) -- e continua fazendo todo o
resto do trabalho dele normalmente.

POR QUE NAO BASTA CHAMAR translation.activate("pt") DEPOIS
----------------------------------------------------------
Porque `reverse()` monta o prefixo da URL a partir do idioma ativo. Se o
pedido chegasse em /fr/ e nos apenas ativassemos "pt" na renderizacao, a
pagina sairia em /fr/ com todos os links e actions de formulario
apontando para /pt/. Redirecionar antes mantem URL, links e formularios
coerentes entre si.
"""

from django.conf import settings
from django.http import HttpResponseRedirect

# Metodos que podem ser repetidos sem efeito colateral. Para eles, um 302
# comum basta.
METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class RedirecionamentoQuePreservaOEnvio(HttpResponseRedirect):
    """
    307: o navegador repete o pedido no novo endereco COM o metodo e o
    corpo originais.

    Um 302 sobre um POST vira um GET e o corpo se perde. Quem tivesse uma
    pagina em /fr/ aberta antes desta mudanca e a submetesse depois
    perderia o que digitou; com 307 o envio chega inteiro em /pt/.
    """

    status_code = 307

# O unico idioma em que a interface e apresentada.
#
# NAO confundir com settings.LANGUAGES, que continua com os quatro
# idiomas porque alimenta `Letter.language`, `DocumentTemplate.language`
# e as opcoes da etapa 5 -- ou seja, o idioma do DOCUMENTO.
IDIOMA_DA_INTERFACE = "pt"


def _prefixos_de_outros_idiomas():
    """Os prefixos de URL que devem ser trazidos para o portugues."""
    return {code for code, _nome in settings.LANGUAGES if code != IDIOMA_DA_INTERFACE}


def caminho_em_portugues(caminho):
    """
    `/fr/letters/new/` -> `/pt/letters/new/`.

    None quando nao ha nada a fazer: o caminho ja esta em portugues
    (`/pt/...`) ou nao comeca por um prefixo de idioma (`/healthz/`,
    `/i18n/setlang/`). Comparar com a lista de idiomas -- em vez de
    recortar o que parecer um prefixo -- e o que garante que
    `/admin/`, `/pt-br/` ou qualquer outra coisa nao sejam mexidos por
    engano, e que o redirecionamento sempre termine.
    """
    partes = caminho.split("/", 2)
    if len(partes) < 2 or partes[1] not in _prefixos_de_outros_idiomas():
        return None
    resto = partes[2] if len(partes) > 2 else ""
    return f"/{IDIOMA_DA_INTERFACE}/{resto}"


class InterfaceEmPortuguesMiddleware:
    """
    Garante que a interface seja renderizada em portugues, venha o pedido
    de onde vier. Precisa ficar ANTES do LocaleMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        destino = caminho_em_portugues(request.path_info)
        if destino is not None:
            # A query string vai inteira, sem interpretacao: e o que
            # preserva `?next=`, `?secao=` e afins. Um `next` que aponte
            # para /fr/ passa por aqui de novo no salto seguinte e
            # tambem acaba em /pt/.
            query = request.META.get("QUERY_STRING")
            url = f"{destino}?{query}" if query else destino
            if request.method in METODOS_SEGUROS:
                return HttpResponseRedirect(url)
            return RedirecionamentoQuePreservaOEnvio(url)

        # Quem ja trocou de idioma antes carrega o cookie no navegador.
        # Tirar do pedido impede que o LocaleMiddleware o use; apagar na
        # resposta evita que ele volte a aparecer a cada visita.
        cookie_antigo = request.COOKIES.pop(settings.LANGUAGE_COOKIE_NAME, None)
        request.META.pop("HTTP_ACCEPT_LANGUAGE", None)

        response = self.get_response(request)

        if cookie_antigo is not None and cookie_antigo != IDIOMA_DA_INTERFACE:
            response.delete_cookie(
                settings.LANGUAGE_COOKIE_NAME,
                path=settings.LANGUAGE_COOKIE_PATH,
                domain=settings.LANGUAGE_COOKIE_DOMAIN,
            )
        return response
