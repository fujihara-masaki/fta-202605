"""The static files each screen loads (docs/static-assets-cache-control-plan.md
2.3, 2.4): its stylesheets and the modules reached from boot.js and its
entry, read from the files' import lines. Shared by the cache tests
(tests/e2e/test_static_cache.py) and W-02's tool
(tests/e2e/cache_manual_check.py), so the list is kept in one place."""

from __future__ import annotations

import os
import pathlib
import re

APP_STATIC = pathlib.Path(__file__).resolve().parents[2] / "app" / "static"

SCREEN_CSS_FILES = {
    "list": ("css/tokens.css", "css/base.css", "css/components.css", "css/list.css"),
    "new": ("css/tokens.css", "css/base.css", "css/components.css", "css/new.css"),
    "edit": ("css/tokens.css", "css/base.css", "css/components.css", "css/edit.css", "style.css"),
}
SCREEN_ENTRY = {"list": "js/pages/list.js", "new": "js/pages/new.js", "edit": "js/pages/edit.js"}
SCREEN_ASSET_COUNTS = {"list": 14, "new": 13, "edit": 34}
ALL_ASSETS = 38
SCREENS = ("list", "new", "edit")
IMPORT = re.compile(r"""(?:from|import)\s*['"]([^'"]+)['"]""")


def module_closure(entry: str) -> set[str]:
    seen, todo = set(), [entry]
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        base = pathlib.PurePosixPath(rel).parent
        for spec in IMPORT.findall((APP_STATIC / rel).read_text(encoding="utf-8")):
            todo.append(os.path.normpath((base / spec).as_posix()).replace(os.sep, "/"))
    return seen


def screen_assets(screen: str) -> list[str]:
    assets = set(SCREEN_CSS_FILES[screen]) | module_closure("js/common/boot.js") | module_closure(SCREEN_ENTRY[screen])
    assert len(assets) == SCREEN_ASSET_COUNTS[screen], (screen, sorted(assets))
    return sorted(assets)


def all_assets() -> list[str]:
    assets = sorted(set().union(*(screen_assets(screen) for screen in SCREENS)))
    files = sorted(p.relative_to(APP_STATIC).as_posix() for p in APP_STATIC.rglob("*") if p.is_file())
    assert assets == files and len(assets) == ALL_ASSETS, sorted(set(assets) ^ set(files))
    return assets
