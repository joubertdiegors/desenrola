"""
As declarações da etapa 4, agora administráveis.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que mudar o texto de uma declaração exija mexer no código.** Elas
   eram constantes (`NOTICE_INFORMAL`, `NOTICE_PRISE_EN_CHARGE`) dentro
   do `field_schema` dos modelos oficiais -- e `field_schema` é imutável
   assim que existe carta, de propósito;
2. **Que nasça um segundo CMS.** O cadastro mora na tela de Política das
   cartas, com o MESMO padrão de lista, setas e ativação de Menu, FAQ e
   Parceiros;
3. **Que o texto administrado vire HTML.** É TEXTO: escapado como
   qualquer outro conteúdo, sem `safe`, sem `mark_safe`;
4. **Que desativar uma declaração não a tire da etapa 4.** Sem isto o
   cadastro seria enfeite;
5. **Que a ordem da tela não seja a ordem do assistente;**
6. **Que qualquer um com acesso ao Backoffice reescreva um texto
   jurídico.** Exige a permissão da política das cartas;
7. **Que apagar uma declaração apague a resposta de quem já a
   aceitou.** `Letter.data` guarda pela chave, e a chave não muda.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.letters import services
from apps.letters.models import LetterNotice

pytestmark = pytest.mark.django_db

POLITICA = reverse("backoffice:letter_policy")


@pytest.fixture(autouse=True)
def _modelos_oficiais_prontos(modelos_oficiais_prontos):
    """Sem eles o assistente recusa criar carta -- e está certo."""


@pytest.fixture(autouse=True)
def _nacionalidades(nacionalidade_factory):
    nacionalidade_factory("Brasileira")
    nacionalidade_factory("Belga")


@pytest.fixture
def draft(user):
    return services.start_draft(user, "fr")


def _pessoa(email, *permissoes):
    pessoa = get_user_model().objects.create_user(
        email=email, password="x", full_name="Clara Dias"
    )
    for app_label, codename in permissoes:
        pessoa.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return get_user_model().objects.get(pk=pessoa.pk)


@pytest.fixture
def editora(db):
    return _pessoa(
        "editora-declaracoes@mail.com",
        ("core", "access_backoffice"),
        ("letters", "change_letterpolicy"),
    )


@pytest.fixture
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


def nova(cliente, texto="Declaro que li o aviso."):
    return cliente.post(reverse("backoffice:letter_notice_new"), {"text": texto, "is_active": "on"})


def chaves_ativas():
    return [campo["key"] for campo in services.campos_das_declaracoes()]


# ===========================================================================
# 1. A semente: instalar não muda nada
# ===========================================================================


class TestASemente:
    def test_as_duas_declaracoes_de_sempre_ja_estao_cadastradas(self):
        """
        A migration copiou o texto que estava no `field_schema`. Quem
        atualizar o sistema vê a etapa 4 exatamente como antes.
        """
        assert LetterNotice.objects.count() == 2
        assert set(chaves_ativas()) == {"notice_informal", "notice_prise_en_charge"}

    def test_elas_nascem_ativas_e_na_ordem_de_sempre(self):
        chaves = chaves_ativas()

        assert chaves == ["notice_informal", "notice_prise_en_charge"]

    def test_o_texto_semeado_e_o_mesmo_do_schema_antigo(self):
        """Se a cópia da migration divergir, a etapa 4 muda de sentido."""
        from apps.doctemplates.official_templates import (
            NOTICE_INFORMAL,
            NOTICE_PRISE_EN_CHARGE,
        )

        assert LetterNotice.objects.get(key="notice_informal").text == NOTICE_INFORMAL
        assert (
            LetterNotice.objects.get(key="notice_prise_en_charge").text
            == NOTICE_PRISE_EN_CHARGE
        )


# ===========================================================================
# 2. O cadastro reflete no assistente
# ===========================================================================


class TestReflexoNoAssistente:
    def test_declaracao_nova_aparece_na_etapa_4(self, cliente):
        nova(cliente, "Declaro que o convidado tem seguro viagem.")

        assert "declaro-que-o-convidado-tem-seguro-viagem" in chaves_ativas()

    def test_editar_o_texto_muda_o_que_a_etapa_4_mostra(self, cliente):
        declaracao = LetterNotice.objects.get(key="notice_informal")

        cliente.post(
            reverse("backoffice:letter_notice_edit", args=[declaracao.pk]),
            {"text": "Texto reescrito pela administração.", "is_active": "on"},
        )

        rotulos = [campo["label"] for campo in services.campos_das_declaracoes()]
        assert "Texto reescrito pela administração." in rotulos

    def test_editar_nao_muda_a_chave(self, cliente):
        """
        A chave é o que liga a resposta gravada em `Letter.data`.
        Reescrever o texto não pode desligar o histórico.
        """
        declaracao = LetterNotice.objects.get(key="notice_informal")

        cliente.post(
            reverse("backoffice:letter_notice_edit", args=[declaracao.pk]),
            {"text": "Outro texto completamente diferente.", "is_active": "on"},
        )

        declaracao.refresh_from_db()
        assert declaracao.key == "notice_informal"

    def test_desativar_tira_da_etapa_4(self, cliente):
        declaracao = LetterNotice.objects.get(key="notice_informal")

        cliente.post(
            reverse("backoffice:letter_notice_activation", args=[declaracao.pk]),
            {"ativo": "0"},
        )

        assert "notice_informal" not in chaves_ativas()
        assert LetterNotice.objects.filter(key="notice_informal").exists(), "não apaga"

    def test_reativar_traz_de_volta(self, cliente):
        declaracao = LetterNotice.objects.get(key="notice_informal")
        url = reverse("backoffice:letter_notice_activation", args=[declaracao.pk])

        cliente.post(url, {"ativo": "0"})
        cliente.post(url, {"ativo": "1"})

        assert "notice_informal" in chaves_ativas()

    def test_a_ordem_da_tela_e_a_ordem_do_assistente(self, cliente):
        segunda = LetterNotice.objects.get(key="notice_prise_en_charge")

        cliente.post(
            reverse("backoffice:letter_notice_move", args=[segunda.pk]),
            {"direcao": "subir"},
        )

        assert chaves_ativas() == ["notice_prise_en_charge", "notice_informal"]

    def test_descer_no_fim_nao_faz_nada(self, cliente):
        ultima = LetterNotice.objects.get(key="notice_prise_en_charge")

        cliente.post(
            reverse("backoffice:letter_notice_move", args=[ultima.pk]),
            {"direcao": "descer"},
        )

        assert chaves_ativas() == ["notice_informal", "notice_prise_en_charge"]

    def test_remover_tira_da_etapa_4(self, cliente):
        declaracao = LetterNotice.objects.get(key="notice_informal")

        cliente.post(reverse("backoffice:letter_notice_delete", args=[declaracao.pk]))

        assert "notice_informal" not in chaves_ativas()
        assert not LetterNotice.objects.filter(key="notice_informal").exists()

    def test_sem_nenhuma_declaracao_a_etapa_4_nao_quebra(self, cliente):
        for declaracao in LetterNotice.objects.all():
            cliente.post(reverse("backoffice:letter_notice_delete", args=[declaracao.pk]))

        assert services.campos_das_declaracoes() == []


# ===========================================================================
# 3. O texto é TEXTO
# ===========================================================================


class TestOTextoETexto:
    def test_o_html_do_texto_e_escapado_na_etapa_4(self, cliente, auth_client, draft):
        from apps.letters.tests.test_navegacao import _fill_until, _step_url

        nova(cliente, '<img src=x onerror="alert(1)"> declaro.')
        _fill_until(auth_client, draft, 4)

        html = auth_client.get(_step_url(draft, 4)).content.decode()

        assert 'onerror="alert(1)"' not in html
        assert "&lt;img" in html

    def test_nem_o_backoffice_confia_no_texto(self, cliente):
        nova(cliente, "<b>negrito</b>")

        html = cliente.get(POLITICA).content.decode()

        assert "<b>negrito</b>" not in html
        assert "&lt;b&gt;negrito&lt;/b&gt;" in html

    def test_nenhum_safe_nos_templates_das_declaracoes(self):
        """
        `|safe` ou `mark_safe` em qualquer um destes arquivos devolveria
        a execução de HTML administrado ao navegador.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        arquivos = [
            raiz / "templates" / "backoffice" / "letter_policy.html",
            raiz / "templates" / "backoffice" / "letter_notice_form.html",
            raiz / "templates" / "backoffice" / "letter_notice_delete.html",
            raiz / "templates" / "letters" / "_field.html",
            raiz / "apps" / "letters" / "backoffice_views.py",
            raiz / "apps" / "letters" / "models.py",
        ]

        for arquivo in arquivos:
            texto = arquivo.read_text(encoding="utf-8")
            # A CHAMADA, e não a palavra: o comentário do próprio
            # template explica por que nenhuma delas está ali.
            assert "mark_safe(" not in texto, arquivo
            assert "|safe" not in texto, arquivo

    def test_o_texto_nao_vai_para_o_javascript(self):
        """Conteúdo administrado não é código: não entra em `app.js`."""
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[3]
        js = (raiz / "static" / "js" / "app.js").read_text(encoding="utf-8")

        assert "notice_informal" not in js
        assert "LetterNotice" not in js


