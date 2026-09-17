# Fontes do overlay do PDF

Estes arquivos fazem parte do repositório de propósito: o renderer não pode
depender de fonte instalada no sistema operacional do servidor.

## O que são

**Liberation Sans** (Regular, Bold, Italic e Bold Italic), da coleção
Liberation Fonts. As duas faces itálicas entraram com o editor rico de
modelos (Etapa 3.7): itálico e negrito-itálico passaram a ser escolhas
do administrador, e uma face inclinada de verdade é a única forma
honesta de as desenhar.

| arquivo | SHA-256 |
| --- | --- |
| `LiberationSans-Regular.ttf` | `76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8` |
| `LiberationSans-Bold.ttf` | `788abee4c806d660e8aee46689dd8540cd4bb98da03dcc9d171ce3efd99a9173` |
| `LiberationSans-Italic.ttf` | `e5bae5c4cde31f22142753855f4f8fb86da6ff39955ed3c0a11248b0d16948b0` |
| `LiberationSans-BoldItalic.ttf` | `698da70fc191cc5f33ad4d6d3fe830fe4624b898ea2e3169955928b7c491f1ee` |

## De onde vieram

Versão **2.1.5**, do lançamento oficial do projeto no GitHub
(<https://github.com/liberationfonts/liberation-fonts>), pacote
`liberation-fonts-ttf-2.1.5.tar.gz`
(SHA-256 `7191c669bf38899f73a2094ed00f7b800553364f90e2637010a69c0e268f25d0`).

## Licença

**SIL Open Font License, Version 1.1** — texto integral em `LICENSE.txt`,
autoria em `AUTHORS.txt`. A OFL permite expressamente usar, embutir num
documento, modificar e redistribuir. Nenhuma fonte proprietária entra no
projeto: o Arial do documento oficial (propriedade da Monotype) **não** é
extraído nem reutilizado.

## Por que esta fonte

O raciocínio completo, com as medições que sustentam a escolha, está no
docstring de [`pdfengine/fontconfig.py`](../fontconfig.py). Em resumo: a
Liberation Sans é metricamente idêntica ao Arial do documento oficial
(verificado glifo a glifo) e foi desenhada para ter o mesmo traço — e,
embutida no PDF, garante que o resultado seja igual em qualquer leitor.
