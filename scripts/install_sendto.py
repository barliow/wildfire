"""Install Wildfire into Windows Send To menu (no admin required)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# Path to the VBS launcher (next to this script)
SCRIPT_DIR = Path(__file__).resolve().parent
VBS_NAME = "install_sendto.vbs"
# SendTo folder
SENDTO = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "SendTo"
TARGET = SENDTO / "Wildfire.vbs"


def install() -> bool:
    if not SENDTO.is_dir():
        print(f"SendTo folder not found: {SENDTO}")
        return False
    src = SCRIPT_DIR / VBS_NAME
    if not src.is_file():
        print(f"Launcher not found: {src}")
        return False
    shutil.copy2(src, TARGET)
    print(f"Installed: {TARGET}")
    print("Right-click a file → Send to → Wildfire")
    return True


def uninstall() -> bool:
    if TARGET.is_file():
        TARGET.unlink()
        print(f"Removed: {TARGET}")
        return True
    print("Wildfire was not installed in Send To.")
    return False


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("uninstall", "-u", "--uninstall"):
        uninstall()
    else:
        install()
