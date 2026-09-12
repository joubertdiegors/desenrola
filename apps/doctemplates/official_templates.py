"""
Dados dos modelos oficiais da Carta Convite (curta duração), seguindo o
contrato de `apps.doctemplates.schema`.

Este modulo e codigo Python puro (nao um modelo Django) de proposito: as
migracoes de dados que semeiam os LetterTemplate/TemplateVersion oficiais
importam apenas isto, sem depender do app registry do Django ainda estar
totalmente carregado.

UM TEMPLATE POR IDIOMA
----------------------
Como decidido na Fase 2, cada idioma e um documento oficial proprio (nao
uma traducao de strings): ha um LetterTemplate por idioma de
settings.LANGUAGES, todos com a MESMA configuracao de campos — mesmas
`key`, mesmo `type`, mesma ordem. E isso que permite trocar o idioma da
carta no meio do assistente sem invalidar o que ja foi preenchido: os
valores gravados em `Letter.data` sao os mesmos; so muda o documento
oficial de destino e o idioma dos rotulos.

TEXTOS E TRADUCOES
------------------
O texto de origem (pt) fica na propria definicao do campo (`label`,
`placeholder`, `help_text`); `translations` traz fr/nl/en. A configuracao
tecnica nunca e duplicada por idioma.

LIMITE DELIBERADO — nenhum texto que o usuario DECLARA/ACEITA foi
traduzido por nos: as tres caixas de confirmacao (`host_confirm`,
`notice_informal`, `notice_prise_en_charge`) ficam sem `translations` e
caem no texto original fornecido pelo projeto, em portugues, em qualquer
idioma. Traduzir uma declaracao que menciona Espaco Schengen, "Prise en
Charge (Annexe 3bis)" e responsabilidade legal seria inventar conteudo
juridico — isso tem que vir do cliente, em texto oficial, e entra depois
como uma nova versao do template (sem alterar as ja publicadas).

`full_width` e uma chave extra, fora do contrato documentado em
`schema.py` — o validador ali ignora chaves desconhecidas, entao isto e
so uma dica de layout para o template (campo ocupa as duas colunas do
`.form-grid`), sem quebrar o contrato nem exigir mudanca em schema.py.
"""

CARTA_CONVITE_SLUG_PREFIX = "carta-convite-curta-duracao"
CARTA_CONVITE_NAME = "Carta Convite — curta duração"
CARTA_CONVITE_DESCRIPTION = (
    "Modelo oficial da Carta Convite para estadias de curta duração "
    "(até 90 dias), usado pelo assistente de geração."
)

# Idioma em que os textos de origem deste modulo estao escritos: e para
# ele que `resolve_field_text` volta quando um idioma nao tem traducao.
SOURCE_LANGUAGE = "pt"

# --- Compatibilidade com a migracao 0002 ----------------------------------
# 0002 semeou um unico template com este slug (sem sufixo de idioma) e o
# importa por estes nomes. A migracao 0003 renomeia esse registro para
# "<prefixo>-fr" e cria os demais idiomas; estas constantes existem so
# para que 0002 continue rodando sem ser alterada.
CARTA_CONVITE_SLUG = CARTA_CONVITE_SLUG_PREFIX
CARTA_CONVITE_LANGUAGE = "fr"


def official_slug(language):
    """O identificador do modelo oficial daquele idioma."""
    return f"{CARTA_CONVITE_SLUG_PREFIX}-{language}"


NOTICE_INFORMAL = (
    "Declaro estar ciente de que a Carta Convite é um documento de caráter "
    "informal e, por si só, não possui força jurídica, não garante a "
    "concessão de visto nem a entrada ou permanência no Espaço Schengen. "
    "Estou ciente de que emitir uma Carta Convite envolve responsabilidade "
    "e que as informações nela declaradas devem ser verdadeiras, completas "
    "e corresponder à realidade da visita e da hospedagem."
)

NOTICE_PRISE_EN_CHARGE = (
    "Declaro estar ciente de que a Carta Convite não deve ser confundida "
    "com a “Prise en Charge” (Annexe 3bis). A Carta Convite serve para "
    "formalizar uma intenção de convite e/ou hospedagem, enquanto a Prise "
    "en Charge é um compromisso formal de responsabilidade financeira "
    "sujeito às condições e formalidades previstas pela legislação belga."
)

HOST_CONFIRM = "Confirmo que estes são os meus dados e que sou eu quem convida e hospeda."

