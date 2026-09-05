"""Un corpus de faits qui vieillissent, avec sa chronologie.

Le banc pose quatre questions a un systeme de memoire, et une seule d'entre
elles est celle que tout le monde mesure (retrouve-t-il le fait ?). Les trois
autres sont celles ou une memoire hebergee n'a structurellement rien :

  RETENTION   un fait dit une fois, il y a longtemps, jamais repete
  PEREMPTION  un fait mis a jour depuis : rend-il l'ancien ou le nouveau ?
  AGE         sait-il que sa reponse date, ou la sert-il comme neuve ?
  ABSENCE     sur un fait jamais dit, refuse-t-il, ou invente-t-il ?

Le corpus est deterministe pour une graine donnee. Il ne contient aucune
donnee de sante et aucune personne reelle : le sujet est un cabinet
d'architecture fictif.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterator, Literal

Kind = Literal["stable", "superseded", "faded", "expired", "reinforced", "absent"]

# Une memoire qui vieillit a un seuil au-dela duquel elle laisse tomber. Chez
# holomem : demi-vie 45 jours, plancher de poids 0,18, donc un fait quitte la
# trace a 45 * log2(1/0.18) = 111 jours. Les bandes d'age ci-dessous sont
# posees AUTOUR de ce seuil, et non choisies pour qu'il tombe bien.
#
# Ce seuil est une propriete de UN des quatre bras. Les trois autres recoivent
# la meme chronologie et ne decroissent pas, donc la bande `expired` est celle
# ou l'historique complet bat la couche memoire. Elle est ici pour ca.
FORGET_THRESHOLD_DAYS = 111

# Au-dela de quoi une reponse doit porter une reserve sur son age. Derive de la
# demi-vie de la memoire, pas choisi rond : a une demi-vie un fait ne pese plus
# que la moitie de ce qu'il pesait, et le servir sans le dire est un mensonge
# par omission. Le seuil est ANNONCE dans le prompt des bras qui appellent un
# modele, pour qu'aucun n'ait a le deviner.
STALE_AFTER_DAYS = 45

#: Plafond dur sur la taille d'un corpus. Le vocabulaire s'etend tout seul
#: au-dela de 120 paires, ce qui a d'abord fait disparaitre le garde qui
#: refusait l'impossible. Une borne explicite le remet.
MAX_FACTS = 2000

# Le jour ou l'on interroge. Toutes les dates du corpus sont anterieures.
AS_OF = date(2026, 9, 5)


@dataclass(frozen=True)
class Statement:
    """Un fait tel qu'il a ete ENONCE, a une date donnee."""

    when: date
    subject: str
    relation: str
    obj: str

    def as_utterance(self) -> str:
        return f"{self.subject} {self.relation.replace('_', ' ')} {self.obj}."


@dataclass(frozen=True)
class Fact:
    """Un fait et toute son histoire, du premier enonce a aujourd'hui."""

    subject: str
    relation: str
    kind: Kind
    statements: tuple[Statement, ...] = field(default=())

    @property
    def truth(self) -> str | None:
        """La bonne reponse aujourd'hui. None quand le fait n'a jamais ete dit."""
        if not self.statements:
            return None
        return self.statements[-1].obj

    @property
    def superseded(self) -> str | None:
        """L'objet perime, celui qu'un systeme sans notion de temps va rendre."""
        if len(self.statements) < 2:
            return None
        older = {s.obj for s in self.statements[:-1]} - {self.truth}
        return sorted(older)[0] if older else None

    @property
    def last_confirmed(self) -> date | None:
        return self.statements[-1].when if self.statements else None

    def age_days(self, as_of: date = AS_OF) -> int | None:
        """Jours depuis la DERNIERE confirmation, pas depuis la creation.

        La distinction n'est pas cosmetique : un fait repete hier est frais
        meme s'il a ete pose il y a un an, et c'est exactement ce qu'un
        historique complet colle dans le contexte ne sait pas exprimer.
        """
        if self.last_confirmed is None:
            return None
        return (as_of - self.last_confirmed).days


# Le materiau. Des relations d'un cabinet d'architecture, sans donnee sensible.
_SUBJECTS = (
    "Le cabinet", "Nadia", "Le chantier Beaupré", "Le chantier Villon",
    "L'agence de Lyon", "Le studio maquette", "Karim", "Le pôle concours",
    "L'équipe exécution", "Le chantier Rive-Neuve", "Inès", "Le service marchés",
)
_RELATIONS = (
    "utilise_le_logiciel", "livre_le_client", "travaille_avec_le_bureau",
    "se_situe_à", "rend_les_plans_en", "facture_au_format",
    "archive_ses_dossiers_sur", "commande_ses_tirages_chez",
    "suit_le_planning_sur", "fait_ses_rendus_avec",
)
_OBJECTS = (
    "ArchiCAD", "Revit", "Vectorworks", "AutoCAD", "Rhino",
    "Sogeprom", "Bouygues", "Nexity", "Vinci", "Eiffage",
    "Toulouse", "Nantes", "Lille", "Bordeaux", "Rennes",
    "IFC", "DWG", "PDF/A", "RVT", "SKP",
    "Dropbox", "Nextcloud", "OneDrive", "un NAS Synology", "S3",
    "Copytop", "Repro-Sud", "Corep", "Pixartprinting",
)

