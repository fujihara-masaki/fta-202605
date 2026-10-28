"""PR-C: the HTTP side of the static files' cache control (H-01 .. H-09 of
docs/static-assets-cache-control-plan.md, section 6.5).

H-01 .. H-03, H-05 .. H-08 ask the app itself (TestClient, a temporary
database). H-04 and H-09 serve a temporary folder with the app's class and
with Starlette's StaticFiles as served before PR-C; H-06 also starts the app
on a local port to send paths no client normalised. The repository's static
files are only read.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import pathlib
import re
import socket
import threading
import time
from email.utils import formatdate

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from app import models
from app.database import get_db
from app.main import app
from app.static_files import RevalidatedStaticFiles, content_etag, etag_matches

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"
STATIC_DIR = APP_DIR / "static"
ASSETS = sorted(p.relative_to(STATIC_DIR).as_posix() for p in STATIC_DIR.rglob("*") if p.is_file())
STRONG_ETAG = re.compile(r'^"[0-9a-f]{32}"$')
FUTURE = "Mon, 01 Jan 2035 00:00:00 GMT"
PAST = "Thu, 01 Jan 2015 00:00:00 GMT"


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
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def sha_etag(data: bytes) -> str:
    return f'"{hashlib.sha256(data).hexdigest()[:32]}"'


def folder_client(directory: pathlib.Path, cls=RevalidatedStaticFiles) -> TestClient:
    return TestClient(Starlette(routes=[Mount("/static", cls(directory=str(directory)), name="static")]))


# ----- H-01 ---------------------------------------------------------------------

def test_H_01_every_static_file_first_fetch(client):
    assert len(ASSETS) == 38, ASSETS
    assert sum(a.endswith(".css") for a in ASSETS) == 7 and sum(a.endswith(".js") for a in ASSETS) == 31
    for rel in ASSETS:
        data = (STATIC_DIR / rel).read_bytes()
        response = client.get(f"/static/{rel}")
        assert response.status_code == 200, rel
        assert response.headers["cache-control"] == "no-cache", rel
        assert STRONG_ETAG.match(response.headers["etag"]), rel
        assert response.headers["etag"] == sha_etag(data) == content_etag(STATIC_DIR / rel), rel
        assert response.headers["last-modified"] == formatdate((STATIC_DIR / rel).stat().st_mtime, usegmt=True)
        expected_type = "text/css; charset=utf-8" if rel.endswith(".css") else "text/javascript; charset=utf-8"
        assert response.headers["content-type"] == expected_type, rel
        assert response.headers["content-length"] == str(len(data))
        assert response.content == data, rel


# ----- H-02 ---------------------------------------------------------------------

def test_H_02_head_has_the_get_headers_and_no_body(client):
    for rel in ASSETS:
        get = client.get(f"/static/{rel}")
        head = client.head(f"/static/{rel}")
        assert head.status_code == 200 and head.content == b"", rel
        for name in ("cache-control", "etag", "last-modified", "content-type", "content-length"):
            assert head.headers[name] == get.headers[name], (rel, name)
        not_modified = client.head(f"/static/{rel}", headers={"If-None-Match": get.headers["etag"]})
        assert not_modified.status_code == 304 and not_modified.content == b"", rel
        assert not_modified.headers["cache-control"] == "no-cache"


# ----- H-03 ---------------------------------------------------------------------

def test_H_03_the_same_version_again_is_304(client):
    rel = "css/components.css"
    first = client.get(f"/static/{rel}")
    etag, modified = first.headers["etag"], first.headers["last-modified"]
    for headers in (
        {"If-None-Match": etag},
        {"If-None-Match": "W/" + etag},
        {"If-None-Match": f'"x", {etag}'},
        {"If-None-Match": "*"},
        {"If-None-Match": etag, "If-Modified-Since": modified},  # as a browser asks
        {"If-None-Match": etag, "If-Modified-Since": PAST},  # If-None-Match alone decides
    ):
        response = client.get(f"/static/{rel}", headers=headers)
        assert response.status_code == 304, headers
        assert response.content == b""
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["etag"] == etag
    # A JavaScript module as well.
    module = client.get("/static/js/pages/edit/factor-source.js")
    again = client.get("/static/js/pages/edit/factor-source.js", headers={"If-None-Match": module.headers["etag"]})
    assert again.status_code == 304 and again.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("field, etag, expected", [
    ('"a"', '"a"', True),
    ('W/"a"', '"a"', True),  # weak comparison
    (' "b" , W/"a" ', '"a"', True),  # a list
    ('"b","a"', '"a"', True),
    ("*", '"a"', True),  # the whole field "*"
    (" * ", '"a"', True),
    ('"b"', '"a"', False),
    ("", '"a"', False),
    ('"a" "b"', '"a"', False),  # malformed: matches nothing
    ("a", '"a"', False),
    ('"prefix,*,suffix"', '"a"', False),  # "," and "*" inside a quoted tag are the tag's
    ('W/"prefix,*,suffix"', '"a"', False),
    ('"prefix,*,suffix"', '"prefix,*,suffix"', True),
    ('"x", *', '"a"', False),  # "*" is only a wildcard alone
])
def test_etag_matches(field, etag, expected):
    assert etag_matches(field, etag) is expected


def test_H_03_a_star_inside_a_quoted_etag_is_not_a_wildcard(client):
    rel = "css/components.css"
    first = client.get(f"/static/{rel}")
    for field in ('"prefix,*,suffix"', 'W/"prefix,*,suffix"'):
        response = client.get(f"/static/{rel}", headers={"If-None-Match": field})
        assert response.status_code == 200, field
        assert response.content == first.content and response.headers["etag"] == first.headers["etag"]
    assert client.get(f"/static/{rel}", headers={"If-None-Match": "*"}).status_code == 304
    listed = client.get(f"/static/{rel}", headers={"If-None-Match": f'"prefix,*,suffix", {first.headers["etag"]}'})
    assert listed.status_code == 304


# ----- H-04 ---------------------------------------------------------------------

CHANGES = {
    # name: (new body, mtime of the new file relative to the old one, or None for now)
    "normal update": (b"BBBBB", None),
    "same size, time kept": (b"BBBB", 0.0),
    "same second": (b"BBBB", 0.5),
    "size changed, time kept": (b"BBBBBB", 0.0),
    "older time": (b"CCCCCCC", -3600.0),
}


def write(path: pathlib.Path, body: bytes, mtime=None) -> None:
    path.write_bytes(body)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


@pytest.mark.parametrize("change", list(CHANGES))
@pytest.mark.parametrize("suffix", [".css", ".js"])
def test_H_04_a_changed_file_is_sent_whatever_its_time_and_size(tmp_path, change, suffix):
    path = tmp_path / f"a{suffix}"
    old_time = float(int(time.time()) - 100) + 0.2
    write(path, b"AAAA", old_time)
    c = folder_client(tmp_path)
    first = c.get(f"/static/a{suffix}")
    body, shift = CHANGES[change]
    write(path, body, None if shift is None else old_time + shift)
    response = c.get(f"/static/a{suffix}", headers={"If-None-Match": first.headers["etag"],
                                                   "If-Modified-Since": first.headers["last-modified"]})
    assert response.status_code == 200, change
    assert response.content == body
    assert response.headers["etag"] == sha_etag(body)


@pytest.mark.parametrize("restore", ["original time", "current time", "same second"])
def test_H_04_rollback_a_b_a(tmp_path, restore):
    """A fetched, B deployed, A back: a client that stored B gets A again,
    and a client that stored A gets 304 (plan 6.5, H-04)."""
    path = tmp_path / "a.css"
    a_time = float(int(time.time()) - 7200) + 0.2
    write(path, b"body A", a_time)
    c = folder_client(tmp_path)
    # 1. A and its ETag.
    a = c.get("/static/a.css")
    assert a.status_code == 200 and a.content == b"body A"
    etag_a, modified_a = a.headers["etag"], a.headers["last-modified"]
    # 2. B; asked with A's ETag: 200, body B, ETag B.
    b_time = a_time + 3600
    write(path, b"body B", b_time)
    b = c.get("/static/a.css", headers={"If-None-Match": etag_a, "If-Modified-Since": modified_a})
    assert (b.status_code, b.content, b.headers["etag"]) == (200, b"body B", sha_etag(b"body B"))
    etag_b, modified_b = b.headers["etag"], b.headers["last-modified"]
    # 3. A back; asked with B's ETag: 200, body A, ETag A again.
    back_time = {"original time": a_time, "current time": None, "same second": b_time + 0.3}[restore]
    write(path, b"body A", back_time)
    back = c.get("/static/a.css", headers={"If-None-Match": etag_b, "If-Modified-Since": modified_b})
    assert (back.status_code, back.content, back.headers["etag"]) == (200, b"body A", etag_a)
    # 4. Asked with A's ETag again: 304.
    again = c.get("/static/a.css", headers={"If-None-Match": etag_a, "If-Modified-Since": back.headers["last-modified"]})
    assert again.status_code == 304 and again.headers["etag"] == etag_a


# ----- H-05 ---------------------------------------------------------------------

def test_H_05_if_modified_since_alone_keeps_starlettes_check(client):
    rel = "css/base.css"
    modified = client.get(f"/static/{rel}").headers["last-modified"]
    for value, status in ((modified, 304), (FUTURE, 304), (PAST, 200)):
        response = client.get(f"/static/{rel}", headers={"If-Modified-Since": value})
        assert response.status_code == status, value
        assert response.headers["cache-control"] == "no-cache"


# ----- H-06 ---------------------------------------------------------------------

class PathRecorder:
    """Records the path each request reached the app with (scope path and
    raw path), so a 404 of the router is not taken for StaticFiles'."""

    def __init__(self, inner):
        self.inner = inner
        self.seen: list[tuple[str, bytes]] = []

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            self.seen.append((scope["path"], scope.get("raw_path") or b""))
        await self.inner(scope, receive, send)


