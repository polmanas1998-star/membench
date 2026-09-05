"""Fait passer le banc aux quatre bras et imprime la table.

    python run_bench.py --limit 8        run de fumee, quelques questions
    python run_bench.py                  le corpus entier

Le modele de base est le meme dans les bras A, B et C. La seule chose qui
change d'un bras a l'autre est ce qu'on lui donne a se souvenir.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import date

from membench.arms import OracleArm, run
from membench.corpus import build_corpus, candidates, timeline
from membench.providers import (DEFAULT_MODEL, DailyBudgetExhausted,
                                GroqModel)
from membench.real_arms import (DermiozArm, FullContextArm, RetrievalArm,
                                StatelessArm)
from membench.scoring import TPM_CEILING, score

COLUMNS = [
    ("couv", "coverage"), ("prec", "gated_precision"), ("reten", "retention"),
    ("perim", "supersession_error"), ("age", "age_awareness"),
    ("oubli", "deep_retention"), ("hallu", "hallucination"), ("illis", "malformed_rate"),
]


def cell(v: float | None) -> str:
    return "  n/m" if v is None else f"{v:5.3f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="n'interroger qu'un echantillon, pour valider le cablage")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dim", type=int, default=1024)
    ap.add_argument("--offline", action="store_true",
                    help="seulement les bras qui ne depensent rien")
    ap.add_argument("--account", default="produit", choices=("produit", "outillage"),
                    help="quel compte Groq depenser. Le defaut est le compte "
                         "de PRODUCTION, dont le budget quotidien est 200 000 "
                         "jetons partages avec le produit vivant.")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    facts = build_corpus(seed=a.seed)
    tl = list(timeline(facts))
    pool = candidates(facts)

    asked = facts
    if a.limit:
        # Echantillon STRATIFIE : tirer au hasard dans 84 faits donnerait des
        # classes a deux elements et des ratios qui ne veulent rien dire.
        rng = random.Random(a.seed)
        by_kind: dict[str, list] = {}
        for f in facts:
            by_kind.setdefault(f.kind, []).append(f)
        per = max(1, a.limit // len(by_kind))
        asked = [f for k in sorted(by_kind)
                 for f in rng.sample(by_kind[k], min(per, len(by_kind[k])))]

    arms = [OracleArm(facts), DermiozArm(dim=a.dim)]
    model = None
    if not a.offline:
        model = GroqModel(model=a.model, account=a.account)
        arms += [StatelessArm(model, pool), RetrievalArm(model, pool),
                 FullContextArm(model, pool)]

    print(f"membench, {len(asked)} questions, corpus {len(facts)} faits, "
          f"graine {a.seed}, {date.today().isoformat()}")
    if model:
        print(f"modele de base tenu constant : {a.model}")
        print(f"compte : {model.account}, empreinte de cle "
              f"{model.key_fingerprint}")
    print()
    header = f"{'bras':<20}" + "".join(f"{n:>7}" for n, _ in COLUMNS) + \
             f"{'jetons/tour':>13}{'tours/min':>11}"
    print(header)
    print("-" * len(header))

    rows: dict = {}

    def flush() -> None:
        """Ecrire APRES CHAQUE BRAS.

        Le run du 05/09 a perdu trois bras deja mesures parce que le
        quatrieme a leve avant l'ecriture finale. Un resultat qui n'existe
        qu'en memoire d'un processus n'existe pas.
        """
        if not a.out:
            return
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"model": a.model, "seed": a.seed, "asked": len(asked),
                       "complete": len(rows) == len(arms), "rows": rows},
                      fh, indent=2, ensure_ascii=False)

    for arm in arms:
        t0 = time.time()
        try:
            r = score(asked, run(arm, asked, tl))
        except DailyBudgetExhausted as exc:
            print(f"{arm.name:<20}  ARRETE : {exc}")
            print(f"  bras mesures avant l'arret : {', '.join(rows) or 'aucun'}")
            flush()
            return 2
        tpt = r.tokens_per_turn or 0.0
        tpm = r.turns_per_minute
        print(f"{arm.name:<20}" + "".join(cell(getattr(r, k)) for _, k in COLUMNS) +
              f"{tpt:>13.0f}" + ("      n/m" if tpm is None else f"{tpm:>11.2f}"))
        rows[arm.name] = r.as_row() | {"seconds": round(time.time() - t0, 1)}
        flush()  # apres CHAQUE bras, pas seulement a la fin

    print()
    print(f"plafond retenu : {TPM_CEILING} jetons/min. « tours/min » est ce "
          f"debit divise par le cout d'un tour.")
    if model:
        print(f"429 rencontres : {model.rate_limited}, "
              f"attente cumulee {model.waited_seconds:.0f} s")
    print()
    print("denominateurs (ce sur quoi chaque colonne est calculee) :")
    r0 = score(asked, run(OracleArm(facts), asked, tl))
    print(f"  retention {r0.retention_n} · peremption {r0.supersession_n} · "
          f"age {r0.age_n} · oubli {r0.expired_n} · absence {r0.absence_n}")

    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"model": a.model, "seed": a.seed, "asked": len(asked),
                       "rows": rows}, fh, indent=2, ensure_ascii=False)
        print(f"\n-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
