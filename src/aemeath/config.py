"""Configuration constants for the Aemeath desktop pet.

All visual parameters (sizes, distances, speeds) are defined as *base*
values calibrated for a 1280 px-tall screen.  Call :func:`adapt_to_screen`
at startup (and whenever the screen geometry changes) to scale them
proportionally.
"""

from __future__ import annotations

from pathlib import Path


def _find_assets_dir() -> Path:
    """Locate the assets directory relative to package or working directory."""
    import sys

    # PyInstaller single-file mode: assets are extracted to sys._MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        assets = Path(meipass) / "assets"
        if assets.exists():
            return assets

    # Try relative to package source tree: src/aemeath/config.py -> ../../assets
    pkg_dir = Path(__file__).resolve().parent
    project_dir = pkg_dir.parent.parent
    assets = project_dir / "assets"
    if assets.exists():
        return assets

    # Fallback: relative to current working directory
    assets = Path.cwd() / "assets"
    if assets.exists():
        return assets

    raise FileNotFoundError(
        "Cannot find 'assets' directory. Run from the project root or install properly."
    )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ASSETS_DIR = _find_assets_dir()
GIFS_DIR = ASSETS_DIR / "gifs"
ICONS_DIR = ASSETS_DIR / "icons"

# GIF file paths
GIF_MOVE: Path = GIFS_DIR / "move.gif"
GIF_DRAG: Path = GIFS_DIR / "drag.gif"
GIF_SEAL: Path = GIFS_DIR / "seal.gif"
GIF_IDLE: list[Path] = [GIFS_DIR / f"idle{i}.gif" for i in range(1, 6)]
GIF_IDLE2: Path = GIFS_DIR / "idle2.gif"  # special: probability ramps up

# Icon
ICON_PATH: Path = ICONS_DIR / "aemeath.ico"

# ---------------------------------------------------------------------------
# Movement
# ---------------------------------------------------------------------------
MOVE_SPEED: float = 4.0        # pixels per tick when chasing
WANDER_SPEED: float = 1.5      # pixels per tick when wandering

# Distance thresholds (hysteresis prevents flickering)
NEAR_DISTANCE: float = 80.0   # distance below which the mouse is "near"
FAR_DISTANCE: float = 250.0    # distance above which the mouse is "far"

# ---------------------------------------------------------------------------
# Wandering
# ---------------------------------------------------------------------------
WANDER_DURATION_MIN: int = 2000    # ms
WANDER_DURATION_MAX: int = 4000    # ms
WANDER_RADIUS: float = 80.0       # pixels from anchor point
WANDER_DIR_CHANGE_MIN: int = 500   # ms between random direction changes
WANDER_DIR_CHANGE_MAX: int = 1500  # ms

# ---------------------------------------------------------------------------
# Idle
# ---------------------------------------------------------------------------
IDLE_MIN_DURATION: int = 2000   # ms, minimum play time for one idle gif
IDLE_MAX_DURATION: int = 6000   # ms, maximum play time for one idle gif

# ---------------------------------------------------------------------------
# Mouse idle detection
# ---------------------------------------------------------------------------
MOUSE_MOVE_THRESHOLD: float = 5.0    # pixels; movement below this = "not moved"
MOUSE_IDLE_T1: int = 30_000          # ms – idle2 probability starts increasing
MOUSE_IDLE_T2: int = 120_000         # ms – seal appears
IDLE2_RAMP_DURATION: int = 60_000    # ms – time for idle2 to reach 100% after t1

# ---------------------------------------------------------------------------
# Seal
# ---------------------------------------------------------------------------
SEAL_WANDER_RADIUS: float = 120.0   # pet wanders within this radius of seal

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
SPRITE_SCALE: float = 0.35      # scale factor applied to every GIF frame

# ---------------------------------------------------------------------------
# Screen-adaptive scaling
# ---------------------------------------------------------------------------
REFERENCE_SCREEN_HEIGHT: int = 1280  # the logical screen height the base values are tuned for

# Base (unscaled) values — used by adapt_to_screen() to recompute.
_BASE_VALUES: dict[str, float] = {
    "SPRITE_SCALE": SPRITE_SCALE,
    "MOVE_SPEED": MOVE_SPEED,
    "WANDER_SPEED": WANDER_SPEED,
    "NEAR_DISTANCE": NEAR_DISTANCE,
    "FAR_DISTANCE": FAR_DISTANCE,
    "WANDER_RADIUS": WANDER_RADIUS,
    "SEAL_WANDER_RADIUS": SEAL_WANDER_RADIUS,
    "MOUSE_MOVE_THRESHOLD": MOUSE_MOVE_THRESHOLD,
}


def adapt_to_screen(screen_height: int) -> None:
    """Scale visual parameters proportionally to *screen_height*.

    Parameters whose *visual* meaning depends on screen size (sprite scale,
    movement speeds, distance thresholds, wander radii) are multiplied by
    ``screen_height / REFERENCE_SCREEN_HEIGHT``.  This keeps the pet the
    same *proportion* of the screen on any resolution.

    Safe to call multiple times — always recalculates from the stored base
    values.
    """
    import aemeath.config as _cfg

    ratio = screen_height / _cfg.REFERENCE_SCREEN_HEIGHT
    for name, base in _cfg._BASE_VALUES.items():
        setattr(_cfg, name, base * ratio)


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------
TICK_INTERVAL: int = 33  # ms (~30 fps)
