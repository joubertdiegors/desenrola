/*
 * DOM minimo para testar os modulos do editor rico
 * (`static/js/template-editor/`) fora do navegador.
 *
 * Implementa exatamente o que os modulos usam -- `createElement`,
 * `createTextNode`, `appendChild`, `removeChild`, `childNodes`, `style`,
 * `classList`, `dataset`, `textContent`, `getAttribute`/`setAttribute`,
 * eventos -- e nada mais. NAO e um navegador e nao tenta ser: nao ha
 * layout, nao ha CSS aplicado, nao ha selecao.
 *
 * TEXTO E NO
 * ----------
 * `textContent = "x"` cria um NO DE TEXTO filho (nodeType 3), como no
 * navegador: e assim que `TERuns.serializar` le o bloco de volta, e um
 * stub que guardasse o texto num campo proprio esconderia justamente o
 * caminho que interessa testar.
 *
 * Ha eventos, desde o Bloco F: uma lista de ouvintes por nome e um
 * `disparar` para o teste aciona-los. Sem isso os paineis, que sao
 * todos feitos de `addEventListener`, ficavam intestaveis fora do
 * navegador.
 *
 * O que ele nao cobre continua dependendo de olhar no navegador:
 * empilhamento real, tamanho em tela, cursor, e se da para clicar.
 */
function criarTexto(valor) {
  return { nodeType: 3, nodeValue: String(valor), parentNode: null, children: [] };
}

function criarNo(tag) {
  var no = {
    nodeType: 1,
    tagName: tag,
    style: {},
    children: [],
    dataset: {},
    attrs: {},
    className: "",
    parentNode: null,
    disabled: false,
    hidden: false,
    value: "",

    // `classList` e `className` sao a mesma coisa, como no navegador:
    // `porClasse` le `className`, e um `classList.add` tem de aparecer la.
    classList: {
      _classes: [],
      _sincronizar: function () {
        var proprias = this._classes;
        var tinha = String(no.className || "").split(" ").filter(Boolean);
        var todas = tinha.filter(function (c) { return proprias.indexOf(c) === -1; }).concat(proprias);
        no.className = todas.join(" ");
      },
      add: function (nome) {
        if (this._classes.indexOf(nome) === -1) {
          this._classes.push(nome);
        }
        this._sincronizar();
      },
      remove: function (nome) {
        this._classes = this._classes.filter(function (c) { return c !== nome; });
        no.className = String(no.className || "").split(" ").filter(function (c) {
          return c && c !== nome;
        }).join(" ");
      },
      toggle: function (nome, forcar) {
        var tem = this._classes.indexOf(nome) !== -1;
        var querer = forcar === undefined ? !tem : !!forcar;
        if (querer && !tem) {
          this.add(nome);
        } else if (!querer && tem) {
          this.remove(nome);
        }
        return querer;
      },
      contains: function (nome) {
        return this._classes.indexOf(nome) !== -1 ||
          String(no.className || "").split(" ").indexOf(nome) !== -1;
      }
    },

    get childNodes() {
      return this.children;
    },

    get firstChild() {
      return this.children[0] || null;
    },

    get options() {
      return this.children.filter(function (f) { return f.tagName === "option"; });
    },

    get textContent() {
      return this.children
        .map(function (filho) {
          return filho.nodeType === 3 ? filho.nodeValue : filho.textContent;
        })
        .join("");
    },
    set textContent(valor) {
      this.children = [];
      if (valor !== "" && valor !== null && valor !== undefined) {
        this.appendChild(criarTexto(valor));
      }
    },

    appendChild: function (filho) {
      filho.parentNode = this;
      this.children.push(filho);
      return filho;
    },
    removeChild: function (filho) {
      this.children = this.children.filter(function (f) { return f !== filho; });
      filho.parentNode = null;
      return filho;
    },
    setAttribute: function (chave, valor) {
      this.attrs[chave] = String(valor);
    },
    getAttribute: function (chave) {
      return this.attrs[chave] === undefined ? null : this.attrs[chave];
    },
    hasAttribute: function (chave) {
      return this.attrs[chave] !== undefined;
    },
    contains: function (outro) {
      var atual = outro;
      while (atual) {
        if (atual === this) {
          return true;
        }
        atual = atual.parentNode;
      }
      return false;
    },
    focus: function () {},

    /*
     * EVENTOS -- o minimo para exercitar os paineis.
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
      var alvo = this;
      (this._ouvintes[evento] || []).forEach(function (fn) {
        fn({ target: alvo });
      });
      return this;
    }
  };
  no._ouvintes = {};
  no.classList._classes = [];
  no.ownerDocument = documento;
  return no;
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
      if (filho.nodeType === 1 && condicao(filho)) {
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

var documento = {
  createElement: criarNo,
  createTextNode: criarTexto,
  procurar: procurar,
  porClasse: porClasse,
  porTag: porTag
};

module.exports = documento;