@pytest.fixture()
def raw_server(client):
    """The app on a local port behind PathRecorder: http.client sends a path
    as it is written (TestClient's httpx normalises "/static/../x" first)."""
    import uvicorn

    recorder = PathRecorder(app)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(recorder, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.05)
    yield port, recorder
    server.should_exit = True
    thread.join(timeout=10)


def raw_get(port: int, path: str, method: str = "GET") -> tuple[int, dict, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        connection.close()


OUTSIDE = (APP_DIR / "main.py").read_bytes()


@pytest.mark.parametrize("path", ["/static/../main.py", "/static/%2e%2e/main.py", "/static/..%2fmain.py",
                                  "/static/css/../../main.py"])
def test_H_06_a_path_that_leaves_the_static_folder_is_refused_by_static_files(raw_server, path):
    port, recorder = raw_server
    status, headers, body = raw_get(port, path)
    reached_path, raw = recorder.seen[-1]
    # It reached the /static mount as written (not normalised by the client).
    assert raw.decode("latin-1") == path
    assert reached_path.startswith("/static/") and "/../" in reached_path + "/", reached_path
    relative = reached_path[len("/static/"):]
    assert RevalidatedStaticFiles(directory=str(STATIC_DIR)).lookup_path(relative)[1] is None
    assert status == 404, path
    assert headers["content-type"] == "application/json" and json.loads(body) == {"detail": "Not Found"}
    assert "cache-control" not in headers and "etag" not in headers
    assert OUTSIDE[:200] not in body


@pytest.mark.parametrize("path", ["/static/css/../css/base.css", "/static/css/%2e%2e/css/base.css",
                                  "/static/./css/base.css"])
def test_H_06_a_path_that_stays_inside_is_served(raw_server, path):
    port, recorder = raw_server
    status, headers, body = raw_get(port, path)
    assert recorder.seen[-1][1].decode("latin-1") == path
    assert status == 200 and body == (STATIC_DIR / "css" / "base.css").read_bytes()
    assert headers["cache-control"] == "no-cache" and headers["etag"] == sha_etag(body)


def test_H_06_missing_file_folder_and_other_methods_answer_as_before(client):
    for path in ("/static/css/nope.css", "/static/css/", "/static/css", "/static/"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"detail": "Not Found"}
        assert "cache-control" not in response.headers and "etag" not in response.headers
    for method in ("post", "put", "delete"):
        response = getattr(client, method)("/static/css/components.css")
        assert response.status_code == 405, method
        assert response.json() == {"detail": "Method Not Allowed"}
        assert "cache-control" not in response.headers


# ----- H-07 ---------------------------------------------------------------------

CACHE_HEADERS = ("cache-control", "etag", "last-modified", "expires")


def test_H_07_html_api_exports_and_redirects_are_unchanged(client):
    created = client.post("/analyses", data={"title": "見出し", "top_event": "頂上"}, follow_redirects=False)
    assert created.status_code == 303
    analysis_id = created.headers["location"].rstrip("/").rsplit("/", 1)[1]
    node = client.post(f"/analyses/{analysis_id}/nodes/add-level1", json={"title": "要因", "description": ""})
    node_id = node.json()["node_id"]
    responses = {
        "/": client.get("/"),
        "/analyses/new": client.get("/analyses/new"),
        f"/analyses/{analysis_id}": client.get(f"/analyses/{analysis_id}"),
        f"/nodes/{node_id}": client.get(f"/nodes/{node_id}"),
        "POST /analyses": created,
    }
    for fmt, kind in (("json", "application/json"), ("csv", "text/csv; charset=utf-8-sig"),
                      ("markdown", "text/markdown; charset=utf-8")):
        response = client.get(f"/analyses/{analysis_id}/export/{fmt}")
        assert response.headers["content-type"] == kind
        assert response.headers["content-disposition"].startswith(f"attachment; filename=fta_{analysis_id}.")
        responses[fmt] = response
    for name in ("/", "/analyses/new", f"/analyses/{analysis_id}"):
        assert responses[name].headers["content-type"] == "text/html; charset=utf-8"
    for name, response in responses.items():
        for header in CACHE_HEADERS:
            assert header not in response.headers, (name, header)


# ----- H-08 ---------------------------------------------------------------------

IMPORT = re.compile(r"""(?:^|[;\s])(?:import|export)\b[^'"]*?\bfrom\s*['"]([^'"]+)['"]|(?:^|[;\s])import\s*['"]([^'"]+)['"]""", re.M)
DYNAMIC_IMPORT = re.compile(r"\bimport\s*\(")
STATIC_URL = re.compile(r'(?:href|src)="(/static/[^"]*)"')


def module_imports(rel: str) -> list[str]:
    text = (STATIC_DIR / rel).read_text(encoding="utf-8")
    return [a or b for a, b in IMPORT.findall(text)]


def test_H_08_every_static_url_and_import_stays_in_the_static_folder(client):
    created = client.post("/analyses", data={"title": "範囲", "top_event": "頂上"}, follow_redirects=False)
    edit = created.headers["location"]
    pages = {"/": client.get("/").text, "/analyses/new": client.get("/analyses/new").text, edit: client.get(edit).text}
    entries = set()
    for path, html in pages.items():
        urls = STATIC_URL.findall(html)
        assert urls, path
        for url in urls:
            assert "?" not in url and "#" not in url, url  # no version in a query
            rel = url[len("/static/"):]
            assert (STATIC_DIR / rel).is_file(), url
            entries.add(rel)
        for src in re.findall(r'<script[^>]*\bsrc="([^"]+)"', html):
            assert src.startswith("/static/"), src
    reached, todo = set(), sorted(entries)
    while todo:
        rel = todo.pop()
        if rel in reached:
            continue
        reached.add(rel)
        if rel.endswith(".js"):
            text = (STATIC_DIR / rel).read_text(encoding="utf-8")
            assert not DYNAMIC_IMPORT.search(text), rel
            for spec in module_imports(rel):
                assert spec.startswith(("./", "../")) and "?" not in spec, (rel, spec)
                target = os.path.normpath(os.path.join(os.path.dirname(rel), spec)).replace(os.sep, "/")
                assert (STATIC_DIR / target).is_file(), (rel, spec)
                todo.append(target)
        else:
            text = (STATIC_DIR / rel).read_text(encoding="utf-8")
            assert "@import" not in text and "url(" not in text, rel
    assert sorted(reached) == ASSETS, sorted(set(ASSETS) ^ reached)


# ----- H-09 ---------------------------------------------------------------------

@pytest.mark.parametrize("change", list(CHANGES))
def test_H_09_starlettes_static_files_misses_these_changes(tmp_path, change):
    """The detection check: served as before PR-C (Starlette's StaticFiles),
    the same changes as H-04 answer 304 to a browser's revalidation, except
    the normal update. H-04 sends all of them with the app's class."""
    path = tmp_path / "a.css"
    old_time = float(int(time.time()) - 100) + 0.2
    write(path, b"AAAA", old_time)
    c = folder_client(tmp_path, StaticFiles)
    first = c.get("/static/a.css")
    body, shift = CHANGES[change]
    write(path, body, None if shift is None else old_time + shift)
    response = c.get("/static/a.css", headers={"If-None-Match": first.headers["etag"],
                                              "If-Modified-Since": first.headers["last-modified"]})
    expected = 200 if change == "normal update" else 304
    assert response.status_code == expected, (change, response.status_code)
    revalidated = folder_client(tmp_path).get("/static/a.css", headers={
        "If-None-Match": first.headers["etag"], "If-Modified-Since": first.headers["last-modified"]})
    assert revalidated.status_code == 200 and revalidated.content == body
