"""C-07 builds its old components.css by taking out the rule that dims the
judgement buttons (tests/e2e/static_assets.without_disabled_rule). A Linux
checkout has LF line ends, a Windows checkout (core.autocrlf) CRLF: the
Windows Chrome Full on a42966b failed C-07 because the rule was looked for
with LF only. Here the repository's components.css is made LF and CRLF and
the rule must be found exactly once and taken out, the rest kept as it is.
No browser; the repository's file is only read."""

from __future__ import annotations

import pytest

from tests.e2e.static_assets import APP_STATIC, without_disabled_rule

SELECTOR = b".ui-judgement__option:disabled"
LF_RULE = b".ui-judgement__option:disabled {\n  opacity: 0.55;\n  cursor: not-allowed;\n}\n"


def as_lf() -> bytes:
    return (APP_STATIC / "css" / "components.css").read_bytes().replace(b"\r\n", b"\n")


def as_crlf() -> bytes:
    return as_lf().replace(b"\n", b"\r\n")


def test_the_lf_rule_is_not_found_in_a_crlf_file():
    # How C-07 failed on Windows: the LF text is in the LF file once, in the
    # CRLF file not at all.
    assert as_lf().count(LF_RULE) == 1
    assert as_crlf().count(LF_RULE) == 0


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"], ids=["LF", "CRLF"])
def test_the_rule_is_taken_out_with_either_line_end(ending):
    css = as_lf().replace(b"\n", ending)
    rule = LF_RULE.replace(b"\n", ending)
    old = without_disabled_rule(css)
    assert SELECTOR not in old
    assert old == css.replace(rule, b"")  # only the rule, nothing else
    assert len(css) - len(old) == len(rule)
    if ending == b"\r\n":
        assert old.count(b"\n") == old.count(b"\r\n")  # CRLF kept everywhere else
    else:
        assert b"\r" not in old


def test_the_repository_file_as_checked_out():
    # What C-07 itself reads, whichever line ends this checkout has.
    css = (APP_STATIC / "css" / "components.css").read_bytes()
    assert SELECTOR not in without_disabled_rule(css)


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"], ids=["LF", "CRLF"])
def test_no_rule_or_two_rules_fail(ending):
    css = as_lf().replace(b"\n", ending)
    rule = LF_RULE.replace(b"\n", ending)
    with pytest.raises(AssertionError, match="0 times"):
        without_disabled_rule(css.replace(rule, b""))
    with pytest.raises(AssertionError, match="2 times"):
        without_disabled_rule(css + rule)
