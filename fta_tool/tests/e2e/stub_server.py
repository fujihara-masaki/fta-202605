"""Run the real app for the browser tests, with a stub AI provider.

Started by tests/e2e/conftest.py as a subprocess:

    python -m tests.e2e.stub_server --port 8765

with the working directory set to a temporary directory given in
FTA_E2E_WORKDIR. The app opens ./fta_tool.db relative to the working
directory, so the database is created there and the user's database is never
used (the launcher refuses to start inside the repository).

No real LLM is called (plan 8.0):
* app.main.get_ai_provider is replaced by StubProvider;
* the real provider factory and outbound HTTP through httpx are blocked and
  recorded in violations.jsonl, which the tests check after each test.

app.main loads fta_tool/.env with override=True when imported, so the
settings that change generation are pinned again afterwards (PINNED_ENV).

The stub's behaviour comes from FTA_E2E_STUB_MODE, or per test from
stub_control.json in the working directory ({"mode": ..., "delay_seconds": ...}):
  create         return `factor_count` new factors (default)
  delay          wait `delay_seconds`, then behave like create
  no_candidates  return no factor
  error          raise RuntimeError (the API answers success=false)
Every call is appended to stub_calls.jsonl.

Faults of the edit screen's parent-link checks (PR-3, J-25), per test from
the same file (the functions are wrapped, the data is never changed):
  "integrity": "lookup_error"   crud.get_cross_analysis_links fails, as if
                                the lookups could not be made
  "integrity_scope_limit": N    the deletion walk of
                                detail_view.build_detail_view gives up after
                                N factors, as if it could not be completed

Diagnosis only (tests/e2e/diagnose_navigation.py), when FTA_E2E_ACCESS_LOG
names a file: every request is written to it as JSON lines when it arrives,
when its response starts (status) and ends (bytes), or when the client went
away first. Method, path, the kind of client (from its User-Agent), its port
and times only: no query, no header, no body. The E2E tests do not set it.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import pathlib
import threading
import time

PINNED_ENV = {
    "AI_PROVIDER": "e2e-stub",
    "ENABLE_LANGGRAPH_GENERATION_WORKFLOW": "false",
    "ENABLE_LANGGRAPH_QUALITY_GATE": "false",
    "FTA_RETRY_BELOW_MIN": "false",
    "FTA_RETRY_BELOW_TARGET": "false",
    "FTA_PRIMARY_FACTOR_COUNT": "4",
    "FTA_SECONDARY_FACTOR_COUNT": "3",
    "FTA_TERTIARY_FACTOR_COUNT": "2",
    "FTA_ADDITIONAL_FACTOR_COUNT": "2",
}

TITLE_POOL = [
    "キャッシュ設定の不整合",
    "証明書更新手順の漏れ",
    "認証サーバーの応答遅延",
    "DB接続プールの枯渇",
    "設定変更レビューの不足",
    "監視閾値の設定誤り",
    "ロードバランサの振り分け設定誤り",
    "セッション管理の不具合",
    "デプロイ手順の誤り",
    "依存ライブラリの版の不整合",
    "ディスク容量の逼迫",
    "時刻同期のずれ",
]

_lock = threading.Lock()


def _append_jsonl(path: pathlib.Path, record: dict) -> None:
    line = json.dumps(record, ensure_ascii=False)
    with _lock, path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


class StubProvider:
    """Deterministic stand-in for the AI provider (never calls an LLM)."""

    def __init__(self, workdir: pathlib.Path):
        self.workdir = workdir
        self._counter = itertools.count(1)

    def _settings(self) -> tuple[str, float]:
        mode = os.environ.get("FTA_E2E_STUB_MODE", "create")
        delay = float(os.environ.get("FTA_E2E_STUB_DELAY_SECONDS", "2"))
        control = self.workdir / "stub_control.json"
        if control.exists():
            try:
                data = json.loads(control.read_text(encoding="utf-8"))
                mode = data.get("mode") or mode
                delay = float(data.get("delay_seconds", delay))
            except (ValueError, OSError):
                pass
        return mode, delay

    def generate_factors(self, **kwargs):
        from app.services.ai_provider import GeneratedFactor

        mode, delay = self._settings()
        context = kwargs.get("context") or {}
        _append_jsonl(self.workdir / "stub_calls.jsonl", {
            "mode": mode,
            "target_level": kwargs.get("target_level"),
            "parent_factor": kwargs.get("parent_factor"),
            "additional": bool(context.get("additional")),
            "factor_count": context.get("factor_count"),
            "analysis_id": context.get("analysis_id"),
        })
        if mode == "delay":
            time.sleep(delay)
            mode = "create"
        if mode == "error":
            raise RuntimeError("E2Eスタブ：生成に失敗しました（検証用）")
        if mode == "no_candidates":
            return []
        if mode != "create":
            raise RuntimeError(f"E2Eスタブ：未対応のモードです（{mode}）")
        count = int(context.get("factor_count") or 2)
        factors = []
        for _ in range(count):
            n = next(self._counter)
            base = TITLE_POOL[(n - 1) % len(TITLE_POOL)]
            factors.append(GeneratedFactor(
                title=f"{base}（{n}）",
                description=f"E2E用スタブが返した説明文です（{n}）。",
                rationale="E2E stub",
                check_points=[],
            ))
        return factors


def install_guards(main_module, workdir: pathlib.Path) -> None:
    """Route generation to the stub and block every other way out."""
    import httpx

    from app.services import ai_provider as provider_module

    violations = workdir / "violations.jsonl"

    def record(message: str) -> None:
        _append_jsonl(violations, {"message": message, "time": time.time()})

    stub = StubProvider(workdir)
    main_module.get_ai_provider = lambda: stub

    def forbidden_provider_factory(*args, **kwargs):
        record("実プロバイダの取得（app.services.ai_provider.get_ai_provider）が呼ばれました")
        raise RuntimeError("E2E: 実LLMプロバイダは使用できません")

    provider_module.get_ai_provider = forbidden_provider_factory

    def blocked_send(self, request, *args, **kwargs):
        record(f"外部への通信を遮断しました: {request.method} {request.url}")
        raise httpx.ConnectError("E2E: 外部への通信は禁止されています", request=request)

    async def blocked_async_send(self, request, *args, **kwargs):
        record(f"外部への通信を遮断しました: {request.method} {request.url}")
        raise httpx.ConnectError("E2E: 外部への通信は禁止されています", request=request)

    httpx.Client.send = blocked_send
    httpx.AsyncClient.send = blocked_async_send


def install_integrity_faults(main_module, workdir: pathlib.Path) -> None:
    """Wrap the lookups and the view of the edit screen for fault injection."""
    crud = main_module.crud
    detail_view = main_module.detail_view
    original_links = crud.get_cross_analysis_links
    original_build = detail_view.build_detail_view

    def control() -> dict:
        path = workdir / "stub_control.json"
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (ValueError, OSError):
            return {}

    def links(db, analysis_id):
        if control().get("integrity") == "lookup_error":
            raise RuntimeError("E2Eスタブ：親子関係の確認に必要な情報を取得できません（検証用）")
        return original_links(db, analysis_id)

    def build(analysis, nodes, links, **kwargs):
        limit = control().get("integrity_scope_limit")
        if limit is not None:
            kwargs["scope_limit"] = int(limit)
        return original_build(analysis, nodes, links, **kwargs)

    crud.get_cross_analysis_links = links
    detail_view.build_detail_view = build


class AccessLog:
    """ASGI wrapper of the app for the diagnosis (FTA_E2E_ACCESS_LOG): when a
    request arrives, when its response starts and ends, or that the client
    went away first. It never changes a request or a response."""

    def __init__(self, app, path: pathlib.Path):
        self.app = app
        self.path = path
        self._numbers = itertools.count(1)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        agent = dict(scope.get("headers") or []).get(b"user-agent", b"").decode("latin-1")
        record = {
            "n": next(self._numbers),
            "method": scope.get("method"),
            "path": scope.get("path"),
            "client": ("python-httpx" if agent.startswith("python-httpx")
                       else "browser" if agent.startswith("Mozilla/") else "other" if agent else "none"),
            "client_port": (scope.get("client") or (None, None))[1],
        }

        def write(event: str, **fields) -> None:
            _append_jsonl(self.path, {"event": event, "time": time.time(),
                                      "ms": round((time.monotonic() - started) * 1000, 1), **record, **fields})

        write("received")
        sent = {"bytes": 0, "ended": False}

        async def logged_send(message):
            if message["type"] == "http.response.start":
                write("response_start", status=message.get("status"))
            elif message["type"] == "http.response.body":
                sent["bytes"] += len(message.get("body") or b"")
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                sent["ended"] = True
                write("response_end", bytes=sent["bytes"])

        async def logged_receive():
            message = await receive()
            if message["type"] == "http.disconnect" and not sent["ended"]:
                write("client_disconnected")
            return message

        try:
            await self.app(scope, logged_receive, logged_send)
        except Exception as error:
            write("error", error=type(error).__name__)
            raise


def _check_working_directory() -> pathlib.Path:
    workdir = pathlib.Path(os.environ["FTA_E2E_WORKDIR"]).resolve()
    cwd = pathlib.Path.cwd().resolve()
    project = pathlib.Path(__file__).resolve().parents[2]  # fta_tool/
    if cwd != workdir:
        raise SystemExit(f"E2E server must run in FTA_E2E_WORKDIR ({workdir}), not {cwd}")
    if cwd == project or project in cwd.parents:
        raise SystemExit(f"E2E server refuses to use a database inside the project: {cwd}")
    return workdir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    workdir = _check_working_directory()

    import app.main as main_module  # loads fta_tool/.env (override=True)

    os.environ.update(PINNED_ENV)
    install_guards(main_module, workdir)
    install_integrity_faults(main_module, workdir)

    import uvicorn

    app = main_module.app
    access_log = os.environ.get("FTA_E2E_ACCESS_LOG")
    if access_log:  # the diagnosis only
        app = AccessLog(app, pathlib.Path(access_log))
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
