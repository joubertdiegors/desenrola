"""
Renderer PDF GENERICO da nova arquitetura (Etapa 3.4).

    DocumentTemplate -> layout JSON -> dados -> renderer -> PDF A4

O PDF sai inteiro dos elementos do layout: cada texto e texto, cada
linha e um traco, a tabela e uma grade desenhada, o QR e gerado. O
documento oficial em PDF NAO entra aqui de forma nenhuma -- nem como
fundo, nem rasterizado, nem sob mascaras. Ele e referencia de medida, e
a medida ja foi tomada na Etapa 3.3.

DUAS CAMADAS, DE PROPOSITO
--------------------------
`render_layout()` e puro: recebe layout, pagina, contexto e os bytes das
imagens, e devolve bytes. Nao importa Django, nao toca banco, nao le
disco. E o que permite testar o motor inteiro sem migrations.

`render_template()` e a camada de aplicacao: le o `DocumentTemplate`,
carrega os `Asset` que o layout referencia e chama a camada pura. E o
unico ponto que conhece Django.

GENERICO
--------
O despacho e por tipo de elemento (`elementos.DESENHADORES`). Nao ha
nada aqui sobre carta-convite, sobre frances ou sobre coordenada
nenhuma: um contrato, uma declaracao ou um modelo em outro idioma
desenham pelo mesmo caminho, desde que usem os tipos registrados.
"""

import io

from django.core.exceptions import ValidationError

from ...layout_schema import referencias_usadas, validate_layout
from . import elementos
from .contexto import (
    CampoDesconhecidoError,
    Contexto,
    ValorAusenteError,
)

__all__ = [
    "AssetAusenteError",
    "CampoDesconhecidoError",
    "Contexto",
    "FonteIndisponivelError",
    "PaginaInvalidaError",
    "ValorAusenteError",
    "campos_do_layout",
    "carregar_assets",
    "render_layout",
    "render_template",
]

AssetAusenteError = elementos.AssetAusenteError
FonteIndisponivelError = elementos.FonteIndisponivelError

# Limites de sanidade da pagina. Nao ha documento util de 2pt nem de 20
# metros; um valor assim e sintoma de dado corrompido, e e melhor dizer
# isso do que gerar um PDF absurdo.
LADO_MINIMO = 10.0
LADO_MAXIMO = 20000.0


class PaginaInvalidaError(ValueError):
    """O `DocumentType.page` nao descreve uma pagina utilizavel."""


def _validar_pagina(pagina):
    if not isinstance(pagina, dict):
        raise PaginaInvalidaError("A página do tipo de documento deve ser um objeto.")
    try:
        largura = float(pagina["width"])
        altura = float(pagina["height"])
    except (KeyError, TypeError, ValueError):
        raise PaginaInvalidaError(
            'A página precisa de "width" e "height" numéricos.'
        ) from None
    for medida, nome in ((largura, "width"), (altura, "height")):
        if not LADO_MINIMO <= medida <= LADO_MAXIMO:
            raise PaginaInvalidaError(
                f'A página tem "{nome}" fora do razoável: {medida}pt.'
            )
    unidade = pagina.get("unit", "pt")
    if unidade != "pt":
        # O layout guarda pontos. Aceitar outra unidade sem converter
        # produziria um documento silenciosamente errado.
        raise PaginaInvalidaError(
            f'O renderer só trabalha em pontos; a página declara "{unidade}".'
        )
    return largura, altura


def render_layout(layout, pagina, contexto=None, *, assets=None, validar=True):
    """
    O PDF de um layout, em bytes. Camada PURA -- sem Django.

    `pagina` e o `DocumentType.page` (`{"width", "height", "unit"}`).
    `contexto` resolve os campos; `assets` e `{asset_id: bytes}`.

    Devolve `(bytes, relatorio)`, em que o relatorio diz quantos
    elementos foram processados e desenhados -- e o que permite um teste
    afirmar que os 23 elementos do FR passaram, em vez de confiar que
    passaram.
    """
    from reportlab.pdfgen import canvas as canvas_do_reportlab

    from pdfengine import fontconfig

    if validar:
        validate_layout(layout)

    largura, altura = _validar_pagina(pagina)
    dimensoes = {"width": largura, "height": altura}

    if contexto is None:
        contexto = Contexto({}, estrito=False)

    # As fontes sao as versionadas em `pdfengine/fonts/`. Registrar aqui
    # (e nao no import) mantem o modulo barato de importar.
    fontconfig.register_fonts()

    saida = io.BytesIO()
    pagina_pdf = canvas_do_reportlab.Canvas(saida, pagesize=(largura, altura))
    pagina_pdf.setTitle("")

    recursos = {"assets": dict(assets or {})}
    relatorio = {"elementos": 0, "desenhados": 0, "por_tipo": {}}

    # A ORDEM da lista e a ordem de desenho: o primeiro fica ao fundo. E
    # o contrato da Etapa 3.1 -- nao ha z_index para consultar.
    for elemento in (layout or {}).get("elements", []):
        tipo = elemento.get("type")
        desenhar = elementos.desenhador(tipo)
        relatorio["elementos"] += 1
        quantos = desenhar(pagina_pdf, elemento, contexto, dimensoes, recursos)
        relatorio["desenhados"] += 1 if quantos else 0
        relatorio["por_tipo"][tipo] = relatorio["por_tipo"].get(tipo, 0) + 1

    pagina_pdf.showPage()
    pagina_pdf.save()
    return saida.getvalue(), relatorio


def render_template(modelo, dados=None, *, estrito=True, validar=True):
    """
    O PDF de um `DocumentTemplate`. Camada de aplicacao.

    `dados` e o dicionario plano `{"convidado.nome": "...", ...}`. Sao os
    valores do documento -- eles NAO ficam gravados no modelo, e e por
    isso que o mesmo modelo serve a todas as cartas.
    """
    layout = modelo.layout or {}
    if not layout.get("elements"):
        raise ValidationError(
            f'O modelo "{modelo.slug}" ainda não tem layout: não há o que desenhar.'
        )

    contexto = Contexto(dados or {}, estrito=estrito)
    return render_layout(
        layout,
        modelo.type.page,
        contexto,
        assets=carregar_assets(layout),
        validar=validar,
    )


def carregar_assets(layout):
    """
    Os bytes de cada `Asset` que o layout referencia.

    Carregados de uma vez, antes de desenhar: se faltar um arquivo, o
    erro aparece agora e nao no meio da pagina.

    PUBLICA de proposito (Etapa 3.5.2): `apps.letters.services.render_letter()`
    chama isto com o `layout` de um `document_snapshot` CONGELADO -- nao o
    de um `DocumentTemplate` ao vivo -- para resolver os assets de uma
    carta ja finalizada pelos mesmos ids que `LetterAsset` protege contra
    exclusao/substituicao (Etapa 3.5.1). A funcao em si nao sabe de onde o
    `layout` veio; so precisa que seja um layout valido.
    """
    from apps.content.models import Asset

    identificadores = {
        (elemento.get("properties") or {}).get("source", {}).get("asset_id")
        for elemento in layout.get("elements", [])
        if elemento.get("type") == "image"
    }
    identificadores.discard(None)
    identificadores.discard(0)
    if not identificadores:
        return {}

    conteudos = {}
    for asset in Asset.objects.filter(pk__in=identificadores):
        with asset.file.open("rb") as arquivo:
            conteudos[asset.pk] = arquivo.read()
    return conteudos


def campos_do_layout(layout):
    """As referencias que o layout imprime -- para montar/conferir o contexto."""
    return referencias_usadas(layout)
