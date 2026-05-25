"""
AI Provider abstraction layer for FTA factor generation.

Supported providers:
- MockAIProvider: Default, works without any external API
- OllamaProvider: Local LLM via Ollama (http://localhost:11434)
- AzureOpenAIProvider: Uses Azure OpenAI Chat Completions API
- HttpCopilotProvider: Uses a custom HTTP endpoint (for Copilot Studio, Power Automate, etc.)

Set AI_PROVIDER environment variable to select provider:
- (not set or "mock"): MockAIProvider
- "ollama": OllamaProvider
- "azure_openai": AzureOpenAIProvider
- "http_copilot": HttpCopilotProvider
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class GeneratedFactor(BaseModel):
    title: str
    description: str
    rationale: str
    check_points: list[str]


class AIProvider(ABC):
    @abstractmethod
    def generate_factors(
        self,
        analysis_title: str,
        top_event: str,
        target_level: int,
        parent_path: list[str],
        parent_factor: Optional[str],
        context: dict,
    ) -> list[GeneratedFactor]:
        ...


LEVEL_NAMES = {
    1: "一次要因（大分類）",
    2: "二次要因（一次要因の具体化）",
    3: "三次要因（調査・確認可能な具体的原因候補）",
}

# ---------------------------------------------------------------------------
# Post-generation quality filter
# ---------------------------------------------------------------------------

_GENERIC_NAMES = frozenset({
    "原因", "要因", "問題", "不備", "障害", "エラー", "失敗", "その他",
    "課題", "不具合", "欠陥", "影響", "リスク", "要因パス",
    "主要因", "副要因", "直接原因", "間接原因", "複合要因", "関連要因",
})

_TRIVIAL_DESC_SUFFIXES = (
    "が原因である", "が要因である", "が問題である", "による障害", "のため",
    "が発生した", "が発生している",
)


def _resembles_parent(name: str, parent: str) -> bool:
    """Return True if name is very similar to parent_factor (heuristic)."""
    n, p = name.strip(), parent.strip()
    if n == p:
        return True
    shorter, longer = (n, p) if len(n) <= len(p) else (p, n)
    # Flag only when the shorter string (≤12 chars) is fully contained in the longer
    if len(shorter) <= 12 and shorter in longer:
        return True
    return False


def _is_trivial_description(desc: str, name: str) -> bool:
    """Return True if description adds no information beyond a trivial suffix."""
    d = desc.strip()
    if not d:
        return True
    if len(d) <= 20:
        for suffix in _TRIVIAL_DESC_SUFFIXES:
            if d.endswith(suffix):
                return True
        if d == name or d == name + "の問題" or d == name + "が発生":
            return True
    return False


def filter_generated_factors(
    factors: list[GeneratedFactor],
    parent_factor: Optional[str],
) -> tuple[list[GeneratedFactor], list[tuple[str, str]]]:
    """
    Remove low-quality factors from AI output.

    Returns (kept, excluded) where excluded is a list of (title, reason) pairs.

    Removes factors that:
    - Have an empty or generic-only name
    - Are identical or very similar to the parent factor
    - Are duplicated within this batch
    - Have an empty description
    - Have a trivially uninformative description
    """
    kept: list[GeneratedFactor] = []
    excluded: list[tuple[str, str]] = []
    seen: set[str] = set()

    for f in factors:
        name = f.title.strip()
        desc = f.description.strip()

        if not name:
            excluded.append(("(空)", "name空"))
        elif name in _GENERIC_NAMES:
            excluded.append((name, "汎用語のみ"))
        elif parent_factor and name == parent_factor.strip():
            excluded.append((name, "親要因と同一"))
        elif parent_factor and _resembles_parent(name, parent_factor):
            excluded.append((name, "親要因に酷似"))
        elif name in seen:
            excluded.append((name, "バッチ内重複"))
        elif not desc:
            excluded.append((name, "description空"))
        elif _is_trivial_description(desc, name):
            excluded.append((name, f"説明が不十分({desc[:30]!r})"))
        else:
            seen.add(name)
            kept.append(f)

    return kept, excluded

# --- Mock data for various scenarios ---
MOCK_FACTORS = {
    1: [
        ("技術的要因", "システム・インフラ・ソフトウェアに起因する技術的な問題", "技術的な観点からの原因を検討する"),
        ("運用・手順要因", "運用手順や作業プロセスに起因する問題", "日常の運用・保守作業における問題を検討する"),
        ("体制・認識要因", "組織体制や担当者の認識・スキルに起因する問題", "組織・人的観点からの原因を検討する"),
        ("変更管理要因", "変更作業・リリースに起因する問題", "直近の変更作業との関連を検討する"),
        ("外部依存要因", "外部サービス・ベンダーに起因する問題", "外部依存関係の観点から原因を検討する"),
    ],
    2: [
        ("設定・パラメータの問題", "設定値や環境パラメータが正しく設定されていなかった可能性", "設定内容を具体的に確認する"),
        ("ソフトウェアの不具合", "アプリケーションやミドルウェアにバグが存在した可能性", "エラーログやコードを確認する"),
        ("リソース不足", "CPU・メモリ・ディスク・ネットワーク帯域が不足していた可能性", "リソース使用状況を確認する"),
        ("依存サービスの障害", "連携する外部サービスや内部サービスが正常でなかった可能性", "依存サービスの状態を確認する"),
        ("タイムアウト・性能劣化", "処理時間が規定を超えた可能性", "レスポンスタイムの推移を確認する"),
    ],
    3: [
        ("ログに異常なエラーメッセージが記録されている", "特定のエラーコードやスタックトレースが存在する可能性", "アプリケーションログ・システムログを精査する"),
        ("直近で設定変更が行われた", "障害発生直前に設定ファイルや環境変数が変更された可能性", "変更履歴・デプロイ記録を確認する"),
        ("証明書・認証情報の期限切れ", "TLS証明書やAPIキー等の有効期限が切れた可能性", "証明書の有効期限と更新履歴を確認する"),
        ("ネットワーク経路の疎通不良", "特定のホスト・ポート間の通信が遮断されている可能性", "ping/traceroute/netstatで経路を確認する"),
        ("データベースの接続上限超過", "DB接続プールが枯渇している可能性", "DB接続数の推移とmax_connectionsを確認する"),
    ],
}


class MockAIProvider(AIProvider):
    """
    Mock AI provider for local testing without external API.
    Returns plausible FTA factors based on input context.
    Respects factor_count from context (default 5).
    """

    def generate_factors(
        self,
        analysis_title: str,
        top_event: str,
        target_level: int,
        parent_path: list[str],
        parent_factor: Optional[str],
        context: dict,
    ) -> list[GeneratedFactor]:
        factor_count = int(context.get("factor_count", 5))
        base_factors = MOCK_FACTORS.get(target_level, MOCK_FACTORS[1])
        results = []
        parent_label = parent_factor or top_event

        for title, desc, rationale in base_factors[:factor_count]:
            results.append(GeneratedFactor(
                title=title,
                description=f"「{parent_label}」に関連する{desc}",
                rationale=rationale,
                check_points=[
                    f"{title}に関するログ・記録を確認する",
                    "直近の変更作業との関連を確認する",
                    "担当者へのヒアリングを実施する",
                    "監視ツールのアラート履歴を確認する",
                ],
            ))
        return results


class AzureOpenAIProvider(AIProvider):
    """
    Azure OpenAI Chat Completions API provider.

    Required environment variables:
        AI_PROVIDER=azure_openai
        AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
        AZURE_OPENAI_API_KEY=<your-key>
        AZURE_OPENAI_DEPLOYMENT=<deployment-name>
        AZURE_OPENAI_API_VERSION=2024-02-01
    """

    def __init__(self):
        self.endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        self.api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        self.deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
        self.api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")

        if not all([self.endpoint, self.api_key, self.deployment]):
            raise ValueError(
                "Azure OpenAI requires AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT"
            )

    def _build_prompt(
        self,
        analysis_title: str,
        top_event: str,
        target_level: int,
        parent_path: list[str],
        parent_factor: Optional[str],
    ) -> str:
        level_name = LEVEL_NAMES.get(target_level, f"レベル{target_level}要因")
        parent_desc = parent_factor or top_event
        path_str = " > ".join(parent_path) if parent_path else top_event

        # FTA factor generation prompt
        # Purpose: Generate MECE candidate factors for FTA tree construction
        # Output must be a JSON array of GeneratedFactor objects
        return f"""あなたはFTA（フォルトツリー解析）の専門家です。
