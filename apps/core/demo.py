"""
Dados ficticios da fase de apresentacao visual.

Alimentam as telas enquanto autenticacao, banco e geracao de PDF nao
existem. Nomes, datas e numeros vem dos layouts de referencia
(desenrola-2-desktop.html e desenrola-3-mobile.html). Este modulo sera
removido quando as views passarem a ler do banco.
"""

from django.utils.translation import gettext_lazy as _

USER = {
    "name": "Claire Dubois",
    "first_name": "Claire",
    "initials": "CD",
    "email": "claire.dubois@exemplo.be",
    "phone": "+32 470 00 00 00",
    "address": "Rue des Exemple 25 – 1200 Woluwe-Saint-Lambert",
    "birth_date": "14/03/1985",
    "nationality": _("Belga"),
    "id_number": "00000000",
    "member_since": _("Conta desde ago. 2026"),
}

GUEST = {
    "name": "Carlos Eduardo Silva",
    "nationality": _("Brasileira"),
    "birth_date": "22/07/1990",
    # Incompleto de proposito: a referencia mostra o estado de erro do campo.
    "passport": "YY0000",
}

STAY = {
    "arrival": "10/10/2026",
    "departure": "24/10/2026",
    "place": "Woluwe-Saint-Lambert",
    "date": "09/09/2026",
}

ALL_LETTERS = [
    {
        "id": 1,
        "date": "09/09/2026",
        "host": "Claire Dubois",
        "guest": "Carlos Eduardo Silva",
        "language": _("Francês"),
        "status": "generated",
        "status_label": _("Gerada"),
        "generated_at": "09/09/2026 · 14:32",
        "filename": "carta-convite-carlos-silva.pdf",
    },
    {
        "id": 2,
        "date": "21/08/2026",
        "host": "Claire Dubois",
        "guest": "Maria Fernanda Souza",
        "language": _("Francês"),
        "status": "generated",
        "status_label": _("Gerada"),
        "generated_at": "21/08/2026 · 10:05",
        "filename": "carta-convite-maria-souza.pdf",
    },
    {
        "id": 3,
        "date": "02/07/2026",
        "host": "Claire Dubois",
        "guest": "João Pedro Alves",
        "language": _("Neerlandês"),
        "status": "draft",
        "status_label": _("Rascunho"),
        "generated_at": "",
        "filename": "carta-convite-joao-alves.pdf",
    },
    {
        "id": 4,
        "date": "12/08/2026",
        "host": "Rafael Costa",
        "guest": "Beatriz Costa",
        "language": _("Francês"),
        "status": "generated",
        "status_label": _("Gerada"),
        "generated_at": "12/08/2026 · 18:20",
        "filename": "carta-convite-beatriz-costa.pdf",
    },
    {
        "id": 5,
        "date": "30/07/2026",
        "host": "Sofia Nkemelu",
        "guest": "Amara Nkemelu",
        "language": _("Neerlandês"),
        "status": "generated",
        "generated_at": "30/07/2026 · 09:41",
        "status_label": _("Gerada"),
        "filename": "carta-convite-amara-nkemelu.pdf",
    },
]

# Cartas da usuaria ficticia (dashboard)
LETTERS = [letter for letter in ALL_LETTERS if letter["host"] == USER["name"]]


def get_letter(pk):
    """Devolve a carta ficticia com esse id ou None."""
    for letter in ALL_LETTERS:
        if letter["id"] == pk:
            return letter
    return None


# Passos do formulario no celular (um passo por tela). So o passo 2 tem
# textos na referencia; os demais derivam dos titulos das secoes do desktop.
FORM_STEPS = {
    1: {
        "kicker": _("Anfitrião"),
        "title": _("Anfitrião (você)"),
        "hint": _("Preenchido a partir do perfil."),
    },
    2: {
        "kicker": _("Convidado"),
        "title": _("Quem você está convidando?"),
        "hint": _("Copie do passaporte, sem abreviações."),
    },
    3: {
        "kicker": _("Estadia"),
        "title": _("Estadia"),
        "hint": "",
    },
    4: {
        "kicker": _("Revisão"),
        "title": _("Gerar Carta Convite"),
        "hint": _("Confira os dados antes de gerar."),
    },
}

# Secoes do perfil (titulo usado no cabecalho do celular)
PROFILE_SECTIONS = {
    "dados": _("Dados pessoais"),
    "senha": _("Alterar senha"),
    "idioma": _("Idioma e aparência"),
    "comunicacoes": _("Comunicações"),
}


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
        "name": "Claire Dubois",
        "initials": "CD",
        "email": "claire.dubois@exemplo.be",
        "role": "user",
        "role_label": _("Usuário"),
        "letters": 3,
        "last_access": _("Hoje"),
        "mobile_note": _("3 cartas"),
        "active": True,
    },
    {
        "name": "Rafael Costa",
        "initials": "RC",
        "email": "rafael.c@exemplo.com",
        "role": "user",
        "role_label": _("Usuário"),
        "letters": 1,
        "last_access": "12/08/2026",
        "mobile_note": _("1 carta"),
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
    {"label": _("Editar modelos, conteúdo e idiomas"), "levels": (True, True, False, False)},
    {"label": _("Gerenciar permissões e sistema"), "levels": (True, False, False, False)},
]

STATS = [
    {"label": _("Usuários"), "value": "1.284", "note": _("+38 esta semana"), "tone": "success"},
    {"label": _("Cartas geradas"), "value": "3.902", "note": _("214 este mês"), "tone": ""},
    {"label": _("Modelos ativos"), "value": "1", "note": _("Carta convite · v2.1"), "tone": ""},
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

# Titulo e acao da barra do celular por secao do admin
BACKOFFICE_SECTIONS = {
    "overview": {"title": _("Visão geral"), "icon": "ph-plus", "action": _("Convidar usuário")},
    "users": {"title": _("Usuários"), "icon": "ph-plus", "action": _("Convidar usuário")},
    "permissions": {"title": _("Permissões"), "icon": "ph-plus", "action": _("Convidar usuário")},
    "letters": {"title": _("Cartas"), "icon": "ph-magnifying-glass", "action": _("Buscar")},
    "templates": {"title": _("Modelos"), "icon": "ph-upload-simple", "action": _("Novo modelo")},
    "content": {"title": _("Conteúdo"), "icon": "ph-upload-simple", "action": _("Novo modelo")},
    "languages": {"title": _("Idiomas"), "icon": "ph-plus", "action": _("Adicionar idioma")},
    "system": {"title": _("Sistema"), "icon": "ph-upload-simple", "action": _("Novo modelo")},
}
