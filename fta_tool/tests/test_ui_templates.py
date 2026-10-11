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
        c.engine = engine
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
        # The edit screen still loads the legacy script and stylesheet (PR-3);
        # its messages use the shared notifications, so no page renders the
        # old toast any more (判断4).
        assert ("/static/app.js" in scripts) is legacy, path
        assert ("/static/style.css" in styles) is legacy, path
        assert not root.find_all(id="toast"), path


def test_javascript_is_served_with_a_javascript_mime_type(client):
    edit_modules = sorted((STATIC_DIR / "js" / "pages" / "edit").glob("*.js"))
    assert edit_modules
    paths = ["/static/js/common/boot.js", "/static/js/pages/list.js", "/static/js/pages/new.js",
             "/static/js/pages/edit.js", "/static/app.js"]
    paths += [f"/static/js/pages/edit/{module.name}" for module in edit_modules]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/javascript"), path


# ----- T-04 -------------------------------------------------------------------
# Analysis edit (B), PR-3 skeleton: regions, the embedded summary, data-node-id
# on every representation, broken parent links (J-25), tags (J-14), counts.

EDIT_REGIONS = {"steps", "nav", "work-2", "work-3", "work-4", "work-anomalies", "tree", "table", "summary"}
SUMMARY_KEYS = {
    "id", "parentId", "level", "title", "description", "judgement", "directCause", "ai", "warning", "memo",
    "kind", "label", "notes", "anomalyRoot", "canParent", "parentReason", "delete",
}


def _raw_node(client, analysis_id, level, parent_id=None, *, title, judgement="unknown", description="",
              ai=False, warning="", memo="", direct="unknown"):
    """A factor inserted directly (parent links the API never makes)."""
    with client.engine.begin() as conn:
        result = conn.execute(models.Node.__table__.insert().values(
            analysis_id=analysis_id, parent_id=parent_id, level=level, title=title,
            description=description, ai_generated=ai, user_judgement=judgement,
            direct_cause_status=direct, display_order=0, memo=memo, warning_flags=warning,
        ))
        return result.inserted_primary_key[0]


def _set_parent(client, node_id, parent_id):
    with client.engine.begin() as conn:
        conn.execute(models.Node.__table__.update().where(models.Node.id == node_id).values(parent_id=parent_id))


def _edit_page(client, analysis_id):
    response = client.get(f"/analyses/{analysis_id}")
    assert response.status_code == 200
    return response.text, parse(response.text)


def _summary(root):
    return json.loads(root.find("script", id="analysis-data").text())


