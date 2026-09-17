"""Le modele de base, tenu CONSTANT pendant qu'on fait varier la memoire.

C'est la correction du 05/09 : comparer Dermioz a Gemini bout en bout mesure
surtout l'ecart entre deux modeles de base. Ici le modele est le meme dans les
quatre bras, et la seule chose qui change est ce qu'on lui donne a se souvenir.

Le compte de jetons vient de `usage.prompt_tokens` rendu par le fournisseur,
jamais d'une estimation locale : c'est ce compteur-la qui decide du plafond par
minute, donc c'est lui qui fait foi.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

# Le bucket que Dermioz fait tourner en production.
DEFAULT_MODEL = "openai/gpt-oss-120b"


# Deux comptes existent sur cette machine, et ils ne doivent pas etre
# confondus. Le compte PRODUIT sert la production : lui prendre son budget
# quotidien met le produit a sec, ce qui est arrive le 05/09 (200 000 jetons
# d'un coup). Le compte OUTILLAGE sert les agents de code.
# Surchargeable par l'environnement, parce qu'un depot public n'a pas a
# connaitre la disposition du disque de son auteur. Le plus simple reste de
# poser GROQ_API_KEY : les chemins ne servent que si elle est absente.
ACCOUNTS = {
    "produit": Path(os.environ.get("MEMBENCH_ENV_PRODUIT",
                                   Path.home() / ".env")),
    "outillage": Path(os.environ.get("MEMBENCH_ENV_OUTILLAGE",
                                     Path.home() / ".aider.conf.yml")),
}


def load_groq_key(account: str = "produit", path: Path | None = None) -> str:
    """Rend la cle du compte demande, sans jamais l'imprimer.

    L'environnement gagne quand `GROQ_API_KEY` est pose, sinon on lit le
    fichier de configuration du compte. Le nom du compte est explicite a
    l'appel, parce qu'un defaut implicite est exactement ce qui fait depenser
    le budget de la production pour un banc.
    """
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    src = path or ACCOUNTS.get(account)
    if src is None:
        raise RuntimeError(
            f"compte inconnu : {account!r}. Connus : {', '.join(ACCOUNTS)}")
    if src.is_file():
        m = re.search(r"gsk_[A-Za-z0-9]{20,}", src.read_text(encoding="utf-8",
                                                             errors="ignore"))
        if m:
            return m.group(0)
    raise RuntimeError(
        f"aucune cle Groq trouvee pour le compte {account!r} (cherche : {src})")


def key_fingerprint(key: str) -> str:
    """Douze caracteres de hachage, pour dire QUEL compte tourne sans le divulguer.

    A imprimer en tete de chaque run : une mesure dont on ne sait pas sur quel
    compte elle a ete prise ne peut pas etre reproduite, et un banc qui tape
    silencieusement sur la production est un incident qui attend son tour.
    """
    return hashlib.sha256(key.encode()).hexdigest()[:12]


class DailyBudgetExhausted(RuntimeError):
    """Le plafond par JOUR est atteint. Attendre ne sert a rien d'utile.

    Un 429 par minute et un 429 par jour se ressemblent et ne se traitent pas
    pareil. Reculer de cinquante secondes devant une limite quotidienne, c'est
    la boucle qui entretient le refus qu'elle retente, un cran plus haut :
    l'attente ne fera pas revenir un budget qui se recharge sur 24 h.
    """


@dataclass
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int


class GroqModel:
    """Un appel, et le compte de jetons que le fournisseur a reellement facture.

    Le 429 est retente avec attente, parce que le banc n'a pas le choix, mais
    l'attente est COMPTEE et rapportee : c'est la these du produit, un plafond
    par minute ne se contourne pas, il se subit.
    """

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None,
                 account: str = "produit", max_retries: int = 6) -> None:
        from groq import Groq  # import tardif : le module n'est pas requis hors ligne

        self.model = model
        key = api_key or load_groq_key(account)
        # L'ETIQUETTE DOIT DIRE LA VERITE. `load_groq_key` donne la priorite a
        # `GROQ_API_KEY` : demander `account="outillage"` ne garantit donc rien
        # des que la variable est posee, et le banc affichait quand meme
        # « outillage ». Paye le 17/09/2026 : un lanceur qui chargeait le .env
        # du depot produit par python-dotenv a fait tourner quatre campagnes,
        # dont ~104 k jetons sur `gpt-oss-120b` — le modele PRINCIPAL de la
        # production — sur un seau de 200 k par jour. Rien dans la sortie ne
        # l'a dit. Un choix explicite qu'une variable d'environnement
        # court-circuite en silence n'est pas un choix.
        if api_key is None and os.environ.get("GROQ_API_KEY"):
            self.account = f"{account}?  ENVIRONNEMENT GROQ_API_KEY"
        else:
            self.account = account
        self.key_fingerprint = key_fingerprint(key)
        self._client = Groq(api_key=key)
        self._max_retries = max_retries
        self.waited_seconds = 0.0
        self.rate_limited = 0

    def complete(self, system: str, user: str, max_tokens: int = 48) -> Completion:
        for attempt in range(self._max_retries + 1):
            try:
                r = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    max_tokens=max_tokens,
                    temperature=0.0,
                )
                return Completion(
                    text=(r.choices[0].message.content or "").strip(),
                    prompt_tokens=r.usage.prompt_tokens,
                    completion_tokens=r.usage.completion_tokens,
                )
            except Exception as exc:  # noqa: BLE001 - on veut le message brut
                msg = str(exc)
                if "429" not in msg and "rate" not in msg.lower():
                    raise
                # Le plafond quotidien n'est expose par AUCUN en-tete de
                # reponse : il n'apparait que dans le corps du 429. Lire les
                # en-tetes et conclure qu'il n'existe pas est l'erreur du
                # 05/09, payee 200 000 jetons du budget du produit.
                if "TPD" in msg or "tokens per day" in msg.lower():
                    raise DailyBudgetExhausted(_tpd_detail(msg)) from None
                if attempt == self._max_retries:
                    raise
                wait = _retry_after(msg, default=2.0 * (attempt + 1))
                self.rate_limited += 1
                self.waited_seconds += wait
                time.sleep(wait)
        raise AssertionError("inatteignable")


def _retry_after(message: str, default: float) -> float:
    """Le fournisseur dit souvent combien de temps attendre. On l'ecoute."""
    # « try again in 2m49.344s » : sans les minutes on lisait 49 s au lieu de
    # 169, donc on repartait avant la reouverture et on rallongeait la file.
    m = re.search(r"try again in (?:(\d+)m)?([0-9.]+)s", message)
    if m:
        minutes = int(m.group(1) or 0)
        return min(minutes * 60 + float(m.group(2)) + 0.25, 300.0)
    return min(default, 60.0)


