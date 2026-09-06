# -*- coding: utf-8 -*-
"""Le sondage de cout : l'echantillonnage, le devis, et l'ordre des bras.

Ces trois choses se testent HORS LIGNE, sans depenser un jeton, et ce sont
exactement les trois qui ont coute la campagne du 06/09 : un echantillon trop
gros, aucun devis, et le bras inconnu passe en dernier.
"""
from __future__ import annotations

import cost_probe as cp
from membench.corpus import build_corpus


def _corpus():
    return build_corpus(seed=1)


def _genres(facts):
    d = {}
    for f in facts:
        d[f.kind] = d.get(f.kind, 0) + 1
    return d


def test_taille_exacte():
    for n in (6, 10, 24, 40, 63, 104):
        assert len(cp.echantillon(_corpus(), n)) == n


def test_sans_doublon_et_issu_du_corpus():
    f = _corpus()
    s = cp.echantillon(f, 40)
    cles = [(x.subject, x.relation) for x in s]
    assert len(set(cles)) == len(cles)
    assert set(cles) <= {(x.subject, x.relation) for x in f}


def test_chaque_genre_recoit_le_plancher_ou_le_plafond_de_sa_part():
    """C'est LA propriete qui rend l'echantillon comparable au corpus complet.

    Sinon les taux globaux ne s'interpretent plus contre ceux des 104
    questions, et les trois bras temoins ne temoignent de rien.
    """
    import math
    f = _corpus()
    total = len(f)
    dispo = _genres(f)
    for n in (24, 40, 63):
        obtenu = _genres(cp.echantillon(f, n))
        for genre, combien in dispo.items():
            exact = combien * n / total
            borne = (math.floor(exact), math.ceil(exact))
            assert borne[0] <= obtenu.get(genre, 0) <= borne[1], (
                n, genre, obtenu.get(genre, 0), exact)


def test_le_plus_fort_reste_est_servi_le_premier():
    """La propriete qui DEFINIT l'arrondi au plus fort reste, et la seule qui
    separe cette regle d'un arrondi arbitraire.

    Une premiere version de ce fichier se contentait de verifier un ecart de
    moins d'une question a la part exacte. Une mutation qui servait les genres
    par ordre ALPHABETIQUE plutot que par reste survivait : elle restait sous
    l'ecart d'une question, tout en donnant une place a un genre qui la
    meritait moins. Ici on epingle la regle elle-meme : aucun genre arrondi
    vers le HAUT ne peut avoir un reste plus petit qu'un genre arrondi vers le
    BAS.
    """
    f = _corpus()
    total = len(f)
    dispo = _genres(f)
    for n in (24, 40, 63, 90):
        obtenu = _genres(cp.echantillon(f, n))
        restes_hauts, restes_bas = [], []
        for genre, combien in dispo.items():
            exact = combien * n / total
            reste = exact - int(exact)
            if obtenu.get(genre, 0) > int(exact):
                restes_hauts.append((reste, genre))
            else:
                restes_bas.append((reste, genre))
        if restes_hauts and restes_bas:
            assert min(restes_hauts)[0] >= max(restes_bas)[0], (
                n, restes_hauts, restes_bas)


def test_deterministe_a_graine_fixee():
    a = cp.echantillon(_corpus(), 40, seed=1)
    b = cp.echantillon(_corpus(), 40, seed=1)
    assert [(x.subject, x.relation) for x in a] == \
           [(x.subject, x.relation) for x in b]


def test_deux_graines_donnent_deux_echantillons():
    """Sinon la graine ne sert a rien et une reprise re-mesure la meme chose."""
    a = cp.echantillon(_corpus(), 40, seed=1)
    b = cp.echantillon(_corpus(), 40, seed=2)
    assert [(x.subject, x.relation) for x in a] != \
           [(x.subject, x.relation) for x in b]


def test_tous_les_genres_representes():
    f = _corpus()
    assert set(_genres(cp.echantillon(f, 40))) == set(_genres(f))


def test_un_genre_ne_donne_pas_plus_qu_il_n_a():
    f = _corpus()
    dispo = _genres(f)
    obtenu = _genres(cp.echantillon(f, 100))
    for genre, combien in obtenu.items():
        assert combien <= dispo[genre], genre
    assert sum(obtenu.values()) == 100


def test_demander_plus_que_le_corpus_leve():
    """Rendre le corpus entier en silence donnerait un echantillon de 104
    questions a qui en a demande 200, et un devis calcule sur 200."""
    import pytest
    f = _corpus()
    for n in (0, -1, len(f) + 1, 200):
        with pytest.raises(ValueError):
            cp.echantillon(f, n)


def test_corpus_entier_rend_tout():
    f = _corpus()
    assert _genres(cp.echantillon(f, len(f))) == _genres(f)


def test_le_devis_refuse_le_corpus_entier_et_accepte_quarante():
    """Le chiffre qui manquait le 06/09, et qui tient en une multiplication."""
    assert cp.devis(104)["part_du_jour"] > 1.0
    assert cp.devis(40)["part_du_jour"] < 1.0


def test_facteur_reel_derive_et_plus_grand_que_un():
    """La reservation compte toujours PLUS que les jetons reellement facturés.

    Un facteur inferieur a 1 signifierait que le devis sous-estime, et la
    campagne repartirait pour se faire couper au meme endroit.
    """
    assert cp.FACTEUR_REEL > 1.0
    assert cp.RESERVATION_MESUREE > cp.REEL_MESURE


def test_ordre_des_bras_le_plus_cher_et_inconnu_d_abord():
    """L'ordre n'est pas cosmetique : c'est ce qui a fait perdre le bras B.

    On epingle la REGLE, pas la liste : le bras le plus cher passe en tete,
    les suivants par cout croissant. Si les couts sont un jour remesures et
    que l'ordre ne suit plus, ce test le dit.
    """
    couts = cp.COUT_PAR_QUESTION
    assert set(cp.ORDRE) == set(couts)
    assert cp.ORDRE[0] == max(couts, key=couts.get)
    suite = [couts[nom] for nom in cp.ORDRE[1:]]
    assert suite == sorted(suite)
