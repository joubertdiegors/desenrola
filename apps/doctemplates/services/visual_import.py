"""
Importa o mapa do documento oficial frances para dentro do editor visual
(Fase 5, Etapa 4.2B).

O QUE ESTE MODULO FAZ -- E O QUE NAO FAZ
----------------------------------------
Ele LE `pdfengine.layouts.carta_convite_fr` e produz um `visual_schema`
equivalente. Nao mede nada, nao estima nada, nao inventa nada: cada
numero que sai daqui foi medido do PDF oficial quando aquele mapa foi
construido. O renderer continua intocado e continua sendo a referencia.

COMO O DOCUMENTO FRANCES E MONTADO HOJE
---------------------------------------
E importante entender isto antes de ler o resto, porque explica a forma
do resultado. O renderer NAO desenha o documento: ele usa o PDF oficial
como base, APAGA nove areas variaveis (as mascaras) e escreve os valores
reais por cima (`pdfengine/render.py`). Tudo o que e fixo -- faixa
tricolor, logo do IBZ, QR Code, bordas da tabela, texto legal, linha da
assinatura -- vive dentro do PDF base e NUNCA foi medido para o mapa.

Entao o mapa tem exatamente tres coisas mensuraveis:

    1. a pagina e as fontes;
    2. nove mascaras (retangulos que cobrem os valores de amostra);
    3. nove caixas de texto com o molde de cada area variavel.

O que o editor recebe reflete isso, em tres camadas:

    z=0    uma IMAGEM da pagina oficial, ao fundo
    z=10   os nove retangulos brancos das mascaras
    z=20   os nove paragrafos/campos variaveis

A imagem de fundo e uma rasterizacao fiel da pagina 1 do PDF oficial --
nao um desenho aproximado dela. E o unico jeito honesto de mostrar a
faixa tricolor, o logo, o QR e as bordas da tabela sem inventar
coordenada nenhuma para eles. Ela serve ao EDITOR, como referencia
visual; o PDF continua sendo gerado a partir do arquivo oficial, nunca
da imagem (ver `is_base_reference` abaixo).

SISTEMAS DE COORDENADAS
-----------------------
O mapa esta em coordenadas PDF (origem embaixo, Y para cima). O editor
usa origem em cima. A conversao passa toda por
`apps.doctemplates.coordinates`, e so por ela.

Um detalhe que nao e obvio: o mapa ancora texto pela LINHA DE BASE
(`first_baseline_y`), enquanto o editor ancora pelo TOPO da caixa. Ir de
um ao outro exige saber quanto a fonte sobe acima da linha de base --
o "ascent". Esse valor nao e chutado: vem da metrica da propria fonte
que o renderer usa (Liberation Sans, via reportlab). A linha de base
original continua guardada em `properties.first_baseline_y`, para a
Etapa 4.2D poder desenhar exatamente onde o renderer desenha hoje, sem
depender de refazer esta conta ao contrario.
"""

import hashlib
import io

from django.core.files.base import ContentFile

from pdfengine.layouts import carta_convite_fr as mapa_fr
from pdfengine.layouts.carta_convite_fr import FieldRef

from ..coordinates import do_pdf_para_documento
from ..visual_schema import (
    FIELD,
    IMAGE,
    RECT,
    RICH_TEXT,
    SCHEMA_VERSION,
    validate_visual_schema,
)

# Identificador do Asset que guarda a imagem de fundo. Fixo: reimportar
# reaproveita o mesmo registro em vez de encher a biblioteca de copias.
CHAVE_DO_ASSET_FR = "modelo-carta-convite-fr-base"

# Resolucao da rasterizacao da pagina oficial. 2x sobre os 72pt/pol do
# PDF da 144 DPI -- nitido o bastante para conferir posicao de texto no
# editor com zoom, e ainda um PNG de tamanho razoavel.
ESCALA_DA_BASE = 2.0

