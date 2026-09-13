"""
Fundacao do editor estrutural (Etapa 3.1): contrato do layout, registros
de tipos e de fontes de dados, e o servico de manipulacao.

Sem banco na maior parte: `layout_schema`, `elements`, `datasources` e
`services/layout` sao codigo puro de proposito -- e o que permite
exercitar cada regra diretamente, sem passar por HTTP nem por modelo.
"""

import copy

import pytest
from django.core.exceptions import ValidationError

from apps.doctemplates import datasources, elements, layout_schema
from apps.doctemplates.services import layout as svc
from apps.doctemplates.services.layout import ElementoNaoEncontradoError


def texto(valor="Olá"):
    return {"kind": "text", "value": valor}


def campo(referencia="convidado.nome"):
    return {"kind": "field", "source": referencia}


def elemento(tipo="text", identificador="e1", **overrides):
    base = {
        "id": identificador,
        "type": tipo,
        "x": 10.0,
        "y": 20.0,
        "width": 100.0,
        "height": 15.0,
        "properties": {},
    }
    padroes = {
        "text": {"content": texto()},
        "rich_text": {"content": {"kind": "mixed", "parts": [texto("Je soussigné "), campo()]}},
        "number": {"content": campo("documento.numero"), "format": "0"},
        "image": {"source": {"kind": "asset", "asset_id": 3}},
        "qr_code": {"source": texto("https://exemplo.be")},
        "line": {"thickness": 0.75},
        "rectangle": {"border_width": 1.0},
        "table": {
            "columns": [{"width": 100.0}, {"width": 200.0}],
            "rows": [{"min_height": 18.0, "cells": [
                {"content": texto("Nome :")}, {"content": campo()},
            ]}],
        },
    }
    base["properties"] = copy.deepcopy(padroes.get(tipo, {}))
    base.update(overrides)
    return base


def layout(*elementos):
    return {"version": 1, "elements": list(elementos)}


# ===========================================================================
# 1. Contrato do layout
# ===========================================================================


class TestLayout:
    def test_layout_vazio_e_valido(self):
        vazio = layout_schema.layout_vazio()

        layout_schema.validate_layout(vazio)
        assert vazio == {"version": 1, "elements": []}

    def test_modelo_sem_desenho_e_valido(self):
        """`{}` e o estado dos quatro oficiais recem-semeados."""
        layout_schema.validate_layout({})

    def test_a_versao_e_declarada(self):
        assert layout_schema.VERSION == 1

    @pytest.mark.parametrize("versao", [0, 2, "1", None])
    def test_versao_desconhecida_e_recusada(self, versao):
        with pytest.raises(ValidationError):
            layout_schema.validate_layout({"version": versao, "elements": []})

    @pytest.mark.parametrize("valor", ["texto", [], 42])
    def test_o_layout_precisa_ser_um_objeto(self, valor):
        with pytest.raises(ValidationError):
            layout_schema.validate_layout(valor)

    def test_elements_precisa_ser_lista(self):
        with pytest.raises(ValidationError):
            layout_schema.validate_layout({"version": 1, "elements": {}})

    def test_layout_gigante_e_recusado(self):
        demais = [elemento(identificador=f"e{i}") for i in range(layout_schema.MAX_ELEMENTS + 1)]

        with pytest.raises(ValidationError, match="limite"):
            layout_schema.validate_layout(layout(*demais))

    def test_elemento_valido_passa(self):
        layout_schema.validate_layout(layout(elemento()))

    def test_ids_duplicados_sao_recusados(self):
        with pytest.raises(ValidationError, match="mais de um elemento"):
            layout_schema.validate_layout(
                layout(elemento(identificador="x"), elemento(identificador="x"))
            )

    @pytest.mark.parametrize("valor", ["", "   ", None, 42])
    def test_id_e_obrigatorio(self, valor):
        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(elemento(identificador=valor)))

    def test_tipo_desconhecido_e_recusado(self):
        with pytest.raises(ValidationError, match="Não existe o tipo"):
            layout_schema.validate_layout(layout(elemento(tipo="video")))

    @pytest.mark.parametrize("chave", ["x", "y", "width", "height"])
    def test_coordenada_nao_numerica_e_recusada(self, chave):
        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(elemento(**{chave: "10"})))

    @pytest.mark.parametrize("chave", ["width", "height"])
    def test_dimensao_negativa_e_recusada(self, chave):
        with pytest.raises(ValidationError, match="não pode ser negativo"):
            layout_schema.validate_layout(layout(elemento(**{chave: -1.0})))

    def test_booleano_nao_passa_por_coordenada(self):
        """`True` é `1` em Python -- não pode virar posição."""
        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(elemento(x=True)))

    @pytest.mark.parametrize("valor", [float("nan"), float("inf")])
    def test_coordenada_nao_finita_e_recusada(self, valor):
        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(elemento(x=valor)))

    def test_casas_decimais_sao_preservadas(self):
        preciso = elemento(x=72.3456, y=120.9876, width=400.125, height=13.5)

        layout_schema.validate_layout(layout(preciso))

        assert preciso["x"] == 72.3456
        assert preciso["width"] == 400.125

    def test_elemento_fora_da_pagina_e_aceito(self):
        """Recusar aqui faria o editor perder trabalho no meio de um arrasto."""
        layout_schema.validate_layout(layout(elemento(x=-50.0, y=5000.0)))

    def test_dimensao_zero_e_aceita(self):
        """Uma linha horizontal tem altura zero -- e legitimo."""
        layout_schema.validate_layout(layout(elemento(tipo="line", height=0.0)))

    def test_validar_nao_modifica_o_layout(self):
        original = layout(elemento(), elemento(tipo="table", identificador="t"))
        antes = copy.deepcopy(original)

        layout_schema.validate_layout(original)

        assert original == antes


