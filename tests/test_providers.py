"""Les gardes des quatre defauts payes le 05/09/2026.

Chacun a coute quelque chose de reel : 200 000 jetons du budget de production,
trois bras deja mesures perdus, et une table publiee ou trois systemes en panne
passaient pour prudents.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from membench.providers import (ACCOUNTS, Completion, DailyBudgetExhausted,
                                GroqModel, _retry_after, _tpd_detail,
                                key_fingerprint, load_groq_key)


class _Stub:
    """Un client qui leve ce qu'on lui dit, et compte ses appels."""

    def __init__(self, error: Exception | None, ok_after: int = 0) -> None:
        self.error, self.ok_after, self.calls = error, ok_after, 0
        self.chat = type("c", (), {"completions": self})()

    def create(self, **_kw):
        self.calls += 1
        if self.error and self.calls <= self.ok_after:
            raise self.error
        if self.error and not self.ok_after:
            raise self.error
        return type("r", (), {
            "choices": [type("c", (), {"message": type("m", (), {"content": "ANSWER: x\nSTALE: no"})()})()],
            "usage": type("u", (), {"prompt_tokens": 10, "completion_tokens": 5})(),
        })()


def _model(stub: _Stub) -> GroqModel:
    m = GroqModel.__new__(GroqModel)
    m.model, m.account, m.key_fingerprint = "test", "test", "0" * 12
    m._client, m._max_retries = stub, 3
    m.waited_seconds, m.rate_limited = 0.0, 0
    return m


# --------------------------------------------------------------------------
# 1. Un 429 par JOUR n'est pas un 429 par minute
# --------------------------------------------------------------------------

TPD_429 = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
    "`openai/gpt-oss-120b` in organization `org_x` service tier `on_demand` on "
    "tokens per day (TPD): Limit 200000, Used 199631, Requested 761. Please try "
    "again in 2m49.344s.'}}"
)
TPM_429 = ("Error code: 429 - {'error': {'message': 'Rate limit reached ... on "
           "tokens per minute (TPM): Limit 8000. Please try again in 0.6s.'}}")


def test_un_plafond_quotidien_leve_au_lieu_de_retenter():
    """Attendre ne recharge pas un seau qui se remplit sur 24 h.

    Reculer devant une limite par jour est la boucle qui entretient le refus
    qu'elle retente, un cran au-dessus de celle deja publiee.
    """
    stub = _Stub(RuntimeError(TPD_429))
    with pytest.raises(DailyBudgetExhausted):
        _model(stub).complete("s", "u")
    assert stub.calls == 1, "un plafond quotidien ne se retente pas"


def test_un_plafond_par_minute_se_retente_lui():
    stub = _Stub(RuntimeError(TPM_429), ok_after=2)
    c = _model(stub).complete("s", "u")
    assert isinstance(c, Completion)
    assert stub.calls == 3


def test_le_detail_du_plafond_quotidien_est_extrait_pour_etre_publie():
    d = _tpd_detail(TPD_429)
    assert "200 000" in d and "199 631" in d


# --------------------------------------------------------------------------
# 2. « 2m49.344s » valait 49 secondes
# --------------------------------------------------------------------------

def test_l_attente_annoncee_en_minutes_est_lue_en_entier():
    """Sans les minutes on repartait avant la reouverture, donc on rallongeait
    la file qu'on attendait."""
    assert _retry_after("try again in 2m49.344s", 2.0) == pytest.approx(169.594)
    assert _retry_after("try again in 0.6s", 2.0) == pytest.approx(0.85)
    assert _retry_after("pas de duree ici", 7.0) == 7.0


def test_l_attente_est_bornee():
    assert _retry_after("try again in 99m0s", 2.0) == 300.0


# --------------------------------------------------------------------------
# 3. Deux comptes, et pas de defaut implicite vers la production
# --------------------------------------------------------------------------

def test_les_deux_comptes_sont_des_cles_differentes():
    """Si les empreintes coincident, les deux comptes partagent un seau et
    basculer de l'un a l'autre ne change rien au budget."""
    for account in ACCOUNTS:
        if not ACCOUNTS[account].is_file():
            pytest.skip(f"le compte {account} n'est pas configure ici")
    fps = {a: key_fingerprint(load_groq_key(a)) for a in ACCOUNTS}
    assert len(set(fps.values())) == len(fps), f"comptes confondus : {fps}"


def test_une_empreinte_ne_divulgue_pas_la_cle():
    fp = key_fingerprint("gsk_" + "A" * 52)
    assert len(fp) == 12 and "gsk_" not in fp


def test_un_compte_inconnu_refuse_plutot_que_de_retomber_sur_la_production(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="compte inconnu"):
        load_groq_key("celui_qui_n_existe_pas")


# --------------------------------------------------------------------------
# 4. Un resultat qui n'existe qu'en memoire d'un processus n'existe pas
# --------------------------------------------------------------------------

