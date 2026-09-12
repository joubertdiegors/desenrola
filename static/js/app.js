/*
 * Desenrola — app.js
 * Comportamentos minimos da interface. Sem framework, sem animacoes.
 *
 *   - Dropdowns (<details class="dropdown">): fecham ao clicar fora, ao
 *     pressionar Esc e quando outro dropdown abre.
 *   - Dialogos: [data-dialog-open="id"] mostra o backdrop com esse id;
 *     [data-dialog-close] ou Esc fecham.
 */
(function () {
  "use strict";

  /* Dropdowns ------------------------------------------------------------ */

  function closeDropdowns(except) {
    var open = document.querySelectorAll("details.dropdown[open]");
    for (var i = 0; i < open.length; i++) {
      if (open[i] !== except) { open[i].removeAttribute("open"); }
    }
  }

  document.addEventListener("toggle", function (event) {
    var details = event.target;
    if (details.matches && details.matches("details.dropdown") && details.open) {
      closeDropdowns(details);
    }
  }, true);

  document.addEventListener("click", function (event) {
    if (!event.target.closest("details.dropdown")) { closeDropdowns(null); }
  });

  /* Dialogos ------------------------------------------------------------- */

  function openDialog(id) {
    var backdrop = document.getElementById(id);
    if (!backdrop) { return; }
    backdrop.hidden = false;
    var focusable = backdrop.querySelector("[autofocus], button, [href], input, select, textarea");
    if (focusable) { focusable.focus(); }
  }

  function closeDialog(backdrop) {
    if (backdrop) { backdrop.hidden = true; }
  }

  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-dialog-open]");
    if (opener) {
      event.preventDefault();
      openDialog(opener.getAttribute("data-dialog-open"));
      return;
    }
    var closer = event.target.closest("[data-dialog-close]");
    if (closer) {
      event.preventDefault();
      closeDialog(closer.closest(".dialog-backdrop"));
      return;
    }
    if (event.target.classList && event.target.classList.contains("dialog-backdrop")) {
      closeDialog(event.target);
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") { return; }
    closeDropdowns(null);
    var dialogs = document.querySelectorAll(".dialog-backdrop:not([hidden])");
    for (var i = 0; i < dialogs.length; i++) { closeDialog(dialogs[i]); }
  });

  window.Desenrola = window.Desenrola || {};
  window.Desenrola.openDialog = openDialog;
  window.Desenrola.closeDialog = function (id) { closeDialog(document.getElementById(id)); };
})();
