"""La surface complete de la couche : dimension x taille x graine.

Un banc de produit publie une cellule. Celui-ci publie la surface, parce que
la seule chose qui coute ici est du temps de calcul local : aucune cle, aucun
jeton, aucun plafond. Il n'y a donc aucune excuse pour ne mesurer qu'un point.

Pour chaque cellule on garde ce qui ne se truque pas :
  couverture, precision gardee, hallucination sur les faits jamais dits,
  et l'ecart entre la couche HONNETE et son jumeau a chronologie MELANGEE,
  qui dit si la confiance suit encore la justesse a cet endroit.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import time

from membench.arms import ScrambledMemory, run
from membench.corpus import DEFAULT_MIX, build_corpus, timeline
from membench.real_arms import DermiozArm
from membench.scoring import score

DIMS = (256, 512, 1024, 2048, 4096, 8192)
SCALES = (0.5, 1.0, 2.0, 3.0, 4.0)   # multiplicateurs de la taille du corpus


def mix_at(scale: float) -> dict:
    m = {k: max(2, round(v * scale)) for k, v in DEFAULT_MIX.items()}
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--out", default="grid.json")
    a = ap.parse_args()

    cells, t0 = [], time.time()
    total = len(DIMS) * len(SCALES)
    done = 0
    for scale in SCALES:
        mix = mix_at(scale)
        n = sum(mix.values())
        for dim in DIMS:
            acc = {"cover": [], "prec": [], "hal": [], "scr": []}
            for s in range(1, a.seeds + 1):
                f = build_corpus(seed=s, mix=mix)
                tl = list(timeline(f))
                r = score(f, run(DermiozArm(dim=dim), f, tl))
                rs = score(f, run(ScrambledMemory(DermiozArm(dim=dim), seed=7), f, tl))
                acc["cover"].append(r.coverage)
                if r.gated_precision is not None:
                    acc["prec"].append(r.gated_precision)
                if r.hallucination is not None:
                    acc["hal"].append(r.hallucination)
                if r.gated_precision is not None and rs.gated_precision is not None:
                    acc["scr"].append(r.gated_precision - rs.gated_precision)
            med = lambda k: (st.median(acc[k]) if acc[k] else None)
            rng = lambda k: ((min(acc[k]), max(acc[k])) if acc[k] else None)
            cells.append({"dim": dim, "n": n, "seeds": a.seeds,
                          "cover": med("cover"), "cover_rng": rng("cover"),
                          "prec": med("prec"), "prec_rng": rng("prec"),
                          "halluc": med("hal"),
                          "gap_vs_scrambled": med("scr")})
            done += 1
            fmt = lambda v, sign="": "  n/m" if v is None else format(v, sign + ".3f")
            print(f"  [{done:>2}/{total}] d={dim:<5} n={n:<4} "
                  f"couv {fmt(med('cover'))}  prec {fmt(med('prec'))}  "
                  f"hal {fmt(med('hal'))}  ecart/melangee {fmt(med('scr'), '+')}",
                  flush=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"seeds": a.seeds, "dims": DIMS, "cells": cells}, fh, indent=2)
    q = sum(c["n"] for c in cells) * a.seeds * 2
    print(f"\n{len(cells)} cellules, {a.seeds} graines, "
          f"{q} questions posees au total, {time.time() - t0:.0f} s")
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
