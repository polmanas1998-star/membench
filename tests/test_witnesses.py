"""Les temoins du jour zero.

Ce fichier ne teste pas les bras reels. Il teste le BANC, avec trois systemes
dont on connait d'avance le verdict. Tant qu'il n'est pas vert, aucun chiffre
produit par ce depot ne vaut d'etre publie.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from membench.arms import GuessArm, NullArm, OracleArm, run
from membench.corpus import (AS_OF, DEFAULT_MIX, Fact, Statement, build_corpus,
                             candidates, timeline)
from membench.scoring import Answer, Report, score


@pytest.fixture
def facts():
    return build_corpus(seed=1)


@pytest.fixture
def tl(facts):
    return list(timeline(facts))


# --------------------------------------------------------------------------
# Le corpus
# --------------------------------------------------------------------------

def test_corpus_est_deterministe():
    a = build_corpus(seed=7)
    b = build_corpus(seed=7)
    assert a == b
    assert build_corpus(seed=8) != a


def test_corpus_contient_les_cinq_genres_aux_bonnes_parts(facts):
    counts: dict[str, int] = {}
    for f in facts:
        counts[f.kind] = counts.get(f.kind, 0) + 1
    assert counts == DEFAULT_MIX


def test_une_part_reelle_de_faits_jamais_dits(facts):
    """Sans ABSENCE, un bras qui repond toujours ne peut pas etre pris en faute."""
    absents = [f for f in facts if f.truth is None]
    assert len(absents) / len(facts) > 0.15


def test_la_verite_est_le_dernier_enonce(facts):
    for f in facts:
        if f.statements:
            assert f.truth == f.statements[-1].obj


def test_un_fait_mis_a_jour_expose_sa_valeur_perimee(facts):
    superseded = [f for f in facts if f.kind == "superseded"]
    assert superseded
    for f in superseded:
        assert f.superseded is not None
        assert f.superseded != f.truth


def test_un_fait_renforce_n_a_pas_de_valeur_perimee(facts):
    """Redire le meme fait n'est pas le contredire."""
    for f in facts:
        if f.kind == "reinforced":
            assert len(f.statements) > 1
            assert f.superseded is None


def test_l_age_court_depuis_la_derniere_confirmation_pas_la_creation():
    """Le fait est pose il y a un an et redit hier : il est frais.

    C'est la distinction qu'un historique complet colle dans un contexte ne
    sait pas exprimer, et elle doit etre vraie dans le corpus avant d'etre
    demandee a quiconque.
    """
    vieux = Statement(AS_OF - timedelta(days=365), "Le cabinet", "se_situe_à", "Lille")
    frais = Statement(AS_OF - timedelta(days=1), "Le cabinet", "se_situe_à", "Lille")
    f = Fact("Le cabinet", "se_situe_à", "reinforced", (vieux, frais))
    assert f.age_days() == 1


def test_la_chronologie_est_ordonnee(facts, tl):
    dates = [s.when for s in tl]
    assert dates == sorted(dates)
    assert len(tl) == sum(len(f.statements) for f in facts)


def test_le_corpus_refuse_au_dela_de_son_plafond():
    """Le vocabulaire s'etend tout seul, donc le garde ne peut plus etre
    « plus de paires que disponibles ». Il devient un plafond explicite, sinon
    rendre le corpus extensible aurait retire le garde sans le remplacer."""
    from membench.corpus import MAX_FACTS

    build_corpus(seed=0, mix={"stable": MAX_FACTS})          # la borne passe
    with pytest.raises(ValueError, match="plafond"):
        build_corpus(seed=0, mix={"stable": MAX_FACTS + 1})  # au-dela, non


# --------------------------------------------------------------------------
# Le piege principal : le silence ne doit pas payer
# --------------------------------------------------------------------------

def test_le_bras_muet_ne_decroche_pas_un_sans_faute(facts, tl):
    arm = NullArm()
    r = score(facts, run(arm, facts, tl))
    assert r.coverage == 0.0
    assert r.gated_precision is None, (
        "une precision calculee sur zero reponse doit valoir None : "
        "sinon se taire partout donne le meilleur score du banc"
    )


def test_une_precision_nulle_ne_se_confond_pas_avec_une_precision_absente():
    """0.0 et None sont deux verdicts differents, et le banc doit les separer."""
    muet = Report(asked=4, answered=0, correct=0, retention_ok=0, retention_n=0,
                  stale_returned=0, supersession_n=0, age_flagged=0,
                  age_answered=0, age_n=0, malformed=0, expired_ok=0, expired_n=0,
                  hallucinated=0, absence_n=0, prompt_tokens_total=0)
    faux = Report(asked=4, answered=4, correct=0, retention_ok=0, retention_n=4,
                  stale_returned=0, supersession_n=0, age_flagged=0,
                  age_answered=0, age_n=0, malformed=0, expired_ok=0, expired_n=0,
                  hallucinated=0, absence_n=0, prompt_tokens_total=0)
    assert muet.gated_precision is None
    assert faux.gated_precision == 0.0


