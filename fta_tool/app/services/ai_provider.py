"""
AI Provider abstraction layer for FTA factor generation.

Supported providers:
- MockAIProvider: Default, works without any external API
- AzureOpenAIProvider: Uses Azure OpenAI Chat Completions API
- HttpCopilotProvider: Uses a custom HTTP endpoint (for Copilot Studio, Power Automate, etc.)

Set AI_PROVIDER environment variable to select provider:
- (not set or "mock"): MockAIProvider
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
        base_factors = MOCK_FACTORS.get(target_level, MOCK_FACTORS[1])
        results = []
        parent_label = parent_factor or top_event

        for i, (title, desc, rationale) in enumerate(base_factors):
            factor_title = title
            factor_desc = f"「{parent_label}」に関連する{desc}"
            factor_rationale = rationale
            check_points = [
                f"{title}に関するログ・記録を確認する",
                f"直近の変更作業との関連を確認する",
                f"担当者へのヒアリングを実施する",
                f"監視ツールのアラート履歴を確認する",
            ]
            results.append(GeneratedFactor(
                title=factor_title,
                description=factor_desc,
                rationale=factor_rationale,
                check_points=check_points,
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

    if provider_name == "azure_openai":
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
        return MockAIProvider()
