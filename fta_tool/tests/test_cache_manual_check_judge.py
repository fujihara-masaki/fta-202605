"""The judgements of W-02's tool (tests/e2e/cache_manual_check.py), without a
browser: phase C checks the edit screen's files by name (each changed file
fetched anew, each of the other 31 present and 304), phase A records how the
profile started without failing on a 304, and the verdict keeps PR-C's
result apart from how far the old way could be prepared."""

from __future__ import annotations

import pathlib

import pytest

from tests.e2e import cache_manual_check as tool
from tests.e2e.static_assets import all_assets, screen_assets

EDIT = screen_assets("edit")
EDIT_PATH = "/analyses/1"
LABEL = "run-w2"


def entry(rel: str, status: int, inm=None, etag=None, body=b"", cc="no-cache", request=None) -> dict:
    return {"path": "/static/" + rel, "method": "GET", "status": status, "client": "browser",
            "request": {**({"if-none-match": inm} if inm else {}), **(request or {})},
            "response": {**({"etag": etag} if etag else {}), **({"cache-control": cc} if cc else {})},
            "body_sha256": tool.sha256(body) if status == 200 else tool.sha256(b"")}


def good_phase_c():
    stored = {rel: f'"{rel}-w1"' for rel in EDIT}
    bodies = {rel: f"{rel} w2".encode() for rel in tool.MARKED}
    entries = [{"path": EDIT_PATH, "method": "GET", "status": 200, "request": {}, "response": {}}]
    for rel in EDIT:
        if rel in tool.MARKED:
            entries.append(entry(rel, 200, stored[rel], tool.content_etag(bodies[rel]), bodies[rel]))
        else:
            entries.append(entry(rel, 304, stored[rel], stored[rel]))
    probe = {"navigation": "reload", "css": LABEL, "js": {tool.DOM: LABEL, tool.DEEP: LABEL}}
    return entries, probe, stored, bodies


def judge(entries, probe, stored, bodies):
    return {item: ok for item, ok, _detail, _by in
            tool.judge_phase_c(entries, probe, EDIT_PATH, EDIT, tool.MARKED, stored, bodies, LABEL)}


def test_the_expected_files_are_34_with_the_3_changed_ones():
    assert len(EDIT) == 34 and set(tool.MARKED) <= set(EDIT) and len(set(EDIT) - set(tool.MARKED)) == 31
    assert len(all_assets()) == 38


def test_phase_c_all_as_expected_is_ok():
    assert all(judge(*good_phase_c()).values())


def test_phase_c_one_unchanged_file_not_requested_is_ng():
    entries, probe, stored, bodies = good_phase_c()
    missing = next(rel for rel in EDIT if rel not in tool.MARKED)
    entries = [e for e in entries if e["path"] != "/static/" + missing]
    results = tool.judge_phase_c(entries, probe, EDIT_PATH, EDIT, tool.MARKED, stored, bodies, LABEL)
    verdicts = {item: ok for item, ok, _d, _b in results}
    assert verdicts["手順3：編集画面の34件がそれぞれ要求された（ファイルの一致）"] is False
    assert verdicts["手順3：変更していない31件がそれぞれ 304"] is False
    details = " ".join(detail for _i, _o, detail, _b in results)
    assert missing in details


def test_phase_c_same_count_but_another_file_is_ng():
    entries, probe, stored, bodies = good_phase_c()
    swapped = next(rel for rel in EDIT if rel not in tool.MARKED)
    entries = [e for e in entries if e["path"] != "/static/" + swapped] + [entry("css/list.css", 304, '"x"', '"x"')]
    assert len([e for e in entries if e["path"].startswith("/static/")]) == 34  # the count alone would pass
    verdicts = judge(entries, probe, stored, bodies)
    assert verdicts["手順3：編集画面の34件がそれぞれ要求された（ファイルの一致）"] is False
    assert verdicts["手順3：変更していない31件がそれぞれ 304"] is False


