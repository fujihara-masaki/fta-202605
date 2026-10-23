"""The diagnosis of the first page load (tests/e2e/diagnose_navigation.py,
the Windows Chrome preflight of 2026-10-05) without a browser:

* the test server's record of each request (tests/e2e/stub_server.py,
  FTA_E2E_ACCESS_LOG, the diagnosis only): received, response started and
  ended, a client that went away, an error; no header and no body; the
  request and the response are passed on unchanged;
* the summary of the browser's NetLog: only the requests to the test server,
  where each one waited (e.g. for the automatic proxy detection of a new
  context), the local network check, the response headers' status line;
  never another site's URL, a proxy's name, a header or a PAC URL; the links
  are followed from a request to its connection only (a shared socket does
  not bring other requests in); a log the browser did not close is read;
* the first reading of the records (a cause is never claimed): not reached,
  a late answer of the server, an answer the browser did not take, a slow
  load; the report is a diagnosis, never a pass.
"""

from __future__ import annotations

import asyncio
import json
import threading

import pytest

from tests.e2e import diagnose_navigation as diag
from tests.e2e.stub_server import AccessLog

ORIGIN = "http://127.0.0.1:50123"
OFFSET = 1_790_000_000_000  # timeTickOffset: the NetLog's ticks plus this are milliseconds since 1970


# ----- the test server's record --------------------------------------------------------

def run_asgi(app, scope, messages=()):
    """Run the ASGI app once, in a thread of its own: in the whole test run the
    browser tests' Playwright (sync API) keeps an event loop in this thread."""
    queue, sent, raised = list(messages), [], []

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    def run():
        try:
            asyncio.run(app(scope, receive, send))
        except BaseException as error:  # noqa: BLE001 - raised again in the test's thread
            raised.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=30)
    assert not thread.is_alive(), "the ASGI app did not finish"
    if raised:
        raise raised[0]
    return sent


def http_scope(agent: bytes = b"Mozilla/5.0 (Windows NT 10.0) Chrome/154.0", path: str = "/analyses/1"):
    return {"type": "http", "method": "GET", "path": path, "query_string": b"step=2",
            "headers": [(b"user-agent", agent), (b"cookie", b"session=secret-cookie")],
            "client": ("127.0.0.1", 61000)}


def read(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_the_server_records_arrival_and_response_without_headers_or_body(tmp_path):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"set-cookie", b"x=secret")]})
        await send({"type": "http.response.body", "body": b"<html>secret body", "more_body": True})
        await send({"type": "http.response.body", "body": b"</html>"})

    log = tmp_path / "access.jsonl"
    sent = run_asgi(AccessLog(app, log), http_scope())
    assert [m.get("status") or m.get("body") for m in sent] == [200, b"<html>secret body", b"</html>"]  # unchanged
    events = read(log)
    assert [e["event"] for e in events] == ["received", "response_start", "response_end"]
    assert events[1]["status"] == 200 and events[2]["bytes"] == len(b"<html>secret body</html>")
    assert {(e["n"], e["method"], e["path"], e["client"], e["client_port"]) for e in events} == {
        (1, "GET", "/analyses/1", "browser", 61000)}
    text = log.read_text(encoding="utf-8")
    assert "secret" not in text and "cookie" not in text.lower() and "Mozilla" not in text and "step=2" not in text


@pytest.mark.parametrize("agent, kind", [(b"python-httpx/0.27.0", "python-httpx"), (b"curl/8.0", "other"), (b"", "none")])
def test_the_server_records_only_the_kind_of_client(tmp_path, agent, kind):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 204})
        await send({"type": "http.response.body", "body": b""})

    log = tmp_path / "access.jsonl"
    run_asgi(AccessLog(app, log), http_scope(agent))
    assert {e["client"] for e in read(log)} == {kind}


