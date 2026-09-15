"""
Regras de negocio do assistente real de Carta Convite: resolver o modelo
oficial DO IDIOMA escolhido, criar o rascunho do usuario, agrupar os
campos do field_schema por etapa, revalidar o conjunto completo no
fechamento e montar o snapshot da geracao.

Mantem a interpretacao do field_schema fora da view e do template (secao
6 do pedido da Fase 3): a view so chama estas funcoes e passa o resultado
pronto ao contexto; o template so exibe.

Idioma: cada idioma tem o seu `DocumentTemplate` oficial na biblioteca.
O idioma da carta e a unica coisa que escolhe o modelo — nunca um
identificador vindo do cliente — e um idioma sem documento pronto NAO
cai no documento de outro idioma: o fluxo para e avisa.
"""

import datetime
import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.content.models import Asset
from apps.core.middleware import IDIOMA_DA_INTERFACE
from apps.doctemplates.layout_schema import assets_referenciados
from apps.doctemplates.models import DocumentTemplate
from apps.doctemplates.schema import OPTION_BASED_TYPES, resolve_label, resolve_options
from apps.doctemplates.services import pdf as document_pdf
from apps.doctemplates.services import snapshot as document_snapshot
from apps.letters.forms import build_dynamic_form, deserialize_initial, serialize_cleaned_data
from apps.letters.models import (
    IDIOMA_PADRAO_DA_CARTA,
    DefaultDocumentTemplateMissingError,
    DocumentLanguageSettings,
    DocumentSnapshotAssetMissingError,
    DocumentSnapshotImmutableError,
    Letter,
    LetterAsset,
    LetterRenderError,
    MissingDocumentSnapshotError,
)
from apps.letters.nationalities import display_name as nationality_display_name
from apps.letters.nationalities import document_nationalities
from apps.letters.rules import stay_duration_days
from pdfengine.textnorm import normalize_for_document

# Etapas 1-4 tem campos vindos do field_schema, cada uma na sua secao;
# 5 (idioma) grava direto em Letter.language; 6 (revisao) so exibe.
STEP_SECTIONS = {1: "convidado", 2: "viagem", 3: "anfitriao", 4: "avisos"}
FIRST_STEP = 1
LAST_FORM_STEP = 4
LANGUAGE_STEP = 5
REVIEW_STEP = 6
LAST_STEP = 6

# Titulo e etapa de cada secao, para a Etapa 6 (Revisao) montar o link
# "Editar" correto sem o template ter que conhecer essa relacao.
SECTION_META = {
    "convidado": {"title": _("Dados do convidado"), "step": 1},
    "viagem": {"title": _("Período da viagem"), "step": 2},
    "anfitriao": {"title": _("Dados do anfitrião"), "step": 3},
    "avisos": {"title": _("Avisos"), "step": 4},
}


# ---------------------------------------------------------------------------
# Modelo oficial por idioma
# ---------------------------------------------------------------------------


def valid_language_codes():
    return {code for code, _label in settings.LANGUAGES}


# `IDIOMA_PADRAO_DA_CARTA` (importado de `.models`) deixou de ser a
# palavra final na Etapa E: agora e o PADRAO DE FABRICA com que
# `DocumentLanguageSettings` nasce, e a resposta quando nao ha
# configuracao alguma. Quem decide e a tela.
#
# NAO confundir com `settings.LANGUAGE_CODE` (o idioma da INTERFACE, que
# e "pt") nem usar um como padrao do outro -- sao decisoes separadas.


def configuracao_de_idiomas():
    """
    A configuracao vigente dos idiomas do documento (singleton).

    Cria com os padroes na primeira leitura, para uma instalacao nova
    nunca ficar sem resposta -- mesmo padrao de `lifecycle.policy()`. A
    migration `letters.0006` ja semeia a linha, entao na pratica isto e
    um SELECT.
    """
    objeto, _criado = DocumentLanguageSettings.objects.get_or_create(
        pk=DocumentLanguageSettings.SINGLETON_ID
    )
    return objeto


def offered_languages(config=None):
    """
    Os idiomas que o administrador escolheu OFERECER, na ordem oficial.

    Nao pergunta se o documento daquele idioma esta pronto -- essa e a
    outra metade, e mora em `available_languages()`. Aqui e so a
    escolha administrativa.

    NUNCA devolve vazio. `DocumentLanguageSettings.clean()` ja impede
    gravar a lista vazia, mas um banco em estado inesperado (uma linha
    escrita por fora, um `update()` cru) nao pode deixar o produto sem
    poder gerar carta nenhuma: sem nada configurado, vale o padrao de
    fabrica.

    `config` evita reler o singleton quando quem chama ja o tem.
    """
    config = config or configuracao_de_idiomas()
    escolhidos = config.available_document_languages
    if not isinstance(escolhidos, list):
        escolhidos = []
    escolhidos = set(escolhidos)

    oferecidos = [code for code, _label in settings.LANGUAGES if code in escolhidos]
    return oferecidos or [IDIOMA_PADRAO_DA_CARTA]