def test_T04_edit_regions_steps_tabs_and_moved_inputs(client):
    analysis_id = _create(client, "編集画面の構造", top_event="頂上事象",
                          context='{"system_context": "構成", "incident_context": "状況"}')
    html, root = _edit_page(client, analysis_id)

    assert {e.attrs["data-region"] for e in root.find_all(**{"data-region": True})} == EDIT_REGIONS
    steps = root.find("nav", **{"aria-label": "作業ステップ"}).find_all("button", **{"data-action": "step"})
    assert [b.attrs["data-step"] for b in steps] == ["1", "2", "3", "4", "5"]
    assert [b.find(**{"class": "edit-step__name"}).text() for b in steps] == [
        "頂上事象・参考情報", "一次要因", "二次要因", "三次要因", "確認・出力"]
    tablist = root.find(role="tablist")
    tabs = tablist.find_all("button", role="tab")
    assert [(t.attrs["id"], t.attrs["aria-controls"], t.text()) for t in tabs] == [
        ("edit-tab-work", "edit-panel-work", "作業"),
        ("edit-tab-tree", "edit-panel-tree", "ツリー"),
        ("edit-tab-table", "edit-panel-table", "一覧表"),
    ]
    for view in ("work", "tree", "table"):
        assert root.find("section", id=f"edit-panel-{view}").attrs["role"] == "tabpanel"
    for element_id in ("edit-nav", "edit-work-area", "edit-inspector", "edit-filter-text", "edit-filter-judgement"):
        root.find(id=element_id)
    root.find(**{"data-inspector-body": True})

    # Skip links to the work list and the inspector (plan 5.7).
    skip = {a.text(): a.attrs["href"] for a in root.find_all("a", **{"class": "skip-link"})}
    assert skip == {"本文へ移動": "#main", "作業リストへ": "#edit-work-area", "インスペクタへ": "#edit-inspector"}

    # Step ① (PR-4): the same ids and saved values, a save status per input
    # (保存済み when the page opens), save buttons wired by the module (no
    # inline handlers), and the explanation of the automatic save (J-09).
    top = root.find("textarea", id="topEventInput")
    assert (top.text(), top.attrs["data-saved"]) == ("頂上事象", "頂上事象")
    assert root.find("textarea", id="systemContextInput").attrs["data-saved"] == "構成"
    assert root.find("textarea", id="incidentContextInput").attrs["data-saved"] == "状況"
    assert "filled" in root.find(id="analysisContextStatus").attrs["class"].split()
    for field_id in ("topEventInput", "systemContextInput", "incidentContextInput"):
        status = root.find(**{"data-save-status": field_id})
        assert (status.attrs["data-state"], status.text()) == ("saved", "保存済み")
    step1 = root.find("section", **{"data-step-panel": "1"})
    assert [b.text() for b in step1.find_all("button", **{"data-save-button": True})] == ["頂上事象を保存", "参考情報を保存"]
    assert not [b for b in step1.find_all("button") if "onclick" in b.attrs]
    note = step1.find(**{"data-autosave-note": True}).text()
    assert "一次要因の生成（通常・追加）の前に、入力中の頂上事象と参考情報を自動で保存します" in note
    assert "頂上事象は保存済みの値を使います（入力中の頂上事象は使われません）" in note

    # Header (PR-4): the title as text with ✎ and an inline editor (hidden),
    # the list's export menu and 一覧へ; no updated time (J-15).
    header = root.find(**{"class": "edit-header"})
    title = header.find("h1", id="analysisTitle")
    assert title.text() == "編集画面の構造" and "contenteditable" not in title.attrs
    assert header.find("button", **{"data-title-edit": True}).attrs["aria-label"] == "分析タイトルを変更：編集画面の構造"
    editor = header.find(**{"data-title-editor": True})
    assert "hidden" in editor.attrs
    title_input = editor.find("input", id="analysisTitleInput")
    assert (title_input.attrs["value"], title_input.attrs["data-saved"]) == ("編集画面の構造", "編集画面の構造")
    assert [b.text() for b in editor.find_all("button")] == ["保存", "取消"]
    assert not [e for e in header.find_all() if "onclick" in e.attrs or "onblur" in e.attrs]
    menu = header.find(**{"data-ui-menu": True})
    assert menu.find("button", **{"data-ui-menu-button": True}).attrs["aria-expanded"] == "false"
    header_links = [(a.attrs["href"], "download" in a.attrs) for a in header.find_all("a")]
    assert header_links == [(f"/analyses/{analysis_id}/export/{fmt}", True) for fmt in ("json", "csv", "markdown")] + [("/", False)]
    assert "更新" not in header.find(**{"class": "edit-header__title"}).text()
    step5 = [a for a in root.find("section", **{"data-step-panel": "5"}).find_all("a")]
    assert [(a.attrs["href"], "download" in a.attrs) for a in step5] == [
        (f"/analyses/{analysis_id}/export/{fmt}", True) for fmt in ("json", "csv", "markdown")]

    # PR-5 replaced the legacy detail and manual-add modals (the inspector's
    # editor and the in-page dialogs); the generation overlay stays until PR-6.
    root.find(id="loadingOverlay")
    for element_id in ("nodeDetailModal", "addNodeModal"):
        assert not root.find_all(id=element_id), element_id
    assert not root.find_all(**{"data-action": "legacy-add"})
    assert not root.find_all(**{"data-action": "legacy-detail"})
    assert not root.find_all(**{"data-action": "legacy-delete"})
    assert root.find_all("button", **{"data-action": "add", "data-level": "1"})  # ② 手動追加: the dialog

    # Scripts: the module and the legacy script by URL; the only inline
    # script is the embedded data.
    scripts = root.find_all("script")
    inline = [s for s in scripts if "src" not in s.attrs]
    assert [(s.attrs.get("type"), s.attrs.get("id")) for s in inline] == [("application/json", "analysis-data")]
    sources = [s.attrs["src"] for s in scripts if "src" in s.attrs]
    assert "/static/js/pages/edit.js" in sources and "/static/app.js" in sources
    styles = [s.attrs["href"] for s in root.find_all("link", rel="stylesheet")]
    assert "/static/css/edit.css" in styles and "/static/style.css" in styles
    assert "ui-page" in root.find("body").attrs["class"].split()


