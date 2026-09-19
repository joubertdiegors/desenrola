"""
O pipeline estrutural como ÚNICO caminho das Cartas Convite.

Não há mais um segundo pipeline para onde cair: `start_draft()`
resolve `active_document_template()` e o rascunho JÁ NASCE
vinculado ao `DocumentTemplate` oficial do idioma -- sem tela nova,
sem segundo mecanismo de escolha, e sem rascunho possível sem modelo
(`Letter.document_template` não aceita nulo).

O FATO CENTRAL QUE MOLDA ESTES TESTES
--------------------------------------
`carta-convite-en` -- o idioma que ESTE arquivo configura como padrão
(`_padrao_em_ingles`; o da instalação é o francês desde a Rodada 18) --
existe, está ativo e, desde a Etapa 3.6, tem desenho. O que ainda falta é o BINÁRIO
do logo: a migration semeia o layout com `asset_id: 0` de propósito
(migration não escreve em MEDIA_ROOT) e só `reconstruir_modelos_oficiais`
materializa o arquivo, no deploy. Por isso
`active_document_template()` distingue três coisas:

  * "idioma sem modelo      -> falha EXPLÍCITA (`DefaultDocumentTemplate
     nenhum"                   MissingError`) -- é erro de infraestrutura,
                               a semeadura sempre cria os quatro oficiais;
  * "nenhum ativo"          -> devolve `None`: desativar é decisão
                               administrativa, não banco quebrado;
  * "sem layout"            -> devolve `None`, SEM levantar;
  * "com layout, sem asset" -> devolve `None` também -- é o estado real
                               logo após um `migrate`, e tratá-lo como
                               "pronto" faria a carta EXPLODIR na
                               finalização (`AssetAusenteError`).

Por isso boa parte dos testes que provam a integração de verdade
funcionando (1-4, 6-11, TESTE PRINCIPAL) primeiro dão ao
`carta-convite-en` um layout mínimo mas válido, com asset de verdade.
Um bloco à parte (`TestBancoRecemMigrado`) prova o outro lado: com o
logo ainda não materializado, o assistente PARA e avisa -- não cria
uma carta que explodiria na finalização.
"""

import datetime
import io

import pytest
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from apps.doctemplates.models import DocumentTemplate
from apps.doctemplates.services import ativacao
from apps.letters import services
from apps.letters.models import (
    DefaultDocumentTemplateMissingError,
    DocumentLanguageSettings,
    Letter,
)

pytestmark = pytest.mark.django_db

SLUG_EN = "carta-convite-en"

LAYOUT_MINIMO = {
    "version": 1,
    "elements": [
        {
            "id": "titulo", "type": "text",
            "x": 50.0, "y": 50.0, "width": 400.0, "height": 20.0,
            "properties": {"content": {"kind": "text", "value": "Invitation Letter"}},
        },
        {
            "id": "convidado", "type": "text",
            "x": 50.0, "y": 100.0, "width": 400.0, "height": 20.0,
            "properties": {"content": {"kind": "field", "source": "convidado.nome"}},
        },
        {
            "id": "anfitriao", "type": "text",
            "x": 50.0, "y": 130.0, "width": 400.0, "height": 20.0,
            "properties": {"content": {"kind": "field", "source": "anfitriao.nome"}},
        },
    ],
}


@pytest.fixture(autouse=True)
def _padrao_em_ingles(db):
    """
    Estes testes provam o pipeline sobre o `carta-convite-en`, e o
    assistente cria a carta no idioma PADRÃO. Desde a Rodada 18 o padrão
    de uma instalação é o francês; aqui ele é o inglês, configurado como
    faria um administrador em Backoffice › Idiomas.
    """
    DocumentLanguageSettings.objects.filter(pk=1).update(default_letter_language="en")


@pytest.fixture(autouse=True)
def _nacionalidades(nacionalidade_factory):
    nacionalidade_factory("brasileira", name_fr="Brésilienne")


@pytest.fixture
def en_reconstruido():
    """
    O `carta-convite-en` com um layout MÍNIMO mas válido -- pequeno de
    propósito, para que os testes possam conferir o snapshot inteiro
    com os olhos. `update()`, não `save()`: é `is_system`, e é assim
    que o próprio `services/carta_convite.py` lida com o mesmo caso.

    Sem imagem nenhuma no layout: é o que dispensa MEDIA_ROOT aqui e
    faz `ativacao.pronto_para_uso()` passar sem materializar binário
    algum.
    """
    DocumentTemplate.objects.filter(slug=SLUG_EN).update(layout=LAYOUT_MINIMO)
    return DocumentTemplate.objects.get(slug=SLUG_EN)


