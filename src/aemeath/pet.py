"""Pet behaviour logic and finite‑state machine.

States
------
CHASING       – mouse is far; pet moves toward cursor
WANDERING     – mouse is near; pet walks randomly near cursor for a while
IDLING        – pet stands still, playing a random idle*.gif
DRAGGING      – mouse button is held down; pet shows drag.gif
SEAL_MODE     – mouse has been idle a very long time; a seal appeared and
                the pet follows / plays around the seal instead
"""

from __future__ import annotations

import enum
import math
import random

from aemeath import config


class PetState(enum.Enum):
    CHASING = "chasing"
    WANDERING = "wandering"
    IDLING = "idling"
    DRAGGING = "dragging"
    SEAL_MODE = "seal_mode"


class Pet:
    """Pure‑logic class (no Qt dependency) that drives the desktop pet.

    Call :meth:`update_mouse` with the current cursor info, then :meth:`tick`
    every frame.  After each ``tick``, read :attr:`current_gif`, :attr:`flipped`,
    :attr:`x`, :attr:`y`, and the ``seal_should_*`` flags.
    """

    def __init__(self, start_x: float, start_y: float) -> None:
        # --- position -------------------------------------------------------
        self.x: float = start_x
        self.y: float = start_y

        # --- state machine --------------------------------------------------
        self.state: PetState = PetState.CHASING
        self._prev_state: PetState = PetState.CHASING

        # --- mouse tracking -------------------------------------------------
        self._mouse_x: float = start_x
        self._mouse_y: float = start_y
        self._last_mouse_x: float = start_x
        self._last_mouse_y: float = start_y
        self._mouse_idle_start_ms: float = 0.0
        self._mouse_idle_time: float = 0.0  # ms since last significant move
        self._mouse_pressed: bool = False

        # --- wandering ------------------------------------------------------
        self._wander_anchor_x: float = start_x
        self._wander_anchor_y: float = start_y
        self._wander_target_x: float = start_x
        self._wander_target_y: float = start_y
        self._wander_end_time: float = 0.0
        self._wander_dir_change_time: float = 0.0

        # --- idling ---------------------------------------------------------
        self._idle_end_time: float = 0.0
        self._idle_anchor_mouse_x: float = start_x  # mouse pos when idling began
        self._idle_anchor_mouse_y: float = start_y

        # --- seal mode ------------------------------------------------------
        self._seal_active: bool = False
        self._seal_x: float = 0.0
        self._seal_y: float = 0.0
        self._seal_wander_target_x: float = 0.0
        self._seal_wander_target_y: float = 0.0
        self._seal_wander_dir_time: float = 0.0

        # --- output (read after tick) ---------------------------------------
        self.current_gif = config.GIF_MOVE
        self.flipped: bool = False
        self.seal_should_appear: bool = False
        self.seal_should_disappear: bool = False

        # --- tunables -------------------------------------------------------
        self.move_speed: float = config.MOVE_SPEED
        self.wander_speed: float = config.WANDER_SPEED

    # ------------------------------------------------------------------
    # External input
    # ------------------------------------------------------------------

    def update_mouse(
        self,
        mx: float,
        my: float,
        buttons_pressed: bool,
        now_ms: float,
    ) -> None:
        """Feed current mouse state.  Call once per tick **before** :meth:`tick`."""
        self._mouse_pressed = buttons_pressed

        dx = mx - self._last_mouse_x
        dy = my - self._last_mouse_y
        moved = math.hypot(dx, dy) > config.MOUSE_MOVE_THRESHOLD

        if moved:
            self._mouse_idle_start_ms = now_ms
            self._mouse_idle_time = 0.0
            # dismiss seal when user starts moving the mouse again
            if self._seal_active:
                self._seal_active = False
                self.seal_should_disappear = True
        else:
            self._mouse_idle_time = now_ms - self._mouse_idle_start_ms

        self._last_mouse_x = mx
        self._last_mouse_y = my
        self._mouse_x = mx
        self._mouse_y = my

    def set_seal_position(self, sx: float, sy: float) -> None:
        self._seal_x = sx
        self._seal_y = sy

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self, now_ms: float) -> None:
        """Advance the state machine by one frame."""
        # --- drag detection (overrides any state) --------------------------
        if self._mouse_pressed and self.state != PetState.DRAGGING:
            self._prev_state = self.state
            self.state = PetState.DRAGGING
        elif not self._mouse_pressed and self.state == PetState.DRAGGING:
            self.state = self._prev_state

        # --- choose target --------------------------------------------------
        if self._seal_active and self.state not in (PetState.DRAGGING,):
            target_x, target_y = self._seal_x, self._seal_y
        else:
            target_x, target_y = self._mouse_x, self._mouse_y

        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.hypot(dx, dy)

        # --- dispatch to current state handler ------------------------------
        handler = {
            PetState.CHASING: self._handle_chasing,
            PetState.WANDERING: self._handle_wandering,
            PetState.IDLING: self._handle_idling,
            PetState.DRAGGING: self._handle_dragging,
            PetState.SEAL_MODE: self._handle_seal_mode,
        }[self.state]
        handler(dx, dy, dist, now_ms)

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_dragging(
        self, dx: float, dy: float, dist: float, now_ms: float
    ) -> None:
        self.current_gif = config.GIF_DRAG
        self.flipped = False

    def _handle_chasing(
        self, dx: float, dy: float, dist: float, now_ms: float
    ) -> None:
        if dist < config.NEAR_DISTANCE:
            # close enough → start wandering
            self.state = PetState.WANDERING
            self._init_wander(now_ms)
            return

        self._move_toward(dx, dy, dist, self.move_speed)
        self.current_gif = config.GIF_MOVE
        self.flipped = dx < 0

    def _handle_wandering(
        self, dx: float, dy: float, dist: float, now_ms: float
    ) -> None:
        # mouse went far → chase again
        if dist > config.FAR_DISTANCE and not self._seal_active:
            self.state = PetState.CHASING
            return

        # wander time elapsed → idle
        if now_ms > self._wander_end_time:
            self.state = PetState.IDLING
            self._init_idle(now_ms)
            return

        # keep anchor near the current target (mouse or seal)
        if self._seal_active:
            self._wander_anchor_x = self._seal_x
            self._wander_anchor_y = self._seal_y
        else:
            self._wander_anchor_x = self._mouse_x
            self._wander_anchor_y = self._mouse_y

        # pick a new random direction when the timer fires
        if now_ms > self._wander_dir_change_time:
            self._pick_wander_target(now_ms)

        # move toward current wander target
        wx = self._wander_target_x - self.x
        wy = self._wander_target_y - self.y
        wdist = math.hypot(wx, wy)

        if wdist < self.wander_speed:
            self._pick_wander_target(now_ms)
        else:
            self._move_toward(wx, wy, wdist, self.wander_speed)

        self.current_gif = config.GIF_MOVE
        self.flipped = wx < 0

    def _handle_idling(
        self, dx: float, dy: float, dist: float, now_ms: float
    ) -> None:
        # mouse went far → chase
        if dist > config.FAR_DISTANCE and not self._seal_active:
            self.state = PetState.CHASING
            return

        # mouse moved significantly since we started idling → re‑wander
        if not self._seal_active:
            mdx = self._mouse_x - self._idle_anchor_mouse_x
            mdy = self._mouse_y - self._idle_anchor_mouse_y
            if math.hypot(mdx, mdy) > config.MOUSE_MOVE_THRESHOLD * 10:
                self.state = PetState.WANDERING
                self._init_wander(now_ms)
                return

        # seal condition: mouse has been idle for a very long time
        if not self._seal_active and self._mouse_idle_time > config.MOUSE_IDLE_T2:
            self._seal_active = True
            self.seal_should_appear = True
            self.state = PetState.SEAL_MODE
            self._seal_wander_dir_time = 0.0
            return

        # switch idle gif when timer fires
        if now_ms > self._idle_end_time:
            self.current_gif = self._pick_idle_gif()
            self._idle_end_time = now_ms + random.randint(
                config.IDLE_MIN_DURATION, config.IDLE_MAX_DURATION
            )

        self.flipped = False  # idle gifs face forward

    def _handle_seal_mode(
        self, dx: float, dy: float, dist: float, now_ms: float
    ) -> None:
        if not self._seal_active:
            # seal dismissed (mouse moved) → chase cursor
            self.state = PetState.CHASING
            return

        sdx = self._seal_x - self.x
        sdy = self._seal_y - self.y
        sdist = math.hypot(sdx, sdy)

        if sdist > config.NEAR_DISTANCE:
            # too far from seal → chase it
            self._move_toward(sdx, sdy, sdist, self.move_speed)
            self.current_gif = config.GIF_MOVE
            self.flipped = sdx < 0
        else:
            # wander around the seal
            if now_ms > self._seal_wander_dir_time:
                angle = random.uniform(0, 2 * math.pi)
                r = random.uniform(20, config.SEAL_WANDER_RADIUS)
                self._seal_wander_target_x = self._seal_x + r * math.cos(angle)
                self._seal_wander_target_y = self._seal_y + r * math.sin(angle)
                self._seal_wander_dir_time = now_ms + random.randint(
                    config.WANDER_DIR_CHANGE_MIN, config.WANDER_DIR_CHANGE_MAX
                )

            wx = self._seal_wander_target_x - self.x
            wy = self._seal_wander_target_y - self.y
            wdist = math.hypot(wx, wy)

            if wdist > self.wander_speed:
                self._move_toward(wx, wy, wdist, self.wander_speed)

            self.current_gif = config.GIF_MOVE
            self.flipped = wx < 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _move_toward(
        self, dx: float, dy: float, dist: float, speed: float
    ) -> None:
        if dist <= speed:
            self.x += dx
            self.y += dy
        else:
            self.x += dx / dist * speed
            self.y += dy / dist * speed

    def _init_wander(self, now_ms: float) -> None:
        self._wander_anchor_x = self._mouse_x
        self._wander_anchor_y = self._mouse_y
        self._wander_end_time = now_ms + random.randint(
            config.WANDER_DURATION_MIN, config.WANDER_DURATION_MAX
        )
        self._pick_wander_target(now_ms)

    def _pick_wander_target(self, now_ms: float) -> None:
        angle = random.uniform(0, 2 * math.pi)
        r = random.uniform(20, config.WANDER_RADIUS)
        self._wander_target_x = self._wander_anchor_x + r * math.cos(angle)
        self._wander_target_y = self._wander_anchor_y + r * math.sin(angle)
        self._wander_dir_change_time = now_ms + random.randint(
            config.WANDER_DIR_CHANGE_MIN, config.WANDER_DIR_CHANGE_MAX
        )

    def _init_idle(self, now_ms: float) -> None:
        self._idle_anchor_mouse_x = self._mouse_x
        self._idle_anchor_mouse_y = self._mouse_y
        self.current_gif = self._pick_idle_gif()
        self._idle_end_time = now_ms + random.randint(
            config.IDLE_MIN_DURATION, config.IDLE_MAX_DURATION
        )
        self.flipped = False

    def _pick_idle_gif(self):
        """Choose an idle GIF respecting the idle2 probability ramp."""
        n = len(config.GIF_IDLE)
        if n == 0:
            return config.GIF_MOVE  # fallback

        # Before t1: equal probability
        if self._mouse_idle_time < config.MOUSE_IDLE_T1:
            return random.choice(config.GIF_IDLE)

        # After t1: idle2 probability linearly increases to 100 %
        elapsed = self._mouse_idle_time - config.MOUSE_IDLE_T1
        ramp = min(elapsed / config.IDLE2_RAMP_DURATION, 1.0)

        base = 1.0 / n
        idle2_prob = base + ramp * (1.0 - base)
        other_prob = (1.0 - idle2_prob) / max(n - 1, 1)

        r = random.random()
        cumulative = 0.0
        for gif in config.GIF_IDLE:
            prob = idle2_prob if gif == config.GIF_IDLE2 else other_prob
            cumulative += prob
            if r < cumulative:
                return gif

        return config.GIF_IDLE[-1]  # fallback
