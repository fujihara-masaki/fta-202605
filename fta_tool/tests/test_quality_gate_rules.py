"""
Tests for the graded quality-gate rules (Step 3.5).

Covers the acceptance criteria of the gate-rule adjustment:
  - parent paraphrase / ancestor reversion / No-rated strong similarity are
    critical → regeneration (retry) target, never a warning-only accept
  - generic-token overlap (DNS, VPN, …) alone is NEVER critical
  - minor warnings end as accept_with_warning without regeneration
  - only the problematic candidate is regenerated (good ones are kept)
  - the retry budget is bounded; after it is spent, usable candidates are
    accepted with warning and critical ones are rejected (reported)
  - gate OFF keeps the legacy behaviour (ancestor reversion stays a
    kept-with-warning candidate, decision vocabulary unchanged)

Same scripted-generate_fn approach as test_quality_gate_workflow.py.
"""

from app.services.ai_provider import GeneratedFactor
from app.services.factor_quality import (
    CRITICAL_ANCESTOR_LABEL,
    CRITICAL_EXISTING_LABEL,
    SEVERITY_CRITICAL,
    SEVERITY_OK,
    SEVERITY_WARNING,
    evaluate_candidate,
)
from app.services.generation_workflow import run_generation_workflow

GOOD = ("証明書の有効期限切れ", "TLS証明書の有効期限が切れていないか確認する")
GOOD2 = ("パスワードポリシーの不整合", "パスワードポリシー設定を確認する")
GOOD3 = ("トークン失効処理の漏れ", "認証トークンの失効処理が実行されているか確認する")
PARENT = "認証基盤の問題"
PARAPHRASE = (PARENT, "認証基盤に問題がある可能性")
PARAPHRASE2 = ("認証基盤の不備", "認証基盤側の不備の可能性")
GENERIC = ("確認不足", "作業前後の確認が実施されていないか確認する")

# 祖先逆戻りシナリオ（依頼文の例に対応）
TOP_EVENT = "在宅勤務者がVPN接続後に社内業務システムへ接続できない"
ANCESTOR = "DNS名前解決の不具合"
REVERT_PARENT = "社内DNSサーバへの問い合わせ失敗"
REVERT = ("DNS名前解決設定の誤り", "DNS名前解決の設定内容を確認する")
REVERT2 = ("DNS名前解決の設定誤り", "名前解決の設定を再確認する")


def _f(title, desc):
    return GeneratedFactor(title=title, description=desc, rationale="r", check_points=[])


class _ScriptedGen:
    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls = 0
        self.received_avoid: list = []

    def __call__(self, extra_existing):
        idx = min(self.calls, len(self.scripts) - 1)
        self.calls += 1
        self.received_avoid.append(list(extra_existing))
        return [_f(t, d) for (t, d) in self.scripts[idx]]


def _run(scripts, *, parent_factor=PARENT, max_retries=1, quality_gate=True,
         quality_threshold=0.7, no_rated=None, ancestors=None, factor_count=4):
    gen = _ScriptedGen(scripts)
    result = run_generation_workflow(
        generate_fn=gen,
        parent_factor=parent_factor,
        parent_description="",
        existing_titles=[],
        all_titles=[],
        no_rated_titles=no_rated or [],
        ancestor_factors=ancestors or [],
        analysis_context={},
        factor_count=factor_count,
        max_retries=max_retries,
        quality_gate=quality_gate,
        quality_threshold=quality_threshold,
    )
    return result, gen


# ---------------------------------------------------------------------------
# per-candidate severity classification (factor_quality)
# ---------------------------------------------------------------------------

