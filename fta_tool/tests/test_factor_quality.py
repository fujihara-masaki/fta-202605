"""
Tests for app.services.factor_quality.

The exclude/warn cases mirror real quality problems observed in exported
FTA CSVs (titles generalized — no product/region specific terms).
"""

from app.services.factor_quality import (
    evaluate_factor,
    normalize_title,
    similarity,
)


# ---------------------------------------------------------------------------
# normalize_title
# ---------------------------------------------------------------------------

class TestNormalizeTitle:
    def test_strips_generic_suffix(self):
        assert normalize_title("確認手順の未整備") == "確認手順"
        assert normalize_title("確認手順の未定義") == "確認手順"
        assert normalize_title("稼働確認不足") == "稼働確認"

    def test_repeated_suffixes_collapse(self):
        # 「の不足の漏れ」のような多重サフィックスも除去される
        assert normalize_title("設定の誤りの漏れ") == "設定"

    def test_does_not_empty_out(self):
        # サフィックス語のみのタイトルは（全部は削らず）空にならない
        assert normalize_title("不足") != ""

    def test_whitespace_and_nfkc(self):
        assert normalize_title(" 確認　手順の未整備 ") == "確認手順"


# ---------------------------------------------------------------------------
# similarity
# ---------------------------------------------------------------------------

class TestSimilarity:
    def test_paraphrase_pairs_high(self):
        # CSV実例（一般化）: 親の言い換えとなった子要因
        assert similarity("対象機器の稼働状況確認不足", "対象機器の稼働確認不足") >= 0.72
        assert similarity("稼働状況確認手順の未定義", "確認手順の未整備") >= 0.72

    def test_legitimate_children_low(self):
        assert similarity("確認担当者の未設定", "確認手順の未整備") < 0.72
        assert similarity("接続確認項目の未定義", "対象機器の稼働確認不足") < 0.72
        assert similarity("フェイルオーバー条件の設定誤り", "対象機器が自動切替しなかった") < 0.72

    def test_identical(self):
        assert similarity("同じ要因名", "同じ要因名") == 1.0

    def test_empty(self):
        assert similarity("", "なにか") == 0.0


# ---------------------------------------------------------------------------
# evaluate_factor
# ---------------------------------------------------------------------------

class TestEvaluateFactor:
    def test_parent_paraphrase_excluded(self):
        r = evaluate_factor(
            title="対象機器の稼働状況確認不足",
            description="再起動後の稼働状況を確認していない",
            parent_title="対象機器の稼働確認不足",
        )
        assert r.exclude
        assert "言い換え" in r.exclude_reason

    def test_same_description_as_parent_excluded(self):
        r = evaluate_factor(
            title="まったく別の要因名",
            description="再起動後、対象機器が正常に稼働していることを確認していない",
            parent_title="対象機器の稼働確認不足",
            parent_description="再起動後、対象機器が正常に稼働していることを確認していない",
        )
        assert r.exclude
        assert "説明文が親要因と同一" in r.exclude_reason

    def test_no_rated_similar_excluded(self):
        r = evaluate_factor(
            title="フェイルオーバー条件の定義漏れ",
            description="切替条件が未定義",
            parent_title="稼働状況確認不足",
            no_rated_titles=["フェイルオーバー条件の定義不足"],
        )
        assert r.exclude
        assert "No評価済み" in r.exclude_reason

    def test_existing_similar_warned_not_excluded(self):
        r = evaluate_factor(
            title="稼働状況確認手順の未定義",
            description="手順が未定義",
            parent_title="接続確認項目の未定義",
            existing_titles=["稼働状況確認手順の未定義"],
        )
        # 別親配下の同名要因 → 除外ではなく要確認
        assert not r.exclude
        assert any("既存要因" in w for w in r.warnings)

    def test_generic_title_warned(self):
        r = evaluate_factor(
            title="確認不足",
            description="確認が足りない",
            parent_title="対象機器が自動切替しなかった",
        )
        assert not r.exclude
        assert any("汎用的" in w for w in r.warnings)

    def test_long_title_warned(self):
        long_title = "対象機器再起動後のサービス接続確認および認証状態確認手順の標準作業書への未記載"
        r = evaluate_factor(
            title=long_title,
            description="手順書に記載がない",
            parent_title="確認手順の未整備",
        )
        assert any("長すぎる" in w for w in r.warnings)

    def test_clean_factor_passes(self):
        r = evaluate_factor(
            title="確認担当者の未設定",
            description="稼働確認の担当者が割り当てられていない状態。",
            parent_title="確認手順の未整備",
            existing_titles=["接続確認項目の未定義"],
            no_rated_titles=["ヘルスチェック設定不備"],
        )
        assert not r.exclude
        assert r.warnings == []
        assert r.warning_flags == ""
