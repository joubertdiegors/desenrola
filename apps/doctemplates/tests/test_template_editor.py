"""
Editor visual dos modelos da biblioteca (Etapa 3.2): telas, salvamento e
as regras que o servidor impõe.

O fio condutor: o editor NUNCA é a autoridade. Ele esconde controles
conforme o estado do modelo, mas quem decide é o servidor — por isso
cada teste de permissão bate direto na URL, sem passar pela interface,
que é exatamente o que alguém mal-intencionado faria.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.doctemplates import datasources, elements, layout_schema
from apps.doctemplates.models import DocumentTemplate, DocumentType
from apps.doctemplates.services import biblioteca
from apps.doctemplates.services import layout as servico_de_layout

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"


def elemento_de_texto(identificador="t1", **overrides):
    base = {
        "id": identificador,
        "type": "text",
        "x": 72.3456,
        "y": 120.9876,
        "width": 400.125,
        "height": 13.5,
        "properties": {"content": {"kind": "text", "value": "Olá"}},
    }
    base.update(overrides)
    return base


def layout_com(*elementos):
    return {"version": 1, "elements": list(elementos)}


@pytest.fixture
def tipo(db):
    return DocumentType.objects.create(
        code="contrato",
        name="Contrato",
        page={"width": 595.2756, "height": 841.8898, "unit": "pt"},
        data_sources=["documento", "convidado"],
    )


@pytest.fixture
def modelo(tipo):
    """Modelo comum e destravado: o caso normal de edição."""
    return DocumentTemplate.objects.create(
        type=tipo, name="Meu contrato", slug="meu-contrato", language="pt"
    )


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_user(
        email="editor@desenrola.be", password=SENHA, full_name="Editor", is_staff=True
    )


@pytest.fixture
def cliente(client, staff):
    client.force_login(staff)
    return client


def _url(nome, modelo):
    return reverse(f"backoffice:{nome}", args=[modelo.pk])


def _salvar(client, modelo, documento):
    return client.post(
        _url("template_editor_save", modelo),
        data=json.dumps({"layout": documento}),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# 1. Acesso
# ---------------------------------------------------------------------------


class TestAcesso:
    def test_anonimo_vai_para_o_login(self, client, modelo):
        resposta = client.get(_url("template_editor", modelo))

        assert resposta.status_code == 302
        assert "/accounts/login/" in resposta.url

    def test_usuario_comum_recebe_403(self, client, user, modelo):
        client.force_login(user)

        assert client.get(_url("template_editor", modelo)).status_code == 403

    def test_staff_abre_o_editor(self, cliente, modelo):
        assert cliente.get(_url("template_editor", modelo)).status_code == 200

    def test_modelo_inexistente_da_404(self, cliente):
        assert cliente.get(
            reverse("backoffice:template_editor", args=[999999])
        ).status_code == 404

    def test_salvar_exige_post(self, cliente, modelo):
        assert cliente.get(_url("template_editor_save", modelo)).status_code == 405

    def test_usuario_comum_nao_salva(self, client, user, modelo):
        client.force_login(user)

        assert _salvar(client, modelo, layout_com()).status_code == 403


# ---------------------------------------------------------------------------
# 2. O que a página entrega ao navegador
# ---------------------------------------------------------------------------


class TestContextoDaPagina:
    def test_leva_o_layout_do_modelo(self, cliente, modelo):
        modelo.layout = layout_com(elemento_de_texto())
        modelo.save()

        contexto = cliente.get(_url("template_editor", modelo)).context

        assert contexto["layout_json"] == modelo.layout

    def test_modelo_sem_desenho_recebe_um_layout_vazio_valido(self, cliente, modelo):
        contexto = cliente.get(_url("template_editor", modelo)).context

        assert contexto["layout_json"] == layout_schema.layout_vazio()
        layout_schema.validate_layout(contexto["layout_json"])

    def test_leva_a_pagina_do_tipo_de_documento(self, cliente, modelo, tipo):
        contexto = cliente.get(_url("template_editor", modelo)).context

        assert contexto["pagina_json"] == tipo.page
        assert contexto["pagina_json"]["unit"] == "pt"

    def test_os_tipos_vem_do_registro_e_nao_do_template(self, cliente, modelo):
        """Uma segunda lista escrita à mão divergiria do validador."""
        contexto = cliente.get(_url("template_editor", modelo)).context

        codigos = {t["code"] for t in contexto["tipos_json"]}
        assert codigos == set(elements.codigos())

    def test_as_fontes_vem_do_registro(self, cliente, modelo):
        contexto = cliente.get(_url("template_editor", modelo)).context

        codigos = {f["code"] for f in contexto["fontes_json"]}
        assert codigos == {f.code for f in datasources.fontes()}

    def test_toda_referencia_oferecida_e_valida(self, cliente, modelo):
        contexto = cliente.get(_url("template_editor", modelo)).context

        for grupo in contexto["fontes_json"]:
            for campo in grupo["fields"]:
                assert datasources.referencia_valida(campo["reference"])

    def test_os_ids_vem_prontos_do_servidor(self, cliente, modelo):
        """
        O navegador não inventa identificador: consome deste lote, gerado
        pelo mesmo `services/layout.py` que o salvamento usaria.
        """
        contexto = cliente.get(_url("template_editor", modelo)).context

        ids = contexto["ids_json"]
        assert len(ids) == 200
        assert len(set(ids)) == 200
        assert all(isinstance(i, str) and i for i in ids)

    def test_o_html_carrega_os_modulos_do_editor_novo(self, cliente, modelo):
        html = cliente.get(_url("template_editor", modelo)).content.decode()

        for modulo in ("geometry", "state", "canvas", "properties", "api", "editor"):
            assert f"template-editor/{modulo}.js" in html
        assert "css/template-editor.css" in html

    def test_nao_usa_nada_do_editor_anterior(self, cliente, modelo):
        """A 4.2C tem os seus arquivos; esta tela não os toca."""
        html = cliente.get(_url("template_editor", modelo)).content.decode()

        assert "js/editor/render.js" not in html
        assert "css/editor.css" not in html

    def test_nenhum_comentario_django_vaza_para_a_pagina(self, cliente, modelo):
        html = cliente.get(_url("template_editor", modelo)).content.decode()

        assert "{#" not in html
        assert "{%" not in html


# ---------------------------------------------------------------------------
# 3. Salvamento
# ---------------------------------------------------------------------------


class TestSalvamento:
    def test_salva_um_layout_valido(self, cliente, modelo):
        resposta = _salvar(cliente, modelo, layout_com(elemento_de_texto()))

        assert resposta.status_code == 200
        assert resposta.json()["ok"] is True
        modelo.refresh_from_db()
        assert len(modelo.layout["elements"]) == 1

    def test_as_casas_decimais_sobrevivem_ao_banco(self, cliente, modelo):
        _salvar(cliente, modelo, layout_com(elemento_de_texto()))

        modelo.refresh_from_db()
        elemento = modelo.layout["elements"][0]
        assert elemento["x"] == 72.3456
        assert elemento["y"] == 120.9876
        assert elemento["width"] == 400.125

    def test_reabrir_encontra_o_mesmo_layout(self, cliente, modelo):
        enviado = layout_com(elemento_de_texto(), elemento_de_texto("t2", x=10.0))
        _salvar(cliente, modelo, enviado)

        contexto = cliente.get(_url("template_editor", modelo)).context

        assert contexto["layout_json"] == enviado

    def test_salvar_de_novo_substitui(self, cliente, modelo):
        _salvar(cliente, modelo, layout_com(elemento_de_texto("a")))
        _salvar(cliente, modelo, layout_com(elemento_de_texto("b")))

        modelo.refresh_from_db()
        assert [e["id"] for e in modelo.layout["elements"]] == ["b"]

    def test_salvar_layout_vazio_e_permitido(self, cliente, modelo):
        resposta = _salvar(cliente, modelo, layout_schema.layout_vazio())

        assert resposta.status_code == 200
        modelo.refresh_from_db()
        assert modelo.layout["elements"] == []

    def test_a_ordem_dos_elementos_e_preservada(self, cliente, modelo):
        """A ordem é a camada: inverter aqui mudaria o desenho."""
        documento = layout_com(*[elemento_de_texto(f"e{i}") for i in range(5)])

        _salvar(cliente, modelo, documento)

        modelo.refresh_from_db()
        assert [e["id"] for e in modelo.layout["elements"]] == [
            "e0", "e1", "e2", "e3", "e4"
        ]

    def test_nenhum_elemento_ganha_z_index(self, cliente, modelo):
        _salvar(cliente, modelo, layout_com(elemento_de_texto()))

        modelo.refresh_from_db()
        assert "z_index" not in modelo.layout["elements"][0]


# ---------------------------------------------------------------------------
# 4. O servidor não confia no editor
# ---------------------------------------------------------------------------


class TestValidacaoNoServidor:
    def test_json_malformado_e_recusado(self, cliente, modelo):
        resposta = cliente.post(
            _url("template_editor_save", modelo),
            data="{isto não é json",
            content_type="application/json",
        )

        assert resposta.status_code == 400
        assert resposta.json()["ok"] is False

    def test_corpo_sem_a_chave_layout_e_recusado(self, cliente, modelo):
        resposta = cliente.post(
            _url("template_editor_save", modelo),
            data=json.dumps({"outra_coisa": 1}),
            content_type="application/json",
        )

        assert resposta.status_code == 400

    @pytest.mark.parametrize(
        "documento",
        [
            {"version": 99, "elements": []},
            {"version": 1, "elements": {}},
            {"version": 1, "elements": [{"type": "text"}]},
        ],
        ids=["versao", "elements-nao-lista", "sem-id"],
    )
    def test_layout_fora_do_contrato_e_recusado(self, cliente, modelo, documento):
        assert _salvar(cliente, modelo, documento).status_code == 400

    def test_tipo_desconhecido_e_recusado(self, cliente, modelo):
        assert _salvar(
            cliente, modelo, layout_com(elemento_de_texto(type="video"))
        ).status_code == 400

    def test_dimensao_negativa_e_recusada(self, cliente, modelo):
        assert _salvar(
            cliente, modelo, layout_com(elemento_de_texto(width=-10))
        ).status_code == 400

    def test_ids_repetidos_sao_recusados(self, cliente, modelo):
        assert _salvar(
            cliente, modelo, layout_com(elemento_de_texto("x"), elemento_de_texto("x"))
        ).status_code == 400

    def test_referencia_de_campo_inexistente_e_recusada(self, cliente, modelo):
        elemento = elemento_de_texto()
        elemento["properties"]["content"] = {
            "kind": "field", "source": "convidado.fantasma"
        }

        resposta = _salvar(cliente, modelo, layout_com(elemento))

        assert resposta.status_code == 400
        assert "fantasma" in resposta.json()["error"]

    def test_um_layout_recusado_nao_apaga_o_que_estava_gravado(self, cliente, modelo):
        _salvar(cliente, modelo, layout_com(elemento_de_texto("bom")))

        _salvar(cliente, modelo, layout_com(elemento_de_texto(type="video")))

        modelo.refresh_from_db()
        assert [e["id"] for e in modelo.layout["elements"]] == ["bom"]

    def test_a_resposta_de_erro_e_estruturada(self, cliente, modelo):
        dados = _salvar(cliente, modelo, {"version": 99, "elements": []}).json()

        assert dados["ok"] is False
        assert isinstance(dados["error"], str) and dados["error"]


# ---------------------------------------------------------------------------
# 5. Metadados protegidos
# ---------------------------------------------------------------------------


class TestMetadadosProtegidos:
    def test_o_endpoint_ignora_tudo_que_nao_seja_layout(self, cliente, modelo, tipo):
        """
        A proteção vem de o endpoint só LER `layout`. Não há lista de
        campos proibidos que alguém possa esquecer de atualizar.
        """
        outro_tipo = DocumentType.objects.create(code="x", name="X", page={"unit": "pt"})
        antes = DocumentTemplate.objects.filter(pk=modelo.pk).values().first()

        resposta = cliente.post(
            _url("template_editor_save", modelo),
            data=json.dumps({
                "layout": layout_schema.layout_vazio(),
                "type": outro_tipo.pk,
                "language": "fr",
                "is_system": True,
                "is_locked": True,
                "slug": "invadido",
                "name": "Invadido",
                "duplicated_from": modelo.pk,
                "created_by": 1,
                "field_schema": {"fields": []},
            }),
            content_type="application/json",
        )

        assert resposta.status_code == 200
        depois = DocumentTemplate.objects.filter(pk=modelo.pk).values().first()
        for campo in (
            "type_id", "language", "is_system", "is_locked", "slug", "name",
            "duplicated_from_id", "created_by_id", "field_schema",
        ):
            assert depois[campo] == antes[campo], campo

    def test_so_o_layout_e_o_updated_at_mudam(self, cliente, modelo):
        antes = DocumentTemplate.objects.filter(pk=modelo.pk).values().first()

        _salvar(cliente, modelo, layout_com(elemento_de_texto()))

        depois = DocumentTemplate.objects.filter(pk=modelo.pk).values().first()
        diferentes = {k for k in antes if antes[k] != depois[k]}
        assert diferentes == {"layout", "updated_at"}


# ---------------------------------------------------------------------------
# 6. Modelos do sistema e travados
# ---------------------------------------------------------------------------


class TestSystemELocked:
    @pytest.fixture
    def travado(self, tipo):
        return DocumentTemplate.objects.create(
            type=tipo, name="Travado", slug="travado", language="pt", is_locked=True
        )

    @pytest.fixture
    def oficial(self, db):
        biblioteca.semear()
        return DocumentTemplate.objects.get(slug="carta-convite-fr")

    def test_modelo_comum_abre_editavel(self, cliente, modelo):
        resposta = cliente.get(_url("template_editor", modelo))

        assert resposta.context["editavel"] is True
        assert resposta.context["config_json"]["editable"] is True

    def test_modelo_travado_abre_em_leitura(self, cliente, travado):
        resposta = cliente.get(_url("template_editor", travado))

        assert resposta.status_code == 200
        assert resposta.context["editavel"] is False
        assert "travado" in resposta.context["motivo_da_leitura"].lower()

    def test_modelo_do_sistema_abre_em_leitura_mesmo_destravado(self, cliente, oficial):
        """
        A reconstrução controlada dos oficiais será feita por um serviço
        próprio, fora do editor.
        """
        assert oficial.is_locked is False

        resposta = cliente.get(_url("template_editor", oficial))

        assert resposta.status_code == 200
        assert resposta.context["editavel"] is False
        assert "oficial" in resposta.context["motivo_da_leitura"].lower()

    def test_modelo_travado_nao_salva(self, cliente, travado):
        resposta = _salvar(cliente, travado, layout_com(elemento_de_texto()))

        assert resposta.status_code == 409
        travado.refresh_from_db()
        assert travado.layout == {}

    def test_modelo_do_sistema_nao_salva(self, cliente, oficial):
        resposta = _salvar(cliente, oficial, layout_com(elemento_de_texto()))

        assert resposta.status_code == 409
        oficial.refresh_from_db()
        assert oficial.layout == {}

    def test_a_tela_em_leitura_nao_mostra_o_botao_salvar(self, cliente, travado):
        html = cliente.get(_url("template_editor", travado)).content.decode()

        assert 'data-acao="salvar"' not in html

    def test_a_tela_editavel_mostra_o_botao_salvar(self, cliente, modelo):
        html = cliente.get(_url("template_editor", modelo)).content.decode()

        assert 'data-acao="salvar"' in html

    def test_modelo_em_leitura_nao_da_mais_ids(self, cliente, travado):
        assert cliente.post(_url("template_editor_ids", travado)).status_code == 403

    def test_uma_copia_do_oficial_abre_editavel(self, cliente, oficial, staff):
        """O caminho previsto: duplicar e trabalhar na cópia."""
        from apps.doctemplates.services.duplicacao import duplicar_modelo

        copia = duplicar_modelo(oficial, "Meu modelo FR", created_by=staff)

        resposta = cliente.get(_url("template_editor", copia))

        assert resposta.context["editavel"] is True
        assert _salvar(cliente, copia, layout_com(elemento_de_texto())).status_code == 200


# ---------------------------------------------------------------------------
# 7. Lote de identificadores
# ---------------------------------------------------------------------------


class TestIdentificadores:
    def test_pedir_outro_lote(self, cliente, modelo):
        resposta = cliente.post(_url("template_editor_ids", modelo))

        dados = resposta.json()
        assert resposta.status_code == 200
        assert dados["ok"] is True
        assert len(set(dados["ids"])) == 200

    def test_dois_lotes_nao_se_repetem(self, cliente, modelo):
        um = set(cliente.post(_url("template_editor_ids", modelo)).json()["ids"])
        dois = set(cliente.post(_url("template_editor_ids", modelo)).json()["ids"])

        assert not (um & dois)

    def test_exige_post(self, cliente, modelo):
        assert cliente.get(_url("template_editor_ids", modelo)).status_code == 405

    def test_os_ids_vem_do_servico_de_layout(self, cliente, modelo):
        """Um gerador só para o sistema inteiro."""
        gerado = servico_de_layout.novo_id()
        do_lote = cliente.post(_url("template_editor_ids", modelo)).json()["ids"][0]

        assert len(do_lote) == len(gerado)


# ---------------------------------------------------------------------------
# 8. Nada da arquitetura anterior foi tocado
# ---------------------------------------------------------------------------


class TestNadaDeRegressao:
    def test_o_editor_anterior_continua_respondendo(self, cliente, draft_version):
        """A 4.2C segue de pé: rotas e views próprias, intactas."""
        resposta = cliente.get(
            reverse("backoffice:document_editor", args=[draft_version.pk])
        )

        assert resposta.status_code in (200, 403)

    def test_as_rotas_dos_dois_editores_sao_distintas(self, modelo, draft_version):
        nova = reverse("backoffice:template_editor", args=[modelo.pk])
        antiga = reverse("backoffice:document_editor", args=[draft_version.pk])

        assert nova != antiga
        assert "/modelos/" in nova
        assert "/documentos/" in antiga

    def test_o_contrato_novo_nao_aceita_o_formato_antigo(self, cliente, modelo):
        antigo = {
            "schema_version": 1,
            "page": {"width": 595.2756, "height": 841.8898, "unit": "pt",
                     "origin": "top-left"},
            "elements": [],
        }

        assert _salvar(cliente, modelo, antigo).status_code == 400