def test_the_server_records_a_client_gone_and_an_error(tmp_path):
    async def waits(scope, receive, send):
        await receive()  # the browser went away before an answer

    log = tmp_path / "access.jsonl"
    run_asgi(AccessLog(waits, log), http_scope())
    assert [e["event"] for e in read(log)] == ["received", "client_disconnected"]

    async def fails(scope, receive, send):
        raise RuntimeError("secret detail")

    log = tmp_path / "error.jsonl"
    with pytest.raises(RuntimeError):
        run_asgi(AccessLog(fails, log), http_scope())
    events = read(log)
    assert [e["event"] for e in events] == ["received", "error"] and events[1]["error"] == "RuntimeError"
    assert "secret" not in log.read_text(encoding="utf-8")


def test_other_messages_pass_without_a_record(tmp_path):
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    log = tmp_path / "access.jsonl"
    run_asgi(AccessLog(app, log), {"type": "lifespan"})
    assert seen == ["lifespan"] and not log.exists()


def test_the_servers_times_are_told_from_the_start_of_the_load():
    events = [
        {"event": "received", "time": 100.010, "ms": 0, "n": 3, "method": "GET", "path": "/analyses/1", "query": "",
         "client": "browser"},
        {"event": "response_start", "time": 145.010, "ms": 45000.0, "n": 3, "status": 200},
        {"event": "response_end", "time": 145.012, "ms": 45002.0, "n": 3, "bytes": 32662},
        {"event": "received", "time": 99.0, "ms": 0, "n": 2, "method": "GET", "path": "/analyses/1", "query": "",
         "client": "browser"},
    ]
    requests = diag.access_requests(events)
    seen = diag.server_side(requests, "/analyses/1", 100.0, 130.0, "browser")
    assert [r["n"] for r in seen["requests"]] == [3]  # the one before the load is another load's
    assert diag.describe_server_side(seen) == "受信 10 ms・応答の開始 45010 ms（200）・終了 45012 ms（32662 バイト）"
    assert diag.describe_server_side({"requests": []}).startswith("受信なし")


# ----- the browser's network log (NetLog) ------------------------------------------------

TYPES = ["REQUEST_ALIVE", "URL_REQUEST_START_JOB", "HTTP_STREAM_REQUEST", "HTTP_STREAM_JOB_CONTROLLER_BOUND",
         "HTTP_STREAM_JOB_CONTROLLER", "PROXY_RESOLUTION_SERVICE", "PROXY_RESOLUTION_SERVICE_WAITING_FOR_INIT_PAC",
         "PROXY_RESOLUTION_SERVICE_RESOLVED_PROXY_LIST", "CANCELLED", "PROXY_CONFIG_CHANGED", "PAC_FILE_DECIDER",
         "PAC_FILE_DECIDER_FETCH_PAC_SCRIPT", "LOCAL_NETWORK_ACCESS_CHECK", "URL_REQUEST_DELEGATE_CONNECTED",
         "HTTP_TRANSACTION_READ_RESPONSE_HEADERS", "URL_REQUEST_JOB_FILTERED_BYTES_READ", "SOCKET_IN_USE",
         "TCP_CONNECT", "HTTP_STREAM_REQUEST_BOUND_TO_JOB", "HTTP_STREAM_JOB"]
SOURCES = ["NONE", "URL_REQUEST", "HTTP_STREAM_JOB_CONTROLLER", "HTTP_STREAM_JOB", "SOCKET", "PAC_FILE_DECIDER"]


class NetLog:
    """A browser's --log-net-log file with the events the summary reads."""

    def __init__(self):
        self.events: list[dict] = []

    def add(self, source_id: int, kind: str, time: int, name: str, phase: int = 0, **params) -> None:
        event = {"source": {"id": source_id, "type": SOURCES.index(kind)}, "time": str(time),
                 "type": TYPES.index(name), "phase": phase}
        if params:
            event["params"] = params
        self.events.append(event)

    def write(self, path, closed: bool = True):
        text = json.dumps({"constants": {
            "logEventTypes": {name: index for index, name in enumerate(TYPES)},
            "logSourceType": {name: index for index, name in enumerate(SOURCES)},
            "logEventPhase": {"PHASE_NONE": 0, "PHASE_BEGIN": 1, "PHASE_END": 2},
            "netError": {"ERR_ABORTED": -3, "ERR_TIMED_OUT": -7, "ERR_NAME_NOT_RESOLVED": -105},
            "timeTickOffset": str(OFFSET),
            "activeFieldTrialGroups": ["SomeTrial:Group1"],
        }, "events": self.events})
        path.write_text(text if closed else text[:-2] + ",\n", encoding="utf-8")  # not closed: no "]}"
        return path


