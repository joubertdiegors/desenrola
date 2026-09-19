/*
 * Editor de conteudo rico -- o do rodape e o dos documentos legais.
 *
 * O MODO "DOCUMENTO"
 * ------------------
 * Nos documentos legais o parcial troca a caixa de icones pela de
 * IMAGENS da biblioteca (`data-editor-caixa-imagens`). Cada botao traz
 * o endereco em `data-imagem-src`, desenhado pelo servidor; o `<img>` e
 * montado pelo DOM (`setAttribute`), como o `<a>` do link -- e passa,
 * como tudo, pelo sanitizador do servidor.
 *
 * O QUE ELE E
 * -----------
 * Um `contenteditable` com uma barra de ferramentas por cima e um
 * `<textarea>` escondido por baixo. Cada mudanca na area editavel e
 * copiada para o `<textarea>` -- e' ELE que vai no formulario, e' ele que
 * a previa ao lado le (`previa-do-conteudo.js` ouve o `input` do
 * formulario e redesenha com o mesmo codigo do salvamento).
 *
 * O NAVEGADOR EDITA; O SERVIDOR DECIDE
 * -------------------------------------
 * A barra usa `document.execCommand`: negrito, listas, alinhamento,
 * link. O HTML que sai daqui NAO e' confiavel -- quem o reduz a lista
 * fechada e' `content.rodape.sanitizar`, no servidor, antes de gravar e
 * de novo antes de desenhar. Nada aqui e' seguranca.
 *
 * PROGRESSIVO
 * -----------
 * Sem este script o `<textarea>` fica visivel e o HTML se edita a mao.
 * A pagina continua salvando; so a barra deixa de existir.
 */
