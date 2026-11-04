"""Accessibility & help modal tests for v1.0.0."""

from __future__ import annotations

import pytest

from yoinktui.app import HIGH_CONTRAST_THEME, YoinkTUIApp
from yoinktui.tui.screens import HelpModal


@pytest.mark.asyncio
async def test_help_modal_push_and_dismiss(app: YoinkTUIApp) -> None:
    async with app.run_test() as pilot:
        # Trigger help modal via action
        app.action_help()
        await pilot.pause(0.05)
        assert isinstance(app.screen, HelpModal)

        # Ensure modal contains help content
        help_screen = app.screen
        title_static = help_screen.query_one(".title")
        assert "Keyboard Shortcuts" in str(title_static.render())

        # Dismiss via Escape
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert not isinstance(app.screen, HelpModal)


@pytest.mark.asyncio
async def test_high_contrast_theme_registered(app: YoinkTUIApp) -> None:
    async with app.run_test() as pilot:
        assert "high-contrast" in app.available_themes
        assert HIGH_CONTRAST_THEME.name == "high-contrast"

        # Theme toggle switches theme
        initial_theme = app.theme
        app.action_toggle_dark()
        await pilot.pause(0.02)
        assert app.theme != initial_theme
