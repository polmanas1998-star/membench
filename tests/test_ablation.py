# -*- coding: utf-8 -*-
"""L'ABLATION : ce que chaque garde achete, et celui qui n'achete rien.

CE QUE CES TESTS FIGENT (2026-09-06)
------------------------------------
Une affirmation sur ce qu'un composant apporte se mesure en le RETIRANT. Le
README en portait une, adossee a un seul point de mesure, et l'ablation ne la
reproduit pas.

    garde z            hallucination 0.000 -> 1.000 quand on le retire
    decroissance       valeur perimee resservie 0.000 -> 0.444
    garde d'age        AUCUN changement, a d = 2048, 4096 et 8192
    plancher de poids  aucun changement mesurable non plus

Le garde d'age est redondant parce que son propre seuil en derive : 111,33
jours vaut 45 x log2(1/0,18), donc le plancher de poids et lui encodent la
meme frontiere, l'un a la construction de la trace, l'autre a l'interrogation.

⚠ CES TESTS NE DEMANDENT PAS DE SUPPRIMER LE GARDE D'AGE. Ils figent le fait
qu'il ne mord pas : le jour ou il se met a mordre, quelque chose a change dans
la decroissance ou le plancher, et il faut le savoir.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

pytest.importorskip("numpy")
try:
    from ablation import _Variante, INFINI
except ImportError as exc:  # pragma: no cover
    pytest.skip(f"holomem absent : {exc}", allow_module_level=True)

from membench.arms import run  # noqa: E402
from membench.corpus import build_corpus, timeline  # noqa: E402
from membench.scoring import score  # noqa: E402

DIM = 2048
GRAINES = (1, 2, 3, 4)


def _mesure(**kw):
    """Mediane des metriques sur quelques graines, pour une variante."""
    import statistics as st
    acc: dict[str, list] = {}
    for g in GRAINES:
        f = build_corpus(seed=g)
        r = score(f, run(_Variante(DIM, **kw), f, list(timeline(f))))
        for k in ("coverage", "gated_precision", "hallucination",
                  "supersession_error", "deep_retention"):
            acc.setdefault(k, []).append(getattr(r, k))
    return {k: st.median([x for x in v if x is not None]) if any(
        x is not None for x in v) else None for k, v in acc.items()}


def test_le_garde_z_est_LE_produit():
    """Sans lui, la couche invente sur CHAQUE fait jamais enonce.

    C'est le seul composant dont le retrait transforme le resultat en son
    contraire. Tout le reste du depot est un raffinement de celui-la.
    """
    complet = _mesure()
    sans = _mesure(z_gate=0.0)
    assert complet["hallucination"] == 0.0
    assert sans["hallucination"] >= 0.9, (
        f"hallucination {sans['hallucination']:.3f} sans le garde z : elle "
        "devrait etre totale, une autre defense s'est glissee la")
    assert sans["gated_precision"] < complet["gated_precision"]


def test_la_decroissance_est_ce_qui_fait_marcher_la_supersession():
    """Sans elle, une valeur remplacee revient comme neuve.

    L'ancien et le nouvel enonce se disputent alors a poids egal, pour
    toujours, et le plus souvent repete gagne.
    """
    complet = _mesure()
    sans = _mesure(half_life=INFINI)
    assert complet["supersession_error"] == 0.0
    assert sans["supersession_error"] >= 0.3, (
        f"{sans['supersession_error']:.3f} de valeurs perimees sans "
        "decroissance : trop bas, la supersession tient par autre chose")


def test_LE_GARDE_D_AGE_NE_MORD_PAS():
    """Le fait que le README affirmait le contraire.

    Le retirer ne change aucune colonne. Son seuil de 111,33 jours derive du
    plancher de poids (45 x log2(1/0,18)) : les deux encodent la meme
    frontiere, et le plancher a deja evince avant que le garde ne s'execute.

    ⚠ Si ce test rougit, ce n'est PAS une regression : c'est que le garde s'est
    mis a servir a quelque chose. Il faut alors remesurer et reecrire le README,
    pas restaurer l'ancien comportement.
    """
    complet = _mesure()
    sans = _mesure(age_gate=False)
    assert sans["hallucination"] == complet["hallucination"]
    assert sans["gated_precision"] == complet["gated_precision"]
    assert abs(sans["coverage"] - complet["coverage"]) < 0.02, (
        f"couverture {sans['coverage']:.3f} sans garde d'age contre "
        f"{complet['coverage']:.3f} avec : il s'est mis a mordre")


def test_la_retention_profonde_est_un_ARBITRAGE_et_voici_son_prix():
    """Couper l'oubli rend TOUS les vieux faits, et coute 44 % de perime.

    Le README dit que la retention profonde est nulle « par conception ». Ce
    test montre ce que la conception achete en echange, plutot que de le
    laisser croire impossible.
    """
    eternelle = _mesure(age_gate=False, half_life=INFINI)
    assert eternelle["deep_retention"] >= 0.9, \
        "couper l'oubli ne rend plus les vieux faits : la decroissance n'est " \
        "plus ce qui les retirait"
    assert eternelle["supersession_error"] >= 0.3, \
        "la retention profonde est devenue gratuite : remesurer, c'est une " \
        "vraie amelioration ou un instrument casse"


def test_une_variante_complete_reproduit_le_banc_publie():
    """Le jour 0 : sans ablation, on doit retrouver les chiffres du README.

    Sans ce point, une classe `_Variante` cassee donnerait des tables entieres
    de differences qui ne diraient rien.
    """
    c = _mesure()
    assert c["gated_precision"] == 1.0
    assert c["hallucination"] == 0.0
    assert c["supersession_error"] == 0.0
    assert 0.4 <= c["coverage"] <= 0.6
