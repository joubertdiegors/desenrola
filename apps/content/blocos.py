"""
Documentos legais em BLOCOS estruturados (Rodada 22).

O QUE ESTE MÓDULO É
--------------------
O contrato de um documento legal (Termos de uso, Privacidade) escrito
por BLOCOS -- parágrafo, título, lista, citação, destaque, botão,
separador, imagem, galeria, tabela, HTML -- em vez de um único HTML
corrido. Cada bloco é um dicionário; o documento inteiro é uma LISTA de
blocos, gravada como JSON em `ContentTranslation.content` quando o
`ContentBlock.kind` é `STRUCTURED`.

POR QUE NÃO UM MODELO PRÓPRIO POR BLOCO
------------------------------------------
Um `Model` por bloco (com `order`, `parent`, tabelas de tradução
próprias) é a arquitetura "certa" para um CMS genérico -- e é
exatamente o tamanho de refatoração que esta rodada pede para NÃO
fazer. JSON dentro do campo que já existe (`ContentTranslation.content`)
resolve o mesmo problema -- ordem, tipo, conteúdo e configuração
persistentes -- sem tocar no esquema além de UM novo `Kind`. O dia em
que um segundo lugar do site precisar de blocos, promover isto a
modelo próprio é um passo isolado; a FORMA dos blocos already é
genérica (nada aqui é específico de "documento legal").

A SEGURANÇA CONTINUA SENDO A DE SEMPRE
------------------------------------------
O fragmento de HTML de cada bloco de texto passa por
`rodape.sanitizar_documento` -- a MESMA lista fechada de sempre. A
imagem nunca guarda uma URL: guarda o `pk` de um `content.Asset` da
biblioteca, e o endereço é lido de lá na hora de desenhar -- não há
como um bloco de imagem apontar para fora do site. O bloco HTML (a
válvula de escape) passa pela MESMA sanitização que qualquer texto.

Contexto do módulo: `sanitizar_blocos` roda no SALVAMENTO;
`renderizar_blocos` roda na LEITURA (visualização e página pública) --
e sanitiza de novo, porque o banco não é confiável por definição (a
mesma regra de `rodape.py`).
"""

import json
import re
import uuid
from html.parser import HTMLParser

from django.utils.html import escape
from django.utils.translation import gettext_lazy as _

from . import rodape
from .models import Asset

# ---------------------------------------------------------------------------
# Os tipos de bloco
# ---------------------------------------------------------------------------

# Os blocos cujo conteúdo principal é um FRAGMENTO DE HTML rico (o texto
# em si, sem a tag externa -- ela é decidida por `TAG_EXTERNA` abaixo).
TIPOS_DE_TEXTO = ("paragraph", "heading", "quote", "list", "highlight", "button")

TAG_EXTERNA = {
    "paragraph": "p",
    "heading": "h2",
    "quote": "blockquote",
    # "list" grava o próprio <ul>/<ol> em `html` (é o que o comando de
    # lista do editor produz) -- não leva tag externa.
    "highlight": None,
    "button": None,
}

# Categoria, tipo, rótulo, descrição e ícone (Phosphor) -- a ordem É a
# do menu "+ Bloco" (referência "Editor Conteudo Estatico").
CATALOGO = (
    (_("Texto"), "paragraph", _("Parágrafo"), _("Texto corrido"), "ph-text-align-left"),
    (_("Texto"), "heading", _("Título de seção"), _("H2 · entra na estrutura"), "ph-text-h"),
    (_("Texto"), "list", _("Lista"), _("Com marcador ou numerada"), "ph-list-bullets"),
    (_("Texto"), "quote", _("Citação"), _("Bloco recuado"), "ph-quotes"),
    (_("Mídia"), "image", _("Imagem"), _("Ancorada, o texto contorna"), "ph-image"),
    (_("Mídia"), "gallery", _("Galeria"), _("Duas ou três lado a lado"), "ph-images-square"),
    (_("Estrutura"), "highlight", _("Destaque"), _("Aviso com ícone e borda"), "ph-shield-check"),
    (_("Estrutura"), "table", _("Tabela"), _("Colunas e cabeçalho"), "ph-table"),
    (_("Estrutura"), "button", _("Botão / link"), _("Chamada para ação"), "ph-cursor-click"),
    (_("Estrutura"), "separator", _("Separador"), _("Linha entre seções"), "ph-minus"),
    (_("Estrutura"), "html", _("HTML"), _("Trecho bruto, sanitizado ao salvar"), "ph-code"),
)

