"""
Ciclo de vida da carta: em que estado ela esta, ate quando pode ser
editada e quando expira.

O UNICO lugar onde essas contas existem. Views, templates, dashboard e
testes perguntam aqui -- nenhuma regra de prazo pode ser recalculada
noutro lugar, senao a tela e o servidor acabam discordando (foi o que
esta etapa veio impedir).

TRES ESTADOS, NENHUMA COLUNA NOVA DE ESTADO
-------------------------------------------
    RASCUNHO   ainda no assistente
    FINALIZADA documento concluido
    EXPIRADA   finalizada e passada do prazo de validade

EXPIRADA e DERIVADA: `agora >= letter_expires_at(carta)`. Nao ha coluna
"expirada" nem tarefa agendada para marca-la -- o estado e calculado no
momento do acesso, que e quando importa. Uma coluna precisaria de um
cron so para ficar correta, e ficaria errada entre duas execucoes.

`Letter.Status` continua sendo o que sempre foi (rascunho/concluida/
gerada/cancelada): diz o que ACONTECEU com a carta. O ciclo de vida aqui
diz o que se PODE FAZER com ela agora. Sao perguntas diferentes.

FUSO HORARIO
------------
Toda comparacao usa `timezone.now()` (UTC, aware) e toda data de negocio
e interpretada no fuso do projeto (`timezone.localdate`/
`get_current_timezone`). Um prazo baseado em DATA (a viagem) vale ate o
FIM daquele dia local: expira a 00:00 do dia seguinte, no fuso do
projeto. Um prazo baseado em QUANTIDADE de horas/dias e um intervalo
exato a partir de um instante gravado.

O LIMITE E EXCLUSIVO
--------------------
Vale enquanto `agora < limite`; no instante exato do limite ja nao vale
mais. Uma regra so, para os dois prazos.
"""

import datetime

from django.utils import timezone

from apps.letters.models import Letter, LetterPolicy

# A permissao que responde por supervisao -- ver cartas de todos, e
# alcancar tambem as expiradas. A mesma que `Letter.objects.visible_to`
# consulta; declarada aqui para nao ficar solta como string nas views.
SUPERVISION_PERM = "letters.view_all_letters"

# Os estados que o produto mostra. Strings curtas, estaveis: entram em
# template e em teste.
RASCUNHO = "rascunho"
FINALIZADA = "finalizada"
EXPIRADA = "expirada"
CANCELADA = "cancelada"


def policy():
    """
    A politica vigente (singleton). Cria com os padroes na primeira
    leitura, para uma instalacao nova nunca ficar sem resposta.

    Os padroes (`NAO_EDITAVEL` + `NUNCA`) sao exatamente o comportamento
    anterior a esta etapa: instalar nao muda nada ate alguem configurar.
    """
    objeto, _criado = LetterPolicy.objects.get_or_create(pk=LetterPolicy.SINGLETON_ID)
    return objeto


def dados_da_carta(letter):
    """
    Os dados que DESCREVEM a carta: o snapshot congelado se ela ja foi
    fechada, senao o que esta preenchido no rascunho.

    Uma carta finalizada e reaberta para edicao volta a ter `data` mais
    novo que o snapshot -- e o snapshot continua sendo a verdade do
    documento EMITIDO. Para prazo de viagem isso nao muda nada: as duas
    fontes tem a mesma chave, e o snapshot e reescrito a cada
    finalizacao.
    """
    if letter.snapshot:
        return letter.snapshot.get("data") or {}
    return letter.data or {}


def travel_date(letter):
    """
    A data da viagem: a CHEGADA (`stay_arrival`).

    Uma so das duas datas, de proposito -- "a data da viagem" precisa
    significar uma coisa so em todas as politicas, e a chegada e o que a
    Carta Convite anuncia. `None` se a carta ainda nao tem a data (um
    rascunho parado na etapa 1) ou se o valor gravado nao for legivel.
    """
    valor = dados_da_carta(letter).get("stay_arrival")
    if isinstance(valor, datetime.date):
        return valor
    if not valor:
        return None
    try:
        return datetime.date.fromisoformat(str(valor))
    except ValueError:
        return None