# Camadas. Deixar buracos entre elas e proposital: da espaco para o
# administrador intercalar elementos proprios sem precisar renumerar
# nada.
Z_BASE = 0
Z_MASCARA = 10
Z_CONTEUDO = 20

# O vocabulario de campos DO DOCUMENTO -- nao o do formulario.
#
# Sao coisas diferentes e confundi-las quebraria a importacao: o
# formulario pergunta `guest_birth_date`, o documento imprime
# `guest_birth`; e `duration_days`, `place` e `document_date` nem existem
# como pergunta, sao calculados na emissao (ver
# `apps.letters.pdf_generation.build_pdf_fields`). Quem manda aqui e o
# documento, entao a lista vem do proprio mapa do renderer.
CAMPOS_DO_DOCUMENTO_FR = tuple(mapa_fr.REQUIRED_FIELDS)


def campos_do_documento(template_slug):
    """
    As referencias de campo que o documento daquele modelo sabe imprimir.

    Hoje so o frances tem documento implementado; os outros idiomas
    entram aqui quando ganharem o seu (Etapa 4.2 e seguintes). Devolver
    vazio para um modelo desconhecido e deliberado: melhor recusar uma
    referencia do que aceitar qualquer nome.
    """
    from ..official_templates import official_slug

    if template_slug == official_slug("fr"):
        return set(CAMPOS_DO_DOCUMENTO_FR)
    return set()


# ---------------------------------------------------------------------------
# Metrica da fonte: linha de base -> topo da caixa
# ---------------------------------------------------------------------------


def _ascent(font_size, fonte=None):
    """
    Quanto a fonte sobe acima da linha de base, em pontos.

    Vem da metrica real da Liberation Sans registrada no reportlab -- a
    MESMA fonte que o renderer embute. Nao e estimativa.
    """
    from reportlab.pdfbase import pdfmetrics

    from pdfengine import fontconfig

    fontconfig.register_fonts()
    return pdfmetrics.getAscent(fonte or fontconfig.REGULAR, font_size)


def caixa_da_zona(zone):
    """
    A caixa de uma zona nas coordenadas do editor (origem em cima).

    Altura = `max_lines * leading`: e a area que o renderer reserva para
    aquela zona, nem mais nem menos. O topo sai da linha de base da
    primeira linha, subindo o ascent da fonte.
    """
    caixa = zone.box
    altura = caixa.max_lines * caixa.leading
    topo_em_pdf = caixa.first_baseline_y + _ascent(caixa.font_size)

    # `do_pdf_para_documento` espera a caixa ancorada na BASE, como tudo
    # em PDF: a base desta caixa esta `altura` abaixo do topo.
    return do_pdf_para_documento(
        {
            "x": caixa.x,
            "y": topo_em_pdf - altura,
            "width": caixa.width,
            "height": altura,
        },
        altura_da_pagina=mapa_fr.PAGE_HEIGHT,
    )


def caixa_da_mascara(zone):
    """A mascara da zona nas coordenadas do editor."""
    return do_pdf_para_documento(
        {
            "x": zone.mask.x,
            "y": zone.mask.y,
            "width": zone.mask.width,
            "height": zone.mask.height,
        },
        altura_da_pagina=mapa_fr.PAGE_HEIGHT,
    )


# ---------------------------------------------------------------------------
# Conversao das zonas
# ---------------------------------------------------------------------------


def _estilo_de_texto(zone):
    """Estilo comum as zonas -- tudo vindo do mapa, nada arbitrado."""
    return {
        "font_family": mapa_fr.FONT_REGULAR,
        "font_size": zone.box.font_size,
        "font_weight": "regular",
        "italic": False,
        # O documento justifica os paragrafos do corpo; celulas de tabela
        # e linhas soltas, nao (`TextBox.justify`).
        "align": "justify" if zone.box.justify else "left",
        "vertical_align": "top",
        "color": "#000000",
        "letter_spacing": 0,
        "wrap": True,
        # Texto que nao cabe reduz a fonte ate `min_font_size`, como o
        # renderer faz -- nunca transborda por cima de um elemento fixo.
        "overflow": "shrink",
        "leading": zone.box.leading,
        "min_font_size": zone.box.min_font_size,
        "max_lines": zone.box.max_lines,
        # Guardada para a Etapa 4.2D desenhar exatamente onde o renderer
        # desenha hoje, sem refazer a conta do ascent ao contrario.
        "first_baseline_y": zone.box.first_baseline_y,
    }


