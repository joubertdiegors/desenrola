/*
 * Desfazer/refazer do editor.
 *
 * Guarda ESTADOS inteiros do documento, nao operacoes inversas. Um
 * documento e um objeto pequeno (uma pagina, poucas centenas de
 * elementos no maximo) e as operacoes de document.js nunca alteram o
 * objeto recebido -- devolvem um novo. Entao "guardar o estado" custa
 * uma referencia, nao uma copia, e desfazer e so voltar um indice.
 *
 * A alternativa (comando + inverso) exigiria escrever e testar o inverso
 * de cada operacao, com a chance de um deles estar sutilmente errado. Com
 * estados, desfazer e sempre exato.
 *
 * O historico e da SESSAO do editor: vive na aba, morre ao recarregar.
 * Nao e auditoria -- versao publicada e que e o registro permanente.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.EditorHistory = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Passos guardados. O suficiente para desfazer um engano real sem
  // segurar o documento inteiro dezenas de vezes na memoria.
  var LIMITE_PADRAO = 50;

  function criar(estadoInicial, limite) {
    return {
      estados: [estadoInicial],
      indice: 0,
      limite: limite === undefined ? LIMITE_PADRAO : limite
    };
  }

  function atual(historico) {
    return historico.estados[historico.indice];
  }

  /*
   * Registra um estado novo.
   *
   * Tudo o que estava "a frente" e descartado: depois de desfazer e
   * fazer outra coisa, o ramo antigo deixa de existir -- e o
   * comportamento que todo editor tem e que o usuario espera.
   */
  function registrar(historico, estado) {
    var estados = historico.estados.slice(0, historico.indice + 1);
    estados.push(estado);

    // Passou do limite: descarta o comeco, que e o mais antigo.
    if (estados.length > historico.limite) {
      estados = estados.slice(estados.length - historico.limite);
    }

    return {
      estados: estados,
      indice: estados.length - 1,
      limite: historico.limite
    };
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
    return {
      estados: historico.estados,
      indice: historico.indice - 1,
      limite: historico.limite
    };
  }

  function refazer(historico) {
    if (!podeRefazer(historico)) {
      return historico;
    }
    return {
      estados: historico.estados,
      indice: historico.indice + 1,
      limite: historico.limite
    };
  }

  return {
    LIMITE_PADRAO: LIMITE_PADRAO,
    criar: criar,
    atual: atual,
    registrar: registrar,
    podeDesfazer: podeDesfazer,
    podeRefazer: podeRefazer,
    desfazer: desfazer,
    refazer: refazer
  };
});
