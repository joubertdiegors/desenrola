# Fase 4 · Etapa 1 — Especificação técnica do PDF oficial (Carta Convite, FR)

Documento de referência para a implementação futura do `pdfengine`. Não
contém código, não altera nenhum modelo existente. Fonte: o arquivo
`Modelo-Carta-Convite-FR.pdf` anexado à conversa em 12/09/2026.

## 0. Como ler este documento

Cada afirmação abaixo é marcada com uma destas três etiquetas:

- **[TEXTO]** — extraído literalmente do conteúdo do PDF (alta confiança;
  é o texto real, caractere a caractere, incluindo acentuação).
- **[VISUAL]** — lido da imagem renderizada da página (posição relativa,
  proporção, hierarquia visual). Confiável para *layout e composição*,
  mas **não é medição em pontos/mm** — são estimativas de proporção.
- **[BINÁRIO — PENDENTE]** — exige abrir o arquivo com `pypdf` /
  `pdfplumber` / `pypdfium2` (já estão em `requirements/base.txt`, já
  instalados no venv) para confirmar. Eu não tive acesso ao arquivo em
  disco nesta etapa — recebi o PDF apenas como conteúdo extraído
  (texto + imagem) dentro da conversa, não como bytes num caminho que eu
  pudesse abrir com essas bibliotecas. **Nenhum valor numérico de
  coordenada, versão de PDF, fonte incorporada ou AcroForm foi inventado
  — o que não pôde ser confirmado está listado explicitamente como
  pendente**, com o comando exato para confirmar assim que o arquivo for
  colocado em disco (ver seção 8).

## 1. Diagnóstico técnico do PDF

### 1.1 Estrutura geral

| Item | Valor | Confiança |
|---|---|---|
| Número de páginas | 1 | **[VISUAL]** — só uma página foi fornecida/renderizada |
| Orientação | Retrato | **[VISUAL]** |
| Tamanho da página | Provavelmente A4 (595 × 842 pt / 210 × 297 mm) | **[VISUAL]** — proporção da imagem é compatível com A4; documento administrativo belga/francês quase certamente não usa Letter. **[BINÁRIO — PENDENTE]** para confirmar `page.mediabox` |
| Versão do PDF | — | **[BINÁRIO — PENDENTE]** — `pypdf.PdfReader(path).pdf_header` |
| AcroForm (campos interativos) | Provavelmente **ausente** | **[VISUAL]** — não há caixas de formulário, checkboxes ou campos sublinhados típicos de formulário preenchível; o documento é uma **amostra já preenchida** (valores como `00000000`, `YY000000`, `Carlos Eduardo Silva`, `Rue des Exemple 25` são claramente placeholders fictícios, não um formulário em branco). **[BINÁRIO — PENDENTE]** para confirmar via `reader.get_fields()` / `"/AcroForm" in reader.trailer["/Root"]` |
| Camada de texto real vs. digitalização | Provavelmente **texto real embutido** (não é um scan/imagem) | **[VISUAL]/[TEXTO]** — a extração reproduziu acentuação francesa perfeita (é, è, °) e **distinguiu negrito de peso regular** run a run dentro da mesma frase; isso é típico de um PDF com texto nativo, não de OCR sobre uma imagem escaneada. **[BINÁRIO — PENDENTE]** para confirmar via `page.extract_text()` não vazio e inspeção de `/Font` em `page["/Resources"]` |
| Fontes utilizadas | **Arial Regular e Arial Bold**, embutidas como subconjunto (`/BAAAAA+ArialMT`, `/AAAAAA+Arial-BoldMT`, Type0/Identity-H) | **[CONFIRMADO na Etapa 2]** — o overlay do projeto NÃO reutiliza essa Arial (proprietária da Monotype): usa **Liberation Sans** (SIL OFL 1.1), metricamente idêntica (verificado glifo a glifo) e desenhada como clone da Arial. Ver `pdfengine/fontconfig.py` |
| Fontes incorporadas | — | **[BINÁRIO — PENDENTE]** — `reader.pages[0]["/Resources"]["/Font"]` |
| Cores | Preto (texto), tricolor preto/amarelo/vermelho (faixa superior — bandeira belga), azul-marinho + laranja/vermelho (logo IBZ, ver 1.3) | **[VISUAL]** |

