"""Cout par REPONSE JUSTE, sur un echantillon DIMENSIONNE POUR TENIR DANS UN JOUR.

Le cout par tour se truque en se taisant : un bras qui refuse la moitie des
questions ne depense rien sur cette moitie et affiche une moyenne flatteuse.
Le cout par reponse juste ne se truque pas, parce que le silence n'y met aucun
numerateur.

CE QUE CE FICHIER CORRIGE, ET CE QUE CA A COUTE
-----------------------------------------------
La campagne du 06/09 a pose les 104 questions du corpus a quatre bras, dans
l'ordre D+, C, A, B. Elle a rendu trois bras et a perdu le quatrieme :

    17:45  seed1/A   termine
    17:50  seed1/B : plafond quotidien atteint, 198 839 consommes -> sommeil
    18:50  seed1/B : plafond quotidien atteint, 199 335 consommes -> sommeil

Une heure de siestes pour zero question. Deux defauts, tous deux reparables
ici, aucun des deux dans le code de mesure :

1. LE BRAS LE PLUS CHER ET LE SEUL INCONNU PASSAIT EN DERNIER. Quand le seau
   se vide, on perd ce qui RESTE a faire. On perdait donc exactement le seul
   chiffre que la campagne existait pour produire, et on gardait trois bras
   deja mesures. **B passe maintenant en premier**, les autres ensuite par
   cout croissant, pour qu'un plafond atteint en chemin coute le moins
   d'information possible.

2. AUCUN DEVIS N'ETAIT FAIT AVANT DE DEPENSER. Le cout par question de chaque
   bras etait connu, le plafond aussi ; personne n'a fait la multiplication.
   Elle tient en une ligne et elle dit non : 104 questions x 6 831 jetons de
   reservation = 710 000, soit trois jours et demi de budget. Le devis est
   maintenant IMPRIME AVANT le premier appel, et la campagne REFUSE de partir
   quand il ne tient pas.

POURQUOI UN ECHANTILLON PROPORTIONNEL, ET PAS EQUILIBRE
--------------------------------------------------------
On pourrait prendre le meme nombre de questions par genre. Ce serait plus
precis genre par genre, et ca rendrait les taux globaux incomparables avec
ceux du corpus complet : un corpus a 21 % d'absents ne se resume pas par un
echantillon a 17 % d'absents.

L'allocation est donc PROPORTIONNELLE au corpus, arrondie au plus fort reste.
Consequence directe et voulue : les trois bras deja mesures sur 104 questions
deviennent un TEMOIN. Si D+ retrouve une couverture proche de 0,510 sur
l'echantillon, l'echantillon est representatif, et le chiffre de B, mesure
pour la premiere fois, herite de cette credibilite. S'il s'en ecarte, c'est
l'echantillon qu'il faut lire avant le bras.

    python cost_probe.py --devis         # ce que ca couterait, sans depenser
    python cost_probe.py                 # 40 questions, tient dans un jour
    python cost_probe.py --questions 24  # plus court, pour un budget entame
"""
from __future__ import annotations

import argparse
import json
import random
from typing import Sequence

from membench.arms import run
from membench.corpus import Fact, build_corpus, candidates, timeline
from membench.providers import DailyBudgetExhausted, GroqModel
from membench.real_arms import (DermiozGroundedArm, FullContextArm,
                                RetrievalArm, StatelessArm)
from membench.scoring import TPM_CEILING, score

#: Le plafond quotidien du compte gratuit. Il n'apparait dans AUCUN en-tete de
#: reponse, seulement dans le corps d'un 429, et la fenetre est GLISSANTE : le
#: compteur ne retombe pas a minuit, il perd ce qui sort des vingt-quatre
#: dernieres heures, quelques centaines de jetons a l'heure.
TPD = 200_000

#: Jetons de RESERVATION par question, mesures le 06/09 sur les 104 questions
#: du corpus (`results-cost-seed1.json`). B vient de la campagne interrompue.
COUT_PAR_QUESTION = {"B": 3483.0, "D+": 665.5, "A": 1280.1, "C": 1402.9}

#: DEUX COMPTABILITES, et les confondre coute une journee. Le plafond par
#: MINUTE debite `prompt + max_tokens`, ce que `tokens_total` rapporte ici. Le
#: plafond par JOUR debite les jetons REELLEMENT produits. Le facteur se derive
#: de la campagne du 06/09 plutot que de se supposer : trois bras y ont reserve
#: 348 244 jetons, le compteur quotidien en a retenu 198 839.
RESERVATION_MESUREE = 69_213 + 145_899 + 133_132
REEL_MESURE = 198_839
FACTEUR_REEL = RESERVATION_MESUREE / REEL_MESURE

