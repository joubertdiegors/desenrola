"""
UM modelo ativo por idioma -- a regra inteira, do banco ate a tela.

O QUE ESTA SENDO PROTEGIDO
--------------------------
Dentro de um tipo de documento, cada idioma tem no maximo UM modelo
ativo, e e ele que o assistente usa para emitir a carta. Ativar outro
do mesmo idioma nao acrescenta um segundo: TROCA. Sem nenhum ativo, o
idioma fica indisponivel -- o assistente avisa, e nao nasce carta
condenada.

A ORDEM DOS TESTES E A ORDEM DA CONFIANCA
-----------------------------------------
  1. o BANCO recusa dois ativos -- e a garantia que vale para
     qualquer caminho de escrita, inclusive shell e migration;
  2. `ativar()` TROCA, e a troca e atomica;
  3. "situacao" e o que a tela mostra, e nao mente sobre o sistema;
  4. pela TELA, com permissao, CSRF e mensagem -- que e como isto
     acontece de verdade.

O que NAO esta aqui: qual modelo o assistente escolhe. Isso e o outro
lado da mesma regra e vive em `apps/letters/tests/
test_modelo_ativo_por_idioma.py`, junto do fluxo que o consome.
"""

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.doctemplates.models import DocumentTemplate, DocumentType
from apps.doctemplates.services import ativacao
from apps.doctemplates.services.duplicacao import duplicar_modelo

pytestmark = pytest.mark.django_db

SENHA = "senha-de-teste-123"
A4 = {"width": 595.2756, "height": 841.8898, "unit": "pt"}

# Desenho valido e SEM imagem nenhuma: e o que faz `pronto_para_uso`
# responder "sim" sem precisar materializar binario em MEDIA_ROOT.
LAYOUT_PRONTO = {
    "version": 1,
    "elements": [
        {
            "id": "t1", "type": "text", "x": 50.0, "y": 50.0,
            "width": 400.0, "height": 20.0,
            "properties": {"content": {"kind": "text", "value": "Olá"}},
        }
    ],
}

# O mesmo desenho com uma imagem que aponta para um asset que EXISTE
# como numero e nao como arquivo -- o que sobra quando alguem apaga a
# imagem que o modelo usava.
LAYOUT_COM_ASSET_SUMIDO = {
    "version": 1,
    "elements": [
        LAYOUT_PRONTO["elements"][0],
        {
            "id": "logo", "type": "image", "x": 50.0, "y": 700.0,
            "width": 120.0, "height": 40.0,
            "properties": {"source": {"kind": "asset", "asset_id": 987654}},
        },
    ],
}

# O mesmo desenho com uma imagem que aponta para lugar nenhum
# (`asset_id: 0`) -- o estado real de um oficial recem-semeado.
LAYOUT_SEM_LOGO = {
    "version": 1,
    "elements": [
        LAYOUT_PRONTO["elements"][0],
        {
            "id": "logo", "type": "image", "x": 50.0, "y": 700.0,
            "width": 120.0, "height": 40.0,
            "properties": {"source": {"kind": "asset", "asset_id": 0}},
        },
    ],
}


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


@pytest.fixture
def tipo(db):
    return DocumentType.objects.create(code="contrato", name="Contrato", page=dict(A4))


@pytest.fixture
def outro_tipo(db):
    return DocumentType.objects.create(code="recibo", name="Recibo", page=dict(A4))


def criar(tipo, slug, idioma, *, ativo=True, layout=None, **extra):
    return DocumentTemplate.objects.create(
        type=tipo, name=slug.replace("-", " ").title(), slug=slug, language=idioma,
        is_active=ativo, layout=layout or {}, **extra,
    )


@pytest.fixture
def fr_a(tipo):
    """O francês em uso."""
    return criar(tipo, "frances-a", "fr", layout=LAYOUT_PRONTO)


@pytest.fixture
def fr_b(tipo):
    """Outro francês, pronto mas fora do ar."""
    return criar(tipo, "frances-b", "fr", ativo=False, layout=LAYOUT_PRONTO)