CARTA_CONVITE_FIELD_SCHEMA = {
    "fields": [
        # --- Etapa 1 · Convidado -------------------------------------------
        {
            "key": "guest_name",
            "type": "text",
            "required": True,
            "order": 1,
            "section": "convidado",
            "full_width": True,
            "label": "Nome completo do convidado",
            "placeholder": "Nome completo",
            "help_text": "Digite exatamente como aparece no passaporte.",
            "translations": {
                "fr": {
                    "label": "Nom complet de l'invité",
                    "placeholder": "Nom complet",
                    "help_text": "Saisissez exactement comme indiqué sur le passeport.",
                },
                "nl": {
                    "label": "Volledige naam van de genodigde",
                    "placeholder": "Volledige naam",
                    "help_text": "Neem exact over zoals vermeld in het paspoort.",
                },
                "en": {
                    "label": "Guest's full name",
                    "placeholder": "Full name",
                    "help_text": "Enter exactly as it appears in the passport.",
                },
            },
        },
        {
            "key": "guest_nationality",
            "type": "text",
            "required": True,
            "order": 2,
            "section": "convidado",
            "label": "Nacionalidade",
            "placeholder": "Nacionalidade do convidado",
            "translations": {
                "fr": {"label": "Nationalité", "placeholder": "Nationalité de l'invité"},
                "nl": {"label": "Nationaliteit", "placeholder": "Nationaliteit van de genodigde"},
                "en": {"label": "Nationality", "placeholder": "Guest's nationality"},
            },
        },
        {
            "key": "guest_birth_date",
            "type": "date",
            "required": True,
            "order": 3,
            "section": "convidado",
            "label": "Data de nascimento",
            "translations": {
                "fr": {"label": "Date de naissance"},
                "nl": {"label": "Geboortedatum"},
                "en": {"label": "Date of birth"},
            },
        },
        {
            "key": "guest_passport",
            "type": "text",
            "required": True,
            "order": 4,
            "section": "convidado",
            "full_width": True,
            "label": "Número do passaporte",
            "placeholder": "Número do passaporte",
            "translations": {
                "fr": {
                    "label": "Numéro de passeport",
                    "placeholder": "Numéro de passeport",
                },
                "nl": {"label": "Paspoortnummer", "placeholder": "Paspoortnummer"},
                "en": {"label": "Passport number", "placeholder": "Passport number"},
            },
        },
        # --- Etapa 2 · Viagem ----------------------------------------------
        {
            "key": "stay_arrival",
            "type": "date",
            "required": True,
            "order": 5,
            "section": "viagem",
            "label": "Data de chegada",
            "translations": {
                "fr": {"label": "Date d'arrivée"},
                "nl": {"label": "Aankomstdatum"},
                "en": {"label": "Arrival date"},
            },
        },
        {
            "key": "stay_departure",
            "type": "date",
            "required": True,
            "order": 6,
            "section": "viagem",
            "label": "Data de partida",
            "translations": {
                "fr": {"label": "Date de départ"},
                "nl": {"label": "Vertrekdatum"},
                "en": {"label": "Departure date"},
            },
        },
        # --- Etapa 3 · Anfitrião -------------------------------------------
        # Nome, telefone e endereço vêm do usuário autenticado (não
        # duplicados aqui); estes complementam o que o modelo de usuário
        # não guarda.
        {
            "key": "host_nationality",
            "type": "text",
            "required": True,
            "order": 7,
            "section": "anfitriao",
            "label": "Nacionalidade",
            "translations": {
                "fr": {"label": "Nationalité"},
                "nl": {"label": "Nationaliteit"},
                "en": {"label": "Nationality"},
            },
        },
        {
            "key": "host_birth_date",
            "type": "date",
            "required": True,
            "order": 8,
            "section": "anfitriao",
            "label": "Data de nascimento",
            "translations": {
                "fr": {"label": "Date de naissance"},
                "nl": {"label": "Geboortedatum"},
                "en": {"label": "Date of birth"},
            },
        },
        {
            "key": "host_document_label",
            "type": "text",
            "required": True,
            "order": 9,
            "section": "anfitriao",
            "label": "Documento de identidade",
            "placeholder": "Ex.: Carte d'identité",
            "translations": {
                "fr": {
                    "label": "Document d'identité",
                    "placeholder": "Ex. : carte d'identité",
                },
                "nl": {
                    "label": "Identiteitsdocument",
                    "placeholder": "Bijv.: identiteitskaart",
                },
                "en": {"label": "Identity document", "placeholder": "E.g.: identity card"},
            },
        },
        {
            "key": "host_document_number",
            "type": "text",
            "required": True,
            "order": 10,
            "section": "anfitriao",
            "label": "Número do documento",
            "translations": {
                "fr": {"label": "Numéro du document"},
                "nl": {"label": "Documentnummer"},
                "en": {"label": "Document number"},
            },
        },
        # Declaração do usuário: sem `translations` de propósito (ver o
        # cabeçalho deste módulo).
        {
            "key": "host_confirm",
            "type": "checkbox",
            "required": True,
            "order": 11,
            "section": "anfitriao",
            "full_width": True,
            "label": HOST_CONFIRM,
        },
        # --- Etapa 4 · Avisos ----------------------------------------------
        # Texto jurídico fornecido pelo projeto, em português. Sem
        # `translations` até o cliente fornecer as versões oficiais.
        {
            "key": "notice_informal",
            "type": "checkbox",
            "required": True,
            "order": 12,
            "section": "avisos",
            "full_width": True,
            "label": NOTICE_INFORMAL,
        },
        {
            "key": "notice_prise_en_charge",
            "type": "checkbox",
            "required": True,
            "order": 13,
            "section": "avisos",
            "full_width": True,
            "label": NOTICE_PRISE_EN_CHARGE,
        },
    ]
}