def idioma_padrao_da_carta(config=None):
    """
    O idioma em que uma carta nova nasce.

    Da configuracao, com uma rede: um padrao que saiu dos oferecidos
    (estado que a tela impede, mas que um `update()` cru produziria) cai
    no primeiro oferecido em vez de criar uma carta num idioma que o
    produto nao oferece mais.
    """
    config = config or configuracao_de_idiomas()
    oferecidos = offered_languages(config)
    padrao = config.default_letter_language
    return padrao if padrao in oferecidos else oferecidos[0]


def available_languages(config=None):
    """
    Os idiomas que a etapa 5 pode oferecer AGORA: os que o administrador
    escolheu oferecer E cujo modelo oficial ja consegue gerar o
    documento.

    Sao duas perguntas diferentes, e as duas precisam ser "sim":

      * OFERECER e decisao administrativa (`offered_languages`);
      * PODER GERAR e estado da biblioteca -- um modelo oficial ausente,
        inativo ou ainda sem desenho nao gera PDF.

    LISTAR nao e USAR: um idioma cujo modelo oficial esteja ausente
    ou inativo sai da lista, em vez de derrubar a pagina inteira por
    causa de um idioma que a pessoa talvez nem fosse escolher. A
    falha continua explicita no momento que importa -- `start_draft`
    e `change_language` levantam se alguem tentar USAR aquele idioma.
    """
    disponiveis = []
    for code in offered_languages(config):
        try:
            modelo = official_document_template(code)
        except DefaultDocumentTemplateMissingError:
            continue
        if modelo is not None:
            disponiveis.append(code)
    return disponiveis


def official_document_template(language):
    """
    O `DocumentTemplate` oficial do idioma pedido, SE ele ja tiver
    conteudo real para desenhar -- `None` se ainda nao tiver.

    E a UNICA resolucao de modelo do assistente: nao ha selecao manual,
    nao ha segundo mecanismo, e o cliente nunca escolhe um id de modelo.

    "Ter conteudo real" e DUAS condicoes, nao uma:

      * o `layout` tem elementos -- ate a Etapa 3.6 so o frances tinha;
      * e todo elemento de imagem aponta para um `Asset` que existe.

    A segunda nao e teorica. O layout nasce da migration com
    `asset_id: 0` (migration nao escreve em MEDIA_ROOT, de proposito) e
    so ganha o binario quando `reconstruir_modelos_oficiais` roda, no
    deploy. Entre uma coisa e outra o modelo tem desenho mas nao tem
    logo: renderizar assim levanta `AssetAusenteError` no meio da
    finalizacao da carta.

    Devolver `None` nos dois casos -- em vez de devolver o modelo mesmo
    assim -- e o que faz o assistente avisar "documento ainda nao
    disponivel" em vez de deixar nascer uma carta que falharia na hora
    de gerar, ou produzir um PDF incompleto marcado como gerado com
    sucesso -- o tipo de erro silencioso que este projeto rejeita em
    toda outra etapa.

    So levanta `DefaultDocumentTemplateMissingError` quando o slug
    oficial (`biblioteca.slug_oficial`) nao existe ou esta inativo -- a
    seed da biblioteca (migration 0010) sempre o cria, entao essa falta
    e sinal de banco fora do estado esperado, nao de "conteudo ainda nao
    pronto".
    """
    from apps.doctemplates.services import biblioteca

    slug = biblioteca.slug_oficial(language)
    modelo = DocumentTemplate.objects.filter(slug=slug).select_related("type").first()
    if modelo is None or not modelo.is_active:
        raise DefaultDocumentTemplateMissingError(
            f'O modelo estrutural oficial "{slug}" não existe ou está inativo; '
            "a biblioteca de modelos não foi semeada corretamente."
        )
    if not (modelo.layout or {}).get("elements"):
        return None
    if not _os_assets_do_layout_existem(modelo.layout):
        return None
    return modelo


