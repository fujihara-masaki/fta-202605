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

# Similarity thresholds (SequenceMatcher.ratio on normalized strings)
PARENT_SIMILARITY_THRESHOLD = 0.72
NO_RATED_SIMILARITY_THRESHOLD = 0.78
EXISTING_SIMILARITY_THRESHOLD = 0.82

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


@dataclass
class QualityResult:
    """Result of checking one generated factor."""
    exclude: bool = False
    exclude_reason: str = ""
    warnings: list[str] = field(default_factory=list)

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

    # --- W2: over-generic title ---
    if t in _OVER_GENERIC_TITLES:
        result.warnings.append("汎用的すぎる要因名")

    # --- W3: over-long title ---
    if len(t) > MAX_TITLE_LENGTH:
        result.warnings.append(f"要因名が長すぎる（{len(t)}文字）")

    return result
