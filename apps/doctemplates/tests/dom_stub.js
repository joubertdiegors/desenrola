/*
 * DOM minimo para testar `static/js/editor/render.js` fora do navegador.
 *
 * Implementa exatamente o que o renderizador usa -- `createElement`,
 * `appendChild`, `style`, `classList`, `dataset`, `textContent`,
 * `setAttribute` -- e nada mais. NAO e um navegador e nao tenta ser: nao
 * ha layout, nao ha CSS aplicado, nao ha eventos.
 *
 * Para que serve, entao: provar que cada elemento do documento produz um
 * no, com a posicao, o tamanho, a camada e o conteudo certos. Foi assim
 * que se descobriu, na correcao da Etapa 4.2B, que os 19 elementos
 * importados JA estavam sendo desenhados -- o problema era de CSS e de
 * zoom, nao de renderizacao. Um teste que so procurasse strings no HTML
 * do servidor nunca teria mostrado isso.
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
    }
  };
}

module.exports = { createElement: criarNo };
