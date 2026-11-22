"""Icons and window identity for The Different Engine's board windows.

On Windows the taskbar otherwise shows python.exe's own logo, unless the
process is given an App User Model ID before the first window is created.
On Linux the same job is done by the window class, which must match
StartupWMClass in the .desktop shortcut.  iconbitmap() with a .ico file is
not supported on X11, so the PNG is always applied with iconphoto().
"""

import os

WINDOW_CLASS = "DifferentEngine"
APP_USER_MODEL_ID = "SixtyFourLanterns.DifferentEngine"

_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PNG = os.path.join(_DIR, "icon.png")
ICON_ICO = os.path.join(_DIR, "icon.ico")
ICON_REVIEW_PNG = os.path.join(_DIR, "icon_review.png")
ICON_REVIEW_ICO = os.path.join(_DIR, "icon_review.ico")

_app_id_set = False


def claim_windows_app_id():
    """Tell Windows this process is The Different Engine, not python.exe.

    Must run before the first window is created.  Does nothing on Linux or a
    Mac, and never raises.
    """
    global _app_id_set
    if _app_id_set or os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        _app_id_set = True
    except Exception:
        pass


def apply_icon(root, review=False):
    """Give a Tk or Toplevel the knight icon.  Never raises.

    The burgundy knight is used for game windows; pass review=True for the
    green knight on the --board review viewer.
    """
    try:
        import tkinter as tk
        png = ICON_REVIEW_PNG if review else ICON_PNG
        ico = ICON_REVIEW_ICO if review else ICON_ICO
        if os.name == "nt" and os.path.exists(ico):
            try:
                root.iconbitmap(default=ico)
            except Exception:
                pass
        if os.path.exists(png):
            image = tk.PhotoImage(file=png)
            root.iconphoto(True, image)
            root._de_icon = image          # keep a reference so it is not discarded
    except Exception:
        pass


def create_root(review=False):
    """Create the main Tk window with the right class (for Linux) and icon."""
    import tkinter as tk
    claim_windows_app_id()
    root = tk.Tk(className=WINDOW_CLASS)
    apply_icon(root, review=review)
    return root
