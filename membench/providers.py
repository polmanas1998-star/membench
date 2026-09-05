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