def _finalizar_direto(letter, *, dados_extra=None):
    """Leva `letter` a COMPLETED e captura o snapshot estrutural."""
    letter.data = {
        "guest_name": "Carlos Eduardo Silva", "guest_nationality": "brasileira",
        "guest_birth_date": "1990-07-22", "guest_passport": "YY000000",
        "stay_arrival": "2026-10-10", "stay_departure": "2026-10-24",
        **(dados_extra or {}),
    }
    letter.save(update_fields=["data", "updated_at"])
    letter.snapshot = services.build_snapshot(letter, letter.user)
    letter.status = Letter.Status.COMPLETED
    letter.save(update_fields=["snapshot", "status", "updated_at"])
    if not letter.document_snapshot_hash:
        services.capture_document_template_snapshot(letter, letter.document_template)
    return letter


def texto_do(pdf_bytes):
    return PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text()


def conteudo_do(pdf_bytes):
    """
    O CONTENT STREAM (os operadores de desenho), não o arquivo inteiro --
    ver a mesma função em `test_render_letter.py` para o motivo
    (`/CreationDate` do reportlab varia a cada chamada).
    """
    return PdfReader(io.BytesIO(pdf_bytes)).pages[0].get_contents().get_data()


# ===========================================================================
# 1-4. start_draft() vincula o modelo estrutural certo
# ===========================================================================


class TestStartDraftVinculaOModeloEstrutural:
    def test_cria_letter_com_document_template_preenchido(self, user, en_reconstruido):
        """1. start_draft() cria Letter com document_template preenchido."""
        letter = services.start_draft(user, "en")

        assert letter.document_template_id is not None

    def test_o_template_associado_e_o_oficial_en(self, user, en_reconstruido):
        """2. O template associado é carta-convite-en."""
        letter = services.start_draft(user, "en")

        assert letter.document_template.slug == SLUG_EN

    def test_o_documenttype_e_carta_convite(self, user, en_reconstruido):
        """3. O DocumentType é carta-convite."""
        letter = services.start_draft(user, "en")

        assert letter.document_template.type.code == "carta-convite"

    def test_o_template_esta_ativo(self, user, en_reconstruido):
        """4. O template está ativo."""
        letter = services.start_draft(user, "en")

        assert letter.document_template.is_active is True

    def test_nenhuma_carta_nasce_sem_modelo(self, user, en_reconstruido):
        """
        `document_template` não aceita nulo -- não existe mais o estado
        "carta sem modelo, que depois cai num segundo pipeline".
        """
        services.start_draft(user, "en")

        assert not Letter.objects.filter(document_template__isnull=True).exists()


# ===========================================================================
# 5. Nenhuma seleção manual foi introduzida
# ===========================================================================


class TestSemSelecaoManualDeModelo:
    def test_o_padrao_de_fabrica_e_o_frances(self):
        """
        O padrão de fábrica é o francês desde a Rodada 18 (antes, inglês).
        Este arquivo configura o inglês (`_padrao_em_ingles`).
        """
        assert services.IDIOMA_PADRAO_DA_CARTA == "fr"

    def test_a_tela_de_nova_carta_nao_ganhou_seletor_de_modelo(
        self, auth_client, en_reconstruido
    ):
        """5. A interface continua sem seletor de idioma/modelo na criação."""
        resposta = auth_client.get(reverse("letters:new"))

        assert resposta.status_code == 200
        html = resposta.content.decode()
        assert "document_template" not in html
        assert 'name="language"' not in html

    def test_start_draft_nao_aceita_um_document_template_por_parametro(self):
        """A única porta de entrada é a resolução automática por idioma."""
        import inspect

        assinatura = inspect.signature(services.start_draft)
        assert list(assinatura.parameters) == ["user", "language"]


# ===========================================================================
# 6-11. O fluxo real, com o modelo já vinculado no nascimento
# ===========================================================================


