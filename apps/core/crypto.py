"""
Cifra de segredos guardados no banco.

Existe por causa de UM caso: a senha SMTP que um administrador cadastra
pelo Backoffice. O sistema precisa dela em texto puro na hora de abrir a
conexão -- não dá para guardar um hash, como se faz com senha de
usuário, porque ninguém vai "conferir" essa senha: ela é REAPRESENTADA
ao servidor de e-mail.

O QUE ISTO PROTEGE, E O QUE NÃO PROTEGE
---------------------------------------
Protege contra vazamento do BANCO: um dump, um backup esquecido, um
`SELECT` de quem tem acesso de leitura. A chave não mora no banco --
vem do ambiente (`.env`) -- então quem tem só as linhas não tem a senha.

NÃO protege contra quem já tem o servidor: com o código e o `.env` na
mão, decifra-se tudo. Não existe forma de um programa guardar um
segredo de si mesmo. A proteção certa para esse caso é o acesso ao
servidor, não a criptografia.

A CHAVE
-------
`EMAIL_SECRET_KEY` se estiver definida; senão, derivada da `SECRET_KEY`
por HKDF-SHA256. HKDF e não PBKDF2 de propósito: a entrada já é um
segredo de alta entropia, não uma senha humana -- não há o que
"endurecer" com iterações, só o que derivar.

Trocar a chave (ou a `SECRET_KEY`, quando não há a específica) torna o
que está guardado ilegível. Não é perda de dado: `decifrar()` devolve
`None`, a tela avisa que a senha precisa ser cadastrada de novo, e o
administrador digita outra. É por isso que nada aqui levanta exceção
por valor ilegível.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

# Separa esta chave derivada de qualquer outra que venha a sair da mesma
# SECRET_KEY. O `v1` é o que permite trocar o esquema um dia sem que os
# valores antigos passem a decifrar em silêncio com a chave nova.
_INFO = b"desenrola.core.segredos.v1"


def _chave():
    """A chave Fernet (32 bytes em base64url) derivada do ambiente."""
    base = getattr(settings, "EMAIL_SECRET_KEY", "") or settings.SECRET_KEY
    derivada = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO
    ).derive(base.encode())
    return base64.urlsafe_b64encode(derivada)


def cifrar(texto):
    """
    O texto cifrado, pronto para guardar. Vazio continua vazio -- "não
    há senha" é um estado legítimo, e cifrar o nada só criaria um valor
    que parece senha.
    """
    if not texto:
        return ""
    return Fernet(_chave()).encrypt(texto.encode()).decode()


def decifrar(guardado):
    """
    O texto original, ou `None` quando não dá para ler.

    `None` cobre chave trocada, valor corrompido e lixo que nunca foi
    cifrado. Quem chama trata os três do mesmo jeito -- "não tenho a
    senha" -- e o erro nunca carrega o valor consigo: uma exceção com o
    conteúdo dentro acabaria num log.
    """
    if not guardado:
        return None
    try:
        return Fernet(_chave()).decrypt(guardado.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return None
