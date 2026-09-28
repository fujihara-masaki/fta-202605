"""Template structure tests for the UI redesign (plan 8.9).

T-01  No screen (list / new / detail) and no stylesheet or script refers to
      a resource on an external URL (link / script / img …, @import, url(),
      module imports), and no web font is declared (J-28).
T-02  Analysis list: title and 編集 links, export URLs with the download
      attribute, the factor-count data attribute, the empty state.

Also covered: the grouped factor count (crud.count_nodes_by_analysis), the
shared frame (skip link, live regions, aria-current), which screens still
load the legacy app.js / style.css, and the JavaScript MIME type that ES
modules need.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, models, schemas
from app.database import get_db
from app.main import app

STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "static"
EXTERNAL = re.compile(r"^\s*(?:https?:)?//", re.IGNORECASE)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


# ----- a small HTML tree for structural assertions ---------------------------

class Element:
    def __init__(self, tag: str, attrs: list[tuple[str, str | None]], parent: "Element | None"):
        self.tag = tag
        self.attrs = {name: (value if value is not None else "") for name, value in attrs}
        self.parent = parent
        self.children: list[Element | str] = []

    def iter(self):
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.iter()

    def find_all(self, tag: str | None = None, **attrs) -> list["Element"]:
        found = []
        for element in self.iter():
            if element is self:
                continue
            if tag and element.tag != tag:
                continue
            if all(
                (name in element.attrs) if value is True else element.attrs.get(name) == value
                for name, value in attrs.items()
            ):
                found.append(element)
        return found

    def find(self, tag: str | None = None, **attrs) -> "Element":
        found = self.find_all(tag, **attrs)
        assert found, f"<{tag} {attrs}> not found"
        return found[0]

    def text(self) -> str:
        parts = []
        for child in self.children:
            parts.append(child if isinstance(child, str) else child.text())
        return "".join(parts)

    def is_hidden(self) -> bool:
        return "hidden" in self.attrs


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("#document", [], None)
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        element = Element(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(element)
        if tag not in VOID_TAGS:
            self.stack.append(element)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Element(tag, attrs, self.stack[-1]))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(html: str) -> Element:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


# ----- fixtures ---------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        c.SessionLocal = TestingSessionLocal
        yield c
    app.dependency_overrides.clear()


def _create(client, title, *, top_event="", context="", updated_at=None, node_titles=()):
    db = client.SessionLocal()
    try:
        analysis = crud.create_analysis(db, schemas.AnalysisCreate(
            title=title, top_event=top_event, analysis_context=context))
        parent_id = None
        for index, node_title in enumerate(node_titles):
            node = crud.create_node(db, analysis.id, {
                "parent_id": parent_id,
                "level": 1 if parent_id is None else 2,
                "title": node_title,
                "description": "",
                "ai_generated": False,
                "user_judgement": "unknown",
                "direct_cause_status": "unknown",
                "display_order": index,
                "warning_flags": "",
            })
            if parent_id is None:
                parent_id = node.id
        if updated_at is not None:
            analysis = crud.get_analysis(db, analysis.id)
            analysis.updated_at = updated_at
            db.commit()
        return analysis.id
    finally:
        db.close()


def _external_refs(root: Element) -> list[str]:
    refs = []
    for element in root.iter():
        for attr in ("src", "href", "data", "poster", "srcset"):
            if element.tag == "a" and attr == "href":
                continue  # navigation, not a loaded resource
            value = element.attrs.get(attr)
            if value and EXTERNAL.search(value):
                refs.append(f"<{element.tag} {attr}={value}>")
        style = element.attrs.get("style", "")
        refs += _css_external_refs(style)
        if element.tag == "style":
            refs += _css_external_refs(element.text())
    return refs


def _css_external_refs(css: str) -> list[str]:
    refs = []
    for match in re.finditer(r"@import\s+(?:url\()?\s*['\"]?([^'\")\s;]+)", css, re.IGNORECASE):
        if EXTERNAL.search(match.group(1)):
            refs.append(f"@import {match.group(1)}")
    for match in re.finditer(r"url\(\s*['\"]?([^'\")]+)", css, re.IGNORECASE):
        if EXTERNAL.search(match.group(1)):
            refs.append(f"url({match.group(1)})")
    return refs


# ----- T-01 -------------------------------------------------------------------

def test_T01_screens_do_not_load_external_resources(client):
    analysis_id = _create(
        client, "外部参照の確認", top_event="頂上事象",
        context='{"system_context": "構成", "incident_context": "状況", "demo_points": "観点"}',
        node_titles=("一次要因", "二次要因"),
    )
    for path in ("/", "/analyses/new", f"/analyses/{analysis_id}"):
        response = client.get(path)
        assert response.status_code == 200, path
        root = parse(response.text)
        assert _external_refs(root) == [], path
        # Every stylesheet and script the screen loads is served by the app.
        for element in root.find_all("link", rel="stylesheet") + root.find_all("script", src=True):
            url = element.attrs.get("href") or element.attrs.get("src")
            assert url.startswith("/static/"), (path, url)
            assert client.get(url).status_code == 200, url


def test_T01_static_css_and_js_have_no_external_urls_or_web_fonts():
    css_files = sorted(STATIC_DIR.rglob("*.css"))
    js_files = sorted(STATIC_DIR.rglob("*.js"))
    assert css_files and js_files
    for path in css_files:
        css = path.read_text(encoding="utf-8")
        assert _css_external_refs(css) == [], path
        assert "@font-face" not in css, path
    import_pattern = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*)['"]((?:https?:)?//[^'"]+)""")
    fetch_pattern = re.compile(r"""\bfetch\(\s*['"`](?:https?:)?//""")
    for path in js_files:
        js = path.read_text(encoding="utf-8")
        assert import_pattern.findall(js) == [], path
        assert not fetch_pattern.search(js), path