def waiting_for_the_proxy_detection() -> NetLog:
    """The first load of a new context waits for the automatic proxy
    detection (WPAD) and is cancelled after 30 seconds; another site's
    request goes through a proxy meanwhile."""
    log = NetLog()
    log.add(1, "NONE", 100, "PROXY_CONFIG_CHANGED", new_config={"auto_detect": True})
    log.add(2, "PAC_FILE_DECIDER", 100, "PAC_FILE_DECIDER", 1)
    log.add(2, "PAC_FILE_DECIDER", 100, "PAC_FILE_DECIDER_FETCH_PAC_SCRIPT", 1, source="WPAD DHCP")
    log.add(2, "PAC_FILE_DECIDER", 2100, "PAC_FILE_DECIDER_FETCH_PAC_SCRIPT", 2, net_error=-7)
    log.add(2, "PAC_FILE_DECIDER", 2100, "PAC_FILE_DECIDER_FETCH_PAC_SCRIPT", 1, source="WPAD DNS: http://wpad/wpad.dat")
    url = ORIGIN + "/analyses/1"
    log.add(10, "URL_REQUEST", 1000, "REQUEST_ALIVE", 1, url=url)
    log.add(10, "URL_REQUEST", 1000, "URL_REQUEST_START_JOB", 1, url=url, method="GET", request_type="main frame")
    log.add(10, "URL_REQUEST", 1001, "HTTP_STREAM_REQUEST", 1)
    log.add(10, "URL_REQUEST", 1001, "HTTP_STREAM_JOB_CONTROLLER_BOUND", source_dependency={"id": 11, "type": 2})
    log.add(11, "HTTP_STREAM_JOB_CONTROLLER", 1001, "HTTP_STREAM_JOB_CONTROLLER", 1, url=url)
    log.add(11, "HTTP_STREAM_JOB_CONTROLLER", 1001, "PROXY_RESOLUTION_SERVICE", 1)
    log.add(11, "HTTP_STREAM_JOB_CONTROLLER", 1001, "PROXY_RESOLUTION_SERVICE_WAITING_FOR_INIT_PAC", 1)
    log.add(20, "URL_REQUEST", 1500, "REQUEST_ALIVE", 1, url="https://intranet.example.co.jp/secret")
    log.add(20, "URL_REQUEST", 1500, "HTTP_STREAM_JOB_CONTROLLER_BOUND", source_dependency={"id": 21, "type": 2})
    log.add(21, "HTTP_STREAM_JOB_CONTROLLER", 1500, "PROXY_RESOLUTION_SERVICE_RESOLVED_PROXY_LIST",
            proxy_info="PROXY corp-proxy.example.co.jp:8080")
    log.add(10, "URL_REQUEST", 31001, "CANCELLED", net_error=-3)
    log.add(11, "HTTP_STREAM_JOB_CONTROLLER", 31001, "PROXY_RESOLUTION_SERVICE_WAITING_FOR_INIT_PAC", 2)
    log.add(11, "HTTP_STREAM_JOB_CONTROLLER", 31001, "PROXY_RESOLUTION_SERVICE", 2, net_error=-3)
    log.add(10, "URL_REQUEST", 31001, "HTTP_STREAM_REQUEST", 2)
    log.add(10, "URL_REQUEST", 31001, "URL_REQUEST_START_JOB", 2, net_error=-3)
    log.add(10, "URL_REQUEST", 31001, "REQUEST_ALIVE", 2, net_error=-3)
    log.add(2, "PAC_FILE_DECIDER", 32000, "PAC_FILE_DECIDER_FETCH_PAC_SCRIPT", 2, net_error=-105)
    log.add(2, "PAC_FILE_DECIDER", 32000, "PAC_FILE_DECIDER", 2, net_error=-105)
    return log


