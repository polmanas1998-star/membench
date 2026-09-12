"""LA DIAGONALE : trois ecritures et vingt ecritures sont la meme memoire.

D'OU VIENT CETTE QUESTION
-------------------------
Sous le fil r/LLMDevs du banc d'empoisonnement, Bright_Mix_773 a propose le test
le moins cher qui manquait : la diagonale des egalites, 1 contre 1, 2 contre 2,
3 contre 3, 4 contre 4. Si seule la masse compte, elle est plate.

Elle est plate. Mais pas pour la raison qu'on donnait tous les deux.

CE QUE LE BANC D'EMPOISONNEMENT NE DISAIT PAS
---------------------------------------------
`HolographicMemory.learn()` n'ajoute PAS une liaison quand le fait existe deja :
il monte son poids de `REINFORCE_STEP` (0,25) et plafonne a `MAX_WEIGHT` (1,5).

    1 ecriture   1,00
    2 ecritures  1,25
    3 ecritures  1,50
    20 ecritures 1,50

Les lignes 3, 8 et 20 mensonges du README sont donc la MEME memoire, et la
table de correction publiee en commentaire (3 verites contre 3 mensonges : 33 %,
contre 4 mensonges : 58 %) opposait deux egalites parfaites, 1,5 contre 1,5.
L'ecart venait des graines, pas des mensonges : `poisoning.py` tire la paire
avec la graine `g * 1000 + mensonges`, donc chaque ligne interroge d'autres
paires.

Ici toutes les cellules utilisent les MEMES paires (graines 1 a N). Deux
cellules de meme poids doivent rendre exactement la meme chose, z compris. Si
elles divergent, le plafond a bouge.

LA CORRECTION TARDIVE
---------------------
Deuxieme affirmation publiee et fausse : « apres une demi-vie, une correction
perd encore contre trois ecritures perimees ». Trois ecritures pesent 1,5 et non
3, donc 0,75 apres 45 jours, et une correction fraiche pese 1,0. Les poids se
croisent a 45 * log2(1,5), environ 26 jours.

⚠ La decroissance part de `last_seen_ts`, PAS de `created_ts`. Antidater
`created_ts` ne teste rien : il faut deplacer l'horloge, et c'est ce que fait
`correction_tardive`. Deux variantes du reste de la memoire, parce qu'elles ne
disent pas la meme chose :

    fond reconfirme  les 60 faits de fond sont reappris au jour T. Ils montent
                     a 1,25 et restent frais : seul le mensonge vieillit.
                     Variante PRUDENTE, plus de bruit contre la correction.
    fond vieilli     personne ne reconfirme rien, le fond vieillit avec le
                     mensonge.

    python diagonale.py --seeds 48      # hors ligne, zero jeton, ~40 s
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics as st
import sys
from datetime import datetime, timezone

from membench.corpus import AS_OF, _OBJECTS, _RELATIONS, _SUBJECTS
from poisoning import une_attaque

_JOUR = 86400.0

#: (verites, mensonges). La diagonale, puis les memes poids atteints autrement,
#: puis les rapports qui manquaient entre 1 et 3.
CELLULES = ((1, 1), (2, 2), (3, 3), (4, 4),
            (3, 4), (1, 3), (1, 4), (1, 20),
            (1, 2), (2, 3), (2, 1), (3, 2))

#: Jours entre les mensonges et la correction.
DELAIS = (0, 14, 27, 45, 90)


def _classe():
    extra = os.environ.get("HOLOMEM_PATH")
    if extra and extra not in sys.path:
        sys.path.insert(0, extra)
    try:
        from holomem import HolographicMemory  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "holomem introuvable. Pose HOLOMEM_PATH sur son dossier."
        ) from exc
    return HolographicMemory


def poids(n: int) -> float:
    """Le poids d'un fait ecrit `n` fois, lu sur la classe et non recopie."""
    hm = _classe()
    if n <= 0:
        return 0.0
    return min(hm.MAX_WEIGHT, 1.0 + hm.REINFORCE_STEP * (n - 1))


