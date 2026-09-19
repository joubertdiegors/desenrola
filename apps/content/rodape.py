"""
O rodapé como CONTEÚDO RICO: o que o Backoffice grava, o que o site desenha.

O QUE ESTE MÓDULO É
-------------------
Três coisas, e só elas:

  1. `sanitizar(html)`    -- o HTML que veio do editor, reduzido a uma
                             lista fechada de marcações e atributos;
  2. `renderizar(html)`   -- o HTML já sanitizado, com os ATALHOS
                             (`{ano}`, `{nome_do_site}`, ...) trocados
                             pelos dados de verdade;
  3. `HTML_PADRAO`        -- o rodapé com que a Home nasce, escrito com
                             os mesmos atalhos, para nada ser duplicado;
  4. `sanitizar_documento` / `renderizar_documento` -- o mesmo par, para
                             os documentos legais (ver abaixo).

POR QUE HÁ UM `mark_safe` AQUI -- O ÚNICO DO PROJETO
------------------------------------------------------
O projeto proíbe HTML cru na página, e com razão. O rodapé é a exceção
deliberada: quem administra ESCREVE marcação (títulos, links, listas,
alinhamento), e escapá-la a tornaria inútil. A proteção, então, não é o
escape -- é `sanitizar`: cada tag e cada atributo passam por uma lista
fechada, `href` só aceita `http(s)`, `mailto:`, `tel:`, caminho do site,
âncora ou atalho, `style` só aceita um punhado de propriedades com
valores sem `url(`, e `<script>`, `<style>`, `<iframe>`, `on*` e tudo o
mais simplesmente não sobrevive. Só o resultado DISSO recebe
`mark_safe`, e só neste arquivo.

OS ATALHOS NÃO DUPLICAM DADO NENHUM
-----------------------------------
Nome do site, e-mail, telefone, endereço e redes vêm de Sistema; os
links legais vêm das páginas legais publicadas; os links de navegação
vêm do MESMO cadastro de itens da barra superior. O editor oferece
`{nome_do_site}` em vez de um campo "nome" próprio -- é o que impede o
rodapé de virar uma segunda fonte de verdade.

LINK QUE NÃO LEVA A LUGAR NENHUM NÃO É DESENHADO
------------------------------------------------
`{url_termos}` sem página publicada, `mailto:{email_contato}` sem e-mail
cadastrado: o atalho resolve para vazio, e `renderizar` REMOVE o `<a>`
inteiro. É a mesma regra do resto do site -- um link para o nada é pior
do que link nenhum.

OS DOCUMENTOS LEGAIS PASSAM PELA MESMA RECONSTRUÇÃO
---------------------------------------------------
Termos de uso e Privacidade são escritos no mesmo editor do rodapé
(Sistema › Documentos legais) e reconstruídos pela mesma classe -- com
uma lista declarada logo abaixo da outra, `TAGS_DO_DOCUMENTO`: ganham
`h2` (o título de um documento) e `img`, e perdem os desenhos inline
(`svg`), que num texto jurídico não têm função. Os atalhos também não
valem ali: não há o que trocar, e um `href` com `{...}` é descartado.

A imagem só aceita arquivo da BIBLIOTECA DE IMAGENS do próprio site
(`MEDIA_URL` + `assets/`, com extensão de imagem) -- nunca endereço de
fora, nunca `data:`. Sem `src` aceito, o `<img>` inteiro sai.

`renderizar_documento` passa pelo MESMO `mark_safe` de `renderizar`:
continua havendo um só no projeto, dentro de `_marcado_como_seguro`.
"""

import datetime
import html
import re
from html.parser import HTMLParser

from django.conf import settings
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

# ---------------------------------------------------------------------------
# A lista fechada
# ---------------------------------------------------------------------------

# O que o editor produz, e nada além disso. `font` porque o comando de
# tamanho dos navegadores gera `<font size>` -- e é mais honesto aceitá-lo
# do que fingir que ele não existe. `svg` e filhos, para os ícones inline
# do editor -- com atributos de DESENHO só, nunca `href`, `xlink` ou `on*`.
TAGS = frozenset(
    {
        "p", "br", "h3", "h4", "strong", "b", "em", "i", "u", "s", "strike",
        "a", "ul", "ol", "li", "blockquote", "hr", "span", "div", "font",
        "svg", "path", "circle", "rect",
    }
)

# Os documentos legais: a mesma lista, com título de documento (`h2`) e
# imagem da biblioteca -- e sem os desenhos inline do rodapé.
TAGS_DO_DOCUMENTO = (TAGS - {"svg", "path", "circle", "rect"}) | {"h2", "img"}

