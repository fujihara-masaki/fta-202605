import pytest
from app.services.ai_provider import MockAIProvider, OllamaProvider, GeneratedFactor


def test_mock_provider_returns_generated_factors():
    provider = MockAIProvider()
    factors = provider.generate_factors(
        analysis_title="テスト分析",
        top_event="〇〇システムでログイン障害が発生した",
        target_level=1,
        parent_path=[],
        parent_factor=None,
        context={},
    )
    assert isinstance(factors, list)
    assert len(factors) > 0
    for factor in factors:
        assert isinstance(factor, GeneratedFactor)
        assert factor.title
        assert factor.description
        assert factor.rationale
        assert isinstance(factor.check_points, list)


def test_mock_provider_level2():
    provider = MockAIProvider()
    factors = provider.generate_factors(
        analysis_title="テスト分析",
        top_event="障害発生",
        target_level=2,
        parent_path=["技術的要因"],
        parent_factor="技術的要因",
        context={},
    )
    assert len(factors) > 0


def test_mock_provider_level3():
    provider = MockAIProvider()
    factors = provider.generate_factors(
        analysis_title="テスト分析",
        top_event="障害発生",
        target_level=3,
        parent_path=["技術的要因", "設定・パラメータの問題"],
        parent_factor="設定・パラメータの問題",
        context={},
    )
    assert len(factors) > 0
    for f in factors:
        assert isinstance(f.check_points, list)
        assert len(f.check_points) > 0


# ===== OllamaProvider._extract_factors tests =====
# These tests exercise the JSON parsing logic without calling the actual Ollama API.

VALID_FACTOR_JSON = """[
  {
    "title": "認証基盤の問題",
    "description": "認証サーバに障害が発生した可能性がある。",
    "rationale": "ログイン失敗が集中して発生しているため。",
    "check_points": ["認証ログを確認する", "サーバ死活監視の結果を確認する"]
  },
  {
    "title": "ネットワーク障害",
    "description": "クライアントと認証サーバ間の通信経路に問題がある可能性がある。",
    "rationale": "特定のネットワークセグメントからのみ障害が報告されているため。",
    "check_points": ["pingで疎通確認する", "ファイアウォールのログを確認する"]
  }
]"""

VALID_FACTOR_OBJECT_WRAPPED = """{
  "factors": [
    {
      "title": "設定ミス",
      "description": "設定ファイルの誤りがある可能性がある。",
      "rationale": "直近のリリース後から障害が発生しているため。",
      "check_points": ["設定ファイルの差分を確認する"]
    }
  ]
}"""

VALID_FACTOR_MARKDOWN_FENCED = """```json
[
  {
    "title": "リソース不足",
    "description": "サーバのメモリが枯渇した可能性がある。",
    "rationale": "メモリ使用率が障害時刻に急上昇しているため。",
    "check_points": ["メモリ使用量のグラフを確認する", "OOMログを確認する"]
  }
]
```"""

INVALID_JSON = "これはJSONではありません。モデルが自然言語で回答してしまいました。"

VALID_JSON_WRONG_SCHEMA = """[{"name": "認証の問題", "detail": "詳細不明"}]"""

OBJECT_NO_LIST = """{"message": "エラーが発生しました", "code": 500}"""


def test_ollama_extract_bare_array():
    """正常なJSON配列をそのままパースできる。"""
    factors = OllamaProvider._extract_factors(VALID_FACTOR_JSON)
    assert len(factors) == 2
    assert factors[0].title == "認証基盤の問題"
    assert isinstance(factors[0].check_points, list)


def test_ollama_extract_object_wrapped():
    """モデルが {"factors": [...]} 形式で返した場合も正しく取り出せる。"""
    factors = OllamaProvider._extract_factors(VALID_FACTOR_OBJECT_WRAPPED)
    assert len(factors) == 1
    assert factors[0].title == "設定ミス"


def test_ollama_extract_markdown_fenced():
    """マークダウンのコードフェンスが付いていても正しくパースできる。"""
    factors = OllamaProvider._extract_factors(VALID_FACTOR_MARKDOWN_FENCED)
    assert len(factors) == 1
    assert factors[0].title == "リソース不足"


def test_ollama_extract_invalid_json_raises():
    """不正なJSONはRuntimeErrorを送出し、アプリを落とさない。"""
    with pytest.raises(RuntimeError) as exc_info:
        OllamaProvider._extract_factors(INVALID_JSON)
    assert "JSON" in str(exc_info.value)


def test_ollama_extract_wrong_schema_raises():
    """必須フィールドが欠けている場合はRuntimeErrorを送出する。"""
    with pytest.raises(RuntimeError) as exc_info:
        OllamaProvider._extract_factors(VALID_JSON_WRONG_SCHEMA)
    assert "GeneratedFactor" in str(exc_info.value) or "title" in str(exc_info.value)


def test_ollama_extract_object_no_list_raises():
    """リストを含まないオブジェクトはRuntimeErrorを送出する。"""
    with pytest.raises(RuntimeError) as exc_info:
        OllamaProvider._extract_factors(OBJECT_NO_LIST)
    assert "配列" in str(exc_info.value) or "list" in str(exc_info.value).lower()
