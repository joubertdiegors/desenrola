"""
Semeadura da biblioteca de modelos: o tipo "Carta Convite" e os seus
quatro modelos oficiais (Etapa 1 da nova arquitetura).

Uma funcao so, usada pela migration de dados E disponivel para codigo
de aplicacao (comando de gestao futuro, testes). Por isso ela recebe as
classes de modelo por parametro: numa migration as classes vem de
`apps.get_model()` (o estado historico), fora dela vem do import normal.
Nao ha duas versoes da mesma semeadura para divergirem.

DETERMINISTICA E IDEMPOTENTE
----------------------------
Slugs fixos (`carta-convite-fr`...), sem UUID nem relogio. Cada registro e
procurado pelo slug/codigo antes de ser criado: rodar duas vezes nao cria
copia nenhuma -- e nao TOCA no que ja existe. Isso e deliberado: um
modelo oficial pode ter sido travado ou ter recebido descricao pelo
administrador, e a semeadura nao pode desfazer isso.

O QUE VAI EM CADA MODELO
------------------------
  field_schema -- o schema vigente da Carta Convite, o MESMO que hoje
                  esta na versao publicada de cada idioma
                  (`official_templates.CARTA_CONVITE_FIELD_SCHEMA`, com as
                  traducoes fr/nl/en ja existentes). Nada novo e escrito.
  layout       -- vazio (`{}`). O desenho vem depois: o FR sera
                  reconstruido do PDF oficial; NL/EN/PT seguirao a
                  estrutura do FR com o texto de cada idioma.
  is_system    -- True: sao os oficiais.
  is_locked    -- False: nascem editaveis e so sao travados quando o
                  administrador aprovar visualmente.
"""

import copy

from ..official_templates import CARTA_CONVITE_FIELD_SCHEMA

CODIGO_CARTA_CONVITE = "carta-convite"

# A4 em pontos -- a unidade do `layout` (ver layout_schema.py).
PAGINA_A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}

# Fontes de dados que a Carta Convite expoe no editor. O registro que da
# significado a cada codigo e etapa posterior.
FONTES_DE_DADOS_CARTA_CONVITE = ["documento", "convidado", "anfitriao", "calculado"]

# Um modelo oficial por idioma do site, na ordem em que aparecem na
# biblioteca. Nomes fixos, como pedidos pelo produto.
MODELOS_OFICIAIS = (
    ("fr", "carta-convite-fr", "Carta Convite — Français"),
    ("nl", "carta-convite-nl", "Carta Convite — Nederlands"),
    ("en", "carta-convite-en", "Carta Convite — English"),
    ("pt", "carta-convite-pt", "Carta Convite — Português"),
)


def slug_oficial(language):
    """O slug do modelo oficial da Carta Convite naquele idioma."""
    for codigo, slug, _nome in MODELOS_OFICIAIS:
        if codigo == language:
            return slug
    raise ValueError(f"não há modelo oficial da Carta Convite para o idioma {language!r}")


def semear_carta_convite(DocumentType, DocumentTemplate):
    """
    Garante que o tipo "Carta Convite" e os quatro modelos oficiais
    existam. Devolve `(tipo, [modelos])`. Nao altera registros existentes.
    """
    tipo, _criado = DocumentType.objects.get_or_create(
        code=CODIGO_CARTA_CONVITE,
        defaults={
            "name": "Carta Convite",
            "description": (
                "Carta de convite e hospedagem para estadia de curta duração "
                "na Bélgica (até 90 dias)."
            ),
            "is_active": True,
            "page": dict(PAGINA_A4),
            "data_sources": list(FONTES_DE_DADOS_CARTA_CONVITE),
            "order": 0,
        },
    )

    modelos = []
    for language, slug, nome in MODELOS_OFICIAIS:
        modelo, _criado = DocumentTemplate.objects.get_or_create(
            slug=slug,
            defaults={
                "type": tipo,
                "name": nome,
                "language": language,
                "description": "",
                "is_system": True,
                "is_locked": False,
                "is_active": True,
                # deepcopy: o dicionario do modulo nunca pode ser
                # compartilhado com o que vai para o banco.
                "field_schema": copy.deepcopy(CARTA_CONVITE_FIELD_SCHEMA),
                "layout": {},
            },
        )
        modelos.append(modelo)
    return tipo, modelos


def semear():
    """Atalho para codigo de aplicacao (fora de migrations)."""
    from ..models import DocumentTemplate, DocumentType

    return semear_carta_convite(DocumentType, DocumentTemplate)
