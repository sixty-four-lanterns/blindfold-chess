"""Desktop shortcut created by the Linux starter (and documented for Windows)."""

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "start-linux.sh"
WINDOWS = ROOT / "Start-Windows.bat"


def test_linux_desktop_shortcut_created_once(tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["DE_DESKTOP_DIR"] = str(desktop)
    env["DE_CREATE_SHORTCUT_ONLY"] = "1"
    r = subprocess.run(["bash", str(SCRIPT)], cwd=str(ROOT), env=env,
                       text=True, capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr
    dest = desktop / "The Different Engine.desktop"
    assert dest.is_file()
    text = dest.read_text()
    assert "Type=Application" in text
    assert "Terminal=true" in text
    assert "Name=The Different Engine" in text
    assert f'Exec=bash "{ROOT}/start-linux.sh"' in text
    assert f"Path={ROOT}" in text
    assert dest.stat().st_mode & stat.S_IXUSR
    assert "Icon=" in text and text.split("Icon=")[1].splitlines()[0].endswith("/different_engine/icon.png")
    assert "StartupWMClass=DifferentEngine" in text
    assert "I've put a shortcut called The Different Engine on your Desktop." in r.stdout

    # A second run must not overwrite or reprint the message.
    dest.write_text(text + "\n# keep\n")
    r2 = subprocess.run(["bash", str(SCRIPT)], cwd=str(ROOT), env=env,
                        text=True, capture_output=True)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert dest.read_text().endswith("# keep\n")
    assert "I've put a shortcut" not in r2.stdout


def test_linux_shortcut_skipped_without_desktop(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["DE_DESKTOP_DIR"] = str(tmp_path / "no-such-desktop")
    env["DE_CREATE_SHORTCUT_ONLY"] = "1"
    r = subprocess.run(["bash", str(SCRIPT)], cwd=str(ROOT), env=env,
                       text=True, capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert list(tmp_path.glob("**/*.desktop")) == []


def test_windows_starter_creates_shortcut_with_powershell():
    text = WINDOWS.read_text()
    assert "WScript.Shell" in text
    assert "CreateShortcut" in text
    assert "The Different Engine.lnk" in text
    assert r"%~f0" in text
    assert "I've put a shortcut called The Different Engine on your Desktop." in text


def test_icon_files_present_and_linked():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ico = os.path.join(root, "different_engine", "icon.ico")
    png = os.path.join(root, "different_engine", "icon.png")
    with open(ico, "rb") as f:
        assert f.read(4) == b"\x00\x00\x01\x00"          # Windows icon header
    with open(png, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
    with open(os.path.join(root, "Start-Windows.bat"), encoding="utf-8") as f:
        assert "IconLocation" in f.read()
    with open(os.path.join(root, "start-linux.sh"), encoding="utf-8") as f:
        starter = f.read()
        assert "Icon=$app/different_engine/icon.png" in starter
        assert "StartupWMClass=DifferentEngine" in starter


def test_review_games_launcher_opens_board_only():
    review = ROOT / "Review-Games-Windows.bat"
    assert review.is_file()
    assert "--board" in review.read_text()
    text = WINDOWS.read_text()
    assert "Different Engine - Review games.lnk" in text
    assert "Review-Games-Windows.bat" in text


def test_review_shortcut_has_its_own_green_icon():
    assert (ROOT / "different_engine" / "icon_review.ico").is_file()
    assert (ROOT / "different_engine" / "icon_review.png").is_file()
    assert "icon_review.ico" in WINDOWS.read_text()


def test_linux_shortcut_gains_window_class_if_missing(tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    dest = desktop / "The Different Engine.desktop"
    dest.write_text("\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=The Different Engine",
        f'Exec=bash "{ROOT}/start-linux.sh"',
        "",
    ]))
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["DE_DESKTOP_DIR"] = str(desktop)
    env["DE_CREATE_SHORTCUT_ONLY"] = "1"
    r = subprocess.run(["bash", str(SCRIPT)], cwd=str(ROOT), env=env,
                       text=True, capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr
    text = dest.read_text()
    assert "StartupWMClass=DifferentEngine" in text
    assert f"Icon={ROOT}/different_engine/icon.png" in text
    assert "I've put a shortcut" not in r.stdout