def _fim_do_dia(dia):
    """
    O instante em que `dia` acaba, no fuso do projeto: a 00:00 do dia
    seguinte.

    Usar o inicio do dia seguinte (e nao 23:59:59) evita a fresta de um
    segundo e faz a comparacao `agora < limite` cobrir o dia inteiro.
    """
    proximo = dia + datetime.timedelta(days=1)
    return timezone.make_aware(
        datetime.datetime.combine(proximo, datetime.time.min),
        timezone.get_current_timezone(),
    )


def _finalizada_em(letter):
    """
    O instante da PRIMEIRA finalizacao -- o marco zero dos prazos.

    Cartas finalizadas antes desta etapa nao tinham a coluna; a migration
    que a criou preencheu o que deu (`generated_at`, senao `updated_at`).
    Se ainda assim vier vazia, nao ha marco: sem marco nao ha prazo, e
    quem chama devolve `None` em vez de inventar um.
    """
    return letter.finalized_at


# ---------------------------------------------------------------------------
# Editabilidade
# ---------------------------------------------------------------------------


def letter_editable_until(letter, *, config=None):
    """
    O instante-limite para editar esta carta FINALIZADA, ou `None`
    quando nao ha um prazo a mostrar.

    `None` significa "nao ha data a exibir", nunca "pode editar": os
    casos sao a carta ainda em rascunho (rascunho edita sempre, sem
    prazo), a politica `NAO_EDITAVEL` (nunca edita) e o dado que falta
    para calcular. Quem DECIDE e `is_letter_editable()`; esta funcao
    serve a tela, para dizer "editável até ...".
    """
    config = config or policy()
    if letter.status == Letter.Status.DRAFT:
        return None

    regra = config.editability
    if regra == LetterPolicy.Editability.NAO_EDITAVEL:
        return None

    if regra == LetterPolicy.Editability.ATE_DATA_VIAGEM:
        viagem = travel_date(letter)
        return _fim_do_dia(viagem) if viagem else None

    if regra == LetterPolicy.Editability.ATE_X_DIAS_APOS_CRIACAO:
        if letter.created_at is None:
            return None
        return letter.created_at + datetime.timedelta(days=config.editability_amount)

    inicio = _finalizada_em(letter)
    if inicio is None:
        return None
    if regra == LetterPolicy.Editability.POR_HORAS:
        return inicio + datetime.timedelta(hours=config.editability_amount)
    if regra == LetterPolicy.Editability.POR_DIAS:
        return inicio + datetime.timedelta(days=config.editability_amount)
    return None


def is_letter_editable(letter, *, now=None, config=None):
    """
    A carta pode ser editada AGORA? A autoridade unica sobre isso.

    Rascunho: sempre. Cancelada: nunca. Finalizada: conforme a politica
    -- e, quando a politica depende de um dado que falta (a data da
    viagem, o instante da finalizacao), a resposta e NAO. Prazo que nao
    se consegue calcular nao vira permissao.
    """
    if letter.status == Letter.Status.DRAFT:
        return True
    if letter.status == Letter.Status.CANCELLED:
        return False

    config = config or policy()
    if config.editability == LetterPolicy.Editability.NAO_EDITAVEL:
        return False

    limite = letter_editable_until(letter, config=config)
    if limite is None:
        return False
    return (now or timezone.now()) < limite


# ---------------------------------------------------------------------------
# Expiracao
# ---------------------------------------------------------------------------


