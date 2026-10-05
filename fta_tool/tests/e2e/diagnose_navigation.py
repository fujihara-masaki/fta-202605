"""Diagnosis of the first page load in an installed browser (PR #18).

The preflight in Windows Chrome of 2026-10-05 (b8b09b0) stopped in all 7
tests at the first page.goto() of the edit screen: Timeout 10000ms, the page
still about:blank, the request recorded without a response, no screenshot.
This shows how far the same first load gets, with one new temporary server
(its own database in --out, a free port):

  1. Python (httpx): GET / and GET /analyses/{id}: status, time, HTML.
  2. The browser (Playwright, the same channel, headed): the pages loaded
     as the tests do (edit screen, list, edit screen): request, response,
     failure, page.url, and when commit, DOMContentLoaded and load were
     reached, each with a finite limit (longer than the tests' on purpose,
     to see how far a load gets); a screenshot of each, or why there is none.
  3. A minimal configuration (no trace, no page check) against the tests'
     one (trace and the page check with its CDP session); when the minimal
     one does not get through either, the same with the browser's sandbox
     on (Playwright starts it with --no-sandbox); the installed browser
     started without Playwright (a new temporary profile, no automation)
     for the same URL.
  4. The server's own record of each request (FTA_E2E_ACCESS_LOG): received,
     response started, response ended (method, path, status, times; no
     header, no body).

The browser's network log (NetLog) of 2 and 3 is summarised for the
requests to the test server: the proxy decision (and a wait for the
automatic proxy detection or a PAC script), the check of local network
access, the connection, and where a request waited. The raw logs stay in
netlog-raw/ (they also list the browser's own background requests and the
proxy settings: hand them over only when asked). Read only, never changed:
which Windows proxy settings are set (not their values) and the names of the
browser policies (not their values).

A diagnosis, never a pass: it checks no screen, and a run without the tests'
configuration is never the acceptance.

    python tests/e2e/diagnose_navigation.py --out <new folder> [--channel chrome] [--env-label TEXT]

scripts/run_browser_e2e.ps1 -Mode Diagnose runs it with the same checks as
the preflight. Exit code: 0 the diagnosis ran (whatever it found), 1 it
could not run (the reason is in the report), 2 wrong arguments or --out not
empty.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Optional

FTA_TOOL_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(FTA_TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(FTA_TOOL_DIR))

COMMIT_SECONDS = 30  # how long a load may take to be committed
# The first load of a new context: it may wait for the context's proxy
# settings (e.g. automatic detection, a PAC script; Chromium gives up a PAC
# fetch after about 30 seconds), so it is watched longer to see if it ends.
FIRST_COMMIT_SECONDS = 60
STAGE_SECONDS = 15  # then DOMContentLoaded, then load, each
TEST_LIMIT_MS = 10000  # the tests allow 10 seconds for a whole load (page.set_default_timeout)
SCREENSHOT_MS = 5000  # as pytest-playwright's screenshot of a failed test
HTTPX_SECONDS = 30
PLAIN_SECONDS = FIRST_COMMIT_SECONDS  # the browser without Playwright: how long to wait for its request
CLOSE_SECONDS = 10
LAUNCH_MS = 60000

VIEWPORT = {"width": 1280, "height": 800}
VARIANTS = {  # name: (description, trace, page check with its CDP session)
    "minimal": ("最小（trace・ページの監視なし）", False, False),
    "tests": ("テストと同じ構成（trace とページの監視（CDP）あり）", True, True),
    "watch": ("ページの監視（CDP）だけ", False, True),
    "trace": ("trace だけ", True, False),
    "sandbox": ("最小・サンドボックスあり（Playwright が既定で付ける --no-sandbox を外した起動）", False, False),
}


def now_text() -> str:
    return dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def clock(moment: Optional[float]) -> str:
    if moment is None:
        return "-"
    return dt.datetime.fromtimestamp(moment).astimezone().strftime("%H:%M:%S.%f")[:-3]


def first_line(error: BaseException) -> str:
    text = str(error).strip()
    return text.splitlines()[0][:300] if text else type(error).__name__


def progress(text: str) -> None:
    print(f"[診断] {text}", flush=True)


def cell(value) -> str:
    return " ".join(str(value).split()).replace("|", "／")


def yes(value) -> str:
    return "あり" if value else "なし"


# ----- 4. the server's record ----------------------------------------------------

def read_access_log(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def access_requests(events: list[dict]) -> list[dict]:
    """The server's record (tests/e2e/stub_server.py AccessLog), one entry per request."""
    by_number: dict = collections.OrderedDict()
    for event in events:
        by_number.setdefault(event.get("n"), []).append(event)
    requests = []
    for number, items in by_number.items():
        kinds = {e.get("event"): e for e in items}
        first = items[0]
        start, end = kinds.get("response_start"), kinds.get("response_end")
        requests.append({
            "n": number,
            "time": first.get("time"),
            "method": first.get("method"),
            "path": first.get("path"),
            "query": first.get("query") or "",
            "client": first.get("client"),
            "received": "received" in kinds,
            "response_start_ms": start.get("ms") if start else None,
            "status": start.get("status") if start else None,
            "response_end_ms": end.get("ms") if end else None,
            "bytes": end.get("bytes") if end else None,
            "client_disconnected": "client_disconnected" in kinds,
            "error": kinds["error"].get("error") if "error" in kinds else None,
        })
    return requests


MARGIN = 0.05  # seconds: the server, the browser's log and this script read the same clock


def server_side(requests: list[dict], path: str, since: float, until: float, client: str,
                margin: float = MARGIN) -> dict:
    """What the server recorded for `path` from `client` between the times
    (with when each one arrived, from `since`)."""
    return {"requests": [{**r, "after_ms": round((r["time"] - since) * 1000)} for r in requests
                         if r["path"] == path and r["client"] == client
                         and r["time"] is not None and since - margin <= r["time"] <= until + margin]}


def describe_server_request(item: dict) -> str:
    """Times from the start of the load when known ("after_ms"), else from receipt."""
    base = item.get("after_ms")

    def moment(ms) -> str:
        return f"{round(base + ms)} ms" if base is not None else f"受信から {ms} ms"

    received = f"受信 {base} ms" if base is not None else "受信あり"
    if item["error"]:
        return f"{received}・処理中に例外（{item['error']}）"
    if item["response_start_ms"] is None:
        return f"{received}・応答の開始なし" + ("（相手が切断）" if item["client_disconnected"] else "")
    if item["response_end_ms"] is None:
        return f"{received}・応答の開始 {moment(item['response_start_ms'])}（{item['status']}）・応答の終了なし"
    return (f"{received}・応答の開始 {moment(item['response_start_ms'])}（{item['status']}）・"
            f"終了 {moment(item['response_end_ms'])}（{item['bytes']} バイト）")


def describe_server_side(record: dict) -> str:
    requests = record.get("requests") or []
    if not requests:
        return "受信なし（この時間にサーバーへ届いた要求はない）"
    return "、".join(describe_server_request(item) for item in requests)


# ----- 1. Python (httpx) ------------------------------------------------------------

def python_get(url: str) -> dict:
    import httpx

    started = time.monotonic()
    result: dict = {"url": url}
    try:
        with httpx.Client(timeout=HTTPX_SECONDS, trust_env=False, follow_redirects=False) as client:
            response = client.get(url)
        body = response.text
        result.update({
            "status": response.status_code,
            "ms": round((time.monotonic() - started) * 1000, 1),
            "bytes": len(response.content),
            "content_type": response.headers.get("content-type", ""),
            "html": "<html" in body.lower(),
            "edit_page": 'class="edit-steps' in body,
        })
    except Exception as error:  # noqa: BLE001 - recorded, the diagnosis goes on
        result.update({"error": f"{type(error).__name__}: {first_line(error)}",
                       "ms": round((time.monotonic() - started) * 1000, 1)})
    return result


# ----- 2. and 3. the browser through Playwright ---------------------------------------

class PageLog:
    """What a page reported, with times relative to the start of each load."""

    def __init__(self, page):
        self.events: list[dict] = []
        page.on("request", lambda r: self._add("request", r.url, resource=r.resource_type,
                                               navigation=r.is_navigation_request()))
        page.on("response", lambda r: self._add("response", r.url, status=r.status))
        page.on("requestfailed", lambda r: self._add("requestfailed", r.url, failure=r.failure))
        page.on("requestfinished", lambda r: self._add("requestfinished", r.url))
        page.on("framenavigated", lambda f: self._add("framenavigated", f.url) if f.parent_frame is None else None)
        page.on("domcontentloaded", lambda p: self._add("domcontentloaded", p.url))
        page.on("load", lambda p: self._add("load", p.url))
        page.on("crash", lambda p: self._add("crash", p.url))
        page.on("console", lambda m: self._add("console", (m.location or {}).get("url") or "", type=m.type,
                                               text=m.text[:200]) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: self._add("pageerror", "", text=str(e)[:200]))

    def _add(self, kind: str, url: str, **fields) -> None:
        if url.startswith("data:"):
            return
        self.events.append({"t": time.monotonic(), "kind": kind, "url": url, **fields})