### 1.2 Elementos gráficos (topo → base da página)

1. **Faixa tricolor no topo** — largura total da página, altura pequena
   (uma faixa fina). Três blocos de cor sólida iguais: preto / amarelo /
   vermelho (bandeira da Bélgica). **[VISUAL]** Muito provavelmente um
   **vetor** (retângulos de cor sólida) e não uma imagem raster — é o
   padrão mais barato e mais nítido de reproduzir, e não há gradientes
   nem textura visíveis. **[BINÁRIO — PENDENTE]** para confirmar (checar
   se há um `XObject` de imagem nessa região ou só operadores de
   desenho vetorial `re`/`f`).
2. **Título + subtítulo**, centralizados, logo abaixo da faixa.
3. **Corpo de texto** (parágrafos, tabela, lista numerada) — texto real.
4. **Bloco de assinatura** (linha em branco + nome + legenda), alinhado à
   esquerda, próximo à base da página.
5. **Linha "Fait à ..., le ..."**, entre o corpo e o bloco de assinatura,
   com alinhamento mais à direita que o corpo do texto (mais perto da
   margem direita do que da esquerda). **[VISUAL]**
6. **Logo IBZ** (Office des étrangers / Vreemdelingenzaken) — canto
   inferior direito, na mesma faixa vertical do bloco de assinatura.
   **Achado importante:** o logo já traz o nome do órgão em **francês E
   holandês** dentro da própria imagem ("Office des étrangers" /
   "Vreemdelingenzaken") — ou seja, **este mesmo asset gráfico serve para
   qualquer idioma do site**, sem precisar de uma variante por idioma.
   **[VISUAL]**. Tipo de objeto (raster vs. vetor): **[BINÁRIO —
   PENDENTE]**.
7. **QR Code** — imediatamente à direita do logo IBZ, mesmo alinhamento
   vertical. **[VISUAL]**. Conteúdo/payload do QR: **não é possível
   decodificar a partir da imagem fornecida** — ver risco crítico na
   seção 7.

### 1.3 Tabela de dados do convidado

Uma tabela com borda visível, 2 colunas × 5 linhas: coluna esquerda com
o rótulo em **negrito** terminado em `:`, coluna direita com o valor em
peso regular. **[VISUAL]/[TEXTO]**

| Linha | Rótulo (fixo) | Valor de exemplo (variável) |
|---|---|---|
| 1 | Nom et prénom : | Carlos Eduardo Silva |
| 2 | Nationalité : | Brésilienne |
| 3 | Date de naissance : | 22/07/1990 |
| 4 | N° de passeport : | YY000000 |
| 5 | Durée : | du 10/10/2026 au 24/10/2026 (15 jours) |

A linha 5 é a única célula da tabela que **mistura texto fixo com
variável dentro do mesmo valor** (`du {chegada} au {partida} ({dias}
jours)`) — as outras quatro células são um valor puro, sem texto fixo
misturado dentro da célula (o rótulo fixo já está na célula vizinha).

## 2. Texto completo, marcado por fixo/variável

Reproduzido na íntegra (é a fonte de verdade — nada foi resumido ou
reescrito). `{chave}` marca onde entra dado variável; **negrito**
reproduz exatamente o que está em negrito no PDF original.

