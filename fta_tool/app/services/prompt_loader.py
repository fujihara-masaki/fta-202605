"""
Load FTA factor generation prompts from a YAML configuration file.

The file path is resolved from:
  1. FTA_PROMPT_FILE environment variable (absolute or relative to fta_tool/)
  2. Default: fta_tool/config/prompts.yaml

Required YAML structure:
  factor_generation:
    system: |
      <system prompt text>
    user: |
      <user prompt template with {variable} placeholders>

Available template variables:
  {level}              - level name (一次要因, 二次要因, ...)
  {top_event}          - top event text
  {parent_factor}      - parent factor title
  {parent_description} - parent factor description (「（説明なし）」 when empty)
  {ancestor_factors}   - ancestor factor titles above the parent (「（なし）」 when empty)
  {path_str}           - full factor path string
  {desired_count}      - requested factor count
  {min_count}          - minimum expected count (desired_count - 1)
  {existing_section}   - formatted existing-titles section (empty string if none)
"""

import logging
import os
import pathlib
import re
from typing import Optional

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = ("system", "user")

# Variables that the template engine recognises and substitutes
TEMPLATE_VARIABLES = frozenset({
    "level", "top_event", "parent_factor", "parent_description",
    "ancestor_factors", "path_str",
    "desired_count", "min_count", "existing_section",
})

_cache: Optional[dict] = None


def _resolve_path() -> pathlib.Path:
    """Return the absolute path of the prompt YAML file."""
    fta_tool_dir = pathlib.Path(__file__).parent.parent.parent  # …/fta_tool/
    env_val = os.environ.get("FTA_PROMPT_FILE", "").strip()
    if env_val:
        p = pathlib.Path(env_val)
        return p if p.is_absolute() else fta_tool_dir / p
    return fta_tool_dir / "config" / "prompts.yaml"


def get_factor_generation_prompts(force_reload: bool = False) -> dict:
    """
    Load and return the ``factor_generation`` mapping from the prompt YAML.

    Results are cached in memory after the first successful load.
    Pass ``force_reload=True`` to re-read the file (e.g. for hot-reload testing).

    Raises
    ------
    RuntimeError
        If PyYAML is not installed, the file is missing, the YAML is invalid,
        or required keys are absent.
    """
    global _cache
    if _cache is not None and not force_reload:
        return _cache

    try:
        import yaml
    except ImportError:
        raise RuntimeError(
            "PyYAML がインストールされていません。pip install pyyaml を実行してください。"
        )

    path = _resolve_path()

    if not path.exists():
        logger.error(
            "プロンプトファイルが見つかりません: %s\n"
            "  FTA_PROMPT_FILE 環境変数またはデフォルトパス config/prompts.yaml を確認してください。\n"
            "  例: cp fta_tool/config/prompts.yaml fta_tool/config/prompts.yaml",
            path,
        )
        raise FileNotFoundError(
            f"プロンプトファイルが見つかりません: {path}\n"
            "FTA_PROMPT_FILE 環境変数またはデフォルトパス config/prompts.yaml を確認してください。"
        )

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error("プロンプトファイルのYAML構文エラー | file=%s | error=%s", path, e)
        raise ValueError(
            f"プロンプトファイルのYAML構文エラー ({path}):\n{e}"
        ) from e

    if not isinstance(data, dict) or "factor_generation" not in data:
        logger.error("プロンプトファイルに 'factor_generation' キーがありません: %s", path)
        raise ValueError(
            f"プロンプトファイルに必須キー 'factor_generation' がありません: {path}"
        )

    fg = data["factor_generation"]
    if not isinstance(fg, dict):
        logger.error("'factor_generation' はマッピングである必要があります: %s", path)
        raise ValueError(
            f"'factor_generation' はマッピング（辞書）形式で記述してください: {path}"
        )

    for key in _REQUIRED_KEYS:
        if key not in fg:
            logger.error(
                "プロンプトファイルに必須キー 'factor_generation.%s' がありません: %s",
                key, path,
            )
            raise ValueError(
                f"プロンプトファイルに必須キー 'factor_generation.{key}' がありません: {path}"
            )

    logger.info("プロンプトファイル読み込み完了: %s", path)
    _cache = fg
    return fg


def apply_template(template: str, variables: dict) -> str:
    """
    Substitute ``{variable}`` placeholders in *template* with values from *variables*.

    Only replaces patterns of the form ``{word}`` where ``word`` is a key in
    *variables*.  Patterns like ``{"name": ...}`` (JSON key syntax) are left
    untouched because the ``"`` after ``{`` breaks the ``\\{(\\w+)\\}`` match.

    Unknown ``{word}`` patterns that are also in TEMPLATE_VARIABLES are logged
    as warnings (likely typos in the YAML file).
    """
    def _replacer(m: re.Match) -> str:
        key = m.group(1)
        if key in variables:
            return str(variables[key])
        return m.group(0)  # leave unrecognised patterns untouched

    result = re.sub(r"\{(\w+)\}", _replacer, template)

    # Warn about remaining patterns that look like intended-but-missing variables
    for m in re.finditer(r"\{(\w+)\}", result):
        if m.group(1) in TEMPLATE_VARIABLES:
            logger.warning(
                "プロンプトテンプレートに未解決の変数が残っています: %s "
                "(YAML ファイルを確認してください)",
                m.group(0),
            )

    return result
