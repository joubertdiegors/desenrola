"""
`apps.content.blocos` -- o contrato de um documento legal em blocos.

O que esta suíte cobre, ISOLADA do Backoffice e da página pública (que
têm as suas próprias suítes, `test_documentos_legais_no_backoffice.py`
e `test_paginas_legais.py`): as FUNÇÕES PURAS deste módulo -- criar,
sanitizar, saber se há conteúdo, desenhar e migrar HTML antigo -- cada
uma testada diretamente, sem passar por uma rota.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que `sanitizar_bloco` aceite um valor fora da lista fechada** em
   qualquer campo -- tipo, âncora, largura, `href`, `id` de asset,
   entrelinha, espaço depois;
2. **Que o separador sozinho conte como conteúdo** (`blocos_tem_conteudo`);
3. **Que `renderizar_blocos` desenhe um bloco vazio** (imagem sem asset,
   tabela em branco, botão sem endereço) ou perca a sanitização de
   cada fragmento;
4. **Que a migração de HTML corrido perca conteúdo** -- o bug do `<hr>`
   que engolia o resto do documento (corrigido nesta rodada) é o
   exemplo concreto que esta suíte tranca.
"""

import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.content import blocos, rodape
from apps.content.models import Asset

pytestmark = pytest.mark.django_db

GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def _asset(nome="foto.gif", **extra):
    """Um Asset ativo, com o arquivo no mesmo padrão de `upload_to='assets/%Y/%m/'`."""
    return Asset.objects.create(
        kind=Asset.Kind.CONTENT,
        file=SimpleUploadedFile(nome, GIF, content_type="image/gif"),
        **extra,
    )


# ===========================================================================
# bloco_novo
# ===========================================================================


class TestBlocoNovo:
    @pytest.mark.parametrize("tipo", list(blocos.TIPOS_VALIDOS))
    def test_todo_tipo_do_catalogo_tem_um_bloco_em_branco(self, tipo):
        novo = blocos.bloco_novo(tipo)

        assert novo["type"] == tipo
        assert novo["id"]
        assert novo["mobile"] == {"visible": True}

    def test_tipo_desconhecido_explode(self):
        with pytest.raises(ValueError):
            blocos.bloco_novo("inexistente")

    def test_imagem_comeca_sem_asset_e_sem_ancora(self):
        novo = blocos.bloco_novo("image")

        assert novo["asset_id"] is None
        assert novo["desktop"] == {"anchor": "none", "width": 36}

    def test_tabela_comeca_com_duas_linhas_e_duas_colunas(self):
        novo = blocos.bloco_novo("table")

        assert novo["cabecalho"] is True
        assert novo["linhas"] == [["", ""], ["", ""]]


# ===========================================================================
# sanitizar_bloco
# ===========================================================================


