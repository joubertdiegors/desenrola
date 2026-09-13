/*
 * Editor visual -- camada de interacao.
 *
 * Toda a logica de dados esta em document.js, history.js e geometry.js,
 * que sao puros e testados no Node. Este arquivo e a casca: escuta
 * eventos, desenha e chama aquelas funcoes. Se algo aqui parecer merecer
 * um teste, provavelmente e regra e deveria estar num dos outros tres.
 *
 * Estado da sessao (selecao, zoom, grade, historico) vive aqui e NAO vai
 * para o JSON: o documento guarda o desenho, nao como alguem o estava
 * olhando.
 */
(function () {
  "use strict";

  var raiz = document.querySelector("[data-editor]");
  if (!raiz) {
    return;
  }

  var Doc = window.EditorDocument;
  var Hist = window.EditorHistory;
  var Geo = window.EditorGeometry;
  var Render = window.EditorRender;

  function lerJson(id) {
    var no = document.getElementById(id);
    return no ? JSON.parse(no.textContent) : null;
  }

  var config = lerJson("editor-config");
  var campos = lerJson("editor-campos") || [];
  var assets = lerJson("editor-assets") || [];

  // Declarado antes de tudo porque `documentoVisivel()` o consulta.
  var arrasto = null;

  var estado = {
    historico: Hist.criar(Doc.desserializar(lerJson("editor-documento"))),
    selecionado: null,
    zoom: 1,
    grade: 12,
    mostrarGrade: true,
    snap: false,
    preview: false,
    sujo: false
  };

  function documento() {
    return Hist.atual(estado.historico);
  }

  /*
   * O documento que esta na tela.
   *
   * Durante um arrasto o desenho segue um estado PROVISORIO que nao entra
   * no historico -- senao cada pixel do movimento viraria um passo de
   * desfazer. So ao soltar o botao o resultado e registrado, como um
   * unico passo.
   */
  function documentoVisivel() {
    return arrasto ? arrasto.provisorio : documento();
  }

  /* Toda mudanca no documento passa por aqui: um lugar so para registrar
   * no historico, marcar como nao salvo e redesenhar. */
  function aplicar(novoDocumento) {
    estado.historico = Hist.registrar(estado.historico, novoDocumento);
    estado.sujo = true;
    desenhar();
  }

  // --- Elementos de tela ---------------------------------------------------

  var pagina = raiz.querySelector("[data-pagina]");
  var camada = raiz.querySelector("[data-camada]");
  var painel = raiz.querySelector("[data-propriedades]");
  var aviso = raiz.querySelector("[data-aviso]");
  var rotuloZoom = raiz.querySelector("[data-zoom-valor]");

  // --- Desenho -------------------------------------------------------------

  function desenhar() {
    var doc = documentoVisivel();
    pagina.style.width = doc.page.width * estado.zoom + "px";
    pagina.style.height = doc.page.height * estado.zoom + "px";
    pagina.classList.toggle("com-grade", estado.mostrarGrade && !estado.preview);
    pagina.style.setProperty("--grade", estado.grade * estado.zoom + "px");

    Render.desenharDocumento(document, camada, doc, {
      zoom: estado.zoom,
      campos: campos,
      assets: assets,
      modo: estado.preview ? "preview" : "editor"
    });

    if (!estado.preview && estado.selecionado) {
      var no = camada.querySelector('[data-id="' + estado.selecionado + '"]');
      if (no) {
        no.classList.add("is-selecionado");
        if (config.editable) {
          adicionarAlcas(no);
        }
      }
    }

    if (rotuloZoom) {
      rotuloZoom.textContent = Math.round(estado.zoom * 100) + "%";
    }
    atualizarBotoes();
    desenharPainel();
  }

  var ALCAS = ["nw", "ne", "sw", "se", "n", "s", "e", "w"];

  function adicionarAlcas(no) {
    ALCAS.forEach(function (posicao) {
      var alca = document.createElement("span");
      alca.className = "ed-alca ed-alca-" + posicao;
      alca.dataset.alca = posicao;
      no.appendChild(alca);
    });
  }

  function atualizarBotoes() {
    var desfazer = raiz.querySelector("[data-acao='desfazer']");
    var refazer = raiz.querySelector("[data-acao='refazer']");
    if (desfazer) {
      desfazer.disabled = !Hist.podeDesfazer(estado.historico);
    }
    if (refazer) {
      refazer.disabled = !Hist.podeRefazer(estado.historico);
    }
    raiz.classList.toggle("is-preview", estado.preview);
  }

  // --- Painel de propriedades ---------------------------------------------

  function campoNumero(rotulo, valor, aoMudar, passo) {
    var bloco = document.createElement("label");
    bloco.className = "ed-campo";
    var nome = document.createElement("span");
    nome.textContent = rotulo;
    var entrada = document.createElement("input");
    entrada.type = "number";
    entrada.className = "input";
    // Passo fino: o documento oficial e medido com casas decimais e o
    // editor precisa alcancar esses valores pelo teclado.
    entrada.step = passo === undefined ? "0.01" : passo;
    entrada.value = valor;
    entrada.disabled = !config.editable;
    entrada.addEventListener("change", function () {
      aoMudar(parseFloat(entrada.value));
    });
    bloco.appendChild(nome);
    bloco.appendChild(entrada);
    return bloco;
  }

  function campoTexto(rotulo, valor, aoMudar, multilinha) {
    var bloco = document.createElement("label");
    bloco.className = "ed-campo";
    var nome = document.createElement("span");
    nome.textContent = rotulo;
    var entrada = document.createElement(multilinha ? "textarea" : "input");
    entrada.className = "input";
    entrada.value = valor || "";
    entrada.disabled = !config.editable;
    if (multilinha) {
      entrada.rows = 4;
    }
    entrada.addEventListener("change", function () {
      aoMudar(entrada.value);
    });
    bloco.appendChild(nome);
    bloco.appendChild(entrada);
    return bloco;
  }

  function campoEscolha(rotulo, valor, opcoes, aoMudar) {
    var bloco = document.createElement("label");
    bloco.className = "ed-campo";
    var nome = document.createElement("span");
    nome.textContent = rotulo;
    var selecao = document.createElement("select");
    selecao.className = "input";
    selecao.disabled = !config.editable;
    opcoes.forEach(function (opcao) {
      var item = document.createElement("option");
      item.value = opcao.value;
      item.textContent = opcao.label;
      if (opcao.value === valor) {
        item.selected = true;
      }
      selecao.appendChild(item);
    });
    selecao.addEventListener("change", function () {
      aoMudar(selecao.value);
    });
    bloco.appendChild(nome);
    bloco.appendChild(selecao);
    return bloco;
  }

  function campoBooleano(rotulo, valor, aoMudar) {
    var bloco = document.createElement("label");
    bloco.className = "ed-campo ed-campo-check";
    var entrada = document.createElement("input");
    entrada.type = "checkbox";
    entrada.checked = !!valor;
    entrada.disabled = !config.editable;
    entrada.addEventListener("change", function () {
      aoMudar(entrada.checked);
    });
    var nome = document.createElement("span");
    nome.textContent = rotulo;
    bloco.appendChild(entrada);
    bloco.appendChild(nome);
    return bloco;
  }

  function opcoesSimples(lista) {
    return lista.map(function (valor) {
      return { value: valor, label: valor };
    });
  }

  function desenharPainel() {
    while (painel.firstChild) {
      painel.removeChild(painel.firstChild);
    }

    var elemento = estado.selecionado
      ? Doc.encontrar(documentoVisivel(), estado.selecionado)
      : null;
    if (!elemento) {
      var vazio = document.createElement("p");
      vazio.className = "ed-vazio";
      vazio.textContent = "Selecione um elemento para ver suas propriedades.";
      painel.appendChild(vazio);
      return;
    }

    var titulo = document.createElement("h3");
    titulo.textContent = elemento.type;
    painel.appendChild(titulo);

    // Geometria: sempre editavel por numero, nunca so pelo mouse.
    var geo = document.createElement("div");
    geo.className = "ed-grade-2";
    ["x", "y", "width", "height"].forEach(function (chave) {
      geo.appendChild(
        campoNumero(chave.toUpperCase(), elemento[chave], function (valor) {
          if (!isNaN(valor)) {
            var mudanca = {};
            mudanca[chave] = valor;
            aplicar(Doc.atualizarGeometria(documento(), elemento.id, mudanca));
          }
        })
      );
    });
    painel.appendChild(geo);
    painel.appendChild(
      campoNumero("Z", elemento.z_index, function (valor) {
        if (!isNaN(valor)) {
          aplicar(Doc.atualizarGeometria(documento(), elemento.id, { z_index: valor }));
        }
      }, "1")
    );

    var props = elemento.properties || {};
    function mudarProp(chave) {
      return function (valor) {
        var mudanca = {};
        mudanca[chave] = valor;
        aplicar(Doc.atualizarPropriedades(documento(), elemento.id, mudanca));
      };
    }

    if (
      elemento.type === "text" ||
      elemento.type === "field" ||
      elemento.type === "rich_text"
    ) {
      if (elemento.type === "text") {
        painel.appendChild(campoTexto("Conteúdo", props.content, mudarProp("content"), true));
      } else if (elemento.type === "rich_text") {
        painel.appendChild(editorDeTrechos(elemento, props));
        painel.appendChild(
          campoNumero("Entrelinha (pt)", props.leading, mudarProp("leading"), "0.1")
        );
        painel.appendChild(
          campoNumero("Máx. linhas", props.max_lines, function (valor) {
            mudarProp("max_lines")(Math.max(1, Math.round(valor) || 1));
          }, "1")
        );
        painel.appendChild(
          campoNumero("Fonte mínima", props.min_font_size, mudarProp("min_font_size"), "0.5")
        );
      } else {
        // Escolher de uma lista, nao digitar uma referencia arbitraria.
        painel.appendChild(
          campoEscolha(
            "Campo",
            props.field,
            [{ value: "", label: "— escolher —" }].concat(
              campos.map(function (campo) {
                return { value: campo.key, label: campo.label };
              })
            ),
            mudarProp("field")
          )
        );
      }
      painel.appendChild(
        campoEscolha("Fonte", props.font_family, opcoesSimples(config.fontFamilies), mudarProp("font_family"))
      );
      painel.appendChild(campoNumero("Tamanho", props.font_size, mudarProp("font_size"), "0.1"));
      painel.appendChild(
        campoEscolha("Peso", props.font_weight, opcoesSimples(["regular", "bold"]), mudarProp("font_weight"))
      );
      painel.appendChild(campoBooleano("Itálico", props.italic, mudarProp("italic")));
      painel.appendChild(
        campoEscolha("Alinhamento", props.align, opcoesSimples(config.alignments), mudarProp("align"))
      );
      painel.appendChild(
        campoEscolha(
          "Vertical",
          props.vertical_align,
          opcoesSimples(["top", "middle", "bottom"]),
          mudarProp("vertical_align")
        )
      );
      painel.appendChild(campoTexto("Cor", props.color, mudarProp("color")));
      painel.appendChild(campoNumero("Entrelinha", props.line_height, mudarProp("line_height"), "0.05"));
      painel.appendChild(
        campoNumero("Espaço entre letras", props.letter_spacing, mudarProp("letter_spacing"), "0.05")
      );
      painel.appendChild(campoBooleano("Quebrar linha", props.wrap, mudarProp("wrap")));
      painel.appendChild(
        campoEscolha(
          "Transbordo",
          props.overflow,
          opcoesSimples(["clip", "shrink", "grow"]),
          mudarProp("overflow")
        )
      );
    }

    if (elemento.type === "image") {
      painel.appendChild(
        campoEscolha(
          "Imagem",
          props.asset_id,
          [{ value: 0, label: "— escolher —" }].concat(
            assets.map(function (asset) {
              return { value: asset.id, label: asset.label };
            })
          ),
          function (valor) {
            mudarProp("asset_id")(parseInt(valor, 10) || 0);
          }
        )
      );
      painel.appendChild(
        campoBooleano("Manter proporção", props.preserve_aspect_ratio, mudarProp("preserve_aspect_ratio"))
      );
    }

    if (elemento.type === "line") {
      painel.appendChild(campoNumero("Espessura", props.thickness, mudarProp("thickness"), "0.1"));
      painel.appendChild(campoTexto("Cor", props.color, mudarProp("color")));
    }

    if (elemento.type === "rect") {
      painel.appendChild(campoNumero("Borda", props.border_width, mudarProp("border_width"), "0.1"));
      painel.appendChild(campoTexto("Cor da borda", props.border_color, mudarProp("border_color")));
      painel.appendChild(campoTexto("Preenchimento", props.fill_color || "", function (valor) {
        mudarProp("fill_color")(valor ? valor : null);
      }));
      painel.appendChild(campoNumero("Raio", props.radius, mudarProp("radius"), "0.5"));
    }

    if (elemento.type === "qrcode") {
      painel.appendChild(campoTexto("Conteúdo", props.content, mudarProp("content"), true));
      painel.appendChild(
        campoEscolha(
          "Correção",
          props.error_correction,
          opcoesSimples(config.qrErrorLevels),
          mudarProp("error_correction")
        )
      );
    }

    if (elemento.type === "table") {
      painel.appendChild(campoNumero("Espaçamento", props.padding, mudarProp("padding"), "0.5"));
      painel.appendChild(campoNumero("Borda", props.border_width, mudarProp("border_width"), "0.1"));
      painel.appendChild(campoTexto("Cor da borda", props.border_color, mudarProp("border_color")));
      painel.appendChild(botao("Adicionar linha", function () {
        var linhas = (props.rows || []).slice();
        linhas.push({
          min_height: 18,
          cells: (props.columns || []).map(function () {
            return { content: "", align: "left", bold: false };
          })
        });
        mudarProp("rows")(linhas);
      }));
      painel.appendChild(botao("Adicionar coluna", function () {
        var colunas = (props.columns || []).slice();
        colunas.push({ width: 100, align: "left" });
        var linhas = (props.rows || []).map(function (linha) {
          return Object.assign({}, linha, {
            cells: linha.cells.concat([{ content: "", align: "left", bold: false }])
          });
        });
        aplicar(
          Doc.atualizarPropriedades(documento(), elemento.id, {
            columns: colunas,
            rows: linhas
          })
        );
      }));
      painel.appendChild(editorDeCelulas(elemento, props));
    }

    var acoes = document.createElement("div");
    acoes.className = "ed-acoes-elemento";
    acoes.appendChild(botao("Duplicar", function () {
      var resultado = Doc.duplicar(documento(), elemento.id);
      estado.selecionado = resultado.id;
      aplicar(resultado.documento);
    }));
    acoes.appendChild(botao("Para frente", function () {
      aplicar(Doc.trazerParaFrente(documento(), elemento.id));
    }));
    acoes.appendChild(botao("Para trás", function () {
      aplicar(Doc.enviarParaTras(documento(), elemento.id));
    }));
    acoes.appendChild(botao("Apagar", function () {
      aplicar(Doc.remover(documento(), elemento.id));
      estado.selecionado = null;
    }));
    painel.appendChild(acoes);
  }

  /*
   * Os trechos de um paragrafo misto.
   *
   * Trecho de texto fixo abre um campo de texto; trecho de campo abre o
   * seletor de campos. O tipo do trecho nao muda aqui -- trocar texto
   * por campo e o contrario seria reescrever a frase, e para isso a
   * pessoa apaga e refaz.
   */
  function editorDeTrechos(elemento, props) {
    var caixa = document.createElement("div");
    caixa.className = "ed-trechos";

    var titulo = document.createElement("h4");
    titulo.textContent = "Trechos";
    caixa.appendChild(titulo);

    function gravar(indice, mudanca) {
      var trechos = (props.runs || []).map(function (trecho, i) {
        return i === indice ? Object.assign({}, trecho, mudanca) : trecho;
      });
      aplicar(Doc.atualizarPropriedades(documento(), elemento.id, { runs: trechos }));
    }

    (props.runs || []).forEach(function (trecho, indice) {
      if (trecho.field !== undefined) {
        caixa.appendChild(
          campoEscolha(
            indice + 1 + " · campo",
            trecho.field,
            [{ value: "", label: "— escolher —" }].concat(
              campos.map(function (campo) {
                return { value: campo.key, label: campo.label };
              })
            ),
            function (valor) {
              gravar(indice, { field: valor });
            }
          )
        );
      } else {
        caixa.appendChild(
          campoTexto(indice + 1 + " · texto", trecho.text, function (valor) {
            gravar(indice, { text: valor });
          })
        );
      }
      caixa.appendChild(
        campoBooleano("negrito", trecho.bold, function (valor) {
          gravar(indice, { bold: valor });
        })
      );
    });

    return caixa;
  }

  function editorDeCelulas(elemento, props) {
    var caixa = document.createElement("div");
    caixa.className = "ed-celulas";
    (props.rows || []).forEach(function (linha, iLinha) {
      (linha.cells || []).forEach(function (celula, iCelula) {
        caixa.appendChild(
          campoTexto("L" + (iLinha + 1) + "C" + (iCelula + 1), celula.content, function (valor) {
            var linhas = (props.rows || []).map(function (l, i) {
              if (i !== iLinha) {
                return l;
              }
              return Object.assign({}, l, {
                cells: l.cells.map(function (c, j) {
                  return j === iCelula ? Object.assign({}, c, { content: valor }) : c;
                })
              });
            });
            aplicar(Doc.atualizarPropriedades(documento(), elemento.id, { rows: linhas }));
          })
        );
      });
    });
    return caixa;
  }

  function botao(rotulo, aoClicar) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn btn-ghost btn-sm";
    b.textContent = rotulo;
    b.disabled = !config.editable;
    b.addEventListener("click", aoClicar);
    return b;
  }

  // --- Selecao, arrasto e redimensionamento --------------------------------

  camada.addEventListener("pointerdown", function (evento) {
    if (estado.preview) {
      return;
    }
    var alvo = evento.target.closest("[data-id]");
    if (!alvo) {
      return;
    }
    // Cinto e suspensorio: o CSS ja tira a imagem de referencia do
    // caminho dos eventos, mas se ela chegar aqui por qualquer motivo,
    // nao vira selecao -- arrastar o fundo sem querer seria pior do que
    // nao poder mexer nele.
    var candidato = Doc.encontrar(documento(), alvo.dataset.id);
    if (candidato && candidato.properties && candidato.properties.is_base_reference) {
      return;
    }
    estado.selecionado = alvo.dataset.id;

    if (!config.editable) {
      desenhar();
      return;
    }

    var elemento = Doc.encontrar(documento(), estado.selecionado);
    arrasto = {
      id: estado.selecionado,
      alca: evento.target.dataset ? evento.target.dataset.alca || null : null,
      inicioX: evento.clientX,
      inicioY: evento.clientY,
      base: { x: elemento.x, y: elemento.y, width: elemento.width, height: elemento.height },
      // O estado de partida, intacto. Cada movimento recalcula a partir
      // DELE, nunca do provisorio anterior -- acumular deslocamento sobre
      // deslocamento faria o elemento disparar tela afora.
      original: documento(),
      provisorio: documento()
    };
    camada.setPointerCapture(evento.pointerId);
    desenhar();
  });

  camada.addEventListener("pointermove", function (evento) {
    if (!arrasto) {
      return;
    }
    var dx = Geo.pixelsParaPontos(evento.clientX - arrasto.inicioX, estado.zoom);
    var dy = Geo.pixelsParaPontos(evento.clientY - arrasto.inicioY, estado.zoom);
    var passo = estado.snap ? estado.grade : 0;
    var base = arrasto.base;
    var mudanca;

    if (!arrasto.alca) {
      mudanca = {
        x: Geo.encaixarNaGrade(base.x + dx, passo),
        y: Geo.encaixarNaGrade(base.y + dy, passo)
      };
    } else {
      var a = arrasto.alca;
      var x = base.x;
      var y = base.y;
      var largura = base.width;
      var altura = base.height;
      if (a.indexOf("e") !== -1) {
        largura = base.width + dx;
      }
      if (a.indexOf("s") !== -1) {
        altura = base.height + dy;
      }
      if (a.indexOf("w") !== -1) {
        x = base.x + dx;
        largura = base.width - dx;
      }
      if (a.indexOf("n") !== -1) {
        y = base.y + dy;
        altura = base.height - dy;
      }
      mudanca = {
        x: Geo.encaixarNaGrade(x, passo),
        y: Geo.encaixarNaGrade(y, passo),
        width: Math.max(0, Geo.encaixarNaGrade(largura, passo)),
        height: Math.max(0, Geo.encaixarNaGrade(altura, passo))
      };
    }

    arrasto.provisorio = Doc.atualizarGeometria(arrasto.original, arrasto.id, mudanca);
    desenhar();
  });

  function terminarArrasto() {
    if (!arrasto) {
      return;
    }
    var resultado = arrasto.provisorio;
    var mexeu = resultado !== arrasto.original;
    arrasto = null;
    // So registra se algo mudou de verdade: um clique para selecionar nao
    // pode gastar um passo de desfazer.
    if (mexeu) {
      aplicar(resultado);
    } else {
      desenhar();
    }
  }

  camada.addEventListener("pointerup", terminarArrasto);
  camada.addEventListener("pointercancel", terminarArrasto);

  pagina.addEventListener("pointerdown", function (evento) {
    if (evento.target === pagina || evento.target === camada) {
      estado.selecionado = null;
      desenhar();
    }
  });

  // --- Barra de ferramentas ------------------------------------------------

  raiz.addEventListener("click", function (evento) {
    var gatilho = evento.target.closest("[data-acao]");
    if (!gatilho) {
      return;
    }
    var acao = gatilho.dataset.acao;

    if (acao === "adicionar") {
      if (!config.editable) {
        return;
      }
      var elemento = Doc.criarElemento(gatilho.dataset.tipo, { x: 72, y: 72 });
      estado.selecionado = elemento.id;
      aplicar(Doc.adicionar(documento(), elemento));
    } else if (acao === "desfazer") {
      estado.historico = Hist.desfazer(estado.historico);
      desenhar();
    } else if (acao === "refazer") {
      estado.historico = Hist.refazer(estado.historico);
      desenhar();
    } else if (acao === "zoom-mais") {
      estado.zoom = Geo.clampZoom(estado.zoom + 0.1);
      desenhar();
    } else if (acao === "zoom-menos") {
      estado.zoom = Geo.clampZoom(estado.zoom - 0.1);
      desenhar();
    } else if (acao === "zoom-caber") {
      estado.zoom = Geo.zoomParaCaber(
        pagina.parentElement.clientWidth,
        documento().page.width
      );
      desenhar();
    } else if (acao === "grade") {
      estado.mostrarGrade = !estado.mostrarGrade;
      gatilho.setAttribute("aria-pressed", String(estado.mostrarGrade));
      desenhar();
    } else if (acao === "snap") {
      estado.snap = !estado.snap;
      gatilho.setAttribute("aria-pressed", String(estado.snap));
    } else if (acao === "preview") {
      estado.preview = !estado.preview;
      gatilho.setAttribute("aria-pressed", String(estado.preview));
      estado.selecionado = estado.preview ? null : estado.selecionado;
      desenhar();
    } else if (acao === "salvar") {
      salvar();
    }
  });

  document.addEventListener("keydown", function (evento) {
    if (evento.target.matches("input, textarea, select")) {
      return;
    }
    var meta = evento.ctrlKey || evento.metaKey;
    if (meta && evento.key.toLowerCase() === "z" && !evento.shiftKey) {
      evento.preventDefault();
      estado.historico = Hist.desfazer(estado.historico);
      desenhar();
    } else if (meta && (evento.key.toLowerCase() === "y" || (evento.key.toLowerCase() === "z" && evento.shiftKey))) {
      evento.preventDefault();
      estado.historico = Hist.refazer(estado.historico);
      desenhar();
    } else if (meta && evento.key.toLowerCase() === "s") {
      evento.preventDefault();
      salvar();
    } else if ((evento.key === "Delete" || evento.key === "Backspace") && estado.selecionado && config.editable) {
      evento.preventDefault();
      aplicar(Doc.remover(documento(), estado.selecionado));
      estado.selecionado = null;
    }
  });

  // --- Salvamento ----------------------------------------------------------

  function csrf() {
    var campo = document.querySelector("[name=csrfmiddlewaretoken]");
    return campo ? campo.value : "";
  }

  function mostrar(texto, erro) {
    if (!aviso) {
      return;
    }
    aviso.textContent = texto;
    aviso.classList.toggle("is-erro", !!erro);
    aviso.hidden = false;
  }

  function salvar() {
    if (!config.editable) {
      return;
    }
    mostrar("Salvando…", false);
    fetch(config.saveUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: Doc.serializar(documento())
    })
      .then(function (resposta) {
        return resposta.json().then(function (dados) {
          return { ok: resposta.ok, dados: dados };
        });
      })
      .then(function (resultado) {
        if (resultado.ok && resultado.dados.ok) {
          estado.sujo = false;
          mostrar("Salvo — " + resultado.dados.elementos + " elemento(s).", false);
        } else {
          mostrar(resultado.dados.error || "Não foi possível salvar.", true);
        }
      })
      .catch(function () {
        mostrar("Não foi possível salvar (falha de rede).", true);
      });
  }

  window.addEventListener("beforeunload", function (evento) {
    if (estado.sujo && config.editable) {
      evento.preventDefault();
      evento.returnValue = "";
    }
  });

  /*
   * Zoom inicial.
   *
   * Duas armadilhas aqui, as duas ja tendo mordido:
   *
   *   1. medir antes de o navegador resolver o grid da tela da uma
   *      largura pequena demais -- por isso a medicao acontece dentro de
   *      requestAnimationFrame, depois do layout;
   *   2. "caber" pode dar um zoom em que a pagina inteira tem 230px e
   *      cada campo fica com 5px de altura: tecnicamente visivel,
   *      inutilizavel na pratica. Dai o piso.
   */
  var ZOOM_INICIAL_MINIMO = 0.5;

  function ajustarZoomInicial() {
    var disponivel = pagina.parentElement.clientWidth;
    var cabe = Geo.zoomParaCaber(disponivel, documento().page.width);
    estado.zoom = Math.max(ZOOM_INICIAL_MINIMO, cabe);
    desenhar();
  }

  desenhar();
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(ajustarZoomInicial);
  } else {
    ajustarZoomInicial();
  }
})();
