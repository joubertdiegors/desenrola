/*
 * Desenha um elemento do documento como DOM.
 *
 * UM SO RENDERIZADOR para o canvas e para o preview. A diferenca entre
 * os dois e apenas `modo`: no preview nao ha alcas de redimensionamento
 * nem contorno de selecao, e um campo mostra o nome da referencia em vez
 * do rotulo tecnico. O resto -- posicao, fonte, cor, borda -- e o mesmo
 * codigo, porque um preview que desenha diferente do editor nao serve
 * para conferir nada.
 *
 * SEGURANCA: nada de innerHTML com conteudo do documento. Todo texto vai
 * por textContent e todo no e criado com createElement. O conteudo vem
 * de um administrador, mas "veio de alguem em quem confio" nunca foi
 * defesa contra XSS armazenado.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.EditorRender = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var PESOS = { regular: "400", bold: "700" };

  /*
   * O estilo CSS de um elemento de texto, na escala do canvas.
   *
   * Funcao pura (devolve um objeto), separada da criacao do no, para
   * poder ser testada no Node sem DOM.
   */
  function estiloDeTexto(props, zoom) {
    var tamanho = Number(props.font_size || 11) * zoom;
    return {
      fontFamily: '"Liberation Sans", Arial, Helvetica, sans-serif',
      fontSize: tamanho + "px",
      fontWeight: PESOS[props.font_weight] || "400",
      fontStyle: props.italic ? "italic" : "normal",
      color: props.color || "#000000",
      textAlign: props.align || "left",
      lineHeight: String(props.line_height || 1.25),
      letterSpacing: Number(props.letter_spacing || 0) * zoom + "px",
      whiteSpace: props.wrap === false ? "pre" : "pre-wrap",
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

  function criarNo(documento, tag, classe) {
    var no = documento.createElement(tag);
    if (classe) {
      no.className = classe;
    }
    return no;
  }

  /*
   * Conteudo visivel de um elemento `field`.
   *
   * O editor NAO tem o valor -- ele so existe quando uma carta e gerada.
   * Mostramos a referencia entre chaves, que e como a pessoa reconhece o
   * que vai aparecer ali.
   */
  function rotuloDeCampo(props, campos) {
    var referencia = props.field || "";
    if (!referencia) {
      return "{{ campo não escolhido }}";
    }
    for (var i = 0; i < (campos || []).length; i += 1) {
      if (campos[i].key === referencia) {
        return "{{ " + campos[i].label + " }}";
      }
    }
    return "{{ " + referencia + " }}";
  }

  function desenharTabela(doc, no, props, zoom) {
    var tabela = criarNo(doc, "table", "ed-tabela");
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
      tr.style.minHeight = Number(linha.min_height || 0) * zoom + "px";
      (linha.cells || []).forEach(function (celula, indice) {
        var coluna = (props.columns || [])[indice] || {};
        var td = criarNo(doc, "td");
        td.style.border =
          Number(props.border_width || 0.5) * zoom +
          "px solid " +
          (props.border_color || "#000000");
        td.style.padding = Number(props.padding || 4) * zoom + "px";
        td.style.textAlign = celula.align || coluna.align || "left";
        td.style.fontWeight = celula.bold ? "700" : "400";
        td.style.height = Number(linha.min_height || 0) * zoom + "px";
        // Celula e texto fixo OU referencia de campo -- nunca as duas.
        td.textContent = celula.field ? "{{ " + celula.field + " }}" : celula.content || "";
        tr.appendChild(td);
      });
      corpo.appendChild(tr);
    });
    tabela.appendChild(corpo);
    no.appendChild(tabela);
  }

  /*
   * Constroi o no de um elemento posicionado.
   *
   * `opcoes`: { zoom, campos, assets, modo } -- modo "editor" ou "preview".
   */
  function desenharElemento(doc, elemento, opcoes) {
    var zoom = opcoes.zoom || 1;
    var props = elemento.properties || {};
    var no = criarNo(doc, "div", "ed-elemento ed-" + elemento.type);

    no.style.position = "absolute";
    no.style.left = elemento.x * zoom + "px";
    no.style.top = elemento.y * zoom + "px";
    no.style.width = elemento.width * zoom + "px";
    no.style.height = elemento.height * zoom + "px";
    no.style.zIndex = String(elemento.z_index || 0);
    no.dataset.id = elemento.id;
    no.dataset.tipo = elemento.type;

    switch (elemento.type) {
      case "text":
        aplicar(no, estiloDeTexto(props, zoom));
        no.textContent = props.content || "";
        break;

      case "field":
        aplicar(no, estiloDeTexto(props, zoom));
        no.textContent = rotuloDeCampo(props, opcoes.campos);
        if (!props.field) {
          no.classList.add("is-incompleto");
        }
        break;

      case "rich_text": {
        // Um paragrafo que mistura texto fixo e campos na mesma linha
        // corrida. Cada trecho vira um <span> proprio para o campo
        // poder ser destacado -- mas o fluxo do texto continua sendo um
        // so, como no documento.
        var estilo = estiloDeTexto(props, zoom);
        estilo.display = "block";
        // A entrelinha do documento e absoluta (pt), nao multiplicador.
        estilo.lineHeight = Number(props.leading || 13.5) * zoom + "px";
        aplicar(no, estilo);
        (props.runs || []).forEach(function (trecho) {
          var span = criarNo(doc, "span");
          if (trecho.field) {
            span.className = "ed-trecho-campo";
            span.textContent = rotuloDeCampo({ field: trecho.field }, opcoes.campos);
          } else {
            span.textContent = trecho.text || "";
          }
          if (trecho.bold) {
            span.style.fontWeight = "700";
          }
          no.appendChild(span);
        });
        break;
      }

      case "image": {
        // A pagina oficial rasterizada e so referencia visual: nao pode
        // receber clique nem ser arrastada, senao ela rouba todos os
        // eventos (cobre a folha inteira) e os elementos de verdade
        // ficam impossiveis de selecionar.
        if (props.is_base_reference) {
          no.classList.add("ed-base-ref");
        }
        var asset = (opcoes.assets || []).filter(function (item) {
          return item.id === props.asset_id;
        })[0];
        if (asset && asset.url) {
          var img = criarNo(doc, "img");
          img.src = asset.url;
          img.alt = "";
          img.style.width = "100%";
          img.style.height = "100%";
          img.style.objectFit = props.preserve_aspect_ratio ? "contain" : "fill";
          no.appendChild(img);
        } else {
          no.classList.add("is-incompleto");
          no.textContent = "imagem não escolhida";
        }
        break;
      }

      case "line":
        // Uma linha e uma borda superior: a altura da caixa nao importa,
        // a espessura e que manda.
        no.style.borderTop =
          Number(props.thickness || 1) * zoom + "px solid " + (props.color || "#000000");
        no.style.height = Math.max(1, Number(props.thickness || 1) * zoom) + "px";
        break;

      case "rect":
        no.style.border =
          Number(props.border_width || 1) * zoom +
          "px solid " +
          (props.border_color || "#000000");
        no.style.background = props.fill_color || "transparent";
        no.style.borderRadius = Number(props.radius || 0) * zoom + "px";
        break;

      case "qrcode":
        // O QR de verdade so e gerado com a carta (Etapa 4.2D). Aqui vale
        // a area reservada -- que e o que o editor precisa posicionar.
        no.classList.add("ed-qr-placeholder");
        no.textContent = "QR";
        break;

      case "table":
        desenharTabela(doc, no, props, zoom);
        break;

      default:
        no.textContent = elemento.type;
    }

    if (opcoes.modo === "editor") {
      no.tabIndex = 0;
      no.setAttribute("role", "button");
      no.setAttribute("aria-label", elemento.type);
    }

    return no;
  }

  /* Desenha o documento inteiro dentro de `alvo`, na ordem de z. */
  function desenharDocumento(doc, alvo, documento, opcoes) {
    while (alvo.firstChild) {
      alvo.removeChild(alvo.firstChild);
    }
    var ordenados = documento.elements
      .slice()
      .sort(function (a, b) {
        return (a.z_index || 0) - (b.z_index || 0);
      });
    ordenados.forEach(function (elemento) {
      alvo.appendChild(desenharElemento(doc, elemento, opcoes));
    });
  }

  return {
    PESOS: PESOS,
    estiloDeTexto: estiloDeTexto,
    rotuloDeCampo: rotuloDeCampo,
    desenharElemento: desenharElemento,
    desenharDocumento: desenharDocumento
  };
});
