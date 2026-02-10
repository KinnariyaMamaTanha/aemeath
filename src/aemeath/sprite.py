"""Transparent sprite widget for displaying animated GIFs on the desktop."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QMovie, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from aemeath import config


class SpriteWidget(QWidget):
    """A frameless, transparent, always‑on‑top widget that plays an animated GIF.

    Supports horizontal flipping (mirroring) so that a rightward-facing
    animation can be shown facing left when the pet moves to the left.
    """

    def __init__(self, click_through: bool = True) -> None:
        super().__init__()

        # --- window flags ---------------------------------------------------
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # hide from taskbar
        )
        if click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        # --- child label for pixmap ----------------------------------------
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background: transparent;")

        # --- movie (single instance, reused) --------------------------------
        self._movie = QMovie()
        self._movie.frameChanged.connect(self._render_frame)

        # --- state ----------------------------------------------------------
        self._current_path: str = ""
        self._flipped: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_animation(self, gif_path: str, flipped: bool = False) -> None:
        """Switch to displaying *gif_path*, optionally flipped horizontally."""
        path_str = str(gif_path)

        if path_str == self._current_path and flipped == self._flipped:
            return  # nothing to change

        if path_str == self._current_path:
            # same animation, only the flip state changed
            self._flipped = flipped
            self._render_frame()
            return

        # brand-new animation
        self._current_path = path_str
        self._flipped = flipped
        self._movie.stop()
        self._movie.setFileName(path_str)
        self._movie.start()

    def set_flipped(self, flipped: bool) -> None:
        """Change horizontal flip without reloading the animation."""
        if flipped != self._flipped:
            self._flipped = flipped
            self._render_frame()

    def current_frame_number(self) -> int:
        return self._movie.currentFrameNumber()

    def frame_count(self) -> int:
        return self._movie.frameCount()

    def move_center_to(self, x: int, y: int) -> None:
        """Position the widget so that its centre is at screen coordinate (*x*, *y*)."""
        self.move(x - self.width() // 2, y - self.height() // 2)

    def center_pos(self) -> tuple[float, float]:
        """Return the centre of the widget in screen coordinates."""
        return (
            self.x() + self.width() / 2.0,
            self.y() + self.height() / 2.0,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _render_frame(self) -> None:
        """Called on every frame change – applies optional flip and resizes."""
        image = self._movie.currentImage()
        if image.isNull():
            return

        if self._flipped:
            image = image.mirrored(True, False)

        pixmap = QPixmap.fromImage(image)

        # scale down if configured
        scale = config.SPRITE_SCALE
        if scale != 1.0:
            new_w = max(1, int(pixmap.width() * scale))
            new_h = max(1, int(pixmap.height() * scale))
            pixmap = pixmap.scaled(
                new_w, new_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        self._label.setPixmap(pixmap)
        self._label.resize(pixmap.size())
        self.resize(pixmap.size())
