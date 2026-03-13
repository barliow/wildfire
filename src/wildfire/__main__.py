"""Entry point: run GUI with optional source file path (e.g. from Send To)."""

from __future__ import annotations

import sys


def main() -> None:
    from wildfire.gui import show_wildfire_dialog

    source = sys.argv[1].strip() if len(sys.argv) > 1 else None
    if source and source.startswith('"') and source.endswith('"'):
        source = source[1:-1]
    show_wildfire_dialog(source)


if __name__ == "__main__":
    main()
