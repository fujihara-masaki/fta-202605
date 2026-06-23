import pytest
from app.services.ai_provider import (
    MockAIProvider, OllamaProvider, GeneratedFactor,
    filter_generated_factors,
)


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


# ===== OllamaProvider._normalize_factors tests =====
# These tests exercise parsing/normalization logic without calling the actual Ollama API.

# Shape A: ideal output — {"factors": [dict, ...]}
FACTORS_OBJECT_WRAPPED = {
    "factors": [
        {
            "title": "認証基盤の問題",
            "description": "認証サーバに障害が発生した可能性がある。",
            "rationale": "ログイン失敗が集中して発生しているため。",
            "check_points": ["認証ログを確認する", "サーバ死活監視の結果を確認する"],
        },
        {
            "title": "ネットワーク障害",
            "description": "クライアントと認証サーバ間の通信経路に問題がある可能性がある。",
            "rationale": "特定のネットワークセグメントからのみ障害が報告されているため。",
            "check_points": ["pingで疎通確認する", "ファイアウォールのログを確認する"],
        },
    ]
}

# Shape B: bare list[dict]
FACTORS_LIST_DICT = [
    {
        "title": "設定ミス",
        "description": "設定ファイルの誤りがある可能性がある。",
        "rationale": "直近のリリース後から障害が発生しているため。",
        "check_points": ["設定ファイルの差分を確認する"],
    }
]

# Shape C: list[str] — the case that triggered the original bug report
FACTORS_LIST_STR = [
    "ネットワーク経路の遅延状況の監視",
    "QoS設定の確認と最適化",
    "プロバイダーとの遅延に関する協議",
]

# Unsupported: dict with no list value
OBJECT_NO_LIST = {"message": "エラーが発生しました", "code": 500}

# Unsupported: wrong schema (missing both 'name' and 'title' — neither format matches)
LIST_WRONG_SCHEMA = [{"foo": "認証の問題", "detail": "詳細不明"}]

# Unsupported: list containing an unexpected type
LIST_WITH_INT = [42, 43]


# --- _normalize_factors unit tests ---

def test_normalize_factors_object_wrapped():
    """Shape A: {"factors": [dict, ...]} を正常にGeneratedFactorに変換できる。"""
    factors = OllamaProvider._normalize_factors(FACTORS_OBJECT_WRAPPED)
    assert len(factors) == 2
    assert factors[0].title == "認証基盤の問題"
    assert isinstance(factors[0].check_points, list)
    assert len(factors[0].check_points) > 0


def test_normalize_factors_list_dict():
    """Shape B: [dict, ...] を正常にGeneratedFactorに変換できる。"""
    factors = OllamaProvider._normalize_factors(FACTORS_LIST_DICT)
    assert len(factors) == 1
    assert factors[0].title == "設定ミス"
    assert isinstance(factors[0], GeneratedFactor)


def test_normalize_factors_list_str_rescue():
    """Shape C: list[str] を救済してGeneratedFactorに変換できる。

    title は元の文字列、description/rationale/check_points は規定値になること。
    """
    factors = OllamaProvider._normalize_factors(FACTORS_LIST_STR)
    assert len(factors) == 3
    assert factors[0].title == "ネットワーク経路の遅延状況の監視"
    assert factors[0].description == OllamaProvider._STR_RESCUE_DESCRIPTION
    assert factors[0].rationale == OllamaProvider._STR_RESCUE_RATIONALE
    assert factors[0].check_points == list(OllamaProvider._STR_RESCUE_CHECK_POINTS)


def test_normalize_factors_object_no_list_raises():
    """リストを含まないオブジェクトはRuntimeErrorを送出する。"""
    with pytest.raises(RuntimeError) as exc_info:
        OllamaProvider._normalize_factors(OBJECT_NO_LIST)
    msg = str(exc_info.value)
    assert "配列" in msg or "list" in msg.lower()


def test_normalize_factors_wrong_schema_raises():
    """必須フィールドが欠けている dict はRuntimeErrorを送出する。"""
    with pytest.raises(RuntimeError) as exc_info:
        OllamaProvider._normalize_factors(LIST_WRONG_SCHEMA)
    msg = str(exc_info.value)
    assert "GeneratedFactor" in msg or "title" in msg or "validation" in msg.lower()


def test_normalize_factors_unexpected_type_raises():
    """list[int] など想定外の型はRuntimeErrorを送出する。"""
    with pytest.raises(RuntimeError) as exc_info:
        OllamaProvider._normalize_factors(LIST_WITH_INT)
    assert "想定外" in str(exc_info.value) or "type" in str(exc_info.value).lower()


# --- _extract_factors integration tests (JSON string → parse → normalize) ---

