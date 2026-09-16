/*
 * DOM minimo para testar o canvas do editor estrutural
 * (`static/js/template-editor/canvas.js`) fora do navegador.
 *
 * Implementa exatamente o que o renderizador usa -- `createElement`,
 * `appendChild`, `style`, `classList`, `dataset`, `textContent`,
 * `setAttribute` -- e nada mais. NAO e um navegador e nao tenta ser: nao
 * ha layout e nao ha CSS aplicado.
 *
 * Ha eventos, desde o Bloco F: uma lista de ouvintes por nome e um
 * `disparar` para o teste aciona-los. Sem isso o painel de propriedades
 * (`properties.js`), que e todo feito de `addEventListener`, ficava
 * intestavel fora do navegador.
 *
 * Para que serve, entao: provar que cada elemento do documento produz um
 * no, com a posicao, o tamanho, a camada e o conteudo certos -- coisa que
 * um teste procurando strings no HTML do servidor nunca mostraria.
 *
 * O que ele nao cobre continua dependendo de olhar no navegador:
 * empilhamento real, tamanho em tela, e se da para clicar.
 */
function criarNo(tag) {
  return {
    tagName: tag,
    style: {},
    children: [],
    dataset: {},
    attrs: {},
    className: "",
    _texto: "",

    classList: {
      _classes: [],
      add: function (nome) {
        if (this._classes.indexOf(nome) === -1) {
          this._classes.push(nome);
        }
      },
      contains: function (nome) {
        return this._classes.indexOf(nome) !== -1;
      }
    },

    set textContent(valor) {
      this._texto = valor;
      this.children = [];
    },
    get textContent() {
      return (
        this._texto +
        this.children
          .map(function (filho) {
            return filho.textContent;
          })
          .join("")
      );
    },

    appendChild: function (no) {
      this.children.push(no);
      return no;
    },
    removeChild: function (no) {
      this.children = this.children.filter(function (filho) {
        return filho !== no;
      });
      return no;
    },
    setAttribute: function (chave, valor) {
      this.attrs[chave] = valor;
    },
    get firstChild() {
      return this.children[0] || null;
    },

    /*
     * EVENTOS -- o minimo para exercitar o painel de propriedades.
     *
     * Nao ha propagacao, nao ha `preventDefault`, nao ha ordem de
     * captura: ha uma lista de ouvintes por nome de evento e um jeito de
     * chama-los. E o bastante para o teste dizer "mexi neste controle" e
     * conferir o que o codigo fez com isso.
     */
    _ouvintes: {},
    addEventListener: function (evento, fn) {
      if (!this._ouvintes[evento]) {
        this._ouvintes[evento] = [];
      }
      this._ouvintes[evento].push(fn);
    },
    disparar: function (evento) {
      var no = this;
      (this._ouvintes[evento] || []).forEach(function (fn) {
        fn({ target: no });
      });
      return this;
    }
  };
}

/*
 * Busca na arvore -- o stub nao tem seletores, e reimplementar a
 * descida em cada teste seria ruido.
 */
function procurar(raiz, condicao) {
  var achados = [];
  (function descer(no) {
    if (!no || !no.children) {
      return;
    }
    no.children.forEach(function (filho) {
      if (condicao(filho)) {
        achados.push(filho);
      }
      descer(filho);
    });
  })(raiz);
  return achados;
}

function porClasse(raiz, classe) {
  return procurar(raiz, function (no) {
    return (no.className || "").split(" ").indexOf(classe) !== -1;
  });
}

function porTag(raiz, tag) {
  return procurar(raiz, function (no) {
    return no.tagName === tag;
  });
}

module.exports = {
  createElement: criarNo,
  procurar: procurar,
  porClasse: porClasse,
  porTag: porTag
};