```
LETTRE D'INVITATION ET D'HÉBERGEMENT                              [fixo, título]
(COURT SÉJOUR EN BELGIQUE)                                        [fixo, subtítulo]

À l'attention des autorités compétentes.                          [fixo, parágrafo isolado]

Je soussignée, {host_name: negrito}, née le {host_birth: regular},
de nationalité {host_nationality: regular}, titulaire de la carte
d'identité {host_document_type: regular} n° {host_document: negrito},
domiciliée au {host_address: negrito}, téléphone {host_phone: negrito},
invite par la présente :                                          [MISTO — ver 3.1]

[TABELA — ver 1.3]

1. La présente invitation est établie dans le cadre d'une            [fixo — "visite privée"
   **visite privée**.                                                 em negrito, resto regular]
2. Pendant toute la durée de son séjour en Belgique, la personne
   invitée sera hébergée à mon domicile situé à l'adresse
   suivante : {host_address: negrito}                             [MISTO — ver 3.2]
3. La personne invitée assume personnellement ses frais de
   voyage, de séjour, de nourriture, d'assurance, de transport
   et autres dépenses liées à son séjour.                         [100% fixo]

La présente lettre constitue exclusivement une invitation privée
et une confirmation d'hébergement et ne constitue pas un
engagement de prise en charge financière au sens de l'Annexe
3bis.                                                              [100% fixo]

Je certifie l'exactitude des informations reprises dans la
présente lettre et reste disponible auprès des autorités
compétentes pour toute vérification concernant cette invitation
et les conditions d'hébergement.                                  [100% fixo]

La personne invitée s'engage à respecter les conditions
applicables à son séjour et à quitter le territoire de l'espace
Schengen à l'issue de la durée autorisée.                         [100% fixo]

Fait à {place: regular}, le {document_date: regular}               [MISTO — ver 3.3]

_______________________________                                   [linha de assinatura,
                                                                     provavelmente traço/
                                                                     sublinhado desenhado]
{signature_name: negrito}                                          [variável isolado — ver 3.4]
Signature de l'invitante                                           [fixo, legenda]

[LOGO IBZ]                              [QR CODE]                  [gráficos fixos]
```

### Observação sobre `host_document_type`

O texto oficial usa **"carte d'identité {qualificador}"** (no exemplo:
"carte d'identité **belge**") — ou seja, o tipo de documento aparece
qualificado pela nacionalidade/origem do documento dentro da própria
frase, não como um rótulo genérico solto ("Documento de identidade:
Carte d'identité", como está hoje o campo `host_document_label` da Fase
3). Isso **não exige mudança agora**, mas é um ponto de atenção para a
Fase 4 seguinte: o campo de texto livre já existente (`host_document_label`)
continua servindo, desde que o usuário digite a frase já qualificada
(ex.: "carte d'identité belge"); alternativamente, no futuro, isso
poderia virar dois campos (tipo + nacionalidade do documento) combinados
pelo template. Registrado aqui, não decidido nem implementado.

## 3. As quatro zonas de texto misto (o ponto central do pedido)

Estas são as únicas quatro zonas do documento onde texto fixo e variável
aparecem **entrelaçados no mesmo fluxo de texto** — todo o resto do
documento é ou 100% fixo (fica intocado no PDF original) ou um valor
100% variável isolado (rótulo fixo já vem do PDF original; só o valor é
"furo a preencher", sem precisar reconstruir nenhuma frase).

### 3.1 Parágrafo do anfitrião ("Je soussignée...")

O mais complexo: uma única frase com **6 valores variáveis** intercalados
em texto fixo, com **pesos de fonte diferentes por valor** (achado
concreto, não estimado — vem da própria extração com marcação de
negrito):

| Trecho | Fixo/Variável | Peso |
|---|---|---|
| "Je soussignée, " | fixo | regular |
| `host_name` | variável | **negrito** |
| ", née le " | fixo | regular |
| `host_birth` | variável | regular (**não** negrito) |
| ", de nationalité " | fixo | regular |
| `host_nationality` | variável | regular (**não** negrito) |
| ", titulaire de la carte d'identité " | fixo | regular |
| `host_document_type` | variável | regular (**não** negrito) |
| " n° " | fixo | regular |
| `host_document` | variável | **negrito** |
| ", domiciliée au " | fixo | regular |
| `host_address` | variável | **negrito** |
| ", téléphone " | fixo | regular |
| `host_phone` | variável | **negrito** |
| ", invite par la présente :" | fixo | regular |

