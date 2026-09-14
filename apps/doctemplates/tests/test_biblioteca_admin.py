"""
A biblioteca de modelos como CENTRO DE GESTÃO: permissões, detalhe,
duplicação, situação e a integração com editor, wizard e PDF.

`test_document_library.py` continua cobrindo a listagem e a duplicação
pela tela; aqui entram as partes novas desta etapa e, principalmente, as
integrações -- que é onde uma biblioteca "bonita" costuma mentir.

AS DUAS PERMISSÕES
------------------
`doctemplates.view_documenttemplate` para VER;
`change_documenttemplate` para ADMINISTRAR. As duas são as que o Django
cria sozinho para o modelo -- não houve necessidade de inventar uma
`manage_templates`.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from apps.doctemplates.models import DocumentTemplate, DocumentType
from apps.doctemplates.services import biblioteca

pytestmark = pytest.mark.django_db

BIBLIOTECA = reverse("backoffice:document_library")
SENHA = "senha-de-teste-123"


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


def permissao(app_label, codename):
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


@pytest.fixture
def perm_backoffice(db):
    return permissao("core", "access_backoffice")


@pytest.fixture
def perm_ver(db):
    return permissao("doctemplates", "view_documenttemplate")


@pytest.fixture
def perm_administrar(db):
    return permissao("doctemplates", "change_documenttemplate")


def criar_pessoa(email, nome, *perms):
    User = get_user_model()
    pessoa = User.objects.create_user(email=email, password=SENHA, full_name=nome)
    if perms:
        pessoa.user_permissions.set(perms)
    return User.objects.get(pk=pessoa.pk)


@pytest.fixture
def administrador(perm_backoffice, perm_ver, perm_administrar):
    return criar_pessoa(
        "admin@desenrola.be", "Admin Modelos", perm_backoffice, perm_ver, perm_administrar
    )


@pytest.fixture
def so_leitor(perm_backoffice, perm_ver):
    """Vê a biblioteca, mas não administra."""
    return criar_pessoa("leitor@desenrola.be", "Só Leitura", perm_backoffice, perm_ver)


@pytest.fixture
def sem_modelos(perm_backoffice):
    """Entra no Backoffice, mas não tem nada a ver com modelos."""
    return criar_pessoa("outro@desenrola.be", "Sem Modelos", perm_backoffice)


@pytest.fixture
def cliente(client, administrador):
    client.force_login(administrador)
    return client


@pytest.fixture
def oficiais(db):
    _, modelos = biblioteca.semear()
    return {m.language: m for m in modelos}


@pytest.fixture
def tipo(db):
    return DocumentType.objects.create(
        code="tipo-de-teste", name="Tipo de teste", page={"width": 1, "height": 1, "unit": "pt"}
    )


@pytest.fixture
def comum(tipo):
    return DocumentTemplate.objects.create(
        type=tipo, name="Modelo comum", slug="modelo-comum", language="pt"
    )


def url_detalhe(modelo):
    return reverse("backoffice:document_detail", args=[modelo.pk])


def url_situacao(modelo):
    return reverse("backoffice:document_library_activation", args=[modelo.pk])


def url_duplicar(modelo):
    return reverse("backoffice:document_library_duplicate", args=[modelo.pk])


# ===========================================================================
# 9-12. Permissões
# ===========================================================================


class TestPermissoes:
    def test_usuario_comum_nao_entra(self, client, db):
        client.force_login(criar_pessoa("ze@exemplo.be", "Zé"))

        assert client.get(BIBLIOTECA).status_code == 403

    def test_backoffice_sem_permissao_de_modelos_nao_entra(self, client, sem_modelos):
        """Entrar na área administrativa não dá acesso à biblioteca."""
        client.force_login(sem_modelos)

        assert client.get(BIBLIOTECA).status_code == 403

    def test_quem_pode_ver_entra(self, client, so_leitor):
        client.force_login(so_leitor)

        assert client.get(BIBLIOTECA).status_code == 200

    def test_quem_so_ve_nao_administra(self, client, so_leitor, comum):
        """Ver e alterar são permissões diferentes -- e o servidor sabe."""
        client.force_login(so_leitor)

        duplicar = client.post(url_duplicar(comum), {"name": "Tentativa"})
        situacao = client.post(url_situacao(comum), {"ativo": "0"})

        assert duplicar.status_code == 403
        assert situacao.status_code == 403
        assert DocumentTemplate.objects.get(pk=comum.pk).is_active is True
        assert not DocumentTemplate.objects.filter(name="Tentativa").exists()

    def test_quem_so_ve_nao_salva_no_editor(self, client, so_leitor, comum):
        client.force_login(so_leitor)

        resposta = client.post(
            reverse("backoffice:template_editor_save", args=[comum.pk]),
            data="{}",
            content_type="application/json",
        )

        assert resposta.status_code == 403

    def test_quem_so_ve_abre_o_editor_em_leitura(self, client, so_leitor, comum):
        """
        Consultar o desenho é legítimo para quem pode ver; o que falta é
        a permissão de gravar.
        """
        client.force_login(so_leitor)

        resposta = client.get(reverse("backoffice:template_editor", args=[comum.pk]))

        assert resposta.status_code == 200
        assert resposta.context["editavel"] is False
        assert "não tem permissão para alterá-lo" in resposta.content.decode()

    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(BIBLIOTECA)

        assert resposta.status_code == 302
        assert reverse("accounts:login") in resposta.url

    @pytest.mark.parametrize(
        "rota", ["document_detail", "document_library_duplicate", "document_library_activation"]
    )
    def test_acesso_direto_a_cada_url_sem_autorizacao(self, client, sem_modelos, comum, rota):
        """Cada URL é alcançável por conta própria -- e é o que se tentaria."""
        client.force_login(sem_modelos)
        url = reverse(f"backoffice:{rota}", args=[comum.pk])

        resposta = client.get(url) if rota == "document_detail" else client.post(url)

        assert resposta.status_code == 403

    def test_o_menu_so_mostra_modelos_para_quem_pode_ver(
        self, client, administrador, sem_modelos
    ):
        client.force_login(administrador)
        com = client.get(reverse("backoffice:overview")).content.decode()
        client.force_login(sem_modelos)
        sem = client.get(reverse("backoffice:overview")).content.decode()

        assert BIBLIOTECA in com
        assert BIBLIOTECA not in sem


# ===========================================================================
# 1-8. Listagem: busca, filtros, paginação
# ===========================================================================


class TestListagem:
    def test_busca_por_nome(self, cliente, comum, oficiais):
        corpo = cliente.get(BIBLIOTECA, {"q": "comum"}).content.decode()

        assert comum.slug in corpo
        assert oficiais["fr"].slug not in corpo

    def test_busca_por_identificador(self, cliente, comum, oficiais):
        corpo = cliente.get(BIBLIOTECA, {"q": "carta-convite-fr"}).content.decode()

        assert oficiais["fr"].slug in corpo
        assert comum.slug not in corpo

    def test_filtro_por_tipo(self, cliente, comum, oficiais):
        corpo = cliente.get(BIBLIOTECA, {"type": str(comum.type_id)}).content.decode()

        assert comum.slug in corpo
        assert oficiais["fr"].slug not in corpo

    def test_filtro_por_idioma(self, cliente, oficiais):
        corpo = cliente.get(BIBLIOTECA, {"language": "nl"}).content.decode()

        assert oficiais["nl"].slug in corpo
        assert oficiais["fr"].slug not in corpo

    def test_filtro_por_situacao(self, cliente, comum, oficiais):
        DocumentTemplate.objects.filter(pk=comum.pk).update(is_active=False)

        inativos = cliente.get(BIBLIOTECA, {"active": "0"}).content.decode()
        ativos = cliente.get(BIBLIOTECA, {"active": "1"}).content.decode()

        assert comum.slug in inativos and oficiais["fr"].slug not in inativos
        assert oficiais["fr"].slug in ativos and comum.slug not in ativos

    def test_filtro_por_natureza(self, cliente, comum, oficiais):
        so_oficiais = cliente.get(BIBLIOTECA, {"system": "1"}).content.decode()
        so_comuns = cliente.get(BIBLIOTECA, {"system": "0"}).content.decode()

        assert oficiais["fr"].slug in so_oficiais and comum.slug not in so_oficiais
        assert comum.slug in so_comuns and oficiais["fr"].slug not in so_comuns

    def test_filtros_combinam(self, cliente, oficiais):
        corpo = cliente.get(BIBLIOTECA, {"system": "1", "language": "pt"}).content.decode()

        assert oficiais["pt"].slug in corpo
        assert oficiais["en"].slug not in corpo

    def test_filtro_invalido_nao_quebra(self, cliente, comum):
        """Querystring é entrada do cliente: lixo não derruba a tela."""
        resposta = cliente.get(BIBLIOTECA, {"type": "abc", "active": "talvez"})

        assert resposta.status_code == 200

    def test_paginacao(self, cliente, tipo):
        from apps.doctemplates.library_views import POR_PAGINA

        for numero in range(POR_PAGINA + 3):
            DocumentTemplate.objects.create(
                type=tipo, name=f"Modelo {numero:03d}", slug=f"modelo-{numero:03d}", language="pt"
            )

        primeira = cliente.get(BIBLIOTECA)
        segunda = cliente.get(BIBLIOTECA, {"page": 2})

        assert len(primeira.context["modelos"]) == POR_PAGINA
        assert segunda.context["pagina"].number == 2

    def test_o_filtro_roda_no_banco(self, cliente, comum, oficiais):
        """
        A consulta já sai filtrada do banco -- nada de trazer tudo e
        peneirar em Python. O `total` conta o que o SQL devolveu.
        """
        contexto = cliente.get(BIBLIOTECA, {"language": "nl"}).context

        assert contexto["total"] == 1
        assert contexto["pagina"].paginator.count == 1


# ===========================================================================
# 13-17. Detalhe
# ===========================================================================


class TestDetalhe:
    def test_mostra_a_identidade(self, cliente, oficiais):
        corpo = cliente.get(url_detalhe(oficiais["fr"])).content.decode()

        assert oficiais["fr"].name in corpo
        assert oficiais["fr"].slug in corpo
        assert "Oficial" in corpo

    def test_mostra_a_estrutura_do_layout(self, cliente, oficiais):
        """Os 23 elementos do modelo oficial, contados do layout real."""
        contexto = cliente.get(url_detalhe(oficiais["fr"])).context

        assert contexto["estrutura"]["elementos"] == 23
        assert contexto["estrutura"]["tipos"]
        assert contexto["estrutura"]["campos_do_formulario"] > 0

    def test_mostra_os_campos_dinamicos_usados(self, cliente, oficiais):
        contexto = cliente.get(url_detalhe(oficiais["fr"])).context

        campos = contexto["estrutura"]["campos"]
        assert "convidado.nome" in campos
        assert "anfitriao.nome" in campos

    def test_mostra_os_assets(self, cliente, oficiais, tmp_path, settings):
        """Os vínculos vêm de `DocumentTemplateAsset`, derivado do layout."""
        from apps.content.models import Asset
        from apps.doctemplates.services import carta_convite

        settings.MEDIA_ROOT = tmp_path
        carta_convite.reconstruir(DocumentTemplate, Asset, "fr")
        fr = DocumentTemplate.objects.get(slug="carta-convite-fr")

        contexto = cliente.get(url_detalhe(fr)).context

        assert [a.key for a in contexto["assets"]] == [carta_convite.LOGO_CHAVE_DO_ASSET]

    def test_modelo_sem_assets_diz_isso(self, cliente, comum):
        corpo = cliente.get(url_detalhe(comum)).content.decode()

        assert "não usa imagens" in corpo

    def test_mostra_a_origem_da_duplicacao(self, cliente, oficiais):
        cliente.post(url_duplicar(oficiais["fr"]), {"name": "Minha cópia"})
        copia = DocumentTemplate.objects.get(name="Minha cópia")

        corpo = cliente.get(url_detalhe(copia)).content.decode()

        assert oficiais["fr"].name in corpo
        assert url_detalhe(oficiais["fr"]) in corpo

    def test_a_origem_lista_as_copias(self, cliente, oficiais):
        cliente.post(url_duplicar(oficiais["fr"]), {"name": "Minha cópia"})

        corpo = cliente.get(url_detalhe(oficiais["fr"])).content.decode()

        assert "Minha cópia" in corpo

    def test_modelo_inexistente_da_404(self, cliente):
        assert cliente.get(reverse("backoffice:document_detail", args=[999999])).status_code == 404

    def test_quem_so_ve_nao_recebe_as_acoes(self, client, so_leitor, comum):
        client.force_login(so_leitor)

        resposta = client.get(url_detalhe(comum))

        assert resposta.context["pode_administrar"] is False
        assert url_situacao(comum) not in resposta.content.decode()


# ===========================================================================
# 18-26. Duplicação
# ===========================================================================


class TestDuplicacao:
    def test_cria_copia_independente(self, cliente, oficiais):
        fr = oficiais["fr"]

        cliente.post(url_duplicar(fr), {"name": "Cópia FR"})

        copia = DocumentTemplate.objects.get(name="Cópia FR")
        assert copia.pk != fr.pk
        assert copia.slug != fr.slug
        assert copia.duplicated_from_id == fr.pk
        assert copia.is_system is False
        assert copia.is_locked is False
        assert copia.is_active is True

    def test_o_layout_da_copia_e_independente(self, cliente, oficiais):
        """
        `deepcopy` de verdade: mexer num elemento ANINHADO da cópia não
        pode alcançar a origem.
        """
        fr = oficiais["fr"]
        cliente.post(url_duplicar(fr), {"name": "Cópia FR"})
        copia = DocumentTemplate.objects.get(name="Cópia FR")

        copia.layout["elements"][0]["x"] = 999.0
        copia.save(update_fields=["layout"])

        fr.refresh_from_db()
        assert fr.layout["elements"][0]["x"] != 999.0

    def test_o_field_schema_da_copia_e_independente(self, cliente, oficiais):
        fr = oficiais["fr"]
        cliente.post(url_duplicar(fr), {"name": "Cópia FR"})
        copia = DocumentTemplate.objects.get(name="Cópia FR")

        copia.field_schema["fields"][0]["label"] = "Mudou"
        copia.save(update_fields=["field_schema"])

        fr.refresh_from_db()
        assert fr.field_schema["fields"][0]["label"] != "Mudou"

    def test_a_copia_preserva_a_estrutura(self, cliente, oficiais):
        fr = oficiais["fr"]

        cliente.post(url_duplicar(fr), {"name": "Cópia FR"})

        copia = DocumentTemplate.objects.get(name="Cópia FR")
        assert copia.layout == fr.layout
        assert copia.field_schema == fr.field_schema
        assert copia.type_id == fr.type_id
        assert copia.language == fr.language

    def test_a_copia_herda_os_assets(self, cliente, oficiais, tmp_path, settings):
        """
        Os vínculos são derivados do layout a cada gravação: a cópia
        nasce apontando para os MESMOS assets, sem duplicar binário.
        """
        from apps.content.models import Asset
        from apps.doctemplates.services import carta_convite

        settings.MEDIA_ROOT = tmp_path
        carta_convite.reconstruir(DocumentTemplate, Asset, "fr")
        fr = DocumentTemplate.objects.get(slug="carta-convite-fr")

        cliente.post(url_duplicar(fr), {"name": "Cópia FR"})
        copia = DocumentTemplate.objects.get(name="Cópia FR")

        assert set(copia.asset_links.values_list("asset_id", flat=True)) == set(
            fr.asset_links.values_list("asset_id", flat=True)
        )

    def test_a_origem_nao_e_tocada(self, cliente, oficiais):
        fr = oficiais["fr"]
        antes = DocumentTemplate.objects.filter(pk=fr.pk).values().first()

        cliente.post(url_duplicar(fr), {"name": "Cópia FR"})

        depois = DocumentTemplate.objects.filter(pk=fr.pk).values().first()
        assert depois == antes

    def test_duplicar_exige_post(self, cliente, comum):
        assert cliente.get(url_duplicar(comum)).status_code == 405

    def test_a_copia_abre_editavel(self, cliente, oficiais):
        cliente.post(url_duplicar(oficiais["fr"]), {"name": "Cópia FR"})
        copia = DocumentTemplate.objects.get(name="Cópia FR")

        resposta = cliente.get(reverse("backoffice:template_editor", args=[copia.pk]))

        assert resposta.context["editavel"] is True


# ===========================================================================
# 27-30. Edição
# ===========================================================================


class TestEdicao:
    def test_o_editor_abre_o_modelo_real(self, cliente, comum):
        resposta = cliente.get(reverse("backoffice:template_editor", args=[comum.pk]))

        assert resposta.status_code == 200
        assert resposta.context["modelo"].pk == comum.pk

    def test_salva_o_layout(self, cliente, comum):
        import json

        layout = {
            "version": 1,
            "elements": [
                {
                    "id": "e1", "type": "text", "x": 10.0, "y": 10.0,
                    "width": 100.0, "height": 20.0,
                    "properties": {"content": {"kind": "text", "value": "Olá"}},
                }
            ],
        }

        resposta = cliente.post(
            reverse("backoffice:template_editor_save", args=[comum.pk]),
            data=json.dumps({"layout": layout}),
            content_type="application/json",
        )

        comum.refresh_from_db()
        assert resposta.status_code == 200
        assert comum.layout == layout

    def test_modelo_travado_nao_salva(self, cliente, tipo):
        import json

        travado = DocumentTemplate.objects.create(
            type=tipo, name="Travado", slug="travado", language="pt", is_locked=True
        )

        resposta = cliente.post(
            reverse("backoffice:template_editor_save", args=[travado.pk]),
            data=json.dumps({"layout": {"version": 1, "elements": []}}),
            content_type="application/json",
        )

        assert resposta.status_code == 409
        assert "travado" in resposta.json()["error"].lower()

    def test_modelo_travado_abre_em_leitura(self, cliente, tipo):
        travado = DocumentTemplate.objects.create(
            type=tipo, name="Travado", slug="travado", language="pt", is_locked=True
        )

        resposta = cliente.get(reverse("backoffice:template_editor", args=[travado.pk]))

        assert resposta.status_code == 200
        assert resposta.context["editavel"] is False

    def test_o_editor_volta_para_a_biblioteca(self, cliente, comum):
        """
        Biblioteca -> editor -> biblioteca. Antes o "voltar" apontava
        para o Django Admin, que não é o caminho do produto.
        """
        resposta = cliente.get(reverse("backoffice:template_editor", args=[comum.pk]))

        assert resposta.context["voltar_url"] == url_detalhe(comum)


# ===========================================================================
# 31-35. Situação
# ===========================================================================


class TestSituacao:
    def test_desativa(self, cliente, comum):
        cliente.post(url_situacao(comum), {"ativo": "0"})

        assert DocumentTemplate.objects.get(pk=comum.pk).is_active is False

    def test_ativa(self, cliente, comum):
        DocumentTemplate.objects.filter(pk=comum.pk).update(is_active=False)

        cliente.post(url_situacao(comum), {"ativo": "1"})

        assert DocumentTemplate.objects.get(pk=comum.pk).is_active is True

    def test_desativa_um_oficial(self, cliente, oficiais):
        """
        `is_active` é um dos três campos que um modelo oficial aceita
        mudar -- desativar é decisão administrativa legítima.
        """
        cliente.post(url_situacao(oficiais["nl"]), {"ativo": "0"})

        assert DocumentTemplate.objects.get(pk=oficiais["nl"].pk).is_active is False

    def test_GET_nao_altera(self, cliente, comum):
        resposta = cliente.get(url_situacao(comum))

        assert resposta.status_code == 405
        assert DocumentTemplate.objects.get(pk=comum.pk).is_active is True

    def test_sem_csrf_nao_altera(self, administrador, comum):
        from django.test import Client

        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(administrador)

        resposta = sem_token.post(url_situacao(comum), {"ativo": "0"})

        assert resposta.status_code == 403
        assert DocumentTemplate.objects.get(pk=comum.pk).is_active is True


# ===========================================================================
# 36-40. Modelos oficiais
# ===========================================================================


class TestModelosOficiais:
    def test_os_quatro_existem(self, oficiais):
        assert sorted(oficiais) == ["en", "fr", "nl", "pt"]
        assert all(m.is_system for m in oficiais.values())

    def test_continuam_destravados(self, oficiais):
        """Decisão desta fase: o bloqueio definitivo vem depois da aprovação."""
        assert all(m.is_locked is False for m in oficiais.values())

    def test_continuam_com_23_elementos(self, oficiais):
        for modelo in oficiais.values():
            assert len(modelo.layout["elements"]) == 23

    def test_nao_podem_ser_apagados(self, oficiais):
        from apps.doctemplates.models import DocumentTemplateLockedError

        with pytest.raises(DocumentTemplateLockedError):
            oficiais["fr"].delete()

    def test_nao_podem_ser_descaracterizados(self, oficiais):
        """
        A guarda é do MODELO (`SYSTEM_MUTABLE_FIELDS`), não da tela:
        um oficial não vira comum, não muda de idioma e não muda de nome.
        """
        from apps.doctemplates.models import DocumentTemplateLockedError

        fr = oficiais["fr"]
        for campo, valor in (("is_system", False), ("language", "en"), ("name", "Outro")):
            recarregado = DocumentTemplate.objects.get(pk=fr.pk)
            setattr(recarregado, campo, valor)
            with pytest.raises(DocumentTemplateLockedError):
                recarregado.save()

    def test_o_layout_de_um_oficial_nao_e_alterado_pelo_editor(self, cliente, oficiais):
        import json

        antes = oficiais["fr"].layout

        resposta = cliente.post(
            reverse("backoffice:template_editor_save", args=[oficiais["fr"].pk]),
            data=json.dumps({"layout": {"version": 1, "elements": []}}),
            content_type="application/json",
        )

        oficiais["fr"].refresh_from_db()
        assert resposta.status_code == 409
        assert oficiais["fr"].layout == antes


# ===========================================================================
# 41-44. Regressão: wizard, PDF, snapshot, supervisão
# ===========================================================================


class TestRegressao:
    @pytest.fixture
    def _nacionalidade(self, nacionalidade_factory):
        nacionalidade_factory("Brasileira", guest_form="Brésilienne")

    def test_modelo_inativo_sai_das_opcoes_de_carta_nova(
        self, modelos_oficiais_prontos, _nacionalidade
    ):
        """
        Desativar um oficial tira o idioma das opções -- sem estourar.
        A proteção já existia; esta etapa não pode tê-la afrouxado.
        """
        from apps.letters import services

        assert "nl" in services.available_languages()

        DocumentTemplate.objects.filter(slug="carta-convite-nl").update(is_active=False)

        assert "nl" not in services.available_languages()

    def test_o_assistente_nao_estoura_com_o_idioma_padrao_desativado(
        self, auth_client, modelos_oficiais_prontos, _nacionalidade
    ):
        from apps.letters import services

        DocumentTemplate.objects.filter(
            slug=f"carta-convite-{services.IDIOMA_PADRAO_DA_CARTA}"
        ).update(is_active=False)

        resposta = auth_client.get(reverse("letters:new"), follow=True)

        assert resposta.status_code == 200
        assert resposta.redirect_chain[-1][0] == reverse("core:dashboard")

    def test_carta_ja_emitida_continua_gerando_com_o_modelo_desativado(
        self, auth_client, user, modelos_oficiais_prontos, _nacionalidade
    ):
        """
        O PDF sai do `document_snapshot` congelado, não do modelo -- e é
        isso que faz desativar ser seguro.
        """
        from apps.letters import services
        from apps.letters.models import Letter

        chegada = timezone.localdate() + datetime.timedelta(days=30)
        auth_client.post(reverse("letters:new"), {
            "guest_name": "Carlos Eduardo Silva", "guest_nationality": "Brasileira",
            "guest_birth_date": "22/07/1990", "guest_passport": "YY0000",
        })
        carta = Letter.objects.get(user=user)
        passos = {
            2: {"stay_arrival": chegada.strftime("%d/%m/%Y"),
                "stay_departure": (chegada + datetime.timedelta(days=14)).strftime("%d/%m/%Y")},
            3: {"host_confirm": "on"},
            4: {"notice_informal": "on", "notice_prise_en_charge": "on"},
        }
        for numero, dados in passos.items():
            auth_client.post(reverse("letters:step", args=[carta.uuid, numero]), dados)
        auth_client.post(reverse("letters:step", args=[carta.uuid, 5]), {"language": "fr"})
        auth_client.post(reverse("letters:step", args=[carta.uuid, 6]))
        carta.refresh_from_db()

        DocumentTemplate.objects.filter(slug="carta-convite-fr").update(is_active=False)

        assert services.render_letter(carta)[:5] == b"%PDF-"

    def test_a_supervisao_de_cartas_nao_depende_da_permissao_de_modelos(
        self, client, administrador
    ):
        """Uma permissão não vaza para a outra seção."""
        assert client.get(reverse("backoffice:letters")).status_code in (302, 403)

        client.force_login(administrador)
        assert client.get(reverse("backoffice:letters")).status_code == 403
