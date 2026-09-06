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


# --- La fenetre glissante, et les deux erreurs d'horloge qui l'ont faussee ---

def test_maintenant_porte_son_fuseau():
    """Le defaut, en une assertion.

    Le journal de campagne ecrivait UTC sans le dire : `[18:50:54]` a ete lu
    comme 18 h 50 alors qu'il etait 20 h 50 a Paris, et l'heure de reouverture
    qu'on en tirait se trompait de deux heures. Une heure NAIVE n'est pas une
    heure, c'est un nombre qui ressemble a une heure.
    """
    assert cp.maintenant().tzinfo is not None


def test_rouvre_a_ajoute_la_fenetre_et_garde_le_fuseau():
    from datetime import datetime
    fin = datetime.fromisoformat("2026-09-06T19:45:22+02:00")
    ouv = cp.rouvre_a(fin)
    assert (ouv - fin).total_seconds() == cp.FENETRE_HEURES * 3600
    assert ouv.utcoffset() == fin.utcoffset()
    assert ouv.isoformat() == "2026-09-07T19:45:22+02:00"


def test_registre_aller_retour_conserve_l_instant():
    """Ecrire puis relire ne doit pas deplacer l'heure d'un fuseau."""
    import tempfile
    from datetime import datetime
    fin = datetime.fromisoformat("2026-09-06T19:45:22+02:00")
    with tempfile.TemporaryDirectory() as d:
        chemin = f"{d}/registre.json"
        cp.noter_depense(fin, 348244, chemin)
        relu = cp.derniere_depense(chemin)
    assert relu == fin
    assert relu.utcoffset() == fin.utcoffset()


def test_l_heure_relue_se_compare_a_maintenant_sans_lever():
    """Une heure relue NAIVE ferait lever la soustraction dans `main()`, apres
    le devis et juste avant la depense : le pire endroit."""
    import tempfile
    from datetime import datetime
    with tempfile.TemporaryDirectory() as d:
        chemin = f"{d}/registre.json"
        cp.noter_depense(datetime.fromisoformat("2026-09-06T19:45:22+02:00"),
                         1000, chemin)
        reste = cp.rouvre_a(cp.derniere_depense(chemin)) - cp.maintenant()
    assert reste.total_seconds() != 0


def test_registre_absent_ou_illisible_rend_none_sans_lever():
    """Un registre corrompu rend l'heure INCONNUE, jamais interdite : bloquer
    ici transformerait un fichier abime en panne totale du banc."""
    import io as _io
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        assert cp.derniere_depense(f"{d}/rien.json") is None
        for contenu in ("pas du json", "{}", '{"fin": null}',
                        '{"fin": "pas une date"}', '{"fin": 42}'):
            chemin = f"{d}/abime.json"
            _io.open(chemin, "w", encoding="utf-8").write(contenu)
            assert cp.derniere_depense(chemin) is None, contenu


def test_la_duree_vient_du_CHRONOMETRE_pas_du_plafond_suppose():
    """La duree se derivait de `reservation / 8000 jetons par minute` et
    sortait 34 minutes. La campagne du 06/09 a soutenu 20 600 jetons de
    reservation par minute : le plafond du compte de PRODUCTION ne decrit pas
    le compte d'OUTILLAGE, et la duree etait fausse d'un facteur 2,6.

    Ce test epingle la source : les secondes chronometrees, jamais le plafond.
    """
    from membench.scoring import TPM_CEILING
    d = cp.devis(40)
    attendu = sum(cp.SECONDES_PAR_QUESTION[k] * 40
                  for k in cp.COUT_PAR_QUESTION) / 60
    assert d["minutes_estimees"] == attendu
    assert d["minutes_estimees"] != d["reservation"] / TPM_CEILING
    assert cp.devis(80)["minutes_estimees"] == 2 * d["minutes_estimees"]


