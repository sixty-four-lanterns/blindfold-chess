"""Window icon helper: Windows taskbar id, Linux window class, no real display."""

import os
import sys
from pathlib import Path

import pytest

from different_engine import window_icon as wi

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "different_engine"


def _os_as(monkeypatch, name):
    """Patch only this module's view of os, so the real os.name stays intact."""
    class FakeOs:
        path = os.path
    FakeOs.name = name
    monkeypatch.setattr(wi, "os", FakeOs)


@pytest.fixture(autouse=True)
def reset_app_id_flag():
    wi._app_id_set = False
    yield
    wi._app_id_set = False


class FakeImage:
    def __init__(self, file=None):
        self.file = file


class FakeRoot:
    def __init__(self):
        self.iconbitmap_calls = []
        self.iconphoto_calls = []
        self._de_icon = None

    def iconbitmap(self, bitmap=None, default=None):
        self.iconbitmap_calls.append((bitmap, default))

    def iconphoto(self, default, image):
        self.iconphoto_calls.append((default, image))


def _install_tk(monkeypatch, photo=FakeImage):
    class FakeTkModule:
        PhotoImage = photo

        class Tk:
            def __init__(self, *a, **k):
                self.kwargs = k
                self.className = k.get("className")

    monkeypatch.setitem(sys.modules, "tkinter", FakeTkModule)
    return FakeTkModule