class TestSanitizarBloco:
    def test_nao_e_dicionario_vira_none(self):
        assert blocos.sanitizar_bloco("texto") is None
        assert blocos.sanitizar_bloco(None) is None
        assert blocos.sanitizar_bloco(["type", "paragraph"]) is None

    def test_tipo_fora_da_lista_vira_none(self):
        assert blocos.sanitizar_bloco({"type": "video"}) is None
        assert blocos.sanitizar_bloco({}) is None

    def test_sem_id_ganha_um(self):
        limpo = blocos.sanitizar_bloco({"type": "separator"})

        assert limpo["id"]

    def test_id_e_cortado_em_40_caracteres(self):
        limpo = blocos.sanitizar_bloco({"type": "separator", "id": "x" * 100})

        assert len(limpo["id"]) == 40

    def test_mobile_ausente_ou_invalido_vira_visivel(self):
        assert blocos.sanitizar_bloco({"type": "separator"})["mobile"] == {"visible": True}
        assert blocos.sanitizar_bloco({"type": "separator", "mobile": "x"})["mobile"] == {
            "visible": True
        }

    def test_mobile_oculto_e_preservado(self):
        limpo = blocos.sanitizar_bloco({"type": "separator", "mobile": {"visible": False}})

        assert limpo["mobile"] == {"visible": False}

    def test_html_do_bloco_de_texto_e_sanitizado(self):
        limpo = blocos.sanitizar_bloco(
            {"type": "paragraph", "html": '<p onclick="x()">Oi</p><script>alert(1)</script>'}
        )

        assert limpo["html"] == "<p>Oi</p>"

    def test_bloco_tipo_html_preserva_o_proprio_campo_html(self):
        """
        A REGRESSÃO: `type: "html"` fica de fora de `TIPOS_DE_TEXTO` (não
        leva `TAG_EXTERNA`, é a válvula de escape) -- mas isso não pode
        significar que seu campo `html` nunca é sanitizado/preservado. A
        função inteira tinha esse buraco: um bloco HTML válido, ao
        passar por `sanitizar_bloco`, saía sem NENHUM campo `html`.
        """
        limpo = blocos.sanitizar_bloco({"type": "html", "html": "<div>Conteúdo real</div>"})

        assert limpo.get("html") == "<div>Conteúdo real</div>"

    def test_bloco_tipo_html_tambem_sanitiza_conteudo_perigoso(self):
        limpo = blocos.sanitizar_bloco(
            {"type": "html", "html": '<div onclick="x()">Oi</div><script>alert(1)</script>'}
        )

        assert limpo["html"] == "<div>Oi</div>"

    @pytest.mark.parametrize("espaco", blocos.ESPACAMENTOS_APOS)
    def test_todo_espacamento_da_lista_e_aceito(self, espaco):
        limpo = blocos.sanitizar_bloco({"type": "separator", "spacing_after": espaco})

        assert limpo["spacing_after"] == espaco

    def test_espacamento_zero_nao_e_tratado_como_ausente(self):
        """Um bug fácil: `if espaco:` descartaria 0 por ser 'falso' em Python."""
        limpo = blocos.sanitizar_bloco({"type": "separator", "spacing_after": 0})

        assert "spacing_after" in limpo
        assert limpo["spacing_after"] == 0

    def test_espacamento_fora_da_lista_e_omitido(self):
        limpo = blocos.sanitizar_bloco({"type": "separator", "spacing_after": 13})

        assert "spacing_after" not in limpo

    @pytest.mark.parametrize("altura", blocos.ALTURAS_DE_LINHA)
    def test_toda_entrelinha_da_lista_e_aceita(self, altura):
        limpo = blocos.sanitizar_bloco({"type": "paragraph", "line_height": altura})

        assert limpo["line_height"] == altura

    def test_entrelinha_fora_da_lista_e_omitida(self):
        limpo = blocos.sanitizar_bloco({"type": "paragraph", "line_height": "3"})

        assert "line_height" not in limpo

    # -- botão ---------------------------------------------------------

    def test_botao_com_endereco_valido(self):
        limpo = blocos.sanitizar_bloco({"type": "button", "href": "https://exemplo.test/"})

        assert limpo["href"] == "https://exemplo.test/"

    def test_botao_com_javascript_vira_vazio(self):
        limpo = blocos.sanitizar_bloco({"type": "button", "href": "javascript:alert(1)"})

        assert limpo["href"] == ""

    def test_botao_com_atalho_vira_vazio_documento_nao_tem_atalho(self):
        limpo = blocos.sanitizar_bloco({"type": "button", "href": "{url_termos}"})

        assert limpo["href"] == ""

    # -- imagem ----------------------------------------------------------

    def test_imagem_sem_desktop_cai_no_padrao(self):
        limpo = blocos.sanitizar_bloco({"type": "image", "asset_id": 1})

        assert limpo["desktop"] == {"anchor": "none", "width": 36}

    def test_imagem_com_ancora_invalida_vira_none(self):
        limpo = blocos.sanitizar_bloco(
            {"type": "image", "desktop": {"anchor": "diagonal", "width": 30}}
        )

        assert limpo["desktop"]["anchor"] == "none"

    @pytest.mark.parametrize("ancora", blocos.ANCORAS)
    def test_toda_ancora_da_lista_e_aceita(self, ancora):
        limpo = blocos.sanitizar_bloco({"type": "image", "desktop": {"anchor": ancora}})

        assert limpo["desktop"]["anchor"] == ancora

    def test_largura_fora_da_lista_arredonda_para_a_mais_proxima(self):
        limpo = blocos.sanitizar_bloco({"type": "image", "desktop": {"width": 34}})

        assert limpo["desktop"]["width"] == 36  # 34 está mais perto de 36 que de 30

    def test_largura_nao_numerica_cai_no_padrao(self):
        limpo = blocos.sanitizar_bloco({"type": "image", "desktop": {"width": "grande"}})

        assert limpo["desktop"]["width"] == 36

    def test_asset_id_nao_numerico_vira_none(self):
        limpo = blocos.sanitizar_bloco({"type": "image", "asset_id": "abc"})

        assert limpo["asset_id"] is None

    def test_alt_e_escapado_e_cortado(self):
        limpo = blocos.sanitizar_bloco({"type": "image", "alt": "<b>" + "a" * 300})

        assert "<b>" not in limpo["alt"]
        assert len(limpo["alt"]) <= 210  # 200 + o `&lt;b&gt;` escapado

    # -- galeria -----------------------------------------------------------

    def test_galeria_filtra_nao_numericos_e_limita_a_seis(self):
        limpo = blocos.sanitizar_bloco(
            {"type": "gallery", "asset_ids": [1, "x", 2, 3, 4, 5, 6, 7, 8]}
        )

        assert limpo["asset_ids"] == [1, 2, 3, 4, 5, 6]

    def test_galeria_sem_lista_vira_vazia(self):
        assert blocos.sanitizar_bloco({"type": "gallery"})["asset_ids"] == []

    # -- tabela --------------------------------------------------------

    def test_tabela_escapa_celulas_e_limita_tamanho(self):
        limpo = blocos.sanitizar_bloco(
            {"type": "table", "linhas": [["<script>x</script>", "b" * 500]]}
        )

        assert "<script>" not in limpo["linhas"][0][0]
        assert len(limpo["linhas"][0][1]) == 400

    def test_tabela_sem_linhas_cai_no_padrao(self):
        limpo = blocos.sanitizar_bloco({"type": "table", "linhas": "não é lista"})

        assert limpo["linhas"] == [["", ""], ["", ""]]

    def test_tabela_limita_linhas_e_colunas(self):
        linha_longa = list(range(20))
        limpo = blocos.sanitizar_bloco(
            {"type": "table", "linhas": [linha_longa for _ in range(50)]}
        )

        assert len(limpo["linhas"]) == 40
        assert len(limpo["linhas"][0]) == 12


