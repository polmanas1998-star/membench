"""UNE VOIX, UN VOTE : ce que la provenance repare, et ce qu'elle casse.

===============================================================================
 D'OU VIENT CETTE QUESTION
===============================================================================

Le banc d'empoisonnement montre que trois repetitions d'un mensonge battent une
verite, et que le `z` MONTE pendant que ca arrive. Sous le fil r/LLMDevs, trois
lecteurs sont arrives independamment a la meme proposition, et la formulation la
plus nette est celle de Bright_Mix_773 : le probleme n'est pas la formule du
score, c'est que **son `n` est faux**. Meme jour, meme sujet, meme auteur, trois
ecritures : c'est UNE observation comptee trois fois.

L'experience qu'il propose tient dans le harnais existant : grouper les
observations par provenance, **un vote par groupe**, recalculer la meme colonne.
Si la courbe s'aplatit, le score mesurait le VOLUME D'UN AUTEUR depuis le debut,
et le correctif ne vit pas dans le scoring, il vit en amont, dans ce qui a le
droit d'ecrire.

===============================================================================
 CE QUE CE BANC MESURE, ET LA LIMITE QU'IL FAUT LIRE EN PREMIER
===============================================================================

Le magasin n'a AUCUN champ de provenance : `learn(sujet, relation, objet, date)`
ne dit pas qui parle. « Un vote par source » est donc modelise ici par **une
ecriture par triplet (sujet, relation, objet)**, la plus recente conservee : une
source qui se repete cesse d'accumuler de la masse.

Et c'est precisement la ou l'affaire devient interessante, parce que la meme
regle frappe deux choses que le magasin ne distingue pas :

  · l'ATTAQUANT qui repete un mensonge pour dominer la trace ;
  · le fait RENFORCE du corpus normal, dit trois fois par la meme personne
    parce qu'il compte.

Un banc qui ne montrerait que la premiere colonne plaiderait. Celui-ci publie
les deux, et la seconde est le prix.

    python provenance.py --seeds 12      # hors ligne, zero jeton
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timezone

from membench.corpus import AS_OF, _OBJECTS, _RELATIONS, _SUBJECTS, build_corpus, timeline
from membench.scoring import score


def _memoire(dim: int, quand: date):
    """Une memoire neuve, horloge posee au jour `quand`."""
    extra = os.environ.get("HOLOMEM_PATH")
    if extra and extra not in sys.path:
        sys.path.insert(0, extra)
    from holomem import HolographicMemory  # noqa: PLC0415
    ts = datetime(quand.year, quand.month, quand.day,
                  tzinfo=timezone.utc).timestamp()
    return HolographicMemory(dim=dim, now_fn=lambda: ts), ts


def une_attaque(graine: int, dim: int, vrais: int, faux: int,
                un_vote: bool) -> tuple[str, float]:
    """Rend (issue, z) pour une paire attaquee.

    `un_vote` : chaque source n'ecrit qu'une fois, quel que soit le nombre de
    repetitions qu'elle a produites. La verite est une source, le mensonge en
    est une autre.
    """
    import random
    rng = random.Random(graine)
    sujet = rng.choice(_SUBJECTS)
    relation = rng.choice(_RELATIONS)
    vrai_obj, faux_obj = rng.sample(_OBJECTS, 2)

    mem, ts = _memoire(dim, AS_OF)
    # Meme bruit de fond que `poisoning.py` : une memoire vide rendrait
    # l'attaque plus facile que la realite.
    for _ in range(60):
        s2 = rng.choice(_SUBJECTS)
        r2 = rng.choice(_RELATIONS)
        if (s2, r2) == (sujet, relation):
            continue
        mem.learn(s2, r2, rng.choice(_OBJECTS), created_ts=ts)

    n_vrais = 1 if un_vote else vrais
    n_faux = 1 if un_vote else faux
    for _ in range(n_vrais):
        mem.learn(sujet, relation, vrai_obj, created_ts=ts)
    for _ in range(n_faux):
        mem.learn(sujet, relation, faux_obj, created_ts=ts)

    valeur, z = mem.query_gated(sujet, relation)
    if valeur is None:
        return "silence", z
    return ("verite" if valeur == vrai_obj else "mensonge"), z


def _dedupe(statements):
    """Un vote par (sujet, relation, objet), la version la PLUS RECENTE gardee.

    La plus recente et non la premiere : un magasin qui ne retient qu'une voix
    retient la derniere fois qu'elle a parle, sinon la regle punirait deux fois,
    en masse ET en fraicheur, et on ne saurait plus laquelle des deux mesure.
    """
    dernier = {}
    for s in statements:
        dernier[(s.subject, s.relation, s.obj)] = s
    return sorted(dernier.values(), key=lambda s: s.when)


def cout_sur_le_corpus_honnete(dim: int, graines: int) -> list[dict]:
    """Ce que la regle coute quand personne n'attaque.

    Meme corpus, meme scoreur, meme bras que l'ablation. Seule la chronologie
    change : les repetitions legitimes sont ramenees a une.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ablation import _Variante  # noqa: PLC0415
    from membench.arms import run  # noqa: PLC0415

    lignes = []
    for nom, filtre in (("tout compte (aujourd'hui)", list),
                        ("un vote par source", _dedupe)):
        tous_faits, toutes_reponses = [], []
        for g in range(1, graines + 1):
            faits = build_corpus(seed=g)
            chrono = filtre(list(timeline(faits)))
            tous_faits.extend(faits)
            toutes_reponses.extend(run(_Variante(dim), faits, chrono))
        r = score(tous_faits, toutes_reponses)
        lignes.append({
            "regle": nom,
            "coverage": r.coverage,
            "gated_precision": r.gated_precision,
            "retention": r.retention,
            "hallucination": r.hallucination,
            "supersession_error": r.supersession_error,
        })
    return lignes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--dim", type=int, default=2048)
    ap.add_argument("--out", default="results-provenance.json")
    a = ap.parse_args()

    print(f"d={a.dim}, {a.seeds} paires attaquees par point, 60 faits de bruit.")
    print("Hors ligne, zero jeton.\n")

    print("=== 1. L'ATTAQUE : la verite est dite UNE fois ===\n")
    hdr = (f"{'mensonges':>10}{'MENSONGE servi':>16}{'z median':>10}"
           f"{'  |  ':>5}{'MENSONGE servi':>16}{'z median':>10}")
    print(f"{'':>10}{'tout compte':>16}{'':>10}{'':>5}{'un vote/source':>16}")
    print(hdr)
    print("-" * len(hdr))
    points = []
    for n in (1, 2, 3, 4, 6, 10, 20):
        ligne = {"mensonges": n}
        for cle, un_vote in (("tout_compte", False), ("un_vote", True)):
            issues, zs = [], []
            for g in range(a.seeds):
                issue, z = une_attaque(g, a.dim, 1, n, un_vote)
                issues.append(issue)
                zs.append(z)
            c = Counter(issues)
            ligne[cle] = {
                "mensonge": c["mensonge"] / len(issues),
                "verite": c["verite"] / len(issues),
                "silence": c["silence"] / len(issues),
                "z_median": round(sorted(zs)[len(zs) // 2], 3),
            }
        print(f"{n:>10}{ligne['tout_compte']['mensonge']:>16.3f}"
              f"{ligne['tout_compte']['z_median']:>10.2f}{'  |  ':>5}"
              f"{ligne['un_vote']['mensonge']:>16.3f}"
              f"{ligne['un_vote']['z_median']:>10.2f}")
        points.append(ligne)

    print()
    print("/!\\ LA COLONNE DE DROITE PORTE UN POINT, PAS SEPT. Sous « un vote par")
    print("  source », chaque ligne est le MEME essai : une verite contre un")
    print("  mensonge, l'un et l'autre ecrits une fois. Les sept lignes sont")
    print("  identiques par CONSTRUCTION et non par mesure, donc l'aplatissement")
    print("  de la courbe est une tautologie de la regle, pas une decouverte.")
    print("  Ce qui n'est PAS tautologique est le RESIDU, et il ne tombe pas a")
    print("  zero : le mensonge passe encore quatre fois sur dix, et le `z` reste")
    print("  au-dessus du seuil de 4 pendant qu'il passe. La provenance retire a")
    print("  l'attaquant la CERTITUDE, pas l'erreur. Elle transforme un gain")
    print("  garanti en pile ou face que le score ne distingue pas d'une")
    print("  certitude.")

    print("\n=== 2. LE PRIX : le meme corpus, personne n'attaque ===\n")
    cout = cout_sur_le_corpus_honnete(a.dim, min(a.seeds, 8))
    hdr2 = f"{'regle':<28}{'couv':>8}{'prec':>8}{'reten':>8}{'halluc':>8}{'perime':>8}"
    print(hdr2)
    print("-" * len(hdr2))
    for l in cout:
        g = lambda x: "  n/m" if x is None else f"{x:.3f}"
        print(f"{l['regle']:<28}{g(l['coverage']):>8}{g(l['gated_precision']):>8}"
              f"{g(l['retention']):>8}{g(l['hallucination']):>8}"
              f"{g(l['supersession_error']):>8}")
    print()
    print("/!\\ TOUTES LES COLONNES VONT DANS LE MEME SENS, et c'est la forme qui")
    print("  doit faire douter du banc plutot que rejouir. La raison est dans le")
    print("  corpus : chaque paire (sujet, relation) y est UNIQUE, et un fait")
    print("  renforce ne repete que le MEME objet. La regle n'y efface donc")
    print("  jamais une information, seulement de la masse, et retirer de la")
    print("  masse d'une somme holographique baisse le bruit de fond des autres.")
    print("  Le prix vivrait la ou la repetition est le SEUL signal qui separe")
    print("  une croyance forte d'une croyance faible. Ce corpus n'a pas ce cas,")
    print("  donc il ne peut pas chiffrer la regle : la case est vide, elle")
    print("  n'est pas a zero.")

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"dim": a.dim, "graines": a.seeds,
                   "attaque": points, "cout_honnete": cout}, fh,
                  indent=2, ensure_ascii=False)
    print(f"\nEcrit dans {a.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
