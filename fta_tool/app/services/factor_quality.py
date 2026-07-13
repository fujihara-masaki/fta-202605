"""
Rule-based quality checks for AI-generated FTA factors.

Runs after generation (provider-agnostic) and decides per factor:
  - exclude: do not save (parent paraphrase, similar to a No-rated factor)
  - warn:    save with warning_flags set (similar to existing factor elsewhere
             in the analysis, over-generic name, over-long name)

All rules are intentionally lightweight (normalization + difflib) and use
domain-generic vocabulary only — no product/region/company specific terms.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Optional

# Generic suffix words that carry little meaning on their own.
# Removing them before comparison makes「確認手順の未整備」and
#「確認手順の未定義」compare as the same core concept「確認手順」.
_SUFFIX_WORDS = (
    "の不足", "不足", "の漏れ", "漏れ", "の未定義", "未定義",
    "の未整備", "未整備", "の欠如", "欠如", "の不備", "不備",
    "の誤り", "誤り", "の未実施", "未実施", "の未設定", "未設定",
    "のミス", "ミス", "の不徹底", "不徹底", "の不十分", "不十分",
    "の遅延", "遅延", "の欠落", "欠落", "の未取得", "未取得",
    # Negation forms:「Xが配布されない」and「Xの配布漏れ」describe the same
    # failure, so the negated verb ending is stripped the same way as the
    # deficiency-noun suffixes above.
    "されていない", "されない", "できていない", "できない",
    "していない", "しない", "がない",
)

# Words that are too generic to be a useful factor title on their own
_OVER_GENERIC_TITLES = frozenset({
    "確認不足", "管理不備", "対応不足", "体制不備", "認識不足",
    "連携不足", "周知不足", "教育不足", "検討不足", "調整不足",
})

# A real factor/top-event title is a single short line. Sample-scenario
# context (system_context / incident_context / demo_points) is multi-line and
# long. The ancestor check must compare against titles only, so any candidate
# that is multi-line or longer than this is treated as non-title text and
# skipped (prevents context blobs from triggering false ancestor warnings).
_MAX_TITLE_LIKE_LENGTH = 60

# Generic tokens that, on their own, do not identify a system component /
# 系統. Excluded from distinctive-token extraction so the No-rated reappearance
# check keys off meaningful component names (DNS, VPN, ファイアウォール, …),
# not bookkeeping words shared by almost every factor title.
_GENERIC_TOKENS = frozenset({
    # generic kanji nouns
    "設定", "確認", "管理", "対応", "不足", "不備", "問題", "状況",
    "影響", "内容", "作業", "手順", "情報", "原因", "要因", "実施",
    "発生", "処理", "利用", "検証", "監視", "機器", "装置", "障害",
    "異常", "状態", "更新", "変更", "誤り", "漏れ", "遅延", "失敗",
    "負荷", "設計", "仕様", "記録", "担当", "通知", "範囲", "条件",
    # generic katakana nouns
    "システム", "サーバ", "アクセス", "データ", "ユーザ", "メモリ",
    "ネットワーク", "サービス", "ファイル", "エラー", "リソース",
    "プロセス", "タイミング", "チェック", "テスト",
})

# Similarity thresholds (SequenceMatcher.ratio on normalized strings)
PARENT_SIMILARITY_THRESHOLD = 0.72
NO_RATED_SIMILARITY_THRESHOLD = 0.78
EXISTING_SIMILARITY_THRESHOLD = 0.82
# Ancestor reversion uses ancestor_similarity() (core-overlap aware),
# so the threshold is independent from the plain-ratio thresholds above.
ANCESTOR_SIMILARITY_THRESHOLD = 0.70
# Minimum shared-core length (chars, after normalization) for the
# core-overlap heuristic — avoids matching on short generic words like「確認」.
_ANCESTOR_MIN_CORE_LENGTH = 4

MAX_TITLE_LENGTH = 30


def normalize_title(title: str) -> str:
    """Normalize a factor title for comparison.

    NFKC-normalize, strip whitespace/punctuation, then repeatedly remove
    generic suffix words so paraphrases collapse to the same core phrase.
    """
    t = unicodedata.normalize("NFKC", title or "").strip().lower()
    t = re.sub(r"[\s「」『』（）()【】・,、。.｡]+", "", t)
    changed = True
    while changed and t:
        changed = False
        for suffix in _SUFFIX_WORDS:
            if t.endswith(suffix) and len(t) > len(suffix):
                t = t[: -len(suffix)]
                changed = True
                break
    return t


def similarity(a: str, b: str) -> float:
    """Similarity in [0,1] between two titles after normalization.

    Containment of one normalized core in the other counts as high
    similarity (e.g.「確認手順」vs「稼働状況確認手順」).
    """
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) >= 4 and shorter in longer:
        # Containment weighted by length ratio: a short core fully contained
        # in a much longer title (e.g. generic「確認手順」inside a long
        # specific title) should NOT count as a paraphrase.
        contained_score = 0.5 + 0.5 * (len(shorter) / len(longer))
        return max(ratio, contained_score)
    return ratio


def ancestor_similarity(child: str, ancestor: str) -> float:
    """Similarity in [0,1] tuned for detecting reversion to an ancestor.

    A child that reverts to an ancestor often re-uses the ancestor's core
    phrase with extra modifiers (e.g.「稼働状況確認手順の未整備」reverting
    to「○○機器の稼働状況確認不足」), which keeps the plain ratio low.
    So in addition to similarity(), score how much of the SHORTER
    normalized title is covered by the longest common substring.
    """
    base = similarity(child, ancestor)
    na, nb = normalize_title(child), normalize_title(ancestor)
    if not na or not nb:
        return base
    shorter_len = min(len(na), len(nb))
    match = SequenceMatcher(None, na, nb).find_longest_match(
        0, len(na), 0, len(nb)
    )
    if match.size >= _ANCESTOR_MIN_CORE_LENGTH and shorter_len > 0:
        return max(base, match.size / shorter_len)
    return base


def _is_title_like(s: str) -> bool:
    """Return True if *s* looks like a factor/top-event title.

    Used to keep the ancestor-similarity check restricted to titles: a real
    title is a single short line, whereas analysis_context text (system /
    incident / demo) is multi-line and long.
    """
    if not s:
        return False
    if "\n" in s or "\r" in s:
        return False
    return len(s.strip()) <= _MAX_TITLE_LIKE_LENGTH


def distinctive_tokens(title: str) -> set[str]:
    """Extract system-component / 系統 identifiers from a factor title.

    Lightweight, dictionary-free extraction (no morphological analysis):
      - ASCII alphanumeric runs of length >= 2  (DNS, VPN, API, TTL, CPU)
      - Katakana runs of length >= 3            (ファイアウォール, キャッシュ)
      - Kanji runs of length >= 2               (認証基盤, 経路制御)

    Generic bookkeeping tokens (_GENERIC_TOKENS) are dropped so the result
    keeps only meaningful component names. Returned tokens are NFKC-normalized
    and ASCII is upper-cased so「ＤＮＳ」and「dns」compare equal.
    """
    if not title:
        return set()
    t = unicodedata.normalize("NFKC", title)
    tokens: set[str] = set()

    for m in re.findall(r"[A-Za-z0-9]{2,}", t):
        tok = m.upper()
        if tok not in _GENERIC_TOKENS:
            tokens.add(tok)
    for m in re.findall(r"[ァ-ヴー]{3,}", t):
        if m not in _GENERIC_TOKENS:
            tokens.add(m)
    for m in re.findall(r"[一-龠々]{2,}", t):
        if m not in _GENERIC_TOKENS:
            tokens.add(m)
    return tokens


@dataclass
class FactorScore:
    """Scored view of a post-generation quality check (Step 1).

    Scores are integers in [0, 100] (higher = better).  ``judgment`` is one of
    ``pass`` / ``warning`` / ``retry_recommended`` / ``fail`` and is intended
    to drive a later LangGraph inspect-then-generate branch — Step 1 only
    computes it, it does not branch on it.
    """
    overall_score: int = 100
    direct_cause_score: int = 100
    parent_child_consistency_score: int = 100
    duplicate_score: int = 100
    specificity_score: int = 100
    hierarchy_score: int = 100
    expression_score: int = 100
    judgment: str = "pass"

    def as_dict(self) -> dict:
        return {
            "overall_score": self.overall_score,
            "direct_cause_score": self.direct_cause_score,
            "parent_child_consistency_score": self.parent_child_consistency_score,
            "duplicate_score": self.duplicate_score,
            "specificity_score": self.specificity_score,
            "hierarchy_score": self.hierarchy_score,
            "expression_score": self.expression_score,
            "judgment": self.judgment,
        }


@dataclass
class QualityResult:
    """Result of checking one generated factor."""
    exclude: bool = False
    exclude_reason: str = ""
    warnings: list[str] = field(default_factory=list)
    # Optional structured score, attached by compute_factor_score(). Stays
    # None for callers that only use exclude/warnings (backward compatible).
    score: Optional["FactorScore"] = None

    @property
    def warning_flags(self) -> str:
        return "; ".join(self.warnings)


def evaluate_factor(
    title: str,
    description: str,
    parent_title: Optional[str],
    parent_description: str = "",
    existing_titles: Optional[list[str]] = None,
    no_rated_titles: Optional[list[str]] = None,
    ancestor_titles: Optional[list[str]] = None,
) -> QualityResult:
    """
    Check one generated factor against its parent and the analysis context.

    Exclusion rules (factor is dropped):
      E1. Title too similar to the parent title  → paraphrase, not a cause
      E2. Description identical to the parent description
      E3. Title too similar to a No-rated factor title

    Warning rules (factor is saved with warning_flags):
      W1. Title similar to an existing factor elsewhere in the analysis
      W2. Title is an over-generic phrase
      W3. Title longer than MAX_TITLE_LENGTH characters
      W4. Title similar to an ancestor factor (above the immediate parent)
          → likely reverting to a higher-level expression instead of
            answering "why did the parent occur". Only title-shaped ancestor
            strings are compared (analysis_context text is ignored). Warning
            only, never excluded — a human should judge it.
      W5. Title shares a system-component token (DNS, VPN, 認証基盤, …) with a
          No-rated factor → the same 系統 reappeared after being rejected.
          Warning only, never excluded.
    """
    result = QualityResult()
    t = (title or "").strip()

    # --- E1: parent paraphrase ---
    if parent_title:
        ratio = similarity(t, parent_title)
        if ratio >= PARENT_SIMILARITY_THRESHOLD:
            result.exclude = True
            result.exclude_reason = f"親要因の言い換え（類似度{ratio:.2f}）"
            return result

    # --- E2: same description as parent ---
    if parent_description and description and \
            description.strip() == parent_description.strip():
        result.exclude = True
        result.exclude_reason = "説明文が親要因と同一"
        return result

    # --- E3: similar to a No-rated factor ---
    for no_title in (no_rated_titles or []):
        ratio = similarity(t, no_title)
        if ratio >= NO_RATED_SIMILARITY_THRESHOLD:
            result.exclude = True
            result.exclude_reason = (
                f"No評価済み要因「{no_title}」に類似（類似度{ratio:.2f}）"
            )
            return result

    # --- W1: similar to existing factor anywhere in the analysis ---
    for ex_title in (existing_titles or []):
        ratio = similarity(t, ex_title)
        if ratio >= EXISTING_SIMILARITY_THRESHOLD:
            result.warnings.append(f"既存要因「{ex_title}」に類似")
            break  # one similar-existing warning is enough

    # --- W4: reversion to an ancestor factor's expression ---
    # Only compare against title-shaped ancestors; analysis_context text
    # (multi-line / long) is never a comparison target.
    for anc_title in (ancestor_titles or []):
        if not _is_title_like(anc_title):
            continue
        ratio = ancestor_similarity(t, anc_title)
        if ratio >= ANCESTOR_SIMILARITY_THRESHOLD:
            result.warnings.append(
                f"祖先要因「{anc_title}」に類似（上位階層の表現への逆戻りの可能性）"
            )
            break  # one ancestor warning is enough

    # --- W5: same system-component (系統) as a No-rated factor reappears ---
    if no_rated_titles:
        cand_tokens = distinctive_tokens(t)
        if cand_tokens:
            no_rated_tokens: set[str] = set()
            for nt in no_rated_titles:
                no_rated_tokens |= distinctive_tokens(nt)
            shared = cand_tokens & no_rated_tokens
            if shared:
                joined = "、".join(sorted(shared))
                result.warnings.append(
                    f"No評価済み要因と同じ系統の語「{joined}」を含む（要確認）"
                )

    # --- W2: over-generic title ---
    if t in _OVER_GENERIC_TITLES:
        result.warnings.append("汎用的すぎる要因名")

    # --- W3: over-long title ---
    if len(t) > MAX_TITLE_LENGTH:
        result.warnings.append(f"要因名が長すぎる（{len(t)}文字）")

    return result


# Score weights for the overall_score (sum = 1.0).
_SCORE_WEIGHTS = {
    "direct_cause_score": 0.20,
    "parent_child_consistency_score": 0.25,
    "duplicate_score": 0.15,
    "specificity_score": 0.15,
    "hierarchy_score": 0.15,
    "expression_score": 0.10,
}


def _clamp(v: int) -> int:
    return max(0, min(100, int(round(v))))


def compute_factor_score(
    result: QualityResult,
    title: str,
    description: str,
    parent_title: Optional[str] = None,
) -> FactorScore:
    """Turn a QualityResult into a structured FactorScore.

    Step 1 only: derives 0–100 sub-scores and a judgment
    (pass/warning/retry_recommended/fail) from the existing rule outputs plus a
    few lightweight heuristics, so a later LangGraph gate can branch on them.
    The QualityResult itself (exclude/warnings) is unchanged.
    """
    t = (title or "").strip()
    desc = (description or "").strip()
    warnings_text = " ".join(result.warnings)
    reason = result.exclude_reason or ""

    # --- parent/child consistency: penalize paraphrase / parent-similarity ---
    if "親要因の言い換え" in reason or "説明文が親要因と同一" in reason:
        parent_child = 10
    elif parent_title:
        sim = similarity(t, parent_title)
        if sim >= PARENT_SIMILARITY_THRESHOLD:
            parent_child = 25
        elif sim >= 0.5:
            parent_child = 60
        else:
            parent_child = 100
    else:
        parent_child = 100

    # --- duplicate / similarity ---
    if "No評価済み要因" in reason and "類似" in reason:
        duplicate = 0
    elif "既存要因" in warnings_text and "類似" in warnings_text:
        duplicate = 50
    else:
        duplicate = 100

    # --- direct-cause likeness: rests on an informative description ---
    if not desc:
        direct_cause = 30
    elif len(desc) < 15:
        direct_cause = 65
    else:
        direct_cause = 100

    # --- specificity: generic name / very short title ---
    specificity = 100
    if "汎用的すぎる要因名" in warnings_text or t in _OVER_GENERIC_TITLES:
        specificity = 40
    elif len(t) <= 3:
        specificity = 60

    # --- hierarchy: reversion to an ancestor expression ---
    hierarchy = 50 if "祖先要因" in warnings_text else 100

    # --- expression naturalness as an FTA factor ---
    expression = 100
    if "要因名が長すぎる" in warnings_text:
        expression = min(expression, 60)
    if "同じ系統の語" in warnings_text:
        expression = min(expression, 70)

    if result.exclude:
        # An excluded factor cannot score well overall regardless of sub-scores.
        direct_cause = min(direct_cause, 30)

    sub = {
        "direct_cause_score": _clamp(direct_cause),
        "parent_child_consistency_score": _clamp(parent_child),
        "duplicate_score": _clamp(duplicate),
        "specificity_score": _clamp(specificity),
        "hierarchy_score": _clamp(hierarchy),
        "expression_score": _clamp(expression),
    }
    overall = _clamp(sum(sub[k] * w for k, w in _SCORE_WEIGHTS.items()))

    if result.exclude:
        judgment = "fail"
        overall = min(overall, 30)
    elif overall < 60:
        judgment = "retry_recommended"
    elif result.warnings:
        judgment = "warning"
    else:
        judgment = "pass"

    return FactorScore(overall_score=overall, judgment=judgment, **sub)


# Short, user-facing label used when a candidate is skipped as a duplicate of
# an existing node already saved in the analysis (DB-level dedup in main.py).
DEDUP_REASON_LABEL = "既存要因との重複・類似"

# ---------------------------------------------------------------------------
# Severity classification for the LangGraph quality gate (additive)
# ---------------------------------------------------------------------------
#
# The legacy path only knows exclude/warn.  The quality gate needs a third
# axis: which kept-with-warning candidates are serious enough to REGENERATE
# (and, if regeneration does not help, to drop).  Severity is computed from
# the existing rule outputs, so the exclude/warn behaviour of the legacy
# path is untouched.
#
#   critical: parent paraphrase / description identical to parent /
#             high similarity to a No-rated factor (all already excluded),
#             plus reversion to an ancestor title and high similarity to an
#             existing factor (kept-with-warning in the legacy path).
#             → regeneration target for the gate.
#   warning:  minor issues a human can resolve (generic-token overlap with a
#             No-rated factor, over-generic name, over-long name).
#             → accept_with_warning, never a regeneration trigger.
#   ok:       no findings.
#
# Token-level overlap of domain-generic words (DNS, VPN, 認証, ファイア
# ウォール, …) is NEVER critical: the similarity() checks compare whole
# normalized titles, and the No-rated token check (W5) stays a warning.

SEVERITY_OK = "ok"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

# Short labels for critical reasons (aligned with summarize_exclusion_reason
# so reason_summary / logs use one vocabulary).
CRITICAL_ANCESTOR_LABEL = "上位階層への逆戻り"
CRITICAL_EXISTING_LABEL = DEDUP_REASON_LABEL

# warning_flags marker appended (by main.py) to factors that were produced by
# a quality-gate regeneration, so the CSV export can tell "warning only" apart
# from "regenerated" / "regenerated but still warned".
REGENERATED_FLAG_LABEL = "再生成により生成"


def classify_warning_severity(warnings: list[str]) -> tuple[str, list[str]]:
    """Classify kept-candidate warnings into a severity + critical labels.

    Only the two structurally-serious warnings become critical:
      - 祖先要因への逆戻り (W4): the candidate is not a deeper cause but a
        return to a higher level of the tree
      - 既存要因との高類似 (W1): semantic near-duplicate inside the analysis
    Everything else (No-rated token overlap, generic name, long name) is a
    minor warning.
    """
    critical: list[str] = []
    for w in warnings or []:
        if "祖先要因" in w:
            critical.append(CRITICAL_ANCESTOR_LABEL)
        elif w.startswith("既存要因") and "類似" in w:
            critical.append(CRITICAL_EXISTING_LABEL)
    if critical:
        return SEVERITY_CRITICAL, list(dict.fromkeys(critical))
    if warnings:
        return SEVERITY_WARNING, []
    return SEVERITY_OK, []


def summarize_exclusion_reason(reason: str) -> str:
    """Collapse a detailed exclusion/skip reason into a short UI-friendly label.

    The detailed text (with similarity ratios etc.) stays in the logs; the UI
    only shows these rolled-up categories so a「+0件」result is explainable.
    """
    r = reason or ""
    if "親要因の言い換え" in r:
        return "親要因の言い換え"
    if "親要因と同一" in r or "説明文が親要因と同一" in r:
        return "親要因と内容が同一"
    if "No評価済み" in r:
        return "No評価済み要因との類似"
    if "既存要因" in r or "重複" in r:
        return DEDUP_REASON_LABEL
    if "汎用" in r or "抽象" in r:
        return "抽象的すぎる要因名"
    if "祖先" in r or "逆戻り" in r:
        return "上位階層への逆戻り"
    if "長すぎる" in r:
        return "要因名が長すぎる"
    return "品質チェックにより除外"


# ---------------------------------------------------------------------------
# Candidate evaluation / outcome classification (Step 2-A refactor)
# ---------------------------------------------------------------------------
#
# These are PURE functions (no DB / no logging / no side effects).  They lift
# the per-candidate quality handling and the outcome classification that were
# previously inlined in main.py's generate endpoint, so the live endpoint and
# the LangGraph workflow (generation_workflow.py) share a single source of
# truth.
#
# DB-dependent duplicate detection (crud.node_title_exists) is intentionally
# NOT handled here — it stays in main.py.


@dataclass
class EvaluatedCandidate:
    """Quality-evaluation result for a single generated candidate.

    ``factor`` is the original candidate object (duck-typed: it only needs
    ``.title`` and ``.description``), returned as-is so the caller can persist
    it.  ``reason_label`` is the short, UI-friendly label and is only set when
    ``excluded`` is True.
    """

    factor: Any
    score: FactorScore
    excluded: bool = False
    exclude_reason: str = ""          # detailed reason (for logs); set when excluded
    reason_label: str = ""            # short summarized label; set when excluded
    warnings: list[str] = field(default_factory=list)
    # Quality-gate severity (additive; legacy callers ignore these):
    # ok / warning / critical, plus short labels for the critical findings.
    severity: str = SEVERITY_OK
    critical_reasons: list[str] = field(default_factory=list)

    @property
    def warning_flags(self) -> str:
        return "; ".join(self.warnings)

    @property
    def judgment(self) -> str:
        return self.score.judgment


@dataclass
class CandidateEvaluation:
    """Aggregated evaluation over a batch of candidates (one parent's worth)."""

    kept: list[EvaluatedCandidate] = field(default_factory=list)
    excluded: list[EvaluatedCandidate] = field(default_factory=list)
    # Short exclusion-reason labels in input order (for reason_summary).
    reasons: list[str] = field(default_factory=list)

    @property
    def excluded_quality(self) -> int:
        return len(self.excluded)

    @property
    def scores(self) -> list[int]:
        """overall_score of each kept candidate (for averaging)."""
        return [c.score.overall_score for c in self.kept]

    @property
    def judgment_counts(self) -> dict:
        counts = {"pass": 0, "warning": 0, "retry_recommended": 0, "fail": 0}
        for c in self.kept:
            counts[c.judgment] = counts.get(c.judgment, 0) + 1
        return counts


def evaluate_candidate(
    factor: Any,
    *,
    parent_factor: Optional[str],
    parent_description: str = "",
    existing_titles: Optional[list[str]] = None,
    no_rated_titles: Optional[list[str]] = None,
    ancestor_titles: Optional[list[str]] = None,
) -> EvaluatedCandidate:
    """Evaluate ONE candidate (pure): rule check + score + reason summary.

    Wraps ``evaluate_factor`` + ``compute_factor_score`` and, for excluded
    candidates, ``summarize_exclusion_reason``.  No DB access, no logging.
    """
    quality = evaluate_factor(
        title=factor.title,
        description=factor.description,
        parent_title=parent_factor,
        parent_description=parent_description,
        existing_titles=existing_titles,
        no_rated_titles=no_rated_titles,
        ancestor_titles=ancestor_titles,
    )
    quality.score = compute_factor_score(
        quality, factor.title, factor.description, parent_factor
    )
    if quality.exclude:
        reason_label = summarize_exclusion_reason(quality.exclude_reason)
        return EvaluatedCandidate(
            factor=factor,
            score=quality.score,
            excluded=True,
            exclude_reason=quality.exclude_reason,
            reason_label=reason_label,
            warnings=list(quality.warnings),
            severity=SEVERITY_CRITICAL,
            critical_reasons=[reason_label],
        )
    severity, critical_reasons = classify_warning_severity(quality.warnings)
    return EvaluatedCandidate(
        factor=factor,
        score=quality.score,
        excluded=False,
        warnings=list(quality.warnings),
        severity=severity,
        critical_reasons=critical_reasons,
    )


def evaluate_candidates(
    factors: list,
    *,
    parent_factor: Optional[str],
    parent_description: str = "",
    existing_titles: Optional[list[str]] = None,
    no_rated_titles: Optional[list[str]] = None,
    ancestor_titles: Optional[list[str]] = None,
) -> CandidateEvaluation:
    """Evaluate a batch of candidates (pure), mirroring main.py's per-factor loop.

    Kept candidates' titles accumulate into the working existing-titles list as
    iteration proceeds, so within-batch near-duplicates get the same
    "既存要因に類似" warning as the live endpoint (which grows
    ``all_analysis_titles`` while creating nodes).

    DB-level dedup is NOT performed here; callers that need it (main.py) do it
    separately before/around this evaluation.
    """
    working_existing = list(existing_titles or [])
    result = CandidateEvaluation()
    for factor in factors:
        ec = evaluate_candidate(
            factor,
            parent_factor=parent_factor,
            parent_description=parent_description,
            existing_titles=working_existing,
            no_rated_titles=no_rated_titles,
            ancestor_titles=ancestor_titles,
        )
        if ec.excluded:
            result.excluded.append(ec)
            result.reasons.append(ec.reason_label)
        else:
            result.kept.append(ec)
            working_existing.append(ec.factor.title)
    return result


def classify_outcome(ai_returned: int, created: int, excluded: int) -> str:
    """Classify a generation result (Step 1.5 semantics).

    - ``created``       : every candidate was kept (created > 0, none excluded)
    - ``partial``       : some kept, some excluded (created > 0, excluded > 0)
    - ``all_excluded``  : candidates existed but all were rejected (created == 0,
                          ai_returned > 0)
    - ``no_candidates`` : the LLM returned nothing (ai_returned == 0)
    """
    if created > 0:
        return "partial" if excluded > 0 else "created"
    if ai_returned > 0:
        return "all_excluded"
    return "no_candidates"