def _elemento_da_zona(zone):
    """
    A zona como elemento do editor.

    Zona de um unico campo vira `field` -- e o tipo que o editor ja
    oferece com seletor de campo. Zona que mistura texto fixo e campos
    vira `rich_text`, que guarda a sequencia de trechos intacta.
    """
    caixa = caixa_da_zona(zone)
    comum = {
        "id": f"fr-{zone.key}",
        "x": caixa["x"],
        "y": caixa["y"],
        "width": caixa["width"],
        "height": caixa["height"],
        "z_index": Z_CONTEUDO,
    }

    somente_um_campo = len(zone.runs) == 1 and isinstance(zone.runs[0], FieldRef)
    if somente_um_campo:
        referencia = zone.runs[0]
        propriedades = _estilo_de_texto(zone)
        propriedades["field"] = referencia.key
        if referencia.bold:
            propriedades["font_weight"] = "bold"
        return {**comum, "type": FIELD, "properties": propriedades}

    return {
        **comum,
        "type": RICH_TEXT,
        "properties": {
            **_estilo_de_texto(zone),
            "runs": [
                {"field": trecho.key, "bold": trecho.bold}
                if isinstance(trecho, FieldRef)
                else {"text": trecho.text, "bold": trecho.bold}
                for trecho in zone.runs
            ],
        },
    }


def _elemento_da_mascara(zone):
    """
    A mascara como retangulo branco.

    E o que ela e de fato: no renderer, um `c.rect(..., fill=1)` branco
    que cobre o valor de amostra antes de o valor real ser escrito. No
    editor ela cumpre o mesmo papel sobre a imagem de fundo.
    """
    caixa = caixa_da_mascara(zone)
    return {
        "id": f"fr-mask-{zone.key}",
        "type": RECT,
        "x": caixa["x"],
        "y": caixa["y"],
        "width": caixa["width"],
        "height": caixa["height"],
        "z_index": Z_MASCARA,
        "properties": {
            "border_width": 0,
            "border_color": "#ffffff",
            "fill_color": "#ffffff",
            "radius": 0,
        },
    }


def _elemento_da_base(asset_id):
    """A pagina oficial ao fundo, do tamanho exato do papel."""
    return {
        "id": "fr-base",
        "type": IMAGE,
        "x": 0.0,
        "y": 0.0,
        "width": mapa_fr.PAGE_WIDTH,
        "height": mapa_fr.PAGE_HEIGHT,
        "z_index": Z_BASE,
        "properties": {
            "asset_id": asset_id,
            "preserve_aspect_ratio": False,
            # AVISO PARA A ETAPA 4.2D: isto e uma imagem de REFERENCIA
            # para o editor, nao o documento. O PDF continua sendo gerado
            # a partir de pdfengine/assets/fr/Modelo-Carta-Convite-FR.pdf.
            # Desenhar esta imagem no PDF final degradaria o documento
            # (raster por cima de vetor) e duplicaria o fundo.
            "is_base_reference": True,
        },
    }


# ---------------------------------------------------------------------------
# Rasterizacao da pagina oficial
# ---------------------------------------------------------------------------