以下の情報を元に、{level_name}の候補を5件生成してください。

【分析タイトル】
{analysis_title}

【頂上事象】
{top_event}

【対象の親要因】
{parent_desc}

【要因パス】
{path_str}

【生成ルール】
- 要因はMECEになるよう心がけてください。
- 技術要因、運用要因、手順要因、体制要因、認識差、監視・検知、変更管理、設計、外部依存、人的要因を必要に応じて考慮してください。
- {level_name}の観点で生成してください。
  - 一次要因: 大分類（技術的・運用的・体制的等の観点）
  - 二次要因: 一次要因の具体化
  - 三次要因: 調査・確認可能な具体的原因候補
- 断定せず、「～の可能性がある」「～が考えられる」等の候補として表現してください。
- 出力は必ずJSON配列のみとし、前後に説明文を入れないでください。

【出力形式】
[
  {{
    "title": "要因のタイトル（簡潔に）",
    "description": "要因の説明（2〜3文）",
    "rationale": "この要因を挙げた理由",
    "check_points": ["確認観点1", "確認観点2", "確認観点3"]
  }},
  ...
]
"""

    def generate_factors(
        self,
        analysis_title: str,
        top_event: str,
        target_level: int,
        parent_path: list[str],
        parent_factor: Optional[str],
        context: dict,
    ) -> list[GeneratedFactor]:
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"
        prompt = self._build_prompt(analysis_title, top_event, target_level, parent_path, parent_factor)

        payload = {
            "messages": [
                {"role": "system", "content": "あなたはFTA分析の専門家です。指示に従い、JSON形式で回答してください。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers={"api-key": self.api_key, "Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                factors_data = json.loads(content)
                return [GeneratedFactor(**f) for f in factors_data]
        except httpx.HTTPStatusError as e:
            logger.error(f"Azure OpenAI HTTP error: {e.response.status_code} {e.response.text}")
            raise RuntimeError(f"Azure OpenAI APIエラー: HTTPステータス {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error(f"Azure OpenAI request error: {e}")
            raise RuntimeError(f"Azure OpenAI 通信エラー: {e}") from e
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Azure OpenAI response parse error: {e}")
            raise RuntimeError(f"AIレスポンスのパースに失敗しました: {e}") from e


class OllamaProvider(AIProvider):
    """
    Local LLM provider using Ollama (https://ollama.com).

    Calls POST {OLLAMA_BASE_URL}/api/chat with stream=false.
    Uses a JSON Schema in the format field (Ollama structured output) so the model
    is constrained to return {"factors": [...]}.  Falls back gracefully when the
    model returns list[str] or other partial formats.

    Environment variables:
        AI_PROVIDER=ollama
        OLLAMA_BASE_URL=http://localhost:11434   (default)
        OLLAMA_MODEL=gemma3:4b                   (default)

    Windows 11 quick start:
        1. Download and install Ollama from https://ollama.com/download/windows
        2. Open a terminal and run: ollama pull gemma3:4b
        3. Set AI_PROVIDER=ollama in .env and start the FTA tool
    """

    # JSON Schema passed to Ollama's format field (structured output).
    # Compact format: {name, description, confidence} reduces tokens and
    # improves generation speed compared to the full 4-field schema.
    _FORMAT_SCHEMA: dict = {
        "type": "object",
        "properties": {
            "factors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":        {"type": "string"},
                        "description": {"type": "string"},
                        "confidence":  {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["name", "description", "confidence"],
                },
            }
        },
        "required": ["factors"],
    }

    # Default values used when a model returns list[str] instead of list[dict]
    _STR_RESCUE_DESCRIPTION = (
        "ローカルLLMが文字列のみで返した候補です。詳細は手動で補足してください。"
    )
    _STR_RESCUE_RATIONALE = "ローカルLLMにより候補として生成されました。"
    _STR_RESCUE_CHECK_POINTS = [
        "候補内容が頂上事象や親要因と関係するか確認する",
        "ログ、設定、手順書、運用記録などで裏付けを確認する",
        "必要に応じて要因名、説明、根拠を手動で補足する",
    ]

    def __init__(self):
        self.base_url   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model      = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
        self.keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "10m")
        self.chat_url   = f"{self.base_url}/api/chat"

        raw_timeout = os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180")
        try:
            self.timeout = float(raw_timeout)
        except ValueError:
            logger.warning(
                "OLLAMA_TIMEOUT_SECONDS=%r is not a valid number; using 180s", raw_timeout
            )
            self.timeout = 180.0

        # Ollama inference options (tunable via .env)
        try:
            self.num_predict = int(os.environ.get("OLLAMA_NUM_PREDICT", "768"))
        except ValueError:
            self.num_predict = 768
        try:
            self.temperature = float(os.environ.get("OLLAMA_TEMPERATURE", "0.2"))
        except ValueError:
            self.temperature = 0.2
        try:
            self.num_ctx = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))
        except ValueError:
            self.num_ctx = 4096

        logger.info(
            "OllamaProvider init | model=%s timeout=%.0fs keep_alive=%s "
            "num_predict=%d temperature=%.2f num_ctx=%d url=%s",
            self.model, self.timeout, self.keep_alive,
            self.num_predict, self.temperature, self.num_ctx,
            self.chat_url,
        )

    def _build_prompt(
        self,
        analysis_title: str,
        top_event: str,
        target_level: int,
        parent_path: list[str],
        parent_factor: Optional[str],
        context: dict,
    ) -> str:
        parent_desc = parent_factor or top_event
        path_str = " > ".join(parent_path) if parent_path else top_event
        factor_count = int(context.get("factor_count", 4))
        existing_titles: list[str] = context.get("existing_titles") or []

        existing_section = ""
        if existing_titles:
            lines = "\n".join(f"- {t}" for t in existing_titles)
            existing_section = f"\n【既存要因（これらと同じ意味の要因は出力しないこと）】\n{lines}\n"

        return f"""あなたはFTA（Fault Tree Analysis：故障の木解析）の専門家です。
以下の「親要因」の直接原因となる子要因を原則{factor_count}件、日本語で出力してください。
必ず複数件生成してください（1件のみで終了しないこと）。

【分析情報】
頂上事象: {top_event}
親要因: {parent_desc}
要因パス: {path_str}
{existing_section}
【子要因の品質要件（必ず守ること）】
- 親要因の「直接原因」のみを出す（間接原因・抽象概念・推測は禁止）
- 親要因よりも必ず具体化された内容にする（抽象度を上げない）
- 現場で「はい/いいえ」で確認できる粒度にする
- 親要因の言い換えや、語尾だけを変えた表現は禁止
- 同じ意味の要因を複数出すことは禁止

【nameに禁止する内容】
- 「原因」「要因」「問題」「不備」「障害」「エラー」「失敗」「その他」だけの名前
- 親要因と同じ名前、または語尾だけを変えた名前
- 単語1つだけの抽象的な名前（例：「不整合」「遅延」「不足」）
- 「〜が原因である」「〜が問題である」のように、確認観点がない表現

【良い要因名の例（具体的で確認可能な粒度）】
- 設定変更の反映漏れ
- 冗長構成の切替失敗
- 依存サービスの応答遅延
- リソース使用率の上限到達
- 認証・認可処理の失敗
- 名前解決の失敗
- バージョン差異による不整合
- 証明書・有効期限の管理漏れ
- 監視アラートの検知遅延
- 変更作業の影響確認不足

【参考観点（必要なものだけ使うこと）】
構成・設定 / ソフトウェア・バージョン / ハードウェア・リソース / ネットワーク・通信経路
認証・権限 / 名前解決 / 外部サービス・依存 / 監視・検知
運用手順・変更管理 / 復旧対応・判断 / ログ・調査 / キャパシティ・性能
冗長化・切替 / セキュリティ設定 / 証明書・期限管理

【出力形式（必ず守ること）】
- 必ず日本語で出力する（英語禁止）
- JSONオブジェクトのみ出力する（前置き・補足・説明文・Markdown禁止）
- nameは30文字以内を目安にする
- descriptionは現場で確認できる観点を80文字以内を目安に記述する
- confidence: "high"=直接原因の可能性が高い / "medium"=可能性あり / "low"=念のため確認

{{"factors": [
  {{"name": "設定変更の反映漏れ", "description": "直近の設定変更が全ノードに反映されているか変更履歴で確認する", "confidence": "high"}},
  {{"name": "冗長構成の切替失敗", "description": "フェイルオーバー発生時に切替が正常に完了したかログで確認する", "confidence": "medium"}}
]}}"""

    @staticmethod
    def _normalize_factors(parsed: object) -> list[GeneratedFactor]:
        """
        Normalize any JSON shape returned by Ollama into list[GeneratedFactor].

        Accepted shapes
        ---------------
        A. {"factors": [{"title": ..., "description": ..., ...}, ...]}  (ideal)
        B. [{"title": ..., "description": ..., ...}, ...]               (bare list[dict])
        C. ["文字列1", "文字列2", ...]                                   (list[str] - rescue)
        D. dict with any list-valued key other than "factors"            (fallback search)

        Raises RuntimeError with a user-visible message for unsupported shapes.
        """
        # --- Step 1: unwrap dict to get the inner list ---
        if isinstance(parsed, dict):
            priority_keys = ("factors", "results", "items", "data")
            factors_raw: Optional[list] = None
            for key in priority_keys:
                if key in parsed and isinstance(parsed[key], list):
                    factors_raw = parsed[key]
                    break
            if factors_raw is None:
                for v in parsed.values():
                    if isinstance(v, list):
                        factors_raw = v
                        break
            if factors_raw is None:
                logger.error(
                    "Ollama returned a JSON object but no list value found: %s",
                    str(parsed)[:300],
                )
                raise RuntimeError(
                    "OllamaがJSONオブジェクトを返しましたが、配列（factors等）が見つかりません。\n"
                    "プロンプトまたはモデルを確認してください。"
                )
            parsed = factors_raw

        if not isinstance(parsed, list):
            raise RuntimeError(
                f"Ollamaの出力が配列でもオブジェクトでもありません: {type(parsed).__name__}"
            )

        # --- Step 2: convert each element ---
        _CONFIDENCE_LABEL = {"high": "可能性高", "medium": "可能性あり", "low": "念のため確認"}

        normalized: list[GeneratedFactor] = []
        for i, item in enumerate(parsed):
            if isinstance(item, dict):
                try:
                    if "name" in item and "title" not in item:
                        # New compact Ollama format: {name, description, confidence}
                        confidence = item.get("confidence", "medium")
                        normalized.append(GeneratedFactor(
                            title=item["name"].strip(),
                            description=item.get("description", "").strip(),
                            rationale=f"AI信頼度: {_CONFIDENCE_LABEL.get(confidence, confidence)}",
                            check_points=[],
                        ))
                    else:
                        # Legacy full format: {title, description, rationale, check_points}
                        normalized.append(GeneratedFactor(**item))
                except (TypeError, ValueError) as e:
                    logger.error(
                        "Ollama factor[%d] validation error: %s | item: %s",
                        i, e, str(item)[:200],
                    )
                    raise RuntimeError(
                        f"OllamaのJSON要素[{i}]がGeneratedFactorの形式と一致しません: {e}\n"
                        "name / description / confidence（または title / description / rationale / check_points）が必要です。"
                    ) from e
            elif isinstance(item, str):
                # Rescue path: model returned plain strings instead of dicts
                if item.strip():
                    logger.warning(
                        "Ollama factor[%d] is a plain string; applying rescue defaults. title=%r",
                        i, item[:80],
                    )
                    normalized.append(
                        GeneratedFactor(
                            title=item.strip(),
                            description=OllamaProvider._STR_RESCUE_DESCRIPTION,
                            rationale=OllamaProvider._STR_RESCUE_RATIONALE,
                            check_points=list(OllamaProvider._STR_RESCUE_CHECK_POINTS),
                        )
                    )
            else:
                logger.error(
                    "Ollama factor[%d] is unexpected type: %s | value: %s",
                    i, type(item).__name__, str(item)[:100],
                )
                raise RuntimeError(
                    f"Ollama応答の要素[{i}]が想定外の型です: {type(item).__name__}\n"
                    "各要素は辞書（dict）または文字列（str）である必要があります。"
                )

        return normalized

    @staticmethod
    def _extract_factors(content: str) -> list[GeneratedFactor]:
        """
        Parse the raw LLM text content into list[GeneratedFactor].

        1. Strips markdown code fences (safety net even with format=json/schema).
        2. JSON-parses the result.
        3. Delegates shape normalization to _normalize_factors.
        """
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            inner = lines[1:] if len(lines) > 1 else lines
            if inner and inner[-1].strip() == "```":
                inner = inner[:-1]
            stripped = "\n".join(inner).strip()

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as e:
            snippet = stripped[:500]
            logger.error("Ollama JSON parse error: %s | raw content: %s", e, snippet)
            raise RuntimeError(
                f"OllamaのレスポンスをJSONとして解析できませんでした。\n"
                f"エラー: {e}\n"
                f"モデル出力（先頭500文字）: {snippet}"
            ) from e

        return OllamaProvider._normalize_factors(parsed)

    def generate_factors(
        self,
        analysis_title: str,
        top_event: str,
        target_level: int,
        parent_path: list[str],
        parent_factor: Optional[str],
        context: dict,
    ) -> list[GeneratedFactor]:
        prompt = self._build_prompt(analysis_title, top_event, target_level, parent_path, parent_factor, context)

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "あなたはFTA（Fault Tree Analysis：故障の木解析）分析の専門家です。"
                        "必ず日本語で回答してください。"
                        "指示に従い、指定されたJSONスキーマ形式のみで回答してください。"
                        "JSON以外の説明文・Markdown・コードブロックは一切出力しないでください。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "keep_alive": self.keep_alive,
            "format": OllamaProvider._FORMAT_SCHEMA,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
                "num_ctx": self.num_ctx,
            },
        }

        # Log the payload model name explicitly so operators can confirm
        # which model is actually being sent to Ollama (not just self.model).
        logger.info(
            "Ollama request | url=%s payload_model=%s timeout=%.0fs keep_alive=%s level=%d parent=%s",
            self.chat_url,
            payload["model"],
            self.timeout,
            self.keep_alive,
            target_level,
            parent_factor or "(top event)",
        )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(self.chat_url, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as e:
            logger.error(
                "Ollama timeout | url=%s payload_model=%s timeout=%.0fs level=%d parent=%s",
                self.chat_url,
                payload["model"],
                self.timeout,
                target_level,
                parent_factor or "(top event)",
            )
            raise RuntimeError(
                f"Ollamaがタイムアウトしました（{self.timeout:.0f}秒）。\n"
                f"モデル: {payload['model']} / URL: {self.chat_url}\n"
                "対処法: .env の OLLAMA_TIMEOUT_SECONDS を大きくするか、"
                "より軽量なモデル（例: llama3.2:3b）に変更してください。"
            ) from e
        except httpx.HTTPStatusError as e:
            logger.error(
                "Ollama HTTP error: status=%d payload_model=%s body=%s",
                e.response.status_code,
                payload["model"],
                e.response.text[:500],
            )
            raise RuntimeError(
                f"Ollama APIエラー: HTTPステータス {e.response.status_code} "
                f"(model={payload['model']})\n"
                f"{e.response.text[:300]}"
            ) from e
        except httpx.ConnectError as e:
            logger.error("Ollama connect error: %s", e)
            raise RuntimeError(
                f"Ollamaに接続できません ({self.base_url})。\n"
                "Ollamaが起動しているか確認してください。\n"
                "起動コマンド: ollama serve"
            ) from e
        except httpx.RequestError as e:
            logger.error(
                "Ollama request error: %s | payload_model=%s", e, payload["model"]
            )
            raise RuntimeError(f"Ollama 通信エラー: {e}") from e

        try:
            data = response.json()
            content: str = data["message"]["content"]
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(
                "Ollama response structure error: %s | body: %s", e, response.text[:500]
            )
            raise RuntimeError(f"Ollamaのレスポンス構造が想定外です: {e}") from e

        # Log Ollama eval metrics for performance analysis
        eval_count        = data.get("eval_count", 0)
        eval_dur_s        = data.get("eval_duration", 0) / 1e9
        total_dur_s       = data.get("total_duration", 0) / 1e9
        load_dur_s        = data.get("load_duration", 0) / 1e9
        prompt_tokens     = data.get("prompt_eval_count", 0)
        prompt_eval_dur_s = data.get("prompt_eval_duration", 0) / 1e9
        logger.info(
            "Ollama stats | model=%s level=%d parent=%r "
            "prompt_tokens=%d prompt_eval_time=%.1fs "
            "eval_tokens=%d eval_time=%.1fs "
            "load_time=%.1fs total_time=%.1fs content_len=%d",
            data.get("model", self.model), target_level, parent_factor or "(top event)",
            prompt_tokens, prompt_eval_dur_s,
            eval_count, eval_dur_s,
            load_dur_s, total_dur_s, len(content),
        )
        logger.debug("Ollama raw content | level=%d parent=%r len=%d:\n%s",
                     target_level, parent_factor or "(top event)", len(content), content)

        factors = self._extract_factors(content)
        raw_count = len(factors)

        # Quality filter: remove abstract, duplicate, or trivially bad factors
        factors, excluded = filter_generated_factors(factors, parent_factor)
        if excluded:
            for title, reason in excluded:
                logger.info(
                    "Ollama factor excluded | level=%d parent=%r title=%r reason=%s",
                    target_level, parent_factor or "(top event)", title, reason,
                )

        factor_count = int(context.get("factor_count", 0))
        logger.info(
            "Ollama generation | model=%s level=%d parent=%r "
            "limit=%d raw=%d filtered_out=%d kept=%d",
            payload["model"], target_level, parent_factor or "(top event)",
            factor_count, raw_count, len(excluded), len(factors),
        )

        # Truncate to requested count after filtering (AI may return more than requested)
        if factor_count > 0 and len(factors) > factor_count:
            logger.info(
                "Ollama truncating %d kept factors to limit=%d",
                len(factors), factor_count,
            )
            factors = factors[:factor_count]

        return factors


class HttpCopilotProvider(AIProvider):
    """
    HTTP-based provider for Copilot Studio / Power Automate / Azure Function / API Management.

    Required environment variables:
        AI_PROVIDER=http_copilot
        COPILOT_FACTOR_API_URL=https://<your-endpoint>/api/generate-factors
        COPILOT_FACTOR_API_KEY=<optional-api-key>

    Expected POST body:
        {
            "analysis_title": str,
            "top_event": str,
            "target_level": int,
            "parent_path": list[str],
            "parent_factor": str | null,
            "context": dict
        }

    Expected response:
        [{"title": ..., "description": ..., "rationale": ..., "check_points": [...]}]
    """

    def __init__(self):
        self.api_url = os.environ.get("COPILOT_FACTOR_API_URL", "")
        self.api_key = os.environ.get("COPILOT_FACTOR_API_KEY", "")

        if not self.api_url:
            raise ValueError("HttpCopilotProvider requires COPILOT_FACTOR_API_URL")

    def generate_factors(
        self,
        analysis_title: str,
        top_event: str,
        target_level: int,
        parent_path: list[str],
        parent_factor: Optional[str],
        context: dict,
    ) -> list[GeneratedFactor]:
        payload = {
            "analysis_title": analysis_title,
            "top_event": top_event,
            "target_level": target_level,
            "parent_path": parent_path,
            "parent_factor": parent_factor,
            "context": context,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(self.api_url, json=payload, headers=headers)
                response.raise_for_status()
                factors_data = response.json()
                return [GeneratedFactor(**f) for f in factors_data]
        except httpx.HTTPStatusError as e:
            logger.error(f"HttpCopilot HTTP error: {e.response.status_code} {e.response.text}")
            raise RuntimeError(f"Copilot APIエラー: HTTPステータス {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error(f"HttpCopilot request error: {e}")
            raise RuntimeError(f"Copilot 通信エラー: {e}") from e
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"HttpCopilot response parse error: {e}")
            raise RuntimeError(f"Copilot レスポンスのパースに失敗しました: {e}") from e


def get_ai_provider() -> AIProvider:
    """Factory function: selects AI provider based on AI_PROVIDER environment variable."""
    provider_name = os.environ.get("AI_PROVIDER", "mock").lower()

    if provider_name == "ollama":
        provider = OllamaProvider()
        logger.info(
            "AI provider: OllamaProvider | base_url=%s model=%s",
            provider.base_url,
            provider.model,
        )
        return provider
    elif provider_name == "azure_openai":
        try:
            return AzureOpenAIProvider()
        except ValueError as e:
            logger.warning(f"AzureOpenAIProvider init failed: {e}. Falling back to MockAIProvider.")
            return MockAIProvider()
    elif provider_name == "http_copilot":
        try:
            return HttpCopilotProvider()
        except ValueError as e:
            logger.warning(f"HttpCopilotProvider init failed: {e}. Falling back to MockAIProvider.")
            return MockAIProvider()
    else:
        logger.info("AI provider: MockAIProvider")
        return MockAIProvider()
