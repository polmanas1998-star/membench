# -*- coding: utf-8 -*-
"""Les deux chambres : ce que la couche fait quand l'environnement ment, et
quand elle n'entend plus que sa jumelle.

CE QUE CES TESTS FIGENT (2026-09-07, d=2048, porte z >= 4)
----------------------------------------------------------
CHAMBRE CLOSE. Six pieces. Deux sont SILENCIEUSES, c'est-a-dire qu'elles
repondent au-dessus du seuil sans que rien dans la reponse ne dise que la piece
etait truquee :

  · magasin minuscule : 6 inventions sur 6, a z = inf. La cause est explicite
    dans `query_gated` : `if len(scored) < 3: return scored[0][1], math.inf`.
    Sous trois objets distincts la porte ne peut pas douter, alors elle ouvre.
    Un service qui vient de demarrer, ou dont la purge a tout efface, est donc
    maximalement sur de lui.
  · saturation x10 : 2 inventions sur 6, a z 4,83, au-dessus du seuil.

Les quatre autres tiennent ou se taisent, y compris la trace corrompue et
l'horloge avancee de dix ans. Le temoin sain repond 18/18 sans rien inventer,
sans quoi le banc mesurerait sa propre severite.

DETENTION LONGUE. La meme memoire interrogee de plus en plus tard tient 18/18
jusqu'a 111 jours, puis tombe a un silence complet entre 111 jours et 6 mois.
Elle n'invente a AUCUN jalon. Vieillir seule ne la rend pas menteuse.

CHAMBRE D'ECHO. Deux memoires qui ne s'entendent plus qu'elles, et le
mecanisme n'est pas celui qu'on attend. Au tour 1, A dit la verite a z 17,7 et
B dit la faussete a z 47,0 : le MOINS informe est le PLUS sur, parce que son
magasin est plus petit et que le vainqueur s'y detache mieux. Apres l'echange,
ni l'une ni l'autre ne repond. Les deux affirmations opposees s'ANNULENT, la
porte se ferme, et la paire reste muette des deux cotes a tous les tours
suivants.

La faussete n'a pas gagne. La verite non plus. A la SAVAIT, A avait RAISON, et
apres un seul echange avec B il ne peut plus jamais repondre : 1 fait perdu sur
18 contre le temoin sans boucle, et c'est une ERASURE, pas une corruption.

Et le `z` va de 14,10 a 14,99 sur toute la duree. Il ne dit rien de l'etat de
la boucle. Une memoire enfermee est aussi sure d'elle qu'une memoire qui parle
au monde, et rien dans sa sortie ne les separe.

CES TESTS NE SONT PAS LA POUR QUE LA COUCHE PASSE. Ils figent le comportement
ACTUEL, et ils rougiront le jour ou quelqu'un ferme la porte sous trois
candidats, ce qui serait une bonne nouvelle.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RACINE))

pytest.importorskip("holomem", reason="le magasin n'est pas installe")

import chambre_close as CC   # noqa: E402
import chambre_echo as CE    # noqa: E402

from datetime import datetime, timezone   # noqa: E402

_TS = datetime(2026, 9, 7, tzinfo=timezone.utc).timestamp()
_DIM = 2048
_Z = 4.0


def test_le_temoin_sain_repond_et_n_invente_rien():
    """Sans ce temoin, un banc qui trouve tout le monde coupable ne mesure que
    sa propre severite."""
    r = CC.piece_temoin(_DIM, _TS, _Z)
    assert r["justes"] == r["connues"], "la piece saine ne repond meme plus"
    assert r["inventees"] == 0, "elle invente alors que rien n'est truque"


def test_un_magasin_MINUSCULE_repond_a_tout_avec_une_confiance_INFINIE():
    """Le defaut le plus grave des six, et il est structurel.

    `query_gated` rend `math.inf` sous trois candidats. Un magasin qui vient
    d'etre purge repond donc a n'importe quelle question, au-dessus de tout
    seuil imaginable. Ce test rougira le jour ou la porte se fermera dans ce
    cas, et ce jour-la il faudra le supprimer en s'en rejouissant.
    """
    r = CC.piece_magasin_minuscule(_DIM, _TS, _Z)
    assert r["inventees"] == r["absentes"], (
        "le magasin minuscule n'invente plus sur tout : la porte a change"
    )
    assert r["z_max_invente"] >= 1e9, "la confiance n'est plus infinie"
    assert CC.verdict("magasin minuscule", r) == "SILENCIEUX"


def test_une_horloge_avancee_de_dix_ans_fait_TAIRE_et_pas_MENTIR():
    """Le bon comportement, fige pour qu'une regression se voie : tout tombe
    sous le plancher de poids, et la couche se tait au lieu d'inventer."""
    r = CC.piece_horloge_avancee(_DIM, _TS, _Z)
    assert r["muettes"] == r["connues"]
    assert r["inventees"] == 0, "elle invente une fois la trace videe"