def test_T01_font_stack_is_local_only():
    tokens = (STATIC_DIR / "css" / "tokens.css").read_text(encoding="utf-8")
    match = re.search(r"--font-sans:\s*([^;]+);", tokens)
    assert match
    assert match.group(1).split(",")[0].strip() == '"BIZ UDPGothic"'
    assert match.group(1).strip().endswith("sans-serif")


# ----- T-02 -------------------------------------------------------------------

def test_T02_list_rows_links_exports_and_factor_counts(client):
    now = dt.datetime(2026, 9, 1, 12, 0, 0)
    a = _create(client, "分析A", top_event="Aの頂上事象", node_titles=("A1", "A1-1", "A1-2"),
                updated_at=now - dt.timedelta(hours=1))
    b = _create(client, "<script>alert(1)</script> & 分析B", updated_at=now)
    c = _create(client, "分析C", node_titles=("C1",), updated_at=now - dt.timedelta(hours=2))

    root = parse(client.get("/").text)
    rows = root.find_all("tr", **{"data-analysis-id": True})
    assert [int(r.attrs["data-analysis-id"]) for r in rows] == [b, a, c]  # updated_at desc
    counts = {int(r.attrs["data-analysis-id"]): int(r.attrs["data-factor-count"]) for r in rows}
    assert counts == {a: 3, b: 0, c: 1}
    assert root.find(**{"data-analysis-count": True}).text() == "3"

    for row in rows:
        analysis_id = int(row.attrs["data-analysis-id"])
        title_link = row.find("a", **{"data-title-link": True})
        assert title_link.attrs["href"] == f"/analyses/{analysis_id}"
        assert title_link.text() == row.attrs["data-title"]
        assert row.find("a", **{"data-edit-link": True}).attrs["href"] == f"/analyses/{analysis_id}"
        rename = row.find("button", **{"data-action": "rename"})
        assert rename.attrs["aria-label"] == f"タイトルを変更：{row.attrs['data-title']}"
        assert row.find("button", **{"data-action": "delete"})

        menu_button = row.find("button", **{"data-ui-menu-button": True})
        assert menu_button.attrs["aria-expanded"] == "false"
        panel = row.find(id=menu_button.attrs["aria-controls"])
        assert panel.is_hidden()
        exports = panel.find_all("a")
        assert [e.attrs["href"] for e in exports] == [
            f"/analyses/{analysis_id}/export/json",
            f"/analyses/{analysis_id}/export/csv",
            f"/analyses/{analysis_id}/export/markdown",
        ]
        assert all("download" in e.attrs for e in exports)

    # User text is escaped: shown as text, never as markup.
    html = client.get("/").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; 分析B" in html
    assert not [s for s in root.find_all("script") if "alert(1)" in s.text()]

    assert not root.find(**{"data-list-table": True}).is_hidden()
    assert root.find(**{"data-empty-state": True}).is_hidden()