def test_T04_embedded_summary_shape_and_content(client, monkeypatch):
    monkeypatch.setenv("FTA_PRIMARY_FACTOR_COUNT", "5")
    monkeypatch.setenv("FTA_SECONDARY_FACTOR_COUNT", "4")
    monkeypatch.setenv("FTA_TERTIARY_FACTOR_COUNT", "3")
    monkeypatch.setenv("FTA_ADDITIONAL_FACTOR_COUNT", "1")
    analysis_id = _create(client, "埋め込みデータ",
                          context='{"system_context": "構成", "incident_context": "状況", "demo_points": "デモ観点Q-秘匿"}')
    root_id = _raw_node(client, analysis_id, 1, title="一次</script><script>alert(1)</script>", judgement="yes",
                        description="説明A", ai=True, memo="メモの本文M", direct="likely")
    child_id = _raw_node(client, analysis_id, 2, root_id, title="二次", warning="既存要因に類似")
    html, root = _edit_page(client, analysis_id)

    summary = _summary(root)
    assert summary["analysisId"] == analysis_id
    assert summary["factorCounts"] == {"1": 5, "2": 4, "3": 3, "additional": 1}
    assert summary["lookupsOk"] is True
    nodes = {n["id"]: n for n in summary["nodes"]}
    assert [n["id"] for n in summary["nodes"]] == [root_id, child_id]  # server order
    for node in summary["nodes"]:
        assert set(node) == SUMMARY_KEYS
    first = nodes[root_id]
    assert (first["parentId"], first["level"], first["title"], first["description"]) == (
        None, 1, "一次</script><script>alert(1)</script>", "説明A")
    assert (first["judgement"], first["directCause"], first["ai"], first["warning"], first["memo"]) == (
        "yes", "likely", True, False, True)
    # delete.scope (PR-5): what the server's walk found the delete would
    # remove, the factor itself included (the dialog shows scope - 1 descendants).
    assert (first["kind"], first["canParent"], first["delete"]) == (
        "ok", True, {"allowed": True, "reason": "", "scope": 2})
    second = nodes[child_id]
    assert second["delete"] == {"allowed": True, "reason": "", "scope": 1}
    assert (second["parentId"], second["warning"], second["memo"], second["ai"]) == (root_id, True, False, False)

    # Never in the page: demo_points and the memo text (only whether there is one).
    assert "デモ観点Q" not in html
    assert "メモの本文M" not in html
    # The title cannot leave the JSON block.
    assert "</script><script>alert(1)" not in html
    assert len(root.find_all("script")) == len(re.findall(r"<script\b", html))


