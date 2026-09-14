/*
 * Desenha o layout como DOM: os oito tipos da Etapa 3.1.
 *
 * Editor estrutural dos modelos da biblioteca (Etapa 3.2).
 *
 * SEGURANCA
 * ---------
 * Nada de innerHTML com conteudo do documento. Todo texto vai por
 * textContent e todo no e criado com createElement. O conteudo vem de um
 * administrador, mas "veio de alguem em quem confio" nunca foi defesa
 * contra XSS armazenado.
 *
 * CAMPOS DINAMICOS
 * ----------------
 * No editor um campo aparece como `[Nome do convidado]` -- legivel para
 * quem desenha. Isso e APRESENTACAO: o que fica gravado continua sendo
 * `{"kind": "field", "source": "convidado.nome"}`, intacto. O rotulo vem
 * do registro de fontes entregue pelo servidor.
 *
 * O zoom multiplica tudo na hora de desenhar e nao encosta nos dados.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.TECanvas = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var PESOS = { regular: "400", bold: "700" };
  var ALCAS = ["nw", "ne", "sw", "se", "n", "s", "e", "w"];

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
    if (!bloco || typeof bloco !== "object") {
      return "";
    }
    if (bloco.kind === "text") {
      return bloco.value || "";
    }
    if (bloco.kind === "field") {
      var rotulo = campos[bloco.source];
      return "[" + (rotulo || bloco.source || "campo não escolhido") + "]";
    }
    if (bloco.kind === "mixed") {
      return (bloco.parts || [])
        .map(function (parte) {
          return textoDoConteudo(parte, campos);
        })
        .join("");
    }
    return "";
  }

  function estiloDeTexto(props, zoom) {
    return {
      fontFamily: '"Liberation Sans", Arial, Helvetica, sans-serif',
      fontSize: Number(props.font_size || 11) * zoom + "px",
      fontWeight: PESOS[props.font_weight] || "400",
      fontStyle: props.font_style === "italic" ? "italic" : "normal",
      textDecoration:
        props.text_decoration && props.text_decoration !== "none"
          ? props.text_decoration
          : "none",
      color: props.color || "#000000",
      textAlign: props.align || "left",
      lineHeight: String(props.line_height || 1.25),
      letterSpacing: Number(props.letter_spacing || 0) * zoom + "px",
      whiteSpace: props.white_space === "nowrap" ? "nowrap" : "pre-wrap",
      overflow: props.overflow === "grow" ? "visible" : "hidden",
      display: "flex",
      flexDirection: "column",
      justifyContent:
        props.vertical_align === "middle"
          ? "center"
          : props.vertical_align === "bottom"
            ? "flex-end"
            : "flex-start"
    };
  }

  function aplicar(no, estilo) {
    Object.keys(estilo).forEach(function (chave) {
      no.style[chave] = estilo[chave];
    });
  }

  function caixaEmPixels(props, zoom) {
    var c = props || {};
    return (
      Number(c.top || 0) * zoom + "px " +
      Number(c.right || 0) * zoom + "px " +
      Number(c.bottom || 0) * zoom + "px " +
      Number(c.left || 0) * zoom + "px"
    );
  }

  function desenharTabela(doc, no, props, zoom, campos) {
    var tabela = criarNo(doc, "table", "te-tabela");
    tabela.style.borderCollapse = "collapse";
    tabela.style.width = "100%";
    tabela.style.tableLayout = "fixed";

    var grupo = criarNo(doc, "colgroup");
    (props.columns || []).forEach(function (coluna) {
      var col = criarNo(doc, "col");
      col.style.width = Number(coluna.width || 0) * zoom + "px";
      grupo.appendChild(col);
    });
    tabela.appendChild(grupo);

    var corpo = criarNo(doc, "tbody");
    (props.rows || []).forEach(function (linha) {
      var tr = criarNo(doc, "tr");
      (linha.cells || []).forEach(function (celula, indice) {
        var coluna = (props.columns || [])[indice] || {};
        var td = criarNo(doc, "td");
        td.style.border =
          Number(props.border_width || 0.5) * zoom + "px solid " +
          (props.border_color || "#000000");
        td.style.padding = caixaEmPixels(props.cell_padding, zoom);
        td.style.textAlign = celula.align || coluna.align || "left";
        td.style.fontFamily = '"Liberation Sans", Arial, Helvetica, sans-serif';
        td.style.fontSize = Number(props.font_size || 11) * zoom + "px";
        td.style.fontWeight = celula.bold ? "700" : PESOS[props.font_weight] || "400";
        td.style.fontStyle = props.font_style === "italic" ? "italic" : "normal";
        td.style.color = props.color || "#000000";
        td.style.lineHeight = String(props.line_height || 1.25);
        td.style.letterSpacing = Number(props.letter_spacing || 0) * zoom + "px";
        td.style.height = Number(linha.min_height || 0) * zoom + "px";
        // A altura da linha inclui o padding: sem isto uma tabela medida
        // sairia com linhas mais altas do que as bordas.
        td.style.boxSizing = "border-box";
        td.textContent = textoDoConteudo(celula.content, campos);
        tr.appendChild(td);
      });
      corpo.appendChild(tr);
    });
    tabela.appendChild(corpo);
    no.appendChild(tabela);
  }

  /*
   * Constroi o no de um elemento posicionado.
   * `opcoes`: { zoom, campos, assets, selecionado, editavel }
   */
  function desenharElemento(doc, elemento, opcoes) {
    var zoom = opcoes.zoom || 1;
    var props = elemento.properties || {};
    var campos = opcoes.campos || {};
    var no = criarNo(doc, "div", "te-elemento te-" + elemento.type);

    no.style.position = "absolute";
    no.style.left = elemento.x * zoom + "px";
    no.style.top = elemento.y * zoom + "px";
    no.style.width = elemento.width * zoom + "px";
    no.style.height = elemento.height * zoom + "px";
    no.dataset.id = elemento.id;
    no.dataset.tipo = elemento.type;

    switch (elemento.type) {
      case "text":
      case "rich_text":
      case "number": {
        var estilo = estiloDeTexto(props, zoom);
        if (props.padding) {
          estilo.padding = caixaEmPixels(props.padding, zoom);
          estilo.boxSizing = "border-box";
        }
        aplicar(no, estilo);
        no.textContent = textoDoConteudo(props.content, campos);
        var vazio = props.content && props.content.kind === "field" && !props.content.source;
        if (vazio) {
          no.classList.add("is-incompleto");
        }
        break;
      }

      case "image": {
        var origem = props.source || {};
        var asset = (opcoes.assets || []).filter(function (item) {
          return item.id === origem.asset_id;
        })[0];
        if (asset && asset.url) {
          var img = criarNo(doc, "img");
          img.src = asset.url;
          img.alt = "";
          img.style.width = "100%";
          img.style.height = "100%";
          img.style.objectFit = props.preserve_aspect_ratio
            ? props.fit === "cover" ? "cover" : "contain"
            : "fill";
          no.appendChild(img);
        } else {
          no.classList.add("is-incompleto");
          no.textContent = "imagem não escolhida";
        }
        break;
      }

      case "qr_code":
        // O QR de verdade so e gerado com o documento. Aqui vale a area
        // reservada -- que e o que o editor precisa posicionar.
        no.classList.add("te-qr");
        no.textContent = "QR";
        break;

      case "line":
        // Uma linha e uma borda superior: a altura da caixa nao manda, a
        // espessura sim. Por isso `line` pode ter altura zero.
        no.style.borderTop =
          Number(props.thickness || 1) * zoom + "px " +
          (props.style || "solid") + " " + (props.color || "#000000");
        no.style.height =
          Math.max(1, Number(props.thickness || 1) * zoom) + "px";
        break;

      case "rectangle":
        no.style.border =
          Number(props.border_width || 1) * zoom + "px " +
          (props.border_style || "solid") + " " + (props.border_color || "#000000");
        no.style.background = props.fill_color || "transparent";
        no.style.borderRadius = Number(props.radius || 0) * zoom + "px";
        break;

      case "table":
        desenharTabela(doc, no, props, zoom, campos);
        break;

      default:
        no.textContent = elemento.type;
    }

    if (opcoes.selecionado === elemento.id) {
      no.classList.add("is-selecionado");
      if (opcoes.editavel) {
        ALCAS.forEach(function (posicao) {
          var alca = criarNo(doc, "span", "te-alca te-alca-" + posicao);
          alca.dataset.alca = posicao;
          no.appendChild(alca);
        });
      }
    }

    no.tabIndex = 0;
    no.setAttribute("role", "button");
    no.setAttribute("aria-label", elemento.type);
    return no;
  }

  /*
   * Desenha o layout inteiro dentro de `alvo`.
   *
   * A ordem de insercao e a ordem da lista -- que E a ordem de camadas.
   * Nao ha z-index: quem vem depois fica por cima.
   */
  function desenharLayout(doc, alvo, layout, opcoes) {
    while (alvo.firstChild) {
      alvo.removeChild(alvo.firstChild);
    }
    ((layout && layout.elements) || []).forEach(function (elemento) {
      alvo.appendChild(desenharElemento(doc, elemento, opcoes));
    });
  }

  return {
    ALCAS: ALCAS,
    indiceDeCampos: indiceDeCampos,
    textoDoConteudo: textoDoConteudo,
    estiloDeTexto: estiloDeTexto,
    desenharElemento: desenharElemento,
    desenharLayout: desenharLayout
  };
});
