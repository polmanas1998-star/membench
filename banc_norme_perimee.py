"""La norme perimee : le danger que la recherche par similarite ne voit pas.

LE CAS REEL (chantier, hopital, service marches)
────────────────────────────────────────────────
Une procedure change. L'ancienne version est ecrite dans les mots que TOUT LE
MONDE utilise encore, parce que c'est comme ca qu'on l'a apprise. La nouvelle
est publiee dans le vocabulaire du texte reglementaire, qui n'est pas le meme.

Quand quelqu'un demande la regle avec les mots d'hier, une recherche par
similarite — lexicale ou vectorielle — retrouve l'ANCIEN texte, qui ressemble
le plus a la question, et le sert avec aplomb. C'est le mode de panne le plus
dangereux d'un RAG en entreprise : il n'est pas faux par hasard, il est faux
PARCE QUE la question ressemble a la vieille version.

CE QUE CE BANC MESURE, ET RIEN D'AUTRE
──────────────────────────────────────
Avant tout modele, au niveau de ce qui est INJECTE :
  · PERIME SERVI  la valeur abrogee est dans le contexte, la nouvelle non.
                  C'est la faute grave : le modele n'a aucun moyen de deviner.
  · A JOUR        la valeur en vigueur est presente.
  · LES DEUX      les deux versions sont la : le modele peut trancher sur les
                  dates, donc ce n'est pas une faute du systeme de rappel.
  · MUET          rien n'est injecte. Sans danger, mais sans service.

Trois systemes, meme corpus, meme question, zero jeton :
  lexical   recouvrement de mots, k plus proches
  FAISS     embeddings du produit + index plat exact, k plus proches
  Dermioz   la trace du produit : une abrogation CONTREDIT l'ancienne valeur,
            qui quitte le ledger au lieu de rester consultable.

TEMOIN DU JOUR ZERO
───────────────────
Avant abrogation, les trois doivent servir la valeur en vigueur. Si l'un echoue
deja la, le banc mesure autre chose que l'obsolescence.

    python -X utf8 banc_norme_perimee.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

#: ⚠ Paye le 16/09 : ce chemin est RELATIF au dossier courant, et sa valeur par
#: defaut designe la production. Lance depuis un worktree, le banc mesurait
#: l'ancien code tout en affichant le nom de la branche : les deux regimes
#: rendaient la meme table, ce qui ressemblait a « le reglage ne change rien »
#: alors que le module lu ignorait le reglage. Un instrument qui peut mesurer
#: un autre arbre que celui qu'on croit doit DIRE lequel il a lu.
sys.path.insert(0, os.environ.get("DERMIOZ_SRC", "../dermioz-ai/src"))

import temporal_hologram as th  # noqa: E402

AUJOURDHUI = date(2026, 9, 16)
K = 6


@dataclass(frozen=True)
class Norme:
    cle: str            # sujet de la memoire (la procedure)
    relation: str       # ce qu'on demande
    ancienne: str       # la valeur ABROGEE
    nouvelle: str       # la valeur EN VIGUEUR
    dit_ancien: str     # l'enonce d'hier, dans les mots de la question
    dit_nouveau: str    # l'enonce d'aujourd'hui, dans d'AUTRES mots
    question: str       # pose avec les mots d'hier, comme sur le terrain


NORMES = [
    Norme("harnais antichute", "hauteur minimale", "3 metres", "2 metres",
          "Le harnais antichute est obligatoire au-dela de 3 metres de hauteur.",
          "Protection individuelle contre les chutes requise des 2 metres de denivele.",
          "a partir de quelle hauteur le harnais antichute est-il obligatoire ?"),
    Norme("plan de prevention", "delai de transmission", "8 jours", "15 jours",
          "Le plan de prevention doit etre transmis 8 jours avant le demarrage.",
          "Le document unique de coordination parvient au coordonnateur deux semaines avant ouverture du chantier.",
          "quel est le delai de transmission du plan de prevention ?"),
    Norme("permis de feu", "duree de validite", "24 heures", "12 heures",
          "Le permis de feu est valable 24 heures apres sa signature.",
          "L'autorisation de travaux par point chaud expire une demi-journee apres delivrance.",
          "quelle est la duree de validite du permis de feu ?"),
    Norme("vestiaire chantier", "surface par personne", "1,25 m2", "1,80 m2",
          "Le vestiaire chantier compte 1,25 m2 par personne.",
          "Les locaux de repos offrent 1,80 m2 d'espace libre par compagnon present.",
          "quelle surface par personne pour le vestiaire chantier ?"),
    Norme("controle des echafaudages", "periodicite", "trimestrielle", "mensuelle",
          "Le controle des echafaudages est trimestriel.",
          "La verification des plateformes de travail en hauteur est reconduite chaque mois.",
          "quelle est la periodicite du controle des echafaudages ?"),
    Norme("dechets amiante", "duree de conservation", "5 ans", "10 ans",
          "Les bordereaux de dechets amiante se conservent 5 ans.",
          "La tracabilite des fibres reglementees est archivee une decennie.",
          "quelle est la duree de conservation des dechets amiante ?"),
    Norme("visite medicale", "frequence", "tous les 2 ans", "tous les 5 ans",
          "La visite medicale a lieu tous les 2 ans.",
          "Le suivi individuel de l'etat de sante est renouvele au plus tard la cinquieme annee.",
          "quelle est la frequence de la visite medicale ?"),
    Norme("consignation electrique", "nombre d'operateurs", "1 operateur", "2 operateurs",
          "La consignation electrique se fait avec 1 operateur habilite.",
          "La mise hors tension exige la presence de deux intervenants habilites.",
          "combien d'operateurs pour la consignation electrique ?"),
]


def _fold(x: str) -> str:
    n = unicodedata.normalize("NFKD", (x or "").lower())
    return "".join(c for c in n if not unicodedata.combining(c))


def _verdict(bloc: str, n: Norme, abroge: bool) -> str:
    """Le verdict se lit par rapport a la valeur EN VIGUEUR ce jour-la.

    Au jour zero, l'ancienne valeur EST la regle : la servir est juste. Ne pas
    en tenir compte transformerait le temoin en fausse accusation, et un
    instrument qui accuse au repos ne mesure rien.
    """
    bas = _fold(bloc)
    a, nv = _fold(n.ancienne) in bas, _fold(n.nouvelle) in bas
    en_vigueur, abrogee = (nv, a) if abroge else (a, False)
    if en_vigueur and abrogee:
        return "les deux"
    if en_vigueur:
        return "a jour"
    if abrogee:
        return "perime servi"
    return "muet"


def _enonces(abroge: bool) -> list[tuple[date, str]]:
    """L'historique tel qu'il arrive : l'ancien d'abord, la mise a jour ensuite."""
    out = []
    for i, n in enumerate(NORMES):
        out.append((AUJOURDHUI - timedelta(days=1800 + i), n.dit_ancien))
        if abroge:
            out.append((AUJOURDHUI - timedelta(days=40 + i), n.dit_nouveau))
    return out


def _lexical(enonces, question: str) -> str:
    want = set(re.findall(r"\w+", _fold(question)))
    rangs = sorted(enonces, key=lambda e: -len(want & set(re.findall(r"\w+", _fold(e[1])))))
    return "\n".join(f"[{d.isoformat()}] {t}" for d, t in rangs[:K])


def _faiss_bloc(enonces, question: str, enc, faiss, np) -> str:
    textes = [f"[{d.isoformat()}] {t}" for d, t in enonces]
    v = enc.encode(textes, normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    idx = faiss.IndexFlatIP(v.shape[1]); idx.add(v)
    q = enc.encode([question], normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    _d, ids = idx.search(q, min(K, len(textes)))
    return "\n".join(textes[i] for i in ids[0] if i >= 0)


def _dermioz_bloc(abroge: bool):
    """La memoire du produit. Une abrogation CONTREDIT l'ancienne valeur."""
    horloge = {"t": datetime(AUJOURDHUI.year, AUJOURDHUI.month, AUJOURDHUI.day,
                             tzinfo=timezone.utc).timestamp()}
    h = th.TemporalHologram(None, dim=1024, now_fn=lambda: horloge["t"])
    jour = 86_400.0
    for i, n in enumerate(NORMES):
        horloge["t"] -= (1800 + i) * jour
        h.learn(n.cle, n.relation, n.ancienne)
        horloge["t"] += (1800 + i) * jour
    if abroge:
        for i, n in enumerate(NORMES):
            horloge["t"] -= (40 + i) * jour
            h.contradict(n.cle, n.relation, n.ancienne)
            h.learn(n.cle, n.relation, n.nouvelle)
            horloge["t"] += (40 + i) * jour
    h.decay()
    return h


