"""
Views de conta: cadastro, login, perfil e recuperacao de senha.

Tudo usa os mecanismos nativos do Django: sessao, hash de senha, CSRF,
validacao de formularios e os tokens de recuperacao de senha. Cada view
opera apenas sobre `request.user`; nao ha rota que exponha dados de outro
usuario.
"""

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme, urlsafe_base64_decode
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from apps.content.context_processors import globais

from . import confirmacao
from .confirmacao import token_de_email
from .forms import LoginForm, PasswordChangeForm, ProfileForm, SetPasswordForm, SignupForm
from .models import User

# Secoes do perfil e o titulo usado no cabecalho do celular.
#
# Nao ha secao "idioma": a interface e so em portugues (Fase 5, Etapa
# 4.1) e o idioma da carta e escolhido na etapa 5 do assistente. Um
# `?secao=idioma` antigo cai no `else` de `profile()` e abre o perfil
# inteiro -- melhor do que um 404 para quem tinha o link guardado.
PROFILE_SECTIONS = {
    "dados": gettext_lazy("Dados pessoais"),
    "senha": gettext_lazy("Alterar senha"),
    "comunicacoes": gettext_lazy("Comunicações"),
}


def _safe_next(request):
    """URL de retorno (?next=) apenas se apontar para este site."""
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return None


