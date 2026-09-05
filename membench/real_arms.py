"""Les quatre bras reels, sur un modele de base tenu constant.

  A  le modele seul, sans etat            le plancher
  B  le modele + tout l'historique        la vraie ligne de base, et la forte
  C  le modele + une recherche top-k      la reponse standard en production
  D  la couche memoire de Dermioz         le traitement mesure

Tous rendent la MEME forme de reponse, sinon le banc mesurerait le respect
d'un format et non la memoire. Le contrat est une ligne `ANSWER:` valant un
candidat exact ou UNKNOWN, et une ligne `STALE:` valant yes ou no.
"""

from __future__ import annotations

import os
import random
import re
import sys
from datetime import date, datetime, timezone

from typing import Sequence

from .corpus import AS_OF, STALE_AFTER_DAYS, Statement
from .scoring import Answer

# La date du jour est dans le prompt : sans elle, demander a un modele si un
# fait est perime n'a pas de sens, et on mesurerait son ignorance du calendrier
# plutot que sa gestion de l'age.
# Deux formulations du MEME contrat, pour separer le signal de la redaction.
#
# Un banc qui ne teste qu'un phrasing ne sait pas si son resultat porte sur le
# systeme ou sur la tournure trouvee ce jour-la. Les deux ci-dessous demandent
# exactement la meme chose et partagent peu de mots : l'une donne des consignes,
# l'autre decrit un role. Si les colonnes bougent entre les deux, la conclusion
# est un artefact de redaction, et il faut le dire avant de publier le reste.
_SYSTEM_A = (
    "You answer questions about one architecture practice from what you have "
    f"been told. Today is {AS_OF.isoformat()}.\n"
    "Reply with exactly two lines and nothing else:\n"
    "ANSWER: <one candidate copied verbatim from the list, or UNKNOWN>\n"
    f"STALE: <yes if your answer rests on information older than "
    f"{STALE_AFTER_DAYS} days, else no>\n"
    "Answer UNKNOWN when you were never told. A wrong confident answer is worse "
    "than UNKNOWN."
)

_SYSTEM_B = (
    f"Date: {AS_OF.isoformat()}. You keep records for an architecture practice "
    "and are asked to look one up.\n"
    "Output format, two lines, no commentary:\n"
    "ANSWER: the matching candidate, spelled as listed, or UNKNOWN\n"
    f"STALE: yes when the record you used is more than {STALE_AFTER_DAYS} days "
    "old, otherwise no\n"
    "If no record covers the question, UNKNOWN is the right output. Guessing "
    "costs more than admitting the gap."
)

PROMPTS = {"A": _SYSTEM_A, "B": _SYSTEM_B}
_SYSTEM = _SYSTEM_A

def _parse(text: str, pool: Sequence[str]) -> tuple[str | None, bool]:
    """Rend (objet ou None, drapeau d'age).

    Un candidat non reconnu compte comme un REFUS et non comme une erreur : le
    banc mesure la memoire, pas la capacite a recopier une liste. Ce choix est
    conservateur pour les bras qui appellent un modele, donc il ne peut pas
    flatter le bras D.
    """
    ans = re.search(r"^\s*ANSWER:\s*(.+?)\s*$", text, re.MULTILINE | re.IGNORECASE)
    stale = re.search(r"^\s*STALE:\s*(\w+)", text, re.MULTILINE | re.IGNORECASE)
    flagged = bool(stale and stale.group(1).lower().startswith("y"))
    if not ans:
        return None, flagged
    value = ans.group(1).strip().strip('."')
    if value.upper() == "UNKNOWN":
        return None, flagged
    lowered = {c.lower(): c for c in pool}
    return lowered.get(value.lower()), flagged

def _question(subject: str, relation: str, pool: Sequence[str]) -> str:
    """La liste de candidats est REORDONNEE a chaque question.

    Defaut trouve le 05/09 : la liste etait triee, donc identique mot pour mot
    d'une question a l'autre. Un modele qui prefere la premiere entree, ou la
    derniere, aurait vu son biais de position se melanger au signal de memoire
    sans qu'aucune colonne ne les distingue. C'est le genre de confusion qu'un
    relecteur releve en premier, et il aurait eu raison.

    L'ordre vient d'un tirage derive de (sujet, relation) : il varie d'une
    question a l'autre et reste identique d'un bras a l'autre et d'un run a
    l'autre. Decorrele sans cesser d'etre reproductible, parce que tous les
    bras doivent voir la MEME liste, sinon on remplace un biais par un autre.
    """
    order = list(pool)
    random.Random(f"{subject}|{relation}").shuffle(order)
    return (f"Question: {subject} {relation.replace('_', ' ')} what?\n"
            f"Candidates: {', '.join(order)}")

