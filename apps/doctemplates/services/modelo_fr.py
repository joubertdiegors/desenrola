"""
Reconstrucao ESTRUTURAL do modelo oficial da Carta Convite em frances
(Etapa 3.3).

O que sai daqui e um `layout` do contrato novo (`layout_schema.py`):
elementos reais -- texto, campos, tabela, imagem, QR, linha, retangulos
-- posicionados nas coordenadas do documento oficial. O PDF oficial NAO
entra no resultado: nao ha pagina de fundo, nem imagem da pagina, nem
mascara branca, nem texto por cima de raster. Se um elemento aparece no
documento, ele existe aqui como elemento.

DE ONDE VEM CADA NUMERO
-----------------------
Todos foram MEDIDOS de `pdfengine/assets/fr/Modelo-Carta-Convite-FR.pdf`:

  * texto      -- percorrendo os operadores de texto do content stream,
                  com a matriz de cada run;
  * tracos     -- percorrendo os operadores graficos (`re`, `m`/`l`, `S`)
                  com a pilha de CTM;
  * imagens    -- pela matriz que precede cada `Do`, cruzada com o
                  retangulo de recorte que a acompanha;
  * a regua da -- pela bbox do glifo "_" lida do TrueType embutido no
    assinatura    proprio PDF.

Nada foi arredondado "para ficar bonito" e nada foi estimado a olho.

A ESCALA QUE ENGANA
-------------------
O CTM da pagina e `[0.75, 0, 0, -0.75, 49.6063, 791]`: escala 0.75 com
inversao de Y (o PDF veio de uma exportacao HTML). Quem le `font_size`
do recurso sem aplicar essa escala conclui que o corpo tem 14.67pt. Tem
11pt. O titulo tem 14pt, nao 18.67pt.

IDS ESTAVEIS, DE PROPOSITO
--------------------------
Os ids sao fixos e legiveis (`fr-titulo`, `fr-tabela`), nao os aleatorios
de `services/layout.novo_id()`. Aquele serve ao editor, onde ids so
precisam nao colidir. Aqui a semeadura tem de ser DETERMINISTICA: rodar
duas vezes tem de dar exatamente o mesmo layout, e a diferenca entre duas
versoes precisa ser legivel por quem revisa.
"""

import copy
import io
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Medidas do documento oficial
# ---------------------------------------------------------------------------

# Margem esquerda: e a translacao do proprio CTM da pagina. As margens
# sao simetricas (1,75cm), o que da a largura util abaixo.
MARGEM_ESQUERDA = 49.6063
LARGURA_DO_TEXTO = 496.063

TAMANHO_DO_CORPO = 11.0
TAMANHO_DO_TITULO = 14.0

# Entrelinha medida: 13,5pt de baseline a baseline, em todo o documento.
ALTURA_DA_LINHA = 13.5
ENTRELINHA = ALTURA_DA_LINHA / TAMANHO_DO_CORPO  # 1.2272...

# `/Ascent` do descritor da fonte embutida (905.27344/1000). E o que
# converte a linha de base medida no PDF para o topo da caixa do editor.
ASCENT = 0.90527344

FONTE = "LiberationSans"

# --- faixa tricolor (topo da pagina) ---------------------------------------
#
# No PDF e um PNG de 344x4 px. Analisando os pixels, sao tres tercos
# solidos -- preto, amarelo e vermelho -- com 1px de antialiasing nas
# juncoes. Tres retangulos reproduzem isso melhor do que embutir a
# imagem: ficam editaveis e nao carregam raster nenhum.
FAIXA_Y = 0.0
FAIXA_X = 168.7224
FAIXA_LARGURA_TOTAL = 258.0
FAIXA_ALTURA = 5.25
FAIXA_CORES = ("#000000", "#FFD966", "#FF0000")

