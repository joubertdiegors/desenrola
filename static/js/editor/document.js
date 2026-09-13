/*
 * O documento visual no navegador: criar, alterar, mover e serializar
 * elementos.
 *
 * Tudo aqui e funcao PURA sobre dados simples -- nenhuma referencia a
 * DOM, evento ou fetch. E o que permite testar a logica de verdade no
 * Node (apps/doctemplates/tests/test_editor_js.py) em vez de conferir
 * strings no HTML.
 *
 * As operacoes NUNCA alteram o documento recebido: devolvem um novo. E o
 * que faz o undo/redo (history.js) funcionar guardando referencias, sem
 * clonar a cada tecla.
 *
 * O contrato do JSON esta em apps/doctemplates/visual_schema.py. Os
 * padroes de cada tipo abaixo tem de continuar batendo com o que aquele
 * validador aceita -- um padrao invalido aqui viraria um salvamento
 * recusado pelo servidor.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.EditorDocument = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var SCHEMA_VERSION = 1;
  var A4_WIDTH_PT = 595.2756;
  var A4_HEIGHT_PT = 841.8898;

  var TIPOS = ["text", "field", "image", "line", "rect", "qrcode", "table", "rich_text"];

  // Aparencia de texto, compartilhada por `text` e `field` -- os dois
  // desenham texto, so muda de onde vem o conteudo.
  function estiloDeTextoPadrao() {
    return {
      font_family: "LiberationSans",
      font_size: 11,
      font_weight: "regular",
      italic: false,
      align: "left",
      vertical_align: "top",
      color: "#000000",
      line_height: 1.25,
      letter_spacing: 0,
      wrap: true,
      overflow: "shrink"
    };
  }

  function propriedadesPadrao(tipo) {
    switch (tipo) {
      case "text":
        return Object.assign(estiloDeTextoPadrao(), { content: "Texto" });
      case "field":
        // `field` guarda so a REFERENCIA. O valor vem da carta na hora de
        // gerar o PDF -- guardar aqui congelaria o dado de uma pessoa
        // dentro do modelo.
        return Object.assign(estiloDeTextoPadrao(), { field: "" });
      case "rich_text":
        // Paragrafo de trechos: texto fixo e campos na mesma linha
        // corrida. `leading` em PONTOS (o documento oficial usa 13,5),
        // nao multiplicador -- ver visual_schema.py.
        return Object.assign(estiloDeTextoPadrao(), {
          runs: [{ text: "Texto ", bold: false }],
          leading: 13.5,
          min_font_size: 9,
          max_lines: 1
        });
      case "image":
        return { asset_id: 0, preserve_aspect_ratio: true };
      case "line":
        return { thickness: 1, color: "#000000" };
      case "rect":
        return {
          border_width: 1,
          border_color: "#000000",
          fill_color: null,
          radius: 0
        };
      case "qrcode":
        return { content: "", error_correction: "M" };
      case "table":
        return {
          columns: [
            { width: 120, align: "left" },
            { width: 200, align: "left" }
          ],
          rows: [
            {
              min_height: 18,
              cells: [
                { content: "Rótulo", align: "left", bold: true },
                { content: "Valor", align: "left", bold: false }
              ]
            }
          ],
          padding: 4,
          border_width: 0.5,
          border_color: "#000000"
        };
      default:
        return {};
    }
  }

  // Tamanho inicial de cada tipo, em pontos. Escolhidos para o elemento
  // nascer visivel e utilizavel, nao para caber num layout especifico.
  function tamanhoPadrao(tipo) {
    switch (tipo) {
      case "text":
      case "field":
        return { width: 220, height: 16 };
      case "rich_text":
        return { width: 400, height: 40.5 };
      case "image":
        return { width: 120, height: 120 };
      case "line":
        return { width: 200, height: 0 };
      case "rect":
        return { width: 160, height: 80 };
      case "qrcode":
        return { width: 80, height: 80 };
      case "table":
        return { width: 320, height: 60 };
      default:
        return { width: 100, height: 40 };
    }
  }

  /*
   * Id estavel de elemento.
   *
   * `crypto.randomUUID` quando existe; senao um id com a mesma forma,
   * montado a partir de valores aleatorios. O id so precisa ser unico
   * dentro de um documento -- nao e segredo nem chave de banco.
   */
  function novoId() {
    if (typeof crypto !== "undefined" && crypto && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    var saida = "";
    for (var i = 0; i < 32; i += 1) {
      saida += Math.floor(Math.random() * 16).toString(16);
      if (i === 7 || i === 11 || i === 15 || i === 19) {
        saida += "-";
      }
    }
    return saida;
  }

  function documentoVazio() {
    return {
      schema_version: SCHEMA_VERSION,
      page: {
        width: A4_WIDTH_PT,
        height: A4_HEIGHT_PT,
        unit: "pt",
        origin: "top-left"
      },
      elements: []
    };
  }

  function maiorZ(documento) {
    return documento.elements.reduce(function (maior, elemento) {
      return Math.max(maior, elemento.z_index || 0);
    }, 0);
  }

  function criarElemento(tipo, posicao) {
    if (TIPOS.indexOf(tipo) === -1) {
      throw new Error("tipo de elemento desconhecido: " + tipo);
    }
    var tamanho = tamanhoPadrao(tipo);
    return {
      id: novoId(),
      type: tipo,
      x: posicao && posicao.x !== undefined ? Number(posicao.x) : 72,
      y: posicao && posicao.y !== undefined ? Number(posicao.y) : 72,
      width: tamanho.width,
      height: tamanho.height,
      z_index: 0,
      properties: propriedadesPadrao(tipo)
    };
  }

  function adicionar(documento, elemento) {
    var novo = Object.assign({}, elemento, { z_index: maiorZ(documento) + 1 });
    return Object.assign({}, documento, {
      elements: documento.elements.concat([novo])
    });
  }

  function encontrar(documento, id) {
    for (var i = 0; i < documento.elements.length; i += 1) {
      if (documento.elements[i].id === id) {
        return documento.elements[i];
      }
    }
    return null;
  }

  /*
   * Altera a geometria e/ou o z_index de um elemento.
   *
   * Nao arredonda: o documento oficial frances foi medido com casas
   * decimais e arredondar aqui deslocaria o texto visivelmente.
   */
  function atualizarGeometria(documento, id, mudancas) {
    return Object.assign({}, documento, {
      elements: documento.elements.map(function (elemento) {
        if (elemento.id !== id) {
          return elemento;
        }
        var atualizado = Object.assign({}, elemento);
        ["x", "y", "width", "height", "z_index"].forEach(function (chave) {
          if (mudancas[chave] !== undefined) {
            atualizado[chave] = Number(mudancas[chave]);
          }
        });
        // Largura e altura negativas nao existem; o servidor recusaria.
        atualizado.width = Math.max(0, atualizado.width);
        atualizado.height = Math.max(0, atualizado.height);
        atualizado.z_index = Math.round(atualizado.z_index);
        return atualizado;
      })
    });
  }

  function atualizarPropriedades(documento, id, mudancas) {
    return Object.assign({}, documento, {
      elements: documento.elements.map(function (elemento) {
        if (elemento.id !== id) {
          return elemento;
        }
        return Object.assign({}, elemento, {
          properties: Object.assign({}, elemento.properties, mudancas)
        });
      })
    });
  }

  function remover(documento, id) {
    return Object.assign({}, documento, {
      elements: documento.elements.filter(function (elemento) {
        return elemento.id !== id;
      })
    });
  }

  /*
   * Duplica um elemento com id novo, deslocado alguns pontos para a
   * copia nao ficar escondida exatamente por cima do original.
   */
  function duplicar(documento, id) {
    var original = encontrar(documento, id);
    if (!original) {
      return { documento: documento, id: null };
    }
    var copia = JSON.parse(JSON.stringify(original));
    copia.id = novoId();
    copia.x = original.x + 10;
    copia.y = original.y + 10;
    copia.z_index = maiorZ(documento) + 1;
    return {
      documento: Object.assign({}, documento, {
        elements: documento.elements.concat([copia])
      }),
      id: copia.id
    };
  }

  function trazerParaFrente(documento, id) {
    return atualizarGeometria(documento, id, { z_index: maiorZ(documento) + 1 });
  }

  function enviarParaTras(documento, id) {
    var menor = documento.elements.reduce(function (menorZ, elemento) {
      return Math.min(menorZ, elemento.z_index || 0);
    }, 0);
    return atualizarGeometria(documento, id, { z_index: menor - 1 });
  }

  /* Ordem de desenho: menor z primeiro. Empate resolve pela posicao na
   * lista, para a ordem ser estavel entre renderizacoes. */
  function ordenadosParaDesenho(documento) {
    return documento.elements
      .map(function (elemento, indice) {
        return { elemento: elemento, indice: indice };
      })
      .sort(function (a, b) {
        var za = a.elemento.z_index || 0;
        var zb = b.elemento.z_index || 0;
        return za === zb ? a.indice - b.indice : za - zb;
      })
      .map(function (item) {
        return item.elemento;
      });
  }

  /*
   * Serializacao. O que sai daqui e exatamente o que o servidor valida e
   * grava -- nada de estado de interface (selecao, zoom, grade) no JSON.
   */
  function serializar(documento) {
    return JSON.stringify({
      schema_version: documento.schema_version,
      page: documento.page,
      elements: ordenadosParaDesenho(documento)
    });
  }

  function desserializar(texto) {
    var dados = typeof texto === "string" ? JSON.parse(texto) : texto;
    if (!dados || !dados.elements) {
      return documentoVazio();
    }
    return {
      schema_version: dados.schema_version || SCHEMA_VERSION,
      page: dados.page || documentoVazio().page,
      elements: dados.elements.slice()
    };
  }

  return {
    SCHEMA_VERSION: SCHEMA_VERSION,
    TIPOS: TIPOS,
    novoId: novoId,
    documentoVazio: documentoVazio,
    propriedadesPadrao: propriedadesPadrao,
    tamanhoPadrao: tamanhoPadrao,
    criarElemento: criarElemento,
    adicionar: adicionar,
    encontrar: encontrar,
    atualizarGeometria: atualizarGeometria,
    atualizarPropriedades: atualizarPropriedades,
    remover: remover,
    duplicar: duplicar,
    trazerParaFrente: trazerParaFrente,
    enviarParaTras: enviarParaTras,
    ordenadosParaDesenho: ordenadosParaDesenho,
    maiorZ: maiorZ,
    serializar: serializar,
    desserializar: desserializar
  };
});
