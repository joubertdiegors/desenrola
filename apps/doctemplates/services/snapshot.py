"""
Snapshot estrutural de um `DocumentTemplate` (Etapa 3.5.1).

Congela, num dicionario JSON-serializavel, tudo que o renderer generico
(`services/pdf/`) precisa para reproduzir o documento: `field_schema`,
`layout`, a pagina do tipo de documento e o idioma -- mais os metadados
que identificam de onde veio (id, slug, nome, linhagem).

QUEM CONSOME ISTO
-----------------
Hoje, `apps.letters.services.capture_document_template_snapshot()`, na
finalizacao de uma `Letter`. O modulo em si nao sabe nada sobre cartas --
so sobre `DocumentTemplate` -- para a direcao de dependencia continuar
`letters -> doctemplates`, nunca o contrario.

NAO E UMA SEGUNDA ARQUITETURA DE MODELOS
-----------------------------------------
Isto nao guarda o modelo de novo em lugar nenhum; e uma COPIA CONGELADA,
de uso de quem precisar reproduzir o documento historicamente. O
`DocumentTemplate` continua sendo a unica fonte editavel -- alterar um
modelo depois de um snapshot tirado NUNCA alcanca o snapshot.

HASH DETERMINISTICO
--------------------
`compute_hash()` serializa o snapshot em JSON CANONICO (chaves
ordenadas, separadores compactos) antes do SHA-256. Duas montagens do
MESMO conteudo -- em qualquer ordem de insercao de chave, em qualquer
nivel de aninhamento -- produzem o mesmo hash; qualquer diferenca no
conteudo estrutural produz um hash diferente.

`captured_at` fica de fora da conta (`CHAVES_FORA_DO_HASH`) de proposito:
ele documenta QUANDO o snapshot foi tirado, nao O QUE ele descreve.
Incluir um timestamp faria duas capturas do MESMO modelo, sem nenhuma
mudanca estrutural entre elas, produzirem hashes diferentes so por terem
acontecido em instantes diferentes -- o oposto do que um hash de
integridade estrutural serve para provar.
"""

import copy
import hashlib
import json

from django.utils import timezone

# Chaves do snapshot que descrevem QUANDO ele foi tirado, nao O QUE ele
# descreve -- ficam fora do hash estrutural (ver docstring do modulo).
CHAVES_FORA_DO_HASH = frozenset({"captured_at"})


def build_snapshot(document_template, *, captured_at=None):
    """
    O snapshot estrutural de `document_template`, pronto para gravar num
    JSONField.

    COPIA PROFUNDA: `field_schema`, `layout` e `type.page` sao
    dicionarios aninhados. `copy.deepcopy()` garante que o resultado nao
    compartilha nenhuma lista/dict de dentro deles com o registro
    original -- alterar o `DocumentTemplate` (ou o proprio dict em
    memoria que originou este snapshot) depois de chamar esta funcao
    nunca alcanca o que foi devolvido aqui.

    So LE `document_template` e `document_template.type`: nenhum dos
    dois e alterado ou salvo por esta funcao.
    """
    tipo = document_template.type
    return {
        "id": document_template.pk,
        "slug": document_template.slug,
        "name": document_template.name,
        "language": document_template.language,
        "is_system": document_template.is_system,
        "is_locked": document_template.is_locked,
        "duplicated_from_id": document_template.duplicated_from_id,
        "type": {
            "code": tipo.code,
            "name": tipo.name,
            # A pagina (largura/altura/unidade) e o que o renderer generico
            # espera como `pagina` -- ver `services/pdf/render_layout()`.
            "page": copy.deepcopy(tipo.page),
        },
        "field_schema": copy.deepcopy(document_template.field_schema),
        "layout": copy.deepcopy(document_template.layout),
        "captured_at": (captured_at or timezone.now()).isoformat(),
    }


def canonical_json(data):
    """
    JSON canonico: chaves ordenadas recursivamente, separadores
    compactos. Duas chamadas com o mesmo conteudo produzem sempre a
    MESMA string, nao importa em que ordem as chaves foram inseridas nos
    dicionarios de origem.
    """
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_hash(snapshot):
    """
    SHA-256 hexadecimal do conteudo ESTRUTURAL de `snapshot`.

    Deterministico: o mesmo conteudo sempre produz o mesmo hash,
    independente da ordem das chaves no dict recebido (`canonical_json`)
    e independente de quando foi tirado (`CHAVES_FORA_DO_HASH`).
    """
    estrutural = {
        chave: valor for chave, valor in snapshot.items() if chave not in CHAVES_FORA_DO_HASH
    }
    return hashlib.sha256(canonical_json(estrutural).encode("utf-8")).hexdigest()
