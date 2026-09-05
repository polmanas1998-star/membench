"""Le banc sur plusieurs graines, avec sa dispersion, plus les deux controles.

Un run unique est un point, pas une mesure. Les bancs qui tiennent publient
une bande : tau-bench compte la reussite sur k essais, la table de capacite de
holomem fait 12 tirages par cellule. Ici : mediane et min-max sur N graines.

Deux lignes de controle que le banc doit passer avant d'etre lu :

  base: majoritaire      la ligne TRIVIALE. Ne pas la battre prouve qu'on n'a rien.
  chronologie melangee   le controle de RACCOURCI. Le meme systeme nourri d'une
                         chronologie dont les objets ont ete redistribues au
                         hasard. S'il score encore, les questions sont
                         repondables sans memoire et le banc mesure autre chose.
"""
from __future__ import annotations

import argparse
import statistics as st

from membench.arms import MajorityArm, OracleArm, ScrambledMemory, run
from membench.corpus import build_corpus, timeline
from membench.real_arms import DermiozArm
from membench.scoring import score

COLS = [("cover", "coverage"), ("gated P", "gated_precision"),
        ("retain", "retention"), ("stale err", "supersession_error"),
        ("age", "age_awareness"), ("deep ret", "deep_retention"),
        ("halluc", "hallucination")]


def cell(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "n/m".rjust(16)
    med = st.median(vals)
    return f"{med:.3f} [{min(vals):.3f}-{max(vals):.3f}]".rjust(16)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--dim", type=int, default=2048)
    a = ap.parse_args()

    makers = [
        ("temoin: oracle", lambda f, tl: OracleArm(f)),
        ("base: majoritaire", lambda f, tl: MajorityArm(tl)),
        ("D couche Dermioz", lambda f, tl: DermiozArm(dim=a.dim)),
        ("D [melangee]", lambda f, tl: ScrambledMemory(DermiozArm(dim=a.dim), seed=7)),
    ]
    acc = {n: {k: [] for _, k in COLS} for n, _ in makers}
    ages = {n: [0, 0] for n, _ in makers}

    for s in range(1, a.seeds + 1):
        f = build_corpus(seed=s)
        tl = list(timeline(f))
        for name, make in makers:
            r = score(f, run(make(f, tl), f, tl))
            for _, k in COLS:
                acc[name][k].append(getattr(r, k))
            ages[name][0] += r.age_answered
            ages[name][1] += r.age_n

    print(f"membench, {a.seeds} graines, d={a.dim}, {len(f)} questions par graine")
    print("mediane [min-max] sur les graines\n")
    head = f"{'arm':<22}" + "".join(h.rjust(16) for h, _ in COLS)
    print(head)
    print("-" * len(head))
    for name, _ in makers:
        print(f"{name:<22}" + "".join(cell(acc[name][k]) for _, k in COLS))
    print()
    for name, _ in makers:
        d, n = ages[name]
        print(f"  {name:<22} age mesure sur {d}/{n} vieux faits repondus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