def _tpd_detail(message: str) -> str:
    """Extrait le plafond et la consommation du corps du 429, pour les publier."""
    lim = re.search(r"Limit (\d+)", message)
    used = re.search(r"Used (\d+)", message)
    if lim and used:
        return (f"plafond quotidien atteint : {int(lim.group(1)):,} jetons/jour, "
                f"{int(used.group(1)):,} consommes").replace(",", " ")
    return "plafond quotidien atteint"


# ---------------------------------------------------------------------------
# Mistral : le meme banc, un autre fournisseur
# ---------------------------------------------------------------------------
#: ⚠ Un banc qui ne sait interroger qu'UN fournisseur mesure ce fournisseur.
#: Les chiffres du 16/09 sur les normes abrogees ont ete pris sur gpt-oss-120b ;
#: tant qu'un second modele ne les a pas rejoues, on ne sait pas si la faute
#: vient de la memoire ou du modele qui la lit.
MISTRAL_BASE = "https://api.mistral.ai/v1"
MISTRAL_DEFAUT = "mistral-large-latest"


def load_mistral_key(path: Path | None = None) -> str:
    """Rend la cle Mistral sans jamais l'imprimer.

    L'environnement gagne ; sinon on lit un `.env` designe par
    MEMBENCH_ENV_MISTRAL, et a defaut celui du depot produit. Le format de cle
    n'est pas devinable comme `gsk_...`, donc on cherche la LIGNE nommee.
    """
    key = os.environ.get("MISTRAL_API_KEY")
    if key:
        return key
    src = path or Path(os.environ.get(
        "MEMBENCH_ENV_MISTRAL",
        Path(__file__).resolve().parents[2] / "dermioz-ai" / ".env"))
    if src.is_file():
        for ligne in src.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ligne.strip().startswith("MISTRAL_API_KEY="):
                v = ligne.split("=", 1)[1].strip().strip('"').strip("'")
                if v:
                    return v
    raise RuntimeError(
        f"aucune cle Mistral. Posez MISTRAL_API_KEY, ou une ligne "
        f"MISTRAL_API_KEY=... dans {src}")


