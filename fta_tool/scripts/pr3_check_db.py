"""Databases for the manual check of PR-3 on Windows
(docs/manual-check-pr3.md, plan 8.3).

Creates a NEW database (fta_tool.db) in a new or empty folder — never in a
folder that already holds anything, so the database the tool is normally
used with is never opened or changed:

    python scripts/pr3_check_db.py normal  C:\\fta-check\\pr3-normal
    python scripts/pr3_check_db.py anomaly C:\\fta-check\\pr3-anomaly

normal   the analyses for checks 1-10: one without factors; one with three
         levels, judgements (Yes parents for ③ and ④), a quality warning,
         saved details, and enough factors for every pane to scroll.
anomaly  analyses with every inconsistent parent link of J-25. The app and
         its API cannot make such data; it is written directly, and only
         into this separate database.

The app keeps its database in ./fta_tool.db of the folder it is started
from, so start it from the folder made here (see the manual-check guide):

    cd C:\\fta-check\\pr3-normal
    python -m uvicorn app.main:app --app-dir C:\\fta-check\\pr3-src\\fta_tool --port 8001
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

FTA_TOOL = pathlib.Path(__file__).resolve().parent.parent
if str(FTA_TOOL) not in sys.path:
    sys.path.insert(0, str(FTA_TOOL))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import models  # noqa: E402  (does not open the default database)

DB_NAME = "fta_tool.db"
MISSING_PARENT_ID = 999999  # no factor has this id in a new database

LONG_DESCRIPTION = (
    "外部の決済APIの応答が遅く、注文確定後の決済処理がタイムアウトしている可能性。"
    "ピーク時間帯に応答時間が伸び、アプリ側のタイムアウト値を超えると決済が未完了のまま残る。"
    "リトライで二重決済にならないかも併せて確認する。"
) * 2

LEVEL1 = [
    ("一次01 決済APIの応答遅延", "yes"),
    ("一次02 在庫引当の失敗", "yes"),
    ("一次03 注文データの不整合", "yes"),
    ("一次04 ネットワーク障害", "no"),
    ("一次05 認証トークンの期限切れ", "unknown"),
    ("一次06 バッチ処理との競合", "unknown"),
    ("一次07 DB接続プールの枯渇", "unknown"),
    ("一次08 設定値の誤り", "unknown"),
    ("一次09 リトライ処理の不具合", "unknown"),
    ("一次10 ログ出力の遅延", "unknown"),
    ("一次11 証明書の期限切れ", "unknown"),
    ("一次12 キャッシュの不整合", "unknown"),
    ("一次13 メッセージキューの滞留", "unknown"),
    ("一次14 時刻同期のずれ", "unknown"),
    ("一次15 負荷分散の偏り", "unknown"),
    ("一次16 ディスク容量の不足", "unknown"),
    ("一次17 依存ライブラリの更新", "unknown"),
    ("一次18 監視アラートの抑止", "unknown"),
    ("一次19 手順書の不備", "unknown"),
    ("一次20 担当者の操作ミス", "unknown"),
]
# parent (level-1 title prefix) -> [(title, judgement)]
LEVEL2 = {
    "一次01": [("二次01-1 タイムアウト値が短すぎる", "yes"), ("二次01-2 接続の再利用が無効", "yes"),
               ("二次01-3 決済事業者側の障害", "no"), ("二次01-4 通信経路の遅延", "unknown")],
    "一次02": [("二次02-1 在庫数の同時更新", "yes"), ("二次02-2 引当処理の例外", "unknown"),
               ("二次02-3 在庫マスタの同期遅れ", "unknown")],
    "一次03": [("二次03-1 注文番号の重複", "no"), ("二次03-2 文字コードの変換誤り", "unknown"),
               ("二次03-3 必須項目の欠落", "unknown")],
}
LEVEL3 = {
    "二次01-1": ["三次01-1-1 既定値のまま運用", "三次01-1-2 設定変更の反映漏れ", "三次01-1-3 環境ごとの差異"],
    "二次01-2": ["三次01-2-1 ライブラリの既定設定", "三次01-2-2 接続数の上限"],
    "二次02-1": ["三次02-1-1 排他制御の不足", "三次02-1-2 更新順序の逆転"],
}
WARNING_ON = "二次01-2"
WARNING_TEXT = "既存要因「二次01-1 タイムアウト値が短すぎる」に類似; 要因名が短く、内容が分かりにくい"


def new_database(folder: pathlib.Path) -> tuple[Session, pathlib.Path]:
    """A session on a new database in `folder`, which must be new or empty."""
    folder = pathlib.Path(folder).expanduser().resolve()
    if folder.exists():
        if not folder.is_dir():
            raise SystemExit(f"中止しました：フォルダではありません：{folder}")
        if any(folder.iterdir()):
            raise SystemExit(
                f"中止しました：フォルダが空ではありません：{folder}\n"
                "既存のデータベースを開いたり変更したりしないため、新しいフォルダか空のフォルダを指定してください。")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / DB_NAME
    engine = create_engine(f"sqlite:///{path}")
    models.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False)(), path


def _analysis(db: Session, title: str, top_event: str, system_context: str = "",
              incident_context: str = "") -> models.Analysis:
    context = ""
    if system_context or incident_context:
        context = json.dumps({"system_context": system_context, "incident_context": incident_context,
                              "demo_points": ""}, ensure_ascii=False)
    analysis = models.Analysis(title=title, top_event=top_event, analysis_context=context)
    db.add(analysis)
    db.flush()
    return analysis


def _node(db: Session, analysis: models.Analysis, level: int, title: str, parent_id=None, *,
          order: int = 0, judgement: str = "unknown", ai: bool = False, **fields) -> models.Node:
    node = models.Node(analysis_id=analysis.id, parent_id=parent_id, level=level, title=title,
                       user_judgement=judgement, ai_generated=ai, display_order=order,
                       description=fields.pop("description", f"{title}の説明"), **fields)
    db.add(node)
    db.flush()
    return node


def build_normal(db: Session) -> dict:
    empty = _analysis(db, "PR3確認：要因なし", "決済処理がタイムアウトする")
    full = _analysis(db, "PR3確認：三次まで", "注文確定後に決済が完了しない",
                     system_context="ECサイトの注文・決済システム（Web、決済API連携、在庫管理）",
                     incident_context="夕方のピーク時間帯に、注文確定後の決済未完了が複数発生した")
    by_prefix: dict[str, models.Node] = {}
    for order, (title, judgement) in enumerate(LEVEL1, start=1):
        extra = {}
        if title.startswith("一次01"):
            extra = dict(description=LONG_DESCRIPTION, memo="確認用のメモ（詳細ダイアログを開くと、この値が読み込まれる）",
                         evidence="決済APIの応答時間のログ（ピーク時に平均4秒）", prevention_idea="タイムアウト値と再試行の見直し")
        node = _node(db, full, 1, title, order=order, judgement=judgement, **extra)
        by_prefix[title.split()[0]] = node
    for parent_prefix, children in LEVEL2.items():
        for order, (title, judgement) in enumerate(children, start=1):
            extra = {}
            if title.startswith(WARNING_ON):
                extra["warning_flags"] = WARNING_TEXT
            if title.startswith("二次01-1"):
                extra["direct_cause_status"] = "likely"
            node = _node(db, full, 2, title, by_prefix[parent_prefix].id, order=order,
                         judgement=judgement, ai=True, **extra)
            by_prefix[title.split()[0]] = node
    for parent_prefix, titles in LEVEL3.items():
        for order, title in enumerate(titles, start=1):
            node = _node(db, full, 3, title, by_prefix[parent_prefix].id, order=order, ai=True)
            by_prefix[title.split()[0]] = node
    db.commit()
    return {"analyses": {"要因なし": empty.id, "三次まで": full.id},
            "titles": {empty.id: empty.title, full.id: full.title},
            "factors": {prefix: node.id for prefix, node in by_prefix.items()}}


def build_anomaly(db: Session) -> dict:
    """Every category of J-25 (plan 5.9.5), in a database of its own."""
    main = _analysis(db, "PR3確認：不整合", "在庫の引当が失敗する")
    other = _analysis(db, "PR3確認：別の分析", "別の分析の頂上事象")
    ids: dict[str, int] = {}

    def node(key, analysis, level, title, parent_id=None, **fields):
        created = _node(db, analysis, level, title, parent_id, order=len(ids) + 1, **fields)
        ids[key] = created.id
        return created

    root = node("正常な一次", main, 1, "一次A 正常な一次要因")
    second = node("正常な二次", main, 2, "二次A-1 正常な二次要因（下に別の分析の要因）", root.id)
    node("正常な三次", main, 3, "三次A-1-1 正常な三次要因", second.id)
    node("階層不一致", main, 3, "三次X 一次要因の直下の三次要因（階層不一致）", root.id)
    missing = node("親不在", main, 2, "二次M 親要因が存在しない（親不在）", MISSING_PARENT_ID)
    node("親不在の下", main, 3, "三次M-1 親不在の要因の下（上位に不整合あり）", missing.id)
    other_root = node("別の分析の一次", other, 1, "一次B 別の分析の一次要因")
    foreign = node("別分析の親", main, 2, "二次F 親が別の分析にある", other_root.id)
    node("別分析の親の下", main, 3, "三次F-1 別の分析の親の要因の下（上位に不整合あり）", foreign.id)
    node("別の分析から付く", other, 3, "三次B 別の分析の要因（二次A-1の下に付く）", second.id)
    self_ref = node("自己参照", main, 2, "二次S 自分自身が親（自己参照）")
    self_ref.parent_id = self_ref.id
    p = node("循環P", main, 1, "一次P 循環する要因P")
    q = node("循環Q", main, 2, "二次Q 循環する要因Q", p.id)
    p.parent_id = q.id  # P -> Q -> P
    node("循環の下", main, 3, "三次Q-1 循環の下の要因（上位に不整合あり）", q.id)
    db.commit()
    return {"analyses": {"不整合": main.id, "別の分析": other.id},
            "titles": {main.id: main.title, other.id: other.title}, "factors": ids}


BUILDERS = {"normal": build_normal, "anomaly": build_anomaly}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PR-3 の手動確認用のデータベースを新しいフォルダに作ります。")
    parser.add_argument("kind", choices=sorted(BUILDERS), help="normal：正常データ / anomaly：不整合データ")
    parser.add_argument("folder", type=pathlib.Path, help="新しいフォルダか空のフォルダ（ここに fta_tool.db を作る）")
    args = parser.parse_args(argv)
    db, path = new_database(args.folder)
    try:
        made = BUILDERS[args.kind](db)
    finally:
        db.close()
    print(f"作成しました：{path}")
    for analysis_id, title in made["titles"].items():
        print(f"  分析 ID {analysis_id}：{title}")
    print("このフォルダを作業フォルダにしてアプリを起動してください（手順書 docs/manual-check-pr3.md）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
