/*
 * Editor de Documentos legais por blocos (Rodada 22).
 *
 * O QUE ESTE ARQUIVO É
 * ---------------------
 * O quadro inteiro (`.eb-canvas`), a lista da estrutura, o menu
 * "+ Bloco", a barra de formatação (compartilhada -- opera sobre o
 * bloco de texto que estiver com o foco) e o painel da imagem
 * selecionada. Uma ferramenta de tela inteira, como o editor de
 * modelos (`template-editor/editor.js`): sem ela, a tela não faz nada
 * -- por isso o `<noscript>` no template avisa.
 *
 * O ESTADO
 * --------
 * Um array só, `estado.blocos`, na MESMA forma que
 * `apps.content.blocos` grava e lê (`{id, type, html?, ...}`). A
 * ORDEM do array É a ordem dos blocos -- arrastar na lista da
 * estrutura só reordena este array e redesenha. No envio do
 * formulário, o array inteiro vira o valor de um campo oculto
 * (`data-campo-blocos`): o servidor sanitiza tudo de novo
 * (`blocos.sanitizar_blocos`), então o que sai daqui não precisa ser
 * perfeito -- precisa apenas representar fielmente o que a pessoa
 * montou.
 *
 * SEGURANÇA
 * ---------
 * Nada aqui decide o que é seguro. `execCommand` e a digitação livre
 * produzem HTML de qualquer jeito; é o SERVIDOR
 * (`rodape.sanitizar_documento`, por bloco) que reduz tudo à lista
 * fechada antes de gravar e de novo antes de desenhar. Este script só
 * precisa não perder o que a pessoa escreveu.
 */