def test_extract_factors_from_json_string_object_wrapped():
    """JSON文字列の {"factors": [...]} 形式をend-to-endで変換できる。"""
    import json
    content = json.dumps(FACTORS_OBJECT_WRAPPED)
    factors = OllamaProvider._extract_factors(content)
    assert len(factors) == 2
    assert factors[1].title == "ネットワーク障害"


def test_extract_factors_from_json_string_list_str():
    """JSON文字列の list[str] 形式をend-to-endで救済変換できる。"""
    import json
    content = json.dumps(FACTORS_LIST_STR)
    factors = OllamaProvider._extract_factors(content)
    assert len(factors) == 3
    assert factors[2].title == "プロバイダーとの遅延に関する協議"


def test_extract_factors_markdown_fenced():
    """マークダウンのコードフェンスが付いていても正しくパースできる。"""
    import json
    fenced = "```json\n" + json.dumps(FACTORS_LIST_DICT) + "\n```"
    factors = OllamaProvider._extract_factors(fenced)
    assert factors[0].title == "設定ミス"


def test_extract_factors_invalid_json_raises():
    """不正なJSONはRuntimeErrorを送出する。"""
    with pytest.raises(RuntimeError) as exc_info:
        OllamaProvider._extract_factors("これはJSONではありません。")
    assert "JSON" in str(exc_info.value)


# --- New compact format {name, description, confidence} tests ---

FACTORS_COMPACT_FORMAT = {
    "factors": [
        {"name": "認証サーバの障害", "description": "認証ログにエラーが記録されているか確認する", "confidence": "high"},
        {"name": "ネットワーク経路の問題", "description": "ping/tracerouteで疎通を確認する", "confidence": "medium"},
        {"name": "設定ファイルの誤り", "description": "直近の設定変更差分を確認する", "confidence": "low"},
    ]
}


def test_normalize_factors_compact_format():
    """新コンパクト形式 {name, description, confidence} を正常にGeneratedFactorに変換できる。"""
    factors = OllamaProvider._normalize_factors(FACTORS_COMPACT_FORMAT)
    assert len(factors) == 3
    assert factors[0].title == "認証サーバの障害"
    assert factors[0].description == "認証ログにエラーが記録されているか確認する"
    assert "可能性高" in factors[0].rationale
    assert isinstance(factors[0].check_points, list)

    assert factors[1].title == "ネットワーク経路の問題"
    assert "可能性あり" in factors[1].rationale

    assert factors[2].title == "設定ファイルの誤り"
    assert "念のため確認" in factors[2].rationale


def test_normalize_factors_compact_format_bare_list():
    """コンパクト形式がベアリストで返ってきても変換できる。"""
    factors = OllamaProvider._normalize_factors(FACTORS_COMPACT_FORMAT["factors"])
    assert len(factors) == 3
    assert factors[0].title == "認証サーバの障害"


def test_normalize_factors_compact_format_unknown_confidence():
    """confidenceが想定外の値でもRuntimeErrorにならずGeneratedFactorを返す。"""
    data = {"factors": [{"name": "テスト要因", "description": "説明", "confidence": "very_high"}]}
    factors = OllamaProvider._normalize_factors(data)
    assert len(factors) == 1
    assert "very_high" in factors[0].rationale


def test_extract_factors_compact_format_end_to_end():
    """JSON文字列のコンパクト形式をend-to-endで変換できる。"""
    import json
    content = json.dumps(FACTORS_COMPACT_FORMAT)
    factors = OllamaProvider._extract_factors(content)
    assert len(factors) == 3
    assert factors[2].title == "設定ファイルの誤り"


# --- factor_count truncation tests ---

def test_mock_provider_respects_factor_count():
    """MockAIProviderはcontextのfactor_countを尊重して件数を絞る。"""
    provider = MockAIProvider()
    factors = provider.generate_factors(
        analysis_title="テスト",
        top_event="障害発生",
        target_level=1,
        parent_path=[],
        parent_factor=None,
        context={"factor_count": 2},
    )
    assert len(factors) == 2


def test_mock_provider_factor_count_default():
    """factor_countが指定されない場合はデフォルト5件を返す。"""
    provider = MockAIProvider()
    factors = provider.generate_factors(
        analysis_title="テスト",
        top_event="障害発生",
        target_level=1,
        parent_path=[],
        parent_factor=None,
        context={},
    )
    assert len(factors) == 5


# --- filter_generated_factors tests ---

def _make_factor(title: str, description: str = "現場確認の観点を記述する") -> GeneratedFactor:
    return GeneratedFactor(title=title, description=description, rationale="テスト", check_points=[])


