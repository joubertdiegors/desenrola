"""
Quais textos cada seção da Home tem -- e só eles.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
`PageSectionTranslation.content` é um JSON livre: o formato depende do
tipo da seção, e o modelo não impõe forma nenhuma (de propósito -- ver o
docstring de `PageSection`). Isso resolve o armazenamento e deixa uma
pergunta aberta: **o que a tela de edição deve mostrar?**

A resposta não pode ser "um campo de JSON". Aqui está a declaração: por
seção, os textos que o template de fato lê, cada um com o rótulo que um
editor entende. O formulário é montado a partir daqui (ver `forms.py`),
então a tela nunca oferece um campo que a página ignora, nem esconde um
que ela mostra.

É o mesmo princípio de `doctemplates.official_templates`, que declara os
campos do assistente em vez de deixar o formulário adivinhar.

POR CHAVE, E NÃO SÓ POR TIPO
----------------------------
O `kind` diz a família da seção; a CHAVE diz exatamente o que aquele
lugar da página mostra. A Home tem duas seções `features` -- a barra de
confiança e o "Como funciona" -- e elas não têm os mesmos textos: uma é
só uma lista curta, a outra tem título, chamada e passos com descrição.
Declarar por `kind` obrigaria a inventar uma união dos dois, e a tela
ofereceria campos que uma das duas ignora.

A busca é por chave e, não achando, pelo tipo -- que cobre uma seção
sem chave própria.

O QUE NÃO ENTRA AQUI
--------------------
Ícone, ordem dos cartões, âncora, grade: isso é DESENHO, e mora no
template. O CMS cuida do que se escreve, não de como se desenha. Um
`ph-lock` num formulário de conteúdo seria pedir que um editor
soubesse o nome interno de uma fonte de ícones.

Acrescentar ou remover um cartão também não está aqui: a tela edita os
que existem. Um construtor de páginas é outra coisa, e não é o que este
produto precisa.
"""

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Texto:
    """Um texto simples da seção."""

    chave: str
    rotulo: str
    longo: bool = False
    ajuda: str = ""


@dataclass(frozen=True)
class Lista:
    """
    Uma lista de itens iguais dentro da seção (os cartões).

    `campos` são os textos de CADA item. A quantidade de itens não se
    edita aqui: a tela mostra os que existem no conteúdo gravado.
    """

    chave: str
    rotulo: str
    campos: tuple = field(default_factory=tuple)


# As seções da Home, pela chave que elas têm em `content.Page("home")`.
SECOES = {
    "hero": (
        Texto("title", _("Título principal")),
        Texto("lead", _("Texto de apoio"), longo=True),
        Texto("cta", _("Botão de criar conta")),
        Texto("login_prompt", _("Antes do link de entrar")),
        Texto("login_link", _("Texto do link de entrar")),
        Texto(
            "badge_label",
            _("Rótulo do contador"),
            longo=True,
            ajuda=_(
                "Aparece ao lado do número de cartas já geradas. "
                "A quebra de linha é respeitada."
            ),
        ),
        Texto("badge_note", _("Nota do contador")),
        Texto(
            "art_caption",
            _("Legenda da imagem"),
            ajuda=_("Texto dentro da moldura, enquanto não houver foto."),
        ),
    ),
    "trust": (
        Lista("cards", _("Itens"), campos=(Texto("title", _("Texto")),)),
    ),
    "partners": (
        Texto("title", _("Título da seção")),
        Texto("lead", _("Texto de apoio"), longo=True),
        Texto(
            "cta",
            _("Botão de cada parceiro"),
            ajuda=_("Os parceiros em si são cadastrados em Parceiros."),
        ),
    ),
    "how": (
        Texto("title", _("Título da seção")),
        Texto("lead", _("Texto de apoio"), longo=True),
        Lista(
            "cards",
            _("Passos"),
            campos=(
                Texto("title", _("Título do passo")),
                Texto("text", _("Descrição"), longo=True),
            ),
        ),
    ),
    "cta": (
        Texto("title", _("Título")),
        Texto("text", _("Texto de apoio"), longo=True),
        Texto("button", _("Botão")),
    ),
}


def campos_da_secao(secao):
    """
    A declaração de `secao`: pela chave e, não achando, pelo tipo.

    Tupla vazia para uma seção que ninguém declarou -- a tela avisa que
    não sabe editá-la, em vez de mostrar um JSON cru.
    """
    return SECOES.get(secao.key) or SECOES.get(secao.kind) or ()


def editavel(secao):
    """Esta seção tem textos declarados?"""
    return bool(campos_da_secao(secao))