def test_T04_every_representation_carries_data_node_id(client):
    analysis_id = _create(client, "表示の対応", top_event="頂上")
    a = _raw_node(client, analysis_id, 1, title="一次A", judgement="yes")
    b = _raw_node(client, analysis_id, 2, a, title="二次B")
    c = _raw_node(client, analysis_id, 3, b, title="三次C")
    d = _raw_node(client, analysis_id, 1, title="一次D")
    broken = _raw_node(client, analysis_id, 2, 99999, title="親不在")
    html, root = _edit_page(client, analysis_id)

    for node_id in (a, b, c, d, broken):
        for role in ("nav", "tree", "table"):
            buttons = root.find_all("button", **{"data-action": "select", "data-role": role, "data-node-id": str(node_id)})
            assert len(buttons) == 1, (role, node_id)
        for role in ("nav-item", "work-item", "tree-item", "table-item"):
            assert len(root.find_all(**{"data-role": role, "data-node-id": str(node_id)})) == 1, (role, node_id)
    # Parent groups of ③ and ④ for the consistent parents.
    assert sorted(int(e.attrs["data-node-id"]) for e in root.find_all(**{"data-role": "group-item"})) == sorted([a, b, d])
    work = {int(e.attrs["data-node-id"]): e for e in root.find_all("li", **{"data-role": "work-item"})}
    step = {n: e for n in (2, 3, 4) for e in [root.find("section", **{"data-step-panel": str(n)})]}
    assert {int(e.attrs["data-node-id"]) for e in step[2].find_all("li", **{"data-role": "work-item"})} == {a, d}
    assert {int(e.attrs["data-node-id"]) for e in step[3].find_all("li", **{"data-role": "work-item"})} == {b}
    assert {int(e.attrs["data-node-id"]) for e in step[4].find_all("li", **{"data-role": "work-item"})} == {c}
    assert work[broken].attrs["class"].split() == ["edit-row", "edit-row--anomaly"]
    # Judgement toggles of the work list start from the saved value.
    toggle = root.find(**{"data-judgement-toggle": True, "data-node-id": str(a)})
    assert [(b_.attrs["data-value"], b_.attrs["aria-pressed"]) for b_ in toggle.find_all("button")] == [
        ("yes", "true"), ("no", "false"), ("unknown", "false")]


def test_T04_broken_parent_links_are_named_and_never_the_top_event(client):
    analysis_id = _create(client, "不正な親子関係", top_event="頂上")
    other = _create(client, "別の分析")
    root_id = _raw_node(client, analysis_id, 1, title="正常な一次")
    missing = _raw_node(client, analysis_id, 2, 99999, title="親不在の二次")
    foreign_parent = _raw_node(client, other, 1, title="別分析の一次")
    foreign = _raw_node(client, analysis_id, 2, foreign_parent, title="別分析が親の二次")
    self_ref = _raw_node(client, analysis_id, 2, title="自己参照の二次")
    _set_parent(client, self_ref, self_ref)
    p = _raw_node(client, analysis_id, 2, title="循環P")
    q = _raw_node(client, analysis_id, 1, p, title="循環Q")
    _set_parent(client, p, q)
    skipped = _raw_node(client, analysis_id, 3, root_id, title="一次の下の三次")
    below = _raw_node(client, analysis_id, 3, missing, title="親不在の下の三次")
    html, root = _edit_page(client, analysis_id)

    expected = {
        missing: "（親が見つかりません：ID 99999）",
        foreign: f"（別の分析の要因を親にしています：ID {foreign_parent}）",
        self_ref: "（自分自身を親にしています）",
        p: "（親子関係が循環しています）",
        q: "（親子関係が循環しています）",
        skipped: "（階層が合いません：親は一次）",
    }
    rows = {int(r.attrs["data-node-id"]): r for r in root.find_all("tr", **{"data-role": "table-item"})}
    for node_id, label in expected.items():
        parent_cell = rows[node_id].find("td", **{"class": "edit-table__parent"})
        assert parent_cell.text().strip() == label, node_id
    assert rows[below].find("td", **{"class": "edit-table__parent"}).text().startswith("親不在の二次")
    assert rows[root_id].find("td", **{"class": "edit-table__parent"}).text() == "（頂上事象）"
    parent_cells = [r.find("td", **{"class": "edit-table__parent"}).text() for r in rows.values()]
    assert parent_cells.count("（頂上事象）") == 1  # only the consistent 一次要因 (C-09)

    # The group at the end of the navigation, the tree and the work list.
    for role, container in (("nav", root.find("nav", id="edit-nav")), ("tree", root.find(id="edit-panel-tree")),
                            ("work", root.find(**{"data-region": "work-anomalies"}))):
        group = container.find("section", **{"class": "edit-anomalies" if role == "work" else f"edit-anomalies edit-anomalies--{role}"})
        assert "親子関係に不整合がある要因（7件）" in group.text()
        ids = {int(e.attrs["data-node-id"]) for e in group.find_all(**{"data-role": f"{role}-item"})}
        assert ids == {missing, foreign, self_ref, p, q, skipped, below}, role
        text = group.text()
        for label in expected.values():
            assert label in text, (role, label)
        assert "上位に不整合あり" in text
    # None of them below the top event in the outlines.
    top_tree = root.find("nav", id="edit-nav").find("li", **{"class": "edit-outline__item edit-outline__item--top"})
    assert {int(e.attrs["data-node-id"]) for e in top_tree.find_all(**{"data-role": "nav-item"})} == {root_id}