Ou seja: nome, número de documento, endereço e telefone saem em
**negrito**; data de nascimento e nacionalidade saem em **peso regular**,
apesar de todos serem variáveis. Um renderer que aplicar negrito
uniformemente a "tudo que é variável" reproduziria o documento
**incorretamente**.

### 3.2 Item 2 da lista ("...à l'adresse suivante : ...")

Mais simples — um único valor variável (`host_address`, em **negrito**)
no final de uma frase fixa. Repete o **mesmo campo** já usado em 3.1
(`host_address`), mas numa posição e frase diferentes — o renderer
precisa desenhar o mesmo valor duas vezes, em dois lugares.

### 3.3 Linha de fechamento ("Fait à ..., le ...")

Dois valores variáveis curtos (`place`, `document_date`), peso regular,
numa linha isolada entre o corpo do texto e o bloco de assinatura.

### 3.4 Nome sob a linha de assinatura

Tecnicamente **não é uma mistura** (é um valor sozinho na própria linha,
em negrito) — mas repete `host_name`, já usado em 3.1. Listado aqui para
fechar a contagem de repetições.

**Resumo de repetição de campos:** `host_name` aparece 2× (3.1 e 3.4);
`host_address` aparece 2× (3.1 e 3.2). Todos os demais campos aparecem
exatamente 1×.

## 4. Mapa completo dos campos

Legenda de coluna **Origem**: campo já existe no modelo atual (Fase 2/3)
ou precisa de derivação nova (sem criar nenhum campo de formulário novo
— ver conclusão ao final da tabela).

