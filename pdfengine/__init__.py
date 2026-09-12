"""
Engine de geracao de PDF do Desenrola.

Esta e uma biblioteca Python pura: nao importa Django, nao acessa banco e nao
conhece models. Recebe o PDF oficial, um mapa de campos e os valores; devolve
bytes. Isso mantem testavel em isolamento a parte mais critica do sistema.

Principio: o PDF oficial NUNCA e recriado em HTML/CSS. Ele e aberto e recebe
uma camada com os dados variaveis, preservando o conteudo original intacto.

Documento implementado ate agora: a Carta Convite oficial francesa
(`render.render_invitation_letter_fr`). Os outros idiomas ainda nao tem
documento oficial.

Mapa do pacote:

  * `render`      -- a API publica: dados -> bytes do PDF;
  * `layouts/`    -- as coordenadas medidas de cada documento (o unico
                     lugar com numeros de posicao; e o que, mais adiante,
                     pode virar dado administravel em `TemplateVersion`);
  * `measure`     -- quebra de linha e deteccao de overflow;
  * `redact`      -- remocao do texto de amostra da pagina-base;
  * `fontconfig`  -- as fontes do overlay (Liberation Sans, embutida);
  * `exceptions`  -- os erros explicitos (nada falha em silencio);
  * `tools/`      -- conferencia visual, so para desenvolvimento.
"""

__all__: list[str] = []