def screenshot(page, path: pathlib.Path) -> dict:
    """The page as it is, or why it could not be saved (as a failed test's)."""
    from tests.e2e.support import save_screenshot

    return save_screenshot(page, path, SCREENSHOT_MS)


def load(page, log: PageLog, url: str, name: str, out: pathlib.Path, commit_seconds: int = COMMIT_SECONDS) -> dict:
    """Load `url` as the tests do and see how far it gets."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    progress(f"  読み込み {name}：{url}")
    mark = len(log.events)
    started, wall = time.monotonic(), time.time()
    result: dict = {"name": name, "url": url, "started": clock(wall), "commit_limit_ms": commit_seconds * 1000}

    def at() -> float:
        return round((time.monotonic() - started) * 1000, 1)

    try:
        response = page.goto(url, wait_until="commit", timeout=commit_seconds * 1000)
        result["commit_ms"] = at()
        result["status"] = response.status if response else None
    except PlaywrightTimeout:
        result["commit_error"] = f"{commit_seconds} 秒で未到達"
    except PlaywrightError as error:
        result["commit_error"] = first_line(error)
    for state, key in (("domcontentloaded", "dcl"), ("load", "load")):
        if "commit_ms" not in result or (key == "load" and "dcl_ms" not in result):
            result[f"{key}_error"] = "未実施（前の段階に未到達）"
            continue
        try:
            page.wait_for_load_state(state, timeout=STAGE_SECONDS * 1000)
            result[f"{key}_ms"] = at()
        except PlaywrightTimeout:
            result[f"{key}_error"] = f"{STAGE_SECONDS} 秒で未到達"
        except PlaywrightError as error:
            result[f"{key}_error"] = first_line(error)
    result["page_url"] = page.url
    result["screenshot"] = screenshot(page, out / f"screen-{name}.png")
    result["window"] = (wall, time.time())
    result["events"] = [{**{k: v for k, v in e.items() if k != "t"}, "ms": round((e["t"] - started) * 1000, 1)}
                        for e in log.events[mark:]]
    own = [e for e in result["events"] if e["url"] == url]
    request = next((e for e in own if e["kind"] == "request"), None)
    response_event = next((e for e in own if e["kind"] == "response"), None)
    failed = next((e for e in own if e["kind"] == "requestfailed"), None)
    result["document"] = {
        "request_ms": request["ms"] if request else None,
        "response_ms": response_event["ms"] if response_event else None,
        "status": response_event.get("status") if response_event else None,
        "failure": failed.get("failure") if failed else None,
    }
    if "commit_ms" not in result:  # leave nothing pending for the next load
        try:
            page.goto("about:blank", timeout=10000)
            result["reset"] = "about:blank へ戻した"
        except Exception as error:  # noqa: BLE001
            result["reset"] = f"about:blank へ戻せなかった：{first_line(error)}"
    return result


def describe_load(result: dict) -> str:
    if "commit_ms" not in result:
        text = f"commit に未到達（{result.get('commit_error')}）"
    else:
        text = f"commit {result['commit_ms']} ms（{result.get('status')}）"
        text += f"・DOMContentLoaded {result['dcl_ms']} ms" if "dcl_ms" in result else f"・DOMContentLoaded {result.get('dcl_error')}"
        text += f"・load {result['load_ms']} ms" if "load_ms" in result else f"・load {result.get('load_error')}"
        if result.get("load_ms", TEST_LIMIT_MS + 1) > TEST_LIMIT_MS:
            text += f"（テストの上限 {TEST_LIMIT_MS // 1000} 秒では足りない）"
    document = result.get("document") or {}
    text += "。主文書：" + (f"要求 {document['request_ms']} ms" if document.get("request_ms") is not None else "要求の記録なし")
    text += (f"・応答 {document['response_ms']} ms（{document['status']}）" if document.get("response_ms") is not None
             else "・応答なし")
    if document.get("failure"):
        text += f"・失敗（{document['failure']}）"
    events = result.get("events") or []
    if any(e["kind"] == "crash" for e in events):
        text += "。ページのプロセスが異常終了した（crash）"
    others = [e for e in events if e["kind"] == "requestfailed" and e["url"] != result["url"]]
    if others:
        text += "。ほかに失敗した要求：" + "、".join(f"{e['url']}（{e.get('failure')}）" for e in others[:3])
    return f"{text}。page.url={result.get('page_url')}"


def launch(playwright, channel: Optional[str], netlog: pathlib.Path, sandbox: bool):
    options: dict = {"headless": False, "timeout": LAUNCH_MS, "args": [f"--log-net-log={netlog}"]}
    if channel:
        options["channel"] = channel
    if sandbox:
        options["chromium_sandbox"] = True
    return playwright.chromium.launch(**options)


VERSION_PAGE = """() => {
  const text = (id) => { const el = document.getElementById(id); return el ? el.textContent.trim() : ''; };
  return { company: text('company'), version: text('version'), executable: text('executable_path'),
           command_line: text('command_line') };
}"""


def describe_launched(browser) -> dict:
    """chrome://version of the started browser: the product, its file and the
    switches it was started with (their names, and the feature lists; never a
    path)."""
    context = None
    try:
        context = browser.new_context()
        page = context.new_page()
        page.goto("chrome://version", timeout=10000)
        info = page.evaluate(VERSION_PAGE)
    except Exception as error:  # noqa: BLE001 - e.g. blocked by a policy
        return {"product": browser.version, "executable": "-", "switches": [],
                "error": f"chrome://version を読めなかった：{first_line(error)}"}
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass
    switches = []
    for token in (info.get("command_line") or "").split():
        if not token.startswith("--"):
            continue
        name = token.split("=", 1)[0]
        switches.append(token if name in ("--enable-features", "--disable-features") else name)
    product = f"{info.get('company', '')} {' '.join((info.get('version') or '').split())}".strip()
    return {"product": product or browser.version, "executable": info.get("executable") or "-", "switches": switches}


def run_variant(browser, key: str, server_url: str, analysis_id: int, out: pathlib.Path,
                first_only: bool = False) -> dict:
    from tests.e2e.support import PageWatcher

    description, trace, watch = VARIANTS[key]
    progress(f"ブラウザ：{description}")
    result: dict = {"key": key, "description": description, "trace": trace, "watch": watch, "loads": []}
    context = browser.new_context(viewport=VIEWPORT, locale="ja-JP", timezone_id="Asia/Tokyo",
                                  base_url=server_url, accept_downloads=True)
    try:
        if trace:  # as pytest-playwright's --tracing retain-on-failure
            context.tracing.start(title=f"diagnose-{key}", screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        watcher = PageWatcher(page, server_url) if watch else None
        log = PageLog(page)
        edit = f"{server_url}/analyses/{analysis_id}"
        plan = [(f"{key}-1-edit", edit), (f"{key}-2-list", server_url + "/"), (f"{key}-3-edit", edit)]
        for index, (name, url) in enumerate(plan[:1] if first_only else plan):
            if index == 2 and not any("commit_ms" in item for item in result["loads"]):
                result["loads_skipped"] = "1回目・2回目とも commit に到達しなかったため、3回目（編集画面をもう一度）は省略しました"
                break
            result["loads"].append(load(page, log, url, name, out,
                                        FIRST_COMMIT_SECONDS if index == 0 else COMMIT_SECONDS))
        if watcher is not None:
            result["page_check"] = {"cdp": watcher.cdp_error or "読めた", "problems": watcher.problems(),
                                    "known_favicon_404": len(watcher.known)}
        if trace:
            path = out / f"trace-{key}.zip"
            try:
                context.tracing.stop(path=str(path))
                result["trace_file"] = path.name if path.exists() else "（保存の呼び出しは終わったが、ファイルがない）"
            except Exception as error:  # noqa: BLE001
                result["trace_file"] = f"（保存できなかった：{first_line(error)}）"
    finally:
        try:
            context.close()
        except Exception:  # noqa: BLE001
            pass
        PageWatcher.take_made()  # the diagnosis records its own results
    return result


class _NotLaunched(Exception):
    """Playwright could not start the browser (the error is in the results)."""


def committed(variant: Optional[dict]) -> bool:
    loads = (variant or {}).get("loads") or []
    return bool(loads) and "commit_ms" in loads[0]


# ----- 3. the browser without Playwright ----------------------------------------------

def find_installed_browser(channel: str) -> Optional[str]:
    """Where Playwright looks for --browser-channel chrome / msedge (Windows)."""
    if sys.platform != "win32":
        return None
    suffix = r"Google\Chrome\Application\chrome.exe" if channel == "chrome" else r"Microsoft\Edge\Application\msedge.exe"
    for variable in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.environ.get(variable)
        if base and (pathlib.Path(base) / suffix).is_file():
            return str(pathlib.Path(base) / suffix)
    return None


def close_started_process(process: subprocess.Popen) -> str:
    """Close the browser this diagnosis started (its process id only), politely first."""
    if process.poll() is not None:
        return "既に終了していた"
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(process.pid)], capture_output=True, timeout=CLOSE_SECONDS)
        else:
            process.terminate()
        process.wait(timeout=CLOSE_SECONDS)
        return "閉じた"
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                           timeout=CLOSE_SECONDS)
        else:
            process.kill()
        process.wait(timeout=CLOSE_SECONDS)
        return "閉じなかったため、この診断が起動したプロセス（とその子）を止めた"
    except (OSError, subprocess.SubprocessError):
        return f"止められなかった（プロセス ID {process.pid}）"


def plain_browser(executable: str, channel: str, url: str, path: str, out: pathlib.Path,
                  access_log: pathlib.Path) -> dict:
    """The installed browser started as a person would (no Playwright, no
    automation), with a new temporary profile, for the same URL."""
    progress("Playwright を使わない起動（新しい一時プロフィール）")
    profile = pathlib.Path(tempfile.mkdtemp(prefix="fta-diagnose-profile-"))  # short: a profile is deep
    netlog = out / "netlog-raw" / "plain.json"
    command = [executable, f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
               f"--log-net-log={netlog}", "--new-window", url]
    shown = ["--user-data-dir=<新しい一時フォルダ>", "--no-first-run", "--no-default-browser-check",
             "--log-net-log=<記録フォルダ>/netlog-raw/plain.json", "--new-window", url]
    if channel == "msedge":  # as Playwright: else Edge may start itself again, leaving this process
        command.insert(1, "--edge-skip-compat-layer-relaunch")
        shown.insert(0, "--edge-skip-compat-layer-relaunch")
    if os.name == "posix" and os.geteuid() == 0:  # the development container runs as root
        command.insert(1, "--no-sandbox")
        shown.insert(0, "--no-sandbox（Linux の root で実行したため。Windows では付けない）")
    result: dict = {"executable": executable, "url": url, "started": clock(time.time()), "arguments": shown}
    wall = time.time()
    try:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as error:
        result["error"] = f"起動できなかった：{first_line(error)}"
        shutil.rmtree(profile, ignore_errors=True)
        return result
    deadline = time.monotonic() + PLAIN_SECONDS
    seen: dict = {"requests": []}
    while time.monotonic() < deadline:
        seen = server_side(access_requests(read_access_log(access_log)), path, wall, time.time(), "browser", margin=0)
        if any(item["response_end_ms"] is not None for item in seen["requests"]):
            break
        if process.poll() is not None:
            result["exited_early"] = f"ブラウザが {round(time.time() - wall, 1)} 秒で終了した（終了コード {process.returncode}）"
            break
        time.sleep(0.5)
    result["waited_seconds"] = round(time.time() - wall, 1)
    result["window"] = (wall, time.time())
    result["server"] = seen
    result["closed"] = close_started_process(process)
    result["profile"] = "削除できなかった"
    for _ in range(10):  # the temporary profile of this run only
        try:
            shutil.rmtree(profile)
            result["profile"] = "終了後に削除した"
            break
        except FileNotFoundError:
            result["profile"] = "終了後に削除した"
            break
        except OSError as error:
            result["profile"] = f"削除できなかった（{first_line(error)}）"
            time.sleep(1)
    return result


# ----- the browser's network log (NetLog) -------------------------------------------------

# The steps of a request where it can wait (net/log/net_log_event_type_list.h).
STAGES = {
    "PROXY_RESOLUTION_SERVICE_WAITING_FOR_INIT_PAC": "プロキシの自動検出・PAC の準備の完了待ち",
    "NETWORK_DELEGATE_BEFORE_URL_REQUEST": "送信前の確認（拡張機能・ポリシーなど）",
    "NETWORK_DELEGATE_BEFORE_START_TRANSACTION": "送信前の確認（ヘッダー。拡張機能など）",
    "HTTP_CACHE_OPEN_OR_CREATE_ENTRY": "キャッシュの確認",
    "HTTP_CACHE_ADD_TO_ENTRY": "キャッシュの確認",
    "HTTP_STREAM_REQUEST": "接続の確保",
    "PROXY_RESOLUTION_SERVICE": "プロキシの決定",
    "HTTP_STREAM_JOB_WAITING": "接続の順番待ち",
    "HTTP_STREAM_JOB_INIT_CONNECTION": "接続の確保（ソケット）",
    "TCP_CONNECT": "TCP 接続",
    "URL_REQUEST_DELEGATE_CONNECTED": "接続後の確認（ローカルネットワークへのアクセスなど）",
    "HTTP_TRANSACTION_SEND_REQUEST": "要求の送信",
    "HTTP_TRANSACTION_READ_HEADERS": "応答ヘッダーの待ち（サーバーの応答待ち）",
    "NETWORK_DELEGATE_HEADERS_RECEIVED": "応答ヘッダー受信後の確認（拡張機能など）",
    "URL_REQUEST_DELEGATE_RESPONSE_STARTED": "応答の受け渡し（ブラウザ内）",
    "HTTP_TRANSACTION_READ_BODY": "本文の受信",
}
EVENT_LABELS = {"CANCELLED": "取り消し", "REQUEST_ALIVE": "要求", "URL_REQUEST_START_JOB": "要求の処理",
                "HTTP_STREAM_PARSER_READ_HEADERS": "応答ヘッダーの読み取り"}
LNA_PERMISSION = ("LOCAL_NETWORK_ACCESS_PERMISSION_REQUESTED",
                  "URL_REQUEST_DELEGATE_PLATFORM_LOCAL_NETWORK_ACCESS_PERMISSION_REQUIRED")
NOISE = ("SOCKET_BYTES_SENT", "SOCKET_BYTES_RECEIVED")
LOOPBACK = ("127.", "[::1]", "::1", "localhost")
SAFE_KEYS = ("result", "client_address_space", "resource_address_space", "should_upgrade_to_ssl", "request_type",
             "method", "byte_count")


def load_netlog(path: pathlib.Path) -> tuple[Optional[dict], str]:
    if not path.exists():
        return None, "ファイルがない"
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(text), "完全"
    except ValueError:
        pass
    repaired = text.rstrip().rstrip(",")  # a browser that did not close cleanly leaves the end out
    for ending in ("]}", "\n]}", "}]}"):
        try:
            return json.loads(repaired + ending), "末尾を補って読んだ（ブラウザが正常に閉じなかった）"
        except ValueError:
            continue
    return None, "読めない"


def _dependencies(params) -> list:
    found = []
    if isinstance(params, dict):
        for key, value in params.items():
            if key == "source_dependency" and isinstance(value, dict) and "id" in value:
                found.append(value["id"])
            else:
                found.extend(_dependencies(value))
    elif isinstance(params, list):
        for value in params:
            found.extend(_dependencies(value))
    return found


def pac_source(text) -> str:
    text = str(text or "")
    if text.startswith("WPAD DHCP"):
        return "WPAD（DHCP）"
    if text.startswith("WPAD DNS"):
        return "WPAD（DNS）"
    if text.startswith("Custom PAC"):
        return "指定の PAC（URL は省略）"
    return "PAC の取得"


def _safe_params(params: dict, origin: str, errors: dict) -> dict:
    """Only what describes this request: never another URL, proxy host or header."""
    kept = {}
    for key, value in (params or {}).items():
        if key == "net_error":
            kept[key] = errors.get(value, value)
        elif key == "url" and isinstance(value, str) and value.startswith(origin + "/"):
            kept[key] = value
        elif key == "proxy_info" and isinstance(value, str):
            kept[key] = value if value.startswith("DIRECT") else "PROXY（ホスト名は省略）"
        elif key in ("address", "remote_address", "local_address") and str(value).startswith(LOOPBACK):
            kept[key] = value
        elif key == "proxy_chain" and isinstance(value, str):
            kept[key] = value if "direct" in value else "（プロキシ。ホスト名は省略）"
        elif key == "source" and isinstance(value, str):
            kept[key] = pac_source(value)
        elif key in SAFE_KEYS and isinstance(value, (str, int, float, bool)):
            kept[key] = value
    return kept


def summarize_netlog(path: pathlib.Path, origin: str) -> dict:
    """The requests of the browser to the test server, from its NetLog: the
    proxy decision, the checks, the connection and where each one waited."""
    data, state = load_netlog(path)
    summary: dict = {"file": path.name, "state": state, "requests": [], "proxy_config": [], "pac": [],
                     "wpad_dhcp": None, "field_trials": []}
    if data is None:
        return summary
    constants = data.get("constants") or {}
    names = {v: k for k, v in (constants.get("logEventTypes") or {}).items()}
    errors = {v: k for k, v in (constants.get("netError") or {}).items()}
    source_types = {v: k for k, v in (constants.get("logSourceType") or {}).items()}
    try:
        offset: Optional[int] = int(float(constants.get("timeTickOffset")))
    except (TypeError, ValueError):
        offset = None
    summary["field_trials"] = [str(item) for item in constants.get("activeFieldTrialGroups") or []]
    events = [e for e in data.get("events") or []
              if isinstance(e, dict) and isinstance(e.get("source"), dict) and "time" in e]
    if not events:
        return summary
    for index, event in enumerate(events):
        event["_i"] = index

    def name_of(event) -> str:
        return names.get(event.get("type"), str(event.get("type")))

    def at(event) -> int:
        return int(event["time"])

    def label(event) -> str:
        name = name_of(event)
        text = STAGES.get(name) or EVENT_LABELS.get(name) or f"{name} "
        return text + {1: "の開始", 2: "の終了"}.get(event.get("phase"), "")

    log_start, log_end = at(events[0]), max(at(e) for e in events)
    by_source: dict = collections.defaultdict(list)
    for event in events:
        by_source[event["source"].get("id")].append(event)

    def kind_of(source_id) -> str:
        return source_types.get(by_source[source_id][0]["source"].get("type"), "")

    for event in events:
        if name_of(event) != "PROXY_CONFIG_CHANGED":
            continue
        config = (event.get("params") or {}).get("new_config") or {}
        bypass = [str(item) for item in config.get("bypass_list") or []]
        summary["proxy_config"].append({
            "ms": at(event) - log_start,
            "auto_detect": bool(config.get("auto_detect")),
            "pac_url": "pac_url" in config,
            "fixed_proxy": any(k in config for k in ("single_proxy", "proxy_per_scheme")),
            "bypass_list": bool(bypass),
            "bypass_has_loopback": any(item.strip("*").startswith(("127.", "localhost", "<local>", "::1", "[::1]"))
                                       for item in bypass),
            "bypass_has_minus_loopback": "<-loopback>" in bypass,
        })

    for source, items in by_source.items():  # automatic proxy detection / PAC
        if kind_of(source) != "PAC_FILE_DECIDER":
            continue
        run: dict = {"start_ms": at(items[0]) - log_start, "duration_ms": None, "net_error": None, "steps": []}
        open_steps: dict = {}
        for event in items:
            name, params = name_of(event), event.get("params") or {}
            step = "待ち" if name == "PAC_FILE_DECIDER_WAIT" else pac_source(params.get("source"))
            if name == "PAC_FILE_DECIDER" and event.get("phase") == 2:
                run["duration_ms"] = at(event) - at(items[0])
                if "net_error" in params:
                    run["net_error"] = errors.get(params["net_error"], params["net_error"])
            elif name in ("PAC_FILE_DECIDER_WAIT", "PAC_FILE_DECIDER_FETCH_PAC_SCRIPT") and event.get("phase") == 1:
                open_steps[name] = (at(event), step)
            elif name in open_steps and event.get("phase") == 2:
                begin, step = open_steps.pop(name)
                run["steps"].append({"step": step, "ms": at(event) - begin,
                                     "net_error": errors.get(params["net_error"], params["net_error"])
                                     if "net_error" in params else None})
            elif name == "PAC_FILE_DECIDER_HAS_NO_FETCHER":
                run["steps"].append({"step": "取得の手段なし", "ms": 0, "net_error": None})
        for begin, step in open_steps.values():
            run["steps"].append({"step": step, "ms": None, "from_ms": begin - at(items[0]), "net_error": None})
        summary["pac"].append(run)
    dhcp = [e for e in events if name_of(e).startswith("WPAD_DHCP_WIN")]
    if dhcp:
        summary["wpad_dhcp"] = {"events": len(dhcp), "start_ms": at(dhcp[0]) - log_start,
                                "span_ms": at(dhcp[-1]) - at(dhcp[0])}

    def depth(source_id) -> int:
        """Links are followed from the request towards its connection only
        (a socket or a pool shared with other requests must not bring them in)."""
        return {"URL_REQUEST": 0, "HTTP_STREAM_JOB_CONTROLLER": 1, "HTTP_STREAM_JOB": 2,
                "HTTP_STREAM_POOL_JOB": 2}.get(kind_of(source_id), 3)

    prefix = origin + "/"
    for source in sorted(by_source, key=lambda s: by_source[s][0]["_i"]):
        own = by_source[source]
        if kind_of(source) != "URL_REQUEST" or not any(
                name_of(e) in ("REQUEST_ALIVE", "URL_REQUEST_START_JOB")
                and str((e.get("params") or {}).get("url", "")).startswith(prefix) for e in own):
            continue
        related, frontier = {source}, [source]
        for _ in range(6):
            following = []
            for item in frontier:
                for event in by_source.get(item, []):
                    for dependency in _dependencies(event.get("params")):
                        if dependency in related or dependency not in by_source:
                            continue
                        if depth(dependency) < depth(item) or depth(dependency) == depth(item) < 3:
                            continue
                        related.add(dependency)
                        following.append(dependency)
            frontier = following
        start = at(own[0])
        alive_end = next((e for e in own if name_of(e) == "REQUEST_ALIVE" and e.get("phase") == 2), None)
        cancel = next((e for e in own if name_of(e) == "CANCELLED"), None)
        end_time = at(alive_end) if alive_end is not None else None
        timeline = sorted((e for item in related for e in by_source[item]), key=lambda e: (at(e), e["_i"]))
        timeline = [e for e in timeline if name_of(e) not in NOISE and (end_time is None or at(e) <= end_time)]
        cut = next((i for i, e in enumerate(timeline) if e is cancel or e is alive_end), len(timeline))
        open_stages: list = []
        for event in timeline[:cut]:
            name = name_of(event)
            if name not in STAGES:
                continue
            if event.get("phase") == 1:
                open_stages.append((name, at(event)))
            elif event.get("phase") == 2:
                for index in range(len(open_stages) - 1, -1, -1):
                    if open_stages[index][0] == name:
                        del open_stages[index]
                        break
        gap = None
        steps = [e for e in timeline if at(e) >= start]
        for before, after in zip(steps, steps[1:]):
            if gap is None or at(after) - at(before) > gap["ms"]:
                gap = {"ms": at(after) - at(before), "from_ms": at(before) - start,
                       "after": label(before), "before": label(after)}
        if end_time is None and steps and (gap is None or log_end - at(steps[-1]) > gap["ms"]):
            gap = {"ms": log_end - at(steps[-1]), "from_ms": at(steps[-1]) - start,
                   "after": label(steps[-1]), "before": "ログの終わり"}
        net_error = None
        for event in own:
            value = (event.get("params") or {}).get("net_error")
            if value is not None:
                net_error = errors.get(value, value)
        start_job = next((e.get("params") or {} for e in own if name_of(e) == "URL_REQUEST_START_JOB"), {})
        headers = next((e for e in own if name_of(e) == "HTTP_TRANSACTION_READ_RESPONSE_HEADERS"), None)
        status_line = None
        if headers is not None:
            lines = (headers.get("params") or {}).get("headers")
            if isinstance(lines, list) and lines and str(lines[0]).startswith("HTTP/"):
                status_line = str(lines[0])[:40]
        upgrade = next(((e.get("params") or {}).get("should_upgrade_to_ssl") for e in own
                        if name_of(e) == "TRANSPORT_SECURITY_STATE_SHOULD_UPGRADE_TO_SSL"), None)
        url = next((str((e.get("params") or {}).get("url")) for e in own if (e.get("params") or {}).get("url")), "")
        summary["requests"].append({
            "url": url,
            "request_type": start_job.get("request_type", "-"),
            "start_ms": start - log_start,
            "epoch": (start + offset) / 1000 if offset is not None else None,
            "proxy": next((_safe_params(e.get("params"), origin, errors).get("proxy_info") for e in timeline
                           if name_of(e) == "PROXY_RESOLUTION_SERVICE_RESOLVED_PROXY_LIST"), None) or "（記録なし）",
            "lna": [{k: v for k, v in (e.get("params") or {}).items()
                     if k in ("result", "client_address_space", "resource_address_space")}
                    for e in timeline if name_of(e) == "LOCAL_NETWORK_ACCESS_CHECK"],
            "lna_permission": any(name_of(e) in LNA_PERMISSION for e in timeline),
            "upgrade_to_ssl": upgrade,
            "headers_received": headers is not None,
            "status_line": status_line,
            "bytes": sum(int((e.get("params") or {}).get("byte_count") or 0) for e in own
                         if name_of(e) == "URL_REQUEST_JOB_FILTERED_BYTES_READ"),
            "ended": alive_end is not None,
            "cancelled": cancel is not None,
            "duration_ms": (end_time - start) if end_time is not None else None,
            "net_error": net_error,
            "open_at_end": [f"{STAGES[name]}（{name}、{begin - start} ms から）" for name, begin in reversed(open_stages)],
            "longest_gap": gap,
            "timeline": [{"ms": at(e) - start, "event": name_of(e),
                          "phase": {0: "", 1: "開始", 2: "終了"}.get(e.get("phase"), e.get("phase")),
                          **_safe_params(e.get("params"), origin, errors)} for e in timeline],
        })
    return summary


def describe_netlog_request(item: dict) -> str:
    parts = [f"プロキシ {item['proxy']}"]
    if item.get("lna"):
        parts.append("ローカルネットワークの確認 " + "、".join(
            f"{x.get('result')}（{x.get('client_address_space')}→{x.get('resource_address_space')}）" for x in item["lna"]))
    if item.get("lna_permission"):
        parts.append("ローカルネットワークへのアクセスの許可を求めた")
    if item.get("upgrade_to_ssl"):
        parts.append("HTTPS への切り替えあり")
    parts.append(f"応答ヘッダー {item['status_line'] or '受信あり'}" if item["headers_received"] else "応答ヘッダー 受信なし")
    if item["ended"]:
        parts.append(f"終了 {item['duration_ms']} ms" + (f"（{item['net_error']}）" if item["net_error"] else "")
                     + ("・取り消し" if item["cancelled"] else ""))
    else:
        parts.append("終了の記録なし（ログの終わりまで処理中）")
    text = "・".join(parts)
    if item["open_at_end"]:
        moment = "取り消しの時点" if item["cancelled"] else ("終了の時点" if item["ended"] else "ログの終わり")
        text += f"。{moment}で処理中の段階（内側から）：" + "、".join(item["open_at_end"])
    gap = item.get("longest_gap")
    if gap and gap["ms"] >= 1000:
        text += f"。最も長い間隔：{gap['after']} → {gap['before']}（{gap['ms']} ms、開始から {gap['from_ms']} ms）"
    return text


def netlog_for(summaries: dict, url: str, window) -> list[dict]:
    """The NetLog entries of the main document of one load (by URL and time)."""
    found = []
    for summary in summaries.values():
        for item in summary["requests"]:
            if item["url"] == url and item["request_type"] == "main frame" and item["epoch"] is not None \
                    and window[0] - MARGIN <= item["epoch"] <= window[1] + MARGIN:
                found.append(item)
    return found


# ----- read-only facts of Windows ---------------------------------------------------------

def _internet_settings(winreg, hive) -> dict:
    key = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    facts: dict = {}
    with winreg.OpenKey(hive, key) as handle:
        def value(name):
            try:
                return winreg.QueryValueEx(handle, name)[0]
            except OSError:
                return None
        override = str(value("ProxyOverride") or "").lower()
        facts.update({
            "proxy_enabled": bool(value("ProxyEnable")),
            "proxy_server_set": bool(value("ProxyServer")),
            "pac_url_set": bool(value("AutoConfigURL")),
            "override_set": bool(override),
            "override_has_local": "<local>" in override,
            "override_has_loopback": any(x in override for x in ("127.0.0.1", "localhost")),
            "override_has_minus_loopback": "<-loopback>" in override,
        })
    try:
        with winreg.OpenKey(hive, key + r"\Connections") as handle:
            blob = winreg.QueryValueEx(handle, "DefaultConnectionSettings")[0]
            facts["automatically_detect"] = bool(blob[8] & 0x08) if len(blob) > 8 else None
    except OSError:
        facts["automatically_detect"] = None
    return facts


def windows_proxy_settings() -> dict:
    """Which proxy settings are set (yes / no), never their values."""
    facts: dict = {"environment_variables": sorted(
        name for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy",
                          "all_proxy", "no_proxy", "auto_proxy") if os.environ.get(name))}
    if sys.platform != "win32":
        facts["windows"] = "Windows 以外のため確認していない"
        return facts
    import winreg

    for label, hive in (("user", winreg.HKEY_CURRENT_USER), ("machine", winreg.HKEY_LOCAL_MACHINE)):
        try:
            facts[label] = _internet_settings(winreg, hive)
        except OSError as error:
            facts[label] = {"error": first_line(error)}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"Software\Policies\Microsoft\Windows\CurrentVersion\Internet Settings") as handle:
            facts["per_user_policy"] = winreg.QueryValueEx(handle, "ProxySettingsPerUser")[0]
    except OSError:
        facts["per_user_policy"] = None
    try:
        output = subprocess.run(["netsh", "winhttp", "show", "proxy"], capture_output=True, timeout=10).stdout
        facts["winhttp"] = winhttp_proxy(output)
    except (OSError, subprocess.SubprocessError) as error:
        facts["winhttp"] = f"確認できなかった（{first_line(error)}）"
    return facts


def winhttp_proxy(output: bytes) -> str:
    """`netsh winhttp show proxy` in English or Japanese, whatever the code
    page of its output (Python runs in UTF-8 mode under the script)."""
    texts = []
    for encoding in ("utf-8", "cp932", "mbcs", "oem", "utf-16-le"):
        try:
            texts.append(output.decode(encoding))
        except (UnicodeDecodeError, LookupError):
            continue
    if any("Direct access" in text or "直接アクセス" in text for text in texts):
        return "直接（プロキシなし）"
    if any("Proxy Server" in text or "プロキシ サーバー" in text for text in texts):
        return "プロキシの設定あり（内容は記録しない）"
    return "判断できなかった（出力の形が想定と違う）"


def browser_policy_names(channel: str) -> dict:
    """The names of the browser's policies set in the registry, never their values."""
    if sys.platform != "win32" or channel == "chromium":
        return {"windows": "Windows 以外（または同梱の Chromium）のため確認していない"}
    import winreg

    sub = r"Software\Policies\Google\Chrome" if channel == "chrome" else r"Software\Policies\Microsoft\Edge"
    found = {}
    for hive_name, hive in (("HKLM", winreg.HKEY_LOCAL_MACHINE), ("HKCU", winreg.HKEY_CURRENT_USER)):
        try:
            with winreg.OpenKey(hive, sub) as handle:
                names = []
                index = 0
                while True:
                    try:
                        names.append(winreg.EnumValue(handle, index)[0])
                        index += 1
                    except OSError:
                        break
                index = 0
                while True:
                    try:
                        names.append(winreg.EnumKey(handle, index) + "（一覧）")
                        index += 1
                    except OSError:
                        break
                found[hive_name] = sorted(names)
        except FileNotFoundError:
            found[hive_name] = []
        except OSError as error:
            found[hive_name] = [f"（読めなかった：{first_line(error)}）"]
    return found


