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

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.doctemplates.models import LetterTemplate
from apps.doctemplates.official_templates import official_slug
from apps.doctemplates.schema import OPTION_BASED_TYPES, resolve_label, resolve_options
from apps.letters.forms import build_dynamic_form, deserialize_initial, serialize_cleaned_data
from apps.letters.models import Letter

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


def validate_all_steps(letter):
    """
    Revalida o conjunto completo (etapas 1-4 a partir de `letter.data`, e
    o idioma escolhido) antes de permitir o fechamento na Etapa 6 -- nao
    confia apenas em cada submissao anterior ter sido validada.

    Retorna o numero da primeira etapa invalida, ou None se tudo estiver
    valido.
    """
    for step in range(FIRST_STEP, LAST_FORM_STEP + 1):
        fields = fields_for_section(letter, STEP_SECTIONS[step])
        if not fields:
            continue
        form = build_dynamic_form(fields, data=letter.data, language=letter.language)
        if not form.is_valid():
            return step

    if letter.language not in valid_language_codes():
        return LANGUAGE_STEP

    return None


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


def build_snapshot(letter, user):
    """
    Congela tudo que influenciou a geracao no momento do fechamento: os
    dados preenchidos, o idioma, a versao do modelo usada e os dados do
    anfitriao vindos do perfil (nome/telefone/endereco) -- para a carta
    continuar reproduzivel mesmo que o usuario edite o perfil depois.
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
        },
        "finalized_at": timezone.now().isoformat(),
    }
