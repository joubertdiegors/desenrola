"""
A declaração do anfitrião nos quatro modelos oficiais, e a carta nova
nascendo em francês (Rodada 18).

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o texto saia diferente do pedido.** Os literais de cada idioma
   estão escritos aqui, um a um, e a frase montada com os dados de
   exemplo é conferida inteira;
2. **Que um campo vire texto.** Os seis dados -- nome, nascimento,
   nacionalidade, documento de identidade, endereço, telefone -- são
   blocos `field`, nessa ordem, cada um uma vez; nada de "[nome]" nem
   "{{...}}" em texto;
3. **Que o documento mude além do parágrafo.** Posição, tamanho, tipo do
   elemento e o resto do layout ficam como estavam; o parágrafo continua
   cabendo nas três linhas sem a fonte encolher;
4. **Que a migration pise em trabalho alheio.** Ela troca só o texto
   antigo exato, só nos quatro oficiais, e volta atrás;
5. **Que o PDF saia sem os dados reais.** Uma carta de verdade, em cada
   idioma, sai com o nome, o documento e o telefone da pessoa no lugar;
6. **Que a carta nova nasça em outro idioma que não o francês** -- e que
   trocar para NL, EN ou PT deixe de funcionar.
"""

import importlib
import io
import re

import pytest
from django.apps import apps as registro
from django.conf import settings
from django.urls import reverse
from pypdf import PdfReader

from apps.doctemplates.models import DocumentTemplate
from apps.doctemplates.services import ativacao, dados_de_exemplo
from apps.doctemplates.services import carta_convite as cc
from apps.letters import services
from apps.letters.models import DocumentLanguageSettings, Letter

pytestmark = pytest.mark.django_db

MIGRATION_DA_DECLARACAO = importlib.import_module(
    "apps.doctemplates.migrations.0020_declaracao_do_anfitriao"
)
MIGRATION_DO_IDIOMA = importlib.import_module(
    "apps.letters.migrations.0010_idioma_padrao_frances"
)

CAMPOS = [
    "anfitriao.nome",
    "anfitriao.data_nascimento",
    "anfitriao.nacionalidade",
    "anfitriao.documento_identidade",
    "anfitriao.endereco",
    "anfitriao.telefone",
]
EM_NEGRITO = {"anfitriao.nome", "anfitriao.documento_identidade", "anfitriao.endereco",
              "anfitriao.telefone"}

LITERAIS = {
    "fr": ("Je soussigné(e), ", ", né(e) le ", ", nationalité : ", ", carte d’identité : ",
           ", domicilié(e) à ", ", téléphone : ", ", invite par la présente :"),
    "nl": ("Ik, ondergetekende, ", ", geboren op ", ", nationaliteit: ", ", identiteitskaart: ",
           ", wonende te ", ", telefoon: ", ", nodig hierbij uit:"),
    "en": ("I, the undersigned, ", ", born on ", ", nationality: ", ", identity card: ",
           ", residing at ", ", telephone: ", ", hereby invite:"),
    "pt": ("Eu, ", ", nascido(a) em ", ", de nacionalidade ",
           ", titular do documento de identidade nº ", ", domiciliado(a) em ", ", telefone: ",
           ", convido pela presente:"),
}

# A frase inteira, com os dados de exemplo no lugar dos campos.
FRASE_DE_EXEMPLO = {
    "fr": "Je soussigné(e), Claire Dubois, né(e) le 14/03/1985, nationalité : belge, "
          "carte d’identité : 00000000, domicilié(e) à Rue des Exemple 25 - 1200 "
          "Woluwe-Saint-Lambert, téléphone : +32 470 00 00 00, invite par la présente :",
    "pt": "Eu, Claire Dubois, nascido(a) em 14/03/1985, de nacionalidade belga, titular do "
          "documento de identidade nº 00000000, domiciliado(a) em Rue des Exemple 25 - 1200 "
          "Woluwe-Saint-Lambert, telefone: +32 470 00 00 00, convido pela presente:",
}


def declaracao(layout, idioma):
    return next(e for e in layout["elements"] if e["id"] == f"{idioma}-declaracao")


def partes(idioma):
    return declaracao(cc.layout(idioma), idioma)["properties"]["content"]["parts"]


def frase(idioma, valores):
    return "".join(
        p["value"] if p["kind"] == "text" else valores[p["source"]] for p in partes(idioma)
    )


# ===========================================================================
# 1-2. O texto e os campos
# ===========================================================================


