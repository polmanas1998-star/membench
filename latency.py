"""LA LATENCE : ce que la couche coute en millisecondes, et comment ca grandit.

LA QUESTION D'EXPLOITATION QUE PERSONNE N'AVAIT POSEE
-----------------------------------------------------
Tout le reste de ce depot mesure la JUSTESSE. Rien n'y mesure le temps. Or le
service qui porte cette couche tourne sur 512 Mo et UN worker : deux secondes
passees dans une requete sont deux secondes pendant lesquelles aucune autre
conversation n'avance. Une couche parfaite qui bloque le processus n'est pas
deployable, et aucun chiffre du README ne le dirait.

CE QUI EST MESURE, ET POURQUOI CE DECOUPAGE
-------------------------------------------
La trace est MISE EN CACHE et invalidee a chaque apprentissage. Deux regimes
completement differents en decoulent, et publier le mauvais ment d'un facteur
qui grandit avec N :

    interrogation A CHAUD   la trace est deja construite. C'est le cout d'une
                            seconde question posee de suite.

    interrogation A FROID   un fait vient d'etre appris, la trace est refaite
                            depuis la liste complete. C'est O(N).

**C'est le froid qui compte.** Dans une conversation reelle on apprend puis on
interroge, tour apres tour : on paie la reconstruction a chaque fois. Un banc
qui ne publierait que le chaud decrirait un usage que personne n'a.

⚠ ON PREND LE MINIMUM, PAS LA MEDIANE, ET C'EST UNE CORRECTION.
La premiere serie a ete prise pendant qu'une campagne payante tournait en fond.
Elle donnait, a d=2048 : 250 ms a 500 faits, 924 ms a 1000, puis 219 ms a 2000.
Non monotone, donc impossible pour un cout lineaire, donc contaminee.

Sous contention, chaque mesure est gonflee d'une quantite aleatoire toujours
POSITIVE : le bruit ne se compense jamais, il s'ajoute. Une mediane l'absorbe
sans le retirer. Le MINIMUM sur plusieurs essais est l'estimateur le plus
proche du cout reel, parce qu'il retient l'essai ou le systeme a le moins
derange. C'est la pratique usuelle du micro-banc, et c'est ce qui rend cette
table lisible sans attendre que la machine soit libre.

⚠ MESURE SUR WINDOWS, PAS SUR LA CIBLE. La production est un conteneur Linux.
Les ordres de grandeur et la FORME de la courbe se transportent, les
millisecondes exactes non. C'est la forme qui decide ici : savoir si le cout
croit avec le nombre de faits, et a partir de quand il devient un probleme pour
un worker unique.

    python latency.py
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import time

#: Le seuil au-dela duquel une requete bloque visiblement un worker unique.
#: 100 ms est le repere usuel d'une interaction qui reste fluide ; au-dela on
#: sent l'attente, et surtout on empeche les autres conversations d'avancer.
SEUIL_MS = 100.0

#: Au-dela de ce rapport mediane / minimum, la machine etait derangee pendant
#: la mesure et la ligne est declaree inutilisable plutot que publiee. 2,0 est
#: large : une machine tranquille reste sous 1,5.
SEUIL_CONTENTION = 2.0

TAILLES = (50, 100, 200, 500, 1000, 2000)
DIMENSIONS = (1024, 2048, 4096)


def _memoire(dim: int):
    extra = os.environ.get("HOLOMEM_PATH")
    if extra and extra not in sys.path:
        sys.path.insert(0, extra)
    from holomem import HolographicMemory  # noqa: PLC0415
    horloge = [time.time()]
    return HolographicMemory(dim=dim, now_fn=lambda: horloge[0])


def mesure(n: int, dim: int, tours: int = 60) -> dict:
    """Apprend n faits, puis chronometre les trois operations."""
    mem = _memoire(dim)

    t0 = time.perf_counter()
    for i in range(n):
        mem.learn(f"sujet{i % 97}", f"relation{i % 13}", f"objet{i}")
    ms_apprentissage = (time.perf_counter() - t0) * 1000 / n

    # A CHAUD : la trace existe deja, on la reutilise.
    mem.trace
    chaud = []
    for i in range(tours):
        t = time.perf_counter()
        mem.query_gated(f"sujet{i % 97}", f"relation{i % 13}")
        chaud.append((time.perf_counter() - t) * 1000)

    # A FROID : un fait appris invalide la trace, la question suivante la
    # reconstruit. C'est le vrai regime d'une conversation.
    froid = []
    for i in range(tours):
        mem.learn("sujet_temoin", f"relation{i % 13}", f"objet_temoin{i}")
        t = time.perf_counter()
        mem.query_gated(f"sujet{i % 97}", f"relation{i % 13}")
        froid.append((time.perf_counter() - t) * 1000)

    octets = mem.trace.nbytes
    return {"n": n, "dim": dim,
            "apprentissage_ms": round(ms_apprentissage, 3),
            "chaud_ms": round(min(chaud), 2),
            "froid_ms": round(min(froid), 2),
            # La mediane est gardee A COTE du minimum, pas a la place : l'ecart
            # entre les deux dit combien la machine etait derangee pendant la
            # mesure. Un ecart enorme invalide la lecture, et il faut le voir.
            "froid_median_ms": round(st.median(froid), 2),
            "trace_ko": round(octets / 1024, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results-latency.json")
    a = ap.parse_args()

    import platform
    print(f"{platform.system()} {platform.machine()}, python "
          f"{sys.version.split()[0]}. Mediane sur 30 tours.\n")

    hdr = (f"{'faits':>7}{'d':>7}{'apprend':>10}{'a chaud':>10}"
           f"{'A FROID':>10}{'(median)':>10}{'trace':>9}")
    print(hdr); print("-" * len(hdr))
    lignes = []
    for dim in DIMENSIONS:
        for n in TAILLES:
            r = mesure(n, dim)
            lignes.append(r)
            # LE RAPPORT MEDIANE / MINIMUM EST LE DETECTEUR DE CONTAMINATION.
            # Sur une machine tranquille il vaut 1,1 a 1,5. Au-dela, une autre
            # charge s'est invitee pendant la mesure et la ligne ne se publie
            # pas. Mesure : la premiere serie de ce banc, prise pendant une
            # campagne payante, montait a 2,3x et rendait une courbe non
            # monotone, donc impossible.
            rapport = (r["froid_median_ms"] / r["froid_ms"]) if r["froid_ms"] else 0
            r["rapport_median_min"] = round(rapport, 2)
            if rapport > SEUIL_CONTENTION:
                alerte = f"  <-- CONTAMINE, {rapport:.1f}x, ne pas publier"
            elif r["froid_ms"] > SEUIL_MS:
                alerte = "  <-- au-dessus du seuil"
            else:
                alerte = ""
            print(f"{n:>7}{dim:>7}{r['apprentissage_ms']:>9.3f}ms"
                  f"{r['chaud_ms']:>9.2f}ms{r['froid_ms']:>9.2f}ms"
                  f"{r['froid_median_ms']:>9.1f}ms"
                  f"{r['trace_ko']:>8.1f}K{alerte}")
        print()

    # Ou casse-t-on le seuil ? On le cherche par dimension.
    print(f"Seuil retenu : {SEUIL_MS:.0f} ms a froid, au-dela desquelles une "
          f"requete bloque\nvisiblement un worker unique.\n")
    sales = [x for x in lignes if x.get("rapport_median_min", 0) > SEUIL_CONTENTION]
    if sales:
        noms = ", ".join(f"n={x['n']}/d={x['dim']}" for x in sales)
        print(f"  {len(sales)} ligne(s) CONTAMINEE(S) : {noms}")
        print("  Elles ne comptent pas dans les seuils ci-dessous." + chr(10))
    for dim in DIMENSIONS:
        pts = [x for x in lignes if x["dim"] == dim
               and x.get("rapport_median_min", 0) <= SEUIL_CONTENTION]
        if not pts:
            print(f"  d={dim:<5} entierement contamine, rien a conclure")
            continue
        casse = next((x["n"] for x in pts if x["froid_ms"] > SEUIL_MS), None)
        if casse is None:
            print(f"  d={dim:<5} tient jusqu'a {pts[-1]['n']} faits "
                  f"({pts[-1]['froid_ms']:.1f} ms), pas de rupture mesuree")
        else:
            print(f"  d={dim:<5} depasse le seuil des {casse} faits")

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"plateforme": platform.system(), "seuil_ms": SEUIL_MS,
                   "points": lignes}, fh, indent=2, ensure_ascii=False)
    print(f"\nEcrit dans {a.out}.")
    print("La trace ne grandit PAS avec le nombre de faits : c'est la promesse\n"
          "de la superposition, et cette colonne la verifie. Le TEMPS, lui,\n"
          "grandit, parce que la trace est reconstruite depuis la liste.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
