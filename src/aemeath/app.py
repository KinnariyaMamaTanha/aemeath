"""Main application – wires up Qt, system tray, game loop, and coordinates
the pet sprite, seal sprite, and behaviour logic.

Run with:
    python -m aemeath          (from project root)
    aemeath                    (if installed via pip / uv)
"""

from __future__ import annotations

import os
import random
import sys
import time

from aemeath import config


def _ensure_xcb_on_wayland() -> None:
    """Force the Qt xcb (X11/XWayland) backend when running on a Wayland
    session.

    The xcb backend is required for transparent, click-through, always-on-top
    windows (`WindowTransparentForInput`).  Input coordinates from the
    cursor tracker are converted to Qt logical coordinates by the
    ``needs_dpr_scaling`` flag — see :func:`_tick`.
    """
    if sys.platform != "linux":
        return
    session = os.environ.get("XDG_SESSION_TYPE", "")
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    if session == "wayland" or wayland_display:
        os.environ["QT_QPA_PLATFORM"] = "xcb"


# Must be called before QApplication is created.
_ensure_xcb_on_wayland()

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon  # noqa: E402

from aemeath.cursor import create_cursor_tracker  # noqa: E402
from aemeath.pet import Pet  # noqa: E402
from aemeath.sprite import SpriteWidget  # noqa: E402


class AemeathApp:
    """Top‑level controller for the desktop pet."""

    def __init__(self) -> None:
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)
        self._app.setApplicationName("Aemeath")

        # application icon
        if config.ICON_PATH.exists():
            self._app.setWindowIcon(QIcon(str(config.ICON_PATH)))

        # ── sprites ────────────────────────────────────────────────────
        self._pet_sprite = SpriteWidget(click_through=True)
        self._seal_sprite = SpriteWidget(click_through=True)
        self._seal_sprite.hide()

        # ── initial position (centre of primary screen) ────────────────
        screen = self._app.primaryScreen()
        geo = screen.availableGeometry()
        start_x = geo.center().x()
        start_y = geo.center().y()

        # ── adapt visual parameters to current screen ──────────────────
        config.adapt_to_screen(geo.height())

        # re-adapt if screen resolution changes (e.g. external monitor)
        screen.geometryChanged.connect(self._on_screen_geometry_changed)

        # ── pet logic ──────────────────────────────────────────────────
        self._pet = Pet(start_x, start_y)

        # show initial animation
        self._pet_sprite.set_animation(str(config.GIF_MOVE))
        self._pet_sprite.move_center_to(start_x, start_y)
        self._pet_sprite.show()

        # preload seal animation (stays hidden)
        self._seal_sprite.set_animation(str(config.GIF_SEAL))

        # cache to avoid redundant sprite updates
        self._prev_gif = None
        self._prev_flipped: bool | None = None

        # ── cursor tracker (X11/Win32, bypasses broken QCursor) ────────
        self._cursor = create_cursor_tracker()

        # ── system tray ────────────────────────────────────────────────
        self._setup_tray()

        # ── game loop ──────────────────────────────────────────────────
        self._start_time = time.monotonic()
        self._timer = QTimer()
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(config.TICK_INTERVAL)

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon()

        if config.ICON_PATH.exists():
            self._tray.setIcon(QIcon(str(config.ICON_PATH)))
        else:
            self._tray.setIcon(self._app.windowIcon())

        self._tray.setToolTip("Aemeath 桌宠")

        menu = QMenu()

        # speed sub‑menu
        speed_menu = menu.addMenu("移动速度")
        for label, speed in [
            ("慢速", 2.0),
            ("正常", 4.0),
            ("快速", 7.0),
            ("极速", 12.0),
        ]:
            action = speed_menu.addAction(label)
            action.triggered.connect(
                lambda _checked, s=speed: self._set_speed(s)
            )

        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._quit)

        self._tray.setContextMenu(menu)
        self._tray.show()

    def _set_speed(self, speed: float) -> None:
        self._pet.move_speed = speed
        self._pet.wander_speed = speed * 0.4

    def _on_screen_geometry_changed(self) -> None:
        """Re-scale visual parameters when the screen resolution changes."""
        screen = self._app.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            config.adapt_to_screen(geo.height())
            # Update cached speeds on the pet instance.
            self._pet.move_speed = config.MOVE_SPEED
            self._pet.wander_speed = config.WANDER_SPEED

    # ------------------------------------------------------------------
    # Game loop
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        now_ms = (time.monotonic() - self._start_time) * 1000.0

        # ── reset one‑shot signals before feeding new input ────────
        self._pet.seal_should_appear = False
        self._pet.seal_should_disappear = False

        # ── read inputs (via native cursor tracker) ───────────────────
        mx, my, buttons = self._cursor.query()

        # Only X11 XQueryPointer returns physical-pixel coords; compositor-
        # native backends (Hyprland, GNOME) already return logical coords.
        if self._cursor.needs_dpr_scaling:
            dpr = self._app.primaryScreen().devicePixelRatio()
            if dpr and dpr != 1.0:
                mx /= dpr
                my /= dpr

        # ── advance logic ──────────────────────────────────────────────
        self._pet.update_mouse(mx, my, buttons, now_ms)
        self._pet.tick(now_ms)

        # ── seal events ────────────────────────────────────────────────
        if self._pet.seal_should_appear:
            self._show_seal()
        if self._pet.seal_should_disappear:
            self._hide_seal()

        if self._seal_sprite.isVisible():
            sx, sy = self._seal_sprite.center_pos()
            self._pet.set_seal_position(sx, sy)

        # ── clamp pet position to screen ───────────────────────────────
        screen = self._app.primaryScreen()
        geo = screen.availableGeometry()
        margin = 30
        self._pet.x = max(geo.left() + margin, min(geo.right() - margin, self._pet.x))
        self._pet.y = max(geo.top() + margin, min(geo.bottom() - margin, self._pet.y))

        # ── update sprite position ─────────────────────────────────────
        self._pet_sprite.move_center_to(int(self._pet.x), int(self._pet.y))

        # ── update animation (only when changed) ───────────────────────
        gif = self._pet.current_gif
        flipped = self._pet.flipped
        if gif != self._prev_gif or flipped != self._prev_flipped:
            self._pet_sprite.set_animation(str(gif), flipped)
            self._prev_gif = gif
            self._prev_flipped = flipped

    # ------------------------------------------------------------------
    # Seal helpers
    # ------------------------------------------------------------------

    def _show_seal(self) -> None:
        screen = self._app.primaryScreen()
        geo = screen.availableGeometry()
        margin = 100
        sx = random.randint(geo.left() + margin, geo.right() - margin)
        sy = random.randint(geo.top() + margin, geo.bottom() - margin)
        self._seal_sprite.set_animation(str(config.GIF_SEAL))
        self._seal_sprite.move_center_to(sx, sy)
        self._seal_sprite.show()

    def _hide_seal(self) -> None:
        self._seal_sprite.hide()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _quit(self) -> None:
        self._timer.stop()
        self._tray.hide()
        self._cursor.close()
        self._app.quit()

    def run(self) -> int:
        return self._app.exec()


def main() -> None:
    app = AemeathApp()
    sys.exit(app.run())