def _os_assets_do_layout_existem(layout):
    """
    Todo elemento de imagem do layout aponta para um `Asset` que existe.

    `layout_schema.assets_referenciados()` NAO serve aqui: para ele
    `asset_id: 0` significa "sem asset" e simplesmente nao entra no
    conjunto. Para esta pergunta zero e justamente o caso que interessa
    -- o layout recem-semeado, ainda sem o binario.
    """
    exigidos = set()
    for elemento in (layout or {}).get("elements", []):
        if not isinstance(elemento, dict) or elemento.get("type") != "image":
            continue
        origem = (elemento.get("properties") or {}).get("source") or {}
        exigidos.add(int(origem.get("asset_id") or 0))

    if not exigidos:
        return True
    if 0 in exigidos:
        return False
    return Asset.objects.filter(pk__in=exigidos).count() == len(exigidos)


# ---------------------------------------------------------------------------
# Rascunho
# ---------------------------------------------------------------------------


def start_draft(user, language):
    """
    Cria uma Letter em rascunho para `user`, no modelo oficial do idioma
    pedido -- resolvido pelo slug, nunca escolhido pelo cliente.

    `None` se aquele idioma ainda nao tem documento pronto: e o que faz
    a view avisar em vez de deixar nascer uma carta que nao geraria PDF.

    A resolucao roda ANTES do `create()`: se o modelo oficial faltar ou
    estiver inativo (erro de infraestrutura, nao "conteudo ainda nao
    pronto"), a excecao sobe e NENHUMA carta chega a existir -- nunca
    uma parcialmente criada, presa sem modelo por um bug de semeadura.
    """
    modelo = official_document_template(language)
    if modelo is None:
        return None

    return Letter.objects.create(
        user=user,
        document_template=modelo,
        language=language,
        status=Letter.Status.DRAFT,
    )


def change_language(letter, language):
    """
    Troca o idioma da carta e, com ele, o documento oficial de destino.

    Os dados preenchidos ficam intactos: os quatro modelos oficiais tem
    exatamente as mesmas chaves de campo. Devolve False (sem gravar nada)
    se o idioma nao existir, nao estiver sendo oferecido ou ainda nao
    tiver documento pronto.

    MANTER O QUE JA SE TEM SEMPRE FUNCIONA
    --------------------------------------
    Reenviar o idioma que a carta ja tem e um sucesso sem escrita. E o
    que impede uma carta de ficar presa quando o administrador para de
    oferecer o idioma dela: a pessoa continua podendo seguir para a
    revisao com a carta como esta. Tirar um idioma da oferta vale para
    carta NOVA -- nao desfaz o que ja foi escrito.
    """
    if language == letter.language:
        return True

    if language not in valid_language_codes():
        return False

    if language not in offered_languages():
        return False

    modelo = official_document_template(language)
    if modelo is None:
        return False

    letter.language = language
    letter.document_template = modelo
    letter.save(update_fields=["language", "document_template", "updated_at"])
    return True


def get_owned_draft(user, letter_uuid):
    """
    A Letter em rascunho identificada por `letter_uuid`, apenas se
    pertencer a `user`. None em qualquer outro caso -- carta de outro
    usuario, carta inexistente ou carta ja finalizada -- para a view
    responder sempre com o mesmo 404 genérico, sem revelar qual dos casos
    ocorreu (secao 9, CRÍTICO: nenhuma enumeração de UUID de terceiros).
    """
    return Letter.objects.filter(uuid=letter_uuid, user=user, status=Letter.Status.DRAFT).first()


def get_owned_editable_letter(user, letter_uuid):
    """
    A Letter de `user` que pode ser EDITADA agora: o rascunho, ou uma
    carta ja finalizada enquanto a politica administrativa permitir
    (`lifecycle.is_letter_editable`).

    `None` em qualquer outro caso -- carta de outra pessoa, carta
    inexistente, ou carta finalizada fora do prazo -- para a view
    responder sempre o mesmo, sem revelar qual dos casos ocorreu.

    E o portao do assistente no SERVIDOR: nao adianta esconder o botao
    "Editar" na tela se a URL da etapa continuar abrindo.
    """
    from apps.letters import lifecycle

    letter = Letter.objects.filter(uuid=letter_uuid, user=user).first()
    if letter is None:
        return None
    return letter if lifecycle.is_letter_editable(letter) else None


# ---------------------------------------------------------------------------
# Campos e formulario por etapa
# ---------------------------------------------------------------------------


def fields_for_section(letter, section):
    """Os campos do field_schema da secao indicada, na ordem definida por `order`."""
    return fields_for_section_in(letter.document_template.field_schema, section)


def fields_for_section_in(schema, section):
    fields = [f for f in (schema or {}).get("fields", []) if f.get("section") == section]
    return sorted(fields, key=lambda f: f.get("order", 0))