@pytest.mark.parametrize("idioma", cc.IDIOMAS)
class TestTexto:
    def test_os_literais_sao_os_pedidos(self, idioma):
        literais = tuple(p["value"] for p in partes(idioma) if p["kind"] == "text")

        assert literais == LITERAIS[idioma]

    def test_os_seis_campos_estruturais_na_ordem(self, idioma):
        campos = [p["source"] for p in partes(idioma) if p["kind"] == "field"]

        assert campos == CAMPOS

    def test_literal_e_campo_se_alternam(self, idioma):
        tipos = [p["kind"] for p in partes(idioma)]

        assert tipos == ["text", "field"] * 6 + ["text"]

    def test_nenhum_campo_virou_texto(self, idioma):
        for parte in partes(idioma):
            if parte["kind"] == "text":
                assert not re.search(r"[\[\]{}]|%s", parte["value"]), parte["value"]

    def test_o_negrito_de_cada_campo_e_o_de_antes(self, idioma):
        for parte in partes(idioma):
            if parte["kind"] == "field":
                negrito = parte.get("font_weight") == "bold"
                assert negrito == (parte["source"] in EM_NEGRITO), parte["source"]


@pytest.mark.parametrize("idioma", sorted(FRASE_DE_EXEMPLO))
def test_a_frase_montada_com_os_dados_de_exemplo(idioma):
    valores = dados_de_exemplo.para(cc.slug_do_modelo(idioma))

    assert frase(idioma, valores) == FRASE_DE_EXEMPLO[idioma]


# ===========================================================================
# 3. Só o parágrafo mudou
# ===========================================================================


@pytest.mark.parametrize("idioma", cc.IDIOMAS)
class TestGeometria:
    def test_a_caixa_e_a_de_sempre(self, idioma):
        elemento = declaracao(cc.layout(idioma), idioma)

        assert elemento["type"] == "rich_text"
        assert elemento["x"] == pytest.approx(cc.MARGEM_ESQUERDA)
        assert elemento["width"] == pytest.approx(cc.LARGURA_DO_TEXTO)
        assert elemento["y"] == pytest.approx(cc.topo_da_caixa(cc.BASE_DECLARACAO))
        assert elemento["height"] == pytest.approx(3 * cc.ALTURA_DA_LINHA)

    def test_cabe_nas_tres_linhas_sem_encolher_a_fonte(self, idioma):
        """
        A caixa tem `overflow: shrink`: texto que não cabe é desenhado
        menor, em silêncio. Com os dados de exemplo, o parágrafo novo
        cabe inteiro, em 11pt -- medido com o motor do próprio renderer.
        """
        from apps.doctemplates.services.pdf import texto as motor
        from apps.doctemplates.services.pdf.contexto import Contexto
        from apps.doctemplates.services.pdf.elementos import _trechos_do_conteudo
        from pdfengine import fontconfig

        fontconfig.register_fonts()
        elemento = declaracao(cc.layout(idioma), idioma)
        propriedades = elemento["properties"]
        valores = dados_de_exemplo.para(cc.slug_do_modelo(idioma))
        trechos = _trechos_do_conteudo(
            propriedades["content"], propriedades, Contexto(valores)
        )

        linhas, fator = motor.encaixar(
            trechos, elemento["width"], elemento["height"],
            propriedades["line_height"] * propriedades["font_size"],
        )

        assert (len(linhas), fator) == (3, 1.0)


# ===========================================================================
# No banco: os quatro oficiais
# ===========================================================================


class TestOsQuatroOficiais:
    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_o_oficial_gravado_tem_o_texto_novo(self, idioma):
        modelo = DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma))

        assert declaracao(modelo.layout, idioma)["properties"]["content"] == (
            MIGRATION_DA_DECLARACAO.NOVA[idioma]
        )

    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_continuam_ativos_desbloqueados_e_prontos(self, modelos_oficiais_prontos, idioma):
        modelo = DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma))

        assert modelo.is_system is True
        assert modelo.is_active is True
        assert modelo.is_locked is False
        assert ativacao.pronto_para_uso(modelo) is True
        assert services.active_document_template(idioma) == modelo


# ===========================================================================
# 4. A migration de dados
# ===========================================================================


def _gravar_declaracao(idioma, conteudo):
    modelo = DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma))
    layout = modelo.layout
    declaracao(layout, idioma)["properties"]["content"] = conteudo
    DocumentTemplate.objects.filter(pk=modelo.pk).update(layout=layout)
    return modelo.pk