def test_T04_tags_step_counts_and_generation_targets(client):
    analysis_id = _create(client, "件数とタグ", top_event="頂上")
    a = _raw_node(client, analysis_id, 1, title="一次A", judgement="yes", direct="likely", memo="メモ", ai=True)
    b = _raw_node(client, analysis_id, 1, title="一次B", judgement="no")
    _raw_node(client, analysis_id, 2, a, title="二次A1", warning="要因名が長すぎる")
    _raw_node(client, analysis_id, 2, a, title="二次A2", judgement="yes")
    broken = _raw_node(client, analysis_id, 1, a, title="親のある一次", judgement="yes")  # level mismatch
    html, root = _edit_page(client, analysis_id)

    row_a = root.find("li", **{"data-role": "work-item", "data-node-id": str(a)})
    tags = [t.text() for t in row_a.find_all(**{"class": "ui-tag ui-tag--direct"})]
    assert tags == ["直接要因評価：可能性高"]  # J-14: with the item name
    assert row_a.find(**{"class": "ui-tag ui-tag--memo"}).text() == "メモあり"
    assert row_a.find(**{"class": "ui-tag ui-tag--ai"}).text() == "AI"
    row_b = root.find("li", **{"data-role": "work-item", "data-node-id": str(b)})
    assert row_b.find(**{"class": "ui-tag ui-tag--manual"}).text() == "手動"
    assert not row_b.find_all(**{"class": "ui-tag ui-tag--memo"})
    warn = root.find("button", **{"data-role": "work-warning"})
    assert (warn.text(), warn.attrs["data-focus"]) == ("要確認", "warning")

    statuses = {s.attrs["data-step-status"]: s.text() for s in root.find_all(**{"data-step-status": True})}
    assert statuses == {"1": "頂上事象：入力済み", "2": "2件・未評価0", "3": "2件・未評価1", "4": "0件・未評価0"}
    # Yes parents of the normal generation, and those left out as inconsistent (判断3).
    assert root.find(**{"data-target-count": "2"}).text() == "1"
    excluded = root.find(**{"data-target-excluded": "2"})
    assert not excluded.is_hidden() and excluded.find(**{"data-target-excluded-count": True}).text() == "1"
    assert root.find(**{"data-target-count": "3"}).text() == "1"
    assert root.find(**{"data-target-excluded": "3"}).is_hidden()
    assert broken not in {int(e.attrs["data-node-id"]) for e in root.find_all(**{"data-role": "group-item"})}


# ----- T-06 -------------------------------------------------------------------
# ⑤'s table of what each export format contains (PR-4, plan section 4 UI-04
# note) is checked against the real exports (services/export_service.py),
# never the other way round: every row and every cell of the table is
# probed in the JSON, CSV and Markdown the export URLs return.

def _t06_analysis(client):
    context = json.dumps({"system_context": "T06構成の印", "incident_context": "T06状況の印",
                          "demo_points": "T06デモ観点の印"}, ensure_ascii=False)
    analysis_id = _create(client, "T06分析タイトルの印", top_event="T06頂上事象の印", context=context)
    first = _raw_node(client, analysis_id, 1, title="T06一次要因の印", judgement="yes", description="T06説明の印",
                      ai=True, warning="T06品質警告の印", memo="T06メモの印", direct="direct")
    with client.engine.begin() as conn:
        conn.execute(models.Node.__table__.update().where(models.Node.id == first).values(
            direct_cause_comment="T06評価コメントの印", evidence="T06根拠の印", prevention_idea="T06再発防止策の印"))
    second = _raw_node(client, analysis_id, 2, first, title="T06二次要因の印", judgement="no")
    orphan = _raw_node(client, analysis_id, 2, 999999, title="T06親不在の印")
    return analysis_id, {"first": first, "second": second, "orphan": orphan}


