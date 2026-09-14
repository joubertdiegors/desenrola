"""
Ponte entre o cadastro de nacionalidades e a carta.

O que fica guardado em `Letter.data` e o CODIGO da nacionalidade, nunca o
texto. Isso e o que permite renomear "Brésilienne" no cadastro sem
reescrever o passado, e o que faz trocar o idioma da carta nao invalidar
o preenchimento.

UMA NACIONALIDADE E UM NOME EM QUATRO IDIOMAS. Nao ha forma por papel
(convidado/anfitriao) nem por genero: a carta usa o nome do idioma dela,
e o mesmo nome aparece na tela.

O texto so aparece em dois momentos, e cada um tem a mesma fonte:

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

# Os campos de nacionalidade que o documento imprime. Os dois sao
# resolvidos do MESMO jeito -- pela traducao no idioma da carta. Nao ha
# forma por papel nem por genero.
CAMPOS_DO_DOCUMENTO = ("guest_nationality", "host_nationality")


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


def display_name(value, language=None):
    """
    O nome da nacionalidade guardada em `value`, no idioma pedido.

    **E a unica resolucao de nacionalidade do sistema** -- a mesma para a
    tela e para o documento. Nao ha versao "do convidado" nem "do
    anfitriao": a nacionalidade e um nome, e o nome e o mesmo.

    Fallback: idioma pedido -> portugues -> codigo (ver
    `Nationality.display_name`). Codigo que nao esta no cadastro e
    devolvido como esta: e o texto que a propria carta guardou, antes de
    a lista existir.
    """
    if not value:
        return ""
    item = Nationality.objects.filter(code=value).first()
    if item is None:
        return str(value)
    return item.display_name(language)


def document_nationalities(data, host_code=None, language=None):
    """
    As nacionalidades que VAO PARA O DOCUMENTO, prontas para congelar no
    snapshot: `{"guest_nationality": "Brésilienne", "host_nationality":
    "Belge"}`.

    A do convidado sai de `data` (o assistente pergunta); a do anfitriao
    vem de `host_code`, o codigo da nacionalidade do PERFIL -- o
    assistente nao pergunta mais isso. Cartas anteriores a essa mudanca
    guardaram `host_nationality` em `data`, e e dali que sai quando
    `host_code` nao vem.

    `language` e o idioma do DOCUMENTO: e ele que escolhe a traducao.

    Resolvido uma vez, no fechamento. Depois disso a carta nao consulta
    mais o cadastro -- e o que mantem o documento igual ao que foi
    emitido, mesmo que a nacionalidade seja renomeada ou desativada.
    """
    valores = dict(data or {})
    if host_code:
        valores["host_nationality"] = host_code
    return {campo: display_name(valores.get(campo), language) for campo in CAMPOS_DO_DOCUMENTO}