def rasterizar_pagina_oficial(escala=ESCALA_DA_BASE):
    """
    A pagina 1 do PDF oficial como PNG.

    `pypdfium2` ja estava nas dependencias do projeto exatamente para
    isto (ver requirements/base.txt: "rasterizar paginas para o editor
    visual de mapeamento").
    """
    import pypdfium2

    from pdfengine.render import BASE_PDF_PATH

    documento = pypdfium2.PdfDocument(str(BASE_PDF_PATH))
    try:
        imagem = documento[0].render(scale=escala).to_pil()
        buffer = io.BytesIO()
        # `optimize` sem metadados: o mesmo PDF gera sempre os mesmos
        # bytes, o que mantem a importacao deterministica.
        imagem.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
    finally:
        documento.close()


def obter_asset_da_base():
    """
    O `Asset` com a imagem da pagina oficial, criando-o se ainda nao
    existir.

    Reaproveita o modelo Asset do app `content` -- nao ha sistema
    paralelo de imagens. Se o PDF oficial mudar, os bytes mudam e o
    arquivo e regravado; se nao mudar, nada acontece (a comparacao e por
    SHA-256, nao por data).
    """
    from apps.content.models import Asset

    conteudo = rasterizar_pagina_oficial()
    impressao = hashlib.sha256(conteudo).hexdigest()

    asset, _criado = Asset.objects.get_or_create(
        key=CHAVE_DO_ASSET_FR,
        defaults={
            "kind": Asset.Kind.OTHER,
            "alt_text": "Modelo oficial da Carta Convite (francês)",
            "is_active": True,
        },
    )

    atual = ""
    if asset.file:
        try:
            with asset.file.open("rb") as arquivo:
                atual = hashlib.sha256(arquivo.read()).hexdigest()
        except (FileNotFoundError, OSError):
            atual = ""

    if atual != impressao:
        asset.file.save(f"{CHAVE_DO_ASSET_FR}.png", ContentFile(conteudo), save=False)
    if not asset.is_active:
        asset.is_active = True
    asset.save()
    return asset


# ---------------------------------------------------------------------------
# A importacao
# ---------------------------------------------------------------------------


def construir_visual_schema_fr(asset_id):
    """
    O `visual_schema` do documento frances.

    Funcao pura: dado o mesmo `asset_id`, devolve sempre exatamente o
    mesmo dicionario. Os ids dos elementos derivam da chave da zona
    (`fr-host_paragraph`, `fr-mask-host_paragraph`), nao de UUID nem de
    relogio -- reimportar nao pode produzir um documento "diferente" que
    so o diff saberia explicar.
    """
    elementos = [_elemento_da_base(asset_id)]
    for zone in mapa_fr.ZONES:
        elementos.append(_elemento_da_mascara(zone))
    for zone in mapa_fr.ZONES:
        elementos.append(_elemento_da_zona(zone))

    documento = {
        "schema_version": SCHEMA_VERSION,
        "page": {
            "width": mapa_fr.PAGE_WIDTH,
            "height": mapa_fr.PAGE_HEIGHT,
            "unit": "pt",
            "origin": "top-left",
        },
        "elements": elementos,
    }

    # Falhar aqui e melhor do que gravar um documento que o editor nao
    # consegue abrir.
    validate_visual_schema(documento, field_keys=set(CAMPOS_DO_DOCUMENTO_FR))
    return documento


def importar_modelo_oficial(version):
    """
    Substitui o layout de `version` pelo do documento oficial do idioma.

    E DESTRUTIVO: o que estava no rascunho e descartado. Quem chama e
    responsavel por confirmar com a pessoa antes.

    Nao decide permissao e nao mexe em versao publicada -- isso e da
    view. Aqui vale a regra do modelo: uma versao publicada recusa a
    gravacao no proprio `save()`.
    """
    from ..official_templates import official_slug

    if version.template.slug != official_slug("fr"):
        raise ValueError(
            f'Ainda não há documento oficial implementado para "{version.template.slug}". '
            "Só o francês tem layout medido."
        )

    asset = obter_asset_da_base()
    version.visual_schema = construir_visual_schema_fr(asset.pk)
    version.save(update_fields=["visual_schema", "updated_at"])
    return version.visual_schema
