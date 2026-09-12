/*
 * Desenrola — theme.js
 * Alternancia claro/escuro, consistente em todas as telas.
 *
 * Replica o mecanismo do arquivo de identidade visual: a preferencia fica
 * em localStorage na chave "desenrola.theme" com os valores "escuro"
 * (padrao) e "claro"; o tema claro e a classe `light` no <html>.
 *
 * O template base aplica a classe antes do primeiro paint (script inline no
 * <head>); este arquivo cuida da interacao:
 *   - [data-theme-toggle]          alterna entre os dois temas;
 *   - [data-theme-option="claro"]  escolhe um tema explicitamente (perfil).
 */
(function () {
  "use strict";

  var KEY = "desenrola.theme";
  var root = document.documentElement;

  function current() {
    return root.classList.contains("light") ? "claro" : "escuro";
  }

  function apply(theme) {
    var light = theme === "claro";
    root.classList.toggle("light", light);

    var toggles = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].setAttribute("aria-pressed", light ? "true" : "false");
    }

    var options = document.querySelectorAll("[data-theme-option]");
    for (var j = 0; j < options.length; j++) {
      var option = options[j];
      var selected = option.getAttribute("data-theme-option") === theme;
      option.setAttribute("aria-checked", selected ? "true" : "false");
      var input = option.querySelector("input");
      if (input) { input.checked = selected; }
    }
  }

  function setTheme(theme) {
    apply(theme);
    try { localStorage.setItem(KEY, theme); } catch (e) { /* armazenamento indisponivel */ }
  }

  function toggleTheme() {
    setTheme(current() === "claro" ? "escuro" : "claro");
  }

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-theme-toggle]");
    if (toggle) { toggleTheme(); return; }

    var option = event.target.closest("[data-theme-option]");
    if (option) { setTheme(option.getAttribute("data-theme-option")); }
  });

  document.addEventListener("change", function (event) {
    var option = event.target.closest("[data-theme-option]");
    if (option && event.target.checked) { setTheme(option.getAttribute("data-theme-option")); }
  });

  window.Desenrola = window.Desenrola || {};
  window.Desenrola.setTheme = setTheme;
  window.Desenrola.toggleTheme = toggleTheme;
  window.Desenrola.currentTheme = current;

  apply(current());
})();