def test_the_summary_says_where_the_request_waited(tmp_path):
    summary = diag.summarize_netlog(waiting_for_the_proxy_detection().write(tmp_path / "playwright.json"), ORIGIN)
    assert summary["state"] == "完全" and summary["field_trials"] == ["SomeTrial:Group1"]
    assert summary["proxy_config"][-1]["auto_detect"] and not summary["proxy_config"][-1]["fixed_proxy"]
    detection = summary["pac"][0]
    assert detection["duration_ms"] == 31900 and detection["net_error"] == "ERR_NAME_NOT_RESOLVED"
    assert [(s["step"], s["ms"], s["net_error"]) for s in detection["steps"]] == [
        ("WPAD（DHCP）", 2000, "ERR_TIMED_OUT"), ("WPAD（DNS）", 29900, "ERR_NAME_NOT_RESOLVED")]
    assert [r["url"] for r in summary["requests"]] == [ORIGIN + "/analyses/1"]  # the test server's only
    request = summary["requests"][0]
    assert request["request_type"] == "main frame" and request["epoch"] == (1000 + OFFSET) / 1000
    assert request["ended"] and request["cancelled"] and request["net_error"] == "ERR_ABORTED"
    assert request["duration_ms"] == 30001 and not request["headers_received"]
    assert request["open_at_end"][0] == ("プロキシの自動検出・PAC の準備の完了待ち"
                                         "（PROXY_RESOLUTION_SERVICE_WAITING_FOR_INIT_PAC、1 ms から）")
    assert request["longest_gap"]["ms"] == 30000 and request["longest_gap"]["before"] == "取り消し"
    text = diag.describe_netlog_request(request)
    assert text.startswith("プロキシ （記録なし）・応答ヘッダー 受信なし・終了 30001 ms（ERR_ABORTED）・取り消し。")
    assert "取り消しの時点で処理中の段階（内側から）：プロキシの自動検出・PAC の準備の完了待ち" in text
    dumped = json.dumps(summary, ensure_ascii=False)
    assert "intranet" not in dumped and "corp-proxy" not in dumped and "wpad.dat" not in dumped


def two_requests_over_one_connection() -> NetLog:
    """Two answered requests of the test server sharing one socket, which
    links back to both of them."""
    log = NetLog()
    log.add(40, "SOCKET", 50, "TCP_CONNECT", 1, address="127.0.0.1:50123")
    log.add(40, "SOCKET", 51, "TCP_CONNECT", 2, local_address="127.0.0.1:61000", remote_address="127.0.0.1:50123")
    for request, job, path, start in ((30, 32, "/static/a.css", 100), (50, 52, "/static/b.css", 200)):
        log.add(request, "URL_REQUEST", start, "REQUEST_ALIVE", 1, url=ORIGIN + path)
        log.add(request, "URL_REQUEST", start, "URL_REQUEST_START_JOB", 1, url=ORIGIN + path, request_type="other")
        log.add(request, "URL_REQUEST", start + 1, "HTTP_STREAM_REQUEST_BOUND_TO_JOB",
                source_dependency={"id": job, "type": 3})
        log.add(job, "HTTP_STREAM_JOB", start + 1, "HTTP_STREAM_JOB", 1, source_dependency={"id": 40, "type": 4})
        log.add(40, "SOCKET", start + 1, "SOCKET_IN_USE", 1, source_dependency={"id": job, "type": 3})
        log.add(request, "URL_REQUEST", start + 2, "URL_REQUEST_DELEGATE_CONNECTED", 1)
        log.add(request, "URL_REQUEST", start + 2, "LOCAL_NETWORK_ACCESS_CHECK", result="allowed-potentially-trustworthy",
                client_address_space="loopback", resource_address_space="loopback")
        log.add(request, "URL_REQUEST", start + 2, "URL_REQUEST_DELEGATE_CONNECTED", 2)
        log.add(request, "URL_REQUEST", start + 5, "HTTP_TRANSACTION_READ_RESPONSE_HEADERS",
                headers=["HTTP/1.1 200 OK", "set-cookie: session=secret-cookie"])
        log.add(request, "URL_REQUEST", start + 6, "URL_REQUEST_JOB_FILTERED_BYTES_READ", byte_count=1234)
        log.add(request, "URL_REQUEST", start + 6, "REQUEST_ALIVE", 2)
    return log