# --- tabela do convidado ----------------------------------------------------
#
# Tracos medidos (espessura 0.75): verticais em x=49.5 / 167.5 / 546.5;
# horizontais em y=201.5 / 225.5 / 250.5 / 275.5 / 300.5 / 324.5.
TABELA_X = 49.5
TABELA_Y = 201.5
TABELA_LARGURA = 497.0
TABELA_ALTURA = 123.0
TABELA_COLUNAS = (118.0, 379.0)
TABELA_LINHAS = (24.0, 25.0, 25.0, 25.0, 24.0)
TABELA_BORDA = 0.75

# O topo de 6.1 vem da primeira linha (base 217.56 menos o ascent, menos
# o topo da linha). Na origem a coluna dos rotulos fica 0,26pt mais a
# direita do que a dos valores -- o PDF desenha os tracos e as caixas das
# celulas com criterios ligeiramente diferentes. Um espacamento uniforme
# nao reproduz os dois ao mesmo tempo; 0,26pt e 0,09mm.
TABELA_ESPACAMENTO = {"top": 6.1, "right": 5.1, "bottom": 4.4, "left": 5.1}

# --- lista numerada ---------------------------------------------------------
#
# Medido: o marcador fica em x=67.606 e o corpo em x=85.606 em TODAS as
# linhas, inclusive a primeira. Nao e recuo de primeira linha -- sao dois
# elementos.
LISTA_X_MARCADOR = 67.606
LISTA_X_CORPO = 85.606
LISTA_LARGURA_CORPO = 460.063
LISTA_LARGURA_MARCADOR = 18.0

# --- logo, QR e regua da assinatura ----------------------------------------

# O PDF coloca o PNG do logo em 102.26x105.0 e o RECORTA para 84x61.5; a
# arte ocupa so o miolo do arquivo. Estes numeros sao os da arte de fato
# -- onde a tinta aparece na pagina.
LOGO_X = 401.8544
LOGO_Y = 686.4549
LOGO_LARGURA = 45.7832
LOGO_ALTURA = 47.1826
LOGO_CHAVE_DO_ASSET = "carta-convite-fr-logo-ibz"

# Caixa de recorte do QR na pagina. O QR vira elemento estrutural: o
# raster do PDF nao e reaproveitado.
QR_X = 470.3563
QR_Y = 682.5
QR_LADO = 78.0
QR_CONTEUDO = "https://dofi.ibz.be/fr/themes/third-country-nationals/court-sejour"

# No original a regua e uma sequencia de "_". Medindo a bbox do glifo no
# TrueType embutido (yMin=-407, yMax=-277 em 2048 upem, a 11pt) ela cai
# 1.49..2.19pt abaixo da linha de base 682.56, com 0.698pt de espessura.
# Como linha de verdade ela fica no centro disso.
ASSINATURA_X = 49.606
ASSINATURA_Y = 684.3969
ASSINATURA_LARGURA = 189.6479
ASSINATURA_ESPESSURA = 0.6982


def topo_da_caixa(linha_de_base, tamanho=TAMANHO_DO_CORPO):
    """
    O topo da caixa de um texto, a partir da linha de base medida no PDF.

    O documento ancora o texto pela LINHA DE BASE; o layout ancora pelo
    TOPO. A diferenca e o quanto a fonte sobe acima da base -- o ascent
    da fonte embutida, nao um chute.
    """
    return linha_de_base - tamanho * ASCENT


def altura_de(linhas, tamanho=TAMANHO_DO_CORPO):
    """A altura reservada para um texto de `linhas` linhas."""
    return linhas * tamanho * ENTRELINHA


# ---------------------------------------------------------------------------
# Blocos de conteudo
# ---------------------------------------------------------------------------


def texto(valor):
    return {"kind": "text", "value": valor}


def campo(referencia, *, negrito=False):
    """Um campo dinamico. ESTRUTURAL -- nunca "{{campo}}" numa string."""
    bloco = {"kind": "field", "source": referencia}
    if negrito:
        bloco["font_weight"] = "bold"
    return bloco


