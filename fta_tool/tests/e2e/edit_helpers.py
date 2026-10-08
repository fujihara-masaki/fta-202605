"""Locators and checks shared by the edit-screen E2E tests (PR-3).

Every representation of a factor carries data-node-id and a data-role
(templates/edit/_parts.html): nav / work / group / tree / table buttons that
select it, and nav-item / work-item / group-item / tree-item / table-item
containers.
"""

from __future__ import annotations

import time

from tests.e2e.support import expect

SELECT_ROLES = ("nav", "tree", "table")


def open_edit(page, analysis_id: int, fragment: str = "") -> None:
    if fragment:
        page.goto("about:blank")  # a hash-only change would not load the page again
    page.goto(f"/analyses/{analysis_id}{fragment}")
    # The module is running once it marked the current work step.
    expect(page.locator('.edit-steps [aria-current="step"]')).to_have_count(1)


def step_button(page, number: int):
    return page.locator(f'.edit-steps [data-action="step"][data-step="{number}"]')


def step_panel(page, number: int):
    return page.locator(f'[data-step-panel="{number}"]')


def tab(page, view: str):
    return page.locator(f'[data-view-tab="{view}"]')


def panel(page, view: str):
    return page.locator(f'[data-view-panel="{view}"]')


def select_button(page, role: str, node_id):
    return page.locator(f'[data-action="select"][data-role="{role}"][data-node-id="{node_id}"]')


def item(page, role: str, node_id):
    return page.locator(f'[data-role="{role}-item"][data-node-id="{node_id}"]')


def top_button(page, role: str = "nav"):
    return page.locator(f'[data-action="select"][data-select="top"][data-role="{role}"]')


def inspector(page):
    return page.locator("[data-inspector-body]")


def inspector_title(page):
    return page.locator("[data-inspector-title]")


def judgement_button(scope, node_id, value: str):
    return scope.locator(f'[data-judgement-toggle][data-node-id="{node_id}"] [data-value="{value}"]')


def chip(scope, node_id):
    return scope.locator(f'[data-judgement-chip][data-node-id="{node_id}"]')


def selected_ids(page) -> set[str]:
    """What every select button marked as current points at."""
    return set(page.eval_on_selector_all(
        '[data-action="select"][aria-current="true"]',
        "els => els.map((e) => e.dataset.nodeId || e.dataset.select)",
    ))


def expect_selected(page, node_id, title: str) -> None:
    """The factor is the selection on every representation and in the inspector."""
    for role in SELECT_ROLES:
        expect(select_button(page, role, node_id)).to_have_attribute("aria-current", "true")
    work = select_button(page, "work", node_id)
    if work.count():
        expect(work).to_have_attribute("aria-current", "true")
    expect(inspector_title(page)).to_have_text(title)
    assert selected_ids(page) == {str(node_id)}


def notifications(page):
    return page.locator("#ui-toasts .ui-toast")


def toast(page, text: str, kind: str, *, exact: bool = False):
    """A notification of the shared stack (js/common/notify.js) of this kind
    ('success' | 'info' | 'warning' | 'error') containing this text, or with
    exactly this message; app.js's messages are shown here too (判断4)."""
    base = f'#ui-toasts .ui-toast[data-toast-type="{kind}"]'
    if exact:
        value = text.replace("\\", "\\\\").replace('"', '\\"')
        return page.locator(f'{base}[data-message="{value}"]')
    return page.locator(base).filter(has_text=text)


def wait_until(check, timeout: float = 10.0, interval: float = 0.1) -> None:
    """Poll a server-side condition (e.g. the database) until it holds."""
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within the timeout")
        time.sleep(interval)


def update_requests(page, node_id=None):
    sent = []

    def record(request):
        if request.method != "POST":
            return
        if node_id is None and "/nodes/" in request.url and request.url.endswith("/update"):
            sent.append(request)
        elif node_id is not None and request.url.endswith(f"/nodes/{node_id}/update"):
            sent.append(request)

    page.on("request", record)
    return sent


# ----- PR-4: the header title, ①, leaving the page ----------------------------

LEAVE_DIALOG = "保存していない変更があります"


def title_input(page):
    return page.locator("#analysisTitleInput")


def title_editor(page):
    return page.locator("[data-title-editor]")


def open_title_editor(page):
    page.locator("[data-title-edit]").click()
    expect(title_input(page)).to_be_focused()
    return title_input(page)


def edit_title(page, text: str, key: str = "Enter"):
    """✎, replace the title, then `key` (None: leave the input as it is)."""
    field = open_title_editor(page)
    field.fill(text)
    if key:
        field.press(key)
    return field


def save_status(page, field_id: str):
    return page.locator(f'[data-save-status="{field_id}"]')


def save_button(page, kind: str):
    """kind: 'top-event' (頂上事象を保存) | 'context' (参考情報を保存)."""
    return page.locator(f'[data-save-button="{kind}"]')


def leave_dialog(page):
    return page.get_by_role("dialog", name=LEAVE_DIALOG)


def leave_link(page):
    return page.locator(".edit-header").get_by_role("link", name="一覧へ")


def post_paths(page) -> list[str]:
    """Paths of the POST requests the page sends from now on, in order."""
    sent: list[str] = []

    def record(request):
        if request.method == "POST":
            sent.append("/" + request.url.split("/", 3)[3])

    page.on("request", record)
    return sent
