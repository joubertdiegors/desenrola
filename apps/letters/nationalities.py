"""
Ponte entre o cadastro de nacionalidades e a carta.

O que fica guardado em `Letter.data` e o CODIGO da nacionalidade, nunca o
texto. Isso e o que permite renomear "Brésilienne" no cadastro sem
reescrever o passado, e o que faz trocar o idioma da carta nao invalidar
o preenchimento.

O texto so aparece em dois momentos, e cada um tem a sua fonte:

  - na TELA, resolvido na hora, no idioma da carta;
  - no DOCUMENTO, congelado no snapshot no fechamento -- dali em diante a
    carta emitida nao depende mais do cadastro.

Cartas antigas, feitas quando o campo era texto livre, guardaram o
proprio texto. Por isso tudo aqui trata "codigo desconhecido" como "ja e
o texto final" e o devolve como esta, em vez de falhar.
"""

from django.core.signals import request_started
from django.db.models.signals import post_delete, post_save

from apps.doctemplates.models import Nationality

# As duas formas gramaticais que o documento oficial usa para a mesma
# nacionalidade -- ver o docstring de `Nationality`.
GUEST_FORM = "guest_form"
HOST_FORM = "host_form"

# Qual forma cada campo da carta usa.
FORM_BY_FIELD = {
    "guest_nationality": GUEST_FORM,
    "host_nationality": HOST_FORM,
}


# A lista e a mesma para todo mundo e muda raramente, mas e consultada
# muitas vezes na MESMA requisicao: o dashboard remonta o formulario de
# cada rascunho para descobrir em que etapa ele parou. Sem isto, cada
# carta listada custava uma consulta a mais.
#
# O cache vale so dentro da requisicao (limpo quando outra comeca) e e
# descartado assim que alguem mexe no cadastro -- entao nunca serve uma
# lista velha depois de uma edicao no admin.
_choices_cache = {}


def _clear_choices_cache(**kwargs):
    _choices_cache.clear()


request_started.connect(_clear_choices_cache, dispatch_uid="nationalities-cache")
post_save.connect(_clear_choices_cache, sender=Nationality, dispatch_uid="nat-save")
post_delete.connect(_clear_choices_cache, sender=Nationality, dispatch_uid="nat-delete")


def nationality_choices(language=None):
    """
    As nacionalidades ATIVAS como pares (codigo, nome), no idioma pedido e
    na ordem definida no cadastro. Lista vazia quando nao ha nenhuma
    cadastrada (ou nenhuma ativa) -- e o que o formulario usa para saber
    que o campo precisa ficar indisponivel (`_UnavailableNationalityField`
    em apps.letters.forms), nunca para cair em texto livre.
    """
    if language not in _choices_cache:
        _choices_cache[language] = [
            (item.code, item.display_name(language))
            for item in Nationality.objects.active()
        ]
    return _choices_cache[language]


def _resolve(value, attribute):
    if not value:
        return ""
    item = Nationality.objects.filter(code=value).first()
    if item is None:
        # Nao e um codigo do cadastro: e o texto que a propria carta
        # guardou (cartas anteriores a existencia da lista).
        return str(value)
    return getattr(item, attribute) or item.name_pt or item.code


def document_forms(data):
    """
    As formas que VAO PARA O DOCUMENTO, prontas para congelar no snapshot:
    `{"guest_nationality": "Brésilienne", "host_nationality": "belge"}`.

    Resolvido uma vez, no fechamento. Depois disso a carta nao consulta
    mais o cadastro -- e o que mantem o documento igual ao que foi
    emitido, mesmo que a nacionalidade seja renomeada ou desativada.
    """
    return {
        campo: _resolve((data or {}).get(campo), atributo)
        for campo, atributo in FORM_BY_FIELD.items()
    }


def display_name(value, language=None):
    """O nome da nacionalidade para mostrar na tela, no idioma pedido."""
    return _resolve(value, f"name_{language}") if value else ""
