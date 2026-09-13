"""
Ponte entre a Letter finalizada (apps.letters) e o motor de PDF
(pdfengine): resolve, a partir do `Letter.snapshot` já congelado, o dict
de campos que o renderer da Carta Convite oficial espera.

So usa o snapshot -- nunca busca de novo um dado mutavel do usuario (o
perfil pode ter mudado desde a finalizacao; o snapshot e a UNICA fonte
para reproduzir a carta como ela foi gerada). Se um dado necessario nao
estiver no snapshot, isto falha explicitamente (MissingSnapshotDataError)
em vez de inventar um valor.

O "local" do fechamento ("Fait à <cidade>, le <data>") e a cidade de
RESIDENCIA de quem emite a carta -- nao e um campo digitado no
formulario. Ele vem de `snapshot["host"]["city"]`, congelado a partir de
`User.city` na finalizacao. Nunca e deduzido do texto do endereco: o
formato do endereco varia demais para isso ser confiavel.

So o idioma frances tem um documento oficial implementado ate agora
(Fase 4, Etapa 1) -- os outros tres nao tem PDF oficial ainda.
"""

import datetime

from apps.doctemplates.official_templates import official_slug
from apps.letters.rules import stay_duration_days
from pdfengine.exceptions import MissingHostCityError, MissingSnapshotDataError
from pdfengine.render import render_invitation_letter_fr

# Qual renderer atende cada idioma. So a Carta Convite francesa tem
# documento oficial ate agora; quando houver outro, entra aqui -- e e o
# unico lugar que precisa mudar.
RENDERERS = {"fr": render_invitation_letter_fr}

SUPPORTED_LANGUAGES = tuple(RENDERERS)


class UnsupportedLanguageError(MissingSnapshotDataError):
    """
    O idioma da carta ainda não tem um documento oficial implementado.

    Herda de MissingSnapshotDataError porque, do ponto de vista de quem
    chama, o efeito é o mesmo: não é possível gerar o PDF agora, e não é
    um erro de programação — é uma limitação de conteúdo/dados a resolver
    fora do código.
    """


class UnsupportedTemplateError(MissingSnapshotDataError):
    """
    O modelo da carta nao e a Carta Convite oficial, o unico documento
    que este motor sabe desenhar.

    Existe para que um modelo futuro (outro tipo de documento) nunca seja
    renderizado com o layout errado: e melhor recusar do que produzir um
    PDF com a aparencia de um documento e os dados de outro.
    """


class MissingSnapshotError(MissingSnapshotDataError):
    """
    A carta nao tem snapshot -- ou nao foi finalizada ainda, ou foi
    gravada sem congelar os dados. Gerar o PDF a partir dos dados ATUAIS
    do usuario nesse caso produziria um documento que nao corresponde ao
    que foi registrado, entao isto interrompe.
    """


def _require(source: dict, key: str, *, context: str):
    value = source.get(key)
    if value in (None, ""):
        raise MissingSnapshotDataError(
            f'O snapshot não tem o dado obrigatório "{key}" ({context}).'
        )
    return value


def _require_city(host: dict) -> str:
    """
    A cidade de residência do anfitrião, usada no fechamento
    ("Fait à <cidade>, le <data>").

    Falha explicitamente se faltar. Não há fallback de propósito: deduzir
    a cidade do texto do endereço seria um palpite, e escrever
    "Fait à , le ..." produziria um documento oficial inválido.
    """
    city = (host.get("city") or "").strip()
    if not city:
        raise MissingHostCityError(
            "O snapshot não tem a cidade de residência do anfitrião "
            '(host.city), usada no fecho "Fait à ...". Preencha a cidade '
            "no perfil antes de finalizar a carta."
        )
    return city


def _format_date(value) -> str:
    """
    Aceita uma data ISO (string; tanto "AAAA-MM-DD", o formato salvo em
    Letter.data, quanto um datetime completo com hora/fuso, o formato de
    `Letter.snapshot["finalized_at"]`) ou já um `date`/`datetime`; sempre
    devolve "DD/MM/AAAA", como no documento oficial.
    """
    if isinstance(value, datetime.datetime):
        date = value.date()
    elif isinstance(value, datetime.date):
        date = value
    else:
        text = str(value)
        try:
            date = datetime.date.fromisoformat(text)
        except ValueError:
            date = datetime.datetime.fromisoformat(text).date()
    return date.strftime("%d/%m/%Y")