#: Consigne NEUTRE, et c'est un choix de banc. Une premiere version disait « une
#: procedure perimee donnee comme certaine est la pire des reponses » : elle
#: apprenait la prudence aux bras concurrents, donc elle mesurait ma consigne et
#: non leur systeme de rappel. On demande la meme chose a tout le monde, sans
#: souffler la reponse.
_SYSTEME = (
    "Tu reponds a une question de procedure interne, a partir du contexte fourni. "
    f"Nous sommes le {AUJOURDHUI.isoformat()}. "
    "Une seule ligne, rien d'autre :" + chr(10) +
    "VALEUR: <la valeur, recopiee du contexte, ou INCONNUE si le contexte ne la donne pas>"
)


def _nombres(x: str) -> set[str]:
    """Les nombres d'une valeur, ecrits en chiffres OU en toutes lettres.

    « 2 metres », « 2 m » et « deux metres » sont la MEME reponse. Comparer les
    chaines entieres faisait tomber la moitie des bonnes reponses dans « autre »
    et rendait le banc illisible : ce n'etait pas le systeme qui variait, c'etait
    la facon dont le modele recopiait la valeur.
    """
    mots = {"un": "1", "une": "1", "deux": "2", "trois": "3", "quatre": "4",
            "cinq": "5", "six": "6", "huit": "8", "dix": "10", "douze": "12",
            "quinze": "15", "vingt-quatre": "24", "demi-journee": "12",
            "decennie": "10", "mensuelle": "mois", "trimestrielle": "trimestre",
            "chaque mois": "mois"}
    bas = _fold(x)
    out = set(re.findall(r"\d+[,.]?\d*", bas))
    for mot, val in mots.items():
        if mot in bas:
            out.add(val)
    for lettre in ("mensuel", "trimestriel", "mois", "trimestre"):
        if lettre in bas:
            out.add("mois" if "mens" in lettre or lettre == "mois" else "trimestre")
    return out