def _declaracao_gravada(idioma, slug=None):
    modelo = DocumentTemplate.objects.get(slug=slug or cc.slug_do_modelo(idioma))
    return declaracao(modelo.layout, idioma)["properties"]["content"]


class TestMigrationDaDeclaracao:
    @pytest.mark.parametrize("idioma", cc.IDIOMAS)
    def test_o_texto_novo_da_migration_e_o_do_modulo(self, idioma):
        assert MIGRATION_DA_DECLARACAO.NOVA[idioma] == (
            declaracao(cc.layout(idioma), idioma)["properties"]["content"]
        )

    def test_troca_o_texto_antigo_e_nada_mais(self):
        for idioma in cc.IDIOMAS:
            _gravar_declaracao(idioma, MIGRATION_DA_DECLARACAO.ANTIGA[idioma])
        antes = {
            i: DocumentTemplate.objects.get(slug=cc.slug_do_modelo(i)).layout for i in cc.IDIOMAS
        }

        MIGRATION_DA_DECLARACAO.aplicar(registro, None)

        for idioma in cc.IDIOMAS:
            depois = DocumentTemplate.objects.get(slug=cc.slug_do_modelo(idioma)).layout
            assert _declaracao_gravada(idioma) == MIGRATION_DA_DECLARACAO.NOVA[idioma]
            outros_antes = [e for e in antes[idioma]["elements"]
                            if e["id"] != f"{idioma}-declaracao"]
            outros_depois = [e for e in depois["elements"] if e["id"] != f"{idioma}-declaracao"]
            assert outros_depois == outros_antes

    def test_nao_toca_uma_declaracao_ja_ajustada(self):
        ajustada = {"kind": "mixed", "parts": [{"kind": "text", "value": "Texto do cliente, "},
                                               {"kind": "field", "source": "anfitriao.nome"}]}
        _gravar_declaracao("fr", ajustada)

        MIGRATION_DA_DECLARACAO.aplicar(registro, None)

        assert _declaracao_gravada("fr") == ajustada

    def test_nao_toca_copias(self):
        from apps.doctemplates.services.duplicacao import duplicar_modelo

        oficial = DocumentTemplate.objects.get(slug=cc.slug_do_modelo("fr"))
        copia = duplicar_modelo(oficial, "Cópia da rodada 18")
        layout = copia.layout
        declaracao(layout, "fr")["properties"]["content"] = MIGRATION_DA_DECLARACAO.ANTIGA["fr"]
        DocumentTemplate.objects.filter(pk=copia.pk).update(layout=layout)

        MIGRATION_DA_DECLARACAO.aplicar(registro, None)

        assert _declaracao_gravada("fr", slug=copia.slug) == MIGRATION_DA_DECLARACAO.ANTIGA["fr"]

    def test_e_reversivel(self):
        MIGRATION_DA_DECLARACAO.desfazer(registro, None)
        assert _declaracao_gravada("pt") == MIGRATION_DA_DECLARACAO.ANTIGA["pt"]

        MIGRATION_DA_DECLARACAO.aplicar(registro, None)
        assert _declaracao_gravada("pt") == MIGRATION_DA_DECLARACAO.NOVA["pt"]


# ===========================================================================
# 5. O PDF de uma carta de verdade, em cada idioma
# ===========================================================================


@pytest.fixture
def anfitria(user):
    """A usuária de teste com dados que NÃO são os de exemplo do modelo."""
    user.full_name = "Hélène Vermeulen"
    user.document_number = "592-1234567-89"
    user.phone = "+32 499 11 22 33"
    user.address_line1 = "Avenue des Arts 125"
    user.save()
    return user


def _carta_fechada(pessoa, idioma, nacionalidade_factory):
    nacionalidade_factory("brasileira", name_fr="Brésilienne", name_nl="Braziliaanse",
                          name_en="Brazilian", name_pt="Brasileira")
    carta = services.start_draft(pessoa, idioma)
    carta.data = {
        "guest_name": "Carlos Eduardo Silva", "guest_nationality": "brasileira",
        "guest_birth_date": "1990-07-22", "guest_passport": "YY123456",
        "stay_arrival": "2026-10-10", "stay_departure": "2026-10-24",
    }
    carta.save(update_fields=["data", "updated_at"])
    carta.snapshot = services.build_snapshot(carta, carta.user)
    carta.status = Letter.Status.COMPLETED
    carta.save(update_fields=["snapshot", "status", "updated_at"])
    services.capture_document_template_snapshot(carta, carta.document_template)
    return carta


