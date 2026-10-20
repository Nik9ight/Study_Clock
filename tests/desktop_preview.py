"""Capture only the app window on Windows, using stdlib APIs.

Run from the repository root: python tests/desktop_preview.py
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import struct
import sys
import tempfile
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import study_clock


def capture_window(app, destination):
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    handle = ctypes.c_void_p
    user32.GetAncestor.argtypes = [handle, wintypes.UINT]
    user32.GetAncestor.restype = handle
    user32.GetWindowRect.argtypes = [handle, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowDC.argtypes = [handle]
    user32.GetWindowDC.restype = handle
    user32.PrintWindow.argtypes = [handle, handle, wintypes.UINT]
    user32.ReleaseDC.argtypes = [handle, handle]
    gdi32.CreateCompatibleDC.argtypes = [handle]
    gdi32.CreateCompatibleDC.restype = handle
    gdi32.CreateCompatibleBitmap.argtypes = [handle, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = handle
    gdi32.SelectObject.argtypes = [handle, handle]
    gdi32.SelectObject.restype = handle
    gdi32.GetDIBits.argtypes = [handle, handle, wintypes.UINT, wintypes.UINT,
                              handle, handle, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [handle]
    gdi32.DeleteDC.argtypes = [handle]
    hwnd = user32.GetAncestor(app.winfo_id(), 2)
    bounds = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(bounds))
    width, height = bounds.right - bounds.left, bounds.bottom - bounds.top
    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, 0):
            raise RuntimeError("Could not capture the app window")
        gdi32.SelectObject(memory_dc, previous)
        info = ctypes.create_string_buffer(struct.pack(
            "<IiiHHIIiiII", 40, width, -height, 1, 32, 0, width * height * 4, 0, 0, 0, 0))
        pixels = ctypes.create_string_buffer(width * height * 4)
        if not gdi32.GetDIBits(memory_dc, bitmap, 0, height, pixels, info, 0):
            raise RuntimeError("Could not read app pixels")
        rows = bytearray()
        for offset in range(0, len(pixels.raw), width * 4):
            bgra = pixels.raw[offset:offset + width * 4]
            rgb = bytearray(width * 3)
            rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
            rows.extend(b"\0" + rgb)

        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

        destination.write_bytes(b"\x89PNG\r\n\x1a\n" +
                                chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
                                chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)


if __name__ == "__main__":
    if os.name != "nt":
        raise SystemExit("Desktop preview capture requires Windows.")
    output = Path(tempfile.mkdtemp(prefix="focus-desktop-previews-"))
    with tempfile.TemporaryDirectory() as preferences:
        with patch.object(study_clock, "PREFERENCES_FILE", Path(preferences) / "preferences.json"):
            app = study_clock.StudyClock()
            app.geometry(f"{study_clock.W}x{study_clock.H_BASE}+40+40")
            try:
                app.state = "paused"
                app.time_left = 1914
                app.total_left = 2214
                for theme in study_clock.THEMES:
                    app._set_theme(theme)
                    app.update()
                    capture_window(app, output / f"{theme}-Installer.png")
                for style in study_clock.PROGRESS_STYLES:
                    app._set_progress_style(style)
                    app.update()
                    capture_window(app, output / f"Forest-{style}.png")
                    app._enter_compact()
                    app.update()
                    capture_window(app, output / f"Compact-{style}.png")
                    app._exit_compact()
                app._set_progress_style("Installer")
                app._open_settings()
                app.update()
                capture_window(app, output / "Customize.png")
                app._close_settings()
                app._set_view("clock")
                app.update()
                capture_window(app, output / "Clock.png")
            finally:
                app._quit()
    print(f"Desktop previews: {output}")