def permissao(app_label, codename):
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def criar_pessoa(email, *codenames):
    User = get_user_model()
    pessoa = User.objects.create_user(email=email, password=SENHA, full_name="Quem Clica")
    pessoa.user_permissions.set([permissao(app, code) for app, code in codenames])
    return User.objects.get(pk=pessoa.pk)


@pytest.fixture
def administrador(db):
    return criar_pessoa(
        "admin@desenrola.be",
        ("core", "access_backoffice"),
        ("doctemplates", "view_documenttemplate"),
        ("doctemplates", "change_documenttemplate"),
    )


@pytest.fixture
def so_leitor(db):
    """Vê a biblioteca, mas não mexe no interruptor."""
    return criar_pessoa(
        "leitor@desenrola.be",
        ("core", "access_backoffice"),
        ("doctemplates", "view_documenttemplate"),
    )


@pytest.fixture
def cliente(client, administrador):
    client.force_login(administrador)
    return client


def url_situacao(modelo):
    return reverse("backoffice:document_library_activation", args=[modelo.pk])


def ativos_de(tipo, idioma):
    return list(
        DocumentTemplate.objects.filter(
            type=tipo, language=idioma, is_active=True
        ).values_list("slug", flat=True)
    )


# ===========================================================================
# 1. O banco e a autoridade
# ===========================================================================


class TestOBancoRecusaDoisAtivos:
    """
    O indice parcial `uniq_documenttemplate_ativo_por_idioma` vale para
    QUALQUER caminho de escrita -- view, shell, admin, migration. Por
    isso os testes daqui escrevem cru, sem passar por `ativacao`: e
    exatamente o que alguem faria por fora.
    """

    def test_criar_um_segundo_ativo_do_mesmo_idioma_e_recusado(self, tipo, fr_a):
        with pytest.raises(IntegrityError), transaction.atomic():
            criar(tipo, "frances-b", "fr")

    def test_ligar_um_segundo_ativo_por_update_cru_e_recusado(self, tipo, fr_a, fr_b):
        """
        O caso de duas requisições simultâneas: mesmo que as duas
        passem pela janela de leitura, só uma grava.
        """
        with pytest.raises(IntegrityError), transaction.atomic():
            DocumentTemplate.objects.filter(pk=fr_b.pk).update(is_active=True)

        assert ativos_de(tipo, "fr") == ["frances-a"]

    def test_idiomas_diferentes_convivem_ativos(self, tipo, fr_a):
        criar(tipo, "portugues", "pt")
        criar(tipo, "neerlandes", "nl")

        assert DocumentTemplate.objects.filter(type=tipo, is_active=True).count() == 3

    def test_o_mesmo_idioma_em_tipos_diferentes_convive(self, tipo, outro_tipo, fr_a):
        """
        A regra é por (tipo, idioma): um recibo em francês e um
        contrato em francês são fluxos diferentes, e ativar um não
        pode desativar o outro.
        """
        recibo = criar(outro_tipo, "recibo-fr", "fr")

        recibo.refresh_from_db()
        fr_a.refresh_from_db()
        assert recibo.is_active and fr_a.is_active

    def test_quantos_inativos_o_idioma_quiser(self, tipo, fr_a):
        """
        O índice é PARCIAL: só linhas ativas entram nele. "Inativo" é
        fora de uso, não apagado -- e não pode haver regra que impeça
        um modelo inativo de existir.
        """
        for numero in range(5):
            criar(tipo, f"frances-arquivado-{numero}", "fr", ativo=False)

        assert DocumentTemplate.objects.filter(type=tipo, language="fr").count() == 6
        assert ativos_de(tipo, "fr") == ["frances-a"]


# ===========================================================================
# 2. Ativar e TROCAR -- e a troca e atomica
# ===========================================================================