def test_icon_files_are_real_images():
    for name in ("icon.ico", "icon_review.ico"):
        with open(PKG / name, "rb") as f:
            assert f.read(4) == b"\x00\x00\x01\x00"
    for name in ("icon.png", "icon_review.png"):
        with open(PKG / name, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n"


def test_claim_windows_app_id_sets_id_before_any_window(monkeypatch):
    _os_as(monkeypatch, "nt")
    called = []

    class FakeShell32:
        @staticmethod
        def SetCurrentProcessExplicitAppUserModelID(app_id):
            called.append(app_id)

    class FakeWindll:
        shell32 = FakeShell32()

    import ctypes
    monkeypatch.setattr(ctypes, "windll", FakeWindll, raising=False)
    wi.claim_windows_app_id()
    assert called == [wi.APP_USER_MODEL_ID]
    assert wi.APP_USER_MODEL_ID == "SixtyFourLanterns.DifferentEngine"
    wi.claim_windows_app_id()
    assert called == [wi.APP_USER_MODEL_ID]          # only once


def test_claim_windows_app_id_is_noop_on_linux(monkeypatch):
    _os_as(monkeypatch, "posix")
    called = []

    class FakeShell32:
        @staticmethod
        def SetCurrentProcessExplicitAppUserModelID(app_id):
            called.append(app_id)

    class FakeWindll:
        shell32 = FakeShell32()

    import ctypes
    monkeypatch.setattr(ctypes, "windll", FakeWindll, raising=False)
    wi.claim_windows_app_id()
    assert called == []
    assert wi._app_id_set is False


def test_claim_windows_app_id_never_raises(monkeypatch):
    _os_as(monkeypatch, "nt")

    class Boom:
        def SetCurrentProcessExplicitAppUserModelID(self, app_id):
            raise OSError("no shell32")

    class FakeWindll:
        shell32 = Boom()

    import ctypes
    monkeypatch.setattr(ctypes, "windll", FakeWindll, raising=False)
    wi.claim_windows_app_id()
    assert wi._app_id_set is False


def test_apply_icon_windows_sets_bitmap_and_photo(monkeypatch):
    _os_as(monkeypatch, "nt")
    _install_tk(monkeypatch)
    root = FakeRoot()
    wi.apply_icon(root)
    assert root.iconbitmap_calls == [(None, wi.ICON_ICO)]
    assert len(root.iconphoto_calls) == 1
    default, image = root.iconphoto_calls[0]
    assert default is True
    assert image.file == wi.ICON_PNG
    assert root._de_icon is image


def test_apply_icon_linux_uses_photo_not_bitmap(monkeypatch):
    _os_as(monkeypatch, "posix")
    _install_tk(monkeypatch)
    root = FakeRoot()
    wi.apply_icon(root)
    assert root.iconbitmap_calls == []
    assert len(root.iconphoto_calls) == 1
    default, image = root.iconphoto_calls[0]
    assert default is True
    assert image.file == wi.ICON_PNG


def test_apply_icon_review_uses_green_knight(monkeypatch):
    _os_as(monkeypatch, "nt")
    _install_tk(monkeypatch)
    root = FakeRoot()
    wi.apply_icon(root, review=True)
    assert root.iconbitmap_calls == [(None, wi.ICON_REVIEW_ICO)]
    assert root.iconphoto_calls[0][1].file == wi.ICON_REVIEW_PNG


def test_apply_icon_never_raises(monkeypatch):
    _os_as(monkeypatch, "nt")

    class Broken(FakeRoot):
        def iconbitmap(self, bitmap=None, default=None):
            raise RuntimeError("bad ico")

        def iconphoto(self, default, image):
            raise RuntimeError("bad png")

    _install_tk(monkeypatch)
    wi.apply_icon(Broken())          # must not raise


def test_create_root_claims_id_then_sets_class_and_icon(monkeypatch):
    _os_as(monkeypatch, "nt")
    order = []

    def fake_claim():
        order.append("claim")

    class FakeTk:
        def __init__(self, *a, **k):
            order.append("tk")
            self.kwargs = k
            self.iconbitmap_calls = []
            self.iconphoto_calls = []
            self._de_icon = None

        def iconbitmap(self, bitmap=None, default=None):
            self.iconbitmap_calls.append((bitmap, default))

        def iconphoto(self, default, image):
            self.iconphoto_calls.append((default, image))

    class FakeTkModule:
        PhotoImage = FakeImage
        Tk = FakeTk

    monkeypatch.setattr(wi, "claim_windows_app_id", fake_claim)
    monkeypatch.setitem(sys.modules, "tkinter", FakeTkModule)
    root = wi.create_root()
    assert order == ["claim", "tk"]
    assert root.kwargs == {"className": "DifferentEngine"}
    assert wi.WINDOW_CLASS == "DifferentEngine"
    assert root.iconbitmap_calls == [(None, wi.ICON_ICO)]
    assert root.iconphoto_calls[0][0] is True
    assert root.iconphoto_calls[0][1].file == wi.ICON_PNG


def test_create_root_review_uses_green_icon(monkeypatch):
    _os_as(monkeypatch, "posix")

    class FakeTk:
        def __init__(self, *a, **k):
            self.kwargs = k
            self.iconbitmap_calls = []
            self.iconphoto_calls = []

        def iconbitmap(self, bitmap=None, default=None):
            self.iconbitmap_calls.append((bitmap, default))

        def iconphoto(self, default, image):
            self.iconphoto_calls.append((default, image))

    class FakeTkModule:
        PhotoImage = FakeImage
        Tk = FakeTk

    monkeypatch.setitem(sys.modules, "tkinter", FakeTkModule)
    root = wi.create_root(review=True)
    assert root.kwargs == {"className": "DifferentEngine"}
    assert root.iconbitmap_calls == []
    assert root.iconphoto_calls[0][1].file == wi.ICON_REVIEW_PNG


def test_every_window_is_created_through_the_helper():
    for name in ("board_editor.py", "reconstruction.py", "replay_viewer.py"):
        text = (PKG / name).read_text()
        assert "from .window_icon import create_root" in text
        assert "tk.Tk(" not in text
        assert "set_window_icon" not in text


def test_main_claims_windows_id_and_review_flag_used_for_board():
    main = (PKG / "__main__.py").read_text()
    assert "from .window_icon import claim_windows_app_id" in main
    assert "claim_windows_app_id()" in main
    assert "review=True" in main
