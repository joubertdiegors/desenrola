/*
 * Desenrola — theme.js
 *
 * A v2 do design nao tem modo escuro: e um tema unico e claro. O que e
 * parametrizavel e a COR (principal e de sucesso), pelo backoffice em
 * Aparencia — mesmo mecanismo do arquivo de referencia (desenrola-v2-1
 * -sistema.html): duas classes no <html>, uma por cor, persistidas em
 * localStorage.
 *
 * Isso e uma personalizacao do NAVEGADOR de quem esta vendo a pagina, nao
 * uma configuracao do site publicada no servidor — o backoffice ainda nao
 * tem onde guardar isso no banco (fase visual). Quando essa etapa entrar,
 * a leitura passa a vir do servidor e este arquivo perde a necessidade de
 * ler o localStorage no primeiro paint.
 *
 *   [data-theme-primary="t-roxo"]  escolhe a cor principal (swatch)
 *   [data-theme-success="s-azul"]  escolhe a cor de sucesso (swatch)
 *   valor vazio ("") volta para o padrao (azul / verde)
 */
(function () {
  "use strict";

  var KEY = "desenrola.theme";
  var root = document.documentElement;
  var PRIMARY_CLASSES = ["t-azul", "t-roxo", "t-verde", "t-laranja", "t-grafite"];
  var SUCCESS_CLASSES = ["s-verde", "s-azul", "s-ambar", "s-teal"];

  function read() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || "{}");
    } catch (e) {
      return {};
    }
  }

  function apply(theme) {
    PRIMARY_CLASSES.forEach(function (cls) { root.classList.remove(cls); });
    SUCCESS_CLASSES.forEach(function (cls) { root.classList.remove(cls); });
    if (theme.p) { root.classList.add(theme.p); }
    if (theme.s) { root.classList.add(theme.s); }

    var swatches = document.querySelectorAll("[data-theme-primary], [data-theme-success]");
    for (var i = 0; i < swatches.length; i++) {
      var el = swatches[i];
      var isPrimary = el.hasAttribute("data-theme-primary");
      var value = el.getAttribute(isPrimary ? "data-theme-primary" : "data-theme-success");
      var current = isPrimary ? theme.p || "" : theme.s || "";
      el.classList.toggle("is-on", value === current);
      el.setAttribute("aria-pressed", value === current ? "true" : "false");
    }
  }

  function setTheme(partial) {
    var theme = read();
    Object.assign(theme, partial);
    apply(theme);
    try { localStorage.setItem(KEY, JSON.stringify(theme)); } catch (e) { /* indisponivel */ }
  }

  document.addEventListener("click", function (event) {
    var primary = event.target.closest("[data-theme-primary]");
    if (primary) { setTheme({ p: primary.getAttribute("data-theme-primary") }); return; }

    var success = event.target.closest("[data-theme-success]");
    if (success) { setTheme({ s: success.getAttribute("data-theme-success") }); }
  });

  window.Desenrola = window.Desenrola || {};
  window.Desenrola.setTheme = setTheme;

  apply(read());
})();
