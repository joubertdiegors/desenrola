"""
"Bloquear modelo": a ação que liga o cadeado pelo Backoffice (Rodada 21).

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que um modelo destravado (oficial ou não) não tenha como ser
   bloqueado sem o Django Admin.** A ação existe no detalhe e no
   editor, e as duas levam ao mesmo lugar;
2. **Que bloquear um modelo comece a aceitar "desbloquear" por aqui.**
   É uma via só: ligar o cadeado. Desligar continua sendo
   administração ou duplicar -- não há botão de volta nesta tela;
3. **Que bloquear enfraqueça qualquer proteção existente.** As regras
   de `DocumentTemplate.save()` (Rodadas 18-19) continuam intactas: um
   oficial travado continua só aceitando description/is_active/
   is_locked; um travado comum continua recusando os campos
   estruturais;
4. **Que a permissão da ação não seja a mesma da biblioteca.** É
   `doctemplates.change_documenttemplate` -- a mesma que já abre o
   editor e duplica, não uma nova;
5. **Que travar pelo detalhe e travar pelo editor divirjam.** Os dois
   usam a MESMA view (`document_library_lock`), só o `voltar` muda.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.doctemplates.models import DocumentTemplate, DocumentTemplateLockedError, DocumentType
from apps.doctemplates.services import biblioteca

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"


@pytest.fixture
def tipo(db):
    return DocumentType.objects.create(
        code="contrato", name="Contrato", page={"width": 595.2756, "unit": "pt"}
    )


@pytest.fixture
def modelo(tipo):
    """Modelo comum, destravado -- o caso normal."""
    return DocumentTemplate.objects.create(
        type=tipo, name="Meu contrato", slug="meu-contrato", language="pt"
    )


@pytest.fixture
def oficial(db):
    """Um dos quatro oficiais, destravado -- o caso do pedido do cliente."""
    _, modelos = biblioteca.semear()
    fr = next(m for m in modelos if m.language == "fr")
    assert fr.is_locked is False
    return fr


@pytest.fixture
def administradora(db, permissao_backoffice, permissoes_de_modelos):
    usuario = get_user_model().objects.create_user(
        email="bloqueio@desenrola.be", password=SENHA, full_name="Admin", is_staff=True
    )
    usuario.user_permissions.add(permissao_backoffice, *permissoes_de_modelos)
    return get_user_model().objects.get(pk=usuario.pk)


@pytest.fixture
def cliente(client, administradora):
    client.force_login(administradora)
    return client


@pytest.fixture
def leitora(db, permissao_backoffice):
    """Só `view_documenttemplate` -- vê a biblioteca, não administra."""
    from django.contrib.auth.models import Permission

    usuario = get_user_model().objects.create_user(
        email="leitora-bloqueio@desenrola.be", password=SENHA, full_name="Leitora", is_staff=True
    )
    usuario.user_permissions.add(
        permissao_backoffice,
        Permission.objects.get(
            content_type__app_label="doctemplates", codename="view_documenttemplate"
        ),
    )
    return get_user_model().objects.get(pk=usuario.pk)


def _bloquear(client, modelo, **extra):
    return client.post(reverse("backoffice:document_library_lock", args=[modelo.pk]), extra)


def _url_editor(modelo):
    return reverse("backoffice:template_editor", args=[modelo.pk])


def _url_detalhe(modelo):
    return reverse("backoffice:document_detail", args=[modelo.pk])


# ===========================================================================
# 1. A ação aparece só quando o modelo está destravado
# ===========================================================================


class TestBotaoNaTela:
    def test_o_detalhe_mostra_bloquear_quando_destravado(self, cliente, modelo):
        html = cliente.get(_url_detalhe(modelo)).content.decode()

        assert "Bloquear modelo" in html
        assert f'action="{reverse("backoffice:document_library_lock", args=[modelo.pk])}"' in html

    def test_o_detalhe_do_oficial_destravado_tambem_mostra_bloquear(self, cliente, oficial):
        html = cliente.get(_url_detalhe(oficial)).content.decode()

        assert "Bloquear modelo" in html

    def test_travado_nao_mostra_bloquear_no_detalhe(self, cliente, modelo):
        DocumentTemplate.objects.filter(pk=modelo.pk).update(is_locked=True)

        html = cliente.get(_url_detalhe(modelo)).content.decode()

        assert "Bloquear modelo" not in html

    def test_o_editor_destravado_mostra_bloquear_ao_lado_de_salvar(self, cliente, modelo):
        html = cliente.get(_url_editor(modelo)).content.decode()

        assert "Bloquear" in html
        assert 'data-acao="salvar"' in html
        assert f'action="{reverse("backoffice:document_library_lock", args=[modelo.pk])}"' in html

    def test_o_editor_do_oficial_destravado_tambem_mostra_bloquear(self, cliente, oficial):
        html = cliente.get(_url_editor(oficial)).content.decode()

        assert "Bloquear" in html
        assert 'data-acao="salvar"' in html

    def test_o_editor_travado_nao_mostra_bloquear_nem_salvar(self, cliente, modelo):
        DocumentTemplate.objects.filter(pk=modelo.pk).update(is_locked=True)

        html = cliente.get(_url_editor(modelo)).content.decode()

        assert 'action="{}"'.format(
            reverse("backoffice:document_library_lock", args=[modelo.pk])
        ) not in html
        assert 'data-acao="salvar"' not in html

    def test_quem_so_ve_nao_recebe_o_botao(self, client, leitora, modelo):
        client.force_login(leitora)

        detalhe = client.get(_url_detalhe(modelo)).content.decode()

        assert "Bloquear modelo" not in detalhe


# ===========================================================================
# 2. Bloquear funciona -- no oficial e no comum
# ===========================================================================


class TestBloquear:
    def test_bloqueia_um_modelo_comum(self, cliente, modelo):
        resposta = _bloquear(cliente, modelo)

        modelo.refresh_from_db()
        assert resposta.status_code == 302
        assert modelo.is_locked is True

    def test_bloqueia_um_oficial_destravado(self, cliente, oficial):
        """O pedido do cliente: abrir, ajustar, salvar e então bloquear."""
        resposta = _bloquear(cliente, oficial)

        oficial.refresh_from_db()
        assert resposta.status_code == 302
        assert oficial.is_locked is True

    def test_bloquear_o_oficial_nao_mexe_no_layout_nem_na_identidade(self, cliente, oficial):
        layout_antes = oficial.layout
        nome_antes = oficial.name

        _bloquear(cliente, oficial)

        oficial.refresh_from_db()
        assert oficial.layout == layout_antes
        assert oficial.name == nome_antes
        assert oficial.is_system is True

    def test_bloquear_ja_bloqueado_nao_da_erro(self, cliente, modelo):
        DocumentTemplate.objects.filter(pk=modelo.pk).update(is_locked=True)

        resposta = _bloquear(cliente, modelo)

        assert resposta.status_code == 302
        modelo.refresh_from_db()
        assert modelo.is_locked is True

    def test_volta_para_o_detalhe_por_padrao(self, cliente, modelo):
        resposta = _bloquear(cliente, modelo)

        assert resposta.url == _url_detalhe(modelo)

    def test_volta_para_o_editor_quando_pedido_de_la(self, cliente, modelo):
        resposta = _bloquear(cliente, modelo, voltar="editor")

        assert resposta.url == _url_editor(modelo)

    def test_get_nao_bloqueia(self, cliente, modelo):
        assert cliente.get(
            reverse("backoffice:document_library_lock", args=[modelo.pk])
        ).status_code == 405
        modelo.refresh_from_db()
        assert modelo.is_locked is False


# ===========================================================================
# 3. Depois de bloqueado: somente leitura, sem "Salvar modelo"
# ===========================================================================


class TestDepoisDeBloqueado:
    def test_o_editor_abre_em_leitura(self, cliente, modelo):
        _bloquear(cliente, modelo)

        resposta = cliente.get(_url_editor(modelo))

        assert resposta.context["editavel"] is False
        assert "travado" in resposta.context["motivo_da_leitura"].lower()

    def test_o_editor_do_oficial_bloqueado_tambem_abre_em_leitura(self, cliente, oficial):
        _bloquear(cliente, oficial)

        resposta = cliente.get(_url_editor(oficial))

        assert resposta.context["editavel"] is False

    def test_salvar_e_recusado_depois_de_bloqueado(self, cliente, modelo):
        import json

        _bloquear(cliente, modelo)

        resposta = cliente.post(
            reverse("backoffice:template_editor_save", args=[modelo.pk]),
            data=json.dumps({"layout": {"version": 1, "elements": []}}),
            content_type="application/json",
        )

        assert resposta.status_code == 409

    def test_o_html_do_editor_nao_traz_mais_salvar_nem_bloquear(self, cliente, modelo):
        _bloquear(cliente, modelo)

        html = cliente.get(_url_editor(modelo)).content.decode()

        assert 'data-acao="salvar"' not in html
        assert "Bloquear" not in html

    def test_o_detalhe_mostra_o_estado_bloqueado(self, cliente, modelo):
        _bloquear(cliente, modelo)

        html = cliente.get(_url_detalhe(modelo)).content.decode()

        assert "Bloqueado" in html
        assert "Bloquear modelo" not in html

    def test_nao_ha_botao_de_desbloquear_em_lugar_nenhum(self, cliente, modelo):
        _bloquear(cliente, modelo)

        detalhe = cliente.get(_url_detalhe(modelo)).content.decode()
        editor = cliente.get(_url_editor(modelo)).content.decode()

        assert "Desbloquear" not in detalhe
        assert "Desbloquear" not in editor


# ===========================================================================
# 4. As proteções de sempre continuam de pé
# ===========================================================================


class TestProtecoesIntactas:
    def test_travado_continua_recusando_campo_estrutural(self, modelo):
        DocumentTemplate.objects.filter(pk=modelo.pk).update(is_locked=True)
        recarregado = DocumentTemplate.objects.get(pk=modelo.pk)
        recarregado.slug = "outro-slug"

        with pytest.raises(DocumentTemplateLockedError):
            recarregado.save()

    def test_oficial_travado_continua_recusando_o_layout(self, oficial):
        DocumentTemplate.objects.filter(pk=oficial.pk).update(is_locked=True)
        recarregado = DocumentTemplate.objects.get(pk=oficial.pk)
        recarregado.layout = {"version": 1, "elements": []}

        with pytest.raises(DocumentTemplateLockedError):
            recarregado.save()

    def test_oficial_travado_continua_recusando_a_identidade(self, oficial):
        DocumentTemplate.objects.filter(pk=oficial.pk).update(is_locked=True)
        recarregado = DocumentTemplate.objects.get(pk=oficial.pk)
        recarregado.name = "Outro nome"

        with pytest.raises(DocumentTemplateLockedError):
            recarregado.save()

    def test_travado_continua_recusando_exclusao(self, modelo):
        DocumentTemplate.objects.filter(pk=modelo.pk).update(is_locked=True)
        recarregado = DocumentTemplate.objects.get(pk=modelo.pk)

        with pytest.raises(DocumentTemplateLockedError):
            recarregado.delete()


# ===========================================================================
# 5. Permissões: a mesma da biblioteca, no servidor
# ===========================================================================


class TestPermissoes:
    def test_anonimo_vai_para_o_login(self, client, modelo):
        resposta = client.post(reverse("backoffice:document_library_lock", args=[modelo.pk]))

        assert resposta.status_code == 302
        assert "/accounts/login/" in resposta.url

    def test_quem_so_ve_nao_bloqueia(self, client, leitora, modelo):
        client.force_login(leitora)

        resposta = _bloquear(client, modelo)

        assert resposta.status_code == 403
        modelo.refresh_from_db()
        assert modelo.is_locked is False

    def test_usuario_comum_recebe_403(self, client, user, modelo):
        client.force_login(user)

        assert _bloquear(client, modelo).status_code == 403

    def test_duplicar_continua_funcionando_depois_do_bloqueio(self, cliente, oficial):
        """A ação de bloquear não tranca o caminho de criação do produto."""
        _bloquear(cliente, oficial)

        resposta = cliente.post(
            reverse("backoffice:document_library_duplicate", args=[oficial.pk]),
            {"name": "Cópia depois de bloqueado"},
        )

        assert resposta.status_code == 302
        copia = DocumentTemplate.objects.get(name="Cópia depois de bloqueado")
        assert copia.is_locked is False
        assert cliente.get(_url_editor(copia)).context["editavel"] is True
