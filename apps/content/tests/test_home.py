"""
A Home passa a ser alimentada por dados reais.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. que os dados inventados voltem. A Home tinha quatro parceiros fixos
   no código e o número "12.458" escrito à mão; os dois viraram cadastro
   e contagem de verdade, e há testes que afirmam a ausência dos nomes
   antigos;
2. que o contador passe a contar outra coisa. `finalized_at` é o marco
   de emissão -- `status` muda depois e `generated_at` é reescrito;
3. que um parceiro a mais custe uma consulta a mais;
4. que a Home quebre com o banco vazio. Instalação nova, sem parceiro e
   sem carta, tem de abrir.
"""

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.content import services
from apps.content.models import Asset, Page, PageSection, PageSectionTranslation, Partner
from apps.doctemplates.models import DocumentTemplate
from apps.letters import statistics
from apps.letters.models import Letter

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")


def _gif():
    return SimpleUploadedFile(
        "x.gif",
        b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
        b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
        content_type="image/gif",
    )


def criar_parceiro(nome, **campos):
    return Partner.objects.create(name=nome, **campos)


def carta(user, *, finalizada=True, status=Letter.Status.GENERATED):
    """
    Uma carta mínima. Não passa pelo assistente de propósito: o contador
    olha uma coluna só, e montar seis etapas para testá-lo esconderia o
    que está sendo medido.
    """
    return Letter.objects.create(
        user=user,
        document_template=DocumentTemplate.objects.get(slug="carta-convite-fr"),
        language="fr",
        status=status,
        finalized_at=timezone.now() if finalizada else None,
    )


# ===========================================================================
# 1. O modelo Partner
# ===========================================================================


class TestPartner:
    def test_nasce_ativo_e_no_comeco_da_fila(self):
        parceiro = criar_parceiro("JD-Print")

        assert parceiro.is_active is True
        assert parceiro.order == 0
        assert str(parceiro) == "JD-Print"

    def test_logo_url_e_descricao_sao_opcionais(self):
        """
        Um parceiro recém-cadastrado, só com o nome, não pode derrubar a
        Home enquanto a imagem não chega.
        """
        parceiro = criar_parceiro("Sem Nada")

        assert parceiro.logo is None
        assert parceiro.url == ""
        assert parceiro.description == ""

    def test_o_logo_e_um_asset(self):
        """Nenhum sistema paralelo de upload: a imagem é `content.Asset`."""
        imagem = Asset.objects.create(key="p", kind=Asset.Kind.PARTNER, file=_gif())

        parceiro = criar_parceiro("Com Logo", logo=imagem)

        assert parceiro.logo == imagem
        assert imagem.partners.get() == parceiro

    def test_apagar_o_asset_nao_apaga_o_parceiro(self):
        """`SET_NULL`: some a imagem, fica o parceiro."""
        imagem = Asset.objects.create(key="p", kind=Asset.Kind.PARTNER, file=_gif())
        parceiro = criar_parceiro("Com Logo", logo=imagem)

        imagem.delete()
        parceiro.refresh_from_db()

        assert parceiro.logo is None

    def test_a_ordem_manda_e_o_pk_desempata(self):
        primeiro = criar_parceiro("A", order=2)
        segundo = criar_parceiro("B", order=1)
        terceiro = criar_parceiro("C", order=1)

        assert list(Partner.objects.all()) == [segundo, terceiro, primeiro]

    def test_publicados_traz_so_os_ativos(self):
        ativo = criar_parceiro("Ativo")
        criar_parceiro("Inativo", is_active=False)

        assert list(Partner.objects.publicados()) == [ativo]

    def test_apagar_parceiro_e_possivel_desde_a_central_de_conteudo(self):
        """
        Até a Etapa 11 parceiro só se desativava, e a permissão de apagar
        nem existia. A Central de Conteúdo passou a permitir remover o
        que entrou errado -- desativar continua sendo o caminho
        recomendado para quem só quer tirar da Home.
        """
        codenames = {
            f"{acao}_partner" for acao in Partner._meta.default_permissions
        }

        assert codenames == {
            "add_partner",
            "change_partner",
            "delete_partner",
            "view_partner",
        }

    def test_o_admin_nao_oferece_exclusao(self, rf):
        from apps.content.admin import PartnerAdmin

        assert PartnerAdmin.has_delete_permission(None, rf.get("/")) is False


# ===========================================================================
# 2. Os parceiros na Home
# ===========================================================================


