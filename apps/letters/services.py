"""
Regras de negocio do assistente real de Carta Convite: resolver o modelo
oficial DO IDIOMA escolhido, criar o rascunho do usuario, agrupar os
campos do field_schema por etapa, revalidar o conjunto completo no
fechamento e montar o snapshot da geracao.

Mantem a interpretacao do field_schema fora da view e do template (secao
6 do pedido da Fase 3): a view so chama estas funcoes e passa o resultado
pronto ao contexto; o template so exibe.

Idioma: cada idioma tem o seu LetterTemplate (um documento oficial
proprio, decisao da Fase 2). O idioma da carta e a unica coisa que
escolhe o template — nunca um identificador vindo do cliente — e um
idioma sem versao publicada NAO cai no documento de outro idioma: o
fluxo para e avisa.
"""

import hashlib

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.doctemplates.models import LetterTemplate
from apps.doctemplates.official_templates import official_slug
from apps.doctemplates.schema import OPTION_BASED_TYPES, resolve_label, resolve_options
from apps.letters.forms import build_dynamic_form, deserialize_initial, serialize_cleaned_data
from apps.letters.models import Letter
from apps.letters.nationalities import display_name as nationality_display_name
from apps.letters.nationalities import document_forms
from apps.letters.pdf_generation import render_letter_pdf

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


def normalize_language(language):
    """
    Devolve `language` se for um idioma do site; senao, o idioma padrao.

    Serve so para o ponto de partida (o idioma em que a pessoa esta
    navegando). NAO e um substituto de documento: a escolha do template
    continua sendo estrita pelo idioma resultante.
    """
    if language in valid_language_codes():
        return language
    return settings.LANGUAGE_CODE


def get_template_version_for_language(language):
    """
    A TemplateVersion PUBLICADA do modelo oficial daquele idioma, ou None
    se aquele idioma ainda nao tem documento publicado.

    Nunca devolve o documento de outro idioma como substituto.
    """
    template = LetterTemplate.objects.filter(
        slug=official_slug(language), is_active=True
    ).first()
    if template is None:
        return None
    return template.published_version


def available_languages():
    """Os idiomas que hoje tem um documento oficial publicado."""
    return [
        code
        for code, _label in settings.LANGUAGES
        if get_template_version_for_language(code) is not None
    ]


# ---------------------------------------------------------------------------
# Rascunho
# ---------------------------------------------------------------------------


def start_draft(user, language):
    """
    Cria uma Letter em rascunho para `user`, no modelo oficial publicado
    do idioma pedido (nunca uma versao em rascunho, nunca uma versao
    escolhida pelo cliente — ver secao 15 do pedido).

    None se aquele idioma nao tiver documento publicado.
    """
    template_version = get_template_version_for_language(language)
    if template_version is None:
        return None
    return Letter.objects.create(
        user=user,
        template=template_version.template,
        template_version=template_version,
        language=language,
        status=Letter.Status.DRAFT,
    )


def change_language(letter, language):
    """
    Troca o idioma da carta e, com ele, o documento oficial de destino.

    Os dados preenchidos ficam intactos: os quatro modelos oficiais tem
    exatamente as mesmas chaves de campo. Devolve False (sem gravar nada)
    se o idioma nao existir ou ainda nao tiver documento publicado.
    """
    if language not in valid_language_codes():
        return False

    template_version = get_template_version_for_language(language)
    if template_version is None:
        return False

    letter.language = language
    letter.template_version = template_version
    letter.template = template_version.template
    letter.save(update_fields=["language", "template", "template_version", "updated_at"])
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


# ---------------------------------------------------------------------------
# Campos e formulario por etapa
# ---------------------------------------------------------------------------


def fields_for_section(letter, section):
    """Os campos do field_schema da secao indicada, na ordem definida por `order`."""
    return fields_for_section_in(letter.template_version.field_schema, section)


def fields_for_section_in(schema, section):
    fields = [f for f in (schema or {}).get("fields", []) if f.get("section") == section]
    return sorted(fields, key=lambda f: f.get("order", 0))


