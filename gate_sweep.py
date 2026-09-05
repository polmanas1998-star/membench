"""La couche n'a pas UNE couverture, elle a une COURBE.

Comparer « la couche repond a 0,500 des questions » a « le top-k repond a
0,833 » compare deux points arbitraires. Le garde z est un reglage : le
baisser achete de la couverture et vend de la precision. La question honnete
n'est pas laquelle des deux valeurs est la plus grande, c'est OU se trouve
l'autre systeme par rapport a la courbe.
"""
from __future__ import annotations

import statistics as st

from membench.arms import run
from membench.corpus import build_corpus, timeline
from membench.real_arms import DermiozArm
from membench.scoring import score

SEEDS = 5


class Gated(DermiozArm):
    """La meme couche, avec le seuil de confiance rendu reglable."""

    def __init__(self, z: float, **kw) -> None:
        super().__init__(**kw)
        self._z = z

    def ask(self, subject: str, relation: str):
        from membench.scoring import Answer
        value, _ = self._mem.query_gated(subject, relation, z_gate=self._z)
        if value is None:
            return Answer(None, prompt_tokens=0)
        age = self._age_days(subject, relation)
        # Le garde d'age s'applique a TOUS les points de la courbe, sinon on
        # comparerait deux versions du systeme le long d'un meme axe.
        if age is not None and age > self.REFUSE_AFTER_DAYS:
            return Answer(None, prompt_tokens=0)
        return Answer(value, stale_flagged=age is not None and age > self._stale_after,
                      prompt_tokens=0)


def main() -> int:
    print(f"courbe precision/couverture du garde, {SEEDS} graines, d=2048\n")
    hdr = f"{'z':>5}{'couverture':>22}{'precision gardee':>26}{'hallucination':>22}"
    print(hdr); print("-" * len(hdr))
    for z in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0):
        cov, pre, hal = [], [], []
        for s in range(1, SEEDS + 1):
            f = build_corpus(seed=s)
            tl = list(timeline(f))
            r = score(f, run(Gated(z, dim=2048), f, tl))
            cov.append(r.coverage)
            if r.gated_precision is not None:
                pre.append(r.gated_precision)
            if r.hallucination is not None:
                hal.append(r.hallucination)
        band = lambda v: (f"{st.median(v):.3f} [{min(v):.3f}-{max(v):.3f}]"
                          if v else "n/m")
        print(f"{z:>5.1f}{band(cov):>22}{band(pre):>26}{band(hal):>22}")
    print("\npour situer : C, recherche lexicale top-k, marque couverture 0.833 "
          "et precision 0.950 sur n=24.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
