"""PR-C: after an update, the browser uses the server's current CSS and modules
(docs/static-assets-cache-control-plan.md, section 6: C-00 .. C-07).

Every test runs its own test server (tests/e2e/stub_server.py) that serves
/static from a copy in the test's temporary folder (FTA_E2E_STATIC_DIR) and
writes every request with its cache headers and the SHA-256 of the body it
sent (FTA_E2E_STATIC_LOG). The repository's static files and the user's
database are never touched. The serving policy (static_control.json) is
"app" (RevalidatedStaticFiles), or "baseline" / "nocache-only" for the
checks that the tests see what PR-C prevents (C-05) and for the migration
from the old serving (C-04).

Conditions of a valid cache test (plan 6.2), kept by every scenario here:
* one browser context, one page and one origin from the first old version
  to the last new one; nothing is cleared, no context is made again;
* no page.route / context.route / HAR, no cache switched off. The forced
  reload (CDP Page.reload with ignoreCache) is only the migration step of
  C-04 (forced_reload); C-00 checks this file for it;
* the values are read from the page as it is (getComputedStyle of the
  markers, globalThis.__ftaCacheProbe set by the modules it ran): no fetch,
  no import() of a static file;
* each operation (link, goto, reload) is preceded by its own change to a
  version not fetched yet, made after the page the operation starts from
  has loaded (update_step): an operation passes only when it fetched that
  version itself. Changed files: the old ETag sent, 200, the new body, the
  new marker in use. Unchanged files: 304. The HTML request reached the
  server (C-03).
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import pathlib
import re
import shutil
import time
from typing import Callable, Optional

import pytest

from tests.e2e.edit_helpers import (
    expect_editor_ready,
    factor_field,
    generate_button,
    item,
    judgement_button,
    select_button,
    step_button,
    toast,
)
from tests.e2e.static_assets import ALL_ASSETS, screen_assets
from tests.e2e.support import expect, free_port, start_server

pytestmark = [pytest.mark.e2e]

SINGLE = pytest.mark.parametrize("viewport", [(1280, 800)], indirect=True, ids=["1280x800"])

FTA_TOOL_DIR = pathlib.Path(__file__).resolve().parents[2]
APP_STATIC = FTA_TOOL_DIR / "app" / "static"
TEN_DAYS = 10 * 24 * 3600
CSS_COMPONENTS = "css/components.css"
JS_DEEP = ("js/pages/edit/factor-source.js", "js/common/dom.js", "js/pages/edit/judgement.js")
SCREEN_CSS = {"list": "css/list.css", "new": "css/new.css", "edit": "css/edit.css"}
DISABLED_RULE = """.ui-judgement__option:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
"""

READ_CSS = """(names) => Object.fromEntries(names.map((name) => [name,
  getComputedStyle(document.documentElement).getPropertyValue('--fta-cache-probe-' + name)
    .trim().replace(/^["']|["']$/g, '')]))"""
READ_JS = "() => Object.assign({}, globalThis.__ftaCacheProbe || {})"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_etag(data: bytes) -> str:
    return f'"{sha256(data)[:32]}"'


def css_marker_name(rel: str) -> str:
    return pathlib.PurePosixPath(rel).stem


def with_marker(rel: str, original: bytes, version: str) -> bytes:
    if rel.endswith(".css"):
        line = f'\n:root{{--fta-cache-probe-{css_marker_name(rel)}:"{version}"}}\n'
    else:
        line = (f'\nglobalThis.__ftaCacheProbe = Object.assign(globalThis.__ftaCacheProbe ?? {{}}, '
                f'{{"{rel}": "{version}"}});\n')
    return original + line.encode("utf-8")


class CacheServer:
    """The test server of one scenario, its copy of /static and its log."""

    def __init__(self, server, static_dir: pathlib.Path, log_path: pathlib.Path):
        self.server = server
        self.static_dir = static_dir
        self.log_path = log_path
        self.originals = {rel: (APP_STATIC / rel).read_bytes() for rel in self.all_assets()}
        self.versions: dict[str, str] = {}
        # Every file looks as if it had been checked out ten days ago, so the
        # old serving lets a browser reuse it without asking (plan 6.3).
        old = time.time() - TEN_DAYS
        for rel in self.originals:
            os.utime(self.static_dir / rel, (old, old))

    def __getattr__(self, name):  # url, reset, violations, create_analysis, ...
        return getattr(self.server, name)

    @staticmethod
    def all_assets() -> list[str]:
        return sorted(p.relative_to(APP_STATIC).as_posix() for p in APP_STATIC.rglob("*") if p.is_file())

    # ----- the copy ---------------------------------------------------------
    def set_policy(self, policy: str) -> None:
        (self.server.workdir / "static_control.json").write_text(json.dumps({"policy": policy}), encoding="utf-8")

    def write(self, rel: str, version: str, *, mtime: Optional[float] = None,
              body: Optional[bytes] = None) -> bytes:
        """Write `rel` as `version` (the original with its marker, or `body`)."""
        data = body if body is not None else with_marker(rel, self.originals[rel], version)
        path = self.static_dir / rel
        path.write_bytes(data)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        self.versions[rel] = version
        return data

    def mtime(self, rel: str) -> float:
        return (self.static_dir / rel).stat().st_mtime

    def current(self, rel: str) -> bytes:
        return (self.static_dir / rel).read_bytes()

    # ----- the log ------------------------------------------------------------
    def entries(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def mark(self) -> int:
        return len(self.entries())

    def browser_entries(self, since: int) -> list[dict]:
        return [e for e in self.entries()[since:] if e.get("client") == "browser"]


@pytest.fixture
def e2e_server(tmp_path_factory):
    """This module's own server: a copy of /static, the request log, the
    policy switch. Replaces the session's server for these tests only."""
    workdir = tmp_path_factory.mktemp("static-cache")
    static_dir = workdir / "static"
    shutil.copytree(APP_STATIC, static_dir)
    log_path = workdir / "static-requests.jsonl"
    server = start_server(workdir, free_port(), {
        "FTA_E2E_STATIC_DIR": str(static_dir),
        "FTA_E2E_STATIC_LOG": str(log_path),
    })
    try:
        yield CacheServer(server, static_dir, log_path)
    finally:
        server.close()


# ----- screens and operations --------------------------------------------------

def screen_path(screen: str, analysis_id: int) -> str:
    return {"list": "/", "new": "/analyses/new", "edit": f"/analyses/{analysis_id}"}[screen]


# The screen a link or a goto starts from, and the link that leads on.
ORIGIN = {"edit": "list", "list": "new", "new": "list"}


def link_to(page, screen: str, analysis_id: int):
    if screen == "edit":
        return page.locator(f'a[data-edit-link][href="/analyses/{analysis_id}"]')
    return page.locator(f'.app-header__nav a[href="{screen_path(screen, analysis_id)}"]')


def url_of(cache, screen: str, analysis_id: int):
    # The edit screen writes its state into the hash (replaceState).
    return re.compile(re.escape(cache.url + screen_path(screen, analysis_id)) + r"(#.*)?$")


def on_screen(page, cache, screen: str, analysis_id: int) -> bool:
    return bool(url_of(cache, screen, analysis_id).match(page.url))


def wait_screen(page, screen: str) -> None:
    if screen == "edit":
        expect(page.locator('.edit-steps [aria-current="step"]')).to_have_count(1)
    page.wait_for_load_state("networkidle")


def forced_reload(page) -> None:
    """The migration step of plan M-3, as Ctrl+F5 (C-04 only)."""
    session = page.context.new_cdp_session(page)
    try:
        with page.expect_navigation():
            session.send("Page.reload", {"ignoreCache": True})
    finally:
        session.detach()


def go(page, cache: CacheServer, operation: str, screen: str, analysis_id: int) -> None:
    if operation == "link":
        link_to(page, screen, analysis_id).first.click()
    elif operation == "goto":
        page.goto(screen_path(screen, analysis_id))
    elif operation == "reload":
        page.reload()
    elif operation == "forced":
        forced_reload(page)
    else:  # pragma: no cover - a mistake in a test
        raise ValueError(operation)
    expect(page).to_have_url(url_of(cache, screen, analysis_id))
    wait_screen(page, screen)


def be_on(page, cache: CacheServer, screen: str, analysis_id: int) -> None:
    """Make `screen` the current page (before any change of a version)."""
    if not on_screen(page, cache, screen, analysis_id):
        page.goto(screen_path(screen, analysis_id))
    wait_screen(page, screen)


class Observation:
    """What one operation did: the server's records and the page's values."""

    def __init__(self, cache: CacheServer, page, since: int, path: str, assets: list[str]):
        self.path = path
        self.assets = assets
        self.entries = cache.browser_entries(since)
        self.html = [e for e in self.entries if e["path"] == path and e["method"] == "GET"]
        self.static = {}
        for entry in self.entries:
            if entry["path"].startswith("/static/") and entry["method"] == "GET":
                self.static.setdefault(entry["path"][len("/static/"):], []).append(entry)
        self.css = page.evaluate(READ_CSS, sorted({css_marker_name(r) for r in cache.versions if r.endswith(".css")}))
        self.js = page.evaluate(READ_JS)

    def one(self, rel: str) -> Optional[dict]:
        found = self.static.get(rel) or []
        return found[-1] if found else None

    def describe(self, rel: str) -> str:
        entry = self.one(rel)
        if entry is None:
            return f"{rel}: 要求なし"
        return (f"{rel}: {entry['status']} INM={entry['request'].get('if-none-match')} "
                f"ETag={entry['response'].get('etag')} CC={entry['response'].get('cache-control')}")

    def value(self, rel: str) -> Optional[str]:
        return self.css.get(css_marker_name(rel)) if rel.endswith(".css") else self.js.get(rel)


def observe(page, cache: CacheServer, since: int, path: str, assets: list[str],
            expect_requests: bool = True, timeout: float = 10.0) -> Observation:
    """The log is written when a response has ended: wait until the HTML and,
    when requests are expected, every file of the screen are there."""
    deadline = time.monotonic() + timeout
    while True:
        obs = Observation(cache, page, since, path, assets)
        complete = bool(obs.html) and (not expect_requests or all(obs.one(r) for r in assets))
        if complete or time.monotonic() > deadline:
            return obs
        time.sleep(0.1)


def first_load(page, cache: CacheServer, screen: str, analysis_id: int) -> tuple[list[str], dict]:
    """U-0, first half: the screen's files, all 200 (nothing stored yet), and
    their ETags. The files requested are exactly the screen's (plan 2.4)."""
    assets = screen_assets(screen)
    since = cache.mark()
    page.goto(screen_path(screen, analysis_id))
    wait_screen(page, screen)
    path = screen_path(screen, analysis_id)
    obs = observe(page, cache, since, path, assets)
    assert obs.html and obs.html[-1]["status"] == 200, f"C-03: HTML の要求が届いていない（初回 {path}）"
    assert sorted(obs.static) == assets, (screen, sorted(set(obs.static) ^ set(assets)))
    for rel in assets:
        entry = obs.one(rel)
        assert entry["status"] == 200, obs.describe(rel)
        assert entry["body_sha256"] == sha256(cache.current(rel)), rel
    return assets, {rel: obs.one(rel)["response"].get("etag") for rel in assets}


def revisit(page, cache: CacheServer, screen: str, analysis_id: int, assets: list[str],
            etags: dict, *, stored_without_asking: bool = False) -> Observation:
    """U-0, second half: away and back by links; the copies are stored and
    used (304 with the stored ETag, or no request at all for the old serving)."""
    origin = ORIGIN[screen]
    go(page, cache, "link", origin, analysis_id)
    since = cache.mark()
    go(page, cache, "link", screen, analysis_id)
    path = screen_path(screen, analysis_id)
    obs = observe(page, cache, since, path, assets, expect_requests=not stored_without_asking)
    assert obs.html and obs.html[-1]["status"] == 200, f"C-03: HTML の要求が届いていない（再訪 {path}）"
    for rel in assets:
        if stored_without_asking:
            assert obs.one(rel) is None, obs.describe(rel)
        else:
            entry = obs.one(rel)
            assert entry is not None and entry["status"] == 304, obs.describe(rel)
            assert entry["request"].get("if-none-match") == etags[rel], obs.describe(rel)
    return obs


def update_step(page, cache: CacheServer, *, screen: str, analysis_id: int, operation: str,
                changes: dict[str, str], assets: list[str],
                mtimes: Optional[Callable[[str], float]] = None,
                bodies: Optional[dict[str, bytes]] = None,
                expect_requests: bool = True) -> tuple[Observation, dict[str, bytes]]:
    """One update step (plan 6.5): (1) go to the page the operation starts
    from and let it load, (2) with no request open, change only `changes` to
    versions not fetched yet, (3) do the one operation, (4) observe."""
    start = screen if operation in ("reload", "forced") else ORIGIN[screen]
    be_on(page, cache, start, analysis_id)
    written = {}
    for rel, version in changes.items():
        body = (bodies or {}).get(rel)
        written[rel] = cache.write(rel, version, mtime=mtimes(rel) if mtimes else None, body=body)
    since = cache.mark()
    go(page, cache, operation, screen, analysis_id)
    obs = observe(page, cache, since, screen_path(screen, analysis_id), assets, expect_requests=expect_requests)
    return obs, written


def assert_updated(obs: Observation, step: str, written: dict[str, bytes], etags: dict,
                   assets: list[str]) -> dict:
    """The judgement of an update step; returns the ETags now stored."""
    assert obs.html and obs.html[-1]["status"] == 200, f"C-03: HTML の要求が届いていない（{step} {obs.path}）"
    new_etags = dict(etags)
    for rel in assets:
        entry = obs.one(rel)
        assert entry is not None, f"{step}: {rel} の要求がない"
        if rel in written:
            assert entry["request"].get("if-none-match") == etags[rel], f"{step}: 旧版の ETag を送っていない {obs.describe(rel)}"
            assert entry["status"] == 200, f"{step}: {obs.describe(rel)}"
            assert entry["response"].get("etag") == content_etag(written[rel]), f"{step}: {obs.describe(rel)}"
            assert entry["body_sha256"] == sha256(written[rel]), f"{step}: {rel} の本文が新版でない"
            assert entry["response"].get("cache-control") == "no-cache", f"{step}: {obs.describe(rel)}"
            new_etags[rel] = entry["response"]["etag"]
        else:
            assert entry["status"] == 304, f"{step}: 変更していない {obs.describe(rel)}"
            assert entry["request"].get("if-none-match") == etags[rel], f"{step}: {obs.describe(rel)}"
    return new_etags


def assert_values(obs: Observation, step: str, expected: dict[str, str]) -> None:
    for rel, version in expected.items():
        assert obs.value(rel) == version, f"{step}: {rel} の使われた版 {obs.value(rel)!r}（期待 {version!r}）"


def make_analysis(cache: CacheServer) -> tuple[int, int, int]:
    analysis_id = cache.create_analysis("キャッシュの確認", top_event="頂上", system_context="構成")
    a = cache.add_level1(analysis_id, "親A")
    b = cache.add_level1(analysis_id, "要因B")
    cache.update_node(a, user_judgement="yes", memo="Aのメモ")
    cache.update_node(b, description="Bの説明")
    return analysis_id, a, b


OPERATIONS = (("U-1", "link"), ("U-2", "goto"), ("U-3", "reload"))


def run_update_steps(page, cache: CacheServer, *, screen: str, analysis_id: int, targets: tuple[str, ...],
                     controls: tuple[str, ...], assets: list[str], etags: dict, first_version: int,
                     mtimes: Optional[Callable[[str, int], float]] = None,
                     check: Optional[Callable[[str], None]] = None) -> dict:
    """U-1 (link), U-2 (goto), U-3 (reload), each with its own new version."""
    number = first_version
    for step, operation in OPERATIONS:
        number += 1
        version = f"v{number}"
        changes = {rel: version for rel in targets}
        obs, written = update_step(page, cache, screen=screen, analysis_id=analysis_id, operation=operation,
                                   changes=changes, assets=assets,
                                   mtimes=(lambda rel, n=number: mtimes(rel, n)) if mtimes else None)
        label = f"{step} {operation} {version}"
        etags = assert_updated(obs, label, written, etags, assets)
        assert_values(obs, label, {**{rel: version for rel in targets},
                                   **{rel: cache.versions[rel] for rel in controls}})
        if check:
            check(label)
    return etags


def prepare(page, cache: CacheServer, screen: str, analysis_id: int, files: tuple[str, ...],
            *, policy: str = "app") -> tuple[list[str], dict]:
    """U-0: v1 of the marked files, the first load, the revisit."""
    cache.set_policy(policy)
    old = time.time() - TEN_DAYS
    for rel in files:
        cache.write(rel, "v1", mtime=old)
    assets, etags = first_load(page, cache, screen, analysis_id)
    assert set(files) <= set(assets), (files, assets)
    obs = revisit(page, cache, screen, analysis_id, assets, etags, stored_without_asking=(policy == "baseline"))
    assert_values(obs, "U-0", {rel: "v1" for rel in files})
    return assets, etags


# ----- C-00 -----------------------------------------------------------------------

# Calls on the page or the context that would change what is tested.
FORBIDDEN_CALLS = {"route", "unroute", "route_from_har", "clear_cookies", "new_context", "new_page",
                   "set_extra_http_headers", "add_init_script", "set_offline"}
# Text in code (not in documentation): switching the cache off, a forced
# reload outside forced_reload, a fetch or an import of a file to read a value.
FORBIDDEN_TEXT = ("setCacheDisabled", "ignoreCache", "import(", "fetch(", "Network.", "bypassCache")
TEXT_ALLOWED_IN = {"ignoreCache": "forced_reload"}
ALLOWED_HELPERS = {"expect_editor_ready", "factor_field", "generate_button", "item", "judgement_button",
                   "select_button", "step_button", "toast", "expect", "free_port", "start_server",
                   "ALL_ASSETS", "screen_assets"}


def _docstrings(tree: ast.Module) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


@pytest.mark.acceptance("C-00")
def test_C_00_the_cache_tests_keep_their_conditions():
    """This file routes, records or replays no request, switches no cache
    off, makes no second context, clears nothing and reads no value by
    fetching or importing a static file; the forced reload is only
    forced_reload(), used by C-04's migration."""
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    owner = {}
    for node in tree.body:
        for child in ast.walk(node):
            owner[id(child)] = getattr(node, "name", None) or getattr(getattr(node, "targets", [None])[0], "id", None)
    skip = _docstrings(tree)
    problems = []
    for node in ast.walk(tree):
        where = owner.get(id(node))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_CALLS:
            problems.append(f"{node.lineno}: {node.func.attr}() in {where}")
        if (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
                and where not in ("FORBIDDEN_TEXT", "TEXT_ALLOWED_IN")):
            for text in FORBIDDEN_TEXT:
                if text in node.value and TEXT_ALLOWED_IN.get(text) != where:
                    problems.append(f"{node.lineno}: {text!r} in {where}")
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("tests."):
            extra = {alias.name for alias in node.names} - ALLOWED_HELPERS
            if extra:  # e.g. edit_helpers.hold (page.route) or phase (import())
                problems.append(f"{node.lineno}: imports {sorted(extra)}")
    assert not problems, problems
    uses = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "forced_reload"]
    assert {owner.get(id(n)) for n in uses} <= {"go"}, "forced_reload is used only through go(..., 'forced')"
    forced = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == "forced"]
    users = {owner.get(id(n)) for n in forced} - {inspect.currentframe().f_code.co_name}
    assert users <= {"go", "update_step", "test_C_04_from_the_old_serving_after_ctrl_f5_on_three_screens"}, users


# ----- C-01 / C-03 ---------------------------------------------------------------

@SINGLE
@pytest.mark.parametrize("screen", ["edit", "list", "new"])
@pytest.mark.acceptance("C-01", "C-03")
def test_C_01_C_03_only_the_css_changes_and_each_operation_fetches_its_own_version(page, e2e_server, screen):
    cache = e2e_server
    analysis_id, _, _ = make_analysis(cache)
    control = SCREEN_CSS[screen]
    assets, etags = prepare(page, cache, screen, analysis_id, (CSS_COMPONENTS, control))
    run_update_steps(page, cache, screen=screen, analysis_id=analysis_id, targets=(CSS_COMPONENTS,),
                     controls=(control,), assets=assets, etags=etags, first_version=1)


# ----- C-02 -------------------------------------------------------------------------

@SINGLE
@pytest.mark.acceptance("C-02", "C-03")
def test_C_02_only_modules_below_the_entry_change_and_run(page, e2e_server):
    cache = e2e_server
    analysis_id, a, b = make_analysis(cache)
    assets, etags = prepare(page, cache, "edit", analysis_id, JS_DEEP + (CSS_COMPONENTS,))
    values = iter(("no", "yes", "no"))

    def works(label: str) -> None:
        # judgement.js: a judgement is saved; factor-source.js: the details show.
        value = next(values)
        judgement_button(item(page, "work", a), a, value).click()
        expect(toast(page, "評価を更新しました", "success")).to_be_visible()
        select_button(page, "nav", b).click()
        expect_editor_ready(page, b)
        expect(factor_field(page, "description")).to_have_value("Bの説明")
        page.wait_for_load_state("networkidle")

    run_update_steps(page, cache, screen="edit", analysis_id=analysis_id, targets=JS_DEEP,
                     controls=(CSS_COMPONENTS,), assets=assets, etags=etags, first_version=1, check=works)
    # The modules ran, so the browser took them as JavaScript; the 200s say so.
    for entry in cache.browser_entries(0):
        if entry["path"].endswith(".js") and entry["status"] == 200:
            assert entry["response"]["content-type"].startswith("text/javascript"), entry


# ----- C-04 ---------------------------------------------------------------------------

@SINGLE
@pytest.mark.acceptance("C-04", "C-03")
def test_C_04_from_the_old_serving_after_ctrl_f5_on_three_screens(page, e2e_server):
    cache = e2e_server
    analysis_id, _, _ = make_analysis(cache)
    targets = (CSS_COMPONENTS, "js/pages/edit/factor-source.js")
    screens = {screen: screen_assets(screen) for screen in ("list", "new", "edit")}
    # 1. The old serving (as before PR-C): every file once 200, then stored
    #    and used without asking.
    cache.set_policy("baseline")
    old = time.time() - TEN_DAYS
    for rel in targets:
        cache.write(rel, "v1", mtime=old)
    stored = {}
    for screen in ("list", "new", "edit"):
        since = cache.mark()
        page.goto(screen_path(screen, analysis_id))
        wait_screen(page, screen)
        obs = observe(page, cache, since, screen_path(screen, analysis_id), [], expect_requests=False)
        for rel, entries in obs.static.items():
            assert entries[-1]["status"] == 200 and "cache-control" not in entries[-1]["response"], obs.describe(rel)
            stored[rel] = entries[-1]["response"]["etag"]
    assert len(stored) == ALL_ASSETS, sorted(set(cache.all_assets()) - set(stored))
    for screen in ("list", "new", "edit"):
        revisit(page, cache, screen, analysis_id, screens[screen], stored, stored_without_asking=True)
    # 2. PR-C deployed, the two files changed.
    cache.set_policy("app")
    for rel in targets:
        cache.write(rel, "v2")
    # 3. Observed only (N-6: normal operations are not relied on to migrate).
    observed = []
    be_on(page, cache, "list", analysis_id)
    for operation in ("link", "reload"):
        since = cache.mark()
        go(page, cache, operation, "edit", analysis_id)
        obs = observe(page, cache, since, screen_path("edit", analysis_id), [], expect_requests=False, timeout=3)
        observed.append({"operation": operation, "css": obs.value(CSS_COMPONENTS),
                         "js": obs.value(targets[1]), "static_requests": len(obs.static)})
    (cache.server.workdir / "c04-observed-before-migration.json").write_text(
        json.dumps(observed, ensure_ascii=False, indent=1), encoding="utf-8")
    # 4. The migration (M-3): one forced reload on each screen. Every file of
    #    the screen comes as 200 with no-cache; together the 38 files.
    fetched = {}
    for screen in ("list", "new", "edit"):
        be_on(page, cache, screen, analysis_id)
        since = cache.mark()
        go(page, cache, "forced", screen, analysis_id)
        obs = observe(page, cache, since, screen_path(screen, analysis_id), screens[screen])
        assert obs.html, f"C-03: HTML の要求が届いていない（強制の再読み込み {screen}）"
        for rel in screens[screen]:
            entry = obs.one(rel)
            assert entry is not None and entry["status"] == 200, obs.describe(rel)
            assert entry["response"].get("cache-control") == "no-cache", obs.describe(rel)
            assert "if-none-match" not in entry["request"], obs.describe(rel)
            fetched[rel] = entry["response"]["etag"]
    assert len(fetched) == ALL_ASSETS, sorted(set(cache.all_assets()) - set(fetched))
    # 5. Migrated: a normal visit asks for every file of each screen (304).
    for screen in ("list", "new", "edit"):
        revisit(page, cache, screen, analysis_id, screens[screen], fetched)
    # 6. After the migration, each operation with its own new version (judged).
    run_update_steps(page, cache, screen="edit", analysis_id=analysis_id, targets=targets, controls=(),
                     assets=screens["edit"], etags={rel: fetched[rel] for rel in screens["edit"]},
                     first_version=2)


# ----- C-05 ---------------------------------------------------------------------------

@SINGLE
@pytest.mark.parametrize("policy", ["baseline", "nocache-only"])
@pytest.mark.acceptance("C-05")
def test_C_05_the_same_steps_see_old_files_without_the_change(page, e2e_server, policy):
    """The detection check: with the old serving, or plan option A alone and
    updates within the same second, the update steps see the old version."""
    cache = e2e_server
    analysis_id, _, _ = make_analysis(cache)
    rel = CSS_COMPONENTS
    base = float(int(time.time() - TEN_DAYS)) + 0.1
    cache.set_policy(policy)
    cache.write(rel, "v1", mtime=base)
    assets, etags = first_load(page, cache, "edit", analysis_id)
    revisit(page, cache, "edit", analysis_id, assets, etags, stored_without_asking=(policy == "baseline"))
    for number, (step, operation) in enumerate(OPERATIONS, start=2):
        obs, _ = update_step(page, cache, screen="edit", analysis_id=analysis_id, operation=operation,
                             changes={rel: f"v{number}"}, assets=assets,
                             mtimes=lambda _rel, n=number: base + 0.1 * (n - 1),
                             expect_requests=(policy != "baseline"))
        label = f"{policy} {step} {operation}"
        assert obs.html, f"C-03: HTML の要求が届いていない（{label}）"
        entry = obs.one(rel)
        if policy == "baseline":
            assert entry is None, f"{label}: {obs.describe(rel)}"
        else:
            assert entry is not None and entry["status"] == 304, f"{label}: {obs.describe(rel)}"
        assert obs.value(rel) == "v1", f"{label}: 古い版を検出できなかった（{obs.value(rel)!r}）"


# ----- C-06 ---------------------------------------------------------------------------

@SINGLE
@pytest.mark.parametrize("form", ["same-second", "older-time"])
@pytest.mark.acceptance("C-06")
def test_C_06_same_second_and_older_time_changes_are_fetched(page, e2e_server, form):
    cache = e2e_server
    analysis_id, _, _ = make_analysis(cache)
    rel = CSS_COMPONENTS
    base = float(int(time.time() - TEN_DAYS)) + 0.1
    cache.set_policy("app")
    cache.write(rel, "v1", mtime=base)
    assets, etags = first_load(page, cache, "edit", analysis_id)
    revisit(page, cache, "edit", analysis_id, assets, etags)

    def mtime(_rel: str, number: int) -> float:
        if form == "same-second":  # the browser holds v(n-1)'s Last-Modified: the same second
            return base + 0.1 * (number - 1)
        return base - 3600 * (number - 1)  # each version an hour older than the one before

    run_update_steps(page, cache, screen="edit", analysis_id=analysis_id, targets=(rel,), controls=(),
                     assets=assets, etags=etags, first_version=1, mtimes=mtime)
    for entry in cache.browser_entries(0):
        if entry["path"] == "/static/" + rel and entry["status"] == 200 and "if-modified-since" in entry["request"]:
            assert "if-none-match" in entry["request"], entry  # the browser sent both


# ----- C-07 ---------------------------------------------------------------------------

@SINGLE
@pytest.mark.acceptance("C-07")
def test_C_07_the_judgement_buttons_look_disabled_after_a_css_update(page, e2e_server):
    """CSS only: the old components.css lacks the rule that dims the judgement
    buttons during a generation, the new one is the current file. One update,
    one operation (a link); the operations one by one are C-01. Not a
    reproduction of 2026-10-22."""
    cache = e2e_server
    analysis_id, a, b = make_analysis(cache)
    rel = CSS_COMPONENTS
    original = cache.originals[rel]
    assert original.count(DISABLED_RULE.encode()) == 1
    cache.set_policy("app")
    cache.write(rel, "old", mtime=time.time() - TEN_DAYS, body=original.replace(DISABLED_RULE.encode(), b""))
    assets, etags = first_load(page, cache, "edit", analysis_id)
    revisit(page, cache, "edit", analysis_id, assets, etags)
    obs, written = update_step(page, cache, screen="edit", analysis_id=analysis_id, operation="link",
                               changes={rel: "new"}, assets=assets, bodies={rel: original})
    assert_updated(obs, "C-07 link", written, etags, assets)

    cache.set_stub_mode("delay", 5)
    step_button(page, 3).click()
    generate_button(page, 2).click()
    edit_page = page.locator("[data-edit-page]")
    expect(edit_page).to_have_attribute("data-generation-phase", "running")
    buttons = page.locator(".ui-judgement__option:disabled:visible")
    expect(buttons.first).to_be_visible()
    count = buttons.count()
    for index in range(count):
        expect(buttons.nth(index)).to_have_css("opacity", "0.55")
        expect(buttons.nth(index)).to_have_css("cursor", "not-allowed")
    # A click on a disabled button changes nothing and sends nothing.
    first = buttons.first
    pressed = first.get_attribute("aria-pressed")
    since = cache.mark()
    first.click(force=True)
    page.wait_for_timeout(300)
    assert first.get_attribute("aria-pressed") == pressed
    assert not [e for e in cache.browser_entries(since) if e["method"] == "POST"], cache.browser_entries(since)
    expect(edit_page).to_have_attribute("data-generation-phase", "idle", timeout=20000)
    shown = page.locator(".ui-judgement__option:visible")
    for index in range(min(count, shown.count())):
        expect(shown.nth(index)).to_have_css("opacity", "1")
        expect(shown.nth(index)).to_have_css("cursor", "pointer")
    step_button(page, 2).click()
    judgement_button(item(page, "work", a), a, "no").click()
    expect(toast(page, "評価を更新しました", "success")).to_be_visible()