class TestFluxoRealComOModeloJaVinculado:
    def test_finalizacao_cria_document_snapshot(self, user, en_reconstruido):
        """6. Finalização cria document_snapshot."""
        letter = services.start_draft(user, "en")

        _finalizar_direto(letter)

        assert letter.document_snapshot != {}
        assert letter.document_snapshot["layout"] == LAYOUT_MINIMO

    def test_finalizacao_gera_pdf_pelo_renderer_novo(self, user, en_reconstruido):
        """7. Finalização gera PDF pelo novo renderer."""
        letter = services.start_draft(user, "en")
        _finalizar_direto(letter)

        services.generate_pdf(letter)

        letter.refresh_from_db()
        assert letter.status == Letter.Status.GENERATED
        with letter.pdf_file.open("rb") as arquivo:
            assert arquivo.read()[:5] == b"%PDF-"

    def test_o_pdf_sai_do_snapshot_e_nao_do_modelo_atual(self, user, en_reconstruido):
        """
        8. Substitui o antigo "o renderer antigo não é usado": não há
        mais renderer antigo. O que continua valendo é que o desenho
        vem do SNAPSHOT -- aqui provado apagando o layout do modelo
        depois da finalização e vendo o PDF sair igual.
        """
        letter = services.start_draft(user, "en")
        _finalizar_direto(letter)
        antes = services.render_letter(letter)

        DocumentTemplate.objects.filter(slug=SLUG_EN).update(
            layout={"version": 1, "elements": []}
        )

        assert conteudo_do(services.render_letter(letter)) == conteudo_do(antes)

    def test_o_pdf_contem_dados_reais(self, user, en_reconstruido):
        """9. O PDF contém dados reais."""
        letter = services.start_draft(user, "en")
        _finalizar_direto(letter)

        dados = services.render_letter(letter)

        texto = texto_do(dados)
        assert "Carlos Eduardo Silva" in texto
        assert "Claire Dubois" in texto  # anfitriao == user, do fixture `user`

    def test_regeneracao_continua_usando_document_snapshot(self, user, en_reconstruido):
        """10. Regeneração continua usando document_snapshot."""
        letter = services.start_draft(user, "en")
        _finalizar_direto(letter)
        services.generate_pdf(letter)
        letter.refresh_from_db()

        # o "administrador" muda o modelo de verdade depois da 1ª geração.
        DocumentTemplate.objects.filter(slug=SLUG_EN).update(
            layout={"version": 1, "elements": []}
        )

        antes = services.render_letter(letter)
        services.generate_pdf(letter)  # a regeneração
        depois = services.render_letter(letter)

        # content stream, nao o arquivo inteiro: o reportlab grava
        # `/CreationDate` com o instante de cada chamada, entao dois PDFs
        # do MESMO conteudo gerados em momentos diferentes nunca sao
        # bytes identicos -- o desenho em si (o que importa aqui) e.
        assert conteudo_do(depois) == conteudo_do(antes)

    def test_alterar_o_template_en_depois_nao_altera_a_letter_finalizada(
        self, user, en_reconstruido
    ):
        """11. Alteração posterior do DocumentTemplate EN não altera uma Letter já finalizada."""
        letter = services.start_draft(user, "en")
        _finalizar_direto(letter)
        snapshot_antes = letter.document_snapshot

        DocumentTemplate.objects.filter(slug=SLUG_EN).update(
            name="Nome mudou depois", layout={"version": 1, "elements": []},
        )

        letter.refresh_from_db()
        assert letter.document_snapshot == snapshot_antes


# ===========================================================================
# 12. Falha explícita, sem Letter parcial
# ===========================================================================


