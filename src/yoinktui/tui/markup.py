"""Small helpers for rendering untrusted text in Textual/Rich markup."""

from __future__ import annotations


def escape_markup(value: str) -> str:
    """Escape every opening bracket so user text renders literally.

    ``rich.markup.escape`` only escapes tags that start with a lowercase
    letter, ``#``, ``/``, or ``@``.  Download titles frequently start with an
    uppercase tag-like word (``[Official Video]``), which Rich would otherwise
    parse as a style and silently remove.
    """

    return value.replace("[", "\\[")
