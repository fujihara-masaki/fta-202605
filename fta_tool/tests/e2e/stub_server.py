"""Run the real app for the browser tests, with a stub AI provider.

Started by tests/e2e/conftest.py as a subprocess:

    python -m tests.e2e.stub_server --port 8765

with the working directory set to a temporary directory given in
FTA_E2E_WORKDIR. It writes its process id to server.pid there, how far it got to
server-stages.jsonl (Python started with which standard streams, app
imported, listening, stopped, or the error; FTA_E2E_START_DELAY seconds
before it listens, for the tests of a server that does not start), and with
--stop-on-stdin-eof (tests/e2e/support.py) it ends by itself when its stdin
is closed (FTA_E2E_EXIT_DELAY seconds later than it would, for the tests of
that stop only). The app opens ./fta_tool.db relative to the working
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
  warning        (PR-6) like create, with titles longer than the quality
                 check allows (MAX_TITLE_LENGTH): created with a quality
                 warning (要確認)
  all_excluded   (PR-6) every candidate is dropped by the server's checks:
                 the parent's own title (a paraphrase of the parent) for
                 二次・三次; for 一次 the titles that already exist below the
                 top event (duplicates; needs at least one 一次要因)
Per parent (PR-6), "by_parent": {"<parent title>": "<mode>"} overrides the
mode for the requests naming that parent ("delay" waits delay_seconds and
creates), so one generation can mix results (a partial failure).
Every call is appended to stub_calls.jsonl.

Faults of the edit screen's parent-link checks (PR-3, J-25), per test from
the same file (the functions are wrapped, the data is never changed):
  "integrity": "lookup_error"   crud.get_cross_analysis_links fails, as if
                                the lookups could not be made
  "integrity_scope_limit": N    the deletion walk of
                                detail_view.build_detail_view gives up after
                                N factors, as if it could not be completed

Static files (PR-C, tests/e2e/test_static_cache.py and
tests/e2e/cache_manual_check.py only; unset, the app is served as it is):
  FTA_E2E_STATIC_DIR   serve /static from this copy instead of app/static
                       (the repository's files are never changed). Each
                       request reads the policy from static_control.json in
                       the working directory ({"policy": ...}):
                         app           the app's RevalidatedStaticFiles
                         baseline      Starlette's StaticFiles as served
                                       before PR-C (no Cache-Control,
                                       ETag of time and size)
                         nocache-only  plan option A: Cache-Control:
                                       no-cache with Starlette's ETag and
                                       its If-Modified-Since check
  FTA_E2E_STATIC_LOG   every HTTP request as a JSON line when its response
                       has ended: method, path (as received, and raw),
                       status, the cache headers of the request
                       (If-None-Match, If-Modified-Since, Cache-Control,
                       Pragma) and of the response (ETag, Cache-Control,
                       Content-Type, Last-Modified), the SHA-256 of the body
                       sent, the policy. No other header, no cookie.
  FTA_E2E_PROBE_LOG    POST /__fta_e2e/probe stores its JSON body (what a
                       page reports it actually used) as a JSON line. With
  FTA_E2E_PROBE_RUN    set as well, every HTML page gets a small inline
                       script before </body> that, at the page's load
                       event, reports this run's id, the path, the
                       navigation type, the CSS marker's computed value, the
                       module markers (globalThis.__ftaCacheProbe) and the
                       browser's version. It is part of the HTML, which is
                       fetched on every navigation, and never touches a
                       static file: a module cached before this run still
                       lets the page be seen (cache_manual_check.py).

Diagnosis only (tests/e2e/diagnose_navigation.py), when FTA_E2E_ACCESS_LOG
names a file: every request is written to it as JSON lines when it arrives,
when its response starts (status) and ends (bytes), or when the client went
away first. Method, path, the kind of client (from its User-Agent), its port
and times only: no query, no header, no body. The E2E tests do not set it.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import pathlib
import sys
import threading
import time
import traceback

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

    def _settings(self, parent_factor=None) -> tuple[str, float]:
        mode = os.environ.get("FTA_E2E_STUB_MODE", "create")
        delay = float(os.environ.get("FTA_E2E_STUB_DELAY_SECONDS", "2"))
        control = self.workdir / "stub_control.json"
        if control.exists():
            try:
                data = json.loads(control.read_text(encoding="utf-8"))
                mode = data.get("mode") or mode
                delay = float(data.get("delay_seconds", delay))
                by_parent = data.get("by_parent") or {}
                if parent_factor is not None and parent_factor in by_parent:
                    mode = by_parent[parent_factor]
            except (ValueError, OSError):
                pass
        return mode, delay

    def generate_factors(self, **kwargs):
        from app.services.ai_provider import GeneratedFactor

        mode, delay = self._settings(kwargs.get("parent_factor"))
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
        count = int(context.get("factor_count") or 2)
        if mode == "all_excluded":
            parent = kwargs.get("parent_factor")
            titles = [parent] * count if parent else list(context.get("existing_titles") or [])[:count]
            if not titles:
                raise RuntimeError("E2Eスタブ：全候補除外には既存の一次要因が必要です")
            return [GeneratedFactor(title=title, description="E2E用スタブ：除外される候補", rationale="E2E stub",
                                    check_points=[]) for title in titles]
        if mode not in ("create", "warning"):
            raise RuntimeError(f"E2Eスタブ：未対応のモードです（{mode}）")
        factors = []
        for _ in range(count):
            n = next(self._counter)
            base = TITLE_POOL[(n - 1) % len(TITLE_POOL)]
            suffix = "について運用手順と設定の両面から詳しく確認する必要がある要因" if mode == "warning" else ""
            factors.append(GeneratedFactor(
                title=f"{base}（{n}）{suffix}",
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


# ----- static files (PR-C, test only) -------------------------------------

STATIC_POLICIES = ("app", "baseline", "nocache-only")
STATIC_CONTROL = "static_control.json"
PROBE_PATH = "/__fta_e2e/probe"


def _static_classes():
    from starlette.staticfiles import StaticFiles

    from app.static_files import CACHE_CONTROL, RevalidatedStaticFiles

    class NoCacheOnlyStaticFiles(StaticFiles):
        """Plan option A alone: Cache-Control: no-cache, Starlette's ETag
        (time and size) and its check (If-Modified-Since even when the ETags
        differ). For the check that the tests can see what PR-C prevents."""

        def file_response(self, full_path, stat_result, scope, status_code=200):
            response = super().file_response(full_path, stat_result, scope, status_code)
            response.headers["cache-control"] = CACHE_CONTROL
            return response

    return {"app": RevalidatedStaticFiles, "baseline": StaticFiles, "nocache-only": NoCacheOnlyStaticFiles}


def read_static_policy(workdir: pathlib.Path) -> str:
    path = workdir / STATIC_CONTROL
    if not path.exists():
        return "app"
    policy = json.loads(path.read_text(encoding="utf-8")).get("policy", "app")
    if policy not in STATIC_POLICIES:
        raise RuntimeError(f"E2E: 未知の静的ファイルの配信方式です（{policy}）")
    return policy


class PolicyStaticFiles:
    """/static from a copy (FTA_E2E_STATIC_DIR), with the policy of
    static_control.json read for every request: one server, one origin, while
    a test switches from the old serving to the new one."""

    def __init__(self, directory: pathlib.Path, workdir: pathlib.Path):
        self.workdir = workdir
        self.apps = {name: cls(directory=str(directory)) for name, cls in _static_classes().items()}

    async def __call__(self, scope, receive, send):
        policy = read_static_policy(self.workdir)
        scope.setdefault("state", {})["fta_static_policy"] = policy
        await self.apps[policy](scope, receive, send)


def install_static_copy(main_module, directory: pathlib.Path, workdir: pathlib.Path) -> None:
    for route in main_module.app.routes:
        if getattr(route, "name", None) == "static":
            served = PolicyStaticFiles(directory, workdir)
            route._base_app = served
            route.app = served
            return
    raise RuntimeError("E2E: /static のマウントが見つかりません")


_LOGGED_REQUEST_HEADERS = ("if-none-match", "if-modified-since", "cache-control", "pragma")
_LOGGED_RESPONSE_HEADERS = ("etag", "cache-control", "content-type", "last-modified", "content-length")


class RequestLog:
    """ASGI wrapper: one JSON line per HTTP request when its response has
    ended (FTA_E2E_STATIC_LOG). It never changes a request or a response."""

    def __init__(self, app, path: pathlib.Path):
        self.app = app
        self.path = path
        self._numbers = itertools.count(1)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        agent = headers.get("user-agent", "")
        record = {
            "n": next(self._numbers),
            "method": scope.get("method"),
            "path": scope.get("path"),
            "raw_path": (scope.get("raw_path") or b"").decode("latin-1"),
            "client": ("python-httpx" if agent.startswith("python-httpx")
                       else "browser" if agent.startswith("Mozilla/") else "other" if agent else "none"),
            "request": {name: headers[name] for name in _LOGGED_REQUEST_HEADERS if name in headers},
        }
        digest = hashlib.sha256()
        state = {"bytes": 0}

        async def logged_send(message):
            if message["type"] == "http.response.start":
                response = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in message.get("headers") or []}
                record["status"] = message.get("status")
                record["response"] = {name: response[name] for name in _LOGGED_RESPONSE_HEADERS if name in response}
            elif message["type"] == "http.response.body":
                body = message.get("body") or b""
                digest.update(body)
                state["bytes"] += len(body)
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                record["body_bytes"] = state["bytes"]
                record["body_sha256"] = digest.hexdigest()
                record["policy"] = (scope.get("state") or {}).get("fta_static_policy")
                record["time"] = time.time()
                _append_jsonl(self.path, record)

        await self.app(scope, receive, logged_send)


PROBE_SCRIPT = """<script>(function () {
  var run = %s;
  addEventListener('load', function () {
    setTimeout(function () {
      var entry = performance.getEntriesByType('navigation')[0];
      var css = getComputedStyle(document.documentElement).getPropertyValue('--fta-cache-probe-components')
        .trim().replace(/^["']|["']$/g, '');
      var send = function (browser) {
        var report = { run: run, path: location.pathname, navigation: entry ? entry.type : null, css: css,
                       js: Object.assign({}, globalThis.__ftaCacheProbe || {}), browser: browser,
                       userAgent: navigator.userAgent, at: Date.now() };
        navigator.sendBeacon('%s', new Blob([JSON.stringify(report)], { type: 'application/json' }));
      };
      var data = navigator.userAgentData;
      if (data && data.getHighEntropyValues) {
        data.getHighEntropyValues(['fullVersionList']).then(function (v) { send(v.fullVersionList); },
                                                              function () { send(null); });
      } else {
        send(null);
      }
    }, 0);
  });
})();</script>"""


class ProbeEndpoint:
    """POST /__fta_e2e/probe (FTA_E2E_PROBE_LOG): a page's own report of the
    values it used. With a run id (FTA_E2E_PROBE_RUN), the HTML pages carry
    the inline script that sends it (cache_manual_check.py)."""

    def __init__(self, app, path: pathlib.Path, run: str = ""):
        self.app = app
        self.path = path
        self.script = (PROBE_SCRIPT % (json.dumps(run), PROBE_PATH)).encode("utf-8") if run else b""

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == PROBE_PATH and scope.get("method") == "POST":
            await self._store(receive, send)
            return
        if not self.script or scope.get("method") != "GET":
            await self.app(scope, receive, send)
            return
        start = {}
        body = []

        async def html_send(message):
            if message["type"] == "http.response.start":
                headers = dict((k.lower(), v) for k, v in message.get("headers") or [])
                if b"text/html" not in headers.get(b"content-type", b""):
                    start["pass"] = True
                    await send(message)
                    return
                start["message"] = message
                return
            if start.get("pass"):
                await send(message)
                return
            body.append(message.get("body") or b"")
            if message.get("more_body", False):
                return
            html = b"".join(body)
            at = html.rfind(b"</body>")
            html = html[:at] + self.script + html[at:] if at >= 0 else html + self.script
            first = start["message"]
            headers = [(k, v) for k, v in first.get("headers") or [] if k.lower() != b"content-length"]
            headers.append((b"content-length", str(len(html)).encode("latin-1")))
            await send({**first, "headers": headers})
            await send({"type": "http.response.body", "body": html, "more_body": False})

        await self.app(scope, receive, html_send)

    async def _store(self, receive, send):
        body = b""
        while True:
            message = await receive()
            body += message.get("body") or b""
            if not message.get("more_body") or len(body) > 65536:
                break
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            data = {"unreadable": body[:200].decode("latin-1")}
        _append_jsonl(self.path, {"time": time.time(), "data": data})
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


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
    parser.add_argument("--stop-on-stdin-eof", action="store_true",
                        help="end when stdin is closed (tests/e2e/support.py E2EServer.close)")
    args = parser.parse_args()

    workdir = _check_working_directory()
    # This process, which holds the database: the tests wait for it to be
    # gone (on Windows the process they started is a venv's launcher).
    (workdir / "server.pid").write_text(str(os.getpid()), encoding="utf-8")
    try:
        _serve(args, workdir)
    except BaseException as error:  # also SystemExit: recorded where the tests read it
        if not isinstance(error, SystemExit) or error.code not in (0, None):
            _stage(workdir, "error", error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
        raise
    _stage(workdir, "stopped")


def _stage(workdir: pathlib.Path, stage: str, **fields) -> None:
    """How far the server got, for start_server()'s error when it does not
    answer (server-stages.jsonl; a file, since its stdout and stderr may be
    missing: a child started on Windows without its standard handles)."""
    _append_jsonl(workdir / "server-stages.jsonl", {"time": time.time(), "stage": stage, "pid": os.getpid(), **fields})


def _serve(args, workdir: pathlib.Path) -> None:
    streams = {name: getattr(sys, name) is not None for name in ("stdin", "stdout", "stderr")}
    _stage(workdir, "python", ppid=os.getppid(), executable=sys.executable, version=sys.version.split()[0],
           streams=streams)
    # uvicorn's logging needs stdout and stderr (sys.stdout.isatty()), and
    # --stop-on-stdin-eof stdin: without them it fails with no word anywhere.
    missing = [name for name, there in streams.items() if not there and (name != "stdin" or args.stop_on_stdin_eof)]
    if missing:
        raise SystemExit(f"標準の入出力がない（起動した側が渡していない）：{', '.join(missing)}")

    import app.main as main_module  # loads fta_tool/.env (override=True)

    os.environ.update(PINNED_ENV)
    install_guards(main_module, workdir)
    install_integrity_faults(main_module, workdir)

    static_dir = os.environ.get("FTA_E2E_STATIC_DIR")
    if static_dir:  # PR-C's tests only
        install_static_copy(main_module, pathlib.Path(static_dir), workdir)

    import uvicorn

    app = main_module.app
    probe_log = os.environ.get("FTA_E2E_PROBE_LOG")
    if probe_log:  # PR-C's check with the user's browser only
        app = ProbeEndpoint(app, pathlib.Path(probe_log), os.environ.get("FTA_E2E_PROBE_RUN", ""))
    static_log = os.environ.get("FTA_E2E_STATIC_LOG")
    if static_log:  # PR-C's tests only
        app = RequestLog(app, pathlib.Path(static_log))
    access_log = os.environ.get("FTA_E2E_ACCESS_LOG")
    if access_log:  # the diagnosis only
        app = AccessLog(app, pathlib.Path(access_log))
    _stage(workdir, "app imported")
    delay = float(os.environ.get("FTA_E2E_START_DELAY", "0"))  # the tests of start_server() only: no answer
    if delay:
        time.sleep(delay)
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="warning",
                                           timeout_graceful_shutdown=SHUTDOWN_SECONDS))
    if args.stop_on_stdin_eof:
        threading.Thread(target=_stop_on_stdin_eof, args=(server,), daemon=True).start()
    threading.Thread(target=_record_listening, args=(server, workdir, args.port), daemon=True).start()
    server.run()
    from app.database import engine

    engine.dispose()  # the pooled connections of fta_tool.db, closed before the process ends
    delay = float(os.environ.get("FTA_E2E_EXIT_DELAY", "0"))  # the tests of close() only: a slow end
    if delay:
        time.sleep(delay)


def _record_listening(server, workdir: pathlib.Path, port: int) -> None:
    while not server.started and not server.should_exit:
        time.sleep(0.05)
    if server.started:
        _stage(workdir, "listening", port=port)


# Open requests are given this long when the app is asked to end.
SHUTDOWN_SECONDS = 5


def _stop_on_stdin_eof(server) -> None:
    """End the app (as uvicorn does on Ctrl+C) when stdin is closed: the
    tests close it to stop the server (E2EServer.close), also when their
    process ends without closing it."""
    try:
        while sys.stdin.buffer.read(4096):
            pass
    except (OSError, ValueError):
        pass
    server.should_exit = True


if __name__ == "__main__":
    main()
