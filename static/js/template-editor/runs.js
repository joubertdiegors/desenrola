/*
 * Trechos de texto rico: o conteudo ESTRUTURAL de um bloco <-> o DOM
 * editavel (Etapa 3.7, editor rico).
 *
 * O que fica gravado continua sendo o contrato de `layout_schema.py`:
 *
 *   {kind: "text",  value: "Je soussigné "}
 *   {kind: "field", source: "anfitriao.nome", font_weight: "bold"}
 *   {kind: "mixed", parts: [ ...trechos... ]}
 *
 * Cada trecho pode carregar o proprio estilo (`ESTILOS`), que sobrepoe
 * o do elemento. Este modulo faz duas travessias:
 *
 *   desenhar()   trechos -> nos do DOM (spans com o estilo, chips para
 *                os campos), o que o `contenteditable` mostra;
 *   serializar() DOM -> trechos, lendo TANTO os nos que desenhar()
 *                criou QUANTO o que o navegador produz ao formatar
 *                (`<b>`, `<i>`, `<font color>`, `<a href>`...).
 *
 * SEGURANCA
 * ---------
 * Nada aqui usa innerHTML. Texto entra por textContent e sai por
 * nodeValue; um `<script>` colado no bloco vira o TEXTO "<script>", e
 * o servidor -- que revalida tudo pelo contrato -- so ve strings. O
 * unico dado que vira URL e `link`, conferido aqui (`linkAceito`) e de
 * novo no servidor (`layout_schema.link_aceito`).
 *
 * Funcoes puras onde possivel: dividir, juntar, aplicarEstilo e
 * blocoDe nao tocam no DOM e sao exercitadas no Node.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.TERuns = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // As chaves de estilo que um trecho pode sobrepor ao elemento. Mesma
  // lista de `layout_schema.ESTILO_DO_TRECHO`.
  var ESTILOS = [
    "font_weight", "font_style", "text_decoration", "color", "highlight",
    "font_size", "font_family", "link"
  ];

  // `<font size="n">` (o que execCommand("fontSize") produz) -> pontos.
  // Sao os seis tamanhos do seletor "Corpo do texto" do design.
  var TAMANHOS = { 1: 8, 2: 9, 3: 10, 4: 12, 5: 14, 6: 18, 7: 24 };
  var TAMANHOS_POR_PALAVRA = {
    "xx-small": 8, "x-small": 9, small: 10, medium: 12, large: 14,
    "x-large": 18, "xx-large": 24
  };

  // A familia do layout -> a pilha CSS que a representa na tela.
  var FAMILIAS_CSS = {
    LiberationSans: '"Liberation Sans", Arial, Helvetica, sans-serif',
    Times: '"Times New Roman", Times, serif',
    Courier: '"Courier New", Courier, monospace'
  };

  var ESQUEMAS_DE_LINK = ["http://", "https://", "mailto:", "tel:"];

  // --- conteudo -> trechos ---------------------------------------------

  function copiar(trecho) {
    var novo = {};
    Object.keys(trecho || {}).forEach(function (chave) {
      novo[chave] = trecho[chave];
    });
    return novo;
  }

  function estiloDe(trecho) {
    var estilo = {};
    ESTILOS.forEach(function (chave) {
      if (trecho && trecho[chave] !== undefined && trecho[chave] !== null) {
        estilo[chave] = trecho[chave];
      }
    });
    return estilo;
  }

  function mesmoEstilo(a, b) {
    var ea = estiloDe(a), eb = estiloDe(b);
    var chaves = Object.keys(ea).concat(Object.keys(eb));
    for (var i = 0; i < chaves.length; i += 1) {
      if (ea[chaves[i]] !== eb[chaves[i]]) {
        return false;
      }
    }
    return true;
  }

  function texto(valor, estilo) {
    var t = copiar(estilo || {});
    t.kind = "text";
    t.value = valor;
    return t;
  }

  function campo(referencia, estilo) {
    var t = copiar(estilo || {});
    t.kind = "field";
    t.source = referencia;
    return t;
  }

  /* Os trechos de um bloco de conteudo, sempre como lista (copias). */
  function trechosDe(bloco) {
    if (!bloco || typeof bloco !== "object") {
      return [];
    }
    if (bloco.kind === "mixed") {
      return (bloco.parts || []).map(copiar);
    }
    if (bloco.kind === "text" || bloco.kind === "field") {
      return [copiar(bloco)];
    }
    return [];
  }

  /*
   * Funde vizinhos de mesmo estilo e joga fora texto vazio. A ordem e a
   * identidade dos campos nunca mudam: um campo nunca se funde com nada.
   */
  function fundir(trechos) {
    var saida = [];
    (trechos || []).forEach(function (trecho) {
      if (!trecho) {
        return;
      }
      if (trecho.kind === "text" && !trecho.value) {
        return;
      }
      var anterior = saida[saida.length - 1];
      if (
        anterior && anterior.kind === "text" && trecho.kind === "text" &&
        mesmoEstilo(anterior, trecho)
      ) {
        saida[saida.length - 1] = texto(anterior.value + trecho.value, estiloDe(anterior));
      } else {
        saida.push(copiar(trecho));
      }
    });
    return saida;
  }

  /*
   * O bloco de conteudo que os trechos formam. Um texto so, sem estilo,
   * volta a ser `{kind: "text"}`; um campo so, sem estilo, `{kind:
   * "field"}`; o resto e `mixed`. E o que mantem um layout simples
   * simples -- e o que faz o contrato continuar reconhecendo o que o
   * editor grava.
   */
  function blocoDe(trechos) {
    var lista = fundir(trechos);
    if (lista.length === 0) {
      return { kind: "text", value: "" };
    }
    if (lista.length === 1 && Object.keys(estiloDe(lista[0])).length === 0) {
      return lista[0].kind === "field"
        ? { kind: "field", source: lista[0].source }
        : { kind: "text", value: lista[0].value };
    }
    return { kind: "mixed", parts: lista };
  }

  // --- posicoes ----------------------------------------------------------
  //
  // Uma posicao por caractere de texto; um campo ocupa UMA posicao (e
  // indivisivel). E a moeda em que o cursor e as divisoes falam.

  function comprimento(trechos) {
    var total = 0;
    (trechos || []).forEach(function (t) {
      total += t.kind === "field" ? 1 : (t.value || "").length;
    });
    return total;
  }

  function dividir(trechos, posicao) {
    var antes = [], depois = [], corrente = 0;
    (trechos || []).forEach(function (t) {
      var tamanho = t.kind === "field" ? 1 : (t.value || "").length;
      if (corrente + tamanho <= posicao) {
        antes.push(copiar(t));
      } else if (corrente >= posicao) {
        depois.push(copiar(t));
      } else {
        // O corte cai DENTRO deste texto.
        var corte = posicao - corrente;
        antes.push(texto(t.value.slice(0, corte), estiloDe(t)));
        depois.push(texto(t.value.slice(corte), estiloDe(t)));
      }
      corrente += tamanho;
    });
    return [fundir(antes), fundir(depois)];
  }

  function juntar(a, b) {
    return fundir((a || []).concat(b || []));
  }

  /*
   * Aplica `estilo` ao intervalo [de, ate). Uma chave com valor null
   * APAGA o estilo (volta a herdar do elemento). Fora do intervalo nada
   * muda. Puro: devolve trechos novos.
   */
  function aplicarEstilo(trechos, de, ate, estilo) {
    var partes = dividir(trechos, de);
    var meio = dividir(partes[1], ate - de);
    var alterados = meio[0].map(function (t) {
      var novo = copiar(t);
      Object.keys(estilo || {}).forEach(function (chave) {
        if (ESTILOS.indexOf(chave) === -1) {
          return;
        }
        if (estilo[chave] === null || estilo[chave] === undefined) {
          delete novo[chave];
        } else {
          novo[chave] = estilo[chave];
        }
      });
      return novo;
    });
    return fundir(partes[0].concat(alterados, meio[1]));
  }

  function limparEstilo(trechos) {
    return (trechos || []).map(function (t) {
      return t.kind === "field" ? campo(t.source) : texto(t.value);
    });
  }

  function textoPlano(trechos, rotulos) {
    return (trechos || []).map(function (t) {
      return t.kind === "field" ? "[" + rotulo(t.source, rotulos) + "]" : (t.value || "");
    }).join("");
  }

  // --- cores, tamanhos, familias --------------------------------------------

  function normalizarCor(valor) {
    if (!valor || typeof valor !== "string") {
      return null;
    }
    var v = valor.trim().toLowerCase();
    var hex = v.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/);
    if (hex) {
      var h = hex[1];
      if (h.length === 3) {
        h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
      }
      return "#" + h;
    }
    var rgb = v.match(/^rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\)$/);
    if (rgb) {
      if (rgb[4] !== undefined && parseFloat(rgb[4]) === 0) {
        return null; // transparente
      }
      return "#" + [rgb[1], rgb[2], rgb[3]].map(function (n) {
        var s = Math.max(0, Math.min(255, parseInt(n, 10))).toString(16);
        return s.length === 1 ? "0" + s : s;
      }).join("");
    }
    return null;
  }

  function familiaDeCss(valor) {
    var v = String(valor || "").toLowerCase();
    if (!v) {
      return null;
    }
    if (v.indexOf("times") !== -1 || v.indexOf("georgia") !== -1 || v.indexOf("serif") === 0) {
      return "Times";
    }
    if (v.indexOf("courier") !== -1 || v.indexOf("mono") !== -1) {
      return "Courier";
    }
    if (v.indexOf("liberation") !== -1 || v.indexOf("arial") !== -1 ||
        v.indexOf("helvetica") !== -1 || v.indexOf("sans") !== -1 ||
        v.indexOf("manrope") !== -1) {
      return "LiberationSans";
    }
    return null;
  }

  function cssDaFamilia(codigo) {
    return FAMILIAS_CSS[codigo] || FAMILIAS_CSS.LiberationSans;
  }

  function tamanhoDeFont(n) {
    return TAMANHOS[parseInt(n, 10)] || null;
  }

  function linkAceito(valor) {
    // Espaco e caractere de controle saem antes da conferencia ("java
    // script:" e o truque classico). Comparar com " " tira os dois sem
    // precisar de um NUL literal no meio do arquivo.
    var limpo = "";
    String(valor || "").split("").forEach(function (c) {
      if (c > " " && c !== "\u007f") {
        limpo += c;
      }
    });
    if (!limpo || limpo.length > 2000) {
      return null;
    }
    var baixo = limpo.toLowerCase();
    for (var i = 0; i < ESQUEMAS_DE_LINK.length; i += 1) {
      if (baixo.indexOf(ESQUEMAS_DE_LINK[i]) === 0) {
        return limpo;
      }
    }
    return null;
  }

  function rotulo(referencia, rotulos) {
    return (rotulos && rotulos[referencia]) || referencia || "campo";
  }

  // --- trechos -> DOM ----------------------------------------------------------

  /*
   * O estilo de um trecho como declaracoes CSS + atributos data-*, para
   * o desenho e para a leitura de volta. `escala` e px por pt.
   */
  function aplicarEstiloNoNo(no, trecho, escala) {
    var estilo = estiloDe(trecho);
    if (estilo.font_weight) {
      no.style.fontWeight = estilo.font_weight === "bold" ? "700" : "400";
      no.dataset.peso = estilo.font_weight;
    }
    if (estilo.font_style) {
      no.style.fontStyle = estilo.font_style;
      no.dataset.estilo = estilo.font_style;
    }
    if (estilo.text_decoration) {
      no.style.textDecoration = estilo.text_decoration;
      no.dataset.decoracao = estilo.text_decoration;
    }
    if (estilo.color) {
      no.style.color = estilo.color;
      no.dataset.cor = estilo.color;
    }
    if (estilo.highlight) {
      no.style.backgroundColor = estilo.highlight;
      no.dataset.realce = estilo.highlight;
    }
    if (estilo.font_size) {
      no.style.fontSize = (Number(estilo.font_size) * (escala || 1)) + "px";
      no.dataset.tamanho = String(estilo.font_size);
    }
    if (estilo.font_family) {
      no.style.fontFamily = cssDaFamilia(estilo.font_family);
      no.dataset.fonte = estilo.font_family;
    }
    if (estilo.link) {
      no.dataset.link = estilo.link;
    }
  }

  /*
   * Desenha os trechos dentro de `alvo` (esvaziado antes).
   * `opcoes`: { rotulos, exemplo, escala }
   *   rotulos -- referencia -> "Grupo · Rótulo"
   *   exemplo -- referencia -> valor de amostra, ou null (mostra o rotulo)
   */
  function desenhar(doc, alvo, bloco, opcoes) {
    var o = opcoes || {};
    while (alvo.firstChild) {
      alvo.removeChild(alvo.firstChild);
    }
    var trechos = trechosDe(bloco);
    trechos.forEach(function (trecho) {
      if (trecho.kind === "field") {
        var chip = doc.createElement("span");
        chip.className = "te-campo";
        chip.setAttribute("data-field", trecho.source || "");
        chip.setAttribute("contenteditable", "false");
        var amostra = o.exemplo && trecho.source in o.exemplo ? o.exemplo[trecho.source] : null;
        if (amostra !== null && amostra !== undefined && amostra !== "") {
          chip.classList.add("is-exemplo");
          chip.textContent = String(amostra);
        } else {
          chip.textContent = "[" + rotulo(trecho.source, o.rotulos) + "]";
        }
        if (!trecho.source) {
          chip.classList.add("is-incompleto");
        }
        aplicarEstiloNoNo(chip, trecho, o.escala);
        alvo.appendChild(chip);
        return;
      }
      // Um trecho e UM span, com as quebras de linha dentro dele: assim
      // o <br> herda o estilo do trecho ao ser lido de volta, e o trecho
      // volta inteiro em vez de partido em tres.
      var span = doc.createElement("span");
      span.className = "te-run";
      aplicarEstiloNoNo(span, trecho, o.escala);
      String(trecho.value || "").split("\n").forEach(function (linha, indice) {
        if (indice > 0) {
          span.appendChild(doc.createElement("br"));
        }
        if (linha) {
          span.appendChild(doc.createTextNode(linha));
        }
      });
      alvo.appendChild(span);
    });
    return alvo;
  }

  // --- DOM -> trechos ----------------------------------------------------------

  var TAGS_DE_BLOCO = { div: 1, p: 1, li: 1, h1: 1, h2: 1, h3: 1, h4: 1, tr: 1 };

  function atributo(no, nome) {
    if (no.dataset && no.dataset[nome] !== undefined) {
      return no.dataset[nome];
    }
    return null;
  }

  /* O estilo que UM no acrescenta ao que herdou. */
  function estiloDoNo(no, escala) {
    var tag = String(no.tagName || "").toLowerCase();
    var estilo = {};
    var s = no.style || {};

    if (tag === "b" || tag === "strong") { estilo.font_weight = "bold"; }
    if (tag === "i" || tag === "em") { estilo.font_style = "italic"; }
    if (tag === "u") { estilo.text_decoration = "underline"; }
    if (tag === "s" || tag === "strike" || tag === "del") { estilo.text_decoration = "line-through"; }
    if (tag === "a") {
      var href = no.getAttribute ? no.getAttribute("href") : null;
      var aceito = linkAceito(href);
      if (aceito) { estilo.link = aceito; }
    }
    if (tag === "font") {
      var size = no.getAttribute ? no.getAttribute("size") : null;
      if (size) { estilo.font_size = tamanhoDeFont(size) || undefined; }
      var color = normalizarCor(no.getAttribute ? no.getAttribute("color") : null);
      if (color) { estilo.color = color; }
      var face = familiaDeCss(no.getAttribute ? no.getAttribute("face") : null);
      if (face) { estilo.font_family = face; }
    }

    // O que desenhar() escreveu, lido de volta sem ambiguidade.
    var peso = atributo(no, "peso");
    if (peso) { estilo.font_weight = peso; }
    var est = atributo(no, "estilo");
    if (est) { estilo.font_style = est; }
    var dec = atributo(no, "decoracao");
    if (dec) { estilo.text_decoration = dec; }
    var cor = atributo(no, "cor");
    if (cor) { estilo.color = cor; }
    var realce = atributo(no, "realce");
    if (realce) { estilo.highlight = realce; }
    var tamanho = atributo(no, "tamanho");
    if (tamanho) { estilo.font_size = Number(tamanho); }
    var fonte = atributo(no, "fonte");
    if (fonte) { estilo.font_family = fonte; }
    var link = atributo(no, "link");
    if (link) { estilo.link = linkAceito(link) || undefined; }

    // O que o navegador escreveu ao formatar com CSS.
    var fw = String(s.fontWeight || "");
    if (fw === "bold" || fw === "bolder" || parseInt(fw, 10) >= 600) {
      estilo.font_weight = "bold";
    } else if (fw === "normal" || (parseInt(fw, 10) > 0 && parseInt(fw, 10) < 600)) {
      estilo.font_weight = "regular";
    }
    var fs = String(s.fontStyle || "");
    if (fs === "italic" || fs === "oblique") {
      estilo.font_style = "italic";
    } else if (fs === "normal") {
      estilo.font_style = "normal";
    }
    var td = String(s.textDecoration || s.textDecorationLine || "");
    if (td.indexOf("underline") !== -1) {
      estilo.text_decoration = "underline";
    } else if (td.indexOf("line-through") !== -1) {
      estilo.text_decoration = "line-through";
    } else if (td === "none") {
      estilo.text_decoration = "none";
    }
    var c = normalizarCor(s.color);
    if (c) { estilo.color = c; }
    var bg = normalizarCor(s.backgroundColor);
    if (bg) { estilo.highlight = bg; }
    var fsz = String(s.fontSize || "");
    if (fsz && !tamanho) {
      if (TAMANHOS_POR_PALAVRA[fsz]) {
        estilo.font_size = TAMANHOS_POR_PALAVRA[fsz];
      } else if (/pt$/.test(fsz)) {
        estilo.font_size = Math.round(parseFloat(fsz) * 2) / 2;
      } else if (/px$/.test(fsz) && escala) {
        estilo.font_size = Math.round((parseFloat(fsz) / escala) * 2) / 2;
      }
    }
    var ff = familiaDeCss(s.fontFamily);
    if (ff && !fonte) { estilo.font_family = ff; }

    Object.keys(estilo).forEach(function (chave) {
      if (estilo[chave] === undefined) {
        delete estilo[chave];
      }
    });
    return estilo;
  }

  function mesclar(base, extra) {
    var novo = copiar(base);
    Object.keys(extra || {}).forEach(function (chave) {
      novo[chave] = extra[chave];
    });
    return novo;
  }

  function filhosDe(no) {
    if (no.childNodes) {
      return Array.prototype.slice.call(no.childNodes);
    }
    return (no.children || []).slice();
  }

  function eTexto(no) {
    return no.nodeType === 3 || (no.nodeType === undefined && typeof no.nodeValue === "string");
  }

  /*
   * Le os trechos de dentro de `no` (o bloco editavel).
   * `opcoes`: { escala, base } -- `base` sao as propriedades do ELEMENTO;
   * um estilo de trecho igual ao do elemento e redundante e sai, para o
   * dado gravado continuar o menor possivel.
   */
  function serializar(no, opcoes) {
    var o = opcoes || {};
    var trechos = [];

    function andar(pai, herdado) {
      var filhos = filhosDe(pai);
      filhos.forEach(function (filho, indice) {
        if (eTexto(filho)) {
          var valor = String(filho.nodeValue || "").replace(/ /g, " ");
          if (valor) {
            trechos.push(texto(valor, herdado));
          }
          return;
        }
        if (filho.nodeType && filho.nodeType !== 1) {
          return; // comentario etc.
        }
        var tag = String(filho.tagName || "").toLowerCase();
        if (tag === "br") {
          trechos.push(texto("\n", herdado));
          return;
        }
        if (tag === "script" || tag === "style" || tag === "template") {
          return; // nunca e conteudo
        }
        var referencia = filho.getAttribute ? filho.getAttribute("data-field") : null;
        if (referencia === null && filho.dataset && filho.dataset.field !== undefined) {
          referencia = filho.dataset.field;
        }
        var estilo = mesclar(herdado, estiloDoNo(filho, o.escala));
        if (referencia !== null && referencia !== undefined) {
          trechos.push(campo(referencia, estilo));
          return;
        }
        andar(filho, estilo);
        if (TAGS_DE_BLOCO[tag] && indice < filhos.length - 1) {
          trechos.push(texto("\n", herdado));
        }
      });
    }

    andar(no, {});

    // O navegador guarda um <br> final para o bloco continuar
    // editavel; ele nao e conteudo.
    var lista = fundir(trechos);
    var ultimo = lista[lista.length - 1];
    if (ultimo && ultimo.kind === "text" && /\n$/.test(ultimo.value)) {
      ultimo.value = ultimo.value.replace(/\n$/, "");
      if (!ultimo.value) {
        lista.pop();
      }
    }

    if (o.base) {
      lista = lista.map(function (t) {
        var novo = copiar(t);
        ESTILOS.forEach(function (chave) {
          if (novo[chave] !== undefined && o.base[chave] === novo[chave]) {
            delete novo[chave];
          }
        });
        if (novo.font_weight === "regular" && !o.base.font_weight) { delete novo.font_weight; }
        if (novo.font_style === "normal" && !o.base.font_style) { delete novo.font_style; }
        if (novo.text_decoration === "none" && !o.base.text_decoration) {
          delete novo.text_decoration;
        }
        return novo;
      });
    }
    return fundir(lista);
  }

  return {
    ESTILOS: ESTILOS,
    TAMANHOS: TAMANHOS,
    FAMILIAS_CSS: FAMILIAS_CSS,
    texto: texto,
    campo: campo,
    copiar: copiar,
    estiloDe: estiloDe,
    mesmoEstilo: mesmoEstilo,
    trechosDe: trechosDe,
    fundir: fundir,
    blocoDe: blocoDe,
    comprimento: comprimento,
    dividir: dividir,
    juntar: juntar,
    aplicarEstilo: aplicarEstilo,
    limparEstilo: limparEstilo,
    textoPlano: textoPlano,
    normalizarCor: normalizarCor,
    familiaDeCss: familiaDeCss,
    cssDaFamilia: cssDaFamilia,
    tamanhoDeFont: tamanhoDeFont,
    linkAceito: linkAceito,
    rotulo: rotulo,
    estiloDoNo: estiloDoNo,
    desenhar: desenhar,
    serializar: serializar
  };
});