def describe_internet_settings(facts: dict) -> str:
    if "error" in facts:
        return f"読めなかった（{facts['error']}）"
    detect = facts.get("automatically_detect")
    return (f"プロキシ サーバーを使う {yes(facts['proxy_enabled'])}（アドレスの設定 {yes(facts['proxy_server_set'])}）、"
            f"自動構成スクリプト（PAC）{yes(facts['pac_url_set'])}、"
            f"設定を自動的に検出する {'記録なし' if detect is None else yes(detect)}、"
            f"例外の一覧 {yes(facts['override_set'])}（<local> {yes(facts['override_has_local'])}、"
            f"127.0.0.1・localhost {yes(facts['override_has_loopback'])}、"
            f"<-loopback> {yes(facts['override_has_minus_loopback'])}）")


# ----- the report ------------------------------------------------------------------------------

def _server_timing(request: dict) -> str:
    """When the server received a request and started its answer, from the start of the load."""
    after = request.get("after_ms")
    if after is None:
        return "サーバーの受信あり"
    if request.get("response_start_ms") is None:
        return f"サーバーの受信 {after} ms・応答の開始なし"
    return f"サーバーの受信 {after} ms・応答の開始 {round(after + request['response_start_ms'])} ms"


def hints(results: dict) -> list[str]:
    """A first reading of what was seen (rules over the records, not a cause)."""
    found = []
    edit = next((p for p in results.get("python") or [] if p["path"].startswith("/analyses/")), None)
    if edit is not None:
        if "status" not in edit:
            found.append(f"Python からの編集画面の GET が失敗した（{edit['error']}）：サーバー側か、この PC のループバック通信全体の問題")
        elif edit["ms"] > TEST_LIMIT_MS:
            found.append(f"Python からの編集画面の GET に {edit['ms']} ms：サーバー側の処理が遅い")
        elif edit["status"] != 200 or not edit.get("edit_page"):
            found.append(f"Python からの編集画面の GET の応答が想定と違う（{edit['status']}、編集画面の要素 {yes(edit.get('edit_page'))}）")
        else:
            found.append(f"Python からの編集画面の GET は {edit['ms']} ms で HTML を返した（サーバーは応答できる）")
    if results.get("launch_error"):
        found.append(f"Playwright でブラウザを起動できなかった（{results['launch_error']}）")
    for variant in results.get("variants") or []:
        if not variant.get("loads"):
            found.append(f"{variant['description']}：実行できなかった（{variant.get('error')}）")
            continue
        first = variant["loads"][0]
        server = (first.get("server") or {}).get("requests") or []
        netlog = first.get("netlog") or []
        where = ""
        if netlog and netlog[0]["open_at_end"]:
            where = f"（NetLog：処理中だった段階 {netlog[0]['open_at_end'][0]}）"
        elif netlog and (netlog[0].get("longest_gap") or {}).get("ms", 0) >= 1000:
            gap = netlog[0]["longest_gap"]
            where = f"（NetLog：最も長い間隔 {gap['after']} → {gap['before']} {gap['ms']} ms）"
        name = variant["description"]
        if "commit_ms" in first:
            if first.get("load_ms", TEST_LIMIT_MS + 1) > TEST_LIMIT_MS:
                timing = f"（{_server_timing(server[0])}）" if server else ""
                found.append(f"{name}：最初の読み込みは commit したが、load まで、テストの上限 {TEST_LIMIT_MS // 1000} 秒では足りない"
                             f"{timing}{where}")
            else:
                found.append(f"{name}：最初の読み込みは {first['load_ms']} ms で load まで進んだ（この実行では止まらなかった）")
        elif not server:
            found.append(f"{name}：最初の読み込みの要求がサーバーに届いていない（サーバーより手前：ブラウザ・プロキシの判定・"
                         f"セキュリティ製品など）{where}")
        else:
            request = server[0]
            started = (round(request["after_ms"] + request["response_start_ms"])
                       if request["response_start_ms"] is not None else None)
            if started is None:
                found.append(f"{name}：要求はサーバーに届いた（{request['after_ms']} ms）が、サーバーが応答を始めていない（サーバーの側）{where}")
            elif started > first.get("commit_limit_ms", COMMIT_SECONDS * 1000):
                found.append(f"{name}：要求はサーバーに届いた（{request['after_ms']} ms）が、応答の開始が {started} ms で、"
                             f"ブラウザが待つのをやめた後だった（サーバーの側の遅れ）{where}")
            else:
                found.append(f"{name}：サーバーは {started} ms に応答を始めたが、ブラウザが画面の遷移を確定していない（ブラウザの側）{where}")
    plain = results.get("plain") or {}
    if plain.get("error"):
        found.append(f"Playwright を使わない起動：{plain['error']}")
    elif plain:
        server = (plain.get("server") or {}).get("requests") or []
        netlog = plain.get("netlog") or []
        where = f"（NetLog：処理中だった段階 {netlog[0]['open_at_end'][0]}）" if netlog and netlog[0]["open_at_end"] else ""
        reached = [r for r in server if r["response_end_ms"] is not None]
        if reached:
            after = reached[0].get("after_ms")
            if after is None:
                text = "Playwright を使わない起動：サーバーに届き、応答が返った"
            else:
                ended = round(after + reached[0]["response_end_ms"])
                text = f"Playwright を使わない起動：起動から {after} ms でサーバーに届き、{ended} ms で応答が終わった"
                if ended > TEST_LIMIT_MS:
                    text += f"（テストの上限 {TEST_LIMIT_MS // 1000} 秒より遅い）"
            gap = (netlog[0].get("longest_gap") or {}) if netlog else {}
            if gap.get("ms", 0) >= 1000:
                text += f"（NetLog：最も長い間隔 {gap['after']} → {gap['before']} {gap['ms']} ms）"
            found.append(text)
        elif server:
            found.append(f"Playwright を使わない起動：要求はサーバーに届いたが、待つ間に応答が終わらなかった（サーバーの側）{where}")
        elif netlog:
            found.append(f"Playwright を使わない起動：ブラウザは要求したが、サーバーに届いていない{where}")
        else:
            found.append("Playwright を使わない起動：この URL の要求の記録がない（起動時の画面などで止まった可能性）"
                         + (f"。{plain['exited_early']}" if plain.get("exited_early") else ""))
    return found


