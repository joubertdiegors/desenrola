"""
As páginas legais -- e o fim dos links mortos.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que volte a existir `href="#"`.** Eram cinco, em três telas: rodapé
   (2), cadastro (2) e perfil (1). A regra agora é uma só -- o link
   existe quando o documento existe;
2. **Que apareça página legal em branco.** Bloco ausente, desativado,
   sem tradução ou com texto vazio: todos são 404. Uma página de Termos
   vazia é pior do que página nenhuma;
3. **Que o sistema invente texto jurídico.** A migration cria os dois
   blocos SEM conteúdo. Quem escreve é o cliente -- desde a Rodada 15,
   pelo Backoffice (Sistema › Documentos legais);
4. **Que o texto SIMPLES vire marcação.** Nada de `|safe`: o que o
   cliente digitar num bloco de texto simples sai como texto, e HTML
   digitado aparece visível em vez de ser interpretado;
5. **Que um documento dependa do outro.** Publicar Termos não pode fazer
   Privacidade aparecer, nem o contrário;
6. **Que o texto FORMATADO passe sem a lista fechada.** O documento
   escrito no editor sai como HTML -- mas só o que
   `content.rodape.sanitizar_documento` deixa passar, de novo na hora de
   desenhar.
"""

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.content import services
from apps.content.models import ContentBlock, ContentTranslation

pytestmark = pytest.mark.django_db

TERMOS = reverse("core:legal_termos")
PRIVACIDADE = reverse("core:legal_privacidade")
HOME = reverse("core:home")
CADASTRO = reverse("accounts:signup")
PERFIL = reverse("accounts:profile")

CHAVE_TERMOS = "legal.terms_of_use"
CHAVE_PRIVACIDADE = "legal.privacy_policy"


def publicar(chave, texto, idioma="pt"):
    """Escreve o texto daquele documento -- o que o cliente fará no Admin."""
    bloco = ContentBlock.objects.get(key=chave)
    traducao, _criada = ContentTranslation.objects.get_or_create(
        block=bloco, language=idioma
    )
    traducao.content = texto
    traducao.save()
    return traducao


# ===========================================================================
# 1. A migration
# ===========================================================================


class TestMigration:
    def test_os_dois_blocos_existem(self):
        for chave in (CHAVE_TERMOS, CHAVE_PRIVACIDADE):
            bloco = ContentBlock.objects.filter(key=chave).first()
            assert bloco is not None, chave
            assert bloco.kind == ContentBlock.Kind.TEXT
            assert bloco.is_active is True

    def test_nascem_sem_texto_nenhum(self):
        """
        Texto jurídico é do cliente. A migration cria o LUGAR, não o
        documento -- nem uma tradução vazia, que o modelo não exige.
        """
        for chave in (CHAVE_TERMOS, CHAVE_PRIVACIDADE):
            bloco = ContentBlock.objects.get(key=chave)
            assert bloco.translations.count() == 0

    def test_e_idempotente(self):
        """
        Rodar de novo não duplica nem apaga o que o cliente escreveu.

        O `get_or_create` da migration é chamado diretamente, com um
        registro de modelos de brinquedo -- é o que a migration recebe
        de verdade, e evita ter de reverter e reaplicar um banco inteiro
        só para fazer esta pergunta.
        """
        import importlib

        migration = importlib.import_module(
            "apps.content.migrations.0007_paginas_legais"
        )

        publicar(CHAVE_TERMOS, "Texto do cliente.")

        class RegistroDeBrinquedo:
            def get_model(self, app_label, model_name):
                assert (app_label, model_name) == ("content", "ContentBlock")
                return ContentBlock

        migration.criar_os_blocos(RegistroDeBrinquedo(), None)

        assert ContentBlock.objects.filter(key=CHAVE_TERMOS).count() == 1
        assert ContentBlock.objects.filter(key=CHAVE_PRIVACIDADE).count() == 1
        assert services.texto_legal(CHAVE_TERMOS) == "Texto do cliente."

    def test_as_chaves_batem_com_o_codigo(self):
        """
        A migration repete as chaves de propósito (é registro histórico),
        mas as duas listas não podem divergir -- se divergirem, o código
        procura um bloco que a migration não criou.
        """
        assert set(services.CHAVES_LEGAIS) == {CHAVE_TERMOS, CHAVE_PRIVACIDADE}


