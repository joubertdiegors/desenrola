"""
Reconstrucao ESTRUTURAL do modelo oficial da Carta Convite, nos quatro
idiomas (Etapas 3.3 e 3.6).

O que sai daqui e um `layout` do contrato novo (`layout_schema.py`):
elementos reais -- texto, campos, tabela, imagem, QR, linha, retangulos
-- posicionados nas coordenadas do documento oficial. O PDF oficial NAO
entra no resultado: nao ha pagina de fundo, nem imagem da pagina, nem
mascara branca, nem texto por cima de raster. Se um elemento aparece no
documento, ele existe aqui como elemento.

UMA ESTRUTURA, QUATRO CONTEUDOS
-------------------------------
A geometria (posicoes, tamanhos, tipos, ordem das camadas) e MEDIDA do
documento frances e vale para os quatro idiomas. So o texto muda, e ele
vive em `CONTEUDO`, uma tabela por idioma -- legivel e editavel sem
mexer na montagem. EN/NL/PT sao traducoes do frances (Etapa 3.6): mesma
estrutura documental, mesmas clausulas, mesmos campos dinamicos.

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

O UNICO AJUSTE POR IDIOMA
-------------------------
Traducao muda o comprimento do texto. O item 2 da lista ocupa 2 linhas
em FR/PT e 3 em EN/NL; por isso o item 3 desce uma linha nesses dois --
pela REGRA em `_base_do_item_3()`, nao por uma tabela de excecoes. Todo
o resto (inclusive a tabela e as caixas de texto) e identico nos quatro.

IDS ESTAVEIS, DE PROPOSITO
--------------------------
Os ids sao fixos e legiveis (`fr-titulo`, `pt-tabela`), nao os aleatorios
de `services/layout.novo_id()`. Aquele serve ao editor, onde ids so
precisam nao colidir. Aqui a semeadura tem de ser DETERMINISTICA: rodar
duas vezes tem de dar exatamente o mesmo layout, e a diferenca entre duas
versoes precisa ser legivel por quem revisa.
"""

import copy
import io
from dataclasses import dataclass
from pathlib import Path

IDIOMAS = ("fr", "en", "nl", "pt")

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

# O asset do logo e UNICO para os quatro idiomas: a arte e a mesma. A
# chave conserva o nome historico (nasceu com o FR) para nao recriar o
# registro que ja existe no banco.
LOGO_CHAVE_DO_ASSET = "carta-convite-fr-logo-ibz"

# Caixa de recorte do QR na pagina. O QR vira elemento estrutural: o
# raster do PDF nao e reaproveitado.
QR_X = 470.3563
QR_Y = 682.5
QR_LADO = 78.0

# A URL do documento oficial. NAO e traduzida: e um endereco, nao texto
# -- e inventar uma variante por idioma seria criar conteudo que o
# documento oficial nao tem.
QR_CONTEUDO = "https://dofi.ibz.be/fr/themes/third-country-nationals/court-sejour"

# No original a regua e uma sequencia de "_". Medindo a bbox do glifo no
# TrueType embutido (yMin=-407, yMax=-277 em 2048 upem, a 11pt) ela cai
# 1.49..2.19pt abaixo da linha de base 682.56, com 0.698pt de espessura.
# Como linha de verdade ela fica no centro disso.
ASSINATURA_X = 49.606
ASSINATURA_Y = 684.3969
ASSINATURA_LARGURA = 189.6479
ASSINATURA_ESPESSURA = 0.6982

# --- linhas de base medidas -------------------------------------------------
BASE_TITULO = 64.44
BASE_SUBTITULO = 78.06
BASE_DESTINATARIO = 134.06
BASE_DECLARACAO = 159.06
BASE_DOS_ITENS = (371.06, 384.06, 411.06)
BASE_DOS_FECHOS = (475.56, 514.56, 567.06)
BASE_LOCAL_E_DATA = 631.56
BASE_ASSINATURA_NOME = 696.06
BASE_ASSINATURA_ROTULO = 709.56