def trecho(valor, *, negrito=False):
    """Um pedaco de texto fixo dentro de uma linha corrida."""
    bloco = {"kind": "text", "value": valor}
    if negrito:
        bloco["font_weight"] = "bold"
    return bloco


def misto(*partes):
    return {"kind": "mixed", "parts": list(partes)}


def _tipografia(*, tamanho=TAMANHO_DO_CORPO, negrito=False):
    return {
        "font_family": FONTE,
        "font_size": tamanho,
        "font_weight": "bold" if negrito else "regular",
        "font_style": "normal",
        "text_decoration": "none",
        "color": "#000000",
        "letter_spacing": 0.0,
    }


def _paragrafo(*, alinhamento="left"):
    return {
        "align": alinhamento,
        "vertical_align": "top",
        "line_height": ENTRELINHA,
        "white_space": "normal",
        "overflow": "shrink",
        "padding": {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0},
        "language": "fr",
    }


def _texto(identificador, conteudo, *, x, base, largura, linhas=1,
           alinhamento="left", tamanho=TAMANHO_DO_CORPO, negrito=False, rico=False):
    """Um elemento de texto ancorado pela linha de base medida no PDF."""
    return {
        "id": identificador,
        "type": "rich_text" if rico else "text",
        "x": x,
        "y": topo_da_caixa(base, tamanho),
        "width": largura,
        "height": altura_de(linhas, tamanho),
        "properties": {
            "content": conteudo,
            **_tipografia(tamanho=tamanho, negrito=negrito),
            **_paragrafo(alinhamento=alinhamento),
        },
    }


def _celula(conteudo, *, negrito=False):
    return {"content": conteudo, "align": "left", "bold": negrito}


def _linha_da_tabela(altura, rotulo, valor):
    return {
        "min_height": altura,
        "cells": [_celula(texto(rotulo), negrito=True), _celula(valor)],
    }


# ---------------------------------------------------------------------------
# O layout
# ---------------------------------------------------------------------------


