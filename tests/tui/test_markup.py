"""Markup escaping for titles, URLs, and other user-controlled text."""

from __future__ import annotations

from textual.content import Content

from yoinktui.tui.markup import escape_markup


def test_escape_markup_renders_all_brackets_literally() -> None:
    samples = [
        "[Official Video] Demo",
        "[red]not a style[/red]",
        "A [bracket] in a title",
        r"a\[b",
        "100% [free]",
    ]
    for raw in samples:
        assert Content.from_markup(escape_markup(raw)).plain == raw
