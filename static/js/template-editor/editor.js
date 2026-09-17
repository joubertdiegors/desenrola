/*
 * Editor rico dos modelos da biblioteca -- orquestracao (Etapa 3.7).
 *
 * A logica de dados vive em geometry.js, state.js, runs.js, document.js,
 * canvas.js e panels.js, que sao puros (ou so montam DOM) e testados no
 * Node. Este arquivo e a casca: le o estado inicial, escuta eventos,
 * chama aquelas funcoes e redesenha. Se algo aqui parecer merecer um
 * teste, provavelmente e regra e deveria estar num dos outros modulos.
 *
 * O QUE E EDITADO ONDE
 * --------------------
 *   texto      -- direto na folha: cada bloco de texto e um
 *                 `contenteditable`; a barra formata a SELECAO
 *                 (execCommand) e o bloco e lido de volta como trechos
 *                 (`TERuns.serializar`) a cada tecla;
 *   bloco      -- alinhamento, lista, recuo, entrelinha, estilo: uma
 *                 propriedade do elemento;
 *   graficos   -- imagem, QR, linha, retangulo: arrasto na folha e a
 *                 barra contextual;
 *   documento  -- idioma, margens, faixa, numeracao: o painel da direita.
 *
 * Estado de sessao (selecao, cursor, zoom, historico, "tem alteracao por
 * salvar") vive aqui e NAO vai para o JSON: o layout guarda o desenho,
 * nao como alguem o estava olhando.
 */
