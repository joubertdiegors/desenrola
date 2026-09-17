/*
 * Desenha o layout como DOM: a folha A4 (ou as folhas, quando ha
 * quebra de pagina) com cada elemento na sua coordenada -- e, no
 * celular, o mesmo documento como um cartao corrido (Etapa 3.7).
 *
 * SEGURANCA
 * ---------
 * Nada de innerHTML com conteudo do documento. Todo texto vai por
 * textContent e todo no e criado com createElement. O conteudo vem de um
 * administrador, mas "veio de alguem em quem confio" nunca foi defesa
 * contra XSS armazenado.
 *
 * BLOCOS DE TEXTO SAO EDITAVEIS NO LUGAR
 * --------------------------------------
 * Um `text`/`rich_text` vira um `contenteditable` posicionado onde o
 * elemento esta, com os trechos desenhados por `runs.js`; a celula de
 * uma tabela, o mesmo. O que fica gravado continua sendo o conteudo
 * ESTRUTURAL -- quem le o DOM de volta e `TERuns.serializar`, chamado
 * pelo editor a cada edicao.
 *
 * CAMPOS DINAMICOS
 * ----------------
 * Um campo aparece como um chip `[Grupo · Rótulo]` (ou, com "Ver com
 * dados de exemplo", como o valor de amostra). Isso e APRESENTACAO: o
 * que fica gravado continua sendo `{"kind": "field", "source": ...}`.
 *
 * A escala (px por pt, ja com o zoom) multiplica tudo na hora de
 * desenhar e nao encosta nos dados.
 */