def _texto_compacto(pdf):
    """O texto da página, sem espaço nenhum -- a justificação espaça à vontade."""
    return re.sub(r"\s+", "", PdfReader(io.BytesIO(pdf)).pages[0].extract_text())


@pytest.mark.parametrize("idioma", cc.IDIOMAS)
def test_o_pdf_sai_com_os_dados_reais_da_pessoa(
    modelos_oficiais_prontos, anfitria, nacionalidade_factory, idioma
):
    carta = _carta_fechada(anfitria, idioma, nacionalidade_factory)

    texto = _texto_compacto(services.render_letter(carta))

    for valor in ("Hélène Vermeulen", "592-1234567-89", "+32 499 11 22 33",
                  "Avenue des Arts 125"):
        assert re.sub(r"\s+", "", valor) in texto, (idioma, valor)
    assert re.sub(r"\s+", "", LITERAIS[idioma][0]) in texto
    assert re.sub(r"\s+", "", LITERAIS[idioma][-1]) in texto
    assert "[" not in texto and "{{" not in texto


# ===========================================================================
# 6. A carta nova nasce em francês
# ===========================================================================


class TestIdiomaPadraoFrances:
    def test_o_padrao_de_fabrica_e_frances(self):
        assert services.IDIOMA_PADRAO_DA_CARTA == "fr"

    def test_a_configuracao_gravada_nasce_em_frances(self):
        """0006 semeia "en"; a 0010 leva a "fr"."""
        assert DocumentLanguageSettings.objects.get(pk=1).default_letter_language == "fr"
        assert services.idioma_padrao_da_carta() == "fr"

    def test_a_lista_de_idiomas_nao_mudou(self):
        assert services.offered_languages() == ["pt", "fr", "nl", "en"]

    def test_a_interface_continua_em_portugues(self):
        assert settings.LANGUAGE_CODE == "pt"

    def test_o_assistente_cria_a_carta_em_frances(
        self, auth_client, user, modelos_oficiais_prontos, nacionalidade_factory
    ):
        nacionalidade_factory("Brasileira")

        auth_client.post(reverse("letters:new"), {
            "guest_name": "Maria Santos da Silva", "guest_nationality": "Brasileira",
            "guest_birth_date": "15/08/1990", "guest_passport": "FA123456",
        })

        carta = Letter.objects.get(user=user)
        assert carta.language == "fr"
        assert carta.document_template.slug == cc.slug_do_modelo("fr")

    def test_a_tela_do_assistente_continua_em_portugues(
        self, auth_client, modelos_oficiais_prontos
    ):
        corpo = auth_client.get(reverse("letters:new")).content.decode()

        assert '<html lang="pt">' in corpo

    @pytest.mark.parametrize("idioma", ["nl", "en", "pt"])
    def test_trocar_de_idioma_usa_o_modelo_daquele_idioma(
        self, user, modelos_oficiais_prontos, idioma
    ):
        carta = services.start_draft(user, services.idioma_padrao_da_carta())

        assert services.change_language(carta, idioma) is True
        carta.refresh_from_db()
        assert carta.language == idioma
        assert carta.document_template.slug == cc.slug_do_modelo(idioma)


class TestMigrationDoIdioma:
    def _configurar(self, disponiveis, padrao):
        DocumentLanguageSettings.objects.filter(pk=1).update(
            available_document_languages=disponiveis, default_letter_language=padrao
        )

    def _padrao(self):
        return DocumentLanguageSettings.objects.get(pk=1).default_letter_language

    def test_leva_o_padrao_antigo_a_frances(self):
        self._configurar(["pt", "fr", "nl", "en"], "en")

        MIGRATION_DO_IDIOMA.para_frances(registro, None)

        assert self._padrao() == "fr"

    def test_nao_mexe_numa_escolha_feita_pela_tela(self):
        self._configurar(["pt", "fr", "nl", "en"], "pt")

        MIGRATION_DO_IDIOMA.para_frances(registro, None)

        assert self._padrao() == "pt"

    def test_nao_escolhe_frances_se_ele_nao_e_oferecido(self):
        self._configurar(["pt", "en"], "en")

        MIGRATION_DO_IDIOMA.para_frances(registro, None)

        assert self._padrao() == "en"

    def test_e_reversivel(self):
        self._configurar(["pt", "fr", "nl", "en"], "fr")

        MIGRATION_DO_IDIOMA.de_volta_ao_ingles(registro, None)

        assert self._padrao() == "en"