class TestAtivarEUmaTroca:
    def test_ativar_outro_desativa_o_anterior(self, tipo, fr_a, fr_b):
        ativacao.ativar(fr_b)

        fr_a.refresh_from_db()
        fr_b.refresh_from_db()
        assert fr_b.is_active and not fr_a.is_active
        assert ativos_de(tipo, "fr") == ["frances-b"]

    def test_nunca_existe_um_instante_com_dois(self, tipo, fr_a, fr_b):
        """O estado depois da troca é o único observável: um só."""
        ativacao.ativar(fr_b)

        assert len(ativos_de(tipo, "fr")) == 1

    def test_devolve_quem_saiu(self, fr_a, fr_b):
        """
        Quem chama precisa poder dizer a quem clicou o que MAIS mudou:
        um "ativado" que escondesse o "desativado" seria meia verdade.
        """
        saiu = ativacao.ativar(fr_b)

        assert [m.pk for m in saiu] == [fr_a.pk]

    def test_ativar_o_que_ja_esta_ativo_nao_mexe_em_nada(self, tipo, fr_a, fr_b):
        assert ativacao.ativar(fr_a) == []

        fr_b.refresh_from_db()
        assert not fr_b.is_active
        assert ativos_de(tipo, "fr") == ["frances-a"]

    def test_a_troca_nao_atravessa_idiomas(self, tipo, fr_a, fr_b):
        portugues = criar(tipo, "portugues", "pt")

        ativacao.ativar(fr_b)

        portugues.refresh_from_db()
        assert portugues.is_active

    def test_a_troca_e_atomica(self, tipo, fr_a, fr_b):
        """
        Se a ativação falhar no meio, o anterior NÃO pode ficar
        desativado: o idioma acabaria sem nenhum modelo em uso por
        causa de um erro. Aqui a gravação do novo estoura de
        propósito, e o que se mede é o estado depois.
        """
        with mock.patch.object(
            DocumentTemplate, "save", side_effect=RuntimeError("disco cheio")
        ):
            with pytest.raises(RuntimeError):
                ativacao.ativar(fr_b)

        assert ativos_de(tipo, "fr") == ["frances-a"]

    def test_desativar_deixa_o_idioma_sem_ativo(self, tipo, fr_a):
        ativacao.desativar(fr_a)

        assert ativos_de(tipo, "fr") == []
        assert ativacao.modelo_ativo("fr", tipo=tipo.code) is None

    def test_desativar_o_que_ja_esta_inativo_nao_e_erro(self, fr_b):
        ativacao.desativar(fr_b)

        fr_b.refresh_from_db()
        assert not fr_b.is_active

    def test_desativar_um_oficial_e_permitido(self, modelos_oficiais_prontos):
        """
        `is_active` é um dos três campos que até um modelo OFICIAL
        aceita mudar: tirar um oficial do ar é decisão administrativa
        legítima, não uma violação da guarda.
        """
        oficial = DocumentTemplate.objects.get(slug="carta-convite-fr")

        ativacao.desativar(oficial)

        oficial.refresh_from_db()
        assert not oficial.is_active

    def test_ativar_uma_copia_tira_o_oficial_do_ar(self, modelos_oficiais_prontos, tipo):
        """O caso que motivou a regra: a cópia entra, o oficial sai."""
        oficial = DocumentTemplate.objects.get(slug="carta-convite-fr")
        copia = duplicar_modelo(oficial, "Francês revisado")

        ativacao.ativar(copia)

        oficial.refresh_from_db()
        copia.refresh_from_db()
        assert copia.is_active and not oficial.is_active
        assert ativacao.modelo_ativo("fr") == copia


# ===========================================================================
# 3. Duplicar nao mexe em quem esta no ar
# ===========================================================================


class TestDuplicarNaoTrocaNada:
    def test_a_copia_nasce_inativa_e_a_origem_continua(self, modelos_oficiais_prontos):
        oficial = DocumentTemplate.objects.get(slug="carta-convite-fr")

        copia = duplicar_modelo(oficial, "Cópia do francês")

        oficial.refresh_from_db()
        assert not copia.is_active
        assert oficial.is_active
        assert ativacao.modelo_ativo("fr") == oficial

    def test_duplicar_varias_vezes_continua_valendo(self, modelos_oficiais_prontos):
        """
        Duas cópias do mesmo idioma existem juntas -- nenhuma ativa. O
        índice parcial não atrapalha o fluxo de duplicação.
        """
        oficial = DocumentTemplate.objects.get(slug="carta-convite-fr")

        duplicar_modelo(oficial, "Cópia 1")
        duplicar_modelo(oficial, "Cópia 2")

        assert DocumentTemplate.objects.filter(language="fr").count() == 3
        assert ativacao.modelo_ativo("fr") == oficial


