# -*- coding: utf-8 -*-
"""arene.py : l'arène portable. Les mêmes questions, posées au même modèle, de trois façons.

Ce que le banc compare
──────────────────────
Un modèle de langue ne lit jamais « l'entreprise » : il lit ce qu'on lui met sous
les yeux. Trois façons de le faire, celles qu'on trouve sur le marché :

  fenetre   Tout le dossier dans la fenêtre du modèle : déclarations et documents,
            datés, dans l'ordre. C'est ce que font les assistants grand public
            quand on leur dépose des fichiers.
  rag       Recherche vectorielle classique : les 6 lignes les plus proches de la
            question (FAISS exact, encodeur multilingue public). C'est l'architecture
            de la plupart des assistants d'entreprise.
  dermioz   La mémoire du produit : chaque fait est appris avec sa provenance
            (« declare » pour ce que dit une personne, « graphe » pour un document
            importé), puis le bloc de rappel du produit est donné au modèle.

Le modèle qui répond est LE MÊME dans les trois cas : seule change la façon de lui
présenter le dossier.

Trois épreuves, rédigées comme la vie d'une PME fictive (Ravel Distribution)
───────────────────────────────────────────────────────────────────────────
  radote    Une personne a tranché une valeur. Ensuite, huit documents importés
            (mail transféré, export de tableur, compte rendu, wiki…) recopient
            l'ANCIENNE proposition. Bonne réponse : ce que la personne a décidé.
            Plusieurs documents disent eux-mêmes la date de leur contenu d'origine :
            un lecteur attentif a de quoi trancher.
  change    Témoin : la personne change VRAIMENT d'avis. Bonne réponse : la nouvelle
            valeur. Un système qui s'entête sur la première échouerait ici.
  jamais    On demande un fait que personne n'a jamais donné (le même client a
            d'autres faits, la même rubrique existe pour d'autres clients).
            Bonne réponse : « je ne sais pas ». Toute valeur est inventée.

Règles d'équité, écrites AVANT de lancer
────────────────────────────────────────
  * Dermioz n'est jamais aidé : aucun appel à contradict(), seulement learn(),
    avec la provenance que le texte donne aussi aux autres (« Document importé »).
  * Même consigne, neutre, pour tous : elle ne souffle ni la prudence ni la règle.
  * Température 0. Un dossier par question, tiré d'une graine : tout est rejouable.
  * Limite assumée : Dermioz reçoit les faits déjà extraits (client, rubrique,
    valeur). La lecture de textes libres par le produit n'est PAS mesurée ici.

Le rendre portable
──────────────────
N'importe quel modèle compatible OpenAI se branche :

    python -X utf8 arene.py --modele gpt-4.1 --base-url https://api.openai.com/v1 --cle-env OPENAI_API_KEY
    python -X utf8 arene.py --modele openai/gpt-oss-120b            # Groq, compte d'outillage
    python -X utf8 arene.py --modele mon-modele --regimes fenetre,rag  # sans le moteur Dermioz

Le régime « dermioz » demande le moteur (DERMIOZ_SRC=<chemin vers src>) ; les deux
autres tournent partout. Chaque réponse brute est gardée dans le JSON de sortie.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

AUJOURDHUI = date(2026, 10, 20)
K = 6
ENTREPRISE = "Ravel Distribution"

# ── Le monde fictif ─────────────────────────────────────────────────────────────
CLIENTS = [
    "la pharmacie Dumas", "la Clinique des Salines", "le Garage Moreau", "l'Hôtel de la Digue",
    "le cabinet Royer", "la boulangerie Ferrand", "les Transports Kerval", "la résidence Les Tilleuls",
    "l'atelier Brunet", "l'imprimerie Lanoë", "la cave Saint-Clair", "la menuiserie Péron",
    "le laboratoire Vautrin", "la crèche Les Mouettes", "le camping de l'Estran", "la quincaillerie Morvan",
]
PERSONNES = [("Inès", "commerciale"), ("Marc", "logistique"), ("Sarah", "achats"),
             ("Paul", "direction"), ("Léa", "comptabilité")]


@dataclass(frozen=True)
class Rubrique:
    cle: str            # la relation, telle que le moteur l'apprend
    valeurs: tuple      # valeurs possibles, deux à deux sans nombre commun
    dit: str            # déclaration orale : {p} {c} {v}
    question: str       # {c}
    docs: tuple         # gabarits de documents : {c} {v} {o} (date d'origine)


RUBRIQUES = [
    Rubrique("remise accordée", ("5 %", "8 %", "12 %", "15 %", "18 %", "25 %", "30 %"),
             "{p} : « Pour {c}, on accorde {v} de remise, c'est validé. »",
             "Quelle remise accorde-t-on à {c} ?",
             ("TR: TR: Proposition commerciale (message d'origine du {o}) : remise de {v} pour {c}.",
              "Export du tableur des ventes : {c} ; remise {v}.",
              "Compte rendu de la réunion du {o} : pour {c}, on part sur {v} de remise.",
              "Pièce jointe « Proposition_v2.pdf », datée du {o} : {c}, remise consentie {v}.",
              "Fiche client du wiki : {c}, remise habituelle {v}.",
              "Brouillon de relance : « Comme convenu, votre remise est de {v} » ({c}).",
              "Message d'équipe recopié : « {c} c'est {v} de remise non ? »",
              "Note manuscrite scannée : {c} → {v}.")),
    Rubrique("délai de paiement", ("15 jours", "30 jours", "45 jours", "60 jours", "90 jours"),
             "{p} : « {c} paiera à {v}, je l'ai confirmé avec eux. »",
             "Quel délai de paiement pour {c} ?",
             ("TR: Conditions de règlement (message d'origine du {o}) : {c}, paiement à {v}.",
              "Export comptable : {c} ; échéance {v}.",
              "Compte rendu du {o} : {c} règle à {v}.",
              "Contrat type en pièce jointe, version du {o} : {c}, délai de paiement {v}.",
              "Fiche client du wiki : {c}, paiement à {v}.",
              "Brouillon de facture : échéance à {v} pour {c}.",
              "Message d'équipe recopié : « {c} c'est bien {v} ? »",
              "Post-it scanné : {c} = {v}.")),
    Rubrique("volume commandé", ("40 palettes", "65 palettes", "80 palettes", "120 palettes", "150 palettes"),
             "{p} : « {c} commande {v} pour la saison, c'est signé. »",
             "Quel volume a commandé {c} ?",
             ("TR: Bon de commande (message d'origine du {o}) : {c}, {v}.",
              "Export du planning de livraison : {c} ; {v}.",
              "Compte rendu du {o} : {c} prendrait {v}.",
              "Devis en pièce jointe, daté du {o} : {c}, {v}.",
              "Fiche client du wiki : {c}, volume annuel {v}.",
              "Brouillon de confirmation : « vos {v} seront livrées » ({c}).",
              "Message d'équipe recopié : « {c} on est sur {v} ? »",
              "Note scannée : {c} → {v}.")),
    Rubrique("interlocuteur", ("Mme Leroy", "M. Garnier", "Mme Benali", "M. Tessier", "Mme Huet", "M. Caradec"),
             "{p} : « Chez {c}, notre interlocuteur c'est maintenant {v}. »",
             "Qui est notre interlocuteur chez {c} ?",
             ("TR: Contact client (message d'origine du {o}) : chez {c}, voir avec {v}.",
              "Export du carnet d'adresses : {c} ; contact {v}.",
              "Compte rendu du {o} : chez {c}, l'interlocuteur est {v}.",
              "Signature de mail en pièce jointe, datée du {o} : {v}, {c}.",
              "Fiche client du wiki : {c}, contact principal {v}.",
              "Brouillon : « Bonjour {v}, » ({c}).",
              "Message d'équipe recopié : « chez {c} on appelle {v} ? »",
              "Post-it scanné : {c}, demander {v}.")),
    Rubrique("jour de livraison", ("lundi", "mardi", "mercredi", "jeudi", "vendredi"),
             "{p} : « On livre {c} le {v}, à partir de maintenant. »",
             "Quel jour livre-t-on {c} ?",
             ("TR: Tournées (message d'origine du {o}) : {c} livrée le {v}.",
              "Export du planning des tournées : {c} ; {v}.",
              "Compte rendu du {o} : {c} passe le {v}.",
              "Planning en pièce jointe, version du {o} : {c}, {v}.",
              "Fiche client du wiki : {c}, livraison le {v}.",
              "Brouillon d'avis de passage : « nous passerons {v} » ({c}).",
              "Message d'équipe recopié : « {c} c'est le {v} ? »",
              "Note scannée : {c} → {v}.")),
]


@dataclass
class Ligne:
    quand: date
    texte: str
    client: str
    rubrique: str
    valeur: str
    source: str          # « declare » ou « graphe »


@dataclass
class Item:
    epreuve: str
    graine: int
    client: str
    rubrique: str
    question: str
    juste: str | None    # None : il faut dire « je ne sais pas »
    piege: str | None    # la valeur fausse qui circule
    lignes: list = field(default_factory=list)


def _fold(x: str) -> str:
    n = unicodedata.normalize("NFKD", (x or "").lower())
    return "".join(c for c in n if not unicodedata.combining(c))


def _francais(t: str) -> str:
    """« à le » → « au », « de le » → « du », majuscule en tête de citation."""
    t = re.sub(r"\bà le ", "au ", t)
    t = re.sub(r"\bà les ", "aux ", t)
    t = re.sub(r"\bde le ", "du ", t)
    t = re.sub(r"\bde les ", "des ", t)
    return re.sub(r"« ([a-zà-ÿ])", lambda m: "« " + m.group(1).upper(), t)


def _fr(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def construire(epreuve: str, graine: int, n_distracteurs: int = 18) -> Item:
    """Un dossier complet pour UNE question. Tout vient de la graine."""
    rng = random.Random(f"{epreuve}:{graine}")
    clients = CLIENTS[:]
    rng.shuffle(clients)
    cible_c = clients[0]
    rub = rng.choice(RUBRIQUES)
    lignes: list[Ligne] = []

    def declare(quand, c, r, v):
        p = rng.choice(PERSONNES)[0]
        lignes.append(Ligne(quand, r.dit.format(p=p, c=c, v=v), c, r.cle, v, "declare"))

    debut = date(2026, 6, 1)
    # Le reste de la vie de l'entreprise : d'autres clients, d'autres rubriques.
    paires = [(c, r) for c in clients[1:] for r in RUBRIQUES]
    rng.shuffle(paires)
    autres_rub = [r for r in RUBRIQUES if r.cle != rub.cle]
    # Le client cible a d'autres faits ; la rubrique cible existe chez d'autres clients.
    pris = [(cible_c, r) for r in rng.sample(autres_rub, 2)]
    pris += [(c, r) for (c, r) in paires if r.cle == rub.cle][:3]
    pris += [p for p in paires if p not in pris][: max(0, n_distracteurs - len(pris))]
    for c, r in pris:
        declare(debut + timedelta(days=rng.randrange(0, 110)), c, r, rng.choice(r.valeurs))

    juste = piege = None
    v1, v2 = rng.sample(rub.valeurs, 2)
    d_decision = date(2026, 9, rng.randrange(8, 25))
    if epreuve == "radote":
        # La proposition d'origine (v2), puis la décision (v1), puis huit copies de v2.
        d_origine = d_decision - timedelta(days=rng.randrange(12, 30))
        declare(d_decision, cible_c, rub, v1)
        for k, g in enumerate(rng.sample(rub.docs, 8)):
            quand = d_decision + timedelta(days=3 + 2 * k + rng.randrange(0, 2))
            lignes.append(Ligne(quand, "Document importé — " + g.format(c=cible_c, v=v2, o=_fr(d_origine)),
                                cible_c, rub.cle, v2, "graphe"))
        juste, piege = v1, v2
    elif epreuve == "change":
        # Première décision (v2), deux documents la recopient, puis la personne change d'avis (v1).
        declare(d_decision - timedelta(days=30), cible_c, rub, v2)
        for k, g in enumerate(rng.sample(rub.docs, 2)):
            quand = d_decision - timedelta(days=20 - 5 * k)
            lignes.append(Ligne(quand, "Document importé — " + g.format(c=cible_c, v=v2, o=_fr(d_decision - timedelta(days=30))),
                                cible_c, rub.cle, v2, "graphe"))
        p = rng.choice(PERSONNES)[0]
        lignes.append(Ligne(d_decision, f"{p} : « Finalement, pour {cible_c}, on change : ce sera {v1} ({rub.cle}). »",
                            cible_c, rub.cle, v1, "declare"))
        juste, piege = v1, v2
    elif epreuve == "jamais":
        pass  # la paire (cible_c, rub) n'est jamais énoncée
    else:
        raise ValueError(epreuve)
    lignes.sort(key=lambda l: l.quand)
    for l in lignes:
        l.texte = _francais(l.texte)
    return Item(epreuve, graine, cible_c, rub.cle, _francais(rub.question.format(c=cible_c)), juste, piege, lignes)


def _textes(item: Item) -> list[str]:
    return [f"[{_fr(l.quand)}] {l.texte}" for l in item.lignes]


# ── Les trois régimes ───────────────────────────────────────────────────────────
def contexte_fenetre(item: Item) -> str:
    return "\n".join(_textes(item))


class Rag:
    def __init__(self):
        import faiss  # noqa: PLC0415
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        self.faiss = faiss
        self.enc = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    def contexte(self, item: Item) -> str:
        textes = _textes(item)
        v = self.enc.encode(textes, normalize_embeddings=True, convert_to_numpy=True).astype("float32")
        idx = self.faiss.IndexFlatIP(v.shape[1])
        idx.add(v)
        q = self.enc.encode([item.question], normalize_embeddings=True, convert_to_numpy=True).astype("float32")
        _d, ids = idx.search(q, min(K, len(textes)))
        garde = sorted(i for i in ids[0] if i >= 0)          # remis dans l'ordre des dates
        return "\n".join(textes[i] for i in garde)


class Dermioz:
    def __init__(self, src: str):
        sys.path.insert(0, src)
        import temporal_hologram as th  # noqa: PLC0415
        self.th = th

    def contexte(self, item: Item) -> str:
        def ts(d: date) -> float:
            return datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp()
        horloge = {"t": ts(item.lignes[0].quand)}
        h = self.th.TemporalHologram(None, dim=1024, now_fn=lambda: horloge["t"])
        for l in item.lignes:
            horloge["t"] = ts(l.quand)
            h.learn(l.client, l.rubrique, l.valeur, created_ts=horloge["t"], source=l.source)
        horloge["t"] = ts(AUJOURDHUI)
        h.decay()
        return h.injection_block(item.question)


# ── Le modèle ───────────────────────────────────────────────────────────────────
SYSTEME = (
    f"Tu es l'assistant de l'entreprise {ENTREPRISE}. Nous sommes le {_fr(AUJOURDHUI)}. "
    "Réponds à la question à partir du contexte fourni, et de rien d'autre. "
    "Termine ta réponse par une ligne, exactement sous cette forme :\n"
    "RÉPONSE: <la valeur> (ou RÉPONSE: INCONNUE si le contexte ne permet pas de répondre)"
)


class Modele:
    """Client minimal compatible OpenAI. Le 429 est attendu et COMPTÉ, jamais caché."""

    def __init__(self, nom: str, base_url: str, cle: str, max_tokens: int = 700):
        import httpx  # noqa: PLC0415
        self.nom = nom
        self.max_tokens = max_tokens
        self.c = httpx.Client(base_url=base_url, timeout=120.0,
                              headers={"Authorization": f"Bearer {cle}"})
        self.extra = {}
        if "gpt-oss" in nom:
            self.extra = {"reasoning_effort": "low"}
        elif "qwen3" in nom:
            self.extra = {"reasoning_effort": "none"}
        self.attente = 0.0

    def repondre(self, contexte: str, question: str) -> dict:
        corps = {"model": self.nom, "temperature": 0, "max_tokens": self.max_tokens,
                 "messages": [{"role": "system", "content": SYSTEME},
                              {"role": "user", "content": f"Contexte :\n{contexte or '(rien)'}\n\nQuestion : {question}"}],
                 **self.extra}
        for essai in range(8):
            t0 = time.time()
            r = self.c.post("/chat/completions", json=corps)
            if r.status_code == 200:
                d = r.json()
                u = d.get("usage") or {}
                return {"texte": (d["choices"][0]["message"].get("content") or "").strip(),
                        "jetons_entree": u.get("prompt_tokens"), "jetons_sortie": u.get("completion_tokens"),
                        "secondes": round(time.time() - t0, 2)}
            txt = r.text[:300]
            if r.status_code == 400 and self.extra:
                self.extra = {}                       # paramètre refusé : on le dit dans le JSON
                corps = {k: v for k, v in corps.items() if k != "reasoning_effort"}
                continue
            if r.status_code in (500, 502, 503, 504):     # fournisseur saturé : on attend, on le compte
                attente = min(120.0, 5.0 * 2 ** essai)
                self.attente += attente
                time.sleep(attente)
                continue
            if r.status_code != 429:
                raise RuntimeError(f"{self.nom} HTTP {r.status_code} : {txt}")
            if "per day" in txt.lower() or "tpd" in txt.lower():
                raise RuntimeError(f"plafond QUOTIDIEN atteint pour {self.nom} : {txt}")
            m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", txt)
            attente = (int(m.group(1) or 0) * 60 + float(m.group(2)) + 0.5) if m else 5.0 * (essai + 1)
            self.attente += attente
            time.sleep(attente)
        raise RuntimeError(f"{self.nom} : trop de 429")


# ── Le verdict ──────────────────────────────────────────────────────────────────
def _jetons(v: str) -> set[str]:
    b = _fold(v)
    out = set(re.findall(r"\d+", b))
    out |= {m for m in ("lundi", "mardi", "mercredi", "jeudi", "vendredi") if m in b}
    out |= {m for m in ("leroy", "garnier", "benali", "tessier", "huet", "caradec") if m in b}
    return out


def verdict(item: Item, texte: str) -> tuple[str, str]:
    """(verdict, ce qui a été lu). Le verdict ne lit QUE la ligne RÉPONSE."""
    lignes = [l for l in texte.splitlines() if re.match(r"\s*\**\s*r[ée]ponse\s*\**\s*:", l, re.I)]
    if not lignes:
        # Coupé avant de conclure (plafond de longueur) : ce n'est ni juste ni faux,
        # et lire la fin d'un raisonnement tronqué inventerait un verdict.
        return "sans_reponse", texte.strip()[-160:]
    dit = re.sub(r"^\s*\**\s*r[ée]ponse\s*\**\s*:\s*", "", lignes[-1], flags=re.I).strip()
    if "inconnu" in _fold(dit) or not _jetons(dit):
        lu = "inconnue"
    else:
        lu = dit
    if item.juste is None:
        return ("juste" if lu == "inconnue" else "invente"), dit
    if lu == "inconnue":
        return "muet", dit
    vus = _jetons(dit)
    j, p = bool(vus & _jetons(item.juste)), bool(item.piege and vus & _jetons(item.piege))
    if j and not p:
        return "juste", dit
    if p and not j:
        return "piege", dit
    if j and p:
        return "les_deux", dit
    return "autre", dit


def rejuger(chemin: Path) -> dict:
    """Recalcule chaque verdict depuis le texte enregistré : zéro appel, même juge pour tous."""
    d = json.loads(chemin.read_text(encoding="utf-8"))
    tab: dict = {}
    for r in d["reponses"].values():
        item = construire(r["epreuve"], r["graine"])
        r["verdict"], r["lu"] = verdict(item, r["texte"])
        tab.setdefault(r["regime"], {}).setdefault(r["epreuve"], {}).setdefault(r["verdict"], 0)
        tab[r["regime"]][r["epreuve"]][r["verdict"]] += 1
    d["tableau"] = tab
    chemin.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return tab


# ── La campagne ─────────────────────────────────────────────────────────────────
def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--modele", required=True)
    ap.add_argument("--base-url", default="https://api.groq.com/openai/v1")
    ap.add_argument("--cle-env", default="", help="variable d'environnement qui porte la clé")
    ap.add_argument("--regimes", default="fenetre,rag,dermioz")
    ap.add_argument("--epreuves", default="radote,change,jamais")
    ap.add_argument("--n", type=int, default=12, help="questions par épreuve")
    ap.add_argument("--sortie", default="")
    ap.add_argument("--pause", type=float, default=2.0, help="secondes entre deux appels")
    ap.add_argument("--max-tokens", type=int, default=700)
    ap.add_argument("--refaire-sans-reponse", action="store_true",
                    help="reposer les questions coupées avant leur ligne RÉPONSE (plafond trop court)")
    a = ap.parse_args()

    if a.cle_env:
        cle = os.environ[a.cle_env]
    else:  # Groq, compte d'OUTILLAGE : jamais le budget de la production
        sys.path.insert(0, str(Path(__file__).parent))
        from membench.providers import load_groq_key  # noqa: PLC0415
        cle = load_groq_key("outillage")
    m = Modele(a.modele, a.base_url, cle, a.max_tokens)
    regimes = a.regimes.split(",")
    sortie = Path(a.sortie or f"arene-{re.sub(r'[^a-z0-9.]+', '-', a.modele.lower())}.json")
    deja = json.loads(sortie.read_text(encoding="utf-8")) if sortie.exists() else {"reponses": {}}
    if a.refaire_sans_reponse:
        refaits = [k for k, r in deja["reponses"].items() if r["verdict"] == "sans_reponse"]
        deja.setdefault("refaits_plafond_large", []).extend(refaits)
        for k in refaits:
            del deja["reponses"][k]
    rag = Rag() if "rag" in regimes else None
    dz = Dermioz(os.environ["DERMIOZ_SRC"]) if "dermioz" in regimes else None

    for ep in a.epreuves.split(","):
        for g in range(1, a.n + 1):
            item = construire(ep, g)
            for reg in regimes:
                cle_r = f"{ep}:{g}:{reg}"
                if cle_r in deja["reponses"]:
                    continue
                ctx = (contexte_fenetre(item) if reg == "fenetre" else rag.contexte(item) if reg == "rag"
                       else dz.contexte(item))
                rep = m.repondre(ctx, item.question)
                v, dit = verdict(item, rep["texte"])
                deja["reponses"][cle_r] = {"max_tokens": m.max_tokens, "epreuve": ep, "graine": g, "regime": reg, "question": item.question,
                                           "juste": item.juste, "piege": item.piege, "contexte": ctx,
                                           "lu": dit, "verdict": v, **rep}
                print(f"{ep:7} {g:2} {reg:8} {v:9} {dit[:60]!r}", flush=True)
                sortie.write_text(json.dumps(deja, ensure_ascii=False, indent=1), encoding="utf-8")
                time.sleep(a.pause)

    tab: dict = {}
    for r in deja["reponses"].values():
        tab.setdefault(r["regime"], {}).setdefault(r["epreuve"], {}).setdefault(r["verdict"], 0)
        tab[r["regime"]][r["epreuve"]][r["verdict"]] += 1
    deja["meta"] = {"modele": a.modele, "base_url": a.base_url, "date": datetime.now().isoformat(timespec="seconds"),
                    "aujourdhui_du_banc": AUJOURDHUI.isoformat(), "n_par_epreuve": a.n, "k_rag": K,
                    "encodeur_rag": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                    "dermioz_src": "fourni" if os.environ.get("DERMIOZ_SRC") else "", "systeme": SYSTEME,
                    "parametres_modele": m.extra, "attente_429_s": round(deja.get("meta", {}).get("attente_429_s", 0) + m.attente, 1)}
    deja["tableau"] = tab
    sortie.write_text(json.dumps(deja, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(tab, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
