"""
Dados ficticios da fase de apresentacao visual.

Alimentam as telas enquanto o modelo de carta e a geracao de PDF nao
existem (apps.letters ainda nao tem modelo proprio). Nomes, datas e
numeros vem dos layouts de referencia (desenrola-v2-2-desktop.html,
desenrola-v2-3-tablet.html e desenrola-v2-4-mobile.html). Este modulo
sera removido conforme cada parte ganhar uma implementacao real.
"""

from django.utils.translation import gettext_lazy as _

# ---------------------------------------------------------------------------
# Landing
# ---------------------------------------------------------------------------

LANDING_STAT = "12.458"

PARTNERS = [
    {
        "slot": "pt1",
        "name": "JD-Print",
        "description": _("Impressões 3D sob medida para suas ideias."),
    },
    {
        "slot": "pt2",
        "name": "Confiar Viagens",
        "description": _("Sua próxima viagem começa aqui."),
    },
    {
        "slot": "pt3",
        "name": _("Nome do parceiro"),
        "description": _("Descrição curta do serviço, em uma linha."),
    },
    {
        "slot": "pt4",
        "name": _("Nome do parceiro"),
        "description": _("Descrição curta do serviço, em uma linha."),
    },
]


# ---------------------------------------------------------------------------
# Gerar Carta Convite: assistente de 6 etapas
# ---------------------------------------------------------------------------

# Dados do anfitriao que o modelo de usuario ainda nao guarda (nacionalidade,
# nascimento, documento). Nome, telefone e endereco vem do usuario real.
HOST_EXTRA = {
    "nationality": _("Brasileira"),
    "birth_date": "03/06/1988",
    "document_label": _("Carte d'identité"),
    "document_number": "592-0000000-00",
}

# Passo 6 (revisao) e a conclusao mostram um exemplo ja preenchido, no
# mesmo padrao do arquivo de referencia — as etapas 1 e 2 comecam vazias
# (o usuario ainda vai preencher; nao ha estado salvo entre passos nesta
# fase, pois o modelo Letter ainda nao existe).
GUEST_EXAMPLE = {
    "name": "Maria Santos da Silva",
    "nationality": _("Brasileira"),
    "birth_date": "15/08/1990",
    "passport": "FA123456",
}

STAY_EXAMPLE = {
    "arrival": "10/04/2025",
    "departure": "25/04/2025",
    "duration_days": 15,
}

LANGUAGE_OPTIONS = [
    {
        "code": "fr",
        "name": "Français",
        "hint": _("Idioma mais utilizado para processos na Bélgica."),
        "flag": "lang-flag-fr",
    },
    {
        "code": "en",
        "name": "English",
        "hint": _("Widely accepted internationally."),
        "flag": "lang-flag-en",
    },
    {
        "code": "pt",
        "name": "Português",
        "hint": _("Versão completa do documento."),
        "flag": "lang-flag-pt",
    },
]
DEFAULT_LANGUAGE = "pt"

LEGAL_NOTICES = [
    _(
        "Declaro estar ciente de que a Carta Convite é um documento de caráter "
        "informal e, por si só, não possui força jurídica, não garante a "
        "concessão de visto nem a entrada ou permanência no Espaço Schengen. "
        "Estou ciente de que emitir uma Carta Convite envolve responsabilidade "
        "e que as informações nela declaradas devem ser verdadeiras, completas "
        "e corresponder à realidade da visita e da hospedagem."
    ),
    _(
        "Declaro estar ciente de que a Carta Convite não deve ser confundida "
        "com a “Prise en Charge” (Annexe 3bis). A Carta Convite serve para "
        "formalizar uma intenção de convite e/ou hospedagem, enquanto a Prise "
        "en Charge é um compromisso formal de responsabilidade financeira "
        "sujeito às condições e formalidades previstas pela legislação belga."
    ),
]

# Kicker, titulo e texto de apoio de cada uma das 6 etapas (usados no
# cabecalho do celular; o desktop repete titulo e texto acima do cartao).
FORM_STEPS = {
    1: {
        "label": _("Convidado"),
        "title": _("1. Dados do convidado"),
        "hint": _("Preencha as informações da pessoa que será convidada."),
    },
    2: {
        "label": _("Viagem"),
        "title": _("2. Período da viagem"),
        "hint": _("Informe as datas da viagem."),
    },
    3: {
        "label": _("Anfitrião"),
        "title": _("3. Dados do anfitrião"),
        "hint": _(
            "Confirme os seus dados. A carta é sempre emitida em nome do "
            "titular da conta."
        ),
    },
    4: {
        "label": _("Avisos"),
        "title": _("4. Avisos importantes"),
        "hint": _("Leia atentamente as informações abaixo."),
    },
    5: {
        "label": _("Idioma"),
        "title": _("5. Escolha o idioma da Carta Convite"),
        "hint": _("Selecione o idioma em que o documento será gerado."),
    },
    6: {
        "label": _("Revisão"),
        "title": _("6. Revise seu documento"),
        "hint": _(
            "Confira atentamente todas as informações antes de gerar sua "
            "Carta Convite."
        ),
    },
}
LAST_STEP = 6


