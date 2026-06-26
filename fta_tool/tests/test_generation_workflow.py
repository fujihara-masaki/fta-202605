"""
Unit tests for the LangGraph per-parent generation workflow (Step 2-1).

The provider call is injected as ``generate_fn`` so no LLM/Ollama is needed.
``generate_fn`` is scripted: it returns the next list on each call, recording
the call count so regeneration behaviour can be asserted precisely.
"""

from app.services.ai_provider import GeneratedFactor
from app.services.generation_workflow import WorkflowResult, run_generation_workflow

GOOD = ("証明書の有効期限切れ", "TLS証明書の有効期限が切れていないか確認する")
GOOD2 = ("DNS応答の遅延", "DNSサーバの応答時間が劣化していないか確認する")
PARENT = "認証基盤の問題"
PARAPHRASE = (PARENT, "認証基盤に問題がある可能性")  # excluded as parent paraphrase


def _f(title, desc):
    return GeneratedFactor(title=title, description=desc, rationale="r", check_points=[])


class _ScriptedGen:
    """Callable generate_fn returning the next scripted list per call."""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls = 0

    def __call__(self, extra_existing):
        idx = min(self.calls, len(self.scripts) - 1)
        self.calls += 1
        return [_f(t, d) for (t, d) in self.scripts[idx]]


def _run(scripts, *, parent_factor=PARENT, max_retries=1, no_rated=None):
    gen = _ScriptedGen(scripts)
    result = run_generation_workflow(
        generate_fn=gen,
        parent_factor=parent_factor,
        parent_description="",
        existing_titles=[],
        all_titles=[],
        no_rated_titles=no_rated or [],
        ancestor_factors=[],
        analysis_context={},
        factor_count=4,
        max_retries=max_retries,
    )
    return result, gen


# 1. created → no regeneration
def test_created_no_regeneration():
    res, gen = _run([[GOOD, GOOD2]])
    assert res.outcome == "created"
    assert res.regenerated is False
    assert res.retry_count == 0
    assert gen.calls == 1


# 2. partial → no regeneration
def test_partial_no_regeneration():
    res, gen = _run([[GOOD, PARAPHRASE]])  # one good + one excluded
    assert res.outcome == "partial"
    assert res.regenerated is False
    assert gen.calls == 1


# 3. all_excluded → regenerate once
def test_all_excluded_regenerates_once():
    res, gen = _run([[PARAPHRASE], [GOOD]])
    assert res.regenerated is True
    assert res.retry_count == 1
    assert gen.calls == 2
    # 5. regeneration produced a good candidate → created
    assert res.outcome == "created"
    assert [c.title for c in res.candidates] == [GOOD[0]]


# 4. no_candidates → regenerate once
def test_no_candidates_regenerates_once():
    res, gen = _run([[], [GOOD]])
    assert res.regenerated is True
    assert res.retry_count == 1
    assert gen.calls == 2
    assert res.outcome == "created"


# 6. regenerate still NG → finalized as all_excluded, regenerated True
def test_regenerate_still_all_excluded():
    res, gen = _run([[PARAPHRASE], [PARAPHRASE]])
    assert res.regenerated is True
    assert res.retry_count == 1
    assert gen.calls == 2
    assert res.outcome == "all_excluded"


def test_regenerate_still_no_candidates():
    res, gen = _run([[], []])
    assert res.regenerated is True
    assert res.outcome == "no_candidates"
    assert gen.calls == 2


# 7. max_retries=0 → never regenerate
def test_max_retries_zero_no_regeneration():
    res, gen = _run([[PARAPHRASE], [GOOD]], max_retries=0)
    assert res.regenerated is False
    assert res.retry_count == 0
    assert gen.calls == 1
    assert res.outcome == "all_excluded"


# 8. provider call count for the created case is exactly 1 (covered above too)
def test_provider_called_once_when_created():
    res, gen = _run([[GOOD]])
    assert gen.calls == 1
    assert res.error is None


# 9. exception → error captured in result (main.py falls back)
def test_exception_sets_error():
    def boom(extra_existing):
        raise RuntimeError("provider down")

    res = run_generation_workflow(
        generate_fn=boom,
        parent_factor=PARENT,
        parent_description="",
        existing_titles=[],
        all_titles=[],
        no_rated_titles=[],
        ancestor_factors=[],
        analysis_context={},
        factor_count=4,
        max_retries=1,
    )
    assert isinstance(res, WorkflowResult)
    assert res.error == "provider down"
    assert res.candidates == []


# no_rated similarity is also an exclusion path → all_excluded then regen
def test_no_rated_excluded_triggers_regeneration():
    res, gen = _run(
        [[("DNS設定の誤り", "DNSの設定値を確認する")], [GOOD]],
        parent_factor="ネットワークの問題",
        no_rated=["DNS設定の誤り"],
    )
    assert res.regenerated is True
    assert gen.calls == 2
    assert res.outcome == "created"