def test_a_shared_connection_does_not_bring_in_the_other_request(tmp_path):
    summary = diag.summarize_netlog(two_requests_over_one_connection().write(tmp_path / "n.json"), ORIGIN)
    first, second = summary["requests"]
    assert (first["url"], second["url"]) == (ORIGIN + "/static/a.css", ORIGIN + "/static/b.css")
    for request in (first, second):
        jobs = [e for e in request["timeline"] if e["event"] == "HTTP_STREAM_JOB"]
        assert len(jobs) == 1  # its own job; the socket's link back to the other job is not followed
        assert {"remote_address": "127.0.0.1:50123", "local_address": "127.0.0.1:61000"}.items() <= next(
            e for e in request["timeline"] if e["event"] == "TCP_CONNECT" and e["phase"] == "終了").items()
    assert not any(e.get("url") == ORIGIN + "/static/b.css" for e in first["timeline"])
    assert first["headers_received"] and first["status_line"] == "HTTP/1.1 200 OK" and first["bytes"] == 1234
    assert first["lna"] == [{"result": "allowed-potentially-trustworthy", "client_address_space": "loopback",
                             "resource_address_space": "loopback"}] and not first["lna_permission"]
    assert diag.describe_netlog_request(first) == (
        "プロキシ （記録なし）・ローカルネットワークの確認 allowed-potentially-trustworthy（loopback→loopback）・"
        "応答ヘッダー HTTP/1.1 200 OK・終了 6 ms")
    assert "secret" not in json.dumps(summary, ensure_ascii=False)


def test_a_log_the_browser_did_not_close_is_still_read(tmp_path):
    path = waiting_for_the_proxy_detection().write(tmp_path / "plain.json", closed=False)
    summary = diag.summarize_netlog(path, ORIGIN)
    assert summary["state"] == "末尾を補って読んだ（ブラウザが正常に閉じなかった）" and len(summary["requests"]) == 1
    assert diag.summarize_netlog(tmp_path / "missing.json", ORIGIN)["state"] == "ファイルがない"
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert diag.summarize_netlog(tmp_path / "broken.json", ORIGIN)["state"] == "読めない"


def test_only_what_describes_the_request_is_kept():
    errors = {-3: "ERR_ABORTED"}
    assert diag._safe_params({"address": "10.1.2.3:8080", "url": "https://example.com/"}, ORIGIN, errors) == {}
    assert diag._safe_params({"url": ORIGIN + "0/x"}, ORIGIN, errors) == {}  # another port, not this server
    assert diag._safe_params({"address": "127.0.0.1:50123", "net_error": -3}, ORIGIN, errors) == {
        "address": "127.0.0.1:50123", "net_error": "ERR_ABORTED"}
    assert diag._safe_params({"proxy_info": "PROXY corp:8080", "proxy_chain": "[corp:8080]"}, ORIGIN, errors) == {
        "proxy_info": "PROXY（ホスト名は省略）", "proxy_chain": "（プロキシ。ホスト名は省略）"}
    assert diag._safe_params({"source": "Custom PAC URL: http://corp/proxy.pac", "headers": ["cookie: x"]},
                             ORIGIN, errors) == {"source": "指定の PAC（URL は省略）"}


def test_the_winhttp_setting_is_read_in_either_language_and_code_page():
    japanese_direct = "現在の WinHTTP プロキシ設定:\r\n\r\n    直接アクセス (プロキシ サーバーなし)。\r\n"
    assert diag.winhttp_proxy(japanese_direct.encode("cp932")) == "直接（プロキシなし）"
    assert diag.winhttp_proxy(japanese_direct.encode("utf-8")) == "直接（プロキシなし）"
    assert diag.winhttp_proxy(b"Current WinHTTP proxy settings:\r\n\r\n    Direct access (no proxy server).\r\n") \
        == "直接（プロキシなし）"
    japanese_proxy = "    プロキシ サーバー:  proxy.example.co.jp:8080\r\n    バイパス一覧     :  (なし)\r\n"
    assert diag.winhttp_proxy(japanese_proxy.encode("cp932")) == "プロキシの設定あり（内容は記録しない）"
    assert diag.winhttp_proxy(b"    Proxy Server(s) :  proxy:8080\r\n") == "プロキシの設定あり（内容は記録しない）"
    assert diag.winhttp_proxy(b"") == "判断できなかった（出力の形が想定と違う）"