def summary_rows(results: dict) -> list[tuple[str, str]]:
    rows = []
    python = results.get("python") or []
    if python:
        rows.append(("要約（Python）", "、".join(
            f"GET {p['path']}：" + (f"{p['status']}・{p['ms']} ms・HTML {yes(p.get('html'))}" if "status" in p
                                    else f"失敗（{p['error']}）") for p in python)))
    variants = results.get("variants") or []
    if results.get("launch_error"):
        rows.append(("要約（ブラウザ・最初の読み込み）", f"Playwright でブラウザを起動できなかった：{results['launch_error']}"))
    if variants:
        rows.append(("要約（ブラウザ・最初の読み込み）", "、".join(
            f"{v['description']}：{describe_load(v['loads'][0]) if v.get('loads') else v.get('error', '未実施')}"
            for v in variants)))
        rows.append(("要約（サーバーへの到達・最初の読み込み）", "、".join(
            f"{v['description']}：{describe_server_side(v['loads'][0].get('server') or {})}" for v in variants
            if v.get("loads"))))
    plain = results.get("plain") or {}
    if plain:
        rows.append(("要約（Playwright を使わない起動）", plain.get("error") or "。".join(
            x for x in (describe_server_side(plain.get("server") or {}), plain.get("exited_early")) if x)))
    for text in hints(results):
        rows.append(("見立て（記録からの分類。原因の確定ではありません）", text))
    return rows