# ---------------------------------------------------------------------------
# Cartas (dashboard e backoffice)
# ---------------------------------------------------------------------------

ALL_LETTERS = [
    {
        "id": 1,
        "date": "01/03/2025",
        "host": "Claire Dubois",
        "guest": "Maria Santos da Silva",
        "language": _("Português"),
        "status": "generated",
        "status_label": _("Gerada"),
        "generated_at": "01/03/2025 · 10:24",
        "filename": "Carta-Convite-Maria-Santos.pdf",
    },
    {
        "id": 2,
        "date": "21/08/2026",
        "host": "Claire Dubois",
        "guest": "João Pedro Alves",
        "language": "Français",
        "status": "generated",
        "status_label": _("Gerada"),
        "generated_at": "21/08/2026 · 10:05",
        "filename": "Carta-Convite-Joao-Pedro.pdf",
    },
    {
        "id": 3,
        "date": "02/07/2026",
        "host": "Claire Dubois",
        "guest": "Ana Beatriz Rocha",
        "language": "English",
        "status": "draft",
        "status_label": _("Rascunho · etapa 4"),
        "generated_at": "",
        "filename": "Carta-Convite-Ana-Beatriz.pdf",
    },
    {
        "id": 4,
        "date": "12/08/2026",
        "host": "Rafael Costa",
        "guest": "Beatriz Costa",
        "language": "Français",
        "status": "generated",
        "status_label": _("Gerada"),
        "generated_at": "12/08/2026 · 18:20",
        "filename": "Carta-Convite-Beatriz-Costa.pdf",
    },
    {
        "id": 5,
        "date": "30/07/2026",
        "host": "Sofia Nkemelu",
        "guest": "Amara Nkemelu",
        "language": _("Português"),
        "status": "generated",
        "generated_at": "30/07/2026 · 09:41",
        "status_label": _("Gerada"),
        "filename": "Carta-Convite-Amara-Nkemelu.pdf",
    },
]

# Cartas mostradas no dashboard: um recorte ilustrativo, igual para
# qualquer usuario ate o modelo Letter existir de verdade.
LETTERS = ALL_LETTERS[:3]


def get_letter(pk):
    """Devolve a carta ficticia com esse id ou None."""
    for letter in ALL_LETTERS:
        if letter["id"] == pk:
            return letter
    return None


# ---------------------------------------------------------------------------
# Area administrativa
# ---------------------------------------------------------------------------

ADMIN = {"name": "Ana Martins", "initials": "AM", "role": _("Administradora")}

ADMIN_USERS = [
    {
        "name": "Ana Martins",
        "initials": "AM",
        "email": "ana@desenrola.be",
        "role": "admin",
        "role_label": _("Administrador"),
        "letters": None,
        "last_access": _("Hoje"),
        "mobile_note": _("Hoje"),
        "active": True,
    },
    {
        "name": "Pedro Lima",
        "initials": "PL",
        "email": "pedro@desenrola.be",
        "role": "manager",
        "role_label": _("Gerente"),
        "letters": None,
        "last_access": _("Ontem"),
        "mobile_note": _("Ontem"),
        "active": True,
    },
    {
        "name": "Sofia Nkemelu",
        "initials": "SN",
        "email": "sofia@desenrola.be",
        "role": "operator",
        "role_label": _("Operador"),
        "letters": None,
        "last_access": _("Seg"),
        "mobile_note": _("Seg"),
        "active": True,
    },
    {
        "name": "Ricardo Costa",
        "initials": "RC",
        "email": "ricardo.costa@exemplo.be",
        "role": "user",
        "role_label": _("Usuário"),
        "letters": 3,
        "last_access": _("Hoje"),
        "mobile_note": _("3 cartas"),
        "active": True,
    },
    {
        "name": "Luísa Ferreira",
        "initials": "LF",
        "email": "luisa.f@exemplo.com",
        "role": "user",
        "role_label": _("Usuário"),
        "letters": 0,
        "last_access": "03/05/2026",
        "mobile_note": _("Inativa"),
        "active": False,
    },
]

