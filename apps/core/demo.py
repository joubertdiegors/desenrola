"""
Dados ficticios da fase de apresentacao visual.

Alimentam as telas que ainda nao tem uma fonte real: a Home/Landing e o
backoffice. Nomes, datas e numeros vem dos layouts de referencia
(desenrola-v2-2-desktop.html, desenrola-v2-3-tablet.html e
desenrola-v2-4-mobile.html). Este modulo sera removido conforme cada
parte ganhar uma implementacao real.

Ja NAO passam por aqui: o assistente de Carta Convite (dados reais desde
a Fase 3), a geracao do PDF (Fase 4) e o dashboard do usuario, que desde
a Fase 5 le as cartas do banco (apps/letters/presentation.py). O que
resta e a landing e a listagem ilustrativa do backoffice.
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
