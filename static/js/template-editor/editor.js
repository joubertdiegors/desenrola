/*
 * Editor visual dos modelos da biblioteca -- orquestracao (Etapa 3.2).
 *
 * Toda a logica de dados esta em geometry.js, state.js, canvas.js e
 * properties.js, que sao puros e testados no Node. Este arquivo e a
 * casca: le o estado inicial, escuta eventos, chama aquelas funcoes e
 * redesenha. Se algo aqui parecer merecer um teste, provavelmente e
 * regra e deveria estar num dos outros modulos.
 *
 * Estado de sessao (selecao, zoom, historico, "tem alteracao por
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
  var Canvas = window.TECanvas;
  var Props = window.TEProperties;
  var Api = window.TEApi;

  function lerJson(id) {
    var no = document.getElementById(id);
    return no ? JSON.parse(no.textContent) : null;
  }

  var config = lerJson("te-config") || {};
  var pagina = lerJson("te-pagina") || {};
  var catalogo = lerJson("te-tipos") || [];
  var fontes = lerJson("te-fontes") || [];
  var camposPorReferencia = Canvas.indiceDeCampos(fontes);

  // Lista plana de referencias, para o seletor de campo do painel.
  var referencias = [];
  fontes.forEach(function (grupo) {
    (grupo.fields || []).forEach(function (campo) {
      referencias.push({
        reference: campo.reference,
        label: grupo.label + " · " + campo.label
      });
    });
  });

  var estado = {
    historico: State.criarHistorico(
      State.normalizar(lerJson("te-layout"), config.layoutVersion)
    ),
    ids: State.criarFilaDeIds(lerJson("te-ids") || []),
    selecionado: null,
    zoom: 1,
    sujo: false
  };

  var arrasto = null;

  function layout() {
    return State.atual(estado.historico);
  }

  /* O que esta na tela: durante um arrasto, o estado provisorio. */
  function layoutVisivel() {
    return arrasto ? arrasto.provisorio : layout();
  }

  /* Toda mudanca passa por aqui: um lugar so para historico e redesenho. */
  function aplicar(novoLayout) {
    estado.historico = State.registrar(estado.historico, novoLayout);
    estado.sujo = true;
    desenhar();
  }

  // --- nos da tela ---------------------------------------------------------

  var noPagina = raiz.querySelector("[data-pagina]");
  var noCamada = raiz.querySelector("[data-camada]");
  var noPainel = raiz.querySelector("[data-propriedades]");
  var noPaletaTipos = raiz.querySelector("[data-paleta-tipos]");
  var noPaletaFontes = raiz.querySelector("[data-paleta-fontes]");
  var noAviso = raiz.querySelector("[data-aviso]");
  var noZoom = raiz.querySelector("[data-zoom-valor]");
  var noEstado = raiz.querySelector("[data-estado]");

  // --- paleta, montada a partir dos registros ------------------------------

  function montarPaleta() {
    catalogo.forEach(function (tipo) {
      var botao = document.createElement("button");
      botao.type = "button";
      botao.className = "te-ferramenta";
      botao.textContent = tipo.label;
      botao.dataset.tipo = tipo.code;
      botao.disabled = !config.editable;
      botao.addEventListener("click", function () {
        inserirElemento(tipo.code);
      });
      noPaletaTipos.appendChild(botao);
    });

    fontes.forEach(function (grupo) {
      var bloco = document.createElement("details");
      bloco.className = "te-fonte";
      var titulo = document.createElement("summary");
      titulo.textContent = grupo.label;
      bloco.appendChild(titulo);
      (grupo.fields || []).forEach(function (campo) {
        var botao = document.createElement("button");
        botao.type = "button";
        botao.className = "te-ferramenta te-ferramenta-campo";
        botao.textContent = campo.label;
        botao.dataset.referencia = campo.reference;
        botao.disabled = !config.editable;
        botao.addEventListener("click", function () {
          inserirCampo(campo.reference);
        });
        bloco.appendChild(botao);
      });
      noPaletaFontes.appendChild(bloco);
    });
  }

  // --- insercao ------------------------------------------------------------

  function proximoId() {
    var id = State.proximoId(estado.ids, layout());
    if (id) {
      return Promise.resolve(id);
    }
    // A fila esgotou: o servidor gera outra -- nunca o navegador.
    return Api.pedirIds(document, config.idsUrl).then(function (novos) {
      State.reabastecer(estado.ids, novos);
      return State.proximoId(estado.ids, layout());
    });
  }

  function posicaoInicial() {
    // Num ponto visivel da pagina, escalonando para dois elementos
    // seguidos nao nascerem exatamente um sobre o outro.
    var quantos = (layout().elements || []).length;
    return { x: 72 + (quantos % 8) * 12, y: 72 + (quantos % 8) * 12 };
  }

  function inserirElemento(tipo) {
    if (!config.editable) {
      return;
    }
    proximoId().then(function (id) {
      if (!id) {
        avisar("Não foi possível obter um identificador para o elemento.", true);
        return;
      }
      var elemento = State.criarElemento(catalogo, tipo, id, posicaoInicial());
      estado.selecionado = id;
      aplicar(State.adicionar(layout(), elemento, config.layoutVersion));
    });
  }

  function inserirCampo(referencia) {
    if (!config.editable) {
      return;
    }
    proximoId().then(function (id) {
      if (!id) {
        avisar("Não foi possível obter um identificador para o elemento.", true);
        return;
      }
      // Elemento ESTRUTURAL: `{kind: "field", source: ...}`, nunca
      // "{{campo}}" dentro de um texto.
      var elemento = State.criarElementoDeCampo(
        catalogo, referencia, id, posicaoInicial()
      );
      estado.selecionado = id;
      aplicar(State.adicionar(layout(), elemento, config.layoutVersion));
    });
  }

  // --- desenho -------------------------------------------------------------

  function desenhar() {
    var doc = layoutVisivel();
    var largura = Number(pagina.width) || 595.2756;
    var altura = Number(pagina.height) || 841.8898;

    noPagina.style.width = largura * estado.zoom + "px";
    noPagina.style.height = altura * estado.zoom + "px";

    Canvas.desenharLayout(document, noCamada, doc, {
      zoom: estado.zoom,
      campos: camposPorReferencia,
      assets: [],
      selecionado: estado.selecionado,
      editavel: config.editable
    });

    if (noZoom) {
      noZoom.textContent = Math.round(estado.zoom * 100) + "%";
    }
    atualizarBotoes();
    desenharPainel();
  }

  function desenharPainel() {
    var elemento = estado.selecionado
      ? State.obter(layoutVisivel(), estado.selecionado)
      : null;

    Props.desenharPainel(document, noPainel, elemento, {
      editavel: config.editable,
      catalogo: catalogo,
      referencias: referencias,
      assets: [],
      modelo: [
        "Página: " + Math.round(Number(pagina.width) || 0) + " × " +
          Math.round(Number(pagina.height) || 0) + " " + (pagina.unit || "pt"),
        "Elementos: " + ((layout().elements || []).length)
      ],
      aoAlterarGeometria: function (chave, valor) {
        var mudanca = {};
        mudanca[chave] = chave === "width" || chave === "height"
          ? Geo.dimensaoValida(valor)
          : valor;
        aplicar(
          State.atualizar(layout(), estado.selecionado, mudanca, config.layoutVersion)
        );
      },
      aoAlterarPropriedade: function (nome, valor) {
        var props = {};
        props[nome] = valor;
        aplicar(
          State.atualizar(
            layout(), estado.selecionado, { properties: props }, config.layoutVersion
          )
        );
      },
      aoAcao: executarAcao
    });
  }

  function atualizarBotoes() {
    var desfazer = raiz.querySelector("[data-acao='desfazer']");
    var refazer = raiz.querySelector("[data-acao='refazer']");
    if (desfazer) {
      desfazer.disabled = !State.podeDesfazer(estado.historico);
    }
    if (refazer) {
      refazer.disabled = !State.podeRefazer(estado.historico);
    }
    if (noEstado) {
      noEstado.hidden = !estado.sujo;
      noEstado.textContent = "alterações não salvas";
    }
  }

  function avisar(texto, erro) {
    if (!noAviso) {
      return;
    }
    noAviso.textContent = texto;
    noAviso.classList.toggle("is-erro", !!erro);
    noAviso.hidden = false;
  }

  // --- acoes sobre o elemento selecionado ----------------------------------

  function executarAcao(acao) {
    var id = estado.selecionado;
    if (!id || !config.editable) {
      return;
    }
    var versao = config.layoutVersion;

    if (acao === "remover") {
      estado.selecionado = null;
      aplicar(State.remover(layout(), id, versao));
    } else if (acao === "duplicar") {
      proximoId().then(function (novo) {
        if (!novo) {
          return;
        }
        var resultado = State.duplicar(layout(), id, novo, versao);
        estado.selecionado = resultado.id;
        aplicar(resultado.layout);
      });
    } else if (acao === "topo") {
      aplicar(State.trazerParaFrente(layout(), id, versao));
    } else if (acao === "fundo") {
      aplicar(State.enviarParaTras(layout(), id, versao));
    } else if (acao === "frente") {
      aplicar(State.moverParaFrente(layout(), id, versao));
    } else if (acao === "tras") {
      aplicar(State.moverParaTras(layout(), id, versao));
    }
  }

  // --- selecao, arrasto e redimensionamento --------------------------------

  noCamada.addEventListener("pointerdown", function (evento) {
    var alvo = evento.target.closest("[data-id]");
    if (!alvo) {
      return;
    }
    estado.selecionado = alvo.dataset.id;

    if (!config.editable) {
      desenhar();
      return;
    }

    var elemento = State.obter(layout(), estado.selecionado);
    arrasto = {
      id: estado.selecionado,
      alca: evento.target.dataset ? evento.target.dataset.alca || null : null,
      inicioX: evento.clientX,
      inicioY: evento.clientY,
      // O estado de PARTIDA, intacto. Cada movimento recalcula a partir
      // dele, nunca do provisorio anterior -- acumular deslocamento
      // sobre deslocamento faria o elemento disparar tela afora.
      original: layout(),
      provisorio: layout(),
      base: {
        x: elemento.x, y: elemento.y, width: elemento.width, height: elemento.height
      }
    };
    noCamada.setPointerCapture(evento.pointerId);
    desenhar();
  });

  noCamada.addEventListener("pointermove", function (evento) {
    if (!arrasto) {
      return;
    }
    // O mouse mede pixels; o documento guarda pontos.
    var dx = Geo.paraDocumento(evento.clientX - arrasto.inicioX, estado.zoom);
    var dy = Geo.paraDocumento(evento.clientY - arrasto.inicioY, estado.zoom);
    var base = arrasto.base;
    var versao = config.layoutVersion;

    if (!arrasto.alca) {
      arrasto.provisorio = State.mover(
        arrasto.original, arrasto.id, base.x + dx, base.y + dy, versao
      );
    } else {
      var a = arrasto.alca;
      var x = base.x, y = base.y, largura = base.width, altura = base.height;
      if (a.indexOf("e") !== -1) { largura = base.width + dx; }
      if (a.indexOf("s") !== -1) { altura = base.height + dy; }
      if (a.indexOf("w") !== -1) { x = base.x + dx; largura = base.width - dx; }
      if (a.indexOf("n") !== -1) { y = base.y + dy; altura = base.height - dy; }
      var movido = State.mover(arrasto.original, arrasto.id, x, y, versao);
      arrasto.provisorio = State.redimensionar(
        movido, arrasto.id,
        Geo.dimensaoValida(largura), Geo.dimensaoValida(altura), versao
      );
    }
    desenhar();
  });

  function terminarArrasto() {
    if (!arrasto) {
      return;
    }
    var resultado = arrasto.provisorio;
    var mexeu = resultado !== arrasto.original;
    arrasto = null;
    // So registra se algo mudou: um clique para selecionar nao pode
    // gastar um passo de desfazer.
    if (mexeu) {
      aplicar(resultado);
    } else {
      desenhar();
    }
  }

  noCamada.addEventListener("pointerup", terminarArrasto);
  noCamada.addEventListener("pointercancel", terminarArrasto);

  noPagina.addEventListener("pointerdown", function (evento) {
    if (evento.target === noPagina || evento.target === noCamada) {
      estado.selecionado = null;
      desenhar();
    }
  });

  // --- barra de ferramentas ------------------------------------------------

  raiz.addEventListener("click", function (evento) {
    var gatilho = evento.target.closest("[data-acao]");
    if (!gatilho) {
      return;
    }
    var acao = gatilho.dataset.acao;

    if (acao === "desfazer") {
      estado.historico = State.desfazer(estado.historico);
      estado.sujo = true;
      desenhar();
    } else if (acao === "refazer") {
      estado.historico = State.refazer(estado.historico);
      estado.sujo = true;
      desenhar();
    } else if (acao === "zoom-mais") {
      estado.zoom = Geo.limitarZoom(estado.zoom + 0.1);
      desenhar();
    } else if (acao === "zoom-menos") {
      estado.zoom = Geo.limitarZoom(estado.zoom - 0.1);
      desenhar();
    } else if (acao === "zoom-caber") {
      estado.zoom = Geo.zoomParaCaber(
        noPagina.parentElement.clientWidth, Number(pagina.width)
      );
      desenhar();
    } else if (acao === "salvar") {
      salvar();
    }
  });

  // --- teclado -------------------------------------------------------------

  document.addEventListener("keydown", function (evento) {
    if (evento.target.matches("input, textarea, select")) {
      return;
    }
    var meta = evento.ctrlKey || evento.metaKey;
    var tecla = evento.key;

    if (meta && tecla.toLowerCase() === "z" && !evento.shiftKey) {
      evento.preventDefault();
      estado.historico = State.desfazer(estado.historico);
      estado.sujo = true;
      desenhar();
    } else if (meta && (tecla.toLowerCase() === "y" ||
               (tecla.toLowerCase() === "z" && evento.shiftKey))) {
      evento.preventDefault();
      estado.historico = State.refazer(estado.historico);
      estado.sujo = true;
      desenhar();
    } else if (meta && tecla.toLowerCase() === "s") {
      evento.preventDefault();
      salvar();
    } else if (tecla === "Escape") {
      estado.selecionado = null;
      desenhar();
    } else if ((tecla === "Delete" || tecla === "Backspace") &&
               estado.selecionado && config.editable) {
      evento.preventDefault();
      executarAcao("remover");
    } else if (estado.selecionado && config.editable && tecla.indexOf("Arrow") === 0) {
      evento.preventDefault();
      // Passo fino com Shift: o documento pede precisao decimal.
      var passo = evento.shiftKey ? 0.5 : 5;
      var elemento = State.obter(layout(), estado.selecionado);
      var dx = tecla === "ArrowLeft" ? -passo : tecla === "ArrowRight" ? passo : 0;
      var dy = tecla === "ArrowUp" ? -passo : tecla === "ArrowDown" ? passo : 0;
      aplicar(
        State.mover(
          layout(), estado.selecionado,
          elemento.x + dx, elemento.y + dy, config.layoutVersion
        )
      );
    }
  });

  // --- salvamento ----------------------------------------------------------

  function salvar() {
    if (!config.editable) {
      return;
    }
    avisar("Salvando…", false);
    Api.salvar(document, config.saveUrl, layout()).then(function (resultado) {
      if (resultado.ok) {
        estado.sujo = false;
        atualizarBotoes();
        avisar("Salvo — " + resultado.dados.elementos + " elemento(s).", false);
      } else {
        avisar(Api.mensagemDeErro(resultado), true);
      }
    });
  }

  window.addEventListener("beforeunload", function (evento) {
    if (estado.sujo && config.editable) {
      evento.preventDefault();
      evento.returnValue = "";
    }
  });

  // --- arranque ------------------------------------------------------------

  montarPaleta();
  desenhar();

  function ajustarZoomInicial() {
    // Medir antes de o navegador resolver o layout da tela daria uma
    // largura pequena demais; dai o requestAnimationFrame.
    estado.zoom = Geo.zoomInicial(
      noPagina.parentElement.clientWidth, Number(pagina.width)
    );
    desenhar();
  }

  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(ajustarZoomInicial);
  } else {
    ajustarZoomInicial();
  }
})();
