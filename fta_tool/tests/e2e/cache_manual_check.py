"""PR-C, W-02: the real Ctrl+F5 and F5 in the user's everyday browser profile
(docs/static-assets-cache-control-plan.md, section 6.5; the steps for the
user are in docs/manual-check-pr-c.md).

    python -m tests.e2e.cache_manual_check --out <new folder> [--port 8001]

Everything but the key presses is done here: a temporary copy of /static
and a test database in <out>/work, the markers and their versions, stopping
the test server and starting it again on the same port (the update
procedure of plan 3.5), collecting what the server sent and what the pages
report they used, the judgement, result.md / result.json, the console
output (w02-output.log) and the clean-up. The repository's files, the
user's database and the browser's data are never changed or cleared.

Phases (each waits for the browser; the instructions are printed):
  A  the old serving (Starlette's StaticFiles as before PR-C): the user
     opens the list, the new-analysis form and the edit screen normally.
     Recorded, not judged: the state the profile started from, and whether
     every file is now stored the old way (no request: used without asking;
     200 without Cache-Control: stored now) or not (304: an earlier stored
     response, e.g. a no-cache one of an earlier run, was confirmed and keeps
     its headers);
  B  stop, PR-C's serving and version w1, start on the same port: the user
     presses Ctrl+F5 once on each of the three screens. Judged: each
     screen's reload bypassed the cache, its page used w1, and the 38 files
     came back as 200 with Cache-Control: no-cache;
  C  the user stays on the edit screen; stop, version w2, start on the same
     port: the user presses F5 once. Judged against the edit screen's 34
     files (tests/e2e/static_assets.py): a normal reload, exactly those
     files requested, the 3 changed ones with w1's ETag and 200 with w2's
     body, each of the 31 others 304 with its stored ETag, and the page used
     w2 (the CSS value and both module markers).

How a page is seen: the test server adds a small inline script to every
HTML page (FTA_E2E_PROBE_RUN, tests/e2e/stub_server.py) that reports at the
load event, with this run's id: the path, the navigation type, the computed
value of the CSS marker, the module markers and the browser's version. The
HTML is fetched on every navigation (C-03), so a page is seen even when its
modules come from a cache made before this run; nothing fetches or imports
a static file to read a value, no cache is switched off, no URL changes.
Reports and markers of other runs carry another run id and are left out.

After the run the profile holds this origin's files as no-cache responses
whose Last-Modified is 2001-01-01, so any server later on this origin
(PR-C's or an older one) answers with its own files (an older server
compares If-Modified-Since with its newer files and sends 200).

Exit code: 0 OK; 3 PR-C's behaviour OK but the old way could not be
prepared for every file (see the record); 1 a judgement failed; 2 not
completed (time out, interrupted, the port in use, an error: the reason is
in result.md).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import pathlib
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import time
import traceback
from typing import Optional

from tests.e2e.static_assets import APP_STATIC, all_assets, screen_assets
from tests.e2e.support import FTA_TOOL_DIR, start_server

CSS = "css/components.css"
DOM = "js/common/dom.js"
DEEP = "js/pages/edit/factor-source.js"
MARKED = (CSS, DOM, DEEP)
TEN_DAYS = 10 * 24 * 3600
OLD_TIME = 978307200.0  # 2001-01-01: Last-Modified of the files from phase B on
SCREEN_NAMES = {"list": "一覧", "new": "新規作成", "edit": "編集"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_etag(data: bytes) -> str:
    return f'"{sha256(data)[:32]}"'


def marked(rel: str, original: bytes, version: str) -> bytes:
    if rel.endswith(".css"):
        return original + f'\n:root{{--fta-cache-probe-components:"{version}"}}\n'.encode("utf-8")
    line = (f'\nglobalThis.__ftaCacheProbe = Object.assign(globalThis.__ftaCacheProbe ?? {{}}, '
            f'{{"{rel}": "{version}"}});\n')
    return original + line.encode("utf-8")


def forced(request: dict) -> bool:
    """A reload that bypassed the cache (Ctrl+F5, or DevTools' "Disable
    cache") sends these on every request; a normal one does not."""
    return "no-cache" in request.get("cache-control", "") or "no-cache" in request.get("pragma", "")


def last_static(entries: list[dict]) -> dict[str, dict]:
    found = {}
    for entry in entries:
        if entry["path"].startswith("/static/") and entry["method"] == "GET":
            found[entry["path"][len("/static/"):]] = entry
    return found


# ----- judgements (pure, unit-tested in tests/test_cache_manual_check_judge.py) -----

def classify_phase_a(entries: list[dict], expected: list[str]) -> dict:
    """How each file stood after phase A (old serving): stored the old way
    or not. Not a judgement of PR-C."""
    found = last_static(entries)
    states, prepared, not_prepared = {}, [], []
    for rel in expected:
        entry = found.get(rel)
        if entry is None:
            state, ok = "要求なし（保存済みを検証なしで使用。旧方式の保存）", True
        elif entry["status"] == 200 and "cache-control" not in entry["response"]:
            state, ok = "200・Cache-Control なし（旧方式で保存）", True
        elif entry["status"] == 304:
            state, ok = "304（既存の保存を確認。保存の形式は変わらない。前回の確認の no-cache の可能性）", False
        else:
            state, ok = f"{entry['status']}（想定外）", False
        states[rel] = state
        (prepared if ok else not_prepared).append(rel)
    if not not_prepared:
        coverage = "すべて"
    elif prepared:
        coverage = "一部"
    else:
        coverage = "なし"
    return {"states": states, "prepared": prepared, "not_prepared": not_prepared, "coverage": coverage,
            "unexpected": sorted(set(found) - set(expected))}


def judge_phase_b(entries: list[dict], probes: list[dict], paths: dict[str, str], label: str,
                  expected: list[str]) -> list[tuple[str, bool, str, str]]:
    results = []
    for screen, path in paths.items():
        html = [e for e in entries if e["path"] == path and e["method"] == "GET"]
        bypass = [e for e in html if forced(e["request"])]
        reload = [p for p in probes if p.get("path") == path and p.get("navigation") == "reload"]
        last = reload[-1] if reload else {}
        wanted = [DOM] + ([DEEP] if screen == "edit" else [])
        used = last.get("css") == label and all(last.get("js", {}).get(rel) == label for rel in wanted)
        results.append((f"手順2 {SCREEN_NAMES[screen]}：Ctrl+F5", bool(bypass) and used,
                        f"HTML の要求 {len(html)} 件のうちキャッシュを使わない要求 {len(bypass)} 件、"
                        f"ページが使った版 CSS={last.get('css')} JS={last.get('js')}", "利用者の実操作"))
    # Any 200 of step 2 counts (a later visit by a link answers 304 for the same file).
    fetched = {}
    for entry in entries:
        if entry["path"].startswith("/static/") and entry["method"] == "GET" and entry["status"] == 200 \
                and entry["response"].get("cache-control") == "no-cache":
            fetched[entry["path"][len("/static/"):]] = entry
    missing = sorted(set(expected) - set(fetched))
    wrong_type = sorted(rel for rel, e in fetched.items() if not e["response"].get("content-type", "").startswith(
        "text/javascript" if rel.endswith(".js") else "text/css"))
    results.append(("手順2：38件が 200・Cache-Control: no-cache・期待どおりの Content-Type（移行）",
                     not missing and not wrong_type and len(expected) == 38,
                     f"{len(set(fetched) & set(expected))}/{len(expected)} 件"
                     + (f"、取得されなかったもの {missing}" if missing else "")
                     + (f"、Content-Type が違うもの {wrong_type}" if wrong_type else ""), "自動"))
    return results


def judge_phase_c(entries: list[dict], probe: dict, edit_path: str, expected: list[str], changed: tuple[str, ...],
                  stored_etags: dict[str, str], new_bodies: dict[str, bytes],
                  label: str) -> list[tuple[str, bool, str, str]]:
    """Phase C against the edit screen's expected files: the changed ones and
    every one of the others, by name (not by count)."""
    results = []
    html = [e for e in entries if e["path"] == edit_path and e["method"] == "GET"]
    normal = bool(html) and not any(forced(e["request"]) for e in html)
    results.append(("手順3：F5 が通常の再読み込み", normal and probe.get("navigation") == "reload",
                    f"HTML の要求 {len(html)} 件、キャッシュを使わない要求 {sum(forced(e['request']) for e in html)} 件、"
                    f"ナビゲーションの種類 {probe.get('navigation')}（Ctrl+F5 や DevTools の「キャッシュを無効にする」では NG）",
                    "利用者の実操作"))
    found = last_static(entries)
    missing = sorted(set(expected) - set(found))
    extra = sorted(set(found) - set(expected))
    results.append(("手順3：編集画面の34件がそれぞれ要求された（ファイルの一致）", not missing and not extra,
                    f"期待 {len(expected)} 件、要求 {len(found)} 件"
                    + (f"、要求のないもの {missing}" if missing else "")
                    + (f"、期待にないもの {extra}" if extra else ""), "自動"))
    problems = []
    for rel in changed:
        entry, body = found.get(rel), new_bodies[rel]
        if entry is None:
            problems.append(f"{rel} の要求なし")
            continue
        if entry["request"].get("if-none-match") != stored_etags.get(rel):
            problems.append(f"{rel} が w1 の ETag を送っていない")
        if entry["status"] != 200 or entry["response"].get("etag") != content_etag(body) \
                or entry.get("body_sha256") != sha256(body):
            problems.append(f"{rel} が w2 の本文で 200 になっていない（{entry['status']}）")
    results.append(("手順3：変更した3件は w1 の ETag で要求され 200・w2 の本文", not problems,
                    "; ".join(problems) or "3件とも期待どおり", "自動"))
    unchanged = sorted(set(expected) - set(changed))
    bad = []
    for rel in unchanged:
        entry = found.get(rel)
        if entry is None:
            bad.append(f"{rel}：要求なし")
        elif entry["status"] != 304:
            bad.append(f"{rel}：{entry['status']}")
        elif entry["request"].get("if-none-match") != stored_etags.get(rel):
            bad.append(f"{rel}：保存した ETag を送っていない")
    results.append(("手順3：変更していない31件がそれぞれ 304", len(unchanged) == 31 and not bad,
                    f"{len(unchanged)} 件中 期待と違うもの {len(bad)} 件" + (f"：{'; '.join(bad)}" if bad else ""), "自動"))
    js = probe.get("js", {})
    used = probe.get("css") == label and js.get(DOM) == label and js.get(DEEP) == label
    results.append(("手順3：ページが使った版（CSS の計算値・下位のモジュールの目印）", used,
                    f"CSS={probe.get('css')} {DOM}={js.get(DOM)} {DEEP}={js.get(DEEP)}（期待 {label}）", "自動"))
    return results


class Incomplete(Exception):
    """The run cannot go on; the reason goes to result.md."""


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
        self.output = out / "w02-output.log"
        self.run = _dt.datetime.now().strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3)
        self.server = None
        self.analysis_id: Optional[int] = None
        self.written: dict[str, dict[str, bytes]] = {}
        self.results: list[dict] = []
        self.observed: dict = {}
        self.preparation: Optional[dict] = None
        self.stored_etags: dict[str, str] = {}
        self.reached = ""
        self.reason = ""
        self.browser = None
        self.originals = {rel: (APP_STATIC / rel).read_bytes() for rel in MARKED}
        self.assets = all_assets()
        self.edit_assets = screen_assets("edit")

    def label(self, step: str) -> str:
        return f"{self.run}-{step}"

    # ----- output -------------------------------------------------------------
    def say(self, text: str = "") -> None:
        print(text, flush=True)
        try:
            with self.output.open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError:
            pass

    def state(self, phase: str, waiting_for: str) -> None:
        self.reached = phase
        (self.out / "state.json").write_text(json.dumps({"phase": phase, "waiting_for": waiting_for, "run": self.run,
                                                         "port": self.port, "analysis_id": self.analysis_id},
                                                        ensure_ascii=False), encoding="utf-8")

    def record(self, results: list[tuple[str, bool, str, str]]) -> None:
        for item, ok, detail, operated_by in results:
            self.results.append({"item": item, "ok": bool(ok), "detail": detail, "operated_by": operated_by})
            self.say(f"  [{'OK' if ok else 'NG'}] {item}：{detail}")

    # ----- server ---------------------------------------------------------------
    def env(self) -> dict:
        return {"FTA_E2E_STATIC_DIR": str(self.static), "FTA_E2E_STATIC_LOG": str(self.request_log),
                "FTA_E2E_PROBE_LOG": str(self.probe_log), "FTA_E2E_PROBE_RUN": self.run}

    def start(self, policy: str) -> None:
        (self.work / "static_control.json").write_text(json.dumps({"policy": policy}), encoding="utf-8")
        last = None
        for _ in range(5):
            try:
                self.server = start_server(self.work, self.port, self.env())
                return
            except RuntimeError as error:
                last = error
                time.sleep(1)
        raise Incomplete(f"テスト用サーバーを {self.port} で起動できませんでした：{str(last).splitlines()[0] if last else ''}")

    def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            self.server = None

    # ----- the copy -------------------------------------------------------------
    def set_times(self, mtime: float) -> None:
        for path in self.static.rglob("*"):
            if path.is_file():
                os.utime(path, (mtime, mtime))

    def write_version(self, step: str, mtime: float) -> None:
        version = self.label(step)
        self.written[step] = {}
        for rel in MARKED:
            data = marked(rel, self.originals[rel], version)
            path = self.static / rel
            path.write_bytes(data)
            os.utime(path, (mtime, mtime))
            self.written[step][rel] = data

    # ----- logs -----------------------------------------------------------------
    @staticmethod
    def _jsonl(path: pathlib.Path) -> list[dict]:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows

    def requests(self, since: int = 0) -> list[dict]:
        return [e for e in self._jsonl(self.request_log)[since:] if e.get("client") == "browser"]

    def probes(self, since: int = 0) -> list[dict]:
        """This run's reports only (another run's page or script has another id)."""
        return [e["data"] for e in self._jsonl(self.probe_log)[since:]
                if isinstance(e.get("data"), dict) and e["data"].get("run") == self.run]

    def marks(self) -> tuple[int, int]:
        return len(self._jsonl(self.request_log)), len(self._jsonl(self.probe_log))

    def wait(self, what: str, done) -> None:
        deadline = time.monotonic() + self.timeout
        last = time.monotonic()
        while time.monotonic() < deadline:
            if done():
                return
            if time.monotonic() - last > 60:
                self.say(f"  …待っています：{what}")
                last = time.monotonic()
            time.sleep(0.5)
        raise Incomplete(f"時間切れ（{self.timeout / 60:.0f} 分）：{what}")

    def paths(self) -> dict[str, str]:
        return {"list": "/", "new": "/analyses/new", "edit": f"/analyses/{self.analysis_id}"}

    # ----- phases -----------------------------------------------------------------
    def prepare(self) -> None:
        self.work.mkdir(parents=True)
        shutil.copytree(APP_STATIC, self.static)
        old = time.time() - TEN_DAYS
        self.set_times(old)
        self.write_version("w0", old)
        self.start("baseline")
        self.analysis_id = self.server.create_analysis("キャッシュの確認（W-02）", top_event="頂上事象",
                                                       system_context="確認用の構成")
        a = self.server.add_level1(self.analysis_id, "要因A")
        self.server.add_level1(self.analysis_id, "要因B")
        self.server.update_node(a, user_judgement="yes", description="Aの説明")
        self.say(f"確認の識別子：{self.run}")

    def phase_a(self) -> None:
        base = f"http://127.0.0.1:{self.port}"
        self.state("A", "3画面を通常に開く")
        self.say("")
        self.say("== 手順1（旧方式の配信で3画面を開く）==")
        self.say(f"普段の Chrome（または Edge）の通常のウィンドウで {base}/ を開き、")
        self.say("ヘッダーの「新規作成」→「分析一覧」→ 一覧の「編集」の順にクリックしてください。")
        self.say("（DevTools の「キャッシュを無効にする」は使わないでください。キャッシュ・サイトデータは消さないでください）")
        paths = self.paths()
        self.wait("3画面の表示", lambda: set(paths.values()) <= {p.get("path") for p in self.probes()})
        time.sleep(1)
        self.preparation = classify_phase_a(self.requests(), self.assets)
        probes = self.probes()
        self.observed["A"] = {"probes": probes, "states": self.preparation["states"]}
        own = [p for p in probes if p.get("css") == self.label("w0")]
        counts = {}
        for state in self.preparation["states"].values():
            key = state.split("（")[0]
            counts[key] = counts.get(key, 0) + 1
        self.say(f"  [記録] 初期状態の観察：{counts}、この回の w0 を使った画面 {len(own)}/{len(probes)}")
        self.say(f"  [記録] 旧方式の準備：{self.preparation['coverage']}（{len(self.preparation['prepared'])}/38 件）")

    def phase_b(self) -> None:
        self.stop()
        self.set_times(OLD_TIME)
        self.write_version("w1", OLD_TIME)
        self.start("app")
        req_mark, probe_mark = self.marks()
        paths = self.paths()
        label = self.label("w1")
        self.state("B", "3画面で Ctrl+F5")
        self.say("")
        self.say("== 手順2（移行：実際の Ctrl+F5）==")
        self.say("サーバーを止め、PR-C の配信と新しい版（w1）で同じポートに起動しました。")
        self.say("一覧・新規作成・編集の3画面それぞれで、Ctrl+F5 を1回ずつ押してください。")
        self.say("（画面の間の移動は、画面のリンクで行ってください）")

        def reloaded(path: str) -> bool:
            return any(p.get("path") == path and p.get("navigation") == "reload" and p.get("css") == label
                       for p in self.probes(probe_mark))

        self.wait("3画面の Ctrl+F5", lambda: all(reloaded(p) for p in paths.values()))
        time.sleep(1.5)
        entries = self.requests(req_mark)
        self.record(judge_phase_b(entries, self.probes(probe_mark), paths, label, self.assets))
        for entry in entries:
            if entry["path"].startswith("/static/") and entry["method"] == "GET" and entry["status"] == 200:
                self.stored_etags[entry["path"][len("/static/"):]] = entry["response"].get("etag")
        self.observed["B"] = {"probes": self.probes(probe_mark)}

    def phase_c(self) -> None:
        edit = self.paths()["edit"]
        self.state("C", "編集画面の表示")
        self.say("")
        self.say("== 手順3（更新の後の実際の F5）==")
        self.say("編集画面を表示して、そのままにしてください（まだ F5 は押さないでください）。")
        _, probe_mark = self.marks()
        mine = self.probes()
        if not mine or mine[-1].get("path") != edit:
            self.wait("編集画面の表示", lambda: bool(self.probes(probe_mark)) and self.probes(probe_mark)[-1].get("path") == edit)
        time.sleep(1)
        self.stop()
        self.write_version("w2", OLD_TIME)
        self.start("app")
        req_mark, probe_mark = self.marks()
        self.state("C", "編集画面で F5")
        self.say("サーバーを止め、新しい版（w2）にして同じポートで起動しました。")
        self.say("編集画面で F5 を1回押してください（Ctrl+F5 ではなく F5 です）。")
        self.wait("編集画面の F5", lambda: any(p.get("path") == edit and p.get("navigation") == "reload"
                                              for p in self.probes(probe_mark)))
        time.sleep(1.5)
        probe = [p for p in self.probes(probe_mark) if p.get("path") == edit and p.get("navigation") == "reload"][0]
        self.record(judge_phase_c(self.requests(req_mark), probe, edit, self.edit_assets, MARKED,
                                  self.stored_etags, self.written["w2"], self.label("w2")))
        self.observed["C"] = {"probe": probe}
        self.browser = probe.get("browser") or probe.get("userAgent")
        self.state("done", "")

    # ----- record ---------------------------------------------------------------------
    def git(self, *args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=FTA_TOOL_DIR, capture_output=True, text=True,
                                  timeout=20).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return "取得できませんでした"

    def verdict(self) -> tuple[str, int]:
        if self.reason or self.reached != "done":
            return "未完了", 2
        if not self.results or not all(r["ok"] for r in self.results):
            return "NG", 1
        if self.preparation and self.preparation["coverage"] != "すべて":
            return "OK（PR-C の動作。旧方式の準備は一部）", 3
        return "OK", 0

    def write_result(self) -> int:
        verdict, code = self.verdict()
        prep = self.preparation or {}
        info = {
            "verdict": verdict, "exit_code": code, "reason": self.reason, "run": self.run,
            "reached": self.reached,
            "sha": self.git("rev-parse", "HEAD"),
            "worktree_clean": self.git("status", "--porcelain", "--untracked-files=no") == "",
            "os": platform.platform(), "python": sys.version.split()[0],
            "browser_label": self.browser_label, "browser_reported": self.browser, "port": self.port,
            "analysis_id": self.analysis_id,
            "preparation": {k: prep.get(k) for k in ("coverage", "prepared", "not_prepared", "unexpected")},
            "results": self.results, "observed": self.observed,
        }
        (self.out / "result.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        lines = [
            "# W-02 実キー操作による移行の確認（PR-C）", "",
            f"- 判定：**{verdict}**（終了コード {code}）",
        ]
        if self.reason:
            lines.append(f"- 未完了の理由：{self.reason}（到達した手順：{self.reached or '準備'}）")
        lines += [
            f"- 対象 SHA：`{info['sha']}`（作業ツリー {'クリーン' if info['worktree_clean'] else '変更あり'}）",
            f"- 確認の識別子：`{self.run}`（ページの報告と目印の版はこの識別子のものだけを使った）",
            f"- OS：{info['os']}、Python {info['python']}",
            f"- ブラウザ（指定）：{self.browser_label}、ページが報告した版：{info['browser_reported']}",
            f"- オリジン：http://127.0.0.1:{self.port}（全手順で同じ）",
            "- Ctrl+F5・F5 は利用者の実操作。それ以外（準備・版の変更・停止と同じポートでの起動・集計・判定）は自動。",
            "", "## 初期状態の観察と旧方式の準備（手順1。PR-C の合否ではない）", "",
            f"- 旧方式の準備：**{prep.get('coverage', '未確認')}**（{len(prep.get('prepared') or [])}/38 件）",
        ]
        if prep.get("not_prepared"):
            lines.append(f"- 旧方式にできなかったファイル（既存の保存を 304 で確認したもの）：{', '.join(prep['not_prepared'])}")
        lines += ["", "## PR-C の動作の判定（手順2・3）", "", "| 項目 | 判定 | 操作 | 内容 |", "|---|---|---|---|"]
        for r in self.results:
            lines.append(f"| {r['item']} | {'OK' if r['ok'] else 'NG'} | {r['operated_by']} | {r['detail']} |")
        if self.reached == "A" or (self.reached == "B" and code == 2):
            lines += ["", "**後片付けの注意**：手順2 の Ctrl+F5 の前に終わったため、このオリジンの静的ファイルが旧方式で"
                      "保存されたまま（最大で約1日、検証なしで使われ得る）です。このオリジンを別の用途に使う前に、"
                      "この確認をもう一度実行するか、3画面で Ctrl+F5 を1回ずつ行ってください。"]
        lines += ["", "記録：`static-requests.jsonl`（サーバーが受けた要求と返した応答）、`probe.jsonl`（ページが使った値）、"
                  "`w02-output.log`（表示した案内と結果）、`server.log`（テスト用サーバーの出力）。"]
        (self.out / "result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.say("")
        self.say(f"判定：{verdict}（{self.out / 'result.md'}）")
        return code

    def clean(self) -> None:
        self.stop()
        log = self.work / "server.log"
        if log.exists():
            try:
                shutil.copyfile(log, self.out / "server.log")
            except OSError:
                pass
        if not self.keep and self.work.exists():
            shutil.rmtree(self.work, ignore_errors=True)


def port_free(port: int) -> bool:
    """No server listens on the port. Off Windows, connections of an earlier
    server that are still closing (TIME_WAIT) do not count, as for uvicorn."""
    with socket.socket() as sock:
        if os.name != "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
        print(f"未完了：記録フォルダはコードの外に指定してください：{out}")
        return 2
    if out.exists() and any(out.iterdir()):
        print(f"未完了：記録フォルダには新しい（空の）フォルダを指定してください：{out}")
        return 2
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"未完了：記録フォルダを作れません：{out}：{error}")
        return 2
    check = Check(out, args.port, args.browser, args.timeout_minutes * 60, args.keep)
    try:
        if not port_free(args.port):
            raise Incomplete(f"ポート {args.port} が使用中です。普段のサーバー・以前の確認のサーバーを止めてから実行してください")
        check.prepare()
        check.phase_a()
        check.phase_b()
        check.phase_c()
    except Incomplete as error:
        check.reason = str(error)
        check.say(f"未完了：{error}")
    except KeyboardInterrupt:
        check.reason = "中断されました（Ctrl+C）"
        check.say(check.reason)
    except Exception as error:  # noqa: BLE001 - recorded as the reason, with the traceback
        check.reason = f"{type(error).__name__}: {str(error).splitlines()[0] if str(error) else ''}"
        check.say(f"未完了：{check.reason}")
        (out / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        check.clean()
    return check.write_result()


if __name__ == "__main__":
    sys.exit(main())