# Somem COM o conteúdo: o texto dentro de um `<script>` não é texto.
TAGS_QUE_LEVAM_O_CONTEUDO = frozenset(
    {"script", "style", "iframe", "object", "embed", "template", "noscript",
     "textarea", "select", "title", "head", "svg:script"}
)

VAZIAS = frozenset({"br", "hr", "img", "path", "circle", "rect"})

ATRIBUTOS = {
    "a": {"href", "target", "rel", "title"},
    "font": {"size", "color"},
    # Só nos documentos legais -- o rodapé não tem `img` na lista.
    "img": {"src", "alt", "width", "height"},
    "svg": {"width", "height", "viewbox", "fill", "stroke", "stroke-width",
            "stroke-linecap", "stroke-linejoin", "xmlns"},
    "path": {"d", "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin"},
    "circle": {"cx", "cy", "r", "fill", "stroke", "stroke-width"},
    "rect": {"x", "y", "width", "height", "rx", "ry", "fill", "stroke", "stroke-width"},
}
ATRIBUTO_COMUM = {"style"}

# `viewBox` tem maiúscula; o parser entrega tudo em minúsculas.
NOME_CERTO = {"viewbox": "viewBox"}

PROPRIEDADES_DE_ESTILO = frozenset(
    {
        "text-align", "color", "font-size", "font-weight", "font-style",
        "text-decoration", "line-height", "letter-spacing", "height",
        "display", "flex-wrap", "flex", "gap", "min-width",
        "margin", "margin-top", "margin-bottom", "padding-left",
    }
)
# Valor de estilo: letras, números, `#`, `%`, `.`, `,`, `-`, espaço e
# parênteses (para `rgb(...)`). Sem aspas, sem `;`, sem `\`, sem `/`.
VALOR_DE_ESTILO = re.compile(r"^[\w#%.,\-\s()]{1,60}$")
VALOR_PROIBIDO = re.compile(r"url|expression|javascript|import|\\", re.I)
COR = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]+|currentColor|rgba?\([\d\s,.%]+\))$")
NUMERO_OU_MEDIDA = re.compile(r"^-?[\d.]+(px|em|rem|%)?$")
SO_TEXTO_SIMPLES = re.compile(r"^[\w\s#.,\-]{1,400}$")
CAMINHO_SVG = re.compile(r"^[\d\s.,\-a-zA-Z]{1,2000}$")
ATALHO = re.compile(r"\{[a-z_]+\}")
INICIO_DE_HREF = re.compile(r"^(https?://|mailto:|tel:|/|#|\{[a-z_]+\})")
# O arquivo de uma imagem da biblioteca, depois do prefixo dela.
ARQUIVO_DE_IMAGEM = re.compile(r"^[\w\-./]+\.(png|jpe?g|gif|webp)$", re.I)
CONTROLE = re.compile(r"[\x00-\x1f\x7f]")

TAMANHO_MAXIMO = 40_000
# Um documento jurídico é bem maior que um rodapé. O formulário recusa o
# que passar disto -- com mensagem, e não cortando o texto em silêncio.
TAMANHO_MAXIMO_DO_DOCUMENTO = 200_000


def _href_aceito(valor):
    """
    `http(s)`, `mailto:`, `tel:`, caminho, âncora ou atalho -- e mais nada.

    O parser já converteu entidades; o que sobra de truque é espaço e
    caractere de controle no meio de `java script:`, e isso sai antes
    da conferência.
    """
    limpo = re.sub(r"[\s\x00-\x1f\x7f]", "", valor or "")
    if not limpo or len(limpo) > 2000:
        return None
    if not INICIO_DE_HREF.match(limpo.lower()):
        return None
    return limpo


def _prefixo_da_biblioteca():
    """Onde a biblioteca de imagens publica os arquivos: `MEDIA_URL` + `assets/`."""
    base = settings.MEDIA_URL or "/media/"
    if not base.startswith(("/", "http://", "https://")):
        base = "/" + base
    return base.rstrip("/") + "/assets/"


def _src_aceito(valor):
    """
    Só arquivo da biblioteca de imagens do site, com extensão de imagem.

    Nada de endereço de fora (uma imagem externa num documento é um
    rastreador de quem o lê), nada de `data:` e nada de `..` para sair
    da pasta.
    """
    limpo = re.sub(r"[\s\x00-\x1f\x7f]", "", valor or "")
    prefixo = _prefixo_da_biblioteca()
    if not limpo.startswith(prefixo):
        return None
    resto = limpo[len(prefixo):]
    if ".." in resto or "//" in resto or resto.startswith("/"):
        return None
    if not ARQUIVO_DE_IMAGEM.match(resto):
        return None
    return limpo


