"""
Recursos tipograficos compartilhados do Desenrola.

Biblioteca Python pura: nao importa Django, nao acessa banco e nao conhece
models. O que sobrou aqui depois de a geracao de PDF passar inteira para
`apps.doctemplates.services.pdf` (o renderer estrutural):

  * `fontconfig` -- registro das fontes embutidas (Liberation Sans), usado
                    pelo renderer;
  * `textnorm`   -- normalizacao tipografica dos valores que vao para o
                    documento (tracos, espacos);
  * `fonts/`     -- os arquivos TrueType versionados;
  * `assets/`    -- o PDF oficial frances, fonte das MEDIDAS e do logo
                    extraido por `services.carta_convite`.

O PDF oficial nunca entra no documento gerado: ele e so a referencia de
onde cada elemento fica.
"""

__all__: list[str] = []