# ===========================================================================
# 2. Propriedades por tipo
# ===========================================================================


class TestPropriedades:
    @pytest.mark.parametrize("tipo", list(elements.codigos()))
    def test_todo_tipo_registrado_tem_um_exemplo_valido(self, tipo):
        layout_schema.validate_layout(layout(elemento(tipo)))

    def test_propriedade_obrigatoria_ausente_e_recusada(self):
        el = elemento("text")
        del el["properties"]["content"]

        with pytest.raises(ValidationError, match="precisa da propriedade"):
            layout_schema.validate_layout(layout(el))

    def test_propriedade_desconhecida_e_recusada(self):
        el = elemento("line")
        el["properties"]["cor_favorita"] = "azul"

        with pytest.raises(ValidationError, match="não aceita"):
            layout_schema.validate_layout(layout(el))

    def test_propriedades_opcionais_podem_faltar(self):
        el = elemento("text")
        el["properties"] = {"content": texto()}

        layout_schema.validate_layout(layout(el))

    # --- texto -------------------------------------------------------------

    @pytest.mark.parametrize(
        "chave, valor",
        [
            ("align", "meio-ish"),
            ("font_weight", "black"),
            ("font_style", "oblique"),
            ("text_decoration", "blink"),
            ("white_space", "wrap"),
            ("overflow", "scroll"),
            ("font_family", "Comic Sans MS"),
        ],
    )
    def test_escolha_fora_do_vocabulario_e_recusada(self, chave, valor):
        el = elemento("text")
        el["properties"][chave] = valor

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    @pytest.mark.parametrize("valor", [0, -1])
    def test_tamanho_de_fonte_nao_positivo_e_recusado(self, valor):
        el = elemento("text")
        el["properties"]["font_size"] = valor

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    @pytest.mark.parametrize("cor", ["preto", "#fff", "rgb(0,0,0)", "#gggggg", ""])
    def test_cor_fora_do_formato_e_recusada(self, cor):
        el = elemento("text")
        el["properties"]["color"] = cor

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    def test_cor_hexadecimal_e_aceita(self):
        el = elemento("text")
        el["properties"]["color"] = "#1A5FD6"

        layout_schema.validate_layout(layout(el))

    def test_padding_e_uma_caixa_de_quatro_lados(self):
        el = elemento("text")
        el["properties"]["padding"] = {"top": 2, "right": 4, "bottom": 2, "left": 4}

        layout_schema.validate_layout(layout(el))

    def test_padding_negativo_e_recusado(self):
        el = elemento("text")
        el["properties"]["padding"] = {"top": -1, "right": 0, "bottom": 0, "left": 0}

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    # --- numero ------------------------------------------------------------

    def test_number_aceita_campo_e_formato(self):
        el = elemento("number")
        el["properties"]["format"] = "#,##0.00"

        layout_schema.validate_layout(layout(el))

    def test_number_nao_aceita_conteudo_misto(self):
        el = elemento("number")
        el["properties"]["content"] = {"kind": "mixed", "parts": [texto()]}

        with pytest.raises(ValidationError, match="não aceita conteúdo misto"):
            layout_schema.validate_layout(layout(el))

    # --- imagem ------------------------------------------------------------

    def test_imagem_referencia_um_asset(self):
        layout_schema.validate_layout(layout(elemento("image")))

    def test_imagem_com_asset_invalido_e_recusada(self):
        el = elemento("image")
        el["properties"]["source"] = {"kind": "asset", "asset_id": -1}

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    def test_imagem_nao_guarda_bytes_no_json(self):
        el = elemento("image")

        layout_schema.validate_layout(layout(el))

        assert set(el["properties"]["source"]) == {"kind", "asset_id"}

    @pytest.mark.parametrize("fit", ["contain", "cover", "fill"])
    def test_modos_de_ajuste(self, fit):
        el = elemento("image")
        el["properties"]["fit"] = fit

        layout_schema.validate_layout(layout(el))

    def test_preserve_aspect_ratio_precisa_ser_booleano(self):
        el = elemento("image")
        el["properties"]["preserve_aspect_ratio"] = "sim"

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    # --- QR ----------------------------------------------------------------

    @pytest.mark.parametrize("nivel", ["L", "M", "Q", "H"])
    def test_os_quatro_niveis_de_correcao(self, nivel):
        el = elemento("qr_code")
        el["properties"]["error_correction"] = nivel

        layout_schema.validate_layout(layout(el))

    def test_nivel_de_correcao_desconhecido_e_recusado(self):
        el = elemento("qr_code")
        el["properties"]["error_correction"] = "Z"

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    def test_qr_pode_vir_de_um_campo(self):
        el = elemento("qr_code")
        el["properties"]["source"] = campo("documento.numero")

        layout_schema.validate_layout(layout(el))

    def test_margem_do_qr_nao_pode_ser_negativa(self):
        el = elemento("qr_code")
        el["properties"]["margin"] = -1

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    # --- linha e retangulo -------------------------------------------------

    @pytest.mark.parametrize("estilo", ["solid", "dashed", "dotted"])
    def test_estilos_de_linha(self, estilo):
        el = elemento("line")
        el["properties"]["style"] = estilo

        layout_schema.validate_layout(layout(el))

    def test_espessura_de_linha_nao_positiva_e_recusada(self):
        el = elemento("line")
        el["properties"]["thickness"] = 0

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    def test_retangulo_sem_preenchimento_e_valido(self):
        el = elemento("rectangle")
        el["properties"]["fill_color"] = None

        layout_schema.validate_layout(layout(el))

    def test_retangulo_com_preenchimento_invalido_e_recusado(self):
        el = elemento("rectangle")
        el["properties"]["fill_color"] = "azul"

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    def test_raio_negativo_e_recusado(self):
        el = elemento("rectangle")
        el["properties"]["radius"] = -2

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    # --- tabela ------------------------------------------------------------

    def test_tabela_com_colunas_e_linhas(self):
        layout_schema.validate_layout(layout(elemento("table")))

    def test_coluna_com_largura_invalida_e_recusada(self):
        el = elemento("table")
        el["properties"]["columns"][0]["width"] = 0

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    def test_linha_com_numero_errado_de_celulas_e_recusada(self):
        el = elemento("table")
        el["properties"]["rows"][0]["cells"] = [{"content": texto()}]

        with pytest.raises(ValidationError, match="células"):
            layout_schema.validate_layout(layout(el))

    def test_celula_pode_referenciar_um_campo(self):
        el = elemento("table")
        el["properties"]["rows"][0]["cells"][1]["content"] = campo("anfitriao.cidade")

        layout_schema.validate_layout(layout(el))

    def test_celula_com_campo_inexistente_e_recusada(self):
        el = elemento("table")
        el["properties"]["rows"][0]["cells"][1]["content"] = campo("convidado.fantasma")

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    def test_tabela_sem_linhas_e_valida(self):
        el = elemento("table")
        el["properties"]["rows"] = []

        layout_schema.validate_layout(layout(el))