# --------------------------------------------------------------------------
# Les trois temoins doivent se distinguer
# --------------------------------------------------------------------------

def test_le_bras_qui_devine_hallucine_sur_tout_ce_qui_n_a_jamais_ete_dit(facts, tl):
    arm = GuessArm(candidates(facts), seed=3)
    r = score(facts, run(arm, facts, tl))
    assert r.coverage == 1.0
    assert r.hallucination == 1.0
    assert r.gated_precision is not None and r.gated_precision < 0.25


def test_l_oracle_repond_juste_date_le_vieux_et_refuse_l_inconnu(facts, tl):
    r = score(facts, run(OracleArm(facts), facts, tl))
    assert r.gated_precision == 1.0
    assert r.hallucination == 0.0
    assert r.supersession_error == 0.0
    assert r.age_awareness == 1.0
    answerable = sum(1 for f in facts if f.truth is not None)
    assert r.coverage == pytest.approx(answerable / len(facts))


def test_aucun_temoin_ne_depasse_l_oracle(facts, tl):
    oracle = score(facts, run(OracleArm(facts), facts, tl))
    guess = score(facts, run(GuessArm(candidates(facts), seed=5), facts, tl))
    assert guess.gated_precision < oracle.gated_precision
    assert guess.hallucination > oracle.hallucination


def test_les_trois_temoins_rendent_trois_verdicts_distincts(facts, tl):
    """La regle du jour zero. Si ce test tombe, le banc ne mesure rien."""
    rows = [
        score(facts, run(NullArm(), facts, tl)).as_row(),
        score(facts, run(GuessArm(candidates(facts), seed=9), facts, tl)).as_row(),
        score(facts, run(OracleArm(facts), facts, tl)).as_row(),
    ]
    signatures = {(r["coverage"], r["gated_precision"], r["hallucination"])
                  for r in rows}
    assert len(signatures) == 3


# --------------------------------------------------------------------------
# Le compte des jetons, qui est la moitie du resultat
# --------------------------------------------------------------------------

def test_le_debit_se_derive_des_jetons_par_tour():
    r = Report(asked=10, answered=10, correct=10, retention_ok=10, retention_n=10,
               stale_returned=0, supersession_n=0, age_flagged=0, age_answered=0,
               age_n=0, malformed=0, expired_ok=0, expired_n=0, hallucinated=0, absence_n=0,
               prompt_tokens_total=36_000)
    assert r.tokens_per_turn == 3600.0
    assert r.turns_per_minute == pytest.approx(8000 / 3600)


def test_un_bras_sans_jetons_comptes_ne_publie_pas_de_debit(facts, tl):
    """Zero jeton veut dire NON MESURE, pas un debit infini."""
    r = score(facts, run(NullArm(), facts, tl))
    assert r.tokens_per_turn == 0.0
    assert r.turns_per_minute is None


def test_le_banc_refuse_d_apparier_des_longueurs_differentes(facts):
    with pytest.raises(ValueError, match="apparier"):
        score(facts, [Answer("x")])


# --------------------------------------------------------------------------
# Denominateurs
# --------------------------------------------------------------------------

def test_la_conscience_de_l_age_se_mesure_sur_les_vieux_faits_REPONDUS(facts, tl):
    """Refuser un vieux fait n'est pas la meme faute que le servir comme neuf.

    Un bras qui refuse tous les vieux faits ne doit pas etre puni sur la
    conscience de l'age : il n'a rien affirme qui puisse etre date.
    """
    answers = []
    for f in facts:
        if f.kind == "faded":
            answers.append(Answer(None))
        else:
            answers.append(Answer(f.truth) if f.truth else Answer(None))
    r = score(facts, answers)
    assert r.age_n > 0
    assert r.age_answered == 0
    assert r.age_awareness is None


