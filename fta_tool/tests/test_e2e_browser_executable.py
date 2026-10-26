"""--e2e-browser-executable (PR-C review of 748ad40): a Chromium given
explicitly where the pinned Playwright's browser cannot be installed. The
record names it as such, never as Playwright's own browser, and the option
cannot be mixed with --browser-channel."""

from __future__ import annotations

import pytest

from tests.e2e import acceptance


class Config:
    def __init__(self, **options):
        self.options = options

    def getoption(self, name, default=None):
        return self.options.get(name, default)


def test_no_executable_by_default():
    assert acceptance.browser_executable(Config()) is None
    rows = acceptance._browser_rows(Config(), acceptance.RunState())
    assert "| ブラウザの channel（指定） | なし（Playwright 同梱の Chromium） |" in rows


def test_the_option_names_the_executable():
    config = Config(e2e_browser_executable="/opt/x/chrome")
    assert acceptance.browser_executable(config) == "/opt/x/chrome"
    run = acceptance.RunState()
    run.launch = {"product": "指定した実行ファイルの Chromium（--e2e-browser-executable）：Google LLC 153", "executable": "/opt/x/real/chrome"}
    rows = acceptance._browser_rows(config, run)
    assert any("--e2e-browser-executable で指定した実行ファイル（Playwright の固定版が使うブラウザではない）：/opt/x/chrome" in r
               for r in rows)
    assert "| ブラウザの実行ファイル | /opt/x/real/chrome |" in rows


def test_not_with_a_channel():
    with pytest.raises(pytest.UsageError):
        acceptance.browser_executable(Config(e2e_browser_executable="/opt/x/chrome", browser_channel="chrome"))