# ===========================================================================
# sanitizar_blocos (a lista inteira)
# ===========================================================================


class TestSanitizarBlocos:
    def test_nao_e_lista_vira_vazia(self):
        assert blocos.sanitizar_blocos("não é lista") == []
        assert blocos.sanitizar_blocos(None) == []

    def test_descarta_itens_nao_reconheciveis_sem_estourar(self):
        limpos = blocos.sanitizar_blocos([{"type": "paragraph", "html": "Ok"}, "lixo", 123, None])

        assert len(limpos) == 1

    def test_limita_a_trezentos_blocos(self):
        muitos = [{"type": "separator"} for _ in range(400)]

        assert len(blocos.sanitizar_blocos(muitos)) == 300

    def test_corta_pelo_fim_quando_estoura_o_tamanho_maximo(self):
        enormes = [{"type": "paragraph", "html": "a" * 60_000} for _ in range(10)]

        limpos = blocos.sanitizar_blocos(enormes)

        assert len(json.dumps(limpos, ensure_ascii=False)) <= rodape.TAMANHO_MAXIMO_DO_DOCUMENTO
        assert len(limpos) < 10


# ===========================================================================
# blocos_tem_conteudo
# ===========================================================================


class TestTemConteudo:
    def test_lista_vazia_nao_tem_conteudo(self):
        assert blocos.blocos_tem_conteudo([]) is False

    def test_so_separador_nao_tem_conteudo(self):
        assert blocos.blocos_tem_conteudo([blocos.bloco_novo("separator")]) is False

    def test_paragrafo_com_texto_tem_conteudo(self):
        bloco = {**blocos.bloco_novo("paragraph"), "html": "Oi"}
        assert blocos.blocos_tem_conteudo([bloco]) is True

    def test_paragrafo_vazio_nao_tem_conteudo(self):
        bloco = {**blocos.bloco_novo("paragraph"), "html": "<br>"}
        assert blocos.blocos_tem_conteudo([bloco]) is False

    def test_imagem_com_asset_tem_conteudo_sem_asset_nao_tem(self):
        com = {**blocos.bloco_novo("image"), "asset_id": 1}
        sem = blocos.bloco_novo("image")

        assert blocos.blocos_tem_conteudo([com]) is True
        assert blocos.blocos_tem_conteudo([sem]) is False

    def test_galeria_com_imagens_tem_conteudo(self):
        cheia = {**blocos.bloco_novo("gallery"), "asset_ids": [1, 2]}
        vazia = blocos.bloco_novo("gallery")

        assert blocos.blocos_tem_conteudo([cheia]) is True
        assert blocos.blocos_tem_conteudo([vazia]) is False

    def test_tabela_com_texto_tem_conteudo_em_branco_nao_tem(self):
        cheia = {**blocos.bloco_novo("table"), "linhas": [["a", ""], ["", ""]]}
        vazia = {**blocos.bloco_novo("table"), "linhas": [["", ""], ["", ""]]}

        assert blocos.blocos_tem_conteudo([cheia]) is True
        assert blocos.blocos_tem_conteudo([vazia]) is False


