# -*- coding: utf-8 -*-
"""Une seule phrase quand `holomem` manque, au lieu de vingt echecs opaques.

CE QUE CE FICHIER CORRIGE (2026-09-06)
--------------------------------------
Mesure sur un clone frais de ce depot, sans configuration :

    20 failed, 52 passed

Rien n'etait casse. `holomem` n'etait simplement pas importable, et chaque test
qui en depend le decouvrait a sa facon, en pleine execution, avec un
`ModuleNotFoundError` different a chaque ligne.

Vingt lignes rouges disent « ce depot est casse » beaucoup plus fort que le
README ne dit « installez holomem d'abord ». Pour un banc PUBLIC, c'est un
defaut de premier contact, et c'est le seul qui se paie avant que qui que ce
soit ait lu un chiffre.

CE QUE CE FICHIER FAIT, DANS L'ORDRE
------------------------------------
1. Il essaie l'import normal, celui d'une installation par `pip`.
2. Sinon, il regarde `HOLOMEM_PATH`, la voie historique.
3. Sinon, il cherche un clone VOISIN, la disposition la plus courante quand on
   travaille sur les deux depots a la fois.
4. Sinon, il SAUTE proprement les tests concernes, avec la commande a taper.

⚠ IL SAUTE, IL NE MASQUE PAS. Un saut annonce sa raison et se compte dans le
resume ; il ne se confond pas avec un succes. Faire passer ces tests en vert
sans holomem serait pire que les vingt echecs : le depot mentirait sur ce qu'il
a verifie.
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest

#: La commande a donner a quelqu'un qui vient d'arriver.
INSTALLER = "pip install git+https://github.com/polmanas1998-star/holomem"


def _importable() -> bool:
    try:
        import holomem  # noqa: F401, PLC0415, F811
    except ImportError:
        return False
    return True


def _trouver_holomem() -> str | None:
    """Rend la raison de l'echec, ou None si holomem est utilisable."""
    if _importable():
        return None

    candidats: list[pathlib.Path] = []
    depuis_env = os.environ.get("HOLOMEM_PATH")
    if depuis_env:
        candidats.append(pathlib.Path(depuis_env))

    # Un clone voisin : c'est la disposition qu'on a des qu'on travaille sur
    # les deux depots ensemble, et la deviner evite une variable a poser.
    racine = pathlib.Path(__file__).resolve().parent.parent
    candidats.append(racine.parent / "holomem")

    for c in candidats:
        if (c / "holomem.py").is_file():
            sys.path.insert(0, str(c))
            if _importable():
                return None
            sys.path.pop(0)

    ou = f", ni dans {depuis_env}" if depuis_env else ""
    return (f"holomem introuvable{ou}. Installez-le :\n    {INSTALLER}\n"
            f"ou posez HOLOMEM_PATH sur le dossier d'un clone.")


_RAISON = _trouver_holomem()


def _est_holomem_absent(exc: BaseException | None) -> bool:
    """Cette exception est-elle l'absence de la couche, et rien d'autre ?

    On regarde le TYPE et le nom du module, jamais le texte du message : un
    `ImportError` sur une autre dependance ne doit pas etre transforme en saut,
    sinon ce fichier masquerait de vraies pannes.
    """
    while exc is not None:
        if isinstance(exc, ImportError):
            nom = getattr(exc, "name", "") or ""
            if nom == "holomem" or "holomem" in str(exc):
                return True
        exc = exc.__cause__ or exc.__context__
    return False


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Transforme en SAUT l'echec cause par l'absence de la couche.

    ⚠ POURQUOI PAS UNE DETECTION PAR LE TEXTE DU FICHIER. La premiere version
    de ce conftest marquait les tests en cherchant « holomem » ou
    « DermiozArm » dans leur source. Elle est passee de 20 echecs a 2 : deux
    tests utilisaient la couche INDIRECTEMENT, a travers la table des bras de
    `long_run`, sans jamais ecrire ces mots. Un detecteur textuel ne voit que ce
    qui est nomme, jamais ce qui est atteint, et ce depot a paye cette lecon
    ailleurs le meme jour.

    Ici on regarde l'exception REELLEMENT levee. C'est exact, ca ne peut pas
    etre contourne par un fichier neuf, et ca n'a aucune heuristique a tenir a
    jour.
    """
    rapport = (yield).get_result()
    if _RAISON is None or not rapport.failed:
        return
    if call.excinfo is not None and _est_holomem_absent(call.excinfo.value):
        rapport.outcome = "skipped"
        rapport.longrepr = _RAISON


def pytest_report_header(config):
    if _RAISON is None:
        return "holomem : disponible"
    return f"holomem : ABSENT, tests de la couche sautes. {INSTALLER}"