def layout_carta_convite_fr(*, asset_do_logo=0):
    """
    O layout estrutural completo do modelo oficial frances.

    `asset_do_logo` e o id do `content.Asset` com o logo do IBZ. Zero
    significa "ainda nao ha asset": o elemento continua existindo, so
    aponta para lugar nenhum -- e assim o layout pode ser montado e
    validado sem depender do banco.
    """
    elementos = []

    # --- faixa tricolor -----------------------------------------------------
    largura_de_cada = FAIXA_LARGURA_TOTAL / len(FAIXA_CORES)
    for posicao, cor in enumerate(FAIXA_CORES):
        elementos.append({
            "id": f"fr-faixa-{posicao}",
            "type": "rectangle",
            "x": FAIXA_X + posicao * largura_de_cada,
            "y": FAIXA_Y,
            "width": largura_de_cada,
            "height": FAIXA_ALTURA,
            "properties": {
                "border_width": 0.0,
                "border_style": "solid",
                "border_color": "#000000",
                "fill_color": cor,
                "radius": 0.0,
            },
        })

    # --- cabecalho ----------------------------------------------------------
    #
    # O apostrofo do titulo e mesmo inconsistente no original: reto em
    # "D'INVITATION" e curvo em "D’HEBERGEMENT". Reproduzido como esta.
    elementos.append(_texto(
        "fr-titulo", texto("LETTRE D'INVITATION ET D’HÉBERGEMENT"),
        x=MARGEM_ESQUERDA, base=64.44, largura=LARGURA_DO_TEXTO,
        alinhamento="center", tamanho=TAMANHO_DO_TITULO, negrito=True,
    ))
    elementos.append(_texto(
        "fr-subtitulo", texto("(COURT SÉJOUR EN BELGIQUE)"),
        x=MARGEM_ESQUERDA, base=78.06, largura=LARGURA_DO_TEXTO,
        alinhamento="center",
    ))
    elementos.append(_texto(
        "fr-destinatario",
        texto("À l’attention des autorités compétentes."),
        x=MARGEM_ESQUERDA, base=134.06, largura=LARGURA_DO_TEXTO,
    ))

    # --- declaracao do anfitriao -------------------------------------------
    #
    # Tres linhas justificadas, com negrito ALTERNANDO dentro da linha
    # corrida. E o trecho que exigiu a enfase por parte de `mixed`.
    elementos.append(_texto(
        "fr-declaracao",
        misto(
            trecho("Je soussignée, "),
            campo("anfitriao.nome", negrito=True),
            trecho(", née le "),
            campo("anfitriao.data_nascimento"),
            trecho(", de nationalité "),
            campo("anfitriao.nacionalidade"),
            trecho(", titulaire de la carte d’identité "),
            # O mesmo dado da nacionalidade: "carte d'identite belge". O
            # documento nao pergunta um segundo valor para isto.
            campo("anfitriao.nacionalidade"),
            trecho(" n° "),
            campo("anfitriao.documento_identidade", negrito=True),
            trecho(", domiciliée au "),
            campo("anfitriao.endereco", negrito=True),
            trecho(", téléphone "),
            campo("anfitriao.telefone", negrito=True),
            trecho(", invite par la présente :"),
        ),
        x=MARGEM_ESQUERDA, base=159.06, largura=LARGURA_DO_TEXTO,
        linhas=3, alinhamento="justify", rico=True,
    ))

    # --- tabela do convidado ------------------------------------------------
    elementos.append({
        "id": "fr-tabela",
        "type": "table",
        "x": TABELA_X,
        "y": TABELA_Y,
        "width": TABELA_LARGURA,
        "height": TABELA_ALTURA,
        "properties": {
            "columns": [{"width": largura, "align": "left"} for largura in TABELA_COLUNAS],
            "rows": [
                _linha_da_tabela(TABELA_LINHAS[0], "Nom et prénom :",
                                 campo("convidado.nome")),
                _linha_da_tabela(TABELA_LINHAS[1], "Nationalité :",
                                 campo("convidado.nacionalidade")),
                _linha_da_tabela(TABELA_LINHAS[2], "Date de naissance :",
                                 campo("convidado.data_nascimento")),
                _linha_da_tabela(TABELA_LINHAS[3], "N° de passeport :",
                                 campo("convidado.passaporte")),
                _linha_da_tabela(
                    TABELA_LINHAS[4], "Durée :",
                    misto(
                        trecho("du "),
                        campo("estadia.chegada"),
                        trecho(" au "),
                        campo("estadia.partida"),
                        trecho(" ("),
                        campo("calculado.duracao_dias"),
                        trecho(" jours)"),
                    ),
                ),
            ],
            "border_width": TABELA_BORDA,
            "border_color": "#000000",
            "cell_padding": dict(TABELA_ESPACAMENTO),
            **_tipografia(),
            "align": "left",
            "line_height": ENTRELINHA,
        },
    })

    # --- lista numerada -----------------------------------------------------
    itens = (
        (1, 371.06, 1, misto(
            trecho("La présente invitation est établie dans le cadre "
                   "d’une "),
            trecho("visite privée", negrito=True),
            trecho("."),
        )),
        (2, 384.06, 2, misto(
            trecho("Pendant toute la durée de son séjour en Belgique, la "
                   "personne invitée sera hébergée à mon domicile "
                   "situé à l’adresse suivante : "),
            campo("anfitriao.endereco", negrito=True),
        )),
        (3, 411.06, 2, texto(
            "La personne invitée assume personnellement ses frais de voyage, de "
            "séjour, de nourriture, d’assurance, de transport et autres "
            "dépenses liées à son séjour."
        )),
    )
    for numero, base, linhas, conteudo in itens:
        elementos.append(_texto(
            f"fr-item-{numero}-marcador", texto(f"{numero}."),
            x=LISTA_X_MARCADOR, base=base, largura=LISTA_LARGURA_MARCADOR,
        ))
        elementos.append(_texto(
            f"fr-item-{numero}", conteudo,
            x=LISTA_X_CORPO, base=base, largura=LISTA_LARGURA_CORPO,
            linhas=linhas, alinhamento="justify",
            rico=conteudo.get("kind") == "mixed",
        ))

    # --- paragrafos de fecho ------------------------------------------------
    fechos = (
        ("fr-fecho-1", 475.56, 2,
         "La présente lettre constitue exclusivement une invitation privée "
         "et une confirmation d’hébergement et ne constitue pas un "
         "engagement de prise en charge financière au sens de l’Annexe "
         "3bis."),
        ("fr-fecho-2", 514.56, 3,
         "Je certifie l’exactitude des informations reprises dans la "
         "présente lettre et reste disponible auprès des autorités "
         "compétentes pour toute vérification concernant cette invitation "
         "et les conditions d’hébergement."),
        ("fr-fecho-3", 567.06, 2,
         "La personne invitée s’engage à respecter les conditions "
         "applicables à son séjour et à quitter le territoire de "
         "l’espace Schengen à l’issue de la durée autorisée."),
    )
    for identificador, base, linhas, corpo in fechos:
        elementos.append(_texto(
            identificador, texto(corpo),
            x=MARGEM_ESQUERDA, base=base, largura=LARGURA_DO_TEXTO,
            linhas=linhas, alinhamento="justify",
        ))

    # --- local e data -------------------------------------------------------
    elementos.append(_texto(
        "fr-local-e-data",
        misto(
            trecho("Fait à "),
            campo("anfitriao.cidade"),
            trecho(", le "),
            campo("calculado.data_documento"),
        ),
        x=MARGEM_ESQUERDA, base=631.56, largura=LARGURA_DO_TEXTO,
        alinhamento="right", rico=True,
    ))

    # --- logo e QR ----------------------------------------------------------
    elementos.append({
        "id": "fr-logo-ibz",
        "type": "image",
        "x": LOGO_X, "y": LOGO_Y, "width": LOGO_LARGURA, "height": LOGO_ALTURA,
        "properties": {
            "source": {"kind": "asset", "asset_id": int(asset_do_logo)},
            "fit": "contain",
            "preserve_aspect_ratio": True,
        },
    })
    elementos.append({
        "id": "fr-qr-code",
        "type": "qr_code",
        "x": QR_X, "y": QR_Y, "width": QR_LADO, "height": QR_LADO,
        "properties": {
            "source": texto(QR_CONTEUDO),
            "margin": 0.0,
            "error_correction": "M",
        },
    })

    # --- bloco da assinatura ------------------------------------------------
    elementos.append({
        "id": "fr-assinatura-linha",
        "type": "line",
        "x": ASSINATURA_X, "y": ASSINATURA_Y,
        "width": ASSINATURA_LARGURA, "height": 0.0,
        "properties": {
            "thickness": ASSINATURA_ESPESSURA,
            "style": "solid",
            "color": "#000000",
        },
    })
    elementos.append(_texto(
        "fr-assinatura-nome", campo("anfitriao.nome"),
        x=MARGEM_ESQUERDA, base=696.06, largura=LARGURA_DO_TEXTO, negrito=True,
    ))
    elementos.append(_texto(
        "fr-assinatura-rotulo", texto("Signature de l’invitante"),
        x=MARGEM_ESQUERDA, base=709.56, largura=LARGURA_DO_TEXTO,
    ))

    return {"version": 1, "elements": elementos}


