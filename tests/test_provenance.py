# -*- coding: utf-8 -*-
"""UNE VOIX, UN VOTE : ce que la regle repare, et ce qu'on ne peut PAS en dire.

CE QUE CES TESTS FIGENT (2026-09-07)
------------------------------------
Mesure, d=2048, 40 graines. Aujourd'hui, trois repetitions d'un mensonge le
font servir 100 % du temps a z = 6,15. Sous « un vote par source », le mensonge
passe 40 % du temps a z = 4,73, et ce chiffre ne bouge plus avec le nombre de
repetitions.

DEUX CHOSES QU'IL FAUT LIRE ENSEMBLE, sinon on publie une victoire.

1. L'APLATISSEMENT EST UNE TAUTOLOGIE. Sous la regle, chaque ligne de la table
   est le MEME essai : une verite contre un mensonge, chacun ecrit une fois.
   Les sept lignes sont identiques par construction. La colonne porte UN point
   de mesure, pas sept, et le dire est la moitie du travail.

2. LE RESIDU N'EST PAS ZERO, et c'est le seul resultat non trivial. A masse
   egale, le gagnant est decide par le bruit des vecteurs : 40 % d'erreur, avec
   un z de 4,73 qui reste AU-DESSUS du seuil de 4. La provenance retire a
   l'attaquant la certitude, pas l'erreur. La porte, elle, ne distingue toujours
   pas un pile ou face d'une certitude.

Le prix de la regle n'est PAS mesure ici, et la case vide n'est pas un zero :
dans ce corpus chaque paire (sujet, relation) est unique et un fait renforce ne
repete que le meme objet, donc la regle n'y efface jamais d'information. Le prix
vivrait la ou la repetition est le SEUL signal separant une croyance forte d'une
croyance faible. Ce corpus n'a pas ce cas.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RACINE))

import provenance as P  # noqa: E402
from membench.corpus import Statement  # noqa: E402

pytest.importorskip("holomem", reason="le magasin n'est pas installe")

from datetime import date  # noqa: E402


def _s(sujet, relation, obj, jour):
    return Statement(subject=sujet, relation=relation, obj=obj,
                     when=date(2026, 1, jour))


def test_dedupe_garde_la_version_la_PLUS_RECENTE():
    """La plus recente et non la premiere. Garder la premiere punirait deux
    fois, en masse ET en fraicheur, et on ne saurait plus laquelle des deux
    la mesure attribue a la regle."""
    chrono = [_s("A", "r", "x", 1), _s("A", "r", "x", 10), _s("A", "r", "x", 20)]
    sortie = P._dedupe(chrono)
    assert len(sortie) == 1
    assert sortie[0].when == date(2026, 1, 20)


def test_dedupe_ne_confond_PAS_deux_objets_differents():
    """Le denominateur. Une regle qui ecraserait aussi les valeurs DIFFERENTES
    ne serait plus « un vote par source », ce serait un oubli, et elle passerait
    le test precedent sans rien mesurer de ce qu'on croit."""
    chrono = [_s("A", "r", "x", 1), _s("A", "r", "y", 10)]
    assert len(P._dedupe(chrono)) == 2


def test_dedupe_rend_une_chronologie_ORDONNEE():
    """La couche apprend en avancant son horloge a la date de chaque enonce.
    Une chronologie rendue dans le desordre ferait reculer cette horloge, et la
    mesure porterait alors sur autre chose que la regle."""
    chrono = [_s("A", "r", "x", 20), _s("B", "r", "y", 5), _s("C", "r", "z", 12)]
    sortie = P._dedupe(chrono)
    assert [s.when.day for s in sortie] == [5, 12, 20]


@pytest.mark.parametrize("faux", [2, 3, 20])
def test_sous_la_regle_le_nombre_de_repetitions_ne_change_RIEN(faux):
    """La tautologie, figee pour qu'elle reste visible.

    Si un jour ce test rougit, c'est que « un vote par source » a cesse de
    collapser les repetitions, et la table de droite redeviendrait sept points
    au lieu d'un.
    """
    a = P.une_attaque(0, 512, 1, 1, un_vote=True)
    b = P.une_attaque(0, 512, 1, faux, un_vote=True)
    assert a == b


def test_sans_la_regle_les_repetitions_changent_TOUT():
    """Le temoin de l'instrument. Sans lui, un `une_attaque` casse qui rendrait
    toujours la meme chose passerait le test precedent en beaute."""
    seul = P.une_attaque(0, 512, 1, 1, un_vote=False)
    masse = P.une_attaque(0, 512, 1, 20, un_vote=False)
    assert seul != masse, (
        "vingt mensonges contre un doivent produire une issue differente d'un "
        "contre un, sinon c'est le harnais qu'on mesure"
    )