def _verdict_reponse(texte: str, n: Norme, abroge: bool) -> str:
    """Ce que le MODELE a fini par dire, une fois le contexte lu."""
    bas = _fold(texte)
    m = re.search(r"valeur\s*:\s*(.+)", bas)
    dit = (m.group(1) if m else bas).strip()
    if "inconnue" in dit:
        return "refus"
    vus = _nombres(dit)
    en_vigueur = _nombres(n.nouvelle if abroge else n.ancienne)
    abrogee = _nombres(n.ancienne) if abroge else set()
    touche_vigueur = bool(vus & en_vigueur)
    touche_abroge = bool(vus & abrogee) and not (abrogee & en_vigueur)
    if touche_vigueur and not touche_abroge:
        return "a jour"
    if touche_abroge and not touche_vigueur:
        return "PERIME AFFIRME"
    if touche_vigueur and touche_abroge:
        return "les deux"
    return "autre"


def _campagne_llm(modele: str, blocs_par_systeme, abroge: bool) -> dict:
    # Le fournisseur se DEDUIT du nom du modele. Un banc qui ne sait interroger
    # qu'un seul fournisseur mesure ce fournisseur : tant qu'un second modele
    # n'a pas rejoue les chiffres, on ne sait pas si la faute vient de la
    # memoire ou du modele qui la lit.
    from membench.providers import modele_pour
    m = modele_pour(modele, account="outillage")
    out = {}
    for systeme, blocs in blocs_par_systeme.items():
        compte = {}
        for n, bloc in zip(NORMES, blocs):
            user = ((bloc + chr(10) + chr(10) + n.question) if bloc
                    else ("(aucun element en memoire)" + chr(10) + chr(10) + n.question))
            c = m.complete(_SYSTEME, user, max_tokens=256)
            v = _verdict_reponse(c.text, n, abroge)
            compte[v] = compte.get(v, 0) + 1
        out[systeme] = compte
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", default="", help="modeles a interroger, separes par une virgule")
    args = ap.parse_args()
    import faiss  # noqa: F401
    import numpy as np
    from sentence_transformers import SentenceTransformer
    enc = SentenceTransformer(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    print(f"module lu      : {Path(th.__file__).resolve()}")
    print(f"reglages lus   : "
          + json.dumps(th.TemporalHologram.reglages(), ensure_ascii=False)
          if hasattr(th.TemporalHologram, "reglages") else
          "reglages lus   : (ce module n'expose pas reglages())")

    sortie = {}
    for scenario, abroge in (("temoin jour zero (rien n'a change)", False),
                             ("apres abrogation", True)):
        enonces = _enonces(abroge)
        h = _dermioz_bloc(abroge)
        compte = {"lexical": {}, "FAISS": {}, "Dermioz": {}}
        detail = []
        for n in NORMES:
            blocs = {
                "lexical": _lexical(enonces, n.question),
                "FAISS": _faiss_bloc(enonces, n.question, enc, faiss, np),
                "Dermioz": h.injection_block(f"{n.cle} {n.relation} ?"),
            }
            for sys_, bloc in blocs.items():
                v = _verdict(bloc, n, abroge)
                compte[sys_][v] = compte[sys_].get(v, 0) + 1
                if sys_ == "lexical":
                    detail.append((n.cle, v))
        sortie[scenario] = {"injecte": compte}
        if args.llm:
            blocs_par_systeme = {"lexical": [], "FAISS": [], "Dermioz": []}
            for n in NORMES:
                blocs_par_systeme["lexical"].append(_lexical(enonces, n.question))
                blocs_par_systeme["FAISS"].append(_faiss_bloc(enonces, n.question, enc, faiss, np))
                blocs_par_systeme["Dermioz"].append(h.injection_block(f"{n.cle} {n.relation} ?"))
            for modele in args.llm.split(","):
                rep = _campagne_llm(modele.strip(), blocs_par_systeme, abroge)
                sortie[scenario][modele.strip()] = rep
                print(chr(10) + f"  ce que {modele.strip()} REPOND :")
                print(f"  {'systeme':<10}{'PERIME AFFIRME':>16}{'a jour':>9}{'refus':>7}{'les deux':>10}{'autre':>7}")
                for sys_, c in rep.items():
                    print(f"  {sys_:<10}{c.get('PERIME AFFIRME', 0):>16}{c.get('a jour', 0):>9}"
                          f"{c.get('refus', 0):>7}{c.get('les deux', 0):>10}{c.get('autre', 0):>7}")
        print(f"\n{scenario}, {len(NORMES)} normes")
        print(f"  {'systeme':<10}{'perime servi':>14}{'a jour':>9}{'les deux':>10}{'muet':>7}")
        for sys_, c in compte.items():
            print(f"  {sys_:<10}{c.get('perime servi', 0):>14}{c.get('a jour', 0):>9}"
                  f"{c.get('les deux', 0):>10}{c.get('muet', 0):>7}")
    Path("results-norme-perimee.json").write_text(
        json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