#: L'ORDRE D'EXECUTION EST UNE DECISION DE CONCEPTION. B d'abord parce qu'il
#: est le seul inconnu et le plus cher ; les autres par cout croissant, pour
#: qu'un plafond atteint laisse le maximum de bras termines derriere lui.
ORDRE = ("B", "D+", "A", "C")

NOMS = {"A": "A modele seul", "B": "B historique complet",
        "C": "C recherche top-k", "D+": "D+ couche puis modele"}


def echantillon(facts: Sequence[Fact], n: int, seed: int = 1) -> list[Fact]:
    """Un sous-echantillon PROPORTIONNEL aux genres du corpus.

    Arrondi au plus fort reste : chaque genre recoit sa part entiere, puis les
    places qui restent vont aux genres dont la part fractionnaire est la plus
    grande. C'est la regle qui garde la somme EXACTE tout en restant au plus
    pres des proportions, et elle est deterministe a graine fixee.

    Demander plus de questions que le corpus n'en contient LEVE, au lieu de
    rendre le corpus entier en silence. Une premiere version bornait chaque
    genre a sa taille, pour eviter un `ValueError` de `random.sample` a
    mi-campagne. Cette borne etait du code MORT : une part proportionnelle
    vaut `len(genre) * n / total`, qui ne peut depasser `len(genre)` que si
    `n` depasse le corpus. La mutation l'a montre, aucun test ne pouvait
    l'atteindre, et un garde qu'aucune entree ne touche vaut moins qu'un refus
    a l'entree, qui, lui, se declenche.
    """
    if not 0 < n <= len(facts):
        raise ValueError(f"{n} questions demandees, le corpus en a "
                         f"{len(facts)}")

    par_genre: dict[str, list[Fact]] = {}
    for f in facts:
        par_genre.setdefault(f.kind, []).append(f)

    total = len(facts)
    exact = {k: len(v) * n / total for k, v in par_genre.items()}
    part = {k: int(v) for k, v in exact.items()}

    # Les places restantes vont aux plus forts restes. Chaque reste valant
    # moins de 1, il en manque toujours moins qu'il n'y a de genres : une
    # seule passe suffit, sans boucle ni garde de sortie. Le nom du genre
    # departage les egalites, sinon l'echantillon dependrait de l'ordre du
    # dictionnaire.
    reste = sorted(par_genre, key=lambda k: (-(exact[k] - int(exact[k])), k))
    for k in reste[:n - sum(part.values())]:
        part[k] += 1

    rng = random.Random(seed)
    return [y for k in sorted(par_genre)
            for y in rng.sample(par_genre[k], part[k])]


