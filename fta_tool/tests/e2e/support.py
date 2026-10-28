"""Helpers for the real-browser tests.

Importable without the development dependencies: when Playwright is not
installed the E2E tests are skipped (or fail in the required run) by
tests/conftest.py instead of breaking collection.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import socket
import sqlite3
import subprocess
import sys
import time
from typing import Optional

import httpx

from tests.e2e.acceptance import VIEWPORT_EXACT, VIEWPORT_REFUSED, VIEWPORT_TOLERATED, css_px

try:  # development dependency (requirements-dev.txt)
    from playwright.sync_api import expect
except ImportError:  # pragma: no cover - the tests are skipped in this case
    expect = None

FTA_TOOL_DIR = pathlib.Path(__file__).resolve().parents[2]


class E2EServer:
    """The app under test, started by tests/e2e/stub_server.py."""

    def __init__(self, url: str, workdir: pathlib.Path, process: subprocess.Popen, log_path: pathlib.Path):
        self.url = url
        self.workdir = workdir
        self.process = process
        self.log_path = log_path
        self.db_path = workdir / "fta_tool.db"
        # The test server is on this PC: never through a proxy of the
        # environment or (on Windows) the system settings (trust_env=False).
        # A new connection for every request (no keep-alive): uvicorn closes
        # an idle connection after 5 s, and a request sent on it just then is
        # lost ("Server disconnected without sending a response"; seen once
        # in 2,629 tests of PR-7's run at every size, test data being made).
        self.http = httpx.Client(base_url=url, timeout=30, follow_redirects=False, trust_env=False,
                                 limits=httpx.Limits(max_keepalive_connections=0))

    # ----- lifecycle -----------------------------------------------------
    def reset(self) -> None:
        """Empty database, default stub mode, empty logs (before every test)."""
        with self._db() as conn:
            conn.execute("DELETE FROM nodes")
            conn.execute("DELETE FROM analyses")
        for name in ("stub_control.json", "stub_calls.jsonl", "violations.jsonl"):
            (self.workdir / name).unlink(missing_ok=True)

    def close(self) -> None:
        self.http.close()
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()

    # ----- stub control --------------------------------------------------
    def set_stub_mode(self, mode: str, delay_seconds: Optional[float] = None) -> None:
        data = {"mode": mode}
        if delay_seconds is not None:
            data["delay_seconds"] = delay_seconds
        (self.workdir / "stub_control.json").write_text(json.dumps(data), encoding="utf-8")

    def _jsonl(self, name: str) -> list[dict]:
        path = self.workdir / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def stub_calls(self) -> list[dict]:
        return self._jsonl("stub_calls.jsonl")

    def violations(self) -> list[dict]:
        return self._jsonl("violations.jsonl")

    # ----- data through the existing API ---------------------------------
    def create_analysis(self, title: str, top_event: str = "", system_context: str = "",
                        incident_context: str = "", demo_points: str = "") -> int:
        response = self.http.post("/analyses", data={
            "title": title,
            "top_event": top_event,
            "system_context": system_context,
            "incident_context": incident_context,
            "demo_points": demo_points,
        })
        assert response.status_code == 303, response.text
        return int(response.headers["location"].rstrip("/").rsplit("/", 1)[1])

    def add_level1(self, analysis_id: int, title: str, description: str = "") -> int:
        response = self.http.post(f"/analyses/{analysis_id}/nodes/add-level1",
                                  json={"title": title, "description": description})
        assert response.status_code == 200, response.text
        return response.json()["node_id"]

    def add_child(self, parent_id: int, title: str, description: str = "") -> int:
        response = self.http.post(f"/nodes/{parent_id}/children", json={"title": title, "description": description})
        assert response.status_code == 200, response.text
        return response.json()["node_id"]

    def update_node(self, node_id: int, **fields) -> None:
        response = self.http.post(f"/nodes/{node_id}/update", json=fields)
        assert response.status_code == 200, response.text

    def get_node(self, node_id: int) -> dict:
        response = self.http.get(f"/nodes/{node_id}")
        assert response.status_code == 200, response.text
        return response.json()

    def rename(self, analysis_id: int, title: str) -> None:
        response = self.http.post(f"/analyses/{analysis_id}/title", json={"title": title})
        assert response.status_code == 200, response.text

    def delete_node(self, node_id: int) -> None:
        response = self.http.post(f"/nodes/{node_id}/delete")
        assert response.status_code == 200, response.text

    def delete_analysis(self, analysis_id: int) -> None:
        response = self.http.post(f"/analyses/{analysis_id}/delete")
        assert response.status_code == 200, response.text

    def generate(self, analysis_id: int, level: int, **body) -> dict:
        response = self.http.post(f"/analyses/{analysis_id}/generate/level/{level}", json=body)
        assert response.status_code == 200, response.text
        return response.json()

    def export(self, analysis_id: int, fmt: str) -> bytes:
        response = self.http.get(f"/analyses/{analysis_id}/export/{fmt}")
        assert response.status_code == 200, response.text
        return response.content

    # ----- direct reads for assertions -----------------------------------
    def _db(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.isolation_level = None  # autocommit
        return _Closing(conn)

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        with self._db() as conn:
            return conn.execute(sql, params).fetchall()

    def analysis(self, analysis_id: int) -> Optional[dict]:
        rows = self.query(
            "SELECT id, title, top_event, analysis_context, updated_at FROM analyses WHERE id = ?", (analysis_id,))
        if not rows:
            return None
        keys = ("id", "title", "top_event", "analysis_context", "updated_at")
        return dict(zip(keys, rows[0]))

    def node_count(self, analysis_id: int) -> int:
        return self.query("SELECT COUNT(*) FROM nodes WHERE analysis_id = ?", (analysis_id,))[0][0]

    def set_updated_at(self, analysis_id: int, value: str) -> None:
        with self._db() as conn:
            conn.execute("UPDATE analyses SET updated_at = ? WHERE id = ?", (value, analysis_id))

    # ----- data the API cannot make (the test database only) -------------
    def insert_node(self, analysis_id: int, level: int, parent_id: Optional[int] = None, *,
                    title: Optional[str] = None, judgement: str = "unknown", description: str = "",
                    ai_generated: bool = False, warning: str = "", memo: str = "") -> int:
        """A factor written directly, e.g. with a parent link the API would
        never create (J-25 checks). Only ever the temporary test database."""
        import datetime as _dt

        now = _dt.datetime.utcnow().isoformat(sep=" ")
        with self._db() as conn:
            cursor = conn.execute(
                "INSERT INTO nodes (analysis_id, parent_id, level, title, description, ai_generated,"
                " user_judgement, direct_cause_status, direct_cause_comment, evidence, prevention_idea,"
                " display_order, memo, warning_flags, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'unknown', '', '', '', 0, ?, ?, ?, ?)",
                (analysis_id, parent_id, level, title or f"要因（階層{level}）", description,
                 1 if ai_generated else 0, judgement, memo, warning, now, now),
            )
            return cursor.lastrowid

    def set_analysis_fields(self, analysis_id: int, **fields) -> None:
        """Values written directly (e.g. CRLF or surrounding spaces the screen
        would never send, PR-4 E-E10). Only ever the temporary test database."""
        allowed = {"title", "top_event", "analysis_context"}
        assert set(fields) <= allowed, fields
        with self._db() as conn:
            for key, value in fields.items():
                conn.execute(f"UPDATE analyses SET {key} = ? WHERE id = ?", (value, analysis_id))

    def set_parent(self, node_id: int, parent_id: Optional[int]) -> None:
        with self._db() as conn:
            conn.execute("UPDATE nodes SET parent_id = ? WHERE id = ?", (parent_id, node_id))

    def set_warning(self, node_id: int, text: str) -> None:
        with self._db() as conn:
            conn.execute("UPDATE nodes SET warning_flags = ? WHERE id = ?", (text, node_id))

    def node_ids(self, analysis_id: Optional[int] = None) -> set[int]:
        if analysis_id is None:
            return {row[0] for row in self.query("SELECT id FROM nodes")}
        return {row[0] for row in self.query("SELECT id FROM nodes WHERE analysis_id = ?", (analysis_id,))}

    def judgement(self, node_id: int) -> Optional[str]:
        rows = self.query("SELECT user_judgement FROM nodes WHERE id = ?", (node_id,))
        return rows[0][0] if rows else None

    def set_control(self, **fields) -> None:
        """Merge settings into stub_control.json (stub mode, fault injection)."""
        path = self.workdir / "stub_control.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data.update(fields)
        path.write_text(json.dumps(data), encoding="utf-8")


class _Closing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, *exc) -> None:
        self.conn.close()


# pytest-playwright 0.7.1 keeps the screenshot and trace of a failed test in
# <--output>/<the whole node id, slugified>/ (up to 122 characters here). Below
# a deep --output on Windows that passes MAX_PATH (260) and the evidence is
# lost, so there the folder is the test's name, shortened, with a hash of the
# node id (still one folder per test).
WINDOWS_EVIDENCE_NAME = 60


def evidence_folder_name(nodeid: str, name: str, slugify, windows: bool) -> str:
    if not windows:  # pytest-playwright's own name (its _truncate_file_name)
        full = slugify(nodeid)
        if len(full) < 256:
            return full
        return f"{full[:100]}-{hashlib.sha256(full.encode()).hexdigest()[:7]}-{full[-100:]}"
    digest = hashlib.sha256(nodeid.encode("utf-8")).hexdigest()[:7]
    return f"{slugify(name)[:WINDOWS_EVIDENCE_NAME]}-{digest}"


# A failed test's page, taken by the page fixture (tests/e2e/conftest.py)
# into the same folder before pytest-playwright takes its own
# (test-failed-1.png): pytest-playwright drops the error when its screenshot
# cannot be taken, this one is recorded either way (tests/e2e/acceptance.py).
FAILURE_SCREENSHOT = "page-at-failure.png"
SCREENSHOT_TIMEOUT_MS = 5000  # as pytest-playwright's


def save_screenshot(page, path: pathlib.Path, timeout_ms: int = SCREENSHOT_TIMEOUT_MS) -> dict:
    """The page as it is: {"file", "bytes"}, or {"file": None, "reason"}."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), timeout=timeout_ms)
    except Exception as error:  # noqa: BLE001 - the reason is what is recorded
        text = str(error).strip()
        detail = text.splitlines()[0][:300] if text else ""
        return {"file": None, "reason": f"{type(error).__name__}: {detail}" if detail else type(error).__name__}
    if not path.exists():
        return {"file": None, "reason": "保存の呼び出しは終わったが、ファイルがない"}
    return {"file": path.name, "bytes": path.stat().st_size}