class TestFalhaExplicitaQuandoAusenteOuInativo:
    def test_template_ausente_levanta_e_nao_cria_letter(self, user):
        DocumentTemplate.objects.filter(slug=SLUG_EN).delete()

        with pytest.raises(DefaultDocumentTemplateMissingError):
            services.start_draft(user, "en")

        assert not Letter.objects.filter(user=user).exists()

    def test_template_inativo_deixa_o_idioma_indisponivel_sem_levantar(self, user):
        """
        Desativar o único modelo do idioma NÃO é erro de
        infraestrutura: é uma decisão administrativa, e a resposta
        certa é "ainda não disponível". Antes isto levantava
        `DefaultDocumentTemplateMissingError` -- o mesmo sinal de
        "a semeadura falhou" --, e por isso a tela dizia que o idioma
        tinha sumido mesmo quando ele estava apenas fora do ar.
        """
        DocumentTemplate.objects.filter(slug=SLUG_EN).update(is_active=False)

        assert services.active_document_template("en") is None  # não levanta
        assert services.start_draft(user, "en") is None
        assert not Letter.objects.filter(user=user).exists()

    def test_com_outro_modelo_ativo_o_idioma_continua_de_pe(self, user, en_reconstruido):
        """
        O outro lado: desativar o oficial com uma cópia ativa é uma
        TROCA, não o fim do idioma -- e a carta nasce pela cópia.
        """
        from apps.doctemplates.services.duplicacao import duplicar_modelo

        copia = duplicar_modelo(en_reconstruido, "Inglês revisado")
        ativacao.ativar(copia)

        assert DocumentTemplate.objects.get(slug=SLUG_EN).is_active is False
        assert services.active_document_template("en") == copia
        assert services.start_draft(user, "en").document_template_id == copia.pk

    def test_a_mensagem_identifica_o_slug_que_faltou(self, user):
        DocumentTemplate.objects.filter(slug=SLUG_EN).delete()

        with pytest.raises(DefaultDocumentTemplateMissingError, match=SLUG_EN):
            services.start_draft(user, "en")

    def test_via_http_a_falha_nao_cria_letter_nem_derruba_a_pagina(self, auth_client, user):
        DocumentTemplate.objects.filter(slug=SLUG_EN).delete()

        resposta = auth_client.post(reverse("letters:new"), {
            "guest_name": "Carlos Eduardo Silva", "guest_nationality": "brasileira",
            "guest_birth_date": "22/07/1990", "guest_passport": "YY000000",
        })

        assert resposta.status_code == 302  # redireciona, não um 500
        assert not Letter.objects.filter(user=user).exists()

    def test_modelo_sem_asset_materializado_nao_e_tratado_como_ausente(self, user):
        """
        O caso REAL logo após um `migrate`: o EN tem desenho (Etapa
        3.6) mas o logo só vira arquivo quando
        `reconstruir_modelos_oficiais` roda, no deploy. Até lá
        `active_document_template()` devolve `None` -- silencioso,
        não a exceção. São coisas diferentes, e `start_draft()`
        devolve `None` em vez de criar uma carta condenada.
        """
        modelo = DocumentTemplate.objects.get(slug=SLUG_EN)
        assert modelo.layout["elements"], "o EN passou a ter desenho na Etapa 3.6"
        assert not ativacao.pronto_para_uso(modelo)

        assert services.active_document_template("en") is None
        assert services.start_draft(user, "en") is None  # não deve levantar
        assert not Letter.objects.filter(user=user).exists()


# ===========================================================================
# 13. Banco recém-migrado: para e avisa, nunca cai noutro pipeline
# ===========================================================================


class TestBancoRecemMigrado:
    """
    Sem popular nada: o estado do banco logo depois de um `migrate`,
    antes de `reconstruir_modelos_oficiais`. Antes existia um segundo
    pipeline para onde a carta caía nesse estado; agora não existe, e
    o comportamento certo é PARAR com um aviso -- nunca gerar meio
    documento e marcá-lo como pronto.
    """

    def test_carta_convite_en_hoje_esta_sem_o_asset_do_logo(self):
        """
        Desde a Etapa 3.6 o EN tem desenho; o que ainda falta é o
        binário do logo, criado só por `reconstruir_modelos_oficiais`.
        """
        modelo = DocumentTemplate.objects.get(slug=SLUG_EN)

        assert len(modelo.layout["elements"]) == 23
        assert not ativacao.pronto_para_uso(modelo)

    def test_start_draft_nao_cria_carta_nenhuma(self, user):
        assert services.start_draft(user, "en") is None
        assert not Letter.objects.filter(user=user).exists()

    def test_o_fluxo_http_devolve_a_pessoa_ao_painel_com_aviso(self, auth_client, user):
        resposta = auth_client.post(reverse("letters:new"), {
            "guest_name": "Carlos Eduardo Silva", "guest_nationality": "brasileira",
            "guest_birth_date": "22/07/1990", "guest_passport": "YY000000",
        }, follow=True)

        assert resposta.redirect_chain[-1][0] == reverse("core:dashboard")
        assert [str(m) for m in resposta.context["messages"]]
        assert not Letter.objects.filter(user=user).exists()


# ===========================================================================
# TESTE PRINCIPAL -- fluxo HTTP real, sem nenhuma preparação manual da Letter
# ===========================================================================


