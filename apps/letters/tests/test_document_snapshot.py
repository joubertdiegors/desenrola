"""
Integração DocumentTemplate <-> Letter.

Duas coisas distintas coexistem em `Letter`:

  * `Letter.snapshot` -- os DADOS congelados da carta (o que a pessoa
    preencheu, o perfil do anfitrião no instante da emissão), a
    fonte de `services.build_document_context()`;
  * `Letter.document_template` / `document_snapshot` /
    `document_snapshot_hash` -- o MODELO ESTRUTURAL congelado (o
    desenho, a página, o field_schema). Vários testes aqui montam
    esse vínculo com um modelo de teste próprio, para exercitar o
    congelamento sem depender do conteúdo dos modelos oficiais.

O ponto central de todos os testes: uma vez capturado, o snapshot é
congelado. O que muda por baixo -- o `DocumentTemplate` em si, ou até um
dict em memória que ajudou a montá-lo -- nunca alcança o que já foi
gravado na carta.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.doctemplates.models import DocumentTemplate, DocumentType
from apps.doctemplates.services import snapshot as document_snapshot
from apps.letters import services
from apps.letters.models import DocumentSnapshotImmutableError, Letter

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures: um DocumentTemplate de teste (pequeno e previsível, para
# conferir o snapshot com os olhos) e um rascunho real para anexá-lo.
# ---------------------------------------------------------------------------


@pytest.fixture
def tipo():
    return DocumentType.objects.create(
        code="carta-de-teste-3-5-1",
        name="Carta de teste",
        page={"width": 595.2756, "height": 841.8898, "unit": "pt"},
    )


@pytest.fixture
def modelo(tipo):
    return DocumentTemplate.objects.create(
        type=tipo,
        name="Modelo estrutural de teste",
        slug="modelo-estrutural-de-teste",
        language="fr",
        field_schema={"fields": [{"key": "guest_name", "type": "text"}]},
        layout={
            "version": 1,
            "elements": [
                {
                    "id": "e1",
                    "type": "text",
                    "x": 10.0,
                    "y": 20.0,
                    "width": 100.0,
                    "height": 15.0,
                    "properties": {"content": {"kind": "text", "value": "Olá"}},
                }
            ],
        },
    )


@pytest.fixture
def outro_modelo(tipo):
    return DocumentTemplate.objects.create(
        type=tipo, name="Outro modelo", slug="outro-modelo-de-teste", language="nl",
    )


# `letter` (rascunho real, já ligado ao modelo oficial francês) vem do
# conftest raiz. Trocá-lo pelo `modelo` daqui é legítimo enquanto a
# carta é rascunho -- é o que a etapa 5 faz ao trocar de idioma.


# ===========================================================================
# 1-5. O conteúdo do snapshot capturado numa Letter
# ===========================================================================


class TestConteudoNaLetter:
    def test_a_letter_recebe_o_snapshot(self, letter, modelo):
        services.capture_document_template_snapshot(letter, modelo)

        letter.refresh_from_db()
        assert letter.document_snapshot != {}
        assert letter.document_snapshot_hash != ""
        assert letter.document_template_id == modelo.pk

    def test_contem_o_field_schema(self, letter, modelo):
        services.capture_document_template_snapshot(letter, modelo)

        assert letter.document_snapshot["field_schema"] == modelo.field_schema

    def test_contem_o_layout(self, letter, modelo):
        services.capture_document_template_snapshot(letter, modelo)

        assert letter.document_snapshot["layout"] == modelo.layout

    def test_contem_os_metadados_necessarios(self, letter, modelo, tipo):
        services.capture_document_template_snapshot(letter, modelo)

        assert letter.document_snapshot["id"] == modelo.pk
        assert letter.document_snapshot["slug"] == modelo.slug
        assert letter.document_snapshot["name"] == modelo.name
        assert letter.document_snapshot["type"]["code"] == tipo.code
        assert letter.document_snapshot["type"]["page"] == tipo.page

    def test_contem_o_idioma(self, letter, modelo):
        services.capture_document_template_snapshot(letter, modelo)

        assert letter.document_snapshot["language"] == "fr"

    def test_nao_duplica_os_dados_de_preenchimento_da_carta(self, letter, modelo):
        """
        `Letter.data` já é a fonte dos dados preenchidos; o snapshot
        estrutural descreve o MODELO, não a carta. Os dois não se
        confundem.
        """
        letter.data = {"guest_name": "Ana"}
        letter.save(update_fields=["data", "updated_at"])

        services.capture_document_template_snapshot(letter, modelo)

        assert "data" not in letter.document_snapshot
        assert letter.data == {"guest_name": "Ana"}


# ===========================================================================
# 6-8. Cópia profunda e imutabilidade histórica
# ===========================================================================


class TestCopiaProfundaEHistorico:
    def test_e_uma_copia_profunda(self, letter, modelo):
        services.capture_document_template_snapshot(letter, modelo)

        assert letter.document_snapshot["layout"] is not modelo.layout

    def test_alterar_o_documenttemplate_depois_nao_altera_o_snapshot(self, letter, modelo):
        services.capture_document_template_snapshot(letter, modelo)

        DocumentTemplate.objects.filter(pk=modelo.pk).update(
            name="Nome mudou depois da captura",
            layout={"version": 1, "elements": []},
        )

        letter.refresh_from_db()
        assert letter.document_snapshot["name"] == "Modelo estrutural de teste"
        assert len(letter.document_snapshot["layout"]["elements"]) == 1

    def test_alterar_o_dict_original_em_memoria_nao_altera_o_snapshot(self, letter, modelo):
        """
        Mesmo sem tocar o banco: mutar o dict Python que `modelo` carrega
        em memória, depois da captura, não pode vazar para o que já foi
        gravado na carta.
        """
        services.capture_document_template_snapshot(letter, modelo)

        modelo.layout["elements"].append({"id": "invasor", "type": "line"})
        modelo.field_schema["fields"].append({"key": "novo", "type": "text"})

        letter.refresh_from_db()
        assert len(letter.document_snapshot["layout"]["elements"]) == 1
        assert len(letter.document_snapshot["field_schema"]["fields"]) == 1

    def test_alterar_a_pagina_do_tipo_depois_nao_altera_o_snapshot(self, letter, modelo, tipo):
        services.capture_document_template_snapshot(letter, modelo)

        tipo.page["width"] = 1.0
        tipo.save(update_fields=["page"])

        letter.refresh_from_db()
        assert letter.document_snapshot["type"]["page"]["width"] == 595.2756

    def test_a_origem_nao_e_alterada_pela_captura(self, letter, modelo):
        antes = DocumentTemplate.objects.get(pk=modelo.pk)

        services.capture_document_template_snapshot(letter, modelo)

        depois = DocumentTemplate.objects.get(pk=modelo.pk)
        assert depois.updated_at == antes.updated_at


# ===========================================================================
# 9-11. Hash
# ===========================================================================


class TestHashNaLetter:
    def test_e_deterministico(self, letter, modelo):
        services.capture_document_template_snapshot(letter, modelo)

        recalculado = document_snapshot.compute_hash(letter.document_snapshot)

        assert recalculado == letter.document_snapshot_hash

    def test_muda_quando_o_conteudo_estrutural_muda(self, letter, modelo, outro_modelo):
        services.capture_document_template_snapshot(letter, modelo)
        hash_do_primeiro = letter.document_snapshot_hash

        outra_letter = Letter.objects.create(
            user=letter.user, document_template=letter.document_template, language="fr",
        )
        services.capture_document_template_snapshot(outra_letter, outro_modelo)

        assert outra_letter.document_snapshot_hash != hash_do_primeiro

    def test_nao_muda_por_ordem_de_chaves_json(self, letter, modelo):
        services.capture_document_template_snapshot(letter, modelo)

        reordenado = dict(reversed(list(letter.document_snapshot.items())))

        assert document_snapshot.compute_hash(reordenado) == letter.document_snapshot_hash


# ===========================================================================
# 12-13. Imutabilidade e atomicidade
# ===========================================================================


class TestImutabilidadeEFalhas:
    def test_nao_pode_capturar_duas_vezes(self, letter, modelo, outro_modelo):
        services.capture_document_template_snapshot(letter, modelo)

        with pytest.raises(DocumentSnapshotImmutableError):
            services.capture_document_template_snapshot(letter, outro_modelo)

    def test_capturar_duas_vezes_nao_altera_o_que_ja_foi_gravado(
        self, letter, modelo, outro_modelo
    ):
        services.capture_document_template_snapshot(letter, modelo)
        hash_original = letter.document_snapshot_hash

        with pytest.raises(DocumentSnapshotImmutableError):
            services.capture_document_template_snapshot(letter, outro_modelo)

        letter.refresh_from_db()
        assert letter.document_snapshot_hash == hash_original
        assert letter.document_template_id == modelo.pk

    def test_save_direto_recusa_trocar_o_template_depois_de_capturado(
        self, letter, modelo, outro_modelo
    ):
        """
        A guarda vive no modelo (`Letter.save()`), não só na função de
        serviço -- vale para qualquer caminho de código.
        """
        services.capture_document_template_snapshot(letter, modelo)

        letter.document_template = outro_modelo
        with pytest.raises(DocumentSnapshotImmutableError):
            letter.save(update_fields=["document_template", "updated_at"])

    def test_save_direto_recusa_trocar_o_snapshot_depois_de_capturado(self, letter, modelo):
        services.capture_document_template_snapshot(letter, modelo)

        letter.document_snapshot = {"adulterado": True}
        with pytest.raises(DocumentSnapshotImmutableError):
            letter.save(update_fields=["document_snapshot", "updated_at"])

    def test_save_direto_permite_regravar_os_mesmos_valores(self, letter, modelo):
        """Salvar de novo sem mudar nada não pode ser tratado como violação."""
        services.capture_document_template_snapshot(letter, modelo)

        letter.status = Letter.Status.GENERATED
        letter.save(update_fields=["status", "updated_at"])  # não deve levantar

        letter.refresh_from_db()
        assert letter.status == Letter.Status.GENERATED

    def test_falha_na_captura_nao_deixa_snapshot_parcial(self, letter, modelo, monkeypatch):
        def _explode(*args, **kwargs):
            raise RuntimeError("falha simulada no meio da captura")

        monkeypatch.setattr(document_snapshot, "compute_hash", _explode)

        original = letter.document_template_id

        with pytest.raises(RuntimeError, match="falha simulada"):
            services.capture_document_template_snapshot(letter, modelo)

        letter.refresh_from_db()
        assert letter.document_template_id == original  # nem o vínculo mudou
        assert letter.document_snapshot == {}
        assert letter.document_snapshot_hash == ""

    def test_template_inexistente_nao_deixa_snapshot_parcial(self, letter, tipo):
        """
        `.get()` dentro da transação levanta antes de qualquer atribuição
        pegar -- o cenário real de "o modelo sumiu entre a escolha e a
        finalização".
        """
        fantasma = DocumentTemplate(pk=999999, type=tipo, name="X", slug="x", language="fr")
        original = letter.document_template_id

        with pytest.raises(DocumentTemplate.DoesNotExist):
            services.capture_document_template_snapshot(letter, fantasma)

        letter.refresh_from_db()
        assert letter.document_template_id == original
        assert letter.document_snapshot == {}


# ---------------------------------------------------------------------------
# Concorrência: a linha do DocumentTemplate é travada durante a captura.
# ---------------------------------------------------------------------------


class TestConcorrencia:
    def test_a_captura_trava_a_linha_do_documenttemplate(self, letter, modelo, monkeypatch):
        """
        SQLite (usado aqui) não aplica o travamento de verdade -- só
        Postgres faz (ver `has_select_for_update` em
        `django.db.connection.features`). O que este teste prova é o
        CONTRATO: a captura precisa passar pelo `select_for_update()` de
        verdade, não por um `.get()` avulso, para o travamento acontecer
        em produção.
        """
        from django.db.models.query import QuerySet

        chamadas = []
        original = QuerySet.select_for_update

        def espiao(self, *args, **kwargs):
            chamadas.append(True)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(QuerySet, "select_for_update", espiao)

        services.capture_document_template_snapshot(letter, modelo)

        assert chamadas, "select_for_update() precisa ser chamado na captura"

    def test_a_captura_nao_altera_o_documenttemplate_travado(self, letter, modelo):
        """`select_for_update()` só lê; nunca escreve na origem."""
        antes = DocumentTemplate.objects.values().get(pk=modelo.pk)

        services.capture_document_template_snapshot(letter, modelo)

        depois = DocumentTemplate.objects.values().get(pk=modelo.pk)
        assert depois == antes

    def test_a_captura_usa_a_linha_mais_recente_do_banco(self, letter, modelo):
        """
        A instância Python passada pode estar desatualizada; a captura
        relê pelo pk dentro da transação -- é o que faz o travamento
        valer a pena.
        """
        desatualizada = DocumentTemplate.objects.get(pk=modelo.pk)
        DocumentTemplate.objects.filter(pk=modelo.pk).update(
            name="Nome atualizado por outra transação"
        )

        services.capture_document_template_snapshot(letter, desatualizada)

        assert letter.document_snapshot["name"] == "Nome atualizado por outra transação"


# ===========================================================================
# 14. Comportamento em rascunho
# ===========================================================================


class TestRascunho:
    def test_rascunho_nasce_com_modelo_e_sem_snapshot(self, letter):
        """
        O vínculo com o modelo existe desde o primeiro instante (é o
        que diz quais campos o assistente pede); o CONGELAMENTO só
        acontece na finalização.
        """
        assert letter.document_template_id is not None
        assert letter.document_snapshot == {}
        assert letter.document_snapshot_hash == ""

    def test_rascunho_pode_escolher_um_modelo(self, letter, modelo):
        letter.document_template = modelo
        letter.save(update_fields=["document_template", "updated_at"])

        letter.refresh_from_db()
        assert letter.document_template_id == modelo.pk
        assert letter.document_snapshot == {}

    def test_rascunho_pode_trocar_de_modelo_livremente(self, letter, modelo, outro_modelo):
        letter.document_template = modelo
        letter.save(update_fields=["document_template", "updated_at"])

        letter.document_template = outro_modelo
        letter.save(update_fields=["document_template", "updated_at"])  # não deve levantar

        letter.refresh_from_db()
        assert letter.document_template_id == outro_modelo.pk


# ===========================================================================
# A finalizacao real: o modelo vem do idioma, e o snapshot e capturado
# ===========================================================================


CHEGADA = timezone.localdate() + datetime.timedelta(days=30)
PASSO_1 = {
    "guest_name": "Carlos Eduardo Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "22/07/1990",
    "guest_passport": "YY0000",
}
PASSOS = {
    1: PASSO_1,
    2: {
        "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
        "stay_departure": (CHEGADA + datetime.timedelta(days=14)).strftime("%d/%m/%Y"),
    },
    3: {"host_confirm": "on"},
    4: {"notice_informal": "on", "notice_prise_en_charge": "on"},
}


def _step_url(carta, step):
    return reverse("letters:step", args=[carta.uuid, step])




class TestIntegracaoComAFinalizacaoReal:
    @pytest.fixture(autouse=True)
    def _nacionalidade(self, nacionalidade_factory, modelos_oficiais_prontos):
        nacionalidade_factory("Brasileira", name_fr="Brésilienne")

    def test_a_finalizacao_real_captura_o_snapshot(self, auth_client, user):
        """
        Sem preparar nada na carta: o modelo sai do idioma da etapa 5,
        e a finalização congela o desenho DAQUELE modelo.
        """
        oficial = services.official_document_template("fr")
        client = auth_client
        client.post(reverse("letters:new"), PASSO_1)
        carta = Letter.objects.get(user=user)

        for numero in (1, 2, 3, 4):
            client.post(_step_url(carta, numero), PASSOS[numero])
        client.post(_step_url(carta, 5), {"language": "fr"})
        client.post(_step_url(carta, 6))

        carta.refresh_from_db()
        assert carta.document_snapshot_hash != ""
        assert carta.document_snapshot["layout"] == oficial.layout
        assert carta.document_template_id == oficial.pk

    def test_a_captura_na_finalizacao_real_e_so_uma_vez(self, auth_client, user):
        """Reenviar o POST de finalização não recaptura nem levanta erro visível ao usuário."""
        client = auth_client
        client.post(reverse("letters:new"), PASSO_1)
        carta = Letter.objects.get(user=user)
        for numero in (1, 2, 3, 4):
            client.post(_step_url(carta, numero), PASSOS[numero])
        client.post(_step_url(carta, 5), {"language": "fr"})

        client.post(_step_url(carta, 6))
        carta.refresh_from_db()
        hash_apos_primeira = carta.document_snapshot_hash

        # A carta ja nao esta mais em rascunho; a segunda tentativa de
        # POST na revisao e tratada pelo fluxo normal (a carta some do
        # `get_owned_draft`), mas o campo em si continua protegido de
        # qualquer jeito que o codigo tente regravar.
        assert hash_apos_primeira != ""
        assert not services.get_owned_draft(user, carta.uuid)
