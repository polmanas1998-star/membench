# -*- coding: utf-8 -*-
"""LA CHAMBRE D'ECHO : deux memoires qui se parlent, et plus personne dehors.

===============================================================================
 POURQUOI CETTE EXPERIENCE, ET CE QU'ELLE ATTAQUE
===============================================================================

Le banc d'empoisonnement a montre qu'une repetition fabrique de la confiance :
trois fois un mensonge bat une verite dite une fois, et le `z` MONTE pendant que
ca arrive. Le controle a chronologie melangee a montre pourquoi : le score
mesure si la trace est d'accord AVEC ELLE-MEME, pas si elle est d'accord avec
le monde.

Ces deux resultats ont une consequence qu'aucun des deux ne teste. Si deux
instances s'alimentent l'une l'autre, chacune devient la source de l'autre, et
il n'existe plus aucune ancre exterieure. La repetition n'a alors plus besoin
d'un attaquant : la BOUCLE la produit toute seule.

C'est la question posee ici, et elle est mesurable sans un seul jeton :

    une faussete introduite UNE fois, dans UNE des deux memoires, devient-elle
    unanime et confiante dans les deux ?

===============================================================================
 LE PROTOCOLE
===============================================================================

Le monde enonce 18 faits, a A seulement. B ne connait rien du monde. On glisse
UNE faussete dans B, une seule, sur une paire que le monde a deja tranchee.

Puis on ferme la porte. A chaque tour, chacune interroge l'autre sur toutes les
paires qu'elle connait, et APPREND ce que l'autre repond quand l'autre repond
au-dessus de la porte. Rien d'autre n'entre. Le monde ne parle plus.

On mesure a chaque tour :

    accord        les deux repondent-elles la meme chose
    juste         cette reponse est-elle celle du MONDE
    contaminee    est-ce la faussete introduite au depart
    z median      la confiance pendant que tout cela se passe

Le resultat grave attendu etait : accord qui monte, juste qui descend, z qui
monte. Ce n'est PAS ce qui arrive, et le vrai mecanisme est plus interessant.

MESURE le 07/09/2026. Au tour 1, A dit la verite a z 17,7 et B dit la faussete
a z 47,0 : le moins informe est le plus sur, son magasin etant plus petit, le
vainqueur s'y detache mieux. Apres l'echange, ni l'une ni l'autre ne repond.
Les deux affirmations opposees s'annulent, le vainqueur ne se detache plus du
lot, la porte se ferme, et la paire reste muette des deux cotes a tous les
tours suivants. A la savait, A avait raison, et il ne peut plus jamais
repondre. Une ERASURE, pas une corruption, et rien ne signale la perte.

⚠ CE QUE CE BANC NE DIT PAS. Deux instances ne se parlent pas toutes seules en
production ; il faut que quelqu'un les cable ainsi. Ce banc mesure ce que coute
ce cablage, pas une pente naturelle. Et le monde ici est synthetique : la
faussete est vraie ou fausse par construction, ce qui est un luxe qu'aucun
deploiement n'a.

    python chambre_echo.py            # hors ligne, zero jeton
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
from datetime import datetime, timezone

_JOUR = 86400.0


def _memoire(dim: int, horloge: dict):
    extra = os.environ.get("HOLOMEM_PATH")
    if extra and extra not in sys.path:
        sys.path.insert(0, extra)
    from holomem import HolographicMemory  # noqa: PLC0415
    return HolographicMemory(dim=dim, now_fn=lambda: horloge["t"])


_SUJETS = ("alice", "bruno", "chantal", "david", "elise", "farid")
_RELATIONS = ("travaille_a", "habite_a", "conduit_une")
_OBJETS = ("lyon", "nantes", "brest", "dijon", "rennes", "amiens",
           "renault", "peugeot", "fiat", "volvo")


def _monde() -> dict:
    """La verite, posee une fois pour toutes. 18 faits."""
    v, k = {}, 0
    for s in _SUJETS:
        for r in _RELATIONS:
            v[(s, r)] = _OBJETS[k % len(_OBJETS)]
            k += 1
    return v


def un_tour(dim: int, tours: int, z_gate: float, ts: float) -> list[dict]:
    horloge = {"t": ts}
    A = _memoire(dim, horloge)
    B = _memoire(dim, horloge)
    monde = _monde()

    # Le monde parle a A, et seulement a A.
    for (s, r), o in monde.items():
        A.learn(s, r, o, created_ts=horloge["t"])

    # B recoit UNE faussete, sur une paire que le monde a deja tranchee, plus
    # de quoi remplir son vivier : sans au moins trois objets distincts la porte
    # de B rend `inf` et repond a tout, ce qui melangerait deux defauts.
    paire_menteuse = ("alice", "travaille_a")
    faux_objet = "amiens" if monde[paire_menteuse] != "amiens" else "volvo"
    B.learn(*paire_menteuse, faux_objet, created_ts=horloge["t"])
    for i, (s, r) in enumerate(list(monde)[1:6]):
        B.learn(s, r, monde[(s, r)], created_ts=horloge["t"])

    lignes = []
    for tour in range(tours + 1):
        # Mesure AVANT d'echanger, pour que le tour 0 soit l'etat initial.
        accord = juste = contaminee = annulee = 0
        zs = []
        for (s, r), verite in monde.items():
            va, za = A.query_gated(s, r, z_gate=z_gate)
            vb, zb = B.query_gated(s, r, z_gate=z_gate)
            for z in (za, zb):
                if z not in (None,) and z < 1e9:
                    zs.append(float(z))
            if va is not None and va == vb:
                accord += 1
            if va is not None and va == verite:
                juste += 1
            if (s, r) == paire_menteuse and faux_objet in (va, vb):
                contaminee += 1
            if (s, r) == paire_menteuse:
                # LE cas. Deux affirmations opposees ne laissent pas un
                # gagnant : elles s'annulent, le vainqueur ne se detache plus
                # du lot, et la porte se ferme. Des deux cotes, definitivement.
                annulee = int(va is None and vb is None)
        lignes.append({"tour": tour, "accord": accord, "juste": juste,
                       "contaminee": contaminee, "annulee": annulee,
                       "n": len(monde),
                       "z_median": round(st.median(zs), 3) if zs else None})
        if tour == tours:
            break

        # On ferme la porte : chacune apprend de l'autre, et de rien d'autre.
        horloge["t"] += _JOUR
        echanges = []
        for source, cible in ((A, B), (B, A)):
            for (s, r) in monde:
                val, _z = source.query_gated(s, r, z_gate=z_gate)
                if val is not None:
                    echanges.append((cible, s, r, val))
        for cible, s, r, val in echanges:
            cible.learn(s, r, val, created_ts=horloge["t"])
    return lignes


def temoin_sans_boucle(dim: int, tours: int, z_gate: float, ts: float) -> dict:
    """A seule, meme horloge, meme nombre de jours, AUCUN echange.

    Sans ce temoin on ne peut rien dire : une justesse qui baisse dans la boucle
    pourrait venir du temps qui passe, pas de la boucle. Il donne le
    denominateur de tout le reste.
    """
    horloge = {"t": ts}
    A = _memoire(dim, horloge)
    monde = _monde()
    for (s, r), o in monde.items():
        A.learn(s, r, o, created_ts=horloge["t"])
    horloge["t"] += tours * _JOUR
    juste = 0
    for (s, r), verite in monde.items():
        val, _ = A.query_gated(s, r, z_gate=z_gate)
        if val == verite:
            juste += 1
    return {"juste": juste, "n": len(monde)}


def _sortie_utf8() -> None:
    """Sous Windows, une sortie REDIRIGEE retombe en cp1252 et le premier
    caractere non-ASCII tue le banc apres qu'il a tout calcule.

    Constate le 12/09/2026 : `python chambre_echo.py > sortie.txt` mourait sur
    un `⚠`, UnicodeEncodeError, alors que la meme commande sans
    redirection passait. Un banc qui ne survit pas a un `>` est un banc que
    personne ne peut archiver.
    """
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _sortie_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dim", type=int, default=2048)
    ap.add_argument("--tours", type=int, default=8)
    ap.add_argument("--z", type=float, default=4.0)
    ap.add_argument("--out", default="results-chambre-echo.json")
    a = ap.parse_args()

    ts = datetime(2026, 9, 7, tzinfo=timezone.utc).timestamp()
    print(f"d={a.dim}, porte z >= {a.z}, {a.tours} tours. Hors ligne, zero jeton.")
    print("Le monde parle a A une seule fois. B part avec UNE faussete.")
    print("Ensuite elles n'entendent plus que l'autre.\n")

    lignes = un_tour(a.dim, a.tours, a.z, ts)
    hdr = f"{'tour':>5}{'accord':>9}{'juste':>8}{'faussete tenue':>17}{'z median':>11}"
    print(hdr); print("-" * len(hdr))
    for l in lignes:
        z = "-" if l["z_median"] is None else f"{l['z_median']:.2f}"
        print(f"{l['tour']:>5}{l['accord']:>4}/{l['n']:<4}{l['juste']:>3}/{l['n']:<4}"
              f"{l['contaminee']:>13}/1  {z:>9}")

    d, f = lignes[0], lignes[-1]
    t = temoin_sans_boucle(a.dim, a.tours, a.z, ts)
    print()
    print(f"Temoin SANS boucle, A seule apres {a.tours} jours : "
          f"juste {t['juste']}/{t['n']}")
    print(f"Dans la boucle, meme duree                     : "
          f"juste {f['juste']}/{f['n']}")
    print()
    print("⚠ L'ACCORD DU TOUR 0 NE SE COMPARE A RIEN. B part presque vide par")
    print("  construction, donc l'accord ne peut que monter. Le seul chiffre qui")
    print("  se lit est la JUSTESSE, contre le temoin sans boucle ci-dessus.")
    print()
    cout = t["juste"] - f["juste"]
    if f["contaminee"]:
        print(f"VERDICT : la faussete introduite UNE fois a survecu {a.tours} tours.")
    elif f["annulee"]:
        print("VERDICT : NI l'une NI l'autre. Les deux affirmations opposees se")
        print("sont ANNULEES des le premier echange, et la paire est muette des")
        print("deux cotes a tous les tours suivants. La faussete n'a pas gagne,")
        print("mais la verite non plus : A la SAVAIT, A avait RAISON, et apres un")
        print("seul echange avec B il ne peut plus jamais repondre.")
        print()
        print(f"C'est la tout le cout de la boucle : {cout} fait sur {t['n']},")
        print("et c'est une ERASURE, pas une corruption. Une seule instance qui")
        print("contredit suffit a faire taire definitivement ce que l'autre")
        print("connaissait, sans que rien ne signale la perte.")
    elif cout > 0:
        print(f"VERDICT : la boucle coute {cout} fait(s) sur {t['n']}.")
    else:
        print("VERDICT : la boucle ne coute rien de mesurable sur ce corpus.")

    zs = [l["z_median"] for l in lignes if l["z_median"] is not None]
    if zs:
        print()
        print(f"Et le chiffre qui compte : le z median va de {min(zs):.2f} a "
              f"{max(zs):.2f} sur toute la duree.")
        print("Il ne dit donc RIEN de l'etat de la boucle. Une memoire enfermee")
        print("avec une autre est aussi sure d'elle qu'une memoire qui parle au")
        print("monde, et rien dans sa sortie ne permet de les distinguer.")

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"dim": a.dim, "tours": a.tours, "z_gate": a.z,
                   "lignes": lignes}, fh, indent=2, ensure_ascii=False)
    print(f"\nEcrit dans {a.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
