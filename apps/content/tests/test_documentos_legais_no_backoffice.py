"""
Documentos legais no Backoffice (Sistema › Documentos legais).

CADA DOCUMENTO, DUAS ROTAS PRÓPRIAS (Rodada 21) + EDITOR POR BLOCOS (Rodada 22)
---------------------------------------------------------------------------------
Termos de uso e Privacidade têm cada um a sua rota de VISUALIZAÇÃO
(sempre o documento renderizado, nunca o HTML cru, nunca os controles
do editor) e a sua rota de EDIÇÃO (o editor por blocos, só para quem
tem a permissão) -- nunca os dois documentos na mesma tela, nunca ver
e editar juntos.

Desde a Rodada 22, editar não é mais preencher um `<textarea>` de HTML:
é montar uma LISTA de blocos (`apps.content.blocos`), mandada ao
servidor como um campo `blocos` (JSON) -- não há mais `Form` nem
`context["form"]`. Uma terceira rota, a PRÉVIA, mostra o rascunho (via
POST) ou o gravado (via GET) num `<iframe>`, sem gravar nada.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que uma rota abra ou grave sem a permissão de sempre.** Ver exige
   `content.view_contentblock`; editar e a prévia (GET e POST), `content.
   change_contentblock` -- as mesmas de sempre;
2. **Que a visualização ou a prévia mostrem HTML cru ou controles de
   edição.** Ambas só mostram o documento RENDERIZADO;
3. **Que abrir o editor altere ou converta o documento.** Só "Salvar"
   grava -- e só aí o bloco passa a "Blocos estruturados";
4. **Que HTML ou endereço perigoso cheguem ao banco**, em qualquer tipo
   de bloco (parágrafo, HTML livre, botão, imagem);
5. **Que a primeira gravação por blocos quebre outro idioma.** As
   traduções que ainda estiverem no formato de antes são convertidas
   junto, com o mesmo conteúdo;
6. **Que um editor esvaziado (ou só com separador) publique uma página
   em branco.** Grava `[]`, e a página volta a responder 404;
7. **Que um documento vaze para a rota do outro** -- visualização,
   edição e prévia;
8. **Que as rotas públicas mudem.** `/legal/termos-de-uso/` e
   `/legal/privacidade/` continuam exatamente como estavam;
9. **Que o rodapé perca a lista dele.** A lista dos documentos
   (`h2`, `img`) é outra; a do rodapé continua a de antes.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.content import blocos, rodape, services
from apps.content.models import ContentBlock, ContentTranslation

pytestmark = pytest.mark.django_db

VER_TERMOS = reverse("backoffice:legal_documents_terms")
EDITAR_TERMOS = reverse("backoffice:legal_documents_terms_edit")
PREVIA_TERMOS = reverse("backoffice:legal_documents_terms_preview")
VER_PRIVACIDADE = reverse("backoffice:legal_documents_privacy")
EDITAR_PRIVACIDADE = reverse("backoffice:legal_documents_privacy_edit")
PREVIA_PRIVACIDADE = reverse("backoffice:legal_documents_privacy_preview")

TERMOS = reverse("core:legal_termos")
PRIVACIDADE = reverse("core:legal_privacidade")
CHAVE_TERMOS = "legal.terms_of_use"
CHAVE_PRIVACIDADE = "legal.privacy_policy"

TODAS_AS_ROTAS = (VER_TERMOS, EDITAR_TERMOS, VER_PRIVACIDADE, EDITAR_PRIVACIDADE)
TODAS_AS_PREVIAS = (PREVIA_TERMOS, PREVIA_PRIVACIDADE)


def _pessoa(email, *permissoes):
    pessoa = get_user_model().objects.create_user(
        email=email, password="x", full_name="Clara Dias"
    )
    for app_label, codename in permissoes:
        pessoa.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return get_user_model().objects.get(pk=pessoa.pk)


def _cliente(pessoa):
    c = Client()
    c.force_login(pessoa)
    return c


@pytest.fixture
def leitora(db):
    return _pessoa(
        "leitora-legais@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_contentblock"),
    )


@pytest.fixture
def editora(db):
    return _pessoa(
        "editora-legais@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_contentblock"),
        ("content", "change_contentblock"),
    )


@pytest.fixture
def cliente(editora):
    return _cliente(editora)


def publicar_simples(chave, texto, idioma="pt"):
    """O estado de hoje: texto simples, escrito pelo Django Admin."""
    bloco = ContentBlock.objects.get(key=chave)
    ContentTranslation.objects.update_or_create(
        block=bloco, language=idioma, defaults={"content": texto}
    )


def paragrafo(html):
    """Um bloco de parágrafo -- o `html` é só o FRAGMENTO interno, sem `<p>` (ver `blocos.py`)."""
    return {"type": "paragraph", "html": html}


def salvar(cliente, lista_de_blocos, rota=EDITAR_TERMOS, idioma="pt", **extra):
    return cliente.post(
        rota, {"idioma": idioma, "blocos": json.dumps(lista_de_blocos), **extra}
    )


def gravado(chave=CHAVE_TERMOS, idioma="pt"):
    return ContentTranslation.objects.get(block__key=chave, language=idioma).content


def blocos_gravados(chave=CHAVE_TERMOS, idioma="pt"):
    return json.loads(gravado(chave, idioma))


def html_renderizado(chave=CHAVE_TERMOS, idioma="pt"):
    return rodape.renderizar_documento_em_blocos(blocos_gravados(chave, idioma))


def _asset_ativo(nome="selo.gif", **extra):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.content.models import Asset

    gif = (
        b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
        b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    )
    return Asset.objects.create(
        kind=Asset.Kind.CONTENT,
        file=SimpleUploadedFile(nome, gif, content_type="image/gif"),
        **extra,
    )


# ===========================================================================
# 1. Seis rotas, as mesmas duas permissões
# ===========================================================================


class TestAcesso:
    @pytest.mark.parametrize("rota", TODAS_AS_ROTAS)
    def test_anonimo_vai_para_o_login(self, client, rota):
        resposta = client.get(rota)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    @pytest.mark.parametrize("rota", TODAS_AS_ROTAS)
    def test_usuario_comum_nao_entra(self, auth_client, rota):
        assert auth_client.get(rota).status_code in (302, 403)

    @pytest.mark.parametrize("rota", TODAS_AS_ROTAS)
    def test_backoffice_sem_a_permissao_nao_entra(self, client, staff_user, rota):
        client.force_login(staff_user)

        assert client.get(rota).status_code == 403

    @pytest.mark.parametrize("rota", [VER_TERMOS, VER_PRIVACIDADE])
    def test_quem_so_ve_abre_a_visualizacao(self, leitora, rota):
        assert _cliente(leitora).get(rota).status_code == 200

    @pytest.mark.parametrize("rota", [EDITAR_TERMOS, EDITAR_PRIVACIDADE])
    def test_quem_so_ve_nao_alcanca_a_edicao(self, leitora, rota):
        """Nem o GET: a permissão de editar é da ROTA, não um `if` interno."""
        assert _cliente(leitora).get(rota).status_code == 403

    def test_quem_so_ve_nao_grava(self, leitora):
        publicar_simples(CHAVE_TERMOS, "Original.")

        resposta = salvar(_cliente(leitora), [paragrafo("Trocado.")])

        assert resposta.status_code == 403
        assert gravado() == "Original."

    def test_post_sem_token_e_recusado(self, editora):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(editora)

        resposta = salvar(sem_token, [paragrafo("Sem token.")])

        assert resposta.status_code == 403
        assert not ContentTranslation.objects.filter(block__key=CHAVE_TERMOS).exists()

    def test_as_duas_permissoes_estao_no_catalogo(self):
        from apps.accounts import admin_permissions

        chaves = {p.chave for p in admin_permissions.todas()}

        assert "content.view_contentblock" in chaves
        assert "content.change_contentblock" in chaves

    def test_o_menu_so_oferece_a_quem_abre(self, client, staff_user, leitora):
        client.force_login(staff_user)
        sem = client.get(reverse("backoffice:overview")).content.decode()
        com = _cliente(leitora).get(reverse("backoffice:overview")).content.decode()

        assert f'href="{VER_TERMOS}"' not in sem
        assert f'href="{VER_PRIVACIDADE}"' not in sem
        assert f'href="{VER_TERMOS}"' in com
        assert f'href="{VER_PRIVACIDADE}"' in com


# ===========================================================================
# 2. A visualização: o documento renderizado, nunca o cru
# ===========================================================================


class TestVisualizacao:
    def test_mostra_o_texto_simples_ja_renderizado(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Linha um\nLinha dois")

        corpo = cliente.get(VER_TERMOS).content.decode()

        assert "Linha um" in corpo
        assert "Linha dois" in corpo

    def test_nao_mostra_html_cru_nem_controles_do_editor(self, cliente):
        salvar(cliente, [
            {"type": "heading", "html": "1. Objeto"},
            paragrafo("Texto <em>leve</em>."),
        ])

        corpo = cliente.get(VER_TERMOS).content.decode()

        # O HTML sanitizado aparece INTERPRETADO -- não escapado feito texto.
        assert "&lt;h2&gt;" not in corpo
        assert 'name="blocos"' not in corpo
        assert "data-editor-blocos" not in corpo
        assert "data-canvas" not in corpo
        assert "js/editor-blocos.js" not in corpo

    def test_o_botao_editar_so_aparece_para_quem_pode_editar(self, leitora, cliente):
        so_ve = _cliente(leitora).get(VER_TERMOS).content.decode()
        com_edicao = cliente.get(VER_TERMOS).content.decode()

        assert f'href="{EDITAR_TERMOS}"' not in so_ve
        assert "Editar" not in so_ve
        assert f'href="{EDITAR_TERMOS}"' in com_edicao

    def test_idioma_sem_texto_avisa_e_cai_no_padrao(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Só em português.")

        resposta = cliente.get(VER_TERMOS, {"idioma": "fr"})

        assert "a página mostra o texto do idioma padrão" in resposta.content.decode()

    def test_sem_texto_nenhum_avisa_que_a_pagina_nao_abre(self, cliente):
        corpo = cliente.get(VER_TERMOS).content.decode()

        assert "a página não abre" in corpo

    def test_documento_desativado_avisa(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Texto.")
        ContentBlock.objects.filter(key=CHAVE_TERMOS).update(is_active=False)

        assert "está desativado" in cliente.get(VER_TERMOS).content.decode()


# ===========================================================================
# 3. Termos e Privacidade não vazam um para o outro
# ===========================================================================


class TestIsolamentoEntreDocumentos:
    def test_a_visualizacao_de_termos_nunca_mostra_privacidade(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Cláusula dos termos.")
        publicar_simples(CHAVE_PRIVACIDADE, "Cláusula da privacidade.")

        corpo = cliente.get(VER_TERMOS).content.decode()

        assert "Cláusula dos termos." in corpo
        assert "Cláusula da privacidade." not in corpo

    def test_a_visualizacao_de_privacidade_nunca_mostra_termos(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Cláusula dos termos.")
        publicar_simples(CHAVE_PRIVACIDADE, "Cláusula da privacidade.")

        corpo = cliente.get(VER_PRIVACIDADE).content.decode()

        assert "Cláusula da privacidade." in corpo
        assert "Cláusula dos termos." not in corpo

    def test_salvar_termos_nao_grava_em_privacidade(self, cliente):
        publicar_simples(CHAVE_PRIVACIDADE, "Intocada.")

        salvar(cliente, [paragrafo("Novo texto dos termos.")], rota=EDITAR_TERMOS)

        assert gravado(CHAVE_PRIVACIDADE) == "Intocada."
        assert "Novo texto dos termos." in html_renderizado(CHAVE_TERMOS)

    def test_salvar_privacidade_nao_grava_em_termos(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Intocada.")

        salvar(cliente, [paragrafo("Novo texto da privacidade.")], rota=EDITAR_PRIVACIDADE)

        assert gravado(CHAVE_TERMOS) == "Intocada."
        assert "Novo texto da privacidade." in html_renderizado(CHAVE_PRIVACIDADE)

    def test_o_editor_de_termos_abre_o_texto_de_termos(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Termos aqui.")
        publicar_simples(CHAVE_PRIVACIDADE, "Privacidade aqui.")

        blocos_iniciais = json.dumps(cliente.get(EDITAR_TERMOS).context["blocos_json"])

        assert "Termos aqui." in blocos_iniciais
        assert "Privacidade aqui." not in blocos_iniciais


# ===========================================================================
# 4. A edição: abrir não muda nada
# ===========================================================================


class TestAbrirParaEditar:
    def test_o_texto_simples_abre_convertido_em_blocos(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Linha um\nLinha dois")

        blocos_iniciais = cliente.get(EDITAR_TERMOS).context["blocos_json"]

        # O `id` de cada bloco é gerado na hora (a conversão não grava
        # nada) -- cada chamada tem o seu; só o CONTEÚDO precisa bater.
        sem_id = [{k: v for k, v in b.items() if k != "id"} for b in blocos_iniciais]
        outra_conversao = [
            {k: v for k, v in b.items() if k != "id"}
            for b in services.blocos_do_documento(CHAVE_TERMOS, "pt")
        ]
        assert sem_id == outra_conversao
        assert blocos.blocos_tem_conteudo(blocos_iniciais)

    def test_abrir_nao_grava_nem_converte(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Linha um\nLinha dois")

        cliente.get(EDITAR_TERMOS)

        assert gravado() == "Linha um\nLinha dois"
        assert ContentBlock.objects.get(key=CHAVE_TERMOS).kind == ContentBlock.Kind.TEXT

    def test_o_link_ver_visualizacao_leva_a_rota_certa(self, cliente):
        assert f'href="{VER_TERMOS}"' in cliente.get(EDITAR_TERMOS).content.decode()
        assert f'href="{VER_PRIVACIDADE}"' in cliente.get(EDITAR_PRIVACIDADE).content.decode()

    def test_e_o_editor_por_blocos_nao_o_editor_de_html_corrido(self, cliente):
        corpo = cliente.get(EDITAR_TERMOS).content.decode()

        assert "data-editor-blocos" in corpo
        assert "js/editor-blocos.js" in corpo
        assert "data-editor-rico" not in corpo
        assert "js/editor-rico.js" not in corpo

    def test_o_catalogo_de_blocos_esta_na_tela(self, cliente):
        corpo = cliente.get(EDITAR_TERMOS).content.decode()

        for tipo in ("paragraph", "heading", "list", "quote", "image", "gallery",
                     "highlight", "table", "button", "separator", "html"):
            assert f'"tipo": "{tipo}"' in corpo

    def test_o_seletor_de_imagens_oferece_so_a_biblioteca(self, cliente, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        viva = _asset_ativo("viva.gif", alt_text="Selo")
        morta = _asset_ativo("morta.gif", is_active=False)

        corpo = cliente.get(EDITAR_TERMOS).content.decode()

        assert viva.file.url in corpo
        assert morta.file.url not in corpo


# ===========================================================================
# 5. Gravar: a lista fechada decide, bloco por bloco
# ===========================================================================


class TestGravar:
    def test_grava_o_html_permitido(self, cliente):
        salvar(cliente, [
            {"type": "heading", "html": "1. Objeto"},
            paragrafo("Texto <em>leve</em>."),
            {"type": "list", "html": "<ol><li>um</li></ol>"},
            {"type": "button", "html": "Site", "href": "https://exemplo.test/"},
        ])

        html = html_renderizado()
        assert "<h2>1. Objeto</h2>" in html
        assert "<p>Texto <em>leve</em>.</p>" in html
        assert "<ol><li>um</li></ol>" in html
        assert '<p class="legal-botao"><a href="https://exemplo.test/">Site</a></p>' in html
        assert ContentBlock.objects.get(key=CHAVE_TERMOS).kind == ContentBlock.Kind.STRUCTURED

    def test_o_perigoso_nao_chega_ao_banco(self, cliente):
        salvar(cliente, [
            paragrafo('<span onclick="x()">Oi</span><script>alert(1)</script>'),
            {"type": "html", "html": '<iframe src="/"></iframe><p>Ok</p>'},
            {"type": "button", "html": "a", "href": "javascript:alert(1)"},
            paragrafo('<a href="{url_termos}">atalho</a>'),
            {"type": "image", "asset_id": 999999, "alt": "x"},
        ])

        html = html_renderizado()
        assert "onclick" not in html
        assert "<script" not in html
        assert "<iframe" not in html
        assert "javascript:" not in html
        assert "legal-bloco-button" not in html  # sem href aceito, o botão não é desenhado
        assert "{url_termos}" not in html  # documento não tem atalhos
        assert "legal-bloco-image" not in html  # asset inexistente não é desenhado
        # A parte SEGURA de cada bloco perigoso precisa sobreviver -- não
        # basta que o perigoso suma; o bloco não pode ficar vazio.
        assert "<p>Ok</p>" in html

    def test_tabela_escapa_o_texto_das_celulas(self, cliente):
        salvar(cliente, [{
            "type": "table",
            "cabecalho": True,
            "linhas": [["Nome", "<script>alert(1)</script>"], ["a", "b"]],
        }])

        html = html_renderizado()
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_a_imagem_da_biblioteca_passa(self, cliente, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        ativa = _asset_ativo("selo.gif", alt_text="Selo")

        salvar(cliente, [{"type": "image", "asset_id": ativa.pk, "alt": "Selo"}])

        html = html_renderizado()
        assert f'src="{ativa.file.url}"' in html
        assert 'alt="Selo"' in html

    def test_imagem_de_asset_inativo_nao_aparece(self, cliente, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        inativo = _asset_ativo("inativo.gif", is_active=False)

        salvar(cliente, [{"type": "image", "asset_id": inativo.pk, "alt": "x"}])

        assert "legal-bloco-image" not in html_renderizado()

    def test_editor_vazio_grava_sem_texto_e_tira_a_pagina(self, cliente):
        salvar(cliente, [paragrafo("Publicado.")])
        assert cliente.get(TERMOS).status_code == 200

        resposta = salvar(cliente, [])

        assert resposta.status_code == 302
        assert gravado() == "[]"
        assert cliente.get(TERMOS).status_code == 404

    def test_apenas_separador_tambem_e_documento_vazio(self, cliente):
        salvar(cliente, [paragrafo("Publicado.")])

        resposta = salvar(cliente, [{"type": "separator"}])

        assert resposta.status_code == 302
        assert gravado() == "[]"
        assert cliente.get(TERMOS).status_code == 404

    def test_volta_para_a_mesma_rota_e_idioma(self, cliente):
        resposta = salvar(cliente, [paragrafo("Tekst.")], rota=EDITAR_PRIVACIDADE, idioma="nl")

        assert resposta.url == f"{EDITAR_PRIVACIDADE}?idioma=nl"
        assert "Tekst." in html_renderizado(CHAVE_PRIVACIDADE, "nl")

    def test_documento_grande_demais_e_cortado_sem_erro(self, cliente):
        """
        Não há mais validação de formulário (não há mais `Form`): um
        documento grande demais é CORTADO pelo fim, como qualquer lista
        longa demais -- nunca um erro de servidor nem uma tela de erro.
        """
        publicar_simples(CHAVE_TERMOS, "Original.")
        enorme = [paragrafo("a" * 60_000) for _ in range(10)]  # bem além do limite

        resposta = salvar(cliente, enorme)

        assert resposta.status_code == 302
        tamanho_gravado = len(gravado())
        assert tamanho_gravado <= rodape.TAMANHO_MAXIMO_DO_DOCUMENTO

    def test_a_primeira_gravacao_converte_os_outros_idiomas_para_blocos(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Texte <un>\nligne deux", idioma="fr")

        salvar(cliente, [paragrafo("Português.")])

        assert ContentBlock.objects.get(key=CHAVE_TERMOS).kind == ContentBlock.Kind.STRUCTURED
        francesa = services.documento_legal(CHAVE_TERMOS, "fr")
        assert francesa.blocos is not None
        assert "Texte" in rodape.renderizar_documento_em_blocos(francesa.blocos)

    def test_o_bloco_apagado_volta_a_existir(self, cliente):
        ContentBlock.objects.filter(key=CHAVE_TERMOS).delete()

        salvar(cliente, [paragrafo("De novo.")])

        bloco = ContentBlock.objects.get(key=CHAVE_TERMOS)
        assert bloco.kind == ContentBlock.Kind.STRUCTURED
        assert "De novo." in html_renderizado()


# ===========================================================================
# 6. A prévia: o rascunho ou o gravado, nunca os controles do editor
# ===========================================================================


class TestPrevia:
    @pytest.mark.parametrize("rota", TODAS_AS_PREVIAS)
    def test_anonimo_vai_para_o_login(self, client, rota):
        resposta = client.get(rota)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    @pytest.mark.parametrize("rota", TODAS_AS_PREVIAS)
    def test_quem_so_ve_nao_alcanca_a_previa(self, leitora, rota):
        """A prévia é parte do editor -- exige editar, não só ver."""
        assert _cliente(leitora).get(rota).status_code == 403

    def test_get_mostra_o_que_esta_gravado(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Gravado de verdade.")

        assert "Gravado de verdade." in cliente.get(PREVIA_TERMOS).content.decode()

    def test_post_mostra_o_rascunho_ainda_nao_salvo(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Gravado de verdade.")

        resposta = cliente.post(PREVIA_TERMOS, {"blocos": json.dumps([paragrafo("Rascunho.")])})
        corpo = resposta.content.decode()

        assert "Rascunho." in corpo
        assert "Gravado de verdade." not in corpo

    def test_o_post_nao_grava_nada(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Original.")

        cliente.post(PREVIA_TERMOS, {"blocos": json.dumps([paragrafo("Rascunho.")])})

        assert gravado() == "Original."

    def test_a_previa_nao_mostra_controles_do_editor(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Texto.")

        corpo = cliente.get(PREVIA_TERMOS).content.decode()

        assert "data-editor-blocos" not in corpo
        assert "data-canvas" not in corpo
        assert "js/editor-blocos.js" not in corpo

    def test_perigoso_no_rascunho_tambem_e_sanitizado(self, cliente):
        bloco_perigoso = {"type": "html", "html": "<script>alert(1)</script><p>Ok</p>"}
        resposta = cliente.post(PREVIA_TERMOS, {"blocos": json.dumps([bloco_perigoso])})

        corpo = resposta.content.decode()
        assert "<script" not in corpo
        assert "<p>Ok</p>" in corpo

    def test_permite_ser_mostrada_num_iframe_do_proprio_site(self, cliente):
        assert cliente.get(PREVIA_TERMOS).headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_privacidade_na_previa_nunca_mostra_termos(self, cliente):
        publicar_simples(CHAVE_TERMOS, "Cláusula dos termos.")
        publicar_simples(CHAVE_PRIVACIDADE, "Cláusula da privacidade.")

        corpo = cliente.get(PREVIA_PRIVACIDADE).content.decode()

        assert "Cláusula da privacidade." in corpo
        assert "Cláusula dos termos." not in corpo


# ===========================================================================
# 7. As rotas públicas não mudaram
# ===========================================================================


class TestRotasPublicas:
    def test_termos_de_uso_continua_no_mesmo_endereco(self):
        assert TERMOS.endswith("/legal/termos-de-uso/")

    def test_privacidade_continua_no_mesmo_endereco(self):
        assert PRIVACIDADE.endswith("/legal/privacidade/")

    def test_as_duas_continuam_abrindo_com_texto_publicado(self, cliente):
        salvar(cliente, [paragrafo("Termos publicados.")], rota=EDITAR_TERMOS)
        salvar(cliente, [paragrafo("Privacidade publicada.")], rota=EDITAR_PRIVACIDADE)

        termos = Client().get(TERMOS)
        privacidade = Client().get(PRIVACIDADE)

        assert termos.status_code == 200
        assert "Termos publicados." in termos.content.decode()
        assert privacidade.status_code == 200
        assert "Privacidade publicada." in privacidade.content.decode()

    def test_sem_texto_continuam_respondendo_404(self):
        assert Client().get(TERMOS).status_code == 404
        assert Client().get(PRIVACIDADE).status_code == 404


# ===========================================================================
# 8. As duas listas: a do documento e a do rodapé
# ===========================================================================


class TestAsDuasListas:
    def test_o_rodape_continua_sem_titulo_de_documento_e_sem_imagem(self):
        limpo = rodape.sanitizar('<h2>T</h2><img src="/media/assets/a.png"><h3>Ok</h3>')

        assert limpo == "T<h3>Ok</h3>"

    def test_o_rodape_continua_com_os_atalhos(self):
        assert rodape.sanitizar('<a href="{url_termos}">T</a>') == '<a href="{url_termos}">T</a>'

    def test_o_documento_nao_aceita_desenho_inline(self):
        assert rodape.sanitizar_documento('<svg><path d="M0 0"/></svg><p>x</p>') == "<p>x</p>"

    @pytest.mark.parametrize(
        "endereco",
        [
            "https://fora.test/a.png",
            "//fora.test/a.png",
            "/media/assets/../../segredo.png",
            "/media/assets//a.png",
            "/media/letters/carta.pdf",
            "/media/assets/a.svg",
            "data:image/png;base64,AAAA",
            "javascript:alert(1)",
        ],
    )
    def test_imagem_fora_da_biblioteca_sai_inteira(self, endereco):
        assert rodape.sanitizar_documento(f'<p><img src="{endereco}" alt="x"></p>') == "<p></p>"

    def test_e_idempotente(self):
        uma = rodape.sanitizar_documento(
            '<h2 style="text-align:right">A</h2><img src="/media/assets/a.png" alt="b">'
        )

        assert rodape.sanitizar_documento(uma) == uma

    def test_o_unico_ponto_que_marca_como_seguro_continua_um(self):
        import pathlib

        fonte = pathlib.Path("apps/content/rodape.py").read_text(encoding="utf-8")

        assert fonte.count("mark_safe(") == 1
        assert "renderizar_documento" in fonte
