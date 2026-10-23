"""Packaging smoke tests (version source and bundled CSS)."""

from __future__ import annotations

from importlib.metadata import version
from importlib.resources import files

from yoinktui import __version__


def test_version_is_single_sourced() -> None:
    assert __version__ == version("yoinktui")
    assert __version__ != "0.0.0+source"


def test_stylesheet_is_packaged() -> None:
    stylesheet = files("yoinktui").joinpath("tui", "app.tcss")
    assert stylesheet.is_file()


def test_required_data_files_are_packaged() -> None:
    package = files("yoinktui")
    assert package.joinpath("assets", "logo-dark.png").is_file()
    assert package.joinpath("assets", "logo-light.png").is_file()