# ===========================================================================
# 2. O resolvedor
# ===========================================================================


class TestResolucao:
    def test_sem_texto_devolve_none(self):
        assert services.texto_legal(CHAVE_TERMOS) is None

    def test_com_texto_devolve_o_texto(self):
        publicar(CHAVE_TERMOS, "Primeira cláusula.")

        assert services.texto_legal(CHAVE_TERMOS) == "Primeira cláusula."

    def test_bloco_inexistente_devolve_none(self):
        assert services.texto_legal("legal.nao_existe") is None

    def test_bloco_inativo_devolve_none(self):
        publicar(CHAVE_TERMOS, "Primeira cláusula.")
        ContentBlock.objects.filter(key=CHAVE_TERMOS).update(is_active=False)

        assert services.texto_legal(CHAVE_TERMOS) is None

    @pytest.mark.parametrize("vazio", ["", "   ", "\n\n", "\t "])
    def test_texto_em_branco_conta_como_ausente(self, vazio):
        """Espaço em branco não é documento publicado."""
        publicar(CHAVE_TERMOS, vazio)

        assert services.texto_legal(CHAVE_TERMOS) is None

    def test_o_idioma_pedido_ganha(self):
        publicar(CHAVE_TERMOS, "Em português.", idioma="pt")
        publicar(CHAVE_TERMOS, "En français.", idioma="fr")

        assert services.texto_legal(CHAVE_TERMOS, language="fr") == "En français."

    def test_sem_traducao_no_idioma_cai_no_padrao(self):
        """A mesma regra de `secoes_da_pagina` -- não é queda inventada."""
        publicar(CHAVE_TERMOS, "Em português.", idioma="pt")

        assert services.texto_legal(CHAVE_TERMOS, language="nl") == "Em português."

    def test_so_o_idioma_errado_nao_serve(self):
        """
        Publicado só em francês e pedido em português: não há queda de
        `fr` para `pt`. A queda é sempre PARA o idioma padrão.
        """
        publicar(CHAVE_TERMOS, "En français.", idioma="fr")

        assert services.texto_legal(CHAVE_TERMOS, language="pt") is None

    def test_publicadas_lista_so_o_que_tem_texto(self):
        publicar(CHAVE_TERMOS, "Cláusulas.")

        assert services.legais_publicadas() == {CHAVE_TERMOS}

    def test_publicadas_numa_consulta_so(self):
        publicar(CHAVE_TERMOS, "Cláusulas.")
        publicar(CHAVE_PRIVACIDADE, "Política.")

        with CaptureQueriesContext(connection) as capturadas:
            services.legais_publicadas()

        assert len(capturadas) == 1


# ===========================================================================
# 3. As páginas
# ===========================================================================