TIPOS_VALIDOS = frozenset(tipo for _cat, tipo, _r, _d, _i in CATALOGO)

LARGURAS_DE_IMAGEM = (20, 25, 30, 36, 40, 50, 60, 70)
ANCORAS = ("none", "left", "right")

# Estilo do BLOCO (não do fragmento de texto dentro dele) -- entrelinha e
# espaço depois, aplicados na `<div class="legal-bloco">` que envolve
# qualquer tipo. Ausente = a entrelinha/espaço padrão de `.legal-texto`.
ALTURAS_DE_LINHA = ("1.4", "1.55", "1.7", "2")
ESPACAMENTOS_APOS = (0, 8, 16, 24, 32, 48)

# Os tipos que uma pessoa pode trocar um pelo outro sem perder o texto
# (todos guardam só `html`, sem campo próprio) -- o seletor "Tipo" da
# barra. "list" fica de fora: é a própria marcação de lista em `html`,
# não um fragmento que vire título ou citação sem perder a estrutura.
TIPOS_CONVERSIVEIS = ("paragraph", "heading", "quote")


def catalogo_para_o_menu():
    """O "+ Bloco", agrupado por categoria, na ordem do catálogo."""
    grupos = {}
    for categoria, tipo, rotulo, descricao, icone in CATALOGO:
        grupos.setdefault(str(categoria), []).append(
            {"tipo": tipo, "rotulo": str(rotulo), "descricao": str(descricao), "icone": icone}
        )
    return [{"categoria": nome, "itens": itens} for nome, itens in grupos.items()]


def _id():
    return uuid.uuid4().hex[:10]


def bloco_novo(tipo, texto_inicial=""):
    """Um bloco em branco do `tipo` pedido, pronto para entrar na lista."""
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"tipo de bloco desconhecido: {tipo}")
    base = {"id": _id(), "type": tipo, "mobile": {"visible": True}}
    if tipo in TIPOS_DE_TEXTO or tipo == "html":
        base["html"] = escape(texto_inicial) if texto_inicial else ""
    if tipo == "button":
        base["href"] = ""
    if tipo == "image":
        base.update({"asset_id": None, "alt": "", "desktop": {"anchor": "none", "width": 36}})
    if tipo == "gallery":
        base["asset_ids"] = []
    if tipo == "table":
        base.update({"cabecalho": True, "linhas": [["", ""], ["", ""]]})
    return base


# ---------------------------------------------------------------------------
# Sanitização -- o que entra no banco
# ---------------------------------------------------------------------------


def _sanitizar_html_do_bloco(valor):
    limpo = rodape.sanitizar_documento(str(valor or ""))
    return limpo


def _href_do_documento(valor):
    """O mesmo `_href_aceito` do rodapé, sem atalhos -- documento não tem `{...}`."""
    aceito = rodape._href_aceito(valor)  # noqa: SLF001 -- mesmo pacote, mesma regra
    if aceito and "{" in aceito:
        return ""
    return aceito or ""


def _largura_aceita(valor):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return 36
    if numero in LARGURAS_DE_IMAGEM:
        return numero
    return min(LARGURAS_DE_IMAGEM, key=lambda v: abs(v - numero))


def _mobile_aceito(bruto):
    bruto = bruto if isinstance(bruto, dict) else {}
    return {"visible": bool(bruto.get("visible", True))}


def _altura_de_linha_aceita(valor):
    return valor if valor in ALTURAS_DE_LINHA else None


def _espacamento_aceito(valor):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero in ESPACAMENTOS_APOS else None