class TestSeverityClassification:
    def test_parent_paraphrase_is_critical(self):
        # 依頼文の例: 親「DNS設定の配布漏れ」/ 子「DNS設定が配布されない」
        ec = evaluate_candidate(
            _f("DNS設定が配布されない", "クライアントにDNS設定が配布されていない"),
            parent_factor="DNS設定の配布漏れ",
        )
        assert ec.excluded is True
        assert ec.severity == SEVERITY_CRITICAL
        assert "親要因の言い換え" in ec.critical_reasons

    def test_ancestor_reversion_is_critical_but_not_excluded(self):
        # 依頼文の例: 上位要因「DNS名前解決の不具合」への逆戻り
        ec = evaluate_candidate(
            _f(*REVERT),
            parent_factor=REVERT_PARENT,
            ancestor_titles=[TOP_EVENT, ANCESTOR],
        )
        assert ec.excluded is False          # レガシーパスでは保存＋警告のまま
        assert ec.severity == SEVERITY_CRITICAL
        assert CRITICAL_ANCESTOR_LABEL in ec.critical_reasons

    def test_existing_high_similarity_is_critical(self):
        ec = evaluate_candidate(
            _f("稼働状況確認手順の未定義", "確認手順が定義されていない"),
            parent_factor="接続確認項目の未定義",
            existing_titles=["稼働状況確認手順の未整備"],
        )
        assert ec.excluded is False
        assert ec.severity == SEVERITY_CRITICAL
        assert CRITICAL_EXISTING_LABEL in ec.critical_reasons

    def test_no_rated_strong_similarity_is_critical(self):
        ec = evaluate_candidate(
            _f("DNS設定の誤り", "DNS設定値を確認する"),
            parent_factor="ネットワークの問題",
            no_rated_titles=["DNS設定の誤り"],
        )
        assert ec.excluded is True
        assert ec.severity == SEVERITY_CRITICAL
        assert "No評価済み要因との類似" in ec.critical_reasons

    def test_generic_token_overlap_is_warning_not_critical(self):
        # DNS という汎用語の一致のみ → warning 止まり
        ec = evaluate_candidate(
            _f("DNSサーバの冗長化不足", "DNSサーバが冗長構成になっているか確認する"),
            parent_factor="ネットワークの問題",
            no_rated_titles=["DNS設定の誤り"],
        )
        assert ec.excluded is False
        assert ec.severity == SEVERITY_WARNING
        assert ec.critical_reasons == []
        assert any("同じ系統" in w for w in ec.warnings)

    def test_clean_candidate_is_ok(self):
        ec = evaluate_candidate(_f(*GOOD), parent_factor=PARENT)
        assert ec.severity == SEVERITY_OK
        assert ec.warnings == []
        assert ec.critical_reasons == []


# ---------------------------------------------------------------------------
# graded decisions (gate ON)
# ---------------------------------------------------------------------------