| Chave | Origem dos dados | Tipo | Obrig. | Zona (seção 2/3) | Isolado/Misto | Peso | Alinhamento | Quebra de linha | Observações |
|---|---|---|---|---|---|---|---|---|---|
| `host_name` | `User.full_name` (live → congelado em `Letter.snapshot.host.full_name`) | texto | sim | 3.1 e 3.4 | misto (3.1) / isolado (3.4) | **negrito** nas duas ocorrências | esquerda, inline | não (nome curto) | aparece 2× |
| `host_birth` | **novo campo necessário** — não existe hoje em `Letter.data` nem em `User` | data | sim | 3.1 | misto | regular | esquerda, inline | não | Fase 3 não coletou data de nascimento do anfitrião; só do convidado. Precisa de decisão do cliente (ver risco 7.6) |
| `host_nationality` | `Letter.data["host_nationality"]` (Fase 3) | texto | sim | 3.1 | misto | regular | esquerda, inline | não | grafia deve concordar em francês (ex.: "belge", minúsculo, forma adjetiva) |
| `host_document_type` | `Letter.data["host_document_label"]` (Fase 3, reaproveitado) | texto | sim | 3.1 | misto | regular | esquerda, inline | não | ver observação da seção 2 sobre a frase já vir qualificada |
| `host_document` | `Letter.data["host_document_number"]` (Fase 3) | texto | sim | 3.1 | misto | **negrito** | esquerda, inline | não | |
| `host_address` | `User.get_address_display()` (live → congelado no snapshot) | texto | sim | 3.1 e 3.2 | misto | **negrito** nas duas ocorrências | esquerda, inline | possível (endereço longo) | aparece 2×; ambas as ocorrências precisam do mesmo valor |
| `host_phone` | `User.phone` (live → congelado no snapshot) | texto | sim | 3.1 | misto | **negrito** | esquerda, inline | não | |
| `guest_name` | `Letter.data["guest_name"]` (Fase 3) | texto | sim | tabela, linha 1 | isolado (célula) | regular | esquerda | possível | |
| `guest_nationality` | `Letter.data["guest_nationality"]` (Fase 3) | texto | sim | tabela, linha 2 | isolado (célula) | regular | esquerda | não | forma de substantivo, não adjetivo (ex.: "Brésilienne", maiúsculo) — diferente da forma usada para `host_nationality`; ver risco 7.7 |
| `guest_birth` | `Letter.data["guest_birth_date"]` (Fase 3) | data | sim | tabela, linha 3 | isolado (célula) | regular | esquerda | não | |
| `guest_passport` | `Letter.data["guest_passport"]` (Fase 3) | texto | sim | tabela, linha 4 | isolado (célula) | regular | esquerda | não | |
| `arrival_date` | `Letter.data["stay_arrival"]` (Fase 3) | data | sim | tabela, linha 5 (composta) | misto (dentro da célula) | regular | esquerda | não | compõe a célula "Durée" junto com `departure_date`/`duration_days` |
| `departure_date` | `Letter.data["stay_departure"]` (Fase 3) | data | sim | tabela, linha 5 (composta) | misto | regular | esquerda | não | |
| `duration_days` | **computado**, não armazenado — `(departure - arrival).days`, já calculado hoje em `apps/letters/views.py:_stay_duration_days` para exibição no wizard | número (derivado) | — | tabela, linha 5 (composta) | misto | regular | esquerda | não | recalcular no momento da geração/snapshot, não reaproveitar um valor gravado (evita inconsistência se a lógica de cálculo mudar) |
| `place` | **derivação recomendada**: `User.city` (já existe no modelo de usuário, Fase 1/2) | texto | sim | 3.3 | misto | regular | direita (mais próximo da margem direita que o corpo) | não | **achado**: no exemplo, o local ("Woluwe-Saint-Lambert") é a MESMA cidade do endereço do anfitrião — sugere fortemente que `place` = cidade do usuário, sem precisar de campo novo. A confirmar com o cliente (ver risco 7.5) |
| `document_date` | **derivação recomendada**: data de `Letter.snapshot.finalized_at` (já gravado hoje pela Fase 3, `services.build_snapshot`) | data | sim | 3.3 | misto | regular | direita | não | data em que a carta foi finalizada — já existe, não precisa de campo novo |
| `signature_name` | = `host_name` (mesmo dado, reaproveitado) | texto | sim | 3.4 | isolado | **negrito** | esquerda | não | não é um campo novo; é `host_name` redesenhado numa segunda posição |

**Conclusão da seção 4:** dos ~17 campos solicitados para avaliação,
**apenas `host_birth` exige uma decisão de coleta de dado novo** — todos
os outros já existem em `User`/`Letter.data` (Fase 2/3) ou são
computáveis a partir do que já existe (`duration_days`, `place`,
`document_date`, `signature_name`). Isso reduz bastante o risco de
mudança no wizard nesta fase.

## 5. Arquitetura recomendada

Mantendo tudo que já existe intacto (`LetterTemplate`, `TemplateVersion`,
`field_schema`, `Letter.data`/`snapshot`, a regra de imutabilidade de
versão publicada) e **acrescentando**, numa fase de implementação futura,
os seguintes blocos ao `TemplateVersion` — conceitualmente, sem
implementar agora:

```
TemplateVersion (já existe)
  ├── field_schema          [JÁ EXISTE — Fase 2/3, inalterado]
  │     Contrato de dados: quais campos existem, tipo, obrigatoriedade,
  │     tradução de rótulos (Fase 3). Continua sendo a ÚNICA fonte de
  │     verdade sobre QUE dados existem e como validá-los.
  │
  ├── document_structure    [NOVO — conteúdo de texto rico, estruturado]
  │     Uma árvore de nós no estilo ProseMirror/Tiptap (parágrafos, texto
  │     com marcas de negrito/itálico, e um tipo de nó especial "field"
  │     que referencia uma `key` do field_schema). Cobre EXATAMENTE as
  │     quatro zonas mistas da seção 3 — cada uma vira um parágrafo com
  │     nós de texto fixo intercalados com nós de campo. Os elementos
  │     100% fixos (títulos, itens 1 e 3, os dois parágrafos jurídicos,
  │     a legenda da assinatura) também entram aqui, como parágrafos só
  │     de texto — isso é o que permite ao administrador editar QUALQUER
  │     texto do documento (inclusive o texto jurídico, quando o cliente
  │     fornecer a versão oficial) sem tocar em código.
  │
  ├── layout                [NOVO — onde cada bloco vai na página]
  │     Tamanho/orientação da página, margens, e uma âncora
  │     (posição aproximada + largura disponível) para cada bloco de
  │     `document_structure` e para a tabela. Também guarda QUAIS regiões
  │     do PDF-base precisam ser "mascaradas" (pintadas de branco) antes
  │     do overlay, porque contêm texto de amostra que será substituído.
  │
  ├── assets                [NOVO — referências, não os arquivos em si]
  │     Referência ao PDF-base por idioma (o arquivo oficial, tratado
  │     como Asset — reaproveitando o modelo `apps.content.Asset` já
  │     existente, com um novo `Kind` do tipo "base_document", em vez de
  │     inventar um mecanismo de arquivo paralelo). Também a regra de
  │     geração do QR Code (estático vs. dinâmico — ver risco 7.1) e a
  │     referência ao logo IBZ (um único asset, reaproveitado nos 4
  │     idiomas, conforme achado da seção 1.2).
  │
  └── styles                [NOVO — tokens de estilo, pequenos e nomeados]
        Um conjunto pequeno de estilos nomeados (ex.: "body",
        "body-bold", "title", "subtitle"), cada um com fonte/tamanho/
        peso/cor. `document_structure` referencia estilos pelo NOME, não
        embute fonte/tamanho em cada nó — isso é o que permite trocar a
        aparência do documento inteiro (ex.: ajustar o tamanho da fonte
        do corpo) sem reescrever cada parágrafo.
```

**Por que não colocar tudo dentro de `field_schema`:** `field_schema`
responde "que dados existem e como validá-los" (contrato de formulário,
já teve seu formato definido e testado na Fase 2/3). `document_structure`
responde "que texto aparece no documento e onde cada dado entra nesse
texto" (contrato de composição do documento). São perguntas diferentes;
tratá-las como uma coisa só forçaria o `field_schema` a carregar texto
jurídico extenso dentro de cada definição de campo, o que já não fazia
sentido nem na Fase 3 (por isso o texto dos avisos ficou nos `label` dos
campos-checkbox, uma solução propositalmente provisória).

**Imutabilidade:** os quatro blocos novos (`document_structure`,
`layout`, `assets`, `styles`) entrariam nos mesmos
`TemplateVersion.STRUCTURAL_FIELDS` já protegidos por
`TemplateVersionImmutableError` — uma versão publicada continuaria
congelada por completo, incluindo o texto do documento e o layout, não
só o `field_schema`. Nenhuma mudança de código é necessária para isso
*hoje*; é só a extensão natural da regra já existente quando os campos
forem de fato adicionados ao modelo.

## 6. Onde entra o editor estruturado (Tiptap ou equivalente)