# Quantas linhas o item 2 ocupa no documento frances. E a referencia de
# `_base_do_item_3()`: um idioma que precise de mais linhas empurra o
# item 3 para baixo na mesma medida.
LINHAS_DO_ITEM_2_NO_FRANCES = 2


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


def _base_do_item_3(linhas_do_item_2):
    """
    A linha de base do item 3, que desce se o item 2 crescer.

    Sem isto, uma traducao que precise de uma linha a mais no item 2
    escreveria por cima do item 3. Ha folga de sobra abaixo (o proximo
    bloco so comeca em 465.6), entao o deslocamento nao cascateia.
    """
    extra = linhas_do_item_2 - LINHAS_DO_ITEM_2_NO_FRANCES
    return BASE_DOS_ITENS[2] + extra * ALTURA_DA_LINHA


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


def _paragrafo(idioma, *, alinhamento="left"):
    return {
        "align": alinhamento,
        "vertical_align": "top",
        "line_height": ENTRELINHA,
        "white_space": "normal",
        "overflow": "shrink",
        "padding": {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0},
        "language": idioma,
    }


def _texto(identificador, conteudo, *, idioma, x, base, largura, linhas=1,
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
            **_paragrafo(idioma, alinhamento=alinhamento),
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
# Campos dinamicos: a ESTRUTURA, igual nos quatro idiomas
# ---------------------------------------------------------------------------

# A declaracao do anfitriao alterna literal e campo: literal[0], campo[0],
# literal[1], campo[1], ... , literal[6]. Os campos e o negrito deles sao
# os mesmos em todos os idiomas; so os literais entre eles mudam.
#
# Seis campos, cada dado uma vez (Rodada 18): nome, nascimento,
# nacionalidade, documento de identidade, endereco e telefone. A versao
# anterior repetia a nacionalidade ("carte d'identite belge"); o texto
# novo diz "carte d'identite : <numero>", e a nacionalidade aparece so no
# seu proprio trecho. O negrito de cada campo e o de antes.
CAMPOS_DA_DECLARACAO = (
    ("anfitriao.nome", True),
    ("anfitriao.data_nascimento", False),
    ("anfitriao.nacionalidade", False),
    ("anfitriao.documento_identidade", True),
    ("anfitriao.endereco", True),
    ("anfitriao.telefone", True),
)

CAMPOS_DA_TABELA = (
    "convidado.nome",
    "convidado.nacionalidade",
    "convidado.data_nascimento",
    "convidado.passaporte",
)

# A linha "Duree" alterna do mesmo jeito: literal, campo, literal, campo,
# literal, campo, literal.
CAMPOS_DA_DURACAO = ("estadia.chegada", "estadia.partida", "calculado.duracao_dias")

CAMPOS_DO_LOCAL_E_DATA = ("anfitriao.cidade", "calculado.data_documento")


# ---------------------------------------------------------------------------
# O conteudo textual, por idioma
# ---------------------------------------------------------------------------
#
# EN/NL/PT sao traducoes do frances (Etapa 3.6). Mesma estrutura, mesmas
# clausulas, nenhuma acrescentada nem removida. Nomes proprios, "IBZ",
# "Annexe 3bis" e a URL do QR NAO sao traduzidos: sao identificadores.
#
# `linhas` e quantas linhas cada bloco ocupa depois de quebrado a 11pt na
# largura util -- medido com a mesma funcao de quebra que o renderer usa.
# Nao e estetica: e a altura da caixa do elemento.

CONTEUDO = {
    "fr": {
        # O apostrofo do titulo e mesmo inconsistente no original: reto em
        # "D'INVITATION" e curvo em "D’HEBERGEMENT". Reproduzido como esta.
        "titulo": "LETTRE D'INVITATION ET D’HÉBERGEMENT",
        "subtitulo": "(COURT SÉJOUR EN BELGIQUE)",
        "destinatario": "À l’attention des autorités compétentes.",
        # Rodada 18: a formulacao neutra pedida pelo cliente -- "(e)" em
        # vez do feminino fixo, e um rotulo com dois-pontos por dado.
        "declaracao": (
            "Je soussigné(e), ",
            ", né(e) le ",
            ", nationalité : ",
            ", carte d’identité : ",
            ", domicilié(e) à ",
            ", téléphone : ",
            ", invite par la présente :",
        ),
        "tabela_rotulos": (
            "Nom et prénom :",
            "Nationalité :",
            "Date de naissance :",
            "N° de passeport :",
            "Durée :",
        ),
        "duracao": ("du ", " au ", " (", " jours)"),
        "item_1": (
            "La présente invitation est établie dans le cadre d’une ",
            "visite privée",
            ".",
        ),
        "item_2": (
            "Pendant toute la durée de son séjour en Belgique, la personne "
            "invitée sera hébergée à mon domicile situé à l’adresse "
            "suivante : "
        ),
        "item_3": (
            "La personne invitée assume personnellement ses frais de voyage, "
            "de séjour, de nourriture, d’assurance, de transport et autres "
            "dépenses liées à son séjour."
        ),
        "fechos": (
            "La présente lettre constitue exclusivement une invitation privée "
            "et une confirmation d’hébergement et ne constitue pas un "
            "engagement de prise en charge financière au sens de l’Annexe "
            "3bis.",
            "Je certifie l’exactitude des informations reprises dans la "
            "présente lettre et reste disponible auprès des autorités "
            "compétentes pour toute vérification concernant cette invitation "
            "et les conditions d’hébergement.",
            "La personne invitée s’engage à respecter les conditions "
            "applicables à son séjour et à quitter le territoire de "
            "l’espace Schengen à l’issue de la durée autorisée.",
        ),
        "local_e_data": ("Fait à ", ", le "),
        "assinatura_rotulo": "Signature de l’invitante",
        "linhas": {
            "declaracao": 3,
            "itens": (1, 2, 2),
            "fechos": (2, 3, 2),
        },
    },
    "en": {
        "titulo": "LETTER OF INVITATION AND ACCOMMODATION",
        "subtitulo": "(SHORT STAY IN BELGIUM)",
        "destinatario": "For the attention of the competent authorities.",
        "declaracao": (
            "I, the undersigned, ",
            ", born on ",
            ", nationality: ",
            ", identity card: ",
            ", residing at ",
            ", telephone: ",
            ", hereby invite:",
        ),
        "tabela_rotulos": (
            "Surname and name:",
            "Nationality:",
            "Date of birth:",
            "Passport no.:",
            "Duration:",
        ),
        "duracao": ("from ", " to ", " (", " days)"),
        "item_1": (
            "This invitation is issued in the context of a ",
            "private visit",
            ".",
        ),
        "item_2": (
            "Throughout the duration of their stay in Belgium, the invited "
            "person will be accommodated at my home located at the following "
            "address: "
        ),
        "item_3": (
            "The invited person personally bears their travel, accommodation, "
            "food, insurance, transport and other expenses related to their "
            "stay."
        ),
        "fechos": (
            "This letter constitutes exclusively a private invitation and a "
            "confirmation of accommodation and does not constitute a "
            "financial commitment within the meaning of Annexe 3bis.",
            "I certify the accuracy of the information set out in this letter "
            "and remain available to the competent authorities for any "
            "verification concerning this invitation and the accommodation "
            "conditions.",
            "The invited person undertakes to comply with the conditions "
            "applicable to their stay and to leave the territory of the "
            "Schengen area at the end of the authorised period.",
        ),
        "local_e_data": ("Done at ", ", on "),
        "assinatura_rotulo": "Signature of the inviting person",
        "linhas": {
            "declaracao": 3,
            "itens": (1, 3, 2),
            "fechos": (2, 2, 2),
        },
    },
    "nl": {
        "titulo": "UITNODIGINGS- EN HUISVESTINGSBRIEF",
        "subtitulo": "(KORT VERBLIJF IN BELGIË)",
        "destinatario": "Ter attentie van de bevoegde autoriteiten.",
        "declaracao": (
            "Ik, ondergetekende, ",
            ", geboren op ",
            ", nationaliteit: ",
            ", identiteitskaart: ",
            ", wonende te ",
            ", telefoon: ",
            ", nodig hierbij uit:",
        ),
        "tabela_rotulos": (
            "Naam en voornaam:",
            "Nationaliteit:",
            "Geboortedatum:",
            "Paspoortnr.:",
            "Duur:",
        ),
        "duracao": ("van ", " tot ", " (", " dagen)"),
        "item_1": (
            "Deze uitnodiging wordt opgesteld in het kader van een ",
            "privébezoek",
            ".",
        ),
        "item_2": (
            "Gedurende de volledige duur van zijn of haar verblijf in België "
            "zal de uitgenodigde persoon worden gehuisvest in mijn woning op "
            "het volgende adres: "
        ),
        "item_3": (
            "De uitgenodigde persoon draagt persoonlijk zijn of haar kosten "
            "voor reis, verblijf, voeding, verzekering, vervoer en andere "
            "uitgaven die verband houden met het verblijf."
        ),
        "fechos": (
            "Deze brief vormt uitsluitend een privé-uitnodiging en een "
            "bevestiging van huisvesting en houdt geen verbintenis tot "
            "financiële tenlasteneming in de zin van Annexe 3bis in.",
            "Ik bevestig de juistheid van de in deze brief vermelde gegevens "
            "en blijf ter beschikking van de bevoegde autoriteiten voor elke "
            "verificatie betreffende deze uitnodiging en de "
            "huisvestingsvoorwaarden.",
            "De uitgenodigde persoon verbindt zich ertoe de op het verblijf "
            "toepasselijke voorwaarden na te leven en het grondgebied van de "
            "Schengenruimte te verlaten na afloop van de toegestane duur.",
        ),
        "local_e_data": ("Gedaan te ", ", op "),
        "assinatura_rotulo": "Handtekening van de uitnodigende persoon",
        "linhas": {
            "declaracao": 3,
            "itens": (1, 3, 2),
            "fechos": (2, 3, 2),
        },
    },
    "pt": {
        "titulo": "CARTA DE CONVITE E DE ALOJAMENTO",
        "subtitulo": "(ESTADA DE CURTA DURAÇÃO NA BÉLGICA)",
        "destinatario": "À atenção das autoridades competentes.",
        "declaracao": (
            "Eu, ",
            ", nascido(a) em ",
            ", de nacionalidade ",
            ", titular do documento de identidade nº ",
            ", domiciliado(a) em ",
            ", telefone: ",
            ", convido pela presente:",
        ),
        "tabela_rotulos": (
            "Apelido e nome:",
            "Nacionalidade:",
            "Data de nascimento:",
            "N.º de passaporte:",
            "Duração:",
        ),
        "duracao": ("de ", " a ", " (", " dias)"),
        "item_1": (
            "O presente convite é emitido no âmbito de uma ",
            "visita privada",
            ".",
        ),
        "item_2": (
            "Durante todo o período da sua estada na Bélgica, a pessoa "
            "convidada será alojada no meu domicílio, sito no seguinte "
            "endereço: "
        ),
        "item_3": (
            "A pessoa convidada assume pessoalmente as suas despesas de "
            "viagem, de estada, de alimentação, de seguro, de transporte e "
            "outras despesas relacionadas com a sua estada."
        ),
        "fechos": (
            "A presente carta constitui exclusivamente um convite privado e "
            "uma confirmação de alojamento e não constitui um compromisso de "
            "tomada a cargo financeira na aceção do Annexe 3bis.",
            "Certifico a exatidão das informações constantes da presente "
            "carta e permaneço à disposição das autoridades competentes para "
            "qualquer verificação relativa a este convite e às condições de "
            "alojamento.",
            "A pessoa convidada compromete-se a respeitar as condições "
            "aplicáveis à sua estada e a abandonar o território do espaço "
            "Schengen no termo do período autorizado.",
        ),
        "local_e_data": ("Feito em ", ", em "),
        "assinatura_rotulo": "Assinatura da convidante",
        "linhas": {
            "declaracao": 3,
            "itens": (1, 2, 2),
            "fechos": (2, 3, 2),
        },
    },
}


class IdiomaDesconhecidoError(KeyError):
    """Pediram um idioma que a Carta Convite nao tem."""


def conteudo_de(idioma):
    try:
        return CONTEUDO[idioma]
    except KeyError:
        raise IdiomaDesconhecidoError(
            f'A Carta Convite não tem conteúdo em "{idioma}"; '
            f"há {', '.join(IDIOMAS)}."
        ) from None


def _alternar(literais, campos):
    """
    Monta `literal, campo, literal, campo, ..., literal`.

    E a forma de todo trecho corrido do documento que intercala texto fixo
    e campo dinamico. A sequencia de CAMPOS e estrutural (igual nos quatro
    idiomas); so os literais entre eles vem da traducao.
    """
    partes = []
    for posicao, literal in enumerate(literais):
        if literal:
            partes.append(trecho(literal))
        if posicao < len(campos):
            referencia, negrito = campos[posicao]
            partes.append(campo(referencia, negrito=negrito))
    return misto(*partes)


# ---------------------------------------------------------------------------
# O layout
# ---------------------------------------------------------------------------


def layout(idioma, *, asset_do_logo=0):
    """
    O layout estrutural completo do modelo oficial naquele idioma.

    `asset_do_logo` e o id do `content.Asset` com o logo do IBZ. Zero
    significa "ainda nao ha asset": o elemento continua existindo, so
    aponta para lugar nenhum -- e assim o layout pode ser montado e
    validado sem depender do banco.
    """
    conteudo = conteudo_de(idioma)
    quantas = conteudo["linhas"]
    elementos = []

    def ident(sufixo):
        return f"{idioma}-{sufixo}"

    # --- faixa tricolor -----------------------------------------------------
    largura_de_cada = FAIXA_LARGURA_TOTAL / len(FAIXA_CORES)
    for posicao, cor in enumerate(FAIXA_CORES):
        elementos.append({
            "id": ident(f"faixa-{posicao}"),
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
    elementos.append(_texto(
        ident("titulo"), texto(conteudo["titulo"]), idioma=idioma,
        x=MARGEM_ESQUERDA, base=BASE_TITULO, largura=LARGURA_DO_TEXTO,
        alinhamento="center", tamanho=TAMANHO_DO_TITULO, negrito=True,
    ))
    elementos.append(_texto(
        ident("subtitulo"), texto(conteudo["subtitulo"]), idioma=idioma,
        x=MARGEM_ESQUERDA, base=BASE_SUBTITULO, largura=LARGURA_DO_TEXTO,
        alinhamento="center",
    ))
    elementos.append(_texto(
        ident("destinatario"), texto(conteudo["destinatario"]), idioma=idioma,
        x=MARGEM_ESQUERDA, base=BASE_DESTINATARIO, largura=LARGURA_DO_TEXTO,
    ))

    # --- declaracao do anfitriao -------------------------------------------
    #
    # Linha corrida com negrito ALTERNANDO dentro dela. E o trecho que
    # exigiu a enfase por parte de `mixed`.
    elementos.append(_texto(
        ident("declaracao"),
        _alternar(conteudo["declaracao"], CAMPOS_DA_DECLARACAO),
        idioma=idioma,
        x=MARGEM_ESQUERDA, base=BASE_DECLARACAO, largura=LARGURA_DO_TEXTO,
        linhas=quantas["declaracao"], alinhamento="justify", rico=True,
    ))

    # --- tabela do convidado ------------------------------------------------
    rotulos = conteudo["tabela_rotulos"]
    linhas_da_tabela = [
        _linha_da_tabela(TABELA_LINHAS[posicao], rotulos[posicao], campo(referencia))
        for posicao, referencia in enumerate(CAMPOS_DA_TABELA)
    ]
    linhas_da_tabela.append(_linha_da_tabela(
        TABELA_LINHAS[4], rotulos[4],
        _alternar(conteudo["duracao"], [(ref, False) for ref in CAMPOS_DA_DURACAO]),
    ))
    elementos.append({
        "id": ident("tabela"),
        "type": "table",
        "x": TABELA_X,
        "y": TABELA_Y,
        "width": TABELA_LARGURA,
        "height": TABELA_ALTURA,
        "properties": {
            "columns": [{"width": largura, "align": "left"} for largura in TABELA_COLUNAS],
            "rows": linhas_da_tabela,
            "border_width": TABELA_BORDA,
            "border_color": "#000000",
            "cell_padding": dict(TABELA_ESPACAMENTO),
            **_tipografia(),
            "align": "left",
            "line_height": ENTRELINHA,
        },
    })

    # --- lista numerada -----------------------------------------------------
    prefixo, destaque, sufixo = conteudo["item_1"]
    corpos = (
        misto(trecho(prefixo), trecho(destaque, negrito=True), trecho(sufixo)),
        misto(trecho(conteudo["item_2"]), campo("anfitriao.endereco", negrito=True)),
        texto(conteudo["item_3"]),
    )
    bases = (
        BASE_DOS_ITENS[0],
        BASE_DOS_ITENS[1],
        _base_do_item_3(quantas["itens"][1]),
    )
    for posicao, corpo in enumerate(corpos):
        numero = posicao + 1
        elementos.append(_texto(
            ident(f"item-{numero}-marcador"), texto(f"{numero}."), idioma=idioma,
            x=LISTA_X_MARCADOR, base=bases[posicao], largura=LISTA_LARGURA_MARCADOR,
        ))
        elementos.append(_texto(
            ident(f"item-{numero}"), corpo, idioma=idioma,
            x=LISTA_X_CORPO, base=bases[posicao], largura=LISTA_LARGURA_CORPO,
            linhas=quantas["itens"][posicao], alinhamento="justify",
            rico=corpo.get("kind") == "mixed",
        ))

    # --- paragrafos de fecho ------------------------------------------------
    for posicao, corpo in enumerate(conteudo["fechos"]):
        elementos.append(_texto(
            ident(f"fecho-{posicao + 1}"), texto(corpo), idioma=idioma,
            x=MARGEM_ESQUERDA, base=BASE_DOS_FECHOS[posicao], largura=LARGURA_DO_TEXTO,
            linhas=quantas["fechos"][posicao], alinhamento="justify",
        ))

    # --- local e data -------------------------------------------------------
    elementos.append(_texto(
        ident("local-e-data"),
        _alternar(conteudo["local_e_data"],
                  [(ref, False) for ref in CAMPOS_DO_LOCAL_E_DATA]),
        idioma=idioma,
        x=MARGEM_ESQUERDA, base=BASE_LOCAL_E_DATA, largura=LARGURA_DO_TEXTO,
        alinhamento="right", rico=True,
    ))

    # --- logo e QR ----------------------------------------------------------
    elementos.append({
        "id": ident("logo-ibz"),
        "type": "image",
        "x": LOGO_X, "y": LOGO_Y, "width": LOGO_LARGURA, "height": LOGO_ALTURA,
        "properties": {
            "source": {"kind": "asset", "asset_id": int(asset_do_logo)},
            "fit": "contain",
            "preserve_aspect_ratio": True,
        },
    })
    elementos.append({
        "id": ident("qr-code"),
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
        "id": ident("assinatura-linha"),
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
        ident("assinatura-nome"), campo("anfitriao.nome"), idioma=idioma,
        x=MARGEM_ESQUERDA, base=BASE_ASSINATURA_NOME, largura=LARGURA_DO_TEXTO,
        negrito=True,
    ))
    elementos.append(_texto(
        ident("assinatura-rotulo"), texto(conteudo["assinatura_rotulo"]),
        idioma=idioma,
        x=MARGEM_ESQUERDA, base=BASE_ASSINATURA_ROTULO, largura=LARGURA_DO_TEXTO,
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


def inventario(desenho=None, *, idioma="fr"):
    """
    O layout numa forma conferivel linha a linha.

    Serve a revisao visual da reconstrucao: da para pegar esta lista e o
    PDF oficial lado a lado e comparar posicao, tamanho e conteudo de
    cada elemento sem abrir o JSON.
    """
    from ..layout_schema import referencias_de

    desenho = desenho if desenho is not None else layout(idioma)
    linhas = []
    for posicao, elemento in enumerate(desenho.get("elements", [])):
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


def inventario_texto(desenho=None, *, idioma="fr"):
    """O inventario como texto, para imprimir no terminal."""
    linhas = inventario(desenho, idioma=idioma)
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


def slug_do_modelo(idioma):
    """O slug do modelo oficial daquele idioma, na biblioteca."""
    from .biblioteca import slug_oficial

    return slug_oficial(idioma)


def id_do_logo(idioma):
    """O id estavel do elemento do logo, para `vincular_logo()` acha-lo."""
    return f"{idioma}-logo-ibz"


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

    E UM SO para os quatro idiomas: a arte e a mesma, e duplicar o
    binario por idioma so criaria versoes podendo divergir.

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


def _sincronizar(DocumentTemplate, modelo):
    """
    `update()` pula o `save()` -- e com ele a sincronizacao dos vinculos
    com os assets. Refeita aqui, para o PROTECT valer tambem para o logo
    do oficial. Tolerante ao modelo historico das migrations.
    """
    from ..models import sincronizar_assets_do_modelo

    sincronizar_assets_do_modelo(DocumentTemplate, modelo)


def aplicar(DocumentTemplate, idioma, *, asset_do_logo=0, forcar=False):
    """
    Grava o layout reconstruido no modelo oficial daquele idioma.

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

    slug = slug_do_modelo(idioma)
    modelo = DocumentTemplate.objects.filter(slug=slug).first()
    if modelo is None:
        return None
    if modelo.layout and not forcar:
        return None

    desenho = layout(idioma, asset_do_logo=asset_do_logo)
    validate_layout(desenho)
    DocumentTemplate.objects.filter(pk=modelo.pk).update(layout=desenho)
    modelo.layout = desenho
    _sincronizar(DocumentTemplate, modelo)
    return modelo


def vincular_logo(DocumentTemplate, idioma, asset_id):
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

    slug = slug_do_modelo(idioma)
    alvo = id_do_logo(idioma)
    modelo = DocumentTemplate.objects.filter(slug=slug).first()
    if modelo is None or not modelo.layout:
        return None

    desenho = copy.deepcopy(modelo.layout)
    mudou = False
    for elemento in desenho.get("elements", []):
        if elemento.get("id") != alvo or elemento.get("type") != "image":
            continue
        propriedades = elemento.setdefault("properties", {})
        if (propriedades.get("source") or {}).get("asset_id") != int(asset_id):
            propriedades["source"] = {"kind": "asset", "asset_id": int(asset_id)}
            mudou = True

    if not mudou:
        return None
    validate_layout(desenho)
    DocumentTemplate.objects.filter(pk=modelo.pk).update(layout=desenho)
    modelo.layout = desenho
    _sincronizar(DocumentTemplate, modelo)
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
    idioma: str
    modelo: object
    layout_gravado: bool
    asset: object
    asset_criado: bool
    logo_vinculado: bool


def reconstruir(DocumentTemplate, Asset, idioma="fr", *, forcar=False, caminho=None):
    """
    O caminho completo de um idioma: grava o layout e anexa o logo.

    Idempotente: rodar de novo nao duplica o asset nem reescreve um
    layout ja existente (a menos de `forcar=True`).
    """
    slug = slug_do_modelo(idioma)
    gravado = aplicar(DocumentTemplate, idioma, forcar=forcar) is not None
    asset, criado = garantir_asset_do_logo(Asset, caminho=caminho)
    vinculado = vincular_logo(DocumentTemplate, idioma, asset.pk) is not None
    return Reconstrucao(
        slug=slug,
        idioma=idioma,
        modelo=DocumentTemplate.objects.filter(slug=slug).first(),
        layout_gravado=gravado,
        asset=asset,
        asset_criado=criado,
        logo_vinculado=vinculado,
    )


def reconstruir_todos(DocumentTemplate, Asset, *, forcar=False, caminho=None):
    """Os quatro modelos oficiais, na ordem de `IDIOMAS`."""
    return [
        reconstruir(DocumentTemplate, Asset, idioma, forcar=forcar, caminho=caminho)
        for idioma in IDIOMAS
    ]
