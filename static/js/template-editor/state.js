/*
 * Estado do editor: o layout, o historico e as operacoes sobre elementos.
 *
 * Editor visual dos modelos da biblioteca (Etapa 3.2). Funcoes puras
 * sobre dados -- nenhum DOM, nenhum fetch. E o que permite testar a
 * logica de verdade no Node em vez de conferir strings no HTML.
 *
 * As operacoes espelham `apps/doctemplates/services/layout.py`. A
 * duplicacao cliente/servidor e inevitavel (um edita, o outro valida e
 * grava), e a forma de mante-las honestas e o servidor ser sempre a
 * autoridade: ele revalida o layout inteiro a cada salvamento, pelo
 * contrato da Etapa 3.1.
 *
 * IDS NAO SAO GERADOS AQUI
 * ------------------------
 * Vem prontos do servidor, num lote entregue ao abrir a pagina
 * (`editor_views.py`). Este modulo apenas CONSOME desse lote. Inventar
 * ids no navegador criaria uma segunda estrategia de identificacao
 * podendo divergir da do servidor.
 *
 * IMUTABILIDADE
 * -------------
 * Toda operacao devolve um layout NOVO e nunca altera o recebido. E o
 * que faz o desfazer funcionar guardando referencias, sem clonar a cada
 * tecla, e o que evita a classe de bug mais cara aqui: alterar um
 * elemento e descobrir depois que o objeto era compartilhado.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.TEState = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Passos guardados no historico. O suficiente para desfazer um engano
  // real sem segurar o documento dezenas de vezes na memoria.
  var LIMITE_DO_HISTORICO = 50;

  function clonar(valor) {
    return JSON.parse(JSON.stringify(valor));
  }

  function layoutVazio(versao) {
    return { version: versao || 1, elements: [] };
  }

  function normalizar(layout, versao) {
    if (!layout || !layout.elements) {
      return layoutVazio(versao);
    }
    return { version: layout.version || versao || 1, elements: layout.elements.slice() };
  }

  // --- fila de ids vinda do servidor ---------------------------------------

  function criarFilaDeIds(ids) {
    return { disponiveis: (ids || []).slice(), usados: {} };
  }

  /*
   * Proximo id ainda nao usado neste layout. Se a fila esgotar, devolve
   * null -- quem chama pede outro lote ao servidor.
   */
  function proximoId(fila, layout) {
    var emUso = {};
    (layout.elements || []).forEach(function (el) {
      emUso[el.id] = true;
    });
    while (fila.disponiveis.length) {
      var candidato = fila.disponiveis.shift();
      if (!emUso[candidato] && !fila.usados[candidato]) {
        fila.usados[candidato] = true;
        return candidato;
      }
    }
    return null;
  }

  function reabastecer(fila, ids) {
    fila.disponiveis = fila.disponiveis.concat(ids || []);
    return fila;
  }

  // --- leitura -------------------------------------------------------------

  function indiceDe(layout, id) {
    for (var i = 0; i < (layout.elements || []).length; i += 1) {
      if (layout.elements[i].id === id) {
        return i;
      }
    }
    return -1;
  }

  function obter(layout, id) {
    var i = indiceDe(layout, id);
    return i === -1 ? null : layout.elements[i];
  }

  // --- construcao de elementos --------------------------------------------

  /*
   * Monta um elemento do `tipo`, com os padroes que o REGISTRO do
   * servidor declarou (`elements.py`, entregue a pagina). Nada de uma
   * segunda tabela de padroes aqui.
   */
  function criarElemento(catalogo, tipo, id, posicao) {
    var declarado = null;
    for (var i = 0; i < catalogo.length; i += 1) {
      if (catalogo[i].code === tipo) {
        declarado = catalogo[i];
        break;
      }
    }
    if (!declarado) {
      throw new Error("tipo de elemento desconhecido: " + tipo);
    }
    var propriedades = {};
    declarado.properties.forEach(function (p) {
      propriedades[p.name] = p.default === null ? null : clonar(p.default);
    });
    var tamanho = tamanhoInicial(tipo);
    return {
      id: id,
      type: tipo,
      x: (posicao && posicao.x) || 72,
      y: (posicao && posicao.y) || 72,
      width: tamanho.width,
      height: tamanho.height,
      properties: propriedades
    };
  }

  /* Tamanho de partida, so para o elemento nascer visivel e clicavel. */
  function tamanhoInicial(tipo) {
    switch (tipo) {
      case "text":
      case "number":
        return { width: 200, height: 16 };
      case "rich_text":
        return { width: 400, height: 40 };
      case "image":
        return { width: 120, height: 120 };
      case "qr_code":
        return { width: 80, height: 80 };
      case "line":
        return { width: 200, height: 0 };
      case "rectangle":
        return { width: 160, height: 80 };
      case "table":
        return { width: 320, height: 60 };
      default:
        return { width: 120, height: 40 };
    }
  }

  /*
   * Um elemento de TEXTO que imprime um campo -- e assim que um dado
   * dinamico entra no documento: conteudo ESTRUTURAL, nunca "{{campo}}"
   * dentro de uma string.
   */
  function criarElementoDeCampo(catalogo, referencia, id, posicao) {
    var elemento = criarElemento(catalogo, "text", id, posicao);
    elemento.properties.content = { kind: "field", source: referencia };
    return elemento;
  }

  // --- escrita -------------------------------------------------------------

  function adicionar(layout, elemento, versao) {
    var novo = normalizar(layout, versao);
    novo.elements = novo.elements.concat([clonar(elemento)]);
    return novo;
  }

  function remover(layout, id, versao) {
    var novo = normalizar(layout, versao);
    novo.elements = novo.elements.filter(function (el) {
      return el.id !== id;
    });
    return novo;
  }

  /*
   * Altera um elemento. `properties` e MESCLADO chave a chave; o resto e
   * substituido. Mesclar e o comportamento util: mudar a cor de um texto
   * nao pode apagar o tamanho da fonte.
   */
  function atualizar(layout, id, mudancas, versao) {
    var novo = normalizar(layout, versao);
    novo.elements = novo.elements.map(function (el) {
      if (el.id !== id) {
        return el;
      }
      var atualizado = clonar(el);
      Object.keys(mudancas).forEach(function (chave) {
        if (chave === "properties") {
          atualizado.properties = atualizado.properties || {};
          Object.keys(mudancas.properties).forEach(function (nome) {
            atualizado.properties[nome] = clonar(mudancas.properties[nome]);
          });
        } else if (chave !== "id") {
          atualizado[chave] = mudancas[chave];
        }
      });
      return atualizado;
    });
    return novo;
  }

  function mover(layout, id, x, y, versao) {
    return atualizar(layout, id, { x: Number(x), y: Number(y) }, versao);
  }

  function redimensionar(layout, id, width, height, versao) {
    return atualizar(
      layout,
      id,
      { width: Math.max(0, Number(width)), height: Math.max(0, Number(height)) },
      versao
    );
  }

  function duplicar(layout, id, novoIdentificador, versao) {
    var original = obter(layout, id);
    if (!original || !novoIdentificador) {
      return { layout: layout, id: null };
    }
    var copia = clonar(original);
    copia.id = novoIdentificador;
    copia.x = Number(copia.x) + 10;
    copia.y = Number(copia.y) + 10;
    return { layout: adicionar(layout, copia, versao), id: novoIdentificador };
  }

  // --- camadas -------------------------------------------------------------
  //
  // A ORDEM da lista e a ordem de desenho: indice 0 ao fundo, ultimo por
  // cima. Nao ha z_index para manter em sincronia.

  function reordenar(layout, id, destino, versao) {
    var novo = normalizar(layout, versao);
    var i = indiceDe(novo, id);
    if (i === -1) {
      return novo;
    }
    var elementos = novo.elements.slice();
    var elemento = elementos.splice(i, 1)[0];
    var posicao = Math.max(0, Math.min(elementos.length, destino(i, elementos.length)));
    elementos.splice(posicao, 0, elemento);
    novo.elements = elementos;
    return novo;
  }

  function trazerParaFrente(layout, id, versao) {
    return reordenar(layout, id, function (i, total) { return total; }, versao);
  }

  function enviarParaTras(layout, id, versao) {
    return reordenar(layout, id, function () { return 0; }, versao);
  }

  function moverParaFrente(layout, id, versao) {
    return reordenar(layout, id, function (i) { return i + 1; }, versao);
  }

  function moverParaTras(layout, id, versao) {
    return reordenar(layout, id, function (i) { return i - 1; }, versao);
  }

  // --- historico -----------------------------------------------------------
  //
  // Guarda ESTADOS inteiros, nao operacoes inversas. Um layout e pequeno
  // e as operacoes acima nunca alteram o objeto recebido, entao guardar
  // um estado custa uma referencia -- e desfazer e sempre exato, sem
  // precisar escrever e testar o inverso de cada operacao.

  function criarHistorico(estadoInicial, limite) {
    return {
      estados: [estadoInicial],
      indice: 0,
      limite: limite || LIMITE_DO_HISTORICO
    };
  }

  function atual(historico) {
    return historico.estados[historico.indice];
  }

  function registrar(historico, estado) {
    // Tudo o que estava "a frente" e descartado: depois de desfazer e
    // fazer outra coisa, o ramo antigo deixa de existir.
    var estados = historico.estados.slice(0, historico.indice + 1);
    estados.push(estado);
    if (estados.length > historico.limite) {
      estados = estados.slice(estados.length - historico.limite);
    }
    return { estados: estados, indice: estados.length - 1, limite: historico.limite };
  }

  function podeDesfazer(historico) {
    return historico.indice > 0;
  }

  function podeRefazer(historico) {
    return historico.indice < historico.estados.length - 1;
  }

  function desfazer(historico) {
    if (!podeDesfazer(historico)) {
      return historico;
    }
    return { estados: historico.estados, indice: historico.indice - 1, limite: historico.limite };
  }

  function refazer(historico) {
    if (!podeRefazer(historico)) {
      return historico;
    }
    return { estados: historico.estados, indice: historico.indice + 1, limite: historico.limite };
  }

  return {
    LIMITE_DO_HISTORICO: LIMITE_DO_HISTORICO,
    clonar: clonar,
    layoutVazio: layoutVazio,
    normalizar: normalizar,
    criarFilaDeIds: criarFilaDeIds,
    proximoId: proximoId,
    reabastecer: reabastecer,
    indiceDe: indiceDe,
    obter: obter,
    criarElemento: criarElemento,
    criarElementoDeCampo: criarElementoDeCampo,
    tamanhoInicial: tamanhoInicial,
    adicionar: adicionar,
    remover: remover,
    atualizar: atualizar,
    mover: mover,
    redimensionar: redimensionar,
    duplicar: duplicar,
    trazerParaFrente: trazerParaFrente,
    enviarParaTras: enviarParaTras,
    moverParaFrente: moverParaFrente,
    moverParaTras: moverParaTras,
    criarHistorico: criarHistorico,
    atual: atual,
    registrar: registrar,
    podeDesfazer: podeDesfazer,
    podeRefazer: podeRefazer,
    desfazer: desfazer,
    refazer: refazer
  };
});