def all_fields(letter):
    """Todos os campos do field_schema, na ordem definida por `order`."""
    schema = letter.template_version.field_schema or {}
    return sorted(schema.get("fields", []), key=lambda f: f.get("order", 0))


def form_for_step(letter, step, data=None):
    """
    O forms.Form dinamico da etapa `step` (1 a 4), com os textos no idioma
    da carta. Sem `data` (GET), vem pre-preenchido com o que ja estiver
    salvo em `letter.data`.
    """
    fields = fields_for_section(letter, STEP_SECTIONS[step])
    initial = None if data is not None else deserialize_initial(fields, letter.data)
    return build_dynamic_form(fields, data=data, initial=initial, language=letter.language)


def form_for_new_letter(template_version, language, data=None):
    """
    O formulario da primeira etapa ANTES de a carta existir: a tela de
    "Gerar Carta Convite" (GET) so apresenta; e o POST valido e que cria
    a Letter. Mesmo formulario da etapa 1, sem nenhum efeito no banco.
    """
    fields = fields_for_section_in(template_version.field_schema, STEP_SECTIONS[FIRST_STEP])
    return build_dynamic_form(fields, data=data, language=language)


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
        form = build_dynamic_form(fields, data=letter.data, language=letter.language)
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
    saem no idioma da carta.
    """
    language = letter.language
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

    Do perfil vem tambem o numero do documento de identidade: e um dado
    da pessoa, nao da viagem, entao o anfitriao o informa uma vez e todas
    as cartas o reaproveitam.

    A cidade e congelada SEPARADA do endereco de proposito. O fechamento
    do documento ("Fait à <cidade>, le <data>") usa a cidade de
    residencia de quem emite a carta; guardando-a como dado estruturado,
    reproduzir a carta antiga nunca depende de adivinhar a cidade a
    partir do texto do endereco.
    """
    return {
        "data": dict(letter.data),
        "language": letter.language,
        "template_slug": letter.template.slug,
        "template_version_number": letter.template_version.version_number,
        "host": {
            "full_name": user.full_name,
            "phone": user.phone,
            "address": user.get_address_display(),
            "city": user.city,
            "document_number": user.document_number,
        },
        # As nacionalidades entram ja RESOLVIDAS na forma que o documento
        # usa. `data` guarda o codigo (estavel); aqui fica o texto que foi
        # impresso -- e o que faz uma carta emitida continuar igual mesmo
        # que a nacionalidade seja renomeada ou desativada no cadastro
        # depois.
        "nationalities": document_forms(letter.data),
        "finalized_at": timezone.now().isoformat(),
    }


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
    return missing


def generate_pdf(letter):
    """
    Gera o PDF da carta a partir do seu snapshot congelado e guarda o
    resultado: o arquivo em `Letter.pdf_file`, a impressao digital em
    `Letter.pdf_sha256`, o instante em `Letter.generated_at`, e so entao
    o status passa a GENERATED.

    A fonte dos dados e SEMPRE o snapshot, nunca o perfil atual do
    usuario -- e o que faz uma carta antiga continuar reproduzindo os
    dados que tinha quando foi emitida, mesmo que o perfil tenha mudado
    desde entao.

    Se a geracao falhar (falta um dado, um valor nao cabe na area
    reservada, o PDF base nao pode ser lido), o erro sobe e NADA e
    gravado: a carta nao vira GENERATED com um arquivo errado.
    """
    pdf_bytes = render_letter_pdf(
        template_version=letter.template_version, snapshot=letter.snapshot
    )
    checksum = hashlib.sha256(pdf_bytes).hexdigest()

    letter.pdf_file.save(f"{letter.reference}.pdf", ContentFile(pdf_bytes), save=False)
    letter.pdf_sha256 = checksum
    letter.generated_at = timezone.now()
    letter.status = Letter.Status.GENERATED
    letter.save(
        update_fields=["pdf_file", "pdf_sha256", "generated_at", "status", "updated_at"]
    )
    return letter