def _estilo_aceito(valor):
    """Só as propriedades da lista, cada uma com um valor inofensivo."""
    aceitas = []
    for declaracao in (valor or "").split(";"):
        if ":" not in declaracao:
            continue
        nome, _dois_pontos, conteudo = declaracao.partition(":")
        nome, conteudo = nome.strip().lower(), conteudo.strip()
        if nome not in PROPRIEDADES_DE_ESTILO:
            continue
        if not VALOR_DE_ESTILO.match(conteudo) or VALOR_PROIBIDO.search(conteudo):
            continue
        aceitas.append(f"{nome}:{conteudo}")
    return ";".join(aceitas) if aceitas else None


def _atributo_aceito(tag, nome, valor, atalhos=True):
    """
    O valor a gravar para `nome` em `tag`, ou None para descartá-lo.

    `atalhos=False` (os documentos legais) recusa `href` com `{...}`: lá
    não há quem troque o atalho pelo endereço de verdade.
    """
    valor = valor if valor is not None else ""
    if nome == "style":
        return _estilo_aceito(valor)
    if nome not in ATRIBUTOS.get(tag, set()):
        return None
    if tag == "img":
        if nome == "src":
            return _src_aceito(valor)
        if nome == "alt":
            return CONTROLE.sub("", valor)[:200]
        return valor if NUMERO_OU_MEDIDA.match(valor) else None
    if tag == "a":
        if nome == "href":
            aceito = _href_aceito(valor)
            if aceito and not atalhos and "{" in aceito:
                return None
            return aceito
        if nome == "target":
            return "_blank" if valor == "_blank" else None
        if nome == "rel":
            return "noopener noreferrer"
        return valor[:200] if SO_TEXTO_SIMPLES.match(valor) else None
    if tag == "font":
        if nome == "size":
            return valor if re.match(r"^[1-7]$", valor) else None
        return valor if COR.match(valor) else None
    # SVG: cores, medidas, o caminho do desenho e o namespace.
    if nome in {"fill", "stroke"}:
        return valor if COR.match(valor) else None
    if nome == "d":
        return valor if CAMINHO_SVG.match(valor) else None
    if nome == "viewbox":
        return valor if re.match(r"^[\d\s.\-]{1,40}$", valor) else None
    if nome == "xmlns":
        return valor if valor == "http://www.w3.org/2000/svg" else None
    if nome in {"stroke-linecap", "stroke-linejoin"}:
        return valor if valor in {"round", "butt", "square", "miter", "bevel"} else None
    return valor if NUMERO_OU_MEDIDA.match(valor) else None


class _Sanitizador(HTMLParser):
    """
    Reconstrói o HTML só com o que a lista fechada deixa passar.

    `tags` é a lista (a do rodapé, por padrão, ou `TAGS_DO_DOCUMENTO`);
    `atalhos` diz se um `href` com `{...}` pode ficar.
    """

    def __init__(self, tags=TAGS, atalhos=True):
        super().__init__(convert_charrefs=True)
        self.tags = tags
        self.atalhos = atalhos
        self.partes = []
        self.abertas = []
        self.engolindo = 0  # dentro de uma tag que leva o conteúdo junto

    # -- tags ---------------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        if self.engolindo:
            if tag in TAGS_QUE_LEVAM_O_CONTEUDO:
                self.engolindo += 1
            return
        if tag in TAGS_QUE_LEVAM_O_CONTEUDO:
            self.engolindo = 1
            return
        if tag not in self.tags:
            return  # desconhecida: some a tag, fica o texto de dentro
        aceitos = []
        for nome, valor in attrs:
            nome = nome.lower()
            if nome.startswith("on"):
                continue
            if nome not in ATRIBUTO_COMUM and nome not in ATRIBUTOS.get(tag, set()):
                continue
            limpo = _atributo_aceito(tag, nome, valor, self.atalhos)
            if limpo is not None:
                aceitos.append((NOME_CERTO.get(nome, nome), limpo))
        # Imagem sem endereço aceito não é imagem: sai inteira, em vez de
        # ficar como uma moldura quebrada no documento.
        if tag == "img" and not any(n == "src" for n, _v in aceitos):
            return
        if tag == "a" and any(n == "target" for n, _v in aceitos):
            aceitos = [(n, v) for n, v in aceitos if n != "rel"]
            aceitos.append(("rel", "noopener noreferrer"))
        marcados = "".join(f' {n}="{html.escape(v, quote=True)}"' for n, v in aceitos)
        if tag in VAZIAS:
            fecho = ">" if tag in {"br", "hr", "img"} else "/>"
            self.partes.append(f"<{tag}{marcados}{fecho}")
            return
        self.partes.append(f"<{tag}{marcados}>")
        self.abertas.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in self.tags and tag not in VAZIAS and not self.engolindo:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.engolindo:
            if tag in TAGS_QUE_LEVAM_O_CONTEUDO:
                self.engolindo -= 1
            return
        if tag not in self.abertas:
            return
        # Fecha o que ficou aberto por dentro, na ordem certa.
        while self.abertas:
            aberta = self.abertas.pop()
            self.partes.append(f"</{aberta}>")
            if aberta == tag:
                break

    # -- o resto -----------------------------------------------------------

    def handle_data(self, data):
        if not self.engolindo:
            self.partes.append(html.escape(data, quote=False))

    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        pass

    def handle_pi(self, data):
        pass

    def resultado(self):
        while self.abertas:
            self.partes.append(f"</{self.abertas.pop()}>")
        return "".join(self.partes)


