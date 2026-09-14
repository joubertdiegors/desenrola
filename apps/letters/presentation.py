"""
Apresentacao de Letters nas telas do usuario (dashboard e detalhe).

Existe para tirar da view a interpretacao de `Letter.data` / `Letter
.snapshot`: a view so pede os cartoes prontos e entrega ao template.

Regra de qual fonte usar, em uma linha: **carta fechada mostra o
snapshot; rascunho mostra o que esta preenchido agora**. O snapshot e a
copia congelada do que virou documento -- e o que a pessoa realmente
emitiu -- enquanto o rascunho ainda muda a cada etapa salva.

Nada aqui inventa dado: campo que nao existe vira vazio, e o template
decide como mostrar a ausencia.
"""

import datetime
from dataclasses import dataclass

from apps.letters import lifecycle, services
from apps.letters.models import Letter

# Quantas cartas o dashboard lista. O contador continua sendo o total.
RECENT_LIMIT = 5


def _as_date(value):
    """Converte a data guardada em JSON (texto ISO) para `date`. Devolve
    None se estiver ausente ou ilegivel -- nunca levanta."""
    if isinstance(value, datetime.date):
        return value
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        return None


def source_data(letter):
    """
    De onde vem o que a tela mostra: o snapshot congelado, se a carta ja
    foi fechada; senao, os dados do rascunho.

    A regra em si mora em `lifecycle.dados_da_carta` -- as politicas de
    prazo precisam da MESMA resposta que a tela, e duas copias da
    escolha acabariam divergindo.
    """
    return lifecycle.dados_da_carta(letter)


def resume_step(letter):
    """
    Em que etapa o rascunho deve ser retomado: a primeira que ainda nao
    esta valida; se ja estiver tudo valido, a revisao (ultima etapa).

    Deriva do mesmo `validate_all_steps` que o fechamento usa -- nao ha
    "etapa atual" guardada no banco, e nao criamos uma: qualquer campo
    editado depois mudaria o que essa coluna significaria.

    Devolve None para cartas que nao sao rascunho (nao ha o que retomar).
    """
    if letter.status != Letter.Status.DRAFT:
        return None
    invalida = services.validate_all_steps(letter)
    return invalida if invalida is not None else services.REVIEW_STEP


@dataclass(frozen=True)
class LetterCard:
    """
    Uma carta pronta para exibir. Guarda a Letter para o template
    chegar aos campos que ja sao diretos (uuid, reference, status...).

    O CICLO DE VIDA VEM CALCULADO
    -----------------------------
    `state`, `is_editable`, `is_expired` e os prazos sao resolvidos
    aqui, uma vez, por `apps.letters.lifecycle`. O template so escolhe
    o que mostrar -- nenhuma regra de prazo e recalculada em `{% if %}`,
    que e como a tela passaria a discordar do servidor.
    """

    letter: Letter
    guest_name: str
    arrival: datetime.date | None
    departure: datetime.date | None
    language_name: str
    resume_step: int | None
    has_pdf: bool
    state: str
    is_editable: bool
    editable_until: datetime.datetime | None
    expires_at: datetime.datetime | None

    # --- atalhos usados pelos templates -----------------------------------
    @property
    def uuid(self):
        return self.letter.uuid

    @property
    def reference(self):
        return self.letter.reference

    @property
    def status(self):
        return self.letter.status

    @property
    def status_label(self):
        return self.letter.get_status_display()

    @property
    def updated_at(self):
        return self.letter.updated_at

    @property
    def generated_at(self):
        return self.letter.generated_at

    @property
    def is_draft(self):
        return self.state == lifecycle.RASCUNHO

    @property
    def is_final(self):
        """Finalizada e ainda valida -- nao expirada."""
        return self.state == lifecycle.FINALIZADA

    @property
    def is_expired(self):
        return self.state == lifecycle.EXPIRADA

    @property
    def is_cancelled(self):
        return self.state == lifecycle.CANCELADA

    @property
    def is_generated(self):
        return self.letter.status == Letter.Status.GENERATED

    @property
    def can_download_pdf(self):
        """O dono consegue abrir o PDF agora? Expirada, nao."""
        return self.has_pdf and not self.is_expired

    @property
    def can_edit(self):
        """Mostra o botao de editar? So numa carta JA finalizada -- o
        rascunho tem o seu proprio botao, "Continuar"."""
        return self.is_editable and not self.is_draft

    @property
    def has_period(self):
        return bool(self.arrival and self.departure)


def build_card(letter, *, config=None) -> LetterCard:
    """
    Monta o cartao de uma Letter.

    `config` e a politica ja carregada: passe-a ao montar uma LISTA de
    cartoes, para o dashboard nao reler o mesmo registro uma vez por
    carta. Sozinha, a funcao busca por conta propria.
    """
    config = config or lifecycle.policy()
    dados = source_data(letter)
    idioma = services.LANGUAGE_META.get(letter.language) or {}
    return LetterCard(
        letter=letter,
        guest_name=(dados.get("guest_name") or "").strip(),
        arrival=_as_date(dados.get("stay_arrival")),
        departure=_as_date(dados.get("stay_departure")),
        language_name=idioma.get("name") or letter.get_language_display(),
        resume_step=resume_step(letter),
        has_pdf=bool(letter.pdf_file),
        state=lifecycle.letter_state(letter, config=config),
        is_editable=lifecycle.is_letter_editable(letter, config=config),
        editable_until=lifecycle.letter_editable_until(letter, config=config),
        expires_at=lifecycle.letter_expires_at(letter, config=config),
    )


def build_cards(letters) -> list[LetterCard]:
    """Varios cartoes lendo a politica UMA vez."""
    config = lifecycle.policy()
    return [build_card(letter, config=config) for letter in letters]


def own_letters(user):
    """
    As cartas DO usuario, da mais recentemente mexida para a mais antiga.

    Deliberadamente `filter(user=...)`, e nao `Letter.objects.visible_to()`:
    esta e a area pessoal, entao mesmo quem tem `letters.view_all_letters`
    ve aqui somente as proprias. Aquela permissao serve a uma tela de
    supervisao, que e outra coisa.
    """
    return (
        Letter.objects.filter(user=user)
        .select_related("document_template")
        .order_by("-updated_at")
    )


def recent_cards(user, limit=RECENT_LIMIT):
    """Os `limit` cartoes mais recentes do usuario."""
    return build_cards(own_letters(user)[:limit])
