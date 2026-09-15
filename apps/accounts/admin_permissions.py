"""
As permissões que o Backoffice administra -- e só elas.

O Django cria dezenas de permissões automáticas (`add_`, `change_`,
`delete_`, `view_` de cada modelo). A imensa maioria não significa nada
para quem administra o produto: nada no código as consulta, e marcá-las
não mudaria coisa alguma. Uma tela que listasse todas seria um CRUD de
`auth_permission` disfarçado -- barulho, e a ilusão de que marcar uma
caixa faz alguma coisa.

Este catálogo é a lista curta do que o produto REALMENTE verifica.

COMO ACRESCENTAR UMA PERMISSÃO AQUI
-----------------------------------
Só entra o que já é conferido em algum lugar do código. O caminho é:
criar a permissão no `Meta.permissions` do modelo a que ela pertence,
passar a exigi-la numa view/serviço, e SÓ ENTÃO listá-la aqui com um
rótulo em português. Assim a tela nunca oferece um controle que não
controla nada.

Cada entrada guarda também ONDE a permissão é exigida -- é o que permite
conferir, numa leitura só, que este catálogo não descolou do código.
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class PermissaoAdministrativa:
    """Uma permissão que o Backoffice sabe conceder e retirar."""

    # "app_label.codename" -- a mesma string que `user.has_perm()` recebe.
    chave: str
    rotulo: str
    descricao: str
    # Onde ela é exigida de verdade. Documentação, não código.
    aplicada_em: str
    # Retirá-la de si mesmo tranca a pessoa para fora da administração?
    tranca_a_porta: bool = False

    @property
    def app_label(self):
        return self.chave.split(".", 1)[0]

    @property
    def codename(self):
        return self.chave.split(".", 1)[1]

    @property
    def campo(self):
        """O nome do campo no formulário -- o ponto não serve em HTML."""
        return self.chave.replace(".", "__")


@dataclass(frozen=True)
class GrupoDePermissoes:
    """Um punhado de permissões sob um título que uma pessoa entende."""

    titulo: str
    permissoes: tuple


CATALOGO = (
    GrupoDePermissoes(
        titulo=_("Acesso administrativo"),
        permissoes=(
            PermissaoAdministrativa(
                chave="core.access_backoffice",
                rotulo=_("Acessar o Backoffice"),
                descricao=_("Entra na área administrativa e vê o atalho para ela no painel."),
                aplicada_em="core.views.backoffice_required",
                tranca_a_porta=True,
            ),
            PermissaoAdministrativa(
                chave="accounts.manage_users",
                rotulo=_("Gerenciar usuários"),
                descricao=_("Vê esta tela, altera permissões e ativa ou desativa pessoas."),
                aplicada_em="accounts.backoffice_views.gerencia_de_usuarios",
                tranca_a_porta=True,
            ),
        ),
    ),
    GrupoDePermissoes(
        titulo=_("Modelos"),
        permissoes=(
            PermissaoAdministrativa(
                chave="doctemplates.view_documenttemplate",
                rotulo=_("Ver a biblioteca de modelos"),
                descricao=_(
                    "Abre a biblioteca, o detalhe de um modelo e o editor em leitura."
                ),
                aplicada_em="doctemplates.library_views / editor_views",
            ),
            PermissaoAdministrativa(
                chave="doctemplates.change_documenttemplate",
                rotulo=_("Administrar modelos"),
                descricao=_(
                    "Duplica, ativa/desativa e salva alterações no editor estrutural."
                ),
                aplicada_em="doctemplates.library_views / editor_views",
            ),
        ),
    ),
    GrupoDePermissoes(
        titulo=_("Cartas"),
        permissoes=(
            PermissaoAdministrativa(
                chave="letters.view_all_letters",
                rotulo=_("Ver as cartas de todos os usuários"),
                descricao=_(
                    "Abre a supervisão de cartas e alcança o documento de qualquer "
                    "pessoa, inclusive de uma carta expirada."
                ),
                aplicada_em="letters.backoffice_views / letters.lifecycle.supervisiona",
            ),
            PermissaoAdministrativa(
                chave="letters.change_letterpolicy",
                rotulo=_("Alterar a política das cartas"),
                descricao=_(
                    "Muda os prazos de edição e de expiração que valem para todas "
                    "as cartas."
                ),
                aplicada_em="core.views.backoffice_letter_policy",
            ),
            PermissaoAdministrativa(
                chave="letters.change_documentlanguagesettings",
                rotulo=_("Alterar os idiomas dos documentos"),
                descricao=_(
                    "Escolhe em que idiomas é possível gerar uma carta nova e em "
                    "qual ela nasce. Não afeta o idioma da interface, que é sempre "
                    "português."
                ),
                aplicada_em="core.views.backoffice_languages",
            ),
        ),
    ),
    GrupoDePermissoes(
        titulo=_("Conteúdo do site"),
        permissoes=(
            PermissaoAdministrativa(
                chave="content.view_pagesection",
                rotulo=_("Ver o conteúdo do site"),
                descricao=_(
                    "Abre a tela de conteúdo e lê os textos da página inicial, "
                    "em qualquer idioma."
                ),
                aplicada_em="content.backoffice_views.backoffice_content",
            ),
            PermissaoAdministrativa(
                chave="content.change_pagesection",
                rotulo=_("Editar o conteúdo do site"),
                descricao=_(
                    "Altera os textos da página inicial e mostra ou oculta seções."
                ),
                aplicada_em="content.backoffice_views.backoffice_content_section / _activation",
            ),
            PermissaoAdministrativa(
                chave="content.view_partner",
                rotulo=_("Ver os parceiros"),
                descricao=_(
                    "Abre a tela de parceiros e vê quem está cadastrado, com que "
                    "imagem e quem aparece na página inicial."
                ),
                aplicada_em="content.backoffice_views.backoffice_partners / _edit",
            ),
            PermissaoAdministrativa(
                chave="content.add_partner",
                rotulo=_("Cadastrar parceiros"),
                descricao=_("Acrescenta um parceiro novo à página inicial."),
                aplicada_em="content.backoffice_views.backoffice_partner_new",
            ),
            PermissaoAdministrativa(
                chave="content.change_partner",
                rotulo=_("Editar os parceiros"),
                descricao=_(
                    "Altera os dados de um parceiro, muda a ordem em que aparecem "
                    "e mostra ou oculta cada um."
                ),
                aplicada_em=(
                    "content.backoffice_views.backoffice_partner_edit / "
                    "_activation / _move"
                ),
            ),
            PermissaoAdministrativa(
                chave="content.delete_partner",
                rotulo=_("Remover parceiros"),
                descricao=_(
                    "Apaga o cadastro de um parceiro para sempre. Para apenas "
                    "tirá-lo da página inicial, basta editar e desativar."
                ),
                aplicada_em="content.backoffice_views.backoffice_partner_delete",
            ),
        ),
    ),
    GrupoDePermissoes(
        titulo=_("Sistema"),
        permissoes=(
            PermissaoAdministrativa(
                chave="content.change_sitesettings",
                rotulo=_("Alterar as configurações do site"),
                descricao=_(
                    "Muda o nome do site, os dados de contato e as redes sociais "
                    "que aparecem no rodapé. Não é uma permissão nova: é a mesma "
                    "que a administração do Django já cobrava neste cadastro."
                ),
                aplicada_em="core.views.backoffice_system / django admin",
            ),
            PermissaoAdministrativa(
                chave="core.view_emailsettings",
                rotulo=_("Ver a configuração de e-mail"),
                descricao=_(
                    "Abre a tela de envio de e-mail e vê o servidor, a porta e o "
                    "remetente cadastrados. A senha nunca é exibida."
                ),
                aplicada_em="core.views.backoffice_email_settings",
            ),
            PermissaoAdministrativa(
                chave="core.change_emailsettings",
                rotulo=_("Configurar o envio de e-mail"),
                descricao=_(
                    "Altera o servidor SMTP e a senha, dispara mensagens de teste e "
                    "liga ou desliga o envio real do sistema."
                ),
                aplicada_em="core.views.backoffice_email_settings / _test / _activation",
            ),
        ),
    ),
)


def todas():
    """Todas as permissões do catálogo, em ordem de exibição."""
    return [permissao for grupo in CATALOGO for permissao in grupo.permissoes]


def por_chave(chave):
    """A permissão do catálogo, ou `None` se não for administrável."""
    for permissao in todas():
        if permissao.chave == chave:
            return permissao
    return None


def concediveis_por(user):
    """
    As permissões que ESTE operador pode conceder ou retirar.

    Ninguém concede o que não tem: é o que impede uma escalada de
    privilégio por dentro da própria tela. Superusuário tem todas, por
    como `has_perm` funciona, e portanto concede todas.
    """
    return [permissao for permissao in todas() if user.has_perm(permissao.chave)]


def as_que_trancam_a_porta():
    """As permissões cuja retirada deixaria a pessoa sem administração."""
    return [permissao for permissao in todas() if permissao.tranca_a_porta]