# ===========================================================================
# 3. Conteudo estrutural e campos dinamicos
# ===========================================================================


class TestConteudoEstrutural:
    def test_texto_fixo(self):
        layout_schema.validar_conteudo(texto("Je soussigné"), "c")

    def test_campo_valido(self):
        layout_schema.validar_conteudo(campo("anfitriao.endereco"), "c")

    @pytest.mark.parametrize(
        "referencia",
        ["convidado.fantasma", "inexistente.nome", "nome", "a.b.c", "", "convidado."],
    )
    def test_referencia_invalida_e_recusada(self, referencia):
        with pytest.raises(ValidationError):
            layout_schema.validar_conteudo({"kind": "field", "source": referencia}, "c")

    def test_forma_desconhecida_e_recusada(self):
        with pytest.raises(ValidationError, match="forma desconhecida"):
            layout_schema.validar_conteudo({"kind": "placeholder", "value": "x"}, "c")

    def test_conteudo_misto(self):
        misto = {
            "kind": "mixed",
            "parts": [
                texto("Je soussigné "),
                campo("convidado.nome"),
                texto(", domicilié à "),
                campo("anfitriao.endereco"),
            ],
        }

        layout_schema.validar_conteudo(misto, "c", permite_misto=True)

    def test_conteudo_misto_so_onde_o_tipo_aceita(self):
        misto = {"kind": "mixed", "parts": [texto()]}

        with pytest.raises(ValidationError, match="não aceita conteúdo misto"):
            layout_schema.validar_conteudo(misto, "c", permite_misto=False)

    def test_misto_aninhado_e_recusado(self):
        misto = {"kind": "mixed", "parts": [{"kind": "mixed", "parts": [texto()]}]}

        with pytest.raises(ValidationError):
            layout_schema.validar_conteudo(misto, "c", permite_misto=True)

    def test_rich_text_aceita_misto(self):
        layout_schema.validate_layout(layout(elemento("rich_text")))

    def test_text_simples_nao_aceita_misto(self):
        el = elemento("text")
        el["properties"]["content"] = {"kind": "mixed", "parts": [texto()]}

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(layout(el))

    def test_nenhum_placeholder_de_string(self):
        """
        Campo dinamico e estrutura, nao `{{nome}}` dentro de um texto.
        Uma string com chaves e texto literal, e nada mais.
        """
        el = elemento("text")
        el["properties"]["content"] = texto("{{convidado.nome}}")

        layout_schema.validate_layout(layout(el))
        assert el["properties"]["content"]["kind"] == "text"

    def test_referencias_usadas_no_layout(self):
        documento = layout(
            elemento("rich_text", "r"),
            elemento("table", "t"),
            elemento("qr_code", "q"),
        )

        usadas = layout_schema.referencias_usadas(documento)

        assert "convidado.nome" in usadas  # do rich_text e da celula
        assert usadas <= datasources.todas_as_referencias()

    def test_referencias_usadas_num_layout_vazio(self):
        assert layout_schema.referencias_usadas({}) == set()


