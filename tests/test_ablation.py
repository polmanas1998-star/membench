# -*- coding: utf-8 -*-
"""L'ABLATION : ce que chaque garde achete, et comment j'ai failli le rater.

CE QUE CES TESTS FIGENT (2026-09-06)
------------------------------------
Une affirmation sur ce qu'un composant apporte se mesure en le RETIRANT.

    garde z            hallucination 0.011 -> 1.000 quand on le retire
    decroissance       valeur perimee resservie 0.000 -> 0.417
    garde d'age        precision 0.995 -> 0.988, soit les 3 erreurs qu'il vise
    plancher de poids  aucun effet mesurable sur la justesse

⚠ LA MEDIANE A FAILLI COUTER UN CHIFFRE PUBLIE. La premiere version de ce banc
resumait les taux par graine avec une mediane. Les 3 erreurs que le garde d'age
retire vivent dans 2 graines sur 8 : la mediane de [1, 1, 1, 1, 1, 1, .98, .97]
vaut 1,000. L'ablation a donc conclu que le garde ne servait a rien, une
affirmation VRAIE du README a ete retiree sur cette base, puis remise quand la
calibration, qui met les graines en commun, a retrouve les 3 erreurs.

Une mediane est aveugle par construction a un evenement rare. Un taux d'erreur
rare se calcule sur le TOTAL des questions, jamais en resumant des taux dont
chacun a son propre denominateur. C'est pourquoi `_mesure` ci-dessous marque
une seule fois sur l'union des graines.
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
    """Taux MIS EN COMMUN sur toutes les graines, jamais une mediane de taux."""
    faits, reponses = [], []
    for g in GRAINES:
        f = build_corpus(seed=g)
        faits.extend(f)
        reponses.extend(run(_Variante(DIM, **kw), f, list(timeline(f))))
    r = score(faits, reponses)
    return {k: getattr(r, k) for k in
            ("coverage", "gated_precision", "hallucination",
             "supersession_error", "deep_retention")}


def test_le_garde_z_est_LE_produit():
    """Sans lui, la couche invente sur CHAQUE fait jamais enonce.

    C'est le seul composant dont le retrait transforme le resultat en son
    contraire. Tout le reste du depot est un raffinement de celui-la.
    """
    complet = _mesure()
    sans = _mesure(z_gate=0.0)
    # 2 inventions sur les 88 faits absents de ces 4 graines. Le seuil est
    # pose sur le TAUX et non sur le compte : change le nombre de graines et
    # le denominateur change, ce qui est precisement la lecon de ce fichier.
    assert complet["hallucination"] <= 0.05
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


def test_LE_GARDE_D_AGE_MORD_et_la_mediane_le_cachait():
    """Le test qui n'existait pas, et dont l'absence a coute un chiffre publie.

    Le garde d'age retire exactement les erreurs qu'il vise : des faits au-dela
    du seuil d'oubli auxquels la couche repondait avec un z superieur au seuil
    de confiance. Mesure : 3 erreurs, d'age 159, 192 et 242 jours.

    Elles ne representent que 0,7 point de precision, et elles vivent dans 2
    graines sur 8. Toute statistique resumee par graine les perd.
    """
    complet = _mesure()
    sans = _mesure(age_gate=False)
    assert sans["gated_precision"] < complet["gated_precision"], (
        f"precision {sans['gated_precision']:.4f} sans garde d'age contre "
        f"{complet['gated_precision']:.4f} avec : il a cesse de mordre, ou "
        "les taux sont a nouveau resumes par graine au lieu d'etre mis en commun")
    assert complet["gated_precision"] - sans["gated_precision"] < 0.05,         "l'ecart a beaucoup grandi : remesurer, ce n'est plus le meme garde"


def test_UNE_MEDIANE_AURAIT_RATE_LE_GARDE_D_AGE():
    """Le piege lui-meme, fige, pour qu'on ne le retombe pas.

    On calcule les deux facons sur les memes donnees : mise en commun, l'effet
    se voit ; mediane des taux par graine, il disparait. Ce test echoue le jour
    ou quelqu'un « simplifie » `_mesure` en remettant une mediane.
    """
    import statistics as st
    par_graine = {"avec": [], "sans": []}
    for g in GRAINES:
        f = build_corpus(seed=g)
        tl = list(timeline(f))
        par_graine["avec"].append(
            score(f, run(_Variante(DIM), f, tl)).gated_precision)
        par_graine["sans"].append(
            score(f, run(_Variante(DIM, age_gate=False), f, tl)).gated_precision)
    m_avec = st.median([x for x in par_graine["avec"] if x is not None])
    m_sans = st.median([x for x in par_graine["sans"] if x is not None])
    assert m_avec == m_sans, (
        "la mediane distingue maintenant les deux variantes : l'erreur n'est "
        "plus assez rare pour se cacher, et cette lecon a perdu son exemple")
    commun = _mesure()["gated_precision"] - _mesure(age_gate=False)["gated_precision"]
    assert commun > 0, "et pourtant l'effet existe quand on met les graines en commun"


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
    assert c["gated_precision"] >= 0.98
    assert c["hallucination"] <= 0.05      # les 2 inventions publiees
    assert c["supersession_error"] == 0.0
    assert 0.4 <= c["coverage"] <= 0.6
