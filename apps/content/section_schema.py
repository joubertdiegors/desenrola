"""
O que cada parte da Home é, como ela se chama para quem administra, e
quais textos ela tem.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
`PageSectionTranslation.content` é um JSON livre: o formato depende do
tipo da seção, e o modelo não impõe forma nenhuma (de propósito -- ver o
docstring de `PageSection`). Isso resolve o armazenamento e deixa duas
perguntas abertas: **o que a tela de edição deve mostrar?** e **como
essa parte da página se chama para uma pessoa que não conhece o
código?**

A resposta para a primeira não pode ser "um campo de JSON". A resposta
para a segunda não pode ser "hero".

Aqui estão as duas: por seção, o nome que um administrador entende, a
explicação do que ela controla, o grupo da página onde ela fica, e os
textos que o template de fato lê. O formulário é montado a partir daqui
(ver `forms.py`), então a tela nunca oferece um campo que a página
ignora, nem esconde um que ela mostra.

NOME TÉCNICO FICA NO CÓDIGO
---------------------------
`hero`, `trust`, `cta` continuam sendo as chaves em banco -- são
estáveis, e renomeá-las seria migração de dados sem ganho. O que NÃO
aparece é isso na tela: quem administra lê "Banner superior",
"Destaques abaixo do Banner superior", "Mini Banner".

OS GRUPOS SÃO DA TELA, NÃO DO BANCO
-----------------------------------
TOPO, MEIO e FINAL são como um administrador enxerga a página, de cima
para baixo. Não viraram tabela: a ordem real continua em
`PageSection.order`, e o grupo é só a forma de agrupar essa ordem numa
tela compreensível.

POR CHAVE, E NÃO SÓ POR TIPO
----------------------------
O `kind` diz a família da seção; a CHAVE diz exatamente o que aquele
lugar da página mostra. A Home tem duas seções `features` -- a barra de
confiança e o "Como funciona" -- e elas não têm os mesmos textos.
Declarar por `kind` obrigaria a inventar uma união dos dois.

O QUE NÃO ENTRA AQUI
--------------------
Ícone, ordem dos cartões, âncora, grade: isso é DESENHO, e mora no
template. O CMS cuida do que se escreve, não de como se desenha -- com
uma exceção explícita, os LAYOUTS do banner, que são escolha do
administrador e por isso estão declarados abaixo.
"""

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Texto:
    """Um texto simples da seção."""

    chave: str
    rotulo: str
    longo: bool = False
    ajuda: str = ""


@dataclass(frozen=True)
class Lista:
    """
    Uma lista de itens iguais dentro da seção (os cartões).

    `campos` são os textos de CADA item. A quantidade de itens não se
    edita aqui: a tela mostra os que existem no conteúdo gravado.
    """

    chave: str
    rotulo: str
    campos: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class Layout:
    """
    Uma variação visual que o administrador pode escolher para a seção.

    `campos` são os textos que AQUELE desenho usa. Trocar de desenho não
    apaga nada: o conteúdo inteiro continua gravado, e o desenho novo
    simplesmente lê os campos que lhe interessam. É o que permite
    experimentar e voltar atrás.
    """

    chave: str
    nome: str
    descricao: str
    campos: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class Bloco:
    """
    Um pedaço do rodapé que se liga, desliga e reordena.

    O CMS controla a COMPOSIÇÃO; os dados continuam vindo de onde já
    vinham. `origem` é o que a tela mostra para deixar isso claro --
    quem quiser mudar o telefone sabe onde ir.
    """

    chave: str
    nome: str
    origem: str


# Os blocos do rodapé, na ordem em que ele nasce.
BLOCOS_DO_RODAPE = (
    Bloco("marca", _("Marca"), _("Aparência (logotipo) e Sistema (nome do site)")),
    Bloco("legais", _("Links legais"), _("Páginas legais")),
    Bloco("contato", _("Contato"), _("Sistema (e-mail, telefone e endereço)")),
    Bloco("redes", _("Redes sociais"), _("Sistema (redes sociais)")),
)