def test_la_detention_longue_n_invente_a_AUCUN_jalon():
    """Vieillir seule ne rend pas la couche menteuse. C'est la reponse a
    « et si on l'enfermait un mois » : a un mois, rien ne bouge."""
    jalons = CC.detention(_DIM, _TS, _Z)
    par_nom = {j["jalon"]: j for j in jalons}
    assert par_nom["1 mois"]["justes"] == par_nom["depart"]["justes"], (
        "un mois de detention a change les reponses"
    )
    assert all(j["inventees"] == 0 for j in jalons), (
        "un jalon invente : le vieillissement seul suffit a la faire mentir"
    )


def test_deux_affirmations_opposees_s_ANNULENT_et_le_fait_est_PERDU():
    """Le vrai mecanisme, et ce n'est pas celui qu'on croit.

    La faussete ne gagne pas. La verite non plus. Les deux s'annulent des le
    premier echange, le vainqueur ne se detache plus du lot, la porte se ferme,
    et la paire reste MUETTE des deux cotes a tous les tours suivants.

    A savait ce fait, A avait raison, et apres un seul echange avec B il ne
    peut plus jamais repondre. C'est une ERASURE, pas une corruption, et rien
    dans la sortie ne signale la perte.
    """
    lignes = CE.un_tour(_DIM, 8, _Z, _TS)
    temoin = CE.temoin_sans_boucle(_DIM, 8, _Z, _TS)
    fin = lignes[-1]
    assert fin["contaminee"] == 0, "la faussete a survecu : autre mecanisme"
    assert fin["annulee"] == 1, (
        "la paire disputee n'est plus muette des deux cotes : l'annulation "
        "mutuelle a change, et le verdict du banc avec elle"
    )
    cout = temoin["juste"] - fin["juste"]
    assert cout == 1, (
        f"la boucle coute {cout} faits et non 1 : ce n'est plus la seule paire "
        "disputee qui se perd"
    )


def test_la_paire_disputee_reste_muette_a_TOUS_les_tours_suivants():
    """L'erasure est definitive, pas un creux passager. Chaque tour reinjecte
    l'ambiguite, donc rien ne la resorbe jamais."""
    lignes = CE.un_tour(_DIM, 8, _Z, _TS)
    apres = [l for l in lignes if l["tour"] >= 1]
    assert all(l["annulee"] == 1 for l in apres), (
        "la paire redevient repondable a un tour : l'erasure n'est plus definitive"
    )


def test_le_z_ne_dit_RIEN_de_l_etat_de_la_boucle():
    """LE resultat de cette chambre. Si un jour le `z` s'effondre quand la
    boucle se ferme, ce test rougit et c'est une bonne nouvelle : la couche
    aurait gagne un moyen de signaler qu'elle n'entend plus le monde."""
    lignes = CE.un_tour(_DIM, 8, _Z, _TS)
    zs = [l["z_median"] for l in lignes if l["z_median"] is not None]
    assert min(zs) > 10.0, (
        "le z est tombe : la couche sait peut-etre maintenant qu'elle est enfermee"
    )
    assert max(zs) - min(zs) < 3.0, (
        "le z bouge desormais avec l'etat de la boucle, ce test a fait son temps"
    )


def test_un_fait_FANE_n_est_jamais_RETIRE_sans_qu_on_le_demande():
    """La reponse au « et si on l'enferme des annees ».

    Passe 111 jours la couche se tait, et elle se tait proprement : mesuree
    jusqu'a 100 000 ans elle n'invente jamais. Mais elle ne LIBERE rien. Un
    fait fane reste dans le magasin, sur le disque, et dans chaque
    reconstruction de la trace. `forget_faded()` existe et fait le travail ;
    personne ne l'appelle, ni dans la bibliotheque, ni dans le produit.

    Mesure du 07/09 : 2 000 faits fanes font passer une requete de 1,2 ms a
    10,2 ms, soit 8,5 fois, pour des faits qui ne contribuent a rien. Un appel
    a `forget_faded()` ramene a 0,7 ms sans toucher a la justesse, 20/20 dans
    les deux cas. Ce test fige la STRUCTURE, pas le chronometre, parce qu'un
    chiffre de temps rougit sur une machine chargee et n'apprend rien.
    """
    from holomem import HolographicMemory   # noqa: PLC0415

    h = {"t": _TS}
    m = HolographicMemory(dim=512, now_fn=lambda: h["t"])
    for i in range(50):
        m.learn(f"vieux{i}", "rel", f"obj{i % 10}")
    h["t"] = _TS + 400 * 86400.0
    for i in range(5):
        m.learn(f"frais{i}", "rel", f"obj{i % 10}")

    assert len(m) == 55, "le magasin ne contient plus ce qu'on y a mis"
    # Sans demande explicite, la decroissance ne retire RIEN.
    assert len(m) == 55, "un fait fane a disparu tout seul : la couche a change"
    retires = m.forget_faded()
    assert retires == 50, f"forget_faded a retire {retires} faits au lieu de 50"
    assert len(m) == 5, "la purge explicite ne libere pas ce qu'elle annonce"