def test_phase_c_an_unchanged_file_sent_again_or_a_changed_one_not_is_ng():
    entries, probe, stored, bodies = good_phase_c()
    unchanged = next(rel for rel in EDIT if rel not in tool.MARKED)
    entries = [entry(unchanged, 200, stored[unchanged], '"y"', b"y") if e["path"] == "/static/" + unchanged else e
               for e in entries]
    assert judge(entries, probe, stored, bodies)["手順3：変更していない31件がそれぞれ 304"] is False
    entries, probe, stored, bodies = good_phase_c()
    entries = [entry(tool.CSS, 304, stored[tool.CSS], stored[tool.CSS]) if e["path"] == "/static/" + tool.CSS else e
               for e in entries]
    assert judge(entries, probe, stored, bodies)["手順3：変更した3件は w1 の ETag で要求され 200・w2 の本文"] is False


def test_phase_c_a_forced_reload_or_old_values_are_ng():
    entries, probe, stored, bodies = good_phase_c()
    entries[0] = {**entries[0], "request": {"cache-control": "no-cache", "pragma": "no-cache"}}
    assert judge(entries, probe, stored, bodies)["手順3：F5 が通常の再読み込み"] is False
    entries, probe, stored, bodies = good_phase_c()
    probe = {**probe, "js": {tool.DOM: LABEL, tool.DEEP: "run-w1"}}
    assert judge(entries, probe, stored, bodies)["手順3：ページが使った版（CSS の計算値・下位のモジュールの目印）"] is False


def test_phase_a_records_the_start_without_failing_on_304():
    expected = all_assets()
    entries = [entry(expected[0], 304, '"a"', '"a"'), entry(expected[1], 200, cc=None, etag='"b"'),
               entry("not/a/file.css", 404, cc=None)]
    result = tool.classify_phase_a(entries, expected)
    assert result["coverage"] == "一部"
    assert result["not_prepared"] == [expected[0]]
    assert expected[1] in result["prepared"] and expected[2] in result["prepared"]  # no request: used as stored
    assert result["states"][expected[0]].startswith("304")
    assert result["unexpected"] == ["not/a/file.css"]
    assert tool.classify_phase_a([], expected)["coverage"] == "すべて"
    assert tool.classify_phase_a([entry(rel, 304, '"a"', '"a"') for rel in expected], expected)["coverage"] == "なし"


@pytest.mark.parametrize("reached, reason, oks, coverage, verdict, code", [
    ("done", "", [True], "すべて", "OK", 0),
    ("done", "", [True], "一部", "OK（PR-C の動作。旧方式の準備は一部）", 3),
    ("done", "", [True], "なし", "OK（PR-C の動作。旧方式の準備は一部）", 3),
    ("done", "", [True, False], "すべて", "NG", 1),
    ("B", "時間切れ（20 分）：3画面の Ctrl+F5", [], "すべて", "未完了", 2),
])
def test_the_verdict_keeps_pr_c_apart_from_the_preparation(tmp_path, reached, reason, oks, coverage, verdict, code):
    check = tool.Check(tmp_path, 8001, "Google Chrome", 60, False)
    check.reached, check.reason = reached, reason
    check.results = [{"item": str(i), "ok": ok, "detail": "", "operated_by": "自動"} for i, ok in enumerate(oks)]
    check.preparation = {"coverage": coverage, "prepared": [], "not_prepared": [], "unexpected": []}
    assert check.verdict() == (verdict, code)
    assert check.write_result() == code
    text = (tmp_path / "result.md").read_text(encoding="utf-8")
    assert f"判定：**{verdict}**" in text
    if reason:
        assert f"未完了の理由：{reason}" in text and "後片付けの注意" in text


def test_a_busy_port_ends_as_incomplete_with_a_reason(tmp_path):
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        out = tmp_path / "record"
        code = tool.main(["--out", str(out), "--port", str(port)])
    assert code == 2
    text = (out / "result.md").read_text(encoding="utf-8")
    assert "未完了" in text and f"ポート {port} が使用中" in text
    assert pathlib.Path(out / "result.json").exists() and not (out / "work").exists()
