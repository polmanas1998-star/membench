# -*- coding: utf-8 -*-
"""LA LATENCE : memoire constante, temps lineaire, et le detecteur de bruit.

CE QUE CES TESTS FIGENT (2026-09-06)
------------------------------------
1. **La trace ne grandit pas avec le nombre de faits.** C'est toute la promesse
   d'une superposition : 32 Ko a d=2048, que le magasin porte 50 faits ou 2 000.
   Si cette colonne se met a bouger, la structure n'est plus celle qu'on decrit.
2. **Le temps, lui, grandit.** La trace est reconstruite depuis la liste a
   chaque apprentissage, donc une interrogation coute O(N). C'est un arbitrage
   assume dans la bibliotheque, pas un oubli, et il est chiffre plutot que
   suppose.
3. **Le rapport mediane / minimum detecte la contention.** La premiere serie de
   ce banc, prise pendant une campagne payante, donnait a d=2048 : 250 ms a 500
   faits, 924 ms a 1000, 219 ms a 2000. Non monotone, donc impossible pour un
   cout lineaire. Ce depot a deja paye une mesure prise sous sa propre charge de
   fond, au prix d'un chiffre publie sur GitHub et sur Reddit.

Ces tests restent LARGES a dessein : ils tournent sur la machine de qui les
lance, et une assertion serree sur des millisecondes rougirait chez tout le
monde sauf chez moi. Ils epinglent des FORMES, pas des durees.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

pytest.importorskip("numpy")
try:
    from latency import SEUIL_CONTENTION, mesure
except ImportError as exc:  # pragma: no cover
    pytest.skip(f"holomem absent : {exc}", allow_module_level=True)


def test_la_trace_ne_grandit_PAS_avec_le_nombre_de_faits():
    """La promesse de la superposition, verifiee plutot qu'affirmee.

    C'est la seule assertion exacte du fichier, parce que c'est la seule
    grandeur qui ne depende ni de la machine ni de sa charge.
    """
    petite = mesure(50, 2048, tours=5)
    grande = mesure(1000, 2048, tours=5)
    assert petite["trace_ko"] == grande["trace_ko"], (
        f"{petite['trace_ko']} Ko a 50 faits contre {grande['trace_ko']} Ko a "
        "1000 : la trace n'est plus de taille fixe, la structure a change")
    assert petite["trace_ko"] == 32.0, "d=2048 en complexe128 fait 32 Ko"


def test_la_taille_de_la_trace_suit_la_DIMENSION_et_elle_seule():
    d1 = mesure(100, 1024, tours=3)["trace_ko"]
    d2 = mesure(100, 2048, tours=3)["trace_ko"]
    assert d2 == 2 * d1, f"{d1} Ko a d=1024 contre {d2} a d=2048"


def test_le_temps_grandit_avec_le_nombre_de_faits():
    """L'autre moitie de l'arbitrage : O(1) en memoire, O(N) en temps.

    Facteur 4 demande pour 20 fois plus de faits : large exprès. On epingle
    qu'il existe une croissance, pas sa pente exacte, qui depend de la machine.
    """
    petite = mesure(50, 2048, tours=10)
    grande = mesure(1000, 2048, tours=10)
    assert grande["froid_ms"] > petite["froid_ms"] * 4, (
        f"{petite['froid_ms']:.1f} ms a 50 faits contre "
        f"{grande['froid_ms']:.1f} ms a 1000 : la croissance a disparu, la "
        "trace est peut-etre maintenue au lieu d'etre reconstruite. Si c'est "
        "voulu, c'est une AMELIORATION : remesurer et reecrire le README.")


def test_une_interrogation_A_CHAUD_est_moins_chere_qu_A_FROID():
    """Le decoupage qui justifie de publier le froid plutot que le chaud.

    Sans cet ecart, les deux regimes seraient le meme et le README aurait
    tort de dire que la reconstruction domine.
    """
    r = mesure(500, 2048, tours=15)
    assert r["chaud_ms"] < r["froid_ms"], (
        f"chaud {r['chaud_ms']:.1f} ms, froid {r['froid_ms']:.1f} ms : la "
        "reconstruction ne coute plus rien, le cache a change de regime")


def test_le_detecteur_de_contention_existe_et_est_pose_bas():
    """Le garde qui manquait a la premiere serie.

    Un seuil trop haut ne rattraperait rien : la serie contaminee montait a
    2,3 fois. On verifie qu'il reste sous cette valeur.
    """
    assert SEUIL_CONTENTION <= 2.5, (
        f"seuil de contention a {SEUIL_CONTENTION} : la serie contaminee du "
        "06/09 montait a 2,3x et passerait a travers")
    r = mesure(200, 2048, tours=20)
    assert "froid_median_ms" in r and "froid_ms" in r, \
        "les deux estimateurs doivent etre rendus ensemble, sinon le rapport " \
        "ne se calcule plus et la contamination redevient invisible"
