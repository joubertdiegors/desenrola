"""
Leitor de QR Code mínimo, para os testes.

Por que existe: validar o QR Code do documento exige LER o código do PDF
final, não só conferir que a imagem continua lá. Nenhuma biblioteca de
leitura (pyzbar, OpenCV, zxing) está instalada, e trazer uma delas só
para um teste seria desproporcional -- OpenCV sozinho pesa mais que todo
o resto das dependências do projeto.

O escopo aqui é deliberadamente pequeno: o código que precisamos ler é
fixo, conhecido e não está danificado (vem intacto do PDF oficial).
Então este leitor não faz correção de erros Reed-Solomon: ele lê a grade,
tira a máscara, desintercala os blocos e interpreta os dados. Se o código
estivesse corrompido, o resultado sairia errado ou levantaria erro -- que
é exatamente o que o teste quer detectar.

Não é uma biblioteca de uso geral: cobre o que este documento usa
(versão 5, modo byte) e recusa explicitamente o resto.
"""

# Quantos codewords de dados tem cada bloco, por (versão, nível de correção).
# Só as entradas que precisamos; o resto é recusado com mensagem clara.
_BLOCOS = {
    (5, "L"): [108],
    (5, "M"): [43, 43],
    (5, "Q"): [15, 15, 16, 16],
    (5, "H"): [11, 11, 12, 12],
}

_NIVEL_EC = {0b01: "L", 0b00: "M", 0b11: "Q", 0b10: "H"}

# Posição de cada bit da informação de formato (bit 14 = mais significativo).
_POS_FORMATO = {
    14: (8, 0), 13: (8, 1), 12: (8, 2), 11: (8, 3), 10: (8, 4), 9: (8, 5),
    8: (8, 7), 7: (8, 8), 6: (7, 8),
    5: (5, 8), 4: (4, 8), 3: (3, 8), 2: (2, 8), 1: (1, 8), 0: (0, 8),
}

_MASCARAS = {
    0: lambda i, j: (i + j) % 2 == 0,
    1: lambda i, j: i % 2 == 0,
    2: lambda i, j: j % 3 == 0,
    3: lambda i, j: (i + j) % 3 == 0,
    4: lambda i, j: (i // 2 + j // 3) % 2 == 0,
    5: lambda i, j: (i * j) % 2 + (i * j) % 3 == 0,
    6: lambda i, j: ((i * j) % 2 + (i * j) % 3) % 2 == 0,
    7: lambda i, j: ((i + j) % 2 + (i * j) % 3) % 2 == 0,
}

# Coordenadas dos centros dos padrões de alinhamento, por versão.
_ALINHAMENTO = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}


class QRDecodeError(Exception):
    """O QR Code não pôde ser lido."""


def _recortar_codigo(imagem):
    """Tira a margem branca em volta e devolve (pixels, caixa) do código."""
    cinza = imagem.convert("L")
    px = cinza.load()
    largura, altura = cinza.size

    def escuro(x, y):
        return px[x, y] < 128

    colunas = [x for x in range(largura) if any(escuro(x, y) for y in range(altura))]
    linhas = [y for y in range(altura) if any(escuro(x, y) for x in range(largura))]
    if not colunas or not linhas:
        raise QRDecodeError("não há nada escuro na imagem: o QR Code sumiu")
    return escuro, (colunas[0], linhas[0], colunas[-1], linhas[-1])


def _tamanho_do_modulo(escuro, caixa):
    """
    Descobre quantos módulos o código tem pelo olho superior esquerdo: a
    barra de cima dele tem exatamente 7 módulos de largura.
    """
    x0, y0, x1, y1 = caixa
    lado = ((x1 - x0 + 1) + (y1 - y0 + 1)) / 2
    y = y0 + max(1, int(lado * 0.02))
    largura_olho = 0
    x = x0
    while x <= x1 and escuro(x, y):
        largura_olho += 1
        x += 1
    if largura_olho < 7:
        raise QRDecodeError("o padrão localizador (olho) do QR Code não foi encontrado")
    modulo = largura_olho / 7
    n = round(lado / modulo)
    if n < 21 or (n - 21) % 4:
        raise QRDecodeError(f"{n} módulos por lado não é um tamanho de QR Code válido")
    return n


def _amostrar_grade(escuro, caixa, n):
    x0, y0, x1, y1 = caixa
    largura = (x1 - x0 + 1) / n
    altura = (y1 - y0 + 1) / n
    return [
        [escuro(int(x0 + (c + 0.5) * largura), int(y0 + (r + 0.5) * altura)) for c in range(n)]
        for r in range(n)
    ]


