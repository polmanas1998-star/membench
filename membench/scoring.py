"""Ce que le banc compte, et ce qu'il refuse de conclure.

Une seule regle gouverne ce fichier : **un instrument muet ne conclut pas.**
Une precision calculee sur zero reponse vaut `None`, jamais 1.0. C'est le
piege exact qui fait qu'un systeme qui ne repond a rien decroche un sans
faute, et c'est la premiere chose que les temoins du jour zero verifient.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .corpus import Fact

# Le plafond du produit, en jetons par minute et par bucket. Sert a convertir
# un cout en jetons par tour en un debit, qui est la grandeur qui decide.
TPM_CEILING = 8000


@dataclass(frozen=True)
class Answer:
    """Ce qu'un bras rend pour une question.

    `value is None` veut dire REFUS, et le refus est une bonne reponse sur la
    classe ABSENCE. `stale_flagged` dit si le bras a assorti sa reponse d'une
    reserve sur son age.
    """

    value: str | None
    stale_flagged: bool = False
    prompt_tokens: int = 0
    #: Vrai quand le bras n'a rien rendu d'exploitable, par opposition a un
    #: UNKNOWN assume. Sans cette distinction, une reponse tronquee compte
    #: comme une abstention calibree et le banc recompense une panne.
    malformed: bool = False

    @property
    def answered(self) -> bool:
        return self.value is not None


def _ratio(num: int, den: int) -> float | None:
    """Aucun ratio sans denominateur. `None` se lit « non mesure »."""
    return num / den if den else None


@dataclass(frozen=True)
class Report:
    asked: int
    answered: int
    correct: int
    # Par classe
    retention_ok: int
    retention_n: int
    stale_returned: int          # a rendu la valeur PERIMEE : le pire cas
    supersession_n: int
    age_flagged: int
    age_answered: int
    age_n: int
    malformed: int               # reponses illisibles, PAS des refus
    expired_ok: int              # retrouve au-dela du seuil d'oubli
    expired_n: int
    hallucinated: int            # a repondu sur un fait jamais dit
    absence_n: int
    prompt_tokens_total: int

    @property
    def coverage(self) -> float | None:
        return _ratio(self.answered, self.asked)

    @property
    def gated_precision(self) -> float | None:
        """Justesse SUR CE QUI A ETE REPONDU. `None` si le bras s'est tu."""
        return _ratio(self.correct, self.answered)

    @property
    def retention(self) -> float | None:
        return _ratio(self.retention_ok, self.retention_n)

    @property
    def supersession_error(self) -> float | None:
        """Part des faits mis a jour rendus dans leur version perimee.

        Une erreur d'un autre genre que « je ne sais pas » : le systeme est
        confiant et faux, et rien dans sa reponse ne le signale.
        """
        return _ratio(self.stale_returned, self.supersession_n)

    @property
    def age_awareness(self) -> float | None:
        """Part des vieux faits REPONDUS assortis d'une reserve sur l'age.

        Denominateur volontairement `age_answered` et non `age_n` : un bras
        qui refuse un vieux fait n'a pas a le dater, et le compter contre lui
        confondrait deux vertus differentes.
        """
        return _ratio(self.age_flagged, self.age_answered)

    @property
    def malformed_rate(self) -> float | None:
        """Part des tours ou le bras n'a rien rendu de lisible.

        A publier a cote de la couverture, toujours. Une reponse vide se lit
        comme une abstention, donc un bras casse ressemble a un bras prudent.
        C'est arrive ici le 05/09 : `max_tokens=48` sur un modele a
        raisonnement rendait 48 jetons de reflexion et zero caractere, et les
        trois bras modele affichaient une hallucination de 0,000.
        """
        return _ratio(self.malformed, self.asked)

    @property
    def deep_retention(self) -> float | None:
        """Part des faits AU-DELA du seuil d'oubli encore rendus, et justes.

        La colonne ou une memoire qui decroit perd contre un contexte complet,
        qui garde le texte quel que soit son age. Elle est publiee pour cette
        raison : un banc dont toutes les colonnes vont dans le meme sens ne
        mesure pas, il plaide.
        """
        return _ratio(self.expired_ok, self.expired_n)

    @property
    def hallucination(self) -> float | None:
        """Part des faits jamais dits sur lesquels le bras a quand meme repondu."""
        return _ratio(self.hallucinated, self.absence_n)

    @property
    def tokens_per_turn(self) -> float | None:
        return _ratio(self.prompt_tokens_total, self.asked)

    @property
    def turns_per_minute(self) -> float | None:
        tpt = self.tokens_per_turn
        if not tpt:
            return None
        return TPM_CEILING / tpt

    def as_row(self) -> dict[str, float | None | int]:
        return {
            "asked": self.asked,
            "coverage": self.coverage,
            "malformed_rate": self.malformed_rate,
            "gated_precision": self.gated_precision,
            "retention": self.retention,
            "supersession_error": self.supersession_error,
            "age_awareness": self.age_awareness,
            "deep_retention": self.deep_retention,
            "hallucination": self.hallucination,
            "tokens_per_turn": self.tokens_per_turn,
            "turns_per_minute": self.turns_per_minute,
        }


def score(facts: Sequence[Fact], answers: Sequence[Answer]) -> Report:
    """Confronte les reponses d'un bras a la verite du corpus.

    `facts` et `answers` sont apparies par position, dans l'ordre ou les
    questions ont ete posees.
    """
    if len(facts) != len(answers):
        raise ValueError(
            f"{len(facts)} questions posees pour {len(answers)} reponses : "
            "le banc ne peut pas apparier"
        )

    asked = answered = correct = 0
    retention_ok = retention_n = 0
    stale_returned = supersession_n = 0
    age_flagged = age_answered = age_n = 0
    malformed = 0
    expired_ok = expired_n = 0
    hallucinated = absence_n = 0
    tokens = 0

    for fact, ans in zip(facts, answers):
        asked += 1
        tokens += ans.prompt_tokens
        malformed += ans.malformed
        truth = fact.truth

        if ans.answered:
            answered += 1
        # La bonne reponse sur un fait jamais dit est le SILENCE.
        if truth is None:
            absence_n += 1
            if ans.answered:
                hallucinated += 1
            # Un refus juste ne gonfle PAS `correct` : il n'entre ni au
            # numerateur ni au denominateur de la precision gardee, sinon se
            # taire partout donnerait un sans faute.
            continue

        if ans.answered and ans.value == truth:
            correct += 1

        if fact.kind in ("stable", "reinforced"):
            retention_n += 1
            if ans.answered and ans.value == truth:
                retention_ok += 1
        elif fact.kind == "superseded":
            supersession_n += 1
            if ans.answered and ans.value == fact.superseded:
                stale_returned += 1
        elif fact.kind == "faded":
            age_n += 1
            if ans.answered:
                age_answered += 1
                if ans.stale_flagged:
                    age_flagged += 1
        elif fact.kind == "expired":
            expired_n += 1
            if ans.answered and ans.value == truth:
                expired_ok += 1

    return Report(
        asked=asked, answered=answered, correct=correct,
        retention_ok=retention_ok, retention_n=retention_n,
        stale_returned=stale_returned, supersession_n=supersession_n,
        age_flagged=age_flagged, age_answered=age_answered, age_n=age_n,
        malformed=malformed, expired_ok=expired_ok, expired_n=expired_n,
        hallucinated=hallucinated, absence_n=absence_n,
        prompt_tokens_total=tokens,
    )
