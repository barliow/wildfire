"""Install Wildfire into Windows Send To menu (no admin required)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# SendTo folder
SENDTO = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "SendTo"
TARGET = SENDTO / "Wildfire.vbs"


def _get_pythonw_path() -> Path:
    """Full path to pythonw.exe (or python.exe so it works even without pythonw)."""
    exe = Path(sys.executable).resolve()
    if exe.name.lower() == "python.exe":
        pythonw = exe.parent / "pythonw.exe"
        if pythonw.is_file():
            return pythonw
    return exe


def install() -> bool:
    if not SENDTO.is_dir():
        print(f"SendTo folder not found: {SENDTO}")
        return False
    pythonw = _get_pythonw_path()
    # VBS that runs Python with full path so it works without PATH
    vbs_content = f'''Option Explicit
Dim sh, args, i
Set sh = CreateObject("WScript.Shell")
args = ""
For i = 0 To WScript.Arguments.Count - 1
  If i > 0 Then args = args & " "
  args = args & """" & Replace(WScript.Arguments(i), """", """""") & """"
Next
sh.Run """{pythonw}"" -m wildfire " & args, 0, False
'''
    TARGET.write_text(vbs_content, encoding="utf-8")
    print(f"Installed: {TARGET}")
    print(f"Using Python: {pythonw}")
    print("Right-click a file -> Send to -> Wildfire")
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
