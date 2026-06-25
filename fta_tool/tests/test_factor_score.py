"""Tests for the post-generation quality scoring (Step 1)."""

import pytest

from app.services.factor_quality import (
    DEDUP_REASON_LABEL,
    FactorScore,
    compute_factor_score,
    evaluate_factor,
    summarize_exclusion_reason,
)


def _score(title, description, parent_title=None, **kw):
    result = evaluate_factor(
        title=title, description=description, parent_title=parent_title, **kw
    )
    return result, compute_factor_score(result, title, description, parent_title)


def test_good_factor_scores_pass():
    result, score = _score(
        "認証トークンの有効期限切れ",
        "認証トークンの有効期限が切れていないかログで確認する",
        parent_title="ログイン処理の失敗",
    )
    assert isinstance(score, FactorScore)
    assert score.judgment == "pass"
    assert score.overall_score >= 80
    assert not result.warnings


def test_parent_paraphrase_scores_fail():
    result, score = _score("ログイン処理の失敗", "ログイン処理が失敗した", parent_title="ログイン処理の失敗")
    assert result.exclude
    assert score.judgment == "fail"
    assert score.overall_score <= 30
    assert score.parent_child_consistency_score <= 30


def test_no_rated_similar_scores_fail():
    result, score = _score(
        "DNS設定の誤り", "DNSの設定値を確認する",
        parent_title="ネットワークの問題",
        no_rated_titles=["DNS設定の誤り"],
    )
    assert result.exclude
    assert score.judgment == "fail"
    assert score.duplicate_score == 0


def test_generic_title_lowers_specificity():
    result, score = _score(
        "確認不足", "関係者への確認が不足していた可能性を調べる",
        parent_title="運用手順の不備",
    )
    # 汎用的すぎる要因名 warning is attached
    assert any("汎用的" in w for w in result.warnings)
    assert score.specificity_score <= 50
    assert score.judgment in ("warning", "retry_recommended")


def test_existing_similar_lowers_duplicate_and_warns():
    result, score = _score(
        "設定変更の反映漏れ", "直近の設定変更が反映されているか確認する",
        parent_title="リリース作業の問題",
        existing_titles=["設定変更の反映漏れ"],
    )
    assert any("既存要因" in w for w in result.warnings)
    assert score.duplicate_score <= 60
    assert score.judgment in ("warning", "retry_recommended")


def test_score_serializable_dict():
    _, score = _score("具体的な要因名", "十分に具体的な説明テキストです", parent_title="親要因")
    d = score.as_dict()
    assert set(d) == {
        "overall_score", "direct_cause_score", "parent_child_consistency_score",
        "duplicate_score", "specificity_score", "hierarchy_score",
        "expression_score", "judgment",
    }
    assert all(0 <= d[k] <= 100 for k in d if k != "judgment")


def test_evaluate_factor_backward_compatible():
    """evaluate_factor still works without scoring (score stays None)."""
    result = evaluate_factor(title="技術的要因", description="技術的な観点", parent_title=None)
    assert result.score is None
    assert not result.exclude


# --- summarize_exclusion_reason (Step 1.5) ---

@pytest.mark.parametrize("detail,expected", [
    ("親要因の言い換え（類似度0.94）", "親要因の言い換え"),
    ("説明文が親要因と同一", "親要因と内容が同一"),
    ("No評価済み要因「DNS設定の誤り」に類似（類似度1.00）", "No評価済み要因との類似"),
    ("既存要因「設定変更の反映漏れ」に類似", DEDUP_REASON_LABEL),
    ("汎用的すぎる要因名", "抽象的すぎる要因名"),
    ("祖先要因「○○」に類似（上位階層の表現への逆戻りの可能性）", "上位階層への逆戻り"),
    ("要因名が長すぎる（35文字）", "要因名が長すぎる"),
])
def test_summarize_exclusion_reason_maps_to_short_label(detail, expected):
    assert summarize_exclusion_reason(detail) == expected


def test_summarize_exclusion_reason_unknown_falls_back():
    assert summarize_exclusion_reason("謎の理由") == "品質チェックにより除外"
    assert summarize_exclusion_reason("") == "品質チェックにより除外"


def test_summarize_real_exclude_reason_from_evaluate_factor():
    """The label derives correctly from an actual evaluate_factor exclusion."""
    result = evaluate_factor(
        title="ログイン処理の失敗", description="失敗した",
        parent_title="ログイン処理の失敗",
    )
    assert result.exclude
    assert summarize_exclusion_reason(result.exclude_reason) == "親要因の言い換え"
