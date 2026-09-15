"""
As configurações globais do site, disponíveis em todo template.

O QUE ESTE MÓDULO RESOLVE
-------------------------
`content.SiteSettings` existe desde a primeira migration do app e nunca
foi lido por nada. Aqui está a ponte: um único ponto por onde a
configuração chega aos templates, em vez de cada view lembrar de passá-la
(e uma esquecer).

O QUE ELE EXPÕE, E POR QUE SÓ ISSO
----------------------------------
A identidade global do site: nome, logo, favicon, as duas cores do
tema e -- desde a etapa do Sistema -- contato e redes sociais. Nada
mais, e não por preguiça: o que um template alcança é o que alguém pode
publicar sem pensar. Cada campo entra junto com a tela que o apresenta,
de propósito. Textos legais continuam de fora: não há tela nem página
que os mostre.

O QUE VAI PARA DENTRO DE UM ATRIBUTO É VALIDADO AQUI, DE NOVO
-------------------------------------------------------------
`SiteSettings.clean()` já protege o formulário, mas `clean()` só roda em
`full_clean()` -- um `save()` programático, um `update()` cru ou uma
linha escrita por fora passam por cima. E dois destes valores não são
texto na página: são ATRIBUTO.

  * as cores entram num `<style>`, onde um `}` fecharia a regra e o
    resto viraria CSS;
  * as URLs das redes entram num `href`, onde `javascript:` é execução
    de código no navegador de quem visita.

O autoescape do template não protege nenhum dos dois casos. Por isso o
valor é conferido no caminho de SAÍDA: cor que não for `#rrggbb` cai no
padrão do modelo, e rede desconhecida ou URL que não seja http(s)
simplesmente não chega à página.

O objeto exposto NÃO é o `SiteSettings`: é um retrato imutável com
esses campos. Passar o modelo inteiro deixaria qualquer template chegar a
qualquer coluna -- inclusive as que ainda não têm tela, ou as que um dia
guardem algo que não deve aparecer numa página pública.

PREGUIÇOSO DE PROPÓSITO
-----------------------
`SimpleLazyObject`: a consulta só acontece se algum template tocar em
`site`. Páginas que não usam nada disto -- o assistente, o Backoffice, as
telas de autenticação -- não pagam uma consulta a mais por causa desta
ponte.

NÃO ESCREVE NO BANCO
--------------------
Sem registro, devolve os padrões do próprio modelo, sem gravar nada. Os
outros singletons do projeto (`SiteSettings.load()`,
`lifecycle.policy()`, `mail.configuracao()`) usam `get_or_create`, e está
certo: são chamados de telas administrativas, onde escrever é esperado.
Aqui não -- isto roda em toda página pública, inclusive num GET anônimo,
e um GET não cria linha em banco.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.utils.functional import SimpleLazyObject

from .models import (
    HEX_COLOR_VALIDATOR,
    REDES_SOCIAIS,
    URL_SOCIAL_VALIDATOR,
    Asset,
    SiteSettings,
)


@dataclass(frozen=True)
class Contato:
    """Como falar com o site. Vazio significa "não configurado"."""

    email: str
    phone: str
    address: str

    def __bool__(self):
        """Há algum meio de contato? O rodapé pergunta isso."""
        return bool(self.email or self.phone or self.address)


@dataclass(frozen=True)
class RedeSocial:
    """Uma rede configurada, já com o rótulo e o ícone que a desenham."""

    chave: str
    nome: str
    icone: str
    url: str


@dataclass(frozen=True)
class GlobaisDoSite:
    """
    O retrato da configuração que os templates enxergam.

    Cresce por etapa, um campo de cada vez, junto com a tela que o
    apresenta -- nunca "por precaução".
    """

    name: str
    logo: Asset | None
    favicon: Asset | None
    primary_color: str
    success_color: str
    contact: Contato
    social: tuple


def _cor(valor, campo):
    """
    A cor, se for um `#rrggbb` de verdade; senão, o padrão do modelo.

    Não levanta: uma cor inválida no banco não pode derrubar todas as
    páginas do site. Ela simplesmente não é usada.
    """
    padrao = SiteSettings._meta.get_field(campo).default
    if not isinstance(valor, str):
        return padrao
    try:
        HEX_COLOR_VALIDATOR(valor)
    except ValidationError:
        return padrao
    return valor


def _redes(valor):
    """
    As redes configuradas, na ordem declarada em `REDES_SOCIAIS`.

    Fora ficam, em silêncio: rede que ninguém declarou (não há rótulo
    nem ícone para ela), valor vazio (não configurada) e URL que não
    seja http(s). Não levanta -- uma linha estranha no banco não pode
    derrubar todas as páginas do site; ela simplesmente não é desenhada.
    """
    if not isinstance(valor, dict):
        return ()

    configuradas = []
    for chave, nome, icone in REDES_SOCIAIS:
        url = valor.get(chave)
        if not isinstance(url, str) or not url:
            continue
        try:
            URL_SOCIAL_VALIDATOR(url)
        except ValidationError:
            continue
        configuradas.append(RedeSocial(chave=chave, nome=str(nome), icone=icone, url=url))
    return tuple(configuradas)


def globais():
    """
    Lê a configuração vigente. Sem registro, os padrões do modelo.

    `select_related` porque logo e favicon são FK: sem ele, um template
    que mostrasse os dois custaria três consultas em vez de uma.
    """
    registro = (
        SiteSettings.objects.select_related("logo", "favicon")
        .filter(pk=SiteSettings.SINGLETON_ID)
        .first()
    )
    if registro is None:
        # Instância NÃO salva: carrega os padrões declarados no modelo
        # (`site_name="Desenrola"`, cores do tema, logo e favicon nulos)
        # sem tocar no banco. É o mesmo que o administrador veria ao
        # abrir a tela pela primeira vez.
        registro = SiteSettings()

    return GlobaisDoSite(
        name=registro.site_name,
        logo=registro.logo,
        favicon=registro.favicon,
        primary_color=_cor(registro.theme_primary_color, "theme_primary_color"),
        success_color=_cor(registro.theme_success_color, "theme_success_color"),
        contact=Contato(
            email=registro.contact_email or "",
            phone=registro.contact_phone or "",
            address=registro.contact_address or "",
        ),
        social=_redes(registro.social_links),
    )


def site(request):
    """
    O processador de contexto. Registrado em `config.settings.base`.

    A chave e `site_config`, e NAO `site`: o `LoginView` e o `LogoutView`
    do Django poem um `site` proprio no contexto (o `django.contrib.sites`
    ou um `RequestSite`), e a chave da view vence a do processador. Com o
    nome `site`, a tela de entrar recebia o objeto do Django e as cores
    saiam vazias -- em silencio, que e o pior jeito de quebrar.
    """
    return {"site_config": SimpleLazyObject(globais)}