def render(results: dict) -> str:
    lines = ["## 実ブラウザの最初の読み込みの診断（diagnose_navigation.py）", "",
             "**診断です。合否は判定しません。** 画面の検査はしません。テストの構成を外した実行を、受入の合格にはしません。", "",
             f"テストは読み込み全体（load まで）を {TEST_LIMIT_MS // 1000} 秒で打ち切ります。この診断は、読み込みがどこまで進むかを見るため、"
             f"commit まで、各コンテキストの最初の読み込みは {FIRST_COMMIT_SECONDS} 秒、ほかは {COMMIT_SECONDS} 秒、"
             f"その後の DOMContentLoaded・load を各 {STAGE_SECONDS} 秒まで待ちます（テストの時間の上限は変えていません）。", "",
             "| 項目 | 値 |", "|---|---|"]
    meta = results["meta"]
    for label, key in (("判定", "verdict"), ("開始", "started"), ("終了", "ended"), ("実行環境の区分", "env_label"),
                       ("OS", "os"), ("Python", "python"), ("Playwright", "playwright"), ("対象コミット", "commit"),
                       ("ブラウザの channel（指定）", "channel"), ("起動したブラウザ", "product"),
                       ("ブラウザの実行ファイル", "executable"), ("テスト用サーバー", "server"),
                       ("テストデータ", "data"), ("外部通信の試み（スタブの記録）", "violations"),
                       ("時間の上限", "limits")):
        lines.append(f"| {label} | {cell(meta.get(key, '-'))} |")
    for label, value in summary_rows(results):
        lines.append(f"| {label} | {cell(value)} |")
    if results.get("fatal"):
        lines.append(f"| 診断を続けられなかった理由 | {cell(results['fatal'])} |")

    lines += ["", "### 1. Python（httpx）からの GET", "",
              "| URL | 状態 | 時間 | バイト | HTML | 編集画面の要素 | エラー |", "|---|---|---|---|---|---|---|"]
    for p in results.get("python") or []:
        lines.append(f"| `{p['url']}` | {p.get('status', '-')} | {p.get('ms', '-')} ms | {p.get('bytes', '-')} "
                     f"| {yes(p.get('html'))} | {yes(p.get('edit_page'))} | {cell(p.get('error', ''))} |")

    lines += ["", "### 2・3. ブラウザ（Playwright）での読み込み", "",
              "各構成で新しいコンテキストを作り、テストと同じ順に `編集画面 → 一覧 → 編集画面` を開きました（時刻は開始の時刻）。", "",
              "| 構成 | 読み込み | Playwright から見た進み方 | サーバーの記録（読み込みの開始からの時間） | ブラウザの通信の記録（NetLog） | 画面 |",
              "|---|---|---|---|---|---|"]
    for v in results.get("variants") or []:
        if v.get("error"):
            lines.append(f"| {v['description']} | - | 実行できなかった：{cell(v['error'])} | - | - | - |")
        for item in v.get("loads") or []:
            shot = item.get("screenshot") or {}
            shot_text = shot.get("file") or f"保存できなかった：{shot.get('reason')}"
            netlog = "、".join(describe_netlog_request(x) for x in item.get("netlog") or []) or "対応する記録なし"
            lines.append(f"| {v['description']} | {item['started']} `{item['url']}` | {cell(describe_load(item))} "
                         f"| {cell(describe_server_side(item.get('server') or {}))} | {cell(netlog)} | {cell(shot_text)} |")
        extra = []
        if v.get("loads_skipped"):
            extra.append(v["loads_skipped"])
        if "page_check" in v:
            extra.append(f"ページの監視：CDP {v['page_check']['cdp']}、問題 {v['page_check']['problems'] or 'なし'}、"
                         f"既知の例外（favicon の 404） {v['page_check']['known_favicon_404']} 件")
        if "trace_file" in v:
            extra.append(f"trace：{v['trace_file']}")
        if extra:
            lines.append(f"| {v['description']} | （補足） | {cell('。'.join(extra))} | | | |")
    for note in (results.get("variants_skipped"), results.get("sandbox_skipped")):
        if note:
            lines += ["", f"注：{note}"]
    for key, launched in (results.get("launched") or {}).items():
        lines += ["", f"起動の引数（{key}。chrome://version から。名前だけ、パスは省略）："
                  + (cell(launched.get("error")) if launched.get("error") else
                     " ".join(f"`{s}`" for s in launched.get("switches") or []) or "（なし）")]

    plain = results.get("plain")
    lines += ["", "### 3. Playwright を使わない起動（新しい一時プロフィール、自動操作なし）", ""]
    if not plain:
        lines.append(results.get("plain_skipped") or "実行していません。")
    else:
        netlog = "、".join(describe_netlog_request(x) for x in plain.get("netlog") or []) or "この URL の要求の記録なし"
        lines += ["| 項目 | 値 |", "|---|---|",
                  f"| 実行ファイル | {cell(plain.get('executable'))} |",
                  f"| 開いた URL | `{plain.get('url')}`（{plain.get('started')}） |",
                  f"| 引数 | {cell(' '.join(plain.get('arguments') or []))} |",
                  f"| 待った時間 | {plain.get('waited_seconds', '-')} 秒（上限 {PLAIN_SECONDS} 秒） |",
                  f"| サーバーの記録（起動からの時間） | {cell(plain.get('error') or describe_server_side(plain.get('server') or {}))} |",
                  f"| ブラウザの通信の記録（NetLog） | {cell(netlog)} |",
                  f"| ブラウザの終了 | {cell(plain.get('exited_early') or '待つ間は動いていた')} |",
                  f"| 終了 | {cell(plain.get('closed', '-'))} |",
                  f"| 一時プロフィール | {cell(plain.get('profile', '-'))} |"]

    lines += ["", "### 4. テスト用サーバーの記録（全件。FTA_E2E_ACCESS_LOG）", "",
              "ヘッダー・本文は記録していません。client は User-Agent の種類だけです（python-httpx・browser・other）。", "",
              "| # | 受信 | client | 要求 | 記録 |", "|---|---|---|---|---|"]
    for item in results.get("server_requests") or []:
        query = f"?{item['query']}" if item["query"] else ""
        lines.append(f"| {item['n']} | {clock(item['time'])} | {item['client']} | {item['method']} `{item['path']}{query}` "
                     f"| {cell(describe_server_request(item))} |")

    lines += ["", "### ブラウザの通信の記録（NetLog）の要約", "",
              "テスト用サーバーへの要求だけを載せます（プロキシのホスト名、ほかのサイトの URL、ヘッダーは載せません）。", ""]
    for key, summary in (results.get("netlog") or {}).items():
        lines += [f"**{key}**（netlog-raw/{summary['file']}、{summary['state']}）", ""]
        configs = summary["proxy_config"]
        if configs:
            last = configs[-1]
            lines.append(f"- ブラウザが受け取ったプロキシの設定（{len(configs)} 件の記録の最後）：自動検出 {yes(last['auto_detect'])}、"
                         f"PAC {yes(last['pac_url'])}、固定のプロキシ {yes(last['fixed_proxy'])}、"
                         f"除外の一覧 {yes(last['bypass_list'])}（ループバックを含む：{yes(last['bypass_has_loopback'])}、"
                         f"<-loopback>：{yes(last['bypass_has_minus_loopback'])}）")
        else:
            lines.append("- ブラウザが受け取ったプロキシの設定の記録：なし")
        if summary["pac"]:
            runs = []
            for run in summary["pac"]:
                steps = "、".join(f"{s['step']} " + (f"{s['ms']} ms" if s["ms"] is not None else "終了の記録なし")
                                 + (f"（{s['net_error']}）" if s.get("net_error") else "") for s in run["steps"])
                total = f"{run['duration_ms']} ms" if run["duration_ms"] is not None else "終了の記録なし"
                runs.append(f"開始 {run['start_ms']} ms・所要 {total}" + (f"（{run['net_error']}）" if run["net_error"] else "")
                            + (f"：{steps}" if steps else ""))
            lines.append(f"- プロキシの自動検出・PAC の判定：{len(runs)} 回（" + "／".join(runs) + "）")
        else:
            lines.append("- プロキシの自動検出・PAC の判定の記録：なし")
        if summary["wpad_dhcp"]:
            dhcp = summary["wpad_dhcp"]
            lines.append(f"- WPAD（DHCP、Windows）の記録：{dhcp['events']} 件（{dhcp['start_ms']} ms から {dhcp['span_ms']} ms の間）")
        lines.append(f"- 有効なフィールドトライアル：{len(summary['field_trials'])} 件（名前は diagnose.json）")
        main = [r for r in summary["requests"] if r["request_type"] == "main frame"]
        others = [r for r in summary["requests"] if r["request_type"] != "main frame"]
        unusual = [r for r in others if not r["ended"] or r["net_error"] or not r["headers_received"]]
        lines.append(f"- テスト用サーバーへの要求：{len(summary['requests'])} 件（画面の遷移 {len(main)} 件、"
                     f"ほか {len(others)} 件。ほかのうち正常に終わらなかったもの {len(unusual)} 件）")
        if main or unusual:
            lines += ["", "| 記録の開始から | URL | 種類 | 内容 |", "|---|---|---|---|"]
            for item in main + unusual[:10]:
                lines.append(f"| {item['start_ms']} ms | `{item['url']}` | {item['request_type']} "
                             f"| {cell(describe_netlog_request(item))} |")
        lines.append("")

    facts = results.get("windows") or {}
    proxy = facts.get("proxy") or {}
    lines += ["### Windows の設定（読み取りだけ。値は記録しない）", "",
              f"- プロキシ関係の環境変数（設定のあるもの）：{'、'.join(proxy.get('environment_variables') or []) or 'なし'}"]
    if "windows" in proxy:
        lines.append(f"- {proxy['windows']}")
    else:
        for key, title in (("user", "利用者（HKCU）のインターネット設定"), ("machine", "コンピューター（HKLM）のインターネット設定")):
            lines.append(f"- {title}：{cell(describe_internet_settings(proxy.get(key) or {'error': '記録なし'}))}")
        per_user = proxy.get("per_user_policy")
        lines.append("- プロキシの設定をコンピューター単位にするポリシー（ProxySettingsPerUser）："
                     + ("設定なし" if per_user is None else str(per_user)))
        lines.append(f"- WinHTTP のプロキシ：{proxy.get('winhttp', '-')}")
    policies = facts.get("policies") or {}
    if "windows" in policies:
        lines.append(f"- ブラウザのポリシー：{policies['windows']}")
    else:
        for hive in ("HKLM", "HKCU"):
            lines.append(f"- ブラウザのポリシーの名前（{hive}）：{cell('、'.join(policies.get(hive) or []) or 'なし')}")
    lines.append("")

    lines += ["### ファイル", ""]
    for name, text in results.get("files") or []:
        lines.append(f"- `{name}`：{text}")
    lines.append("")
    return "\n".join(lines)


