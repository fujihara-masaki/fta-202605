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
from typing import Optional

# Generic suffix words that carry little meaning on their own.
# Removing them before comparison makes「確認手順の未整備」and
#「確認手順の未定義」compare as the same core concept「確認手順」.
_SUFFIX_WORDS = (
    "の不足", "不足", "の漏れ", "漏れ", "の未定義", "未定義",
    "の未整備", "未整備", "の欠如", "欠如", "の不備", "不備",
    "の誤り", "誤り", "の未実施", "未実施", "の未設定", "未設定",
    "のミス", "ミス", "の不徹底", "不徹底", "の不十分", "不十分",
    "の遅延", "遅延", "の欠落", "欠落", "の未取得", "未取得",
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