def all_fields(letter):
    """Todos os campos do field_schema, na ordem definida por `order`."""
    schema = letter.document_template.field_schema or {}
    return sorted(schema.get("fields", []), key=lambda f: f.get("order", 0))


def form_for_step(letter, step, data=None):
    """
    O forms.Form dinamico da etapa `step` (1 a 4), com os textos no idioma
    da INTERFACE (`IDIOMA_DA_INTERFACE`), nunca no idioma da carta. Sem
    `data` (GET), vem pre-preenchido com o que ja estiver salvo em
    `letter.data`.
    """
    fields = fields_for_section(letter, STEP_SECTIONS[step])
    initial = None if data is not None else deserialize_initial(fields, letter.data)
    # IDIOMA_DA_INTERFACE, nao letter.language: o wizard e sempre em
    # portugues, so o DOCUMENTO tem idioma proprio (ver o comentario de
    # IDIOMA_PADRAO_DA_CARTA acima).
    return build_dynamic_form(
        fields, data=data, initial=initial, language=IDIOMA_DA_INTERFACE
    )


def form_for_new_letter(document_template, data=None):
    """
    O formulario da primeira etapa ANTES de a carta existir: a tela de
    "Gerar Carta Convite" (GET) so apresenta; e o POST valido e que cria
    a Letter. Mesmo formulario da etapa 1, sem nenhum efeito no banco.
    """
    fields = fields_for_section_in(document_template.field_schema, STEP_SECTIONS[FIRST_STEP])
    return build_dynamic_form(fields, data=data, language=IDIOMA_DA_INTERFACE)


def save_step_data(letter, step, cleaned_data):
    """Grava so os campos desta etapa em Letter.data, preservando os das demais."""
    fields = fields_for_section(letter, STEP_SECTIONS[step])
    keys = {f["key"] for f in fields}
    updated = dict(letter.data)
    updated.update(serialize_cleaned_data({k: v for k, v in cleaned_data.items() if k in keys}))
    letter.data = updated
    letter.save(update_fields=["data", "updated_at"])


def blocking_step_before(letter, target_step):
    """
    A primeira etapa ANTERIOR a `target_step` que ainda nao esta valida --
    ou None se o caminho ate ali esta todo preenchido.

    E o que permite navegar pelo assistente sem furar a validacao: voltar
    e sempre livre, mas so se avanca ate onde os dados ja sustentam. Como
    a checagem e feita a partir de `letter.data` (e nao de um "ate onde
    ele chegou" guardado), nao ha como contornar pela URL: pedir a etapa 5
    com a 2 invalida devolve 2, tenha a pessoa passado por la antes ou
    nao.

    Revalidar assim tambem e o que sustenta o fechamento na etapa 6: nunca
    confiamos apenas em cada submissao anterior ter sido validada no seu
    momento.
    """
    for step in range(FIRST_STEP, min(target_step, LAST_FORM_STEP + 1)):
        fields = fields_for_section(letter, STEP_SECTIONS[step])
        if not fields:
            continue
        form = build_dynamic_form(fields, data=letter.data, language=IDIOMA_DA_INTERFACE)
        if not form.is_valid():
            return step

    if target_step > LANGUAGE_STEP and letter.language not in valid_language_codes():
        return LANGUAGE_STEP

    return None


def validate_all_steps(letter):
    """
    Revalida o conjunto completo antes de permitir o fechamento. Retorna o
    numero da primeira etapa invalida, ou None se tudo estiver valido.
    """
    return blocking_step_before(letter, LAST_STEP + 1)


def reachable_steps(letter):
    """
    Ate que etapa a pessoa pode ir agora: todas as anteriores (voltar e
    sempre livre) mais a primeira que ainda falta preencher.

    Serve para os indicadores 1-6 saberem quais viram link e quais ficam
    inertes -- a regra de verdade continua sendo a do servidor, esta aqui
    e so para nao oferecer um caminho que seria recusado.
    """
    bloqueio = validate_all_steps(letter)
    limite = LAST_STEP if bloqueio is None else bloqueio
    return set(range(FIRST_STEP, limite + 1))


# ---------------------------------------------------------------------------
# Revisao e fechamento
# ---------------------------------------------------------------------------


