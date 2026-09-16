"""
Preenche o CMS com conteúdo de DEMONSTRAÇÃO, para mostrar o produto.

    migrate
    reconstruir_modelos_oficiais
    conteudo_demonstrativo            <-- este

POR QUE UM COMANDO, E NÃO UMA MIGRATION
---------------------------------------
Migration roda em produção, sempre. Conteúdo de demonstração em
produção é pior do que nenhum: o cliente veria "Endereço de
demonstração" no rodapé do site dele. Aqui é opt-in -- roda quem quer
montar uma demonstração, e ninguém mais.

É o mesmo motivo pelo qual `reconstruir_modelos_oficiais` existe
separado do `migrate`: um passo de deploy visível vale mais do que um
efeito escondido.

O QUE ELE NÃO FAZ
-----------------
  * não apaga nada, nunca -- inclusive o que um administrador tenha
    cadastrado antes;
  * não inventa número de cartas: o contador da Home conta
    `Letter.finalized_at` de verdade e continua em zero num banco de
    demonstração;
  * não mexe em cor, logo nem favicon. O padrão do produto já é neutro
    e profissional, e não há imagem de marca para cadastrar -- sem
    logo, sai a marca desenhada, que é a identidade padrão e não um
    espaço vazio;
  * não escreve texto jurídico. As duas páginas legais recebem um aviso
    dizendo, em letras maiúsculas, que precisam ser substituídas.

IDEMPOTENTE
-----------
Roda de novo sem duplicar e sem sobrescrever o que já tem conteúdo. Quem
quiser mesmo refazer por cima passa `--forcar` -- e aí o que o
administrador escreveu se perde, o que é decisão de quem digita o
comando.

NADA REAL AQUI
--------------
Nenhum e-mail, telefone, endereço, empresa ou perfil de verdade. Os
endereços usam `exemplo.test`, um domínio reservado pela RFC 2606
justamente para isto, e o telefone é uma sequência de zeros no formato
belga. Tudo aqui existe para ser apagado pelo cliente.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.content.models import (
    ContentBlock,
    ContentTranslation,
    FaqItem,
    Partner,
    SiteSettings,
)

AVISO = (
    "CONTEÚDO DE DEMONSTRAÇÃO — SUBSTITUIR PELO TEXTO JURÍDICO "
    "DEFINITIVO ANTES DA PUBLICAÇÃO."
)

# Contato: reconhecível como demonstração à primeira vista. O domínio
# `exemplo.test` é reservado (RFC 2606) e nunca resolve.
CONTATO = {
    "contact_email": "contato@exemplo.test",
    "contact_phone": "+32 000 00 00 00",
    "contact_address": (
        "Endereço de demonstração\nRua Exemplo, 0\n1000 Bruxelas, Bélgica"
    ),
}

# As duas redes que o rodapé sabe desenhar (`content.REDES_SOCIAIS`).
REDES = {
    "facebook": "https://exemplo.test/demonstracao",
    "instagram": "https://exemplo.test/demonstracao",
}

# Nomes genéricos de propósito: descrevem o tipo de serviço, não uma
# empresa. Sem logotipo -- a tela de Parceiros mostra "Sem imagem", que
# é o estado honesto.
PARCEIROS = (
    (
        "Global Travel Services",
        "Passagens, seguro viagem e apoio na organização da estadia.",
        "https://exemplo.test/global-travel-services",
        1,
    ),
    (
        "European Welcome",
        "Acolhimento de quem chega: hospedagem, transporte e primeiros passos.",
        "https://exemplo.test/european-welcome",
        2,
    ),
    (
        "Travel Support",
        "Suporte durante a viagem, em português, do embarque ao retorno.",
        "https://exemplo.test/travel-support",
        3,
    ),
    (
        "Visa Assistance",
        "Orientação sobre documentos e acompanhamento do pedido de visto.",
        "https://exemplo.test/visa-assistance",
        4,
    ),
)

TERMOS = f"""{AVISO}

Esta página existe para receber os Termos de Uso do serviço: as regras
que valem entre quem oferece a ferramenta e quem a utiliza.

O texto definitivo deve tratar, entre outros pontos, do que o serviço
faz e do que não faz, das responsabilidades de cada lado, das condições
de uso da conta e do que acontece quando elas não são cumpridas.

Enquanto este aviso estiver aqui, a página NÃO tem valor jurídico. O
texto é escrito por quem responde legalmente pelo serviço e cadastrado
na administração do sistema, no bloco de conteúdo `legal.terms_of_use`.
"""

PRIVACIDADE = f"""{AVISO}

Esta página existe para receber a Política de Privacidade do serviço: o
que se faz com os dados de quem usa a ferramenta.

O texto definitivo deve tratar, entre outros pontos, de quais dados são
coletados, para quê, por quanto tempo ficam guardados, com quem são
compartilhados e como a pessoa exerce os direitos que a lei lhe dá.

