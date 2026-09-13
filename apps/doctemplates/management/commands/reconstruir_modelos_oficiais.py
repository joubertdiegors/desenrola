"""
Materializa os modelos oficiais: layout no banco e assets em MEDIA_ROOT.

    migrate
    reconstruir_modelos_oficiais      <-- este
    collectstatic

POR QUE ISTO NAO ESTA NA MIGRATION
----------------------------------
A migration 0011 grava o LAYOUT -- dado puro, nenhuma escrita em disco.
Os binarios ficam aqui, de proposito:

  * migration que escreve em MEDIA_ROOT quebra em armazenamento remoto e
    em sistema de arquivos somente-leitura;
  * e gravaria um arquivo a cada criacao de banco de teste. Isso nao e
    hipotese: a arquitetura anterior faz assim e ja deixou mais de mil
    PNGs esquecidos em `media/assets/`.

Separar tambem torna o passo visivel no deploy, em vez de escondido no
meio de um `migrate`.

DE ONDE VEM O BINARIO
---------------------
Do PDF oficial versionado no repositorio -- `pdfengine/assets/fr/
Modelo-Carta-Convite-FR.pdf`. Nada depende de arquivo que exista so na
maquina de quem desenvolveu: um clone novo tem tudo o que e preciso.

IDEMPOTENTE
-----------
Rodar de novo nao cria asset nem arquivo duplicado, e NAO reescreve um
layout ja existente -- um administrador pode ter ajustado o documento, e
nenhum passo de deploy tem o direito de apagar esse trabalho. Quem
precisar mesmo reconstruir por cima chama
`services.modelo_fr.aplicar(..., forcar=True)` explicitamente.
"""

from django.core.management.base import BaseCommand

from apps.content.models import Asset
from apps.doctemplates.models import DocumentTemplate
from apps.doctemplates.services import modelo_fr

# Os modelos oficiais que tem reconstrucao controlada, e o servico que
# sabe reconstruir cada um. NL/EN/PT entram aqui quando ganharem o seu:
# hoje ainda nascem com `layout` vazio (ver `services/biblioteca.py`).
RECONSTRUCOES = (
    (modelo_fr.SLUG_DO_MODELO_FR, modelo_fr.reconstruir),
)


class Command(BaseCommand):
    help = (
        "Reconstroi os modelos oficiais de documento: garante o layout "
        "estrutural e materializa os assets (logo) em MEDIA_ROOT."
    )

    def handle(self, *args, **opcoes):
        self.stdout.write("Reconstruindo os modelos oficiais...")

        reconstruidos = 0
        for slug, reconstruir in RECONSTRUCOES:
            if not DocumentTemplate.objects.filter(slug=slug).exists():
                # Sem o modelo na biblioteca nao ha o que reconstruir. Nao
                # e erro: pode ser um banco onde a semeadura ainda nao
                # rodou.
                self.stdout.write(
                    self.style.WARNING(f"  ! {slug}: modelo não encontrado, ignorado")
                )
                continue

            resultado = reconstruir(DocumentTemplate, Asset)
            reconstruidos += 1
            for linha in self._relatar(resultado):
                self.stdout.write(linha)

        self.stdout.write(f"Pronto. {reconstruidos} modelo(s) oficial(is) verificado(s).")

    def _simbolo(self):
        """
        O "✓" onde o terminal souber escreve-lo, "OK" onde nao souber.

        O console do Windows costuma vir em cp1252, que nao tem esse
        glifo: escrever direto derruba o comando com UnicodeEncodeError
        -- no meio do deploy, depois de ja ter criado o asset. Um passo
        de deploy nao pode morrer por causa de um caractere decorativo.
        """
        codificacao = getattr(self.stdout, "encoding", None)
        try:
            "✓".encode(codificacao or "ascii")
        except (LookupError, UnicodeEncodeError):
            return "OK"
        return "✓"

    def _relatar(self, resultado):
        """As linhas de relato de uma reconstrucao, na ordem do fluxo."""
        marca = self.style.SUCCESS(f"  {self._simbolo()}")
        slug = resultado.slug

        elementos = len((resultado.modelo.layout or {}).get("elements", []))
        layout = "gravado" if resultado.layout_gravado else "já existia"
        yield f"{marca} {slug}: layout {layout} ({elementos} elementos)"

        asset = "criado" if resultado.asset_criado else "reaproveitado"
        yield f"{marca} {slug}: asset do logo IBZ {asset} (#{resultado.asset.pk})"

        if resultado.logo_vinculado:
            yield f"{marca} {slug}: layout apontado para o asset"
