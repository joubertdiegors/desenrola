"""
O contador de cartas no Banner superior -- estrutural, não hardcode.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o número seja digitado à mão.** Vem sempre de
   `letters.statistics.cartas_emitidas()` -- nunca um texto solto no
   banco nem um "8" copiado do arquivo de referência;
2. **Que o interruptor do Backoffice não desligue nada de verdade.**
   `contador_ativo` e a ausência de rótulo levam ao mesmo resultado: o
   elemento não é desenhado -- nem vazio, nem como pílula sem número;
3. **Que uma posição livre apareça.** Só as nove de
   `PageSection.Posicao9` -- nunca uma coordenada solta;
4. **Que o contador fique preso a um só desenho de banner.** Os sete
   têm de suportá-lo -- inclusive "Somente texto", sem imagem nenhuma;
5. **Que a lógica de contagem seja duplicada.** Um segundo lugar
   somando cartas divergiria do selo com o tempo;
6. **Que a prévia do Backoffice desenhe um contador diferente do da
   Home pública** -- os dois usam o mesmo parcial e o mesmo método de
   montagem de conteúdo.
"""

import pathlib

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.content.models import PageSection, PageSectionTranslation
from apps.letters import statistics

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")

TEMPLATE_DO_DESENHO = {
    "imagem_texto": "banner_imagem_texto.html",
    "imagem_completa": "banner_imagem_completa.html",
    "somente_texto": "banner_somente_texto.html",
    "destaque": "banner_destaque.html",
    "assimetrico": "banner_assimetrico.html",
    "foto_ampla": "banner_foto_ampla.html",
    "editorial": "banner_editorial.html",
}
TODOS_OS_DESENHOS = tuple(TEMPLATE_DO_DESENHO)

POSICOES = (
    "superior-esquerda",
    "superior-centro",
    "superior-direita",
    "centro-esquerda",
    "centro",
    "centro-direita",
    "inferior-esquerda",
    "inferior-centro",
    "inferior-direita",
)


def secao():
    return PageSection.objects.get(page__key="home", key="hero")


def traducao():
    return PageSectionTranslation.objects.get(
        section__page__key="home", section__key="hero", language="pt"
    )


def usar_desenho(desenho):
    PageSection.objects.filter(page__key="home", key="hero").update(layout=desenho)


def escrever(**textos):
    t = traducao()
    t.content = {**t.content, **textos}
    t.save(update_fields=["content"])
    return t


def corpo(client):
    return client.get(HOME).content.decode()


def url_da_previa():
    return reverse("backoffice:content_preview", args=[secao().pk])


def url_do_editor():
    return reverse("backoffice:content_section", args=[secao().pk])


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
        "editora@mail.com",
        ("core", "access_backoffice"),
        ("content", "view_pagesection"),
        ("content", "change_pagesection"),
    )


@pytest.fixture
def cliente(editora):
    c = Client()
    c.force_login(editora)
    return c


def _payload_do_editor(**extra):
    """
    Um POST completo para a tela de edição -- idioma, os textos
    gravados e os três campos do contador. Só assim salvar não reseta,
    de volta, o que este teste não está tentando mudar (a mesma
    convenção de `layout`/`imagem`: campo ausente é campo desmarcado).
    """
    base = {
        "idioma": "pt",
        **traducao().content,
        "contador_ativo": "on",
        "contador_posicao": secao().counter_position,
        "contador_ao_vivo_ativo": "on",
    }
    base.update(extra)
    return base


# ===========================================================================
# 1. O número é sempre o do sistema -- nunca um texto gravado
# ===========================================================================


class TestNumeroReal:
    def test_sem_carta_nenhuma_mostra_zero(self, client):
        statistics.esquecer_a_contagem()

        assert '<span class="stat-badge-value">0</span>' in corpo(client)

    def test_mostra_a_contagem_do_sistema(self, client, letter):
        letter.finalized_at = letter.created_at
        letter.save(update_fields=["finalized_at"])
        statistics.esquecer_a_contagem()

        html = corpo(client)

        assert statistics.cartas_emitidas() == 1
        assert '<span class="stat-badge-value">1</span>' in html

    def test_o_numero_muda_quando_a_contagem_muda(self, client, letter):
        """Duas leituras diferentes provam que não é um texto fixo."""
        statistics.esquecer_a_contagem()
        zero = corpo(client)

        letter.finalized_at = letter.created_at
        letter.save(update_fields=["finalized_at"])
        statistics.esquecer_a_contagem()
        um = corpo(client)

        assert '<span class="stat-badge-value">0</span>' in zero
        assert '<span class="stat-badge-value">1</span>' in um

    def test_a_referencia_visual_nao_sobrevive_na_home(self, client):
        """"8 cartas geradas" é o texto do arquivo de desenho, não dado."""
        statistics.esquecer_a_contagem()

        assert "8 cartas" not in corpo(client)

    @pytest.mark.parametrize("nome_do_arquivo", TEMPLATE_DO_DESENHO.values())
    def test_nenhum_desenho_escreve_a_contagem_a_mao(self, nome_do_arquivo):
        """
        O dígito "8" do arquivo de referência não pode ter sido copiado
        para dentro de nenhum dos sete templates -- só o `{% comment %}`
        pode falar sobre ele.
        """
        raiz = pathlib.Path(__file__).resolve().parents[3]
        texto = (raiz / "templates" / "core" / "secoes" / nome_do_arquivo).read_text(
            encoding="utf-8"
        )
        executavel = texto.split("{% endcomment %}", 1)[-1]

        assert "8" not in executavel

    def test_o_parcial_do_contador_nao_tem_o_digito(self):
        raiz = pathlib.Path(__file__).resolve().parents[3]
        texto = (
            raiz / "templates" / "core" / "secoes" / "_banner_contador.html"
        ).read_text(encoding="utf-8")
        executavel = texto.split("{% endcomment %}", 1)[-1]

        assert "8" not in executavel


