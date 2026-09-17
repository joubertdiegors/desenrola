/*
 * Desenrola — app.js
 * Comportamentos minimos da interface. Sem framework, sem animacoes.
 *
 *   - Dropdowns (<details class="dropdown">): fecham ao clicar fora, ao
 *     pressionar Esc e quando outro dropdown abre.
 *   - Dialogos: [data-dialog-open="id"] mostra o backdrop com esse id;
 *     [data-dialog-close] ou Esc fecham.
 *   - Senha: [data-pw-toggle] alterna mostrar/ocultar o campo ao lado;
 *     [data-pw-confirm] avisa, enquanto se digita, se a confirmacao
 *     bate com a senha.
 *   - Telefone: [data-telefone] formata o numero conforme o pais
 *     escolhido no seletor ao lado.
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
    // Quem le a tela precisa saber o ESTADO, nao so que ha um botao.
    toggle.setAttribute("aria-pressed", show ? "true" : "false");
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

  // --- Campos de data ---------------------------------------------------
  // O input visivel mostra dd/mm/aaaa; digitar 10102026 vira 10/10/2026
  // sozinho. Ao lado, invisivel mas por cima do icone, fica um
  // <input type="date"> de verdade: tocar nele abre o calendario NATIVO
  // do navegador -- inclusive no celular. Antes de enviar, a data vai
  // normalizada para ISO.
  //
  // Nada aqui e seguranca: o servidor revalida e converte de qualquer
  // jeito (apps/letters/forms.py aceita dd/mm/aaaa e ISO). Sem
  // JavaScript, o campo continua sendo um campo de data que se digita.

  function maskDate(value) {
    var digits = value.replace(/\D/g, "").slice(0, 8);
    if (digits.length <= 2) { return digits; }
    if (digits.length <= 4) { return digits.slice(0, 2) + "/" + digits.slice(2); }
    return digits.slice(0, 2) + "/" + digits.slice(2, 4) + "/" + digits.slice(4);
  }

  function toIso(value) {
    var parts = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value.trim());
    if (!parts) { return null; }
    var day = Number(parts[1]);
    var month = Number(parts[2]);
    var year = Number(parts[3]);
    var date = new Date(year, month - 1, day);
    // Recusa data impossivel (31/02 viraria 03/03 sozinho no Date).
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
      return null;
    }
    return parts[3] + "-" + parts[2] + "-" + parts[1];
  }

  function fromIso(value) {
    var parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
    return parts ? parts[3] + "/" + parts[2] + "/" + parts[1] : "";
  }

  document.addEventListener("input", function (event) {
    var input = event.target;
    if (!input.matches || !input.matches("[data-date-input]")) { return; }
    var masked = maskDate(input.value);
    if (masked !== input.value) { input.value = masked; }
  });

  // Abrir o calendario nativo
  // -------------------------
  // Quem recebe o clique e o BOTAO do icone, nao o <input type="date">.
  //
  // O motivo: clicar num input de data NAO abre o seletor no Chrome nem
  // no Edge -- la so o `::-webkit-calendar-picker-indicator` abre, e ele
  // ocupa uma fracao do canto direito. Era por isso que o clique no
  // icone quase sempre nao fazia nada.
  //
  // O <input type="date"> continua existindo, logo abaixo do botao: e
  // nele que o navegador ancora o calendario e e ele que guarda o valor
  // em ISO. Nao pode ser `display:none`.

  function prepararPicker(picker) {
    // O seletor comeca na data que ja estiver digitada, e com a data
    // minima do campo -- o calendario nativo desabilita os dias
    // anteriores sozinho. A regra de verdade continua no servidor.
    var caixa = picker.closest(".date-input");
    var input = caixa && caixa.querySelector("[data-date-input]");
    if (!input) { return; }
    picker.value = toIso(input.value) || "";
    var min = input.getAttribute("data-date-min");
    if (min) { picker.min = min; }
  }

  document.addEventListener("click", function (event) {
    var botao = event.target.closest && event.target.closest(".date-input-open");
    if (!botao) { return; }
    var caixa = botao.closest(".date-input");
    var picker = caixa && caixa.querySelector(".date-input-picker");
    if (!picker) { return; }

    prepararPicker(picker);

    if (typeof picker.showPicker === "function") {
      // Estamos DENTRO do clique, entao a ativacao do usuario que o
      // `showPicker()` exige existe. Ainda assim ele pode recusar (num
      // iframe sem permissao, por exemplo) -- dai cai no caminho de
      // baixo, em vez de estourar.
      try {
        picker.showPicker();
        return;
      } catch (err) { /* segue para o caminho alternativo */ }
    }

    // Sem `showPicker()` (Safari do iOS ate a 15, navegadores antigos):
    // levar o foco ao proprio campo de data e o que abre a roda do
    // sistema. Continua sendo o navegador quem decide se abre.
    try {
      picker.focus();
      picker.click();
    } catch (err) { /* o navegador decide */ }
  });

  // Toque direto no <input type="date">: onde o botao for contornado, o
  // seletor ainda precisa comecar na data certa. `pointerdown` vem ANTES
  // de o navegador abrir o calendario, entao o valor chega a tempo.
  //
  // A guarda `event.target.closest &&` nao e enfeite: `pointerdown`
  // dispara com alvos que nem sempre sao Element, e sem ela uma excecao
  // derrubaria o resto do tratamento.
  document.addEventListener("pointerdown", function (event) {
    var picker = event.target.closest && event.target.closest(".date-input-picker");
    if (!picker) { return; }
    prepararPicker(picker);
  });

  document.addEventListener("change", function (event) {
    var picker = event.target;
    if (!picker.matches || !picker.matches(".date-input-picker")) { return; }
    var input = picker.closest(".date-input").querySelector("[data-date-input]");
    if (!input || !picker.value) { return; }
    input.value = fromIso(picker.value);
    // Escrever o valor por codigo nao dispara `input`: avisamos na mao,
    // senao a duracao e o botao ficariam com o estado antigo.
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });

  // --- Duracao da estadia (etapa "Viagem") ------------------------------
  // Recalcula na hora, enquanto a pessoa digita ou escolhe no calendario.
  //
  // A conta e a MESMA do servidor (apps/letters/rules.py): contagem
  // INCLUSIVA, ou seja, diferenca entre as datas + 1 -- de 10/10/2026 a
  // 24/10/2026 sao 15 dias, como o documento oficial declara. Aqui e so
  // adiantar o numero; quem valida continua sendo o servidor.

  var MS_POR_DIA = 24 * 60 * 60 * 1000;

  function stayDurationDays(isoChegada, isoPartida) {
    if (!isoChegada || !isoPartida) { return null; }
    var chegada = new Date(isoChegada + "T00:00:00");
    var partida = new Date(isoPartida + "T00:00:00");
    if (isNaN(chegada) || isNaN(partida) || partida < chegada) { return null; }
    return Math.round((partida - chegada) / MS_POR_DIA) + 1;
  }

  function refreshDuration(form) {
    var caixa = form.querySelector("[data-duration-box]");
    if (!caixa) { return; }

    var chegada = form.querySelector('[name="stay_arrival"]');
    var partida = form.querySelector('[name="stay_departure"]');
    if (!chegada || !partida) { return; }

    // Campo vazio, data incompleta, data impossivel (31/02) ou partida
    // antes da chegada: `toIso`/`stayDurationDays` devolvem null e a
    // caixa some, em vez de mostrar um numero errado.
    var dias = stayDurationDays(toIso(chegada.value), toIso(partida.value));
    if (dias === null) {
      caixa.hidden = true;
      return;
    }

    var unidade = dias === 1
      ? caixa.getAttribute("data-unit-one")
      : caixa.getAttribute("data-unit-many");
    var valor = caixa.querySelector("[data-duration-value]");
    if (valor) { valor.textContent = dias + " " + unidade; }

    var maximo = Number(caixa.getAttribute("data-max-stay"));
    var passou = !!maximo && dias > maximo;
    // A caixa RESPONDE EM COR: verde dentro da regra dos 90 dias,
    // vermelha fora. As duas classes sao exclusivas -- sem o `false`
    // explicito na outra, voltar as datas para dentro do prazo deixaria
    // a caixa vermelha E verde ao mesmo tempo.
    caixa.classList.toggle("is-invalid", passou);
    caixa.classList.toggle("is-ok", !passou);

    // Nao ha etiqueta "> 90 dias" aqui: a cor da caixa e o aviso abaixo
    // ja dizem a mesma coisa, e o selo compacto repetia o numero que a
    // frase do aviso ja traz por extenso.
    var aviso = form.querySelector("[data-duration-warning]");
    if (aviso) { aviso.hidden = !passou; }

    caixa.hidden = false;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var caixas = document.querySelectorAll("[data-duration-box]");
    for (var i = 0; i < caixas.length; i++) {
      var form = caixas[i].closest("form");
      if (form) { refreshDuration(form); }
    }
  });

  // --- Estado do botao "Proxima etapa" ----------------------------------
  // O botao fica com CARA de desabilitado enquanto faltar campo
  // obrigatorio, mas continua clicavel de proposito: se a pessoa insistir
  // e enviar, o Django valida e devolve as mensagens de erro campo a
  // campo. Um `disabled` de verdade engoliria esse retorno e deixaria o
  // formulario mudo.
  //
  // Isto e so conforto visual. Quem decide continua sendo o servidor --
  // nada aqui impede (nem autoriza) o envio.

  function dateFieldIsValid(input) {
    var iso = toIso(input.value);
    if (!iso) { return false; }
    var min = input.getAttribute("data-date-min");
    return !min || iso >= min;
  }

  function fieldIsFilled(field) {
    if (field.type === "checkbox") { return field.checked; }
    if (field.type === "radio") {
      var grupo = field.form ? field.form.querySelectorAll('[name="' + field.name + '"]') : [];
      for (var i = 0; i < grupo.length; i++) {
        if (grupo[i].checked) { return true; }
      }
      return false;
    }
    if (!field.value || !field.value.trim()) { return false; }
    if (field.hasAttribute("data-date-input")) { return dateFieldIsValid(field); }
    return true;
  }

  function refreshStepButton(form) {
    var botao = document.querySelector('[data-step-submit][form="' + form.id + '"]')
      || form.querySelector("[data-step-submit]");
    if (!botao) { return; }

    var obrigatorios = form.querySelectorAll("[required]");
    var completo = true;
    for (var i = 0; i < obrigatorios.length; i++) {
      var campo = obrigatorios[i];
      if (campo.disabled) { completo = false; break; }
      if (!fieldIsFilled(campo)) { completo = false; break; }
    }

    botao.classList.toggle("is-disabled", !completo);
    botao.setAttribute("aria-disabled", completo ? "false" : "true");
  }

  function refreshAllStepButtons() {
    var forms = document.querySelectorAll("form");
    for (var i = 0; i < forms.length; i++) { refreshStepButton(forms[i]); }
  }

  document.addEventListener("DOMContentLoaded", refreshAllStepButtons);
  document.addEventListener("input", function (event) {
    if (event.target.form) {
      refreshStepButton(event.target.form);
      refreshDuration(event.target.form);
    }
  });
  document.addEventListener("change", function (event) {
    if (event.target.form) {
      refreshStepButton(event.target.form);
      refreshDuration(event.target.form);
    }
  });

  // O campo ja envia dd/mm/aaaa, e o servidor aceita esse formato direto
  // (`input_formats` em apps/letters/forms.py) -- nao converter para ISO
  // aqui de proposito. Convertendo, um erro em OUTRO campo da mesma
  // etapa reexibia este (valido) em "2026-09-13" em vez de
  // "13/09/2026": o widget so reformata um `date` de verdade, e uma
  // string ja vinculada volta sem tocar. Foi o que pareceu "dia e mes
  // invertidos" na validacao manual.

  // Imprimir a carta: usa o PDF REAL da Letter, nunca um substituto.
  // O <a> ja abre o PDF em outra aba sozinho (funciona sem JavaScript);
  // aqui so tentamos poupar um passo, carregando o mesmo arquivo num
  // iframe escondido e chamando a caixa de impressao. Se o navegador nao
  // permitir, nao fazemos nada e o link segue o seu caminho normal.
  document.addEventListener("click", function (event) {
    var trigger = event.target.closest(".js-print-pdf");
    if (!trigger) { return; }
    var url = trigger.getAttribute("data-pdf-url");
    if (!url || !window.HTMLIFrameElement) { return; }

    var frame = document.createElement("iframe");
    frame.hidden = true;
    frame.src = url;
    frame.addEventListener("load", function () {
      try {
        frame.contentWindow.focus();
        frame.contentWindow.print();
      } catch (err) {
        // Sem permissao para imprimir de dentro do iframe: abre a aba.
        window.open(url, "_blank", "noopener");
      }
    });
    document.body.appendChild(frame);
    event.preventDefault();
  });

  // --------------------------------------------------------------------
  // Compartilhar a carta
  // --------------------------------------------------------------------
  //
  // O QUE SE COMPARTILHA E O ARQUIVO, NAO UM LINK
  // O PDF fica atras de login: mandar a URL a alguem de fora nao serve de
  // nada -- a pessoa cairia na tela de entrar. Entao o que sai daqui e
  // sempre o ARQUIVO.
  //
  // TRES CAMINHOS, NESTA ORDEM
  //   1. Web Share com arquivo (`navigator.canShare({files})`): abre a
  //      folha do sistema e a pessoa escolhe WhatsApp, e-mail, o que for.
  //      E o unico caminho que entrega o PDF de verdade.
  //   2. Sem suporte a arquivo: baixa o PDF e o proprio botao avisa
  //      que e para anexar a mao.
  //   3. Sem JavaScript: o proprio <a> ja aponta para a rota de download.
  //
  // Nenhum deles inventa um link publico para um documento privado.

  function baixarPeloLink(url) {
    // Navega para a rota de anexo: e o SERVIDOR que manda baixar
    // (Content-Disposition: attachment), entao isto nao depende do
    // atributo `download`, que varios navegadores ignoram.
    window.location.href = url;
  }

  function pdfComoArquivo(trigger) {
    // Busca o PDF na MESMA origem, com a sessao -- o arquivo e privado.
    return fetch(trigger.getAttribute("data-pdf-url"), { credentials: "same-origin" })
      .then(function (resposta) {
        if (!resposta.ok) { throw new Error("nao foi possivel obter o PDF"); }
        return resposta.blob();
      })
      .then(function (blob) {
        return new File([blob], trigger.getAttribute("data-filename") || "carta.pdf", {
          type: "application/pdf"
        });
      });
  }

  function aceitaCompartilharPdf() {
    // Decide ANTES de qualquer `await`. O motivo e o bloqueador de
    // pop-up: `window.open` so e permitido enquanto o gesto do clique
    // ainda vale, e ele nao sobrevive a uma ida ao servidor. Perguntando
    // aqui, o caminho alternativo do WhatsApp roda ainda dentro do
    // clique.
    //
    // A pergunta e feita com um PDF de mentira (quatro bytes, "%PDF"):
    // `canShare` olha o tipo do arquivo, nao o conteudo -- e assim nao
    // precisamos baixar o de verdade so para saber se da.
    if (!navigator.share || !navigator.canShare || !window.File || !window.fetch) {
      return false;
    }
    try {
      var amostra = new File(
        [new Blob([new Uint8Array([0x25, 0x50, 0x44, 0x46])], { type: "application/pdf" })],
        "carta.pdf",
        { type: "application/pdf" }
      );
      return !!navigator.canShare({ files: [amostra] });
    } catch (erro) {
      return false;
    }
  }

  function avisarQueBaixou(trigger) {
    // O caminho alternativo baixa o arquivo, e um download silencioso
    // depois de clicar em "Compartilhar" nao explica nada. O proprio
    // botao passa a dizer o que aconteceu, e volta ao normal depois.
    var rotulo = trigger.querySelector(".js-rotulo");
    var aviso = trigger.getAttribute("data-aviso");
    if (!rotulo || !aviso) { return; }
    var antes = rotulo.textContent;
    rotulo.textContent = aviso;
    window.setTimeout(function () { rotulo.textContent = antes; }, 6000);
  }

  function compartilhar(trigger, aoFalhar) {
    var titulo = trigger.getAttribute("data-title") || "";
    var texto = trigger.getAttribute("data-text") || "";

    if (!aceitaCompartilharPdf()) {
      aoFalhar();
      return;
    }

    pdfComoArquivo(trigger).then(function (arquivo) {
      navigator.share({ files: [arquivo], title: titulo, text: texto })["catch"](function (erro) {
        // A pessoa fechou a folha de compartilhamento: nao e erro, e
        // desistencia -- nao se faz nada. Qualquer outra falha cai no
        // caminho alternativo.
        if (erro && erro.name === "AbortError") { return; }
        aoFalhar();
      });
    })["catch"](aoFalhar);
  }

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest(".js-share-pdf");
    if (!trigger) { return; }
    event.preventDefault();

    compartilhar(trigger, function () {
      avisarQueBaixou(trigger);
      baixarPeloLink(trigger.getAttribute("data-download-url"));
    });
  });

  // WhatsApp
  // --------
  // Um link `wa.me` so carrega TEXTO -- nao existe forma de anexar um
  // arquivo por URL, em nenhum navegador. Entao:
  //
  //   * onde a folha de compartilhamento aceita arquivo, usamos ela (o
  //     WhatsApp aparece la dentro e recebe o PDF de verdade);
  //   * onde nao aceita, abrimos a conversa com a mensagem pronta E
  //     baixamos o PDF, para a pessoa anexar. E o maximo que o
  //     navegador permite.
  document.addEventListener("click", function (event) {
    var trigger = event.target.closest(".js-share-whatsapp");
    if (!trigger) { return; }
    event.preventDefault();

    compartilhar(trigger, function () {
      var texto = trigger.getAttribute("data-text") || "";
      window.open("https://wa.me/?text=" + encodeURIComponent(texto), "_blank", "noopener");
      avisarQueBaixou(trigger);
      baixarPeloLink(trigger.getAttribute("data-download-url"));
    });
  });

  /* Telefone: mascara por pais ------------------------------------------

     O seletor de pais traz a mascara em `data-mascara` (`#` = digito) e
     um exemplo em `data-exemplo`. Quem monta os dois e o Python
     (`accounts.telefone`): a lista de paises fica em UM lugar, e este
     arquivo nao guarda copia nenhuma dela.

     O QUE ELA NAO FAZ
     -----------------
     Nao recusa nada. Quem valida e o servidor, que aceita o numero com
     ou sem a formatacao -- um pais sem mascara declarada continua
     aceitando o que a pessoa digitar, e e assim de proposito: mascara
     errada atrapalha mais do que mascara nenhuma. */

  function aplicarMascara(digitos, mascara) {
    var saida = "";
    var i = 0;
    for (var j = 0; j < mascara.length && i < digitos.length; j++) {
      if (mascara[j] === "#") {
        saida += digitos[i];
        i++;
      } else {
        saida += mascara[j];
      }
    }
    // O que passar do tamanho da mascara continua entrando: numero de
    // ramal, ou um pais cujo formato mudou. Cortar seria apagar o que a
    // pessoa digitou.
    return saida + digitos.slice(i);
  }

  function paisEscolhido(campo) {
    var seletor = campo.querySelector("select");
    if (!seletor) { return null; }
    return seletor.options[seletor.selectedIndex] || null;
  }

  function formatarTelefone(campo) {
    var entrada = campo.querySelector("input");
    var opcao = paisEscolhido(campo);
    if (!entrada || !opcao) { return; }

    var exemplo = opcao.getAttribute("data-exemplo") || "";
    entrada.setAttribute("placeholder", exemplo);

    var mascara = opcao.getAttribute("data-mascara") || "";
    if (!mascara || !entrada.value) { return; }

    var digitos = entrada.value.replace(/\D/g, "");
    if (!digitos) { return; }
    entrada.value = aplicarMascara(digitos, mascara);
  }

  document.addEventListener("input", function (event) {
    var campo = event.target.closest("[data-telefone]");
    if (campo && event.target.tagName === "INPUT") { formatarTelefone(campo); }
  });

  document.addEventListener("change", function (event) {
    var campo = event.target.closest("[data-telefone]");
    if (campo && event.target.tagName === "SELECT") { formatarTelefone(campo); }
  });

  // No carregamento: o exemplo do pais ja escolhido entra no campo, e o
  // que veio gravado ganha a formatacao daquele pais.
  document.addEventListener("DOMContentLoaded", function () {
    var campos = document.querySelectorAll("[data-telefone]");
    for (var i = 0; i < campos.length; i++) { formatarTelefone(campos[i]); }
  });


  /* Senha: a confirmacao responde enquanto se digita --------------------

     `[data-pw-confirm="id-do-campo-original"]` compara os dois campos e
     escreve o resultado num `[data-pw-confirm-aviso]` proximo.

     ISTO NAO SUBSTITUI A VALIDACAO
     ------------------------------
     Quem recusa senhas diferentes continua sendo o servidor
     (`SignupForm`). Isto e so o aviso que chega ANTES de enviar, para
     ninguem descobrir o engano depois de a pagina recarregar.

     `aria-live="polite"` faz o leitor de tela anunciar a mudanca sem
     interromper quem esta digitando. */

  function avisarDaConfirmacao(campo) {
    var original = document.getElementById(campo.getAttribute("data-pw-confirm"));
    var aviso = document.querySelector(
      "[data-pw-confirm-aviso='" + campo.getAttribute("data-pw-confirm") + "']"
    );
    if (!original || !aviso) { return; }

    if (!campo.value) {
      aviso.textContent = "";
      aviso.className = "field-hint";
      campo.removeAttribute("aria-invalid");
      return;
    }

    var igual = campo.value === original.value;
    aviso.textContent = igual
      ? aviso.getAttribute("data-igual")
      : aviso.getAttribute("data-diferente");
    aviso.className = igual ? "field-ok" : "field-error";
    if (igual) {
      campo.removeAttribute("aria-invalid");
    } else {
      campo.setAttribute("aria-invalid", "true");
    }
  }

  document.addEventListener("input", function (event) {
    var campo = event.target.closest("[data-pw-confirm]");
    if (campo) { avisarDaConfirmacao(campo); return; }

    // Digitar na senha ORIGINAL tambem tem de atualizar o aviso: quem
    // corrige a primeira depois de confirmar a segunda veria um aviso
    // velho ate tocar na confirmacao de novo.
    if (event.target.id) {
      var confirmacao = document.querySelector(
        "[data-pw-confirm='" + event.target.id + "']"
      );
      if (confirmacao && confirmacao.value) { avisarDaConfirmacao(confirmacao); }
    }
  });

  window.Desenrola = window.Desenrola || {};
  window.Desenrola.openDialog = openDialog;
  window.Desenrola.closeDialog = function (id) { closeDialog(document.getElementById(id)); };
})();