class TestPaginas:
    @pytest.mark.parametrize("url", [TERMOS, PRIVACIDADE])
    def test_sem_texto_responde_404(self, client, url):
        assert client.get(url).status_code == 404

    def test_com_texto_abre(self, client):
        publicar(CHAVE_TERMOS, "Primeira cláusula.")

        resposta = client.get(TERMOS)

        assert resposta.status_code == 200
        assert "Primeira cláusula." in resposta.content.decode()

    def test_bloco_inativo_responde_404(self, client):
        publicar(CHAVE_TERMOS, "Primeira cláusula.")
        ContentBlock.objects.filter(key=CHAVE_TERMOS).update(is_active=False)

        assert client.get(TERMOS).status_code == 404

    def test_bloco_apagado_responde_404(self, client):
        ContentBlock.objects.filter(key=CHAVE_TERMOS).delete()

        assert client.get(TERMOS).status_code == 404

    def test_os_dois_documentos_sao_independentes(self, client):
        publicar(CHAVE_TERMOS, "Cláusulas.")

        assert client.get(TERMOS).status_code == 200
        assert client.get(PRIVACIDADE).status_code == 404

    def test_a_pagina_e_publica(self, client):
        """
        Um documento legal precisa ser legível ANTES de criar conta -- o
        link dele está, justamente, na tela de cadastro.
        """
        publicar(CHAVE_TERMOS, "Cláusulas.")

        resposta = client.get(TERMOS)

        assert resposta.status_code == 200

    def test_o_titulo_traz_o_documento_e_o_site(self, client):
        publicar(CHAVE_TERMOS, "Cláusulas.")

        corpo = client.get(TERMOS).content.decode()

        assert "<title>Termos de uso · " in corpo

    def test_o_html_digitado_e_escapado(self, client):
        """Nada de `|safe`: o que o cliente escreve é TEXTO."""
        publicar(CHAVE_TERMOS, "<script>alert(1)</script> e <b>negrito</b>")

        corpo = client.get(TERMOS).content.decode()

        assert "<script>alert(1)</script>" not in corpo
        assert "<b>negrito</b>" not in corpo
        assert "&lt;script&gt;" in corpo

    def test_paragrafos_e_quebras_sao_preservados(self, client):
        publicar(CHAVE_TERMOS, "Linha um\nLinha dois\n\nSegundo parágrafo")

        corpo = client.get(TERMOS).content.decode()

        assert "<p>Linha um<br>Linha dois</p>" in corpo
        assert "<p>Segundo parágrafo</p>" in corpo

    def test_a_pagina_nao_traz_ancora_morta(self, client):
        """
        O cabeçalho não é o `site_nav`: as âncoras dele (`#como-funciona`,
        `#parceiros`) são seções da Home e aqui não levariam a lugar
        nenhum -- seria o mesmo defeito, de novo.
        """
        publicar(CHAVE_TERMOS, "Cláusulas.")

        corpo = client.get(TERMOS).content.decode()

        # Ancora RELATIVA e' a morta. O rodape rico leva os links do
        # menu com o caminho da Home na frente (`/pt/#como-funciona`),
        # e esses levam a Home -- ver `content.rodape._menu_renderizado`.
        assert 'href="#como-funciona"' not in corpo
        assert 'href="#parceiros"' not in corpo

    def test_o_custo_nao_cresce_com_o_texto(self, client):
        publicar(CHAVE_TERMOS, "Cláusulas.")
        publicar(CHAVE_PRIVACIDADE, "Política.")

        with CaptureQueriesContext(connection) as capturadas:
            client.get(TERMOS)

        legais = [c for c in capturadas if "contentblock" in c["sql"]]
        # Exatamente duas, e não "no máximo duas": limite frouxo não
        # guarda nada. Uma traz o texto da página, outra diz ao rodapé
        # quais links mostrar. Nenhuma das duas cresce com a quantidade
        # de documentos nem com o tamanho do texto.
        assert len(legais) == 2


# ===========================================================================
# 4. Os links, nas três telas
# ===========================================================================


def _corpos_das_tres_telas(user):
    """
    As três telas que tinham `href="#"`, cada uma no seu cliente.

    UM CLIENTE POR TELA, e não o `client`/`auth_client` do conftest: lá
    os dois são o MESMO objeto (`auth_client` só faz `force_login` e o
    devolve). Pedir a tela de cadastro por um cliente já autenticado cai
    num redirecionamento, e o corpo vazio faria qualquer asserção sobre
    ele passar sem ter visto nada.
    """
    anonimo = Client()
    logado = Client()
    logado.force_login(user)

    corpos = {
        "home": anonimo.get(HOME),
        "cadastro": anonimo.get(CADASTRO),
        "perfil": logado.get(PERFIL),
    }
    for nome, resposta in corpos.items():
        assert resposta.status_code == 200, f"{nome} respondeu {resposta.status_code}"
    return {nome: r.content.decode() for nome, r in corpos.items()}