class TestGradedDecisions:
    def test_minor_warning_is_accept_with_warning_without_regen(self):
        res, gen = _run([[GENERIC]], quality_threshold=0.7)
        assert res.decision == "accept_with_warning"
        assert res.regenerated is False
        assert gen.calls == 1
        assert [c.title for c in res.candidates] == [GENERIC[0]]

    def test_generic_token_overlap_accepted_without_regen(self):
        res, gen = _run(
            [[("DNSサーバの冗長化不足", "DNSサーバの冗長構成を確認する")]],
            parent_factor="ネットワークの問題",
            no_rated=["DNS設定の誤り"],
        )
        assert res.decision == "accept_with_warning"
        assert res.regenerated is False
        assert gen.calls == 1
        assert res.rejected == []

    def test_clean_candidates_accepted(self):
        res, gen = _run([[GOOD, GOOD2]])
        assert res.decision == "accept"
        assert res.severity == "ok"
        assert gen.calls == 1

    def test_ancestor_reversion_triggers_regen_and_is_replaced(self):
        res, gen = _run(
            [[REVERT, GOOD], [GOOD2]],
            parent_factor=REVERT_PARENT,
            ancestors=[TOP_EVENT, ANCESTOR],
        )
        assert res.decision == "accept"
        assert res.regenerated is True
        assert res.retry_count == 1
        assert gen.calls == 2
        # 良い候補は維持され、逆戻り候補だけが置き換わる
        assert [c.title for c in res.candidates] == [GOOD[0], GOOD2[0]]
        assert res.regenerated_titles == [GOOD2[0]]

    def test_ancestor_reversion_unimproved_is_rejected(self):
        res, gen = _run(
            [[REVERT], [REVERT2]],
            parent_factor=REVERT_PARENT,
            ancestors=[TOP_EVENT, ANCESTOR],
            max_retries=1,
        )
        assert res.decision == "reject"
        assert res.candidates == []
        assert gen.calls == 2
        assert res.rejected, "rejected には理由付きで残る"
        assert any(
            CRITICAL_ANCESTOR_LABEL in r
            for item in res.rejected for r in item["reasons"]
        )

    def test_no_rated_strong_similarity_triggers_regen(self):
        res, gen = _run(
            [[("DNS設定の誤り", "DNS設定値を確認する")], [GOOD]],
            parent_factor="ネットワークの問題",
            no_rated=["DNS設定の誤り"],
        )
        assert res.decision == "accept"
        assert res.regenerated is True
        assert gen.calls == 2
        assert [c.title for c in res.candidates] == [GOOD[0]]

    def test_partial_regen_keeps_good_candidates(self):
        """3件中1件だけ言い換え → その1件のみ再生成、残り2件は維持。"""
        res, gen = _run([[GOOD, GOOD2, PARAPHRASE], [GOOD3]])
        assert res.decision == "accept"
        assert res.regenerated is True
        assert gen.calls == 2
        assert [c.title for c in res.candidates] == [GOOD[0], GOOD2[0], GOOD3[0]]
        assert res.regenerated_titles == [GOOD3[0]]
        # 再生成呼び出しには前回の全タイトルが回避リストとして渡る
        assert PARAPHRASE[0] in gen.received_avoid[1]
        assert GOOD[0] in gen.received_avoid[1]

    def test_mixed_budget_spent_accepts_good_and_rejects_critical(self):
        """再生成しても言い換えが残る → 良い候補は警告付きaccept、
        言い換えはreject（除外）される。"""
        res, gen = _run([[GOOD, PARAPHRASE], [PARAPHRASE2]], max_retries=1)
        assert res.decision == "accept_with_warning"
        assert gen.calls == 2
        assert [c.title for c in res.candidates] == [GOOD[0]]
        assert [item["title"] for item in res.rejected] == [PARAPHRASE2[0]]
        assert any(
            "親要因の言い換え" in r
            for item in res.rejected for r in item["reasons"]
        )

    def test_paraphrase_never_accepted_with_warning_only(self):
        """親の言い換えは accept（警告のみ）で残らない: 全attemptで言い換え
        → reject で除外される。"""
        res, gen = _run([[PARAPHRASE], [PARAPHRASE2]], max_retries=1)
        assert res.decision == "reject"
        assert res.candidates == []
        assert res.severity == "critical"

    def test_retry_budget_is_bounded(self):
        res, gen = _run(
            [[PARAPHRASE], [PARAPHRASE2], [PARAPHRASE], [PARAPHRASE2]],
            max_retries=2,
        )
        assert gen.calls == 3          # 初回 + 再生成2回まで
        assert res.retry_count == 2
        assert res.decision == "reject"


# ---------------------------------------------------------------------------
# gate OFF: legacy behaviour preserved
# ---------------------------------------------------------------------------

class TestGateOffUnchanged:
    def test_ancestor_reversion_kept_without_regen(self):
        """ゲートOFFでは祖先逆戻りは従来通り保存対象（警告のみ）で、
        再生成は発生しない。"""
        res, gen = _run(
            [[REVERT, GOOD]],
            parent_factor=REVERT_PARENT,
            ancestors=[TOP_EVENT, ANCESTOR],
            quality_gate=False,
        )
        assert res.decision == "accept"
        assert res.regenerated is False
        assert gen.calls == 1
        assert [c.title for c in res.candidates] == [REVERT[0], GOOD[0]]
        assert res.rejected == []

    def test_gate_off_decision_vocabulary_unchanged(self):
        res, _ = _run([[PARAPHRASE], [PARAPHRASE]], quality_gate=False)
        assert res.decision == "fail_soft"   # 従来の語彙のまま
        res2, _ = _run([[GOOD]], quality_gate=False)
        assert res2.decision == "accept"