# ===========================================================================
# renderizar_blocos
# ===========================================================================


class TestRenderizarBlocos:
    def test_lista_vazia_nao_desenha_nada(self):
        assert blocos.renderizar_blocos([]) == ""

    def test_paragrafo_titulo_e_citacao_ganham_a_tag_externa(self):
        html = blocos.renderizar_blocos([
            {**blocos.bloco_novo("paragraph"), "html": "P"},
            {**blocos.bloco_novo("heading"), "html": "H"},
            {**blocos.bloco_novo("quote"), "html": "Q"},
        ])

        assert "<p>P</p>" in html
        assert "<h2>H</h2>" in html
        assert "<blockquote>Q</blockquote>" in html

    def test_lista_usa_a_marcacao_gravada_direto(self):
        bloco = {**blocos.bloco_novo("list"), "html": "<ul><li>um</li></ul>"}
        html = blocos.renderizar_blocos([bloco])

        assert "<ul><li>um</li></ul>" in html

    def test_destaque_ganha_icone_e_o_vazio_nao_e_desenhado(self):
        cheio = blocos.renderizar_blocos([{**blocos.bloco_novo("highlight"), "html": "Atenção"}])
        vazio = blocos.renderizar_blocos([blocos.bloco_novo("highlight")])

        assert "legal-destaque-icone" in cheio
        assert "Atenção" in cheio
        assert vazio == ""

    def test_separador_vira_hr(self):
        assert "<hr>" in blocos.renderizar_blocos([blocos.bloco_novo("separator")])

    def test_botao_sem_endereco_nao_e_desenhado(self):
        assert blocos.renderizar_blocos([{**blocos.bloco_novo("button"), "html": "Clique"}]) == ""

    def test_botao_com_endereco_e_desenhado(self):
        html = blocos.renderizar_blocos([
            {**blocos.bloco_novo("button"), "html": "Clique", "href": "https://exemplo.test/"}
        ])

        assert '<a href="https://exemplo.test/">Clique</a>' in html

    def test_html_e_sanitizado_de_novo_ao_desenhar(self):
        """O banco não é confiável: mesmo já sanitizado uma vez, sanitiza de novo."""
        html = blocos.renderizar_blocos(
            [{**blocos.bloco_novo("html"), "html": '<p>Ok</p><script>alert(1)</script>'}]
        )

        assert "<script" not in html
        assert "<p>Ok</p>" in html

    def test_tabela_vazia_nao_e_desenhada(self):
        assert blocos.renderizar_blocos([blocos.bloco_novo("table")]) == ""

    def test_tabela_com_cabecalho_usa_th_na_primeira_linha(self):
        bloco = {**blocos.bloco_novo("table"), "linhas": [["Nome", "E-mail"], ["Ana", "a@x.com"]]}

        html = blocos.renderizar_blocos([bloco])

        assert "<th>Nome</th>" in html
        assert "<td>Ana</td>" in html

    def test_imagem_valida_e_desenhada_com_src_e_alt(self):
        asset = _asset()
        bloco = {**blocos.bloco_novo("image"), "asset_id": asset.pk, "alt": "Foto"}

        html = blocos.renderizar_blocos([bloco])

        assert f'src="{asset.file.url}"' in html
        assert 'alt="Foto"' in html

    def test_imagem_ancorada_ganha_float_e_largura(self):
        asset = _asset()
        bloco = {
            **blocos.bloco_novo("image"),
            "asset_id": asset.pk,
            "desktop": {"anchor": "right", "width": 40},
        }

        html = blocos.renderizar_blocos([bloco])

        assert "float:right" in html
        assert "width:40%" in html

    def test_galeria_desenha_cada_imagem_ativa(self):
        um, dois = _asset("um.gif"), _asset("dois.gif")
        bloco = {**blocos.bloco_novo("gallery"), "asset_ids": [um.pk, dois.pk]}

        html = blocos.renderizar_blocos([bloco])

        assert html.count("<img") == 2

    def test_asset_inativo_nao_aparece_na_galeria(self):
        ativo = _asset("ativo.gif")
        inativo = _asset("inativo.gif", is_active=False)
        bloco = {**blocos.bloco_novo("gallery"), "asset_ids": [ativo.pk, inativo.pk]}

        html = blocos.renderizar_blocos([bloco])

        assert html.count("<img") == 1

    def test_bloco_oculto_no_mobile_ganha_a_classe(self):
        bloco = {**blocos.bloco_novo("paragraph"), "html": "Oi", "mobile": {"visible": False}}

        html = blocos.renderizar_blocos([bloco])

        assert "legal-bloco-oculto-no-mobile" in html

    def test_entrelinha_e_espacamento_viram_estilo_no_envolucro(self):
        bloco = {
            **blocos.bloco_novo("paragraph"),
            "html": "Oi",
            "line_height": "2",
            "spacing_after": 32,
        }

        html = blocos.renderizar_blocos([bloco])

        assert 'style="line-height:2;margin-bottom:32px"' in html

    def test_sem_entrelinha_nem_espacamento_nao_ha_atributo_style_no_envolucro(self):
        bloco = {**blocos.bloco_novo("paragraph"), "html": "Oi"}

        html = blocos.renderizar_blocos([bloco])

        assert '<div class="legal-bloco legal-bloco-paragraph" data-bloco-tipo="paragraph">' in html

    def test_todo_bloco_desenhado_tem_a_classe_e_o_data_attr(self):
        bloco = {**blocos.bloco_novo("paragraph"), "html": "Oi"}

        html = blocos.renderizar_blocos([bloco])

        assert 'class="legal-bloco legal-bloco-paragraph"' in html
        assert 'data-bloco-tipo="paragraph"' in html