class TestLinks:
    def test_nenhuma_das_tres_telas_tem_href_morto(self, user):
        """
        A varredura que motivou a etapa: cinco `href="#"` em três telas.
        """
        publicar(CHAVE_TERMOS, "Cláusulas.")
        publicar(CHAVE_PRIVACIDADE, "Política.")

        for tela, corpo in _corpos_das_tres_telas(user).items():
            assert 'href="#"' not in corpo, tela

    def test_nenhuma_das_tres_telas_tem_href_morto_sem_publicar(self, user):
        """Sem documento publicado, o link some -- não vira `#`."""
        for tela, corpo in _corpos_das_tres_telas(user).items():
            assert 'href="#"' not in corpo, tela

    def test_o_rodape_esconde_o_que_nao_esta_publicado(self, client):
        corpo = client.get(HOME).content.decode()

        assert TERMOS not in corpo
        assert PRIVACIDADE not in corpo

    def test_o_rodape_mostra_o_que_esta_publicado(self, client):
        publicar(CHAVE_TERMOS, "Cláusulas.")

        corpo = client.get(HOME).content.decode()

        assert f'href="{TERMOS}"' in corpo
        assert PRIVACIDADE not in corpo

    def test_o_cadastro_aponta_para_as_paginas_reais(self, client):
        publicar(CHAVE_TERMOS, "Cláusulas.")
        publicar(CHAVE_PRIVACIDADE, "Política.")

        corpo = client.get(CADASTRO).content.decode()

        assert f'href="{TERMOS}"' in corpo
        assert f'href="{PRIVACIDADE}"' in corpo

    def test_o_cadastro_continua_pedindo_o_aceite_sem_documento(self, client):
        """
        O rótulo continua lá mesmo sem texto publicado: a pessoa precisa
        saber o que está aceitando. O que não existe é o link.
        """
        corpo = client.get(CADASTRO).content.decode()

        assert "Li e aceito os Termos de uso" in corpo
        assert 'name="terms"' in corpo
        assert TERMOS not in corpo

    def test_o_perfil_aponta_para_a_privacidade_publicada(self, auth_client):
        publicar(CHAVE_PRIVACIDADE, "Política.")

        corpo = auth_client.get(PERFIL).content.decode()

        assert f'href="{PRIVACIDADE}"' in corpo

    def test_o_perfil_esconde_o_link_sem_documento(self, auth_client):
        corpo = auth_client.get(PERFIL).content.decode()

        assert PRIVACIDADE not in corpo

    @pytest.mark.parametrize(
        ("publicado", "url_visivel", "url_oculta"),
        [
            (CHAVE_PRIVACIDADE, PRIVACIDADE, TERMOS),
            (CHAVE_TERMOS, TERMOS, PRIVACIDADE),
        ],
    )
    def test_publicar_um_nao_faz_o_outro_aparecer(
        self, client, publicado, url_visivel, url_oculta
    ):
        """
        Nas DUAS direções: uma só delas não prova independência -- prova
        apenas que aquele documento funciona.
        """
        publicar(publicado, "Texto.")

        corpo = client.get(HOME).content.decode()

        assert f'href="{url_visivel}"' in corpo
        assert url_oculta not in corpo


# ===========================================================================
# 5. O cadastro continua o que era
# ===========================================================================


class TestCadastroIntacto:
    """
    A REGRA do aceite não mudou nesta etapa, e continua coberta por
    `accounts/tests/test_views.py::test_cadastro_exige_aceite_dos_termos`.
    O que esta etapa mexeu foi na MARCAÇÃO do rótulo -- e é isso que se
    verifica aqui, nos quatro estados de publicação possíveis.
    """

    @pytest.mark.parametrize(
        "publicados",
        [
            (),
            (CHAVE_TERMOS,),
            (CHAVE_PRIVACIDADE,),
            (CHAVE_TERMOS, CHAVE_PRIVACIDADE),
        ],
    )
    def test_a_caixa_de_aceite_sobrevive_a_qualquer_estado(self, client, publicados):
        for chave in publicados:
            publicar(chave, "Texto.")

        corpo = client.get(CADASTRO).content.decode()

        assert 'name="terms"' in corpo
        assert 'type="checkbox"' in corpo
        assert "Termos de uso" in corpo
        assert "Política de privacidade" in corpo
        assert 'href="#"' not in corpo


# ===========================================================================
# 6. Identidade conta o estado e aponta para onde se escreve
# ===========================================================================