Enquanto este aviso estiver aqui, a página NÃO tem valor jurídico. O
texto é escrito por quem responde legalmente pelo serviço e cadastrado
na administração do sistema, no bloco de conteúdo `legal.privacy_policy`.
"""


# Perguntas de demonstração. Descrevem o que o produto REALMENTE faz --
# nada de prazo, preço ou promessa que o sistema não cumpra.
PERGUNTAS = (
    (
        "O que é a Carta Convite?",
        "É o documento em que alguém que mora na Bélgica convida formalmente "
        "um visitante. Ela acompanha o pedido de visto de curta duração e "
        "descreve quem convida, quem é convidado e o período da visita.",
        1,
    ),
    (
        "Em quais idiomas a carta pode ser gerada?",
        "Nos idiomas oferecidos na etapa de idioma do assistente. A escolha "
        "muda o texto inteiro do documento, não apenas o cabeçalho.",
        2,
    ),
    (
        "Preciso assinar o documento?",
        "Sim. O sistema entrega o PDF pronto para impressão com o espaço da "
        "assinatura; assinar e apresentar o documento continua sendo com "
        "você.",
        3,
    ),
    (
        "Posso corrigir uma carta depois de gerar?",
        "Enquanto a carta está em rascunho, você volta a qualquer etapa e "
        "altera o que quiser. Depois de finalizada ela fica preservada como "
        "está -- e você pode criar uma nova a partir dela.",
        4,
    ),
    (
        "Meus dados ficam guardados?",
        "Os dados do seu perfil ficam, para você não redigitar a cada carta. "
        "Você pode alterá-los no Perfil a qualquer momento.",
        5,
    ),
)


class Command(BaseCommand):
    help = "Preenche o CMS com conteúdo de demonstração (não usar em produção)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--forcar",
            action="store_true",
            help="Sobrescreve o que já tiver conteúdo. Apaga o que foi editado.",
        )

    @transaction.atomic
    def handle(self, *args, **opcoes):
        forcar = opcoes["forcar"]

        self._identidade(forcar)
        self._parceiros()
        self._perguntas()
        self._paginas_legais(forcar)
        self._lembretes()

    # -- identidade e contato ------------------------------------------

    def _identidade(self, forcar):
        config = SiteSettings.load()
        mudou = []

        for campo, valor in CONTATO.items():
            if forcar or not getattr(config, campo):
                setattr(config, campo, valor)
                mudou.append(campo)

        if forcar or not config.social_links:
            config.social_links = dict(REDES)
            mudou.append("social_links")

        if mudou:
            config.full_clean()
            config.save()
            self._ok(f"Sistema: {', '.join(mudou)}")
        else:
            self._pular("Sistema: já preenchido")

        self._pular(
            f"Aparência: mantida ({config.theme_primary_color} / "
            f"{config.theme_success_color}, sem logo) -- o padrão já é neutro"
        )

    # -- parceiros -----------------------------------------------------

    def _parceiros(self):
        criados = 0
        for nome, descricao, endereco, ordem in PARCEIROS:
            _parceiro, criado = Partner.objects.get_or_create(
                name=nome,
                defaults={
                    "description": descricao,
                    "url": endereco,
                    "order": ordem,
                    "is_active": True,
                },
            )
            criados += int(criado)

        if criados:
            self._ok(f"Parceiros: {criados} cadastrado(s)")
        else:
            self._pular("Parceiros: os quatro já existem")

        estranhos = Partner.objects.exclude(
            name__in=[nome for nome, *_resto in PARCEIROS]
        )
        for parceiro in estranhos:
            self._aviso(
                f'Parceiro "{parceiro.name}" não veio daqui e foi mantido. '
                "Apague-o na administração do Django se não for para a demonstração."
            )

    # -- perguntas frequentes ------------------------------------------

    def _perguntas(self):
        """
        As perguntas de demonstração da Home.

        Sem nenhuma pergunta a seção não aparece -- que é o estado certo
        de uma instalação nova, e por isso a migration não semeia
        nenhuma. Aqui, onde o conteúdo É de demonstração, elas entram.
        As respostas descrevem o produto de verdade: são o texto que o
        cliente vai ajustar, não invenção sobre prazos ou preços.
        """
        criadas = 0
        for pergunta, resposta, ordem in PERGUNTAS:
            _item, criada = FaqItem.objects.get_or_create(
                question=pergunta,
                defaults={"answer": resposta, "order": ordem, "is_active": True},
            )
            criadas += int(criada)

        if criadas:
            self._ok(f"Perguntas frequentes: {criadas} cadastrada(s)")
        else:
            self._pular(f"Perguntas frequentes: as {len(PERGUNTAS)} já existem")

    # -- páginas legais ------------------------------------------------

    def _paginas_legais(self, forcar):
        for chave, texto in (
            ("legal.terms_of_use", TERMOS),
            ("legal.privacy_policy", PRIVACIDADE),
        ):
            bloco = ContentBlock.objects.filter(key=chave).first()
            if bloco is None:
                self._aviso(f"Bloco {chave} não existe. Rode `migrate` antes.")
                continue

            traducao, criada = ContentTranslation.objects.get_or_create(
                block=bloco, language="pt", defaults={"content": texto}
            )
            if criada:
                self._ok(f"{chave}: aviso de demonstração publicado")
            elif forcar or not traducao.content.strip():
                traducao.content = texto
                traducao.save()
                self._ok(f"{chave}: aviso de demonstração publicado")
            else:
                self._pular(f"{chave}: já tem texto -- não foi tocado")

    # -- o que este comando deliberadamente não faz --------------------

    def _lembretes(self):
        from apps.content.services import secoes_da_pagina

        secoes = secoes_da_pagina("home")
        if secoes:
            self._pular(
                f"Home: {len(secoes)} seções já preenchidas pela migration "
                "`content.0004` -- não foram reescritas"
            )
        else:
            self._aviso("Home sem conteúdo. Rode `migrate` antes.")

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Lembre-se: as duas páginas legais estão com AVISO DE "
                "DEMONSTRAÇÃO e não têm valor jurídico."
            )
        )

    # -- saída ---------------------------------------------------------

    def _ok(self, texto):
        self.stdout.write(self.style.SUCCESS(f"  + {texto}"))

    def _pular(self, texto):
        self.stdout.write(f"  = {texto}")

    def _aviso(self, texto):
        self.stdout.write(self.style.WARNING(f"  ! {texto}"))