(function (root, factory) {
  var api = factory(
    typeof require === "function" ? require("./runs.js") : root.TERuns,
    typeof require === "function" ? require("./document.js") : root.TEDocument
  );
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.TECanvas = api;
  }
})(typeof self !== "undefined" ? self : this, function (Runs, Doc) {
  "use strict";

  // 1pt = 1/72 pol; a tela desenha a 96 px por polegada. A folha A4
  // (595.28pt) tem 794px a 100% -- os 794px do arquivo de design.
  var PX_POR_PT = 96 / 72;

  var PESOS = { regular: "400", bold: "700" };
  var ALCAS = ["nw", "ne", "sw", "se", "n", "s", "e", "w"];
  var GRAFICOS = { image: 1, qr_code: 1, line: 1, rectangle: 1 };

  function criarNo(doc, tag, classe) {
    var no = doc.createElement(tag);
    if (classe) {
      no.className = classe;
    }
    return no;
  }

  /* Um indice `referencia -> rotulo` a partir do registro de fontes. */
  function indiceDeCampos(fontes) {
    var indice = {};
    (fontes || []).forEach(function (grupo) {
      (grupo.fields || []).forEach(function (campo) {
        indice[campo.reference] = grupo.label + " · " + campo.label;
      });
    });
    return indice;
  }

  /*
   * O texto que representa um bloco de conteudo na TELA. O dado gravado
   * nao muda; isto e so o que a pessoa le enquanto desenha.
   */
  function textoDoConteudo(bloco, campos) {
    return Runs.textoPlano(Runs.trechosDe(bloco), campos);
  }

  function estiloDeTexto(props, escala) {
    var p = props || {};
    var e = escala || PX_POR_PT;
    return {
      fontFamily: Runs.cssDaFamilia(p.font_family || "LiberationSans"),
      fontSize: Number(p.font_size || 11) * e + "px",
      fontWeight: PESOS[p.font_weight] || "400",
      fontStyle: p.font_style === "italic" ? "italic" : "normal",
      textDecoration:
        p.text_decoration && p.text_decoration !== "none" ? p.text_decoration : "none",
      color: p.color || "#000000",
      textAlign: p.align || "left",
      lineHeight: String(p.line_height || 1.25),
      letterSpacing: Number(p.letter_spacing || 0) * e + "px",
      whiteSpace: p.white_space === "nowrap" ? "nowrap" : "pre-wrap"
    };
  }

  function aplicar(no, estilo) {
    Object.keys(estilo).forEach(function (chave) {
      no.style[chave] = estilo[chave];
    });
  }

  function caixaEmPixels(props, escala) {
    var c = props || {};
    return (
      Number(c.top || 0) * escala + "px " +
      Number(c.right || 0) * escala + "px " +
      Number(c.bottom || 0) * escala + "px " +
      Number(c.left || 0) * escala + "px"
    );
  }

  // --- texto ---------------------------------------------------------------

  function desenharBlocoDeTexto(doc, no, elemento, opcoes) {
    var escala = opcoes.escala;
    var props = elemento.properties || {};
    var recuo = Number(props.indent || 0);
    if (props.list_marker && recuo <= 0) {
      recuo = Doc.PASSO_DO_RECUO;
    }
    var texto = estiloDeTexto(props, escala);
    // O alinhamento vertical desloca o bloco dentro da caixa.
    no.style.display = "flex";
    no.style.flexDirection = "column";
    no.style.justifyContent =
      props.vertical_align === "middle" ? "center"
        : props.vertical_align === "bottom" ? "flex-end" : "flex-start";
    if (props.padding) {
      no.style.padding = caixaEmPixels(props.padding, escala);
    }

    if (props.list_marker) {
      var marcador = criarNo(doc, "span", "te-marcador");
      marcador.setAttribute("contenteditable", "false");
      marcador.textContent = props.list_marker;
      aplicar(marcador, texto);
      marcador.style.textAlign = "left";
      marcador.style.left = Number((props.padding || {}).left || 0) * escala + "px";
      marcador.style.top = Number((props.padding || {}).top || 0) * escala + "px";
      no.appendChild(marcador);
    }

    var bloco = criarNo(doc, "div", "te-bloco");
    bloco.setAttribute("contenteditable", opcoes.editavel ? "true" : "false");
    bloco.setAttribute("spellcheck", "false");
    bloco.setAttribute("role", "textbox");
    bloco.setAttribute("aria-label", opcoes.rotuloDoBloco || "Bloco de texto");
    bloco.dataset.bloco = elemento.id;
    aplicar(bloco, texto);
    bloco.style.paddingLeft = recuo * escala + "px";
    Runs.desenhar(doc, bloco, props.content, {
      rotulos: opcoes.campos, exemplo: opcoes.exemplo, escala: escala
    });
    var incompleto = props.content && props.content.kind === "field" && !props.content.source;
    if (incompleto) {
      no.classList.add("is-incompleto");
    }
    no.appendChild(bloco);
  }

  // --- tabela --------------------------------------------------------------

  function desenharTabela(doc, no, elemento, opcoes) {
    var escala = opcoes.escala;
    var props = elemento.properties || {};
    var tabela = criarNo(doc, "table", "te-tabela");
    tabela.style.borderCollapse = "collapse";
    tabela.style.width = "100%";
    tabela.style.tableLayout = "fixed";

    // Na folha as colunas tem a largura medida; no cartao corrido
    // (celular) sao fracoes da tabela, que por sua vez cabe no cartao.
    var total = (props.columns || []).reduce(function (soma, c) {
      return soma + Number(c.width || 0);
    }, 0) || 1;
    var grupo = criarNo(doc, "colgroup");
    (props.columns || []).forEach(function (coluna) {
      var col = criarNo(doc, "col");
      col.style.width = opcoes.posicionar === false
        ? ((Number(coluna.width || 0) / total) * 100).toFixed(2) + "%"
        : Number(coluna.width || 0) * escala + "px";
      grupo.appendChild(col);
    });
    tabela.appendChild(grupo);

    var texto = estiloDeTexto(props, escala);
    var corpo = criarNo(doc, "tbody");
    (props.rows || []).forEach(function (linha, iLinha) {
      var tr = criarNo(doc, "tr");
      (linha.cells || []).forEach(function (celula, iCelula) {
        var coluna = (props.columns || [])[iCelula] || {};
        var td = criarNo(doc, "td");
        td.style.border =
          Number(props.border_width === undefined ? 0.5 : props.border_width) * escala +
          "px solid " + (props.border_color || "#000000");
        td.style.padding = caixaEmPixels(props.cell_padding, escala);
        td.style.height = Number(linha.min_height || 0) * escala + "px";
        td.style.boxSizing = "border-box";
        td.style.verticalAlign = "top";
        var area = criarNo(doc, "div", "te-celula");
        area.setAttribute("contenteditable", opcoes.editavel ? "true" : "false");
        area.setAttribute("spellcheck", "false");
        area.setAttribute("role", "textbox");
        area.setAttribute("aria-label", "Célula " + (iLinha + 1) + "," + (iCelula + 1));
        area.dataset.bloco = elemento.id;
        area.dataset.linha = String(iLinha);
        area.dataset.celula = String(iCelula);
        aplicar(area, texto);
        area.style.textAlign = celula.align || coluna.align || props.align || "left";
        area.style.fontWeight = celula.bold ? "700" : texto.fontWeight;
        Runs.desenhar(doc, area, celula.content, {
          rotulos: opcoes.campos, exemplo: opcoes.exemplo, escala: escala
        });
        td.appendChild(area);
        tr.appendChild(td);
      });
      corpo.appendChild(tr);
    });
    tabela.appendChild(corpo);
    no.appendChild(tabela);
  }

  // --- os demais ---------------------------------------------------------------

  function desenharImagem(doc, no, elemento, opcoes) {
    var props = elemento.properties || {};
    var origem = props.source || {};
    var asset = (opcoes.assets || []).filter(function (item) {
      return item.id === origem.asset_id;
    })[0];
    if (asset && asset.url) {
      var img = criarNo(doc, "img");
      img.src = asset.url;
      img.alt = "";
      img.draggable = false;
      img.style.width = "100%";
      img.style.height = "100%";
      img.style.objectFit = props.preserve_aspect_ratio
        ? props.fit === "cover" ? "cover" : "contain"
        : "fill";
      no.appendChild(img);
    } else {
      no.classList.add("is-incompleto");
      no.textContent = "Imagem não escolhida";
    }
  }

  function desenharQr(doc, no, elemento, opcoes) {
    var props = elemento.properties || {};
    var origem = props.source || {};
    no.classList.add("te-qr");
    var titulo = criarNo(doc, "span");
    titulo.textContent = "QR";
    no.appendChild(titulo);
    var legenda = criarNo(doc, "span", "te-qr-legenda");
    if (origem.kind === "field") {
      legenda.textContent = Runs.rotulo(origem.source, opcoes.campos);
    } else {
      legenda.textContent = origem.value ? "URL fixa" : "sem conteúdo";
      if (!origem.value) {
        no.classList.add("is-incompleto");
      }
    }
    no.appendChild(legenda);
  }

  function desenharLinha(no, elemento, escala) {
    var props = elemento.properties || {};
    // Uma linha e uma borda superior: a altura da caixa nao manda, a
    // espessura sim. Por isso `line` pode ter altura zero.
    no.style.borderTop =
      Number(props.thickness || 1) * escala + "px " +
      (props.style || "solid") + " " + (props.color || "#000000");
    no.style.height = Math.max(1, Number(props.thickness || 1) * escala) + "px";
  }

  function desenharRetangulo(no, elemento, escala) {
    var props = elemento.properties || {};
    no.style.border =
      Number(props.border_width || 0) * escala + "px " +
      (props.border_style || "solid") + " " + (props.border_color || "#000000");
    no.style.background = props.fill_color || "transparent";
    no.style.borderRadius = Number(props.radius || 0) * escala + "px";
  }

  function desenharQuebra(doc, no) {
    no.classList.add("te-quebra");
    var etiqueta = criarNo(doc, "span", "te-quebra-etiqueta");
    etiqueta.textContent = "Quebra de página";
    no.appendChild(etiqueta);
  }

  /*
   * Constroi o no de um elemento.
   * `opcoes`: { escala, campos, exemplo, assets, selecionado, ativo,
   *             editavel, posicionar (true no modo pagina) }
   */
  function desenharElemento(doc, elemento, opcoes) {
    var escala = opcoes.escala || PX_POR_PT;
    var no = criarNo(doc, "div", "te-elemento te-" + elemento.type);
    no.dataset.id = elemento.id;
    no.dataset.tipo = elemento.type;

    if (opcoes.posicionar !== false) {
      no.style.position = "absolute";
      no.style.left = elemento.x * escala + "px";
      no.style.top = (Number(elemento.y) - (opcoes.deslocamento || 0)) * escala + "px";
      no.style.width = elemento.width * escala + "px";
      if (Doc.eTexto(elemento)) {
        no.style.minHeight = elemento.height * escala + "px";
      } else if (elemento.type !== "line") {
        no.style.height = elemento.height * escala + "px";
      }
    } else {
      no.style.position = "relative";
    }

    switch (elemento.type) {
      case "text":
      case "rich_text":
        desenharBlocoDeTexto(doc, no, elemento, Object.assign({}, opcoes, { escala: escala }));
        break;
      case "number": {
        var texto = estiloDeTexto(elemento.properties, escala);
        aplicar(no, texto);
        no.textContent = textoDoConteudo((elemento.properties || {}).content, opcoes.campos);
        break;
      }
      case "image":
        desenharImagem(doc, no, elemento, opcoes);
        break;
      case "qr_code":
        desenharQr(doc, no, elemento, opcoes);
        break;
      case "line":
        desenharLinha(no, elemento, escala);
        break;
      case "rectangle":
        desenharRetangulo(no, elemento, escala);
        break;
      case "table":
        desenharTabela(doc, no, elemento, Object.assign({}, opcoes, { escala: escala }));
        break;
      case "page_break":
        desenharQuebra(doc, no);
        break;
      default:
        no.textContent = elemento.type;
    }

    if (opcoes.selecionado === elemento.id) {
      no.classList.add("is-selecionado");
      if (opcoes.editavel && GRAFICOS[elemento.type] && opcoes.posicionar !== false) {
        ALCAS.forEach(function (posicao) {
          var alca = criarNo(doc, "span", "te-alca te-alca-" + posicao);
          alca.dataset.alca = posicao;
          no.appendChild(alca);
        });
      }
    }
    if (opcoes.ativo === elemento.id) {
      no.classList.add("is-ativo");
    }
    if (!Doc.eTexto(elemento) && elemento.type !== "table") {
      no.tabIndex = 0;
      no.setAttribute("role", "button");
      no.setAttribute("aria-label", elemento.type);
    }
    return no;
  }

  // --- a folha ---------------------------------------------------------------

  function esvaziar(alvo) {
    while (alvo.firstChild) {
      alvo.removeChild(alvo.firstChild);
    }
  }

  /*
   * Modo PAGINA: uma folha por pagina do documento, cada elemento na
   * coordenada dele. A ordem de insercao e a ordem da lista -- que E
   * a ordem de camadas. Nao ha z-index: quem vem depois fica por cima.
   */
  function desenharPaginas(doc, alvo, layout, opcoes) {
    var escala = opcoes.escala || PX_POR_PT;
    var pagina = opcoes.pagina || {};
    var largura = Number(pagina.width) || 595.2756;
    var altura = Number(pagina.height) || 841.8898;
    var total = Doc.totalDePaginas(layout);
    var camadas = [];

    esvaziar(alvo);
    for (var k = 0; k < total; k += 1) {
      var folha = criarNo(doc, "div", "te-folha");
      folha.dataset.pagina = String(k + 1);
      folha.style.width = largura * escala + "px";
      folha.style.height = altura * escala + "px";
      var camada = criarNo(doc, "div", "te-camada");
      folha.appendChild(camada);
      alvo.appendChild(folha);
      camadas.push(camada);
    }

    ((layout && layout.elements) || []).forEach(function (elemento) {
      var k = Doc.paginaDe(layout, elemento);
      var camada = camadas[Math.min(k, camadas.length - 1)];
      camada.appendChild(desenharElemento(doc, elemento, Object.assign({}, opcoes, {
        escala: escala, deslocamento: k * altura, posicionar: true
      })));
    });
    return alvo;
  }

  /*
   * Modo FLUXO (celular): o documento como cartao corrido. Cada linha
   * de leitura vira uma linha flexivel; um bloco de texto ocupa a
   * fracao da largura util que ocupa na folha.
   */
  function desenharFluxo(doc, alvo, layout, opcoes) {
    var escala = opcoes.escala || PX_POR_PT;
    var pagina = opcoes.pagina || {};
    var margemDoc = Doc.margem(layout);
    var margemEsq = margemDoc === null ? 0 : margemDoc;
    var larguraUtil = Math.max(1, (Number(pagina.width) || 595.2756) - 2 * margemEsq);

    esvaziar(alvo);
    Doc.linhasVisuais(layout).forEach(function (linha) {
      var no = criarNo(doc, "div", "te-fluxo-linha");
      linha.elementos.forEach(function (elemento) {
        var item = desenharElemento(doc, elemento, Object.assign({}, opcoes, {
          escala: escala, posicionar: false
        }));
        var fracao = Math.min(100, Math.max(8, (Number(elemento.width) / larguraUtil) * 100));
        if (Doc.eTexto(elemento) || elemento.type === "table") {
          item.style.flex = "0 1 " + fracao.toFixed(2) + "%";
          item.style.maxWidth = "100%";
        } else if (elemento.type === "page_break") {
          item.style.flex = "1 1 100%";
        } else if (elemento.type === "rectangle" || elemento.type === "line") {
          // Faixas e linhas acompanham a largura do cartao.
          item.style.flex = "0 1 " + fracao.toFixed(2) + "%";
          item.style.height = elemento.type === "line" ? "" : Number(elemento.height) * escala + "px";
        } else {
          item.style.width = Number(elemento.width) * escala + "px";
          item.style.height = Number(elemento.height) * escala + "px";
          item.style.flex = "0 0 auto";
        }
        no.appendChild(item);
      });
      alvo.appendChild(no);
    });
    return alvo;
  }

  function desenharLayout(doc, alvo, layout, opcoes) {
    var o = opcoes || {};
    if (o.modo === "fluxo") {
      return desenharFluxo(doc, alvo, layout, o);
    }
    return desenharPaginas(doc, alvo, layout, o);
  }

  /*
   * Atualiza SO a geometria dos nos ja desenhados (modo pagina): e o que
   * o refluxo usa depois de uma tecla, sem reconstruir o bloco em que o
   * cursor esta. Exige `querySelectorAll` (navegador).
   */
  function reposicionar(alvo, layout, opcoes) {
    var escala = opcoes.escala || PX_POR_PT;
    var altura = Number((opcoes.pagina || {}).height) || 841.8898;
    var porId = {};
    ((layout && layout.elements) || []).forEach(function (el) { porId[el.id] = el; });
    var nos = alvo.querySelectorAll("[data-id]");
    for (var i = 0; i < nos.length; i += 1) {
      var no = nos[i];
      var el = porId[no.dataset.id];
      if (!el) {
        continue;
      }
      var k = Doc.paginaDe(layout, el);
      no.style.left = el.x * escala + "px";
      no.style.top = (Number(el.y) - k * altura) * escala + "px";
      no.style.width = el.width * escala + "px";
      if (Doc.eTexto(el)) {
        no.style.minHeight = el.height * escala + "px";
      } else if (el.type !== "line") {
        no.style.height = el.height * escala + "px";
      }
    }
  }

  return {
    PX_POR_PT: PX_POR_PT,
    ALCAS: ALCAS,
    GRAFICOS: GRAFICOS,
    indiceDeCampos: indiceDeCampos,
    textoDoConteudo: textoDoConteudo,
    estiloDeTexto: estiloDeTexto,
    desenharElemento: desenharElemento,
    desenharLayout: desenharLayout,
    reposicionar: reposicionar
  };
});