# ---------------------------------------------------------------------------
# Inventario, para revisao humana
# ---------------------------------------------------------------------------


def _resumo_do_conteudo(bloco, limite=60):
    """Uma linha legivel descrevendo um bloco de conteudo estrutural."""
    if not isinstance(bloco, dict):
        return ""
    forma = bloco.get("kind")
    if forma == "text":
        valor = " ".join((bloco.get("value") or "").split())
        return valor if len(valor) <= limite else valor[: limite - 1] + "…"
    if forma == "field":
        return f"<{bloco.get('source')}>"
    if forma == "asset":
        return f"<asset #{bloco.get('asset_id')}>"
    if forma == "mixed":
        return " + ".join(
            _resumo_do_conteudo(parte, limite=24) for parte in bloco.get("parts") or []
        )
    return ""


def inventario(layout=None):
    """
    O layout numa forma conferivel linha a linha.

    Serve a revisao visual da reconstrucao: da para pegar esta lista e o
    PDF oficial lado a lado e comparar posicao, tamanho e conteudo de
    cada elemento sem abrir o JSON.
    """
    from ..layout_schema import referencias_de

    layout = layout if layout is not None else layout_carta_convite_fr()
    linhas = []
    for posicao, elemento in enumerate(layout.get("elements", [])):
        propriedades = elemento.get("properties") or {}
        conteudo = propriedades.get("content") or propriedades.get("source")

        referencias = set()
        for chave in ("content", "source"):
            referencias |= referencias_de(propriedades.get(chave))
        for linha in propriedades.get("rows") or []:
            for celula in linha.get("cells") or []:
                referencias |= referencias_de(celula.get("content"))

        linhas.append({
            "ordem": posicao,
            "id": elemento.get("id"),
            "tipo": elemento.get("type"),
            "x": elemento.get("x"),
            "y": elemento.get("y"),
            "largura": elemento.get("width"),
            "altura": elemento.get("height"),
            "resumo": _resumo_do_conteudo(conteudo),
            "campos": sorted(referencias),
        })
    return linhas


