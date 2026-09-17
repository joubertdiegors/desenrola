/*
 * Os paineis do editor rico (Etapa 3.7): os campos do banco (esquerda
 * / aba Campos), "Campos no documento" (direita / aba Documento), a
 * barra contextual de um elemento que nao e texto, e o reflexo do
 * bloco ativo na barra de ferramentas.
 *
 * Tudo aqui MONTA DOM a partir dos registros que o servidor entrega
 * (`datasources.para_o_editor()`, `elements.para_o_editor()`) e do
 * layout; nenhuma lista de campos ou de tipos e escrita aqui. Nada de
 * innerHTML.
 */
(function (root, factory) {
  var api = factory(
    typeof require === "function" ? require("./document.js") : root.TEDocument
  );
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.TEPanels = api;
  }
})(typeof self !== "undefined" ? self : this, function (Doc) {
  "use strict";

  function criarNo(doc, tag, classe) {
    var no = doc.createElement(tag);
    if (classe) {
      no.className = classe;
    }
    return no;
  }

  function esvaziar(alvo) {
    while (alvo.firstChild) {
      alvo.removeChild(alvo.firstChild);
    }
  }

  function normalizar(texto) {
    return String(texto || "").toLowerCase();
  }

  // --- campos do banco ---------------------------------------------------------

  function campoBate(campo, filtro) {
    if (!filtro) {
      return true;
    }
    var f = normalizar(filtro);
    return (
      normalizar(campo.label).indexOf(f) !== -1 ||
      normalizar(campo.reference).indexOf(f) !== -1
    );
  }

  /*
   * O painel "Campos do banco": grupos com o ponto colorido, cada campo
   * com o rotulo e a referencia (no celular: rotulo, valor de amostra e
   * o "+"). Um filtro abre todos os grupos e esconde o que nao bate.
   *
   * `opcoes`: { filtro, exemplo, abertos, celular, editavel,
   *             aoInserir(ref), aoAlternar(code) }
   */
  function montarCampos(doc, alvo, fontes, opcoes) {
    var o = opcoes || {};
    esvaziar(alvo);
    var algum = false;

    (fontes || []).forEach(function (grupo) {
      var campos = (grupo.fields || []).filter(function (c) { return campoBate(c, o.filtro); });
      if (o.filtro && !campos.length) {
        return;
      }
      algum = true;
      var aberto = o.filtro ? true : (o.abertos || {})[grupo.code] !== false;

      var bloco = criarNo(doc, "div", "te-grupo" + (aberto ? " is-aberto" : ""));
      bloco.dataset.grupo = grupo.code;

      var cabeca = criarNo(doc, "button", "te-grp");
      cabeca.type = "button";
      cabeca.dataset.grupo = grupo.code;
      cabeca.setAttribute("aria-expanded", aberto ? "true" : "false");
      var nome = criarNo(doc, "span", "te-grp-nome");
      var ponto = criarNo(doc, "span", "te-ponto");
      ponto.style.background = grupo.color || "#7c8aa6";
      nome.appendChild(ponto);
      var rotulo = criarNo(doc, "span");
      rotulo.textContent = grupo.label;
      nome.appendChild(rotulo);
      cabeca.appendChild(nome);
      var seta = criarNo(doc, "span", "te-grp-seta");
      seta.textContent = aberto ? "▾" : "▸";
      cabeca.appendChild(seta);
      cabeca.addEventListener("click", function () {
        if (o.aoAlternar) {
          o.aoAlternar(grupo.code);
        }
      });
      bloco.appendChild(cabeca);

      if (aberto) {
        var lista = criarNo(doc, "div", "te-grp-campos");
        campos.forEach(function (campo) {
          var item = criarNo(doc, "button", "te-fld");
          item.type = "button";
          item.dataset.ref = campo.reference;
          item.disabled = o.editavel === false;
          item.setAttribute("title", "Inserir " + campo.label);
          var textos = criarNo(doc, "span", "te-fld-textos");
          var etiqueta = criarNo(doc, "span", "te-fld-rotulo");
          etiqueta.textContent = campo.label;
          textos.appendChild(etiqueta);
          var chave = criarNo(doc, "span", "te-fld-chave");
          if (o.celular && o.exemplo && o.exemplo[campo.reference]) {
            chave.textContent = String(o.exemplo[campo.reference]);
          } else {
            chave.textContent = campo.reference;
          }
          textos.appendChild(chave);
          item.appendChild(textos);
          if (o.celular) {
            var mais = criarNo(doc, "span", "te-fld-mais");
            mais.textContent = "+";
            mais.setAttribute("aria-hidden", "true");
            item.appendChild(mais);
          }
          item.addEventListener("click", function () {
            if (o.aoInserir) {
              o.aoInserir(campo.reference);
            }
          });
          lista.appendChild(item);
        });
        bloco.appendChild(lista);
      }
      alvo.appendChild(bloco);
    });

    if (!algum) {
      var vazio = criarNo(doc, "p", "te-vazio");
      vazio.textContent = "Nenhum campo com esse nome.";
      alvo.appendChild(vazio);
    }
    return alvo;
  }

  // --- campos no documento -------------------------------------------------------

  /*
   * "Campos no documento": quantas vezes o documento imprime um campo e
   * um chip por campo distinto, com o ponto na cor do grupo.
   */
  function montarUsos(doc, alvo, layout, fontes, opcoes) {
    var o = opcoes || {};
    esvaziar(alvo);
    var usos = Doc.usosDeCampos(layout);
    var rotulos = {}, cores = {};
    (fontes || []).forEach(function (grupo) {
      (grupo.fields || []).forEach(function (campo) {
        rotulos[campo.reference] = campo.label;
        cores[campo.reference] = grupo.color || "#7c8aa6";
      });
    });

    var cabeca = criarNo(doc, "div", "te-usos-cabeca");
    var titulo = criarNo(doc, "span", "te-usos-titulo");
    titulo.textContent = "Campos no documento";
    cabeca.appendChild(titulo);
    var contagem = criarNo(doc, "span", "te-usos-contagem");
    contagem.dataset.usos = String(usos.total);
    contagem.textContent = o.celular
      ? usos.ordem.length + (usos.ordem.length === 1 ? " campo" : " campos")
      : usos.total + (usos.total === 1 ? " uso" : " usos");
    cabeca.appendChild(contagem);
    alvo.appendChild(cabeca);

    var chips = criarNo(doc, "div", "te-chips");
    usos.ordem.forEach(function (ref) {
      var chip = criarNo(doc, "span", "te-chip");
      chip.dataset.ref = ref;
      var ponto = criarNo(doc, "span", "te-ponto te-ponto-redondo");
      ponto.style.background = cores[ref] || "#7c8aa6";
      chip.appendChild(ponto);
      var nome = criarNo(doc, "span");
      nome.textContent = rotulos[ref] || ref;
      chip.appendChild(nome);
      chip.setAttribute("title", ref + " · " + usos.porReferencia[ref] + "×");
      chips.appendChild(chip);
    });
    if (!usos.ordem.length) {
      var vazio = criarNo(doc, "span", "te-vazio");
      vazio.textContent = "Nenhum campo ainda.";
      chips.appendChild(vazio);
    }
    alvo.appendChild(chips);

    var nota = criarNo(doc, "span", "te-usos-nota");
    nota.textContent = o.celular
      ? "Campos sem valor no cadastro bloqueiam a emissão e são apontados na hora."
      : "Ao emitir, qualquer campo sem valor no cadastro bloqueia a geração e aponta o que falta.";
    alvo.appendChild(nota);
    return alvo;
  }

  // --- barra do elemento ---------------------------------------------------------

  function rotuloCurto(doc, texto) {
    var s = criarNo(doc, "span", "te-ctx-rotulo");
    s.textContent = texto;
    return s;
  }

  function seletor(doc, valor, opcoes, aoMudar, habilitado) {
    var s = criarNo(doc, "select", "te-ctx-select");
    s.disabled = !habilitado;
    opcoes.forEach(function (op) {
      var item = criarNo(doc, "option");
      item.value = String(op.value);
      item.textContent = op.label;
      if (String(op.value) === String(valor)) {
        item.selected = true;
      }
      s.appendChild(item);
    });
    s.addEventListener("change", function () { aoMudar(s.value); });
    return s;
  }

  function numero(doc, valor, aoMudar, habilitado, passo) {
    var e = criarNo(doc, "input", "te-ctx-input");
    e.type = "number";
    e.step = passo || "0.5";
    e.min = "0";
    e.value = valor === null || valor === undefined ? "" : String(valor);
    e.disabled = !habilitado;
    e.addEventListener("change", function () {
      var n = parseFloat(e.value);
      if (!isNaN(n)) {
        aoMudar(n);
      }
    });
    return e;
  }

  function textoCurto(doc, valor, aoMudar, habilitado, placeholder) {
    var e = criarNo(doc, "input", "te-ctx-input te-ctx-input-texto");
    e.type = "text";
    e.value = valor || "";
    e.placeholder = placeholder || "";
    e.disabled = !habilitado;
    e.addEventListener("change", function () { aoMudar(e.value); });
    return e;
  }

  function botao(doc, texto, aoClicar, classe) {
    var b = criarNo(doc, "button", "te-ctx-botao" + (classe ? " " + classe : ""));
    b.type = "button";
    b.textContent = texto;
    b.addEventListener("click", aoClicar);
    return b;
  }

  function marcado(doc, valor, rotulo, aoMudar, habilitado) {
    var l = criarNo(doc, "label", "te-ctx-check");
    var e = criarNo(doc, "input");
    e.type = "checkbox";
    e.checked = !!valor;
    e.disabled = !habilitado;
    e.addEventListener("change", function () { aoMudar(e.checked); });
    l.appendChild(e);
    var s = criarNo(doc, "span");
    s.textContent = rotulo;
    l.appendChild(s);
    return l;
  }

  /*
   * A barra contextual de um elemento selecionado que NAO e bloco de
   * texto: imagem, QR, tabela, linha, retangulo, quebra. Os blocos de
   * texto sao editados pela barra de ferramentas principal.
   *
   * `opcoes`: { assets, referencias, editavel, aoAlterar(props),
   *             aoAcao(acao) }
   */
  function montarBarraDoElemento(doc, alvo, elemento, opcoes) {
    var o = opcoes || {};
    esvaziar(alvo);
    if (!elemento || Doc.eTexto(elemento)) {
      alvo.hidden = true;
      return alvo;
    }
    alvo.hidden = false;
    var p = elemento.properties || {};
    var pode = o.editavel !== false;
    var mudar = function (props) { if (o.aoAlterar) { o.aoAlterar(props); } };
    var acao = function (nome) { return function () { if (o.aoAcao) { o.aoAcao(nome); } }; };

    var titulo = criarNo(doc, "span", "te-ctx-titulo");
    titulo.textContent = o.rotulo || elemento.type;
    alvo.appendChild(titulo);

    switch (elemento.type) {
      case "image": {
        var origem = p.source || {};
        alvo.appendChild(rotuloCurto(doc, "Imagem"));
        alvo.appendChild(seletor(
          doc, origem.asset_id || 0,
          [{ value: 0, label: "— escolher —" }].concat((o.assets || []).map(function (a) {
            return { value: a.id, label: a.label };
          })),
          function (v) { mudar({ source: { kind: "asset", asset_id: parseInt(v, 10) || 0 } }); },
          pode
        ));
        alvo.appendChild(rotuloCurto(doc, "Ajuste"));
        alvo.appendChild(seletor(
          doc, p.fit || "contain",
          [{ value: "contain", label: "Conter" }, { value: "cover", label: "Cobrir" },
           { value: "fill", label: "Esticar" }],
          function (v) { mudar({ fit: v }); }, pode
        ));
        alvo.appendChild(marcado(doc, p.preserve_aspect_ratio !== false, "Manter proporção",
          function (v) { mudar({ preserve_aspect_ratio: v }); }, pode));
        break;
      }
      case "qr_code": {
        var fonte = p.source || {};
        alvo.appendChild(rotuloCurto(doc, "Conteúdo"));
        alvo.appendChild(seletor(
          doc, fonte.kind === "field" ? fonte.source : "__url__",
          [{ value: "__url__", label: "URL fixa" }].concat((o.referencias || []).map(function (r) {
            return { value: r.reference, label: r.label };
          })),
          function (v) {
            mudar({ source: v === "__url__" ? { kind: "text", value: fonte.kind === "text" ? fonte.value || "" : "" }
              : { kind: "field", source: v } });
          },
          pode
        ));
        if (fonte.kind !== "field") {
          alvo.appendChild(textoCurto(doc, fonte.value || "", function (v) {
            mudar({ source: { kind: "text", value: v } });
          }, pode, "https://…"));
        }
        alvo.appendChild(rotuloCurto(doc, "Lado (pt)"));
        alvo.appendChild(numero(doc, elemento.width, function (n) {
          if (o.aoGeometria) { o.aoGeometria({ width: n, height: n }); }
        }, pode, "1"));
        break;
      }
      case "table": {
        alvo.appendChild(botao(doc, "+ Linha", acao("tabela-mais-linha")));
        alvo.appendChild(botao(doc, "− Linha", acao("tabela-menos-linha")));
        alvo.appendChild(botao(doc, "+ Coluna", acao("tabela-mais-coluna")));
        alvo.appendChild(botao(doc, "− Coluna", acao("tabela-menos-coluna")));
        alvo.appendChild(rotuloCurto(doc, "Borda"));
        alvo.appendChild(numero(doc, p.border_width === undefined ? 0.5 : p.border_width,
          function (n) { mudar({ border_width: n }); }, pode, "0.25"));
        break;
      }
      case "line": {
        alvo.appendChild(rotuloCurto(doc, "Espessura"));
        alvo.appendChild(numero(doc, p.thickness || 1, function (n) { mudar({ thickness: n }); },
          pode, "0.25"));
        alvo.appendChild(seletor(doc, p.style || "solid",
          [{ value: "solid", label: "Contínua" }, { value: "dashed", label: "Tracejada" },
           { value: "dotted", label: "Pontilhada" }],
          function (v) { mudar({ style: v }); }, pode));
        alvo.appendChild(rotuloCurto(doc, "Cor"));
        alvo.appendChild(textoCurto(doc, p.color || "#000000", function (v) {
          if (/^#[0-9a-fA-F]{6}$/.test(v)) { mudar({ color: v }); }
        }, pode, "#000000"));
        break;
      }
      case "rectangle": {
        alvo.appendChild(rotuloCurto(doc, "Borda"));
        alvo.appendChild(numero(doc, p.border_width || 0, function (n) { mudar({ border_width: n }); },
          pode, "0.25"));
        alvo.appendChild(rotuloCurto(doc, "Fundo"));
        alvo.appendChild(textoCurto(doc, p.fill_color || "", function (v) {
          if (!v) { mudar({ fill_color: null }); } else if (/^#[0-9a-fA-F]{6}$/.test(v)) { mudar({ fill_color: v }); }
        }, pode, "#rrggbb ou vazio"));
        alvo.appendChild(rotuloCurto(doc, "Cantos"));
        alvo.appendChild(numero(doc, p.radius || 0, function (n) { mudar({ radius: n }); }, pode, "0.5"));
        break;
      }
      case "page_break":
        break;
      default:
        break;
    }

    if (pode) {
      var acoes = criarNo(doc, "span", "te-ctx-acoes");
      if (elemento.type === "page_break") {
        acoes.appendChild(botao(doc, "Remover quebra", acao("remover"), "is-perigo"));
      } else {
        if (elemento.type !== "table") {
          acoes.appendChild(botao(doc, "Duplicar", acao("duplicar")));
        }
        acoes.appendChild(botao(doc, "Para frente", acao("frente")));
        acoes.appendChild(botao(doc, "Para trás", acao("tras")));
        acoes.appendChild(botao(doc, "Apagar", acao("remover"), "is-perigo"));
      }
      alvo.appendChild(acoes);
    }
    return alvo;
  }

  // --- a barra de ferramentas reflete o bloco ativo ------------------------------------

  function opcaoExtra(select, valor, rotulo) {
    var existente = null;
    for (var i = 0; i < select.options.length; i += 1) {
      if (select.options[i].dataset && select.options[i].dataset.extra !== undefined) {
        existente = select.options[i];
      }
    }
    if (existente) {
      existente.parentNode.removeChild(existente);
    }
    if (valor === null) {
      return;
    }
    var op = select.ownerDocument.createElement("option");
    op.value = String(valor);
    op.textContent = rotulo;
    op.dataset.extra = "1";
    select.appendChild(op);
  }

  function marcarValor(select, valor, rotuloExtra) {
    if (!select) {
      return;
    }
    var achou = false;
    for (var i = 0; i < select.options.length; i += 1) {
      if (String(select.options[i].value) === String(valor) &&
          !(select.options[i].dataset && select.options[i].dataset.extra)) {
        achou = true;
      }
    }
    opcaoExtra(select, achou ? null : valor, rotuloExtra);
    select.value = String(valor);
  }

  /*
   * Deixa a barra de ferramentas dizendo a verdade sobre o bloco ativo
   * e a selecao: estilo do bloco, fonte, corpo, entrelinha, alinhamento,
   * lista, e os quatro botoes de enfase.
   *
   * `estado`: { bloco (elemento ou null), selecao: {bold, italic,
   *   underline, strike, font_size, font_family}, editavel }
   * `nos`: os controles, achados pelo editor uma vez.
   */
  function refletir(nos, estado) {
    var bloco = estado.bloco;
    var p = (bloco && bloco.properties) || {};
    var sel = estado.selecao || {};
    var textual = !!bloco && Doc.eTexto(bloco);
    var editavel = estado.editavel !== false;

    (nos.soDeBloco || []).forEach(function (no) {
      no.disabled = !editavel || !textual;
    });

    if (nos.estilo) {
      nos.estilo.value = textual ? Doc.estiloDoBloco(bloco) : "p";
    }
    if (nos.fonte) {
      marcarValor(nos.fonte, sel.font_family || p.font_family || "LiberationSans", "Atual");
    }
    if (nos.tamanho) {
      var corpo = sel.font_size || p.font_size || 11;
      marcarValor(nos.tamanho, corpo, "Atual (" + String(corpo).replace(".", ",") + " pt)");
    }
    if (nos.entrelinha) {
      var lh = p.line_height || 1.25;
      marcarValor(nos.entrelinha, lh, "Atual (" + String(Math.round(lh * 100) / 100).replace(".", ",") + ")");
    }
    var ligar = function (no, ativo) {
      if (no) {
        no.classList.toggle("is-ativo", !!ativo);
        no.setAttribute("aria-pressed", ativo ? "true" : "false");
      }
    };
    ligar(nos.negrito, sel.bold);
    ligar(nos.italico, sel.italic);
    ligar(nos.sublinhado, sel.underline);
    ligar(nos.riscado, sel.strike);
    var alinhamento = textual ? (p.align || "left") : "";
    ["left", "center", "right", "justify"].forEach(function (a) {
      ligar(nos["alinhar_" + a], alinhamento === a);
    });
    var lista = textual ? Doc.tipoDeLista(bloco) : "";
    ligar(nos.listaMarcadores, lista === "marcadores");
    ligar(nos.listaNumerada, lista === "numerada");
  }

  return {
    campoBate: campoBate,
    montarCampos: montarCampos,
    montarUsos: montarUsos,
    montarBarraDoElemento: montarBarraDoElemento,
    marcarValor: marcarValor,
    refletir: refletir
  };
});
