# -*- coding: utf-8 -*-
"""LA CHAMBRE CLOSE : ce que la memoire fait quand son ENVIRONNEMENT ment.

===============================================================================
 CE QUE CE BANC MESURE, ET CE QU'IL NE MESURE PAS
===============================================================================

Il ne mesure PAS une evasion. La couche n'a ni but, ni outil, ni action sur le
monde : elle repond ou elle se tait. Il n'y a rien a « sortir » d'une piece.

Il mesure la seule question qui vaille pour un composant qu'on met en
production : **quand la piece est truquee, est-ce qu'il CRIE ou est-ce qu'il
MENT ?** Tous les autres bancs de ce depot supposent un environnement sain, une
horloge juste, un disque intact, une capacite respectee. Aucun ne demande ce
qu'il advient quand cette hypothese tombe.

Le verdict de chaque piece est binaire et il est toujours le meme :

    BRUYANT   la couche refuse, ou leve, ou repond avec un z sous le seuil.
              L'appelant apprend qu'il se passe quelque chose.
    SILENCIEUX  elle repond, au-dessus du seuil, et rien dans la reponse ne
              dit que la piece etait truquee. C'est le seul resultat grave.

===============================================================================
 LES PIECES, ET POURQUOI CELLES-LA
===============================================================================

Chacune correspond a une panne qui arrive vraiment, pas a une curiosite.

  horloge reculee   NTP corrige en arriere, un fuseau mal pose, un conteneur
                    qui demarre avec une horloge fausse. `effective_weight`
                    borne l'age a zero, donc un temps qui recule rend tous les
                    faits NEUFS. Ce depot a deja paye deux fois une horloge de
                    datacenter lue comme une horloge humaine.
  horloge avancee   la machine saute de dix ans, ou le service dort et reprend.
                    Tout passe sous le plancher de poids et sort de la trace.
  magasin minuscule un service qui vient de demarrer, ou dont la purge RGPD a
                    tout efface. Le vivier de candidats tombe sous trois.
  saturation        dix fois la capacite du vecteur. Le regime ou la somme
                    holographique n'est plus qu'un bruit.
  trace corrompue   un NaN, une page memoire abimee, un fichier tronque.

Le TEMOIN SAIN est une piece aussi, et c'est la plus importante : si la couche
se tait la ou tout va bien, le banc mesure sa propre severite et rien d'autre.

    python chambre_close.py            # hors ligne, zero jeton
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

_JOUR = 86400.0


def _memoire(dim: int, ts: float):
    extra = os.environ.get("HOLOMEM_PATH")
    if extra and extra not in sys.path:
        sys.path.insert(0, extra)
    from holomem import HolographicMemory  # noqa: PLC0415
    horloge = {"t": ts}
    mem = HolographicMemory(dim=dim, now_fn=lambda: horloge["t"])
    return mem, horloge


#: Un petit monde coherent : assez d'objets distincts pour que la porte ait de
#: quoi douter, sauf dans la piece qui retire justement cela.
_SUJETS = ("alice", "bruno", "chantal", "david", "elise", "farid")
_RELATIONS = ("travaille_a", "habite_a", "conduit_une")
_OBJETS = ("lyon", "nantes", "brest", "dijon", "rennes", "amiens",
           "renault", "peugeot", "fiat", "volvo")


def _peupler(mem, ts: float, n_sujets: int = 6, n_objets: int = 10) -> list:
    """Apprend un fait par (sujet, relation), et rend la verite de reference."""
    verite = []
    k = 0
    for s in _SUJETS[:n_sujets]:
        for r in _RELATIONS:
            o = _OBJETS[k % n_objets]
            k += 1
            mem.learn(s, r, o, created_ts=ts)
            verite.append((s, r, o))
    return verite


def _interroger(mem, verite, z_gate: float) -> dict:
    """Pose deux familles de questions et compte ce qui sort.

    CONNUES : des faits appris. Une reponse juste est bonne, le silence est un
    cout, une reponse FAUSSE est le defaut grave.
    JAMAIS DITES : des paires que personne n'a enoncees. Le silence est la
    SEULE bonne reponse.
    """
    justes = faux = muettes = 0
    for s, r, o in verite:
        try:
            val, z = mem.query_gated(s, r, z_gate=z_gate)
        except Exception:                                        # noqa: BLE001
            return {"leve": True}
        if val is None:
            muettes += 1
        elif val == o:
            justes += 1
        else:
            faux += 1

    inventees = 0
    z_max = 0.0
    absentes = [(s, "porte_le_nom", "x") for s in _SUJETS[:6]]
    for s, r, _ in absentes:
        try:
            val, z = mem.query_gated(s, r, z_gate=z_gate)
        except Exception:                                        # noqa: BLE001
            return {"leve": True}
        if val is not None:
            inventees += 1
            z_max = max(z_max, z if math.isfinite(z) else 1e9)
    return {"leve": False, "justes": justes, "faux": faux, "muettes": muettes,
            "connues": len(verite), "inventees": inventees,
            "absentes": len(absentes), "z_max_invente": z_max}


# ── Les pieces ───────────────────────────────────────────────────────────────

def piece_temoin(dim, ts, z_gate):
    mem, _ = _memoire(dim, ts)
    v = _peupler(mem, ts)
    return _interroger(mem, v, z_gate)


def piece_horloge_reculee(dim, ts, z_gate):
    """On apprend, puis l'horloge RECULE de 60 jours."""
    mem, h = _memoire(dim, ts)
    v = _peupler(mem, ts)
    h["t"] = ts - 60 * _JOUR
    return _interroger(mem, v, z_gate)