def list_files(out: pathlib.Path) -> list[tuple[str, str]]:
    notes = {
        "diagnose-report.md": "この記録",
        "diagnose.json": "同じ内容（機械で読む形。NetLog の要約の時系列を含む）",
        "server-access.jsonl": "テスト用サーバーの受信・応答の記録（ヘッダー・本文なし）",
        "server": "テスト用サーバーの作業フォルダ（この診断の一時 DB・server.log）",
        "netlog-raw": "ブラウザの通信の記録の原本（ほかのサイトの URL やプロキシの設定を含む。依頼があるときだけ渡す）",
    }
    files = []
    for path in sorted(out.iterdir()):
        name = path.name + ("/" if path.is_dir() else "")
        if path.name in notes:
            files.append((name, notes[path.name]))
        elif path.suffix == ".png":
            files.append((name, f"読み込みの終わりの画面（{path.stat().st_size} バイト）"))
        elif path.suffix == ".zip":
            files.append((name, "Playwright の trace（手元で show-trace で開く）"))
        else:
            files.append((name, ""))
    return files


def _commit() -> str:
    try:
        head = subprocess.run(["git", "-C", str(FTA_TOOL_DIR), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(FTA_TOOL_DIR), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        return f"取得できなかった（{first_line(error)}）"
    if not head:
        return "取得できなかった"
    return f"{head}（{'追跡中のファイルに未コミットの変更あり' if dirty else '未コミットの変更なし'}）"


# ----- main ---------------------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="実ブラウザの最初の読み込みの診断（合否は判定しない）")
    parser.add_argument("--out", required=True, help="記録を書く新しいフォルダ（空であること）")
    parser.add_argument("--channel", default="chrome", choices=("chrome", "msedge", "chromium"),
                        help="chromium は Playwright 同梱の Chromium（開発環境での確認用）")
    parser.add_argument("--env-label", default="未指定", help="実行環境の区分（記録に書く）")
    parser.add_argument("--all-variants", action="store_true",
                        help="結果にかかわらず、ページの監視だけ・trace だけ・サンドボックスありも試す")
    parser.add_argument("--skip-plain", action="store_true", help="Playwright を使わない起動を試さない")
    args = parser.parse_args(argv)

    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        print(f"記録フォルダが空ではありません：{out}", file=sys.stderr)
        return 2
    (out / "netlog-raw").mkdir()

    from importlib import metadata

    from tests.e2e.support import free_port, start_server

    channel = None if args.channel == "chromium" else args.channel
    results: dict = {"meta": {
        "verdict": "診断（合否は判定しません）",
        "started": now_text(),
        "env_label": args.env_label,
        "os": platform.platform(),
        "python": platform.python_version(),
        "playwright": metadata.version("playwright"),
        "commit": _commit(),
        "channel": args.channel,
        "limits": (f"commit {FIRST_COMMIT_SECONDS} 秒（各コンテキストの最初の読み込み）・{COMMIT_SECONDS} 秒（ほか）、"
                   f"DOMContentLoaded・load 各 {STAGE_SECONDS} 秒、画面 {SCREENSHOT_MS // 1000} 秒、"
                   f"Python の GET {HTTPX_SECONDS} 秒、Playwright を使わない起動 {PLAIN_SECONDS} 秒"
                   f"（テストは読み込み全体で {TEST_LIMIT_MS // 1000} 秒）"),
    }}
    access_log = out / "server-access.jsonl"
    server = None
    exit_code = 0
    try:
        progress("Windows の設定（読み取りだけ）")
        results["windows"] = {"proxy": windows_proxy_settings(), "policies": browser_policy_names(args.channel)}

        progress("テスト用サーバー（新しい一時 DB、空いているポート）")
        workdir = out / "server"
        workdir.mkdir()
        server = start_server(workdir, free_port(), extra_env={"FTA_E2E_ACCESS_LOG": str(access_log)})
        analysis_id = server.create_analysis("診断：最初の読み込み", top_event="頂上事象（診断）")
        first = server.add_level1(analysis_id, "一次要因A")
        server.add_child(first, "二次要因B")
        server.add_level1(analysis_id, "一次要因D")
        results["meta"]["server"] = f"{server.url}（AI: e2e-stub、作業フォルダ server/）"
        results["meta"]["data"] = f"分析 {analysis_id}（要因 3件）。Python の API で作成"

        progress("1. Python（httpx）から GET")
        results["python"] = []
        for path in ("/", f"/analyses/{analysis_id}"):
            item = python_get(server.url + path)
            item["path"] = path
            results["python"].append(item)

        from playwright.sync_api import sync_playwright

        variants: list = []
        results["variants"] = variants
        results["launched"] = {}
        netlogs = {"Playwright で起動したブラウザ": out / "netlog-raw" / "playwright.json"}
        with sync_playwright() as p:
            progress("2・3. ブラウザ（Playwright）を起動")
            try:
                browser = launch(p, channel, netlogs["Playwright で起動したブラウザ"], sandbox=False)
            except Exception as error:  # noqa: BLE001 - recorded; the browser without Playwright is still tried
                results["launch_error"] = f"{type(error).__name__}: {first_line(error)}"
                browser = None
            try:
                if browser is None:
                    raise _NotLaunched
                info = describe_launched(browser)
                results["launched"]["Playwright の既定"] = info
                results["meta"]["product"] = info["product"]
                results["meta"]["executable"] = info["executable"]
                for key in ("minimal", "tests"):
                    try:
                        variants.append(run_variant(browser, key, server.url, analysis_id, out))
                    except Exception as error:  # noqa: BLE001
                        variants.append({"key": key, "description": VARIANTS[key][0], "error": first_line(error)})
                if args.all_variants or committed(variants[0]) != committed(variants[1]):
                    for key in ("watch", "trace"):
                        try:
                            variants.append(run_variant(browser, key, server.url, analysis_id, out))
                        except Exception as error:  # noqa: BLE001
                            variants.append({"key": key, "description": VARIANTS[key][0], "error": first_line(error)})
                else:
                    results["variants_skipped"] = ("最小とテストの構成で、最初の読み込みの結果（commit の到達）が同じだったため、"
                                                   "ページの監視だけ・trace だけの構成は試していません（--all-variants で試せます）。")
            except _NotLaunched:
                pass
            finally:
                if browser is not None:
                    browser.close()
            if browser is None:
                results["sandbox_skipped"] = "Playwright でブラウザを起動できなかったため、サンドボックスありの起動は試していません。"
            elif args.all_variants or not committed(variants[0]):
                progress("ブラウザ：サンドボックスあり（診断だけ）で起動")
                netlogs["サンドボックスありで起動したブラウザ"] = out / "netlog-raw" / "playwright-sandbox.json"
                try:
                    browser = launch(p, channel, netlogs["サンドボックスありで起動したブラウザ"], sandbox=True)
                except Exception as error:  # noqa: BLE001 - e.g. Linux as root
                    root = " （Linux の root ではサンドボックスありで起動できない）" if os.name == "posix" and os.geteuid() == 0 else ""
                    variants.append({"key": "sandbox", "description": VARIANTS["sandbox"][0],
                                     "error": f"起動できなかった：{first_line(error)}{root}"})
                else:
                    try:
                        results["launched"]["サンドボックスあり"] = describe_launched(browser)
                        variants.append(run_variant(browser, "sandbox", server.url, analysis_id, out, first_only=True))
                    except Exception as error:  # noqa: BLE001
                        variants.append({"key": "sandbox", "description": VARIANTS["sandbox"][0], "error": first_line(error)})
                    finally:
                        browser.close()
            else:
                results["sandbox_skipped"] = ("最小の構成で最初の読み込みが commit に到達したため、サンドボックスありの起動は"
                                              "試していません（--all-variants で試せます）。")

        executable = results["meta"].get("executable")
        if channel and (not executable or executable == "-" or not pathlib.Path(executable).exists()):
            executable = find_installed_browser(args.channel)
        if args.skip_plain:
            results["plain_skipped"] = "--skip-plain のため、Playwright を使わない起動は試していません。"
        elif executable and executable != "-" and pathlib.Path(executable).exists():
            netlogs["Playwright を使わない起動"] = out / "netlog-raw" / "plain.json"
            results["plain"] = plain_browser(executable, args.channel, f"{server.url}/analyses/{analysis_id}",
                                             f"/analyses/{analysis_id}", out, access_log)
        else:
            results["plain_skipped"] = "ブラウザの実行ファイルが分からないため、Playwright を使わない起動は試していません。"

        progress("記録をまとめています（NetLog の要約）")
        requests = access_requests(read_access_log(access_log))
        results["server_requests"] = requests
        results["netlog"] = {key: summarize_netlog(path, server.url) for key, path in netlogs.items() if path.exists()}
        for variant in variants:
            for item in variant.get("loads") or []:
                path = item["url"].removeprefix(server.url)
                item["server"] = server_side(requests, path, item["window"][0], item["window"][1], "browser")
                item["netlog"] = netlog_for(results["netlog"], item["url"], item["window"])
        plain = results.get("plain")
        if plain and "window" in plain:
            plain["server"] = server_side(requests, f"/analyses/{analysis_id}", plain["window"][0],
                                          plain["window"][1], "browser", margin=0)
            plain["netlog"] = netlog_for({k: v for k, v in results["netlog"].items() if k == "Playwright を使わない起動"},
                                         plain["url"], plain["window"])
        violations = server.violations()
        results["meta"]["violations"] = (f"{len(violations)} 件" + (f"（{violations[0].get('message')}）" if violations else "")
                                         + "（stub_server の遮断の記録 violations.jsonl）")
    except Exception as error:  # noqa: BLE001 - the report says how far it got
        results["fatal"] = f"{type(error).__name__}: {first_line(error)}"
        exit_code = 1
    finally:
        if server is not None:
            server.close()
        results["meta"]["ended"] = now_text()
        for item in [*(i for v in results.get("variants") or [] for i in v.get("loads") or []),
                     results.get("plain") or {}]:
            item.pop("window", None)
        results["files"] = []
        (out / "diagnose.json").write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str),
                                           encoding="utf-8")
        report = out / "diagnose-report.md"
        report.write_text(render(results), encoding="utf-8")
        results["files"] = list_files(out)
        report.write_text(render(results), encoding="utf-8")
        progress(f"終わりました：{report}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