# ===========================================================================
# 4. Registro de fontes de dados
# ===========================================================================


class TestFontesDeDados:
    NAMESPACES = ("documento", "convidado", "anfitriao", "calculado")

    @pytest.mark.parametrize("code", NAMESPACES)
    def test_os_quatro_namespaces_existem(self, code):
        assert datasources.fonte(code).code == code

    @pytest.mark.parametrize(
        "referencia",
        [
            "documento.numero", "documento.data",
            "convidado.nome", "convidado.nacionalidade",
            "convidado.data_nascimento", "convidado.passaporte",
            "anfitriao.nome", "anfitriao.endereco", "anfitriao.cidade",
            "anfitriao.telefone", "anfitriao.email",
            "calculado.data_documento",
        ],
    )
    def test_os_campos_pedidos_pela_especificacao_existem(self, referencia):
        assert datasources.referencia_valida(referencia)

    def test_namespace_inexistente_e_rejeitado(self):
        with pytest.raises(datasources.FonteDesconhecidaError):
            datasources.validar_referencia("empresa.cnpj")

    def test_campo_inexistente_e_rejeitado(self):
        with pytest.raises(datasources.CampoDesconhecidoError):
            datasources.validar_referencia("convidado.altura")

    @pytest.mark.parametrize("referencia", ["nome", "a.b.c", "", ".", "convidado.", 42])
    def test_forma_invalida_e_rejeitada(self, referencia):
        with pytest.raises(datasources.ReferenciaInvalidaError):
            datasources.dividir(referencia)

    def test_dividir_uma_referencia(self):
        assert datasources.dividir("convidado.nome") == ("convidado", "nome")

    def test_todas_as_referencias_tem_a_forma_completa(self):
        for referencia in datasources.todas_as_referencias():
            assert datasources.referencia_valida(referencia)
            assert "." in referencia

    def test_o_registro_e_extensivel(self):
        """Compatibilidade futura: `empresa.*` entra sem tocar em mais nada."""
        empresa = datasources.FonteDeDados(
            code="empresa", label="Empresa",
            campos=(datasources.Campo("cnpj", "CNPJ"),),
        )
        try:
            datasources.registrar_fonte(empresa)

            assert datasources.referencia_valida("empresa.cnpj")
            assert not datasources.referencia_valida("empresa.inexistente")
            # e o layout passa a aceitar a referencia nova
            el = elemento("text")
            el["properties"]["content"] = campo("empresa.cnpj")
            layout_schema.validate_layout(layout(el))
        finally:
            datasources.remover_fonte("empresa")

        assert not datasources.referencia_valida("empresa.cnpj")

    def test_registrar_duas_vezes_e_recusado(self):
        with pytest.raises(ValueError, match="já está registrada"):
            datasources.registrar_fonte(
                datasources.FonteDeDados(code="convidado", label="Outro")
            )

    def test_formato_para_o_editor(self):
        grupos = datasources.para_o_editor()
        por_code = {g["code"]: g for g in grupos}

        assert set(self.NAMESPACES) <= set(por_code)
        campos = por_code["convidado"]["fields"]
        assert {"reference", "key", "label", "kind"} <= set(campos[0])
        assert por_code["convidado"]["label"] == "Convidado"
        assert campos[0]["reference"] == "convidado.nome"


