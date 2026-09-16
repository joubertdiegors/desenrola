/*
 * DOM minimo para testar a reatividade do botao "Proxima etapa" de
 * `static/js/app.js` fora do navegador.
 *
 * `app.js` registra os manipuladores por delegacao (`document.addEventListener`)
 * e le o formulario por seletor (`form.querySelectorAll("[required]")`,
 * `form.querySelector("[data-step-submit]")`). Este stub cobre exatamente
 * essas chamadas -- nada de motor de seletor CSS de verdade, so o que
 * `refreshStepButton`/`fieldIsFilled`/`refreshDuration` realmente usam.
 *
 * NAO e um navegador: nao ha layout nem CSS. O que ele prova e que os
 * MESMOS manipuladores que o `document` real dispara em "input"/"change"
 * reavaliam o botao sozinhos, sem precisar de um segundo evento.
 */
function criarBarramentoDeEventos() {
  var ouvintes = {};
  return {
    addEventListener: function (tipo, funcao) {
      (ouvintes[tipo] = ouvintes[tipo] || []).push(funcao);
    },
    disparar: function (tipo, alvo) {
      (ouvintes[tipo] || []).forEach(function (funcao) { funcao({ target: alvo }); });
    },
    // Chamado no carregamento do modulo (querySelectorAll("[data-gate]")
    // etc.) e por `refreshStepButton` (botao associado por atributo
    // `form=""`) -- nenhum dos dois existe neste stub: o botao sempre
    // vive DENTRO do <form>, achado por `form.querySelector` mesmo.
    querySelectorAll: function () { return []; },
    querySelector: function () { return null; }
  };
}

function criarCampoDeData(id, valorInicial, opcoes) {
  opcoes = opcoes || {};
  var valor = valorInicial || "";
  var atributos = {};
  if (opcoes.min) { atributos["data-date-min"] = opcoes.min; }

  var campo = {
    id: id,
    type: "text",
    required: opcoes.required !== false,
    disabled: false,
    get value() { return valor; },
    set value(novo) { valor = novo; },
    // Todo Element de verdade tem `closest`. Sem ele aqui, qualquer
    // manipulador de `app.js` que procure um ancestral explodia ao
    // receber este campo -- e nenhum deles procura um ancestral que
    // exista neste cenario, entao a resposta certa e "nao achei".
    closest: function () { return null; },
    classList: {
      add: function () {},
      remove: function () {},
      toggle: function () {},
      contains: function () { return false; }
    },
    hasAttribute: function (nome) {
      return nome === "data-date-input" || Object.prototype.hasOwnProperty.call(atributos, nome);
    },
    getAttribute: function (nome) {
      return Object.prototype.hasOwnProperty.call(atributos, nome) ? atributos[nome] : null;
    }
  };
  return campo;
}

function criarBotaoDeEtapa() {
  var classes = [];
  var atributos = {};
  return {
    classList: {
      toggle: function (nome, forcar) {
        var tem = classes.indexOf(nome) !== -1;
        var deve = forcar === undefined ? !tem : !!forcar;
        if (deve && !tem) { classes.push(nome); }
        if (!deve && tem) { classes.splice(classes.indexOf(nome), 1); }
      },
      contains: function (nome) { return classes.indexOf(nome) !== -1; }
    },
    setAttribute: function (nome, valor) { atributos[nome] = String(valor); },
    getAttribute: function (nome) { return atributos[nome]; }
  };
}

function criarFormularioDeEtapa(id, campos, botao) {
  return {
    id: id,
    querySelectorAll: function (seletor) {
      if (seletor === "[required]") {
        return campos.filter(function (campo) { return campo.required; });
      }
      return [];
    },
    // "[data-duration-box]" (refreshDuration) nao existe neste stub: a
    // funcao sai cedo, exatamente como numa etapa sem essa caixa.
    querySelector: function (seletor) {
      return seletor === "[data-step-submit]" ? botao : null;
    }
  };
}

module.exports = {
  criarBarramentoDeEventos: criarBarramentoDeEventos,
  criarCampoDeData: criarCampoDeData,
  criarBotaoDeEtapa: criarBotaoDeEtapa,
  criarFormularioDeEtapa: criarFormularioDeEtapa
};
