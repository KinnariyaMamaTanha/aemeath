"""Cross-platform cursor position tracking.

On Wayland, ``QCursor.pos()`` and ``XQueryPointer`` are unreliable —
they only return correct coordinates when the pointer is over an
XWayland surface.  This module provides compositor-native backends
that always return the correct global cursor position.

Backend priority (Linux / Wayland)
----------------------------------
1. **_HyprlandCursor** — Hyprland IPC socket (``cursorpos``)
2. **_GnomeCursor** — GNOME Shell ``Eval`` via D-Bus
3. **_KDECursor** — KWin scripting + D-Bus (``workspace.cursorPos``)
4. **_WaylandHybridCursor** — XQueryPointer + raw ``/dev/input/mice``
5. **_X11Cursor** — ``XQueryPointer`` via libX11 (X11 sessions only)

Other platforms
---------------
* **_Win32Cursor** — ``GetCursorPos`` / ``GetAsyncKeyState``
* **_QtCursor** — ``QCursor.pos()`` fallback
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod


class CursorTracker(ABC):
    """Abstract interface returned by :func:`create_cursor_tracker`."""

    @property
    def needs_dpr_scaling(self) -> bool:
        """Whether returned coordinates are physical pixels needing DPR
        division to match Qt's logical coordinate space."""
        return False

    @abstractmethod
    def query(self) -> tuple[float, float, bool]:
        """Return ``(x, y, any_button_pressed)`` in screen coordinates."""

    def close(self) -> None:  # noqa: B027 – optional override
        """Release resources (optional)."""


# =====================================================================
# Hyprland  (IPC socket — fastest, works on Hyprland ≥ 0.25)
# =====================================================================


class _HyprlandCursor(CursorTracker):
    """Query cursor position via Hyprland's IPC socket.

    The compositor returns logical (scaled) coordinates, so
    :attr:`needs_dpr_scaling` is ``False``.
    """

    def __init__(self) -> None:
        sig = os.environ["HYPRLAND_INSTANCE_SIGNATURE"]
        runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")

        candidates = [
            f"{runtime}/hypr/{sig}/.socket.sock",   # Hyprland ≥ 0.40
            f"/tmp/hypr/{sig}/.socket.sock",         # older versions
        ]
        self._socket_path: str = ""
        for p in candidates:
            if os.path.exists(p):
                self._socket_path = p
                break
        if self._socket_path is None:
            raise RuntimeError("Hyprland IPC socket not found")

        # Verify the socket actually responds.
        self._get_pos()

    # -- internal -----------------------------------------------------

    def _get_pos(self) -> tuple[float, float]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(self._socket_path)
            s.sendall(b"cursorpos")
            resp = s.recv(256).decode().strip()
        parts = resp.split(",")
        if len(parts) != 2:
            raise ValueError(f"Unexpected cursorpos response: {resp!r}")
        return float(parts[0].strip()), float(parts[1].strip())

    # -- public API ----------------------------------------------------

    def query(self) -> tuple[float, float, bool]:
        try:
            x, y = self._get_pos()
            # Hyprland IPC does not expose button state; default to False.
            return x, y, False
        except Exception:
            return 0.0, 0.0, False


# =====================================================================
# GNOME  (D-Bus — works on GNOME / Ubuntu / Pop!_OS)
# =====================================================================


