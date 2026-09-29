"""Helpers for the real-browser tests.

Importable without the development dependencies: when Playwright is not
installed the E2E tests are skipped (or fail in the required run) by
tests/conftest.py instead of breaking collection.
"""

from __future__ import annotations

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
        self.http = httpx.Client(base_url=url, timeout=30, follow_redirects=False)

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


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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
            if httpx.get(url + "/", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            process.kill()
            log.close()
            raise RuntimeError(f"E2E server did not start:\n{log_path.read_text(encoding='utf-8', errors='replace')}")
        time.sleep(0.2)
    return E2EServer(url, workdir, process, log_path)


class PageWatcher:
    """Collects what must not happen on a page during a test."""

    def __init__(self, page, origin: str):
        self.origin = origin.rstrip("/")
        self.console_errors: list[str] = []
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

    def _on_request(self, request) -> None:
        url = request.url
        self.requests.append(url)
        same_origin = url == self.origin or url.startswith(self.origin + "/")
        if not same_origin and not url.startswith(("data:", "blob:", "about:")):
            self.foreign_requests.append(url)

    def allow_console_error(self, pattern: str) -> None:
        """Expected console errors, e.g. the browser's log of a 500 the test forced."""
        self._allowed.append(re.compile(pattern))

    def problems(self) -> list[str]:
        unexpected = [text for text in self.console_errors if not any(p.search(text) for p in self._allowed)]
        found = []
        if unexpected:
            found.append(f"コンソールのエラー: {unexpected}")
        if self.page_errors:
            found.append(f"ページのエラー（例外）: {self.page_errors}")
        if self.foreign_requests:
            found.append(f"外部へのリクエスト: {self.foreign_requests}")
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