class TestPontaAPontaSemPreparacaoManualDaLetter:
    """
    Começa só com o usuário autenticado. Nenhuma linha deste teste toca
    `letter.document_template`: quem vincula é `start_draft()`, dentro do
    próprio código de produção. `en_reconstruido` prepara o CONTEÚDO da
    biblioteca (o que uma etapa futura, equivalente à 3.3 para o inglês,
    faria) -- não prepara a carta.
    """

    def _step_url(self, carta, step):
        return reverse("letters:step", args=[carta.uuid, step])

    def test_ponta_a_ponta(self, auth_client, user, en_reconstruido):
        client = auth_client
        chegada = timezone.localdate() + datetime.timedelta(days=30)

        # criação da carta -- SEM tocar em document_template.
        client.post(reverse("letters:new"), {
            "guest_name": "Carlos Eduardo Silva", "guest_nationality": "brasileira",
            "guest_birth_date": "22/07/1990", "guest_passport": "YY000000",
        })
        carta = Letter.objects.get(user=user)

        # a única verificação de que o vínculo já aconteceu sozinho.
        assert carta.document_template_id is not None
        assert carta.document_template.slug == SLUG_EN

        # wizard
        client.post(self._step_url(carta, 2), {
            "stay_arrival": chegada.strftime("%d/%m/%Y"),
            "stay_departure": (chegada + datetime.timedelta(days=14)).strftime("%d/%m/%Y"),
        })
        client.post(self._step_url(carta, 3), {"host_confirm": "on"})
        client.post(self._step_url(carta, 4), {
            "notice_informal": "on", "notice_prise_en_charge": "on",
        })
        # idioma NÃO é trocado -- continua "en", o padrão.

        # finalização
        resposta = client.post(self._step_url(carta, 6))
        assert resposta.status_code == 302

        carta.refresh_from_db()

        # snapshot
        assert carta.document_snapshot_hash != ""
        assert carta.document_snapshot["layout"] == LAYOUT_MINIMO

        # geração
        assert carta.status == Letter.Status.GENERATED
        assert carta.pdf_file

        # o PDF final, pelo renderer novo
        with carta.pdf_file.open("rb") as arquivo:
            conteudo = arquivo.read()
        documento = PdfReader(io.BytesIO(conteudo))
        assert len(documento.pages) == 1
        texto = documento.pages[0].extract_text()
        assert "Carlos Eduardo Silva" in texto
        assert "Claire Dubois" in texto

    def test_a_view_de_pdf_entrega_o_arquivo(self, auth_client, user, en_reconstruido):
        client = auth_client
        chegada = timezone.localdate() + datetime.timedelta(days=30)
        client.post(reverse("letters:new"), {
            "guest_name": "Carlos Eduardo Silva", "guest_nationality": "brasileira",
            "guest_birth_date": "22/07/1990", "guest_passport": "YY000000",
        })
        carta = Letter.objects.get(user=user)
        client.post(self._step_url(carta, 2), {
            "stay_arrival": chegada.strftime("%d/%m/%Y"),
            "stay_departure": (chegada + datetime.timedelta(days=14)).strftime("%d/%m/%Y"),
        })
        client.post(self._step_url(carta, 3), {"host_confirm": "on"})
        client.post(self._step_url(carta, 4), {
            "notice_informal": "on", "notice_prise_en_charge": "on",
        })
        client.post(self._step_url(carta, 6))

        resposta = client.get(reverse("letters:pdf", args=[carta.uuid]))

        assert resposta.status_code == 200
        assert resposta["Content-Type"] == "application/pdf"


# ===========================================================================
# 14. Depois do deploy: o EN entra no pipeline novo sozinho
# ===========================================================================


class TestQuandoOLogoEMaterializado:
    """
    O outro lado de `TestComportamentoDeHojeSemRegressao`: assim que
    `reconstruir_modelos_oficiais` roda, o `carta-convite-en` fica
    completo e o rascunho novo JÁ NASCE no pipeline estrutural -- sem
    tela nova, sem segundo mecanismo de escolha.
    """

    @pytest.fixture
    def media(self, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        return tmp_path

    @pytest.fixture
    def reconstruido(self, media):
        from apps.content.models import Asset
        from apps.doctemplates.services import carta_convite

        carta_convite.reconstruir_todos(DocumentTemplate, Asset)
        return DocumentTemplate.objects.get(slug=SLUG_EN)

    def test_o_modelo_fica_pronto(self, reconstruido):
        assert ativacao.pronto_para_uso(reconstruido)

    def test_active_document_template_passa_a_devolver_o_modelo(self, reconstruido):
        assert services.active_document_template("en") == reconstruido

    def test_o_rascunho_novo_ja_nasce_vinculado(self, user, reconstruido):
        letter = services.start_draft(user, "en")

        assert letter.document_template_id == reconstruido.pk