class TestParceirosNaHome:
    def test_o_parceiro_ativo_aparece(self, client):
        """
        Desde o Bloco B o cartão mostra só imagem e botão -- o nome
        continua saindo no `aria-label` do link inteiro, mas a
        descrição não é mais desenhada em lugar nenhum (ver
        `test_parceiros_carrossel_e_botao.py`).
        """
        criar_parceiro("JD-Print", description="Impressões 3D sob medida.")

        html = client.get(HOME).content.decode()

        assert "JD-Print" in html
        assert "Nossos parceiros" in html

    def test_o_inativo_nao_aparece(self, client):
        criar_parceiro("Visível")
        criar_parceiro("Escondido", is_active=False)

        html = client.get(HOME).content.decode()

        assert "Visível" in html
        assert "Escondido" not in html

    def test_a_ordem_do_cadastro_e_a_ordem_da_pagina(self, client):
        criar_parceiro("Terceiro", order=3)
        criar_parceiro("Primeiro", order=1)
        criar_parceiro("Segundo", order=2)

        html = client.get(HOME).content.decode()

        assert html.index("Primeiro") < html.index("Segundo") < html.index("Terceiro")

    def test_sem_parceiros_a_secao_inteira_some(self, client):
        html = client.get(HOME).content.decode()

        assert 'id="parceiros"' not in html
        assert "Nossos parceiros" not in html

    def test_e_o_item_do_menu_some_junto(self, client):
        """Âncora que não existe mais não pode continuar no menu."""
        sem = client.get(HOME).content.decode()
        criar_parceiro("JD-Print")
        com = client.get(HOME).content.decode()

        assert 'href="#parceiros"' not in sem
        assert 'href="#parceiros"' in com

    def test_com_endereco_o_cartao_e_um_link(self, client):
        criar_parceiro("Com Link", url="https://exemplo.com")

        html = client.get(HOME).content.decode()

        assert 'href="https://exemplo.com"' in html
        assert 'rel="noopener"' in html

    def test_sem_endereco_o_cartao_nao_e_clicavel(self, client):
        """Melhor um cartão parado do que um link que não leva a lugar nenhum."""
        criar_parceiro("Sem Link")

        html = client.get(HOME).content.decode()
        inicio = html.index("Sem Link")
        cartao = html[max(0, inicio - 600) : inicio]

        assert 'href="#"' not in cartao

    def test_com_logo_sai_a_imagem_de_verdade(self, client):
        imagem = Asset.objects.create(key="p", kind=Asset.Kind.PARTNER, file=_gif())
        criar_parceiro("Com Logo", logo=imagem)

        html = client.get(HOME).content.decode()

        assert f'src="{imagem.file.url}"' in html
        assert "<img class=\"partner-image\"" in html

    def test_sem_logo_fica_a_moldura(self, client):
        criar_parceiro("Sem Logo")

        html = client.get(HOME).content.decode()

        assert "img-slot partner-image" in html

    def test_os_nomes_inventados_sumiram_do_codigo(self):
        """
        `demo.PARTNERS` trazia "JD-Print" e "Confiar Viagens" escritos no
        código. Parceiro agora é cadastro -- e ninguém semeia acordo
        comercial por migration.
        """
        from apps.core import demo

        assert not hasattr(demo, "PARTNERS")


# ===========================================================================
# 3. O contador
# ===========================================================================


