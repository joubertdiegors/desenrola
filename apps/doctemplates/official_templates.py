"""
O field_schema do modelo oficial da Carta Convite, no contrato de
`apps.doctemplates.schema`.

Codigo Python puro (nao um modelo Django) de proposito: e daqui que
`services.biblioteca` semeia `DocumentTemplate.field_schema` dos quatro
oficiais, e uma migration de dados consegue importa-lo sem depender do
app registry estar totalmente carregado.

UM MODELO POR IDIOMA, O MESMO FORMULARIO
----------------------------------------
Cada idioma tem o seu `DocumentTemplate`, mas todos com a MESMA
configuracao de campos -- mesmas `key`, mesmo `type`, mesma ordem. E
isso que permite trocar o idioma da carta no meio do assistente sem
invalidar o que ja foi preenchido: os valores gravados em `Letter.data`
sao os mesmos; so muda o documento de destino.

TEXTOS E TRADUCOES
------------------
O texto de origem (pt) fica na propria definicao do campo (`label`,
`placeholder`, `help_text`); `translations` traz fr/nl/en. A
configuracao tecnica nunca e duplicada por idioma. Desde a Etapa de
correcoes pos-validacao manual o ASSISTENTE mostra sempre o portugues --
as traducoes seguem aqui porque descrevem o campo, nao a interface.

LIMITE DELIBERADO -- nenhum texto que o usuario DECLARA/ACEITA foi
traduzido por nos: as tres caixas de confirmacao (`host_confirm`,
`notice_informal`, `notice_prise_en_charge`) ficam sem `translations` e
caem no texto original fornecido pelo projeto, em portugues. Traduzir
uma declaracao que menciona Espaco Schengen, "Prise en Charge (Annexe
3bis)" e responsabilidade legal seria inventar conteudo juridico.

`full_width` e uma chave extra, fora do contrato documentado em
`schema.py` -- o validador ali ignora chaves desconhecidas, entao isto e
so uma dica de layout para o template (campo ocupa as duas colunas do
`.form-grid`), sem quebrar o contrato nem exigir mudanca em schema.py.
"""

# Idioma em que os textos de origem deste modulo estao escritos: e para
# ele que `resolve_field_text` volta quando um idioma nao tem traducao.
SOURCE_LANGUAGE = "pt"

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
            "type": "nationality",
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
            # O placeholder aqui é um EXEMPLO DE FORMATO, não uma frase:
            # não muda com o idioma, então não tem tradução por idioma --
            # `resolve_field_text` cai neste valor de origem em todos.
            #
            # "YY123456": duas letras e seis dígitos, que é a forma do
            # passaporte belga e da maioria dos europeus. O exemplo
            # anterior ("YY0000") tinha quatro dígitos e sugeria um
            # número mais curto do que o real.
            "placeholder": "YY123456",
            "translations": {
                "fr": {"label": "Numéro de passeport"},
                "nl": {"label": "Paspoortnummer"},
                "en": {"label": "Passport number"},
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
