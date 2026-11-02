"""Run requests against the app in a process of its own, with a time limit
(S-11・S-12 regression tests on parent-link loops).

Before S-11・S-12 a request on looping data could fail to end (S-12: the
parent path of generation; measured on 254f826: no answer within 20 seconds)
— and a request that never ends inside the test process would stop the whole
test run (the TestClient's event-loop thread is joined when the process
exits). So the tests on loops make their data in a temporary SQLite file in
the test process, then send the requests from a child process started by
run(): if the child has not finished within the time limit it is killed and
the test fails with that reason, while the rest of the run goes on.

In the child (``python tests/guarded_requests.py <spec.json>``):

* the working directory is the test's temporary directory before the app
  is imported (app/database.py binds ./fta_tool.db there, never the user's
  database), and get_db is bound to the test's database file;
* the AI provider is a stub that appends every call to ``ai_calls.jsonl``
  (no real LLM, nothing outbound) and returns two factors named after the
  parent; the settings that change generation are pinned after the import
  (app.main loads fta_tool/.env with override=True): legacy path, no retry;
* each request is sent in order, and status and body are written to
  ``results.json``.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from typing import Optional

FTA_TOOL_DIR = pathlib.Path(__file__).resolve().parents[1]

# Seconds a child may take: the import of the app and a few requests take a
# few seconds; a request that does not end is cut here.
DEFAULT_TIMEOUT = 30

PINNED_ENV = {
    "ENABLE_LANGGRAPH_GENERATION_WORKFLOW": "false",
    "ENABLE_LANGGRAPH_QUALITY_GATE": "false",
    "FTA_RETRY_BELOW_MIN": "false",
    "FTA_RETRY_BELOW_TARGET": "false",
}


# Titles the stub returns (numbered per call): unlike any parent title, so
# the server's quality check keeps them.
STUB_TITLES = ("設定変更の手順が守られていない", "監視の閾値が適切でない")


class GuardedResult:
    def __init__(self, responses: list[dict], ai_calls: list[dict]):
        self.responses = responses
        self.ai_calls = ai_calls


def run(workdir: pathlib.Path, db_path: pathlib.Path, requests: list[dict], *,
        timeout: float = DEFAULT_TIMEOUT, env_overrides: Optional[dict] = None) -> GuardedResult:
    """Send `requests` ({"url": ..., "json": ...}, all POST) from a child
    process. Fails the calling test (pytest.fail) if the child does not end
    within `timeout` seconds or ends with an error. `env_overrides` are set
    in the child after PINNED_ENV (e.g. the LangGraph workflow on)."""
    import pytest

    workdir.mkdir(parents=True, exist_ok=True)
    spec = {
        "workdir": str(workdir),
        "db": str(db_path),
        "requests": requests,
        "out": str(workdir / "results.json"),
        "ai_calls": str(workdir / "ai_calls.jsonl"),
        "env": dict(env_overrides or {}),
    }
    spec_path = workdir / "spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ)
    env.pop("AI_PROVIDER", None)
    try:
        completed = subprocess.run(
            [sys.executable, str(pathlib.Path(__file__).resolve()), str(spec_path)],
            cwd=str(workdir), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{timeout} 秒以内に要求が終わりませんでした（子プロセスを停止）：{[r['url'] for r in requests]}")
    if completed.returncode != 0:
        pytest.fail(f"子プロセスが異常終了しました（終了コード {completed.returncode}）\n{completed.stderr[-4000:]}")
    responses = json.loads((workdir / "results.json").read_text(encoding="utf-8"))
    calls_path = workdir / "ai_calls.jsonl"
    calls = []
    if calls_path.exists():
        calls = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return GuardedResult(responses, calls)


def _child(spec_path: str) -> None:
    spec = json.loads(pathlib.Path(spec_path).read_text(encoding="utf-8"))
    os.chdir(spec["workdir"])
    sys.path.insert(0, str(FTA_TOOL_DIR))

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.main as main_module
    from app.database import get_db
    from app.services.ai_provider import GeneratedFactor

    os.environ.update(PINNED_ENV)
    os.environ.update(spec.get("env") or {})
    os.environ.pop("AI_PROVIDER", None)

    engine = create_engine(f"sqlite:///{spec['db']}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    calls_path = pathlib.Path(spec["ai_calls"])

    class RecordingStub:
        def generate_factors(self, **kwargs):
            with calls_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "target_level": kwargs.get("target_level"),
                    "parent_factor": kwargs.get("parent_factor"),
                    "parent_path": kwargs.get("parent_path"),
                }, ensure_ascii=False) + "\n")
            calls = len(calls_path.read_text(encoding="utf-8").splitlines())
            return [
                GeneratedFactor(title=f"{base}（{calls}）", description="スタブの説明", rationale="stub", check_points=[])
                for base in STUB_TITLES
            ]

    main_module.get_ai_provider = lambda: RecordingStub()
    main_module.app.dependency_overrides[get_db] = _override_get_db
    results: list[dict] = []
    with TestClient(main_module.app, raise_server_exceptions=False) as client:
        for request in spec["requests"]:
            response = client.post(request["url"], json=request.get("json"))
            try:
                body: Optional[object] = response.json()
            except ValueError:
                body = response.text
            results.append({"status": response.status_code, "body": body})
    main_module.app.dependency_overrides.clear()
    engine.dispose()
    pathlib.Path(spec["out"]).write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    _child(sys.argv[1])
