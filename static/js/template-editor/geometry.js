/*
 * Conversao entre as coordenadas do DOCUMENTO e as da TELA.
 *
 * Editor visual dos modelos da biblioteca (Etapa 3.2). Nada aqui toca o
 * DOM: sao contas puras, exercitadas no Node pelos testes.
 *
 * DOIS SISTEMAS, UM SO GRAVADO
 * ----------------------------
 *   documento -- pontos (pt), origem no canto superior esquerdo, Y para
 *                baixo. E o que fica em `DocumentTemplate.layout`.
 *   tela      -- pixels CSS, mesma origem e mesmo sentido. So muda de
 *                escala: tela = documento x zoom.
 *
 * O zoom NUNCA entra no que se grava. Um `x` de 49.6 continua 49.6 com
 * a pagina a 40% ou a 200% -- o zoom e uma lente, nao um dado. Por isso
 * toda leitura de mouse passa por `paraDocumento()` antes de virar
 * posicao, e toda escrita na tela passa por `paraTela()`.
 *
 * A unidade vem do tipo de documento (`DocumentType.page`); este modulo
 * nao a interpreta, so preserva os numeros.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.TEGeometry = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Abaixo de 25% nada e legivel; acima de 400% a pagina fica maior do
  // que qualquer tela util.
  var ZOOM_MINIMO = 0.25;
  var ZOOM_MAXIMO = 4;

  // Piso do zoom inicial. "Caber" pode dar uma pagina de 230px, em que
  // um campo de 13pt tem 5px de altura: tecnicamente visivel,
  // inutilizavel na pratica.
  var ZOOM_INICIAL_MINIMO = 0.5;

  function limitarZoom(zoom) {
    return Math.max(ZOOM_MINIMO, Math.min(ZOOM_MAXIMO, Number(zoom)));
  }

  /* Um comprimento do documento, em pixels da tela. */
  function paraTela(valor, zoom) {
    return Number(valor) * Number(zoom);
  }

  /* O caminho de volta: o que o mouse mediu em pixels, em pontos. */
  function paraDocumento(valor, zoom) {
    var escala = Number(zoom);
    if (!escala) {
      throw new Error("zoom não pode ser zero");
    }
    return Number(valor) / escala;
  }

  function caixaParaTela(caixa, zoom) {
    return {
      x: paraTela(caixa.x, zoom),
      y: paraTela(caixa.y, zoom),
      width: paraTela(caixa.width, zoom),
      height: paraTela(caixa.height, zoom)
    };
  }

  function caixaParaDocumento(caixa, zoom) {
    return {
      x: paraDocumento(caixa.x, zoom),
      y: paraDocumento(caixa.y, zoom),
      width: paraDocumento(caixa.width, zoom),
      height: paraDocumento(caixa.height, zoom)
    };
  }

  /*
   * O zoom que faz a pagina caber na largura disponivel.
   *
   * Nunca passa de 100%: ampliar so porque sobra tela daria uma falsa
   * impressao de tamanho real.
   */
  function zoomParaCaber(larguraDisponivel, larguraDaPagina, margem) {
    var folga = margem === undefined ? 48 : Number(margem);
    var util = Number(larguraDisponivel) - folga;
    if (util <= 0 || !larguraDaPagina) {
      return ZOOM_MINIMO;
    }
    return limitarZoom(Math.min(1, util / Number(larguraDaPagina)));
  }

  /* Como acima, mas com o piso de legibilidade -- para abrir o editor. */
  function zoomInicial(larguraDisponivel, larguraDaPagina, margem) {
    return Math.max(
      ZOOM_INICIAL_MINIMO,
      zoomParaCaber(larguraDisponivel, larguraDaPagina, margem)
    );
  }

  /*
   * Arredonda para a grade quando o encaixe esta ligado. Passo 0
   * desliga e devolve o valor intacto -- e o que permite posicionar com
   * a precisao decimal que o documento exige.
   */
  function encaixar(valor, passo) {
    var p = Number(passo);
    if (!p) {
      return Number(valor);
    }
    return Math.round(Number(valor) / p) * p;
  }

  /* Largura e altura nunca sao negativas; o servidor recusaria. */
  function dimensaoValida(valor) {
    var n = Number(valor);
    return isFinite(n) && n >= 0 ? n : 0;
  }

  return {
    ZOOM_MINIMO: ZOOM_MINIMO,
    ZOOM_MAXIMO: ZOOM_MAXIMO,
    ZOOM_INICIAL_MINIMO: ZOOM_INICIAL_MINIMO,
    limitarZoom: limitarZoom,
    paraTela: paraTela,
    paraDocumento: paraDocumento,
    caixaParaTela: caixaParaTela,
    caixaParaDocumento: caixaParaDocumento,
    zoomParaCaber: zoomParaCaber,
    zoomInicial: zoomInicial,
    encaixar: encaixar,
    dimensaoValida: dimensaoValida
  };
});
