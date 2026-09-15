/*
 * Pre-visualizacao do conteudo, no editor de uma parte da Home.
 *
 * DUAS COISAS, E SO ELAS
 * ----------------------
 * 1. trocar a LARGURA do quadro (Desktop / Tablet / Celular);
 * 2. redesenhar o quadro com o que esta DIGITADO, sem gravar.
 *
 * PROGRESSIVO
 * -----------
 * Sem este script o quadro continua mostrando o que esta SALVO -- o
 * `src` do iframe e um GET comum -- e os botoes de largura ficam
 * escondidos por CSS (`.bo-previa-head nav` so aparece com
 * `js-ligado` no `<html>`). Nada de botao que nao faz nada.
 *
 * A LARGURA E DE VERDADE
 * ----------------------
 * Trocar de aparelho estreita o QUADRO. Dentro de um `<iframe>`, a
 * largura do elemento e a largura de referencia das media queries --
 * entao o CSS do site responde como responderia naquele aparelho. Nao
 * ha desenho encolhido: ha a pagina, mais estreita.
 *
 * O SERVIDOR DESENHA
 * ------------------
 * O quadro nao e montado aqui. O formulario inteiro vai por POST para
 * a previa, o Django monta o conteudo com o MESMO codigo do
 * salvamento (`FormularioDeSecao.conteudo()`) e devolve a pagina
 * pronta. Montar o HTML aqui seria a segunda implementacao visual que
 * este projeto recusa.
 */
(function () {
  "use strict";

  var form = document.getElementById("form-da-secao");
  var painel = document.getElementById("painel-da-previa");
  if (!form || !painel) {
    return;
  }

  var quadro = painel.querySelector(".bo-previa-quadro");
  var palco = painel.querySelector(".bo-previa-palco");
  var botoes = painel.querySelectorAll("[data-viewport]");
  var endereco = form.getAttribute("data-previa");
  if (!quadro || !palco || !endereco) {
    return;
  }

  // Diz ao CSS que os controles agora fazem alguma coisa.
  document.documentElement.classList.add("js-ligado");

  var viewport = "desktop";
  var pedido = null;
  var esperando = null;

  function escolherLargura(nome) {
    viewport = nome;
    palco.setAttribute("data-viewport", nome);
    botoes.forEach(function (botao) {
      var ligado = botao.getAttribute("data-viewport") === nome;
      botao.classList.toggle("is-on", ligado);
      botao.setAttribute("aria-pressed", ligado ? "true" : "false");
    });
    redesenhar();
  }

  function redesenhar() {
    // Uma requisicao por vez: a anterior e abandonada quando outra
    // comeca, senao duas respostas fora de ordem deixariam o quadro
    // mostrando o texto antigo.
    if (pedido) {
      pedido.abort();
    }
    pedido = new AbortController();

    var dados = new FormData(form);
    dados.set("viewport", viewport);

    fetch(endereco, {
      method: "POST",
      body: dados,
      credentials: "same-origin",
      signal: pedido.signal,
    })
      .then(function (resposta) {
        if (!resposta.ok) {
          throw new Error(String(resposta.status));
        }
        return resposta.text();
      })
      .then(function (html) {
        quadro.srcdoc = html;
      })
      .catch(function () {
        /*
         * Sessao expirada, rede fora, permissao revogada. O quadro fica
         * com o ultimo desenho bom -- melhor do que ficar em branco --
         * e o formulario continua funcionando: quem salva e o POST
         * normal, nao isto.
         */
      });
  }

  function agendar() {
    window.clearTimeout(esperando);
    esperando = window.setTimeout(redesenhar, 350);
  }

  botoes.forEach(function (botao) {
    botao.addEventListener("click", function () {
      escolherLargura(botao.getAttribute("data-viewport"));
    });
  });

  form.addEventListener("input", agendar);
  form.addEventListener("change", agendar);

  // O primeiro desenho ja sai com o que esta na tela.
  redesenhar();
})();