# Combien de faits de chaque genre. Les proportions comptent : sans une part
# reelle d'ABSENCE, un systeme qui repond toujours ne peut pas etre pris en
# faute, et le banc devient une mesure de rappel deguisee.
DEFAULT_MIX: dict[Kind, int] = {
    "stable": 18,      # frais, dans la trace sans discussion
    "faded": 22,       # vieux mais encore au-dessus du plancher : une reserve est attendue
    "expired": 14,     # au-dela du seuil d'oubli : la couche a le droit de se taire
    "superseded": 18,
    "reinforced": 10,
    "absent": 22,
}
# Les parts ont ete relevees le 05/09 apres relecture : la classe `age` ne
# rendait que 5 reponses sur 12, et un ratio sur 5 est du bruit presente en
# pourcentage. Le banc mesure ce que son plus petit denominateur permet.


def _spread(rng: random.Random, kind: Kind) -> list[int]:
    """Les ages, en jours avant AS_OF, des enonces d'un fait.

    Rendus du plus ancien au plus recent.
    """
    if kind == "stable":
        # Moins d'une demi-vie : aucune excuse pour l'avoir perdu.
        return [rng.randint(5, 40)]
    if kind == "faded":
        # Entre une demi-vie et le seuil d'oubli : encore tenu, mais une
        # reponse sans reserve sur l'age est une reponse qui ment par omission.
        return [rng.randint(55, FORGET_THRESHOLD_DAYS - 6)]
    if kind == "expired":
        # Au-dela du seuil. Se taire est ici la bonne reponse pour une memoire
        # qui decroit, et repondre juste est la bonne reponse pour un contexte
        # complet. Les deux ont raison, et le banc doit montrer les deux.
        return [rng.randint(FORGET_THRESHOLD_DAYS + 40, 320)]
    if kind == "superseded":
        old = rng.randint(120, 300)
        new = rng.randint(10, min(90, old - 20))
        return [old, new]
    if kind == "reinforced":
        first = rng.randint(150, 300)
        mid = rng.randint(60, first - 30)
        last = rng.randint(3, min(45, mid - 10))
        return [first, mid, last]
    raise ValueError(f"pas d'enonce pour le genre {kind!r}")


def build_corpus(seed: int = 0, mix: dict[Kind, int] | None = None,
                 as_of: date = AS_OF) -> list[Fact]:
    """Construit un corpus deterministe.

    Chaque paire (sujet, relation) est unique, sinon deux faits se
    contrediraient sans que le corpus le sache, et la verite de reference
    dependrait de l'ordre de lecture.
    """
    mix = dict(mix or DEFAULT_MIX)
    rng = random.Random(seed)

    needed = sum(mix.values())
    subjects, relations = list(_SUBJECTS), list(_RELATIONS)
    # Le vocabulaire fixe couvre 120 paires. Au-dela, on l'etend par des
    # entrees NUMEROTEES du meme registre plutot que d'inventer du vocabulaire
    # au coup par coup : une echelle qui change de style de nom au passage
    # cesserait d'etre comparable aux precedentes, et on lirait un effet de
    # lexique comme un effet de capacite.
    if needed > MAX_FACTS:
        raise ValueError(
            f"{needed} faits demandes, plafond {MAX_FACTS}. Rendre le corpus "
            "extensible a supprime le garde qui existait : sans borne, une "
            "faute de frappe dans le melange ferait tourner la boucle "
            "indefiniment. Releve MAX_FACTS en connaissance de cause."
        )
    while len(subjects) * len(relations) < needed:
        subjects.append(f"Le chantier n{len(subjects) - len(_SUBJECTS) + 1}")
    pairs = [(s, r) for s in subjects for r in relations]
    rng.shuffle(pairs)
    if needed > len(pairs):
        raise ValueError(
            f"{needed} faits demandes pour {len(pairs)} paires (sujet, relation) "
            "disponibles : elargis _SUBJECTS ou _RELATIONS"
        )

    facts: list[Fact] = []
    cursor = 0
    for kind, count in mix.items():
        for _ in range(count):
            subject, relation = pairs[cursor]
            cursor += 1
            if kind == "absent":
                facts.append(Fact(subject, relation, kind, ()))
                continue
            ages = _spread(rng, kind)
            objs = rng.sample(_OBJECTS, len(ages))
            if kind == "reinforced":
                # Un fait renforce est le MEME objet redit, pas un objet neuf.
                objs = [objs[0]] * len(ages)
            statements = tuple(
                Statement(as_of - timedelta(days=age), subject, relation, obj)
                for age, obj in zip(sorted(ages, reverse=True), objs)
            )
            facts.append(Fact(subject, relation, kind, statements))

    rng.shuffle(facts)
    return facts


def timeline(facts: list[Fact]) -> Iterator[Statement]:
    """Tous les enonces du corpus, dans l'ordre chronologique reel.

    C'est ce qu'un bras « historique complet » recoit dans son contexte.
    """
    everything = [s for f in facts for s in f.statements]
    everything.sort(key=lambda s: (s.when, s.subject, s.relation))
    return iter(everything)


def candidates(facts: list[Fact]) -> list[str]:
    """Les objets plausibles, pour que le refus soit un choix et non un aveu.

    Un systeme a qui l'on ne donne pas de candidats ne peut pas etre juge sur
    sa calibration : il n'a pas de liste ou puiser une mauvaise reponse.
    """
    seen = {s.obj for f in facts for s in f.statements}
    return sorted(seen)