def test_a_load_gets_the_netlog_entry_of_its_own_time():
    entry = {"url": ORIGIN + "/analyses/1", "request_type": "main frame", "epoch": 1000.02}
    summaries = {"Playwright": {"requests": [entry, {**entry, "epoch": 999.0}, {**entry, "request_type": "other"}]}}
    assert diag.netlog_for(summaries, ORIGIN + "/analyses/1", (1000.0, 1001.0)) == [entry]


# ----- the first reading and the report ---------------------------------------------------

def first_load(**fields) -> dict:
    return {"name": "minimal-1-edit", "url": ORIGIN + "/analyses/1", "started": "10:00:00.000",
            "page_url": "about:blank", "events": [], "document": {"request_ms": 5.0}, **fields}


def variant(load: dict) -> dict:
    return {"key": "minimal", "description": "最小", "loads": [load]}


def pending_netlog(stage: str) -> list[dict]:
    return [{"open_at_end": [stage], "longest_gap": {"ms": 30000, "after": "a", "before": "b", "from_ms": 1}}]


def test_the_first_reading_tells_where_the_load_stopped():
    not_reached = first_load(commit_error="30 秒で未到達", server={"requests": []},
                             netlog=pending_netlog("プロキシの自動検出・PAC の準備の完了待ち（…、1 ms から）"))
    late = first_load(commit_error="30 秒で未到達", commit_limit_ms=30000, server={"requests": [
        {"after_ms": 8, "response_start_ms": 45000.0, "response_end_ms": 45002.0}]})
    taken_not = first_load(commit_error="30 秒で未到達", server={"requests": [
        {"after_ms": 8, "response_start_ms": 12.0, "response_end_ms": 15.0}]})
    slow = first_load(commit_ms=25000.0, dcl_ms=25100.0, load_ms=25200.0, server={"requests": [
        {"after_ms": 24800, "response_start_ms": 5.0, "response_end_ms": 6.0}]},
                      netlog=[{"open_at_end": [], "longest_gap": {"ms": 24900, "after": "プロキシの自動検出・PAC の準備の完了待ちの開始",
                                                                  "before": "プロキシの自動検出・PAC の準備の完了待ちの終了", "from_ms": 1}}])
    fine = first_load(commit_ms=30.0, dcl_ms=200.0, load_ms=210.0, server={"requests": []})
    results = {"python": [{"path": "/analyses/1", "error": "ReadTimeout: timed out", "ms": 30000.0}],
               "variants": [variant(load) for load in (not_reached, late, taken_not, slow, fine)]}
    found = diag.hints(results)
    assert found[0].startswith("Python からの編集画面の GET が失敗した（ReadTimeout: timed out）")
    assert "最初の読み込みの要求がサーバーに届いていない" in found[1] and "プロキシの自動検出・PAC の準備の完了待ち" in found[1]
    assert "応答の開始が 45008 ms で、ブラウザが待つのをやめた後だった（サーバーの側の遅れ）" in found[2]
    assert "サーバーは 20 ms に応答を始めたが、ブラウザが画面の遷移を確定していない（ブラウザの側）" in found[3]
    assert "テストの上限 10 秒では足りない（サーバーの受信 24800 ms・応答の開始 24805 ms）（NetLog：最も長い間隔" in found[4]
    assert "210.0 ms で load まで進んだ（この実行では止まらなかった）" in found[5]


