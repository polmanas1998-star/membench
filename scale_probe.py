"""Les deux bras qui comptent, sur le corpus ENTIER.

n = 24 etait une sonde. La comparaison la plus dure pour la couche est C, la
recherche lexicale bete, qui repond plus souvent qu'elle. Cette comparaison
merite le corpus complet, donc on la fait d'abord et on laisse tomber le reste
si le plafond quotidien coupe.
"""
from __future__ import annotations

import json
import sys

from membench.arms import run
from membench.corpus import build_corpus, candidates, timeline
from membench.providers import DailyBudgetExhausted, GroqModel
from membench.real_arms import DermiozGroundedArm, FullContextArm, RetrievalArm
from membench.scoring import score

TPD = 200_000
OUT = sys.argv[1] if len(sys.argv) > 1 else "scale.json"


def main() -> int:
    f = build_corpus(seed=1)
    tl, pool = list(timeline(f)), candidates(f)
    m = GroqModel(account="outillage")
    print(f"{len(f)} questions, compte outillage {m.key_fingerprint}, d=2048",
          flush=True)
    hdr = (f"{'bras':<24}{'couv':>7}{'prec':>7}{'halluc':>8}{'deep':>7}"
           f"{'jet/tour':>10}{'jet/juste':>11}")
    print(hdr, flush=True); print("-" * len(hdr), flush=True)

    rows = {}
    # Ordre delibere : le moins cher d'abord, pour que le plafond coupe le
    # plus gourmand et pas l'inverse.
    for name, arm in [("D+ couche puis modele", DermiozGroundedArm(m, pool, dim=2048)),
                      ("C recherche top-k", RetrievalArm(m, pool)),
                      ("B historique complet", FullContextArm(m, pool))]:
        try:
            r = score(f, run(arm, f, tl))
        except DailyBudgetExhausted as exc:
            print(f"{name:<24}  ARRETE : {exc}", flush=True)
            break
        pr = r.prompt_tokens_total / r.correct if r.correct else None
        g = lambda v: "  n/m" if v is None else f"{v:.3f}"
        print(f"{name:<24}{g(r.coverage):>7}{g(r.gated_precision):>7}"
              f"{g(r.hallucination):>8}{g(r.deep_retention):>7}"
              f"{(r.tokens_per_turn or 0):>10.0f}"
              f"{('n/m' if pr is None else f'{pr:.0f}'):>11}", flush=True)
        rows[name] = r.as_row() | {"tokens_total": r.prompt_tokens_total,
                                   "correct": r.correct,
                                   "tok_per_correct": pr}
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2, ensure_ascii=False)
    print(f"\n429 : {m.rate_limited}, attente {m.waited_seconds:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