def test_T02_empty_list_shows_the_empty_state(client):
    root = parse(client.get("/").text)
    assert root.find_all("tr", **{"data-analysis-id": True}) == []
    empty = root.find(**{"data-empty-state": True})
    assert not empty.is_hidden()
    assert "分析がまだありません" in empty.text()
    assert empty.find("a").attrs["href"] == "/analyses/new"
    assert root.find(**{"data-list-table": True}).is_hidden()
    assert root.find(**{"data-analysis-count": True}).text() == "0"


def test_T02_export_menu_describes_the_contents_of_each_format(client):
    analysis_id = _create(client, "出力の説明")
    panel = parse(client.get("/").text).find(id=f"export-menu-{analysis_id}")
    descriptions = {a.attrs["data-export-format"]: a.text() for a in panel.find_all("a")}
    assert "要因のすべての項目" in descriptions["json"]
    assert "分析タイトル・頂上事象・参考情報は含みません" in descriptions["csv"]
    assert "分析タイトル・説明・AI／手動・根拠・メモ・品質警告は含みません" in descriptions["markdown"]


# ----- supporting checks -------------------------------------------------------

def test_count_nodes_by_analysis_uses_one_grouped_result(client):
    a = _create(client, "件数A", node_titles=("1", "2", "3"))
    b = _create(client, "件数B")
    c = _create(client, "件数C", node_titles=("1",))
    db = client.SessionLocal()
    try:
        assert crud.count_nodes_by_analysis(db) == {a: 3, c: 1}
        assert b not in crud.count_nodes_by_analysis(db)
    finally:
        db.close()


def test_shared_frame_on_every_screen(client):
    analysis_id = _create(client, "共通の枠")
    expectations = {
        "/": ("分析一覧", False),
        "/analyses/new": ("新規作成", True),
        f"/analyses/{analysis_id}": (None, True),
    }
    for path, (current, legacy) in expectations.items():
        root = parse(client.get(path).text)
        skip = root.find("a", **{"class": "skip-link"})
        assert skip.attrs["href"] == "#main" and root.find("main", id="main")
        assert root.find(id="ui-live-status").attrs["role"] == "status"
        assert root.find(id="ui-live-alert").attrs["role"] == "alert"
        nav = root.find("nav")
        current_links = [a.text() for a in nav.find_all("a", **{"aria-current": "page"})]
        assert current_links == ([current] if current else []), path
        scripts = [s.attrs.get("src") for s in root.find_all("script", src=True)]
        styles = [s.attrs.get("href") for s in root.find_all("link", rel="stylesheet")]
        assert "/static/js/common/boot.js" in scripts
        assert "/static/css/tokens.css" in styles
        # Screens not migrated yet keep the legacy script, stylesheet and toast.
        assert ("/static/app.js" in scripts) is legacy, path
        assert ("/static/style.css" in styles) is legacy, path
        assert bool(root.find_all(id="toast")) is legacy, path


def test_javascript_is_served_with_a_javascript_mime_type(client):
    for path in ("/static/js/common/boot.js", "/static/js/pages/list.js", "/static/app.js"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/javascript"), path
