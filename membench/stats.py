"""Un intervalle sur l'ECART, parce que deux medianes cote a cote n'en sont pas un.

Publier « 1,000 contre 0,043 » laisse au lecteur le travail de decider si
l'ecart tient. Le bootstrap APPARIE le fait a sa place : les bras repondent aux
MEMES questions, donc on retire les questions au sort, on recalcule l'ecart sur
chaque tirage, et on lit la bande.

Deux niveaux, et il faut dire lequel on cite :

  question   des milliers de tirages, bande etroite, mais traite les questions
             d'un meme corpus comme independantes, ce qu'elles ne sont pas tout
             a fait.
  graine     l'unite vraiment independante, mais 5 a 8 valeurs seulement, donc
             une bande large et honnete.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Sequence

from .corpus import Fact
from .scoring import Answer


@dataclass(frozen=True)
class Interval:
    point: float
    lo: float
    hi: float
    dropped: int  # tirages ou la metrique etait indefinie pour un des bras

    def __str__(self) -> str:
        return f"{self.point:+.3f} [{self.lo:+.3f}, {self.hi:+.3f}]"

    @property
    def excludes_zero(self) -> bool:
        """Vrai si la bande entiere est d'un cote de zero, zero exclu.

        La premiere version comparait les signes des deux bornes. Elle rendait
        VRAI pour une bande [0, 0], donc elle declarait significatif un ecart
        exactement nul, ce qui est le pire faux positif possible pour ce
        fichier : il valide toutes les conclusions qu'on lui soumet.
        Trouve par un test qui compare un bras a lui-meme, le 05/09.
        """
        return self.lo > 0 or self.hi < 0


def gated_precision(facts: Sequence[Fact], answers: Sequence[Answer]) -> float | None:
    ans = [(f, a) for f, a in zip(facts, answers) if a.answered]
    if not ans:
        return None
    return sum(1 for f, a in ans if a.value == f.truth) / len(ans)


def coverage(facts: Sequence[Fact], answers: Sequence[Answer]) -> float | None:
    return len(answers) and sum(1 for a in answers if a.answered) / len(answers)


def paired_bootstrap(facts: Sequence[Fact],
                     left: Sequence[Answer], right: Sequence[Answer],
                     metric: Callable = gated_precision,
                     draws: int = 4000, seed: int = 0,
                     alpha: float = 0.05) -> Interval:
    """Bande sur `metric(left) - metric(right)`, questions retirees au sort.

    Apparie : chaque tirage prend le MEME jeu d'indices pour les deux bras,
    donc la variance due au choix des questions se soustrait au lieu de
    s'ajouter. Un bootstrap non apparie sur deux bras qui repondent aux memes
    questions surestime la largeur, parfois du double.
    """
    if not (len(facts) == len(left) == len(right)):
        raise ValueError("bras non apparies : longueurs differentes")
    rng = random.Random(seed)
    n = len(facts)
    diffs: list[float] = []
    dropped = 0
    for _ in range(draws):
        idx = [rng.randrange(n) for _ in range(n)]
        f = [facts[i] for i in idx]
        a, b = metric(f, [left[i] for i in idx]), metric(f, [right[i] for i in idx])
        if a is None or b is None:
            dropped += 1
            continue
        diffs.append(a - b)
    if not diffs:
        raise ValueError("aucun tirage exploitable : la metrique est indefinie partout")
    diffs.sort()
    lo = diffs[int(alpha / 2 * len(diffs))]
    hi = diffs[min(len(diffs) - 1, int((1 - alpha / 2) * len(diffs)))]
    pt_l, pt_r = metric(facts, left), metric(facts, right)
    point = (pt_l - pt_r) if (pt_l is not None and pt_r is not None) else st_mid(diffs)
    return Interval(point, lo, hi, dropped)


def st_mid(xs: list[float]) -> float:
    return xs[len(xs) // 2]