def sanitizar_bloco(bruto):
    """
    Um bloco pronto para o banco, ou `None` se `bruto` não for um bloco
    reconhecível -- descartado em silêncio (a mesma regra de um `<script>`
    que o parser do rodapé engole): o que sobrevive é sempre válido.
    """
    if not isinstance(bruto, dict):
        return None
    tipo = bruto.get("type")
    if tipo not in TIPOS_VALIDOS:
        return None

    limpo = {
        "id": str(bruto.get("id") or _id())[:40],
        "type": tipo,
        "mobile": _mobile_aceito(bruto.get("mobile")),
    }
    altura = _altura_de_linha_aceita(bruto.get("line_height"))
    if altura:
        limpo["line_height"] = altura
    espaco = _espacamento_aceito(bruto.get("spacing_after"))
    if espaco is not None:
        limpo["spacing_after"] = espaco

    if tipo in TIPOS_DE_TEXTO or tipo == "html":
        limpo["html"] = _sanitizar_html_do_bloco(bruto.get("html"))
    if tipo == "button":
        limpo["href"] = _href_do_documento(bruto.get("href"))
    if tipo == "image":
        asset_id = bruto.get("asset_id")
        try:
            asset_id = int(asset_id) if asset_id not in (None, "") else None
        except (TypeError, ValueError):
            asset_id = None
        desktop = bruto.get("desktop") if isinstance(bruto.get("desktop"), dict) else {}
        ancora = desktop.get("anchor")
        limpo.update(
            {
                "asset_id": asset_id,
                "alt": escape(str(bruto.get("alt") or "")[:200]),
                "desktop": {
                    "anchor": ancora if ancora in ANCORAS else "none",
                    "width": _largura_aceita(desktop.get("width")),
                },
            }
        )
    if tipo == "gallery":
        brutos = bruto.get("asset_ids")
        ids = []
        if isinstance(brutos, list):
            for item in brutos:
                try:
                    ids.append(int(item))
                except (TypeError, ValueError):
                    continue
        limpo["asset_ids"] = ids[:6]
    if tipo == "table":
        linhas_brutas = bruto.get("linhas")
        linhas = []
        if isinstance(linhas_brutas, list):
            for linha in linhas_brutas[:40]:
                if not isinstance(linha, list):
                    continue
                linhas.append([escape(str(celula)[:400]) for celula in linha[:12]])
        limpo["linhas"] = linhas or [["", ""], ["", ""]]
        limpo["cabecalho"] = bool(bruto.get("cabecalho", True))

    return limpo


def sanitizar_blocos(bruto):
    """
    A lista inteira, pronta para o banco. Nunca estoura: item que não é
    um bloco reconhecível é descartado; a lista vazia é um documento
    vazio (o mesmo estado de sempre -- a página some do ar).

    O limite de tamanho é o MESMO dos documentos de HTML corrido
    (`rodape.TAMANHO_MAXIMO_DO_DOCUMENTO`), medido no JSON inteiro: um
    documento jurídico que caiba em 200 KB de HTML corrido cabe na
    mesma medida em blocos.
    """
    if not isinstance(bruto, list):
        return []
    limpos = [sanitizar_bloco(item) for item in bruto[:300]]
    limpos = [b for b in limpos if b is not None]
    # Um estouro de tamanho não trava o salvamento -- corta pelo fim,
    # como qualquer lista longa demais. É um caso extremo (bem além do
    # que um documento jurídico de verdade usa).
    while limpos:
        if len(json.dumps(limpos, ensure_ascii=False)) <= rodape.TAMANHO_MAXIMO_DO_DOCUMENTO:
            break
        limpos.pop()
    return limpos


def blocos_tem_conteudo(blocos):
    """
    Há algo para LER? A mesma pergunta de `rodape.tem_conteudo`, agora
    pela lista -- um separador sozinho não é documento, pela mesma
    razão que `<p><br></p>` não era: marcação sem conteúdo.
    """
    for bloco in blocos or []:
        tipo = bloco.get("type")
        if tipo in TIPOS_DE_TEXTO or tipo == "html":
            if rodape.tem_conteudo(bloco.get("html") or ""):
                return True
        elif tipo == "image" and bloco.get("asset_id"):
            return True
        elif tipo == "gallery" and bloco.get("asset_ids"):
            return True
        elif tipo == "table" and any(c.strip() for linha in bloco.get("linhas", []) for c in linha):
            return True
    return False


# ---------------------------------------------------------------------------
# Leitura -- os assets citados, para o desenho
# ---------------------------------------------------------------------------


def _assets_dos_blocos(blocos):
    ids = set()
    for bloco in blocos:
        if bloco.get("type") == "image" and bloco.get("asset_id"):
            ids.add(bloco["asset_id"])
        if bloco.get("type") == "gallery":
            ids.update(bloco.get("asset_ids") or [])
    if not ids:
        return {}
    return {a.pk: a for a in Asset.objects.filter(pk__in=ids, is_active=True)}


# ---------------------------------------------------------------------------
# Desenho -- o HTML final, pronto para `rodape._marcado_como_seguro`
# ---------------------------------------------------------------------------


def _classe_do_bloco(bloco):
    classes = ["legal-bloco", f"legal-bloco-{bloco['type']}"]
    if not bloco.get("mobile", {}).get("visible", True):
        classes.append("legal-bloco-oculto-no-mobile")
    return " ".join(classes)


