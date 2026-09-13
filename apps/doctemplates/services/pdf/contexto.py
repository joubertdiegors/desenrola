"""
Resolucao dos CAMPOS de um documento na hora de gerar o PDF (Etapa 3.4).

O layout guarda campos como estrutura -- `{"kind": "field", "source":
"convidado.nome"}` -- e nao como `{{convidado.nome}}` dentro de uma
string. Este modulo e o unico ponto em que essa estrutura vira texto, e
so no momento do desenho.

POR QUE ISSO IMPORTA
--------------------
Substituicao textual e o atalho que estraga documento: um valor que por
acaso contenha "{{" ou "}}" passa a ser reinterpretado, e nao ha como
distinguir o que era dado do que era gabarito. Mantendo o campo
estrutural ate aqui, o valor do usuario nunca e reinterpretado -- ele e
escrito onde o elemento manda e acabou.

SEM DJANGO
----------
Nada aqui importa Django. O contexto chega pronto, como um dicionario
plano de `"fonte.campo" -> texto`. Quem sabe ler um `User` ou um
snapshot de carta e a camada de aplicacao, nao o renderer.
"""

from ... import datasources


class CampoDesconhecidoError(KeyError):
    """A referencia nao existe no registro de fontes de dados."""


class ValorAusenteError(KeyError):
    """A referencia existe, mas o contexto nao trouxe valor para ela."""


class Contexto:
    """
    Os valores de um documento, prontos para desenhar.

    `valores` e plano: `{"convidado.nome": "Carlos", ...}`. Simples de
    montar a partir de qualquer origem e simples de conferir num teste.

    `estrito` decide o que fazer com um campo sem valor. Ligado (padrao),
    levanta: um documento oficial com um campo vazio e um documento
    errado, e falhar alto na geracao e melhor do que entregar um PDF com
    um buraco. Desligado, devolve vazio -- util para pre-visualizacao.
    """

    def __init__(self, valores=None, *, estrito=True):
        self.valores = dict(valores or {})
        self.estrito = estrito
        self._conferir_referencias()

    def _conferir_referencias(self):
        """
        Recusa, na CONSTRUCAO, uma chave que nao exista no registro.

        Assim um erro de digitacao (`convidado.nomee`) aparece antes de
        qualquer desenho, e nao como um campo silenciosamente vazio no
        meio da pagina.
        """
        desconhecidas = sorted(
            chave for chave in self.valores if not datasources.referencia_valida(chave)
        )
        if desconhecidas:
            raise CampoDesconhecidoError(
                "O contexto tem referências que não existem no registro de fontes "
                f"de dados: {', '.join(desconhecidas)}."
            )

    def resolver(self, referencia):
        """O texto de um campo. Sempre str -- quem desenha nao trata None."""
        if not datasources.referencia_valida(referencia):
            raise CampoDesconhecidoError(
                f'O layout referencia "{referencia}", que não existe no registro '
                "de fontes de dados."
            )
        if referencia not in self.valores:
            if self.estrito:
                raise ValorAusenteError(
                    f'O contexto não trouxe valor para "{referencia}".'
                )
            return ""
        valor = self.valores[referencia]
        return "" if valor is None else str(valor)

    def referencias_faltando(self, usadas):
        """
        Quais das `usadas` o contexto nao tem -- para quem chama poder
        avisar de uma vez, em vez de descobrir uma por vez ao desenhar.
        """
        return sorted(referencia for referencia in usadas if referencia not in self.valores)


def texto_do_bloco(bloco, contexto):
    """
    O texto de um bloco de conteudo, ja resolvido.

    Serve a `text`, `number` e as celulas da tabela. `rich_text` NAO usa
    esta funcao: la cada trecho pode ter peso proprio, entao os trechos
    precisam sobreviver separados ate a quebra de linha (ver `texto.py`).
    """
    if not isinstance(bloco, dict):
        return ""
    forma = bloco.get("kind")
    if forma == "text":
        return bloco.get("value") or ""
    if forma == "field":
        return contexto.resolver(bloco.get("source"))
    if forma == "mixed":
        return "".join(
            texto_do_bloco(parte, contexto) for parte in bloco.get("parts") or []
        )
    # `asset` nao tem texto: quem desenha imagem nao passa por aqui.
    return ""
