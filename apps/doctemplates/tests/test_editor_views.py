"""
Editor visual: telas, salvamento, permissoes e imutabilidade (Etapa 4.2A).

O fio condutor destes testes e que o editor NUNCA e a autoridade. Ele
esconde botoes conforme a permissao, mas quem decide e o servidor: cada
teste de permissao aqui bate direto na URL, sem passar pela interface,
que e exatamente o que um atacante faria.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.doctemplates.models import TemplateVersion, TemplateVersionImmutableError
from apps.doctemplates.visual_schema import documento_vazio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"

PERMISSOES = {
    "ver": "view_templateversion",
    "editar": "change_templateversion",
    "criar": "add_templateversion",
    "publicar": "publish_templateversion",
}


def _usuario(email, *permissoes, staff=True):
    pessoa = get_user_model().objects.create_user(
        email=email, password=SENHA, full_name="Admin Teste", is_staff=staff
    )
    for apelido in permissoes:
        pessoa.user_permissions.add(
            Permission.objects.get(
                codename=PERMISSOES[apelido], content_type__app_label="doctemplates"
            )
        )
    return pessoa


@pytest.fixture
def editor(db):
    """Quem pode ver, editar, criar e publicar."""
    return _usuario("editor@desenrola.be", "ver", "editar", "criar", "publicar")


@pytest.fixture
def apenas_leitor(db):
    """Staff que so consulta -- nao pode salvar nada."""
    return _usuario("leitor@desenrola.be", "ver")


@pytest.fixture
def cliente_editor(client, editor):
    client.force_login(editor)
    return client


def documento_com_texto(conteudo="Olá"):
    doc = documento_vazio()
    doc["elements"] = [
        {
            "id": "t1",
            "type": "text",
            "x": 72.3456,
            "y": 120.9876,
            "width": 400.125,
            "height": 13.5,
            "z_index": 1,
            "properties": {"content": conteudo},
        }
    ]
    return doc


def _salvar(client, versao, documento):
    return client.post(
        reverse("backoffice:document_save", args=[versao.pk]),
        data=json.dumps(documento),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# 1. Acesso as telas
# ---------------------------------------------------------------------------


class TestAcesso:
    def test_anonimo_nao_chega_ao_editor(self, client, draft_version):
        resposta = client.get(reverse("backoffice:document_editor", args=[draft_version.pk]))

        assert resposta.status_code == 302
        assert "/accounts/login/" in resposta.url

    def test_usuario_comum_recebe_403(self, client, user, draft_version):
        client.force_login(user)

        resposta = client.get(reverse("backoffice:document_editor", args=[draft_version.pk]))

        assert resposta.status_code == 403

    def test_staff_sem_permissao_de_ver_recebe_403(self, client, staff_user, draft_version):
        """`is_staff` abre o backoffice, nao o documento."""
        client.force_login(staff_user)

        resposta = client.get(reverse("backoffice:document_editor", args=[draft_version.pk]))

        assert resposta.status_code == 403

    def test_quem_tem_permissao_abre_o_editor(self, cliente_editor, draft_version):
        resposta = cliente_editor.get(
            reverse("backoffice:document_editor", args=[draft_version.pk])
        )

        assert resposta.status_code == 200

    def test_a_lista_mostra_as_versoes(self, cliente_editor, draft_version):
        resposta = cliente_editor.get(reverse("backoffice:documents"))

        assert resposta.status_code == 200
        assert draft_version.template.name in resposta.content.decode()

    def test_versao_inexistente_da_404(self, cliente_editor):
        assert cliente_editor.get(
            reverse("backoffice:document_editor", args=[999999])
        ).status_code == 404


# ---------------------------------------------------------------------------
# 2. Salvar e reabrir -- o criterio de conclusao da etapa
# ---------------------------------------------------------------------------


class TestSalvarECarregar:
    def test_salvar_grava_o_documento(self, cliente_editor, draft_version):
        resposta = _salvar(cliente_editor, draft_version, documento_com_texto())

        assert resposta.status_code == 200
        assert resposta.json()["ok"] is True
        draft_version.refresh_from_db()
        assert len(draft_version.visual_schema["elements"]) == 1

    def test_reabrir_encontra_o_mesmo_layout(self, cliente_editor, draft_version):
        """
        O criterio de conclusao: salvar, reabrir e achar tudo igual --
        inclusive as casas decimais.
        """
        enviado = documento_com_texto("Conteúdo com acento à ç")
        _salvar(cliente_editor, draft_version, enviado)

        resposta = cliente_editor.get(
            reverse("backoffice:document_editor", args=[draft_version.pk])
        )

        # O que o editor recebe para desenhar tem de ser igual ao enviado.
        assert resposta.context["documento_json"] == enviado
        # E tem de chegar mesmo ao HTML, pelo json_script (que escapa).
        assert 'id="editor-documento"' in resposta.content.decode()

    def test_as_casas_decimais_sobrevivem_ao_banco(self, cliente_editor, draft_version):
        _salvar(cliente_editor, draft_version, documento_com_texto())

        draft_version.refresh_from_db()
        elemento = draft_version.visual_schema["elements"][0]

        assert elemento["x"] == 72.3456
        assert elemento["y"] == 120.9876
        assert elemento["width"] == 400.125

    def test_salvar_de_novo_substitui(self, cliente_editor, draft_version):
        _salvar(cliente_editor, draft_version, documento_com_texto("primeiro"))
        _salvar(cliente_editor, draft_version, documento_com_texto("segundo"))

        draft_version.refresh_from_db()
        assert draft_version.visual_schema["elements"][0]["properties"]["content"] == "segundo"

    def test_salvar_documento_vazio_e_permitido(self, cliente_editor, draft_version):
        resposta = _salvar(cliente_editor, draft_version, documento_vazio())

        assert resposta.status_code == 200
        draft_version.refresh_from_db()
        assert draft_version.visual_schema["elements"] == []

    def test_varios_elementos_e_z_index_sao_preservados(self, cliente_editor, draft_version):
        doc = documento_vazio()
        doc["elements"] = [
            {
                "id": f"e{i}",
                "type": "rect",
                "x": i * 10.0,
                "y": i * 10.0,
                "width": 50.0,
                "height": 20.0,
                "z_index": 10 - i,
                "properties": {"border_width": 1},
            }
            for i in range(5)
        ]

        _salvar(cliente_editor, draft_version, doc)

        draft_version.refresh_from_db()
        guardados = draft_version.visual_schema["elements"]
        assert len(guardados) == 5
        assert [e["z_index"] for e in guardados] == [10, 9, 8, 7, 6]


# ---------------------------------------------------------------------------
# 3. O servidor nao confia no editor
# ---------------------------------------------------------------------------


class TestValidacaoNoServidor:
    def test_json_malformado_e_recusado(self, cliente_editor, draft_version):
        resposta = cliente_editor.post(
            reverse("backoffice:document_save", args=[draft_version.pk]),
            data="{isto não é json",
            content_type="application/json",
        )

        assert resposta.status_code == 400
        assert resposta.json()["ok"] is False

    def test_tipo_invalido_e_recusado(self, cliente_editor, draft_version):
        doc = documento_com_texto()
        doc["elements"][0]["type"] = "iframe"

        resposta = _salvar(cliente_editor, draft_version, doc)

        assert resposta.status_code == 400
        draft_version.refresh_from_db()
        assert draft_version.visual_schema == {}

    def test_dimensao_negativa_e_recusada(self, cliente_editor, draft_version):
        doc = documento_com_texto()
        doc["elements"][0]["width"] = -10

        assert _salvar(cliente_editor, draft_version, doc).status_code == 400

    def test_ids_repetidos_sao_recusados(self, cliente_editor, draft_version):
        doc = documento_com_texto()
        doc["elements"].append(dict(doc["elements"][0]))

        assert _salvar(cliente_editor, draft_version, doc).status_code == 400

    def test_um_campo_inexistente_e_recusado(self, cliente_editor, draft_version):
        """
        A referencia e conferida contra o `field_schema` DESTA versao --
        e a checagem que so o servidor pode fazer.
        """
        doc = documento_vazio()
        doc["elements"] = [
            {
                "id": "f1",
                "type": "field",
                "x": 10.0,
                "y": 10.0,
                "width": 100.0,
                "height": 12.0,
                "z_index": 1,
                "properties": {"field": "campo_fantasma"},
            }
        ]

        resposta = _salvar(cliente_editor, draft_version, doc)

        assert resposta.status_code == 400
        assert "campo_fantasma" in resposta.json()["error"]

    def test_uma_imagem_inexistente_e_recusada(self, cliente_editor, draft_version):
        doc = documento_vazio()
        doc["elements"] = [
            {
                "id": "i1",
                "type": "image",
                "x": 10.0,
                "y": 10.0,
                "width": 100.0,
                "height": 100.0,
                "z_index": 1,
                "properties": {"asset_id": 4242},
            }
        ]

        assert _salvar(cliente_editor, draft_version, doc).status_code == 400

    def test_um_documento_recusado_nao_apaga_o_que_estava_gravado(
        self, cliente_editor, draft_version
    ):
        _salvar(cliente_editor, draft_version, documento_com_texto("bom"))

        ruim = documento_com_texto("ruim")
        ruim["elements"][0]["type"] = "desconhecido"
        _salvar(cliente_editor, draft_version, ruim)

        draft_version.refresh_from_db()
        assert draft_version.visual_schema["elements"][0]["properties"]["content"] == "bom"

    def test_get_nao_salva(self, cliente_editor, draft_version):
        assert cliente_editor.get(
            reverse("backoffice:document_save", args=[draft_version.pk])
        ).status_code == 405


# ---------------------------------------------------------------------------
# 4. Permissoes -- batendo direto na URL
# ---------------------------------------------------------------------------


class TestPermissoes:
    def test_sem_permissao_de_editar_nao_salva(self, client, apenas_leitor, draft_version):
        client.force_login(apenas_leitor)

        resposta = _salvar(client, draft_version, documento_com_texto())

        assert resposta.status_code == 403
        draft_version.refresh_from_db()
        assert draft_version.visual_schema == {}

    def test_leitor_ve_o_editor_em_modo_somente_leitura(
        self, client, apenas_leitor, draft_version
    ):
        client.force_login(apenas_leitor)

        resposta = client.get(
            reverse("backoffice:document_editor", args=[draft_version.pk])
        )

        assert resposta.status_code == 200
        assert resposta.context["editavel"] is False

    def test_sem_permissao_de_publicar_nao_publica(self, client, draft_version):
        pessoa = _usuario("so-edita@desenrola.be", "ver", "editar")
        client.force_login(pessoa)

        resposta = client.post(
            reverse("backoffice:document_publish", args=[draft_version.pk])
        )

        assert resposta.status_code == 403
        draft_version.refresh_from_db()
        assert draft_version.status == TemplateVersion.Status.DRAFT

    def test_sem_permissao_de_criar_nao_cria_versao(self, client, published_version):
        pessoa = _usuario("so-ve@desenrola.be", "ver")
        client.force_login(pessoa)

        resposta = client.post(
            reverse("backoffice:document_new_version", args=[published_version.pk])
        )

        assert resposta.status_code == 403
        assert published_version.template.versions.count() == 1

    def test_usuario_comum_nao_salva(self, client, user, draft_version):
        client.force_login(user)

        assert _salvar(client, draft_version, documento_com_texto()).status_code == 403


# ---------------------------------------------------------------------------
# 5. Imutabilidade -- a regra que ja existia continua valendo
# ---------------------------------------------------------------------------


class TestVersaoPublicada:
    def test_nao_pode_ser_salva_pelo_editor(self, cliente_editor, published_version):
        resposta = _salvar(cliente_editor, published_version, documento_com_texto())

        assert resposta.status_code == 409
        published_version.refresh_from_db()
        assert published_version.visual_schema == {}

    def test_o_editor_abre_em_modo_leitura(self, cliente_editor, published_version):
        resposta = cliente_editor.get(
            reverse("backoffice:document_editor", args=[published_version.pk])
        )

        assert resposta.status_code == 200
        assert resposta.context["editavel"] is False

    def test_o_modelo_recusa_mesmo_por_fora_do_editor(self, published_version):
        """
        A regra vale para qualquer caminho de codigo, nao so para a view.
        """
        published_version.visual_schema = documento_com_texto()

        with pytest.raises(TemplateVersionImmutableError):
            published_version.save()

    def test_criar_proxima_versao_herda_o_layout(self, cliente_editor, draft_version):
        _salvar(cliente_editor, draft_version, documento_com_texto("herdado"))
        draft_version.refresh_from_db()
        draft_version.publish()

        resposta = cliente_editor.post(
            reverse("backoffice:document_new_version", args=[draft_version.pk])
        )

        nova = draft_version.template.versions.order_by("-version_number").first()
        assert resposta.status_code == 302
        assert nova.version_number == 2
        assert nova.status == TemplateVersion.Status.DRAFT
        assert nova.visual_schema["elements"][0]["properties"]["content"] == "herdado"

    def test_editar_a_nova_versao_nao_toca_na_publicada(self, cliente_editor, draft_version):
        _salvar(cliente_editor, draft_version, documento_com_texto("original"))
        draft_version.refresh_from_db()
        draft_version.publish()
        cliente_editor.post(
            reverse("backoffice:document_new_version", args=[draft_version.pk])
        )
        nova = draft_version.template.versions.order_by("-version_number").first()

        _salvar(cliente_editor, nova, documento_com_texto("alterado"))

        draft_version.refresh_from_db()
        nova.refresh_from_db()
        assert draft_version.visual_schema["elements"][0]["properties"]["content"] == "original"
        assert nova.visual_schema["elements"][0]["properties"]["content"] == "alterado"

    def test_a_heranca_e_copia_profunda(self, draft_version):
        """Editar o rascunho novo nao pode alcancar o JSON da origem."""
        draft_version.visual_schema = documento_com_texto()
        draft_version.save()

        nova = draft_version.create_next_version()
        nova.visual_schema["elements"][0]["properties"]["content"] = "mexido"

        draft_version.refresh_from_db()
        assert draft_version.visual_schema["elements"][0]["properties"]["content"] == "Olá"


# ---------------------------------------------------------------------------
# 6. Publicacao
# ---------------------------------------------------------------------------


class TestPublicacao:
    def test_publicar_um_rascunho_valido(self, cliente_editor, draft_version):
        _salvar(cliente_editor, draft_version, documento_com_texto())

        cliente_editor.post(reverse("backoffice:document_publish", args=[draft_version.pk]))

        draft_version.refresh_from_db()
        assert draft_version.status == TemplateVersion.Status.PUBLISHED
        assert draft_version.published_at is not None

    def test_um_documento_invalido_nao_e_publicado(self, cliente_editor, draft_version):
        """
        Publicar congela o layout: e a ultima chance de barrar um
        documento quebrado antes de ele virar imutavel.
        """
        TemplateVersion.objects.filter(pk=draft_version.pk).update(
            visual_schema={"schema_version": 99, "page": {}, "elements": []}
        )

        cliente_editor.post(reverse("backoffice:document_publish", args=[draft_version.pk]))

        draft_version.refresh_from_db()
        assert draft_version.status == TemplateVersion.Status.DRAFT

    def test_publicar_duas_vezes_nao_quebra(self, cliente_editor, published_version):
        resposta = cliente_editor.post(
            reverse("backoffice:document_publish", args=[published_version.pk])
        )

        assert resposta.status_code == 302
        published_version.refresh_from_db()
        assert published_version.status == TemplateVersion.Status.PUBLISHED


# ---------------------------------------------------------------------------
# 7. O editor nao mudou o resto do sistema
# ---------------------------------------------------------------------------


class TestNadaDeRegressao:
    def test_versoes_antigas_continuam_validas_sem_layout(self, draft_version):
        """
        Toda versao criada antes desta etapa tem `visual_schema` vazio, e
        isso nao pode virar erro de validacao em lugar nenhum.
        """
        from apps.doctemplates.visual_schema import validate_visual_schema

        assert draft_version.visual_schema == {}
        validate_visual_schema(draft_version.visual_schema)
        # E continua podendo ser gravada normalmente.
        draft_version.save()

    def test_o_field_schema_nao_foi_tocado(self, cliente_editor, draft_version):
        antes = draft_version.field_schema

        _salvar(cliente_editor, draft_version, documento_com_texto())

        draft_version.refresh_from_db()
        assert draft_version.field_schema == antes

    def test_o_visual_entrou_nos_campos_estruturais(self):
        assert "visual_schema" in TemplateVersion.STRUCTURAL_FIELDS