class MistralModel:
    """Meme interface que `GroqModel` : un appel, et les jetons factures.

    Deliberement sans le SDK maison : l'API est compatible OpenAI, et `httpx`
    est deja une dependance du produit. Une dependance de plus pour un banc,
    c'est une raison de plus qu'il ne tourne pas le jour ou on en a besoin.
    """

    def __init__(self, model: str = MISTRAL_DEFAUT, api_key: str | None = None,
                 max_retries: int = 6) -> None:
        import httpx  # noqa: PLC0415

        self.model = model
        key = api_key or load_mistral_key()
        self.account = "mistral"
        self.key_fingerprint = key_fingerprint(key)
        self._client = httpx.Client(
            base_url=MISTRAL_BASE, timeout=90.0,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"})
        self._max_retries = max_retries
        self.waited_seconds = 0.0
        self.rate_limited = 0

    def complete(self, system: str, user: str, max_tokens: int = 48) -> Completion:
        charge = {"model": self.model,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}],
                  "max_tokens": max_tokens, "temperature": 0.0}
        for attempt in range(self._max_retries + 1):
            r = self._client.post("/chat/completions", json=charge)
            if r.status_code == 200:
                d = r.json()
                u = d.get("usage") or {}
                return Completion(
                    text=(d["choices"][0]["message"]["content"] or "").strip(),
                    prompt_tokens=int(u.get("prompt_tokens") or 0),
                    completion_tokens=int(u.get("completion_tokens") or 0))
            corps = r.text[:400]
            if r.status_code != 429:
                raise RuntimeError(f"Mistral HTTP {r.status_code} : {corps}")
            # Meme distinction que chez Groq : une limite par JOUR ne se
            # contourne pas en attendant cinquante secondes.
            if "day" in corps.lower() or "daily" in corps.lower():
                raise DailyBudgetExhausted(corps)
            if attempt == self._max_retries:
                raise RuntimeError(f"Mistral 429 apres {attempt} tentatives : {corps}")
            wait = float(r.headers.get("retry-after") or 0) or 2.0 * (attempt + 1)
            self.rate_limited += 1
            self.waited_seconds += wait
            time.sleep(wait)
        raise AssertionError("inatteignable")


def modele_pour(nom: str, account: str = "outillage"):
    """Le fournisseur se DEDUIT du nom du modele, jamais d'un defaut implicite.

    Un banc qui prend le mauvais fournisseur ne plante pas : il mesure autre
    chose, et le dit dans un nom de colonne que personne ne relit.
    """
    if nom.startswith(("mistral", "open-mistral", "open-mixtral", "magistral",
                       "ministral", "codestral", "pixtral", "devstral")):
        return MistralModel(model=nom)
    return GroqModel(model=nom, account=account)
