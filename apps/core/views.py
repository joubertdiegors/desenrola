"""
Views do app core.

As areas do usuario exigem login; a area administrativa exige a
permissao `core.access_backoffice`. O dashboard e a supervisao de
cartas (esta em `apps.letters.backoffice_views`) leem o banco; a
landing e as demais telas administrativas continuam com dados
ficticios (apps.core.demo) ate as proximas etapas do backend.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.content import services as content
from apps.content.models import Partner
from apps.letters import lifecycle, presentation, statistics
from apps.letters import services as letter_services

from . import demo, mail
from .forms import (
    DocumentLanguagesForm,
    EmailSettingsForm,
    EmailTestForm,
    LetterPolicyForm,
)

# A permissao que abre a porta do Backoffice. Uma constante, e nao a
# string solta em cada view/template, para o dia em que alguem precisar
# procurar "quem decide isso".
BACKOFFICE_PERM = "core.access_backoffice"

# Permissao para MUDAR a politica das cartas. Entrar no Backoffice e uma
# coisa; alterar uma regra que vale para todo mundo e outra.
LETTER_POLICY_PERM = "letters.change_letterpolicy"

# Mesma ideia para os idiomas do DOCUMENTO: qualquer pessoa do
# Backoffice pode ver quais idiomas o produto oferece; mudar a oferta
# e um degrau acima.
DOCUMENT_LANGUAGES_PERM = "letters.change_documentlanguagesettings"

# Configuracao de e-mail: ver e alterar sao permissoes diferentes. Quem
# altera mexe em credencial de um servidor externo -- e o degrau mais
# alto desta area, e nao vem junto com "entrar no Backoffice".
#
# (Os comentarios desta metade do arquivo seguem sem acento, como o
# resto do cabecalho; as docstrings das telas novas, acentuadas, como as
# das telas mais recentes logo abaixo.)
EMAIL_VIEW_PERM = "core.view_emailsettings"
EMAIL_CHANGE_PERM = "core.change_emailsettings"


def backoffice_required(view):
    """
    Exige login e a permissao `core.access_backoffice`; sem ela, 403.

    E a UNICA porta do Backoffice, e ela e no servidor: esconder o
    link no dashboard nao protege nada -- a URL continua sendo
    digitavel. Superusuario passa por `has_perm` automaticamente.

    Substituiu a checagem de `is_staff` (a flag do Django Admin, que
    este projeto nao usa como backoffice). Quem ja era staff recebeu a
    permissao na migration `core.0001`, entao ninguem perdeu acesso.
    """

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.has_perm(BACKOFFICE_PERM):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def exige_permissao(permissao):
    """
    Decorador: entrar no Backoffice E ter `permissao`; senao, 403.

    Mora aqui, junto de `backoffice_required`, porque a decisao e a
    mesma em toda a area administrativa -- `doctemplates.library_views`
    e as telas de e-mail usam este mesmo decorador, e uma segunda copia
    acabaria divergindo.

    A porta e no SERVIDOR. Esconder o botao nao protege nada -- a URL
    continua sendo digitavel, e e o que alguem tentaria.
    """

    def decorador(view):
        @backoffice_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.has_perm(permissao):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorador


def home(request):
    """
    Landing publica (layouts 2a, 3a e 4a).

    Quem ja esta logado nao tem o que fazer na pagina de apresentacao:
    vai direto para a sua area. O logout traz de volta para ca
    (LOGOUT_REDIRECT_URL), e ai a sessao ja acabou -- entao nao ha laco.

    TRES FONTES REAIS, NENHUMA INVENTADA
    ------------------------------------
      secoes          o texto, de `content.Page` (chave "home");
      parceiros       os `content.Partner` ativos, com o logo ja carregado;
      cartas_emitidas quantas Cartas Convite existem de fato.

    Carregadas AQUI, e nao no processador de contexto global: sao dados
    desta pagina. O processador guarda o que vale para o site inteiro
    (`site.name`, logo, favicon) -- enche-lo com o que so a Home usa
    faria toda pagina pagar por isto.
    """
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    return render(
        request,
        "core/home.html",
        {
            "secoes": content.secoes_da_pagina(content.CHAVE_DA_HOME),
            "parceiros": Partner.objects.publicados(),
            "cartas_emitidas": statistics.cartas_emitidas(),
        },
    )


@login_required
def dashboard(request):
    """
    Area do usuario: as cartas DELE, vindas do banco.

    Lista as mais recentes (`presentation.RECENT_LIMIT`), mas conta o
    total -- o numero ao lado do titulo e quantas cartas a pessoa tem, nao
    quantas couberam na lista.

    Nao passa nada sobre o Backoffice: o atalho para la mora na barra
    superior e se decide sozinho, por `perms.core.access_backoffice`
    (o processador de contexto de autenticacao ja o entrega a todo
    template). Uma porta so, e sem uma chave por view.
    """
    letters = presentation.own_letters(request.user)
    return render(
        request,
        "core/dashboard.html",
        {
            "cards": presentation.build_cards(letters[: presentation.RECENT_LIMIT]),
            "letters_total": letters.count(),
            "active_nav": "home",
            "mobile_nav": True,
        },
    )


def healthz(request):
    """
    Verificacao de saude da aplicacao.

    Responde sem tocar no banco nem em templates, para servir de sonda
    barata de monitoramento apos o deploy.
    """
    return HttpResponse("ok", content_type="text/plain")


# ---------------------------------------------------------------------------
# Area administrativa (representacao visual; nao substitui o Django Admin)
# ---------------------------------------------------------------------------


def _backoffice_context(active):
    section = demo.BACKOFFICE_SECTIONS[active]
    return {
        "active": active,
        "bo_title": section["title"],
        "bo_action_icon": section["icon"],
        "bo_action_label": section["action"],
    }


@backoffice_required
def backoffice_overview(request):
    """
    A porta de entrada do Backoffice: alguns números reais e os
    atalhos que ESTA pessoa pode abrir.

    Deliberadamente pequena. Um painel administrativo de verdade
    (gráficos, séries, alertas) é etapa própria; o que esta tela não
    pode é continuar mostrando estatísticas inventadas, que era o que
    fazia até aqui.

    Exige só `core.access_backoffice`: é para cá que o atalho do
    painel aponta, e quem administra modelos ou cartas precisa entrar
    sem ter `accounts.manage_users`. Cada atalho, esse sim, aparece
    conforme a permissão de quem olha.
    """
    from apps.doctemplates.models import DocumentTemplate
    from apps.letters.models import Letter

    User = get_user_model()
    context = _backoffice_context("overview")
    context.update(
        {
            "numeros": [
                {
                    "rotulo": _("Usuários ativos"),
                    "valor": User.objects.filter(is_active=True).count(),
                },
                {"rotulo": _("Cartas"), "valor": Letter.objects.count()},
                {
                    "rotulo": _("Modelos oficiais"),
                    "valor": DocumentTemplate.objects.filter(is_system=True).count(),
                },
            ],
        }
    )
    return render(request, "backoffice/overview.html", context)


@backoffice_required
def backoffice_templates(request, active="templates"):
    """
    Modelos e Sistema -- as duas telas que ainda sao ilustrativas.

    Ja NAO serve mais Conteudo (Etapa D) nem Idiomas (Etapa E): as
    duas viraram telas reais, com view propria. O cartao de idiomas
    que morava aqui saiu junto, com os percentuais de traducao que
    ele inventava.
    """
    context = _backoffice_context(active)
    return render(request, "backoffice/templates.html", context)


@backoffice_required
def backoffice_partners(request):
    """Parceiros (novo menu na v2; sem layout de tela detalhado)."""
    context = _backoffice_context("partners")
    context["partners"] = demo.ADMIN_PARTNERS
    return render(request, "backoffice/partners.html", context)


@backoffice_required
def backoffice_appearance(request):
    """
    Aparencia: mostra as cores publicadas -- e diz onde se edita.

    SOMENTE LEITURA, de proposito. Ate aqui esta tela oferecia botoes de
    cor que gravavam a escolha no `localStorage` do navegador de quem
    estava mexendo: mudavam a aparencia para uma pessoa so, e nada era
    publicado. Os botoes sairam.

    As cores agora vem de `content.SiteSettings` e valem para todo
    visitante. A tela de edicao propria do Backoffice e etapa posterior;
    ate la o cadastro e pelo Django Admin, e a tela diz isso.

    Nao passa as cores no contexto: elas ja chegam a todo template pelo
    processador de contexto do app content (`site.primary_color`).
    """
    context = _backoffice_context("appearance")
    context["url_do_admin"] = reverse("admin:content_sitesettings_changelist")
    return render(request, "backoffice/appearance.html", context)


@backoffice_required
def backoffice_letter_policy(request):
    """
    Política das cartas: por quanto tempo uma carta finalizada pode ser
    editada, e quando ela expira.

    Entrar aqui exige `core.access_backoffice`; SALVAR exige, além
    disso, `letters.change_letterpolicy` -- ver uma regra que vale para
    todo mundo é uma coisa, mudá-la é outra. A checagem é no POST, não
    só no botão.

    Os valores vão para `letters.LetterPolicy` (um registro só). Quem
    faz a conta com eles é `apps.letters.lifecycle`; esta view não
    calcula prazo nenhum.
    """
    config = lifecycle.policy()
    pode_editar = request.user.has_perm(LETTER_POLICY_PERM)

    if request.method == "POST":
        if not pode_editar:
            raise PermissionDenied
        form = LetterPolicyForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, _("Política das cartas atualizada."))
            return redirect(reverse("backoffice:letter_policy"))
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = LetterPolicyForm(instance=config)

    context = _backoffice_context("letter_policy")
    context.update({"form": form, "pode_editar": pode_editar})
    return render(request, "backoffice/letter_policy.html", context)


@backoffice_required
def backoffice_languages(request):
    """
    Idiomas dos documentos: quais o assistente oferece para uma carta
    nova, e em qual ela nasce.

    NÃO É O IDIOMA DA INTERFACE. A interface é só portuguesa desde a
    Etapa 4.1 e continua sendo -- esta tela não a toca, e diz isso em
    voz alta, porque os dois conceitos são fáceis de confundir.

    Entrar aqui exige `core.access_backoffice`; SALVAR exige, além
    disso, `letters.change_documentlanguagesettings` -- ver uma regra que
    vale para todo mundo é uma coisa, mudá-la é outra (mesma decisão de
    `backoffice_letter_policy`). A checagem é no POST, no servidor, não
    só no botão.

    Desativar um idioma não apaga nada: nem carta, nem modelo oficial,
    nem histórico. Quem faz a conta com esses valores é
    `apps.letters.services`; esta view não decide idioma nenhum.
    """
    config = letter_services.configuracao_de_idiomas()
    pode_editar = request.user.has_perm(DOCUMENT_LANGUAGES_PERM)

    if request.method == "POST":
        if not pode_editar:
            raise PermissionDenied
        form = DocumentLanguagesForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, _("Idiomas dos documentos atualizados."))
            return redirect(reverse("backoffice:languages"))
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
    else:
        form = DocumentLanguagesForm(instance=config)

    context = _backoffice_context("languages")
    context.update({"form": form, "pode_editar": pode_editar})
    return render(request, "backoffice/languages.html", context)


# ---------------------------------------------------------------------------
# Configuracao de envio de e-mail
# ---------------------------------------------------------------------------


def _contexto_do_email(request, config, form=None):
    """A casca da tela de e-mail, montada num lugar so -- as tres views
    terminam nela (duas por redirect, uma renderizando)."""
    context = _backoffice_context("email_settings")
    context.update(
        {
            "form": form if form is not None else EmailSettingsForm(instance=config),
            "teste": EmailTestForm(),
            "config": config,
            "pode_editar": request.user.has_perm(EMAIL_CHANGE_PERM),
        }
    )
    return context


@exige_permissao(EMAIL_VIEW_PERM)
def backoffice_email_settings(request):
    """
    Como o sistema manda e-mail: servidor, porta, segurança, usuário,
    senha e remetente.

    VER exige `core.view_emailsettings`; SALVAR exige, além disso,
    `core.change_emailsettings` -- consultar para onde o sistema aponta
    é uma coisa, mexer na credencial de um servidor externo é outra. A
    checagem do POST é aqui, no servidor, não no botão.

    A SENHA NÃO SAI DAQUI. O formulário tem um campo de escrita que
    volta sempre em branco; o que a tela mostra é apenas SE existe uma
    senha guardada. Não há caminho que a devolva.

    Salvar NÃO liga o envio: ativar e desativar tem botão próprio, para
    dar para cadastrar, testar e só então passar a valer.
    """
    config = mail.configuracao()

    if request.method == "POST":
        if not request.user.has_perm(EMAIL_CHANGE_PERM):
            raise PermissionDenied
        form = EmailSettingsForm(request.POST, instance=config)
        if form.is_valid():
            configuracao = form.save(commit=False)
            configuracao.updated_by = request.user
            configuracao.save()
            messages.success(request, _("Configuração de e-mail salva."))
            return redirect(reverse("backoffice:email_settings"))
        messages.error(request, _("Corrija os campos destacados antes de salvar."))
        # Config RECARREGADA para a tela: o formulario ja aplicou a senha
        # digitada (ou a remocao) na instancia dele, e nada disso foi
        # gravado. Mostrar aquele objeto diria "senha apagada" sobre uma
        # senha que continua no banco.
        return render(
            request,
            "backoffice/email_settings.html",
            _contexto_do_email(request, mail.configuracao(), form),
        )

    return render(request, "backoffice/email_settings.html", _contexto_do_email(request, config))


@exige_permissao(EMAIL_CHANGE_PERM)
@require_POST
def backoffice_email_settings_test(request):
    """
    Manda uma mensagem de teste para o endereço que o administrador
    digitar.

    Exige a permissão de ALTERAR, e não a de ver: o teste abre uma
    conexão com a credencial guardada e gasta o servidor de e-mail de
    verdade -- não é uma leitura.

    Usa o que está salvo, ativo ou não. Testar antes de ligar é a ordem
    certa de fazer as coisas.

    O resultado nunca revela credencial: o erro vem traduzido por
    `mail._motivo`, que troca a exceção por uma frase.
    """
    config = mail.configuracao()
    form = EmailTestForm(request.POST)

    if not form.is_valid():
        messages.error(request, _("Informe um endereço de e-mail válido para o teste."))
        return redirect(reverse("backoffice:email_settings"))

    if not config.host:
        messages.error(request, _("Cadastre o servidor SMTP antes de enviar um teste."))
        return redirect(reverse("backoffice:email_settings"))

    destino = form.cleaned_data["destino"]
    ok, motivo = mail.enviar_teste(config, destino)
    if ok:
        messages.success(
            request,
            _("Mensagem de teste enviada para %(destino)s.") % {"destino": destino},
        )
    else:
        messages.error(request, motivo)
    return redirect(reverse("backoffice:email_settings"))


@exige_permissao(EMAIL_CHANGE_PERM)
@require_POST
def backoffice_email_settings_activation(request):
    """
    Liga e desliga o envio real.

    Desligado, as mensagens do sistema seguem para o destino de reserva
    do ambiente (console em desenvolvimento, `EMAIL_URL` em produção) --
    o fluxo continua funcionando, nada estoura.

    Ligar passa pelo `full_clean()` do modelo: uma configuração ativa
    sem servidor ou sem remetente falharia em toda mensagem, inclusive
    na recuperação de senha de quem está trancado para fora.
    """
    config = mail.configuracao()
    config.is_active = request.POST.get("ativo") == "1"

    try:
        config.full_clean()
    except ValidationError:
        messages.error(
            request,
            _("Cadastre o servidor SMTP e o remetente antes de ativar o envio."),
        )
        return redirect(reverse("backoffice:email_settings"))

    config.updated_by = request.user
    config.save()
    if config.is_active:
        messages.success(request, _("Envio de e-mail ativado."))
    else:
        messages.success(request, _("Envio de e-mail desativado."))
    return redirect(reverse("backoffice:email_settings"))
