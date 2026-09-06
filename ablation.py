"""L'ABLATION : ce que chaque garde achete, mesure en le RETIRANT.

POURQUOI CETTE TABLE MANQUAIT
-----------------------------
Le README affirmait ceci :

    « Un garde de confiance et un garde d'age ne sont pas la meme chose. L'un
      demande a quel point un souvenir est net, l'autre s'il a le droit
      d'exister. »

C'est une belle phrase, et elle reposait sur UN point de mesure : en refusant
les faits perimes, on retirait 3 erreurs sur 5 sans perdre une bonne reponse.
Un point ne fait pas une demonstration. Une affirmation sur ce qu'un composant
apporte se mesure en le retirant, une piece a la fois, et en regardant ce qui
casse.

C'est la table la plus banale d'un laboratoire, et c'est exactement pour ca
qu'elle manquait : elle n'apprend rien de flatteur.

LES QUATRE PIECES
-----------------
    garde z             la reponse ne sort que si le gagnant se detache
    garde d'age         un fait de plus de 111 jours est refuse d'office
    decroissance        le poids d'un fait tombe de moitie tous les 45 jours
    plancher de poids   sous 0,18 un fait sort de la trace au lieu d'y
                        verser son bruit sans y verser de signal

Chaque ligne en retire UNE, sauf la derniere qui en retire deux pour montrer
un couplage. Tout est hors ligne : aucun jeton depense.

    python ablation.py --seeds 8
"""
from __future__ import annotations

import argparse
import json

from membench.arms import run
from membench.corpus import build_corpus, timeline
from membench.real_arms import DermiozArm
from membench.scoring import score

INFINI = 10 ** 9


class _Variante(DermiozArm):
    """Une couche a laquelle on a retire quelque chose.

    Les constantes sont lues sur l'INSTANCE (`self.HALF_LIFE_DAYS`,
    `self.MIN_WEIGHT`), donc les poser ici les remplace sans toucher a la
    bibliotheque. Le seuil `z`, lui, est un defaut d'argument fige a la
    definition : il ne se remplace pas par attribut, il se passe a l'appel.
    C'est pour cela que `ask` est reecrit plutot que configure.
    """

    def __init__(self, dim: int, z_gate: float = 4.0,
                 age_gate: bool = True, half_life: float = 45.0,
                 min_weight: float = 0.18) -> None:
        super().__init__(dim=dim)
        self._z_gate = z_gate
        self._mem.HALF_LIFE_DAYS = half_life
        self._mem.MIN_WEIGHT = min_weight
        if not age_gate:
            self.REFUSE_AFTER_DAYS = INFINI

    def ask(self, subject: str, relation: str):
        from membench.real_arms import Answer
        valeur, _z = self._mem.query_gated(subject, relation,
                                           z_gate=self._z_gate)
        if valeur is None:
            return Answer(None, prompt_tokens=0)
        age = self._age_days(subject, relation)
        if age is not None and age > self.REFUSE_AFTER_DAYS:
            return Answer(None, prompt_tokens=0)
        return Answer(valeur,
                      stale_flagged=age is not None and age > self._stale_after,
                      prompt_tokens=0)


#: nom, ce qui est retire, fabricant
VARIANTES = [
    ("complete", "rien", lambda d: _Variante(d)),
    ("sans garde z", "le seuil de confiance", lambda d: _Variante(d, z_gate=0.0)),
    ("sans garde d'age", "le refus au-dela de 111 jours",
     lambda d: _Variante(d, age_gate=False)),
    ("sans decroissance", "la demi-vie de 45 jours",
     lambda d: _Variante(d, half_life=INFINI)),
    ("sans plancher", "l'eviction sous 0,18",
     lambda d: _Variante(d, min_weight=0.0)),
    ("memoire eternelle", "decroissance ET garde d'age",
     lambda d: _Variante(d, age_gate=False, half_life=INFINI)),
]


# ⚠ ON MET LES GRAINES EN COMMUN, ON NE PREND PAS LA MEDIANE.
#
# La premiere version de ce banc prenait la mediane des taux par graine, et
# elle a rate le seul effet qu'elle cherchait. Les 3 erreurs que le garde d'age
# retire vivent dans 2 graines sur 8 : la mediane de
# [1, 1, 1, 1, 1, 1, 0,98, 0,97] vaut 1,000. Elle est AVEUGLE par construction
# a un evenement rare, et l'ablation a conclu que le garde ne servait a rien.
# Un chiffre publie a ete retire sur cette erreur, puis remis.
#
# Un taux d'erreur rare se calcule sur le TOTAL, jamais en moyennant des taux
# par lot : chaque lot a son propre denominateur, et resumer des taux revient a
# donner le meme poids a un lot sans erreur qu'a un lot qui en porte trois.


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--dim", type=int, default=2048)
    ap.add_argument("--out", default="results-ablation.json")
    a = ap.parse_args()

    corpus = [build_corpus(seed=g) for g in range(1, a.seeds + 1)]
    lignes = []
    print(f"d={a.dim}, {a.seeds} graines, {sum(len(f) for f in corpus)} questions "
          f"par variante. Hors ligne, zero jeton.\n")
    hdr = (f"{'variante':<20}{'couv':>7}{'prec':>7}{'halluc':>8}"
           f"{'perime':>8}{'profond':>9}{'age ok':>8}")
    print(hdr); print("-" * len(hdr))

    for nom, retire, fab in VARIANTES:
        # Une memoire NEUVE par graine, mais un seul calcul de score sur
        # l'union : c'est ce qui donne des taux mis en commun plutot qu'une
        # moyenne de taux.
        tous_faits, toutes_reponses = [], []
        for f in corpus:
            tous_faits.extend(f)
            toutes_reponses.extend(run(fab(a.dim), f, list(timeline(f))))
        r = score(tous_faits, toutes_reponses)
        v = {k: getattr(r, k) for k in
             ("coverage", "gated_precision", "hallucination",
              "supersession_error", "deep_retention", "age_awareness")}
        g = lambda x: "  n/m" if x is None else f"{x:.3f}"
        print(f"{nom:<20}{g(v['coverage']):>7}{g(v['gated_precision']):>7}"
              f"{g(v['hallucination']):>8}{g(v['supersession_error']):>8}"
              f"{g(v['deep_retention']):>9}{g(v['age_awareness']):>8}")
        lignes.append({"variante": nom, "retire": retire, **v})

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"dim": a.dim, "graines": a.seeds, "variantes": lignes},
                  fh, indent=2, ensure_ascii=False)
    print(f"\nEcrit dans {a.out}.")
    print("« perime » = valeur remplacee resservie comme neuve, plus bas est mieux.\n"
          "« profond » = faits au-dela du seuil d'oubli retrouves.\n"
          "Une variante qui gagne sur une colonne en perdant sur une autre ne\n"
          "prouve pas qu'il faut la retirer : elle montre l'arbitrage qu'on a fait.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
