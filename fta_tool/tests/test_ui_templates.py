"""Template structure tests for the UI redesign (plan 8.9).

T-01  No screen (list / new / detail) and no stylesheet or script refers to
      a resource on an external URL (link / script / img …, @import, url(),
      module imports), and no web font is declared (J-28).
T-02  Analysis list: title and 編集 links, export URLs with the download
      attribute, the factor-count data attribute, the empty state.
T-03  New analysis: the form posts the same field names (ids kept), the
      sample data is embedded as JSON (not script) and cannot break out of
      its block, demo_points is a hidden field, and without a readable
      sample file the form has no sample panel and still creates.

Also covered: the grouped factor count (crud.count_nodes_by_analysis), the
shared frame (skip link, live regions, aria-current), which screens still
load the legacy app.js / style.css, and the JavaScript MIME type that ES
modules need.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app import crud, models, schemas
from app.database import get_db
from app.main import app
from app.services import sample_scenarios

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

    def text_without_scripts(self) -> str:
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag not in ("script", "style"):
                parts.append(child.text_without_scripts())
        return "".join(parts)


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


# ----- T-03 -------------------------------------------------------------------

# POST /analyses fields (unchanged contract) -> (tag, id). The ids are the
# ones the old form used.
NEW_FORM_FIELDS = {
    "title": ("input", "title"),
    "top_event": ("textarea", "top_event"),
    "system_context": ("textarea", "systemContextInput"),
    "incident_context": ("textarea", "incidentContextInput"),
    "demo_points": ("input", "demoPointsInput"),
}
SAMPLE_KEYS = {"id", "category", "title", "top_event", "system_context", "incident_context", "demo_points"}


def _new_form(client) -> tuple[Element, str]:
    response = client.get("/analyses/new")
    assert response.status_code == 200
    return parse(response.text), response.text


def test_T03_new_form_posts_the_same_fields(client):
    root, _ = _new_form(client)
    form = root.find("form", id="new-analysis-form")
    assert form.attrs["method"] == "post" and form.attrs["action"] == "/analyses"
    named = [e for e in form.iter() if e.tag in ("input", "textarea", "select", "button") and e.attrs.get("name")]
    assert {e.attrs["name"]: (e.tag, e.attrs.get("id")) for e in named} == NEW_FORM_FIELDS

    for name in ("title", "top_event", "system_context", "incident_context"):
        field_id = NEW_FORM_FIELDS[name][1]
        assert root.find("label", **{"for": field_id}), name  # visible, labelled
    title = form.find("input", id="title")
    assert title.attrs["type"] == "text" and "required" in title.attrs
    # 255 is counted in code points by the screen (J-22); maxlength would
    # count UTF-16 units and cut titles with characters such as 𠮷.
    assert "maxlength" not in title.attrs
    assert set(title.attrs["aria-describedby"].split()) == {"title-help", "title-error"}
    assert root.find(id="title-error").is_hidden()
    demo = form.find("input", id="demoPointsInput")
    assert demo.attrs["type"] == "hidden" and demo.attrs["value"] == ""
    assert "name" not in root.find("select", id="sampleSelect").attrs  # not sent

    submit = form.find("button", type="submit")
    assert submit.text() == "作成して編集へ"
    cancel = form.find("a", **{"data-cancel-link": True})
    assert cancel.attrs["href"] == "/" and cancel.text() == "キャンセル"


def test_T03_new_form_layout_and_scripts(client):
    root, _ = _new_form(client)
    assert root.find("title").text() == "新規FTA分析作成"
    assert root.find("h1").text() == "新規FTA分析を作成"
    main_column = root.find(**{"class": "new-page__main"})
    aside = root.find("aside", **{"class": "new-page__aside"})
    assert [h.text() for h in main_column.find_all("h2")] == ["1 分析の名前と頂上事象", "2 AIへの参考情報 任意"]
    assert [h.text() for h in aside.find_all("h2")] == ["入力の使われ方", "サンプルから入力 デモ用"]
    usage = aside.find("dl", **{"class": "new-usage"})
    assert [term.text() for term in usage.find_all("dt")] == ["頂上事象", "AIへの参考情報", "作成後"]
    status = root.find(**{"data-sample-status": True})
    assert status.is_hidden() and "サンプルを転記済み・未保存" in status.text()

    # No inline script is left: modules from /static and the sample data.
    scripts = root.find_all("script")
    for script in scripts:
        assert script.attrs.get("src", "").startswith("/static/") or script.attrs.get("type") == "application/json"
    modules = [s.attrs["src"] for s in scripts if s.attrs.get("type") == "module"]
    assert modules == ["/static/js/common/boot.js", "/static/js/pages/new.js"]
    styles = [s.attrs["href"] for s in root.find_all("link", rel="stylesheet")]
    assert styles == ["/static/css/tokens.css", "/static/css/base.css", "/static/css/components.css", "/static/css/new.css"]
    assert not [e for e in root.iter() if any(name.startswith("on") for name in e.attrs)]  # no inline handlers


def test_T03_sample_data_is_embedded_as_json(client):
    samples = main_module.get_sample_scenarios()
    assert samples, "config/sample_scenarios.yaml provides the demo samples"
    root, _ = _new_form(client)
    node = root.find("script", id="sample-scenarios-data")
    assert node.attrs["type"] == "application/json"
    data = json.loads(node.text())
    assert data == samples
    for sample in data:
        assert SAMPLE_KEYS <= set(sample)
        assert all(isinstance(sample[key], str) for key in SAMPLE_KEYS)

    options = root.find("select", id="sampleSelect").find_all("option")
    assert [(o.attrs["value"], o.text()) for o in options] == [("", "選択してください")] + [
        (s["id"], f"[{s['category']}] {s['title']}") for s in samples
    ]
    preview = root.find(id="samplePreview")
    assert preview.is_hidden()
    assert preview.find("button", **{"data-apply-sample": True}).text() == "この内容を入力欄へ転記"
    # demo_points are data only: never rendered as text.
    shown = root.text_without_scripts()
    for sample in samples:
        assert sample["demo_points"].strip().splitlines()[0] not in shown


def test_T03_sample_text_is_data_not_markup(client, monkeypatch):
    evil = {
        "id": "evil\"'<>",
        "category": "<b>カテゴリ</b>",
        "title": "</script><script>alert(1)</script>",
        "top_event": "</script><!-- <script>",
        "system_context": "<img src=x onerror=alert(2)>",
        "incident_context": "& &amp;   '",
        "demo_points": "</SCRIPT>",
    }
    monkeypatch.setattr(main_module, "get_sample_scenarios", lambda: [evil])
    root, html = _new_form(client)
    assert json.loads(root.find("script", id="sample-scenarios-data").text()) == [evil]
    # The data can neither close its <script> element nor start markup.
    assert html.lower().count("</script>") == len(root.find_all("script"))
    assert "<script>alert(1)" not in html and "<img src=x" not in html
    option = root.find("select", id="sampleSelect").find_all("option")[1]
    assert option.attrs["value"] == evil["id"]
    assert option.text() == f"[{evil['category']}] {evil['title']}"


@pytest.mark.parametrize("problem", ["missing", "broken"])
def test_T03_new_form_without_a_readable_sample_file(client, monkeypatch, tmp_path, problem):
    path = tmp_path / "sample_scenarios.yaml"
    if problem == "broken":
        path.write_text("scenarios: [\n  - id: [unclosed\n", encoding="utf-8")
    monkeypatch.setenv("FTA_SAMPLE_SCENARIOS_FILE", str(path))
    monkeypatch.setattr(sample_scenarios, "_cache", None)  # read the file again

    root, _ = _new_form(client)
    assert not root.find_all(**{"data-sample-panel": True})
    assert not root.find_all("select", id="sampleSelect")
    assert not root.find_all("script", id="sample-scenarios-data")
    assert root.find("h2", id="new-usage-title").text() == "入力の使われ方"
    form = root.find("form", id="new-analysis-form")
    named = [e for e in form.iter() if e.attrs.get("name")]
    assert {e.attrs["name"]: (e.tag, e.attrs.get("id")) for e in named} == NEW_FORM_FIELDS

    response = client.post("/analyses", data={
        "title": "サンプルなしで作成", "top_event": "頂上事象",
        "system_context": "構成", "incident_context": "", "demo_points": "",
    }, follow_redirects=False)
    assert response.status_code == 303
    assert re.fullmatch(r"/analyses/\d+", response.headers["location"])


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
        "/analyses/new": ("新規作成", False),  # migrated in PR-2
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
    for path in ("/static/js/common/boot.js", "/static/js/pages/list.js", "/static/js/pages/new.js", "/static/app.js"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/javascript"), path