# ===========================================================================
# 4. A situacao que a tela mostra
# ===========================================================================


class TestSituacao:
    def test_ligado_e_pronto_e_ativo(self, fr_a):
        assert ativacao.situacao(fr_a) == ativacao.ATIVO

    def test_ligado_sem_desenho_e_rascunho(self, tipo):
        vazio = criar(tipo, "sem-desenho", "pt")

        assert ativacao.situacao(vazio) == ativacao.RASCUNHO

    def test_ligado_com_imagem_que_nao_existe_e_rascunho(self, tipo):
        """
        O estado real logo depois de um `migrate`: tem desenho, não tem
        logo. Chamar isso de "ativo" seria a tela mentindo -- o
        assistente recusa emitir carta com ele.
        """
        sem_logo = criar(tipo, "sem-logo", "pt", layout=LAYOUT_SEM_LOGO)

        assert ativacao.situacao(sem_logo) == ativacao.RASCUNHO

    def test_desligado_e_inativo_mesmo_estando_pronto(self, fr_b):
        assert ativacao.situacao(fr_b) == ativacao.INATIVO

    def test_a_versao_em_lote_diz_o_mesmo_que_a_individual(self, tipo, fr_a, fr_b):
        modelos = [
            fr_a, fr_b,
            criar(tipo, "sem-desenho", "pt"),
            criar(tipo, "sem-logo", "nl", layout=LAYOUT_SEM_LOGO),
        ]

        em_lote = ativacao.situacoes(modelos)

        assert em_lote == {m.pk: ativacao.situacao(m) for m in modelos}

    def test_a_versao_em_lote_faz_UMA_consulta_de_assets(
        self, tipo, django_assert_num_queries
    ):
        """
        A biblioteca desenha dezenas de linhas: perguntar modelo a
        modelo daria uma consulta por linha só para escrever uma
        palavra na tela.
        """
        modelos = [
            criar(tipo, f"com-logo-{codigo}", codigo, layout=LAYOUT_COM_ASSET_SUMIDO)
            for codigo in ("pt", "fr", "nl", "en")
        ]

        with django_assert_num_queries(1):
            ativacao.situacoes(modelos)


# ===========================================================================
# 5. Pela tela -- como isto acontece de verdade
# ===========================================================================


class TestPelaTela:
    def test_ativar_troca_e_a_mensagem_diz_quem_saiu(self, cliente, tipo, fr_a, fr_b):
        resposta = cliente.post(
            url_situacao(fr_b), {"ativo": "1", "voltar": "biblioteca"}, follow=True
        )

        fr_a.refresh_from_db()
        assert not fr_a.is_active
        assert ativos_de(tipo, "fr") == ["frances-b"]
        recado = " ".join(str(m) for m in resposta.context["messages"])
        assert fr_b.name in recado and fr_a.name in recado

    def test_ativar_volta_para_a_biblioteca_quando_veio_dela(self, cliente, fr_b):
        resposta = cliente.post(url_situacao(fr_b), {"ativo": "1", "voltar": "biblioteca"})

        assert resposta["Location"] == reverse("backoffice:document_library")

    def test_ativar_volta_para_o_detalhe_por_padrao(self, cliente, fr_b):
        resposta = cliente.post(url_situacao(fr_b), {"ativo": "1"})

        assert resposta["Location"] == reverse(
            "backoffice:document_detail", args=[fr_b.pk]
        )

    def test_desativar_deixa_o_idioma_indisponivel(self, cliente, tipo, fr_a):
        cliente.post(url_situacao(fr_a), {"ativo": "0"})

        assert ativos_de(tipo, "fr") == []

    def test_a_tela_nunca_deixa_dois_ativos(self, cliente, tipo, fr_a, fr_b):
        """
        Mesmo atacando o endpoint direto, um atrás do outro: cada POST
        troca, nenhum acumula.
        """
        for _ in range(3):
            cliente.post(url_situacao(fr_b), {"ativo": "1"})
            cliente.post(url_situacao(fr_a), {"ativo": "1"})

        assert ativos_de(tipo, "fr") == ["frances-a"]

    def test_ativar_o_que_ja_esta_ativo_avisa_que_nao_ha_o_que_fazer(
        self, cliente, fr_a
    ):
        resposta = cliente.post(url_situacao(fr_a), {"ativo": "1"}, follow=True)

        fr_a.refresh_from_db()
        mensagens = list(resposta.context["messages"])
        assert fr_a.is_active
        assert len(mensagens) == 1 and mensagens[0].level_tag == "info"

    def test_get_nao_liga_nada(self, cliente, fr_b):
        resposta = cliente.get(url_situacao(fr_b))

        fr_b.refresh_from_db()
        assert resposta.status_code == 405
        assert not fr_b.is_active

    def test_sem_permissao_de_administrar_nao_mexe(self, client, so_leitor, fr_a, fr_b):
        client.force_login(so_leitor)

        resposta = client.post(url_situacao(fr_b), {"ativo": "1"})

        fr_a.refresh_from_db()
        fr_b.refresh_from_db()
        assert resposta.status_code == 403
        assert fr_a.is_active and not fr_b.is_active

    def test_anonimo_nao_mexe(self, client, fr_a, fr_b):
        resposta = client.post(url_situacao(fr_b), {"ativo": "1"})

        fr_b.refresh_from_db()
        assert resposta.status_code in (302, 403)
        assert not fr_b.is_active

    def test_modelo_inexistente_e_404(self, cliente):
        resposta = cliente.post(
            reverse("backoffice:document_library_activation", args=[999999]),
            {"ativo": "1"},
        )

        assert resposta.status_code == 404