`document_structure`, do jeito descrito acima, **já nasce no formato que
um editor ProseMirror/Tiptap produz nativamente**: um documento é uma
lista de nós, cada nó tem um tipo (`paragraph`, `text`) e nós de texto
podem ter `marks` (negrito, itálico). O único ingrediente que falta no
Tiptap "de fábrica" é o nó de campo variável — e isso é um caso de uso
**padrão e bem documentado** no ecossistema Tiptap/ProseMirror (o mesmo
padrão usado por editores de e-mail com "mail merge": um nó inline
customizado, ex. `field`, com um atributo `key` apontando para o
`field_schema`, que a extensão do editor renderiza como uma "pastilha"
visual (ex.: `[Nome do anfitrião]`) em vez de texto editável solto.

Isso significa que a arquitetura proposta não precisa de nenhum ajuste
para acomodar o Tiptap no futuro — `document_structure` PODE ser editado
por um Tiptap com uma extensão de nó de campo customizada, sem mudar o
formato de armazenamento. **Nada disso é implementado nesta etapa** —
nenhuma dependência de frontend foi adicionada; é uma verificação de que
o formato de dados escolhido não empurra o projeto para um beco sem
saída quando o editor visual chegar.

## 7. Estratégia de renderização recomendada

**Recomendo a abordagem híbrida** (PDF original como base + overlay para
as zonas variáveis) — e não por preferência isolada: é exatamente o que
já está registrado em `pdfengine/__init__.py` ("o PDF oficial NUNCA é
recriado em HTML/CSS... preservando o conteúdo original intacto") e em
`requirements/base.txt` (`pypdf` para "ler/fundir/achatar o PDF oficial",
`reportlab` para "gerar a camada de overlay com os dados variáveis",
`pypdfium2` para "rasterizar páginas para o editor visual de
mapeamento"). Este documento só torna essa decisão já existente precisa,
zona por zona:

1. **Elementos 100% fixos** (faixa da bandeira, logo IBZ, QR code, título,
   subtítulo, itens 1 e 3 da lista, os dois parágrafos jurídicos, bordas
   e rótulos da tabela, legenda "Signature de l'invitante") — ficam
   **intocados**, vindos diretamente da página do PDF oficial. Máxima
   fidelidade possível, porque é literalmente o arquivo original.

2. **Valores 100% isolados** (as 4 células de valor simples da tabela,
   o nome sob a linha de assinatura) — a região correspondente na página
   original (que hoje contém o valor de AMOSTRA) é coberta por um
   retângulo branco, e o valor real é desenhado por cima com
   `reportlab`, no mesmo estilo (fonte/tamanho/peso) documentado na
   seção 4. Simples: não precisa reconstruir nenhuma frase.

3. **As quatro zonas mistas** (seção 3) — a região é coberta da mesma
   forma, e o **parágrafo inteiro** (fixo + variável entrelaçados) é
   redesenhado a partir do `document_structure`, respeitando negrito por
   trecho (conforme a tabela da seção 3.1) e a quebra de linha do
   original. É o único ponto que exige alguma "reconstrução", e é
   deliberadamente limitado a essas quatro zonas — não ao documento
   inteiro.

**Por que não reconstrução total:** recriar a página inteira em
`reportlab` (ou HTML→PDF) arriscaria não reproduzir com exatidão a
faixa da bandeira, o logo oficial e o QR Code — exatamente os elementos
em que "parecer errado" é mais visível e mais grave (são os elementos de
autenticidade/oficialidade do documento). A abordagem híbrida garante que
esses elementos sejam **pixel-idênticos ao original em qualquer idioma**,
já que só o texto (que muda por natureza) é redesenhado.

## 8. Riscos e pontos que precisam de validação

1. **[CRÍTICO] Conteúdo do QR Code desconhecido.** Não é possível
   decodificá-lo a partir da imagem fornecida. Precisa de confirmação do
   cliente: é um QR estático (mesmo em toda carta, ex. link institucional
   do IBZ) ou dinâmico (codifica a referência/UUID da Letter para
   verificação)? Isso muda inteiramente a implementação (asset fixo vs.
   geração por carta).
2. **Assinatura física vs. eletrônica.** O modelo mostra uma linha em
   branco para assinatura manuscrita após impressão — a suposição de
   trabalho é que o sistema gera o documento para impressão e assinatura
   física, sem assinatura eletrônica embutida. Confirmar antes de
   avançar.
3. **`host_birth` (data de nascimento do anfitrião) não é coletada hoje.**
   É o único campo genuinamente novo identificado. Precisa de decisão:
   adicionar ao `field_schema` da etapa "Anfitrião" (mudança pequena e
   já prevista pela arquitetura da Fase 3) ou confirmar se deve vir de
   outro lugar.
4. **Todos os valores binários deste documento (versão do PDF, AcroForm,
   fontes incorporadas, coordenadas exatas em pt, se a faixa/logo/QR são
   vetor ou raster) são hipóteses visuais, não medições.** Antes de
   escrever qualquer código de renderização, é indispensável rodar, com
   o arquivo em disco:
   ```python
   from pypdf import PdfReader
   reader = PdfReader("caminho/Modelo-Carta-Convite-FR.pdf")
   print(reader.pdf_header, len(reader.pages), reader.pages[0].mediabox)
   print(reader.get_fields())  # None ou {} => sem AcroForm
   print(reader.pages[0]["/Resources"].get("/Font"))
   ```
   e, para coordenadas exatas por trecho de texto,
   `pdfplumber` (`page.extract_words()`/`page.chars()`, que devolve
   `x0`/`x1`/`top`/`bottom`/`fontname`/`size` por caractere) — isso
   resolve de uma vez toda a coluna "coordenada aproximada" da seção 4
   com números reais, em vez de estimativa visual.
5. ~~**`place` = cidade do usuário é uma hipótese, não uma regra
   confirmada pelo cliente.**~~ **RESOLVIDO na Etapa 3** (decisão de
   negócio do cliente): o local do fecho é, por definição, a cidade de
   residência de quem emite a carta — `User.city`, que já existia como
   campo estruturado. Não é um campo do formulário, não entra no
   `field_schema`, não é perguntado ao usuário e **nunca** é deduzido do
   texto do endereço. É congelado em `snapshot["host"]["city"]` no
   fechamento, e é de lá que a geração o lê (nunca do perfil atual). Sem
   cidade, a carta não é finalizada — ver
   `services.missing_host_profile_fields` e `MissingHostCityError`.
6. **Concordância gramatical de nacionalidade.** `host_nationality`
   aparece no documento como adjetivo minúsculo ("belge"); a nacionalidade
   do convidado aparece na tabela como substantivo maiúsculo
   ("Brésilienne"). Como ambos são campos de texto livre (decisão já
   tomada na Fase 3, por não haver lista de países aprovada), a
   responsabilidade de digitar na forma gramatical certa continua sendo
   do usuário — vale um texto de ajuda (`help_text`) explícito quando
   esses campos forem usados na geração real.
7. **Divergência entre o texto jurídico do wizard (Fase 3) e o texto
   real impresso no PDF.** Os dois avisos que o usuário aceita hoje no
   wizard (`notice_informal`, `notice_prise_en_charge`) têm redação
   diferente dos dois parágrafos jurídicos reais deste PDF. Isso não é
   corrigido nesta etapa (instrução explícita: não alterar o wizard, não
   traduzir/inventar texto jurídico) — fica registrado para quando o
   cliente fornecer/validar o texto oficial definitivo, momento em que
   os dois devem ser reconciliados (idealmente, o aviso do wizard deveria
   ser a tradução fiel do parágrafo que realmente sai impresso).
8. **PT/NL/EN**: nenhum documento oficial equivalente foi fornecido.
   A arquitetura (um `document_structure`/`assets` por
   `LetterTemplate`/idioma, já estabelecido na Fase 3) suporta os quatro
   idiomas sem mudança estrutural, mas nenhum conteúdo foi produzido para
   os outros três — não seria apropriado inventar.

## 9. O que NÃO foi alterado nesta etapa

Nenhum modelo, migração, view, template do wizard, dashboard ou
dependência foi tocado. Este documento e a pasta que o contém
(`pdfengine/docs/`) são a única adição.
