/*
 * Painel de propriedades do elemento selecionado.
 *
 * Editor visual dos modelos da biblioteca (Etapa 3.2).
 *
 * O painel e MONTADO A PARTIR DO REGISTRO que o servidor entrega
 * (`elements.py` -> `para_o_editor()`): cada propriedade declara nome,
 * rotulo, tipo de valor e opcoes. Nao ha uma segunda lista de
 * propriedades escrita em JavaScript -- se um tipo ganhar um atributo no
 * registro, ele aparece aqui sozinho, e o validador do servidor ja o
 * conhece.
 *
 * Geometria (X/Y/largura/altura) e sempre editavel por numero, nao so
 * pelo mouse: o documento pede precisao decimal que arrastar nao alcanca.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.TEProperties = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Passo fino nos campos numericos: o layout guarda casas decimais e o
  // teclado precisa alcanca-las.
  var PASSO_PADRAO = "0.01";

  function criarNo(doc, tag, classe) {
    var no = doc.createElement(tag);
    if (classe) {
      no.className = classe;
    }
    return no;
  }

  function campoComRotulo(doc, rotulo, entrada) {
    var bloco = criarNo(doc, "label", "te-campo");
    var nome = criarNo(doc, "span");
    nome.textContent = rotulo;
    bloco.appendChild(nome);
    bloco.appendChild(entrada);
    return bloco;
  }

  function entradaNumero(doc, valor, aoMudar, passo, habilitado) {
    var entrada = criarNo(doc, "input", "input");
    entrada.type = "number";
    entrada.step = passo || PASSO_PADRAO;
    entrada.value = valor === null || valor === undefined ? "" : valor;
    entrada.disabled = !habilitado;
    entrada.addEventListener("change", function () {
      var n = parseFloat(entrada.value);
      if (!isNaN(n)) {
        aoMudar(n);
      }
    });
    return entrada;
  }

  function entradaTexto(doc, valor, aoMudar, habilitado, multilinha) {
    var entrada = criarNo(doc, multilinha ? "textarea" : "input", "input");
    entrada.value = valor === null || valor === undefined ? "" : valor;
    entrada.disabled = !habilitado;
    if (multilinha) {
      entrada.rows = 3;
    }
    entrada.addEventListener("change", function () {
      aoMudar(entrada.value);
    });
    return entrada;
  }

  function entradaEscolha(doc, valor, opcoes, aoMudar, habilitado) {
    var selecao = criarNo(doc, "select", "input");
    selecao.disabled = !habilitado;
    opcoes.forEach(function (opcao) {
      var item = criarNo(doc, "option");
      item.value = opcao.value;
      item.textContent = opcao.label;
      if (String(opcao.value) === String(valor)) {
        item.selected = true;
      }
      selecao.appendChild(item);
    });
    selecao.addEventListener("change", function () {
      aoMudar(selecao.value);
    });
    return selecao;
  }

  function entradaBooleano(doc, valor, aoMudar, habilitado) {
    var entrada = criarNo(doc, "input");
    entrada.type = "checkbox";
    entrada.checked = !!valor;
    entrada.disabled = !habilitado;
    entrada.addEventListener("change", function () {
      aoMudar(entrada.checked);
    });
    return entrada;
  }

  /*
   * Uma propriedade declarada no registro vira o controle adequado ao
   * seu `kind`. `conteudo`, `colunas` e `linhas` sao estruturas: o
   * conteudo simples e editavel aqui; tabela fica com o que ja da para
   * mostrar, e o editor de celulas e etapa seguinte.
   */
  function controleDaPropriedade(doc, declaracao, valor, aoMudar, contexto) {
    var habilitado = contexto.editavel;

    switch (declaracao.kind) {
      case "numero":
      case "positivo":
      case "nao_neg":
        return campoComRotulo(
          doc, declaracao.label,
          entradaNumero(doc, valor, aoMudar, PASSO_PADRAO, habilitado)
        );

      case "booleano": {
        var bloco = criarNo(doc, "label", "te-campo te-campo-check");
        bloco.appendChild(entradaBooleano(doc, valor, aoMudar, habilitado));
        var nome = criarNo(doc, "span");
        nome.textContent = declaracao.label;
        bloco.appendChild(nome);
        return bloco;
      }

      case "escolha":
        return campoComRotulo(
          doc, declaracao.label,
          entradaEscolha(
            doc, valor,
            declaracao.options.map(function (o) {
              return { value: o, label: o };
            }),
            aoMudar, habilitado
          )
        );

      case "cor":
        return campoComRotulo(
          doc, declaracao.label,
          entradaTexto(doc, valor, aoMudar, habilitado)
        );

      case "texto":
        return campoComRotulo(
          doc, declaracao.label,
          entradaTexto(doc, valor, aoMudar, habilitado)
        );

      case "caixa": {
        var caixa = criarNo(doc, "div", "te-campo");
        var titulo = criarNo(doc, "span");
        titulo.textContent = declaracao.label;
        caixa.appendChild(titulo);
        var grade = criarNo(doc, "div", "te-grade-4");
        ["top", "right", "bottom", "left"].forEach(function (lado) {
          var atual = (valor || {})[lado] || 0;
          grade.appendChild(
            entradaNumero(doc, atual, function (n) {
              var novo = Object.assign({ top: 0, right: 0, bottom: 0, left: 0 }, valor || {});
              novo[lado] = n;
              aoMudar(novo);
            }, PASSO_PADRAO, habilitado)
          );
        });
        caixa.appendChild(grade);
        return caixa;
      }

      case "conteudo":
        return controleDeConteudo(doc, declaracao, valor, aoMudar, contexto);

      case "colunas":
      case "linhas": {
        // Estrutural: o editor de celulas e etapa seguinte. Aqui o que
        // interessa e a pessoa ver o que existe, sem ilusao de edicao.
        var resumo = criarNo(doc, "p", "te-resumo");
        var quantos = Array.isArray(valor) ? valor.length : 0;
        resumo.textContent = declaracao.label + ": " + quantos;
        return resumo;
      }

      default:
        return null;
    }
  }

  /*
   * Conteudo estrutural. Um bloco `text` vira caixa de texto; um `field`
   * vira seletor de campo; `mixed` fica em leitura -- editar a sequencia
   * de trechos e etapa seguinte, e uma caixa de texto simples destruiria
   * a estrutura.
   */
  function controleDeConteudo(doc, declaracao, valor, aoMudar, contexto) {
    var bloco = valor || { kind: "text", value: "" };
    var habilitado = contexto.editavel;

    if (bloco.kind === "asset") {
      return campoComRotulo(
        doc, declaracao.label,
        entradaEscolha(
          doc, bloco.asset_id,
          [{ value: 0, label: "— escolher —" }].concat(
            (contexto.assets || []).map(function (a) {
              return { value: a.id, label: a.label };
            })
          ),
          function (v) {
            aoMudar({ kind: "asset", asset_id: parseInt(v, 10) || 0 });
          },
          habilitado
        )
      );
    }

    if (bloco.kind === "field") {
      return campoComRotulo(
        doc, declaracao.label + " (campo)",
        entradaEscolha(
          doc, bloco.source,
          [{ value: "", label: "— escolher —" }].concat(
            (contexto.referencias || []).map(function (r) {
              return { value: r.reference, label: r.label };
            })
          ),
          function (v) {
            aoMudar({ kind: "field", source: v });
          },
          habilitado
        )
      );
    }

    if (bloco.kind === "mixed") {
      var resumo = criarNo(doc, "p", "te-resumo");
      var partes = (bloco.parts || []).length;
      resumo.textContent = declaracao.label + ": " + partes + " trecho(s)";
      return resumo;
    }

    return campoComRotulo(
      doc, declaracao.label,
      entradaTexto(doc, bloco.value, function (v) {
        aoMudar({ kind: "text", value: v });
      }, habilitado, true)
    );
  }

  /*
   * Monta o painel inteiro.
   *
   * `contexto`: { editavel, catalogo, referencias, assets, modelo,
   *               aoAlterarGeometria, aoAlterarPropriedade, aoAcao }
   */
  function desenharPainel(doc, alvo, elemento, contexto) {
    while (alvo.firstChild) {
      alvo.removeChild(alvo.firstChild);
    }

    if (!elemento) {
      // Sem selecao: o que se mostra e o documento.
      var titulo = criarNo(doc, "h3");
      titulo.textContent = "Documento";
      alvo.appendChild(titulo);
      (contexto.modelo || []).forEach(function (linha) {
        var p = criarNo(doc, "p", "te-resumo");
        p.textContent = linha;
        alvo.appendChild(p);
      });
      var dica = criarNo(doc, "p", "te-vazio");
      dica.textContent = "Selecione um elemento para ver suas propriedades.";
      alvo.appendChild(dica);
      return;
    }

    var declarado = null;
    (contexto.catalogo || []).forEach(function (t) {
      if (t.code === elemento.type) {
        declarado = t;
      }
    });

    var cabecalho = criarNo(doc, "h3");
    cabecalho.textContent = (declarado && declarado.label) || elemento.type;
    alvo.appendChild(cabecalho);

    // Geometria primeiro: e o que mais se ajusta, e por numero.
    var geometria = criarNo(doc, "div", "te-grade-2");
    [
      ["x", "X"], ["y", "Y"], ["width", "Largura"], ["height", "Altura"]
    ].forEach(function (par) {
      geometria.appendChild(
        campoComRotulo(
          doc, par[1],
          entradaNumero(doc, elemento[par[0]], function (n) {
            contexto.aoAlterarGeometria(par[0], n);
          }, PASSO_PADRAO, contexto.editavel)
        )
      );
    });
    alvo.appendChild(geometria);

    (declarado ? declarado.properties : []).forEach(function (declaracao) {
      var controle = controleDaPropriedade(
        doc, declaracao,
        (elemento.properties || {})[declaracao.name],
        function (v) {
          contexto.aoAlterarPropriedade(declaracao.name, v);
        },
        contexto
      );
      if (controle) {
        alvo.appendChild(controle);
      }
    });

    if (!contexto.editavel) {
      return;
    }

    var acoes = criarNo(doc, "div", "te-acoes-elemento");
    [
      ["duplicar", "Duplicar"],
      ["frente", "Para frente"],
      ["tras", "Para trás"],
      ["topo", "Trazer ao topo"],
      ["fundo", "Enviar ao fundo"],
      ["remover", "Apagar"]
    ].forEach(function (par) {
      var botao = criarNo(doc, "button", "btn btn-ghost btn-sm");
      botao.type = "button";
      botao.textContent = par[1];
      botao.addEventListener("click", function () {
        contexto.aoAcao(par[0]);
      });
      acoes.appendChild(botao);
    });
    alvo.appendChild(acoes);
  }

  return {
    PASSO_PADRAO: PASSO_PADRAO,
    controleDaPropriedade: controleDaPropriedade,
    controleDeConteudo: controleDeConteudo,
    desenharPainel: desenharPainel
  };
});