def test_a_browser_playwright_could_not_start_is_read_as_such():
    results = {"launch_error": "Error: BrowserType.launch: Chromium distribution 'chrome' is not found"}
    assert diag.hints(results) == ["Playwright でブラウザを起動できなかった（Error: BrowserType.launch: "
                                   "Chromium distribution 'chrome' is not found）"]
    assert ("要約（ブラウザ・最初の読み込み）", "Playwright でブラウザを起動できなかった：Error: BrowserType.launch: "
            "Chromium distribution 'chrome' is not found") in diag.summary_rows(results)


def test_the_first_reading_of_the_browser_started_without_playwright():
    def reading(plain):
        return diag.hints({"plain": plain})[0]

    assert reading({"server": {"requests": [{"after_ms": 480, "response_end_ms": 5.0}]}}) == \
        "Playwright を使わない起動：起動から 480 ms でサーバーに届き、485 ms で応答が終わった"
    late_arrival = reading({"server": {"requests": [{"after_ms": 30413, "response_end_ms": 6.0}]},
                            "netlog": [{"open_at_end": [], "longest_gap": {"ms": 29900, "after": "A の開始", "before": "A の終了"}}]})
    assert late_arrival == ("Playwright を使わない起動：起動から 30413 ms でサーバーに届き、30419 ms で応答が終わった"
                            "（テストの上限 10 秒より遅い）（NetLog：最も長い間隔 A の開始 → A の終了 29900 ms）")
    late_answer = reading({"server": {"requests": [{"after_ms": 569, "response_end_ms": 45024.0}]}})
    assert late_answer == "Playwright を使わない起動：起動から 569 ms でサーバーに届き、45593 ms で応答が終わった（テストの上限 10 秒より遅い）"
    assert "サーバーの側" in reading({"server": {"requests": [{"response_end_ms": None}]}})
    assert "サーバーに届いていない（NetLog：処理中だった段階 X）" in reading(
        {"server": {"requests": []}, "netlog": [{"open_at_end": ["X"]}]})
    assert "要求の記録がない" in reading({"server": {"requests": []}, "netlog": [], "exited_early": "ブラウザが 1 秒で終了した"})


def test_the_report_is_a_diagnosis_never_a_pass(tmp_path):
    netlog = diag.summarize_netlog(waiting_for_the_proxy_detection().write(tmp_path / "p.json"), ORIGIN)
    load = first_load(commit_error="30 秒で未到達", server={"requests": []}, netlog=netlog["requests"],
                      screenshot={"file": None, "reason": "TimeoutError: Page.screenshot: Timeout 5000ms exceeded."})
    results = {
        "meta": {"verdict": "診断（合否は判定しません）", "channel": "chrome"},
        "python": [{"url": ORIGIN + "/analyses/1", "path": "/analyses/1", "status": 200, "ms": 80.0, "bytes": 1,
                    "html": True, "edit_page": True}],
        "variants": [variant(load)],
        "server_requests": [],
        "netlog": {"Playwright で起動したブラウザ": netlog},
        "windows": {"proxy": {"environment_variables": [], "windows": "Windows 以外のため確認していない"},
                    "policies": {"windows": "Windows 以外のため確認していない"}},
    }
    text = diag.render(results)
    assert "| 判定 | 診断（合否は判定しません） |" in text and "受入の合格にはしません" in text
    assert "| 判定 | 合格" not in text and "| 判定 | 成功" not in text
    assert "保存できなかった：TimeoutError: Page.screenshot: Timeout 5000ms exceeded." in text
    assert "プロキシの自動検出・PAC の判定：1 回（開始 0 ms・所要 31900 ms（ERR_NAME_NOT_RESOLVED）：" in text
    assert "| 見立て（記録からの分類。原因の確定ではありません） | Python からの編集画面の GET は 80.0 ms で HTML を返した" in text
    assert "最初の読み込みの要求がサーバーに届いていない" in text


def test_a_folder_with_records_in_it_is_refused(tmp_path, capsys):
    (tmp_path / "earlier.md").write_text("前の記録", encoding="utf-8")
    assert diag.main(["--out", str(tmp_path)]) == 2
    assert "空ではありません" in capsys.readouterr().err
    assert [p.name for p in tmp_path.iterdir()] == ["earlier.md"]