def correction_tardive(graine: int, dim: int, mensonges: int, jours: float,
                       fond_reconfirme: bool) -> tuple[str, float]:
    """Les mensonges au jour 0, UNE verite au jour `jours`, question au meme jour.

    Meme tirage que `une_attaque(graine, ...)` : a `jours = 0` avec le fond
    vieilli, c'est exactement la cellule 1 verite contre `mensonges`.
    """
    rng = random.Random(graine)
    sujet = rng.choice(_SUBJECTS)
    relation = rng.choice(_RELATIONS)
    vrai_obj, faux_obj = rng.sample(_OBJECTS, 2)

    t0 = datetime(AS_OF.year, AS_OF.month, AS_OF.day,
                  tzinfo=timezone.utc).timestamp()
    horloge = [t0]
    mem = _classe()(dim=dim, now_fn=lambda: horloge[0])

    fond = []
    for _ in range(60):
        s2 = rng.choice(_SUBJECTS)
        r2 = rng.choice(_RELATIONS)
        if (s2, r2) == (sujet, relation):
            continue
        fond.append((s2, r2, rng.choice(_OBJECTS)))
    for f in fond:
        mem.learn(*f, created_ts=t0)
    for _ in range(mensonges):
        mem.learn(sujet, relation, faux_obj, created_ts=t0)

    horloge[0] = t0 + jours * _JOUR
    if fond_reconfirme:
        for f in fond:
            mem.learn(*f)
    mem.learn(sujet, relation, vrai_obj)

    valeur, z = mem.query_gated(sujet, relation)
    if valeur is None:
        return "silence", z
    return ("verite" if valeur == vrai_obj else "mensonge"), z


def _parts(issues: list[tuple[str, float]]) -> dict:
    n = len(issues)
    return {**{k: round(sum(1 for i, _ in issues if i == k) / n, 4)
               for k in ("verite", "silence", "mensonge")},
            "z_median": round(st.median(z for _, z in issues), 3)}


def _sortie_utf8() -> None:
    """Meme garde que `chambre_echo.py` : un banc doit survivre a un `>`."""
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _sortie_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=48)
    ap.add_argument("--dim", type=int, default=2048)
    ap.add_argument("--out", default="results-diagonale.json")
    a = ap.parse_args()
    graines = range(1, a.seeds + 1)

    print(f"d={a.dim}, les MEMES {a.seeds} paires dans chaque cellule.\n")
    hdr = (f"{'verites':>8}{'mensonges':>10}{'poids V':>9}{'poids M':>9}"
           f"{'verite':>8}{'silence':>9}{'MENSONGE':>10}{'z median':>10}")
    print(hdr)
    print("-" * len(hdr))
    cellules = []
    for v, m in CELLULES:
        c = _parts([une_attaque(g, a.dim, v, m) for g in graines])
        print(f"{v:>8}{m:>10}{poids(v):>9.2f}{poids(m):>9.2f}"
              f"{c['verite']:>8.2f}{c['silence']:>9.2f}{c['mensonge']:>10.2f}"
              f"{c['z_median']:>10.2f}")
        cellules.append({"verites": v, "mensonges": m,
                         "poids_verite": poids(v), "poids_mensonge": poids(m),
                         **c})

    hm = _classe()
    croisement = hm.HALF_LIFE_DAYS * math.log2(poids(3) / poids(1))
    print(f"\nUNE correction ecrite T jours apres les mensonges. Les poids se "
          f"croisent a {croisement:.1f} jours.")
    tardives = []
    for reconfirme in (True, False):
        print(f"\n--- fond {'reconfirme au jour T' if reconfirme else 'vieilli'} ---")
        hdr = (f"{'mensonges':>10}{'jours':>7}{'poids M':>9}{'verite':>8}"
               f"{'silence':>9}{'MENSONGE':>10}{'z median':>10}")
        print(hdr)
        print("-" * len(hdr))
        for m in (3, 4):
            for t in DELAIS:
                c = _parts([correction_tardive(g, a.dim, m, t, reconfirme)
                            for g in graines])
                pm = poids(m) * 0.5 ** (t / hm.HALF_LIFE_DAYS)
                print(f"{m:>10}{t:>7}{pm:>9.2f}{c['verite']:>8.2f}"
                      f"{c['silence']:>9.2f}{c['mensonge']:>10.2f}"
                      f"{c['z_median']:>10.2f}")
                tardives.append({"fond_reconfirme": reconfirme, "mensonges": m,
                                 "jours": t, "poids_mensonge": round(pm, 4),
                                 **c})

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"dim": a.dim, "graines": a.seeds,
                   "reinforce_step": hm.REINFORCE_STEP,
                   "max_weight": hm.MAX_WEIGHT,
                   "half_life_days": hm.HALF_LIFE_DAYS,
                   "croisement_jours": round(croisement, 2),
                   "cellules": cellules, "correction_tardive": tardives},
                  fh, indent=2, ensure_ascii=False)
    print(f"\nEcrit dans {a.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
