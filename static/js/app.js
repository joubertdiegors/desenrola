/*
 * Desenrola — app.js
 * Comportamentos minimos da interface. Sem framework, sem animacoes.
 *
 *   - Dropdowns (<details class="dropdown">): fecham ao clicar fora, ao
 *     pressionar Esc e quando outro dropdown abre.
 *   - Dialogos: [data-dialog-open="id"] mostra o backdrop com esse id;
 *     [data-dialog-close] ou Esc fecham.
 *   - Senha: [data-pw-toggle] alterna mostrar/ocultar o campo ao lado.
 *   - Avisos legais (etapa 4 do assistente): [data-gate] desabilita o
 *     botao ate que todos os campos com [data-gate-check] dentro dele
 *     estejam marcados.
 *   - Fase de apresentacao (mock): [data-mock-submit] em um <form> navega
 *     para data-next em vez de enviar; [data-mock-loading] em um botao
 *     mostra um rotulo de carregamento e depois navega para data-next.
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

  /* Mostrar/ocultar senha ------------------------------------------------ */

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-pw-toggle]");
    if (!toggle) { return; }
    var wrap = toggle.closest(".pw-wrap");
    var input = wrap && wrap.querySelector("input");
    var icon = toggle.querySelector(".ph");
    if (!input) { return; }
    var show = input.type === "password";
    input.type = show ? "text" : "password";
    if (icon) {
      icon.classList.toggle("ph-eye", !show);
      icon.classList.toggle("ph-eye-slash", show);
    }
  });

  /* Interruptor (components/switch.html) ---------------------------------- */

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest(".toggle");
    if (!toggle) { return; }
    var on = !toggle.classList.contains("is-on");
    toggle.classList.toggle("is-on", on);
    toggle.setAttribute("aria-checked", String(on));
    var input = toggle.querySelector("input");
    if (input) { input.checked = on; }
  });

  /* Avisos legais: trava o botao ate marcar todas as caixas --------------- */

  function syncGate(gate) {
    var checks = gate.querySelectorAll("[data-gate-check]");
    var button = document.querySelector('[data-gate-submit="' + gate.id + '"]');
    if (!button) { return; }
    var allChecked = true;
    for (var i = 0; i < checks.length; i++) {
      if (!checks[i].checked) { allChecked = false; break; }
    }
    button.disabled = !allChecked;
    button.setAttribute("aria-disabled", String(!allChecked));
  }

  document.querySelectorAll("[data-gate]").forEach(function (gate) { syncGate(gate); });

  document.addEventListener("change", function (event) {
    if (!event.target.hasAttribute || !event.target.hasAttribute("data-gate-check")) { return; }
    var gate = event.target.closest("[data-gate]");
    if (gate) { syncGate(gate); }
  });

  /* Fase de apresentacao: formularios e acoes simuladas ------------------- */

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form.hasAttribute || !form.hasAttribute("data-mock-submit")) { return; }
    event.preventDefault();
    var next = form.getAttribute("data-next");
    if (next) { window.location.href = next; }
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-mock-loading]");
    if (!button || button.disabled) { return; }
    event.preventDefault();
    var next = button.getAttribute("data-next");
    var label = button.getAttribute("data-loading-text");
    button.disabled = true;
    if (label) { button.textContent = label; }
    window.setTimeout(function () {
      if (next) { window.location.href = next; }
    }, 900);
  });

  window.Desenrola = window.Desenrola || {};
  window.Desenrola.openDialog = openDialog;
  window.Desenrola.closeDialog = function (id) { closeDialog(document.getElementById(id)); };
})();
