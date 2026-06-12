"""
Load demo "sample scenario" definitions from a YAML configuration file.

Sample scenarios are an optional aid shown on the new-analysis screen. Each
scenario provides a top_event plus a system_context / incident_context /
demo_points triple that can be carried into the analysis as
``analysis_context`` and fed to the factor-generation prompts.

The file path is resolved from:
  1. FTA_SAMPLE_SCENARIOS_FILE environment variable (absolute or relative to fta_tool/)
  2. Default: fta_tool/config/sample_scenarios.yaml

Required YAML structure:
  scenarios:
    - id: ...
      category: ...
      title: ...
      top_event: ...
      system_context: ...
      incident_context: ...
      demo_points: ...
"""

import logging
import os
import pathlib
from typing import Optional

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = (
    "id", "category", "title", "top_event",
    "system_context", "incident_context", "demo_points",
)

_cache: Optional[list[dict]] = None


def _resolve_path() -> pathlib.Path:
    fta_tool_dir = pathlib.Path(__file__).parent.parent.parent  # …/fta_tool/
    env_val = os.environ.get("FTA_SAMPLE_SCENARIOS_FILE", "").strip()
    if env_val:
        p = pathlib.Path(env_val)
        return p if p.is_absolute() else fta_tool_dir / p
    return fta_tool_dir / "config" / "sample_scenarios.yaml"


def get_sample_scenarios(force_reload: bool = False) -> list[dict]:
    """
    Return the list of sample scenario dicts.

    Missing file or invalid YAML results in an empty list (logged as a
    warning) so the new-analysis screen degrades gracefully — the sample
    feature is optional and must never block normal hand-entered analysis.
    """
    global _cache
    if _cache is not None and not force_reload:
        return _cache

    path = _resolve_path()
    if not path.exists():
        logger.warning("サンプルシナリオファイルが見つかりません: %s", path)
        _cache = []
        return _cache

    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.warning("サンプルシナリオファイルの読み込みに失敗しました: %s | %s", path, e)
        _cache = []
        return _cache

    scenarios = (data or {}).get("scenarios") or []
    valid: list[dict] = []
    for s in scenarios:
        if not isinstance(s, dict) or not all(k in s for k in _REQUIRED_KEYS):
            logger.warning("サンプルシナリオの必須項目が不足しています: %r", s)
            continue
        valid.append(s)

    _cache = valid
    return _cache


def get_sample_scenario(scenario_id: str) -> Optional[dict]:
    for s in get_sample_scenarios():
        if s.get("id") == scenario_id:
            return s
    return None
