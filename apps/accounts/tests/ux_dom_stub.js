/*
 * DOM minimo para testar, fora do navegador, os dois comportamentos que
 * a revisao final de UX acrescentou a `static/js/app.js`:
 *
 *   - a mascara de telefone por pais ([data-telefone]);
 *   - o aviso vivo da confirmacao de senha ([data-pw-confirm]).
 *
 * Mesma ideia do stub do assistente (`letters/tests/wizard_dom_stub.js`):
 * `app.js` registra tudo por delegacao no `document` e le os elementos
 * por seletor. Este arquivo cobre EXATAMENTE as chamadas que esses dois
 * manipuladores fazem -- nao e um motor de seletor CSS, e nem tenta ser.
 *
 * O que ele prova: dado um evento "input" ou "change" no mesmo lugar em
 * que o navegador o dispararia, o manipulador formata o numero e escreve
 * o aviso -- sem depender de layout nem de CSS.
 */

function criarDocumento() {
  var ouvintes = {};
  var porId = {};
  var porSeletor = {};

  return {
    addEventListener: function (tipo, funcao) {
      (ouvintes[tipo] = ouvintes[tipo] || []).push(funcao);
    },
    disparar: function (tipo, alvo) {
      (ouvintes[tipo] || []).forEach(function (funcao) { funcao({ target: alvo }); });
    },
    registrar: function (elemento) {
      if (elemento.id) { porId[elemento.id] = elemento; }
      return elemento;
    },
    registrarSeletor: function (seletor, elemento) {
      porSeletor[seletor] = elemento;
      return elemento;
    },
    getElementById: function (id) {
      return Object.prototype.hasOwnProperty.call(porId, id) ? porId[id] : null;
    },
    querySelector: function (seletor) {
      return Object.prototype.hasOwnProperty.call(porSeletor, seletor)
        ? porSeletor[seletor]
        : null;
    },
    // Chamado no carregamento do modulo ([data-gate]) e no
    // DOMContentLoaded ([data-telefone]) -- os cenarios disparam o
    // evento a mao quando querem esse caminho.
    querySelectorAll: function () { return []; }
  };
}

function atributos(mapa) {
  return {
    getAttribute: function (nome) {
      return Object.prototype.hasOwnProperty.call(mapa, nome) ? mapa[nome] : null;
    },
    setAttribute: function (nome, valor) { mapa[nome] = valor; },
    removeAttribute: function (nome) { delete mapa[nome]; },
    hasAttribute: function (nome) {
      return Object.prototype.hasOwnProperty.call(mapa, nome);
    }
  };
}

/* Um campo de telefone: a moldura [data-telefone] com o <select> de
 * paises e o <input> do numero dentro. */
function criarCampoDeTelefone(paises, escolhido, valorInicial) {
  var opcoes = paises.map(function (pais) {
    var base = atributos({
      "data-mascara": pais.mascara || "",
      "data-exemplo": pais.exemplo || ""
    });
    base.value = pais.ddi;
    return base;
  });

  var seletorPais = {
    tagName: "SELECT",
    options: opcoes,
    selectedIndex: Math.max(0, paises.map(function (p) { return p.ddi; }).indexOf(escolhido))
  };

  var numero = atributos({});
  numero.tagName = "INPUT";
  numero.value = valorInicial || "";

  var campo = {
    querySelector: function (seletor) {
      if (seletor === "select") { return seletorPais; }
      if (seletor === "input") { return numero; }
      return null;
    }
  };

  seletorPais.closest = function (seletor) {
    return seletor === "[data-telefone]" ? campo : null;
  };
  numero.closest = function (seletor) {
    return seletor === "[data-telefone]" ? campo : null;
  };

  campo.seletorPais = seletorPais;
  campo.numero = numero;
  campo.escolher = function (ddi) {
    seletorPais.selectedIndex = paises.map(function (p) { return p.ddi; }).indexOf(ddi);
  };
  return campo;
}

/* O par senha + confirmacao, com o aviso ao lado. */
function criarParDeSenhas(documento, idDaSenha) {
  var senha = atributos({});
  senha.id = idDaSenha;
  senha.value = "";
  senha.closest = function () { return null; };

  var confirmacao = atributos({ "data-pw-confirm": idDaSenha });
  confirmacao.id = idDaSenha + "_2";
  confirmacao.value = "";
  confirmacao.closest = function (seletor) {
    return seletor === "[data-pw-confirm]" ? confirmacao : null;
  };

  var aviso = atributos({
    "data-igual": "As senhas conferem.",
    "data-diferente": "As senhas nao coincidem."
  });
  aviso.textContent = "";
  aviso.className = "field-hint";

  documento.registrar(senha);
  documento.registrarSeletor("[data-pw-confirm-aviso='" + idDaSenha + "']", aviso);
  documento.registrarSeletor("[data-pw-confirm='" + idDaSenha + "']", confirmacao);

  return { senha: senha, confirmacao: confirmacao, aviso: aviso };
}

module.exports = {
  criarDocumento: criarDocumento,
  criarCampoDeTelefone: criarCampoDeTelefone,
  criarParDeSenhas: criarParDeSenhas
};
