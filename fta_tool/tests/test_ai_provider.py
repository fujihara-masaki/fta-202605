import pytest
from app.services.ai_provider import MockAIProvider, GeneratedFactor


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