(function () {
  "use strict";

  var ICONES = [
    ["Instagram", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="3.5" y="3.5" width="17" height="17" rx="5"></rect><circle cx="12" cy="12" r="4"></circle><circle cx="17" cy="7" r="1.1" fill="currentColor" stroke="none"></circle></svg>'],
    ["Facebook", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M14.5 8.5H17V5h-2.5A3.5 3.5 0 0 0 11 8.5V11H8.5v3.5H11V21h3.5v-6.5H17V11h-2.5V9.2c0-.4.3-.7.7-.7z"></path></svg>'],
    ["WhatsApp", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20l1.3-3.6A8 8 0 1 1 12 20a8 8 0 0 1-4-1.1z"></path><path d="M9 9.5c0 3 2.5 5.5 5.5 5.5l.8-1.6-2-.8-.9 1a5.6 5.6 0 0 1-2-2l1-.9-.8-2z"></path></svg>'],
    ["E-mail", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5.5" width="18" height="13" rx="2.5"></rect><path d="M4 7l8 6 8-6"></path></svg>'],
    ["Telefone", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h3.5l1.5 4-2 1.5a10 10 0 0 0 4.5 4.5L14 12l4 1.5V17a2 2 0 0 1-2.2 2A13 13 0 0 1 3 6.2A2 2 0 0 1 5 4z"></path></svg>'],
    ["Endereço", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11z"></path><circle cx="12" cy="10" r="2.5"></circle></svg>'],
    ["Horário", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"></circle><path d="M12 7.5V12l3 2"></path></svg>'],
    ["Documento", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"></path><path d="M14 3v5h5"></path></svg>'],
    ["Globo", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"></circle><path d="M3.5 12h17M12 3.5c2.5 2.5 2.5 14 0 17M12 3.5c-2.5 2.5-2.5 14 0 17"></path></svg>'],
    ["Coração", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20s-7-4.4-7-9.2A3.8 3.8 0 0 1 12 8.4 3.8 3.8 0 0 1 19 10.8C19 15.6 12 20 12 20z"></path></svg>'],
    ["Verificado", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"></circle><path d="M8.5 12.5l2.5 2.5 4.5-5"></path></svg>'],
    ["Seta", '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h15M13 6l6 6-6 6"></path></svg>'],
  ];

  function montar(raiz) {
    // O campo do FORMULARIO -- nao o primeiro `<textarea>` que aparecer:
    // a caixa de HTML tambem e' um, e vem antes na marcacao.
    var campo = raiz.querySelector("textarea[data-editor-rico-campo]");
    var area = raiz.querySelector("[data-editor-area]");
    var fonte = raiz.querySelector("[data-editor-fonte]");
    var caixaFonte = raiz.querySelector("[data-editor-caixa-fonte]");
    var caixaLink = raiz.querySelector("[data-editor-caixa-link]");
    var caixaIcones = raiz.querySelector("[data-editor-caixa-icones]");
    var caixaImagens = raiz.querySelector("[data-editor-caixa-imagens]");
    var paletaIcones = raiz.querySelector("[data-editor-icones]");
    var contador = raiz.querySelector("[data-editor-contador]");
    if (!campo || !area) { return; }

    raiz.classList.add("is-ligado");
    area.innerHTML = campo.value;
    try { document.execCommand("defaultParagraphSeparator", false, "p"); } catch (e) { /* motor antigo */ }

    var selecao = null;

    function guardarSelecao() {
      var sel = window.getSelection();
      if (sel && sel.rangeCount && area.contains(sel.anchorNode)) {
        selecao = sel.getRangeAt(0).cloneRange();
      }
    }

    function devolverSelecao() {
      area.focus();
      if (selecao) {
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(selecao);
      }
    }

    function sincronizar() {
      campo.value = area.innerHTML;
      if (contador) {
        var texto = (area.innerText || "").trim();
        var palavras = texto ? texto.split(/\s+/).length : 0;
        contador.textContent = palavras + " " + (contador.getAttribute("data-palavras") || "palavras");
      }
      // E' este evento que a previa ao lado escuta.
      campo.dispatchEvent(new Event("input", { bubbles: true }));
    }

    function executar(comando, valor) {
      devolverSelecao();
      try { document.execCommand(comando, false, valor); } catch (e) { /* comando fora do motor */ }
      guardarSelecao();
      sincronizar();
    }

    function inserirHtml(html) {
      executar("insertHTML", html);
    }

    // A barra: cada botao declara o comando em `data-comando` e, quando
    // houver, o valor em `data-valor`.
    raiz.addEventListener("mousedown", function (evento) {
      if (evento.target.closest("[data-comando], [data-atalho], [data-icone], [data-editor-caixa-icones], [data-editor-caixa-imagens]")) {
        evento.preventDefault();
        guardarSelecao();
      }
    });

    raiz.addEventListener("click", function (evento) {
      var botao = evento.target.closest("[data-comando]");
      if (!botao) { return; }
      var comando = botao.getAttribute("data-comando");
      var valor = botao.getAttribute("data-valor");
      if (comando === "abrir-link") { abrirLink(); return; }
      if (comando === "fechar-link") { caixaLink.hidden = true; return; }
      if (comando === "aplicar-link") { aplicarLink(); return; }
      if (comando === "icones") { alternarCaixa(caixaIcones); return; }
      if (comando === "imagens") { alternarCaixa(caixaImagens); return; }
      if (comando === "fonte") { alternarFonte(); return; }
      if (comando === "aplicar-fonte") { area.innerHTML = fonte.value; sincronizar(); return; }
      if (comando === "espaco") { inserirHtml('<p style="height:18px">&nbsp;</p>'); return; }
      if (comando === "colunas") {
        inserirHtml('<div style="display:flex;flex-wrap:wrap;gap:24px"><div style="flex:1;min-width:150px"><h4>Coluna</h4><p>Texto da coluna.</p></div><div style="flex:1;min-width:150px"><h4>Coluna</h4><p>Texto da coluna.</p></div><div style="flex:1;min-width:150px"><h4>Coluna</h4><p>Texto da coluna.</p></div></div><p><br></p>');
        return;
      }
      executar(comando, valor);
    });

    raiz.addEventListener("change", function (evento) {
      var seletor = evento.target.closest("select[data-comando]");
      if (!seletor) { return; }
      var comando = seletor.getAttribute("data-comando");
      if (comando === "entrelinha") {
        area.style.lineHeight = seletor.value;
        return;
      }
      executar(comando, seletor.value);
      seletor.selectedIndex = 0;
    });

    // Uma caixa por vez: abrir uma fecha as outras.
    function alternarCaixa(caixa) {
      if (!caixa) { return; }
      var abrir = caixa.hidden;
      [caixaLink, caixaIcones, caixaImagens].forEach(function (outra) {
        if (outra) { outra.hidden = true; }
      });
      caixa.hidden = !abrir;
    }

    // Imagens da biblioteca: o `<img>` sai do DOM, com o endereco que o
    // servidor desenhou no botao.
    raiz.addEventListener("click", function (evento) {
      var botao = evento.target.closest("[data-imagem-src]");
      if (!botao) { return; }
      var img = document.createElement("img");
      img.setAttribute("src", botao.getAttribute("data-imagem-src"));
      img.setAttribute("alt", botao.getAttribute("data-imagem-alt") || "");
      inserirHtml(img.outerHTML);
      if (caixaImagens) { caixaImagens.hidden = true; }
    });

    // Atalhos: o texto do proprio botao e' o que entra.
    raiz.addEventListener("click", function (evento) {
      var atalho = evento.target.closest("[data-atalho]");
      if (!atalho) { return; }
      inserirHtml(atalho.getAttribute("data-atalho"));
    });

    // Icones inline: entram como SVG e herdam a cor do texto.
    if (paletaIcones) {
      ICONES.forEach(function (icone) {
        var botao = document.createElement("button");
        botao.type = "button";
        botao.className = "editor-rico-icone";
        botao.title = icone[0];
        botao.setAttribute("data-icone", "1");
        botao.innerHTML = icone[1];
        botao.addEventListener("click", function () { inserirHtml(icone[1] + "&nbsp;"); });
        paletaIcones.appendChild(botao);
      });
    }

    function abrirLink() {
      guardarSelecao();
      var sel = window.getSelection();
      var texto = sel ? String(sel) : "";
      if (caixaIcones) { caixaIcones.hidden = true; }
      if (caixaImagens) { caixaImagens.hidden = true; }
      caixaLink.hidden = false;
      caixaLink.querySelector("[data-link-texto]").value = texto;
      caixaLink.querySelector("[data-link-endereco]").focus();
    }

    function aplicarLink() {
      var endereco = (caixaLink.querySelector("[data-link-endereco]").value || "").trim();
      if (!endereco) { caixaLink.querySelector("[data-link-endereco]").focus(); return; }
      var rotulo = (caixaLink.querySelector("[data-link-texto]").value || "").trim() || endereco;
      var novaAba = caixaLink.querySelector("[data-link-nova-aba]").checked;
      var a = document.createElement("a");
      a.setAttribute("href", endereco);
      if (novaAba) { a.setAttribute("target", "_blank"); a.setAttribute("rel", "noopener"); }
      a.textContent = rotulo;
      inserirHtml(a.outerHTML + "&nbsp;");
      caixaLink.hidden = true;
      caixaLink.querySelector("[data-link-endereco]").value = "";
    }

    function alternarFonte() {
      if (caixaFonte.hidden) {
        fonte.value = area.innerHTML.replace(/></g, ">\n<");
        caixaFonte.hidden = false;
      } else {
        caixaFonte.hidden = true;
      }
    }

    area.addEventListener("input", function () { guardarSelecao(); sincronizar(); });
    area.addEventListener("blur", function () { guardarSelecao(); sincronizar(); });
    area.addEventListener("keyup", guardarSelecao);
    area.addEventListener("mouseup", guardarSelecao);

    sincronizar();
  }

  document.querySelectorAll("[data-editor-rico]").forEach(montar);
})();