# ===========================================================================
# 4. Quem pode
# ===========================================================================


class TestPermissao:
    @pytest.fixture
    def curiosa(self, db):
        pessoa = _pessoa("curiosa-declaracoes@mail.com", ("core", "access_backoffice"))
        c = Client()
        c.force_login(pessoa)
        return c

    def test_sem_a_permissao_nao_cria(self, curiosa):
        antes = LetterNotice.objects.count()

        resposta = curiosa.post(
            reverse("backoffice:letter_notice_new"), {"text": "x", "is_active": "on"}
        )

        assert resposta.status_code == 403
        assert LetterNotice.objects.count() == antes

    def test_sem_a_permissao_nao_edita(self, curiosa):
        declaracao = LetterNotice.objects.get(key="notice_informal")
        antes = declaracao.text

        resposta = curiosa.post(
            reverse("backoffice:letter_notice_edit", args=[declaracao.pk]),
            {"text": "invadido", "is_active": "on"},
        )

        declaracao.refresh_from_db()
        assert resposta.status_code == 403
        assert declaracao.text == antes

    def test_sem_a_permissao_nao_desativa(self, curiosa):
        declaracao = LetterNotice.objects.get(key="notice_informal")

        resposta = curiosa.post(
            reverse("backoffice:letter_notice_activation", args=[declaracao.pk]),
            {"ativo": "0"},
        )

        declaracao.refresh_from_db()
        assert resposta.status_code == 403
        assert declaracao.is_active is True

    def test_sem_a_permissao_nao_apaga(self, curiosa):
        declaracao = LetterNotice.objects.get(key="notice_informal")

        resposta = curiosa.post(
            reverse("backoffice:letter_notice_delete", args=[declaracao.pk])
        )

        assert resposta.status_code == 403
        assert LetterNotice.objects.filter(pk=declaracao.pk).exists()

    def test_sem_a_permissao_a_tela_nao_oferece_o_cadastro(self, curiosa):
        html = curiosa.get(POLITICA).content.decode()

        assert reverse("backoffice:letter_notice_new") not in html

    def test_anonimo_nao_entra(self, client):
        resposta = client.post(
            reverse("backoffice:letter_notice_new"), {"text": "x", "is_active": "on"}
        )

        assert resposta.status_code in (302, 403)

    @pytest.mark.parametrize("rota", ["letter_notice_activation", "letter_notice_move"])
    def test_as_acoes_so_aceitam_post(self, cliente, rota):
        declaracao = LetterNotice.objects.get(key="notice_informal")

        resposta = cliente.get(reverse(f"backoffice:{rota}", args=[declaracao.pk]))

        assert resposta.status_code == 405


