"""Les bras du banc, et les temoins qui disent si le banc mesure quoi que ce soit.

Un bras est une fonction : on lui montre la chronologie, puis on lui pose les
questions dans l'ordre. Les bras reels (modele nu, historique complet, RAG,
couche Dermioz) branchent un fournisseur ; les trois temoins ci-dessous n'en
branchent aucun et servent a calibrer le harnais AVANT de depenser un jeton.

Regle du jour zero : si les trois temoins ne se distinguent pas, le banc ne
mesure rien, et aucun chiffre produit par les bras reels ne vaut d'etre lu.
"""

from __future__ import annotations

import random
from typing import Protocol, Sequence

from .corpus import STALE_AFTER_DAYS, Fact, Statement, candidates
from .scoring import Answer


class Arm(Protocol):
    """Un systeme de memoire soumis au banc."""

    name: str

    def observe(self, timeline: Sequence[Statement]) -> None:
        """Recoit la chronologie, du plus ancien au plus recent."""

    def ask(self, subject: str, relation: str) -> Answer:
        """Rend l'objet, ou `Answer(None)` pour refuser."""


class NullArm:
    """Ne repond jamais.

    Doit produire une couverture de 0 et une precision NON MESUREE. S'il
    decroche une precision de 1.0, le harnais recompense le silence et tout le
    reste du banc est faux.
    """

    name = "temoin: muet"

    def observe(self, timeline: Sequence[Statement]) -> None:
        return None

    def ask(self, subject: str, relation: str) -> Answer:
        return Answer(None)


class GuessArm:
    """Repond toujours, au hasard, parmi les objets plausibles.

    Doit produire une couverture de 1.0, une precision proche du hasard, et
    une hallucination de 1.0 sur la classe ABSENCE. C'est la ligne de base
    qu'un bras reel doit battre pour avoir dit quelque chose.
    """

    name = "temoin: devine"

    def __init__(self, pool: Sequence[str], seed: int = 0) -> None:
        self._pool = list(pool)
        self._rng = random.Random(seed)

    def observe(self, timeline: Sequence[Statement]) -> None:
        return None

    def ask(self, subject: str, relation: str) -> Answer:
        return Answer(self._rng.choice(self._pool))


class OracleArm:
    """Connait le corpus et se comporte parfaitement.

    Repond juste sur tout ce qui a ete dit, date ce qui est vieux, et refuse
    ce qui n'a jamais ete dit. C'est le plafond : aucun bras reel ne doit le
    depasser, et s'il le depasse c'est le harnais qui fuit.
    """

    name = "temoin: oracle"

    def __init__(self, facts: Sequence[Fact],
                 stale_after_days: int = STALE_AFTER_DAYS) -> None:
        self._truth = {(f.subject, f.relation): f for f in facts}
        self._stale_after = stale_after_days

    def observe(self, timeline: Sequence[Statement]) -> None:
        return None

    def ask(self, subject: str, relation: str) -> Answer:
        fact = self._truth.get((subject, relation))
        if fact is None or fact.truth is None:
            return Answer(None)
        age = fact.age_days() or 0
        return Answer(fact.truth, stale_flagged=age > self._stale_after)


class MajorityArm:
    """Repond toujours l'objet le plus frequent du corpus.

    La ligne de base TRIVIALE, celle qu'un banc doit exiger qu'on batte avant
    de parler de memoire. Battre l'oracle est impossible et battre le hasard
    ne prouve presque rien ; ne pas battre celle-ci prouve qu'on n'a rien.
    """

    name = "base: majoritaire"

    def __init__(self, timeline_: Sequence[Statement]) -> None:
        counts: dict[str, int] = {}
        for s in timeline_:
            counts[s.obj] = counts.get(s.obj, 0) + 1
        self._top = max(counts, key=lambda k: (counts[k], k)) if counts else None

    def observe(self, timeline: Sequence[Statement]) -> None:
        return None

    def ask(self, subject: str, relation: str) -> Answer:
        return Answer(self._top)


class ScrambledMemory:
    """Un bras reel, mais nourri d'une chronologie MELANGEE.

    Le controle de raccourci. On garde le systeme, on detruit l'information :
    les objets sont redistribues au hasard entre les paires (sujet, relation).
    Si le score tient quand meme, les questions sont repondables sans memoire
    et le banc mesure autre chose que ce qu'il annonce.

    C'est l'equivalent, au niveau de la TACHE, des trois temoins du jour zero
    qui ne valident que le harnais.
    """

    def __init__(self, inner, seed: int = 0) -> None:
        self._inner = inner
        self._seed = seed
        self.name = inner.name + " [chronologie melangee]"

    def observe(self, timeline: Sequence[Statement]) -> None:
        rng = random.Random(self._seed)
        objs = [s.obj for s in timeline]
        rng.shuffle(objs)
        self._inner.observe([
            Statement(s.when, s.subject, s.relation, o)
            for s, o in zip(timeline, objs)
        ])

    def ask(self, subject: str, relation: str) -> Answer:
        return self._inner.ask(subject, relation)


def witnesses(facts: Sequence[Fact], seed: int = 0) -> list[Arm]:
    """Les trois temoins, prets a passer le banc."""
    return [NullArm(), GuessArm(candidates(list(facts)), seed), OracleArm(facts)]


def run(arm: Arm, facts: Sequence[Fact],
        timeline_: Sequence[Statement]) -> list[Answer]:
    """Montre la chronologie au bras, puis pose les questions dans l'ordre."""
    arm.observe(timeline_)
    return [arm.ask(f.subject, f.relation) for f in facts]