def _estilo_do_bloco(bloco):
    """
    Entrelinha e espaço depois -- gerados por este módulo (nunca por
    HTML de quem administra), então dispensam a sanitização de estilo
    do rodapé; `sanitizar_bloco` já garante que só um valor da lista
    fechada chega aqui.
    """
    declaracoes = []
    altura = bloco.get("line_height")
    if altura in ALTURAS_DE_LINHA:
        declaracoes.append(f"line-height:{altura}")
    espaco = bloco.get("spacing_after")
    if espaco in ESPACAMENTOS_APOS:
        declaracoes.append(f"margin-bottom:{espaco}px")
    return f' style="{";".join(declaracoes)}"' if declaracoes else ""


def _desenhar_imagem(bloco, assets):
    asset = assets.get(bloco.get("asset_id"))
    if asset is None:
        return ""
    ancora = bloco.get("desktop", {}).get("anchor", "none")
    largura = bloco.get("desktop", {}).get("width", 36)
    estilo = f"float:{ancora};width:{largura}%" if ancora in ("left", "right") else ""
    alt = bloco.get("alt") or ""
    atributo_estilo = f' style="{estilo}"' if estilo else ""
    img = f'<img src="{asset.file.url}" alt="{escape(alt)}"{atributo_estilo}>'
    return img if estilo else f"<p>{img}</p>"


def _desenhar_galeria(bloco, assets):
    imagens = [assets[i] for i in bloco.get("asset_ids", []) if i in assets]
    if not imagens:
        return ""
    itens = "".join(f'<span><img src="{a.file.url}" alt=""></span>' for a in imagens)
    return f'<div class="legal-galeria">{itens}</div>'


def _desenhar_tabela(bloco):
    linhas = [linha for linha in bloco.get("linhas", []) if any(c.strip() for c in linha)]
    if not linhas:
        return ""
    corpo = []
    for indice, linha in enumerate(linhas):
        celula_tag = "th" if bloco.get("cabecalho") and indice == 0 else "td"
        celulas = "".join(f"<{celula_tag}>{c}</{celula_tag}>" for c in linha)
        corpo.append(f"<tr>{celulas}</tr>")
    return "<table>" + "".join(corpo) + "</table>"


def renderizar_blocos(blocos):
    """
    O documento inteiro, em HTML -- pronto para
    `rodape.renderizar_documento_em_blocos` marcar como seguro.

    Cada bloco já está SANITIZADO (veio de `sanitizar_blocos`, no
    salvamento) -- mas o fragmento de texto passa por
    `rodape.sanitizar_documento` DE NOVO aqui, pela mesma razão de
    sempre: o banco não é confiável por definição. O que envolve cada
    bloco (a `<div class="legal-bloco">`) é gerado por este módulo, não
    por quem administra -- por isso não precisa da mesma sanitização.

    O bloco cujo conteúdo está vazio (imagem sem asset, tabela sem
    texto nenhum) simplesmente não é desenhado -- a mesma regra de
    "adorno vazio não aparece" do resto do site.
    """
    if not blocos:
        return ""
    assets = _assets_dos_blocos(blocos)
    partes = []
    for bloco in blocos:
        tipo = bloco.get("type")
        miolo = ""
        if tipo in TIPOS_DE_TEXTO:
            fragmento = _sanitizar_html_do_bloco(bloco.get("html"))
            if not rodape.tem_conteudo(fragmento) and tipo != "highlight":
                continue
            tag = TAG_EXTERNA.get(tipo)
            if tipo == "highlight":
                if not rodape.tem_conteudo(fragmento):
                    continue
                miolo = (
                    '<div class="legal-destaque">'
                    '<span class="legal-destaque-icone" aria-hidden="true"></span>'
                    f'<span>{fragmento}</span></div>'
                )
            elif tipo == "button":
                href = _href_do_documento(bloco.get("href"))
                if not href or not rodape.tem_conteudo(fragmento):
                    continue
                miolo = f'<p class="legal-botao"><a href="{escape(href)}">{fragmento}</a></p>'
            elif tag:
                miolo = f"<{tag}>{fragmento}</{tag}>"
            else:
                miolo = fragmento
        elif tipo == "separator":
            miolo = "<hr>"
        elif tipo == "html":
            fragmento = _sanitizar_html_do_bloco(bloco.get("html"))
            if not rodape.tem_conteudo(fragmento):
                continue
            miolo = fragmento
        elif tipo == "image":
            miolo = _desenhar_imagem(bloco, assets)
        elif tipo == "gallery":
            miolo = _desenhar_galeria(bloco, assets)
        elif tipo == "table":
            miolo = _desenhar_tabela(bloco)

        if not miolo:
            continue
        classe = _classe_do_bloco(bloco)
        estilo = _estilo_do_bloco(bloco)
        partes.append(f'<div class="{classe}"{estilo} data-bloco-tipo="{tipo}">{miolo}</div>')

    return "".join(partes)


