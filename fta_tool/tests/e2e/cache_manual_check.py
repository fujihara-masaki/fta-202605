"""PR-C, W-02: the real Ctrl+F5 and F5 in the user's everyday browser profile
(docs/static-assets-cache-control-plan.md, section 6.5; the steps for the
user are in docs/manual-check-pr-c.md).

    python -m tests.e2e.cache_manual_check --out <new folder> [--port 8001]

Everything but the two key presses is done here: a temporary copy of
/static and a test database in <out>/work, the markers and their versions,
stopping the test server and starting it again on the same port (the
update procedure of plan 3.5), collecting what the server sent and what the
pages report they used, the judgement, result.md / result.json and the
clean-up. The repository's files, the user's database and the browser's
data are never changed or cleared.

Phases (each waits for the browser; the instructions are printed):
  A  the old serving (Starlette's StaticFiles as before PR-C): the user
     opens the list, the new-analysis form and the edit screen normally, so
     the profile holds files stored the old way (no Cache-Control);
  B  stop, PR-C's serving and version w1 of the marked files, start on the
     same port: the user presses Ctrl+F5 once on each of the three screens.
     Judged: each screen's reload bypassed the cache (the request's
     Cache-Control / Pragma), its page ran w1, and all 38 files came back as
     200 with Cache-Control: no-cache;
  C  the user stays on the edit screen; stop, version w2, start on the same
     port: the user presses F5 once. Judged: a normal reload (no bypass), the
     three changed files fetched with w1's ETag (200, w2's body), the other
     files 304, the page ran w2 (CSS value and both module markers).

The marked files: css/components.css (a custom property on :root),
js/common/dom.js (every screen) and js/pages/edit/factor-source.js (three
imports below edit.js). dom.js also reports, at the page's load event, the
values the page actually used (getComputedStyle, the markers the modules
set), the navigation type and the browser's version, to
POST /__fta_e2e/probe (tests/e2e/stub_server.py). Nothing fetches or imports
a static file to read a value, no cache is switched off, no URL changes.

Exit code: 0 all judged OK, 1 a judgement failed, 2 not completed (time
out, interrupted, the port in use, a wrong folder).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import pathlib
import platform
import shutil
import socket
import subprocess
import sys
import time
from typing import Optional

from tests.e2e.support import FTA_TOOL_DIR, start_server

APP_STATIC = FTA_TOOL_DIR / "app" / "static"
CSS = "css/components.css"
DOM = "js/common/dom.js"
DEEP = "js/pages/edit/factor-source.js"
MARKED = (CSS, DOM, DEEP)
TEN_DAYS = 10 * 24 * 3600
ALL_ASSETS = 38
PROBE = "/__fta_e2e/probe"

REPORTER = r"""
;(() => {
  if (globalThis.__ftaCacheProbeReporter) return;
  globalThis.__ftaCacheProbeReporter = true;
  window.addEventListener('load', async () => {
    const entry = performance.getEntriesByType('navigation')[0];
    const css = getComputedStyle(document.documentElement).getPropertyValue('--fta-cache-probe-components')
      .trim().replace(/^["']|["']$/g, '');
    let browser = null;
    try {
      if (navigator.userAgentData) {
        browser = (await navigator.userAgentData.getHighEntropyValues(['fullVersionList'])).fullVersionList;
      }
    } catch (error) { browser = null; }
    const report = { path: location.pathname, navigation: entry ? entry.type : null, css,
                     js: Object.assign({}, globalThis.__ftaCacheProbe || {}), browser,
                     userAgent: navigator.userAgent, at: Date.now() };
    navigator.sendBeacon('/__fta_e2e/probe', new Blob([JSON.stringify(report)], { type: 'application/json' }));
  });
})();
"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_etag(data: bytes) -> str:
    return f'"{sha256(data)[:32]}"'


def marked(rel: str, original: bytes, version: str) -> bytes:
    if rel.endswith(".css"):
        return original + f'\n:root{{--fta-cache-probe-components:"{version}"}}\n'.encode("utf-8")
    line = (f'\nglobalThis.__ftaCacheProbe = Object.assign(globalThis.__ftaCacheProbe ?? {{}}, '
            f'{{"{rel}": "{version}"}});\n')
    body = original + line.encode("utf-8")
    return body + REPORTER.encode("utf-8") if rel == DOM else body


def forced(request: dict) -> bool:
    """A reload that bypassed the cache (Ctrl+F5, or DevTools' "Disable
    cache") sends these on every request; a normal one does not."""
    return "no-cache" in request.get("cache-control", "") or "no-cache" in request.get("pragma", "")


class Check:
    def __init__(self, out: pathlib.Path, port: int, browser_label: str, timeout: float, keep: bool):
        self.out = out
        self.port = port
        self.browser_label = browser_label
        self.timeout = timeout
        self.keep = keep
        self.work = out / "work"
        self.static = self.work / "static"
        self.request_log = out / "static-requests.jsonl"
        self.probe_log = out / "probe.jsonl"
        self.server = None
        self.analysis_id: Optional[int] = None
        self.written: dict[str, dict[str, bytes]] = {}
        self.results: list[dict] = []
        self.observed: dict = {}
        self.originals = {rel: (APP_STATIC / rel).read_bytes() for rel in MARKED}
        self.run = _dt.datetime.now().strftime("%H%M%S")

    # ----- output -------------------------------------------------------------
    def say(self, text: str = "") -> None:
        print(text, flush=True)

    def state(self, phase: str, waiting_for: str) -> None:
        (self.out / "state.json").write_text(json.dumps({"phase": phase, "waiting_for": waiting_for,
                                                         "port": self.port, "analysis_id": self.analysis_id},
                                                        ensure_ascii=False), encoding="utf-8")

    def judge(self, item: str, ok: bool, detail: str, operated_by: str = "自動") -> None:
        self.results.append({"item": item, "ok": bool(ok), "detail": detail, "operated_by": operated_by})
        self.say(f"  [{'OK' if ok else 'NG'}] {item}：{detail}")

    # ----- server ---------------------------------------------------------------
    def env(self) -> dict:
        return {"FTA_E2E_STATIC_DIR": str(self.static), "FTA_E2E_STATIC_LOG": str(self.request_log),
                "FTA_E2E_PROBE_LOG": str(self.probe_log)}

    def start(self, policy: str) -> None:
        (self.work / "static_control.json").write_text(json.dumps({"policy": policy}), encoding="utf-8")
        for attempt in range(5):
            try:
                self.server = start_server(self.work, self.port, self.env())
                return
            except RuntimeError:
                if attempt == 4:
                    raise
                time.sleep(1)

    def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            self.server = None

    # ----- the copy -------------------------------------------------------------
    def write_version(self, version: str, mtime: Optional[float] = None) -> None:
        self.written[version] = {}
        for rel in MARKED:
            data = marked(rel, self.originals[rel], version)
            path = self.static / rel
            path.write_bytes(data)
            if mtime is not None:
                os.utime(path, (mtime, mtime))
            self.written[version][rel] = data

    # ----- logs -----------------------------------------------------------------
    @staticmethod
    def _jsonl(path: pathlib.Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def requests(self, since: int = 0) -> list[dict]:
        return [e for e in self._jsonl(self.request_log)[since:] if e.get("client") == "browser"]

    def probes(self, since: int = 0) -> list[dict]:
        return [e["data"] for e in self._jsonl(self.probe_log)[since:]]

    def marks(self) -> tuple[int, int]:
        return len(self._jsonl(self.request_log)), len(self._jsonl(self.probe_log))

    def wait(self, what: str, done) -> bool:
        deadline = time.monotonic() + self.timeout
        last = 0.0
        while time.monotonic() < deadline:
            if done():
                return True
            if time.monotonic() - last > 60:
                self.say(f"  …待っています：{what}")
                last = time.monotonic()
            time.sleep(0.5)
        self.say(f"  時間切れ：{what}")
        return False

    def paths(self) -> dict[str, str]:
        return {"一覧": "/", "新規作成": "/analyses/new", "編集": f"/analyses/{self.analysis_id}"}

    # ----- phases -----------------------------------------------------------------
    def prepare(self) -> None:
        self.work.mkdir(parents=True)
        shutil.copytree(APP_STATIC, self.static)
        old = time.time() - TEN_DAYS
        for path in self.static.rglob("*"):
            if path.is_file():
                os.utime(path, (old, old))
        self.write_version(f"w0-{self.run}", mtime=old)
        self.start("baseline")
        self.analysis_id = self.server.create_analysis("キャッシュの確認（W-02）", top_event="頂上事象",
                                                       system_context="確認用の構成")
        a = self.server.add_level1(self.analysis_id, "要因A")
        self.server.add_level1(self.analysis_id, "要因B")
        self.server.update_node(a, user_judgement="yes", description="Aの説明")

    def phase_a(self) -> bool:
        base = f"http://127.0.0.1:{self.port}"
        self.state("A", "3画面を通常に開く")
        self.say("")
        self.say("== 手順1（旧方式のキャッシュを作る）==")
        self.say(f"普段の Chrome（または Edge）の通常のウィンドウで {base}/ を開き、")
        self.say("ヘッダーの「新規作成」→「分析一覧」→ 一覧の「編集」の順にクリックしてください。")
        self.say("（DevTools の「キャッシュを無効にする」は使わないでください。キャッシュ・サイトデータは消さないでください）")
        paths = self.paths()

        def seen() -> bool:
            got = {p["path"] for p in self.probes()}
            return set(paths.values()) <= got

        if not self.wait("3画面の表示", seen):
            return False
        time.sleep(1)
        entries = [e for e in self.requests() if e["path"].startswith("/static/")]
        statuses = {}
        for entry in entries:
            statuses[entry["path"]] = entry
        revalidated = [p for p, e in statuses.items() if e["status"] == 304]
        no_cc = all("cache-control" not in e["response"] for e in entries if e["status"] == 200)
        self.observed["A"] = {"requested": len(statuses), "status_200": sum(e["status"] == 200 for e in statuses.values()),
                              "status_304": len(revalidated), "probes": self.probes()}
        self.judge("旧方式の状態（手順1）", not revalidated and no_cc,
                   f"静的ファイルの要求 {len(statuses)} 件（200 は Cache-Control なし）、304 {len(revalidated)} 件"
                   "（要求のないファイルは、旧方式で保存されたものを検証なしで使った）")
        return True

    def phase_b(self) -> bool:
        self.stop()
        self.write_version("w1")
        self.start("app")
        req_mark, probe_mark = self.marks()
        paths = self.paths()
        self.state("B", "3画面で Ctrl+F5")
        self.say("")
        self.say("== 手順2（移行：実際の Ctrl+F5）==")
        self.say("サーバーを止め、PR-C の配信と新しい版（w1）で同じポートに起動しました。")
        self.say("一覧・新規作成・編集の3画面それぞれで、Ctrl+F5 を1回ずつ押してください。")
        self.say("（画面の間の移動は、画面のリンクで行ってください）")

        def reloaded(path: str) -> bool:
            return any(p["path"] == path and p.get("navigation") == "reload" and p.get("css") == "w1"
                       for p in self.probes(probe_mark))

        def done() -> bool:
            return all(reloaded(p) for p in paths.values())

        if not self.wait("3画面の Ctrl+F5", done):
            return False
        time.sleep(1.5)
        entries = self.requests(req_mark)
        for name, path in paths.items():
            html = [e for e in entries if e["path"] == path and e["method"] == "GET"]
            bypass = [e for e in html if forced(e["request"])]
            probe = [p for p in self.probes(probe_mark) if p["path"] == path and p.get("navigation") == "reload"]
            last = probe[-1] if probe else {}
            ok = bool(bypass) and last.get("css") == "w1" and all(v == "w1" for v in last.get("js", {}).values())
            self.judge(f"手順2 {name}：Ctrl+F5（利用者の実操作）", ok,
                       f"HTML の要求 {len(html)} 件のうちキャッシュを使わない要求 {len(bypass)} 件、"
                       f"ページが使った版 CSS={last.get('css')} JS={last.get('js')}", operated_by="利用者の実操作")
        fetched = {}
        for entry in entries:
            if entry["path"].startswith("/static/") and entry["status"] == 200 \
                    and entry["response"].get("cache-control") == "no-cache":
                fetched[entry["path"][len("/static/"):]] = entry
        mime_ok = all(e["response"].get("content-type", "").startswith(
            "text/javascript" if rel.endswith(".js") else "text/css") for rel, e in fetched.items())
        self.judge("手順2：38件が 200・Cache-Control: no-cache で取得された（移行）", len(fetched) == ALL_ASSETS and mime_ok,
                   f"{len(fetched)} 件、Content-Type {'すべて期待どおり' if mime_ok else '期待と違うものあり'}")
        self.w1_etags = {rel: e["response"]["etag"] for rel, e in fetched.items()}
        self.observed["B"] = {"fetched": sorted(fetched), "probes": self.probes(probe_mark)}
        return True

    def phase_c(self) -> bool:
        edit = self.paths()["編集"]
        self.state("C", "編集画面の表示")
        self.say("")
        self.say("== 手順3（更新の後の実際の F5）==")
        self.say("編集画面を表示して、そのままにしてください（まだ F5 は押さないでください）。")
        _, probe_mark = self.marks()
        last_probe = self.probes()[-1] if self.probes() else {}
        if last_probe.get("path") != edit:
            if not self.wait("編集画面の表示", lambda: bool(self.probes(probe_mark))
                             and self.probes(probe_mark)[-1].get("path") == edit):
                return False
        time.sleep(1)
        self.stop()
        self.write_version("w2")
        self.start("app")
        req_mark, probe_mark = self.marks()
        self.state("C", "編集画面で F5")
        self.say("サーバーを止め、新しい版（w2）にして同じポートで起動しました。")
        self.say("編集画面で F5 を1回押してください（Ctrl+F5 ではなく F5 です）。")

        def done() -> bool:
            return any(p["path"] == edit and p.get("navigation") == "reload" for p in self.probes(probe_mark))

        if not self.wait("編集画面の F5", done):
            return False
        time.sleep(1.5)
        entries = self.requests(req_mark)
        probe = [p for p in self.probes(probe_mark) if p["path"] == edit and p.get("navigation") == "reload"][0]
        html = [e for e in entries if e["path"] == edit and e["method"] == "GET"]
        normal = bool(html) and not any(forced(e["request"]) for e in html)
        self.judge("手順3：F5（利用者の実操作）が通常の再読み込みだった", normal,
                   f"HTML の要求 {len(html)} 件、キャッシュを使わない要求 {sum(forced(e['request']) for e in html)} 件"
                   "（Ctrl+F5 や DevTools の「キャッシュを無効にする」では NG）", operated_by="利用者の実操作")
        static = {}
        for entry in entries:
            if entry["path"].startswith("/static/") and entry["method"] == "GET":
                static[entry["path"][len("/static/"):]] = entry
        problems = []
        for rel in MARKED:
            entry = static.get(rel)
            new = self.written["w2"][rel]
            if entry is None:
                problems.append(f"{rel} の要求なし")
                continue
            if entry["request"].get("if-none-match") != self.w1_etags.get(rel):
                problems.append(f"{rel} が w1 の ETag を送っていない")
            if entry["status"] != 200 or entry["response"].get("etag") != content_etag(new) \
                    or entry["body_sha256"] != sha256(new):
                problems.append(f"{rel} が w2 の本文で 200 になっていない（{entry['status']}）")
        unchanged = [rel for rel in static if rel not in MARKED]
        not_304 = [rel for rel in unchanged if static[rel]["status"] != 304]
        self.judge("手順3：変更した3件は w1 の ETag で要求され 200・w2 の本文", not problems,
                   "; ".join(problems) or "3件とも期待どおり")
        self.judge("手順3：変更していないファイルは 304", bool(unchanged) and not not_304,
                   f"{len(unchanged)} 件中 304 でないもの {len(not_304)} 件{('：' + ', '.join(not_304)) if not_304 else ''}")
        values_ok = probe.get("css") == "w2" and probe.get("js", {}).get(DOM) == "w2" \
            and probe.get("js", {}).get(DEEP) == "w2"
        self.judge("手順3：ページが使った版（CSS の計算値・下位のモジュールの目印）", values_ok,
                   f"CSS={probe.get('css')} {DOM}={probe.get('js', {}).get(DOM)} {DEEP}={probe.get('js', {}).get(DEEP)}")
        self.observed["C"] = {"probe": probe, "requests": len(static)}
        self.browser = probe.get("browser") or probe.get("userAgent")
        return True

    # ----- record ---------------------------------------------------------------------
    def git(self, *args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=FTA_TOOL_DIR, capture_output=True, text=True,
                                  timeout=20).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return "取得できませんでした"

    def write_result(self, completed: bool) -> int:
        verdict = "OK" if completed and self.results and all(r["ok"] for r in self.results) else \
            ("NG" if completed else "未完了")
        info = {
            "verdict": verdict,
            "sha": self.git("rev-parse", "HEAD"),
            "worktree_clean": self.git("status", "--porcelain") == "",
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "browser_label": self.browser_label,
            "browser_reported": getattr(self, "browser", None),
            "port": self.port,
            "analysis_id": self.analysis_id,
            "results": self.results,
            "observed": self.observed,
        }
        (self.out / "result.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        lines = [
            "# W-02 実キー操作による移行の確認（PR-C）", "",
            f"- 判定：**{verdict}**",
            f"- 対象 SHA：`{info['sha']}`（作業ツリー {'クリーン' if info['worktree_clean'] else '変更あり'}）",
            f"- OS：{info['os']}、Python {info['python']}",
            f"- ブラウザ（指定）：{self.browser_label}、ページが報告した版：{info['browser_reported']}",
            f"- オリジン：http://127.0.0.1:{self.port}（全手順で同じ）",
            "- Ctrl+F5・F5 は利用者の実操作。それ以外（準備・版の変更・停止と同じポートでの起動・集計・判定）は自動。",
            "", "| 項目 | 判定 | 操作 | 内容 |", "|---|---|---|---|",
        ]
        for r in self.results:
            lines.append(f"| {r['item']} | {'OK' if r['ok'] else 'NG'} | {r['operated_by']} | {r['detail']} |")
        lines += ["", "記録：`static-requests.jsonl`（サーバーが受けた要求と返した応答）、`probe.jsonl`（ページが使った値）。"]
        (self.out / "result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.say("")
        self.say(f"判定：{verdict}（{self.out / 'result.md'}）")
        return 0 if verdict == "OK" else (1 if verdict == "NG" else 2)

    def clean(self) -> None:
        self.stop()
        if not self.keep and self.work.exists():
            shutil.rmtree(self.work, ignore_errors=True)


def port_free(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="new record folder (outside the code)")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--browser", default="Google Chrome", help="the browser used, for the record")
    parser.add_argument("--timeout-minutes", type=float, default=20)
    parser.add_argument("--keep", action="store_true", help="keep the copy and the test database")
    args = parser.parse_args(argv)
    out = pathlib.Path(args.out).resolve()
    if out == FTA_TOOL_DIR or FTA_TOOL_DIR in out.parents:
        print(f"記録フォルダはコードの外に指定してください：{out}")
        return 2
    if out.exists() and any(out.iterdir()):
        print(f"記録フォルダには新しい（空の）フォルダを指定してください：{out}")
        return 2
    if not port_free(args.port):
        print(f"ポート {args.port} が使用中です。普段のサーバー・以前の確認のサーバーを止めてから実行してください。")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    check = Check(out, args.port, args.browser, args.timeout_minutes * 60, args.keep)
    completed = False
    try:
        check.prepare()
        completed = check.phase_a() and check.phase_b() and check.phase_c()
    except KeyboardInterrupt:
        check.say("中断しました。")
    finally:
        check.clean()
    return check.write_result(completed)


if __name__ == "__main__":
    sys.exit(main())