def inventario_texto(layout=None):
    """O inventario como texto, para imprimir no terminal."""
    linhas = inventario(layout)
    saida = [
        f"{'#':>2}  {'id':<22} {'tipo':<10} {'x':>9} {'y':>9} "
        f"{'larg':>8} {'alt':>7}  conteúdo",
        "-" * 118,
    ]
    for linha in linhas:
        saida.append(
            f"{linha['ordem']:>2}  {linha['id']:<22} {linha['tipo']:<10} "
            f"{linha['x']:>9.4f} {linha['y']:>9.4f} "
            f"{linha['largura']:>8.4f} {linha['altura']:>7.4f}  {linha['resumo']}"
        )
    campos = sorted({ref for linha in linhas for ref in linha["campos"]})
    saida.append("")
    saida.append(f"{len(linhas)} elementos, {len(campos)} campos dinâmicos:")
    saida.extend(f"    {ref}" for ref in campos)
    return "\n".join(saida)


# ---------------------------------------------------------------------------
# O logo, extraido do proprio PDF oficial
# ---------------------------------------------------------------------------

SLUG_DO_MODELO_FR = "carta-convite-fr"

# O id estavel do elemento do logo, para `vincular_logo()` achar sem
# depender da posicao dele na lista.
ID_DO_LOGO = "fr-logo-ibz"

# O PDF oficial e a unica fonte do asset: nao guardamos uma copia do logo
# no repositorio para nao existirem duas versoes podendo divergir.
CAMINHO_DO_PDF = (
    Path(__file__).resolve().parents[3] / "pdfengine" / "assets" / "fr"
    / "Modelo-Carta-Convite-FR.pdf"
)

# Um strip fino e a faixa tricolor; um quadrado exato e o QR. O logo e o
# que sobra. Identificar por FORMA, e nao pelo nome do XObject ("/X7"),
# evita quebrar se o PDF for reexportado com outra numeracao.
ALTURA_MAXIMA_DE_UMA_FAIXA = 10


class LogoNaoEncontradoError(RuntimeError):
    """O PDF oficial nao tem uma imagem reconhecivel como o logo."""