def _conferir_padroes_fixos(grade, n):
    olho = [
        [1, 1, 1, 1, 1, 1, 1],
        [1, 0, 0, 0, 0, 0, 1],
        [1, 0, 1, 1, 1, 0, 1],
        [1, 0, 1, 1, 1, 0, 1],
        [1, 0, 1, 1, 1, 0, 1],
        [1, 0, 0, 0, 0, 0, 1],
        [1, 1, 1, 1, 1, 1, 1],
    ]
    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
        for i in range(7):
            for j in range(7):
                if grade[r0 + i][c0 + j] != bool(olho[i][j]):
                    raise QRDecodeError(
                        f"padrão localizador em ({r0},{c0}) está danificado"
                    )
    if not all(grade[6][c] == (c % 2 == 0) for c in range(8, n - 8)):
        raise QRDecodeError("o padrão de sincronismo (timing) está danificado")


def _ler_formato(grade):
    bruto = 0
    for bit, (r, c) in _POS_FORMATO.items():
        if grade[r][c]:
            bruto |= 1 << bit
    valor = bruto ^ 0x5412
    nivel = _NIVEL_EC[(valor >> 13) & 0b11]
    mascara = (valor >> 10) & 0b111
    return nivel, mascara


def _mapa_reservado(n, versao):
    reservado = [[False] * n for _ in range(n)]

    def marcar(r0, c0, r1, c1):
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                reservado[r][c] = True

    marcar(0, 0, 8, 8)              # olho + separador + formato (sup. esq.)
    marcar(0, n - 8, 8, n - 1)      # olho + formato (sup. dir.)
    marcar(n - 8, 0, n - 1, 8)      # olho + formato (inf. esq.)
    for c in range(n):
        reservado[6][c] = True      # sincronismo horizontal
    for r in range(n):
        reservado[r][6] = True      # sincronismo vertical
    reservado[n - 8][8] = True      # módulo sempre escuro

    centros = _ALINHAMENTO.get(versao, [])
    for r in centros:
        for c in centros:
            # os que ficariam por cima dos olhos não existem
            if (r, c) in ((6, 6), (6, centros[-1]), (centros[-1], 6)):
                continue
            marcar(r - 2, c - 2, r + 2, c + 2)
    return reservado


def _ler_bits(grade, reservado, n, mascara):
    aplica = _MASCARAS[mascara]
    bits = []
    coluna = n - 1
    subindo = True
    while coluna > 0:
        if coluna == 6:
            coluna -= 1
        for i in range(n):
            linha = (n - 1 - i) if subindo else i
            for c in (coluna, coluna - 1):
                if not reservado[linha][c]:
                    valor = grade[linha][c]
                    if aplica(linha, c):
                        valor = not valor
                    bits.append(1 if valor else 0)
        subindo = not subindo
        coluna -= 2
    return bits


def _desintercalar(codewords, tamanhos):
    blocos = [[] for _ in tamanhos]
    i = 0
    for k in range(max(tamanhos)):
        for b, tamanho in enumerate(tamanhos):
            if k < tamanho:
                blocos[b].append(codewords[i])
                i += 1
    return [cw for bloco in blocos for cw in bloco]


def decode_qr(imagem) -> str:
    """
    Lê o QR Code de uma imagem PIL e devolve o texto. Levanta
    `QRDecodeError` se a grade estiver danificada ou se o conteúdo não
    for texto em modo byte.
    """
    escuro, caixa = _recortar_codigo(imagem)
    n = _tamanho_do_modulo(escuro, caixa)
    versao = (n - 17) // 4
    grade = _amostrar_grade(escuro, caixa, n)
    _conferir_padroes_fixos(grade, n)

    nivel, mascara = _ler_formato(grade)
    tamanhos = _BLOCOS.get((versao, nivel))
    if tamanhos is None:
        raise QRDecodeError(
            f"versão {versao} nível {nivel}: este leitor mínimo só conhece "
            f"as combinações {sorted(_BLOCOS)}"
        )

    bits = _ler_bits(grade, _mapa_reservado(n, versao), n, mascara)
    codewords = [
        int("".join(map(str, bits[i : i + 8])), 2) for i in range(0, len(bits) - 7, 8)
    ]
    dados = _desintercalar(codewords, tamanhos)

    fluxo = "".join(f"{c:08b}" for c in dados)
    modo = int(fluxo[:4], 2)
    if modo != 0b0100:
        raise QRDecodeError(f"modo {modo:04b} não suportado (só modo byte)")
    comprimento = int(fluxo[4:12], 2)
    if comprimento * 8 + 12 > len(fluxo):
        raise QRDecodeError("comprimento declarado maior que os dados disponíveis")

    conteudo = bytes(
        int(fluxo[12 + 8 * i : 20 + 8 * i], 2) for i in range(comprimento)
    )
    try:
        return conteudo.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise QRDecodeError(f"o conteúdo lido não é UTF-8 válido: {exc}") from exc
