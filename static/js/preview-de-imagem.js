/*
 * Pre-visualizacao de um arquivo de imagem escolhido, antes de enviar
 * (Bloco D: upload direto no formulario de Parceiros e de Banners).
 *
 * PROGRESSIVO
 * -----------
 * Sem este script o campo continua sendo um `<input type="file">`
 * comum -- o navegador ja mostra o nome do arquivo escolhido. O script
 * so acrescenta a MINIATURA ao lado, delegado em `change` para
 * qualquer campo com `data-preview-de-imagem`, presente hoje ou
 * inserido depois.
 *
 * NUNCA MONTA HTML
 * ----------------
 * Só troca o `src` de um `<img>` que já existe na marcação (gravado
 * pelo servidor, escondido por `hidden`) -- nunca `innerHTML`, nunca
 * `createElement`. Montar marcação aqui seria a segunda implementação
 * visual que este projeto recusa.
 */
(function () {
  "use strict";

  document.addEventListener("change", function (evento) {
    var campo = evento.target;
    if (!campo.matches("[data-preview-de-imagem]")) {
      return;
    }
    var preview = campo.parentElement.querySelector(".imagem-preview");
    if (!preview) {
      return;
    }
    var arquivo = campo.files && campo.files[0];
    if (!arquivo) {
      preview.hidden = true;
      preview.src = "";
      return;
    }
    preview.src = URL.createObjectURL(arquivo);
    preview.hidden = false;
  });
})();