def piece_horloge_avancee(dim, ts, z_gate):
    """On apprend, puis l'horloge SAUTE de dix ans."""
    mem, h = _memoire(dim, ts)
    v = _peupler(mem, ts)
    h["t"] = ts + 3650 * _JOUR
    return _interroger(mem, v, z_gate)


def piece_magasin_minuscule(dim, ts, z_gate):
    """Deux objets distincts en tout : le vivier tombe sous trois."""
    mem, _ = _memoire(dim, ts)
    v = _peupler(mem, ts, n_sujets=2, n_objets=2)
    return _interroger(mem, v, z_gate)


def piece_saturation(dim, ts, z_gate):
    """Dix fois plus de faits que la capacite raisonnable du vecteur."""
    mem, _ = _memoire(dim, ts)
    v = _peupler(mem, ts)
    import random
    rng = random.Random(7)
    for i in range(dim * 10 // 64):
        mem.learn(f"bruit{i}", rng.choice(_RELATIONS), rng.choice(_OBJETS),
                  created_ts=ts)
    return _interroger(mem, v, z_gate)


def piece_trace_corrompue(dim, ts, z_gate):
    """Un NaN dans la trace, comme une page memoire abimee."""
    import numpy as np                                           # noqa: PLC0415
    mem, _ = _memoire(dim, ts)
    v = _peupler(mem, ts)
    t = mem.trace
    t[0] = np.nan
    try:
        mem._cache = t          # noqa: SLF001 - on abime volontairement
    except Exception:                                            # noqa: BLE001
        pass
    return _interroger(mem, v, z_gate)


PIECES = [
    ("temoin sain", piece_temoin),
    ("horloge reculee 60 j", piece_horloge_reculee),
    ("horloge avancee 10 ans", piece_horloge_avancee),
    ("magasin minuscule", piece_magasin_minuscule),
    ("saturation x10", piece_saturation),
    ("trace corrompue (NaN)", piece_trace_corrompue),
]


def verdict(nom: str, r: dict) -> str:
    """BRUYANT ou SILENCIEUX. Une piece truquee doit s'entendre."""
    if r.get("leve"):
        return "BRUYANT (leve)"
    if nom == "temoin sain":
        # Ici la seule faute est de se taire ou de mentir alors que tout va bien.
        return "SAIN" if r["justes"] and not r["inventees"] else "TEMOIN CASSE"
    if r["inventees"]:
        return "SILENCIEUX"
    if r["faux"]:
        return "SILENCIEUX"
    if r["muettes"] == r["connues"]:
        return "BRUYANT (muet)"
    return "TIENT"


def detention(dim: int, ts: float, z_gate: float) -> list[dict]:
    """La MEME memoire, interrogee de plus en plus tard. Sans rien reapprendre.

    Pourquoi simuler plutot qu'attendre : la demi-vie et le seuil d'oubli sont
    des fonctions de l'horloge, et l'horloge est injectee. Attendre un mois
    reel donnerait le meme point que `now + 30 jours`, en un mois. Ce qu'un
    sejour reel apporterait en plus n'est PAS le temps : c'est la fuite de
    memoire, la croissance du disque, le processus tue et relance, l'etat
    efface au deploiement. Rien de tout cela ne se simule ici, et ce banc ne
    pretend pas le couvrir.

    Ce qu'on cherche est le moment ou la couche cesse de savoir ET la maniere
    dont elle cesse : se taire est propre, inventer ne l'est pas.
    """
    jalons = [("depart", 0), ("1 semaine", 7), ("1 mois", 30), ("45 j (demi-vie)", 45),
              ("90 j", 90), ("111 j (seuil)", 111), ("6 mois", 182),
              ("1 an", 365), ("10 ans", 3650)]
    out = []
    for nom, jours in jalons:
        mem, h = _memoire(dim, ts)
        v = _peupler(mem, ts)
        h["t"] = ts + jours * _JOUR
        r = _interroger(mem, v, z_gate)
        out.append({"jalon": nom, "jours": jours, **r})
    return out


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
    ap.add_argument("--z", type=float, default=4.0)
    ap.add_argument("--out", default="results-chambre-close.json")
    a = ap.parse_args()

    ts = datetime(2026, 9, 7, tzinfo=timezone.utc).timestamp()
    print(f"d={a.dim}, porte z >= {a.z}. Hors ligne, zero jeton.\n")
    hdr = (f"{'piece':<24}{'justes':>8}{'faux':>7}{'muettes':>9}"
           f"{'inventees':>11}{'z invente':>11}  verdict")
    print(hdr); print("-" * (len(hdr) + 8))

    lignes = []
    for nom, fn in PIECES:
        r = fn(a.dim, ts, a.z)
        v = verdict(nom, r)
        if r.get("leve"):
            print(f"{nom:<24}{'-':>8}{'-':>7}{'-':>9}{'-':>11}{'-':>11}  {v}")
        else:
            zi = r["z_max_invente"]
            ztxt = "-" if not r["inventees"] else (
                "inf" if zi >= 1e9 else f"{zi:.2f}")
            print(f"{nom:<24}{r['justes']:>8}{r['faux']:>7}{r['muettes']:>9}"
                  f"{r['inventees']:>3}/{r['absentes']:<7}{ztxt:>11}  {v}")
        lignes.append({"piece": nom, "verdict": v, **r})

    print()
    print("=== DETENTION LONGUE : la meme memoire, interrogee plus tard ===")
    print()
    hdr2 = f"{'apres':<18}{'justes':>8}{'muettes':>9}{'inventees':>11}{'z invente':>11}"
    print(hdr2); print("-" * len(hdr2))
    detenu = detention(a.dim, ts, a.z)
    for d in detenu:
        zi = d.get("z_max_invente", 0)
        ztxt = "-" if not d.get("inventees") else ("inf" if zi >= 1e9 else f"{zi:.2f}")
        print(f"{d['jalon']:<18}{d['justes']:>8}{d['muettes']:>9}"
              f"{d['inventees']:>3}/{d['absentes']:<7}{ztxt:>11}")

    silencieuses = [l["piece"] for l in lignes if l["verdict"] == "SILENCIEUX"]
    print()
    print("Lire : « inventees » compte les reponses donnees sur des paires que")
    print("PERSONNE n'a enoncees. Le silence y est la seule bonne reponse, et un")
    print("`z` au-dessus du seuil pendant qu'on invente est le defaut grave :")
    print("l'appelant n'a aucun moyen d'apprendre que la piece etait truquee.")
    print()
    if silencieuses:
        print(f"PIECES SILENCIEUSES : {len(silencieuses)} sur {len(PIECES)} -> "
              + ", ".join(silencieuses))
    else:
        print("Aucune piece silencieuse. A verifier par mutation avant d'y croire.")

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"dim": a.dim, "z_gate": a.z, "pieces": lignes,
                   "detention": detenu}, fh,
                  indent=2, ensure_ascii=False)
    print(f"\nEcrit dans {a.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