class TestBackoffice:
    def test_a_tela_de_sistema_mostra_o_estado(self, client, staff_user):
        client.force_login(staff_user)

        corpo = client.get(reverse("backoffice:system")).content.decode()

        assert "Sem texto" in corpo
        assert "Não há links legais configurados" not in corpo

    def test_a_tela_de_sistema_mostra_publicado(self, client, staff_user):
        publicar(CHAVE_TERMOS, "Cláusulas.")
        publicar(CHAVE_PRIVACIDADE, "Política.")
        client.force_login(staff_user)

        corpo = client.get(reverse("backoffice:system")).content.decode()

        assert "Publicado" in corpo
        assert f'href="{TERMOS}"' in corpo

    def test_a_tela_aponta_para_os_documentos_legais_e_nao_edita(
        self, client, staff_user
    ):
        """
        Não há editor paralelo em Identidade: o texto se escreve em
        Documentos legais, no próprio Backoffice -- e não mais no Django
        Admin (Rodada 15).
        """
        from django.contrib.auth.models import Permission

        staff_user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="view_contentblock")
        )
        client.force_login(staff_user)

        corpo = client.get(reverse("backoffice:system")).content.decode()

        assert f'href="{reverse("backoffice:legal_documents")}"' in corpo
        assert reverse("admin:content_contentblock_changelist") not in corpo
        assert 'name="legal.terms_of_use"' not in corpo
        assert 'name="termos_de_uso"' not in corpo

    def test_sem_a_permissao_o_nome_aparece_sem_link(self, client, staff_user):
        """O menu esconde a tela de quem não a abre; o cartão também."""
        client.force_login(staff_user)

        corpo = client.get(reverse("backoffice:system")).content.decode()

        assert "Documentos legais" in corpo
        assert reverse("backoffice:legal_documents") not in corpo


# ===========================================================================
# 7. O texto formatado, na página pública
# ===========================================================================


def publicar_formatado(chave, html, idioma="pt"):
    """O que o editor de Documentos legais grava: HTML e "Texto formatado"."""
    ContentBlock.objects.filter(key=chave).update(kind=ContentBlock.Kind.RICH_TEXT)
    return publicar(chave, html, idioma)


class TestTextoFormatado:
    def test_a_marcacao_permitida_vira_marcacao(self, client):
        publicar_formatado(
            CHAVE_TERMOS,
            '<h2>1. Objeto</h2><p style="text-align:center">Texto <strong>forte</strong>.</p>'
            "<ul><li>item</li></ul>",
        )

        corpo = client.get(TERMOS).content.decode()

        assert "<h2>1. Objeto</h2>" in corpo
        assert '<p style="text-align:center">Texto <strong>forte</strong>.</p>' in corpo
        assert "<ul><li>item</li></ul>" in corpo

    def test_o_que_a_lista_nao_aceita_sai_na_hora_de_desenhar(self, client):
        """
        O banco não é confiável por definição: um HTML gravado por fora do
        editor (o Django Admin, um script) passa pela lista de novo.
        """
        publicar_formatado(
            CHAVE_TERMOS,
            '<p onclick="roubar()">Oi</p><script>alert(1)</script>'
            '<a href="javascript:alert(1)">x</a><img src="https://fora.test/p.png">',
        )

        corpo = client.get(TERMOS).content.decode()
        texto = corpo[corpo.index('class="legal-texto"') :]

        assert "onclick" not in texto
        assert "<script>alert(1)</script>" not in texto
        assert "javascript:" not in texto
        assert "fora.test" not in texto
        assert "<p>Oi</p>" in texto

    def test_o_texto_simples_continua_como_era(self, client):
        """O formato do bloco decide: texto simples não vira HTML."""
        publicar(CHAVE_TERMOS, "<b>negrito</b>\nLinha dois")

        corpo = client.get(TERMOS).content.decode()

        assert "<p>&lt;b&gt;negrito&lt;/b&gt;<br>Linha dois</p>" in corpo

    def test_formatado_so_com_marcacao_conta_como_sem_texto(self, client):
        """`<p><br></p>` é o editor vazio -- não é documento publicado."""
        publicar_formatado(CHAVE_TERMOS, "<p><br></p><p>&nbsp;</p>")

        assert client.get(TERMOS).status_code == 404
        assert "legal.terms_of_use" not in services.legais_publicadas()

    def test_o_custo_continua_o_mesmo(self, client):
        publicar_formatado(CHAVE_TERMOS, "<h2>Um</h2><p>Dois</p>")
        publicar(CHAVE_PRIVACIDADE, "Política.")

        with CaptureQueriesContext(connection) as capturadas:
            client.get(TERMOS)

        assert len([c for c in capturadas if "contentblock" in c["sql"]]) == 2
