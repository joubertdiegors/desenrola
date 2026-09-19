"""
O contador da Home: valor inicial + cartas emitidas de verdade.

O QUE ESTA SUÍTE EXISTE PARA IMPEDIR
------------------------------------
1. **Que o valor more fora da configuração do contador.** É uma coluna
   de `PageSection`, ao lado das outras três do contador, e se edita no
   MESMO grupo do formulário da Home -- sem tela nem menu novos;
2. **Que a conta saia errada.** A Home mostra valor inicial + a
   contagem real (`letters.statistics.cartas_emitidas()`): 1500 + 37 =
   1537; trocar o valor para 2000 passa a mostrar 2037, na visita
   seguinte;
3. **Que o valor inicial vá para o público separado.** Nem no HTML,
   nem como atributo, nem no contexto do template: o template recebe só
   o número pronto;
4. **Que a prévia do Backoffice faça outra conta.** Ela usa a mesma
   função, com o valor digitado ainda não salvo;
5. **Que um valor negativo ou absurdo seja gravado.**
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import translation

from apps.content import services
from apps.content.models import PageSection, PageSectionTranslation
from apps.letters import statistics

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")


def secao():
    return PageSection.objects.get(page__key="home", key="hero")


def url_do_editor():
    return reverse("backoffice:content_section", args=[secao().pk])


def url_da_previa():
    return reverse("backoffice:content_preview", args=[secao().pk])


def valor_inicial(numero):
    PageSection.objects.filter(pk=secao().pk).update(counter_initial_value=numero)


def cartas_reais(numero):
    """A contagem real, pelo cache que o próprio `statistics` consulta."""
    cache.set(statistics.CHAVE_DO_CACHE, numero, statistics.VALIDADE_EM_SEGUNDOS)


def exibido(numero):
    """O número como a Home o escreve (`intcomma`, em português)."""
    with translation.override("pt"):
        return f'<span class="banner-contador-valor">{intcomma(numero)}</span>'


@pytest.fixture
def cliente(db):
    pessoa = get_user_model().objects.create_user(
        email="editora-contador@mail.com", password="x", full_name="Clara Dias"
    )
    for app_label, codename in (
        ("core", "access_backoffice"),
        ("content", "view_pagesection"),
        ("content", "change_pagesection"),
    ):
        pessoa.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    c = Client()
    c.force_login(pessoa)
    return c


def _payload(**extra):
    """Um POST completo da tela -- os textos gravados e os campos do contador."""
    traducao = PageSectionTranslation.objects.get(
        section__page__key="home", section__key="hero", language="pt"
    )
    base = {
        "idioma": "pt",
        **traducao.content,
        "contador_ativo": "on",
        "contador_posicao": secao().counter_position,
        "contador_ao_vivo_ativo": "on",
    }
    base.update(extra)
    return base


# ===========================================================================
# 1. Na configuração que já existia
# ===========================================================================


class TestNaConfiguracaoExistente:
    def test_nasce_em_zero(self):
        assert secao().counter_initial_value == 0

    def test_o_campo_esta_no_grupo_do_contador(self, cliente):
        """Na mesma tela e no mesmo cartão dos outros campos do contador."""
        resposta = cliente.get(url_do_editor())
        form = resposta.context["form"]
        nomes = [campo.name for campo in form.campos_da_parte()]

        assert "contador_valor_inicial" in nomes
        assert nomes.index("contador_ao_vivo_ativo") < nomes.index("contador_valor_inicial")
        assert "Valor inicial do contador" in resposta.content.decode()

    def test_grava_na_secao(self, cliente):
        cliente.post(url_do_editor(), _payload(contador_valor_inicial="1500"))

        assert secao().counter_initial_value == 1500

    def test_vazio_vale_zero(self, cliente):
        valor_inicial(40)

        cliente.post(url_do_editor(), _payload(contador_valor_inicial=""))

        assert secao().counter_initial_value == 0

    @pytest.mark.parametrize("valor", ["-1", "1000001", "dez"])
    def test_valor_fora_do_permitido_e_recusado(self, cliente, valor):
        valor_inicial(40)

        resposta = cliente.post(url_do_editor(), _payload(contador_valor_inicial=valor))

        assert resposta.status_code == 200
        assert secao().counter_initial_value == 40

    def test_nao_mexe_nos_outros_campos_do_contador(self, cliente):
        cliente.post(
            url_do_editor(),
            _payload(contador_valor_inicial="7", contador_posicao="inferior-direita"),
        )

        atual = secao()
        assert atual.counter_initial_value == 7
        assert atual.counter_position == "inferior-direita"
        assert atual.counter_enabled is True


# ===========================================================================
# 2. A regra: valor inicial + cartas reais
# ===========================================================================


class TestARegra:
    def test_1500_mais_37_mostra_1537(self, client):
        valor_inicial(1500)
        cartas_reais(37)

        assert exibido(1537) in client.get(HOME).content.decode()

    def test_mudar_o_valor_inicial_vale_na_visita_seguinte(self, client):
        """O cache é só da contagem real -- o valor inicial vale na hora."""
        cartas_reais(37)
        valor_inicial(1500)
        antes = client.get(HOME).content.decode()

        valor_inicial(2000)
        depois = client.get(HOME).content.decode()

        assert exibido(1537) in antes
        assert exibido(2037) in depois

    def test_sem_valor_inicial_e_a_contagem_real(self, client):
        cartas_reais(37)

        assert exibido(37) in client.get(HOME).content.decode()

    def test_a_contagem_real_continua_vindo_do_sistema(self, client, letter):
        """Uma carta finalizada de verdade entra na soma."""
        valor_inicial(1500)
        letter.finalized_at = letter.created_at
        letter.save(update_fields=["finalized_at"])
        statistics.esquecer_a_contagem()

        assert exibido(1501) in client.get(HOME).content.decode()

    def test_uma_conta_so(self):
        cartas_reais(37)

        assert services.numero_do_contador(1500) == 1537
        assert services.numero_do_contador(0) == 37
        assert services.numero_do_contador(None) == 37


# ===========================================================================
# 3. O valor inicial não chega ao público separado
# ===========================================================================


class TestNaoExposto:
    def test_o_html_so_tem_o_numero_final(self, client):
        valor_inicial(1500)
        cartas_reais(37)

        html = client.get(HOME).content.decode()

        assert "1500" not in html
        assert "1.500" not in html
        assert "1.537" in html

    def test_o_contexto_do_template_so_tem_o_numero_final(self, client):
        valor_inicial(1500)
        cartas_reais(37)

        resposta = client.get(HOME)
        contextos = resposta.context if isinstance(resposta.context, list) else [resposta.context]
        valores = {}
        for contexto in contextos:
            valores.update(contexto.flatten())
        inteiros = [v for v in valores.values() if isinstance(v, int) and not isinstance(v, bool)]

        assert valores["cartas_emitidas"] == 1537
        assert 1500 not in inteiros

    def test_a_parte_da_pagina_nao_o_carrega(self):
        """O que os templates públicos recebem de cada parte não tem o campo."""
        parte = services.partes_da_pagina("home")["hero"]

        assert not hasattr(parte, "contador_valor_inicial")
        assert not hasattr(parte, "counter_initial_value")

    def test_a_home_nao_ganhou_consulta(self, client, django_assert_max_num_queries):
        """
        O valor sai da seção que a Home já carrega -- nenhuma consulta a
        mais. Cache frio, como no orçamento de `test_home.TestCusto`.
        """
        valor_inicial(1500)
        cache.clear()

        with django_assert_max_num_queries(9):
            client.get(HOME)


# ===========================================================================
# 4. A prévia do Backoffice faz a mesma conta
# ===========================================================================


class TestPrevia:
    def test_a_previa_mostra_o_numero_salvo(self, cliente):
        valor_inicial(1500)
        cartas_reais(37)

        assert exibido(1537) in cliente.get(url_da_previa()).content.decode()

    def test_a_previa_reflete_o_valor_ainda_nao_salvo(self, cliente):
        valor_inicial(1500)
        cartas_reais(37)

        html = cliente.post(
            url_da_previa(), _payload(contador_valor_inicial="2000")
        ).content.decode()

        assert exibido(2037) in html
        assert secao().counter_initial_value == 1500