def sanitizar(bruto):
    """
    O HTML do editor, reduzido à lista fechada. Idempotente: sanitizar
    duas vezes dá o mesmo resultado, então gravar o resultado e
    sanitizar de novo ao desenhar não perde nada.
    """
    return _reconstruir(bruto, _Sanitizador(), TAMANHO_MAXIMO)


def sanitizar_documento(bruto):
    """
    O HTML de um documento legal, reduzido à lista DOS DOCUMENTOS
    (`TAGS_DO_DOCUMENTO`), sem atalhos. Idempotente, como `sanitizar`.
    """
    return _reconstruir(
        bruto, _Sanitizador(TAGS_DO_DOCUMENTO, atalhos=False), TAMANHO_MAXIMO_DO_DOCUMENTO
    )


def _reconstruir(bruto, parser, limite):
    parser.feed((bruto or "")[:limite])
    parser.close()
    return parser.resultado().strip()


MARCACAO = re.compile(r"<[^>]+>")


def tem_conteudo(html_limpo):
    """
    Há algo para LER? Texto de verdade -- não só marcação, espaço e
    `&nbsp;` -- ou uma imagem. Um editor esvaziado deixa `<p><br></p>`,
    e isso não é documento.
    """
    if "<img" in (html_limpo or ""):
        return True
    texto = html.unescape(MARCACAO.sub("", html_limpo or ""))
    return bool(texto.replace("\xa0", " ").strip())


# ---------------------------------------------------------------------------
# Os atalhos
# ---------------------------------------------------------------------------

# Nome do atalho -> o que a tela do editor diz sobre ele. A ORDEM é a da
# tela. Todos resolvem para dados que já existem em outro lugar do sistema.
ATALHOS = (
    ("{ano}", _("O ano corrente")),
    ("{nome_do_site}", _("O nome do site, de Sistema")),
    ("{menu}", _("Os links da barra superior, do cadastro de itens do menu")),
    ("mailto:{email_contato}", _("Como endereço de um link: o e-mail de contato de Sistema")),
    ("{telefone}", _("O telefone de contato, de Sistema")),
    ("{endereco}", _("O endereço, de Sistema")),
    ("{redes_sociais}", _("As redes sociais configuradas em Sistema, com ícone")),
    ("{url_termos}", _("Como endereço de um link: a página de Termos de uso")),
    ("{url_privacidade}", _("Como endereço de um link: a página de Privacidade")),
    ("{url_parceiros}", _("Como endereço de um link: a página de todos os parceiros")),
    ("{url_home}", _("Como endereço de um link: a página inicial")),
)

# O rodapé com que a Home nasce -- a composição da referência visual
# (marca, uma linha de links, copyright), escrita SÓ com atalhos: nenhum
# nome, e-mail ou endereço fica gravado aqui.
HTML_PADRAO = (
    '<h3 style="text-align:center">{nome_do_site}</h3>'
    '<p style="text-align:center">{menu} '
    '<a href="mailto:{email_contato}">Contato</a> '
    '<a href="{url_termos}">Termos de uso</a> '
    '<a href="{url_privacidade}">Privacidade</a></p>'
    '<p style="text-align:center"><font size="2">© {ano} {nome_do_site}</font></p>'
)


