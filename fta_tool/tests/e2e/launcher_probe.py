"""Does a Python child start under a stand-in for a venv's launcher?

The tests of the test server's stop (tests/e2e/test_display_check.py) run
the app under a stand-in for the launcher that a venv's Scripts\\python.exe
is on Windows (CPython PC/launcher.c, run_child: the real python.exe runs as
a child with the launcher's standard handles; the launcher waits for it).
On Windows the stand-in then runs a venv's python.exe again: two launchers.

This probe starts no FTA app: the child is a one-line script that writes
`reached.json` (its process id and which standard streams it has) as its
first statement. Each way of starting it (SCENARIOS) runs in a folder of its
own, and the stand-in writes what it did to launcher-stages.jsonl there
(a file: it needs no stdout). Run on Windows:

    python -m tests.e2e.launcher_probe --out <new folder outside the code>

It writes probe-result.md and probe-result.json and stops only the
processes it started (their process ids, recorded).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import platform
import subprocess
import sys
import time

# The stand-in launcher (the tests use it too). `mode`:
#   inherit-none   Popen(command): what the stand-in of 32730b8 did; on
#                  Windows the child inherits no handle (close_fds)
#   share-stdin    the child gets this process's stdin, stdout and stderr
#                  (as launcher.c passes them): what the stand-in of 5773c84 did
#   own-stdin      the child gets a stdin pipe of its own (closed when this
#                  process's stdin is closed) and this process's stdout, stderr
#   null-handles   the child gets no standard handle (Windows: STARTUPINFO
#                  with STARTF_USESTDHANDLES and NULL handles; elsewhere fds
#                  0, 1, 2 closed): an app started without them
# and `then`: "read" waits for this process's stdin to be closed and ends
# then (before its child: the case the tests need), "wait" waits for the child.
LAUNCHER = r'''import json, os, pathlib, subprocess, sys, threading, time, traceback
def stage(name, **fields):
    with open("launcher-stages.jsonl", "a", encoding="utf-8") as record:
        record.write(json.dumps({"time": time.time(), "stage": name, "pid": os.getpid(), **fields},
                                ensure_ascii=False) + "\n")
pathlib.Path("launcher.pid").write_text(str(os.getpid()))
stage("launcher started", ppid=os.getppid(), executable=sys.executable,
      streams={name: getattr(sys, name) is not None for name in ("stdin", "stdout", "stderr")})
mode, then, command = sys.argv[1], sys.argv[2], sys.argv[3:]
if mode == "inherit-none":
    options = {}
elif mode == "share-stdin":
    options = {"stdin": sys.stdin, "stdout": sys.stdout, "stderr": sys.stderr}
elif mode == "own-stdin":
    options = {"stdin": subprocess.PIPE, "stdout": sys.stdout, "stderr": sys.stderr}
elif os.name == "nt":  # null-handles
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESTDHANDLES  # hStdInput, hStdOutput, hStdError left None: NULL
    options = {"startupinfo": info}
else:
    options = {"preexec_fn": lambda: [os.close(fd) for fd in (0, 1, 2)]}
stage("starting child", mode=mode, then=then, command=command)
try:
    child = subprocess.Popen(command, **options)
except BaseException as error:
    stage("child not started", error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
    raise
stage("child started", child_pid=child.pid)
def watch():
    stage("child exited", child_pid=child.pid, exit_code=child.wait())
if then == "wait":
    watch()
else:
    threading.Thread(target=watch, daemon=True).start()
    sys.stdin.buffer.read()
    stage("stdin closed")
    if child.stdin is not None:
        child.stdin.close()  # passes the stop on to the child, which ends after this process
stage("launcher ends")
'''

# The child: its first statement records that it runs.
CHILD = ("import json, os, sys; open('reached.json', 'w').write(json.dumps({'pid': os.getpid(), "
         "'streams': {n: getattr(sys, n) is not None for n in ('stdin', 'stdout', 'stderr')}}))")

# name: (description, stand-in mode or None for no stand-in, then, child python)
SCENARIOS = {
    "direct": ("スタンドインなし。テストのプロセスが venv の python.exe で子を起動（通常のテスト用サーバーと同じ）",
               None, None, "venv"),
    "inherit-none": ("スタンドインが子に標準ハンドルを渡さない（32730b8 の方式）。スタンドインは標準入力を読んで待つ",
                     "inherit-none", "read", "venv"),
    "share-stdin": ("スタンドインが自分の標準入出力を子に渡し、同じ標準入力を読んで待つ（5773c84 の方式）",
                    "share-stdin", "read", "venv"),
    "share-stdin-base": ("share-stdin と同じだが、子は venv のランチャーを通さず本物の python.exe（sys._base_executable）",
                         "share-stdin", "read", "base"),
    "share-stdin-wait": ("スタンドインが自分の標準入出力を子に渡し、標準入力は読まずに子の終了を待つ",
                         "share-stdin", "wait", "venv"),
    "own-stdin": ("スタンドインが子に専用の標準入力（パイプ）と自分の標準出力・標準エラーを渡し、自分の標準入力を読んで待つ（修正後の方式）",
                  "own-stdin", "read", "venv"),
    "null-handles": ("スタンドインが子に標準ハンドルを NULL として明示して渡し、自分の標準入力を読んで待つ（修正後の「標準入出力なし」）",
                     "null-handles", "read", "venv"),
}
# These must start their child on every system (tests/e2e/test_display_check.py).
MUST_START = ("direct", "share-stdin-wait", "own-stdin", "null-handles")

# How long the probe looks for the child's first statement (a detection
# limit, not a wait the result depends on: a child that starts writes it at once).
REACH_SECONDS = 15


def read_stages(folder: pathlib.Path) -> list[dict]:
    path = folder / "launcher-stages.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_scenario(name: str, folder: pathlib.Path, reach_seconds: float = REACH_SECONDS) -> dict:
    from tests.e2e.support import process_gone, python_env, stop_started

    description, mode, then, which = SCENARIOS[name]
    folder.mkdir(parents=True)
    python = sys.executable if which == "venv" else getattr(sys, "_base_executable", sys.executable)
    child = [python, "-c", CHILD]
    if mode is None:
        command = child
    else:
        (folder / "launcher.py").write_text(LAUNCHER, encoding="utf-8")
        command = [sys.executable, str(folder / "launcher.py"), mode, then, *child]
    log = (folder / "output.log").open("wb")
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=folder, env=python_env(), stdin=subprocess.PIPE, stdout=log,
                               stderr=subprocess.STDOUT)
    reached = folder / "reached.json"

    def wait_reached(limit: float) -> bool:
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            if reached.exists() and reached.stat().st_size:
                return True
            time.sleep(0.05)
        return reached.exists() and reached.stat().st_size > 0

    before_close = wait_reached(reach_seconds)
    seconds = round(time.monotonic() - started, 2) if before_close else None
    stages_before = read_stages(folder)
    child_pids = [s["child_pid"] for s in stages_before if s["stage"] == "child started"]
    alive_before = {pid: not process_gone(pid, 0) for pid in child_pids}
    process.stdin.close()
    after_close = before_close or wait_reached(reach_seconds)
    try:
        process.wait(timeout=reach_seconds)
    except subprocess.TimeoutExpired:
        pass
    stages = read_stages(folder)
    left = []
    if process.poll() is None or any(not process_gone(pid, 0) for pid in child_pids):
        left = stop_started(process, None, child_pids)
    log.close()
    return {
        "scenario": name, "description": description,
        "reached_before_stdin_closed": before_close, "seconds_to_reach": seconds,
        "reached_after_stdin_closed": after_close and not before_close,
        "child": json.loads(reached.read_text(encoding="utf-8")) if reached.exists() and reached.stat().st_size else None,
        "launcher_pid": int((folder / "launcher.pid").read_text()) if (folder / "launcher.pid").exists() else None,
        "child_pids": child_pids, "child_alive_while_waiting": alive_before,
        "started_process_exit_code": process.poll(),
        "launcher_stages": stages,
        "output": (folder / "output.log").read_text(encoding="utf-8", errors="replace"),
        "left_running": left,
    }


def verdict(result: dict) -> str:
    if result["reached_before_stdin_closed"]:
        return f"子は起動した（{result['seconds_to_reach']} 秒）"
    exited = [s for s in result["launcher_stages"] if s["stage"] == "child exited"]
    if any(s["stage"] == "child not started" for s in result["launcher_stages"]):
        return "子のプロセスを作れなかった（Popen の例外）"
    if result["reached_after_stdin_closed"]:
        return "スタンドインの標準入力が閉じられるまで、子は最初の行に達しなかった（閉じた後に達した）"
    if exited:
        return f"子は最初の行に達せずに終了した（終了コード {exited[0]['exit_code']}）"
    return "子は最初の行に達しなかった（動作中のまま）"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=pathlib.Path, help="new folder for the record (outside the code)")
    parser.add_argument("--scenarios", default=",".join(SCENARIOS), help="comma-separated names")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        print(f"記録フォルダには新しい（空の）フォルダを指定してください：{out}")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for name in [n.strip() for n in args.scenarios.split(",") if n.strip()]:
        result = run_scenario(name, out / name)
        results.append(result)
        print(f"{name}: {verdict(result)}", flush=True)
    info = {"python": sys.version, "executable": sys.executable,
            "base_executable": getattr(sys, "_base_executable", ""), "platform": platform.platform()}
    (out / "probe-result.json").write_text(json.dumps({"environment": info, "results": results},
                                                      ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# スタンドインのランチャーの下の Python の起動（launcher_probe）", "",
             f"- Python：{info['python']}", f"- sys.executable：{info['executable']}",
             f"- sys._base_executable：{info['base_executable']}", f"- OS：{info['platform']}", "",
             "| 方式 | 内容 | 結果 | 子の PID | 子の標準入出力 | 残ったプロセス |", "|---|---|---|---|---|---|"]
    for r in results:
        streams = r["child"]["streams"] if r["child"] else "—"
        lines.append(f"| {r['scenario']} | {r['description']} | {verdict(r)} | {r['child_pids'] or '—'} "
                     f"| {streams} | {r['left_running'] or 'なし'} |")
    lines += ["", "各方式のスタンドインの記録（launcher-stages.jsonl）と出力は probe-result.json にあります。"]
    (out / "probe-result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    failed = [r["scenario"] for r in results if r["scenario"] in MUST_START and not r["reached_before_stdin_closed"]]
    print(f"記録：{out / 'probe-result.md'}")
    if failed:
        print(f"起動すべき方式で子が起動しなかった：{', '.join(failed)}")
    return 1 if failed or any(r["left_running"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
