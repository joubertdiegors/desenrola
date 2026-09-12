"""
Testes dos modelos oficiais semeados por migracao: um documento por
idioma, cada um com uma versao publicada, todos com a MESMA configuracao
de campos (a invariante que permite trocar o idioma da carta sem
invalidar o preenchimento).
"""

import pytest
from django.conf import settings

from apps.doctemplates.models import LetterTemplate, TemplateVersion
from apps.doctemplates.official_templates import CARTA_CONVITE_FIELD_SCHEMA, official_slug

pytestmark = pytest.mark.django_db


def _published_versions():
    return {
        code: LetterTemplate.objects.get(slug=official_slug(code)).published_version
        for code, _label in settings.LANGUAGES
    }


class TestSemeadura:
    @pytest.mark.parametrize("language", ["pt", "fr", "nl", "en"])
    def test_existe_um_modelo_ativo_por_idioma(self, language):
        template = LetterTemplate.objects.get(slug=official_slug(language))

        assert template.language == language
        assert template.is_active is True

    def test_ha_exatamente_um_modelo_por_idioma_do_site(self):
        slugs = {official_slug(code) for code, _label in settings.LANGUAGES}

        assert LetterTemplate.objects.filter(slug__in=slugs).count() == len(settings.LANGUAGES)

    def test_o_slug_sem_idioma_da_migracao_0002_nao_sobra(self):
        """0003 renomeia o registro de 0002 para o slug do francês."""
        assert not LetterTemplate.objects.filter(slug="carta-convite-curta-duracao").exists()

    @pytest.mark.parametrize("language", ["pt", "fr", "nl", "en"])
    def test_cada_modelo_tem_uma_versao_publicada_com_o_schema_vigente(self, language):
        version = LetterTemplate.objects.get(slug=official_slug(language)).published_version

        assert version is not None
        assert version.status == TemplateVersion.Status.PUBLISHED
        assert version.published_at is not None
        assert version.field_schema == CARTA_CONVITE_FIELD_SCHEMA

    def test_os_quatro_documentos_tem_os_mesmos_campos(self):
        """
        Mesmas chaves, tipos e ordem em todos os idiomas: e isso que faz
        `Letter.data` continuar valido ao trocar o idioma no meio do
        assistente. Só o texto exibido muda.
        """
        assinaturas = {
            code: [(f["key"], f["type"], f["order"]) for f in version.field_schema["fields"]]
            for code, version in _published_versions().items()
        }

        referencia = assinaturas["pt"]
        assert all(assinatura == referencia for assinatura in assinaturas.values())

    def test_nenhuma_versao_publicada_foi_alterada_no_lugar(self):
        """
        Se o schema vigente mudou, a migracao cria a PROXIMA versao e
        desativa a anterior — nunca reescreve uma versao publicada. Aqui
        garantimos que no máximo uma versão de cada modelo está publicada.
        """
        for code, _label in settings.LANGUAGES:
            template = LetterTemplate.objects.get(slug=official_slug(code))
            publicadas = template.versions.filter(status=TemplateVersion.Status.PUBLISHED)
            assert publicadas.count() == 1
