"""
O titulo e a acao de cada secao do backoffice, para o cabecalho do
celular.

O QUE SOBROU AQUI, E O QUE O NOME DO MODULO AINDA CONTA
-------------------------------------------------------
Este modulo nasceu com os dados ficticios da fase de apresentacao
visual, copiados dos layouts de referencia. Nao ha mais nenhum: o
assistente e o PDF leem o banco desde as Fases 3 e 4; o dashboard, desde
a Fase 5; e o bloco CMS (Etapas A a I) levou o resto -- `LANGUAGES` saiu
na Etapa E, `LANDING_STAT` e `PARTNERS` na Etapa B, `ADMIN_PARTNERS` na
Etapa I.

O que resta e `BACKOFFICE_SECTIONS`, que NAO e dado ficticio: e a
configuracao de qual titulo o cabecalho do celular mostra em cada tela.
Continua neste arquivo porque move-lo seria renomear modulo sem mudar
comportamento -- o nome `demo` e o que envelheceu, nao o conteudo.

`action` vazio significa "esta tela e real": `backoffice/base.html` so
desenha o botao do cabecalho movel quando ha rotulo, justamente para nao
existir botao que nao faz nada.
"""

from django.utils.translation import gettext_lazy as _

# ---------------------------------------------------------------------------
# Cartas (dashboard e backoffice)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Area administrativa
# ---------------------------------------------------------------------------


# (administrador, gerente, operador, usuario)


# Titulo e acao da barra do celular por secao do admin
BACKOFFICE_SECTIONS = {
    # A visao geral e real desde a etapa do gerenciador de usuarios, e
    # nao tem acao propria: sem `action`, o cabecalho movel nao
    # renderiza botao nenhum.
    "overview": {"title": _("Visão geral"), "icon": "", "action": ""},
    # Tela real desde a Etapa I: sem `action`, o cabecalho do celular
    # nao renderiza botao nenhum (ver backoffice/base.html). O "Novo
    # parceiro" que havia aqui nao cadastrava nada -- quem cadastra e a
    # administracao do Django.
    "partners": {"title": _("Parceiros"), "icon": "", "action": ""},
    # Tela real desde a Etapa E: sem `action`, o cabecalho do celular
    # nao renderiza botao nenhum. Nao havia idioma para "adicionar" --
    # os quatro oficiais sao fixos; o que se administra e quais deles
    # sao oferecidos.
    "languages": {"title": _("Idiomas"), "icon": "", "action": ""},
    # Tela de leitura: sem `action`, o cabecalho do celular nao renderiza
    # botao nenhum (ver backoffice/base.html). O "Publicar" que havia aqui
    # nao publicava nada.
    "appearance": {"title": _("Aparência"), "icon": "", "action": ""},
    # Tela real: sem `action`, o cabeçalho do celular não renderiza
    # botão nenhum (ver backoffice/base.html). O "Salvar" que havia aqui
    # não salvava nada -- quem salva é o "Salvar política" do formulário,
    # no corpo da tela.
    "letter_policy": {"title": _("Wizzard - gerar carta"), "icon": "", "action": ""},
    # Tela real: sem `action`, o cabeçalho do celular não renderiza
    # botão nenhum (ver backoffice/base.html) -- os botões desta tela
    # ficam no corpo, onde fazem alguma coisa.
    "email_settings": {"title": _("Configuração de e-mail"), "icon": "", "action": ""},
    # Tela real desde a Etapa F: sem `action`, o cabecalho do celular
    # nao renderiza botao nenhum. O "Novo modelo" que havia aqui era
    # copia da tela de Modelos e nao fazia nada.
    "system": {"title": _("Identidade"), "icon": "", "action": ""},
    # Os documentos legais (Rodada 21): cada um com a sua tela, e por
    # isso com o proprio titulo -- `content.backoffice_views` monta o
    # cabecalho sozinho (sempre montou, mesmo antes da separacao), sem
    # passar por `_backoffice_context`. As chaves ficam aqui pela mesma
    # razao do resto do dicionario: documentar qual `active` cada tela usa.
    "legal_documents_terms": {"title": _("Termos de uso"), "icon": "", "action": ""},
    "legal_documents_privacy": {"title": _("Privacidade"), "icon": "", "action": ""},
}
