"""
Gerenciador de usuários e permissões do Backoffice.

Arquivo PRÓPRIO, no app que tem o modelo -- mesma convenção de
`letters/backoffice_views.py` e `doctemplates/library_views.py`: a view
mora junto do que ela lê, e só a ROTA mora em
`core/backoffice_urls.py`.

DUAS PERMISSÕES
---------------
`core.access_backoffice` abre a área administrativa;
`accounts.manage_users` abre ESTA seção. São decisões separadas: quem
supervisiona cartas ou edita modelos não passa a mexer em quem pode o
quê por causa disso.

A permissão `accounts.manage_users` já existia no `Meta` do `User`
(migration `accounts.0002`) sem nunca ser exigida em lugar nenhum. Esta
etapa lhe dá a função para a qual foi criada, em vez de inventar uma
segunda.

O QUE ESTA TELA NÃO FAZ
-----------------------
Não troca senha, não apaga ninguém e não cria usuário. Senha é assunto
do dono da conta (`accounts:profile`); apagar destruiria o histórico de
cartas, que é justamente o que o produto existe para guardar --
desativar resolve o caso real sem perder nada.

AS TRÊS TRAVAS DE SEGURANÇA
---------------------------
1. NINGUÉM CONCEDE O QUE NÃO TEM. O formulário é montado apenas com as
   permissões que o operador possui (`admin_permissions.concediveis_por`),
   então um POST forjado com as outras simplesmente não as alcança --
   não há campo para elas.
2. NINGUÉM SE TRANCA PARA FORA. Retirar de si mesmo uma permissão
   marcada como `tranca_a_porta`, ou desativar a própria conta, é
   recusado com uma explicação.
3. SUPERUSUÁRIO SÓ É MEXIDO POR SUPERUSUÁRIO. Um superusuário tem todas
   as permissões implicitamente: marcar caixas nele não significaria
   nada, e desativá-lo seria uma porta de negação de serviço.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts import admin_permissions
from apps.core.views import BACKOFFICE_PERM, backoffice_required
from apps.letters.lifecycle import SUPERVISION_PERM

# A permissão desta seção. Uma constante, e não a string solta em cada
# view e template, para o dia em que alguém procurar "quem decide isto".
GERENCIA_PERM = "accounts.manage_users"

POR_PAGINA = 25


def gerencia_de_usuarios(view):
    """
    Exige entrar no Backoffice E `accounts.manage_users`; sem isso, 403.

    A porta é no SERVIDOR: esconder o item do menu não protege nada --
    a URL continua sendo digitável.
    """

    @backoffice_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.has_perm(GERENCIA_PERM):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def _contexto_do_backoffice(titulo):
    """
    A casca da area administrativa. Sem `bo_action_*` de proposito:
    estas telas nao tem uma acao unica de cabecalho, e o botao do
    celular so aparece quando ha uma de verdade (ver
    `backoffice/base.html`).
    """
    return {
        "active": "users",
        "bo_title": titulo,
    }


# ---------------------------------------------------------------------------
# Listagem
# ---------------------------------------------------------------------------


@gerencia_de_usuarios
def backoffice_users(request):
    """
    As pessoas cadastradas, com o que cada uma pode fazer.

    Busca por nome ou e-mail (`q`) e filtro por situação (`status`).
    Nenhum dado sensível: a senha é um hash que nem aparece na consulta,
    e documento/endereço não têm por que estar numa listagem.
    """
    User = get_user_model()
    pessoas = User.objects.annotate(cartas=Count("letters")).order_by("full_name", "email")

    busca = (request.GET.get("q") or "").strip()
    if busca:
        pessoas = pessoas.filter(Q(full_name__icontains=busca) | Q(email__icontains=busca))

    situacao = request.GET.get("status") or ""
    if situacao in ("ativos", "inativos"):
        pessoas = pessoas.filter(is_active=(situacao == "ativos"))

    pagina = Paginator(pessoas, POR_PAGINA).get_page(request.GET.get("page"))

    # A querystring sem o `page`, para os links não acumularem o
    # parâmetro a cada clique.
    querystring = request.GET.copy()
    querystring.pop("page", None)

    contexto = _contexto_do_backoffice(_("Usuários"))
    contexto.update(
        {
            "pagina": pagina,
            "querystring": querystring.urlencode(),
            "pessoas": [_resumo(pessoa) for pessoa in pagina.object_list],
            "total": pagina.paginator.count,
            "filtros": {"q": busca, "status": situacao},
        }
    )
    return render(request, "backoffice/users.html", contexto)


def _resumo(pessoa):
    """
    O que a LISTAGEM mostra de cada pessoa.

    As duas permissões em destaque são resolvidas aqui, uma vez por
    linha, em vez de no template: `{% if %}` não deve consultar
    permissão de terceiro -- `perms` no template é sempre o de quem está
    logado, e usá-lo aqui mostraria a resposta errada.

    As chaves vêm das CONSTANTES de quem as define (`core.views` e
    `letters.lifecycle`), nunca de uma string repetida aqui: cada
    permissão tem um dono só, e uma segunda cópia é uma segunda
    decisão esperando para divergir.
    """
    return {
        "pessoa": pessoa,
        "acessa_backoffice": pessoa.has_perm(BACKOFFICE_PERM),
        "ve_todas_as_cartas": pessoa.has_perm(SUPERVISION_PERM),
        "cartas": pessoa.cartas,
    }


# ---------------------------------------------------------------------------
# Detalhe
# ---------------------------------------------------------------------------


@gerencia_de_usuarios
def backoffice_user_detail(request, pk):
    """
    Uma pessoa: seus dados, sua situação e o que ela pode fazer.

    O formulário de permissões traz SÓ as que o operador pode conceder
    -- as demais aparecem como informação, marcadas e travadas, para a
    tela não mentir sobre o que a pessoa tem.
    """
    User = get_user_model()
    alvo = get_object_or_404(User.objects.annotate(cartas=Count("letters")), pk=pk)

    contexto = _contexto_do_backoffice(_("Usuário"))
    contexto.update(
        {
            "alvo": alvo,
            "grupos": _grupos_para_a_tela(request.user, alvo),
            "pode_mexer": _pode_mexer_em(request.user, alvo),
            "e_voce_mesmo": alvo.pk == request.user.pk,
            "cartas": alvo.cartas,
            "ultimas_cartas": alvo.letters.order_by("-created_at")[:5],
        }
    )
    return render(request, "backoffice/user_detail.html", contexto)


def _grupos_para_a_tela(operador, alvo):
    """
    O catálogo pronto para exibir: cada permissão com o estado do ALVO e
    se o OPERADOR pode mexer nela.
    """
    concediveis = {p.chave for p in admin_permissions.concediveis_por(operador)}
    grupos = []
    for grupo in admin_permissions.CATALOGO:
        itens = [
            {
                "permissao": permissao,
                "marcada": alvo.has_perm(permissao.chave),
                "editavel": permissao.chave in concediveis,
            }
            for permissao in grupo.permissoes
        ]
        grupos.append({"titulo": grupo.titulo, "itens": itens})
    return grupos


def _pode_mexer_em(operador, alvo):
    """
    Superusuário só é alterado por superusuário.

    Ele já tem todas as permissões implicitamente (`has_perm` devolve
    True para tudo), então marcar caixas nele não mudaria nada -- e
    desativá-lo seria uma porta de negação de serviço aberta a quem tem
    apenas `manage_users`.
    """
    if alvo.is_superuser and not operador.is_superuser:
        return False
    return True


# ---------------------------------------------------------------------------
# Alterações (sempre POST)
# ---------------------------------------------------------------------------


@gerencia_de_usuarios
@require_POST
def backoffice_user_permissions(request, pk):
    """
    Grava as permissões administrativas de uma pessoa.

    POST obrigatório (`require_POST`): um GET não altera nada, e o CSRF
    do Django cobre o envio. O conjunto de permissões que este operador
    pode mexer é recalculado AQUI, no servidor -- o que veio do
    navegador é só a lista de marcadas.
    """
    User = get_user_model()
    alvo = get_object_or_404(User, pk=pk)

    if not _pode_mexer_em(request.user, alvo):
        raise PermissionDenied

    concediveis = admin_permissions.concediveis_por(request.user)
    marcadas = set(request.POST.getlist("permissoes"))

    recusadas = []
    aplicadas = []
    for permissao in concediveis:
        quer_marcar = permissao.chave in marcadas
        tem_agora = _tem_diretamente(alvo, permissao)
        if quer_marcar == tem_agora:
            continue

        # Trava 2: ninguém se tranca para fora.
        if not quer_marcar and alvo.pk == request.user.pk and permissao.tranca_a_porta:
            recusadas.append(permissao)
            continue

        aplicadas.append((permissao, quer_marcar))

    for permissao, conceder in aplicadas:
        objeto = _permissao_do_banco(permissao)
        if conceder:
            alvo.user_permissions.add(objeto)
        else:
            alvo.user_permissions.remove(objeto)

    if recusadas:
        messages.error(
            request,
            _(
                "Você não pode retirar de si mesmo: %(itens)s. "
                "Peça a outra pessoa com acesso administrativo."
            )
            % {"itens": ", ".join(str(p.rotulo) for p in recusadas)},
        )
    if aplicadas:
        messages.success(request, _("Permissões atualizadas."))
    elif not recusadas:
        messages.info(request, _("Nenhuma alteração a fazer."))

    return redirect("backoffice:user_detail", pk=alvo.pk)


def _tem_diretamente(alvo, permissao):
    """
    A pessoa tem esta permissão ATRIBUÍDA a ela (direta ou por grupo)?

    Diferente de `has_perm`, que devolve True para todo superusuário --
    usar `has_perm` aqui faria a tela achar que precisa "retirar" uma
    permissão que o superusuário nunca teve atribuída, e a remoção não
    faria efeito nenhum.
    """
    if alvo.is_superuser:
        return True
    return alvo.user_permissions.filter(
        codename=permissao.codename, content_type__app_label=permissao.app_label
    ).exists() or alvo.groups.filter(
        permissions__codename=permissao.codename,
        permissions__content_type__app_label=permissao.app_label,
    ).exists()


def _permissao_do_banco(permissao):
    """A linha de `auth.Permission` correspondente à entrada do catálogo."""
    try:
        return Permission.objects.get(
            codename=permissao.codename, content_type__app_label=permissao.app_label
        )
    except Permission.DoesNotExist as erro:
        # Catálogo apontando para permissão inexistente é erro de
        # programação (ou migration não aplicada), não entrada do usuário.
        raise Http404("Permissão desconhecida.") from erro


@gerencia_de_usuarios
@require_POST
def backoffice_user_activation(request, pk):
    """
    Ativa ou desativa uma pessoa. NUNCA apaga.

    Desativada, ela não consegue mais autenticar (o `ModelBackend` do
    Django recusa `is_active=False`), mas as cartas e todo o histórico
    ficam intactos -- é justamente o que o produto existe para guardar.
    """
    User = get_user_model()
    alvo = get_object_or_404(User, pk=pk)

    if not _pode_mexer_em(request.user, alvo):
        raise PermissionDenied

    ativar = request.POST.get("ativo") == "1"

    if not ativar and alvo.pk == request.user.pk:
        messages.error(
            request,
            _("Você não pode desativar a sua própria conta."),
        )
        return redirect("backoffice:user_detail", pk=alvo.pk)

    if alvo.is_active != ativar:
        alvo.is_active = ativar
        alvo.save(update_fields=["is_active"])
        messages.success(
            request,
            _("Usuário ativado.") if ativar else _("Usuário desativado."),
        )
    else:
        messages.info(request, _("Nenhuma alteração a fazer."))

    return redirect("backoffice:user_detail", pk=alvo.pk)