def extrair_logo_ibz(caminho=None):
    """
    Os bytes PNG do logo do IBZ, recortados a arte.

    O arquivo dentro do PDF tem bastante margem branca em volta -- e o
    PDF a esconde recortando a imagem na hora de desenhar. Quem so
    extraisse o XObject e o colocasse na caixa do recorte veria o logo
    encolhido e fora de lugar. Por isso aqui a arte e recortada pela sua
    caixa de conteudo, e as medidas de `LOGO_*` sao as dessa arte.
    """
    from PIL import Image, ImageChops
    from pypdf import PdfReader

    origem = Path(caminho) if caminho else CAMINHO_DO_PDF
    if not origem.is_file():
        raise LogoNaoEncontradoError(f"O PDF oficial não foi encontrado em {origem}.")

    candidatos = []
    for imagem in PdfReader(str(origem)).pages[0].images:
        figura = Image.open(io.BytesIO(imagem.data))
        if figura.height <= ALTURA_MAXIMA_DE_UMA_FAIXA:
            continue                       # a faixa tricolor
        if figura.width == figura.height:
            continue                       # o QR
        candidatos.append(figura)

    if len(candidatos) != 1:
        raise LogoNaoEncontradoError(
            f"Esperava exatamente uma imagem de logo em {origem.name}; "
            f"encontrei {len(candidatos)}."
        )

    figura = candidatos[0].convert("RGB")
    branco = Image.new("RGB", figura.size, (255, 255, 255))
    caixa = ImageChops.difference(figura, branco).getbbox()
    if caixa is None:
        raise LogoNaoEncontradoError("A imagem do logo está inteiramente em branco.")

    saida = io.BytesIO()
    figura.crop(caixa).save(saida, format="PNG")
    return saida.getvalue()


def garantir_asset_do_logo(Asset, *, caminho=None):
    """
    O `content.Asset` do logo, criado se ainda nao existir.

    Devolve `(asset, criado)` -- o booleano existe para quem chama poder
    dizer se criou ou reaproveitou, em vez de deduzir consultando o banco
    de novo e correndo o risco de responder errado.

    Procurado pela `key` fixa: rodar de novo reaproveita o registro em
    vez de encher a biblioteca de copias, e NUNCA troca o arquivo de um
    asset existente -- o administrador pode te-lo substituido de
    proposito.
    """
    from django.core.files.base import ContentFile

    existente = Asset.objects.filter(key=LOGO_CHAVE_DO_ASSET).first()
    if existente is not None:
        return existente, False

    asset = Asset(
        key=LOGO_CHAVE_DO_ASSET,
        kind="content",
        alt_text="Office des étrangers — Vreemdelingenzaken (IBZ)",
        is_active=True,
    )
    asset.file.save(
        f"{LOGO_CHAVE_DO_ASSET}.png",
        ContentFile(extrair_logo_ibz(caminho)),
        save=False,
    )
    asset.save()
    return asset, True


# ---------------------------------------------------------------------------
# Aplicacao
# ---------------------------------------------------------------------------


def aplicar(DocumentTemplate, *, asset_do_logo=0, forcar=False):
    """
    Grava o layout reconstruido no modelo oficial frances.

    Devolve o modelo quando grava e `None` quando nao ha o que fazer.

    NAO SOBRESCREVE TRABALHO DE ADMINISTRADOR
    -----------------------------------------
    Se o modelo ja tiver qualquer layout, esta funcao nao faz nada. Quem
    quiser mesmo reconstruir por cima pede `forcar=True` -- explicitamente,
    nunca por acidente de uma segunda execucao.

    POR QUE `update()` E NAO `save()`
    ---------------------------------
    `DocumentTemplate.save()` recusa alterar `layout` num modelo
    `is_system`: a guarda existe para que a INTERFACE nao corrompa um
    modelo oficial. Mas quem escreve o conteudo oficial e justamente a
    semeadura -- a mesma que criou estes registros na 0010. Enfraquecer
    a guarda (por exemplo pondo `layout` em `SYSTEM_MUTABLE_FIELDS`)
    abriria o modelo oficial para qualquer edicao pela tela, que e o
    oposto do que ela protege.

    Como `update()` nao chama `clean()`, o layout e validado aqui antes
    de ir para o banco: nada invalido chega gravado.
    """
    from ..layout_schema import validate_layout

    modelo = DocumentTemplate.objects.filter(slug=SLUG_DO_MODELO_FR).first()
    if modelo is None:
        return None
    if modelo.layout and not forcar:
        return None

    layout = layout_carta_convite_fr(asset_do_logo=asset_do_logo)
    validate_layout(layout)
    DocumentTemplate.objects.filter(pk=modelo.pk).update(layout=layout)
    modelo.layout = layout
    # `update()` pula o `save()` -- e com ele a sincronizacao dos vinculos
    # com os assets. Refeita aqui, para o PROTECT valer tambem para o
    # logo do oficial. Tolerante ao modelo historico das migrations.
    from ..models import sincronizar_assets_do_modelo

    sincronizar_assets_do_modelo(DocumentTemplate, modelo)
    return modelo


