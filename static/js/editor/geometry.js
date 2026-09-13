/*
 * Conversao de coordenadas do editor visual.
 *
 * Espelho em JavaScript de apps/doctemplates/coordinates.py. As duas
 * implementacoes existem porque as contas sao necessarias dos dois lados
 * -- o navegador para desenhar e arrastar, o servidor para validar e, na
 * Etapa 4.2D, gerar o PDF. Um teste de paridade roda estas funcoes no
 * Node e compara com as de Python, para as duas nao divergirem em
 * silencio (apps/doctemplates/tests/test_editor_js.py).
 *
 * Os tres sistemas estao documentados no modulo Python. Em resumo:
 *   documento = pontos, origem em cima, Y para baixo   (o que se grava)
 *   canvas    = pixels, origem em cima, Y para baixo   (o que se ve)
 *   pdf       = pontos, origem em baixo, Y para cima   (Etapa 4.2D)
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.EditorGeometry = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var A4_WIDTH_PT = 595.2756;
  var A4_HEIGHT_PT = 841.8898;

  var ZOOM_MINIMO = 0.25;
  var ZOOM_MAXIMO = 4.0;

  function clampZoom(zoom) {
    return Math.max(ZOOM_MINIMO, Math.min(ZOOM_MAXIMO, Number(zoom)));
  }

  function pontosParaPixels(valor, zoom) {
    return Number(valor) * Number(zoom);
  }

  function pixelsParaPontos(valor, zoom) {
    return Number(valor) / Number(zoom);
  }

  function caixaParaCanvas(caixa, zoom) {
    return {
      x: pontosParaPixels(caixa.x, zoom),
      y: pontosParaPixels(caixa.y, zoom),
      width: pontosParaPixels(caixa.width, zoom),
      height: pontosParaPixels(caixa.height, zoom)
    };
  }

  function caixaDoCanvas(caixa, zoom) {
    return {
      x: pixelsParaPontos(caixa.x, zoom),
      y: pixelsParaPontos(caixa.y, zoom),
      width: pixelsParaPontos(caixa.width, zoom),
      height: pixelsParaPontos(caixa.height, zoom)
    };
  }

  function zoomParaCaber(larguraDisponivel, larguraDaPagina, margem) {
    var pagina = larguraDaPagina === undefined ? A4_WIDTH_PT : Number(larguraDaPagina);
    var folga = margem === undefined ? 32 : Number(margem);
    var util = Number(larguraDisponivel) - folga;
    if (util <= 0) {
      return ZOOM_MINIMO;
    }
    // Nunca passa de 100%: ampliar so porque sobra tela daria falsa
    // impressao de tamanho real.
    return clampZoom(Math.min(1, util / pagina));
  }

  /*
   * Documento -> PDF. Uma caixa e ancorada pelo TOPO no documento e pela
   * BASE no PDF, por isso a conta subtrai tambem a altura. Esquecer a
   * altura desloca cada elemento por si mesmo -- um erro que parece
   * "quase certo" e passa despercebido em elementos baixos.
   */
  function paraCoordenadasPdf(caixa, alturaDaPagina) {
    var altura = alturaDaPagina === undefined ? A4_HEIGHT_PT : Number(alturaDaPagina);
    return {
      x: Number(caixa.x),
      y: altura - Number(caixa.y) - Number(caixa.height),
      width: Number(caixa.width),
      height: Number(caixa.height)
    };
  }

  // Inverter um eixo duas vezes devolve o original: a transformacao e a
  // sua propria inversa. Ver o docstring da versao Python.
  function doPdfParaDocumento(caixa, alturaDaPagina) {
    return paraCoordenadasPdf(caixa, alturaDaPagina);
  }

  /*
   * Arredonda para a grade quando o "snap" esta ligado. `passo` em
   * pontos; passo 0 desliga (devolve o valor intacto, sem perder as
   * casas decimais -- e o que permite posicionar com precisao de PDF).
   */
  function encaixarNaGrade(valor, passo) {
    var p = Number(passo);
    if (!p) {
      return Number(valor);
    }
    return Math.round(Number(valor) / p) * p;
  }

  return {
    A4_WIDTH_PT: A4_WIDTH_PT,
    A4_HEIGHT_PT: A4_HEIGHT_PT,
    ZOOM_MINIMO: ZOOM_MINIMO,
    ZOOM_MAXIMO: ZOOM_MAXIMO,
    clampZoom: clampZoom,
    pontosParaPixels: pontosParaPixels,
    pixelsParaPontos: pixelsParaPontos,
    caixaParaCanvas: caixaParaCanvas,
    caixaDoCanvas: caixaDoCanvas,
    zoomParaCaber: zoomParaCaber,
    paraCoordenadasPdf: paraCoordenadasPdf,
    doPdfParaDocumento: doPdfParaDocumento,
    encaixarNaGrade: encaixarNaGrade
  };
});
