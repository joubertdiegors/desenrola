/*
 * Setas do carrossel de "Nossos Parceiros" (Bloco B).
 *
 * PROGRESSIVO
 * -----------
 * A trilha (`.partners-carrossel`) já rola sem nenhuma linha de script:
 * toque, roda do mouse e teclado (a trilha é focável) funcionam por CSS
 * puro (`overflow-x: auto`). As setas, quando o Backoffice as liga, são
 * só mais um jeito de mover a mesma rolagem -- nunca o único.
 *
 * "PREFERS-REDUCED-MOTION" TAMBÉM VALE PARA CLIQUE
 * ---------------------------------------------------
 * `scrollBy({behavior: "smooth"})` anima mesmo quando o navegador não
 * suaviza rolagem nenhuma sozinho -- por isso a checagem aqui, e não só
 * no CSS.
 */
(function () {
  "use strict";

  var reduzido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.querySelectorAll(".partners-carrossel-caixa").forEach(function (caixa) {
    var trilha = caixa.querySelector(".partners-carrossel");
    var setas = caixa.querySelectorAll("[data-partners-seta]");
    if (!trilha || !setas.length) {
      return;
    }

    setas.forEach(function (seta) {
      seta.addEventListener("click", function () {
        var item = trilha.querySelector(".partner-item");
        // O passo é a largura de um cartão, com o espaçamento entre
        // eles -- rolar um "cartão inteiro" por clique, não um pedaço.
        var passo = item ? item.getBoundingClientRect().width + 20 : trilha.clientWidth;
        trilha.scrollBy({
          left: Number(seta.getAttribute("data-partners-seta")) * passo,
          behavior: reduzido ? "auto" : "smooth",
        });
      });
    });
  });
})();
