/*
 * O documento como FLUXO sobre um layout de coordenadas (Etapa 3.7).
 *
 * O layout continua guardando cada elemento em x/y/width/height (pt) --
 * e a geometria medida do documento oficial, e o renderer PDF a desenha
 * tal e qual. O que este modulo acrescenta e a leitura de DOCUMENTO
 * dessa geometria: ordem de leitura, "o que esta abaixo", empurrar o
 * que esta abaixo quando um bloco cresce, inserir um bloco depois de
 * outro, dividir e juntar paragrafos, listas, margens, paginas.
 *
 * REFLUXO
 * -------
 * Quando um paragrafo cresce N pontos (o editor mediu o texto), tudo
 * que COMECA abaixo do pe antigo dele desce N pontos -- e so isso. O
 * que esta ao lado (o marcador "1." de um item, o logo ao lado do QR)
 * nao se mexe, e o que esta acima tambem nao. Coordenadas que nao
 * precisam mudar ficam exatamente como estavam: e o que preserva a
 * medida do documento oficial numa copia que so teve um paragrafo
 * editado.
 *
 * Tudo puro: recebe um layout, devolve um layout novo. Nada de DOM.
 */
(function (root, factory) {
  var api = factory(
    typeof require === "function" ? require("./state.js") : root.TEState,
    typeof require === "function" ? require("./runs.js") : root.TERuns
  );
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.TEDocument = api;
  }
})(typeof self !== "undefined" ? self : this, function (State, Runs) {
  "use strict";

  // Tolerancia ao comparar coordenadas: o layout guarda casas decimais.
  var EPS = 0.01;

  // O respiro entre um bloco e o proximo quando o editor cria um novo.
  var ESPACO_ENTRE_BLOCOS = 6;

  // O passo do recuo (e o recuo que uma lista abre para o marcador).
  var PASSO_DO_RECUO = 18;

  // Largura que o texto guarda para si: um recuo maior do que a caixa
  // deixaria o texto sem lugar. O renderer tem a mesma guarda
  // (`elementos.LARGURA_MINIMA_DO_TEXTO`), mas o editor nem chega a
  // gravar um recuo assim -- o que se ve na tela e o que sai no PDF.
  var LARGURA_MINIMA_DO_TEXTO = 12;

  var TIPOS_DE_TEXTO = { text: 1, rich_text: 1 };

  // Marcadores de lista: numerada e com marcadores.
  var MARCADOR_DE_ITEM = "•";
  var NUMERO = /^(\d+)\.$/;

  // Os tres estilos de bloco do seletor, em propriedades do elemento.
  var ESTILOS_DE_BLOCO = {
    p: { font_size: 11, font_weight: "regular", block_style: "p" },
    h1: { font_size: 14, font_weight: "bold", align: "center", block_style: "h1" },
    h2: { font_size: 12, font_weight: "bold", block_style: "h2" }
  };

  function elementos(layout) {
    return (layout && layout.elements) || [];
  }

  function eTexto(el) {
    return !!el && TIPOS_DE_TEXTO[el.type] === 1;
  }

  function pe(el) {
    return Number(el.y) + Number(el.height || 0);
  }

  function props(el) {
    return (el && el.properties) || {};
  }

  function novoLayout(layout, lista) {
    var novo = State.normalizar(layout);
    novo.elements = lista;
    if (layout && layout.document) {
      novo.document = State.clonar(layout.document);
    }
    return novo;
  }

  // --- ordem de leitura -----------------------------------------------------

  function ordenar(layout) {
    return elementos(layout).slice().sort(function (a, b) {
      var dy = Number(a.y) - Number(b.y);
      return Math.abs(dy) > EPS ? dy : Number(a.x) - Number(b.x);
    });
  }

  function blocosDeTexto(layout) {
    return ordenar(layout).filter(eTexto);
  }

  /* O bloco de texto imediatamente ACIMA de `id`, ou null. */
  function blocoAnterior(layout, id) {
    var lista = blocosDeTexto(layout);
    for (var i = 0; i < lista.length; i += 1) {
      if (lista[i].id === id) {
        return i > 0 ? lista[i - 1] : null;
      }
    }
    return null;
  }

  function blocoSeguinte(layout, id) {
    var lista = blocosDeTexto(layout);
    for (var i = 0; i < lista.length; i += 1) {
      if (lista[i].id === id) {
        return i < lista.length - 1 ? lista[i + 1] : null;
      }
    }
    return null;
  }

  /* O ultimo bloco de texto do documento -- onde se insere sem cursor. */
  function ultimoBloco(layout) {
    var lista = blocosDeTexto(layout);
    return lista.length ? lista[lista.length - 1] : null;
  }

  // --- refluxo ----------------------------------------------------------------

  /*
   * Desloca em `delta` todo elemento que COMECA em `aPartirDe` ou
   * abaixo, menos os de `ignorar`. Uma quebra de pagina abaixo tambem
   * desce: ela e uma posicao como as outras.
   */
  function deslocar(layout, aPartirDe, delta, ignorar) {
    if (!delta) {
      return layout;
    }
    var fora = {};
    (ignorar || []).forEach(function (id) { fora[id] = true; });
    var lista = elementos(layout).map(function (el) {
      if (fora[el.id] || Number(el.y) < aPartirDe - EPS) {
        return el;
      }
      var novo = State.clonar(el);
      novo.y = Number(el.y) + delta;
      return novo;
    });
    return novoLayout(layout, lista);
  }

  /*
   * O bloco passou a ter `novaAltura`: grava e empurra (ou puxa) o que
   * comecava no pe antigo dele. Devolve o layout intacto se nada mudou.
   */
  function ajustarAltura(layout, id, novaAltura) {
    var el = State.obter(layout, id);
    if (!el) {
      return layout;
    }
    var delta = Number(novaAltura) - Number(el.height);
    if (Math.abs(delta) < 0.5) {
      return layout;
    }
    var peAntigo = pe(el);
    var comAltura = State.atualizar(layout, id, { height: Number(novaAltura) });
    return deslocar(comAltura, peAntigo, delta, [id]);
  }

  /*
   * Coloca `elemento` logo abaixo de `idRef` (ou no fim do documento),
   * abrindo espaco: o que estava abaixo desce a altura do novo mais o
   * respiro. Sem `idRef` e sem elementos, o novo vai para `y`.
   */
  function inserirDepois(layout, idRef, elemento, opcoes) {
    var o = opcoes || {};
    var espaco = o.espaco === undefined ? ESPACO_ENTRE_BLOCOS : o.espaco;
    var ref = idRef ? State.obter(layout, idRef) : null;
    var novo = State.clonar(elemento);
    var topo;
    if (ref) {
      topo = pe(ref) + espaco;
    } else {
      var maior = -Infinity;
      elementos(layout).forEach(function (el) { maior = Math.max(maior, pe(el)); });
      topo = maior === -Infinity ? (o.y || 0) : maior + espaco;
    }
    novo.y = topo;
    if (ref && eTexto(ref) && eTexto(novo) && !o.manterGeometria) {
      novo.x = ref.x;
      novo.width = ref.width;
    }
    var afastado = deslocar(layout, topo - espaco + EPS, Number(novo.height) + espaco, [novo.id]);
    return State.adicionar(afastado, novo);
  }

  /*
   * Tira `id` do documento e fecha o buraco: o primeiro elemento que
   * comecava abaixo dele passa a comecar onde ele comecava.
   */
  function remover(layout, id) {
    var el = State.obter(layout, id);
    if (!el) {
      return layout;
    }
    var proximoY = null;
    elementos(layout).forEach(function (outro) {
      if (outro.id === id || Number(outro.y) < pe(el) - EPS) {
        return;
      }
      proximoY = proximoY === null ? Number(outro.y) : Math.min(proximoY, Number(outro.y));
    });
    var sem = State.remover(layout, id);
    if (proximoY === null) {
      return sem;
    }
    return deslocar(sem, pe(el) - EPS, Number(el.y) - proximoY, []);
  }

  // --- paragrafos ---------------------------------------------------------------

  function alturaDeUmaLinha(el) {
    var p = props(el);
    return Number(p.font_size || 11) * Number(p.line_height || 1.25);
  }

  /* Um bloco de texto novo, herdando a tipografia de `ref`. */
  function novoBlocoDeTexto(id, ref, conteudo) {
    var base = ref && eTexto(ref) ? State.clonar(props(ref)) : {};
    delete base.list_marker;
    delete base.indent;
    var propriedades = {
      content: conteudo || { kind: "text", value: "" },
      font_family: base.font_family || "LiberationSans",
      font_size: base.font_size || 11,
      font_weight: "regular",
      font_style: "normal",
      text_decoration: "none",
      color: base.color || "#000000",
      letter_spacing: base.letter_spacing || 0,
      align: base.align === "center" ? "left" : (base.align || "left"),
      vertical_align: "top",
      line_height: base.line_height || 1.25,
      white_space: "normal",
      overflow: "shrink",
      padding: { top: 0, right: 0, bottom: 0, left: 0 },
      language: base.language || "",
      indent: 0,
      list_marker: "",
      block_style: "p"
    };
    var trechos = Runs.trechosDe(propriedades.content);
    var tipo = trechos.length > 1 || (trechos.length === 1 && Object.keys(Runs.estiloDe(trechos[0])).length)
      ? "rich_text" : "text";
    var el = {
      id: id,
      type: tipo,
      x: ref ? Number(ref.x) : 49.6063,
      y: 0,
      width: ref ? Number(ref.width) : 496.063,
      height: 0,
      properties: propriedades
    };
    el.height = alturaDeUmaLinha(el);
    return el;
  }

  /*
   * Grava `trechos` como conteudo de `id`. Um bloco `text` que ganhou
   * estilo ou campo no meio vira `rich_text` (mesmas propriedades; e o
   * unico tipo que aceita `mixed`).
   */
  function gravarConteudo(layout, id, trechos) {
    var el = State.obter(layout, id);
    if (!el) {
      return layout;
    }
    var bloco = Runs.blocoDe(trechos);
    var mudancas = { properties: { content: bloco } };
    if (bloco.kind === "mixed" && el.type === "text") {
      mudancas.type = "rich_text";
    }
    return State.atualizar(layout, id, mudancas);
  }

  /*
   * Divide o bloco `id` na posicao do cursor: o que vem depois vira um
   * bloco novo (`novoId`) logo abaixo. Devolve {layout, id: novoId}.
   */
  function dividirBloco(layout, id, posicao, novoId) {
    var el = State.obter(layout, id);
    if (!el || !eTexto(el) || !novoId) {
      return { layout: layout, id: null };
    }
    var partes = Runs.dividir(Runs.trechosDe(props(el).content), posicao);
    var comAntes = gravarConteudo(layout, id, partes[0]);
    var novo = novoBlocoDeTexto(novoId, el, Runs.blocoDe(partes[1]));
    // A copia herda o alinhamento e a entrelinha do original, e a lista
    // continua: um Enter num item numerado abre o item seguinte.
    novo.properties.align = props(el).align || "left";
    if (props(el).list_marker) {
      novo.properties.list_marker = NUMERO.test(props(el).list_marker)
        ? (parseInt(props(el).list_marker, 10) + 1) + "." : props(el).list_marker;
      novo.properties.indent = props(el).indent || PASSO_DO_RECUO;
    }
    var comNovo = inserirDepois(comAntes, id, novo, { espaco: 0 });
    return { layout: renumerar(comNovo), id: novoId };
  }

  /*
   * Junta o bloco `id` ao bloco de texto imediatamente acima. Devolve
   * {layout, id: anterior, posicao: onde o cursor deve ficar}.
   */
  function juntarComAnterior(layout, id) {
    var el = State.obter(layout, id);
    var anterior = blocoAnterior(layout, id);
    if (!el || !anterior) {
      return { layout: layout, id: null, posicao: 0 };
    }
    var deCima = Runs.trechosDe(props(anterior).content);
    var deBaixo = Runs.trechosDe(props(el).content);
    var posicao = Runs.comprimento(deCima);
    var juntado = gravarConteudo(layout, anterior.id, Runs.juntar(deCima, deBaixo));
    return { layout: renumerar(remover(juntado, id)), id: anterior.id, posicao: posicao };
  }

  // --- listas e recuo -----------------------------------------------------------

  /*
   * Renumera as sequencias de itens numerados: blocos de texto
   * CONSECUTIVOS na ordem de leitura, na MESMA coluna (mesmo `x`), com
   * marcador "n." contam 1, 2, 3... Um bloco sem numero na mesma coluna
   * entre eles recomeca a contagem; um bloco de outra coluna (o "1."
   * solto de um documento antigo, uma legenda ao lado) nao interfere.
   */
  function renumerar(layout) {
    var contadores = {};
    var mudou = false;
    var lista = elementos(layout);
    var ordem = blocosDeTexto(layout);
    var novos = {};
    ordem.forEach(function (el) {
      var coluna = String(Math.round(Number(el.x)));
      var marcador = props(el).list_marker || "";
      if (NUMERO.test(marcador)) {
        contadores[coluna] = (contadores[coluna] || 0) + 1;
        var certo = contadores[coluna] + ".";
        if (marcador !== certo) {
          novos[el.id] = certo;
          mudou = true;
        }
      } else {
        contadores[coluna] = 0;
      }
    });
    if (!mudou) {
      return layout;
    }
    return novoLayout(layout, lista.map(function (el) {
      if (novos[el.id] === undefined) {
        return el;
      }
      var novo = State.clonar(el);
      novo.properties.list_marker = novos[el.id];
      return novo;
    }));
  }

  function tipoDeLista(el) {
    var marcador = props(el).list_marker || "";
    if (NUMERO.test(marcador)) {
      return "numerada";
    }
    return marcador ? "marcadores" : "";
  }

  /* O maior recuo que cabe neste bloco sem espremer o texto a zero. */
  function recuoPossivel(el, pedido) {
    var p = props(el);
    var caixa = p.padding || {};
    var util = Number(el.width) - Number(caixa.left || 0) - Number(caixa.right || 0);
    return Math.max(0, Math.min(pedido, util - LARGURA_MINIMA_DO_TEXTO));
  }

  /* Liga/desliga a lista (`numerada` ou `marcadores`) no bloco. */
  function alternarLista(layout, id, tipo) {
    var el = State.obter(layout, id);
    if (!el || !eTexto(el)) {
      return layout;
    }
    var atual = tipoDeLista(el);
    var p = props(el);
    var mudancas;
    if (atual === tipo) {
      mudancas = {
        list_marker: "",
        indent: Math.max(0, Number(p.indent || 0) - PASSO_DO_RECUO)
      };
    } else {
      mudancas = {
        list_marker: tipo === "numerada" ? "1." : MARCADOR_DE_ITEM,
        indent: recuoPossivel(el, Math.max(Number(p.indent || 0), PASSO_DO_RECUO))
      };
    }
    return renumerar(State.atualizar(layout, id, { properties: mudancas }));
  }

  function recuar(layout, id, passos) {
    var el = State.obter(layout, id);
    if (!el || !eTexto(el)) {
      return layout;
    }
    var pedido = Math.max(0, Number(props(el).indent || 0) + passos * PASSO_DO_RECUO);
    return State.atualizar(layout, id, { properties: { indent: recuoPossivel(el, pedido) } });
  }

  // --- estilo de bloco -------------------------------------------------------------

  /* O que o seletor "Estilo do bloco" mostra para este bloco. */
  function estiloDoBloco(el) {
    var p = props(el);
    if (p.block_style) {
      return p.block_style;
    }
    // Um layout anterior ao editor rico nao declara: o titulo do
    // documento oficial e bold de 14pt centralizado.
    if (p.font_weight === "bold" && Number(p.font_size || 11) >= 13) {
      return "h1";
    }
    return "p";
  }

  function aplicarEstiloDoBloco(layout, id, estilo) {
    var el = State.obter(layout, id);
    var receita = ESTILOS_DE_BLOCO[estilo];
    if (!el || !eTexto(el) || !receita) {
      return layout;
    }
    var mudancas = State.clonar(receita);
    if (estilo !== "h1" && props(el).align === "center" && estiloDoBloco(el) === "h1") {
      mudancas.align = "left";
    }
    return State.atualizar(layout, id, { properties: mudancas });
  }

  // --- margens -------------------------------------------------------------------

  /*
   * A margem do documento, em pontos: a declarada em `document.margin`
   * ou, num layout antigo, a menor borda esquerda de um bloco de texto
   * ou tabela.
   */
  function margem(layout) {
    if (layout && layout.document && typeof layout.document.margin === "number") {
      return layout.document.margin;
    }
    var menor = null;
    elementos(layout).forEach(function (el) {
      if (!eTexto(el) && el.type !== "table") {
        return;
      }
      menor = menor === null ? Number(el.x) : Math.min(menor, Number(el.x));
    });
    return menor;
  }

  function comOpcoes(layout, opcoes) {
    var novo = novoLayout(layout, elementos(layout).slice());
    var atual = State.clonar((layout && layout.document) || {});
    Object.keys(opcoes || {}).forEach(function (chave) {
      atual[chave] = opcoes[chave];
    });
    novo.document = atual;
    return novo;
  }

  /*
   * Troca a margem: tudo desliza `delta` para a direita e para baixo, e
   * o que encostava na margem direita encolhe a mesma medida do outro
   * lado. Regra unica e reversivel.
   */
  function aplicarMargem(layout, pagina, nova) {
    var atual = margem(layout);
    if (atual === null || Math.abs(Number(nova) - atual) < EPS) {
      return comOpcoes(layout, { margin: Number(nova) });
    }
    var delta = Number(nova) - atual;
    var direitaAntiga = Number(pagina.width) - atual;
    var lista = elementos(layout).map(function (el) {
      if (el.type === "page_break") {
        return el;
      }
      var novo = State.clonar(el);
      novo.x = Number(el.x) + delta;
      novo.y = Number(el.y) + delta;
      if (Math.abs(Number(el.x) + Number(el.width) - direitaAntiga) < 0.6) {
        novo.width = Math.max(1, Number(el.width) - 2 * delta);
      }
      return novo;
    });
    return comOpcoes(novoLayout(layout, lista), { margin: Number(nova) });
  }

  // --- faixa da bandeira -------------------------------------------------------------

  /*
   * Os retangulos que formam a faixa tricolor no topo: retangulos sem
   * borda, encostados no topo, baixos, com as tres cores da faixa.
   * Reconhecida pelo desenho, e nao por um nome: e assim que os quatro
   * oficiais (e as copias deles) a trazem.
   */
  function faixa(layout, cores) {
    var validas = {};
    (cores || []).forEach(function (c) { validas[String(c).toLowerCase()] = true; });
    var ids = [];
    elementos(layout).forEach(function (el) {
      var p = props(el);
      if (
        el.type === "rectangle" && Number(el.y) <= 1 && Number(el.height) <= 10 &&
        !Number(p.border_width || 0) && validas[String(p.fill_color || "").toLowerCase()]
      ) {
        ids.push(el.id);
      }
    });
    return ids.length >= 2 ? ids : [];
  }

  function alternarFaixa(layout, ligar, medidas, ids) {
    var atual = faixa(layout, medidas.colors);
    if (!ligar) {
      var lista = elementos(layout).filter(function (el) { return atual.indexOf(el.id) === -1; });
      return novoLayout(layout, lista);
    }
    if (atual.length) {
      return layout;
    }
    var largura = Number(medidas.width) / medidas.colors.length;
    var novo = layout;
    // Da ultima cor para a primeira: cada retangulo vai para o FUNDO da
    // pilha (e decoracao da pagina), e assim a primeira cor acaba na
    // frente da lista, na ordem em que a faixa e lida.
    medidas.colors.slice().reverse().forEach(function (cor, posicao) {
      var indice = medidas.colors.length - 1 - posicao;
      if (!ids[indice]) {
        return;
      }
      novo = State.adicionar(novo, {
        id: ids[indice],
        type: "rectangle",
        x: Number(medidas.x) + indice * largura,
        y: 0,
        width: largura,
        height: Number(medidas.height),
        properties: {
          border_width: 0, border_style: "solid", border_color: "#000000",
          fill_color: cor, radius: 0
        }
      });
      novo = State.enviarParaTras(novo, ids[indice]);
    });
    return novo;
  }

  // --- paginas ----------------------------------------------------------------------

  function quebras(layout) {
    return elementos(layout)
      .filter(function (el) { return el.type === "page_break"; })
      .map(function (el) { return Number(el.y); })
      .sort(function (a, b) { return a - b; });
  }

  function totalDePaginas(layout) {
    return quebras(layout).length + 1;
  }

  /* Em que pagina (0, 1, 2...) o elemento cai -- a regra do renderer. */
  function paginaDe(layout, el) {
    var y = Number(el.y);
    var estrita = el.type === "page_break";
    return quebras(layout).filter(function (q) { return estrita ? q < y : q <= y; }).length;
  }

  /*
   * Insere uma quebra logo abaixo de `idRef`: o que vinha depois passa a
   * comecar no topo da pagina seguinte (na margem).
   */
  function inserirQuebra(layout, idRef, novoId, pagina, margemTopo) {
    var ref = State.obter(layout, idRef);
    if (!ref || !novoId) {
      return layout;
    }
    var yQuebra = pe(ref) + EPS;
    var k = paginaDe(layout, ref);
    var alturaDaPagina = Number(pagina.height);
    var primeiro = null;
    elementos(layout).forEach(function (el) {
      if (el.id !== idRef && Number(el.y) >= yQuebra - EPS) {
        primeiro = primeiro === null ? Number(el.y) : Math.min(primeiro, Number(el.y));
      }
    });
    var quebra = {
      id: novoId, type: "page_break",
      x: 0, y: yQuebra, width: Number(pagina.width), height: 0, properties: {}
    };
    var novo = layout;
    if (primeiro !== null) {
      var destino = (k + 1) * alturaDaPagina + Number(margemTopo || 0);
      novo = deslocar(layout, yQuebra - EPS, destino - primeiro, [idRef]);
    }
    return State.adicionar(novo, quebra);
  }

  /* Tira a quebra e traz o que vinha depois de volta para logo abaixo. */
  function removerQuebra(layout, id) {
    var quebra = State.obter(layout, id);
    if (!quebra) {
      return layout;
    }
    var primeiro = null;
    elementos(layout).forEach(function (el) {
      if (el.id !== id && Number(el.y) >= Number(quebra.y) - EPS) {
        primeiro = primeiro === null ? Number(el.y) : Math.min(primeiro, Number(el.y));
      }
    });
    var sem = State.remover(layout, id);
    if (primeiro === null) {
      return sem;
    }
    return deslocar(sem, Number(quebra.y) - EPS, Number(quebra.y) + ESPACO_ENTRE_BLOCOS - primeiro, []);
  }

  // --- campos usados -------------------------------------------------------------

  function referenciasDe(bloco, saida) {
    if (!bloco || typeof bloco !== "object") {
      return;
    }
    if (bloco.kind === "field" && bloco.source) {
      saida.push(bloco.source);
    } else if (bloco.kind === "mixed") {
      (bloco.parts || []).forEach(function (parte) { referenciasDe(parte, saida); });
    }
  }

  /*
   * Todas as ocorrencias de campo no documento, na ordem em que
   * aparecem: {total, porReferencia: {ref: n}, ordem: [ref...]}.
   */
  function usosDeCampos(layout) {
    var todas = [];
    elementos(layout).forEach(function (el) {
      var p = props(el);
      referenciasDe(p.content, todas);
      referenciasDe(p.source, todas);
      (p.rows || []).forEach(function (linha) {
        (linha.cells || []).forEach(function (celula) {
          referenciasDe(celula && celula.content, todas);
        });
      });
    });
    var por = {}, ordem = [];
    todas.forEach(function (ref) {
      if (!por[ref]) {
        por[ref] = 0;
        ordem.push(ref);
      }
      por[ref] += 1;
    });
    return { total: todas.length, porReferencia: por, ordem: ordem };
  }

  // --- linhas visuais (celular) --------------------------------------------------------

  /*
   * Agrupa os elementos em linhas de leitura: elementos que se
   * sobrepoem na vertical ficam na mesma linha (o "1." e o texto do
   * item; o logo e o QR). E como o celular mostra o documento como um
   * cartao corrido em vez de uma folha em escala.
   */
  function linhasVisuais(layout) {
    var linhas = [];
    ordenar(layout).forEach(function (el) {
      var ultima = linhas[linhas.length - 1];
      // Mesma linha quando a sobreposicao vertical e mais que metade do
      // menor dos dois: duas linhas de texto consecutivas medidas com
      // meio ponto de sobra nao sao "lado a lado".
      var alturaMinima = Math.max(1, Math.min(Number(el.height) || 0, ultima ? ultima.pe - ultima.y : 0));
      var sobreposicao = ultima ? ultima.pe - Number(el.y) : 0;
      if (
        ultima && el.type !== "page_break" && ultima.tipo !== "page_break" &&
        sobreposicao > alturaMinima / 2
      ) {
        ultima.elementos.push(el);
        ultima.pe = Math.max(ultima.pe, pe(el));
        return;
      }
      linhas.push({ y: Number(el.y), pe: pe(el), tipo: el.type, elementos: [el] });
    });
    linhas.forEach(function (linha) {
      linha.elementos.sort(function (a, b) { return Number(a.x) - Number(b.x); });
    });
    return linhas;
  }

  return {
    EPS: EPS,
    ESPACO_ENTRE_BLOCOS: ESPACO_ENTRE_BLOCOS,
    PASSO_DO_RECUO: PASSO_DO_RECUO,
    MARCADOR_DE_ITEM: MARCADOR_DE_ITEM,
    ESTILOS_DE_BLOCO: ESTILOS_DE_BLOCO,
    eTexto: eTexto,
    pe: pe,
    ordenar: ordenar,
    blocosDeTexto: blocosDeTexto,
    blocoAnterior: blocoAnterior,
    blocoSeguinte: blocoSeguinte,
    ultimoBloco: ultimoBloco,
    deslocar: deslocar,
    ajustarAltura: ajustarAltura,
    inserirDepois: inserirDepois,
    remover: remover,
    alturaDeUmaLinha: alturaDeUmaLinha,
    novoBlocoDeTexto: novoBlocoDeTexto,
    gravarConteudo: gravarConteudo,
    dividirBloco: dividirBloco,
    juntarComAnterior: juntarComAnterior,
    renumerar: renumerar,
    tipoDeLista: tipoDeLista,
    alternarLista: alternarLista,
    recuar: recuar,
    estiloDoBloco: estiloDoBloco,
    aplicarEstiloDoBloco: aplicarEstiloDoBloco,
    margem: margem,
    comOpcoes: comOpcoes,
    aplicarMargem: aplicarMargem,
    faixa: faixa,
    alternarFaixa: alternarFaixa,
    quebras: quebras,
    totalDePaginas: totalDePaginas,
    paginaDe: paginaDe,
    inserirQuebra: inserirQuebra,
    removerQuebra: removerQuebra,
    usosDeCampos: usosDeCampos,
    linhasVisuais: linhasVisuais
  };
});
