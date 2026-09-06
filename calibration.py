"""LA CALIBRATION : le score de confiance veut-il dire quelque chose ?

LA DIFFERENCE AVEC `gate_sweep.py`
----------------------------------
`gate_sweep.py` repond a « ou couper » : pour chaque seuil, la couverture et la
precision obtenues. C'est une courbe de reglage.

Ce banc-ci repond a une autre question, et elle est plus dure : **a l'interieur
des reponses donnees, le score distingue-t-il les bonnes des mauvaises ?** Un
seuil peut tres bien fonctionner alors que le score n'a, au-dessus de lui,
aucun pouvoir de discrimination. On saurait ou couper sans rien savoir de ce
qu'on garde.

Deux choses sont mesurees, et la seconde est la seule qui resiste au choix des
tranches :

    LE DIAGRAMME DE FIABILITE   par tranche de z, la part de reponses justes.
                                Un score honnete produit une courbe qui MONTE.

    LA CONCORDANCE              on tire au hasard une reponse juste et une
                                fausse : quelle est la probabilite que la
                                juste porte le z le plus haut ? 0,5 = le score
                                ne sait rien. 1,0 = il ordonne parfaitement.
                                C'est une AUROC, elle ne depend d'aucun seuil
                                ni d'aucun decoupage.

⚠ LA PORTE EST DEBRANCHEE ICI. On interroge a `z_gate=0` pour voir ce que la
couche AURAIT repondu a chaque niveau de confiance, y compris tout en bas. Un
banc de calibration qui n'observerait que les reponses deja acceptees ne
mesurerait que sa propre selection.

Ce qui compte comme faux : sur un fait perime ou jamais enonce, il n'existe
aucune bonne reponse, donc toute reponse est fausse. C'est la que le score doit
s'effondrer, et c'est la qu'on regarde.

    python calibration.py --seeds 8
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from datetime import datetime, timezone

from membench.corpus import AS_OF, build_corpus, timeline
from membench.real_arms import DermiozArm

#: Bornes des tranches de z. La derniere est ouverte.
TRANCHES = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0)


def observations(graine: int, dim: int) -> list[tuple[float, bool, str]]:
    """(z, juste, genre) pour chaque question, PORTE DEBRANCHEE."""
    faits = build_corpus(seed=graine)
    bras = DermiozArm(dim=dim)
    bras.observe(list(timeline(faits)))
    # On remet l'horloge a aujourd'hui : `observe` l'a promenee dans le passe.
    bras._now = datetime(AS_OF.year, AS_OF.month, AS_OF.day,
                         tzinfo=timezone.utc).timestamp()
    vues = []
    for f in faits:
        valeur, z = bras._mem.query_gated(f.subject, f.relation, z_gate=0.0)
        if valeur is None:
            continue          # la couche n'a produit aucun candidat
        vues.append((float(z), valeur == f.truth, f.kind))
    return vues


def concordance(vues: list[tuple[float, bool, str]]) -> float | None:
    """Probabilite qu'une reponse juste porte un z plus haut qu'une fausse.

    Calcul exact par paires, pas d'echantillonnage : les egalites comptent
    pour une demi-victoire, comme dans toute AUROC.
    """
    justes = [z for z, ok, _ in vues if ok]
    fausses = [z for z, ok, _ in vues if not ok]
    if not justes or not fausses:
        return None
    gagne = sum(1.0 if a > b else 0.5 if a == b else 0.0
                for a in justes for b in fausses)
    return gagne / (len(justes) * len(fausses))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--dim", type=int, default=2048)
    ap.add_argument("--out", default="results-calibration.json")
    a = ap.parse_args()

    vues: list[tuple[float, bool, str]] = []
    for g in range(1, a.seeds + 1):
        vues.extend(observations(g, a.dim))

    print(f"d={a.dim}, {a.seeds} graines, {len(vues)} reponses produites "
          f"porte debranchee.\n")

    hdr = f"{'tranche de z':<16}{'n':>6}{'justes':>9}{'perime/absent':>15}"
    print(hdr); print("-" * len(hdr))
    lignes = []
    for i, bas in enumerate(TRANCHES):
        haut = TRANCHES[i + 1] if i + 1 < len(TRANCHES) else None
        dedans = [v for v in vues
                  if v[0] >= bas and (haut is None or v[0] < haut)]
        if not dedans:
            continue
        part = sum(1 for _, ok, _ in dedans if ok) / len(dedans)
        sans_reponse = sum(1 for _, _, k in dedans
                           if k in ("expired", "absent")) / len(dedans)
        etiq = f"[{bas:g}, {haut:g})" if haut else f"[{bas:g}, inf)"
        print(f"{etiq:<16}{len(dedans):>6}{part:>9.3f}{sans_reponse:>15.3f}")
        lignes.append({"de": bas, "a": haut, "n": len(dedans),
                       "part_justes": round(part, 4),
                       "part_sans_bonne_reponse": round(sans_reponse, 4)})

    c = concordance(vues)
    parts = [x["part_justes"] for x in lignes]
    monotone = all(b >= a_ - 1e-9 for a_, b in zip(parts, parts[1:]))

    print(f"\nCONCORDANCE : {c:.3f}" if c is not None else "\nCONCORDANCE : n/m")
    print("  0,500 = le score n'ordonne rien. 1,000 = il ordonne parfaitement.")
    print(f"MONOTONE : {'oui' if monotone else 'NON'}"
          f"  (la part de justes monte-t-elle a chaque tranche ?)")
    print(f"\nz median des justes  : "
          f"{st.median([z for z, ok, _ in vues if ok]):.2f}")
    print(f"z median des fausses : "
          f"{st.median([z for z, ok, _ in vues if not ok]):.2f}")

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"dim": a.dim, "graines": a.seeds, "n_reponses": len(vues),
                   "concordance": c, "monotone": monotone,
                   "tranches": lignes}, fh, indent=2, ensure_ascii=False)
    print(f"\nEcrit dans {a.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
