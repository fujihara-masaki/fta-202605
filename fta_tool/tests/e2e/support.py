"""Helpers for the real-browser tests.

Importable without the development dependencies: when Playwright is not
installed the E2E tests are skipped (or fail in the required run) by
tests/conftest.py instead of breaking collection.
"""

from __future__ import annotations

import hashlib
import json
import os
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

    def __init__(self, url: str, workdir: pathlib.Path, process: subprocess.Popen, log_path: pathlib.Path,
                 log_file=None, server_pid: Optional[int] = None):
        self.url = url
        self.workdir = workdir
        self.process = process
        self.log_path = log_path
        # The process that runs the app (stub_server.py writes it to
        # server.pid). On Windows it is not `process`: a venv's
        # Scripts\python.exe is a launcher that runs the real python.exe as
        # its child, in a job that kills the child when the launcher ends
        # (CPython PC/launcher.c, run_child). Ending the launcher therefore
        # only starts the end of the app, which still holds fta_tool.db and
        # server.log for a moment: close() waits for this process itself.
        self.server_pid = server_pid
        self.stopped = ""  # how close() stopped the app (the tests record it)
        # Whether the app still ran when the process started for it had
        # ended (a launcher that ends before its child): close() then waited.
        self.app_outlived_process: Optional[bool] = None
        # This process's handle of server.log (the server's stdout): closed in
        # close(). Left open (until PR-7's fix of 2026-10-30) it kept Windows
        # from deleting the work folder (a file open without FILE_SHARE_DELETE
        # cannot be removed there; display_check.py's work stayed).
        self.log_file = log_file
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

    # How long the app may take to end by itself once asked (its open
    # requests are given SHUTDOWN_SECONDS by uvicorn, stub_server.py), and
    # how long a stopped process may take to be gone.
    STOP_SECONDS = 20
    GONE_SECONDS = 10

    def close(self) -> None:
        """Stop the server and release what this process holds of its
        folder (the HTTP client, the handle of server.log), so that the
        folder can be removed, also on Windows.

        The app is asked to end by closing its stdin (stub_server.py
        --stop-on-stdin-eof): it ends by itself, and a venv's launcher ends
        only after it. Only if it does not end in time is it stopped
        (terminate, then kill). Either way this returns only when the app's
        own process (server_pid) is gone; if it is not, it raises (a server
        left running is never let through)."""
        self.http.close()
        how = ""
        try:
            if self.process.stdin is not None and not self.process.stdin.closed:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=self.STOP_SECONDS)
                how = f"自分で終了（終了コード {self.process.returncode}）"
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=self.GONE_SECONDS)
                    how = f"{self.STOP_SECONDS} 秒で終わらず、止めた（terminate）"
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=self.GONE_SECONDS)
                    how = f"{self.STOP_SECONDS} 秒で終わらず、強制終了した（kill）"
            if self.server_pid is not None and self.server_pid != self.process.pid:
                self.app_outlived_process = not process_gone(self.server_pid, 0)
                if self.app_outlived_process:
                    how += "。起動したプロセスの終了時にアプリはまだ動作中"
                if not process_gone(self.server_pid, self.GONE_SECONDS):
                    how += f"。アプリのプロセス（PID {self.server_pid}）が {self.GONE_SECONDS} 秒後も残っている"
                    raise RuntimeError(f"E2E server not stopped: {how}")
                how += f"。アプリのプロセス（PID {self.server_pid}）の終了を確認"
        finally:
            self.stopped = how
            if self.log_file is not None and not self.log_file.closed:
                self.log_file.close()

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


