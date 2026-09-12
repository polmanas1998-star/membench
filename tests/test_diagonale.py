# -*- coding: utf-8 -*-
"""La diagonale : ce qui compte, c'est le POIDS, et le poids plafonne a 3 ecritures.

CE QUE CES TESTS FIGENT (mesure 2026-09-13, d=2048)
---------------------------------------------------
`learn()` sur un fait deja connu monte son poids de 0,25 jusqu'a 1,5. Trois
ecritures et vingt sont donc la meme memoire. Sur les MEMES paires :

  · 3 verites contre 3 mensonges et contre 4 mensonges : resultat identique,
    z compris. La table de correction publiee le 07/09 (33 % contre 58 %)
    opposait deux egalites, l'ecart venait des graines.
  · 1 verite contre 3 mensonges et contre 20 : identique.
  · UNE correction ecrite 45 jours apres trois mensonges revient 79 % du temps
    avec le fond reconfirme, 100 % avec le fond vieilli. Il avait ete ecrit
    qu'elle perdait encore.

Le jour ou le plafond bouge, les deux premiers tests rougissent, et c'est voulu :
les lignes du README au-dela de 3 repetitions redeviendraient des mesures
distinctes et il faudrait les remesurer.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

pytest.importorskip("numpy")
try:
    from diagonale import correction_tardive, poids
    from poisoning import une_attaque
except ImportError as exc:  # pragma: no cover
    pytest.skip(f"holomem absent : {exc}", allow_module_level=True)

GRAINES = range(1, 13)


def _cellule(vrais: int, faux: int) -> list[tuple[str, float]]:
    return [une_attaque(g, 2048, vrais, faux) for g in GRAINES]


def test_le_poids_plafonne_a_trois_ecritures():
    assert (poids(1), poids(2), poids(3), poids(20)) == (1.0, 1.25, 1.5, 1.5)


def test_TROIS_et_QUATRE_mensonges_contre_trois_verites_sont_la_meme_memoire():
    """Le 33 % contre 58 % publie etait deux tirages d'une meme egalite."""
    assert _cellule(3, 3) == _cellule(3, 4)


def test_VINGT_mensonges_ne_pesent_pas_plus_que_trois():
    assert _cellule(1, 3) == _cellule(1, 20)


def test_UNE_correction_bat_trois_mensonges_perimes_d_une_demi_vie():
    """L'affirmation inverse a ete publiee. Variante prudente : fond reconfirme."""
    issues = [correction_tardive(g, 2048, 3, 45, fond_reconfirme=True)[0]
              for g in GRAINES]
    assert issues.count("verite") / len(issues) >= 0.6, issues
    assert issues.count("mensonge") / len(issues) <= 0.2, issues


def test_sans_delai_la_correction_tardive_est_la_cellule_d_attaque():
    """Le jour 0 du banc : si ca diverge, le harnais n'interroge plus les memes paires.

    Le z est compare a 1e-9 pres et non a l'egalite : ici les mensonges entrent
    AVANT la verite, dans `une_attaque` apres. La somme est commutative, les
    arrondis flottants non (ecart mesure a la 13e decimale).
    """
    for g in GRAINES:
        issue, z = correction_tardive(g, 2048, 3, 0, fond_reconfirme=False)
        issue_ref, z_ref = une_attaque(g, 2048, 1, 3)
        assert issue == issue_ref
        assert z == pytest.approx(z_ref, rel=1e-9)