# ===========================================================================
# 6. A pagina do modelo conta a mesma historia
# ===========================================================================


class TestAPaginaDoModelo:
    """
    O interruptor existe em duas telas. A do detalhe nao pode descrever
    um mundo diferente do da biblioteca -- nem chamar de "Ativo" o que
    o assistente recusa, nem esconder que ativar DESATIVA outro.
    """

    def url(self, modelo):
        return reverse("backoffice:document_detail", args=[modelo.pk])

    def test_ligado_e_pronto_aparece_como_ativo(self, cliente, fr_a):
        corpo = cliente.get(self.url(fr_a)).content.decode()

        assert ">Ativo<" in corpo
        assert ">Rascunho<" not in corpo

    def test_ligado_sem_desenho_aparece_como_rascunho(self, cliente, tipo):
        sem_desenho = criar(tipo, "sem-desenho", "pt")

        resposta = cliente.get(self.url(sem_desenho))

        assert resposta.context["situacao"] == ativacao.RASCUNHO
        corpo = resposta.content.decode()
        assert ">Rascunho<" in corpo
        assert "o desenho ainda não pode ser usado" in corpo

    def test_a_tela_de_um_inativo_diz_quem_esta_no_lugar(self, cliente, fr_a, fr_b):
        resposta = cliente.get(self.url(fr_b))

        assert resposta.context["em_uso_no_idioma"] == fr_a
        assert fr_a.name in resposta.content.decode()

    def test_a_pergunta_do_botao_avisa_que_e_uma_troca(self, cliente, fr_a, fr_b):
        """Antes do clique, e por extenso: quem sai do ar."""
        corpo = cliente.get(self.url(fr_b)).content.decode()

        assert "será desativado" in corpo
        assert fr_a.name in corpo

    def test_sem_ninguem_no_lugar_a_pergunta_e_a_simples(self, cliente, fr_b):
        corpo = cliente.get(self.url(fr_b)).content.decode()

        assert "será desativado" not in corpo
        assert "passa a ser o documento usado" in corpo

    def test_desativar_avisa_que_o_idioma_fica_sem_modelo(self, cliente, fr_a):
        corpo = cliente.get(self.url(fr_a)).content.decode()

        assert "fica sem modelo em uso" in corpo

    def test_ativar_pela_pagina_do_modelo_volta_para_ela(self, cliente, fr_a, fr_b):
        resposta = cliente.post(url_situacao(fr_b), {"ativo": "1"})

        assert resposta["Location"] == self.url(fr_b)
        fr_a.refresh_from_db()
        assert not fr_a.is_active