# ===========================================================================
# 2. O interruptor -- ativo/inativo -- e a ausência de rótulo
# ===========================================================================


class TestAtivacao:
    def test_ativo_por_padrao(self, client):
        assert secao().counter_enabled is True
        assert "stat-badge-value" in corpo(client)

    def test_desativado_no_backoffice_some_da_home(self, client):
        PageSection.objects.filter(pk=secao().pk).update(counter_enabled=False)

        assert "stat-badge-value" not in corpo(client)
        assert "banner-contador" not in corpo(client)

    def test_desligar_nao_apaga_o_resto_do_banner(self, client):
        PageSection.objects.filter(pk=secao().pk).update(counter_enabled=False)

        html = corpo(client)

        assert 'class="hero container"' in html
        assert traducao().content["title"] in html

    def test_sem_rotulo_o_contador_nao_aparece_mesmo_ativo(self, client):
        """Um número solto, sem dizer o que conta, não informa nada."""
        assert secao().counter_enabled is True
        escrever(badge_label="")

        assert "stat-badge-value" not in corpo(client)

    def test_o_backoffice_liga_e_desliga_de_verdade(self, cliente):
        cliente.post(url_do_editor(), _payload_do_editor(contador_ativo=""))
        assert secao().counter_enabled is False

        cliente.post(url_do_editor(), _payload_do_editor(contador_ativo="on"))
        assert secao().counter_enabled is True


# ===========================================================================
# 3. O texto do contador é configurável
# ===========================================================================


class TestTextoConfiguravel:
    def test_o_rotulo_escrito_aparece_no_lugar_do_numero(self, client):
        escrever(badge_label="clientes satisfeitos na Bélgica")

        assert "clientes satisfeitos na Bélgica" in corpo(client)

    def test_o_backoffice_grava_o_novo_rotulo(self, cliente):
        cliente.post(url_do_editor(), _payload_do_editor(badge_label="Novo rótulo"))

        assert traducao().content["badge_label"] == "Novo rótulo"
        assert "Novo rótulo" in corpo(Client())


# ===========================================================================
# 4. O indicador "ao vivo" é configurável -- ativo/inativo e texto
# ===========================================================================


class TestIndicadorAoVivo:
    def test_com_nota_e_indicador_ativo_o_selo_aparece(self, client):
        escrever(badge_note="Atualizado em tempo real")

        assert "Atualizado em tempo real" in corpo(client)
        assert "stat-badge-live" in corpo(client)

    def test_indicador_desativado_esconde_o_selo_mas_nao_o_numero(self, client):
        escrever(badge_note="Atualizado em tempo real")
        PageSection.objects.filter(pk=secao().pk).update(counter_live_enabled=False)

        html = corpo(client)

        assert "Atualizado em tempo real" not in html
        assert "stat-badge-value" in html

    def test_sem_nota_o_selo_nao_aparece_mesmo_ativo(self, client):
        assert secao().counter_live_enabled is True
        escrever(badge_note="")

        assert "stat-badge-live" not in corpo(client)

    def test_o_backoffice_liga_e_desliga_o_indicador(self, cliente):
        escrever(badge_note="Atualizado em tempo real")

        cliente.post(url_do_editor(), _payload_do_editor(contador_ao_vivo_ativo=""))
        assert secao().counter_live_enabled is False

        cliente.post(url_do_editor(), _payload_do_editor(contador_ao_vivo_ativo="on"))
        assert secao().counter_live_enabled is True


# ===========================================================================
# 5. A posição -- só as nove do conjunto fechado
# ===========================================================================


