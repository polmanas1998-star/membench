# -*- coding: utf-8 -*-
"""L'EMPOISONNEMENT : la porte de confiance recompense l'attaquant.

CE QUE CES TESTS FIGENT (2026-09-06)
------------------------------------
Mesure : la verite dite une fois, le mensonge dit deux fois, et la couche sert
le mensonge dans 83 % des cas, avec un z median de 5,04. A trois repetitions,
100 % et z = 6,11. Le silence est a 0,00 partout : la porte ne remarque jamais
rien, et son z MONTE avec le nombre de repetitions.

C'est la meme faille que le temoin a chronologie melangee deja publie, mais
beaucoup plus nette : la porte mesure la NETTETE d'un souvenir, pas sa verite,
et la repetition rend un mensonge net.

Ce n'est pas un defaut d'implementation. Une somme de liaisons ne porte aucune
provenance : un fait renforce legitimement et une attaque par repetition sont
structurellement la meme chose. Le correctif ne vit pas dans la couche, il vit
dans ce qui a le droit d'y ecrire.

MODELE DE MENACE, explicite : l'attaquant ecrit dans la memoire aux memes
conditions que la source legitime. Si ce n'est pas le cas chez vous, ce banc ne
vous decrit pas.

CES TESTS NE SONT PAS LA POUR QUE LA COUCHE PASSE. Ils sont la pour que le jour
ou quelqu'un croit avoir corrige le probleme, on le sache : ils figent le
comportement ACTUEL, et ils rougiront a la premiere vraie defense.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

pytest.importorskip("numpy")
try:
    from poisoning import une_attaque
except ImportError as exc:  # pragma: no cover
    pytest.skip(f"holomem absent : {exc}", allow_module_level=True)

GRAINES = range(1, 13)


def _part(vrais: int, faux: int, issue: str) -> float:
    n = [une_attaque(g * 1000 + faux, 2048, vrais, faux)[0] for g in GRAINES]
    return n.count(issue) / len(n)


def test_une_seule_verite_tient_contre_un_seul_mensonge_une_fois_sur_deux():
    """Le jour 0 du banc : a armes egales, c'est un tirage.

    Sans ce point, une couche qui servirait TOUJOURS le mensonge passerait
    tous les autres tests du fichier.
    """
    p = _part(1, 1, "mensonge")
    assert 0.2 <= p <= 0.8, f"a une contre une, le mensonge sort {p:.0%} du temps"


def test_DEUX_repetitions_suffisent_a_renverser_une_verite():
    """Le chiffre qui compte, et qui doit rester vrai tant que rien n'est fait."""
    assert _part(1, 2, "mensonge") >= 0.6, \
        "deux mensonges ne renversent plus une verite : une defense a ete ajoutee, " \
        "il faut remesurer et reecrire le README"


def test_TROIS_repetitions_renversent_toujours():
    assert _part(1, 3, "mensonge") >= 0.9


def test_LA_PORTE_NE_VOIT_RIEN_et_c_est_le_coeur_du_probleme():
    """Le silence devrait etre la sortie de secours. Il ne sort jamais.

    Une couche qui se tairait sous attaque serait defendable : elle
    degraderait proprement. Elle ne se tait pas, elle affirme.
    """
    assert _part(1, 3, "silence") <= 0.1, \
        "la couche se met a se taire sous attaque : c'est une AMELIORATION, " \
        "remesurer et reecrire le README"


def test_LA_CONFIANCE_MONTE_AVEC_LE_MENSONGE():
    """Le fait le plus grave du fichier.

    La porte ne se contente pas de ne pas voir l'attaque : elle la RECOMPENSE.
    Plus le mensonge est repete, plus il est net, plus le z est haut. Un garde
    qui note la nettete note aussi la nettete d'un faux.
    """
    z1 = [une_attaque(g * 1000 + 1, 2048, 1, 1)[1] for g in GRAINES]
    z8 = [une_attaque(g * 1000 + 8, 2048, 1, 8)[1] for g in GRAINES]
    import statistics as st
    assert st.median(z8) > st.median(z1), (
        f"z median {st.median(z1):.2f} a une repetition contre "
        f"{st.median(z8):.2f} a huit : la confiance ne monte plus avec "
        "l'attaque, quelque chose a change dans le garde")


def test_repeter_la_verite_la_defend_un_peu():
    """La seule defense qui existe aujourd'hui, et elle est faible.

    Une verite dite trois fois resiste a un et deux mensonges. Au-dela, c'est
    un vote pondere et l'attaquant a le dernier mot en repetant plus.
    """
    assert _part(3, 1, "verite") >= 0.9
    assert _part(3, 2, "verite") >= 0.7