class TestContador:
    def test_zero_quando_nao_ha_carta(self):
        assert statistics.cartas_emitidas() == 0

    def test_conta_as_finalizadas(self, user):
        carta(user)
        carta(user)

        assert statistics.cartas_emitidas() == 2

    def test_rascunho_nao_conta(self, user):
        carta(user, finalizada=False, status=Letter.Status.DRAFT)

        assert statistics.cartas_emitidas() == 0

    def test_cancelada_ja_finalizada_continua_contando(self, user):
        """
        Ela FOI emitida. Um contador de apresentação não anda para trás
        -- e é por isso que a conta olha `finalized_at`, não `status`.
        """
        carta(user, status=Letter.Status.CANCELLED)

        assert statistics.cartas_emitidas() == 1

    def test_nao_usa_generated_at(self, user):
        """
        `generated_at` é reescrito a cada reemissão; `finalized_at` é
        gravado uma vez. Uma carta com um e sem o outro prova qual conta.
        """
        uma = carta(user)
        uma.generated_at = None
        uma.save(update_fields=["generated_at"])

        assert statistics.cartas_emitidas() == 1

    def test_o_numero_aparece_na_home(self, client, user):
        carta(user)
        carta(user)

        html = client.get(HOME).content.decode()

        assert '<span class="banner-contador-valor">2</span>' in html

    def test_zero_aparece_na_home(self, client):
        html = client.get(HOME).content.decode()

        assert '<span class="banner-contador-valor">0</span>' in html

    @pytest.mark.parametrize(
        "quantas, escrito",
        [(0, "0"), (3, "3"), (999, "999"), (1000, "1.000"), (12458, "12.458")],
    )
    def test_o_numero_sai_com_separador_de_milhar(self, client, quantas, escrito):
        """
        `999` continua `999`; a partir de mil entra o ponto, que é o
        separador do português.

        O valor é posto direto no cache em vez de criar milhares de
        cartas: o que se mede aqui é a APRESENTAÇÃO do número, e a
        contagem em si já tem os seus próprios testes.
        """
        cache.set(statistics.CHAVE_DO_CACHE, quantas)

        html = client.get(HOME).content.decode()

        assert f'<span class="banner-contador-valor">{escrito}</span>' in html

    def test_o_contexto_recebe_o_numero_e_nao_o_texto(self, client, user):
        """
        A separação é de apresentação: quem calcula entrega um inteiro, e
        quem desenha decide como escrevê-lo.
        """
        carta(user)

        contexto = client.get(HOME).context

        assert contexto["cartas_emitidas"] == 1

    def test_o_rotulo_fala_de_cartas_e_nao_de_pessoas(self, client, user):
        """
        O número conta documentos. Dizer "pessoas" seria contar uma coisa
        e afirmar outra -- a mesma pessoa emite várias cartas.
        """
        html = client.get(HOME).content.decode()

        assert "cartas já geradas" in html
        assert "pessoas já utilizaram" not in html

    def test_o_valor_inventado_sumiu_do_codigo(self):
        from apps.core import demo

        assert not hasattr(demo, "LANDING_STAT")


class TestCacheDoContador:
    def test_a_segunda_leitura_nao_vai_ao_banco(
        self, user, django_assert_num_queries
    ):
        carta(user)

        with django_assert_num_queries(1):
            statistics.cartas_emitidas()
        with django_assert_num_queries(0):
            statistics.cartas_emitidas()

    def test_o_numero_guardado_e_servido_ate_expirar(self, user):
        assert statistics.cartas_emitidas() == 0

        carta(user)

        assert statistics.cartas_emitidas() == 0  # ainda o valor guardado

    def test_esquecer_a_contagem_volta_ao_banco(self, user):
        assert statistics.cartas_emitidas() == 0
        carta(user)

        statistics.esquecer_a_contagem()

        assert statistics.cartas_emitidas() == 1

    def test_zero_tambem_e_guardado(self, user, django_assert_num_queries):
        """
        `cache.get_or_set` com valor 0 é a armadilha clássica: um `if not
        valor` guardaria de novo a cada visita.
        """
        assert statistics.cartas_emitidas() == 0

        with django_assert_num_queries(0):
            assert statistics.cartas_emitidas() == 0

    def test_o_cache_comeca_vazio_em_cada_teste(self):
        """A fixture `cache_limpo` do conftest -- sem ela a suíte
        dependeria da ordem em que roda."""
        assert cache.get(statistics.CHAVE_DO_CACHE) is None


# ===========================================================================
# 4. O conteúdo vem do CMS
# ===========================================================================


class TestConteudoDoCms:
    def test_a_home_existe_como_pagina(self):
        """Semeada pela migration `content.0004`."""
        pagina = Page.objects.get(key=services.CHAVE_DA_HOME)

        assert pagina.is_active is True
        assert set(pagina.sections.values_list("key", flat=True)) == {
            "navbar",
            "hero",
            "trust",
            "partners",
            "how",
            "faq",
            "cta",
            "footer",
        }

    def test_os_textos_da_pagina_vem_do_banco(self, client):
        secao = PageSection.objects.get(page__key="home", key="hero")
        traducao = secao.translations.get()
        traducao.content = {**traducao.content, "title": "Outro título"}
        traducao.save()

        html = client.get(HOME).content.decode()

        assert "Outro título" in html
        assert "Gere sua Carta Convite em poucos minutos" not in html

    def test_secao_desativada_some_da_pagina(self, client):
        PageSection.objects.filter(page__key="home", key="how").update(is_active=False)

        html = client.get(HOME).content.decode()

        assert "Como funciona?" not in html

    def test_os_cartoes_de_uma_secao_de_lista_saem_na_ordem(self, client):
        """
        A numeração escrita no título ("1. ") sai na hora de desenhar --
        quem numera os passos agora é a posição na lista (ver
        `conteudo.sem_numeracao`). A ORDEM continua sendo a do cadastro.
        """
        html = client.get(HOME).content.decode()

        assert html.index("Preencha") < html.index("Escolha") < html.index("Receba")

    def test_sem_pagina_no_banco_a_home_nao_quebra(self, client):
        """Instalação sem o conteúdo semeado: página em branco, não 500."""
        Page.objects.filter(key="home").delete()

        resposta = client.get(HOME)

        assert resposta.status_code == 200
        assert resposta.context["secoes"] == {}

    def test_idioma_sem_traducao_cai_no_padrao(self):
        """A infraestrutura de tradução do CMS, sem inventar percentuais."""
        conteudo = services.secoes_da_pagina("home", language="nl")

        assert conteudo["hero"]["title"] == "Gere sua Carta Convite em poucos minutos"

    def test_a_traducao_do_idioma_pedido_ganha(self):
        secao = PageSection.objects.get(page__key="home", key="hero")
        PageSectionTranslation.objects.create(
            section=secao, language="nl", content={"title": "Nederlands"}
        )

        conteudo = services.secoes_da_pagina("home", language="nl")

        assert conteudo["hero"]["title"] == "Nederlands"

    def test_pagina_inexistente_devolve_vazio(self):
        assert services.secoes_da_pagina("nao-existe") == {}