def test_chaque_classe_a_un_denominateur_reel(facts, tl):
    """Le defaut du 05/09 : `age_awareness` valait 1.000 sur UN seul fait.

    Une classe dont le denominateur tombe a un ou deux ne mesure rien et
    publie quand meme un pourcentage. Le corpus doit garantir qu'aucune classe
    n'arrive en dessous d'un seuil ou le ratio devient du bruit.
    """
    from membench.real_arms import DermiozArm
    r = score(facts, run(DermiozArm(dim=2048), facts, tl))
    assert r.retention_n >= 10
    assert r.supersession_n >= 10
    assert r.expired_n >= 10
    assert r.absence_n >= 10
    assert r.age_answered >= 10, (
        f"seulement {r.age_answered} vieux faits repondus sur {r.age_n} : "
        "la conscience de l'age est mesuree sur du bruit"
    )


def test_une_reponse_vide_ne_compte_pas_comme_une_abstention_calibree():
    """La panne du 05/09 : trois bras casses affichaient une hallucination nulle.

    Un modele a raisonnement dont le budget de sortie est trop serre rend zero
    caractere. Sans ce compteur, le banc lit ce silence comme de la prudence et
    publie un bras en panne comme un bras exemplaire.
    """
    facts = build_corpus(seed=2)[:6]
    casse = [Answer(None, malformed=True) for _ in facts]
    prudent = [Answer(None, malformed=False) for _ in facts]
    assert score(facts, casse).malformed_rate == 1.0
    assert score(facts, prudent).malformed_rate == 0.0
    # Les deux ont la meme couverture : c'est bien pour cela qu'il faut la
    # deuxieme colonne pour les distinguer.
    assert score(facts, casse).coverage == score(facts, prudent).coverage


def test_une_reponse_vide_du_MODELE_est_marquee_illisible():
    """Le garde precedent construisait l'Answer a la main : il ne traversait
    jamais `ask`, donc il ne gardait pas la detection, seulement le compteur.

    Ici on fait vraiment repondre un modele qui rend zero caractere, ce qui est
    exactement ce que fait un modele a raisonnement au budget trop serre.
    """
    from membench.corpus import candidates
    from membench.providers import Completion
    from membench.real_arms import StatelessArm

    class _Muet:
        def complete(self, system, user, max_tokens=0):
            return Completion(text="", prompt_tokens=100, completion_tokens=48)

    facts = build_corpus(seed=3)
    arm = StatelessArm(_Muet(), candidates(facts))
    a = arm.ask("Le cabinet", "se_situe_à")
    assert a.value is None
    assert a.malformed is True, (
        "une reponse vide doit etre marquee illisible, sinon un modele en "
        "panne passe pour un modele prudent"
    )

    class _Prudent:
        def complete(self, system, user, max_tokens=0):
            return Completion(text="ANSWER: UNKNOWN\nSTALE: no",
                              prompt_tokens=100, completion_tokens=12)

    b = StatelessArm(_Prudent(), candidates(facts)).ask("Le cabinet", "se_situe_à")
    assert b.value is None and b.malformed is False


def test_la_liste_de_candidats_est_reordonnee_a_chaque_question():
    """Sinon un biais de position se melange au signal de memoire.

    La liste etait triee, donc identique mot pour mot d'une question a l'autre.
    Un modele qui prefere systematiquement la premiere entree aurait vu ce
    penchant compte comme de la memoire.
    """
    from membench.corpus import candidates
    from membench.real_arms import _question

    pool = candidates(build_corpus(seed=1))
    a = _question("Le cabinet", "se_situe_à", pool)
    b = _question("Karim", "livre_le_client", pool)
    la = a.split("Candidates: ")[1]
    lb = b.split("Candidates: ")[1]
    assert la != lb, "deux questions recoivent la meme liste, dans le meme ordre"
    assert sorted(la.split(", ")) == sorted(lb.split(", ")), "meme contenu"


def test_le_reordonnancement_est_reproductible():
    """Tous les bras doivent voir la MEME liste, sinon on remplace un biais
    par un autre et les bras cessent d'etre comparables."""
    from membench.corpus import candidates
    from membench.real_arms import _question

    pool = candidates(build_corpus(seed=1))
    assert _question("Karim", "livre_le_client", pool) == \
           _question("Karim", "livre_le_client", pool)


def test_le_corpus_s_etend_sans_changer_de_registre():
    """Une echelle qui change de style de nom cesse d'etre comparable.

    Le vocabulaire fixe couvre 120 paires. Au-dela il s'etend par des entrees
    numerotees du meme registre, et les 120 premieres paires restent celles
    d'avant, sinon deux echelles mesureraient deux corpus differents.
    """
    petit = build_corpus(seed=4, mix={"stable": 100, "absent": 20})
    grand = build_corpus(seed=4, mix={"stable": 300, "absent": 60})
    assert len(petit) == 120 and len(grand) == 360
    for f in grand:
        assert f.relation in {x.relation for x in petit}, "relation inventee"