# ===========================================================================
# 5. Registro de tipos de elemento
# ===========================================================================


class TestRegistroDeTipos:
    ESPERADOS = (
        "text", "rich_text", "number", "image", "qr_code", "table", "line", "rectangle",
    )

    @pytest.mark.parametrize("code", ESPERADOS)
    def test_todos_os_tipos_da_especificacao_estao_registrados(self, code):
        assert elements.tipo(code).code == code

    def test_nao_ha_tipos_alem_dos_previstos(self):
        assert set(elements.codigos()) == set(self.ESPERADOS)

    def test_tipo_desconhecido_levanta_erro_claro(self):
        with pytest.raises(elements.TipoDesconhecidoError, match="Disponíveis"):
            elements.tipo("video")

    @pytest.mark.parametrize("code", ESPERADOS)
    def test_todo_tipo_tem_metadados_para_a_ui(self, code):
        t = elements.tipo(code)

        assert t.label
        assert t.categoria in (elements.CONTEUDO, elements.GRAFICO)
        assert t.propriedades

    def test_categorias(self):
        conteudo = {t.code for t in elements.tipos() if t.categoria == elements.CONTEUDO}
        grafico = {t.code for t in elements.tipos() if t.categoria == elements.GRAFICO}

        assert conteudo == {"text", "rich_text", "number", "table"}
        assert grafico == {"image", "qr_code", "line", "rectangle"}

    def test_so_rich_text_aceita_conteudo_misto(self):
        mistos = {t.code for t in elements.tipos() if t.aceita_conteudo_misto}

        assert mistos == {"rich_text"}

    @pytest.mark.parametrize("code", ESPERADOS)
    def test_os_padroes_de_cada_tipo_produzem_elemento_valido(self, code):
        """
        Um padrao que o validador recusasse daria um elemento impossivel
        de salvar assim que criado.
        """
        novo = svc.criar_elemento(code, id="x")

        layout_schema.validate_layout(layout(novo))

    def test_padroes_nao_compartilham_memoria_entre_elementos(self):
        a = svc.criar_elemento("text", id="a")
        b = svc.criar_elemento("text", id="b")

        a["properties"]["padding"]["top"] = 99

        assert b["properties"]["padding"]["top"] == 0

    def test_propriedades_de_texto_cobrem_a_especificacao(self):
        nomes = set(elements.tipo("text").nomes_das_propriedades)

        assert {
            "content", "font_family", "font_size", "font_weight", "font_style",
            "text_decoration", "color", "align", "line_height", "letter_spacing",
            "padding", "white_space", "language",
        } <= nomes

    def test_formato_para_o_editor(self):
        catalogo = {t["code"]: t for t in elements.para_o_editor()}

        assert set(catalogo) == set(self.ESPERADOS)
        propriedade = catalogo["line"]["properties"][0]
        assert {"name", "label", "kind", "required", "default", "options"} <= set(propriedade)

    def test_o_registro_e_extensivel(self):
        novo = elements.TipoDeElemento(
            code="barcode", label="Código de barras", categoria=elements.GRAFICO,
            propriedades=(elements.Propriedade("source", "Conteúdo", "conteudo",
                                               obrigatoria=True, padrao={"kind": "text",
                                                                         "value": ""}),),
        )
        try:
            elements.registrar_tipo(novo)

            el = elemento("barcode")
            el["properties"] = {"source": texto("123")}
            layout_schema.validate_layout(layout(el))
        finally:
            elements.remover_tipo("barcode")

        with pytest.raises(elements.TipoDesconhecidoError):
            elements.tipo("barcode")


# ===========================================================================
# 6. Servico: operacoes sobre elementos
# ===========================================================================