def python_env(base: Optional[dict[str, str]] = None) -> dict[str, str]:
    """The environment of a Python process the tests start (the app, the
    display check tool): fta_tool on its path, and its stdout and stderr in
    UTF-8. Without PYTHONIOENCODING, Python writes a pipe or a file in the
    locale's encoding on Windows (cp932 for Japanese), while the tests read
    it as UTF-8: the Japanese messages were lost (UnicodeDecodeError in
    subprocess's reader thread, PytestUnhandledThreadExceptionWarning, the
    Windows run of 2026-10-30). Only the standard streams change (not
    PYTHONUTF8, which would also change how the process opens files)."""
    env = dict(os.environ if base is None else base)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(FTA_TOOL_DIR), env.get("PYTHONPATH", "")]))
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def process_gone(pid: int, timeout: float) -> bool:
    """True once the process `pid` has ended (waits up to `timeout` s)."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        synchronize = 0x00100000
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: no such process
        try:
            return kernel32.WaitForSingleObject(handle, int(timeout * 1000)) == 0  # WAIT_OBJECT_0
        finally:
            kernel32.CloseHandle(handle)
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass
        status = pathlib.Path(f"/proc/{pid}/status")
        try:
            if "\nState:\tZ" in status.read_text():  # ended, not yet reaped: holds no file
                return True
        except OSError:
            pass
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)


def remove_folder(path: pathlib.Path, tries: int, wait: float) -> tuple[bool, list[str]]:
    """Remove a folder of the tests (never ignoring an error), trying up to
    `tries` times `wait` s apart: on Windows a file can stay in use a moment
    after the process that had it ended (an antivirus or the indexer may
    open it). Returns whether it is gone and the error of each failed try."""
    import shutil

    errors: list[str] = []
    for attempt in range(tries):
        try:
            shutil.rmtree(path)
            return True, errors
        except OSError as error:
            if not path.exists():  # gone after all (removed meanwhile): this try did it
                return True, errors
            errors.append(f"{type(error).__name__}: {error}")
            if attempt + 1 < tries:
                time.sleep(wait)
    return False, errors


def start_server(workdir: pathlib.Path, port: int, extra_env: Optional[dict[str, str]] = None, *,
                 python: Optional[list[str]] = None, start_seconds: float = 60) -> E2EServer:
    """Start the app for the tests; `extra_env` changes its settings (e.g.
    FTA_SAMPLE_SCENARIOS_FILE for a server without sample scenarios).
    `python` replaces the interpreter's command and `start_seconds` the time
    it is given (the tests of the server's start and stop).

    If the app does not answer, the error says how far it got (what
    stub_server.py recorded in server-stages.jsonl, whether its port is open,
    which processes still run) and only then are the processes it started
    stopped (start_failure)."""
    env = python_env()
    env["FTA_E2E_WORKDIR"] = str(workdir)
    env["FTA_E2E_STUB_MODE"] = "create"
    env.update(extra_env or {})
    # What a server started before in this folder left (the W-02 tool starts
    # it again in the same folder): never read as this start's.
    for name in ("server.pid", "server-stages.jsonl", "launcher.pid", "launcher-stages.jsonl"):
        (workdir / name).unlink(missing_ok=True)
    log_path = workdir / "server.log"
    log = log_path.open("wb")
    # stdin is how close() asks the app to end (stub_server.py --stop-on-stdin-eof).
    process = subprocess.Popen(
        [*(python or [sys.executable]), "-m", "tests.e2e.stub_server", "--port", str(port), "--stop-on-stdin-eof"],
        cwd=workdir, env=env, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + start_seconds
    while True:
        if process.poll() is not None:
            start_failure(process, workdir, port, log, f"起動したプロセスが終了した（終了コード {process.returncode}）")
        server_pid = read_server_pid(workdir)
        if server_pid is not None and server_pid != process.pid and process_gone(server_pid, 0):
            start_failure(process, workdir, port, log, f"アプリのプロセス（PID {server_pid}）が起動の途中で終了した")
        ended = [s for s in launcher_stages(workdir) if s.get("stage") in ("child exited", "child not started")]
        if server_pid is None and ended:  # a stand-in launcher (the tests) says its child is gone
            start_failure(process, workdir, port, log, f"起動したプロセスの子が、アプリの起動の前に終わった（{ended[0]['stage']}）")
        try:
            if httpx.get(url + "/", timeout=2, trust_env=False).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            start_failure(process, workdir, port, log, f"{start_seconds:g} 秒たっても HTTP の応答がない")
        time.sleep(0.2)
    return E2EServer(url, workdir, process, log_path, log, read_server_pid(workdir))


def read_server_pid(workdir: pathlib.Path) -> Optional[int]:
    """The app's process id (stub_server.py writes it first), None before."""
    try:
        return int((workdir / "server.pid").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def launcher_stages(workdir: pathlib.Path) -> list[dict]:
    """What a stand-in launcher of the tests recorded (launcher-stages.jsonl,
    tests/e2e/launcher_probe.py): none for the usual start."""
    path = workdir / "launcher-stages.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    stages = []
    for line in lines:
        try:
            stages.append(json.loads(line))
        except ValueError:
            pass  # a line being written
    return stages


def start_failure(process: subprocess.Popen, workdir: pathlib.Path, port: int, log, reason: str):
    """Raise for a server that did not start, with what is known of it
    (gathered before anything is stopped), then stop what it started: the
    process started here and its descendants (Windows: taskkill /T, which
    follows the parent links of a venv's launcher and its child), and the
    app's own process (server.pid) if it still runs. What could not be
    stopped is said."""
    server_pid = read_server_pid(workdir)
    stand_in = launcher_stages(workdir)
    child_pids = [s["child_pid"] for s in stand_in if s.get("stage") == "child started"]
    lines = [f"E2E server did not start: {reason}",
             f"- 起動したプロセス（PID {process.pid}）：" + ("動作中" if process.poll() is None
                                                          else f"終了（終了コード {process.returncode}）")]
    if server_pid is None:
        lines.append("- アプリのプロセス：server.pid がない（stub_server.py の main() に達していない。"
                     "起動の途中か、その前に止まった。子のプロセスがないとは限らない）")
    else:
        lines.append(f"- アプリのプロセス（PID {server_pid}）：" + ("終了" if process_gone(server_pid, 0) else "動作中"))
    if (workdir / "launcher.pid").exists() or stand_in:
        launcher = (workdir / "launcher.pid").read_text(encoding="utf-8").strip() if (workdir / "launcher.pid").exists() else "なし"
        lines.append(f"- スタンドインのランチャー：launcher.pid {launcher}、記録（launcher-stages.jsonl）："
                     + ("\n" + "\n".join(json.dumps(s, ensure_ascii=False) for s in stand_in) if stand_in else "なし"))
        for pid in child_pids:
            lines.append(f"- スタンドインの子（PID {pid}）：" + ("終了" if process_gone(pid, 0) else "動作中"))
    stages = workdir / "server-stages.jsonl"
    lines.append("- stub_server.py の記録（server-stages.jsonl）：" + (
        "\n" + stages.read_text(encoding="utf-8", errors="replace").rstrip() if stages.exists() else "なし"))
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            lines.append(f"- ポート {port}：開いている（接続できる）")
    except OSError as error:
        lines.append(f"- ポート {port}：開いていない（{type(error).__name__}: {error}）")
    left = stop_started(process, server_pid, child_pids)
    lines.append("- 後片付け：" + (f"止められなかったプロセス {left}" if left else "起動したプロセスとアプリのプロセスは終了した"))
    log.close()
    text = (workdir / "server.log").read_text(encoding="utf-8", errors="replace")
    lines.append("- server.log：" + ("\n" + text.rstrip() if text.strip() else "空"))
    raise RuntimeError("\n".join(lines))


def stop_started(process: subprocess.Popen, server_pid: Optional[int], others: tuple = ()) -> list[int]:
    """Stop the process started for the server with its descendants, the
    app's own process and `others` (the children a stand-in launcher
    recorded): only these recorded processes. Returns those still running."""
    if process.poll() is None:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=30)
        else:
            process.kill()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    recorded = [pid for pid in (server_pid, *others) if pid is not None and pid != process.pid]
    for pid in recorded:
        if not process_gone(pid, 0):
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
            else:
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass
    left = [] if process.poll() is not None else [process.pid]
    left += [pid for pid in recorded if not process_gone(pid, 10)]
    return left


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


# ----- The page's sideways scroll ---------------------------------------------------

# Since PR-7's fix of 2026-10-29 the main area scrolls (css/base.css), not the
# page: a content wider than the display area makes #main scroll sideways
# while the root does not. The page's width is the larger of the root's and
# the main area's scroll width (with the room of its own scroll bar, so it
# compares with the display area's width as the root's did).
PAGE_WIDTH = """() => {
  const root = document.documentElement, main = document.getElementById('main');
  const inMain = main ? main.scrollWidth + (main.offsetWidth - main.clientWidth) : 0;
  return { width: Math.max(root.scrollWidth, inMain), left: Math.max(window.scrollX, main ? main.scrollLeft : 0) };
}"""


def page_scroll_width(page) -> int:
    """The page's scroll width, the main area's included (see PAGE_WIDTH)."""
    return page.evaluate(PAGE_WIDTH)["width"]


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
# 320/0.17, 340/0.23 and 440/0.23; the dialogs, min(520px, 100vw - 32px),
# at 552; the menu panel (340px, at most 100vw - 16px) at 356. Since PR-7's
# fix of 2026-10-29 the notifications are in a row of their own (no width
# of the display area: the boundaries 592 and 932 of their former width are
# gone). Heights: 700 (below it the notifications take at most 25vh instead
# of 30vh; components.css); otherwise the page is 100vh less the header and
# the dialogs' max-height depends on their content.
LAYOUT_BOUNDARIES = {
    "width": (356, 552, 1024, 1280, 240 / 0.17, 340 / 0.23, 320 / 0.17, 440 / 0.23),
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