# ===========================================================================
# 5. Custo
# ===========================================================================


class TestCusto:
    def _consultas_da_home(self, client, quantos_parceiros, prefixo):
        """Quantas consultas a Home custa com N parceiros cadastrados."""
        for indice in range(quantos_parceiros):
            imagem = Asset.objects.create(
                key=f"{prefixo}{indice}", kind=Asset.Kind.PARTNER, file=_gif()
            )
            criar_parceiro(f"Parceiro {prefixo}{indice}", order=indice, logo=imagem)
        cache.clear()

        with CaptureQueriesContext(connection) as capturadas:
            client.get(HOME)
        return len(capturadas)

    def test_um_parceiro_a_mais_nao_custa_uma_consulta_a_mais(self, client):
        """
        O N+1 que este teste existe para impedir é o do logo: sem
        `select_related`, cada parceiro COM IMAGEM custaria uma consulta
        a mais -- por isso os parceiros daqui têm logo.
        """
        com_um = self._consultas_da_home(client, 1, "um")
        Partner.objects.all().delete()
        com_muitos = self._consultas_da_home(client, 8, "muitos")

        assert com_um == com_muitos

    def test_a_home_cabe_em_poucas_consultas(self, client):
        criar_parceiro("JD-Print")
        cache.clear()

        with CaptureQueriesContext(connection) as capturadas:
            client.get(HOME)

        # seções + traduções + parceiros + PERGUNTAS + contador +
        # configuração do site. Subiu de 8 para 9 quando as Perguntas
        # frequentes entraram: é UMA consulta a mais, e o teste seguinte
        # prova que ela não cresce com o número de perguntas.
        assert len(capturadas) <= 9, [c["sql"] for c in capturadas]

    def test_uma_pergunta_a_mais_nao_custa_uma_consulta_a_mais(self, client):
        """
        O mesmo N+1 que os parceiros já não têm. As perguntas não
        carregam objeto relacionado nenhum -- este teste é o que garante
        que continue assim se um dia carregarem.
        """
        from apps.content.models import FaqItem

        def consultas(quantas):
            FaqItem.objects.all().delete()
            for numero in range(quantas):
                FaqItem.objects.create(
                    question=f"Pergunta {numero}?", answer="Resposta.", order=numero
                )
            cache.clear()
            client.get(HOME)  # aquece o contador de cartas
            with CaptureQueriesContext(connection) as capturadas:
                client.get(HOME)
            return len(capturadas)

        assert consultas(1) == consultas(12)


# ===========================================================================
# 6. Segurança
# ===========================================================================


class TestSegurancaDaHome:
    def test_nenhum_dado_sensivel_no_html(self, client, user):
        """
        A Home é pública e anônima. Nada de e-mail de usuário, senha SMTP
        ou configuração privada.
        """
        from apps.core import mail

        configuracao = mail.configuracao()
        configuracao.host = "smtp.exemplo.com"
        configuracao.username = "mail@mail.com"
        configuracao.definir_senha("senha-de-mentira")
        configuracao.save()
        carta(user)

        html = client.get(HOME).content.decode()

        assert "senha-de-mentira" not in html
        assert configuracao.password_encrypted not in html
        assert "smtp.exemplo.com" not in html
        assert user.email not in html

    def test_o_endereco_do_parceiro_e_escapado(self, client):
        """Texto de administrador continua sendo texto, não marcação."""
        criar_parceiro('Aspas" <script>alert(1)</script>')

        html = client.get(HOME).content.decode()

        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
