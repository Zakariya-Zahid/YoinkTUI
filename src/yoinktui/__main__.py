"""Package entry point: ``python -m yoinktui``."""

from __future__ import annotations

import sys


def main() -> int:
    from yoinktui.app import YoinkTUIApp

    app = YoinkTUIApp()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