# Ports of the user's own servers (the manual check uses 8001 and 8002,
# uvicorn's default is 8000): a test server never takes one of them.
RESERVED_PORTS = frozenset({8000, 8001, 8002})


def free_port() -> int:
    while True:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port not in RESERVED_PORTS:
            return port


def start_server(workdir: pathlib.Path, port: int, extra_env: Optional[dict[str, str]] = None) -> E2EServer:
    """Start the app for the tests; `extra_env` changes its settings (e.g.
    FTA_SAMPLE_SCENARIOS_FILE for a server without sample scenarios)."""
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(FTA_TOOL_DIR), env.get("PYTHONPATH", "")]))
    env["FTA_E2E_WORKDIR"] = str(workdir)
    env["FTA_E2E_STUB_MODE"] = "create"
    env.update(extra_env or {})
    log_path = workdir / "server.log"
    log = log_path.open("wb")
    process = subprocess.Popen(
        [sys.executable, "-m", "tests.e2e.stub_server", "--port", str(port)],
        cwd=workdir, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 60
    while True:
        if process.poll() is not None:
            log.close()
            raise RuntimeError(f"E2E server exited early:\n{log_path.read_text(encoding='utf-8', errors='replace')}")
        try:
            if httpx.get(url + "/", timeout=2, trust_env=False).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            process.kill()
            log.close()
            raise RuntimeError(f"E2E server did not start:\n{log_path.read_text(encoding='utf-8', errors='replace')}")
        time.sleep(0.2)
    return E2EServer(url, workdir, process, log_path)


# No console error is let through. Until PR-7 the browser's own 404 for
# /favicon.ico of the test's server was (the user's decision of 2026-10-03,
# a narrowed check for a known issue); PR-7 gave every screen its icon
# (/static/favicon.svg, declared in base.html, so the browser does not ask
# for /favicon.ico) and removed the exception: a 404 of the icon, of
# /favicon.ico or of anything else fails the test as any console error
# (tests/test_e2e_infrastructure.py, tests/e2e/test_console_check.py).
FAVICON_URL = "/static/favicon.svg"
NOT_FOUND_TEXT = "Failed to load resource: the server responded with a status of 404 (Not Found)"


class PageWatcher:
    """Collects what must not happen on a page during a test: console errors,
    uncaught page errors and requests to another origin."""

    START = (0, 0, 0)

    def __init__(self, page, origin: str):
        self.origin = origin.rstrip("/")
        self.console_errors: list[str] = []
        self.console_error_urls: list[str] = []  # where each came from (e.g. the resource that failed)
        self.page_errors: list[str] = []
        self.requests: list[str] = []
        self.foreign_requests: list[str] = []
        self.dialogs: list[str] = []
        self._allowed: list[re.Pattern] = []
        page.on("console", self._on_console)
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        page.context.on("request", self._on_request)

    def _on_console(self, message) -> None:
        if message.type == "error":
            self.console_errors.append(message.text)
            self.console_error_urls.append((message.location or {}).get("url") or "")

    def _on_request(self, request) -> None:
        url = request.url
        self.requests.append(url)
        same_origin = url == self.origin or url.startswith(self.origin + "/")
        if not same_origin and not url.startswith(("data:", "blob:", "about:")):
            self.foreign_requests.append(url)

    def allow_console_error(self, pattern: str) -> None:
        """Expected console errors, e.g. the browser's log of a 500 the test forced."""
        self._allowed.append(re.compile(pattern))

    def mark(self) -> tuple[int, int, int]:
        """How far the page has been checked (for problems() of what came after)."""
        return (len(self.console_errors), len(self.page_errors), len(self.foreign_requests))

    def problems(self, since: tuple[int, int, int] = START,
                 until: Optional[tuple[int, int, int]] = None) -> list[str]:
        """What came between `since` and `until` (default: up to now) and must not."""
        console, page, foreign = since
        console_end, page_end, foreign_end = until or self.mark()
        unexpected = []
        for index in range(console, console_end):
            text, url = self.console_errors[index], self.console_error_urls[index]
            # The allowed patterns match the message only; its URL is shown, never matched.
            if not any(p.search(text) for p in self._allowed):
                unexpected.append(f"{text}（{url}）" if url else text)
        found = []
        if unexpected:
            found.append(f"コンソールのエラー: {unexpected}")
        if self.page_errors[page:page_end]:
            found.append(f"ページのエラー（例外）: {self.page_errors[page:page_end]}")
        if self.foreign_requests[foreign:foreign_end]:
            found.append(f"外部へのリクエスト: {self.foreign_requests[foreign:foreign_end]}")
        return found


def record_dialogs(page, action: str = "dismiss") -> list:
    """Record native dialogs (beforeunload, confirm) and answer them."""
    seen: list = []

    def handler(dialog) -> None:
        seen.append(dialog.type)
        if action == "accept":
            dialog.accept()
        else:
            dialog.dismiss()

    page.on("dialog", handler)
    return seen


# ----- The display area of PR3-LAYOUT ---------------------------------------------

# What the browser reports about its display area, in CSS px: the root's
# clientWidth x clientHeight (whole numbers, the quantity measured on the
# user's PC), innerWidth x innerHeight, devicePixelRatio, the visual viewport
# (fractional) and the page's scroll size. On about:blank (quirks mode) the
# root's client size is the display area as well.
VIEWPORT_METRICS = """() => {
  const root = document.documentElement, vv = window.visualViewport;
  return {
    client: [root.clientWidth, root.clientHeight],
    inner: [window.innerWidth, window.innerHeight],
    devicePixelRatio: window.devicePixelRatio,
    visualViewport: vv ? [vv.width, vv.height, vv.scale] : null,
    scroll: [root.scrollWidth, root.scrollHeight],
  };
}"""


def measure_viewport(page) -> dict:
    return page.evaluate(VIEWPORT_METRICS)


# Display-area sizes (CSS px) at which the edit page's layout changes, from
# its stylesheets (tokens.css, base.css, components.css, edit.css; their
# rules that depend on the display area are pinned by
# tests/test_e2e_infrastructure.py, so a changed or new one makes this list
# be revisited). Widths: 1280 (three panes from here, J-20; below it the
# structure navigation is folded and the inspector 340px wide) and 1024
# (below it the work area's content keeps its width at 1024px and scrolls
# sideways; PR-7, edit.css's two media queries); the pane columns
# clamp(240px, 17vw, 320px) and clamp(340px, 23vw, 440px) stop at 240/0.17,
# 320/0.17, 340/0.23 and 440/0.23; the notifications below 1280px,
# min(560px, 100vw - 340px - 32px), at 932; the dialogs,
# min(520px | 560px, 100vw - 32px), at 552 and 592; the menu panel (340px,
# at most 100vw - 16px) at 356. Heights: 700 (below it the notifications
# take at most 30vh and scroll, and the panes keep 30vh + 48px below their
# content; PR-7); otherwise the page is 100vh less the header and the
# dialogs' max-height depends on their content.
LAYOUT_BOUNDARIES = {
    "width": (356, 552, 592, 932, 1024, 1280, 240 / 0.17, 340 / 0.23, 320 / 0.17, 440 / 0.23),
    "height": (700,),
}


def judge_viewport(requested, before: Optional[dict], after: dict, allowed: int,
                   boundaries: dict = LAYOUT_BOUNDARIES) -> dict:
    """The display area PR3-LAYOUT checks the page against, and why.

    The measured clientWidth x clientHeight is the requested size: exact.
    Otherwise the difference is tolerated only where the case allows it
    (`allowed` CSS px; 0 for every case but chrome-1905x945, the user's
    instruction of 2026-10-06) and only when all of these hold; the checks
    are then made against the measured size:
    * the browser had the same size before the app was shown (about:blank),
      so the difference does not come from the page;
    * on each axis the measured size is the requested one or larger by at
      most `allowed` (a browser that cannot show the requested size exactly
      rounds its display area up; seen in Chromium with a display scale of
      1.25, where 1905 CSS px would be 2381.25 device px);
    * no size of `boundaries` lies between the requested and the measured
      sizes (the fractional visual viewport included), or on either.
    """
    req = tuple(requested)
    got = tuple(after["client"])
    if got == req:
        return {"size": got, "verdict": VIEWPORT_EXACT, "reason": ""}
    problems = []
    if not allowed:
        problems.append("この寸法では差を許容しない")
    else:
        if before is None:
            problems.append("アプリの表示前に測っていない")
        elif tuple(before["client"]) != got:
            problems.append(f"アプリの表示後に寸法が変わった（表示前 {before['client'][0]}×{before['client'][1]}）")
        for index, axis in enumerate(("width", "height")):
            name = "幅" if axis == "width" else "高さ"
            difference = got[index] - req[index]
            if not 0 <= difference <= allowed:
                problems.append(f"{name}の差 {difference:+d} が許容（0〜+{allowed} CSS px）の外")
            sizes = [req[index], got[index]]
            for measured in (before, after):
                if measured is not None:
                    sizes.append(measured["client"][index])
                    if measured.get("visualViewport"):
                        sizes.append(measured["visualViewport"][index])
            low, high = min(sizes), max(sizes)
            crossed = [b for b in boundaries.get(axis, ()) if low <= b <= high]
            if crossed:
                problems.append(f"要求と実測の間にレイアウトの境界がある（{name} "
                                + "、".join(f"{css_px(float(b))} px" for b in crossed) + "）")
    if problems:
        return {"size": got, "verdict": VIEWPORT_REFUSED, "reason": "；".join(problems)}
    return {"size": got, "verdict": VIEWPORT_TOLERATED,
            "reason": (f"幅 {got[0] - req[0]:+d}・高さ {got[1] - req[1]:+d} CSS px。アプリの表示前（about:blank）から同じで、"
                       "レイアウトの境界を跨がない")}
