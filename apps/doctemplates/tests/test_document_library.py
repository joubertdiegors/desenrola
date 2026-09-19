"""
Biblioteca de modelos da nova arquitetura (Etapa 3.2.1).

O fio condutor: esta tela e a nova porta de entrada de "Modelos" no
backoffice, e sua ÚNICA fonte de dados é `DocumentTemplate`. Nenhum
teste aqui deve depender de `LetterTemplate`/`TemplateVersion` --
inclusive há um teste que confere isso na resposta HTTP real.

A tela antiga de versionamento (`/backoffice/documentos/`) foi aposentada
na Etapa 3.5.3: esta é a única biblioteca de modelos do produto.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse

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
def staff(db, permissao_backoffice, permissoes_de_modelos):
    """
    Quem administra: `is_staff` E `core.access_backoffice`.

    Tres permissoes: entrar no Backoffice e as duas da biblioteca de
    modelos (ver e administrar). A flag `is_staff` sozinha nao abre nada
    desde a etapa do ciclo de vida.
    """
    usuario = get_user_model().objects.create_user(
        email="biblioteca@desenrola.be", password=SENHA, full_name="Admin", is_staff=True
    )
    usuario.user_permissions.add(permissao_backoffice, *permissoes_de_modelos)
    return get_user_model().objects.get(pk=usuario.pk)


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
        corpo = resposta.content.decode()

        assert modelo in resposta.context["modelos"]
        assert all(not m.is_system for m in resposta.context["modelos"])
        # A palavra "Oficial" tambem vive no filtro ("Oficiais") e na
        # janela de detalhes, que nasce escondida -- procura-la na
        # pagina inteira nao diz nada. A pergunta certa e se alguma
        # LINHA se declara oficial: a badge da linha e a unica
        # `mod-pilula-oficial` sem `data-campo`.
        assert 'mod-pilula-oficial">' not in corpo
        assert 'data-oficial="1"' not in corpo

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
    def test_o_link_editar_sai_do_detalhe(self, cliente, modelo):
        """
        A listagem leva ao DETALHE; é de lá que se abre o editor. Uma
        linha de tabela com quatro ações vira ruído -- o detalhe é
        onde a pessoa decide o que fazer com o modelo.
        """
        html = cliente.get(
            reverse("backoffice:document_detail", args=[modelo.pk])
        ).content.decode()

        assert reverse("backoffice:template_editor", args=[modelo.pk]) in html

    def test_a_listagem_leva_ao_detalhe(self, cliente, modelo):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert reverse("backoffice:document_detail", args=[modelo.pk]) in html

    def test_o_link_nao_aponta_para_o_editor_antigo(self, cliente, modelo):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert "/documentos/" not in html

    def test_modelo_editavel_mostra_rotulo_editar(self, cliente, modelo):
        html = cliente.get(
            reverse("backoffice:document_detail", args=[modelo.pk])
        ).content.decode()

        assert "Editar no editor" in html

    def test_modelo_oficial_destravado_mostra_rotulo_editar(self, cliente, oficiais):
        """
        Rodada 19: quem decide é `is_locked` (`editor_views._pode_editar`),
        oficial ou não. Destravado, a ação oferecida é EDITAR.
        """
        fr = oficiais["fr"]
        html = cliente.get(
            reverse("backoffice:document_detail", args=[fr.pk])
        ).content.decode()

        assert "Editar no editor" in html
        assert "Ver no editor" not in html

    def test_modelo_oficial_travado_mostra_rotulo_ver(self, cliente, oficiais):
        """Travado, a ação oferecida é VER, e a tela explica o porquê."""
        fr = oficiais["fr"]
        DocumentTemplate.objects.filter(pk=fr.pk).update(is_locked=True)
        html = cliente.get(
            reverse("backoffice:document_detail", args=[fr.pk])
        ).content.decode()

        assert "Ver no editor" in html
        assert "está travado" in html

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
        # E inativa: o português continua no oficial até alguém trocar.
        assert copia.is_active is False

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


class TestNaoExisteExclusao:
    """
    A biblioteca não apaga modelo nenhum -- foi uma decisão desta etapa.

    Um modelo pode ter cartas apontando para ele
    (`Letter.document_template`, PROTECT) e, mesmo sem nenhuma, sumir com
    o registro é irreversível onde desativar resolve: o modelo sai das
    opções de carta nova e todo o histórico continua reproduzível.

    Antes existia exclusão de modelo comum e destravado. A capacidade foi
    retirada, e esta classe é o que impede que volte por descuido.
    """

    def test_a_rota_de_excluir_nao_existe(self):
        from django.urls import NoReverseMatch

        with pytest.raises(NoReverseMatch):
            reverse("backoffice:document_library_delete", args=[1])

    def test_a_biblioteca_nao_oferece_exclusao(self, cliente, modelo):
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert "Excluir" not in html

    def test_o_detalhe_nao_oferece_exclusao(self, cliente, modelo):
        html = cliente.get(
            reverse("backoffice:document_detail", args=[modelo.pk])
        ).content.decode()

        assert "Excluir" not in html

    def test_nenhuma_view_da_biblioteca_apaga(self):
        """A view não chama `.delete()` em lugar nenhum."""
        import inspect

        from apps.doctemplates import library_views

        codigo = inspect.getsource(library_views)

        assert ".delete()" not in codigo


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

    def test_filtro_por_situacao(self, cliente, tipo):
        """
        Três situações, três listas, e cada modelo em uma só: desligado
        (inativo), ligado sem desenho utilizável (rascunho) e ligado e
        pronto (ativo). Chamar o rascunho de "ativo" seria a tela
        mentindo: o assistente recusa emitir carta com ele.
        """
        url = reverse("backoffice:document_library")
        inativo = DocumentTemplate.objects.create(
            type=tipo, name="Inativo", slug="inativo", language="pt", is_active=False
        )
        rascunho = DocumentTemplate.objects.create(
            type=tipo, name="Rascunho", slug="rascunho", language="pt"
        )
        pronto = DocumentTemplate.objects.create(
            type=tipo, name="Pronto", slug="pronto", language="en",
            layout={
                "version": 1,
                "elements": [{
                    "id": "e1", "type": "text", "x": 10.0, "y": 10.0,
                    "width": 100.0, "height": 20.0,
                    "properties": {"content": {"kind": "text", "value": "Olá"}},
                }],
            },
        )

        ativos = cliente.get(url, {"situacao": "ativo"}).context["modelos"]
        rascunhos = cliente.get(url, {"situacao": "rascunho"}).context["modelos"]
        inativos = cliente.get(url, {"situacao": "inativo"}).context["modelos"]

        assert all(m.is_active for m in ativos)
        assert pronto in ativos and rascunho not in ativos and inativo not in ativos
        assert rascunho in rascunhos and pronto not in rascunhos
        assert inativo in inativos and rascunho not in inativos

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

    def test_o_menu_nao_aponta_para_a_tela_aposentada(self, cliente, modelo):
        """`/backoffice/documentos/` não existe mais (Etapa 3.5.3)."""
        html = cliente.get(reverse("backoffice:document_library")).content.decode()

        assert "/backoffice/documentos/" not in html

    def test_a_biblioteca_marca_modelos_como_item_ativo_do_menu(self, cliente, modelo):
        resposta = cliente.get(reverse("backoffice:document_library"))

        assert resposta.context["active"] == "templates"

    def test_a_rota_da_biblioteca_e_distinta_da_do_editor(self):
        assert reverse("backoffice:document_library") != reverse(
            "backoffice:template_editor", args=[1]
        )


# ---------------------------------------------------------------------------
# 8. A tela antiga de versionamento foi aposentada
# ---------------------------------------------------------------------------


class TestTelaAntigaAposentada:
    @pytest.mark.parametrize(
        "nome",
        [
            "documents",
            "document_editor",
            "document_save",
            "document_publish",
            "document_import_official",
            "document_new_version",
        ],
    )
    def test_as_rotas_da_tela_antiga_nao_existem_mais(self, nome):
        """
        Etapa 3.5.3: `/backoffice/documentos/` e o editor visual da
        4.2A/4.2C saíram do produto. Reverter por engano reintroduziria
        uma segunda arquitetura de documentos.
        """
        with pytest.raises(NoReverseMatch):
            reverse(f"backoffice:{nome}")

    def test_as_cartas_nao_sao_tocadas_pela_biblioteca(self, cliente, modelo, letter):
        """
        Substitui o antigo teste sobre `LetterTemplate`/
        `TemplateVersion` (tabelas removidas): abrir a biblioteca e
        uma leitura -- nao mexe em nenhuma carta, nem no vinculo dela
        com o modelo.
        """
        from apps.letters.models import Letter

        antes = list(Letter.objects.values())

        cliente.get(reverse("backoffice:document_library"))

        assert list(Letter.objects.values()) == antes