# ---------------------------------------------------------------------------
# Migração -- HTML corrido de antes vira blocos
# ---------------------------------------------------------------------------


class _DivisorDeNivelZero(HTMLParser):
    """
    Corta um HTML já sanitizado nos elementos do NÍVEL MAIS ALTO --
    cada `<p>`, `<h2>`, `<ul>`, `<blockquote>`, `<hr>`, `<img>` solto
    vira um pedaço próprio; o que não é nenhum desses (texto solto sem
    tag, ou uma tag que este divisor não reconhece) é ACUMULADO à parte
    e sai como um pedaço de HTML no fim -- nunca descartado.
    """

    TAGS_DE_NIVEL_ZERO = {"p", "h2", "h3", "h4", "ul", "ol", "blockquote", "hr", "div"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.pedacos = []
        self._pilha = []
        self._atual = []
        self._resto = []

    def _saida_atual(self):
        return self._atual if self._pilha else self._resto

    # `hr` é de nível zero (uma linha divisória é o próprio bloco
    # "separador") mas nunca tem `</hr>` -- sem este caso à parte, ele
    # ficaria "aberto" no `_pilha` para sempre e engoliria todo o resto
    # do documento dentro de um pedaço que nunca fecha.
    VAZIAS_DE_NIVEL_ZERO = frozenset({"hr"})

    def handle_starttag(self, tag, attrs):
        bruto = self.get_starttag_text() or f"<{tag}>"
        if not self._pilha and tag in self.TAGS_DE_NIVEL_ZERO:
            self._fechar_resto()
            if tag in self.VAZIAS_DE_NIVEL_ZERO:
                self.pedacos.append(bruto)
            else:
                self._pilha.append(tag)
                self._atual = [bruto]
            return
        self._saida_atual().append(bruto)
        if tag not in ("br", "hr", "img") and self._pilha:
            self._pilha.append(tag)

    def handle_startendtag(self, tag, attrs):
        bruto = self.get_starttag_text() or f"<{tag}/>"
        if not self._pilha and tag in self.TAGS_DE_NIVEL_ZERO:
            self._fechar_resto()
            self.pedacos.append(bruto)
            return
        self._saida_atual().append(bruto)

    def handle_endtag(self, tag):
        self._saida_atual().append(f"</{tag}>")
        if self._pilha and self._pilha[-1] == tag:
            self._pilha.pop()
            if not self._pilha:
                self.pedacos.append("".join(self._atual))
                self._atual = []

    def handle_data(self, data):
        self._saida_atual().append(data)

    def handle_entityref(self, name):
        self._saida_atual().append(f"&{name};")

    def handle_charref(self, name):
        self._saida_atual().append(f"&#{name};")

    def _fechar_resto(self):
        if self._resto:
            self.pedacos.append("".join(self._resto))
            self._resto = []

    def dividir(self, html_bruto):
        self.feed(html_bruto or "")
        self.close()
        if self._pilha:
            # HTML mal fechado -- devolve tudo isto como resto, intacto.
            self.pedacos.append("".join(self._atual))
        self._fechar_resto()
        return [p for p in self.pedacos if p.strip()]


def migrar_html_para_blocos(html_antigo):
    """
    O texto de HOJE (HTML corrido, já sanitizado por
    `rodape.sanitizar_documento`) virando blocos -- SEM PERDER NADA.

    Cada `<h2>`, `<p>`, `<ul>/<ol>`, `<blockquote>` e `<hr>` do nível
    mais alto vira o bloco correspondente (`heading`, `paragraph`,
    `list`, `quote`, `separator`). Um `<p>` cuja ÚNICA coisa dentro é
    uma `<img>` vira um bloco de imagem de verdade -- procurando o
    `content.Asset` pelo arquivo do `src` -- em vez de um parágrafo com
    uma tag de imagem escondida dentro.

    QUALQUER OUTRA COISA -- uma tag que este divisor não reconhece,
    texto solto fora de qualquer tag, HTML mal formado -- vira um bloco
    `html` só, no LUGAR em que apareceu. Nada é descartado: o pior caso
    é o documento inteiro virar um bloco `html`, idêntico ao que já
    era.
    """
    limpo = rodape.sanitizar_documento(html_antigo or "")
    if not rodape.tem_conteudo(limpo):
        return []

    pedacos = _DivisorDeNivelZero().dividir(limpo)
    blocos = []
    for pedaco in pedacos:
        bloco = _pedaco_para_bloco(pedaco)
        if bloco:
            blocos.append(bloco)
    return blocos or [{**bloco_novo("html"), "html": limpo}]


_ABRE_TAG = re.compile(r"^<(\w+)\b[^>]*>")
_IMG_SOLTA = re.compile(r"^<p>\s*(<img\b[^>]*>)\s*</p>$", re.I)
_SRC_DA_IMG = re.compile(r'src="([^"]*)"', re.I)
_ALT_DA_IMG = re.compile(r'alt="([^"]*)"', re.I)


def _pedaco_para_bloco(pedaco):
    """Um PEDAÇO de nível zero (já fechado, já sanitizado) virando UM bloco."""
    pedaco = pedaco.strip()
    if not pedaco:
        return None

    imagem_solta = _IMG_SOLTA.match(pedaco)
    if imagem_solta:
        bloco_de_imagem = _imagem_da_tag(imagem_solta.group(1))
        if bloco_de_imagem:
            return bloco_de_imagem
        # O arquivo não está mais na biblioteca (apagado, por exemplo):
        # não vira bloco de imagem, mas o pedaço CONTINUA -- cai no
        # tratamento comum de `<p>` logo abaixo, como um parágrafo com
        # a tag de imagem embutida. Perder a referência aqui violaria a
        # garantia desta função: nada desaparece na migração.

    inicio = _ABRE_TAG.match(pedaco)
    tag = inicio.group(1).lower() if inicio else ""

    if tag == "hr":
        return bloco_novo("separator")
    if tag in ("h2", "h3", "h4"):
        return {**bloco_novo("heading"), "html": _sem_tag_externa(pedaco)}
    if tag in ("ul", "ol"):
        # A lista grava a MARCAÇÃO inteira (`<ul>...</ul>`): é o que o
        # comando de lista do editor rico já produz e o que a leitura
        # espera de volta -- sem tag externa própria.
        return {**bloco_novo("list"), "html": pedaco}
    if tag == "blockquote":
        return {**bloco_novo("quote"), "html": _sem_tag_externa(pedaco)}
    if tag == "p":
        texto = _sem_tag_externa(pedaco)
        if not rodape.tem_conteudo(texto):
            return None
        return {**bloco_novo("paragraph"), "html": texto}

    # Qualquer outra coisa (uma `<div>` da referência antiga, texto
    # solto, uma tag que este divisor não separou): preservada inteira
    # num bloco HTML -- nunca perdida.
    if not rodape.tem_conteudo(pedaco):
        return None
    return {**bloco_novo("html"), "html": pedaco}


def _sem_tag_externa(pedaco):
    """`<h2>Texto</h2>` -> `Texto` -- só a tag mais externa, preservando o miolo."""
    sem_abertura = _ABRE_TAG.sub("", pedaco, count=1)
    return re.sub(r"</\w+>\s*$", "", sem_abertura, count=1)


def _imagem_da_tag(tag_img):
    """`<img src="..." alt="...">` (já sanitizada) virando um bloco de imagem."""
    src = _SRC_DA_IMG.search(tag_img)
    if not src:
        return None
    # `_prefixo_da_biblioteca()` é `MEDIA_URL` + "assets" (ex.:
    # "/media/assets"); `Asset.file.name` guarda o caminho A PARTIR de
    # "assets/" (o `upload_to` do campo) -- daí o `"assets" + resto`.
    prefixo = rodape._prefixo_da_biblioteca()  # noqa: SLF001 -- mesmo pacote
    valor = src.group(1)
    if not valor.startswith(prefixo):
        return None
    resto = valor[len(prefixo):].lstrip("/")
    asset = Asset.objects.filter(file=f"assets/{resto}").first()
    if asset is None:
        return None
    alt = _ALT_DA_IMG.search(tag_img)
    bloco = bloco_novo("image")
    bloco.update({"asset_id": asset.pk, "alt": alt.group(1) if alt else ""})
    return bloco
