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


# ---------------------------------------------------------------------------
# Area administrativa
# ---------------------------------------------------------------------------


# (administrador, gerente, operador, usuario)


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
    # A visao geral e real desde a etapa do gerenciador de usuarios, e
    # nao tem acao propria: sem `action`, o cabecalho movel nao
    # renderiza botao nenhum.
    "overview": {"title": _("Visão geral"), "icon": "", "action": ""},
    "letters": {"title": _("Cartas"), "icon": "ph-magnifying-glass", "action": _("Buscar")},
    "templates": {"title": _("Modelos"), "icon": "ph-upload-simple", "action": _("Novo modelo")},
    "content": {"title": _("Conteúdo"), "icon": "ph-upload-simple", "action": _("Novo modelo")},
    "partners": {"title": _("Parceiros"), "icon": "ph-plus", "action": _("Novo parceiro")},
    "languages": {"title": _("Idiomas"), "icon": "ph-plus", "action": _("Adicionar idioma")},
    "appearance": {"title": _("Aparência"), "icon": "ph-check", "action": _("Publicar")},
    "letter_policy": {
        "title": _("Política das cartas"),
        "icon": "ph-floppy-disk",
        "action": _("Salvar"),
    },
    # Tela real: sem `action`, o cabeçalho do celular não renderiza
    # botão nenhum (ver backoffice/base.html) -- os botões desta tela
    # ficam no corpo, onde fazem alguma coisa.
    "email_settings": {"title": _("Configuração de e-mail"), "icon": "", "action": ""},
    "system": {"title": _("Sistema"), "icon": "ph-upload-simple", "action": _("Novo modelo")},
}