def test_les_vitesses_chronometrees_collent_a_la_campagne_mesuree():
    """Elles doivent se relire dans `results-cost-seed1.json`, sinon ce sont
    des nombres inventes qui ressemblent a des mesures."""
    import json
    with open("results-cost-seed1.json", encoding="utf-8") as fh:
        mesure = json.load(fh)
    for bras in ("D+", "C", "A"):
        r = mesure[f"seed1/{bras}"]
        chrono = r["seconds"] / r["asked"]
        assert abs(cp.SECONDES_PAR_QUESTION[bras] - chrono) < 0.02, bras
    # B n'a jamais tourne : sa valeur est une EXTRAPOLATION, pas une mesure,
    # et elle doit rester coherente avec le cout par jeton de C et A.
    par_jeton = [mesure[f"seed1/{b}"]["seconds"] / mesure[f"seed1/{b}"]["asked"]
                 / cp.COUT_PAR_QUESTION[b] for b in ("C", "A")]
    attendu = cp.COUT_PAR_QUESTION["B"] * sum(par_jeton) / len(par_jeton)
    assert abs(cp.SECONDES_PAR_QUESTION["B"] - attendu) < 0.5


def test_le_cout_de_B_se_derive_du_prompt_et_non_du_neant():
    """Le bras B n'a JAMAIS termine une question, et son cout est pourtant le
    chiffre qui porte la conclusion publiee (il ne tient pas dans une journee).

    Un nombre sans source dans un README public est une dette : celui-ci valait
    3 483 et personne, moi compris, ne pouvait dire d'ou il venait. Il est
    maintenant DERIVE, et ce test refait la derivation entierement :

      * on construit le prompt de chaque bras par le chemin de code de la
        campagne, jamais une copie a la main ;
      * on calibre le rapport caracteres/jeton sur A et C, dont le fournisseur
        a RAPPORTE les jetons de prompt ;
      * on applique ce rapport a B et on compare a la constante.

    Si le prompt de B change, ce test rougit, ce qui est exactement ce qu'on
    veut d'un chiffre qu'aucune campagne ne peut verifier pour l'instant.
    """
    import json
    from membench.corpus import build_corpus, candidates, timeline
    from membench.real_arms import (PROMPTS, FullContextArm, RetrievalArm,
                                    StatelessArm, _ModelArm, _question)

    f = build_corpus(seed=1)
    tl, pool = list(timeline(f)), candidates(f)
    q = f[0]

    def prompt_complet(cls):
        a = cls(None, pool)
        a.observe(tl)
        ctx = a._context(q.subject, q.relation)
        pose = _question(q.subject, q.relation, pool)
        return PROMPTS[a._prompt] + "\n" + (f"{ctx}\n\n{pose}" if ctx else pose)

    with open("results-cost-seed1.json", encoding="utf-8") as fh:
        mesure = json.load(fh)

    rapports = []
    for nom, cls in (("A", StatelessArm), ("C", RetrievalArm)):
        jetons = mesure[f"seed1/{nom}"]["tokens_per_turn"] - _ModelArm.MAX_TOKENS
        rapports.append(len(prompt_complet(cls)) / jetons)
    # Deux prompts de longueurs tres differentes doivent donner le MEME
    # rapport, sinon la conversion ne vaut rien et B n'est pas derivable.
    assert abs(rapports[0] - rapports[1]) / max(rapports) < 0.10, rapports

    ratio = sum(rapports) / len(rapports)
    attendu = len(prompt_complet(FullContextArm)) / ratio + _ModelArm.MAX_TOKENS
    ecart = abs(cp.COUT_PAR_QUESTION["B"] - attendu) / attendu
    assert ecart < 0.03, (cp.COUT_PAR_QUESTION["B"], attendu, ecart)


def test_le_bras_B_ne_tient_toujours_pas_dans_une_journee():
    """La conclusion publiee, epinglee sur le corpus entier."""
    besoin = cp.COUT_PAR_QUESTION["B"] * 104 / cp.FACTEUR_REEL
    assert besoin > cp.TPD, besoin