ORDEM_PADRAO_DO_RODAPE = tuple(bloco.chave for bloco in BLOCOS_DO_RODAPE)


def blocos_do_rodape(conteudo):
    """
    Os blocos que o rodapé desenha, na ordem escolhida.

    Sem escolha gravada -- rodapé recém-semeado, ou conteúdo estranho no
    banco -- vale a ordem padrão com tudo ligado. Um rodapé vazio por
    acidente seria pior do que um rodapé completo.
    """
    escolhidos = (conteudo or {}).get("blocos")
    if not isinstance(escolhidos, list) or not escolhidos:
        return list(ORDEM_PADRAO_DO_RODAPE)
    conhecidos = set(ORDEM_PADRAO_DO_RODAPE)
    vistos = []
    for chave in escolhidos:
        if chave in conhecidos and chave not in vistos:
            vistos.append(chave)
    return vistos or list(ORDEM_PADRAO_DO_RODAPE)


@dataclass(frozen=True)
class Secao:
    """Uma parte da Home, do ponto de vista de quem administra."""

    chave: str
    nome: str
    descricao: str
    grupo: str
    campos: tuple = field(default_factory=tuple)
    layouts: tuple = field(default_factory=tuple)
    # A seção administra registros próprios, além de textos?
    # "parceiros" e "menu" têm tela de cadastro dentro do editor.
    cadastro: str = ""
    # A seção tem uma imagem própria (`PageSection.image`)?
    #
    # Declarado aqui, e não deduzido do desenho escolhido: o banner
    # guarda a imagem mesmo enquanto está em "Somente texto", e voltar
    # para um desenho com imagem a traz de volta inteira. Trocar de
    # desenho nunca apaga dado -- é a mesma regra dos textos.
    imagem: bool = False

    def layout_ou_padrao(self, escolhido):
        """O layout escolhido, ou o primeiro declarado."""
        for layout in self.layouts:
            if layout.chave == escolhido:
                return layout
        return self.layouts[0] if self.layouts else None


TOPO = "topo"
MEIO = "meio"
FINAL = "final"

GRUPOS = (
    (TOPO, _("Topo"), _("O que a pessoa vê primeiro, antes de rolar a página.")),
    (MEIO, _("Meio"), _("O corpo da página, onde o serviço é explicado.")),
    (FINAL, _("Final"), _("O fecho da página e o rodapé.")),
)


# ---------------------------------------------------------------------------
# Os três desenhos do Banner superior
# ---------------------------------------------------------------------------
#
# O primeiro e o que a Home ja usa -- continua disponivel, e continua
# sendo o padrao. Acrescentar um quarto e acrescentar um `Layout` aqui e
# um bloco no template; nada mais do CMS muda.

BANNER_IMAGEM_TEXTO = Layout(
    chave="imagem_texto",
    nome=_("Imagem e texto"),
    descricao=_("Texto à esquerda, imagem à direita. É o desenho atual da Home."),
    campos=(
        Texto("title", _("Título principal")),
        Texto("lead", _("Texto de apoio"), longo=True),
        Texto("cta", _("Botão")),
        Texto("login_prompt", _("Antes do link de entrar")),
        Texto("login_link", _("Texto do link de entrar")),
        Texto(
            "badge_label",
            _("Rótulo do contador"),
            longo=True,
            ajuda=_(
                "Aparece ao lado do número de cartas já geradas. "
                "A quebra de linha é respeitada."
            ),
        ),
        Texto("badge_note", _("Nota do contador")),
        Texto(
            "art_caption",
            _("Legenda da imagem"),
            ajuda=_("Texto dentro da moldura, enquanto não houver foto."),
        ),
    ),
)