def test_filter_keeps_good_factors():
    """品質の良い要因はそのまま返す。"""
    factors = [
        _make_factor("設定変更の反映漏れ", "直近の設定変更が全ノードに反映されているか確認する"),
        _make_factor("認証処理の失敗", "認証ログにエラーが記録されているか確認する"),
    ]
    kept, excluded = filter_generated_factors(factors, "ネットワーク接続の問題")
    assert len(kept) == 2
    assert len(excluded) == 0


def test_filter_removes_generic_names():
    """汎用語だけのnameは除外する。"""
    factors = [
        _make_factor("問題", "詳細確認が必要"),
        _make_factor("エラー", "ログを確認する"),
        _make_factor("障害", "現場で確認する"),
    ]
    kept, excluded = filter_generated_factors(factors, "認証の失敗")
    assert len(kept) == 0
    assert len(excluded) == 3
    reasons = [r for _, r in excluded]
    assert all(r == "汎用語のみ" for r in reasons)


def test_filter_removes_parent_identical():
    """親要因と同一のnameは除外する。"""
    factors = [_make_factor("認証の失敗", "ログを確認する")]
    kept, excluded = filter_generated_factors(factors, "認証の失敗")
    assert len(kept) == 0
    assert excluded[0][1] == "親要因と同一"


def test_filter_removes_parent_resembling():
    """親要因に酷似した短いnameは除外する。"""
    factors = [_make_factor("認証", "ログを確認する")]
    kept, excluded = filter_generated_factors(factors, "認証の失敗")
    assert len(kept) == 0
    assert "親要因に酷似" in excluded[0][1]


def test_filter_removes_batch_duplicates():
    """バッチ内で同一nameが重複する場合、2件目以降を除外する。"""
    factors = [
        _make_factor("設定変更の反映漏れ", "変更履歴で確認する"),
        _make_factor("設定変更の反映漏れ", "別の説明でも同じタイトルは重複"),
    ]
    kept, excluded = filter_generated_factors(factors, "ネットワーク障害")
    assert len(kept) == 1
    assert excluded[0][1] == "バッチ内重複"


def test_filter_removes_empty_description():
    """descriptionが空の要因は除外する。"""
    factors = [_make_factor("設定変更の反映漏れ", "")]
    kept, excluded = filter_generated_factors(factors, "ネットワーク障害")
    assert len(kept) == 0
    assert excluded[0][1] == "description空"


def test_filter_removes_trivial_description():
    """短い説明で「が原因である」で終わる要因は除外する。"""
    factors = [_make_factor("設定変更の反映漏れ", "設定が原因である")]
    kept, excluded = filter_generated_factors(factors, "ネットワーク障害")
    assert len(kept) == 0
    assert "説明が不十分" in excluded[0][1]


def test_filter_no_parent_factor():
    """parent_factorがNone（一次要因生成）の場合も正常動作する。"""
    factors = [
        _make_factor("技術的要因", "システム・インフラに起因する技術的な問題を確認する"),
        _make_factor("問題"),  # should be filtered as generic
    ]
    kept, excluded = filter_generated_factors(factors, None)
    assert len(kept) == 1
    assert kept[0].title == "技術的要因"


# --- analysis_context (sample scenario) prompt section tests ---

def _ollama_prompt(context: dict) -> str:
    from app.services.prompt_loader import get_factor_generation_prompts
    provider = OllamaProvider()
    prompts = get_factor_generation_prompts()
    return provider._build_prompt(
        top_event="テストの頂上事象",
        target_level=1,
        parent_path=[],
        parent_factor=None,
        context=context,
        user_template=prompts["user"],
    )


def test_prompt_includes_analysis_context_when_present():
    prompt = _ollama_prompt({
        "factor_count": 3,
        "analysis_context": {
            "system_context": "システム構成テキスト",
            "incident_context": "障害状況テキスト",
            "demo_points": "デモ観点テキスト",
        },
    })
    assert "分析コンテキスト" in prompt
    assert "システム構成テキスト" in prompt
    assert "障害状況テキスト" in prompt
    assert "デモ観点テキスト" in prompt


def test_prompt_omits_analysis_context_when_absent():
    """サンプルを使わない通常分析では analysis_context_section は空文字。

    ルール10に「分析コンテキスト」という語が常に含まれるため、動的に挿入される
    セクション見出し【分析コンテキスト…】の有無で判定する。
    """
    prompt = _ollama_prompt({"factor_count": 3})
    assert "【分析コンテキスト" not in prompt
    prompt_empty_dict = _ollama_prompt({"factor_count": 3, "analysis_context": {}})
    assert "【分析コンテキスト" not in prompt_empty_dict
