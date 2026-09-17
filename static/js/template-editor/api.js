/*
 * Conversa com o servidor: salvar o layout e pedir mais ids.
 *
 * Editor visual dos modelos da biblioteca (Etapa 3.2). Uma camada fina
 * de proposito -- toda a decisao (se pode gravar, se o layout e valido)
 * e do servidor; aqui so se transporta e se traduz a resposta.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.TEApi = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function csrf(doc) {
    var campo = doc.querySelector("[name=csrfmiddlewaretoken]");
    return campo ? campo.value : "";
  }

  function enviar(doc, url, corpo) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf(doc) },
      body: JSON.stringify(corpo || {})
    }).then(function (resposta) {
      return resposta
        .json()
        .catch(function () {
          // Uma resposta que nao e JSON (500 em HTML, proxy no caminho)
          // nao pode virar "sucesso" por omissao.
          return { ok: false, error: "Resposta inesperada do servidor." };
        })
        .then(function (dados) {
          return { ok: resposta.ok && dados.ok === true, status: resposta.status, dados: dados };
        });
    });
  }

  /*
   * Grava o layout (e o que mais o editor mandar em `extras`, hoje o
   * idioma). Devolve sempre `{ok, status, dados}` -- inclusive em falha
   * de rede, para quem chama nunca precisar de try/catch.
   */
  function salvar(doc, url, layout, extras) {
    var corpo = { layout: layout };
    Object.keys(extras || {}).forEach(function (chave) {
      corpo[chave] = extras[chave];
    });
    return enviar(doc, url, corpo).catch(function () {
      return { ok: false, status: 0, dados: { error: "Falha de rede ao salvar." } };
    });
  }

  function pedirIds(doc, url) {
    return enviar(doc, url, {})
      .then(function (resultado) {
        return resultado.ok ? resultado.dados.ids || [] : [];
      })
      .catch(function () {
        return [];
      });
  }

  /* A mensagem que o servidor mandou, ou uma explicacao honesta. */
  function mensagemDeErro(resultado) {
    if (resultado && resultado.dados && resultado.dados.error) {
      return resultado.dados.error;
    }
    if (resultado && resultado.status) {
      return "Não foi possível salvar (HTTP " + resultado.status + ").";
    }
    return "Não foi possível salvar.";
  }

  return {
    csrf: csrf,
    salvar: salvar,
    pedirIds: pedirIds,
    mensagemDeErro: mensagemDeErro
  };
});