class TestOperacoes:
    def test_criar_layout(self):
        assert svc.criar_layout() == {"version": 1, "elements": []}

    def test_adicionar_elemento(self):
        novo = svc.adicionar_elemento(svc.criar_layout(), elemento())

        assert len(novo["elements"]) == 1
        assert novo["elements"][0]["id"] == "e1"

    def test_adicionar_a_um_layout_vazio_de_modelo_novo(self):
        """Os oficiais tem `layout = {}`: acrescentar tem de funcionar."""
        novo = svc.adicionar_elemento({}, elemento())

        assert novo["version"] == 1
        assert len(novo["elements"]) == 1

    def test_adicionar_com_id_repetido_gera_outro(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento(identificador="x"))

        novo = svc.adicionar_elemento(base, elemento(identificador="x"))

        ids = [e["id"] for e in novo["elements"]]
        assert len(set(ids)) == 2

    def test_adicionar_sem_id_gera_um(self):
        el = elemento()
        del el["id"]

        novo = svc.adicionar_elemento(svc.criar_layout(), el)

        assert novo["elements"][0]["id"]

    def test_obter_elemento(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento(identificador="alvo"))

        assert svc.obter_elemento(base, "alvo")["id"] == "alvo"

    def test_obter_devolve_copia(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        obtido = svc.obter_elemento(base, "e1")
        obtido["properties"]["content"]["value"] = "mexido"

        assert base["elements"][0]["properties"]["content"]["value"] == "Olá"

    def test_existe_elemento(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        assert svc.existe_elemento(base, "e1")
        assert not svc.existe_elemento(base, "outro")

    def test_atualizar_elemento(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        novo = svc.atualizar_elemento(base, "e1", {"properties": {"font_size": 14.0}})

        assert novo["elements"][0]["properties"]["font_size"] == 14.0

    def test_atualizar_mescla_as_propriedades(self):
        """Mudar a cor nao pode apagar o tamanho da fonte."""
        base = svc.adicionar_elemento(
            svc.criar_layout(), svc.criar_elemento("text", id="e1")
        )

        novo = svc.atualizar_elemento(base, "e1", {"properties": {"color": "#ff0000"}})

        propriedades = novo["elements"][0]["properties"]
        assert propriedades["color"] == "#ff0000"
        assert propriedades["font_size"] == 11.0
        assert "content" in propriedades

    def test_atualizar_valida_o_resultado(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        with pytest.raises(ValidationError):
            svc.atualizar_elemento(base, "e1", {"properties": {"font_size": -5}})

    def test_atualizar_nao_deixa_trocar_o_id(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        with pytest.raises(ValueError, match="não pode ser alterado"):
            svc.atualizar_elemento(base, "e1", {"id": "outro"})

    def test_remover_elemento(self):
        base = svc.adicionar_elemento(
            svc.adicionar_elemento(svc.criar_layout(), elemento(identificador="a")),
            elemento(identificador="b"),
        )

        novo = svc.remover_elemento(base, "a")

        assert [e["id"] for e in novo["elements"]] == ["b"]

    def test_mover_elemento(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        novo = svc.mover_elemento(base, "e1", 72.3456, 120.9876)

        assert novo["elements"][0]["x"] == 72.3456
        assert novo["elements"][0]["y"] == 120.9876

    def test_redimensionar_elemento(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        novo = svc.redimensionar_elemento(base, "e1", 400.125, 13.5)

        assert novo["elements"][0]["width"] == 400.125
        assert novo["elements"][0]["height"] == 13.5

    def test_redimensionar_para_negativo_e_recusado(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        with pytest.raises(ValidationError):
            svc.redimensionar_elemento(base, "e1", -10, 10)

    def test_duplicar_elemento(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        novo, novo_id = svc.duplicar_elemento(base, "e1")

        assert len(novo["elements"]) == 2
        assert novo_id != "e1"

    def test_duplicar_gera_id_novo_e_desloca(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        novo, novo_id = svc.duplicar_elemento(base, "e1")
        copia = svc.obter_elemento(novo, novo_id)

        assert copia["x"] == 20.0  # 10 + deslocamento
        assert copia["y"] == 30.0
        assert copia["properties"] == base["elements"][0]["properties"]

    def test_duplicar_faz_copia_profunda(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento("table", "t"))

        novo, novo_id = svc.duplicar_elemento(base, "t")
        indice = [e["id"] for e in novo["elements"]].index(novo_id)
        novo["elements"][indice]["properties"]["columns"][0]["width"] = 999

        original = [e for e in novo["elements"] if e["id"] == "t"][0]
        assert original["properties"]["columns"][0]["width"] == 100.0

    def test_duplicar_a_copia_de_novo(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        um, id_um = svc.duplicar_elemento(base, "e1")
        dois, id_dois = svc.duplicar_elemento(um, id_um)

        ids = [e["id"] for e in dois["elements"]]
        assert len(set(ids)) == 3

    @pytest.mark.parametrize(
        "operacao",
        [
            lambda base: svc.obter_elemento(base, "fantasma"),
            lambda base: svc.atualizar_elemento(base, "fantasma", {}),
            lambda base: svc.remover_elemento(base, "fantasma"),
            lambda base: svc.mover_elemento(base, "fantasma", 1, 1),
            lambda base: svc.redimensionar_elemento(base, "fantasma", 1, 1),
            lambda base: svc.duplicar_elemento(base, "fantasma"),
            lambda base: svc.trazer_para_frente(base, "fantasma"),
            lambda base: svc.enviar_para_tras(base, "fantasma"),
        ],
    )
    def test_elemento_inexistente_levanta_erro_especifico(self, operacao):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento())

        with pytest.raises(ElementoNaoEncontradoError, match="fantasma"):
            operacao(base)

    def test_a_mensagem_de_erro_lista_os_ids_existentes(self):
        base = svc.adicionar_elemento(svc.criar_layout(), elemento(identificador="a"))

        with pytest.raises(ElementoNaoEncontradoError, match="a"):
            svc.remover_elemento(base, "fantasma")


# ===========================================================================
# 7. Imutabilidade
# ===========================================================================


class TestImutabilidade:
    @pytest.fixture
    def base(self):
        documento = svc.criar_layout()
        documento = svc.adicionar_elemento(documento, elemento("text", "a"))
        return svc.adicionar_elemento(documento, elemento("table", "b"))

    @pytest.mark.parametrize(
        "operacao",
        [
            lambda base: svc.adicionar_elemento(base, elemento(identificador="novo")),
            lambda base: svc.atualizar_elemento(base, "a", {"properties": {"font_size": 20.0}}),
            lambda base: svc.remover_elemento(base, "a"),
            lambda base: svc.mover_elemento(base, "a", 1, 1),
            lambda base: svc.redimensionar_elemento(base, "a", 5, 5),
            lambda base: svc.duplicar_elemento(base, "a"),
            lambda base: svc.trazer_para_frente(base, "a"),
            lambda base: svc.enviar_para_tras(base, "b"),
            lambda base: svc.mover_para_frente(base, "a"),
            lambda base: svc.mover_para_tras(base, "b"),
        ],
    )
    def test_nenhuma_operacao_altera_o_original(self, base, operacao):
        antes = copy.deepcopy(base)

        operacao(base)

        assert base == antes

    def test_o_resultado_nao_compartilha_estrutura_com_a_entrada(self, base):
        novo = svc.mover_elemento(base, "a", 99, 99)

        assert novo["elements"] is not base["elements"]
        assert novo["elements"][1]["properties"] is not base["elements"][1]["properties"]

    def test_alterar_o_resultado_nao_alcanca_a_entrada(self, base):
        novo = svc.atualizar_elemento(base, "b", {"properties": {"border_width": 2.0}})

        novo["elements"][1]["properties"]["columns"][0]["width"] = 1
        novo["elements"][0]["properties"]["content"]["value"] = "mexido"

        assert base["elements"][1]["properties"]["columns"][0]["width"] == 100.0
        assert base["elements"][0]["properties"]["content"]["value"] == "Olá"

    def test_alterar_a_entrada_depois_nao_alcanca_o_resultado(self, base):
        novo = svc.mover_elemento(base, "a", 1, 1)

        base["elements"][0]["properties"]["content"]["value"] = "na entrada"

        assert novo["elements"][0]["properties"]["content"]["value"] == "Olá"

    def test_criar_elemento_nao_compartilha_os_padroes_do_registro(self):
        el = svc.criar_elemento("table", id="x")
        el["properties"]["columns"].append({"width": 10})

        assert elements.tipo("table").propriedade("columns").padrao == []


# ===========================================================================
# 8. Camadas
# ===========================================================================


class TestCamadas:
    @pytest.fixture
    def base(self):
        documento = svc.criar_layout()
        for identificador in ("a", "b", "c"):
            documento = svc.adicionar_elemento(documento, elemento(identificador=identificador))
        return documento

    def _ordem(self, documento):
        return [e["id"] for e in documento["elements"]]

    def test_a_ordem_da_lista_e_a_ordem_de_desenho(self, base):
        assert self._ordem(base) == ["a", "b", "c"]

    def test_nao_ha_z_index(self, base):
        """Uma fonte de verdade so para a camada: a posicao na lista."""
        for el in base["elements"]:
            assert "z_index" not in el

    def test_trazer_para_frente(self, base):
        assert self._ordem(svc.trazer_para_frente(base, "a")) == ["b", "c", "a"]

    def test_enviar_para_tras(self, base):
        assert self._ordem(svc.enviar_para_tras(base, "c")) == ["c", "a", "b"]

    def test_mover_uma_posicao_para_frente(self, base):
        assert self._ordem(svc.mover_para_frente(base, "a")) == ["b", "a", "c"]

    def test_mover_uma_posicao_para_tras(self, base):
        assert self._ordem(svc.mover_para_tras(base, "c")) == ["a", "c", "b"]

    def test_trazer_para_frente_quem_ja_esta_na_frente(self, base):
        assert self._ordem(svc.trazer_para_frente(base, "c")) == ["a", "b", "c"]

    def test_enviar_para_tras_quem_ja_esta_atras(self, base):
        assert self._ordem(svc.enviar_para_tras(base, "a")) == ["a", "b", "c"]

    def test_mover_para_frente_no_topo_nao_muda(self, base):
        assert self._ordem(svc.mover_para_frente(base, "c")) == ["a", "b", "c"]

    def test_mover_para_tras_no_fundo_nao_muda(self, base):
        assert self._ordem(svc.mover_para_tras(base, "a")) == ["a", "b", "c"]

    def test_adicionar_poe_por_cima(self, base):
        novo = svc.adicionar_elemento(base, elemento(identificador="d"))

        assert self._ordem(novo)[-1] == "d"

    def test_duplicar_poe_a_copia_por_cima(self, base):
        novo, novo_id = svc.duplicar_elemento(base, "a")

        assert self._ordem(novo)[-1] == novo_id

    def test_reordenar_preserva_todos_os_elementos(self, base):
        novo = svc.enviar_para_tras(svc.trazer_para_frente(base, "a"), "b")

        assert sorted(self._ordem(novo)) == ["a", "b", "c"]

    def test_elementos_em_ordem_de_desenho_devolve_copia(self, base):
        lista = svc.elementos_em_ordem_de_desenho(base)
        lista[0]["x"] = 999

        assert base["elements"][0]["x"] == 10.0


# ===========================================================================
# 9. Compatibilidade com DocumentTemplate
# ===========================================================================


@pytest.mark.django_db
class TestCompatibilidadeComOModelo:
    def test_os_quatro_oficiais_continuam_validos(self):
        from apps.doctemplates.models import DocumentTemplate

        oficiais = DocumentTemplate.objects.filter(is_system=True)

        assert oficiais.count() == 4
        for modelo in oficiais:
            assert modelo.layout == {}
            modelo.full_clean()

    def test_um_modelo_aceita_o_layout_novo(self, db):
        from apps.doctemplates.models import DocumentTemplate, DocumentType

        tipo = DocumentType.objects.create(code="t", name="T", page={"unit": "pt"})
        modelo = DocumentTemplate(
            type=tipo, name="M", slug="m", language="pt",
            layout=svc.adicionar_elemento(svc.criar_layout(), elemento()),
        )

        modelo.full_clean()
        modelo.save()
        modelo.refresh_from_db()

        assert modelo.layout["elements"][0]["id"] == "e1"

    def test_um_modelo_recusa_layout_invalido(self, db):
        from apps.doctemplates.models import DocumentTemplate, DocumentType

        tipo = DocumentType.objects.create(code="t2", name="T", page={"unit": "pt"})
        modelo = DocumentTemplate(
            type=tipo, name="M", slug="m2", language="pt",
            layout=layout(elemento(tipo="video")),
        )

        with pytest.raises(ValidationError):
            modelo.full_clean()

    def test_os_dois_contratos_sao_mesmo_independentes(self):
        """
        `visual_schema` (legado) e `layout_schema` (novo) descrevem
        formatos diferentes, e cada um recusa o do outro. E o que garante
        que ninguem confunda os dois enquanto as duas arquiteturas
        convivem.
        """
        from apps.doctemplates import visual_schema

        formato_antigo = {
            "schema_version": 1,
            "page": {"width": 595.2756, "height": 841.8898, "unit": "pt",
                     "origin": "top-left"},
            "elements": [],
        }
        formato_novo = layout_schema.layout_vazio()

        visual_schema.validate_visual_schema(formato_antigo)
        layout_schema.validate_layout(formato_novo)

        with pytest.raises(ValidationError):
            layout_schema.validate_layout(formato_antigo)
        with pytest.raises(ValidationError):
            visual_schema.validate_visual_schema(formato_novo)

    def test_o_legado_continua_de_pe(self):
        """A 4.2C nao foi tocada: as versoes antigas seguem publicadas."""
        from apps.doctemplates.models import TemplateVersion

        assert TemplateVersion.objects.filter(status="published").count() == 4