@sensitive_post_parameters("password1", "password2")
@never_cache
def signup(request):
    """Criar conta (layouts 1d e 1m). Apos criar, autentica e vai ao dashboard."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            # O convite de confirmacao sai AQUI, depois de a conta
            # existir. `enviar` nao levanta excecao se o servidor de
            # e-mail estiver fora: a conta ja foi criada e a pessoa ja
            # esta dentro -- derrubar a tela agora seria o pior dos dois
            # mundos. O botao de reenviar fica no aviso da area logada.
            confirmacao.enviar(request, user)
            return redirect(_safe_next(request) or "core:dashboard")
    else:
        form = SignupForm()

    return render(
        request,
        "accounts/signup.html",
        {"form": form, "next": request.GET.get("next", "")},
    )


class LoginView(auth_views.LoginView):
    """Entrar (layouts 1c e 1l). Template em registration/login.html."""

    authentication_form = LoginForm
    redirect_authenticated_user = True


def _profile_url(section):
    url = reverse("accounts:profile")
    if section in PROFILE_SECTIONS:
        url += f"?secao={section}#{section}"
    return url


@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@login_required
def profile(request):
    """
    Perfil (layouts 1h e 1q).

    Uma pagina, dois formularios: dados pessoais (action=dados) e troca de
    senha (action=senha). No celular, ?secao= abre uma secao por vez; o
    campo oculto `secao` devolve o usuario a mesma secao apos salvar.
    """
    user = request.user
    section = request.GET.get("secao")
    # De onde a pessoa veio (ex.: uma etapa do assistente que exigia um
    # dado do perfil). So aceitamos caminhos internos, para o parametro
    # nao virar um redirecionamento para fora do site.
    voltar_para = _safe_next(request)
    profile_form = ProfileForm(instance=user)
    password_form = PasswordChangeForm(user)

    if request.method == "POST":
        section = request.POST.get("secao") or None
        if request.POST.get("action") == "senha":
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                password_form.save()
                # Mantem a sessao valida apos trocar a senha.
                update_session_auth_hash(request, password_form.user)
                messages.success(request, _("Senha atualizada."))
                return redirect(_profile_url(section))
            section = "senha"
        else:
            profile_form = ProfileForm(request.POST, instance=user)
            if profile_form.is_valid():
                # O endereco ANTES de salvar: e a comparacao que diz se a
                # confirmacao ainda vale.
                email_anterior = User.objects.values_list("email", flat=True).get(pk=user.pk)
                profile_form.save()

                if user.email != email_anterior:
                    # Herdar a confirmacao do endereco antigo faria a
                    # marca de "confirmado" dizer algo falso. Some, e o
                    # convite sai para o endereco novo.
                    confirmacao.esquecer(user)
                    confirmacao.enviar(request, user)
                    messages.success(
                        request,
                        _(
                            "Alterações salvas. Enviamos um link de confirmação "
                            "para %(email)s."
                        )
                        % {"email": user.email},
                    )
                else:
                    messages.success(request, _("Alterações salvas."))
                return redirect(voltar_para or _profile_url(section))
            section = "dados"

    if section not in PROFILE_SECTIONS:
        section = None

    return render(
        request,
        "accounts/profile.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
            "section": section,
            "section_title": PROFILE_SECTIONS.get(section, ""),
            "return_to": voltar_para,
            "active_nav": "profile",
        },
    )


# ---------------------------------------------------------------------------
# Recuperacao de senha: fluxo nativo do Django (token assinado, com prazo
# PASSWORD_RESET_TIMEOUT), apenas com os templates do Desenrola.
# ---------------------------------------------------------------------------


class PasswordResetView(auth_views.PasswordResetView):
    """
    Pedir uma nova senha.

    O NOME DO SITE CHEGA AO E-MAIL POR AQUI, E NAO POR PROCESSADOR DE
    CONTEXTO
    ----------------------------------------------------------------
    O corpo e o assunto sao renderizados por `render_to_string` DENTRO
    de `PasswordResetForm.save()` -- sem request. Processador de
    contexto so roda com request, entao `site_config` simplesmente nao
    existe la: usa-lo deixaria o nome VAZIO no e-mail, em silencio.

    A ponte certa e `extra_email_context`, que o proprio Django preve
    para isto: a view TEM request, le o nome aqui e o entrega pronto no
    contexto do template. E o mesmo caminho por onde `domain` e
    `protocol` ja chegam.

    O ENDERECO NAO PRECISA DE CONFIGURACAO NOVA
    -------------------------------------------
    `domain` e `protocol` sao calculados por `PasswordResetForm.save()`
    a partir do request (`get_host()` e `is_secure()`) ANTES da
    renderizacao. Em producao isso da o dominio real, porque
    `ALLOWED_HOSTS` vem do ambiente, e da `https`, porque
    `SECURE_PROXY_SSL_HEADER` esta configurado (ver `settings/prod.py`).
    Uma constante `SITE_URL` seria uma segunda fonte de verdade para
    algo que o Django ja deriva certo.
    """

    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    # A alternativa HTML. O Django manda as DUAS: quem le em texto puro,
    # em cliente antigo ou com HTML desligado recebe a mesma informacao.
    # O texto continua sendo o conteudo; o HTML e a apresentacao.
    html_email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form):
        # No `form_valid`, e nao como atributo de classe: um atributo
        # seria avaliado no import, quando ainda nao ha banco para ler.
        #
        # `globais()` e nao `SiteSettings.load()`: aquele LE sem criar
        # linha. Pedir uma senha nova nao e motivo para escrever no
        # banco de configuracao.
        site = globais()
        self.extra_email_context = {
            **(self.extra_email_context or {}),
            "nome_do_site": site.name,
            # A identidade visual vem do MESMO lugar que o site le. Uma
            # cor escrita no template do e-mail seria uma segunda fonte
            # de verdade, e o e-mail deixaria de acompanhar a Aparencia.
            "cor_principal": site.primary_color,
            "logo_url": self._endereco_da_logomarca(site),
        }
        return super().form_valid(form)

    def _endereco_da_logomarca(self, site):
        """
        O endereco ABSOLUTO da logomarca, ou vazio.

        Absoluto porque um e-mail nao tem pagina de origem: `/media/...`
        nao resolve em lugar nenhum dentro do cliente de e-mail.
        `build_absolute_uri` usa o mesmo host de onde a pessoa pediu a
        senha -- a mesma regra de `domain` e `protocol`.

        Vazio quando nao ha logomarca cadastrada: o template cai na marca
        escrita, como o site faz.
        """
        if not (site.logo and site.logo.file):
            return ""
        return self.request.build_absolute_uri(site.logo.file.url)


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    form_class = SetPasswordForm
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


# ---------------------------------------------------------------------------
# Confirmacao de e-mail
# ---------------------------------------------------------------------------
#
# O token, o prazo e o que entra no hash estao em `accounts.confirmacao`.
# Aqui ficam so as duas portas: abrir o link, e pedir outro.


def _pessoa_do_link(uidb64):
    """
    De quem e o link, ou None.

    `None` para uid ilegivel, para pk inexistente e para conta
    desativada -- os tres dao a MESMA resposta na tela, de proposito:
    dizer "esta conta nao existe" contaria a quem tem o link se aquele
    endereco tem conta aqui.
    """
    try:
        pk = urlsafe_base64_decode(uidb64).decode()
        pessoa = User.objects.get(pk=pk, is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist, ValidationError):
        return None
    return pessoa


@never_cache
def confirmar_email(request, uidb64, token):
    """
    Abre o link do e-mail e confirma o endereco.

    NAO EXIGE ESTAR AUTENTICADO
    ---------------------------
    O link chega por e-mail e costuma ser aberto no celular, noutro
    navegador, sem sessao. Exigir login mandaria a pessoa para a tela de
    entrar e o link se perderia no caminho. O que prova quem e nao e a
    sessao: e o token assinado.

    JA CONFIRMADO NAO E ERRO
    ------------------------
    O token morre no uso, entao abrir de novo cai no ramo invalido. Por
    isso quem ja confirmou e reconhecido ANTES da checagem do token e ve
    uma tela de sucesso -- e o mesmo link, aberto duas vezes, ou o
    pre-carregador do cliente de e-mail.
    """
    pessoa = _pessoa_do_link(uidb64)

    if pessoa is not None and pessoa.email_confirmado:
        return render(
            request,
            "accounts/email_confirmation_done.html",
            {"confirmou": True, "ja_estava": True, "pessoa": pessoa},
        )

    valido = pessoa is not None and token_de_email.check_token(pessoa, token)
    if valido:
        confirmacao.confirmar(pessoa)

    return render(
        request,
        "accounts/email_confirmation_done.html",
        {"confirmou": valido, "ja_estava": False, "pessoa": pessoa if valido else None},
    )


@login_required
@require_POST
def reenviar_confirmacao(request):
    """
    Manda outro convite de confirmacao para o proprio e-mail.

    So POST, e so para `request.user`: um GET seria disparado por
    qualquer pre-carregador de navegador, e um destinatario vindo do
    pedido transformaria esta rota num disparador de e-mail para
    terceiros.
    """
    if request.user.email_confirmado:
        messages.info(request, _("Seu e-mail já está confirmado."))
    elif confirmacao.enviar(request, request.user):
        messages.success(
            request,
            _("Enviamos um novo link para %(email)s. Confira também o spam.")
            % {"email": request.user.email},
        )
    else:
        messages.error(
            request,
            _(
                "Não conseguimos enviar o e-mail agora. Tente de novo em alguns "
                "minutos."
            ),
        )
    return redirect(_safe_next(request) or "accounts:profile")
