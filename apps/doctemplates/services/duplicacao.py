"""
Duplicacao de modelos da biblioteca (Etapa 2 da nova arquitetura).

O fluxo que isto habilita:

    modelo oficial (travado ou nao)  ->  duplicar  ->  modelo INDEPENDENTE e editavel

A copia e um registro novo, comum (`is_system=False`), destravado
(`is_locked=False`), com os mesmos tipo, idioma, descricao, `field_schema`
e `layout` da origem -- e com `duplicated_from` apontando para ela, so
como linhagem. A partir dai as duas vivem separadas: nada que se faca na
copia alcanca a origem, e vice-versa.

INDEPENDENCIA DE VERDADE
------------------------
`field_schema` e `layout` sao dicionarios aninhados. Uma copia rasa
(`dict(...)`) compartilharia as listas de campos e de elementos por
dentro, e editar um elemento da copia mudaria o da origem em silencio --
o pior tipo de bug, porque so aparece bem depois. Por isso `deepcopy`,
e por isso os testes alteram estruturas ANINHADAS da copia e conferem a
origem.

A ORIGEM NAO E TOCADA
---------------------
Duplicar so LE a origem. Nao ha `save()` nela, nao ha atributo alterado.
E isso que permite duplicar um modelo travado ou oficial sem esbarrar
nas guardas de `DocumentTemplate.save()` -- elas continuam valendo para
a origem, e a copia nasce fora delas.
"""

from copy import deepcopy

from django.db import transaction
from django.utils.text import slugify

from ..models import DocumentTemplate

# Espaco reservado no slug para o sufixo de desambiguacao ("-2", "-99"...),
# para o resultado nunca estourar o max_length do campo.
_RESERVA_PARA_SUFIXO = 4


def slug_unico(nome, *, max_length=None):
    """
    Um slug valido e ainda nao usado por nenhum `DocumentTemplate`,
    derivado de `nome`.

    Deterministico e simples: `minha-carta-convite`; se ja existir,
    `minha-carta-convite-2`, depois `-3`, e assim por diante -- o primeiro
    livre. Nunca renomeia nem sobrescreve o slug de quem ja esta la.

    Um nome que nao produz slug nenhum (so simbolos, vazio) devolve "";
    a validacao do modelo e quem recusa isso, com a mensagem certa.
    """
    limite = max_length or DocumentTemplate._meta.get_field("slug").max_length
    base = slugify(nome or "")[: limite - _RESERVA_PARA_SUFIXO].strip("-")
    if not base:
        return ""

    usados = set(
        DocumentTemplate.objects.filter(slug__startswith=base).values_list("slug", flat=True)
    )
    if base not in usados:
        return base
    numero = 2
    while f"{base}-{numero}" in usados:
        numero += 1
    return f"{base}-{numero}"


def duplicar_modelo(origem, nome, created_by=None):
    """
    Cria e devolve uma copia independente de `origem` chamada `nome`.

    Funciona com origem comum, oficial (`is_system`), travada
    (`is_locked`) ou que ja seja copia de outra. `created_by` fica
    registrado como autor da copia. Tudo dentro de uma transacao: ou a
    copia inteira existe, ou nada mudou.

    A validacao e a do proprio modelo (`full_clean()`): nome vazio, slug
    impossivel ou JSON invalido sao recusados por ela, nao por regras
    repetidas aqui.
    """
    with transaction.atomic():
        copia = DocumentTemplate(
            type=origem.type,
            name=nome,
            slug=slug_unico(nome),
            language=origem.language,
            description=origem.description,
            is_system=False,
            is_locked=False,
            duplicated_from=origem,
            field_schema=deepcopy(origem.field_schema),
            layout=deepcopy(origem.layout),
            is_active=True,
            created_by=created_by,
        )
        copia.full_clean()
        copia.save()
    return copia
