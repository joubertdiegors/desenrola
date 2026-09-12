/*
 * Desenrola — theme.js
 * Alternancia claro/escuro, consistente em todas as telas.
 *
 * Replica o mecanismo do arquivo de identidade visual: a preferencia fica
 * em localStorage na chave "desenrola.theme" com os valores "escuro"
 * (padrao) e "claro"; o tema claro e a classe `light` no <html>. O valor
 * "sistema" (opcao do perfil) segue a preferencia do sistema operacional.
 *
 * O template base aplica a classe antes do primeiro paint (script inline no
 * <head>); este arquivo cuida da interacao:
 *   - [data-theme-toggle]           alterna entre os dois temas (botao sol/lua);
 *   - [data-theme-option="claro"]   escolhe um tema explicitamente (segmentado);
 *   - [data-theme-switch]           interruptor "Modo claro" (checkbox).
 */
(function () {
  "use strict";

  var KEY = "desenrola.theme";
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }

  function resolve(pref) {
    if (pref === "claro") { return "claro"; }
    if (pref === "sistema") { return media && media.matches ? "claro" : "escuro"; }
    return "escuro";
  }

  function apply(pref) {
    var theme = resolve(pref);
    var light = theme === "claro";
    root.classList.toggle("light", light);

    var toggles = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].setAttribute("aria-pressed", light ? "true" : "false");
    }

    var options = document.querySelectorAll("[data-theme-option]");
    for (var j = 0; j < options.length; j++) {
      var option = options[j];
      var selected = option.getAttribute("data-theme-option") === pref;
      var input = option.querySelector("input");
      if (input) { input.checked = selected; }
    }

    var switches = document.querySelectorAll("[data-theme-switch]");
    for (var k = 0; k < switches.length; k++) {
      switches[k].checked = light;
    }
  }

  function setTheme(pref) {
    if (pref !== "claro" && pref !== "sistema") { pref = "escuro"; }
    apply(pref);
    try { localStorage.setItem(KEY, pref); } catch (e) { /* armazenamento indisponivel */ }
  }

  function currentTheme() {
    return root.classList.contains("light") ? "claro" : "escuro";
  }

  function toggleTheme() {
    setTheme(currentTheme() === "claro" ? "escuro" : "claro");
  }

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-theme-toggle]");
    if (toggle) { toggleTheme(); }
  });

  document.addEventListener("change", function (event) {
    var option = event.target.closest("[data-theme-option]");
    if (option && event.target.checked) {
      setTheme(option.getAttribute("data-theme-option"));
      return;
    }
    if (event.target.matches && event.target.matches("[data-theme-switch]")) {
      setTheme(event.target.checked ? "claro" : "escuro");
    }
  });

  if (media && media.addEventListener) {
    media.addEventListener("change", function () {
      if (stored() === "sistema") { apply("sistema"); }
    });
  }

  window.Desenrola = window.Desenrola || {};
  window.Desenrola.setTheme = setTheme;
  window.Desenrola.toggleTheme = toggleTheme;
  window.Desenrola.currentTheme = currentTheme;

  apply(stored() || "escuro");
})();