# ===========================================================================
# 5. A chave
# ===========================================================================


class TestAChave:
    def test_textos_iguais_nao_colidem(self, cliente):
        nova(cliente, "Declaro que sim.")
        nova(cliente, "Declaro que sim.")

        chaves = list(LetterNotice.objects.values_list("key", flat=True))
        assert len(chaves) == len(set(chaves))

    def test_a_declaracao_nova_entra_no_fim(self, cliente):
        nova(cliente, "A última da lista.")

        assert chaves_ativas()[-1] == "a-ultima-da-lista"

    def test_texto_sem_letras_ainda_produz_chave(self, cliente):
        nova(cliente, "!!! ???")

        assert LetterNotice.objects.filter(key__startswith="declaracao").exists()


# ===========================================================================
# 6. O histórico
# ===========================================================================


class TestOHistorico:
    def test_a_resposta_gravada_sobrevive_a_desativacao(self, cliente, auth_client, draft):
        """
        A carta guarda `notice_informal: True`. Desligar a declaração
        tira-a das cartas NOVAS; a que já existe continua íntegra.
        """
        from apps.letters.tests.test_navegacao import _fill_until

        _fill_until(auth_client, draft, 5)
        draft.refresh_from_db()
        assert draft.data.get("notice_informal") is True

        declaracao = LetterNotice.objects.get(key="notice_informal")
        cliente.post(
            reverse("backoffice:letter_notice_activation", args=[declaracao.pk]),
            {"ativo": "0"},
        )

        draft.refresh_from_db()
        assert draft.data.get("notice_informal") is True

    def test_o_field_schema_dos_modelos_nao_foi_tocado(self):
        """
        `field_schema` é imutável assim que existe carta -- é ele que
        garante que uma carta antiga continue se reproduzindo igual.
        Esta etapa acrescentou uma FONTE, não reescreveu a garantia.
        """
        from apps.doctemplates.models import DocumentTemplate

        for modelo in DocumentTemplate.objects.all():
            campos = modelo.field_schema["fields"]
            avisos = [campo for campo in campos if campo.get("section") == "avisos"]
            assert avisos, "o schema perdeu a seção"
            assert {campo["key"] for campo in avisos} == {
                "notice_informal",
                "notice_prise_en_charge",
            }