def grouped_review(letter):
    """
    Os dados preenchidos, agrupados por secao, com o label e o titulo/link
    de cada secao ja resolvidos -- a Etapa 6 so percorre esta lista, sem
    interpretar o schema nem conhecer a relacao secao->etapa. Os textos
    saem no idioma da INTERFACE (`IDIOMA_DA_INTERFACE`): esta e a tela de
    revisao do assistente, nao o documento -- o valor da nacionalidade,
    por exemplo, e so exibicao aqui, o que vai impresso na carta e
    resolvido a parte, no idioma dela.
    """
    language = IDIOMA_DA_INTERFACE
    sections = {}
    for field_def in all_fields(letter):
        section = field_def.get("section", "")
        value = letter.data.get(field_def["key"])
        if field_def["type"] == "checkbox":
            value = _("Sim") if value else _("Não")
        elif field_def["type"] in OPTION_BASED_TYPES:
            labels = dict(resolve_options(field_def, language))
            value = labels.get(value, value)
        elif field_def["type"] == "nationality":
            # Em Letter.data fica o codigo; na revisao a pessoa tem de ver
            # o nome, no idioma da carta.
            value = nationality_display_name(value, language)
        sections.setdefault(section, []).append(
            {"label": resolve_label(field_def, language), "value": value}
        )

    ordered = []
    for key, meta in SECTION_META.items():
        if key in sections:
            ordered.append(
                {"key": key, "title": meta["title"], "step": meta["step"], "items": sections[key]}
            )
    return ordered


# Metadados de exibicao de cada idioma disponivel (nome/dica/bandeira). Os
# CODIGOS validos continuam vindo so de settings.LANGUAGES — isto e so a
# camada visual de apoio, nunca a fonte de verdade sobre quais idiomas
# existem, nem sobre quais tem documento oficial publicado.
LANGUAGE_META = {
    "pt": {
        "name": "Português",
        "hint": _("Versão completa do documento."),
        "flag": "lang-flag-pt",
    },
    "fr": {
        "name": "Français",
        "hint": _("Idioma mais utilizado para processos na Bélgica."),
        "flag": "lang-flag-fr",
    },
    "nl": {
        "name": "Nederlands",
        "hint": _("Também é idioma oficial na Bélgica e nos Países Baixos."),
        "flag": "lang-flag-nl",
    },
    "en": {
        "name": "English",
        "hint": _("Widely accepted internationally."),
        "flag": "lang-flag-en",
    },
}


def build_snapshot(letter, user):
    """
    Congela tudo que influenciou a geracao no momento do fechamento: os
    dados preenchidos, o idioma, a versao do modelo usada e os dados do
    anfitriao vindos do perfil (nome/telefone/endereco/cidade) -- para a
    carta continuar reproduzivel mesmo que o usuario edite o perfil
    depois.

    Do perfil vem tambem o numero do documento de identidade, a data de
    nascimento e a nacionalidade do anfitriao: sao dados da pessoa, nao
    da viagem, entao ele os informa uma vez e todas as cartas os
    reaproveitam.

    A cidade e congelada SEPARADA do endereco de proposito. O fechamento
    do documento ("Fait à <cidade>, le <data>") usa a cidade de
    residencia de quem emite a carta; guardando-a como dado estruturado,
    reproduzir a carta antiga nunca depende de adivinhar a cidade a
    partir do texto do endereco.
    """
    return {
        "data": dict(letter.data),
        "language": letter.language,
        "document_template_slug": letter.document_template.slug,
        "host": {
            "full_name": user.full_name,
            "phone": user.phone,
            "address": user.get_address_display(),
            "city": user.city,
            "document_number": user.document_number,
            "birth_date": user.birth_date.isoformat() if user.birth_date else "",
        },
        # As nacionalidades entram ja RESOLVIDAS na forma que o documento
        # usa. `data` guarda o codigo do convidado (estavel) e o do
        # anfitriao vem do perfil; aqui fica o texto que foi impresso --
        # e o que faz uma carta emitida continuar igual mesmo que a
        # nacionalidade seja renomeada ou desativada no cadastro depois.
        "nationalities": document_nationalities(
            letter.data,
            host_code=user.nationality and user.nationality.code,
            # O idioma do DOCUMENTO, nao o da interface: e ele que
            # escolhe a traducao da nacionalidade.
            language=letter.language,
        ),
        "finalized_at": timezone.now().isoformat(),
    }