def _t06_exports(client, analysis_id):
    out = {}
    for fmt in ("json", "csv", "markdown"):
        response = client.get(f"/analyses/{analysis_id}/export/{fmt}")
        assert response.status_code == 200
        out[fmt] = response.content.decode("utf-8-sig")
    return out


DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _t06_probes(exports, ids):
    """For each row of the table: is the item in each format (as written)?"""
    data = json.loads(exports["json"])
    nodes = {n["id"]: n for n in data["nodes"]}
    csv_text, md = exports["csv"], exports["markdown"]
    header = csv_text.splitlines()[0].split(",")
    first = nodes[ids["first"]]
    md_lines = md.splitlines()

    def in_all(text):
        return {"json": text in exports["json"], "csv": text in csv_text, "markdown": text in md}

    return {
        "title": {"json": data["title"] == "T06分析タイトルの印", "csv": "T06分析タイトルの印" in csv_text,
                  "markdown": "T06分析タイトルの印" in md},
        "top_event": {"json": data["top_event"] == "T06頂上事象の印", "csv": "T06頂上事象の印" in csv_text,
                      "markdown": "T06頂上事象の印" in md},
        "context": {fmt: all(mark in text for mark in ("T06構成の印", "T06状況の印", "T06デモ観点の印"))
                    for fmt, text in (("json", exports["json"]), ("csv", csv_text), ("markdown", md))},
        "timestamps": {"json": bool(data["created_at"]) and bool(data["updated_at"]),
                       "csv": bool(DATE.search(csv_text)), "markdown": bool(DATE.search(md))},
        "structure": {
            "json": (first["level"], nodes[ids["second"]]["parent_id"]) == (1, ids["first"]),
            "csv": header[:6] == ["ID", "レベル", "タイトル", "説明", "親ID", "親要因"]
            and f"{ids['second']},二次要因,T06二次要因の印,,{ids['first']},T06一次要因の印" in csv_text,
            "markdown": any(line.startswith("  - 一次要因: T06一次要因の印") for line in md_lines)
            and any(line.startswith("    - 二次要因: T06二次要因の印") for line in md_lines),
        },
        "factor_title": in_all("T06二次要因の印"),
        "description": in_all("T06説明の印"),
        "origin": {"json": first["ai_generated"] is True and nodes[ids["second"]]["ai_generated"] is False,
                   "csv": "AI生成" in csv_text and ",手動," in csv_text,
                   "markdown": "AI生成" in md or "手動" in md},
        "judgement": {"json": (first["user_judgement"], nodes[ids["second"]]["user_judgement"]) == ("yes", "no"),
                      "csv": ",Yes," in csv_text and ",No," in csv_text,
                      "markdown": "T06一次要因の印 [Yes]" in md and "T06二次要因の印 [No]" in md},
        "direct_cause": {"json": first["direct_cause_status"] == "direct" and "T06評価コメントの印" in exports["json"],
                         "csv": ",直接要因,T06評価コメントの印," in csv_text,
                         "markdown": "直接要因評価: 直接要因" in md and "T06評価コメントの印" in md
                         and "直接要因評価: 未評価" not in md},
        "evidence": in_all("T06根拠の印"),
        "prevention": in_all("T06再発防止策の印"),
        "memo": in_all("T06メモの印"),
        "warning": {"json": first["warning_flags"] == "T06品質警告の印",
                    "csv": ",要確認,T06品質警告の印,警告のみ" in csv_text, "markdown": "T06品質警告の印" in md},
        "anomaly": {"json": ids["orphan"] in nodes, "csv": "T06親不在の印" in csv_text,
                    # partial: the factor in place is written, the one whose parent cannot be followed is not
                    "markdown": "partial" if ("T06二次要因の印" in md and "T06親不在の印" not in md) else "T06親不在の印" in md},
    }


