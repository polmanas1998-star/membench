"""Cout par TOUR et cout par REPONSE JUSTE, sur le meme echantillon.

Le cout par tour se truque en se taisant : un bras qui refuse la moitie des
questions ne depense rien sur cette moitie et affiche une moyenne flatteuse.
Le cout par reponse juste ne se truque pas, parce que le silence n'y met
aucun numerateur.
"""
from __future__ import annotations

import random

from membench.arms import run
from membench.corpus import build_corpus, candidates, timeline
from membench.providers import GroqModel
from membench.real_arms import (DermiozGroundedArm, FullContextArm,
                                RetrievalArm, StatelessArm)
from membench.scoring import TPM_CEILING, score

TPD = 200_000


def main() -> int:
    f = build_corpus(seed=1)
    tl, pool = list(timeline(f)), candidates(f)
    rng = random.Random(1)
    byk: dict = {}
    for x in f:
        byk.setdefault(x.kind, []).append(x)
    sample = [y for k in sorted(byk) for y in rng.sample(byk[k], 4)]

    m = GroqModel(account="outillage")
    print(f"{len(sample)} questions stratifiees, compte outillage "
          f"{m.key_fingerprint}, d=2048\n")
    hdr = (f"{'bras':<24}{'couv':>7}{'prec':>7}{'halluc':>8}"
           f"{'jet/tour':>10}{'jet/juste':>11}{'justes/jour':>12}")
    print(hdr); print("-" * len(hdr))
    for name, arm in [
        ("A modele seul", StatelessArm(m, pool)),
        ("D+ couche puis modele", DermiozGroundedArm(m, pool, dim=2048)),
        ("C recherche top-k", RetrievalArm(m, pool)),
        ("B historique complet", FullContextArm(m, pool)),
    ]:
        r = score(sample, run(arm, sample, tl))
        tot = r.prompt_tokens_total
        tpt = r.tokens_per_turn or 0
        per_right = tot / r.correct if r.correct else None
        right_day = TPD / per_right if per_right else 0
        g = lambda v: "  n/m" if v is None else f"{v:.3f}"
        print(f"{name:<24}{g(r.coverage):>7}{g(r.gated_precision):>7}"
              f"{g(r.hallucination):>8}{tpt:>10.0f}"
              f"{('n/m' if per_right is None else f'{per_right:.0f}'):>11}"
              f"{right_day:>12.0f}")
    print(f"\nplafonds : {TPM_CEILING} jetons/min, {TPD} jetons/jour")
    print(f"429 rencontres : {m.rate_limited}, attente cumulee "
          f"{m.waited_seconds:.0f} s")
    print("\n« jet/juste » = jetons totaux depenses / reponses justes. "
          "Un bras qui se tait n'y gagne rien.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
