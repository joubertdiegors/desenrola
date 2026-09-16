"""
Deixa o banco como uma instalação NOVA, antes do lançamento.

    migrate
    reconstruir_modelos_oficiais
    conteudo_demonstrativo          (opcional, para demonstrar)
    preparar_para_producao          <-- este, antes de entregar

POR QUE UM COMANDO EXPLÍCITO
----------------------------
Apagar dado é a operação menos reversível que existe. Uma migration
faria isso sozinha, em toda subida, para sempre -- e um dia apagaria o
banco de alguém sem que ninguém tivesse pedido. Aqui é preciso digitar o
comando, ler o relatório e confirmar.

NÃO FAZ NADA SEM CONFIRMAÇÃO
----------------------------
Sem argumento nenhum, ele apenas RELATA o que removeria. É preciso
`--confirmar` para apagar, e aí ainda pergunta -- digitar a palavra é o
último degrau antes de uma operação sem volta.

O QUE ELE NUNCA TOCA
--------------------
  * as configurações do sistema (`SiteSettings`, `EmailSettings`,
    `LetterPolicy`, `DocumentLanguageSettings`) -- as linhas continuam
    lá, com o que estiver nelas;
  * os quatro modelos oficiais da Carta Convite;
  * as permissões e os grupos;
  * as seções e traduções da página inicial (vêm das migrations, não de
    demonstração);
  * os itens do menu (idem);
  * os superusuários.

O QUE ELE REMOVE
----------------
  * TODAS as cartas -- de teste ou não. Uma instalação nova não tem
    histórico de ninguém;
  * todos os usuários que NÃO são superusuário;
  * todos os parceiros;
  * os modelos de documento que não são oficiais (as cópias);
  * as imagens que nenhum modelo oficial e nenhuma configuração usam;
  * o conteúdo de DEMONSTRAÇÃO, e só ele: contato e redes que apontam
    para `exemplo.test`, e os textos legais que ainda carregam o aviso
    de "SUBSTITUIR". Contato de verdade e texto jurídico de verdade
    ficam onde estão -- o comando sabe distinguir porque a demonstração
    se identifica (o domínio `exemplo.test` é reservado pela RFC 2606 e
    nunca resolve).

POR QUE APAGAR CARTAS DE TODO MUNDO
-----------------------------------
Porque "instalação nova" quer dizer isso. Um banco entregue ao cliente
com a carta de um testador dentro é vazamento de dado pessoal, não
conveniência. Quem quiser preservar histórico não deve rodar este
comando.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

# O domínio que a demonstração usa. Reservado pela RFC 2606: nunca
# resolve, e por isso é reconhecível à primeira vista.
DOMINIO_DE_DEMONSTRACAO = "exemplo.test"

# A primeira linha do aviso que o comando de demonstração põe nas
# páginas legais. Enquanto ela estiver lá, o texto não é jurídico.
MARCA_DO_AVISO = "SUBSTITUIR"

PALAVRA_DE_CONFIRMACAO = "PREPARAR"


class Command(BaseCommand):
    help = (
        "Deixa o banco como uma instalação nova: apaga cartas, usuários não "
        "superusuários, parceiros, cópias de modelos e o conteúdo de demonstração. "
        "Sem --confirmar, apenas relata."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Executa de verdade. Sem isto, o comando apenas relata.",
        )
        parser.add_argument(
            "--nao-perguntar",
            action="store_true",
            help=(
                "Não pede a palavra de confirmação. Só para execução automatizada; "
                "à mão, prefira responder à pergunta."
            ),
        )

    def handle(self, *args, **opcoes):
        plano = self._levantar()
        self._relatar(plano)

        if not opcoes["confirmar"]:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Nada foi apagado. Para executar de verdade, repita com "
                    "--confirmar."
                )
            )
            return

        if not opcoes["nao_perguntar"]:
            self.stdout.write("")
            resposta = input(
                f"Isto NÃO tem volta. Digite {PALAVRA_DE_CONFIRMACAO} para continuar: "
            )
            if resposta.strip() != PALAVRA_DE_CONFIRMACAO:
                raise CommandError("Cancelado: a palavra de confirmação não confere.")

        self._executar(plano)

    # -- levantamento -------------------------------------------------------

    def _levantar(self):
        """
        O que seria removido -- SEM remover nada.

        O mesmo levantamento alimenta o relatório e a execução, para não
        haver o risco clássico de o relatório dizer uma coisa e a
        execução fazer outra.
        """
        from apps.content.models import Asset, ContentTranslation, Partner, SiteSettings
        from apps.doctemplates.models import DocumentTemplate
        from apps.letters.models import Letter

        oficiais = DocumentTemplate.objects.filter(is_system=True)
        config = SiteSettings.objects.filter(pk=SiteSettings.SINGLETON_ID).first()

        # As imagens que precisam ficar: as que um modelo oficial usa
        # (o banco recusaria apagar, por PROTECT) e as da identidade do
        # site. Uma logomarca de verdade não é dado de teste.
        protegidas = set(
            Asset.objects.filter(template_references__template__in=oficiais)
            .values_list("pk", flat=True)
        )
        if config:
            protegidas |= {pk for pk in (config.logo_id, config.favicon_id) if pk}

        return {
            "cartas": Letter.objects.all(),
            "usuarios": get_user_model().objects.filter(is_superuser=False),
            "parceiros": Partner.objects.all(),
            "copias": DocumentTemplate.objects.filter(is_system=False),
            "imagens": Asset.objects.exclude(pk__in=protegidas),
            "legais_de_demonstracao": ContentTranslation.objects.filter(
                block__key__startswith="legal.", content__contains=MARCA_DO_AVISO
            ),
            "contato_de_demonstracao": self._contato_e_de_demonstracao(config),
            "config": config,
        }

    def _contato_e_de_demonstracao(self, config):
        """
        O contato gravado aponta para o domínio de demonstração?

        Só então ele é limpo. Um contato de verdade -- que é o que o
        cliente cadastra -- fica onde está: apagá-lo tiraria o rodapé do
        ar sem ninguém ter pedido.
        """
        if config is None:
            return False
        campos = (config.contact_email or "", config.contact_address or "")
        redes = " ".join(str(v) for v in (config.social_links or {}).values())
        return any(DOMINIO_DE_DEMONSTRACAO in valor for valor in (*campos, redes))

    # -- relatório ----------------------------------------------------------

    def _relatar(self, plano):
        self.stdout.write(self.style.MIGRATE_HEADING("Seria removido:"))
        for rotulo, chave in (
            ("cartas (de todo mundo)", "cartas"),
            ("usuários não superusuários", "usuarios"),
            ("parceiros", "parceiros"),
            ("cópias de modelos", "copias"),
            ("imagens sem uso oficial", "imagens"),
            ("textos legais de demonstração", "legais_de_demonstracao"),
        ):
            self.stdout.write(f"  {plano[chave].count():>5}  {rotulo}")

        contato = "sim" if plano["contato_de_demonstracao"] else "não"
        self.stdout.write(f"  {contato:>5}  contato/redes de demonstração")

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Fica intacto:"))
        from apps.doctemplates.models import DocumentTemplate

        self.stdout.write(
            f"  {DocumentTemplate.objects.filter(is_system=True).count():>5}  "
            "modelos oficiais"
        )
        self.stdout.write(
            f"  {get_user_model().objects.filter(is_superuser=True).count():>5}  "
            "superusuários"
        )
        self.stdout.write(
            "        configurações do sistema, permissões, conteúdo da página "
            "inicial e itens do menu"
        )

    # -- execução -----------------------------------------------------------

    @transaction.atomic
    def _executar(self, plano):
        """
        Tudo numa transação: ou o banco fica limpo, ou fica como estava.
        Uma limpeza pela metade seria o pior dos dois mundos.

        A ORDEM IMPORTA: as cartas primeiro, porque são elas que
        seguram imagens por PROTECT. Com elas fora, a imagem pode sair.
        """
        apagadas = plano["cartas"].count()
        plano["cartas"].delete()

        usuarios = plano["usuarios"].count()
        plano["usuarios"].delete()

        parceiros = plano["parceiros"].count()
        plano["parceiros"].delete()

        copias = plano["copias"].count()
        plano["copias"].delete()

        # `plano["imagens"]` é uma queryset PREGUIÇOSA: ao ser percorrida
        # agora, as cópias de modelos já foram apagadas, então uma imagem
        # que só elas seguravam já está livre. O conjunto protegido
        # (modelos oficiais e identidade do site) não muda no meio do
        # caminho.
        #
        # Nada de excluir de novo aqui: uma segunda regra faria o
        # relatório poder dizer uma coisa e a execução fazer outra -- que
        # é exatamente o que este comando promete não fazer.
        quantas = plano["imagens"].count()
        plano["imagens"].delete()

        legais = plano["legais_de_demonstracao"].count()
        plano["legais_de_demonstracao"].delete()

        config = plano["config"]
        if config and plano["contato_de_demonstracao"]:
            config.contact_email = ""
            config.contact_phone = ""
            config.contact_address = ""
            config.social_links = {}
            config.save()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Pronto. O banco está como uma instalação nova."))
        self.stdout.write(
            f"  removidos: {apagadas} cartas, {usuarios} usuários, {parceiros} "
            f"parceiros, {copias} cópias de modelos, {quantas} imagens, "
            f"{legais} textos legais de demonstração"
        )
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Falta o que só uma pessoa pode fazer: cadastrar o contato real, "
                "escrever os textos legais e conferir a configuração de e-mail."
            )
        )
