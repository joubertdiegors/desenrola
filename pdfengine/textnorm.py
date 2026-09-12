"""
Normalizacao e validacao do texto que vai para dentro do documento.

Duas responsabilidades, as duas de FIDELIDADE -- nenhuma reescreve
conteudo do usuario alem do necessario para o documento sair certo:

1. `normalize_for_document` ajusta os caracteres que tem mais de uma
   forma possivel para a forma que o documento oficial usa. O caso
   concreto e o separador do endereco: o perfil monta
   "Rua 25 – 1200 Cidade" com travessao (U+2013, a convencao de exibicao
   do proprio perfil), e o documento oficial escreve
   "Rue des Exemple 25 - 1200 Woluwe-Saint-Lambert" com hifen simples
   (U+002D). A normalizacao acontece aqui, na camada do documento, e nao
   em `User.get_address_display()`: assim o perfil continua com a sua
   semantica e e o documento que se adapta a propria convencao.

   Os espacos especiais (insecavel, fino) viram espaco normal pelo mesmo
   motivo pratico: a quebra de linha do renderer separa palavras por
   espaco, e um espaco insecavel no meio de um valor faria a "palavra"
   ficar longa demais e estourar a area reservada sem necessidade.

2. `unsupported_characters` diz quais caracteres a fonte embutida nao
   sabe desenhar. Isso importa porque o reportlab NAO avisa: um caractere
   fora da fonte sai como um glifo vazio (`\\x00` na extracao), ou seja,
   um PDF errado gerado em silencio. Com esta checagem, quem chama pode
   falhar explicitamente -- a regra do projeto para tudo neste motor.
"""

from reportlab.pdfbase import pdfmetrics

# Formas de traco que o documento escreve como hifen simples.
_DASHES = {
    "‐": "-",  # hifen tipografico
    "‑": "-",  # hifen insecavel (nem existe na Liberation Sans)
    "‒": "-",  # traco de algarismo
    "–": "-",  # travessao curto (o que o perfil usa)
    "—": "-",  # travessao longo
    "―": "-",  # barra horizontal
    "−": "-",  # sinal de menos
}

# Espacos especiais -> espaco normal (ver motivo no docstring).
_SPACES = {
    " ": " ",  # insecavel
    " ": " ",  # espaco de algarismo
    " ": " ",  # fino
    " ": " ",  # fino insecavel
    "\t": " ",
}

_TRANSLATION = str.maketrans({**_DASHES, **_SPACES})


def normalize_for_document(value) -> str:
    """
    Devolve `value` como texto, na forma que o documento oficial usa.

    Nao mexe em acentos, cedilhas, apostrofos nem em qualquer outra coisa
    que o usuario escreveu: so unifica as variantes de traco e de espaco.
    """
    return str(value).translate(_TRANSLATION)


def unsupported_characters(text, font_name) -> list:
    """
    Os caracteres de `text` que a fonte `font_name` nao sabe desenhar, em
    ordem de aparicao e sem repetir. Lista vazia = tudo renderizavel.
    """
    face = pdfmetrics.getFont(font_name).face
    mapping = getattr(face, "charToGlyph", None)
    if mapping is None:  # fontes padrao do PDF nao expoem o mapa
        return []

    faltando = []
    for char in text:
        if char in ("\n", "\r"):
            continue
        if ord(char) not in mapping and char not in faltando:
            faltando.append(char)
    return faltando


def describe_characters(chars) -> str:
    """Descricao legivel dos caracteres, para a mensagem de erro."""
    return ", ".join(f"{char!r} (U+{ord(char):04X})" for char in chars)
