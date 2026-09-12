"""Erros do pdfengine. Nenhum depende do Django."""


class PdfEngineError(Exception):
    """Base de todos os erros deste pacote."""


class MissingSnapshotDataError(PdfEngineError):
    """
    Um campo obrigatorio para gerar o documento nao foi encontrado nos
    dados fornecidos. Nunca inventamos um valor no lugar -- quem chamou o
    renderer precisa resolver a ausencia antes de gerar o PDF.
    """


class TextOverflowError(PdfEngineError):
    """
    Um texto nao coube na area reservada do layout, mesmo depois de
    tentar reduzir a fonte ate o minimo permitido. Gerar o PDF mesmo
    assim produziria um documento com texto cortado ou sobreposto -- por
    isso isto interrompe a geracao em vez de seguir silenciosamente.
    """


class MissingHostCityError(MissingSnapshotDataError):
    """
    A cidade de residencia do anfitriao nao esta disponivel.

    O fechamento do documento ("Fait à <cidade>, le <data>") usa a cidade
    de residencia de quem emite a carta. Sem ela nao ha o que escrever --
    e as alternativas todas estariam erradas: deixar "Fait à , le ..."
    produz um documento oficial invalido; deduzir a cidade do endereco
    por parsing e um palpite (o formato do endereco varia por pais e por
    como a pessoa digitou); e usar uma cidade generica seria inventar um
    dado juridico. Entao isto interrompe a geracao.
    """


class BasePdfUnavailableError(PdfEngineError):
    """
    O PDF oficial que serve de base/background nao pode ser lido --
    arquivo ausente, ilegivel ou corrompido. Sem ele nao existe documento
    a gerar: todo o conteudo fixo (titulo, textos juridicos, tabela,
    bandeira, logo IBZ, QR Code) vem dele.
    """


class UnrenderableCharacterError(PdfEngineError):
    """
    O texto tem um caractere que a fonte embutida nao sabe desenhar.

    Sem esta checagem o PDF sairia mesmo assim: o reportlab desenha um
    glifo vazio no lugar e nao avisa nada -- um documento oficial errado,
    gerado em silencio. Melhor interromper e dizer qual e o caractere.
    """