def vincular_logo(DocumentTemplate, asset_id):
    """
    Aponta o elemento do logo para um asset, sem tocar no resto do layout.

    Existe separada de `aplicar()` porque a migration de dados NAO cria
    o arquivo: uma migration que escreve em MEDIA_ROOT quebra em
    armazenamento remoto ou sistema de arquivos somente-leitura, e numa
    suite de testes deixaria uma copia do PNG por execucao. O layout
    nasce com `asset_id: 0` -- o elemento existe, so ainda sem binario --
    e ganha a imagem quando `reconstruir()` roda.
    """
    from ..layout_schema import validate_layout

    modelo = DocumentTemplate.objects.filter(slug=SLUG_DO_MODELO_FR).first()
    if modelo is None or not modelo.layout:
        return None

    layout = copy.deepcopy(modelo.layout)
    mudou = False
    for elemento in layout.get("elements", []):
        if elemento.get("id") != ID_DO_LOGO or elemento.get("type") != "image":
            continue
        propriedades = elemento.setdefault("properties", {})
        if (propriedades.get("source") or {}).get("asset_id") != int(asset_id):
            propriedades["source"] = {"kind": "asset", "asset_id": int(asset_id)}
            mudou = True

    if not mudou:
        return None
    validate_layout(layout)
    DocumentTemplate.objects.filter(pk=modelo.pk).update(layout=layout)
    modelo.layout = layout
    # `update()` pula o `save()` -- e com ele a sincronizacao dos vinculos
    # com os assets. Refeita aqui, para o PROTECT valer tambem para o
    # logo do oficial. Tolerante ao modelo historico das migrations.
    from ..models import sincronizar_assets_do_modelo

    sincronizar_assets_do_modelo(DocumentTemplate, modelo)
    return modelo


@dataclass(frozen=True)
class Reconstrucao:
    """
    O que uma reconstrucao fez, para quem chamou poder relatar.

    Sem isto o comando de gestao teria de consultar o banco de novo para
    adivinhar se criou ou reaproveitou -- e adivinharia errado sempre que
    duas execucoes acontecessem juntas.
    """

    slug: str
    modelo: object
    layout_gravado: bool
    asset: object
    asset_criado: bool
    logo_vinculado: bool


def reconstruir(DocumentTemplate, Asset, *, forcar=False, caminho=None):
    """
    O caminho completo: grava o layout e anexa o logo.

    Idempotente: rodar de novo nao duplica o asset nem reescreve um
    layout ja existente (a menos de `forcar=True`). Disponivel para
    codigo de aplicacao -- testes e o comando
    `reconstruir_modelos_oficiais` -- no mesmo espirito de
    `services.biblioteca.semear_carta_convite`.
    """
    gravado = aplicar(DocumentTemplate, forcar=forcar) is not None
    asset, criado = garantir_asset_do_logo(Asset, caminho=caminho)
    vinculado = vincular_logo(DocumentTemplate, asset.pk) is not None
    return Reconstrucao(
        slug=SLUG_DO_MODELO_FR,
        modelo=DocumentTemplate.objects.filter(slug=SLUG_DO_MODELO_FR).first(),
        layout_gravado=gravado,
        asset=asset,
        asset_criado=criado,
        logo_vinculado=vinculado,
    )