def capture_document_template_snapshot(letter, document_template):
    """
    Congela `document_template` em `letter`: grava `document_template`,
    `document_snapshot` (copia estrutural profunda) e
    `document_snapshot_hash` -- ver `apps.doctemplates.services.snapshot`.

    Congela o MODELO; `build_snapshot()` acima congela os DADOS. As duas
    rodam no mesmo instante da finalizacao, nessa ordem (ver
    `views._finalize()`). O modelo vem do IDIOMA da carta, resolvido em
    `official_document_template()` -- nunca de um id enviado pelo cliente.

    PROTEGIDA CONTRA EDICAO CONCORRENTE DO MODELO
    -----------------------------------------------
    `select_for_update()` trava a linha do `DocumentTemplate` dentro da
    transacao: se um administrador estiver salvando uma alteracao nesse
    exato modelo neste exato instante, uma das duas operacoes espera a
    outra terminar -- nunca ha uma leitura pela metade de um `save()`
    alheio. So LE o modelo travado; nunca o altera nem o salva (por isso
    "o template original não deve ser alterado durante a criação do
    snapshot").

    (Em SQLite -- usado em desenvolvimento e nos testes -- o travamento
    e um no-op sem erro; o efeito pratico so existe em PostgreSQL, o
    banco de producao. Ver `config/settings/prod.py`.)

    IMUTAVEL DEPOIS DE CAPTURADO
    ------------------------------
    Chamar isto numa `letter` que ja tem `document_snapshot_hash`
    preenchido levanta `DocumentSnapshotImmutableError` -- a mesma regra
    que `Letter.save()` ja aplica a qualquer tentativa de reescrever os
    tres campos; aqui so falha mais cedo, antes do trabalho de montar o
    snapshot e travar a linha do modelo.

    TUDO OU NADA
    ------------
    A montagem do snapshot, o calculo do hash e o `save()` acontecem
    dentro da MESMA transacao: se qualquer passo falhar, nada e gravado
    -- nunca sobra um snapshot parcial (hash sem conteudo, ou conteudo
    sem hash).
    """
    if letter.document_snapshot_hash:
        raise DocumentSnapshotImmutableError(
            "Esta carta já capturou um modelo estrutural; o snapshot não pode "
            "ser substituído."
        )

    with transaction.atomic():
        travado = DocumentTemplate.objects.select_for_update().get(pk=document_template.pk)
        estrutura = document_snapshot.build_snapshot(travado)

        # Os assets que o layout congelado precisa tem de EXISTIR agora e
        # continuar existindo depois. Existir: senao a carta nasceria
        # irreproduzivel, e e melhor recusar a finalizacao. Continuar
        # existindo: `LetterAsset` (FK PROTECT) e o que impede a exclusao
        # e, via `Asset.save()`, a troca do arquivo -- ver letters/models.
        necessarios = assets_referenciados(estrutura["layout"])
        existentes = set(Asset.objects.filter(pk__in=necessarios).values_list("pk", flat=True))
        faltando = sorted(necessarios - existentes)
        if faltando:
            raise DocumentSnapshotAssetMissingError(
                "O modelo referencia imagens que não existem mais (asset "
                f"{', '.join(map(str, faltando))}); a carta não pode ser finalizada "
                "com um documento irreproduzível."
            )

        letter.document_template = travado
        letter.document_snapshot = estrutura
        letter.document_snapshot_hash = document_snapshot.compute_hash(estrutura)
        letter.save(
            update_fields=[
                "document_template",
                "document_snapshot",
                "document_snapshot_hash",
                "updated_at",
            ]
        )
        LetterAsset.objects.bulk_create(
            [LetterAsset(letter=letter, asset_id=asset_id) for asset_id in sorted(existentes)]
        )
    return letter


def _data_br(valor):
    """
    Uma data guardada no snapshot (ISO, `date`/`datetime` ou vazia) como
    "DD/MM/AAAA" -- o mesmo formato que o documento oficial usa.

    O valor sai do snapshot em ISO; o documento mostra DD/MM/AAAA.
    """
    if not valor:
        return ""
    if isinstance(valor, datetime.datetime):
        return valor.date().strftime("%d/%m/%Y")
    if isinstance(valor, datetime.date):
        return valor.strftime("%d/%m/%Y")
    texto = str(valor)
    try:
        data = datetime.date.fromisoformat(texto)
    except ValueError:
        data = datetime.datetime.fromisoformat(texto).date()
    return data.strftime("%d/%m/%Y")