class TestPosicionamento:
    def test_o_padrao_e_superior_esquerda(self, client):
        assert secao().counter_position == "superior-esquerda"
        assert 'pos-superior-esquerda' in corpo(client)

    @pytest.mark.parametrize("posicao", POSICOES)
    def test_cada_uma_das_nove_desenha_a_classe_correspondente(self, client, posicao):
        PageSection.objects.filter(pk=secao().pk).update(counter_position=posicao)

        html = corpo(client)

        assert f'banner-contador tint stat-badge pos-{posicao}"' in html

    @pytest.mark.parametrize("posicao", POSICOES)
    def test_o_backoffice_grava_a_posicao_escolhida(self, cliente, posicao):
        cliente.post(url_do_editor(), _payload_do_editor(contador_posicao=posicao))

        assert secao().counter_position == posicao

    def test_as_nove_sao_as_unicas_opcoes_no_formulario(self, cliente):
        """Nada de coordenada livre: o campo é um `<select>` fechado."""
        corpo_html = cliente.get(url_do_editor()).content.decode()

        for posicao in POSICOES:
            assert f'value="{posicao}"' in corpo_html

    def test_valor_fora_do_conjunto_e_recusado_pelo_formulario(self, cliente):
        resposta = cliente.post(
            url_do_editor(), _payload_do_editor(contador_posicao="direita-solta-33px")
        )

        assert resposta.status_code == 200
        assert secao().counter_position != "direita-solta-33px"


# ===========================================================================
# 6. Funciona nos sete desenhos -- inclusive sem imagem nenhuma
# ===========================================================================


class TestTodosOsDesenhos:
    @pytest.mark.parametrize("desenho", TODOS_OS_DESENHOS)
    def test_o_contador_aparece_em_cada_um_dos_sete(self, client, desenho):
        usar_desenho(desenho)

        assert "stat-badge-value" in corpo(client)

    def test_funciona_em_somente_texto_sem_imagem_nenhuma(self, client):
        usar_desenho("somente_texto")

        html = corpo(client)

        assert "img-slot" not in html
        assert "stat-badge-value" in html

    @pytest.mark.parametrize("desenho", TODOS_OS_DESENHOS)
    def test_desativado_continua_ausente_em_qualquer_desenho(self, client, desenho):
        usar_desenho(desenho)
        PageSection.objects.filter(pk=secao().pk).update(counter_enabled=False)

        assert "stat-badge-value" not in corpo(client)

    def test_nao_ha_uma_segunda_logica_de_contagem(self):
        """
        Um só ponto no template lê `cartas_emitidas` -- os sete desenhos
        incluem o MESMO parcial, em vez de calcular ou copiar o número
        cada um a seu modo.
        """
        raiz = pathlib.Path(__file__).resolve().parents[3]
        pasta = raiz / "templates" / "core" / "secoes"

        for nome_do_arquivo in TEMPLATE_DO_DESENHO.values():
            texto = (pasta / nome_do_arquivo).read_text(encoding="utf-8")
            assert 'include "core/secoes/_banner_contador.html"' in texto
            assert "cartas_emitidas" not in texto.split("{% endcomment %}", 1)[-1]

        parcial = (pasta / "_banner_contador.html").read_text(encoding="utf-8")
        executavel = parcial.split("{% endcomment %}", 1)[-1]
        assert executavel.count("cartas_emitidas") == 1


# ===========================================================================
# 7. A prévia do Backoffice usa o mesmo parcial da Home
# ===========================================================================


class TestPrevia:
    def test_a_previa_mostra_o_contador_salvo(self, cliente, letter):
        letter.finalized_at = letter.created_at
        letter.save(update_fields=["finalized_at"])
        statistics.esquecer_a_contagem()

        html = cliente.get(url_da_previa()).content.decode()

        assert '<span class="stat-badge-value">1</span>' in html

    def test_a_previa_reflete_o_interruptor_ainda_nao_salvo(self, cliente):
        assert secao().counter_enabled is True

        html = cliente.post(
            url_da_previa(), _payload_do_editor(contador_ativo="")
        ).content.decode()

        assert "stat-badge-value" not in html
        assert secao().counter_enabled is True

    def test_a_previa_reflete_a_posicao_ainda_nao_salva(self, cliente):
        html = cliente.post(
            url_da_previa(), _payload_do_editor(contador_posicao="inferior-direita")
        ).content.decode()

        assert 'pos-inferior-direita"' in html
        assert secao().counter_position != "inferior-direita"

    def test_a_previa_reflete_o_rotulo_ainda_nao_salvo(self, cliente):
        html = cliente.post(
            url_da_previa(), _payload_do_editor(badge_label="Rótulo só na prévia")
        ).content.decode()

        assert "Rótulo só na prévia" in html
        assert traducao().content["badge_label"] != "Rótulo só na prévia"

    def test_previa_e_salvamento_desenham_o_mesmo_contador(self, cliente):
        """
        As duas telas montam o conteúdo com `FormularioDeSecao`: o que a
        prévia mostrou tem de ser exatamente o que fica gravado.
        """
        dados = _payload_do_editor(
            badge_label="Mesmo contador nos dois", contador_posicao="centro"
        )

        da_previa = cliente.post(url_da_previa(), dados).content.decode()
        cliente.post(url_do_editor(), dados)

        assert "Mesmo contador nos dois" in da_previa
        assert 'pos-centro"' in da_previa
        assert traducao().content["badge_label"] == "Mesmo contador nos dois"
        assert secao().counter_position == "centro"