# (administrador, gerente, operador, usuario)
PERMISSIONS = [
    {"label": _("Gerar cartas próprias"), "levels": (True, True, True, True)},
    {"label": _("Visualizar cartas de todos"), "levels": (True, True, True, False)},
    {"label": _("Ativar / desativar usuários"), "levels": (True, True, False, False)},
    {"label": _("Editar conteúdo, parceiros e idiomas"), "levels": (True, True, False, False)},
    {"label": _("Aparência, permissões e sistema"), "levels": (True, False, False, False)},
]

STATS = [
    {"label": _("Usuários"), "value": "1.284", "note": _("+38 esta semana"), "tone": "success"},
    {"label": _("Cartas geradas"), "value": LANDING_STAT, "note": _("214 este mês"), "tone": ""},
    {"label": _("Parceiros ativos"), "value": "4", "note": _("2 aguardando imagem"), "tone": ""},
    {"label": _("Idiomas"), "value": "4", "note": _("NL · 3 textos pendentes"), "tone": "warning"},
]

STATS_MOBILE = [
    {"label": _("Usuários"), "value": "1.284"},
    {"label": _("Cartas · mês"), "value": "214"},
]

LANGUAGES = [
    {
        "name": "Português",
        "interface": "100%",
        "interface_tone": "success",
        "letter": "—",
        "letter_tone": "muted",
        "default": True,
    },
    {
        "name": "Français",
        "interface": "100%",
        "interface_tone": "success",
        "letter": _("Oficial"),
        "letter_tone": "success",
        "default": False,
    },
    {
        "name": "Nederlands",
        "interface": _("97% · 3 pendentes"),
        "interface_tone": "warning",
        "letter": _("Oficial"),
        "letter_tone": "success",
        "default": False,
    },
    {
        "name": "English",
        "interface": "100%",
        "interface_tone": "success",
        "letter": _("Tradução livre"),
        "letter_tone": "muted",
        "default": False,
    },
]

# Cores prontas para a Aparencia do backoffice. "cls" e a classe aplicada
# no <html> (static/css/base.css); "swatch" e a classe puramente visual do
# botao (mesma cor, sem depender de estilo inline).
THEME_PRIMARY_SWATCHES = [
    {"cls": "", "swatch": "swatch-azul", "name": _("Azul")},
    {"cls": "t-roxo", "swatch": "swatch-roxo", "name": _("Roxo")},
    {"cls": "t-verde", "swatch": "swatch-verde", "name": _("Verde")},
    {"cls": "t-laranja", "swatch": "swatch-laranja", "name": _("Laranja")},
    {"cls": "t-grafite", "swatch": "swatch-grafite", "name": _("Grafite")},
]
THEME_SUCCESS_SWATCHES = [
    {"cls": "", "swatch": "swatch-s-verde", "name": _("Verde")},
    {"cls": "s-teal", "swatch": "swatch-s-teal", "name": _("Teal")},
    {"cls": "s-azul", "swatch": "swatch-s-azul", "name": _("Azul")},
    {"cls": "s-ambar", "swatch": "swatch-s-ambar", "name": _("Âmbar")},
]

# Parceiros administrados (mesmos 4 da landing, com estado de publicacao)
ADMIN_PARTNERS = [
    {
        "name": "JD-Print",
        "description": _("Impressões 3D sob medida para suas ideias."),
        "status": "published",
    },
    {
        "name": "Confiar Viagens",
        "description": _("Sua próxima viagem começa aqui."),
        "status": "published",
    },
    {
        "name": _("Nome do parceiro"),
        "description": _("Descrição curta do serviço."),
        "status": "pending_image",
    },
    {
        "name": _("Nome do parceiro"),
        "description": _("Descrição curta do serviço."),
        "status": "pending_image",
    },
]

# Titulo e acao da barra do celular por secao do admin
BACKOFFICE_SECTIONS = {
    "overview": {"title": _("Visão geral"), "icon": "ph-plus", "action": _("Convidar usuário")},
    "users": {"title": _("Usuários"), "icon": "ph-plus", "action": _("Convidar usuário")},
    "permissions": {"title": _("Permissões"), "icon": "ph-plus", "action": _("Convidar usuário")},
    "letters": {"title": _("Cartas"), "icon": "ph-magnifying-glass", "action": _("Buscar")},
    "templates": {"title": _("Modelos"), "icon": "ph-upload-simple", "action": _("Novo modelo")},
    "content": {"title": _("Conteúdo"), "icon": "ph-upload-simple", "action": _("Novo modelo")},
    "partners": {"title": _("Parceiros"), "icon": "ph-plus", "action": _("Novo parceiro")},
    "languages": {"title": _("Idiomas"), "icon": "ph-plus", "action": _("Adicionar idioma")},
    "appearance": {"title": _("Aparência"), "icon": "ph-check", "action": _("Publicar")},
    "system": {"title": _("Sistema"), "icon": "ph-upload-simple", "action": _("Novo modelo")},
}