def build_document_context(letter):
    """
    O contexto que o renderer generico (Etapa 3.4) consome, montado a
    partir do que a carta JA TEM CONGELADO -- nunca do perfil ATUAL do
    usuario.

    A fonte e `letter.snapshot` (o dict antigo, congelado por
    `build_snapshot()` no MESMO instante da finalizacao, sempre antes de
    `capture_document_template_snapshot()` rodar -- ver
    `views._finalize()`). Reutiliza-lo aqui, em vez de resolver o perfil
    de novo, e o que evita duas fontes de verdade sobre "qual era o
    endereco do anfitriao quando esta carta foi emitida" -- e o que
    `build_snapshot()` ja resolve, uma vez, ficaria fora de sincronia se
    fosse recalculado aqui a partir de `User` ao vivo.

    So os nomes das chaves mudam: de `host.full_name` (como o snapshot
    guarda) para `anfitriao.nome` (o vocabulario do registro de fontes
    de dados, `apps.doctemplates.datasources`).

    `calculado.duracao_dias` e recalculada aqui, nunca lida de um campo
    gravado -- os dados de entrada
    (`estadia.chegada`/`estadia.partida`) ja estao congelados,
    entao recalcular da sempre o mesmo resultado, e nunca fica
    desatualizada se a formula mudar.

    `documento.numero` e `documento.data` nao tem um dado especifico
    proprio na Letter: usam a referencia da carta e a data de finalizacao,
    respectivamente -- os dados EQUIVALENTES mais proximos que ja
    existem, em vez de inventar um conceito novo. O modelo FR nao os usa;
    ficam disponiveis para um documento futuro que precise deles.

    NORMALIZACAO TIPOGRAFICA
    ------------------------
    Todo valor passa por `pdfengine.textnorm.normalize_for_document()`
    antes de sair daqui. Sem isso, o travessao que
    `User.get_address_display()` usa para exibicao ("Rua 25 – 1200
    Cidade") apareceria assim no PDF, em vez do hifen simples que o
    documento oficial usa ("Rue des Exemple 25 - 1200 ..."). Aplicar
    aqui, na camada do documento -- e nao em `get_address_display()`,
    que tem a sua propria convencao de tela --, e o que mantem a
    convencao tipografica do documento num lugar so.
    """
    snapshot = letter.snapshot or {}
    dados = snapshot.get("data") or {}
    host = snapshot.get("host") or {}
    nacionalidades = snapshot.get("nationalities") or {
        chave: dados.get(chave) for chave in ("guest_nationality", "host_nationality")
    }

    chegada = dados.get("stay_arrival")
    partida = dados.get("stay_departure")
    duracao = ""
    if chegada and partida:
        dias = stay_duration_days(
            datetime.date.fromisoformat(str(chegada)), datetime.date.fromisoformat(str(partida))
        )
        duracao = str(dias) if dias is not None else ""

    contexto = {
        "documento.numero": letter.reference,
        "documento.data": _data_br(snapshot.get("finalized_at")),
        "convidado.nome": dados.get("guest_name") or "",
        "convidado.nacionalidade": nacionalidades.get("guest_nationality") or "",
        "convidado.data_nascimento": _data_br(dados.get("guest_birth_date")),
        "convidado.passaporte": dados.get("guest_passport") or "",
        "anfitriao.nome": host.get("full_name") or "",
        "anfitriao.nacionalidade": nacionalidades.get("host_nationality") or "",
        "anfitriao.data_nascimento": _data_br(
            host.get("birth_date") or dados.get("host_birth_date")
        ),
        "anfitriao.documento_identidade": host.get("document_number") or "",
        "anfitriao.endereco": host.get("address") or "",
        "anfitriao.cidade": host.get("city") or "",
        "anfitriao.telefone": host.get("phone") or "",
        "anfitriao.email": letter.user.email or "",
        "estadia.chegada": _data_br(chegada),
        "estadia.partida": _data_br(partida),
        "calculado.duracao_dias": duracao,
        "calculado.data_documento": _data_br(snapshot.get("finalized_at")),
    }
    return {chave: normalize_for_document(valor) for chave, valor in contexto.items()}