BANNER_IMAGEM_COMPLETA = Layout(
    chave="imagem_completa",
    nome=_("Imagem completa"),
    descricao=_("A imagem ocupa o banner inteiro. Sem texto por cima."),
    campos=(
        Texto(
            "art_caption",
            _("Legenda da imagem"),
            ajuda=_("Texto dentro da moldura, enquanto não houver foto."),
        ),
        Texto("cta", _("Botão"), ajuda=_("Em branco, o botão não aparece.")),
    ),
)

BANNER_SOMENTE_TEXTO = Layout(
    chave="somente_texto",
    nome=_("Somente texto"),
    descricao=_("Sem imagem. Título, texto e botão, centralizados."),
    campos=(
        Texto("title", _("Título principal")),
        Texto("lead", _("Texto de apoio"), longo=True),
        Texto("cta", _("Botão")),
        Texto("login_prompt", _("Antes do link de entrar")),
        Texto("login_link", _("Texto do link de entrar")),
    ),
)


# ---------------------------------------------------------------------------
# As partes da Home
# ---------------------------------------------------------------------------

SECOES = {
    "navbar": Secao(
        chave="navbar",
        nome=_("Barra superior"),
        descricao=_(
            "O menu no alto do site: a marca, os links de navegação e os "
            "botões de entrar e criar conta."
        ),
        grupo=TOPO,
        campos=(
            Texto("login_label", _("Botão de entrar")),
            Texto("signup_label", _("Botão de criar conta")),
        ),
        cadastro="menu",
    ),
    "hero": Secao(
        chave="hero",
        nome=_("Banner superior"),
        descricao=_("A primeira área da página, com o título e a chamada principal."),
        grupo=TOPO,
        layouts=(BANNER_IMAGEM_TEXTO, BANNER_IMAGEM_COMPLETA, BANNER_SOMENTE_TEXTO),
        imagem=True,
    ),
    "trust": Secao(
        chave="trust",
        nome=_("Destaques abaixo do Banner superior"),
        descricao=_("A faixa curta logo abaixo do banner, com os pontos fortes."),
        grupo=TOPO,
        campos=(Lista("cards", _("Itens"), campos=(Texto("title", _("Texto")),)),),
    ),
    "partners": Secao(
        chave="partners",
        nome=_("Nossos Parceiros"),
        descricao=_(
            "A faixa de parceiros no meio da página. Sem nenhum cadastrado, "
            "a seção inteira não aparece."
        ),
        grupo=MEIO,
        campos=(
            Texto("title", _("Título da seção")),
            Texto("lead", _("Texto de apoio"), longo=True),
            Texto("cta", _("Botão de cada parceiro")),
        ),
        cadastro="parceiros",
    ),
    "how": Secao(
        chave="how",
        nome=_("Como funciona"),
        descricao=_("Os passos que explicam o serviço, em ordem."),
        grupo=MEIO,
        campos=(
            Texto("title", _("Título da seção")),
            Texto("lead", _("Texto de apoio"), longo=True),
            Lista(
                "cards",
                _("Passos"),
                campos=(
                    Texto("title", _("Título do passo")),
                    Texto("text", _("Descrição"), longo=True),
                ),
            ),
        ),
    ),
    "cta": Secao(
        chave="cta",
        nome=_("Mini Banner"),
        descricao=_("A faixa de chamada no fim da página, antes do rodapé."),
        grupo=FINAL,
        campos=(
            Texto("title", _("Título")),
            Texto("text", _("Texto de apoio"), longo=True),
            Texto("button", _("Botão")),
        ),
    ),
    "footer": Secao(
        chave="footer",
        nome=_("Rodapé"),
        descricao=_(
            "O fim de toda página. O nome, o contato, as redes e os links "
            "legais vêm de Sistema e das páginas legais -- aqui se controla "
            "a composição."
        ),
        grupo=FINAL,
        campos=(Texto("contato_label", _("Texto do link de contato")),),
        cadastro="rodape",
    ),
}


