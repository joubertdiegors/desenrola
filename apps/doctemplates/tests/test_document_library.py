"""
Biblioteca de modelos da nova arquitetura (Etapa 3.2.1).

O fio condutor: esta tela e a nova porta de entrada de "Modelos" no
backoffice, e sua ÚNICA fonte de dados é `DocumentTemplate`. Nenhum
teste aqui deve depender de `LetterTemplate`/`TemplateVersion` --
inclusive há um teste que confere isso na resposta HTTP real.

A arquitetura antiga continua registrada (suas próprias rotas e testes
não foram tocados); o que muda é que a navegação normal não leva mais a
ela.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.doctemplates.models import DocumentTemplate, DocumentType
from apps.doctemplates.services import biblioteca

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"

SLUGS_OFICIAIS = ["carta-convite-fr", "carta-convite-nl", "carta-convite-en", "carta-convite-pt"]


@pytest.fixture
def tipo(db):
    return DocumentType.objects.create(
        code="contrato", name="Contrato", page={"width": 595.2756, "unit": "pt"}
    )


@pytest.fixture
def modelo(tipo):
    """Modelo comum, editável e ativo -- o caso normal."""
    return DocumentTemplate.objects.create(
        type=tipo, name="Meu contrato", slug="meu-contrato", language="pt"
    )


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_user(
        email="biblioteca@desenrola.be", password=SENHA, full_name="Admin", is_staff=True
    )


@pytest.fixture
def cliente(client, staff):
    client.force_login(staff)
    return client


@pytest.fixture
def oficiais(db):
    """Os quatro modelos oficiais semeados pela Etapa 1."""
    _, modelos = biblioteca.semear()
    return {m.language: m for m in modelos}


def _duplicar(client, modelo, nome="Cópia de teste"):
    return client.post(
        reverse("backoffice:document_library_duplicate", args=[modelo.pk]),
        {"name": nome},
    )


def _excluir(client, modelo):
    return client.post(reverse("backoffice:document_library_delete", args=[modelo.pk]))


# ---------------------------------------------------------------------------
# 1. Acesso e origem dos dados
# ---------------------------------------------------------------------------


class TestAcessoEOrigemDosDados:
    def test_anonimo_vai_para_o_login(self, client, modelo):
        resposta = client.get(reverse("backoffice:document_library"))

        assert resposta.status_code == 302
        assert "/accounts/login/" in resposta.url

    def test_usuario_comum_recebe_403(self, client, user, modelo):
        client.force_login(user)

        assert client.get(reverse("backoffice:document_library")).status_code == 403

    def test_staff_ve_a_biblioteca(self, cliente, modelo):
        resposta = cliente.get(reverse("backoffice:document_library"))

        assert resposta.status_code == 200
        assert modelo in resposta.context["modelos"]

    def test_a_fonte_e_exclusivamente_documenttemplate(self, cliente, modelo):
        """A view não recebe (nem usa) nada do modelo antigo."""
        resposta = cliente.get(reverse("backoffice:document_library"))

        assert set(resposta.context.keys()) >= {"modelos", "tipos", "idiomas", "filtros"}
        assert "templates" not in resposta.context  # nome usado pela tela antiga
        assert "template_versions" not in resposta.context
        for objeto in resposta.context["modelos"]:
            assert isinstance(objeto, DocumentTemplate)

    def test_a_resposta_html_nao_menciona_versao_nem_publicacao(self, cliente, modelo):
        """
        A tela antiga fala em "versão"/"publicar". Se esse vocabulário
        aparecer aqui, algo foi copiado da arquitetura errada.
        """
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert "version_number" not in html
        assert "Publicar" not in html
        assert "Nova versão" not in html

    def test_nenhum_comentario_django_vaza_para_a_pagina(self, cliente, modelo):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert "{#" not in html
        assert "{%" not in html


# ---------------------------------------------------------------------------
# 2. Os quatro oficiais aparecem, intactos
# ---------------------------------------------------------------------------


class TestModelosOficiais:
    def test_os_quatro_aparecem_na_listagem(self, cliente, oficiais):
        resposta = cliente.get(reverse("backoffice:document_library"))

        slugs = {m.slug for m in resposta.context["modelos"]}
        assert set(SLUGS_OFICIAIS) <= slugs

    def test_a_semeadura_nao_alterou_dados_ao_abrir_a_biblioteca(self, cliente, oficiais):
        antes = {
            slug: DocumentTemplate.objects.get(slug=slug).field_schema
            for slug in SLUGS_OFICIAIS
        }

        cliente.get(reverse("backoffice:document_library"))

        for slug in SLUGS_OFICIAIS:
            assert DocumentTemplate.objects.get(slug=slug).field_schema == antes[slug]

    def test_oficial_aparece_marcado_como_tal(self, cliente, oficiais):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert "Oficial" in html

    def test_modelo_comum_nao_aparece_marcado_como_oficial(self, cliente, modelo):
        """
        A migration de semeadura já roda ao criar o banco de teste, então
        os quatro oficiais sempre existem; por isso o filtro "somente
        comuns" (já coberto em TestFiltros) é o jeito correto de isolar
        a badge de uma linha comum, sem a página inteira.
        """
        resposta = cliente.get(reverse("backoffice:document_library"), {"system": "0"})

        assert modelo in resposta.context["modelos"]
        assert all(not m.is_system for m in resposta.context["modelos"])
        assert "Oficial" not in resposta.content.decode()

    def test_modelo_travado_aparece_marcado(self, cliente, tipo):
        DocumentTemplate.objects.create(
            type=tipo, name="Travado", slug="travado", language="pt", is_locked=True
        )

        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert "Travado" in html


# ---------------------------------------------------------------------------
# 3. Ação Editar: abre o editor novo
# ---------------------------------------------------------------------------


class TestAcaoEditar:
    def test_o_link_editar_aponta_para_o_editor_da_etapa_3_2(self, cliente, modelo):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        url_esperada = reverse("backoffice:template_editor", args=[modelo.pk])
        assert url_esperada in html

    def test_o_link_nao_aponta_para_o_editor_antigo(self, cliente, modelo):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert "/documentos/" not in html

    def test_modelo_editavel_mostra_rotulo_editar(self, cliente, modelo):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert "Editar" in html

    def test_modelo_oficial_mostra_rotulo_ver(self, cliente, oficiais):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert "Ver" in html

    def test_seguindo_o_link_o_editor_abre_de_verdade(self, cliente, modelo):
        resposta = cliente.get(
            reverse("backoffice:template_editor", args=[modelo.pk])
        )

        assert resposta.status_code == 200
        assert resposta.context["editavel"] is True


# ---------------------------------------------------------------------------
# 4. Ação Duplicar: usa o serviço existente
# ---------------------------------------------------------------------------


class TestAcaoDuplicar:
    def test_duplicar_usa_o_servico_e_nao_copia_manual(self, cliente, oficiais, staff):
        origem = oficiais["fr"]

        resposta = _duplicar(cliente, origem, "Meu modelo FR")

        assert resposta.status_code == 302
        copia = DocumentTemplate.objects.get(name="Meu modelo FR")
        assert copia.duplicated_from_id == origem.pk
        assert copia.field_schema == origem.field_schema
        assert copia.field_schema is not origem.field_schema  # cópia profunda

    def test_a_copia_nasce_nao_system_e_destravada(self, cliente, oficiais):
        origem = oficiais["pt"]

        _duplicar(cliente, origem, "Cópia do PT")

        copia = DocumentTemplate.objects.get(name="Cópia do PT")
        assert copia.is_system is False
        assert copia.is_locked is False
        assert copia.is_active is True

    def test_a_copia_registra_quem_criou(self, cliente, oficiais, staff):
        _duplicar(cliente, oficiais["en"], "Cópia do EN")

        copia = DocumentTemplate.objects.get(name="Cópia do EN")
        assert copia.created_by_id == staff.pk

    def test_duplicar_redireciona_para_o_editor_da_copia(self, cliente, modelo):
        resposta = _duplicar(cliente, modelo, "Cópia direta")

        copia = DocumentTemplate.objects.get(name="Cópia direta")
        assert resposta.url == reverse("backoffice:template_editor", args=[copia.pk])

    def test_a_copia_abre_editavel_no_editor(self, cliente, oficiais):
        _duplicar(cliente, oficiais["nl"], "Cópia editável")
        copia = DocumentTemplate.objects.get(name="Cópia editável")

        resposta = cliente.get(reverse("backoffice:template_editor", args=[copia.pk]))

        assert resposta.context["editavel"] is True

    def test_duplicar_um_modelo_travado_funciona(self, cliente, tipo):
        travado = DocumentTemplate.objects.create(
            type=tipo, name="Travado", slug="travado-dup", language="pt", is_locked=True
        )

        resposta = _duplicar(cliente, travado, "Cópia do travado")

        assert resposta.status_code == 302
        copia = DocumentTemplate.objects.get(name="Cópia do travado")
        assert copia.is_locked is False

    def test_nome_vazio_e_recusado_pela_validacao_do_servico(self, cliente, modelo):
        antes = DocumentTemplate.objects.count()

        resposta = _duplicar(cliente, modelo, "")

        assert resposta.status_code == 302  # volta para a biblioteca com mensagem de erro
        assert DocumentTemplate.objects.count() == antes

    def test_duplicar_exige_post(self, cliente, modelo):
        assert cliente.get(
            reverse("backoffice:document_library_duplicate", args=[modelo.pk])
        ).status_code == 405

    def test_usuario_comum_nao_duplica(self, client, user, modelo):
        client.force_login(user)

        assert _duplicar(client, modelo).status_code == 403

    def test_a_origem_nao_e_alterada_pela_duplicacao(self, cliente, oficiais):
        origem = oficiais["fr"]
        antes = DocumentTemplate.objects.filter(pk=origem.pk).values().first()

        _duplicar(cliente, origem, "Não deve tocar a origem")

        depois = DocumentTemplate.objects.filter(pk=origem.pk).values().first()
        assert depois == antes


# ---------------------------------------------------------------------------
# 5. Ação Excluir: respeita as regras do modelo
# ---------------------------------------------------------------------------


class TestAcaoExcluir:
    def test_modelo_comum_pode_ser_excluido(self, cliente, modelo):
        resposta = _excluir(cliente, modelo)

        assert resposta.status_code == 302
        assert not DocumentTemplate.objects.filter(pk=modelo.pk).exists()

    def test_modelo_oficial_nunca_e_excluido(self, cliente, oficiais):
        origem = oficiais["fr"]

        resposta = _excluir(cliente, origem)

        assert resposta.status_code == 302
        assert DocumentTemplate.objects.filter(pk=origem.pk).exists()

    def test_modelo_travado_nao_e_excluido(self, cliente, tipo):
        travado = DocumentTemplate.objects.create(
            type=tipo, name="Travado", slug="travado-excl", language="pt", is_locked=True
        )

        resposta = _excluir(cliente, travado)

        assert resposta.status_code == 302
        assert DocumentTemplate.objects.filter(pk=travado.pk).exists()

    def test_excluir_nao_usa_queryset_delete_para_contornar_a_guarda(
        self, cliente, oficiais
    ):
        """
        Prova indireta: se a view usasse `queryset.delete()`, a guarda de
        `DocumentTemplate.delete()` não rodaria e o oficial sumiria.
        """
        origem = oficiais["pt"]

        _excluir(cliente, origem)

        assert DocumentTemplate.objects.filter(pk=origem.pk, is_system=True).exists()

    def test_excluir_exige_post(self, cliente, modelo):
        assert cliente.get(
            reverse("backoffice:document_library_delete", args=[modelo.pk])
        ).status_code == 405

    def test_usuario_comum_nao_exclui(self, client, user, modelo):
        client.force_login(user)

        assert _excluir(client, modelo).status_code == 403

    def test_botao_excluir_nao_aparece_para_oficial(self, cliente, oficiais):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()
        url_excluir = reverse(
            "backoffice:document_library_delete", args=[oficiais["fr"].pk]
        )

        assert url_excluir not in html

    def test_botao_excluir_nao_aparece_para_travado(self, cliente, tipo):
        travado = DocumentTemplate.objects.create(
            type=tipo, name="Travado", slug="travado-html", language="pt", is_locked=True
        )

        html = cliente.get(reverse("backoffice:document_library")).content.decode()
        url_excluir = reverse("backoffice:document_library_delete", args=[travado.pk])

        assert url_excluir not in html

    def test_botao_excluir_aparece_para_modelo_comum(self, cliente, modelo):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()
        url_excluir = reverse("backoffice:document_library_delete", args=[modelo.pk])

        assert url_excluir in html


# ---------------------------------------------------------------------------
# 6. Filtros
# ---------------------------------------------------------------------------


class TestFiltros:
    def test_filtro_por_idioma(self, cliente, oficiais):
        resposta = cliente.get(reverse("backoffice:document_library"), {"language": "fr"})

        idiomas = {m.language for m in resposta.context["modelos"]}
        assert idiomas == {"fr"}

    def test_filtro_por_tipo(self, cliente, modelo, oficiais):
        tipo_carta = oficiais["fr"].type

        resposta = cliente.get(
            reverse("backoffice:document_library"), {"type": tipo_carta.pk}
        )

        tipos = {m.type_id for m in resposta.context["modelos"]}
        assert tipos == {tipo_carta.pk}

    def test_filtro_somente_oficiais(self, cliente, modelo, oficiais):
        resposta = cliente.get(reverse("backoffice:document_library"), {"system": "1"})

        assert all(m.is_system for m in resposta.context["modelos"])
        assert modelo not in resposta.context["modelos"]

    def test_filtro_somente_comuns(self, cliente, modelo, oficiais):
        resposta = cliente.get(reverse("backoffice:document_library"), {"system": "0"})

        assert all(not m.is_system for m in resposta.context["modelos"])
        assert modelo in resposta.context["modelos"]

    def test_filtro_somente_ativos(self, cliente, tipo):
        DocumentTemplate.objects.create(
            type=tipo, name="Inativo", slug="inativo", language="pt", is_active=False
        )

        resposta = cliente.get(reverse("backoffice:document_library"), {"active": "1"})

        assert all(m.is_active for m in resposta.context["modelos"])

    def test_sem_filtro_mostra_tudo(self, cliente, modelo, oficiais):
        resposta = cliente.get(reverse("backoffice:document_library"))

        assert len(resposta.context["modelos"]) >= 5  # 4 oficiais + 1 comum


# ---------------------------------------------------------------------------
# 7. Navegação
# ---------------------------------------------------------------------------


class TestNavegacao:
    def test_o_menu_aponta_para_a_biblioteca_nova(self, cliente):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert reverse("backoffice:document_library") in html

    def test_o_item_modelos_do_menu_nao_aponta_mais_para_a_tela_antiga(self, cliente, modelo):
        """A tela antiga (`documents.html`) não é mais alcançada pelo menu."""
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert reverse("backoffice:documents") not in html

    def test_a_biblioteca_marca_modelos_como_item_ativo_do_menu(self, cliente, modelo):
        resposta = cliente.get(reverse("backoffice:document_library"))

        assert resposta.context["active"] == "templates"

    def test_a_rota_da_biblioteca_e_distinta_da_do_editor(self):
        assert reverse("backoffice:document_library") != reverse(
            "backoffice:template_editor", args=[1]
        )


# ---------------------------------------------------------------------------
# 8. A arquitetura antiga continua existindo, mas não é mais o caminho
# ---------------------------------------------------------------------------


class TestArquiteturaAntigaPreservada:
    def test_a_rota_antiga_continua_registrada(self, cliente, draft_version):
        """As rotas/testes da 4.2C não foram tocados."""
        resposta = cliente.get(reverse("backoffice:documents"))

        assert resposta.status_code == 200

    def test_a_view_antiga_ainda_le_templateversion(self, cliente, draft_version):
        resposta = cliente.get(reverse("backoffice:documents"))

        assert "templates" in resposta.context  # o nome de contexto da tela antiga

    def test_letters_e_lettertemplate_nao_sao_tocados_pela_biblioteca(
        self, cliente, modelo, draft_version
    ):
        from apps.doctemplates.models import LetterTemplate, TemplateVersion

        antes_lt = list(LetterTemplate.objects.values())
        antes_tv = list(TemplateVersion.objects.values())

        cliente.get(reverse("backoffice:document_library"))

        assert list(LetterTemplate.objects.values()) == antes_lt
        assert list(TemplateVersion.objects.values()) == antes_tv