def render_letter(letter):
    """
    O PDF de `letter` pelo renderer GENERICO (Etapa 3.4), a partir do seu
    `document_snapshot` -- nunca do `DocumentTemplate` atual.

    Os quatro passos que o renderer generico pede, aqui montados a partir
    do que a carta ja tem congelado:

      1. verificar que ha snapshot estrutural -- senao,
         `MissingDocumentSnapshotError`, que e erro de programacao: o
         snapshot e capturado na finalizacao, antes de qualquer geracao;
      2. montar o contexto com os dados REAIS da carta
         (`build_document_context`);
      3. resolver os assets do layout CONGELADO, pelos ids do proprio
         snapshot (`document_pdf.carregar_assets`) -- protegidos contra
         exclusao/substituicao por `LetterAsset` (Etapa 3.5.1);
      4. chamar `document_pdf.render_layout()` e devolver os bytes.

    NUNCA CONSULTA O DOCUMENTTEMPLATE ATUAL
    -----------------------------------------
    Nem o layout, nem a pagina, nem o idioma vem de `letter.document_
    template` -- vem inteiramente de `letter.document_snapshot`, onde a
    Etapa 3.5.1 os congelou no instante da finalizacao. Alterar o
    `DocumentTemplate` depois -- trocar o layout, mudar de asset, ate
    apaga-lo (se nada mais o protege) -- nao muda uma linha do que sai
    daqui: e esse o ponto central desta etapa.
    """
    estrutura = letter.document_snapshot
    if not estrutura:
        raise MissingDocumentSnapshotError(
            f'A carta "{letter.reference}" não tem snapshot estrutural '
            "(document_snapshot); não há o que o renderer genérico desenhe."
        )

    try:
        contexto = document_pdf.Contexto(build_document_context(letter))
        assets = document_pdf.carregar_assets(estrutura["layout"])
        dados, _relatorio = document_pdf.render_layout(
            estrutura["layout"], estrutura["type"]["page"], contexto, assets=assets,
        )
    except (
        document_pdf.CampoDesconhecidoError,
        document_pdf.ValorAusenteError,
        document_pdf.AssetAusenteError,
        document_pdf.FonteIndisponivelError,
        document_pdf.PaginaInvalidaError,
        ValidationError,
    ) as erro:
        raise LetterRenderError(
            f'Não foi possível gerar o PDF de "{letter.reference}" a partir do '
            f"modelo estrutural: {erro}"
        ) from erro
    return dados


def missing_host_profile_fields(user):
    """
    Os dados de perfil que o documento oficial exige e o perfil ainda
    nao tem -- lista vazia quando esta tudo certo.

    Serve para barrar a finalizacao ANTES de congelar um snapshot
    incompleto: uma carta finalizada sem a cidade ficaria presa, porque o
    snapshot e imutavel e regerar o PDF continuaria falhando. Devolve a
    lista de rotulos que faltam (vazia se estiver tudo certo).
    """
    missing = []
    if not (user.full_name or "").strip():
        missing.append(_("nome completo"))
    if not (user.get_address_display() or "").strip():
        missing.append(_("endereço"))
    if not (user.city or "").strip():
        missing.append(_("cidade"))
    if not (user.document_number or "").strip():
        missing.append(_("número do documento de identidade"))
    if not (user.phone or "").strip():
        missing.append(_("telefone"))
    if not user.birth_date:
        missing.append(_("data de nascimento"))
    if user.nationality_id is None:
        missing.append(_("nacionalidade"))
    return missing


def generate_pdf(letter):
    """
    Gera o PDF da carta a partir do seu snapshot congelado e guarda o
    resultado: o arquivo em `Letter.pdf_file`, a impressao digital em
    `Letter.pdf_sha256`, o instante em `Letter.generated_at`, e so entao
    o status passa a GENERATED.

    SEMPRE O RENDERER ESTRUTURAL, SEMPRE A PARTIR DO SNAPSHOT
    ---------------------------------------------------------
    O PDF sai de `render_letter()`, a partir do modelo estrutural
    congelado na finalizacao -- nunca do `DocumentTemplate` atual. Isto
    vale tanto para a primeira geracao quanto para uma eventual
    REGERACAO: chamar esta funcao de novo, mais tarde, sobre a MESMA
    carta, sempre relê o MESMO `document_snapshot` (imutavel desde a
    Etapa 3.5.1) e produz o MESMO documento -- nunca o layout/pagina que
    o `DocumentTemplate` tiver NAQUELE momento.

    A fonte dos dados e SEMPRE um snapshot congelado, nunca o perfil
    atual do usuario nem o modelo atual -- e o que faz uma carta antiga
    continuar reproduzindo o que tinha quando foi emitida, mesmo que o
    perfil ou o modelo tenham mudado desde entao.

    Se a geracao falhar (falta um dado, um valor nao cabe na area
    reservada, um asset nao pode ser lido), o erro sobe ANTES de
    qualquer `save()`: a carta nao vira GENERATED com um arquivo errado,
    nem fica com o arquivo antigo meio-substituido.
    """
    pdf_bytes = render_letter(letter)
    checksum = hashlib.sha256(pdf_bytes).hexdigest()

    letter.pdf_file.save(f"{letter.reference}.pdf", ContentFile(pdf_bytes), save=False)
    letter.pdf_sha256 = checksum
    letter.generated_at = timezone.now()
    letter.status = Letter.Status.GENERATED
    letter.save(
        update_fields=["pdf_file", "pdf_sha256", "generated_at", "status", "updated_at"]
    )
    return letter