class _ModelArm:
    """Base des bras A, B et C : tout ce qui appelle le modele."""

    name = "modele"

    def __init__(self, model, pool: Sequence[str], prompt: str = "A") -> None:
        self._model = model
        self._pool = list(pool)
        self._prompt = prompt
        self._timeline: list[Statement] = []

    def observe(self, timeline: Sequence[Statement]) -> None:
        self._timeline = list(timeline)

    def _context(self, subject: str, relation: str) -> str:
        return ""

    #: Un modele a raisonnement depense AVANT d'ecrire. Mesure le 05/09 sur
    #: gpt-oss-120b : a 48 jetons de budget la completion en consomme 48 et le
    #: texte revient VIDE ; a 512 elle repond mais le bras a contexte long redevient illisible 42 % du temps, donc 1024. Un budget
    #: trop serre ne tronque pas la reponse, il la supprime.
    MAX_TOKENS = 1024

    def ask(self, subject: str, relation: str) -> Answer:
        ctx = self._context(subject, relation)
        user = (f"{ctx}\n\n{_question(subject, relation, self._pool)}"
                if ctx else _question(subject, relation, self._pool))
        c = self._model.complete(PROMPTS[self._prompt], user,
                                 max_tokens=self.MAX_TOKENS)
        value, flagged = _parse(c.text, self._pool)
        malformed = not re.search(r"ANSWER:", c.text, re.IGNORECASE)
        # Le plafond par minute se prend sur prompt + RESERVATION, pas sur les
        # jetons reellement produits : le fournisseur immobilise le budget
        # demande. Mesure du depot produit le 31/08 : prompt 3 442 + 1 280
        # reserves = 1,69 tour par minute.
        return Answer(value, stale_flagged=flagged, malformed=malformed,
                      prompt_tokens=c.prompt_tokens + self.MAX_TOKENS)

class StatelessArm(_ModelArm):
    """A. On ne lui a rien dit. Le plancher : tout ce qu'il rend est invente."""

    name = "A modele seul"

class FullContextArm(_ModelArm):
    """B. Tout l'historique, date, dans le prompt, a chaque tour.

    C'est ce que fait tout le monde, c'est la ligne de base FORTE, et c'est
    celle qui coute le plus cher par tour. Le resultat interessant du banc est
    la ou elle gagne en exactitude et perd en debit.
    """

    name = "B historique complet"

    def _context(self, subject: str, relation: str) -> str:
        lines = [f"[{s.when.isoformat()}] {s.as_utterance()}" for s in self._timeline]
        return "What you have been told, oldest first:\n" + "\n".join(lines)

class RetrievalArm(_ModelArm):
    """C. Une recherche lexicale, les k enonces les plus proches.

    Lexicale et non semantique, faute de fournisseur d'embeddings ici, et c'est
    ecrit plutot que sous-entendu : un RAG semantique ferait mieux sur la
    reformulation. Sur CETTE tache les cles sont litterales, donc l'ecart entre
    les deux est petit, mais il n'est pas nul et le chiffre doit le dire.
    """

    name = "C recherche top-k"

    def __init__(self, model, pool: Sequence[str], k: int = 6,
                 prompt: str = "A") -> None:
        super().__init__(model, pool, prompt)
        self._k = k

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"\w+", text.lower()))

    def _context(self, subject: str, relation: str) -> str:
        want = self._tokens(subject) | self._tokens(relation.replace("_", " "))
        scored = sorted(
            self._timeline,
            key=lambda s: (
                -len(want & (self._tokens(s.subject) | self._tokens(s.relation.replace("_", " ")))),
                -s.when.toordinal(),
            ),
        )
        hits = scored[: self._k]
        if not hits:
            return ""
        hits.sort(key=lambda s: s.when)
        lines = [f"[{s.when.isoformat()}] {s.as_utterance()}" for s in hits]
        return f"The {len(hits)} most relevant things you were told:\n" + "\n".join(lines)