(function () {
  "use strict";

  var raiz = document.querySelector("[data-editor-blocos]");
  if (!raiz) { return; }

  function json(id, padrao) {
    var no = document.getElementById(id);
    if (!no) { return padrao; }
    try { return JSON.parse(no.textContent); } catch (erro) { return padrao; }
  }

  var catalogo = json("eb-catalogo", []);
  var imagensDaBiblioteca = json("eb-imagens", []);

  // Mesma lista de `apps.content.blocos.TIPOS_CONVERSIVEIS`: os únicos
  // tipos que só guardam `html` e por isso podem trocar de tipo sem
  // perder o texto.
  var TIPOS_CONVERSIVEIS = ["paragraph", "heading", "quote"];

  var estado = {
    blocos: json("eb-dados-iniciais", []),
    selecionadoId: null,
    sujo: false,
  };

  // --- Referências ---------------------------------------------------------

  var canvas = raiz.querySelector("[data-canvas]");
  var listaEstrutura = raiz.querySelector("[data-lista-estrutura]");
  var campoBlocos = raiz.querySelector("[data-campo-blocos]");
  var campoBlocosPrevia = raiz.querySelector("[data-campo-blocos-previa]");
  var campoViewportPrevia = raiz.querySelector("[data-campo-viewport-previa]");
  var formPrevia = raiz.querySelector("[data-form-previa]");
  var estadoTexto = raiz.querySelector("[data-estado]");
  var barra = raiz.querySelector("[data-barra]");
  var caixaLink = raiz.querySelector("[data-caixa-link]");
  var seletorImagem = raiz.querySelector("[data-seletor-imagem]");
  var gradeImagens = raiz.querySelector("[data-grade-imagens]");
  var menuBloco = raiz.querySelector("[data-menu-bloco]");
  var itensMenuBloco = raiz.querySelector("[data-itens-menu-bloco]");
  var buscaBloco = raiz.querySelector("[data-busca-bloco]");

  var ICONES_POR_TIPO = {
    paragraph: "ph-text-align-left", heading: "ph-text-h", list: "ph-list-bullets",
    quote: "ph-quotes", image: "ph-image", gallery: "ph-images-square",
    highlight: "ph-shield-check", table: "ph-table", button: "ph-cursor-click",
    separator: "ph-minus", html: "ph-code",
  };
  var ROTULO_POR_TIPO = {};
  catalogo.forEach(function (grupo) {
    grupo.itens.forEach(function (item) { ROTULO_POR_TIPO[item.tipo] = item.rotulo; });
  });

  function idCurto() {
    return "b" + Math.random().toString(36).slice(2, 10);
  }

  // --- Um bloco em branco, do tipo pedido -----------------------------------
  // O MESMO formato de `apps.content.blocos.bloco_novo` -- se um campo daqui
  // divergir do que o servidor espera, o pior caso é o servidor descartar o
  // bloco na sanitização (nunca um erro de servidor).

  function blocoNovo(tipo) {
    var base = { id: idCurto(), type: tipo, mobile: { visible: true } };
    if (["paragraph", "heading", "quote", "list", "highlight", "button", "html"].indexOf(tipo) !== -1) {
      base.html = "";
    }
    if (tipo === "button") { base.href = ""; }
    if (tipo === "image") { base.asset_id = null; base.alt = ""; base.desktop = { anchor: "none", width: 36 }; }
    if (tipo === "gallery") { base.asset_ids = []; }
    if (tipo === "table") { base.cabecalho = true; base.linhas = [["", ""], ["", ""]]; }
    return base;
  }

  function porId(id) {
    for (var i = 0; i < estado.blocos.length; i++) {
      if (estado.blocos[i].id === id) { return estado.blocos[i]; }
    }
    return null;
  }

  function marcarSujo() {
    estado.sujo = true;
    if (estadoTexto) { estadoTexto.textContent = "Alterações não salvas"; }
  }

  function marcarLimpo() {
    estado.sujo = false;
    if (estadoTexto) { estadoTexto.textContent = "Tudo salvo"; }
  }

  // --- Desenho de cada bloco -------------------------------------------------

  function elemento(tag, classe, html) {
    var el = document.createElement(tag);
    if (classe) { el.className = classe; }
    if (html !== undefined) { el.innerHTML = html; }
    return el;
  }

  function areaDeTexto(bloco, tagInterna, placeholder) {
    var area = document.createElement(tagInterna === "ul" ? "div" : tagInterna);
    if (tagInterna === "ul") {
      // "list" grava a marcação da lista inteira em `html`; a área
      // editável é um <div> que já contém o <ul>/<ol>.
      area.innerHTML = bloco.html || "<ul><li></li></ul>";
    } else {
      area.innerHTML = bloco.html || "";
    }
    area.setAttribute("contenteditable", "true");
    area.setAttribute("data-campo-html", "1");
    if (placeholder) { area.setAttribute("data-placeholder", placeholder); }
    area.addEventListener("input", function () {
      bloco.html = tagInterna === "ul" ? area.innerHTML : area.innerHTML;
      marcarSujo();
      atualizarItemDaEstrutura(bloco);
    });
    area.addEventListener("focus", function () { focoAtual = area; });
    return area;
  }

  var RENDERIZADORES = {
    paragraph: function (bloco) {
      return areaDeTexto(bloco, "p", "Escreva um parágrafo…");
    },
    heading: function (bloco) {
      return areaDeTexto(bloco, "h2", "Título da seção…");
    },
    quote: function (bloco) {
      return areaDeTexto(bloco, "blockquote", "Uma citação…");
    },
    list: function (bloco) {
      return areaDeTexto(bloco, "ul", "");
    },
    highlight: function (bloco) {
      var caixa = elemento("div", "legal-destaque");
      caixa.appendChild(elemento("span", "legal-destaque-icone"));
      var texto = areaDeTexto(bloco, "span", "Texto do destaque…");
      caixa.appendChild(texto);
      return caixa;
    },
    button: function (bloco) {
      var caixa = elemento("div", "eb-bloco-botao");
      var rotulo = areaDeTexto(bloco, "span", "Texto do botão…");
      rotulo.classList.add("legal-botao-texto");
      caixa.appendChild(rotulo);
      var endereco = document.createElement("input");
      endereco.type = "text";
      endereco.placeholder = "https://…, /pt/… ou mailto:…";
      endereco.value = bloco.href || "";
      endereco.addEventListener("input", function () { bloco.href = endereco.value; marcarSujo(); });
      caixa.appendChild(endereco);
      return caixa;
    },
    separator: function () {
      return elemento("div", "eb-bloco-separador", "<hr>");
    },
    html: function (bloco) {
      var caixa = elemento("div", "eb-bloco-html");
      var campo = document.createElement("textarea");
      campo.value = bloco.html || "";
      campo.placeholder = "HTML do bloco — sanitizado ao salvar.";
      campo.addEventListener("input", function () { bloco.html = campo.value; marcarSujo(); });
      caixa.appendChild(campo);
      return caixa;
    },
    image: function (bloco) {
      var caixa = elemento("div", "eb-bloco-imagem");
      preencherImagem(caixa, bloco);
      return caixa;
    },
    gallery: function (bloco) {
      var caixa = elemento("div", "eb-bloco-galeria-caixa");
      preencherGaleria(caixa, bloco);
      return caixa;
    },
    table: function (bloco) {
      var caixa = elemento("div", "eb-bloco-tabela");
      preencherTabela(caixa, bloco);
      return caixa;
    },
  };

  function preencherImagem(caixa, bloco) {
    caixa.innerHTML = "";
    var asset = imagensDaBiblioteca.filter(function (a) { return a.id === bloco.asset_id; })[0];
    if (!asset) {
      var vazio = elemento(
        "div", "eb-bloco-imagem-vazio",
        '<i class="ph ph-image" aria-hidden="true"></i><span>Escolher imagem da biblioteca</span>'
      );
      vazio.addEventListener("click", function () { abrirSeletorDeImagem(bloco, caixa); });
      caixa.appendChild(vazio);
      return;
    }
    var img = document.createElement("img");
    img.src = asset.url;
    img.alt = bloco.alt || "";
    if (bloco.desktop && bloco.desktop.anchor !== "none") {
      img.style.float = bloco.desktop.anchor;
      img.style.width = (bloco.desktop.width || 36) + "%";
    }
    img.addEventListener("click", function () { abrirSeletorDeImagem(bloco, caixa); });
    img.title = "Clique para trocar a imagem";
    caixa.appendChild(img);
  }

  function preencherGaleria(caixa, bloco) {
    caixa.innerHTML = "";
    if (!bloco.asset_ids || !bloco.asset_ids.length) {
      var vazio = elemento(
        "div", "eb-bloco-galeria-vazia",
        '<i class="ph ph-images-square" aria-hidden="true"></i><span>Escolher imagens da galeria</span>'
      );
      vazio.addEventListener("click", function () { abrirSeletorDeGaleria(bloco, caixa); });
      caixa.appendChild(vazio);
      return;
    }
    var grade = elemento("div", "legal-galeria");
    bloco.asset_ids.forEach(function (id) {
      var asset = imagensDaBiblioteca.filter(function (a) { return a.id === id; })[0];
      if (!asset) { return; }
      var span = document.createElement("span");
      var img = document.createElement("img");
      img.src = asset.url;
      img.alt = "";
      span.appendChild(img);
      grade.appendChild(span);
    });
    grade.title = "Clique para escolher outras imagens";
    grade.addEventListener("click", function () { abrirSeletorDeGaleria(bloco, caixa); });
    caixa.appendChild(grade);
  }

  function preencherTabela(caixa, bloco) {
    caixa.innerHTML = "";
    var tabela = document.createElement("table");
    (bloco.linhas || []).forEach(function (linha, indiceLinha) {
      var tr = document.createElement("tr");
      linha.forEach(function (valor, indiceColuna) {
        var celulaTag = bloco.cabecalho && indiceLinha === 0 ? "th" : "td";
        var celula = document.createElement(celulaTag);
        celula.contentEditable = "true";
        celula.textContent = valor;
        celula.addEventListener("input", function () {
          bloco.linhas[indiceLinha][indiceColuna] = celula.textContent;
          marcarSujo();
        });
        tr.appendChild(celula);
      });
      tabela.appendChild(tr);
    });
    caixa.appendChild(tabela);

    var acoes = elemento("div", "eb-bloco-tabela-acoes");
    var addLinha = elemento("button", "btn btn-ghost btn-sm", "+ Linha");
    addLinha.type = "button";
    addLinha.addEventListener("click", function () {
      var colunas = (bloco.linhas[0] || [""]).length;
      var nova = [];
      for (var i = 0; i < colunas; i++) { nova.push(""); }
      bloco.linhas.push(nova);
      marcarSujo();
      preencherTabela(caixa, bloco);
    });
    var addColuna = elemento("button", "btn btn-ghost btn-sm", "+ Coluna");
    addColuna.type = "button";
    addColuna.addEventListener("click", function () {
      bloco.linhas.forEach(function (linha) { linha.push(""); });
      marcarSujo();
      preencherTabela(caixa, bloco);
    });
    acoes.appendChild(addLinha);
    acoes.appendChild(addColuna);

    if (bloco.linhas.length > 1) {
      var remLinha = elemento("button", "btn btn-ghost btn-sm", "− Linha");
      remLinha.type = "button";
      remLinha.addEventListener("click", function () {
        bloco.linhas.pop();
        marcarSujo();
        preencherTabela(caixa, bloco);
      });
      acoes.appendChild(remLinha);
    }
    if ((bloco.linhas[0] || []).length > 1) {
      var remColuna = elemento("button", "btn btn-ghost btn-sm", "− Coluna");
      remColuna.type = "button";
      remColuna.addEventListener("click", function () {
        bloco.linhas.forEach(function (linha) { linha.pop(); });
        marcarSujo();
        preencherTabela(caixa, bloco);
      });
      acoes.appendChild(remColuna);
    }
    caixa.appendChild(acoes);
  }

  // --- O quadro do bloco (moldura, faixa de ações, painel de imagem) --------

  function iconeAcao(caminhoSvg) {
    return (
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      caminhoSvg + "</svg>"
    );
  }

  var SVG_OLHO = iconeAcao('<path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.6"/>');
  var SVG_OLHO_FECHADO = iconeAcao('<path d="M3.5 3.5 20.5 20.5"/><path d="M2.5 12S6 6.5 12 6.5c1.4 0 2.7.3 3.8.8"/><path d="M19 9.4c1.6 1.4 2.5 2.6 2.5 2.6S18 17.5 12 17.5c-1.6 0-3-.4-4.2-1"/>');
  var SVG_LIXEIRA = iconeAcao('<path d="M4 7h16"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/><path d="M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"/>');

  function montarFaixaDeAcoes(bloco, blocoEl) {
    var faixa = elemento("div", "eb-bloco-faixa");

    var mobile = document.createElement("button");
    mobile.type = "button";
    mobile.title = "Visível no mobile";
    mobile.setAttribute("data-mobile", "1");
    faixa.appendChild(mobile);

    var remover = document.createElement("button");
    remover.type = "button";
    remover.title = "Excluir bloco";
    remover.innerHTML = SVG_LIXEIRA;
    remover.setAttribute("data-remover", "1");
    remover.addEventListener("click", function (evento) {
      evento.stopPropagation();
      excluirBloco(bloco.id);
    });
    faixa.appendChild(remover);

    function atualizarOlho() {
      var visivel = !bloco.mobile || bloco.mobile.visible !== false;
      mobile.innerHTML = visivel ? SVG_OLHO : SVG_OLHO_FECHADO;
      mobile.classList.toggle("is-ativo", !visivel);
    }
    mobile.addEventListener("click", function (evento) {
      evento.stopPropagation();
      bloco.mobile = bloco.mobile || {};
      bloco.mobile.visible = bloco.mobile.visible === false;
      atualizarOlho();
      marcarSujo();
      atualizarItemDaEstrutura(bloco);
      blocoEl.classList.toggle("is-oculto-no-mobile", bloco.mobile.visible === false);
    });
    atualizarOlho();
    return faixa;
  }

  var modeloControlesImagem = document.querySelector("[data-modelo-controles-imagem]");

  function montarPainelDeImagem(bloco, blocoEl, caixaImagem) {
    var painel = modeloControlesImagem.content.firstElementChild.cloneNode(true);

    var botoesAncora = painel.querySelectorAll("[data-ancora]");
    var seletorLargura = painel.querySelector("[data-largura-imagem]");
    var campoAlt = painel.querySelector("[data-alt-imagem]");

    function atualizarPainel() {
      var ancoraAtual = (bloco.desktop && bloco.desktop.anchor) || "none";
      botoesAncora.forEach(function (b) {
        b.classList.toggle("is-ativo", b.getAttribute("data-ancora") === ancoraAtual);
      });
      seletorLargura.value = String((bloco.desktop && bloco.desktop.width) || 36);
      seletorLargura.closest(".eb-painel-campo").style.display = ancoraAtual === "none" ? "none" : "flex";
      if (document.activeElement !== campoAlt) { campoAlt.value = bloco.alt || ""; }
    }

    botoesAncora.forEach(function (botao) {
      botao.addEventListener("click", function (evento) {
        evento.stopPropagation();
        bloco.desktop = bloco.desktop || { anchor: "none", width: 36 };
        bloco.desktop.anchor = botao.getAttribute("data-ancora");
        marcarSujo();
        atualizarPainel();
        preencherImagem(caixaImagem, bloco);
      });
    });
    seletorLargura.addEventListener("click", function (evento) { evento.stopPropagation(); });
    seletorLargura.addEventListener("change", function () {
      bloco.desktop = bloco.desktop || { anchor: "none", width: 36 };
      bloco.desktop.width = parseInt(seletorLargura.value, 10);
      marcarSujo();
      preencherImagem(caixaImagem, bloco);
    });
    campoAlt.addEventListener("click", function (evento) { evento.stopPropagation(); });
    campoAlt.addEventListener("input", function () {
      bloco.alt = campoAlt.value;
      marcarSujo();
      var img = caixaImagem.querySelector("img");
      if (img) { img.alt = bloco.alt; }
    });
    painel.querySelector("[data-trocar-imagem]").addEventListener("click", function (evento) {
      evento.stopPropagation();
      abrirSeletorDeImagem(bloco, caixaImagem);
    });

    atualizarPainel();
    return painel;
  }

  function montarBlocoDom(bloco) {
    var blocoEl = elemento("div", "eb-bloco eb-bloco-" + bloco.type);
    blocoEl.setAttribute("data-bloco", "1");
    blocoEl.setAttribute("data-id", bloco.id);
    blocoEl.setAttribute("draggable", "true");
    if (bloco.mobile && bloco.mobile.visible === false) {
      blocoEl.classList.add("is-oculto-no-mobile");
    }
    if (bloco.line_height) { blocoEl.style.lineHeight = bloco.line_height; }
    if (typeof bloco.spacing_after === "number") { blocoEl.style.marginBottom = bloco.spacing_after + "px"; }

    var construtor = RENDERIZADORES[bloco.type];
    var conteudo = construtor ? construtor(bloco) : elemento("div", "", "");
    blocoEl.appendChild(conteudo);
    blocoEl.appendChild(montarFaixaDeAcoes(bloco, blocoEl));
    if (bloco.type === "image") {
      blocoEl.appendChild(montarPainelDeImagem(bloco, blocoEl, conteudo));
    }

    blocoEl.addEventListener("click", function () { selecionar(bloco.id); });
    blocoEl.addEventListener("dragstart", function (evento) {
      evento.dataTransfer.setData("text/plain", bloco.id);
      blocoEl.classList.add("is-arrastando");
    });
    blocoEl.addEventListener("dragend", function () { blocoEl.classList.remove("is-arrastando"); });
    // Arrastar direto no quadro reordena igual à lista da estrutura --
    // a alça da lateral não é a ÚNICA forma, só a mais previsível.
    blocoEl.addEventListener("dragover", function (evento) {
      evento.preventDefault();
      blocoEl.classList.add("is-alvo-de-soltura");
    });
    blocoEl.addEventListener("dragleave", function () { blocoEl.classList.remove("is-alvo-de-soltura"); });
    blocoEl.addEventListener("drop", function (evento) {
      evento.preventDefault();
      blocoEl.classList.remove("is-alvo-de-soltura");
      moverBlocoAntesDe(evento.dataTransfer.getData("text/plain"), bloco.id);
    });

    return blocoEl;
  }

  function montarItemDaEstrutura(bloco) {
    var item = elemento("div", "eb-item");
    item.setAttribute("data-item", "1");
    item.setAttribute("data-id", bloco.id);
    item.setAttribute("draggable", "true");
    if (bloco.mobile && bloco.mobile.visible === false) { item.classList.add("is-oculto-no-mobile"); }

    var alca = elemento(
      "span", "eb-item-alca",
      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">' +
      '<circle cx="9" cy="6" r="1.3" fill="currentColor"></circle><circle cx="15" cy="6" r="1.3" fill="currentColor"></circle>' +
      '<circle cx="9" cy="12" r="1.3" fill="currentColor"></circle><circle cx="15" cy="12" r="1.3" fill="currentColor"></circle>' +
      '<circle cx="9" cy="18" r="1.3" fill="currentColor"></circle><circle cx="15" cy="18" r="1.3" fill="currentColor"></circle></svg>'
    );
    var icone = elemento("i", "ph " + (ICONES_POR_TIPO[bloco.type] || "ph-square") + " eb-item-icone");
    var rotulo = elemento("span", "eb-item-rotulo", rotuloDoBloco(bloco));
    var mobile = document.createElement("button");
    mobile.type = "button";
    mobile.className = "eb-item-mobile";
    mobile.title = "Visível no mobile";
    mobile.innerHTML = (!bloco.mobile || bloco.mobile.visible !== false) ? SVG_OLHO : SVG_OLHO_FECHADO;
    mobile.setAttribute("aria-pressed", String(!bloco.mobile || bloco.mobile.visible !== false));
    mobile.addEventListener("click", function (evento) {
      evento.stopPropagation();
      bloco.mobile = bloco.mobile || {};
      bloco.mobile.visible = bloco.mobile.visible === false;
      marcarSujo();
      desenharTudo();
    });

    item.appendChild(alca);
    item.appendChild(icone);
    item.appendChild(rotulo);
    item.appendChild(mobile);
    item.addEventListener("click", function () { selecionar(bloco.id); });
    item.addEventListener("dragstart", function (evento) {
      evento.dataTransfer.setData("text/plain", bloco.id);
      item.classList.add("is-arrastando");
    });
    item.addEventListener("dragend", function () { item.classList.remove("is-arrastando"); });
    item.addEventListener("dragover", function (evento) {
      evento.preventDefault();
      item.classList.add("is-alvo-de-soltura");
    });
    item.addEventListener("dragleave", function () { item.classList.remove("is-alvo-de-soltura"); });
    item.addEventListener("drop", function (evento) {
      evento.preventDefault();
      item.classList.remove("is-alvo-de-soltura");
      var idArrastado = evento.dataTransfer.getData("text/plain");
      moverBlocoAntesDe(idArrastado, bloco.id);
    });
    return item;
  }

  function rotuloDoBloco(bloco) {
    var base = ROTULO_POR_TIPO[bloco.type] || bloco.type;
    if (["paragraph", "heading", "quote", "highlight", "button"].indexOf(bloco.type) !== -1) {
      var texto = (bloco.html || "").replace(/<[^>]+>/g, "").trim();
      if (texto) { return texto.slice(0, 40); }
    }
    return base;
  }

  function atualizarItemDaEstrutura(bloco) {
    var item = listaEstrutura.querySelector('[data-id="' + bloco.id + '"]');
    if (item) {
      var rotulo = item.querySelector(".eb-item-rotulo");
      if (rotulo) { rotulo.textContent = rotuloDoBloco(bloco); }
    }
  }

  // --- Desenho completo ------------------------------------------------------

  var focoAtual = null;

  function desenharTudo() {
    var idSelecionadoAntes = estado.selecionadoId;
    canvas.innerHTML = "";
    listaEstrutura.innerHTML = "";
    estado.blocos.forEach(function (bloco) {
      canvas.appendChild(montarBlocoDom(bloco));
      listaEstrutura.appendChild(montarItemDaEstrutura(bloco));
    });
    if (idSelecionadoAntes && porId(idSelecionadoAntes)) {
      selecionar(idSelecionadoAntes);
    }
  }

  var seletorTipoBloco = barra.querySelector('[data-comando="tipo-bloco"]');
  var seletorEntrelinha = barra.querySelector('[data-comando="lineHeight"]');
  var seletorEspacoDepois = barra.querySelector('[data-comando="spacing-after"]');

  function selecionar(id) {
    estado.selecionadoId = id;
    canvas.querySelectorAll("[data-bloco]").forEach(function (el) {
      el.classList.toggle("is-selecionado", el.getAttribute("data-id") === id);
    });
    listaEstrutura.querySelectorAll("[data-item]").forEach(function (el) {
      el.classList.toggle("is-selecionado", el.getAttribute("data-id") === id);
    });
    var bloco = porId(id);
    if (!bloco) { return; }
    if (seletorTipoBloco) {
      var conversivel = TIPOS_CONVERSIVEIS.indexOf(bloco.type) !== -1;
      seletorTipoBloco.disabled = !conversivel;
      if (conversivel) { seletorTipoBloco.value = bloco.type; }
    }
    if (seletorEntrelinha) { seletorEntrelinha.value = bloco.line_height || "1.55"; }
    if (seletorEspacoDepois) {
      seletorEspacoDepois.value = String(typeof bloco.spacing_after === "number" ? bloco.spacing_after : 16);
    }
  }

  function blocoSelecionadoOuDoFoco() {
    var doSelecionado = estado.selecionadoId && porId(estado.selecionadoId);
    if (doSelecionado) { return doSelecionado; }
    var elFoco = focoAtual && focoAtual.closest("[data-bloco]");
    return elFoco ? porId(elFoco.getAttribute("data-id")) : null;
  }

  function converterTipoDeBloco(novoTipo) {
    var bloco = blocoSelecionadoOuDoFoco();
    if (!bloco || bloco.type === novoTipo) { return; }
    if (TIPOS_CONVERSIVEIS.indexOf(bloco.type) === -1 || TIPOS_CONVERSIVEIS.indexOf(novoTipo) === -1) { return; }
    bloco.type = novoTipo;
    marcarSujo();
    desenharTudo();
    selecionar(bloco.id);
  }

  function aplicarEntrelinhaAoBloco(valor) {
    var bloco = blocoSelecionadoOuDoFoco();
    if (!bloco) { return; }
    bloco.line_height = valor;
    marcarSujo();
    var el = canvas.querySelector('[data-id="' + bloco.id + '"]');
    if (el) { el.style.lineHeight = valor; }
  }

  function aplicarEspacoDepoisAoBloco(valor) {
    var bloco = blocoSelecionadoOuDoFoco();
    if (!bloco) { return; }
    bloco.spacing_after = valor;
    marcarSujo();
    var el = canvas.querySelector('[data-id="' + bloco.id + '"]');
    if (el) { el.style.marginBottom = valor + "px"; }
  }

  function excluirBloco(id) {
    estado.blocos = estado.blocos.filter(function (b) { return b.id !== id; });
    if (estado.selecionadoId === id) { estado.selecionadoId = null; }
    marcarSujo();
    desenharTudo();
  }

  function inserirBloco(tipo) {
    var novo = blocoNovo(tipo);
    var indice = estado.blocos.length;
    if (estado.selecionadoId) {
      var i = estado.blocos.findIndex(function (b) { return b.id === estado.selecionadoId; });
      if (i !== -1) { indice = i + 1; }
    }
    estado.blocos.splice(indice, 0, novo);
    marcarSujo();
    desenharTudo();
    selecionar(novo.id);
    var elBloco = canvas.querySelector('[data-id="' + novo.id + '"]');
    if (elBloco) {
      elBloco.scrollIntoView({ block: "center", behavior: "smooth" });
      var campo = elBloco.querySelector("[contenteditable]");
      if (campo) { campo.focus(); }
    }
  }

  function moverBlocoAntesDe(idArrastado, idAlvo) {
    if (idArrastado === idAlvo) { return; }
    var doIndice = estado.blocos.findIndex(function (b) { return b.id === idArrastado; });
    var paraIndice = estado.blocos.findIndex(function (b) { return b.id === idAlvo; });
    if (doIndice === -1 || paraIndice === -1) { return; }
    var item = estado.blocos.splice(doIndice, 1)[0];
    var destino = estado.blocos.findIndex(function (b) { return b.id === idAlvo; });
    estado.blocos.splice(destino, 0, item);
    marcarSujo();
    desenharTudo();
    selecionar(idArrastado);
  }

  // Soltar no FIM do quadro (depois do último bloco) também reordena.
  canvas.addEventListener("dragover", function (evento) { evento.preventDefault(); });
  canvas.addEventListener("drop", function (evento) {
    if (evento.target !== canvas) { return; }
    evento.preventDefault();
    var idArrastado = evento.dataTransfer.getData("text/plain");
    var indice = estado.blocos.findIndex(function (b) { return b.id === idArrastado; });
    if (indice === -1) { return; }
    var item = estado.blocos.splice(indice, 1)[0];
    estado.blocos.push(item);
    marcarSujo();
    desenharTudo();
  });

  // --- "+ Bloco" ---------------------------------------------------------------

  function montarMenuDeBlocos(filtro) {
    itensMenuBloco.innerHTML = "";
    var termo = (filtro || "").trim().toLowerCase();
    catalogo.forEach(function (grupo) {
      var itens = grupo.itens.filter(function (item) {
        return !termo || item.rotulo.toLowerCase().indexOf(termo) !== -1 || item.descricao.toLowerCase().indexOf(termo) !== -1;
      });
      if (!itens.length) { return; }
      itensMenuBloco.appendChild(elemento("div", "eb-menu-bloco-categoria", grupo.categoria));
      itens.forEach(function (item) {
        var botao = document.createElement("button");
        botao.type = "button";
        botao.className = "eb-menu-bloco-item";
        botao.innerHTML =
          '<i class="ph ' + item.icone + '" aria-hidden="true"></i>' +
          '<span class="eb-menu-bloco-item-textos"><span class="eb-menu-bloco-item-nome">' + item.rotulo +
          '</span><span class="eb-menu-bloco-item-desc">' + item.descricao + "</span></span>";
        botao.addEventListener("click", function () {
          inserirBloco(item.tipo);
          fecharMenuDeBlocos();
        });
        itensMenuBloco.appendChild(botao);
      });
    });
  }

  function abrirMenuDeBlocos() {
    montarMenuDeBlocos("");
    menuBloco.hidden = false;
    buscaBloco.value = "";
    buscaBloco.focus();
  }
  function fecharMenuDeBlocos() { menuBloco.hidden = true; }

  raiz.querySelector("[data-abrir-menu-bloco]").addEventListener("click", function (evento) {
    evento.stopPropagation();
    if (menuBloco.hidden) { abrirMenuDeBlocos(); } else { fecharMenuDeBlocos(); }
  });
  buscaBloco.addEventListener("input", function () { montarMenuDeBlocos(buscaBloco.value); });
  document.addEventListener("click", function (evento) {
    if (!menuBloco.hidden && !evento.target.closest(".eb-menu-bloco")) { fecharMenuDeBlocos(); }
  });
  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape") { fecharMenuDeBlocos(); fecharSeletorDeImagem(); }
  });

  // --- Seletor de imagem (imagem única ou galeria) ----------------------------

  var alvoDoSeletor = null; // { bloco, caixa, modo: "imagem" | "galeria" }

  function abrirSeletorDeImagem(bloco, caixa) {
    alvoDoSeletor = { bloco: bloco, caixa: caixa, modo: "imagem" };
    montarGradeDeImagens();
    seletorImagem.hidden = false;
  }
  function abrirSeletorDeGaleria(bloco, caixa) {
    alvoDoSeletor = { bloco: bloco, caixa: caixa, modo: "galeria" };
    montarGradeDeImagens();
    seletorImagem.hidden = false;
  }
  function fecharSeletorDeImagem() {
    seletorImagem.hidden = true;
    alvoDoSeletor = null;
  }

  function montarGradeDeImagens() {
    gradeImagens.innerHTML = "";
    if (!imagensDaBiblioteca.length) {
      gradeImagens.appendChild(elemento("p", "field-hint", "Nenhuma imagem ativa na biblioteca."));
      return;
    }
    imagensDaBiblioteca.forEach(function (asset) {
      var botao = document.createElement("button");
      botao.type = "button";
      botao.title = asset.nome || "";
      var img = document.createElement("img");
      img.src = asset.url;
      img.alt = "";
      botao.appendChild(img);
      botao.addEventListener("click", function () {
        if (!alvoDoSeletor) { return; }
        if (alvoDoSeletor.modo === "imagem") {
          alvoDoSeletor.bloco.asset_id = asset.id;
          alvoDoSeletor.bloco.alt = alvoDoSeletor.bloco.alt || asset.nome || "";
          preencherImagem(alvoDoSeletor.caixa, alvoDoSeletor.bloco);
        } else {
          alvoDoSeletor.bloco.asset_ids = alvoDoSeletor.bloco.asset_ids || [];
          if (alvoDoSeletor.bloco.asset_ids.indexOf(asset.id) === -1 && alvoDoSeletor.bloco.asset_ids.length < 6) {
            alvoDoSeletor.bloco.asset_ids.push(asset.id);
          }
          preencherGaleria(alvoDoSeletor.caixa, alvoDoSeletor.bloco);
        }
        marcarSujo();
        atualizarItemDaEstrutura(alvoDoSeletor.bloco);
        if (alvoDoSeletor.modo === "imagem") { fecharSeletorDeImagem(); }
      });
      gradeImagens.appendChild(botao);
    });
  }

  raiz.querySelector("[data-fechar-seletor-imagem]").addEventListener("click", fecharSeletorDeImagem);
  seletorImagem.addEventListener("click", function (evento) {
    if (evento.target === seletorImagem) { fecharSeletorDeImagem(); }
  });

  // --- A barra de formatação compartilhada -------------------------------------
  // Opera sobre `document.activeElement` -- o campo de texto que tiver o
  // foco no instante do clique. `mousedown` (não `click`) guarda a seleção
  // ANTES do navegador tirar o foco do campo para o botão.

  var selecaoGuardada = null;

  function guardarSelecao() {
    var s = window.getSelection();
    selecaoGuardada = s && s.rangeCount ? s.getRangeAt(0).cloneRange() : null;
  }
  function restaurarSelecao() {
    if (!selecaoGuardada) { return; }
    var s = window.getSelection();
    s.removeAllRanges();
    s.addRange(selecaoGuardada);
  }

  barra.addEventListener("mousedown", function (evento) {
    if (evento.target.closest("[data-comando], select")) { guardarSelecao(); }
  });

  barra.addEventListener("click", function (evento) {
    var botao = evento.target.closest("[data-comando]");
    if (!botao || botao.tagName === "SELECT") { return; }
    var comando = botao.getAttribute("data-comando");
    if (comando === "abrir-link") { abrirLink(); return; }
    if (comando === "html") { alternarVisualizacaoHtml(); return; }
    if (!focoAtual) { return; }
    restaurarSelecao();
    focoAtual.focus();
    if (comando === "foreColor" || comando === "hiliteColor") {
      document.execCommand(comando, false, botao.getAttribute("data-valor"));
    } else {
      document.execCommand(comando, false, null);
    }
    sincronizarFoco();
  });

  barra.querySelectorAll("select[data-comando]").forEach(function (select) {
    select.addEventListener("change", function () {
      var comando = select.getAttribute("data-comando");
      // Estas três mexem no BLOCO selecionado, não no texto sob o
      // cursor -- funcionam mesmo sem foco ativo num contenteditable
      // (ex.: um bloco de imagem ou tabela selecionado).
      if (comando === "tipo-bloco") { converterTipoDeBloco(select.value); return; }
      if (comando === "lineHeight") { aplicarEntrelinhaAoBloco(select.value); return; }
      if (comando === "spacing-after") { aplicarEspacoDepoisAoBloco(parseInt(select.value, 10)); return; }
      if (!focoAtual) { return; }
      restaurarSelecao();
      focoAtual.focus();
      document.execCommand(comando, false, select.value);
      sincronizarFoco();
    });
  });

  function sincronizarFoco() {
    if (!focoAtual) { return; }
    var blocoEl = focoAtual.closest("[data-bloco]");
    if (!blocoEl) { return; }
    var bloco = porId(blocoEl.getAttribute("data-id"));
    if (bloco) {
      bloco.html = focoAtual.innerHTML;
      marcarSujo();
      atualizarItemDaEstrutura(bloco);
    }
  }

  function alternarVisualizacaoHtml() {
    if (!focoAtual) { return; }
    if (focoAtual.getAttribute("data-modo-html") === "1") {
      focoAtual.innerHTML = focoAtual.textContent;
      focoAtual.contentEditable = "true";
      focoAtual.removeAttribute("data-modo-html");
    } else {
      focoAtual.textContent = focoAtual.innerHTML;
      focoAtual.contentEditable = "true";
      focoAtual.setAttribute("data-modo-html", "1");
    }
    sincronizarFoco();
  }

  function abrirLink() {
    if (!focoAtual) { return; }
    guardarSelecao();
    var selecao = window.getSelection();
    caixaLink.hidden = false;
    caixaLink.querySelector("[data-link-texto]").value = selecao ? String(selecao) : "";
    caixaLink.querySelector("[data-link-endereco]").focus();
  }
  raiz.querySelector("[data-fechar-link]").addEventListener("click", function () { caixaLink.hidden = true; });
  raiz.querySelector("[data-aplicar-link]").addEventListener("click", function () {
    var endereco = caixaLink.querySelector("[data-link-endereco]").value.trim();
    var texto = caixaLink.querySelector("[data-link-texto]").value.trim() || endereco;
    var novaAba = caixaLink.querySelector("[data-link-nova-aba]").checked;
    if (!endereco || !focoAtual) { caixaLink.hidden = true; return; }
    restaurarSelecao();
    focoAtual.focus();
    var alvo = novaAba ? ' target="_blank" rel="noopener noreferrer"' : "";
    if (selecaoGuardada && !selecaoGuardada.collapsed) {
      document.execCommand("createLink", false, endereco);
    } else {
      document.execCommand(
        "insertHTML", false,
        '<a href="' + endereco.replace(/"/g, "&quot;") + '"' + alvo + ">" + texto.replace(/</g, "&lt;") + "</a>"
      );
    }
    sincronizarFoco();
    caixaLink.hidden = true;
  });

  // --- Abas Editar / Visualizar + Desktop/Mobile --------------------------------

  var corpoEditar = raiz.querySelector('[data-modo="editar"]');
  var corpoVisualizar = raiz.querySelector('[data-modo="visualizar"]');
  var dispositivoAtual = "desktop";

  function enviarPrevia() {
    campoBlocosPrevia.value = JSON.stringify(estado.blocos);
    campoViewportPrevia.value = dispositivoAtual;
    formPrevia.submit();
  }

  raiz.querySelectorAll("[data-aba-botao]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      var aba = botao.getAttribute("data-aba-botao");
      raiz.setAttribute("data-aba", aba);
      raiz.querySelectorAll("[data-aba-botao]").forEach(function (b) {
        var ativa = b === botao;
        b.classList.toggle("is-ativa", ativa);
        b.setAttribute("aria-selected", String(ativa));
      });
      raiz.querySelectorAll('[data-so-na-aba="visualizar"]').forEach(function (el) {
        el.hidden = aba !== "visualizar";
      });
      corpoEditar.hidden = aba !== "editar";
      corpoVisualizar.hidden = aba !== "visualizar";
      if (aba === "visualizar") { enviarPrevia(); }
    });
  });

  // A largura do `<iframe>` -- a referência das media queries de dentro,
  // a mesma técnica de `content_preview.html` -- é toda CSS
  // (`.eb[data-dispositivo="mobile"] .eb-iframe`), por `max-width`, não
  // um valor fixo: assim ela NUNCA estoura a largura real da janela do
  // Backoffice, em qualquer tamanho de tela. Este script só marca o
  // estado; o `<meta viewport>` de dentro do iframe continua fixo em
  // `device-width`.
  raiz.querySelectorAll("[data-dispositivo-botao]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      dispositivoAtual = botao.getAttribute("data-dispositivo-botao");
      raiz.setAttribute("data-dispositivo", dispositivoAtual);
      raiz.querySelectorAll("[data-dispositivo-botao]").forEach(function (b) {
        var ativo = b === botao;
        b.classList.toggle("is-ativo", ativo);
        b.setAttribute("aria-pressed", String(ativo));
      });
    });
  });

  // --- Salvar ------------------------------------------------------------------

  raiz.querySelector("[data-form-blocos]").addEventListener("submit", function () {
    // Um campo de texto pode ainda não ter disparado `input` se a
    // pessoa clicou direto em "Salvar" -- `sincronizarFoco` já cobre
    // isso a cada mudança, mas o `blur` implícito do submit garante.
    campoBlocos.value = JSON.stringify(estado.blocos);
  });

  // --- Primeiro desenho ----------------------------------------------------------

  desenharTudo();
})();
