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

  // As duas propriedades que um TRECHO de conteudo misto pode ter por
  // conta propria. Ausentes, o trecho herda o peso e o estilo do
  // elemento -- e o contrato de `layout_schema.ENFASE_DO_TRECHO`.
  var ENFASE_DO_TRECHO = ["font_weight", "font_style"];

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
   * seu `kind`. `conteudo`, `colunas` e `linhas` sao estruturas, e as
   * tres tem editor proprio -- inclusive as celulas da tabela, que
   * aceitam o mesmo conteudo estrutural de qualquer texto do documento.
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
        return declaracao.kind === "colunas"
          ? controleDeColunas(doc, declaracao, valor, contexto)
          : controleDeLinhas(doc, declaracao, valor, contexto);
      }

      default:
        return null;
    }
  }


  // ---------------------------------------------------------------------
  // Tabela
  // ---------------------------------------------------------------------

  function copiarRaso(objeto) {
    var copia = {};
    Object.keys(objeto || {}).forEach(function (chave) {
      copia[chave] = objeto[chave];
    });
    return copia;
  }

  function copiarLinha(linha) {
    var copia = copiarRaso(linha);
    copia.cells = (linha && linha.cells ? linha.cells : []).map(copiarRaso);
    return copia;
  }

  function celulaVazia() {
    return { content: { kind: "text", value: "" }, align: "left", bold: false };
  }

  function propriedadesDaTabela(contexto) {
    return ((contexto.elemento || {}).properties) || {};
  }

  /*
   * As colunas: largura, alinhamento, acrescentar e remover.
   *
   * Acrescentar e remover mexem TAMBEM nas linhas, porque o validador
   * cobra uma celula por coluna em cada linha. As duas propriedades vao
   * juntas numa alteracao so.
   */
  function controleDeColunas(doc, declaracao, valor, contexto) {
    var colunas = Array.isArray(valor) ? valor : [];
    var linhas = propriedadesDaTabela(contexto).rows || [];

    function publicarColunas(novasColunas, novasLinhas) {
      if (contexto.aoAlterarPropriedades) {
        contexto.aoAlterarPropriedades({ columns: novasColunas, rows: novasLinhas });
      }
    }

    var caixa = criarNo(doc, "div", "te-tabela-editor");
    var titulo = criarNo(doc, "h4", "te-misto-titulo");
    titulo.textContent = declaracao.label + " (" + colunas.length + ")";
    caixa.appendChild(titulo);

    colunas.forEach(function (coluna, indice) {
      var linha = criarNo(doc, "div", "te-coluna");
      var numero = criarNo(doc, "span", "te-trecho-numero");
      numero.textContent = String(indice + 1);
      linha.appendChild(numero);

      var corpo = criarNo(doc, "div", "te-grade-2");
      corpo.appendChild(
        campoComRotulo(
          doc, "Largura",
          entradaNumero(doc, coluna.width, function (n) {
            var novas = colunas.map(copiarRaso);
            novas[indice].width = n;
            publicarColunas(novas, linhas);
          }, PASSO_PADRAO, contexto.editavel)
        )
      );
      corpo.appendChild(
        campoComRotulo(
          doc, "Alinhamento",
          entradaEscolha(
            doc, coluna.align || "left",
            opcoesDeclaradas(contexto, "align").map(function (v) {
              return { value: v, label: v };
            }),
            function (v) {
              var novas = colunas.map(copiarRaso);
              novas[indice].align = v;
              publicarColunas(novas, linhas);
            },
            contexto.editavel
          )
        )
      );
      linha.appendChild(corpo);

      if (contexto.editavel && colunas.length > 1) {
        var acoes = criarNo(doc, "div", "te-trecho-acoes");
        acoes.appendChild(
          botaoDeTrecho(doc, "✕", "Remover coluna", function () {
            var novasColunas = colunas.filter(function (_c, i) {
              return i !== indice;
            }).map(copiarRaso);
            var novasLinhas = linhas.map(function (l) {
              var copia = copiarLinha(l);
              copia.cells = copia.cells.filter(function (_c, i) {
                return i !== indice;
              });
              return copia;
            });
            publicarColunas(novasColunas, novasLinhas);
          })
        );
        linha.appendChild(acoes);
      }
      caixa.appendChild(linha);
    });

    if (contexto.editavel) {
      var novos = criarNo(doc, "div", "te-misto-novos");
      var botao = criarNo(doc, "button", "btn btn-secondary btn-sm");
      botao.type = "button";
      botao.textContent = "+ Coluna";
      botao.addEventListener("click", function () {
        var novasColunas = colunas.map(copiarRaso);
        novasColunas.push({ width: 60, align: "left" });
        var novasLinhas = linhas.map(function (l) {
          var copia = copiarLinha(l);
          copia.cells.push(celulaVazia());
          return copia;
        });
        publicarColunas(novasColunas, novasLinhas);
      });
      novos.appendChild(botao);
      caixa.appendChild(novos);
    }

    return caixa;
  }

  /*
   * As linhas e as celulas.
   *
   * O conteudo de cada celula passa pelo MESMO `controleDeConteudo` do
   * resto do painel -- entao uma celula aceita texto, campo dinamico ou
   * sequencia mista sem nenhum codigo novo, que e exatamente o que o
   * contrato do servidor ja permitia.
   */
  function controleDeLinhas(doc, declaracao, valor, contexto) {
    var linhas = Array.isArray(valor) ? valor : [];
    var colunas = propriedadesDaTabela(contexto).columns || [];

    function publicar(novas) {
      if (contexto.aoAlterarPropriedades) {
        contexto.aoAlterarPropriedades({ rows: novas });
      }
    }

    var caixa = criarNo(doc, "div", "te-tabela-editor");
    var titulo = criarNo(doc, "h4", "te-misto-titulo");
    titulo.textContent = declaracao.label + " (" + linhas.length + ")";
    caixa.appendChild(titulo);

    linhas.forEach(function (linha, iLinha) {
      var bloco = criarNo(doc, "div", "te-linha");

      var cabeca = criarNo(doc, "div", "te-linha-cabeca");
      var numero = criarNo(doc, "span", "te-trecho-numero");
      numero.textContent = "Linha " + (iLinha + 1);
      cabeca.appendChild(numero);
      cabeca.appendChild(
        campoComRotulo(
          doc, "Altura mín.",
          entradaNumero(doc, linha.min_height || 0, function (n) {
            var novas = linhas.map(copiarLinha);
            novas[iLinha].min_height = n;
            publicar(novas);
          }, PASSO_PADRAO, contexto.editavel)
        )
      );

      if (contexto.editavel) {
        var acoes = criarNo(doc, "div", "te-trecho-acoes");
        if (iLinha > 0) {
          acoes.appendChild(
            botaoDeTrecho(doc, "↑", "Subir linha", function () {
              var novas = linhas.map(copiarLinha);
              var tirada = novas.splice(iLinha, 1)[0];
              novas.splice(iLinha - 1, 0, tirada);
              publicar(novas);
            })
          );
        }
        if (iLinha < linhas.length - 1) {
          acoes.appendChild(
            botaoDeTrecho(doc, "↓", "Descer linha", function () {
              var novas = linhas.map(copiarLinha);
              var tirada = novas.splice(iLinha, 1)[0];
              novas.splice(iLinha + 1, 0, tirada);
              publicar(novas);
            })
          );
        }
        acoes.appendChild(
          botaoDeTrecho(doc, "✕", "Remover linha", function () {
            publicar(
              linhas.filter(function (_l, i) {
                return i !== iLinha;
              }).map(copiarLinha)
            );
          })
        );
        cabeca.appendChild(acoes);
      }
      bloco.appendChild(cabeca);

      (linha.cells || []).forEach(function (celula, iCelula) {
        var caixaDaCelula = criarNo(doc, "div", "te-celula");
        var rotulo = criarNo(doc, "span", "te-celula-rotulo");
        rotulo.textContent = "Célula " + (iCelula + 1);
        caixaDaCelula.appendChild(rotulo);

        caixaDaCelula.appendChild(
          controleDeConteudo(
            doc, { label: "Conteúdo" },
            celula.content || { kind: "text", value: "" },
            function (novoConteudo) {
              var novas = linhas.map(copiarLinha);
              novas[iLinha].cells[iCelula].content = novoConteudo;
              publicar(novas);
            },
            contexto
          )
        );

        var extras = criarNo(doc, "div", "te-grade-2");
        extras.appendChild(
          campoComRotulo(
            doc, "Alinhamento",
            entradaEscolha(
              doc, celula.align || "left",
              opcoesDeclaradas(contexto, "align").map(function (v) {
                return { value: v, label: v };
              }),
              function (v) {
                var novas = linhas.map(copiarLinha);
                novas[iLinha].cells[iCelula].align = v;
                publicar(novas);
              },
              contexto.editavel
            )
          )
        );
        extras.appendChild(
          campoComRotulo(
            doc, "Negrito",
            entradaBooleano(doc, celula.bold, function (marcado) {
              var novas = linhas.map(copiarLinha);
              novas[iLinha].cells[iCelula].bold = marcado;
              publicar(novas);
            }, contexto.editavel)
          )
        );
        caixaDaCelula.appendChild(extras);
        bloco.appendChild(caixaDaCelula);
      });

      caixa.appendChild(bloco);
    });

    if (contexto.editavel) {
      var novos = criarNo(doc, "div", "te-misto-novos");
      var botao = criarNo(doc, "button", "btn btn-secondary btn-sm");
      botao.type = "button";
      botao.textContent = "+ Linha";
      botao.addEventListener("click", function () {
        var novas = linhas.map(copiarLinha);
        // Uma celula por COLUNA -- e a invariante que o servidor cobra.
        novas.push({
          min_height: 0,
          cells: colunas.map(function () {
            return celulaVazia();
          })
        });
        publicar(novas);
      });
      novos.appendChild(botao);
      caixa.appendChild(novos);
    }

    return caixa;
  }

  /*
   * As opcoes declaradas para uma propriedade, vindas do REGISTRO do
   * servidor. Peso e estilo de um trecho usam o MESMO vocabulario do
   * elemento -- e ler do registro evita uma segunda lista para manter
   * em dia.
   */
  function opcoesDeclaradas(contexto, nome) {
    var achadas = [];
    (contexto.catalogo || []).forEach(function (tipo) {
      (tipo.properties || []).forEach(function (propriedade) {
        if (propriedade.name === nome && achadas.length === 0) {
          achadas = propriedade.options || [];
        }
      });
    });
    return achadas;
  }

  /*
   * Copia rasa de um trecho. Toda alteracao devolve trechos NOVOS: um
   * trecho compartilhado entre o antes e o depois faria o desfazer
   * enxergar o estado ja alterado.
   */
  function copiarTrecho(parte) {
    var copia = {};
    Object.keys(parte || {}).forEach(function (chave) {
      copia[chave] = parte[chave];
    });
    return copia;
  }

  /*
   * Converte um trecho de Texto para Campo, ou o contrario, PRESERVANDO
   * a enfase. O valor nao atravessa: um texto livre nao e referencia de
   * campo, e uma referencia nao e texto para se ler.
   */
  function converterTrecho(parte, paraKind) {
    var novo = { kind: paraKind };
    ENFASE_DO_TRECHO.forEach(function (chave) {
      if (parte && parte[chave] !== undefined) {
        novo[chave] = parte[chave];
      }
    });
    if (paraKind === "field") {
      novo.source = "";
    } else {
      novo.value = "";
    }
    return novo;
  }

  /*
   * O seletor de enfase de um trecho.
   *
   * A opcao vazia significa HERDAR do elemento, e herdar e a ausencia da
   * chave -- nao um valor "herda" gravado. Por isso escolher o vazio
   * APAGA a chave em vez de grava-la.
   */
  function seletorDeEnfase(doc, parte, nome, rotulo, contexto, aoTrocar) {
    var opcoes = [{ value: "", label: "— herda do elemento —" }];
    opcoesDeclaradas(contexto, nome).forEach(function (valor) {
      opcoes.push({ value: valor, label: valor });
    });
    return campoComRotulo(
      doc, rotulo,
      entradaEscolha(
        doc, parte[nome] === undefined ? "" : parte[nome], opcoes,
        function (escolhido) {
          var novo = copiarTrecho(parte);
          if (escolhido === "") {
            delete novo[nome];
          } else {
            novo[nome] = escolhido;
          }
          aoTrocar(novo);
        },
        contexto.editavel
      )
    );
  }

  /*
   * Uma linha da sequencia: o que o trecho e, o que ele diz, a enfase
   * dele e o que da para fazer com ele.
   */
  function linhaDoTrecho(doc, parte, indice, total, contexto, acoes) {
    var linha = criarNo(doc, "div", "te-trecho");

    var numero = criarNo(doc, "span", "te-trecho-numero");
    numero.textContent = String(indice + 1);
    linha.appendChild(numero);

    var corpo = criarNo(doc, "div", "te-trecho-corpo");

    corpo.appendChild(
      campoComRotulo(
        doc, "O que é",
        entradaEscolha(
          doc, parte.kind,
          [{ value: "text", label: "Texto" }, { value: "field", label: "Campo" }],
          function (escolhido) {
            if (escolhido !== parte.kind) {
              acoes.trocar(indice, converterTrecho(parte, escolhido));
            }
          },
          contexto.editavel
        )
      )
    );

    if (parte.kind === "field") {
      corpo.appendChild(
        campoComRotulo(
          doc, "Campo",
          entradaEscolha(
            doc, parte.source,
            [{ value: "", label: "— escolher —" }].concat(
              (contexto.referencias || []).map(function (r) {
                return { value: r.reference, label: r.label };
              })
            ),
            function (v) {
              var novo = copiarTrecho(parte);
              novo.source = v;
              acoes.trocar(indice, novo);
            },
            contexto.editavel
          )
        )
      );
    } else {
      corpo.appendChild(
        campoComRotulo(
          doc, "Texto",
          entradaTexto(
            doc, parte.value,
            function (v) {
              var novo = copiarTrecho(parte);
              novo.value = v;
              acoes.trocar(indice, novo);
            },
            contexto.editavel, false
          )
        )
      );
    }

    var enfase = criarNo(doc, "div", "te-grade-2");
    enfase.appendChild(
      seletorDeEnfase(doc, parte, "font_weight", "Peso", contexto, function (novo) {
        acoes.trocar(indice, novo);
      })
    );
    enfase.appendChild(
      seletorDeEnfase(doc, parte, "font_style", "Estilo", contexto, function (novo) {
        acoes.trocar(indice, novo);
      })
    );
    corpo.appendChild(enfase);

    linha.appendChild(corpo);

    if (contexto.editavel) {
      var botoes = criarNo(doc, "div", "te-trecho-acoes");
      // Quem esta no topo nao recebe "subir": botao que nao faz nada e
      // o que este projeto tira de tela desde a Etapa I.
      if (indice > 0) {
        botoes.appendChild(
          botaoDeTrecho(doc, "↑", "Subir", function () {
            acoes.mover(indice, indice - 1);
          })
        );
      }
      if (indice < total - 1) {
        botoes.appendChild(
          botaoDeTrecho(doc, "↓", "Descer", function () {
            acoes.mover(indice, indice + 1);
          })
        );
      }
      botoes.appendChild(
        botaoDeTrecho(doc, "✕", "Remover", function () {
          acoes.remover(indice);
        })
      );
      linha.appendChild(botoes);
    }

    return linha;
  }

  function botaoDeTrecho(doc, simbolo, titulo, aoClicar) {
    var botao = criarNo(doc, "button", "btn btn-ghost btn-icon-sm");
    botao.type = "button";
    botao.textContent = simbolo;
    botao.setAttribute("title", titulo);
    botao.setAttribute("aria-label", titulo);
    botao.addEventListener("click", aoClicar);
    return botao;
  }

  /*
   * O editor da sequencia inteira.
   *
   * Toda alteracao monta uma LISTA NOVA e devolve o bloco completo. Nada
   * e juntado: `texto + campo + texto` continua sendo tres trechos
   * depois de editar qualquer um deles -- e disso que depende o campo
   * dinamico nao virar texto solto na hora de gerar o documento.
   */
  function controleDeMisto(doc, declaracao, bloco, aoMudar, contexto) {
    var partes = Array.isArray(bloco.parts) ? bloco.parts : [];

    function publicar(novas) {
      aoMudar({ kind: "mixed", parts: novas });
    }

    var acoes = {
      trocar: function (indice, novo) {
        var novas = partes.map(copiarTrecho);
        novas[indice] = novo;
        publicar(novas);
      },
      mover: function (de, para) {
        var novas = partes.map(copiarTrecho);
        var tirado = novas.splice(de, 1)[0];
        novas.splice(para, 0, tirado);
        publicar(novas);
      },
      remover: function (indice) {
        var novas = partes.map(copiarTrecho);
        novas.splice(indice, 1);
        publicar(novas);
      },
      acrescentar: function (kind) {
        var novas = partes.map(copiarTrecho);
        novas.push(kind === "field" ? { kind: "field", source: "" } : { kind: "text", value: "" });
        publicar(novas);
      }
    };

    var caixa = criarNo(doc, "div", "te-misto");

    var titulo = criarNo(doc, "h4", "te-misto-titulo");
    titulo.textContent = declaracao.label + " (sequência)";
    caixa.appendChild(titulo);

    if (partes.length === 0) {
      var vazio = criarNo(doc, "p", "te-vazio");
      vazio.textContent = "Nenhum trecho ainda.";
      caixa.appendChild(vazio);
    }

    partes.forEach(function (parte, indice) {
      caixa.appendChild(
        linhaDoTrecho(doc, parte || {}, indice, partes.length, contexto, acoes)
      );
    });

    if (contexto.editavel) {
      var novos = criarNo(doc, "div", "te-misto-novos");
      [["text", "+ Texto"], ["field", "+ Campo"]].forEach(function (par) {
        var botao = criarNo(doc, "button", "btn btn-secondary btn-sm");
        botao.type = "button";
        botao.textContent = par[1];
        botao.addEventListener("click", function () {
          acoes.acrescentar(par[0]);
        });
        novos.appendChild(botao);
      });
      caixa.appendChild(novos);
    }

    return caixa;
  }

  /*
   * Conteudo estrutural. Um bloco `text` vira caixa de texto, um `field`
   * vira seletor de campo, um `asset` vira seletor de imagem -- e
   * `mixed` vira o editor de SEQUENCIA acima, porque uma caixa de texto
   * unica faria `texto + campo + texto` virar uma string so e os campos
   * perderiam identidade.
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
      return controleDeMisto(doc, declaracao, bloco, aoMudar, contexto);
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

    // A tabela precisa enxergar `columns` e `rows` ao mesmo tempo para
    // manter `len(cells) == len(columns)`. Entregar o elemento e mais
    // honesto do que fazer o controle adivinhar pelo irmao.
    var contextoDoElemento = Object.create(contexto);
    contextoDoElemento.elemento = elemento;

    (declarado ? declarado.properties : []).forEach(function (declaracao) {
      var controle = controleDaPropriedade(
        doc, declaracao,
        (elemento.properties || {})[declaracao.name],
        function (v) {
          contexto.aoAlterarPropriedade(declaracao.name, v);
        },
        contextoDoElemento
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
    controleDeMisto: controleDeMisto,
    controleDeColunas: controleDeColunas,
    controleDeLinhas: controleDeLinhas,
    converterTrecho: converterTrecho,
    desenharPainel: desenharPainel
  };
});