class _GnomeCursor(CursorTracker):
    """Query cursor via GNOME Shell's ``global.get_pointer()`` D-Bus Eval.

    Tries ``gi.repository.Gio`` for zero-overhead D-Bus calls first;
    falls back to the ``gdbus`` CLI tool.
    """

    def __init__(self) -> None:
        self._bus: object | None = None
        self._use_gi: bool = False

        try:
            from gi.repository import Gio, GLib  # type: ignore[import-untyped]

            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._Gio = Gio
            self._GLib = GLib
            self._use_gi = True
            self._query_gi()  # smoke-test
        except Exception:
            self._use_gi = False
            self._query_subprocess()  # smoke-test (raises on failure)

    # -- gi.repository path --------------------------------------------

    def _query_gi(self) -> tuple[float, float, bool]:
        result = self._bus.call_sync(  # type: ignore[union-attr]
            "org.gnome.Shell",
            "/org/gnome/Shell",
            "org.gnome.Shell",
            "Eval",
            self._GLib.Variant("(s)", ("global.get_pointer()",)),
            self._GLib.VariantType.new("(bs)"),
            self._Gio.DBusCallFlags.NONE,
            500,
            None,
        )
        success, value = result.unpack()
        if not success:
            raise RuntimeError("GNOME Shell Eval returned failure")
        data = json.loads(value)
        # data == [x, y, Clutter.ModifierType]
        btn = bool(int(data[2]) & 0x100)  # BUTTON1_MASK
        return float(data[0]), float(data[1]), btn

    # -- subprocess path -----------------------------------------------

    @staticmethod
    def _query_subprocess() -> tuple[float, float, bool]:
        result = subprocess.run(
            [
                "gdbus", "call", "--session",
                "--dest", "org.gnome.Shell",
                "--object-path", "/org/gnome/Shell",
                "--method", "org.gnome.Shell.Eval",
                "global.get_pointer()",
            ],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gdbus call failed: {result.stderr}")
        m = re.search(r"\[(\d+),\s*(\d+),\s*(\d+)\]", result.stdout)
        if not m:
            raise RuntimeError(f"Cannot parse gdbus output: {result.stdout}")
        x, y, mods = float(m.group(1)), float(m.group(2)), int(m.group(3))
        return x, y, bool(mods & 0x100)

    # -- public API ----------------------------------------------------

    def query(self) -> tuple[float, float, bool]:
        try:
            if self._use_gi:
                return self._query_gi()
            return self._query_subprocess()
        except Exception:
            return 0.0, 0.0, False


# =====================================================================
# KDE  (KWin scripting + D-Bus — works on KDE Plasma 5.27+ / 6.x)
# =====================================================================

from PySide6.QtCore import ClassInfo, QObject, Slot  # noqa: E402
from PySide6.QtDBus import QDBusAbstractAdaptor, QDBusConnection  # noqa: E402

_KWIN_SCRIPT_NAME = "aemeath-cursor"

_KWIN_CURSOR_JS = """\
// KWin script: report cursor position to aemeath via D-Bus.
function send() {
    var pos = workspace.cursorPos;
    callDBus(
        "com.aemeath.CursorTracker", "/cursor",
        "com.aemeath.CursorTracker", "update",
        pos.x, pos.y
    );
}
// Send initial position.
send();
// Send on every cursor move.
workspace.cursorPosChanged.connect(send);
"""


class _CursorDBusParent(QObject):
    """Internal parent QObject for the D-Bus adaptor."""

    def __init__(self) -> None:
        super().__init__()
        self.x: float = -1.0
        self.y: float = -1.0


@ClassInfo({"D-Bus Interface": "com.aemeath.CursorTracker"})
class _CursorDBusAdaptor(QDBusAbstractAdaptor):
    """D-Bus adaptor that receives cursor updates from KWin.

    By using ``@ClassInfo`` the D-Bus interface name is fixed to
    ``com.aemeath.CursorTracker`` regardless of how the module is
    loaded or what the Python class path looks like.
    """

    def __init__(self, parent: _CursorDBusParent) -> None:
        super().__init__(parent)

    @Slot(int, int)
    def update(self, x: int, y: int) -> None:  # noqa: D401
        p = self.parent()
        p.x = float(x)
        p.y = float(y)


class _KDECursor(CursorTracker):
    """Query cursor via KWin scripting + D-Bus.

    Loads a tiny JavaScript snippet into KWin (the compositor) that
    connects to ``workspace.cursorPosChanged`` and sends the cursor
    coordinates to our D-Bus service.  KWin always knows the accurate
    cursor position, so this works regardless of whether the pointer
    is over XWayland or native Wayland surfaces.

    Returns logical (compositor-scaled) coordinates.
    """

    def __init__(self) -> None:
        import re
        import time

        from PySide6.QtWidgets import QApplication

        # ── D-Bus adaptor ───────────────────────────────────────────
        self._parent = _CursorDBusParent()
        self._adaptor = _CursorDBusAdaptor(self._parent)

        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            raise RuntimeError("Cannot connect to session D-Bus")

        if not bus.registerService("com.aemeath.CursorTracker"):
            raise RuntimeError(
                f"Cannot register D-Bus service: {bus.lastError().message()}"
            )
        if not bus.registerObject(
            "/cursor",
            self._parent,
            QDBusConnection.RegisterOption.ExportAdaptors,
        ):
            raise RuntimeError(
                f"Cannot register D-Bus object: {bus.lastError().message()}"
            )

        self._bus = bus

        # ── write KWin script to a temp file ────────────────────────
        self._script_dir = tempfile.mkdtemp(prefix="aemeath-kwin-")
        self._script_path = os.path.join(self._script_dir, "main.js")
        self._meta_path = os.path.join(self._script_dir, "metadata.json")
        with open(self._script_path, "w") as f:
            f.write(_KWIN_CURSOR_JS)
        with open(self._meta_path, "w") as f:
            json.dump(
                {
                    "KPlugin": {
                        "Name": "Aemeath Cursor Tracker",
                        "Id": _KWIN_SCRIPT_NAME,
                    }
                },
                f,
            )

        # ── unload any leftover script from a previous run ──────────
        subprocess.run(
            [
                "gdbus", "call", "--session",
                "--dest", "org.kde.KWin",
                "--object-path", "/Scripting",
                "--method", "org.kde.kwin.Scripting.unloadScript",
                _KWIN_SCRIPT_NAME,
            ],
            capture_output=True,
            timeout=3,
        )

        # ── load the script ────────────────────────────────────────
        result = subprocess.run(
            [
                "gdbus", "call", "--session",
                "--dest", "org.kde.KWin",
                "--object-path", "/Scripting",
                "--method", "org.kde.kwin.Scripting.loadScript",
                self._script_path,
                _KWIN_SCRIPT_NAME,
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0:
            self.close()
            raise RuntimeError(f"Failed to load KWin script: {result.stderr}")

        # ── start the script via its object ────────────────────────
        m = re.search(r"\((\d+),?\)", result.stdout)
        script_id = m.group(1) if m else "0"

        proc = subprocess.Popen(
            [
                "gdbus", "call", "--session",
                "--dest", "org.kde.KWin",
                "--object-path", f"/Scripting/Script{script_id}",
                "--method", "org.kde.kwin.Script.run",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Process Qt events while waiting for gdbus to finish so that
        # the D-Bus adaptor can respond to KWin's introspection query.
        while proc.poll() is None:
            QApplication.processEvents()
            time.sleep(0.01)
        proc.communicate()

        # ── wait for initial cursor data ───────────────────────────
        for _ in range(40):
            QApplication.processEvents()
            time.sleep(0.025)
            if self._parent.x >= 0:
                break

        if self._parent.x < 0:
            self.close()
            raise RuntimeError(
                "KWin script loaded but no cursor data received"
            )

    # -- public API ----------------------------------------------------

    def query(self) -> tuple[float, float, bool]:
        return self._parent.x, self._parent.y, False

    def close(self) -> None:
        try:
            subprocess.run(
                [
                    "gdbus", "call", "--session",
                    "--dest", "org.kde.KWin",
                    "--object-path", "/Scripting",
                    "--method", "org.kde.kwin.Scripting.unloadScript",
                    _KWIN_SCRIPT_NAME,
                ],
                capture_output=True,
                timeout=3,
            )
        except Exception:
            pass

        try:
            os.unlink(self._script_path)
            os.unlink(self._meta_path)
            os.rmdir(self._script_dir)
        except Exception:
            pass

        try:
            self._bus.unregisterObject("/cursor")
            self._bus.unregisterService("com.aemeath.CursorTracker")
        except Exception:
            pass


# =====================================================================
# Wayland hybrid  (XQueryPointer + /dev/input/mice — works on ALL
#                   Wayland compositors when user is in the `input` group)
# =====================================================================


class _WaylandHybridCursor(CursorTracker):
    """Combines ``XQueryPointer`` with raw ``/dev/input/mice`` deltas.

    On XWayland, ``XQueryPointer`` returns correct coordinates **only**
    when the pointer is over an XWayland surface.  When it is over a
    native Wayland window the value goes stale.

    This tracker detects staleness (position unchanged between ticks)
    and falls back to accumulating raw PS/2 mouse deltas to extrapolate
    the cursor position.  A dynamically-calibrated sensitivity factor
    maps raw counts to X11 pixels, automatically adapting to the user's
    pointer-acceleration settings.

    The position self-corrects whenever ``XQueryPointer`` returns a
    fresh value (e.g. when the cursor touches the pet sprite or any
    other XWayland window).

    Requires the user to be in the ``input`` group (or have read access
    to ``/dev/input/mice``).
    """

    @property
    def needs_dpr_scaling(self) -> bool:
        return True  # coordinates are in X11 physical-pixel space

    def __init__(self) -> None:
        # -- open /dev/input/mice for raw relative deltas ----------------
        if not os.access("/dev/input/mice", os.R_OK):
            raise RuntimeError(
                "/dev/input/mice is not readable. "
                "Add your user to the 'input' group: "
                "sudo usermod -aG input $USER"
            )
        self._mice_fd: int = os.open(
            "/dev/input/mice", os.O_RDONLY | os.O_NONBLOCK
        )

        # -- set up XQueryPointer via libX11 ----------------------------
        libname = ctypes.util.find_library("X11")
        if not libname:
            os.close(self._mice_fd)
            raise RuntimeError("libX11 not found")
        self._lib = ctypes.cdll.LoadLibrary(libname)

        self._lib.XOpenDisplay.restype = ctypes.c_void_p
        self._lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self._lib.XDefaultRootWindow.restype = ctypes.c_ulong
        self._lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self._lib.XQueryPointer.restype = ctypes.c_int
        self._lib.XQueryPointer.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint),
        ]
        self._lib.XCloseDisplay.restype = ctypes.c_int
        self._lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self._lib.XDisplayWidth.restype = ctypes.c_int
        self._lib.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._lib.XDisplayHeight.restype = ctypes.c_int
        self._lib.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]

        self._display = self._lib.XOpenDisplay(None)
        if not self._display:
            os.close(self._mice_fd)
            raise RuntimeError("Cannot open X display")
        self._root = self._lib.XDefaultRootWindow(self._display)

        # X11 screen dimensions (physical pixels).
        self._screen_w = float(self._lib.XDisplayWidth(self._display, 0))
        self._screen_h = float(self._lib.XDisplayHeight(self._display, 0))

        # Pre-allocated ctypes buffers.
        self._r_ret = ctypes.c_ulong()
        self._c_ret = ctypes.c_ulong()
        self._rx = ctypes.c_int()
        self._ry = ctypes.c_int()
        self._wx = ctypes.c_int()
        self._wy = ctypes.c_int()
        self._mask = ctypes.c_uint()

        # Seed with current XQueryPointer position.
        self._query_x11()
        self._x: float = float(self._rx.value)
        self._y: float = float(self._ry.value)
        self._last_x11_x: float = self._x
        self._last_x11_y: float = self._y

        # Dynamic sensitivity (raw-count → X11-pixel ratio).
        self._sensitivity: float = 1.0

    # -- internal helpers -----------------------------------------------

    def _query_x11(self) -> None:
        self._lib.XQueryPointer(
            self._display, self._root,
            ctypes.byref(self._r_ret), ctypes.byref(self._c_ret),
            ctypes.byref(self._rx), ctypes.byref(self._ry),
            ctypes.byref(self._wx), ctypes.byref(self._wy),
            ctypes.byref(self._mask),
        )

    def _read_mice(self) -> tuple[int, int, bool]:
        """Drain pending PS/2 packets from ``/dev/input/mice``.

        Returns cumulative ``(dx, dy_screen, left_button)`` since last
        call.  ``dy_screen`` is already negated (PS/2 Y-up → screen
        Y-down).
        """
        total_dx = 0
        total_dy = 0
        btn = False
        while True:
            try:
                data = os.read(self._mice_fd, 3)
            except OSError:
                break
            if len(data) < 3:
                break
            b = data[0]
            dx = data[1]
            dy = data[2]
            if b & 0x10:   # X sign bit → negative
                dx -= 256
            if b & 0x20:   # Y sign bit → negative
                dy -= 256
            total_dx += dx
            total_dy -= dy  # negate for screen coordinates
            btn = bool(b & 0x01)
        return total_dx, total_dy, btn

    # -- public API -----------------------------------------------------

    def query(self) -> tuple[float, float, bool]:
        # 1. Read raw deltas from /dev/input/mice.
        raw_dx, raw_dy, mice_btn = self._read_mice()

        # 2. Read XQueryPointer.
        self._query_x11()
        x11_x = float(self._rx.value)
        x11_y = float(self._ry.value)
        x11_btn = bool(self._mask.value & (1 << 8))

        # 3. Did XQueryPointer return a FRESH value?
        x11_dx = x11_x - self._last_x11_x
        x11_dy = x11_y - self._last_x11_y
        x11_changed = (x11_dx != 0.0 or x11_dy != 0.0)

        if x11_changed:
            # ── XQueryPointer is live → use its value directly ──
            self._x = x11_x
            self._y = x11_y
            self._last_x11_x = x11_x
            self._last_x11_y = x11_y

            # Dynamically calibrate sensitivity from the raw / actual
            # movement ratio (exponential moving average).
            raw_mag = math.hypot(raw_dx, raw_dy)
            actual_mag = math.hypot(x11_dx, x11_dy)
            if raw_mag > 3.0:
                new_ratio = actual_mag / raw_mag
                self._sensitivity = (
                    0.85 * self._sensitivity + 0.15 * new_ratio
                )
        else:
            # ── XQueryPointer is stale → extrapolate from raw deltas ──
            if raw_dx != 0 or raw_dy != 0:
                self._x += raw_dx * self._sensitivity
                self._y += raw_dy * self._sensitivity
                # Clamp to screen bounds.
                self._x = max(0.0, min(self._screen_w - 1, self._x))
                self._y = max(0.0, min(self._screen_h - 1, self._y))

        return self._x, self._y, x11_btn or mice_btn

    def close(self) -> None:
        if self._display:
            self._lib.XCloseDisplay(self._display)
            self._display = None
        if self._mice_fd >= 0:
            os.close(self._mice_fd)
            self._mice_fd = -1


# =====================================================================
# X11  (XQueryPointer — works on native X11 sessions)
# =====================================================================


class _X11Cursor(CursorTracker):
    """Query cursor position via ``XQueryPointer`` (libX11 + ctypes).

    Reliable on native X11.  On XWayland, coordinates are only correct
    when the pointer is over an XWayland surface — prefer a compositor-
    specific backend on Wayland.
    """

    @property
    def needs_dpr_scaling(self) -> bool:  # X11 returns physical pixels
        return True

    def __init__(self) -> None:
        libname = ctypes.util.find_library("X11")
        if not libname:
            raise RuntimeError("libX11 not found")

        self._lib = ctypes.cdll.LoadLibrary(libname)

        self._lib.XOpenDisplay.restype = ctypes.c_void_p
        self._lib.XOpenDisplay.argtypes = [ctypes.c_char_p]

        self._lib.XDefaultRootWindow.restype = ctypes.c_ulong
        self._lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]

        self._lib.XQueryPointer.restype = ctypes.c_int
        self._lib.XQueryPointer.argtypes = [
            ctypes.c_void_p,                   # display
            ctypes.c_ulong,                    # window
            ctypes.POINTER(ctypes.c_ulong),    # root_return
            ctypes.POINTER(ctypes.c_ulong),    # child_return
            ctypes.POINTER(ctypes.c_int),      # root_x_return
            ctypes.POINTER(ctypes.c_int),      # root_y_return
            ctypes.POINTER(ctypes.c_int),      # win_x_return
            ctypes.POINTER(ctypes.c_int),      # win_y_return
            ctypes.POINTER(ctypes.c_uint),     # mask_return
        ]

        self._lib.XCloseDisplay.restype = ctypes.c_int
        self._lib.XCloseDisplay.argtypes = [ctypes.c_void_p]

        self._display = self._lib.XOpenDisplay(None)
        if not self._display:
            raise RuntimeError("Cannot open X display")

        self._root = self._lib.XDefaultRootWindow(self._display)

        # Pre-allocate return-value buffers.
        self._root_ret = ctypes.c_ulong()
        self._child_ret = ctypes.c_ulong()
        self._root_x = ctypes.c_int()
        self._root_y = ctypes.c_int()
        self._win_x = ctypes.c_int()
        self._win_y = ctypes.c_int()
        self._mask = ctypes.c_uint()

    def query(self) -> tuple[float, float, bool]:
        self._lib.XQueryPointer(
            self._display,
            self._root,
            ctypes.byref(self._root_ret),
            ctypes.byref(self._child_ret),
            ctypes.byref(self._root_x),
            ctypes.byref(self._root_y),
            ctypes.byref(self._win_x),
            ctypes.byref(self._win_y),
            ctypes.byref(self._mask),
        )
        pressed = bool(self._mask.value & (1 << 8))  # Button1Mask
        return float(self._root_x.value), float(self._root_y.value), pressed

    def close(self) -> None:
        if self._display:
            self._lib.XCloseDisplay(self._display)
            self._display = None


# =====================================================================
# Win32
# =====================================================================


class _Win32Cursor(CursorTracker):
    """Query cursor position via Win32 API."""

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        self._pt = self._POINT()

    def query(self) -> tuple[float, float, bool]:
        self._user32.GetCursorPos(ctypes.byref(self._pt))
        VK_LBUTTON = 0x01
        pressed = bool(self._user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        return float(self._pt.x), float(self._pt.y), pressed


# =====================================================================
# Qt fallback
# =====================================================================


class _QtCursor(CursorTracker):
    """Fallback using ``QCursor.pos()`` (works on X11 / Windows)."""

    def query(self) -> tuple[float, float, bool]:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication

        pos = QCursor.pos()
        buttons = QApplication.mouseButtons()
        return (
            float(pos.x()),
            float(pos.y()),
            buttons != Qt.MouseButton.NoButton,
        )


# =====================================================================
# Factory
# =====================================================================


def create_cursor_tracker() -> CursorTracker:
    """Return the best available :class:`CursorTracker` for this platform."""

    if sys.platform == "win32":
        try:
            return _Win32Cursor()
        except Exception:
            pass

    elif sys.platform == "linux":
        is_wayland = bool(
            os.environ.get("WAYLAND_DISPLAY")
            or os.environ.get("XDG_SESSION_TYPE") == "wayland"
        )

        if is_wayland:
            # ── compositor-specific (reliable on Wayland) ──────────
            if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
                try:
                    return _HyprlandCursor()
                except Exception:
                    pass

            desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
            if any(d in desktop for d in ("GNOME", "UBUNTU", "POP", "UNITY")):
                try:
                    return _GnomeCursor()
                except Exception:
                    pass

            if any(d in desktop for d in ("KDE", "PLASMA")):
                try:
                    return _KDECursor()
                except Exception:
                    pass

            # Other Wayland compositors: hybrid XQueryPointer +
            # /dev/input/mice. Works when user is in the `input` group.

            # ── hybrid: XQueryPointer + raw mouse deltas ───────────
            try:
                return _WaylandHybridCursor()
            except Exception:
                pass

        # ── X11 (native X11 sessions, or XWayland fallback) ────────
        try:
            return _X11Cursor()
        except Exception:
            pass

    # ── last resort ────────────────────────────────────────────────
    return _QtCursor()
