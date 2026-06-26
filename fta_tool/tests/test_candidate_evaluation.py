"""
Unit tests for the Step 2-A extraction: pure candidate-evaluation and
outcome-classification helpers in factor_quality.

These mirror the per-factor quality logic that previously lived inline in
main.py's generate endpoint. They are DB-free and side-effect-free.
"""

from app.services.ai_provider import GeneratedFactor
from app.services.factor_quality import (
    CandidateEvaluation,
    EvaluatedCandidate,
    classify_outcome,
    evaluate_candidate,
    evaluate_candidates,
)


def _f(title: str, description: str = "十分に具体的な説明テキストです") -> GeneratedFactor:
    return GeneratedFactor(title=title, description=description, rationale="r", check_points=[])


# --- classify_outcome -------------------------------------------------------

def test_classify_outcome_created():
    assert classify_outcome(ai_returned=3, created=3, excluded=0) == "created"


def test_classify_outcome_partial():
    assert classify_outcome(ai_returned=3, created=2, excluded=1) == "partial"


def test_classify_outcome_all_excluded():
    assert classify_outcome(ai_returned=2, created=0, excluded=2) == "all_excluded"


def test_classify_outcome_no_candidates():
    assert classify_outcome(ai_returned=0, created=0, excluded=0) == "no_candidates"


def test_classify_outcome_all_dedup_is_all_excluded():
    """created==0 with candidates (even if all dedup) is all_excluded, matching
    main.py's all_candidates_excluded = ai_returned>0 and created==0."""
    assert classify_outcome(ai_returned=2, created=0, excluded=2) == "all_excluded"


# --- evaluate_candidate (single) -------------------------------------------

def test_evaluate_candidate_parent_paraphrase_excluded():
    ec = evaluate_candidate(
        _f("認証基盤の問題", "認証基盤に問題がある可能性"),
        parent_factor="認証基盤の問題",
    )
    assert isinstance(ec, EvaluatedCandidate)
    assert ec.excluded is True
    assert ec.reason_label == "親要因の言い換え"
    assert "親要因の言い換え" in ec.exclude_reason  # detailed reason retained
    assert ec.judgment == "fail"


def test_evaluate_candidate_good_is_kept_with_pass():
    ec = evaluate_candidate(
        _f("証明書の有効期限切れ", "TLS証明書の有効期限が切れていないか確認する"),
        parent_factor="ネットワークの問題",
    )
    assert ec.excluded is False
    assert ec.warnings == []
    assert ec.judgment == "pass"


def test_evaluate_candidate_warning_kept():
    """A near-duplicate of an existing title is kept WITH a warning (not dropped)."""
    ec = evaluate_candidate(
        _f("設定変更の反映漏れ", "直近の設定変更が反映されているか確認する"),
        parent_factor="リリース作業の問題",
        existing_titles=["設定変更の反映漏れ"],
    )
    assert ec.excluded is False
    assert any("既存要因" in w for w in ec.warnings)
    assert "既存要因" in ec.warning_flags


# --- evaluate_candidates (batch) -------------------------------------------

def test_evaluate_candidates_excludes_parent_paraphrase():
    ev = evaluate_candidates(
        [
            _f("証明書の有効期限切れ", "TLS証明書の有効期限を確認する"),
            _f("ネットワークの問題", "ネットワークに問題がある可能性"),  # parent paraphrase
        ],
        parent_factor="ネットワークの問題",
    )
    assert isinstance(ev, CandidateEvaluation)
    assert len(ev.kept) == 1
    assert ev.kept[0].factor.title == "証明書の有効期限切れ"
    assert ev.excluded_quality == 1
    assert ev.reasons == ["親要因の言い換え"]


def test_evaluate_candidates_keeps_warning_candidate():
    ev = evaluate_candidates(
        [_f("設定変更の反映漏れ", "直近の設定変更が反映されているか確認する")],
        parent_factor="リリース作業の問題",
        existing_titles=["設定変更の反映漏れ"],
    )
    assert len(ev.kept) == 1
    assert ev.excluded_quality == 0
    assert any("既存要因" in w for w in ev.kept[0].warnings)
    # judgment counts reflect the warning candidate
    assert ev.judgment_counts["warning"] >= 1


def test_evaluate_candidates_reason_summary_labels():
    """reason labels are the short, rolled-up form, in input order."""
    ev = evaluate_candidates(
        [
            _f("親要因X", "親と同じ"),                 # parent paraphrase
            _f("DNS設定の誤り", "DNSの設定値を確認する"),  # No-rated similar
        ],
        parent_factor="親要因X",
        no_rated_titles=["DNS設定の誤り"],
    )
    assert ev.reasons == ["親要因の言い換え", "No評価済み要因との類似"]


def test_evaluate_candidates_within_batch_duplicate_warns():
    """Kept titles accumulate, so a later identical candidate is flagged."""
    ev = evaluate_candidates(
        [
            _f("証明書の有効期限切れ", "TLS証明書の有効期限を確認する"),
            _f("証明書の有効期限切れ", "別の説明だが同じタイトル"),
        ],
        parent_factor="ネットワークの問題",
    )
    # Both kept (no DB dedup here), but the 2nd carries a similar-existing warning.
    assert len(ev.kept) == 2
    assert any("既存要因" in w for w in ev.kept[1].warnings)


def test_evaluate_candidates_does_not_dedup_existing_title():
    """A candidate whose title is already in existing_titles is NOT dropped here
    (DB-level dedup is main.py's job) — it is kept (with a warning)."""
    ev = evaluate_candidates(
        [_f("既存タイトル", "既存タイトルに関する具体的な確認内容")],
        parent_factor="別の親要因",
        existing_titles=["既存タイトル"],
    )
    assert len(ev.kept) == 1  # kept, not deduped
    assert ev.excluded_quality == 0


def test_factor_quality_has_no_db_dependency():
    """The evaluation module must not import DB/crud (pure functions)."""
    import app.services.factor_quality as fq
    assert not hasattr(fq, "crud")
    assert not hasattr(fq, "node_title_exists")