def _e(valor):
    return html.escape(str(valor or ""), quote=True)


def _menu_renderizado(menu_itens, url_home):
    """
    Os mesmos itens da barra superior, como links. Uma âncora da Home
    (`#faq`) ganha o caminho da Home na frente: o rodapé aparece em
    outras páginas também, e `#faq` sozinho lá não levaria a nada.
    """
    links = []
    for item in menu_itens or ():
        destino = getattr(item, "destination", "") or ""
        if destino.startswith("#"):
            destino = f"{url_home}{destino}"
        rotulo = getattr(item, "label", "") or ""
        if destino and rotulo:
            links.append(f'<a href="{_e(destino)}">{_e(rotulo)}</a>')
    return " ".join(links)


def _redes_renderizadas(redes):
    links = []
    for rede in redes or ():
        links.append(
            f'<a class="site-footer-social" href="{_e(rede.url)}" rel="noopener noreferrer" '
            f'target="_blank" aria-label="{_e(rede.nome)}">'
            f'<i class="ph {_e(rede.icone)}" aria-hidden="true"></i></a>'
        )
    return " ".join(links)


def valores_dos_atalhos(site_config, paginas_legais, menu_itens=()):
    """
    Cada atalho e o que ele vale AGORA. Tudo já escapado: o resultado
    entra direto no HTML sanitizado.
    """
    url_home = reverse("core:home")
    contato = getattr(site_config, "contact", None)
    email = getattr(contato, "email", "") or ""
    telefone = getattr(contato, "phone", "") or ""
    endereco = getattr(contato, "address", "") or ""
    return {
        "{ano}": str(datetime.date.today().year),
        "{nome_do_site}": _e(getattr(site_config, "name", "")),
        "{menu}": _menu_renderizado(menu_itens, url_home),
        "{email_contato}": _e(email),
        "{telefone}": _e(telefone),
        "{endereco}": "<br>".join(_e(linha) for linha in endereco.splitlines()),
        "{redes_sociais}": _redes_renderizadas(getattr(site_config, "social", ())),
        "{url_termos}": (
            reverse("core:legal_termos")
            if getattr(paginas_legais, "termos_de_uso", False)
            else ""
        ),
        "{url_privacidade}": (
            reverse("core:legal_privacidade")
            if getattr(paginas_legais, "privacidade", False)
            else ""
        ),
        "{url_parceiros}": reverse("core:parceiros"),
        "{url_home}": url_home,
    }


# Um `<a>` cujo endereço ficou vazio depois dos atalhos -- página legal
# sem texto, e-mail de contato em branco. Sai inteiro, com o rótulo.
LINK_MORTO = re.compile(r'<a href="(|mailto:|tel:)"[^>]*>.*?</a>\s?', re.S)
ATALHO_QUE_SOBROU = re.compile(r"\{[a-z_]+\}")


def _marcado_como_seguro(limpo):
    """
    O único ponto do projeto que marca HTML como seguro. Só recebe o que
    acabou de sair de `sanitizar` ou de `sanitizar_documento` -- ver o
    cabeçalho do módulo.
    """
    return mark_safe(limpo)  # noqa: S308 -- sanitizado por quem chama; ver o cabeçalho


def renderizar(html_gravado, site_config, paginas_legais, menu_itens=()):
    """
    O rodapé pronto para a página: sanitizado de novo (o banco não é
    confiável por definição), com os atalhos trocados e os links mortos
    removidos. É o ÚNICO ponto do projeto que devolve HTML marcado como
    seguro -- ver o cabeçalho do módulo.
    """
    limpo = sanitizar(html_gravado if html_gravado is not None else HTML_PADRAO)
    if not limpo:
        limpo = sanitizar(HTML_PADRAO)
    valores = valores_dos_atalhos(site_config, paginas_legais, menu_itens)
    for atalho, valor in valores.items():
        limpo = limpo.replace(atalho, valor)
    limpo = LINK_MORTO.sub("", limpo)
    # Um atalho que ninguém conhece não vira texto na página.
    limpo = ATALHO_QUE_SOBROU.sub("", limpo)
    return _marcado_como_seguro(limpo)


def renderizar_documento(html_gravado):
    """
    Um documento legal pronto para a página: sanitizado de novo com a
    lista dos documentos -- o banco não é confiável por definição. Sem
    atalhos: não há o que trocar.
    """
    return _marcado_como_seguro(sanitizar_documento(html_gravado))