def build_pdf_fields(snapshot: dict) -> dict:
    """
    Resolve o `snapshot` congelado de uma Letter finalizada (formato de
    `apps.letters.services.build_snapshot`) para o dict de campos que
    `pdfengine.render.render_invitation_letter_fr` espera.

De onde vem cada coisa: os dados do convidado e da viagem de
    `snapshot["data"]`; os do anfitrião (nome, endereço, telefone,
    cidade) de `snapshot["host"]`; e a data do documento de
    `snapshot["finalized_at"]`, o instante da emissão. Nada é lido do
    perfil atual do usuário.

    O `place` do documento é a cidade de residência do anfitrião,
    congelada em `snapshot["host"]["city"]`. Se ela não estiver lá, isto
    levanta `MissingHostCityError` — nunca deduz a cidade do endereço
    nem usa um valor genérico.
    """
    data = snapshot.get("data") or {}
    host = snapshot.get("host") or {}

    arrival_iso = _require(data, "stay_arrival", context="etapa Viagem")
    departure_iso = _require(data, "stay_departure", context="etapa Viagem")
    # Sempre recalculada, nunca lida de um campo guardado -- assim nao
    # fica desatualizada se o dado de origem mudar. A conta vem de
    # `rules`, a mesma que o assistente mostra na etapa da viagem: a tela
    # e o documento nunca dizem numeros diferentes.
    duration_days = stay_duration_days(
        datetime.date.fromisoformat(arrival_iso),
        datetime.date.fromisoformat(departure_iso),
    )
    if duration_days is None:
        raise MissingSnapshotDataError(
            "As datas da viagem no snapshot são inválidas: a partida "
            "é anterior à chegada."
        )

    # As nacionalidades vêm do snapshot já na forma impressa no documento
    # (congeladas no fechamento). Cartas anteriores ao cadastro de
    # nacionalidades não têm esta chave: aí valem os valores de `data`,
    # que naquela época já eram o próprio texto.
    nationalities = snapshot.get("nationalities") or {
        chave: data.get(chave) for chave in ("guest_nationality", "host_nationality")
    }
    host_nationality = _require(
        nationalities, "host_nationality", context="etapa Anfitrião"
    )

    host_name = _require(host, "full_name", context="dados do anfitrião")
    document_date_raw = _require(snapshot, "finalized_at", context="data de finalização")

    return {
        "host_name": host_name,
        # A data de nascimento do anfitriao vem do PERFIL congelado. Em
        # cartas anteriores a essa mudanca ela ficava em `data`, porque o
        # assistente ainda perguntava -- por isso as duas origens.
        "host_birth": _format_date(
            host.get("birth_date") or _require(
                data, "host_birth_date", context="data de nascimento no perfil"
            )
        ),
        "host_nationality": host_nationality,
        # O "belge" de "titulaire de la carte d'identité belge n° ..." é a
        # MESMA nacionalidade do anfitrião, na forma que o documento usa --
        # não um segundo dado. Antes havia um campo separado no
        # assistente (`host_document_label`), com rótulo de "tipo de
        # documento", que na verdade recebia a nacionalidade. O tipo é
        # fixo e já está no texto impresso do documento.
        "host_document_type": host_nationality,
        "host_document": _require(
            host, "document_number", context="documento de identidade no perfil"
        ),
        "host_address": _require(host, "address", context="dados do anfitrião"),
        "host_phone": _require(host, "phone", context="dados do anfitrião"),
        "guest_name": _require(data, "guest_name", context="etapa Convidado"),
        "guest_nationality": _require(
            nationalities, "guest_nationality", context="etapa Convidado"
        ),
        "guest_birth": _format_date(_require(data, "guest_birth_date", context="etapa Convidado")),
        "guest_passport": _require(data, "guest_passport", context="etapa Convidado"),
        "arrival_date": _format_date(arrival_iso),
        "departure_date": _format_date(departure_iso),
        "duration_days": str(duration_days),
        "place": _require_city(host),
        "document_date": _format_date(document_date_raw),
        "signature_name": host_name,
    }


def render_letter_pdf(*, template_version, snapshot: dict) -> bytes:
    """
    Gera o PDF de uma carta a partir da `template_version` usada e do seu
    `snapshot` congelado -- não recebe nem consulta `request`, usuário
    autenticado ou sessão.

    Despacha pelo idioma do documento oficial (`template_version.template
    .language`), não pelo idioma da interface nem por nada vindo do
    cliente. Só o francês está implementado; qualquer outro idioma
    levanta `UnsupportedLanguageError`.

    Erros explícitos possíveis, todos subclasses de `PdfEngineError` --
    nenhum produz um PDF incorreto silenciosamente:

      * `MissingSnapshotError` — a carta não tem snapshot;
      * `UnsupportedTemplateError` — o modelo não é a Carta Convite oficial;
      * `UnsupportedLanguageError` — idioma sem documento oficial;
      * `MissingHostCityError` — falta a cidade do anfitrião;
      * `MissingSnapshotDataError` — falta outro campo obrigatório;
      * `TextOverflowError` — algum valor não cabe na área reservada;
      * `BasePdfUnavailableError` — o PDF oficial de base não pôde ser lido.
    """
    if not snapshot:
        raise MissingSnapshotError(
            "A carta não tem snapshot congelado: não é possível gerar o PDF "
            "sem os dados que foram registrados na finalização."
        )

    template = template_version.template
    language = template.language

    if template.slug != official_slug(language):
        raise UnsupportedTemplateError(
            f'O modelo "{template.slug}" não é a Carta Convite oficial de '
            f'"{language}" ({official_slug(language)}): não há um layout '
            "implementado para ele."
        )

    renderer = RENDERERS.get(language)
    if renderer is None:
        raise UnsupportedLanguageError(
            f'Ainda não há um documento oficial implementado para o idioma "{language}".'
        )

    return renderer(build_pdf_fields(snapshot))