# Onde mora o desenho de cada parte. So o Banner tem mais de um hoje;
# o dia em que outra parte tiver, entra aqui do mesmo jeito.
PASTA_DOS_DESENHOS = "core/secoes/"


def desenho_da_secao(chave_da_secao, escolhido):
    """
    O `Layout` que aquela seção deve usar, e NUNCA `None`.

    Valor vazio, desconhecido ou estranho cai no primeiro desenho
    declarado -- que para o Banner é `imagem_texto`, o que a Home sempre
    teve. Uma página não pode quebrar porque alguém gravou um valor
    inválido na coluna.
    """
    declarada = SECOES.get(chave_da_secao)
    if declarada is None or not declarada.layouts:
        return None
    return declarada.layout_ou_padrao(escolhido)


def template_do_desenho(chave_da_secao, escolhido):
    """O template do desenho escolhido, já com a queda para o padrão."""
    desenho = desenho_da_secao(chave_da_secao, escolhido)
    if desenho is None:
        return None
    return f"{PASTA_DOS_DESENHOS}{chave_da_secao_em_arquivo(chave_da_secao)}_{desenho.chave}.html"


# O parcial de cada parte. As que tem desenho proprio (o Banner)
# resolvem por `template_do_desenho`; as demais tem um arquivo so.
PARCIAIS = {
    "navbar": "components/site_nav.html",
    "trust": "core/secoes/trust.html",
    "partners": "core/secoes/partners.html",
    "how": "core/secoes/how.html",
    "cta": "core/secoes/cta.html",
    "footer": "components/site_footer.html",
}


def parcial_da_secao(chave, desenho=""):
    """
    O template que desenha aquela parte -- o MESMO que a Home usa.

    `None` para uma chave que ninguém declarou: a prévia responde 404 em
    vez de tentar incluir um arquivo inventado.
    """
    if chave in PARCIAIS:
        return PARCIAIS[chave]
    return template_do_desenho(chave, desenho)


def chave_da_secao_em_arquivo(chave):
    """O nome que o arquivo de template usa para aquela seção."""
    return {"hero": "banner"}.get(chave, chave)


def secao_declarada(secao):
    """A declaração de `secao`: pela chave e, não achando, pelo tipo."""
    return SECOES.get(secao.key) or SECOES.get(secao.kind)


def campos_da_secao(secao):
    """
    Os campos que ESTA seção edita, já considerando o desenho escolhido.

    Tupla vazia para uma seção que ninguém declarou -- a tela avisa que
    não sabe editá-la, em vez de mostrar um JSON cru.
    """
    declarada = secao_declarada(secao)
    if declarada is None:
        return ()
    if declarada.layouts:
        layout = declarada.layout_ou_padrao(secao.layout)
        return layout.campos if layout else ()
    return declarada.campos


def editavel(secao):
    """Esta seção tem o que editar -- textos, desenho ou cadastro?"""
    declarada = secao_declarada(secao)
    if declarada is None:
        return False
    return bool(campos_da_secao(secao) or declarada.layouts or declarada.cadastro)


def nome_amigavel(secao):
    """Como esta seção se chama para quem administra."""
    declarada = secao_declarada(secao)
    return declarada.nome if declarada else (secao.key or secao.kind)


def por_grupo(secoes):
    """
    As seções agrupadas em TOPO/MEIO/FINAL, na ordem da página.

    Devolve `[(chave, nome, descricao, [secoes...]), ...]`, já sem os
    grupos vazios -- um cabeçalho de grupo sem nada embaixo seria uma
    promessa vazia.
    """
    por_chave = {}
    for secao in secoes:
        declarada = secao_declarada(secao)
        if declarada is None:
            continue
        por_chave.setdefault(declarada.grupo, []).append(secao)

    agrupadas = []
    for chave, nome, descricao in GRUPOS:
        se_houver = por_chave.get(chave)
        if se_houver:
            agrupadas.append((chave, nome, descricao, se_houver))
    return agrupadas
