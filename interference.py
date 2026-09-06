"""L'INTERFERENCE : ce que coute un sujet qui porte beaucoup de relations.

CE QUE CE BANC MESURE, ET POURQUOI IL A FALLU L'ECRIRE
------------------------------------------------------
La trace est une somme de liaisons `bind(S, R, O)`, et on l'interroge avec
`unbind(trace, bind(S, R))`. Quand plusieurs faits partagent le meme sujet, le
bruit que les autres versent dans la reponse cesse d'etre independant : il est
correle par ce sujet commun. C'est le pire cas d'une memoire holographique, et
c'est aussi le cas REEL : une personne parle beaucoup d'elle-meme, d'un projet,
d'une machine.

Le README annoncait cette structure comme ABSENTE du corpus :

    « chaque paire sujet-relation est unique par construction, donc le cas
      reel le plus difficile, un sujet portant plusieurs relations qui
      interferent, est absent »

C'est faux, et mesure le 06/09/2026. Le vocabulaire compte 12 sujets et 10
relations, soit 120 paires, et le melange par defaut en consomme 104 : le
corpus tourne a 87 % de la saturation, avec 8,7 relations par sujet. Il ne
manquait pas d'interference, il en avait presque le maximum possible, et
personne ne l'avait compte.

CE QUI EST COMPARE ICI
----------------------
Le nombre de faits est CONSTANT d'un point a l'autre. Meme quantite
d'information, meme longueur de trace, meme melange de genres. Seule la
STRUCTURE change : on concentre les memes faits sur de moins en moins de
sujets. Sans cette constante, on lirait un effet de taille comme un effet
d'interference.

    python interference.py --seeds 8
"""
from __future__ import annotations

import argparse
import json

from membench.arms import ScrambledMemory, run
from membench.corpus import build_corpus, timeline
from membench.real_arms import DermiozArm
from membench.scoring import score

#: Melange reduit a 30 faits, proportionnel au melange par defaut. Il faut
#: qu'il tienne sur 3 sujets (3 x 10 relations = 30 paires) pour que le point
#: le plus concentre existe. A 104 faits, seul 12 serait possible, et il n'y
#: aurait pas de courbe.
MIX30 = {"stable": 5, "faded": 6, "expired": 4,
         "superseded": 5, "reinforced": 4, "absent": 6}

#: De la concentration maximale (3 sujets, 10 relations chacun) a l'etalement
#: le plus large que le vocabulaire permette.
SUJETS = (3, 4, 5, 6, 8, 10, 12)


# ⚠ TAUX MIS EN COMMUN, PAS MEDIANE DES TAUX.
#
# La premiere version de ce banc mediane les taux par graine. Une mediane est
# AVEUGLE a un evenement rare : trois erreurs reparties sur deux graines sur
# huit disparaissent derriere six graines parfaites. C'est exactement ce qui
# s'est produit dans `ablation.py`, ou la mediane a fait conclure qu'un garde
# ne servait a rien alors qu'il retirait toutes les erreurs qu'il visait.
#
# Un taux d'erreur rare se calcule sur le total des questions, jamais en
# resumant des taux dont chacun a son propre denominateur.


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--dim", type=int, default=2048)
    ap.add_argument("--out", default="results-interference.json")
    a = ap.parse_args()

    total = sum(MIX30.values())
    print(f"{total} faits par corpus, constant. d={a.dim}, {a.seeds} graines.")
    print(f"{a.seeds * len(SUJETS) * total * 2} questions posees au total.\n")

    hdr = (f"{'sujets':>7}{'rel/sujet':>11}{'couv':>8}{'prec':>8}"
           f"{'halluc':>9}{'melangee':>10}{'ecart':>8}")
    print(hdr)
    print("-" * len(hdr))

    cellules = []
    for n in SUJETS:
        faits, rep, rep_mel = [], [], []
        for g in range(1, a.seeds + 1):
            f = build_corpus(seed=g, mix=MIX30, sujets_max=n)
            tl = list(timeline(f))
            faits.extend(f)
            rep.extend(run(DermiozArm(dim=a.dim), f, tl))
            rep_mel.extend(run(ScrambledMemory(DermiozArm(dim=a.dim), seed=7), f, tl))
        r, m = score(faits, rep), score(faits, rep_mel)
        c, p, h = r.coverage, r.gated_precision, m.gated_precision
        hal = [r.hallucination]
        ecart = None if (p is None or h is None) else p - h
        g_ = lambda v: "  n/m" if v is None else f"{v:.3f}"
        print(f"{n:>7}{total / n:>11.1f}{g_(c):>8}{g_(p):>8}"
              f"{g_(hal[0]):>9}{g_(h):>10}{g_(ecart):>8}")
        cellules.append({"sujets": n, "relations_par_sujet": round(total / n, 1),
                         "couverture": c, "precision_gardee": p,
                         "hallucination": hal[0], "precision_melangee": h,
                         "ecart_au_temoin": ecart})

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"faits_par_corpus": total, "dim": a.dim, "graines": a.seeds,
                   "melange": MIX30, "cellules": cellules}, fh,
                  indent=2, ensure_ascii=False)
    print(f"\nEcrit dans {a.out}.")
    print("« ecart » = precision de la couche moins celle de sa jumelle a "
          "chronologie melangee.\nSi cet ecart s'effondre, la tache cesse "
          "d'exiger de la memoire et le banc ne mesure plus rien.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
