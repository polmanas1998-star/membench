"""Ou la couche se trompe, et ou elle se tait. Par classe, pas en agregat.

Un taux agrege dit qu'il y a 5 erreurs sur 416. Il ne dit pas si ce sont
5 erreurs benignes sur des faits vieux, ou 5 erreurs graves sur des faits
frais que le systeme aurait du tenir. Ce sont deux produits differents.
"""
from __future__ import annotations

from collections import Counter

from membench.corpus import build_corpus, timeline
from membench.real_arms import DermiozArm
from membench.scoring import Answer

SEEDS = 8


def main() -> int:
    rows: list[tuple] = []
    for s in range(1, SEEDS + 1):
        f = build_corpus(seed=s)
        tl = list(timeline(f))
        arm = DermiozArm(dim=2048)
        arm.observe(tl)
        for fact in f:
            a: Answer = arm.ask(fact.subject, fact.relation)
            age = fact.age_days()
            if not a.answered:
                verdict = "silence"
            elif fact.truth is None:
                verdict = "hallucination"
            elif a.value == fact.truth:
                verdict = "juste"
            elif a.value == fact.superseded:
                verdict = "valeur PERIMEE"
            else:
                verdict = "faux"
            rows.append((fact.kind, verdict, age, fact.subject, fact.relation,
                         a.value, fact.truth))

    kinds = ["stable", "reinforced", "superseded", "faded", "expired", "absent"]
    verdicts = ["juste", "silence", "faux", "valeur PERIMEE", "hallucination"]
    tab: Counter = Counter((k, v) for k, v, *_ in rows)

    print(f"analyse d'erreurs, {SEEDS} graines, {len(rows)} questions, d=2048\n")
    hdr = f"{'classe':<13}" + "".join(v.rjust(16) for v in verdicts) + f"{'total':>8}"
    print(hdr); print("-" * len(hdr))
    for k in kinds:
        tot = sum(tab[(k, v)] for v in verdicts)
        print(f"{k:<13}" + "".join(f"{tab[(k, v)]:>16}" for v in verdicts)
              + f"{tot:>8}")
    print("-" * len(hdr))
    print(f"{'total':<13}" + "".join(
        f"{sum(tab[(k, v)] for k in kinds):>16}" for v in verdicts)
        + f"{len(rows):>8}")

    print("\nles erreurs, une par une :")
    bad = [r for r in rows if r[1] in ("faux", "valeur PERIMEE", "hallucination")]
    if not bad:
        print("  aucune")
    for kind, verdict, age, subj, rel, got, want in bad:
        print(f"  [{verdict:<14}] {kind:<11} age {str(age):>4} j   "
              f"{subj} / {rel}\n{'':>21}rendu {got!r}, attendu {want!r}")

    print("\nou va le silence :")
    sil = Counter(k for k, v, *_ in rows if v == "silence")
    for k in kinds:
        tot = sum(tab[(k, v)] for v in verdicts)
        if tot:
            print(f"  {k:<13} {sil[k]:>4} / {tot:<4} "
                  f"({sil[k] / tot:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
