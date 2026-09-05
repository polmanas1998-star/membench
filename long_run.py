"""Le banc complet, etale sur des heures, reprenable, et qui mesure son mur.

Un plafond quotidien ne se contourne pas : il se subit. Un run qui meurt dessus
perd tout ; un run qui l'attend le traverse. Celui-ci :

  * enregistre un POINT DE REPRISE apres chaque paire (graine, bras), donc une
    coupure de courant coute une paire et pas la campagne ;
  * traite un 429 quotidien en DORMANT le temps annonce, au lieu de lever ;
  * et journalise chaque attente, ce qui donne a la fin la vitesse de
    RECHARGE reelle du seau quotidien, un nombre que le fournisseur ne
    publie pas.

Usage :
    python long_run.py --seeds 5 --out run.json --log run.log
Reprise : relancer la meme commande, les paires deja faites sont sautees.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
from datetime import datetime, timezone

from membench.arms import run as run_arm
from membench.corpus import build_corpus, candidates, timeline
from membench.providers import DailyBudgetExhausted, GroqModel
from membench.real_arms import (DermiozGroundedArm, FullContextArm,
                                RetrievalArm, StatelessArm)
from membench.scoring import score

ARMS = {
    "D+": lambda m, p: DermiozGroundedArm(m, p, dim=2048),
    "C": lambda m, p: RetrievalArm(m, p),
    "A": lambda m, p: StatelessArm(m, p),
    "B": lambda m, p: FullContextArm(m, p),
}
# Ordre delibere : du moins cher au plus cher. Si le budget coupe, il coupe le
# bras le plus gourmand, et les autres sont deja au chaud sur le disque.
ORDER = ["D+", "C", "A", "B"]


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--account", default="outillage")
    ap.add_argument("--out", default="run.json")
    ap.add_argument("--log", default="run.log")
    ap.add_argument("--max-hours", type=float, default=10.0)
    a = ap.parse_args()

    if a.account == "produit":
        raise SystemExit(
            "refus : ce run est long et depenserait le budget de la PRODUCTION. "
            "Passe --account outillage, ou change ce garde en connaissance de cause."
        )

    out = pathlib.Path(a.out)
    state = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    log = open(a.log, "a", encoding="utf-8", buffering=1)

    def say(msg: str) -> None:
        line = f"[{stamp()}] {msg}"
        print(line, flush=True)
        log.write(line + "\n")

    m = GroqModel(account=a.account, max_retries=8)
    started = time.time()
    waits: list[dict] = state.get("_waits", [])
    say(f"depart. compte {a.account} {m.key_fingerprint}, "
        f"{a.seeds} graines x {len(ORDER)} bras, plafond de duree {a.max_hours} h")

    for seed in range(1, a.seeds + 1):
        f = build_corpus(seed=seed)
        tl, pool = list(timeline(f)), candidates(f)
        for key in ORDER:
            tag = f"seed{seed}/{key}"
            if tag in state:
                say(f"{tag} deja fait, saute")
                continue
            if (time.time() - started) / 3600 > a.max_hours:
                say(f"plafond de duree atteint, arret propre apres {len(state)} paires")
                return 0
            t0 = time.time()
            while True:
                try:
                    r = score(f, run_arm(ARMS[key](m, pool), f, tl))
                    break
                except DailyBudgetExhausted as exc:
                    # Le seau quotidien se remplit. On l'attend, et on note
                    # combien de temps : c'est la mesure de la recharge.
                    nap = 15 * 60
                    waits.append({"at": stamp(), "tag": tag, "slept_s": nap,
                                  "detail": str(exc)})
                    say(f"{tag} : {exc} -> sommeil {nap // 60} min")
                    if (time.time() - started) / 3600 > a.max_hours:
                        say("plafond de duree atteint pendant l'attente, arret")
                        state["_waits"] = waits
                        out.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
                        return 0
                    time.sleep(nap)
            pr = r.prompt_tokens_total / r.correct if r.correct else None
            state[tag] = r.as_row() | {
                "tokens_total": r.prompt_tokens_total, "correct": r.correct,
                "tok_per_correct": pr, "seconds": round(time.time() - t0, 1),
            }
            state["_waits"] = waits
            out.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            say(f"{tag}  couv {r.coverage:.3f}  prec "
                f"{'n/m' if r.gated_precision is None else f'{r.gated_precision:.3f}'}"
                f"  halluc {r.hallucination:.3f}  jet/juste "
                f"{'n/m' if pr is None else f'{pr:.0f}'}  ({time.time() - t0:.0f} s)")

    say(f"termine. {len([k for k in state if not k.startswith('_')])} paires, "
        f"{len(waits)} attentes de budget, {m.rate_limited} 429 par minute")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
