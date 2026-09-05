"""Les ecarts qui portent une conclusion, avec leur bande."""
from __future__ import annotations

from membench.arms import MajorityArm, OracleArm, ScrambledMemory, run
from membench.corpus import build_corpus, timeline
from membench.real_arms import DermiozArm
from membench.stats import coverage, gated_precision, paired_bootstrap

SEEDS = 8


def main() -> int:
    pooled_f, pooled = [], {}
    for s in range(1, SEEDS + 1):
        f = build_corpus(seed=s)
        tl = list(timeline(f))
        arms = {
            "D": DermiozArm(dim=2048),
            "D melangee": ScrambledMemory(DermiozArm(dim=2048), seed=7),
            "majoritaire": MajorityArm(tl),
            "oracle": OracleArm(f),
        }
        for name, arm in arms.items():
            pooled.setdefault(name, []).extend(run(arm, f, tl))
        pooled_f.extend(f)

    print(f"bootstrap apparie, {len(pooled_f)} questions "
          f"({SEEDS} graines x {len(pooled_f)//SEEDS}), 4000 tirages, IC 95 %\n")
    tests = [
        ("precision gardee", gated_precision,
         [("D", "D melangee"), ("D", "majoritaire"), ("D", "oracle")]),
        ("couverture", coverage,
         [("D", "D melangee"), ("D", "oracle")]),
    ]
    for label, metric, pairs in tests:
        print(f"  {label}")
        for l, r in pairs:
            iv = paired_bootstrap(pooled_f, pooled[l], pooled[r], metric=metric)
            verdict = "ecart net" if iv.excludes_zero else "BANDE TRAVERSE ZERO"
            drop = f", {iv.dropped} tirages ecartes" if iv.dropped else ""
            print(f"    {l:<12} - {r:<12} {iv}   {verdict}{drop}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