def devis(n: int) -> dict:
    """Ce que la campagne va couter, calcule AVANT le premier appel."""
    reservation = {k: v * n for k, v in COUT_PAR_QUESTION.items()}
    total = sum(reservation.values())
    return {"questions": n, "reservation": total,
            "reel_estime": total / FACTEUR_REEL,
            "part_du_jour": total / FACTEUR_REEL / TPD,
            "par_bras": reservation}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="results-cost-subsample.json")
    ap.add_argument("--oui", action="store_true",
                    help="partir meme si le devis ne tient pas dans le jour")
    ap.add_argument("--devis", action="store_true",
                    help="afficher le devis et l'echantillon, sans depenser")
    a = ap.parse_args()

    f = build_corpus(seed=a.seed)
    tl, pool = list(timeline(f)), candidates(f)
    sample = echantillon(f, a.questions, a.seed)

    genres: dict[str, int] = {}
    for x in sample:
        genres[x.kind] = genres.get(x.kind, 0) + 1
    d = devis(len(sample))

    print(f"{len(sample)} questions sur {len(f)}, echantillon proportionnel, "
          f"graine {a.seed}, d=2048")
    print("  genres : " + ", ".join(
        f"{k} {v}/{sum(1 for y in f if y.kind == k)}"
        for k, v in sorted(genres.items())))
    print("\nDEVIS AVANT DEPENSE, aux couts par question mesures le 06/09 :")
    for nom in ORDRE:
        print(f"  {NOMS[nom]:<24}{d['par_bras'][nom]:>9.0f} jetons reserves")
    print(f"  {'TOTAL':<24}{d['reservation']:>9.0f} reserves, "
          f"{d['reel_estime']:>7.0f} reels estimes")
    print(f"  soit {d['part_du_jour']:.0%} du plafond de "
          + f"{TPD:,} jetons/jour".replace(",", " "))
    if d["part_du_jour"] > 1.0 and not a.oui:
        tient = int(a.questions / d["part_du_jour"])
        print(f"\nCe devis NE TIENT PAS dans une journee. Rien n'a ete "
              f"depense.\nReduisez a --questions {tient}, ou passez --oui "
              f"pour partir quand meme et perdre le dernier bras.")
        return 2
    if d["part_du_jour"] > 0.85:
        print("  Marge etroite : un depassement de 15 % suffit a couper le "
              "dernier bras.")
    if a.devis:
        # Le devis se lit quand le budget est VIDE, la veille de la campagne.
        # Il ne doit toucher ni la cle ni le reseau, sans quoi l'outil qui
        # sert a ne pas depenser depenserait.
        print()
        print("--devis : rien n'a ete depense, aucune cle n'a ete lue.")
        return 0

    m = GroqModel(account="outillage")
    print(f"\ncompte outillage {m.key_fingerprint}, bras dans l'ordre "
          f"{' puis '.join(ORDRE)}\n")
    fabriques = {
        "A": lambda: StatelessArm(m, pool),
        "B": lambda: FullContextArm(m, pool),
        "C": lambda: RetrievalArm(m, pool),
        "D+": lambda: DermiozGroundedArm(m, pool, dim=2048),
    }

    hdr = (f"{'bras':<24}{'couv':>7}{'prec':>7}{'halluc':>8}{'perime':>8}"
           f"{'jet/tour':>10}{'jet/juste':>11}")
    print(hdr)
    print("-" * len(hdr))

    sortie: dict = {"questions": len(sample), "graine": a.seed,
                    "genres": genres, "devis": d, "bras": {}}
    consomme = 0.0
    for nom in ORDRE:
        try:
            r = score(sample, run(fabriques[nom](), sample, tl))
        except DailyBudgetExhausted as exc:
            # On s'arrete PROPREMENT et on ecrit ce qui est deja mesure. Un
            # plafond atteint n'invalide pas les bras termines ; les perdre en
            # levant, si. C'est exactement ce qui s'est passe le 06/09.
            print(f"\n{NOMS[nom]} : {exc}")
            print("Arret propre, les bras deja mesures sont ecrits.")
            sortie["interrompu_a"] = nom
            sortie["cause"] = str(exc)
            break
        consomme += r.prompt_tokens_total
        par_juste = r.prompt_tokens_total / r.correct if r.correct else None
        g = lambda v: "  n/m" if v is None else f"{v:.3f}"
        print(f"{NOMS[nom]:<24}{g(r.coverage):>7}{g(r.gated_precision):>7}"
              f"{g(r.hallucination):>8}{g(r.supersession_error):>8}"
              f"{(r.tokens_per_turn or 0):>10.0f}"
              f"{('n/m' if par_juste is None else f'{par_juste:.0f}'):>11}")
        sortie["bras"][nom] = {
            "asked": r.asked, "coverage": r.coverage,
            "gated_precision": r.gated_precision,
            "hallucination": r.hallucination,
            "supersession_error": r.supersession_error,
            "retention": r.retention, "deep_retention": r.deep_retention,
            "age_awareness": r.age_awareness,
            "tokens_total": r.prompt_tokens_total,
            "tokens_per_turn": r.tokens_per_turn,
            "correct": r.correct,
            "tok_per_correct": par_juste}
        # Ecrit apres CHAQUE bras : une coupure ne doit jamais couter un bras
        # qui a deja ete paye.
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(sortie, fh, indent=2, ensure_ascii=False)

    sortie["reservation_reelle"] = consomme
    sortie["ecart_au_devis"] = (consomme / d["reservation"]
                                if d["reservation"] else None)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(sortie, fh, indent=2, ensure_ascii=False)

    print("\nreserve : " + f"{consomme:,.0f}".replace(",", " ")
          + " jetons, devis " + f"{d['reservation']:,.0f}".replace(",", " ")
          + f" ({consomme / d['reservation']:.2f}x)")
    print(f"429 par minute : {m.rate_limited}, attente cumulee "
          f"{m.waited_seconds:.0f} s, plafond par minute {TPM_CEILING}")
    print(f"Ecrit dans {a.out}.")
    print("\nLe cout par reponse juste = jetons totaux / reponses justes. Un "
          "bras qui se tait n'y gagne rien.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