def test_T06_the_export_table_of_step_5_matches_the_real_exports(client):
    analysis_id, ids = _t06_analysis(client)
    _, root = _edit_page(client, analysis_id)
    table = root.find(**{"data-export-table": True})
    rows = {row.attrs["data-export-item"]: row for row in table.find_all("tr", **{"data-export-item": True})}
    probes = _t06_probes(_t06_exports(client, analysis_id), ids)
    assert set(rows) == set(probes)  # every row is checked, nothing is left out
    for key, row in rows.items():
        for cell in row.find_all("td"):
            fmt, claimed = cell.attrs["data-format"], cell.attrs["data-included"]
            found = probes[key][fmt]
            expected = {"yes": True, "no": False, "partial": "partial"}[claimed]
            assert found == expected, f"{key} / {fmt}：表は「{cell.text()}」、出力は {found}"
        assert [c.attrs["data-format"] for c in row.find_all("td")] == ["json", "csv", "markdown"]


def test_T06_the_differences_the_screen_must_state(client):
    """The differences the user named for PR-4, stated in ⑤ and true of the exports."""
    analysis_id, ids = _t06_analysis(client)
    _, root = _edit_page(client, analysis_id)
    cells = {(row.attrs["data-export-item"], td.attrs["data-format"]): td.attrs["data-included"]
             for row in root.find(**{"data-export-table": True}).find_all("tr", **{"data-export-item": True})
             for td in row.find_all("td")}
    exports = _t06_exports(client, analysis_id)
    # CSV: no analysis title, top event or reference information.
    for item, mark in (("title", "T06分析タイトルの印"), ("top_event", "T06頂上事象の印"), ("context", "T06構成の印")):
        assert cells[(item, "csv")] == "no" and mark not in exports["csv"]
    # Markdown: no analysis title, description, AI／手動, evidence, memo, quality warning.
    for item, mark in (("title", "T06分析タイトルの印"), ("description", "T06説明の印"), ("evidence", "T06根拠の印"),
                       ("memo", "T06メモの印"), ("warning", "T06品質警告の印")):
        assert cells[(item, "markdown")] == "no" and mark not in exports["markdown"]
    assert cells[("origin", "markdown")] == "no" and "AI生成" not in exports["markdown"]
    assert exports["markdown"].startswith("# FTA分析結果")
    # The three formats keep different items.
    columns = {fmt: {item for (item, f), v in cells.items() if f == fmt and v == "yes"} for fmt in ("json", "csv", "markdown")}
    assert columns["json"] > columns["csv"] and columns["json"] > columns["markdown"]
    assert columns["csv"] - columns["markdown"] and columns["markdown"] - columns["csv"]


def test_step_5_counts_per_level_and_for_inconsistent_factors(client):
    analysis_id = _create(client, "⑤の件数", top_event="頂上")
    a = _raw_node(client, analysis_id, 1, title="一次A", judgement="yes", direct="direct", warning="警告")
    _raw_node(client, analysis_id, 1, title="一次B", judgement="no", direct="likely")
    _raw_node(client, analysis_id, 2, a, title="二次C")
    _raw_node(client, analysis_id, 2, 999999, title="二次（親不在）", judgement="yes", direct="direct")
    _, root = _edit_page(client, analysis_id)
    table = root.find(**{"data-summary-table": True})
    values = {row.attrs["data-summary-row"]: [td.text() for td in row.find_all("td")]
              for row in table.find_all("tr", **{"data-summary-row": True})}
    # 件数, Yes, No, 未評価, 要確認, 直接要因 (直接要因評価「直接要因」 only, not 可能性高)
    assert values == {
        "1": ["2", "1", "1", "0", "1", "1"],
        "2": ["1", "0", "0", "1", "0", "0"],
        "3": ["0", "0", "0", "0", "0", "0"],
        "anomaly": ["1", "1", "0", "0", "0", "1"],
        "all": ["4", "2", "1", "1", "1", "2"],
    }
    assert "hidden" not in table.find("tr", **{"data-summary-row": "anomaly"}).attrs
    # Without inconsistent factors the row and its note are hidden.
    other = _create(client, "⑤の件数（不整合なし）")
    _, root = _edit_page(client, other)
    assert "hidden" in root.find("tr", **{"data-summary-row": "anomaly"}).attrs
    assert "hidden" in root.find(**{"data-summary-anomaly-note": True}).attrs