class DermiozArm:
    """D. La couche memoire : holomem, horloge simulee, garde z.

    Ce bras n'appelle PAS le modele, et c'est le resultat, pas une triche : sur
    une question factuelle de ce genre la couche repond seule, donc elle depense
    zero jeton de prompt la ou le bras B depense tout l'historique. Le chiffre
    est donc un PLANCHER de cout : le produit reel ferait encore formuler la
    reponse par le modele, ce qui ajouterait un tour court.
    """

    name = "D couche Dermioz"

    def __init__(self, dim: int = 1024, as_of: date = AS_OF,
                 stale_after_days: int = STALE_AFTER_DAYS) -> None:
        # holomem est une dependance externe (MIT) :
        #   github.com/polmanas1998-star/holomem
        # Soit il est installe, soit on dit ou le chercher. Un `sys.path`
        # code en dur marcherait sur une seule machine au monde.
        extra = os.environ.get("HOLOMEM_PATH")
        if extra:
            sys.path.insert(0, extra)
        try:
            from holomem import HolographicMemory, fold  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depend de l'install
            raise ImportError(
                "holomem introuvable. Clone github.com/polmanas1998-star/holomem "
                "et pose HOLOMEM_PATH sur son dossier, ou installe-le."
            ) from exc

        self._fold = fold
        self._as_of = as_of
        self._day = 86_400.0
        self._as_of_ts = datetime(as_of.year, as_of.month, as_of.day,
                                  tzinfo=timezone.utc).timestamp()
        self._now = self._as_of_ts
        self._stale_after = stale_after_days
        self._mem = HolographicMemory(dim=dim, now_fn=lambda: self._now)

    def observe(self, timeline: Sequence[Statement]) -> None:
        for s in timeline:
            ts = datetime(s.when.year, s.when.month, s.when.day,
                          tzinfo=timezone.utc).timestamp()
            # L'horloge avance a la date de l'enonce pendant qu'on apprend,
            # sinon `last_seen` vaudrait aujourd'hui pour tout le corpus et la
            # decroissance ne mesurerait plus rien.
            self._now = ts
            self._mem.learn(s.subject, s.relation, s.obj, created_ts=ts)
        self._now = self._as_of_ts

    def _age_days(self, subject: str, relation: str) -> float | None:
        """L'age selon la MEMOIRE, pas selon le corpus.

        Le bras ne doit pas consulter la verite de reference, meme pour un
        detail : un dictionnaire annexe rempli a l'apprentissage dirait aussi
        quels faits n'ont jamais ete enonces, ce que la memoire est justement
        censee devoir deduire.
        """
        ks, kr = self._fold(subject), self._fold(relation)
        seen = [f.last_seen_ts for f in self._mem.facts()
                if self._fold(f.s) == ks and self._fold(f.r) == kr]
        if not seen:
            return None
        return (self._as_of_ts - max(seen)) / self._day

    #: Au-dela du seuil d'oubli, la trace ne porte plus le fait : ce qui reste
    #: est du bruit, et le garde `z` note ce bruit comme il noterait un
    #: souvenir. Mesure du 05/09 sur 8 graines : sur les 112 faits perimes, la
    #: couche rendait 0 bonne reponse, 109 silences et 3 FAUX. Refuser la
    #: classe entiere ne coute donc aucune bonne reponse et retire 3 erreurs
    #: sur 5. Un garde d'age n'est pas redondant avec un garde de confiance :
    #: le second mesure la nettete du souvenir, le premier son droit d'exister.
    REFUSE_AFTER_DAYS = 111

    def ask(self, subject: str, relation: str) -> Answer:
        value, _z = self._mem.query_gated(subject, relation)
        if value is None:
            return Answer(None, prompt_tokens=0)
        age = self._age_days(subject, relation)
        if age is not None and age > self.REFUSE_AFTER_DAYS:
            return Answer(None, prompt_tokens=0)
        return Answer(value,
                      stale_flagged=age is not None and age > self._stale_after,
                      prompt_tokens=0)

class DermiozGroundedArm:
    """D+. La couche recupere le fait, PUIS le modele redige.

    `DermiozArm` rend zero jeton parce qu'il n'appelle jamais le modele. C'est
    vrai et c'est trompeur : un produit reel fait formuler la reponse. Un cout
    de 0 se lit comme une triche, et un lecteur a raison de s'en mefier.

    Ce bras-ci est le cout HONNETE de la couche : ce que la memoire recupere,
    et rien d'autre, est injecte dans le prompt. A comparer au bras B, qui
    colle la chronologie entiere a chaque question.
    """

    name = "D+ couche puis modele"

    def __init__(self, model, pool: Sequence[str], dim: int = 2048,
                 as_of: date = AS_OF, prompt: str = "A") -> None:
        self._model = model
        self._pool = list(pool)
        self._prompt = prompt
        self._mem = DermiozArm(dim=dim, as_of=as_of)

    def observe(self, timeline: Sequence[Statement]) -> None:
        self._mem.observe(timeline)

    def ask(self, subject: str, relation: str) -> Answer:
        recalled = self._mem.ask(subject, relation)
        if recalled.value is None:
            # La memoire se tait. Le produit ne depense PAS un tour pour
            # rediger un refus qu'il connait deja, et le banc ne doit pas lui
            # facturer des jetons qu'il n'aurait pas payes.
            return Answer(None, prompt_tokens=0)
        age = "old" if recalled.stale_flagged else "recent"
        ctx = (f"Your memory returns one fact, and nothing else:\n"
               f"{subject} {relation.replace('_', ' ')} {recalled.value}. "
               f"This memory is {age}.")
        user = f"{ctx}\n\n{_question(subject, relation, self._pool)}"
        c = self._model.complete(PROMPTS[self._prompt], user,
                                 max_tokens=_ModelArm.MAX_TOKENS)
        value, flagged = _parse(c.text, self._pool)
        malformed = not re.search(r"ANSWER:", c.text, re.IGNORECASE)
        return Answer(value, stale_flagged=flagged, malformed=malformed,
                      prompt_tokens=c.prompt_tokens + _ModelArm.MAX_TOKENS)
