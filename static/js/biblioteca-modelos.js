/*
 * As janelas sobrepostas da tela de Modelos.
 *
 * O QUE ELE FAZ -- E O QUE ELE NAO FAZ
 * ------------------------------------
 * Faz: abrir e fechar as tres janelas (`<dialog>`), preencher a que
 * abriu com o que o botao clicado carrega em `data-*`, e ligar o
 * interruptor "Ver com dados de exemplo" a URL do documento.
 *
 * Nao faz: filtrar, ordenar, paginar, duplicar, ativar. Tudo isso e
 * link ou formulario de verdade, resolvido no servidor -- a tela
 * continua inteira com o JavaScript desligado, e as janelas sao o
 * unico luxo que depende dele (por isso o botao de visualizar so
 * aparece quando ha o que mostrar).
 *
 * NADA DE innerHTML
 * -----------------
 * Os valores vem do banco. Entram por `textContent` e por `src`/`href`
 * de URLs que o proprio Django gerou -- nunca como marcacao.
 */
(function () {
  "use strict";

  var pagina = document.querySelector(".mod");
  if (!pagina || typeof HTMLDialogElement === "undefined") {
    return;
  }

  /* O modelo que abriu a janela: e dele que sai o que ela mostra. */
  var atual = null;

  function janela(id) {
    var no = document.getElementById(id);
    return no && typeof no.showModal === "function" ? no : null;
  }

  function preencher(alvo, dados) {
    alvo.querySelectorAll("[data-campo]").forEach(function (no) {
      var chave = no.dataset.campo;
      if (chave === "oficial") {
        // A pílula "Oficial" aparece ou não; o texto dela é fixo.
        no.hidden = dados.oficial !== "1";
        return;
      }
      var valor = dados[chave];
      no.textContent = valor === undefined || valor === "" ? "—" : valor;
    });
    alvo.querySelectorAll("[data-campo-href]").forEach(function (no) {
      var destino = dados[no.dataset.campoHref];
      if (destino) {
        no.href = destino;
        no.hidden = false;
      } else {
        no.hidden = true;
      }
    });
  }

  /* A situação em palavra, para a janela de detalhes. */
  var SITUACOES = { ativo: "Ativo", rascunho: "Rascunho (ainda não utilizável)", inativo: "Inativo" };

  function documentoDoModelo(dados, comExemplo) {
    if (!dados.previa) {
      return "about:blank";
    }
    return dados.previa + (comExemplo ? "?exemplo=1" : "");
  }

  pagina.addEventListener("click", function (evento) {
    var gatilho = evento.target.closest("[data-abrir]");
    if (!gatilho) {
      return;
    }
    var alvo = janela(gatilho.dataset.abrir);
    if (!alvo) {
      return;
    }
    evento.preventDefault();

    atual = Object.assign({}, gatilho.dataset);
    if (atual.situacao) {
      atual.situacao = SITUACOES[atual.situacao] || atual.situacao;
    }
    preencher(alvo, atual);

    var quadro = alvo.querySelector("[data-documento]");
    if (quadro) {
      var exemplo = alvo.querySelector("[data-exemplo]");
      if (exemplo) {
        exemplo.checked = false;
      }
      quadro.src = documentoDoModelo(atual, false);
    }

    // O menu de ações fica aberto atrás da janela se ninguém o fechar.
    var menu = gatilho.closest("details[open]");
    if (menu) {
      menu.open = false;
    }

    alvo.showModal();
    var primeiro = alvo.querySelector("[data-exemplo], input, select, .mod-btn");
    if (primeiro) {
      primeiro.focus();
    }
  });

  document.querySelectorAll("dialog.mod-janela").forEach(function (alvo) {
    alvo.addEventListener("click", function (evento) {
      if (evento.target.closest("[data-fechar]")) {
        alvo.close();
        return;
      }
      // Clique no fundo (fora do conteúdo) fecha, como a referência.
      if (evento.target === alvo) {
        alvo.close();
      }
    });

    alvo.addEventListener("close", function () {
      var quadro = alvo.querySelector("[data-documento]");
      if (quadro) {
        // Solta o PDF: uma janela fechada não continua carregando nada.
        quadro.src = "about:blank";
      }
    });

    var exemplo = alvo.querySelector("[data-exemplo]");
    if (exemplo) {
      exemplo.addEventListener("change", function () {
        var quadro = alvo.querySelector("[data-documento]");
        if (quadro && atual) {
          quadro.src = documentoDoModelo(atual, exemplo.checked);
        }
      });
    }
  });

  /*
   * "Novo modelo": o formulário posta para a rota de DUPLICAÇÃO do
   * modelo escolhido como base -- criar é copiar um que já funciona.
   * O nome começa preenchido a partir da base, e quem clicou pode
   * trocá-lo antes de criar.
   */
  var novo = document.querySelector("[data-form-novo]");
  if (novo) {
    var base = novo.querySelector("[data-base]");
    var nome = novo.querySelector("input[data-nome]");

    var sugerir = function () {
      var escolhida = base.options[base.selectedIndex];
      novo.action = base.value;
      if (escolhida && (!nome.value || nome.dataset.sugerido === "1")) {
        nome.value = "Cópia de " + escolhida.dataset.nome;
        nome.dataset.sugerido = "1";
      }
    };

    nome.addEventListener("input", function () {
      nome.dataset.sugerido = "0";
    });
    base.addEventListener("change", function () {
      nome.dataset.sugerido = nome.dataset.sugerido === "0" ? "0" : "1";
      sugerir();
    });
    nome.dataset.sugerido = "1";
    sugerir();
  }

  /* Um menu aberto fecha ao clicar fora dele ou com Esc. */
  document.addEventListener("click", function (evento) {
    document.querySelectorAll(".mod-menu[open]").forEach(function (menu) {
      if (!menu.contains(evento.target)) {
        menu.open = false;
      }
    });
  });
  document.addEventListener("keydown", function (evento) {
    if (evento.key !== "Escape") {
      return;
    }
    document.querySelectorAll(".mod-menu[open]").forEach(function (menu) {
      menu.open = false;
    });
  });
})();