(function () {
  "use strict";

  var raiz = document.querySelector("[data-editor]");
  if (!raiz) {
    return;
  }

  var Geo = window.TEGeometry;
  var State = window.TEState;
  var Runs = window.TERuns;
  var Doc = window.TEDocument;
  var Canvas = window.TECanvas;
  var Panels = window.TEPanels;
  var Api = window.TEApi;

  function lerJson(id) {
    var no = document.getElementById(id);
    return no ? JSON.parse(no.textContent) : null;
  }

  var config = lerJson("te-config") || {};
  var pagina = lerJson("te-pagina") || {};
  var catalogo = lerJson("te-tipos") || [];
  var fontes = lerJson("te-fontes") || [];
  var assets = lerJson("te-assets") || [];
  var exemplo = lerJson("te-exemplo") || {};
  var layoutPadrao = lerJson("te-layout-padrao");
  var rotulos = Canvas.indiceDeCampos(fontes);

  // Lista plana de referencias, para os seletores.
  var referencias = [];
  fontes.forEach(function (grupo) {
    (grupo.fields || []).forEach(function (campo) {
      referencias.push({ reference: campo.reference, label: grupo.label + " · " + campo.label });
    });
  });

  var larguraDaPagina = Number(pagina.width) || 595.2756;
  var alturaDaPagina = Number(pagina.height) || 841.8898;
  var PT_POR_MM = 72 / 25.4;
  var ZOOM_INICIAL = 0.9;
  var ESCALA_DO_FLUXO = 1.4;
  var COR_DO_LINK = "#1d4ed8";
  var COR_DO_REALCE = "#fff6c9";
  var JANELA_DE_COALESCENCIA = 1500;

  var celular = window.matchMedia ? window.matchMedia("(max-width: 1023px)") : { matches: false };

  var layoutInicial = State.normalizar(lerJson("te-layout"), config.layoutVersion);
  if (lerJson("te-layout") && lerJson("te-layout").document) {
    layoutInicial.document = lerJson("te-layout").document;
  }

  var estado = {
    historico: State.criarHistorico(layoutInicial),
    salvo: layoutInicial,
    ids: State.criarFilaDeIds(lerJson("te-ids") || []),
    language: config.language || "",
    languageSalvo: config.language || "",
    selecionado: null,         // elemento grafico selecionado
    ativo: null,               // {id, linha, celula} do bloco/celula com o cursor
    cursor: null,              // {id, linha, celula, posicao} para restaurar
    zoom: ZOOM_INICIAL,
    exemplo: false,
    sujo: false,
    aba: "texto",
    filtro: "",
    abertos: {},
    ultimaCoalescencia: { chave: null, quando: 0 }
  };

  var arrasto = null;
  // Sair de proposito (botao "Descartar"): nao perguntar de novo.
  var saindo = false;

  function layout() {
    return State.atual(estado.historico);
  }

  function layoutVisivel() {
    return arrasto ? arrasto.provisorio : layout();
  }

  function modo() {
    return celular.matches ? "fluxo" : "pagina";
  }

  function escala() {
    return modo() === "fluxo" ? ESCALA_DO_FLUXO : Canvas.PX_POR_PT * estado.zoom;
  }

  /*
   * Toda mudanca passa por aqui: um lugar so para historico e sujeira.
   * `opcoes.coalescer` junta teclas seguidas no mesmo passo de desfazer.
   */
  function aplicar(novoLayout, opcoes) {
    var o = opcoes || {};
    if (novoLayout === layout()) {
      return;
    }
    var agora = Date.now();
    var mesma = o.coalescer && estado.ultimaCoalescencia.chave === o.coalescer &&
      agora - estado.ultimaCoalescencia.quando < JANELA_DE_COALESCENCIA;
    if (mesma && State.podeDesfazer(estado.historico)) {
      estado.historico = State.substituir(estado.historico, novoLayout);
    } else {
      estado.historico = State.registrar(estado.historico, novoLayout);
    }
    estado.ultimaCoalescencia = { chave: o.coalescer || null, quando: agora };
    estado.sujo = true;
    if (!o.semRedesenho) {
      desenhar();
    } else {
      atualizarLaterais();
    }
  }

  // --- nos da tela ---------------------------------------------------------

  var noPaginas = raiz.querySelector("[data-paginas]");
  var noArea = raiz.querySelector("[data-area]");
  var noCampos = raiz.querySelector("[data-campos]");
  var noUsos = raiz.querySelector("[data-usos]");
  var noCtx = raiz.querySelector("[data-ctx]");
  var noAviso = raiz.querySelector("[data-aviso]");
  var noZoom = raiz.querySelector("[data-zoom-valor]");
  var noInfo = raiz.querySelector("[data-info-pagina]");
  var nosEstado = raiz.querySelectorAll("[data-estado]");
  var noBusca = raiz.querySelector("[data-busca]");
  var noIdioma = raiz.querySelector("[data-idioma]");
  var noMargens = raiz.querySelector("[data-margens]");
  var noFaixa = raiz.querySelector("[data-faixa]");
  var noNumeracao = raiz.querySelector("[data-numeracao]");
  var nosExemplo = raiz.querySelectorAll("[data-exemplo]");
  var caixaLink = raiz.querySelector("[data-caixa='link']");
  var caixaHtml = raiz.querySelector("[data-caixa='html']");
  var formPrevia = raiz.querySelector("[data-form-previa]");

  var barra = {
    estilo: raiz.querySelector("[data-cmd='estilo']"),
    fonte: raiz.querySelector("[data-cmd='fonte']"),
    tamanho: raiz.querySelector("[data-cmd='tamanho']"),
    entrelinha: raiz.querySelector("[data-cmd='entrelinha']"),
    negrito: raiz.querySelector("[data-cmd='bold']"),
    italico: raiz.querySelector("[data-cmd='italic']"),
    sublinhado: raiz.querySelector("[data-cmd='underline']"),
    riscado: raiz.querySelector("[data-cmd='strikeThrough']"),
    alinhar_left: raiz.querySelector("[data-cmd='alinhar'][data-valor='left']"),
    alinhar_center: raiz.querySelector("[data-cmd='alinhar'][data-valor='center']"),
    alinhar_right: raiz.querySelector("[data-cmd='alinhar'][data-valor='right']"),
    alinhar_justify: raiz.querySelector("[data-cmd='alinhar'][data-valor='justify']"),
    listaMarcadores: raiz.querySelector("[data-cmd='lista'][data-valor='marcadores']"),
    listaNumerada: raiz.querySelector("[data-cmd='lista'][data-valor='numerada']"),
    soDeBloco: Array.prototype.slice.call(raiz.querySelectorAll("[data-so-bloco]"))
  };

  try {
    document.execCommand("styleWithCSS", false, false);
  } catch (e) { /* motor antigo */ }

  // Em leitura a barra inteira e desligada: um botao que nao faz nada e
  // pior do que botao nenhum. Desfazer/refazer e o zoom continuam.
  if (!config.editable) {
    var controles = raiz.querySelectorAll("[data-cmd]");
    for (var c = 0; c < controles.length; c += 1) {
      if (controles[c].dataset.cmd !== "undo" && controles[c].dataset.cmd !== "redo") {
        controles[c].disabled = true;
      }
    }
  }

  // --- ajudantes de DOM ------------------------------------------------------

  function noDoElemento(id) {
    return noPaginas.querySelector("[data-id='" + id + "']");
  }

  function noDoBloco(ativo) {
    if (!ativo) {
      return null;
    }
    var seletor = "[data-bloco='" + ativo.id + "']";
    if (ativo.linha !== undefined && ativo.linha !== null) {
      seletor += "[data-linha='" + ativo.linha + "'][data-celula='" + ativo.celula + "']";
    }
    return noPaginas.querySelector(seletor);
  }

  function ativoDe(no) {
    var area = no && no.closest ? no.closest("[data-bloco]") : null;
    if (!area) {
      return null;
    }
    var ativo = { id: area.dataset.bloco };
    if (area.dataset.linha !== undefined) {
      ativo.linha = parseInt(area.dataset.linha, 10);
      ativo.celula = parseInt(area.dataset.celula, 10);
    }
    return ativo;
  }

  function elementoAtivo() {
    return estado.ativo ? State.obter(layout(), estado.ativo.id) : null;
  }

  function blocoDeReferencia() {
    var el = elementoAtivo();
    if (el) {
      return el;
    }
    if (estado.selecionado) {
      return State.obter(layout(), estado.selecionado);
    }
    return Doc.ultimoBloco(layout());
  }

  // --- cursor ----------------------------------------------------------------
  //
  // A posicao e contada em "posicoes de trecho" (um caractere de texto,
  // um chip de campo, uma quebra de linha), a mesma moeda de
  // `TERuns.dividir`.

  function eChip(no) {
    return no && no.nodeType === 1 && no.hasAttribute && no.hasAttribute("data-field");
  }

  function posicaoDoCursor(bloco) {
    var sel = window.getSelection();
    if (!sel || !sel.rangeCount || !bloco.contains(sel.anchorNode)) {
      return null;
    }
    var alcance = sel.getRangeAt(0);
    var ate = document.createRange();
    ate.setStart(bloco, 0);
    ate.setEnd(alcance.startContainer, alcance.startOffset);
    return contarPosicoes(ate.cloneContents());
  }

  function contarPosicoes(fragmento) {
    var total = 0;
    (function andar(no) {
      var filhos = no.childNodes;
      for (var i = 0; i < filhos.length; i += 1) {
        var f = filhos[i];
        if (f.nodeType === 3) {
          total += f.nodeValue.length;
        } else if (eChip(f) || String(f.tagName).toLowerCase() === "br") {
          total += 1;
        } else {
          andar(f);
        }
      }
    })(fragmento);
    return total;
  }

  function fimDoBloco(bloco) {
    return contarPosicoes(bloco);
  }

  /*
   * Põe uma das pontas de `alcance` na posição `posicao` do bloco.
   *
   * Um chip de campo é indivisível: a ponta cai ANTES ou DEPOIS dele,
   * nunca dentro -- é o que mantém a posição em trechos e a posição no
   * DOM falando a mesma língua.
   */
  function aplicarPonto(alcance, bloco, posicao, ponta) {
    var restante = posicao;
    var achou = false;

    function marcar(metodo, no, deslocamento) {
      if (ponta === "inicio") {
        if (metodo === "dentro") {
          alcance.setStart(no, deslocamento);
        } else if (metodo === "antes") {
          alcance.setStartBefore(no);
        } else {
          alcance.setStartAfter(no);
        }
      } else if (metodo === "dentro") {
        alcance.setEnd(no, deslocamento);
      } else if (metodo === "antes") {
        alcance.setEndBefore(no);
      } else {
        alcance.setEndAfter(no);
      }
      achou = true;
    }

    (function andar(no) {
      var filhos = no.childNodes;
      for (var i = 0; i < filhos.length && !achou; i += 1) {
        var f = filhos[i];
        if (f.nodeType === 3) {
          if (restante <= f.nodeValue.length) {
            marcar("dentro", f, restante);
            return;
          }
          restante -= f.nodeValue.length;
        } else if (eChip(f) || String(f.tagName).toLowerCase() === "br") {
          if (restante <= 0) {
            marcar("antes", f);
            return;
          }
          restante -= 1;
          if (restante === 0) {
            marcar("depois", f);
            return;
          }
        } else {
          andar(f);
        }
      }
    })(bloco);
    return achou;
  }

  function colocarCursor(bloco, posicao) {
    var sel = window.getSelection();
    var alcance = document.createRange();
    if (!aplicarPonto(alcance, bloco, posicao, "inicio")) {
      alcance.selectNodeContents(bloco);
      alcance.collapse(false);
    } else {
      alcance.collapse(true);
    }
    sel.removeAllRanges();
    sel.addRange(alcance);
  }

  /* Devolve a seleção a um intervalo de trechos depois de redesenhar. */
  function selecionarIntervalo(bloco, de, ate) {
    var sel = window.getSelection();
    var alcance = document.createRange();
    if (!aplicarPonto(alcance, bloco, de, "inicio")) {
      return;
    }
    if (!aplicarPonto(alcance, bloco, ate, "fim")) {
      alcance.collapse(true);
    }
    sel.removeAllRanges();
    sel.addRange(alcance);
  }

  function selecaoNoBloco(bloco) {
    var sel = window.getSelection();
    return !!(sel && sel.rangeCount && bloco.contains(sel.anchorNode) && bloco.contains(sel.focusNode));
  }

  function intervaloDaSelecao(bloco) {
    var sel = window.getSelection();
    if (!selecaoNoBloco(bloco)) {
      return null;
    }
    var alcance = sel.getRangeAt(0);
    var inicio = document.createRange();
    inicio.setStart(bloco, 0);
    inicio.setEnd(alcance.startContainer, alcance.startOffset);
    var fim = document.createRange();
    fim.setStart(bloco, 0);
    fim.setEnd(alcance.endContainer, alcance.endOffset);
    return { de: contarPosicoes(inicio.cloneContents()), ate: contarPosicoes(fim.cloneContents()) };
  }

  function guardarCursor() {
    var no = noDoBloco(estado.ativo);
    if (!no) {
      estado.cursor = null;
      return;
    }
    var posicao = posicaoDoCursor(no);
    estado.cursor = posicao === null ? null : Object.assign({ posicao: posicao }, estado.ativo);
  }

  function restaurarCursor() {
    if (!estado.cursor) {
      return;
    }
    var no = noDoBloco(estado.cursor);
    if (!no) {
      return;
    }
    no.focus();
    colocarCursor(no, Math.min(estado.cursor.posicao, fimDoBloco(no)));
  }

  // --- desenho ---------------------------------------------------------------

  function opcoesDeDesenho() {
    return {
      escala: escala(),
      pagina: pagina,
      campos: rotulos,
      exemplo: estado.exemplo ? exemplo : null,
      assets: assets,
      selecionado: estado.selecionado,
      ativo: estado.ativo ? estado.ativo.id : null,
      editavel: config.editable,
      modo: modo()
    };
  }

  function desenhar() {
    var doc = layoutVisivel();
    Canvas.desenharLayout(document, noPaginas, doc, opcoesDeDesenho());
    raiz.dataset.modo = modo();
    if (noZoom) {
      noZoom.textContent = Math.round(estado.zoom * 100) + "%";
    }
    atualizarLaterais();
    restaurarCursor();
  }

  function infoDaPagina() {
    var nome = Math.abs(larguraDaPagina - 595.2756) < 1 && Math.abs(alturaDaPagina - 841.8898) < 1
      ? "A4" : "Página";
    var m = Doc.margem(layout());
    var margem = m === null ? "" : " · margens " + String(Math.round((m / PT_POR_MM) * 10) / 10).replace(".", ",") + " mm";
    return nome + " · " + Math.round(larguraDaPagina) + " × " + Math.round(alturaDaPagina) + " pt" + margem;
  }

  function atualizarLaterais() {
    var doc = layout();
    if (noInfo) {
      noInfo.textContent = infoDaPagina();
    }
    Panels.montarCampos(document, noCampos, fontes, {
      filtro: estado.filtro,
      exemplo: exemplo,
      abertos: estado.abertos,
      celular: modo() === "fluxo",
      editavel: config.editable,
      aoInserir: inserirCampo,
      aoAlternar: function (code) {
        estado.abertos[code] = estado.abertos[code] === false;
        atualizarLaterais();
      }
    });
    Panels.montarUsos(document, noUsos, doc, fontes, { celular: modo() === "fluxo" });
    atualizarDocumento();
    atualizarBotoes();
    refletirBarra();
    atualizarCtx();
  }

  function atualizarDocumento() {
    var doc = layout();
    if (noIdioma) {
      noIdioma.value = estado.language;
    }
    if (noMargens) {
      var m = Doc.margem(doc);
      var achou = null;
      (config.margins || []).forEach(function (op) {
        if (m !== null && Math.abs(op.pt - m) < 0.6) {
          achou = op.key;
        }
      });
      if (achou) {
        Panels.marcarValor(noMargens, achou, "");
      } else if (m !== null) {
        Panels.marcarValor(
          noMargens, "atual",
          "Atuais (" + String(Math.round((m / PT_POR_MM) * 10) / 10).replace(".", ",") + " mm)"
        );
      }
    }
    if (noFaixa) {
      noFaixa.checked = Doc.faixa(doc, (config.flagStripe || {}).colors).length > 0;
    }
    if (noNumeracao) {
      noNumeracao.checked = !!(doc.document && doc.document.page_numbers);
    }
    for (var i = 0; i < nosExemplo.length; i += 1) {
      nosExemplo[i].checked = estado.exemplo;
    }
  }

  function atualizarBotoes() {
    var desfazer = raiz.querySelectorAll("[data-cmd='undo']");
    var refazer = raiz.querySelectorAll("[data-cmd='redo']");
    var i;
    for (i = 0; i < desfazer.length; i += 1) {
      desfazer[i].disabled = !State.podeDesfazer(estado.historico);
    }
    for (i = 0; i < refazer.length; i += 1) {
      refazer[i].disabled = !State.podeRefazer(estado.historico);
    }
    var texto = estado.sujo ? "Alterações não salvas" : "Tudo salvo";
    for (i = 0; i < nosEstado.length; i += 1) {
      nosEstado[i].textContent = texto;
      nosEstado[i].classList.toggle("is-sujo", estado.sujo);
    }
  }

  function selecaoAtual() {
    var no = noDoBloco(estado.ativo);
    var sel = { bold: false, italic: false, underline: false, strike: false };
    if (!no || !selecaoNoBloco(no)) {
      return sel;
    }
    try {
      sel.bold = document.queryCommandState("bold");
      sel.italic = document.queryCommandState("italic");
      sel.underline = document.queryCommandState("underline");
      sel.strike = document.queryCommandState("strikeThrough");
    } catch (e) { /* fora de um editavel */ }
    var s = window.getSelection();
    var alvo = s.anchorNode && s.anchorNode.nodeType === 3 ? s.anchorNode.parentNode : s.anchorNode;
    var estilo = {};
    while (alvo && alvo !== no) {
      var proprio = Runs.estiloDoNo(alvo, escala());
      Object.keys(proprio).forEach(function (k) {
        if (estilo[k] === undefined) {
          estilo[k] = proprio[k];
        }
      });
      alvo = alvo.parentNode;
    }
    sel.font_size = estilo.font_size;
    sel.font_family = estilo.font_family;
    sel.link = estilo.link;
    return sel;
  }

  function refletirBarra() {
    Panels.refletir(barra, {
      bloco: elementoAtivo(),
      selecao: selecaoAtual(),
      editavel: config.editable
    });
  }

  function atualizarCtx() {
    if (!noCtx) {
      return;
    }
    var el = estado.selecionado ? State.obter(layout(), estado.selecionado) : null;
    var declarado = null;
    catalogo.forEach(function (t) { if (el && t.code === el.type) { declarado = t; } });
    Panels.montarBarraDoElemento(document, noCtx, el, {
      assets: assets,
      referencias: referencias,
      editavel: config.editable,
      rotulo: declarado ? declarado.label : "",
      aoAlterar: function (props) {
        aplicar(State.atualizar(layout(), el.id, { properties: props }, config.layoutVersion));
      },
      aoGeometria: function (geometria) {
        aplicar(State.atualizar(layout(), el.id, geometria, config.layoutVersion));
      },
      aoAcao: executarAcao
    });
  }

  function avisar(texto, erro) {
    if (!noAviso) {
      return;
    }
    noAviso.textContent = texto;
    noAviso.classList.toggle("is-erro", !!erro);
    noAviso.hidden = !texto;
  }

  // --- ids ----------------------------------------------------------------------

  function proximoId() {
    var id = State.proximoId(estado.ids, layout());
    if (id) {
      return Promise.resolve(id);
    }
    return Api.pedirIds(document, config.idsUrl).then(function (novos) {
      State.reabastecer(estado.ids, novos);
      return State.proximoId(estado.ids, layout());
    });
  }

  function proximosIds(quantos) {
    var lista = [];
    function pegar() {
      if (lista.length >= quantos) {
        return Promise.resolve(lista);
      }
      return proximoId().then(function (id) {
        if (!id) {
          return lista;
        }
        lista.push(id);
        return pegar();
      });
    }
    return pegar();
  }

  // --- o bloco de texto: ler de volta e refluir ----------------------------------

  function lerBloco(no, el, ativo) {
    var base = el.properties || {};
    if (ativo.linha !== undefined) {
      var celula = ((base.rows || [])[ativo.linha] || {}).cells;
      celula = celula ? celula[ativo.celula] || {} : {};
      base = Object.assign({}, base, { font_weight: celula.bold ? "bold" : base.font_weight });
    }
    return Runs.serializar(no, { escala: escala(), base: base });
  }

  /*
   * A altura que o bloco quer ter, em pt, sem a altura minima da caixa.
   *
   * MEDIDA EM LINHAS INTEIRAS, e nao em pixels crus. Duas razoes:
   *
   *   1. `scrollHeight` e INTEIRO. Um bloco de duas linhas de 13,5pt
   *      ocupa 32,4px a 90% e volta como 32 -- 26,67pt em vez de 27,0.
   *      A caixa ficava 0,33pt curta e o renderer, que reduz a fonte
   *      para caber (`overflow: shrink`), desenhava o texto 2,3% menor
   *      do que o editor mostrava. Diferenca silenciosa entre a tela e
   *      o PDF, e foi assim que ela apareceu;
   *   2. o renderer mede exatamente `linhas x entrelinha`. Arredondar
   *      para o mesmo multiplo e falar a lingua dele.
   *
   * `getBoundingClientRect()` porque devolve fracao; o arredondamento
   * final e para a linha mais proxima, nunca para baixo do que cabe.
   */
  function alturaNatural(noElemento, elemento) {
    var minimo = noElemento.style.minHeight;
    noElemento.style.minHeight = "0";
    var medida = noElemento.getBoundingClientRect().height / escala();
    noElemento.style.minHeight = minimo;
    return emLinhasInteiras(medida, elemento);
  }

  function emLinhasInteiras(medida, elemento) {
    var p = (elemento && elemento.properties) || {};
    var entrelinha = Number(p.line_height || 1.25) * Number(p.font_size || 11);
    if (!entrelinha) {
      return Math.round(medida * 100) / 100;
    }
    var caixa = Number((p.padding || {}).top || 0) + Number((p.padding || {}).bottom || 0);
    var linhas = Math.max(1, Math.round((medida - caixa) / entrelinha));
    return Math.round((linhas * entrelinha + caixa) * 1000) / 1000;
  }

  /* A altura de cada linha da tabela, pela mesma regra. */
  function alturasDasLinhas(noElemento, elemento) {
    var p = (elemento && elemento.properties) || {};
    var entrelinha = Number(p.line_height || 1.25) * Number(p.font_size || 11);
    var caixa = Number((p.cell_padding || {}).top || 0) + Number((p.cell_padding || {}).bottom || 0);
    var linhas = noElemento.querySelectorAll("tr");
    var alturas = [];
    for (var i = 0; i < linhas.length; i += 1) {
      var medida = linhas[i].getBoundingClientRect().height / escala();
      var quantas = entrelinha ? Math.max(1, Math.round((medida - caixa) / entrelinha)) : 1;
      alturas.push(entrelinha
        ? Math.round((quantas * entrelinha + caixa) * 1000) / 1000
        : Math.round(medida * 100) / 100);
    }
    return alturas;
  }

  /*
   * Depois de uma tecla: le o bloco (ou a celula), grava, mede e
   * empurra o que esta abaixo. O bloco em edicao NAO e redesenhado --
   * o cursor fica onde esta; so as posicoes dos outros mudam.
   */
  function sincronizarBloco(chave) {
    var ativo = estado.ativo;
    var no = noDoBloco(ativo);
    var el = elementoAtivo();
    if (!no || !el) {
      return;
    }
    var trechos = lerBloco(no, el, ativo);
    var novo;
    if (ativo.linha !== undefined) {
      var linhas = State.clonar(el.properties.rows || []);
      if (!linhas[ativo.linha] || !linhas[ativo.linha].cells[ativo.celula]) {
        return;
      }
      linhas[ativo.linha].cells[ativo.celula].content = Runs.blocoDe(trechos);
      novo = State.atualizar(layout(), el.id, { properties: { rows: linhas } }, config.layoutVersion);
    } else {
      novo = Doc.gravarConteudo(layout(), el.id, trechos);
    }
    novo = medirEAjustar(novo, el.id);
    if (novo !== layout()) {
      aplicar(novo, { coalescer: chave || "digitar:" + el.id, semRedesenho: true });
      Canvas.reposicionar(noPaginas, layout(), opcoesDeDesenho());
    }
  }

  function medirEAjustar(doc, id) {
    if (modo() !== "pagina") {
      return doc;
    }
    var noElemento = noDoElemento(id);
    var el = State.obter(doc, id);
    if (!noElemento || !el) {
      return doc;
    }
    if (el.type === "table") {
      var alturas = alturasDasLinhas(noElemento, el);
      var linhas = State.clonar(el.properties.rows || []);
      var mudou = false;
      alturas.forEach(function (h, i) {
        if (linhas[i] && Math.abs(Number(linhas[i].min_height || 0) - h) > 0.5) {
          linhas[i].min_height = h;
          mudou = true;
        }
      });
      if (mudou) {
        doc = State.atualizar(doc, id, { properties: { rows: linhas } }, config.layoutVersion);
      }
      var total = alturas.reduce(function (a, b) { return a + b; }, 0);
      return total ? Doc.ajustarAltura(doc, id, total) : doc;
    }
    if (Doc.eTexto(el)) {
      return Doc.ajustarAltura(doc, id, alturaNatural(noElemento, el));
    }
    return doc;
  }

  /* Redesenha um bloco a partir do estado e devolve o cursor a ele. */
  function redesenharBlocoAtivo(posicao) {
    guardarCursor();
    if (posicao !== undefined && estado.cursor) {
      estado.cursor.posicao = posicao;
    } else if (posicao !== undefined && estado.ativo) {
      estado.cursor = Object.assign({ posicao: posicao }, estado.ativo);
    }
    desenhar();
  }

  // --- formatacao ---------------------------------------------------------------------

  // O que cada botão de formatação significa no DADO. É por aqui que a
  // formatação de um CAMPO acontece -- ver `estiloEstruturalNaSelecao`.
  var ESTILO_DO_COMANDO = {
    bold: ["font_weight", "bold"],
    italic: ["font_style", "italic"],
    underline: ["text_decoration", "underline"],
    strikeThrough: ["text_decoration", "line-through"]
  };

  function trechosDaSelecao(trechos, intervalo) {
    var depois = Runs.dividir(trechos, intervalo.de)[1];
    return Runs.dividir(depois, intervalo.ate - intervalo.de)[0];
  }

  /*
   * Formata a SELEÇÃO no dado, não no DOM.
   *
   * Um campo é um chip `contenteditable="false"`: o `execCommand` do
   * navegador não o formata -- não há texto dele para embrulhar, e o
   * clique em "B" simplesmente não fazia nada. Quando a seleção inclui
   * um campo, então, o estilo vai direto nos TRECHOS
   * (`TERuns.aplicarEstilo`) e o bloco é redesenhado com a seleção de
   * volta no lugar. É o que faz "negrito só no campo" existir de
   * verdade -- e é como o documento oficial já negrita o nome do
   * anfitrião no meio da frase.
   *
   * Devolve `false` quando não se aplica (sem seleção, ou seleção sem
   * campo nenhum): aí quem chamou segue pelo `execCommand`, que mexe
   * menos no DOM e preserva melhor o cursor no texto comum.
   */
  function estiloEstruturalNaSelecao(chave, valor, alternar) {
    var no = noDoBloco(estado.ativo);
    var el = elementoAtivo();
    if (!no || !el || !config.editable || selecaoColapsada(no)) {
      return false;
    }
    var intervalo = intervaloDaSelecao(no);
    if (!intervalo || intervalo.ate <= intervalo.de) {
      return false;
    }
    var trechos = lerBloco(no, el, estado.ativo);
    var dentro = trechosDaSelecao(trechos, intervalo);
    if (!dentro.some(function (t) { return t.kind === "field"; })) {
      return false;
    }
    // Liga/desliga (negrito, itálico, sublinhado, riscado, realce): se
    // TUDO que está selecionado já tem o valor, o clique tira. Cor,
    // fonte e tamanho não alternam -- escolher "14 pt" é pedir 14 pt.
    var ja = alternar && dentro.length > 0 && dentro.every(function (t) {
      return t[chave] === valor;
    });
    var mudanca = {};
    mudanca[chave] = ja ? null : valor;
    gravarTrechosNoAtivo(Runs.aplicarEstilo(trechos, intervalo.de, intervalo.ate, mudanca));
    guardarCursor();
    desenhar();
    var redesenhado = noDoBloco(estado.ativo);
    if (redesenhado) {
      redesenhado.focus();
      selecionarIntervalo(redesenhado, intervalo.de, intervalo.ate);
    }
    refletirBarra();
    medirDepoisDeDesenhar(el.id);
    return true;
  }

  function executarNoBloco(comando, valor) {
    var no = noDoBloco(estado.ativo);
    if (!no || !config.editable) {
      return;
    }
    if (!selecaoNoBloco(no)) {
      no.focus();
      colocarCursor(no, fimDoBloco(no));
    }
    try {
      document.execCommand(comando, false, valor);
    } catch (e) { /* comando fora do motor */ }
    sincronizarBloco("formato:" + comando);
    refletirBarra();
  }

  function selecaoColapsada(no) {
    var sel = window.getSelection();
    return !sel || !sel.rangeCount || sel.isCollapsed || !selecaoNoBloco(no);
  }

  /* Estilo para a selecao quando ha uma; para o bloco inteiro quando nao ha. */
  function estiloDeSelecaoOuBloco(comando, valor, propriedade, valorDoBloco) {
    var no = noDoBloco(estado.ativo);
    var el = elementoAtivo();
    if (!no || !el) {
      return;
    }
    if (selecaoColapsada(no) || estado.ativo.linha !== undefined) {
      var props = {};
      props[propriedade] = valorDoBloco;
      aplicar(State.atualizar(layout(), el.id, { properties: props }, config.layoutVersion));
      medirDepoisDeDesenhar(el.id);
      return;
    }
    executarNoBloco(comando, valor);
  }

  function medirDepoisDeDesenhar(id) {
    var novo = medirEAjustar(layout(), id);
    if (novo !== layout()) {
      aplicar(novo, { semRedesenho: true });
      Canvas.reposicionar(noPaginas, layout(), opcoesDeDesenho());
    }
  }

  function alterarBloco(props) {
    var el = elementoAtivo();
    if (!el || !config.editable) {
      return;
    }
    guardarCursor();
    aplicar(State.atualizar(layout(), el.id, { properties: props }, config.layoutVersion));
    medirDepoisDeDesenhar(el.id);
  }

  function limparFormatacao() {
    var no = noDoBloco(estado.ativo);
    var el = elementoAtivo();
    if (!no || !el || !config.editable) {
      return;
    }
    var trechos = lerBloco(no, el, estado.ativo);
    var intervalo = selecaoColapsada(no) ? null : intervaloDaSelecao(no);
    var limpos;
    if (intervalo && intervalo.ate > intervalo.de) {
      var nulos = {};
      Runs.ESTILOS.forEach(function (k) { nulos[k] = null; });
      limpos = Runs.aplicarEstilo(trechos, intervalo.de, intervalo.ate, nulos);
    } else {
      limpos = Runs.limparEstilo(trechos);
    }
    gravarTrechosNoAtivo(limpos);
    redesenharBlocoAtivo(intervalo ? intervalo.ate : undefined);
  }

  function gravarTrechosNoAtivo(trechos) {
    var el = elementoAtivo();
    if (!el) {
      return;
    }
    var novo;
    if (estado.ativo.linha !== undefined) {
      var linhas = State.clonar(el.properties.rows || []);
      linhas[estado.ativo.linha].cells[estado.ativo.celula].content = Runs.blocoDe(trechos);
      novo = State.atualizar(layout(), el.id, { properties: { rows: linhas } }, config.layoutVersion);
    } else {
      novo = Doc.gravarConteudo(layout(), el.id, trechos);
    }
    aplicar(novo, { semRedesenho: true });
  }

  // --- link ----------------------------------------------------------------------------

  var selecaoGuardada = null;

  function guardarSelecao() {
    var sel = window.getSelection();
    var no = noDoBloco(estado.ativo);
    if (sel && sel.rangeCount && no && no.contains(sel.anchorNode)) {
      selecaoGuardada = sel.getRangeAt(0).cloneRange();
    }
  }

  function devolverSelecao() {
    var no = noDoBloco(estado.ativo);
    if (!no) {
      return;
    }
    no.focus();
    if (selecaoGuardada) {
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(selecaoGuardada);
    }
  }

  function abrirLink() {
    var no = noDoBloco(estado.ativo);
    if (!no || !caixaLink) {
      return;
    }
    guardarSelecao();
    var sel = window.getSelection();
    var atual = selecaoAtual();
    caixaLink.hidden = false;
    if (caixaHtml) { caixaHtml.hidden = true; }
    caixaLink.querySelector("[data-link-texto]").value = sel ? String(sel) : "";
    caixaLink.querySelector("[data-link-endereco]").value = atual.link || "";
    caixaLink.querySelector("[data-link-remover]").hidden = !atual.link;
    caixaLink.querySelector("[data-link-endereco]").focus();
  }

  function aplicarLink() {
    var entrada = caixaLink.querySelector("[data-link-endereco]");
    var endereco = Runs.linkAceito(entrada.value);
    if (!endereco) {
      entrada.classList.add("is-invalido");
      entrada.focus();
      return;
    }
    entrada.classList.remove("is-invalido");
    var no = noDoBloco(estado.ativo);
    var el = elementoAtivo();
    if (!no || !el) {
      return;
    }
    devolverSelecao();
    var rotulo = (caixaLink.querySelector("[data-link-texto]").value || "").trim() || endereco;
    var intervalo = selecaoColapsada(no) ? null : intervaloDaSelecao(no);
    var trechos = lerBloco(no, el, estado.ativo);
    var estilo = { link: endereco, color: COR_DO_LINK, text_decoration: "underline" };
    var novos, posicao;
    if (intervalo && intervalo.ate > intervalo.de) {
      novos = Runs.aplicarEstilo(trechos, intervalo.de, intervalo.ate, estilo);
      posicao = intervalo.ate;
    } else {
      var onde = posicaoDoCursor(no);
      if (onde === null) { onde = Runs.comprimento(trechos); }
      var partes = Runs.dividir(trechos, onde);
      novos = Runs.juntar(Runs.juntar(partes[0], [Runs.texto(rotulo, estilo)]), partes[1]);
      posicao = onde + rotulo.length;
    }
    gravarTrechosNoAtivo(novos);
    caixaLink.hidden = true;
    redesenharBlocoAtivo(posicao);
  }

  function removerLink() {
    var no = noDoBloco(estado.ativo);
    var el = elementoAtivo();
    if (!no || !el) {
      return;
    }
    devolverSelecao();
    var trechos = lerBloco(no, el, estado.ativo);
    var onde = posicaoDoCursor(no) || 0;
    var novos = trechos.map(function (t) {
      var copia = Runs.copiar(t);
      if (copia.link) {
        delete copia.link;
        delete copia.color;
        delete copia.text_decoration;
      }
      return copia;
    });
    gravarTrechosNoAtivo(novos);
    caixaLink.hidden = true;
    redesenharBlocoAtivo(onde);
  }

  // --- HTML do bloco -------------------------------------------------------------------

  function abrirHtml() {
    var no = noDoBloco(estado.ativo);
    if (!no || !caixaHtml) {
      return;
    }
    guardarSelecao();
    caixaHtml.hidden = !caixaHtml.hidden;
    if (caixaLink) { caixaLink.hidden = true; }
    if (!caixaHtml.hidden) {
      caixaHtml.querySelector("[data-html-fonte]").value = no.innerHTML.replace(/></g, ">\n<");
    }
  }

  function aplicarHtml() {
    var el = elementoAtivo();
    if (!el || !caixaHtml) {
      return;
    }
    // DOMParser produz um documento INERTE: nada executa, nada carrega.
    // So o que `serializar` reconhece sobrevive -- texto e trechos.
    var fonte = caixaHtml.querySelector("[data-html-fonte]").value;
    var inerte = new DOMParser().parseFromString("<div>" + fonte + "</div>", "text/html");
    var raizInerte = inerte.body.firstChild;
    var base = el.properties || {};
    var trechos = Runs.serializar(raizInerte, { escala: escala(), base: base });
    gravarTrechosNoAtivo(trechos);
    caixaHtml.hidden = true;
    redesenharBlocoAtivo(Runs.comprimento(trechos));
  }

  // --- insercao ------------------------------------------------------------------------

  function inserirCampo(referencia) {
    if (!config.editable) {
      return;
    }
    var no = noDoBloco(estado.ativo);
    var el = elementoAtivo();
    if (no && el) {
      var trechos = lerBloco(no, el, estado.ativo);
      var onde = posicaoDoCursor(no);
      if (onde === null) {
        onde = Runs.comprimento(trechos);
      }
      var partes = Runs.dividir(trechos, onde);
      var novos = Runs.juntar(Runs.juntar(partes[0], [Runs.campo(referencia)]), partes[1]);
      gravarTrechosNoAtivo(novos);
      if (celular.matches) {
        estado.aba = "texto";
        raiz.dataset.aba = "texto";
      }
      redesenharBlocoAtivo(onde + 1);
      medirDepoisDeDesenhar(el.id);
      return;
    }
    // Sem cursor: um bloco novo com o campo, depois do ultimo bloco.
    proximoId().then(function (id) {
      if (!id) {
        avisar("Não foi possível obter um identificador para o elemento.", true);
        return;
      }
      var ref = Doc.ultimoBloco(layout());
      var novo = Doc.novoBlocoDeTexto(id, ref, { kind: "field", source: referencia });
      estado.ativo = { id: id };
      estado.cursor = { id: id, posicao: 1 };
      estado.selecionado = null;
      aplicar(Doc.inserirDepois(layout(), ref ? ref.id : null, novo, { y: margemTopo() }));
      medirDepoisDeDesenhar(id);
    });
  }

  function margemTopo() {
    var m = Doc.margem(layout());
    return m === null ? 25 * PT_POR_MM : m;
  }

  function inserirElementoDepois(fabrica) {
    if (!config.editable) {
      return;
    }
    proximoId().then(function (id) {
      if (!id) {
        avisar("Não foi possível obter um identificador para o elemento.", true);
        return;
      }
      var ref = blocoDeReferencia();
      var elemento = fabrica(id, ref);
      estado.ativo = null;
      estado.cursor = null;
      estado.selecionado = Doc.eTexto(elemento) ? null : id;
      if (Doc.eTexto(elemento)) {
        estado.ativo = { id: id };
        estado.cursor = { id: id, posicao: 0 };
      }
      aplicar(Doc.inserirDepois(layout(), ref ? ref.id : null, elemento, {
        y: margemTopo(), manterGeometria: !Doc.eTexto(elemento)
      }));
      if (Doc.eTexto(elemento) || elemento.type === "table") {
        medirDepoisDeDesenhar(id);
      }
    });
  }

  function geometriaDeReferencia(ref) {
    var m = margemTopo();
    return {
      x: ref ? Number(ref.x) : m,
      width: ref ? Number(ref.width) : larguraDaPagina - 2 * m
    };
  }

  function inserirTabela() {
    inserirElementoDepois(function (id, ref) {
      var g = geometriaDeReferencia(ref);
      var el = State.criarElemento(catalogo, "table", id, { x: g.x, y: 0 });
      var esquerda = Math.round(g.width * 0.34 * 100) / 100;
      el.width = g.width;
      el.properties.columns = [
        { width: esquerda, align: "left" }, { width: g.width - esquerda, align: "left" }
      ];
      el.properties.rows = [0, 1, 2].map(function () {
        return { min_height: 20, cells: [
          { content: { kind: "text", value: "" }, align: "left", bold: false },
          { content: { kind: "text", value: "" }, align: "left", bold: false }
        ] };
      });
      el.properties.border_width = 0.75;
      el.properties.cell_padding = { top: 4, right: 5, bottom: 4, left: 5 };
      var tipografia = ref && Doc.eTexto(ref) ? ref.properties : {};
      el.properties.font_family = tipografia.font_family || "LiberationSans";
      el.properties.font_size = tipografia.font_size || 11;
      el.properties.line_height = tipografia.line_height || 1.25;
      el.height = 60;
      return el;
    });
  }

  function inserirImagem() {
    inserirElementoDepois(function (id, ref) {
      var g = geometriaDeReferencia(ref);
      var el = State.criarElemento(catalogo, "image", id, { x: g.x, y: 0 });
      el.width = 120;
      el.height = 120;
      return el;
    });
  }

  function inserirQr() {
    inserirElementoDepois(function (id, ref) {
      var g = geometriaDeReferencia(ref);
      var el = State.criarElemento(catalogo, "qr_code", id, { x: g.x, y: 0 });
      el.width = 78;
      el.height = 78;
      return el;
    });
  }

  function inserirLinha() {
    inserirElementoDepois(function (id, ref) {
      var g = geometriaDeReferencia(ref);
      var el = State.criarElemento(catalogo, "line", id, { x: g.x, y: 0 });
      el.width = g.width;
      el.height = 0;
      el.properties.thickness = 0.75;
      return el;
    });
  }

  function inserirQuebra() {
    if (!config.editable) {
      return;
    }
    var ref = blocoDeReferencia();
    if (!ref) {
      return;
    }
    proximoId().then(function (id) {
      if (!id) {
        return;
      }
      guardarCursor();
      aplicar(Doc.inserirQuebra(layout(), ref.id, id, pagina, margemTopo()));
    });
  }

  function inserirAssinatura() {
    if (!config.editable) {
      return;
    }
    var ref = blocoDeReferencia();
    proximosIds(3).then(function (ids) {
      if (ids.length < 3) {
        avisar("Não foi possível obter identificadores para a assinatura.", true);
        return;
      }
      var g = geometriaDeReferencia(ref);
      var linha = State.criarElemento(catalogo, "line", ids[0], { x: g.x, y: 0 });
      linha.width = Math.min(190, g.width);
      linha.height = 0;
      linha.properties.thickness = 0.7;
      var nome = Doc.novoBlocoDeTexto(ids[1], ref, {
        kind: "mixed", parts: [{ kind: "field", source: "anfitriao.nome", font_weight: "bold" }]
      });
      nome.x = g.x;
      nome.width = g.width;
      var rotulo = Doc.novoBlocoDeTexto(ids[2], ref, { kind: "text", value: "Assinatura" });
      rotulo.x = g.x;
      rotulo.width = g.width;
      var doc = Doc.inserirDepois(layout(), ref ? ref.id : null, linha, {
        y: margemTopo(), manterGeometria: true, espaco: 26
      });
      doc = Doc.inserirDepois(doc, ids[0], nome, { espaco: 4 });
      doc = Doc.inserirDepois(doc, ids[1], rotulo, { espaco: 0 });
      estado.ativo = { id: ids[2] };
      estado.cursor = { id: ids[2], posicao: 0 };
      estado.selecionado = null;
      aplicar(doc);
    });
  }

  // --- acoes sobre o elemento selecionado -------------------------------------------

  function executarAcao(acao) {
    var id = estado.selecionado;
    if (!id || !config.editable) {
      return;
    }
    var versao = config.layoutVersion;
    var el = State.obter(layout(), id);

    if (acao === "remover") {
      estado.selecionado = null;
      if (el && el.type === "page_break") {
        aplicar(Doc.removerQuebra(layout(), id));
      } else {
        aplicar(Doc.remover(layout(), id));
      }
    } else if (acao === "duplicar") {
      proximoId().then(function (novo) {
        if (!novo) {
          return;
        }
        var resultado = State.duplicar(layout(), id, novo, versao);
        estado.selecionado = resultado.id;
        aplicar(resultado.layout);
      });
    } else if (acao === "frente") {
      aplicar(State.moverParaFrente(layout(), id, versao));
    } else if (acao === "tras") {
      aplicar(State.moverParaTras(layout(), id, versao));
    } else if (acao.indexOf("tabela-") === 0 && el && el.type === "table") {
      aplicar(alterarTabela(el, acao));
      medirDepoisDeDesenhar(id);
    }
  }

  function alterarTabela(el, acao) {
    var colunas = State.clonar(el.properties.columns || []);
    var linhas = State.clonar(el.properties.rows || []);
    var celulaVazia = function () {
      return { content: { kind: "text", value: "" }, align: "left", bold: false };
    };
    if (acao === "tabela-mais-linha") {
      linhas.push({ min_height: linhas.length ? linhas[linhas.length - 1].min_height : 20,
        cells: colunas.map(celulaVazia) });
    } else if (acao === "tabela-menos-linha" && linhas.length > 1) {
      linhas.pop();
    } else if (acao === "tabela-mais-coluna") {
      var largura = 60;
      colunas.push({ width: largura, align: "left" });
      linhas.forEach(function (l) { l.cells.push(celulaVazia()); });
    } else if (acao === "tabela-menos-coluna" && colunas.length > 1) {
      colunas.pop();
      linhas.forEach(function (l) { l.cells.pop(); });
    }
    var largura = colunas.reduce(function (a, c) { return a + Number(c.width || 0); }, 0);
    var altura = linhas.reduce(function (a, l) { return a + Number(l.min_height || 0); }, 0);
    var doc = State.atualizar(layout(), el.id, {
      width: largura, properties: { columns: colunas, rows: linhas }
    }, config.layoutVersion);
    return Doc.ajustarAltura(doc, el.id, altura);
  }

  // --- teclado dentro de um bloco -------------------------------------------------------

  function tratarTeclaNoBloco(evento, no) {
    var el = elementoAtivo();
    if (!el || !config.editable) {
      return;
    }
    var tecla = evento.key;
    var meta = evento.ctrlKey || evento.metaKey;

    if (meta && tecla.toLowerCase() === "z") {
      evento.preventDefault();
      desfazer(!!evento.shiftKey);
      return;
    }
    if (meta && tecla.toLowerCase() === "y") {
      evento.preventDefault();
      desfazer(true);
      return;
    }
    if (meta && tecla.toLowerCase() === "s") {
      evento.preventDefault();
      salvar();
      return;
    }
    if (estado.ativo.linha !== undefined) {
      if (tecla === "Enter" && !evento.shiftKey) {
        evento.preventDefault();
        try { document.execCommand("insertLineBreak"); } catch (e) { /* motor antigo */ }
        sincronizarBloco();
      }
      return;
    }
    if (tecla === "Enter") {
      evento.preventDefault();
      if (evento.shiftKey) {
        try { document.execCommand("insertLineBreak"); } catch (e) { /* motor antigo */ }
        sincronizarBloco();
        return;
      }
      var onde = posicaoDoCursor(no);
      if (onde === null) {
        return;
      }
      sincronizarBloco();
      proximoId().then(function (id) {
        if (!id) {
          return;
        }
        var resultado = Doc.dividirBloco(layout(), el.id, onde, id);
        if (!resultado.id) {
          return;
        }
        estado.ativo = { id: resultado.id };
        estado.cursor = { id: resultado.id, posicao: 0 };
        aplicar(resultado.layout);
        medirDepoisDeDesenhar(el.id);
        medirDepoisDeDesenhar(resultado.id);
      });
      return;
    }
    if (tecla === "Backspace") {
      var posicao = posicaoDoCursor(no);
      var sel = window.getSelection();
      if (posicao === 0 && sel && sel.isCollapsed) {
        evento.preventDefault();
        sincronizarBloco();
        var vazio = Runs.comprimento(lerBloco(no, el, estado.ativo)) === 0;
        var anterior = Doc.blocoAnterior(layout(), el.id);
        if (vazio && !anterior) {
          return;
        }
        if (vazio) {
          estado.ativo = { id: anterior.id };
          estado.cursor = { id: anterior.id, posicao: Runs.comprimento(Runs.trechosDe(anterior.properties.content)) };
          aplicar(Doc.remover(layout(), el.id));
          return;
        }
        var juntado = Doc.juntarComAnterior(layout(), el.id);
        if (!juntado.id) {
          return;
        }
        estado.ativo = { id: juntado.id };
        estado.cursor = { id: juntado.id, posicao: juntado.posicao };
        aplicar(juntado.layout);
        medirDepoisDeDesenhar(juntado.id);
      }
      return;
    }
    if (tecla === "Delete") {
      var fim = posicaoDoCursor(no);
      var selecao = window.getSelection();
      if (fim !== null && fim === fimDoBloco(no) && selecao && selecao.isCollapsed) {
        var seguinte = Doc.blocoSeguinte(layout(), el.id);
        if (!seguinte) {
          return;
        }
        evento.preventDefault();
        sincronizarBloco();
        var res = Doc.juntarComAnterior(layout(), seguinte.id);
        if (!res.id) {
          return;
        }
        estado.ativo = { id: res.id };
        estado.cursor = { id: res.id, posicao: res.posicao };
        aplicar(res.layout);
        medirDepoisDeDesenhar(res.id);
      }
      return;
    }
    if (tecla === "Tab") {
      evento.preventDefault();
      guardarCursor();
      aplicar(Doc.recuar(layout(), el.id, evento.shiftKey ? -1 : 1));
      medirDepoisDeDesenhar(el.id);
    }
  }

  function desfazer(refazer) {
    guardarCursor();
    estado.historico = refazer ? State.refazer(estado.historico) : State.desfazer(estado.historico);
    estado.ultimaCoalescencia = { chave: null, quando: 0 };
    estado.sujo = true;
    if (estado.selecionado && !State.obter(layout(), estado.selecionado)) {
      estado.selecionado = null;
    }
    if (estado.ativo && !State.obter(layout(), estado.ativo.id)) {
      estado.ativo = null;
      estado.cursor = null;
    }
    desenhar();
  }

  // --- eventos: folha ------------------------------------------------------------------

  noPaginas.addEventListener("focusin", function (evento) {
    var ativo = ativoDe(evento.target);
    if (!ativo) {
      return;
    }
    estado.ativo = ativo;
    if (estado.selecionado) {
      var anterior = noDoElemento(estado.selecionado);
      if (anterior) { anterior.classList.remove("is-selecionado"); }
      estado.selecionado = null;
      atualizarCtx();
    }
    var no = noDoElemento(ativo.id);
    var ativos = noPaginas.querySelectorAll(".is-ativo");
    for (var i = 0; i < ativos.length; i += 1) { ativos[i].classList.remove("is-ativo"); }
    if (no) { no.classList.add("is-ativo"); }
    refletirBarra();
  });

  noPaginas.addEventListener("input", function (evento) {
    var ativo = ativoDe(evento.target);
    if (!ativo) {
      return;
    }
    estado.ativo = ativo;
    sincronizarBloco();
  });

  noPaginas.addEventListener("keydown", function (evento) {
    var area = evento.target.closest ? evento.target.closest("[data-bloco]") : null;
    if (!area) {
      return;
    }
    estado.ativo = ativoDe(area);
    tratarTeclaNoBloco(evento, area);
  });

  noPaginas.addEventListener("paste", function (evento) {
    var area = evento.target.closest ? evento.target.closest("[data-bloco]") : null;
    if (!area || !evento.clipboardData) {
      return;
    }
    // Colar entra como TEXTO: o que vier formatado de fora nao traz
    // marcacao nenhuma para dentro do documento.
    evento.preventDefault();
    var texto = evento.clipboardData.getData("text/plain");
    if (texto) {
      try { document.execCommand("insertText", false, texto); } catch (e) { /* motor antigo */ }
      sincronizarBloco();
    }
  });

  document.addEventListener("selectionchange", function () {
    if (estado.ativo && noDoBloco(estado.ativo)) {
      refletirBarra();
    }
  });

  noPaginas.addEventListener("pointerdown", function (evento) {
    var alvo = evento.target.closest ? evento.target.closest("[data-id]") : null;
    if (!alvo) {
      return;
    }
    var id = alvo.dataset.id;
    var el = State.obter(layout(), id);
    if (!el || Doc.eTexto(el) || el.type === "table") {
      return; // texto e tabela sao editados no lugar
    }
    evento.preventDefault();
    estado.selecionado = id;
    estado.ativo = null;
    estado.cursor = null;
    if (!config.editable || modo() !== "pagina") {
      desenhar();
      return;
    }
    arrasto = {
      id: id,
      alca: evento.target.dataset ? evento.target.dataset.alca || null : null,
      inicioX: evento.clientX,
      inicioY: evento.clientY,
      original: layout(),
      provisorio: layout(),
      base: { x: el.x, y: el.y, width: el.width, height: el.height }
    };
    noPaginas.setPointerCapture(evento.pointerId);
    desenhar();
  });

  noPaginas.addEventListener("pointermove", function (evento) {
    if (!arrasto) {
      return;
    }
    var dx = Geo.paraDocumento(evento.clientX - arrasto.inicioX, escala());
    var dy = Geo.paraDocumento(evento.clientY - arrasto.inicioY, escala());
    var base = arrasto.base;
    var versao = config.layoutVersion;
    if (!arrasto.alca) {
      arrasto.provisorio = State.mover(arrasto.original, arrasto.id, base.x + dx, base.y + dy, versao);
    } else {
      var a = arrasto.alca;
      var x = base.x, y = base.y, largura = base.width, altura = base.height;
      if (a.indexOf("e") !== -1) { largura = base.width + dx; }
      if (a.indexOf("s") !== -1) { altura = base.height + dy; }
      if (a.indexOf("w") !== -1) { x = base.x + dx; largura = base.width - dx; }
      if (a.indexOf("n") !== -1) { y = base.y + dy; altura = base.height - dy; }
      var movido = State.mover(arrasto.original, arrasto.id, x, y, versao);
      arrasto.provisorio = State.redimensionar(
        movido, arrasto.id, Geo.dimensaoValida(largura), Geo.dimensaoValida(altura), versao
      );
    }
    Canvas.reposicionar(noPaginas, arrasto.provisorio, opcoesDeDesenho());
  });

  function terminarArrasto() {
    if (!arrasto) {
      return;
    }
    var resultado = arrasto.provisorio;
    var mexeu = resultado !== arrasto.original;
    arrasto = null;
    if (mexeu) {
      aplicar(resultado);
    } else {
      desenhar();
    }
  }

  noPaginas.addEventListener("pointerup", terminarArrasto);
  noPaginas.addEventListener("pointercancel", terminarArrasto);

  noArea.addEventListener("pointerdown", function (evento) {
    var dentro = evento.target.closest ? evento.target.closest("[data-id]") : null;
    if (dentro) {
      return;
    }
    if (estado.selecionado) {
      estado.selecionado = null;
      desenhar();
    }
  });

  // --- eventos: barra de ferramentas -----------------------------------------------------

  raiz.addEventListener("mousedown", function (evento) {
    // Nao roubar a selecao do bloco ao clicar num botao da barra.
    if (evento.target.closest && evento.target.closest("[data-cmd], [data-caixa] button, .te-fld")) {
      if (!evento.target.closest("input, select, textarea")) {
        evento.preventDefault();
        guardarSelecao();
      }
    }
  });

  raiz.addEventListener("click", function (evento) {
    var gatilho = evento.target.closest ? evento.target.closest("button[data-cmd]") : null;
    if (!gatilho || gatilho.disabled) {
      return;
    }
    var cmd = gatilho.dataset.cmd;
    var valor = gatilho.dataset.valor;

    switch (cmd) {
      case "undo": desfazer(false); break;
      case "redo": desfazer(true); break;
      case "bold": case "italic": case "underline": case "strikeThrough":
        if (!estiloEstruturalNaSelecao(
          ESTILO_DO_COMANDO[cmd][0], ESTILO_DO_COMANDO[cmd][1], true
        )) {
          executarNoBloco(cmd);
        }
        break;
      case "cor":
        if (!estiloEstruturalNaSelecao("color", valor)) {
          executarNoBloco("foreColor", valor);
        }
        break;
      case "realce":
        if (!estiloEstruturalNaSelecao("highlight", COR_DO_REALCE, true)) {
          executarNoBloco("hiliteColor", COR_DO_REALCE);
        }
        break;
      case "alinhar": alterarBloco({ align: valor }); break;
      case "lista": {
        var el = elementoAtivo();
        if (el) {
          guardarCursor();
          aplicar(Doc.alternarLista(layout(), el.id, valor));
          medirDepoisDeDesenhar(el.id);
        }
        break;
      }
      case "recuo": {
        var bloco = elementoAtivo();
        if (bloco) {
          guardarCursor();
          aplicar(Doc.recuar(layout(), bloco.id, valor === "mais" ? 1 : -1));
          medirDepoisDeDesenhar(bloco.id);
        }
        break;
      }
      case "link": abrirLink(); break;
      case "link-aplicar": aplicarLink(); break;
      case "link-remover": removerLink(); break;
      case "link-fechar": caixaLink.hidden = true; devolverSelecao(); break;
      case "imagem": inserirImagem(); break;
      case "qr": inserirQr(); break;
      case "tabela": inserirTabela(); break;
      case "linha": inserirLinha(); break;
      case "quebra": inserirQuebra(); break;
      case "assinatura": inserirAssinatura(); break;
      case "limpar": limparFormatacao(); break;
      case "html": abrirHtml(); break;
      case "html-aplicar": aplicarHtml(); break;
      case "html-fechar": caixaHtml.hidden = true; devolverSelecao(); break;
      default: break;
    }
  });

  raiz.addEventListener("change", function (evento) {
    var seletor = evento.target.closest ? evento.target.closest("select[data-cmd]") : null;
    if (!seletor) {
      return;
    }
    var cmd = seletor.dataset.cmd;
    var valor = seletor.value;
    if (cmd === "estilo") {
      var el = elementoAtivo();
      if (el) {
        guardarCursor();
        aplicar(Doc.aplicarEstiloDoBloco(layout(), el.id, valor));
        medirDepoisDeDesenhar(el.id);
      }
    } else if (cmd === "fonte") {
      if (!estiloEstruturalNaSelecao("font_family", valor)) {
        estiloDeSelecaoOuBloco("fontName", Runs.cssDaFamilia(valor), "font_family", valor);
      }
    } else if (cmd === "tamanho") {
      var pt = parseFloat(valor);
      var indice = null;
      Object.keys(Runs.TAMANHOS).forEach(function (n) {
        if (Runs.TAMANHOS[n] === pt) { indice = n; }
      });
      if (estiloEstruturalNaSelecao("font_size", pt)) {
        return;
      }
      if (indice === null) {
        alterarBloco({ font_size: pt });
      } else {
        estiloDeSelecaoOuBloco("fontSize", indice, "font_size", pt);
      }
    } else if (cmd === "entrelinha") {
      alterarBloco({ line_height: parseFloat(valor) });
    }
  });

  // --- eventos: cabecalho, abas, paineis --------------------------------------------------

  raiz.addEventListener("click", function (evento) {
    var gatilho = evento.target.closest ? evento.target.closest("[data-acao]") : null;
    if (!gatilho) {
      return;
    }
    var acao = gatilho.dataset.acao;
    if (acao === "salvar") {
      salvar();
    } else if (acao === "descartar") {
      descartar();
    } else if (acao === "visualizar") {
      visualizar();
    } else if (acao === "restaurar") {
      restaurar();
    } else if (acao === "zoom-mais") {
      estado.zoom = Geo.limitarZoom(estado.zoom + 0.1);
      guardarCursor();
      desenhar();
    } else if (acao === "zoom-menos") {
      estado.zoom = Geo.limitarZoom(estado.zoom - 0.1);
      guardarCursor();
      desenhar();
    } else if (acao === "campo-rapido") {
      estado.aba = "campos";
      raiz.dataset.aba = "campos";
      if (noBusca) { noBusca.focus(); }
    }
  });

  raiz.addEventListener("click", function (evento) {
    var aba = evento.target.closest ? evento.target.closest("[data-aba]") : null;
    if (!aba || !aba.dataset.aba) {
      return;
    }
    estado.aba = aba.dataset.aba;
    raiz.dataset.aba = estado.aba;
    var abas = raiz.querySelectorAll("[data-aba]");
    for (var i = 0; i < abas.length; i += 1) {
      abas[i].classList.toggle("is-ativa", abas[i].dataset.aba === estado.aba);
      abas[i].setAttribute("aria-selected", abas[i].dataset.aba === estado.aba ? "true" : "false");
    }
  });

  if (noBusca) {
    noBusca.addEventListener("input", function () {
      estado.filtro = noBusca.value.trim();
      atualizarLaterais();
    });
  }

  for (var e = 0; e < nosExemplo.length; e += 1) {
    nosExemplo[e].addEventListener("change", function (evento) {
      estado.exemplo = evento.target.checked;
      guardarCursor();
      desenhar();
    });
  }

  if (noIdioma) {
    noIdioma.addEventListener("change", function () {
      if (!config.editable) {
        noIdioma.value = estado.language;
        return;
      }
      estado.language = noIdioma.value;
      estado.sujo = true;
      atualizarBotoes();
    });
  }

  if (noMargens) {
    noMargens.addEventListener("change", function () {
      if (!config.editable || noMargens.value === "atual") {
        return;
      }
      var escolhida = null;
      (config.margins || []).forEach(function (op) {
        if (op.key === noMargens.value) { escolhida = op; }
      });
      if (!escolhida) {
        return;
      }
      guardarCursor();
      aplicar(Doc.aplicarMargem(layout(), pagina, escolhida.pt));
    });
  }

  if (noFaixa) {
    noFaixa.addEventListener("change", function () {
      if (!config.editable || !config.flagStripe) {
        return;
      }
      var ligar = noFaixa.checked;
      proximosIds(ligar ? config.flagStripe.colors.length : 0).then(function (ids) {
        guardarCursor();
        aplicar(Doc.alternarFaixa(layout(), ligar, config.flagStripe, ids));
      });
    });
  }

  if (noNumeracao) {
    noNumeracao.addEventListener("change", function () {
      if (!config.editable) {
        return;
      }
      guardarCursor();
      aplicar(Doc.comOpcoes(layout(), { page_numbers: noNumeracao.checked }));
    });
  }

  // --- teclado global ------------------------------------------------------------------------

  document.addEventListener("keydown", function (evento) {
    if (evento.target.matches("input, textarea, select, [contenteditable='true']")) {
      return;
    }
    var meta = evento.ctrlKey || evento.metaKey;
    var tecla = evento.key;

    if (meta && tecla.toLowerCase() === "z" && !evento.shiftKey) {
      evento.preventDefault();
      desfazer(false);
    } else if (meta && (tecla.toLowerCase() === "y" || (tecla.toLowerCase() === "z" && evento.shiftKey))) {
      evento.preventDefault();
      desfazer(true);
    } else if (meta && tecla.toLowerCase() === "s") {
      evento.preventDefault();
      salvar();
    } else if (tecla === "Escape") {
      if (caixaLink) { caixaLink.hidden = true; }
      if (caixaHtml) { caixaHtml.hidden = true; }
      estado.selecionado = null;
      desenhar();
    } else if ((tecla === "Delete" || tecla === "Backspace") && estado.selecionado && config.editable) {
      evento.preventDefault();
      executarAcao("remover");
    } else if (estado.selecionado && config.editable && tecla.indexOf("Arrow") === 0) {
      evento.preventDefault();
      var passo = evento.shiftKey ? 0.5 : 5;
      var el = State.obter(layout(), estado.selecionado);
      if (!el) {
        return;
      }
      var dx = tecla === "ArrowLeft" ? -passo : tecla === "ArrowRight" ? passo : 0;
      var dy = tecla === "ArrowUp" ? -passo : tecla === "ArrowDown" ? passo : 0;
      aplicar(State.mover(layout(), estado.selecionado, el.x + dx, el.y + dy, config.layoutVersion));
    }
  });

  // --- salvar, descartar, visualizar, restaurar -----------------------------------------------

  function corpoParaSalvar() {
    return { layout: layout(), language: estado.language };
  }

  function salvar() {
    if (!config.editable) {
      return;
    }
    if (estado.ativo) {
      sincronizarBloco();
    }
    avisar("Salvando…", false);
    Api.salvar(document, config.saveUrl, layout(), { language: estado.language }).then(function (resultado) {
      if (resultado.ok) {
        estado.sujo = false;
        estado.salvo = layout();
        estado.languageSalvo = resultado.dados.language || estado.language;
        atualizarBotoes();
        avisar("Salvo — " + resultado.dados.elementos + " elemento(s).", false);
      } else {
        avisar(Api.mensagemDeErro(resultado), true);
      }
    });
  }

  /*
   * "Descartar" SAI do editor sem salvar.
   *
   * Com alteracao pendente, pergunta antes -- e a unica porta por onde
   * se perde trabalho, entao ela avisa -- e joga fora o que nao foi
   * salvo ANTES de sair: o que ficou gravado no banco continua
   * gravado, o que estava so na tela vai embora. Sem alteracao
   * pendente nao ha o que perguntar: e so a saida.
   *
   * O que ele NAO faz: salvar, e recarregar a pagina fingindo descarte.
   * Por isso o estado da sessao distingue tres coisas -- o que esta
   * salvo (`estado.salvo`), o que esta na tela (`layout()`) e se ha
   * diferenca entre os dois (`estado.sujo`).
   */
  function descartar() {
    if (estado.sujo && !window.confirm(
      "Sair sem salvar? As alterações feitas desde o último salvamento serão perdidas."
    )) {
      return;
    }
    estado.historico = State.criarHistorico(estado.salvo);
    estado.language = estado.languageSalvo;
    estado.sujo = false;
    estado.selecionado = null;
    estado.ativo = null;
    estado.cursor = null;
    sair();
  }

  /*
   * Deixa a tela pela URL de volta. `saindo` desliga o aviso de saida:
   * quem clicou em "Descartar" ja respondeu a pergunta, e perguntar
   * duas vezes e o tipo de zelo que so atrapalha.
   */
  function sair() {
    saindo = true;
    window.location.href = config.backUrl || voltarUrl();
  }

  function voltarUrl() {
    var link = raiz.querySelector(".te-voltar");
    return link ? link.getAttribute("href") : "/";
  }

  function visualizar() {
    if (!formPrevia) {
      return;
    }
    if (estado.ativo) {
      sincronizarBloco();
    }
    formPrevia.querySelector("[name='layout']").value = JSON.stringify(corpoParaSalvar().layout);
    formPrevia.querySelector("[name='exemplo']").value = estado.exemplo ? "1" : "0";
    formPrevia.submit();
  }

  function restaurar() {
    if (!layoutPadrao || !config.editable) {
      return;
    }
    if (!window.confirm("Restaurar o modelo padrão? O conteúdo atual do editor será substituído (é preciso salvar para valer).")) {
      return;
    }
    estado.selecionado = null;
    estado.ativo = null;
    estado.cursor = null;
    var padrao = State.normalizar(State.clonar(layoutPadrao), config.layoutVersion);
    if (layoutPadrao.document) {
      padrao.document = State.clonar(layoutPadrao.document);
    }
    aplicar(padrao);
  }

  /*
   * Fechar a aba, recarregar ou clicar em "Voltar" com alteracao
   * pendente pede confirmacao ao navegador -- a protecao padrao, que
   * nao impede navegacao nenhuma. Sair por "Descartar" nao pergunta de
   * novo (`saindo`).
   */
  window.addEventListener("beforeunload", function (evento) {
    if (estado.sujo && config.editable && !saindo) {
      evento.preventDefault();
      evento.returnValue = "";
    }
  });

  // --- arranque -------------------------------------------------------------------------------

  if (celular.addEventListener) {
    celular.addEventListener("change", function () {
      guardarCursor();
      desenhar();
    });
  }

  raiz.dataset.aba = estado.aba;

  function ajustarZoomInicial() {
    var disponivel = noArea.clientWidth;
    var cabe = Geo.zoomParaCaber(disponivel, larguraDaPagina * Canvas.PX_POR_PT, 44);
    estado.zoom = Math.min(ZOOM_INICIAL, Math.max(Geo.ZOOM_INICIAL_MINIMO, cabe));
    desenhar();
  }

  desenhar();
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(ajustarZoomInicial);
  } else {
    ajustarZoomInicial();
  }
})();
