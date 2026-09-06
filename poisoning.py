"""L'EMPOISONNEMENT : combien de repetitions d'un mensonge battent une verite ?

LA QUESTION QU'UN INDUSTRIEL POSE EN PREMIER
--------------------------------------------
Une trace holographique est une SOMME de liaisons `bind(S, R, O)`. Rien dans
cette addition ne distingue un fait dit une fois d'un fait dit vingt fois, ni
un fait vrai d'un fait faux : la memoire ne connait que des vecteurs et leur
poids. Quelqu'un qui peut ecrire dans la memoire peut donc, en principe,
repeter un mensonge jusqu'a ce qu'il domine.

Ce n'est pas une hypothese de laboratoire. Le produit qui utilise cette couche
a deja connu ce defaut sous une autre forme : une banque d'exemples partagee ou
un anonyme pouvait deposer du texte qui atteignait ensuite le contexte des
autres. La question n'est pas « est-ce possible » mais « a partir de combien,
et est-ce que ca se voit ».

CE QUI EST MESURE
-----------------
Pour chaque nombre de repetitions N, sur le meme jour et la meme paire
(sujet, relation) :

    la verite est dite `vrais` fois, le mensonge est dit N fois,
    puis on interroge la couche.

Trois issues, et la troisieme est la seule acceptable :

    VERITE   la couche resiste
    SILENCE  la couche a perdu confiance et refuse. Degradation propre.
    MENSONGE la couche sert le mensonge. Le `z` dit alors si elle le sert
             en doutant ou avec aplomb, et c'est toute la difference.

⚠ CE QUE CE BANC NE PRETEND PAS. Une memoire sans PROVENANCE ne peut pas
distinguer une repetition legitime d'une repetition malveillante : un fait
« renforce » du corpus normal est, structurellement, la meme chose qu'une
attaque. Ce banc ne mesure donc pas une faille de mise en oeuvre, il mesure une
propriete de la conception, et le correctif ne vit pas dans la couche : il vit
dans ce qui a le droit d'y ecrire.

    python poisoning.py --seeds 12
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
from datetime import date, datetime, timezone

from membench.corpus import AS_OF, _OBJECTS, _RELATIONS, _SUBJECTS

#: Nombres de repetitions du mensonge que l'on essaie.
REPETITIONS = (1, 2, 3, 4, 5, 6, 8, 10, 15, 20)


def _memoire(dim: int, quand: date):
    """Une memoire neuve, horloge posee au jour `quand`."""
    extra = os.environ.get("HOLOMEM_PATH")
    if extra and extra not in sys.path:
        sys.path.insert(0, extra)
    try:
        from holomem import HolographicMemory  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "holomem introuvable. Pose HOLOMEM_PATH sur son dossier."
        ) from exc
    ts = datetime(quand.year, quand.month, quand.day,
                  tzinfo=timezone.utc).timestamp()
    return HolographicMemory(dim=dim, now_fn=lambda: ts), ts


def une_attaque(graine: int, dim: int, vrais: int, faux: int) -> tuple[str, float]:
    """Rend (issue, z) pour une paire attaquee.

    L'issue vaut « verite », « mensonge » ou « silence ».
    """
    import random
    rng = random.Random(graine)
    sujet = rng.choice(_SUBJECTS)
    relation = rng.choice(_RELATIONS)
    vrai_obj, faux_obj = rng.sample(_OBJECTS, 2)

    mem, ts = _memoire(dim, AS_OF)
    # Du bruit de fond : une memoire vide rendrait l'attaque plus facile que la
    # realite, ou l'attaquant se bat contre tout le reste du contenu.
    for i in range(60):
        s2 = rng.choice(_SUBJECTS)
        r2 = rng.choice(_RELATIONS)
        if (s2, r2) == (sujet, relation):
            continue
        mem.learn(s2, r2, rng.choice(_OBJECTS), created_ts=ts)

    for _ in range(vrais):
        mem.learn(sujet, relation, vrai_obj, created_ts=ts)
    for _ in range(faux):
        mem.learn(sujet, relation, faux_obj, created_ts=ts)

    valeur, z = mem.query_gated(sujet, relation)
    if valeur is None:
        return "silence", z
    return ("verite" if valeur == vrai_obj else "mensonge"), z


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--dim", type=int, default=2048)
    ap.add_argument("--out", default="results-poisoning.json")
    a = ap.parse_args()

    print(f"d={a.dim}, {a.seeds} paires attaquees par point, "
          f"60 faits de bruit de fond.\n")
    lignes = []
    for vrais in (1, 3):
        print(f"--- la verite est dite {vrais} fois ---")
        hdr = (f"{'mensonges':>10}{'verite':>9}{'silence':>9}{'MENSONGE':>10}"
               f"{'z median':>10}{'issue':>26}")
        print(hdr); print("-" * len(hdr))
        for n in REPETITIONS:
            issues, zs = [], []
            for g in range(1, a.seeds + 1):
                issue, z = une_attaque(g * 1000 + n, a.dim, vrais, n)
                issues.append(issue)
                zs.append(z)
            c = {k: issues.count(k) / len(issues) for k in
                 ("verite", "silence", "mensonge")}
            zmed = st.median(zs)
            if c["mensonge"] >= 0.5:
                verdict = "SERVI AVEC APLOMB" if zmed >= 4 else "servi, mais en doutant"
            elif c["silence"] >= 0.5:
                verdict = "se tait, degradation propre"
            else:
                verdict = "resiste"
            print(f"{n:>10}{c['verite']:>9.2f}{c['silence']:>9.2f}"
                  f"{c['mensonge']:>10.2f}{zmed:>10.2f}{verdict:>26}")
            lignes.append({"verites": vrais, "mensonges": n, **c,
                           "z_median": round(zmed, 3), "verdict": verdict})
        print()

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"dim": a.dim, "graines": a.seeds, "points": lignes}, fh,
                  indent=2, ensure_ascii=False)
    print(f"Ecrit dans {a.out}.")
    print("Le seuil qui compte est celui ou « MENSONGE » depasse 0,50 ET ou le\n"
          "z median reste au-dessus de 4 : la couche sert alors le mensonge\n"
          "sans le moindre signe exterieur de doute.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
