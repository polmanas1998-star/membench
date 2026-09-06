# -*- coding: utf-8 -*-
"""L'INTERFERENCE : concentrer les faits sur moins de sujets.

POURQUOI CE FICHIER EXISTE (2026-09-06)
---------------------------------------
Le README annoncait une limite qui n'existait pas :

    « chaque paire sujet-relation est unique par construction, donc le cas
      reel le plus difficile, un sujet portant plusieurs relations qui
      interferent, est absent »

Mesure : le vocabulaire compte 12 sujets et 10 relations, soit 120 paires, et
le melange par defaut en consomme 104. Le corpus tourne donc a 87 % de la
saturation, avec 8,7 relations par sujet. L'interference n'etait pas absente,
elle etait presque maximale, et personne ne l'avait comptee.

CE QUE CES TESTS PROTEGENT
--------------------------
1. **Le defaut ne bouge pas d'un octet.** Une campagne payante reprend sur les
   memes graines : un corpus qui aurait derive rendrait ses points de reprise
   incomparables entre eux. C'est le test le plus important du fichier.
2. Le parametre CONCENTRE reellement, il ne fait pas semblant.
3. Il refuse clairement l'impossible plutot que de lever une erreur opaque.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from membench.corpus import (DEFAULT_MIX, _RELATIONS, _SUBJECTS,  # noqa: E402
                             build_corpus)


def _empreinte(facts) -> str:
    """Une signature du corpus ENTIER, enonces compris."""
    return "|".join(
        f"{f.subject}~{f.relation}~{f.kind}~"
        + ",".join(s.as_utterance() for s in f.statements)
        for f in facts
    )


def _par_sujet(facts) -> dict[str, int]:
    d: dict[str, int] = {}
    for f in facts:
        d[f.subject] = d.get(f.subject, 0) + 1
    return d


@pytest.mark.parametrize("graine", [1, 2, 3, 7, 11])
def test_le_defaut_ne_bouge_pas_dun_octet(graine):
    """Le test qui protege la campagne en cours.

    `sujets_max=None` doit produire exactement le corpus d'avant, y compris le
    flux du generateur aleatoire : le parametre ne doit consommer aucun tirage
    quand il n'est pas utilise, sinon toutes les graines derivent en silence.
    """
    assert _empreinte(build_corpus(seed=graine)) == \
           _empreinte(build_corpus(seed=graine, sujets_max=None))


def test_le_corpus_par_defaut_porte_DEJA_de_l_interference():
    """Le fait qui corrige le README.

    Ce n'est pas un detail de documentation : une limite annoncee a tort rend
    suspects les chiffres qui l'entourent, et se retourne des que quelqu'un
    compte lui-meme.
    """
    d = _par_sujet(build_corpus(seed=1))
    moyenne = sum(d.values()) / len(d)
    assert moyenne > 5.0, (
        f"{moyenne:.1f} relations par sujet : si ce nombre tombe sous 5, la "
        "limite annoncee dans le README redevient vraie et il faut la remettre.")
    assert sum(DEFAULT_MIX.values()) / (len(_SUBJECTS) * len(_RELATIONS)) > 0.8, \
        "le corpus n'est plus proche de la saturation de l'espace des paires"


@pytest.mark.parametrize("n", [3, 4, 6])
def test_le_parametre_concentre_vraiment(n):
    """Un reglage qui ne change rien est un reglage mort.

    On verifie l'EFFET, le nombre de sujets distincts, et pas seulement que
    l'appel passe.
    """
    mix = {"stable": 5, "faded": 6, "expired": 4,
           "superseded": 5, "reinforced": 4, "absent": 6}
    d = _par_sujet(build_corpus(seed=1, mix=mix, sujets_max=n))
    assert len(d) <= n, f"{len(d)} sujets distincts alors que {n} etaient demandes"
    large = _par_sujet(build_corpus(seed=1, mix=mix, sujets_max=12))
    assert len(d) < len(large), "concentrer ne reduit pas le nombre de sujets"


def test_les_paires_restent_uniques_meme_concentrees():
    """La garantie d'origine ne doit pas tomber avec le nouveau parametre.

    Deux faits sur la meme paire se contrediraient sans que le corpus le sache,
    et la verite de reference dependrait de l'ordre de lecture.
    """
    mix = {"stable": 5, "faded": 6, "expired": 4,
           "superseded": 5, "reinforced": 4, "absent": 6}
    f = build_corpus(seed=3, mix=mix, sujets_max=3)
    paires = [(x.subject, x.relation) for x in f]
    assert len(paires) == len(set(paires)), "une paire sujet-relation est en double"


def test_demander_plus_de_sujets_que_le_vocabulaire_est_REFUSE():
    """Le parametre concentre, il n'invente pas de vocabulaire.

    Sans ce garde, l'appel levait une erreur opaque venant de `random.sample`,
    qui n'apprenait rien a personne.
    """
    with pytest.raises(ValueError, match="vocabulaire"):
        build_corpus(seed=1, sujets_max=len(_SUBJECTS) + 1)


def test_un_melange_trop_gros_pour_les_sujets_demandes_est_REFUSE():
    """104 faits sur 3 sujets et 10 relations, c'est 30 paires possibles.

    ⚠ ON EPINGLE LE MESSAGE DE CE GARDE, PAS LE TYPE DE L'EXCEPTION. La
    premiere version se contentait de `pytest.raises(ValueError)` et de trois
    nombres : elle passait quand on desarmait ce garde, parce qu'un AUTRE
    garde, en aval, levait le meme type avec un message qui contenait par
    hasard les memes chiffres. Trouve par mutation, pas par relecture.
    """
    with pytest.raises(ValueError, match=r"sujets et \d+ relations : au plus"):
        build_corpus(seed=1, sujets_max=3)


@pytest.mark.parametrize("mauvais", [0, -1])
def test_sujets_max_zero_ou_negatif_est_REFUSE(mauvais):
    """Meme piege que ci-dessus, et il s'est referme de la meme facon.

    Sans ce garde, `random.sample` leve tout seul, ou rend une liste vide qui
    fait lever le garde suivant : dans les deux cas un ValueError sort, et un
    test qui ne regarde que le type reste vert alors que le garde a disparu.
    """
    with pytest.raises(ValueError, match="au moins un"):
        build_corpus(seed=1, sujets_max=mauvais)


def test_les_taux_sont_MIS_EN_COMMUN_et_pas_medianes():
    """Le garde contre l'erreur qui a coute un chiffre publie le 06/09.

    `interference.py` medianait les taux par graine. Une mediane est aveugle
    par construction a un evenement rare : trois erreurs sur deux graines sur
    huit disparaissent derriere six graines parfaites. Dans `ablation.py`, la
    meme faute a fait conclure qu'un garde ne servait a rien, et une
    affirmation VRAIE du README a ete retiree sur cette base.

    On epingle donc l'ABSENCE de resume par graine dans le source. C'est un
    test sur le texte, ce qui est faible en general, et c'est ici le seul moyen
    d'attraper une regression qui ne change aucune valeur de sortie mais rend
    toutes les valeurs fausses.
    """
    src = (RACINE / "interference.py").read_text(encoding="utf-8")
    corps = src[src.index("def main("):]
    assert "median" not in corps, (
        "une mediane est revenue dans interference.py : elle cache les erreurs "
        "rares, calculer le taux sur le total des questions")
    assert "score(faits, rep)" in corps, \
        "le score n'est plus calcule sur l'union des graines"