def test_le_runner_ecrit_apres_chaque_bras(tmp_path, monkeypatch):
    """Le run du 05/09 a perdu trois bras mesures parce que le quatrieme a leve.

    On fait tomber le troisieme bras et on exige que les deux premiers soient
    sur le disque malgre tout.
    """
    import run_bench
    from membench import arms as arms_mod

    out = tmp_path / "partiel.json"
    real_run = arms_mod.run
    seen: list[str] = []

    def exploding_run(arm, facts, tl):
        seen.append(arm.name)
        if len(seen) == 3:
            # Volontairement PAS un DailyBudgetExhausted : cette panne-la est
            # rattrapee et suivie d'une ecriture, donc elle ne prouve rien sur
            # l'ecriture de boucle. Il faut une panne qui tue le processus.
            raise RuntimeError("panne non rattrapee au troisieme bras")
        return real_run(arm, facts, tl)

    monkeypatch.setattr(run_bench, "run", exploding_run)
    monkeypatch.setattr(
        run_bench, "GroqModel",
        lambda **kw: type("m", (), {"account": "test", "key_fingerprint": "x",
                                    "rate_limited": 0, "waited_seconds": 0.0})())
    monkeypatch.setattr("sys.argv", ["run_bench.py", "--limit", "6",
                                     "--out", str(out)])
    with pytest.raises(RuntimeError, match="non rattrapee"):
        run_bench.main()

    assert out.is_file(), (
        "rien n'a ete ecrit : une panne au troisieme bras a emporte les deux "
        "premiers, deja mesures et payes"
    )
    data = json.loads(pathlib.Path(out).read_text(encoding="utf-8"))
    assert data["complete"] is False
    assert len(data["rows"]) == 2, "les bras deja mesures doivent survivre"


def test_un_plafond_quotidien_laisse_aussi_les_bras_deja_mesures(tmp_path, monkeypatch):
    """La meme garantie sur le chemin rattrape, qui rend 2 au lieu de lever."""
    import run_bench
    from membench import arms as arms_mod

    out = tmp_path / "partiel2.json"
    real_run, seen = arms_mod.run, []

    def stopping_run(arm, facts, tl):
        seen.append(arm.name)
        if len(seen) == 3:
            raise DailyBudgetExhausted("plafond quotidien atteint : test")
        return real_run(arm, facts, tl)

    monkeypatch.setattr(run_bench, "run", stopping_run)
    monkeypatch.setattr(
        run_bench, "GroqModel",
        lambda **kw: type("m", (), {"account": "test", "key_fingerprint": "x",
                                    "rate_limited": 0, "waited_seconds": 0.0})())
    monkeypatch.setattr("sys.argv", ["run_bench.py", "--limit", "6", "--out", str(out)])
    assert run_bench.main() == 2
    data = json.loads(pathlib.Path(out).read_text(encoding="utf-8"))
    assert data["complete"] is False and len(data["rows"]) == 2


# --------------------------------------------------------------------------
# 5. Un ecart sans bande n'est pas un resultat
# --------------------------------------------------------------------------

def test_le_bootstrap_est_apparie_et_reproductible():
    """Non apparie, la bande serait plus large et le verdict plus mou."""
    from membench.corpus import build_corpus
    from membench.scoring import Answer
    from membench.stats import paired_bootstrap

    f = build_corpus(seed=1)
    bon = [Answer(x.truth) if x.truth else Answer(None) for x in f]
    mauvais = [Answer("Revit") if x.truth else Answer(None) for x in f]
    a = paired_bootstrap(f, bon, mauvais, draws=500, seed=3)
    b = paired_bootstrap(f, bon, mauvais, draws=500, seed=3)
    assert (a.point, a.lo, a.hi) == (b.point, b.lo, b.hi), "non reproductible"
    assert a.point > 0.5 and a.excludes_zero


def test_un_ecart_nul_donne_une_bande_qui_traverse_zero():
    """Le garde du garde : si deux bras identiques donnent un ecart net,
    l'intervalle est faux et tout ce qu'il valide l'est aussi."""
    from membench.corpus import build_corpus
    from membench.scoring import Answer
    from membench.stats import paired_bootstrap

    f = build_corpus(seed=1)
    same = [Answer(x.truth) if x.truth else Answer(None) for x in f]
    iv = paired_bootstrap(f, same, list(same), draws=500, seed=3)
    assert iv.point == 0.0
    assert not iv.excludes_zero, "deux bras identiques ne peuvent pas differer"


def test_le_bootstrap_refuse_des_bras_non_apparies():
    from membench.corpus import build_corpus
    from membench.scoring import Answer
    from membench.stats import paired_bootstrap

    f = build_corpus(seed=1)
    with pytest.raises(ValueError, match="apparies"):
        paired_bootstrap(f, [Answer("x")], [Answer("y")])


# --------------------------------------------------------------------------
# 6. Deux formulations, un seul contrat
# --------------------------------------------------------------------------

def test_les_deux_gabarits_demandent_le_meme_contrat():
    """Sinon l'A/B mesurerait deux taches, pas deux redactions."""
    from membench.real_arms import PROMPTS

    for key, text in PROMPTS.items():
        assert "ANSWER:" in text, key
        assert "STALE:" in text, key
        assert "UNKNOWN" in text, key
        assert "45" in text, f"{key} n'annonce pas le seuil de peremption"


def test_les_deux_gabarits_ne_sont_pas_la_meme_redaction():
    """Un A/B entre deux paraphrases proches ne teste rien."""
    from membench.real_arms import PROMPTS

    a, b = set(PROMPTS["A"].lower().split()), set(PROMPTS["B"].lower().split())
    shared = len(a & b) / len(a | b)
    assert shared < 0.45, f"gabarits trop proches : {shared:.0%} de mots communs"


def test_le_gabarit_choisi_est_bien_celui_envoye():
    """Le cablage, pas l'intention : un parametre ignore est le defaut maison."""
    from membench.corpus import build_corpus, candidates
    from membench.providers import Completion
    from membench.real_arms import PROMPTS, StatelessArm

    seen = []

    class _Spy:
        def complete(self, system, user, max_tokens=0):
            seen.append(system)
            return Completion(text="ANSWER: UNKNOWN\nSTALE: no", prompt_tokens=1,
                              completion_tokens=1)

    pool = candidates(build_corpus(seed=1))
    for key in ("A", "B"):
        StatelessArm(_Spy(), pool, prompt=key).ask("Le cabinet", "se_situe_à")
    assert seen == [PROMPTS["A"], PROMPTS["B"]]
