"""Tests for prompt_loader — YAML loading and template substitution."""

import pathlib
import textwrap

import pytest

import app.services.prompt_loader as pl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path: pathlib.Path, content: str) -> pathlib.Path:
    p = tmp_path / "prompts.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


VALID_YAML = """
factor_generation:
  system: |
    システムプロンプトです。
  user: |
    頂上事象: {top_event}
    親要因: {parent_factor}
    生成件数: {desired_count}
"""


# ---------------------------------------------------------------------------
# get_factor_generation_prompts
# ---------------------------------------------------------------------------

def test_load_valid_yaml(tmp_path, monkeypatch):
    """有効なYAMLを正常に読み込める。"""
    p = _write_yaml(tmp_path, VALID_YAML)
    monkeypatch.setenv("FTA_PROMPT_FILE", str(p))
    pl._cache = None  # reset cache

    prompts = pl.get_factor_generation_prompts()
    assert "system" in prompts
    assert "user" in prompts
    assert "システムプロンプト" in prompts["system"]


def test_load_caches_result(tmp_path, monkeypatch):
    """2回目の呼び出しはキャッシュを返す（ファイル再読み込みしない）。"""
    p = _write_yaml(tmp_path, VALID_YAML)
    monkeypatch.setenv("FTA_PROMPT_FILE", str(p))
    pl._cache = None

    first = pl.get_factor_generation_prompts()
    # overwrite file — cache should still return original
    p.write_text("factor_generation:\n  system: changed\n  user: changed\n", encoding="utf-8")
    second = pl.get_factor_generation_prompts()
    assert first is second  # same object from cache


def test_force_reload(tmp_path, monkeypatch):
    """force_reload=True でキャッシュを無効化して再読み込みする。"""
    p = _write_yaml(tmp_path, VALID_YAML)
    monkeypatch.setenv("FTA_PROMPT_FILE", str(p))
    pl._cache = None

    pl.get_factor_generation_prompts()
    p.write_text(
        "factor_generation:\n  system: new_system\n  user: new_user\n",
        encoding="utf-8",
    )
    reloaded = pl.get_factor_generation_prompts(force_reload=True)
    assert reloaded["system"] == "new_system"


def test_missing_file_raises(tmp_path, monkeypatch):
    """ファイルが存在しない場合は FileNotFoundError を送出する。"""
    monkeypatch.setenv("FTA_PROMPT_FILE", str(tmp_path / "nonexistent.yaml"))
    pl._cache = None

    with pytest.raises(FileNotFoundError, match="プロンプトファイルが見つかりません"):
        pl.get_factor_generation_prompts()


def test_invalid_yaml_raises(tmp_path, monkeypatch):
    """YAMLの構文エラーは ValueError を送出する。"""
    p = tmp_path / "bad.yaml"
    p.write_text("factor_generation:\n  system: [\ninvalid", encoding="utf-8")
    monkeypatch.setenv("FTA_PROMPT_FILE", str(p))
    pl._cache = None

    with pytest.raises(ValueError, match="YAML構文エラー"):
        pl.get_factor_generation_prompts()


def test_missing_factor_generation_key_raises(tmp_path, monkeypatch):
    """'factor_generation' キーがない場合は ValueError を送出する。"""
    p = _write_yaml(tmp_path, "other_section:\n  key: value\n")
    monkeypatch.setenv("FTA_PROMPT_FILE", str(p))
    pl._cache = None

    with pytest.raises(ValueError, match="factor_generation"):
        pl.get_factor_generation_prompts()


def test_missing_system_key_raises(tmp_path, monkeypatch):
    """'factor_generation.system' がない場合は ValueError を送出する。"""
    p = _write_yaml(tmp_path, "factor_generation:\n  user: テスト\n")
    monkeypatch.setenv("FTA_PROMPT_FILE", str(p))
    pl._cache = None

    with pytest.raises(ValueError, match="system"):
        pl.get_factor_generation_prompts()


def test_missing_user_key_raises(tmp_path, monkeypatch):
    """'factor_generation.user' がない場合は ValueError を送出する。"""
    p = _write_yaml(tmp_path, "factor_generation:\n  system: テスト\n")
    monkeypatch.setenv("FTA_PROMPT_FILE", str(p))
    pl._cache = None

    with pytest.raises(ValueError, match="user"):
        pl.get_factor_generation_prompts()


# ---------------------------------------------------------------------------
# apply_template
# ---------------------------------------------------------------------------

def test_apply_template_substitutes_known_vars():
    """既知の変数を正しく置換する。"""
    tpl = "頂上事象: {top_event}\n生成件数: {desired_count}件"
    result = pl.apply_template(tpl, {"top_event": "ログイン障害", "desired_count": 4})
    assert result == "頂上事象: ログイン障害\n生成件数: 4件"


def test_apply_template_leaves_json_untouched():
    """JSON形式の {"key": "value"} はテンプレート変数として扱わない。"""
    tpl = '{"factors": [{"name": "テスト", "confidence": "high"}]}'
    result = pl.apply_template(tpl, {"top_event": "事象"})
    assert result == tpl  # unchanged


def test_apply_template_leaves_unknown_vars_untouched():
    """テンプレートに存在しない変数は置換せずそのまま残す。"""
    tpl = "既知: {top_event} 未知: {unknown_var}"
    result = pl.apply_template(tpl, {"top_event": "事象"})
    assert "事象" in result
    assert "{unknown_var}" in result


def test_apply_template_existing_section_empty():
    """{existing_section} が空文字の場合、空文字に置換される。"""
    tpl = "前\n{existing_section}\n後"
    result = pl.apply_template(tpl, {"existing_section": ""})
    assert result == "前\n\n後"


def test_apply_template_existing_section_with_content():
    """{existing_section} に内容がある場合、そのまま展開される。"""
    section = "【既存要因】\n- 要因A\n"
    tpl = "前\n{existing_section}\n後"
    result = pl.apply_template(tpl, {"existing_section": section})
    assert "既存要因" in result
    assert "要因A" in result


def test_default_prompt_file_loads():
    """デフォルトの config/prompts.yaml が正常に読み込めることを確認する。"""
    pl._cache = None
    import os
    # Ensure no override that would point to a test file
    orig = os.environ.pop("FTA_PROMPT_FILE", None)
    try:
        prompts = pl.get_factor_generation_prompts()
        assert "system" in prompts
        assert "user" in prompts
        assert "{top_event}" in prompts["user"]
        assert "{desired_count}" in prompts["user"]
    finally:
        if orig is not None:
            os.environ["FTA_PROMPT_FILE"] = orig
        pl._cache = None