# ===========================================================================
# catalogo_para_o_menu
# ===========================================================================


class TestCatalogo:
    def test_agrupa_por_categoria_na_ordem_do_catalogo(self):
        grupos = blocos.catalogo_para_o_menu()

        categorias = [g["categoria"] for g in grupos]
        assert categorias == list(dict.fromkeys(str(c) for c, *_r in blocos.CATALOGO))

    def test_todo_item_tem_tipo_rotulo_descricao_e_icone(self):
        for grupo in blocos.catalogo_para_o_menu():
            for item in grupo["itens"]:
                assert item["tipo"] in blocos.TIPOS_VALIDOS
                assert item["rotulo"]
                assert item["descricao"]
                assert item["icone"].startswith("ph-")


# ===========================================================================
# migrar_html_para_blocos -- HTML corrido de antes, sem perder nada
# ===========================================================================


class TestMigracao:
    def test_html_vazio_vira_lista_vazia(self):
        assert blocos.migrar_html_para_blocos("") == []
        assert blocos.migrar_html_para_blocos("<p><br></p>") == []

    def test_separa_paragrafo_titulo_hr_e_lista_em_blocos_proprios(self):
        """
        A REGRESSÃO do `<hr>`: antes da correção, ele ficava aberto no
        divisor de nível zero e engolia tudo o que vinha depois -- este
        teste teria uma lista de 2 blocos (o `<p>` antes do `<hr>`, e um
        bloco `html` só com TUDO daí para frente) em vez de 4.
        """
        antigo = "<p>Antes.</p><h2>Título</h2><hr><ul><li>Depois</li></ul>"

        migrados = blocos.migrar_html_para_blocos(antigo)

        assert [b["type"] for b in migrados] == ["paragraph", "heading", "separator", "list"]
        assert migrados[0]["html"] == "Antes."
        assert migrados[1]["html"] == "Título"
        assert migrados[3]["html"] == "<ul><li>Depois</li></ul>"

    def test_blockquote_vira_bloco_de_citacao(self):
        migrados = blocos.migrar_html_para_blocos("<blockquote>Uma frase.</blockquote>")

        assert len(migrados) == 1
        assert migrados[0]["type"] == "quote"
        assert migrados[0]["html"] == "Uma frase."

    def test_paragrafo_so_com_imagem_vira_bloco_de_imagem(self, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        asset = _asset("convertida.gif")

        html_antigo = f'<p><img src="{asset.file.url}" alt="Legenda"></p>'
        migrados = blocos.migrar_html_para_blocos(html_antigo)

        assert len(migrados) == 1
        assert migrados[0]["type"] == "image"
        assert migrados[0]["asset_id"] == asset.pk
        assert migrados[0]["alt"] == "Legenda"

    def test_imagem_junto_com_texto_no_paragrafo_fica_embutida(self, settings, tmp_path):
        """Só a `<img>` SOZINHA no `<p>` vira bloco de imagem -- com texto junto, é parágrafo."""
        settings.MEDIA_ROOT = tmp_path
        asset = _asset("junto.gif")

        migrados = blocos.migrar_html_para_blocos(f'<p>Legenda: <img src="{asset.file.url}"></p>')

        assert len(migrados) == 1
        assert migrados[0]["type"] == "paragraph"
        assert "<img" in migrados[0]["html"]

    def test_imagem_de_fora_da_biblioteca_fica_embutida_num_paragrafo(self):
        """
        Sem `Asset` correspondente (arquivo apagado da biblioteca), não
        vira bloco de imagem -- mas a tag continua, embutida num
        parágrafo, nunca descartada silenciosamente.
        """
        html_sem_asset = '<p><img src="/media/assets/2020/01/sumida.png"></p>'
        migrados = blocos.migrar_html_para_blocos(html_sem_asset)

        assert len(migrados) == 1
        assert migrados[0]["type"] == "paragraph"
        assert "<img" in migrados[0]["html"]

    def test_imagem_sem_asset_no_meio_de_outros_blocos_nao_desaparece(self):
        """
        A REGRESSÃO específica: antes da correção, `_pedaco_para_bloco`
        devolvia `None` direto quando a imagem não resolvia um `Asset`
        -- e um pedaço no MEIO da lista que vira `None` é descartado
        pelo laço de `migrar_html_para_blocos` (só a lista INTEIRA vazia
        aciona o fallback), então os blocos vizinhos escondiam a perda.
        """
        antigo = '<p>Antes.</p><p><img src="/media/assets/2020/01/sumida.png"></p><p>Depois.</p>'

        migrados = blocos.migrar_html_para_blocos(antigo)

        assert [b["type"] for b in migrados] == ["paragraph", "paragraph", "paragraph"]
        assert migrados[0]["html"] == "Antes."
        assert "<img" in migrados[1]["html"]
        assert migrados[2]["html"] == "Depois."

    def test_tag_nao_reconhecida_vira_bloco_html_preservado(self):
        migrados = blocos.migrar_html_para_blocos('<div class="antigo">Conteúdo velho</div>')

        assert len(migrados) == 1
        assert migrados[0]["type"] == "html"
        assert "Conteúdo velho" in migrados[0]["html"]

    def test_nada_e_perdido_mesmo_no_pior_caso(self):
        """Texto solto sem NENHUMA tag ainda vira um bloco -- nunca desaparece."""
        migrados = blocos.migrar_html_para_blocos("Só texto solto, sem tag nenhuma.")

        assert len(migrados) == 1
        assert "Só texto solto" in migrados[0]["html"]

    def test_o_html_de_entrada_e_sanitizado_antes_de_dividir(self):
        migrados = blocos.migrar_html_para_blocos("<p>Ok</p><script>alert(1)</script>")

        assert len(migrados) == 1
        assert migrados[0]["html"] == "Ok"

    def test_a_lista_toda_e_um_documento_que_renderizar_blocos_aceita(self):
        """O resultado da migração é sempre um documento válido para render de novo."""
        antigo = "<h2>1</h2><p>Um</p><blockquote>Dois</blockquote><hr><ul><li>Três</li></ul>"

        migrados = blocos.migrar_html_para_blocos(antigo)
        desenhado = blocos.renderizar_blocos(migrados)

        assert "<h2>1</h2>" in desenhado
        assert "<p>Um</p>" in desenhado
        assert "<blockquote>Dois</blockquote>" in desenhado
        assert "<hr>" in desenhado
        assert "<ul><li>Três</li></ul>" in desenhado
