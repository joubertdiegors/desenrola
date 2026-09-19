"""
Os idiomas do DOCUMENTO, agora configuráveis.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que idioma de documento vire idioma de interface.** São duas
   decisões separadas e a confusão entre elas é o erro mais fácil de
   cometer aqui: a interface continua só em português, venha o que vier
   desta tela;
2. **Que o sistema fique sem idioma nenhum.** Zero disponíveis, ou um
   padrão fora dos disponíveis, tornaria impossível gerar carta nova --
   as duas regras são do CONJUNTO e valem em qualquer caminho de código,
   não só no formulário;
3. **Que tirar um idioma da oferta destrua o passado.** Carta escrita,
   modelo oficial e histórico ficam onde estão: a configuração vale
   daqui para a frente;
4. **Que volte a existir percentual de tradução.** A tela antiga
   inventava "97% · 3 pendentes" e "3 textos usando o fallback". Nada
   disso era medido em lugar nenhum;
5. **Que o cliente escolha o que só o servidor pode decidir.** Código de
   idioma chega por POST e acaba num filtro e num FK de documento.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone

from apps.doctemplates.models import DocumentTemplate
from apps.doctemplates.services.biblioteca import MODELOS_OFICIAIS, slug_oficial
from apps.letters import services
from apps.letters.models import DocumentLanguageSettings, Letter

pytestmark = pytest.mark.django_db

TELA = reverse("backoffice:languages")
OFICIAIS = ("pt", "fr", "nl", "en")


@pytest.fixture(autouse=True)
def _modelos_oficiais_prontos(modelos_oficiais_prontos):
    """Os quatro modelos oficiais com o logo materializado."""


@pytest.fixture(autouse=True)
def _nacionalidades(nacionalidade_factory):
    nacionalidade_factory("Brasileira")
    nacionalidade_factory("Belga")


def config():
    return services.configuracao_de_idiomas()


def configurar(disponiveis, padrao):
    """Grava direto, sem passar pela tela -- para armar um cenário."""
    atual = config()
    atual.available_document_languages = list(disponiveis)
    atual.default_letter_language = padrao
    atual.save()
    return atual


@pytest.fixture
def editora(db):
    """Entra no Backoffice E pode mudar os idiomas."""
    pessoa = get_user_model().objects.create_user(
        email="editora@mail.com", password="x", full_name="Clara Dias"
    )
    for app_label, codename in (
        ("core", "access_backoffice"),
        ("letters", "change_documentlanguagesettings"),
    ):
        pessoa.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return get_user_model().objects.get(pk=pessoa.pk)


@pytest.fixture
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


# ===========================================================================
# 1. A configuração
# ===========================================================================


class TestConfiguracao:
    def test_nasce_com_os_quatro_idiomas_e_padrao_fr(self):
        """
        O estado inicial: os quatro idiomas e o francês como padrão. A
        0006 semeava "en"; a 0010 (Rodada 18) leva a "fr".
        """
        atual = config()

        assert atual.available_document_languages == list(OFICIAIS)
        assert atual.default_letter_language == "fr"

    def test_a_migration_ja_deixou_a_linha_pronta(self):
        """Ler não cria: a semente da migration já está lá."""
        assert DocumentLanguageSettings.objects.count() == 1

    def test_um_segundo_registro_falha_alto_em_vez_de_duplicar(self):
        """
        Salvar um objeto NOVO cairia num UPDATE da linha existente com
        `created_at` nulo. Falhar é o certo: duas configurações
        "vigentes" ao mesmo tempo seria pior do que um erro visível. A
        forma correta de obter o registro é
        `services.configuracao_de_idiomas()`.
        """
        from django.db import IntegrityError, transaction

        outra = DocumentLanguageSettings(
            available_document_languages=["pt"], default_letter_language="pt"
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            outra.save()

        assert DocumentLanguageSettings.objects.count() == 1
        assert config().available_document_languages == list(OFICIAIS)

    def test_os_codigos_oficiais_continuam_sendo_os_quatro(self):
        """
        Não se acrescenta idioma por esta etapa. A lista-mãe é
        `settings.LANGUAGES`, e os modelos oficiais batem com ela.
        """
        from apps.letters.models import idiomas_oficiais

        assert idiomas_oficiais() == list(OFICIAIS)
        assert {code for code, _slug, _nome in MODELOS_OFICIAIS} == set(OFICIAIS)

    def test_um_subconjunto_e_valido(self):
        atual = config()
        atual.available_document_languages = ["fr", "en"]
        atual.default_letter_language = "fr"

        atual.full_clean()  # não levanta

    def test_nenhum_idioma_e_recusado(self):
        atual = config()
        atual.available_document_languages = []

        with pytest.raises(ValidationError) as erro:
            atual.full_clean()

        assert "available_document_languages" in erro.value.error_dict

    def test_o_padrao_precisa_estar_entre_os_disponiveis(self):
        atual = config()
        atual.available_document_languages = ["fr", "nl"]
        atual.default_letter_language = "en"

        with pytest.raises(ValidationError) as erro:
            atual.full_clean()

        assert "default_letter_language" in erro.value.error_dict

    @pytest.mark.parametrize("lixo", ["es", "de", "PT", ""])
    def test_codigo_desconhecido_e_recusado(self, lixo):
        atual = config()
        atual.available_document_languages = ["en", lixo]

        with pytest.raises(ValidationError) as erro:
            atual.full_clean()

        assert "available_document_languages" in erro.value.error_dict

    def test_idioma_repetido_e_recusado(self):
        atual = config()
        atual.available_document_languages = ["en", "en", "fr"]

        with pytest.raises(ValidationError) as erro:
            atual.full_clean()

        assert "available_document_languages" in erro.value.error_dict

    @pytest.mark.parametrize("lixo", ["en", {"en": True}, 7, None, ["en", 7]])
    def test_o_que_nao_e_lista_de_codigos_e_recusado(self, lixo):
        """JSON é livre: o `clean()` é quem o fecha."""
        atual = config()
        atual.available_document_languages = lixo

        with pytest.raises(ValidationError):
            atual.full_clean()

    def test_padrao_fora_dos_oficiais_e_recusado(self):
        atual = config()
        atual.default_letter_language = "es"

        with pytest.raises(ValidationError) as erro:
            atual.full_clean()

        assert "default_letter_language" in erro.value.error_dict


# ===========================================================================
# 2. O que o serviço responde
# ===========================================================================


class TestServico:
    def test_oferecidos_saem_na_ordem_oficial(self):
        configurar(["en", "pt"], "en")

        assert services.offered_languages() == ["pt", "en"]

    def test_oferecidos_nunca_fica_vazio(self):
        """
        `clean()` impede gravar a lista vazia. Um `update()` cru não passa
        por ele -- e o produto ainda assim não pode ficar sem poder gerar
        carta nenhuma.
        """
        DocumentLanguageSettings.objects.all().update(available_document_languages=[])

        assert services.offered_languages() == [services.IDIOMA_PADRAO_DA_CARTA]

    def test_o_padrao_vem_da_configuracao(self):
        configurar(OFICIAIS, "pt")

        assert services.idioma_padrao_da_carta() == "pt"

    def test_padrao_fora_dos_oferecidos_cai_no_primeiro(self):
        """Outra rede para um estado que só um `update()` cru produz."""
        DocumentLanguageSettings.objects.all().update(
            available_document_languages=["fr", "nl"], default_letter_language="en"
        )

        assert services.idioma_padrao_da_carta() == "fr"

    def test_disponiveis_e_a_intersecao_das_duas_perguntas(self):
        """
        Oferecido pelo administrador E com documento capaz de gerar.
        As duas precisam ser "sim".
        """
        configurar(["fr", "nl", "en"], "en")
        DocumentTemplate.objects.filter(slug=slug_oficial("nl")).update(layout={})

        disponiveis = services.available_languages()

        assert "fr" in disponiveis
        assert "en" in disponiveis
        assert "nl" not in disponiveis  # oferecido, mas sem desenho
        assert "pt" not in disponiveis  # pronto, mas não oferecido

    def test_desativar_o_modelo_continua_tirando_o_idioma(self):
        """A proteção que já existia não pode ter sido afrouxada."""
        assert "nl" in services.available_languages()

        DocumentTemplate.objects.filter(slug=slug_oficial("nl")).update(is_active=False)

        assert "nl" not in services.available_languages()


# ===========================================================================
# 3. A porta do Backoffice
# ===========================================================================


class TestAcesso:
    def test_anonimo_vai_para_o_login(self, client):
        resposta = client.get(TELA)

        assert resposta.status_code == 302
        assert resposta.url.startswith(reverse("accounts:login"))

    def test_usuario_comum_e_recusado(self, auth_client):
        assert auth_client.get(TELA).status_code == 403

    def test_quem_entra_no_backoffice_pode_VER(self, client, staff_user):
        """
        Ver uma regra que vale para todo mundo é uma coisa; mudá-la é
        outra -- mesma decisão da política das cartas.
        """
        client.force_login(staff_user)

        resposta = client.get(TELA)

        assert resposta.status_code == 200
        assert resposta.context["pode_editar"] is False

    def test_quem_so_ve_nao_grava(self, client, staff_user):
        """A URL continua digitável -- a recusa é no servidor."""
        client.force_login(staff_user)

        resposta = client.post(
            TELA, {"available_document_languages": ["pt"], "default_letter_language": "pt"}
        )

        assert resposta.status_code == 403
        assert config().available_document_languages == list(OFICIAIS)

    def test_a_tela_avisa_quem_nao_pode_editar(self, client, staff_user):
        client.force_login(staff_user)

        corpo = client.get(TELA).content.decode()

        assert "não tem permissão para alterá-la" in corpo
        assert "Salvar idiomas" not in corpo

    def test_sem_csrf_nao_grava(self, editora):
        sem_token = Client(enforce_csrf_checks=True)
        sem_token.force_login(editora)

        resposta = sem_token.post(
            TELA, {"available_document_languages": ["pt"], "default_letter_language": "pt"}
        )

        assert resposta.status_code == 403
        assert config().available_document_languages == list(OFICIAIS)


# ===========================================================================
# 4. A tela
# ===========================================================================


class TestTela:
    def test_mostra_os_quatro_com_caixas(self, cliente):
        corpo = cliente.get(TELA).content.decode()

        for codigo in OFICIAIS:
            assert f'value="{codigo}"' in corpo
        assert 'type="checkbox"' in corpo

    def test_diz_que_a_interface_continua_em_portugues(self, cliente):
        """
        O erro mais fácil desta tela é confundir idioma de documento com
        idioma de interface. Ela diz isso em voz alta.
        """
        corpo = cliente.get(TELA).content.decode()

        assert "O idioma da interface do site permanece em português" in corpo

    def test_nao_ha_percentual_de_traducao(self, cliente):
        corpo = cliente.get(TELA).content.decode()

        for inventado in ("97%", "pendentes", "fallback", "Revisar agora"):
            assert inventado not in corpo

    def test_salvar_os_idiomas_disponiveis(self, cliente):
        cliente.post(
            TELA,
            {"available_document_languages": ["fr", "en"], "default_letter_language": "en"},
        )

        assert config().available_document_languages == ["fr", "en"]

    def test_salvar_o_idioma_padrao(self, cliente):
        cliente.post(
            TELA,
            {
                "available_document_languages": list(OFICIAIS),
                "default_letter_language": "pt",
            },
        )

        assert config().default_letter_language == "pt"

    def test_a_ordem_gravada_e_a_oficial(self, cliente):
        """A ordem em que as caixas chegam não é a ordem dos idiomas."""
        cliente.post(
            TELA,
            {"available_document_languages": ["en", "pt"], "default_letter_language": "pt"},
        )

        assert config().available_document_languages == ["pt", "en"]

    def test_repetido_no_post_nao_grava_repetido(self, cliente):
        cliente.post(
            TELA,
            {
                "available_document_languages": ["pt", "pt", "en"],
                "default_letter_language": "pt",
            },
        )

        assert config().available_document_languages == ["pt", "en"]

    def test_desmarcar_todos_e_recusado(self, cliente):
        resposta = cliente.post(
            TELA, {"available_document_languages": [], "default_letter_language": "en"}
        )

        assert resposta.status_code == 200
        assert config().available_document_languages == list(OFICIAIS)
        assert "Pelo menos um idioma" in resposta.content.decode()

    def test_deixar_um_so_funciona(self, cliente):
        """Um é o mínimo, e é válido."""
        cliente.post(
            TELA, {"available_document_languages": ["fr"], "default_letter_language": "fr"}
        )

        assert config().available_document_languages == ["fr"]

    def test_padrao_fora_dos_marcados_e_recusado(self, cliente):
        resposta = cliente.post(
            TELA,
            {"available_document_languages": ["fr", "nl"], "default_letter_language": "en"},
        )

        assert resposta.status_code == 200
        assert config().default_letter_language == "fr"
        assert config().available_document_languages == list(OFICIAIS)

    @pytest.mark.parametrize("lixo", ["es", "de", "'; DROP TABLE", "PT"])
    def test_codigo_inventado_e_recusado(self, cliente, lixo):
        resposta = cliente.post(
            TELA,
            {
                "available_document_languages": ["en", lixo],
                "default_letter_language": "en",
            },
        )

        assert resposta.status_code == 200
        assert config().available_document_languages == list(OFICIAIS)

    def test_padrao_inventado_e_recusado(self, cliente):
        resposta = cliente.post(
            TELA,
            {"available_document_languages": list(OFICIAIS), "default_letter_language": "es"},
        )

        assert resposta.status_code == 200
        assert config().default_letter_language == "fr"


# ===========================================================================
# 5. O assistente obedece
# ===========================================================================

VALID_STEP_1 = {
    "guest_name": "Maria Santos da Silva",
    "guest_nationality": "Brasileira",
    "guest_birth_date": "15/08/1990",
    "guest_passport": "FA123456",
}
# Datas relativas a hoje: a chegada não pode ser no passado (regra do
# servidor), então uma data fixa no código venceria com o tempo.
CHEGADA = timezone.localdate() + datetime.timedelta(days=30)
PARTIDA = CHEGADA + datetime.timedelta(days=15)


def _passo(carta, numero):
    return reverse("letters:step", args=[carta.uuid, numero])


def _ate_a_etapa_5(client, carta):
    """Preenche as etapas 1-4; o servidor não deixa pular."""
    client.post(_passo(carta, 1), VALID_STEP_1)
    client.post(
        _passo(carta, 2),
        {
            "stay_arrival": CHEGADA.strftime("%d/%m/%Y"),
            "stay_departure": PARTIDA.strftime("%d/%m/%Y"),
        },
    )
    client.post(_passo(carta, 3), {"host_confirm": "on"})
    client.post(_passo(carta, 4), {"notice_informal": "on", "notice_prise_en_charge": "on"})


class TestAssistente:
    def test_a_carta_nova_nasce_no_padrao_configurado(self, auth_client, user):
        configurar(OFICIAIS, "pt")

        auth_client.post(reverse("letters:new"), VALID_STEP_1)

        carta = Letter.objects.get(user=user)
        assert carta.language == "pt"
        assert carta.document_template.slug == slug_oficial("pt")

    def test_mudar_o_padrao_muda_as_cartas_novas(self, auth_client, user):
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        primeira = Letter.objects.get(user=user)
        assert primeira.language == "fr"

        configurar(OFICIAIS, "nl")
        auth_client.post(reverse("letters:new"), VALID_STEP_1)

        segunda = Letter.objects.exclude(pk=primeira.pk).get(user=user)
        assert segunda.language == "nl"

    def test_mudar_o_padrao_nao_toca_nas_cartas_existentes(self, auth_client, user):
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        carta = Letter.objects.get(user=user)
        modelo_antes = carta.document_template_id

        configurar(OFICIAIS, "pt")

        carta.refresh_from_db()
        assert carta.language == "fr"
        assert carta.document_template_id == modelo_antes

    def test_a_etapa_5_so_lista_os_oferecidos(self, auth_client, user):
        configurar(["fr", "en"], "en")
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        carta = Letter.objects.get(user=user)
        _ate_a_etapa_5(auth_client, carta)

        resposta = auth_client.get(_passo(carta, 5))

        oferecidos = [item["code"] for item in resposta.context["language_options"]]
        assert oferecidos == ["fr", "en"]

    def test_idioma_nao_oferecido_e_recusado_no_post(self, auth_client, user):
        """Some da tela E é recusado no servidor -- a URL continua aberta."""
        configurar(["fr", "en"], "en")
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        carta = Letter.objects.get(user=user)
        _ate_a_etapa_5(auth_client, carta)

        auth_client.post(_passo(carta, 5), {"language": "nl"})

        carta.refresh_from_db()
        assert carta.language == "en"
        assert carta.document_template.slug == slug_oficial("en")

    def test_trocar_para_um_oferecido_funciona(self, auth_client, user):
        configurar(["fr", "en"], "en")
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        carta = Letter.objects.get(user=user)
        _ate_a_etapa_5(auth_client, carta)

        auth_client.post(_passo(carta, 5), {"language": "fr"})

        carta.refresh_from_db()
        assert carta.language == "fr"
        assert carta.document_template.slug == slug_oficial("fr")

    def test_a_etapa_5_le_a_configuracao_uma_vez_so(self, auth_client, user):
        """
        Duas funções precisam da configuração para montar esta tela.
        Cada uma abrindo o seu próprio SELECT do mesmo registro seria
        consulta repetida por renderização -- por isso as duas aceitam
        recebê-la pronta.
        """
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        carta = Letter.objects.get(user=user)
        _ate_a_etapa_5(auth_client, carta)

        with CaptureQueriesContext(connection) as capturadas:
            auth_client.get(_passo(carta, 5))

        leituras = [
            consulta
            for consulta in capturadas
            if "documentlanguagesettings" in consulta["sql"]
        ]
        assert len(leituras) == 1

    def test_mais_idiomas_oferecidos_nao_custam_mais_leituras(self, auth_client, user):
        """O custo não pode crescer com a quantidade de idiomas."""
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        carta = Letter.objects.get(user=user)
        _ate_a_etapa_5(auth_client, carta)

        def leituras():
            with CaptureQueriesContext(connection) as capturadas:
                auth_client.get(_passo(carta, 5))
            return len(
                [c for c in capturadas if "documentlanguagesettings" in c["sql"]]
            )

        configurar(["en"], "en")
        com_um = leituras()
        configurar(OFICIAIS, "en")
        com_quatro = leituras()

        assert com_um == com_quatro == 1


# ===========================================================================
# 6. Tirar um idioma da oferta não destrói o passado
# ===========================================================================


class TestOPassadoFicaIntacto:
    def test_os_quatro_modelos_oficiais_continuam_existindo(self, cliente):
        cliente.post(
            TELA, {"available_document_languages": ["en"], "default_letter_language": "en"}
        )

        for _code, slug, _nome in MODELOS_OFICIAIS:
            modelo = DocumentTemplate.objects.filter(slug=slug).first()
            assert modelo is not None, slug
            assert modelo.is_active is True

    def test_a_carta_existente_mantem_idioma_e_modelo(self, cliente, letter):
        """`letter` nasce em francês; o francês sai da oferta."""
        antes = (letter.language, letter.document_template_id)

        cliente.post(
            TELA, {"available_document_languages": ["en"], "default_letter_language": "en"}
        )

        letter.refresh_from_db()
        assert (letter.language, letter.document_template_id) == antes

    def test_a_carta_existente_nao_fica_presa_na_etapa_5(self, auth_client, user):
        """
        Com o idioma dela fora da oferta, a pessoa ainda precisa poder
        seguir para a revisão mantendo o que tem. Se todas as opções
        ficassem desabilitadas, o formulário (que exige uma escolha) não
        teria como ser enviado.
        """
        auth_client.post(reverse("letters:new"), VALID_STEP_1)
        carta = Letter.objects.get(user=user)
        _ate_a_etapa_5(auth_client, carta)
        configurar(["nl"], "nl")  # o "fr" da carta sai da oferta

        resposta = auth_client.get(_passo(carta, 5))
        opcoes = {item["code"]: item["available"] for item in resposta.context["language_options"]}

        assert opcoes["fr"] is True, "o idioma da própria carta continua escolhível"

        seguiu = auth_client.post(_passo(carta, 5), {"language": "fr"})

        assert seguiu.status_code == 302
        carta.refresh_from_db()
        assert carta.language == "fr"

    def test_a_carta_finalizada_continua_abrindo(self, auth_client, user, letter):
        """Nem o detalhe nem o histórico dependem da oferta atual."""
        configurar(["en"], "en")  # o francês da carta sai

        detalhe = auth_client.get(reverse("letters:detail", args=[letter.uuid]))
        historico = auth_client.get(reverse("letters:history"))

        assert detalhe.status_code == 200
        assert historico.status_code == 200


# ===========================================================================
# 7. O menu e o catálogo
# ===========================================================================


class TestBackofficeAoRedor:
    def test_o_menu_aponta_para_a_tela_real(self, client, staff_user):
        client.force_login(staff_user)

        corpo = client.get(reverse("backoffice:overview")).content.decode()

        assert f'href="{TELA}"' in corpo
        assert f'href="{TELA}#idiomas"' not in corpo

    def test_a_rota_nao_e_mais_o_placeholder(self):
        from apps.core import views

        assert resolve(TELA).func is views.backoffice_languages

    def test_a_permissao_esta_no_catalogo(self):
        from apps.accounts import admin_permissions

        chaves = {permissao.chave for permissao in admin_permissions.todas()}

        assert "letters.change_documentlanguagesettings" in chaves

    def test_so_a_permissao_de_alterar_foi_criada(self):
        """
        Ver esta tela exige apenas `core.access_backoffice`. Criar
        `view`, `add` e `delete` seria criar três permissões que nada
        confere.
        """
        assert DocumentLanguageSettings._meta.default_permissions == ("change",)

        codenames = set(
            Permission.objects.filter(
                content_type__app_label="letters",
                content_type__model="documentlanguagesettings",
            ).values_list("codename", flat=True)
        )
        assert codenames == {"change_documentlanguagesettings"}

    def test_os_percentuais_inventados_sumiram_do_projeto(self):
        """
        `demo.LANGUAGES` trazia "97% · 3 pendentes" e "Oficial" escritos
        no código, e o cartão que os exibia dizia que três textos em
        neerlandês usavam o fallback em francês. Nada disso era medido.
        """
        from apps.core import demo

        assert not hasattr(demo, "LANGUAGES")

    def test_a_tela_ilustrativa_deixou_de_existir(self):
        """
        Até a Etapa H o cartão de Idiomas tinha saído de uma tela que
        ainda existia. Na Etapa I a tela inteira saiu: era rota órfã,
        fora de todo menu.
        """
        from django.urls import NoReverseMatch

        with pytest.raises(NoReverseMatch):
            reverse("backoffice:templates")