def letter_expires_at(letter, *, config=None):
    """
    O instante em que a carta deixa de valer, ou `None` se ela nao
    expira.

    `None` tambem quando a politica depende da data da viagem e a carta
    ainda nao a tem: sem data nao ha prazo, e o certo e NAO expirar --
    tirar da pessoa o proprio documento por um dado ausente seria o pior
    dos dois erros possiveis.
    """
    config = config or policy()
    regra = config.expiration

    if regra == LetterPolicy.Expiration.NUNCA:
        return None

    if regra == LetterPolicy.Expiration.X_DIAS_APOS_CRIACAO:
        if letter.created_at is None:
            return None
        return letter.created_at + datetime.timedelta(days=config.expiration_amount)

    viagem = travel_date(letter)
    if viagem is None:
        return None

    if regra == LetterPolicy.Expiration.NA_DATA_DA_VIAGEM:
        return _fim_do_dia(viagem)
    if regra == LetterPolicy.Expiration.X_DIAS_ANTES_DA_VIAGEM:
        return _fim_do_dia(viagem - datetime.timedelta(days=config.expiration_amount))
    if regra == LetterPolicy.Expiration.X_DIAS_DEPOIS_DA_VIAGEM:
        return _fim_do_dia(viagem + datetime.timedelta(days=config.expiration_amount))
    return None


def is_letter_expired(letter, *, now=None, config=None):
    """
    A carta ja expirou? So faz sentido para carta FINALIZADA: um
    rascunho nao tem documento a perder a validade, entao nunca expira.
    """
    if letter.status == Letter.Status.DRAFT:
        return False

    limite = letter_expires_at(letter, config=config)
    if limite is None:
        return False
    return (now or timezone.now()) >= limite


# ---------------------------------------------------------------------------
# O estado, e o que ele permite
# ---------------------------------------------------------------------------


def letter_state(letter, *, now=None, config=None):
    """
    O estado do ciclo de vida: RASCUNHO, FINALIZADA, EXPIRADA ou
    CANCELADA.

    CANCELADA nao e um dos tres estados desta etapa -- e um estado que o
    modelo ja tinha e que nada no fluxo atual produz. Fica reconhecido
    aqui para nao ser silenciosamente tratado como "finalizada".
    """
    if letter.status == Letter.Status.DRAFT:
        return RASCUNHO
    if letter.status == Letter.Status.CANCELLED:
        return CANCELADA
    if is_letter_expired(letter, now=now, config=config):
        return EXPIRADA
    return FINALIZADA


def can_download_pdf(letter, *, now=None, config=None):
    """
    O DONO pode abrir/baixar o PDF desta carta agora? Expirada, nao.

    Responde so pelo usuario comum. Para decidir por uma PESSOA
    especifica -- que pode ser quem supervisiona -- use
    `can_user_download_pdf()`.
    """
    if not letter.pdf_file:
        return False
    return not is_letter_expired(letter, now=now, config=config)


def supervisiona(user):
    """
    Esta pessoa ve as cartas de TODOS (`letters.view_all_letters`)?

    Uma funcao, e nao a string espalhada por views e templates: e o
    unico lugar que sabe qual permissao responde por supervisao.
    Superusuario passa, por como `has_perm` funciona.
    """
    return bool(user) and user.is_authenticated and user.has_perm(SUPERVISION_PERM)


def can_user_download_pdf(user, letter, *, now=None, config=None):
    """
    ESTA pessoa pode obter o PDF DESTA carta agora?

    Junta as duas metades num lugar so: a regra de ciclo de vida (a
    carta expirou?) e a autorizacao (quem esta pedindo?). Quem
    supervisiona alcanca tambem a carta expirada -- a expiracao tira
    o documento do usuario comum, nao do registro nem de quem
    responde por ele.

    Nao decide PROPRIEDADE: qual carta a pessoa pode sequer enxergar
    e questao de `Letter.objects.visible_to()`, aplicada antes.
    """
    if not letter.pdf_file:
        return False
    if supervisiona(user):
        return True
    return not is_letter_expired(letter, now=now, config=config)
