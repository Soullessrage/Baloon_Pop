"""Canvas-based four-direction balloon-popping game."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
import time
import tkinter as tk


PASTEL_BALLOON_COLORS = ("#f28fad", "#82c9e8", "#a8dba8", "#f5d76e", "#c5a3e8", "#f3ad7b")
PLAYER_SPEED = 285
SHOT_INTERVAL = 0.22


@dataclass
class Balloon:
    """A pastel balloon drifting in from the right edge."""

    x: float
    y: float
    radius: float
    speed: float
    drift: float
    color: str


@dataclass
class Projectile:
    """A small pixel shot travelling in the plane's facing direction."""

    x: float
    y: float
    velocity_x: float
    velocity_y: float


class PlaneGame:
    """Manage game state, controls, collisions, and Canvas rendering."""

    def __init__(self, root: tk.Tk, canvas: tk.Canvas, on_exit):
        self.root = root
        self.canvas = canvas
        self.on_exit = on_exit
        self.state = "stopped"
        self._after_id = None
        self._held_keys = set()
        self._last_frame = 0.0
        self._last_shot = 0.0
        self._spawn_in = 0.0
        self._cloud_offset = 0.0
        self._width = 1
        self._height = 1

    def start(self):
        """Start a fresh game and focus keyboard input on the game canvas."""
        self._cancel_frame()
        self.state = "playing"
        self.score = 0
        self.lives = 3
        self.plane_x = max(60, self.canvas.winfo_width() * 0.14)
        self.plane_y = self.canvas.winfo_height() * 0.5
        self.facing = (1, 0)
        self.balloons: list[Balloon] = []
        self.projectiles: list[Projectile] = []
        self._held_keys.clear()
        self._spawn_in = 0.45
        self._last_shot = 0.0
        self._last_frame = time.perf_counter()
        self.canvas.focus_set()
        self.draw()
        self._schedule_frame()

    def stop(self):
        """Stop the game loop and release held controls."""
        self.state = "stopped"
        self._held_keys.clear()
        self._cancel_frame()

    def handle_keypress(self, key):
        """Handle a key press; return whether the game consumed it."""
        normalized = key.lower()
        if normalized == "escape":
            self.handle_escape()
            return True
        if self.state != "playing":
            return normalized in {"w", "a", "s", "d", "space"}
        if normalized in {"w", "a", "s", "d", "space"}:
            self._held_keys.add(normalized)
            direction = {"w": (0, -1), "a": (-1, 0), "s": (0, 1), "d": (1, 0)}.get(normalized)
            if direction:
                self.facing = direction
            return True
        return False

    def handle_keyrelease(self, key):
        """Stop continuous movement or shooting when the key is released."""
        normalized = key.lower()
        self._held_keys.discard(normalized)
        return normalized in {"w", "a", "s", "d", "space"}

    def handle_escape(self):
        """Pause the game when Escape is pressed during play."""
        if self.state == "playing":
            self.state = "paused"
            self._held_keys.clear()
            self._cancel_frame()
            self.draw()

    def continue_game(self):
        """Resume a paused game without resetting its score or lives."""
        if self.state != "paused":
            return
        self.state = "playing"
        self._last_frame = time.perf_counter()
        self.canvas.focus_set()
        self.draw()
        self._schedule_frame()

    def exit_to_menu(self):
        """Return to the app menu and stop the active game."""
        self.stop()
        self.on_exit()

    def _schedule_frame(self):
        if self.state == "playing" and self._after_id is None:
            self._after_id = self.root.after(16, self._tick)

    def _cancel_frame(self):
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _tick(self):
        self._after_id = None
        if self.state != "playing":
            return
        now = time.perf_counter()
        delta = min(now - self._last_frame, 0.05)
        self._last_frame = now
        self._step(delta)
        self.draw()
        self._schedule_frame()

    def _step(self, delta):
        self._width = max(self.canvas.winfo_width(), 1)
        self._height = max(self.canvas.winfo_height(), 1)
        self._cloud_offset += 38 * delta

        horizontal = int("d" in self._held_keys) - int("a" in self._held_keys)
        vertical = int("s" in self._held_keys) - int("w" in self._held_keys)
        magnitude = math.hypot(horizontal, vertical)
        if magnitude:
            self.plane_x += horizontal / magnitude * PLAYER_SPEED * delta
            self.plane_y += vertical / magnitude * PLAYER_SPEED * delta
        self.plane_x = max(26, min(self._width - 26, self.plane_x))
        self.plane_y = max(74, min(self._height - 42, self.plane_y))

        self._last_shot -= delta
        if "space" in self._held_keys and self._last_shot <= 0:
            self._fire()
            self._last_shot = SHOT_INTERVAL

        self._spawn_in -= delta
        if self._spawn_in <= 0:
            self._spawn_balloon()
            self._spawn_in = random.uniform(0.9, 1.55)

        for projectile in self.projectiles:
            projectile.x += projectile.velocity_x * delta
            projectile.y += projectile.velocity_y * delta
        self.projectiles = [
            projectile
            for projectile in self.projectiles
            if -12 <= projectile.x <= self._width + 12 and -12 <= projectile.y <= self._height + 12
        ]

        missed = []
        for balloon in self.balloons:
            balloon.x -= balloon.speed * delta
            balloon.y = max(56, min(self._height - 44, balloon.y + balloon.drift * delta))
            if balloon.x + balloon.radius < 0:
                missed.append(balloon)
                self._lose_life()
                if self.state == "game_over":
                    break
        for balloon in missed:
            if balloon in self.balloons:
                self.balloons.remove(balloon)

        if self.state != "playing":
            return

        player_radius = 14
        for balloon in tuple(self.balloons):
            if math.hypot(balloon.x - self.plane_x, balloon.y - self.plane_y) < balloon.radius + player_radius:
                self.balloons.remove(balloon)
                self._lose_life()
                break

        if self.state != "playing":
            return

        for projectile in tuple(self.projectiles):
            for balloon in tuple(self.balloons):
                if math.hypot(balloon.x - projectile.x, balloon.y - projectile.y) <= balloon.radius + 4:
                    self.balloons.remove(balloon)
                    self.projectiles.remove(projectile)
                    self.score += 1
                    break

    def _fire(self):
        self.projectiles.append(
            Projectile(
                self.plane_x + 21,
                self.plane_y,
                470,
                0,
            )
        )

    def _spawn_balloon(self):
        self.balloons.append(
            Balloon(
                x=self._width + 24,
                y=random.uniform(82, max(83, self._height - 58)),
                radius=random.uniform(14, 21),
                speed=random.uniform(100, 155),
                drift=random.uniform(-18, 18),
                color=random.choice(PASTEL_BALLOON_COLORS),
            )
        )

    def _lose_life(self):
        self.lives = max(0, self.lives - 1)
        if self.lives == 0:
            self.state = "game_over"
            self._held_keys.clear()
            self._cancel_frame()

    def draw(self):
        """Redraw the sky, sprites, HUD, and state overlay."""
        self._width = max(self.canvas.winfo_width(), 1)
        self._height = max(self.canvas.winfo_height(), 1)
        self.canvas.delete("all")
        self._draw_sky()
        self._draw_hud()
        for balloon in self.balloons:
            self._draw_balloon(balloon)
        for projectile in self.projectiles:
            self.canvas.create_rectangle(
                projectile.x - 4,
                projectile.y - 3,
                projectile.x + 4,
                projectile.y + 3,
                fill="#fff1a8",
                outline="#fffdf0",
            )
        if self.state != "game_over":
            self._draw_plane()
        if self.state == "paused":
            self._draw_overlay("PAUSED", "Take a breather, pilot.", "CONTINUE", self.continue_game)
        elif self.state == "game_over":
            self._draw_overlay("FLIGHT OVER", f"BALLOONS POPPED: {self.score}", "CONTINUE", self.start)

    def _draw_sky(self):
        for y in range(0, self._height, 4):
            amount = y / max(self._height, 1)
            red = round(193 + (229 - 193) * amount)
            green = round(229 + (244 - 229) * amount)
            blue = round(249 + (250 - 249) * amount)
            self.canvas.create_rectangle(
                0,
                y,
                self._width,
                y + 4,
                fill=f"#{red:02x}{green:02x}{blue:02x}",
                outline="",
            )

        sun_x = self._width - 92
        self.canvas.create_oval(sun_x - 27, 72, sun_x + 27, 126, fill="#fff0a8", outline="")
        cloud_rows = ((118, 0.75), (188, 1.0), (260, 0.8), (332, 1.0), (404, 0.7), (478, 0.9))
        cloud_period = self._width + 180
        for index, (base_y, scale) in enumerate(cloud_rows):
            speed = 0.65 + (index % 3) * 0.2
            offset = self._cloud_offset * speed + index * cloud_period / len(cloud_rows)
            cloud_x = (self._width + 100 - offset) % cloud_period - 60
            self._draw_cloud(cloud_x, base_y, scale)

    def _draw_cloud(self, x, y, scale):
        block = 12 * scale
        color = "#f8fcff"
        self.canvas.create_rectangle(x, y, x + 5 * block, y + block, fill=color, outline="")
        self.canvas.create_rectangle(x + block, y - block, x + 4 * block, y + block, fill=color, outline="")
        self.canvas.create_rectangle(x + 2 * block, y - 2 * block, x + 3 * block, y + block, fill=color, outline="")
        self.canvas.create_rectangle(x + block / 2, y + block, x + 4.5 * block, y + 1.5 * block, fill=color, outline="")

    def _draw_hud(self):
        self.canvas.create_text(
            24,
            20,
            anchor="nw",
            text=f"SCORE  {self.score:03d}",
            fill="#354356",
            font=("Courier New", 13, "bold"),
        )
        self.canvas.create_text(
            self._width - 24,
            20,
            anchor="ne",
            text=f"LIVES  {'♥ ' * self.lives}",
            fill="#d96787",
            font=("Courier New", 13, "bold"),
        )
        self.canvas.create_text(
            self._width / 2,
            24,
            text="WASD  FLY     SPACE  FIRE     ESC  PAUSE",
            fill="#637c91",
            font=("Courier New", 9, "bold"),
        )

    def _draw_balloon(self, balloon):
        x, y, radius = balloon.x, balloon.y, balloon.radius
        self.canvas.create_line(x, y + radius, x + 3, y + radius + 19, fill="#798a9a", width=2)
        self.canvas.create_polygon(
            x - 5, y + radius - 1,
            x + 5, y + radius - 1,
            x, y + radius + 7,
            fill=balloon.color,
            outline="",
        )
        self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=balloon.color, outline="#ffffff", width=2)
        self.canvas.create_oval(
            x - radius * 0.48,
            y - radius * 0.56,
            x - radius * 0.16,
            y - radius * 0.16,
            fill="#fff9f7",
            outline="",
        )

    def _draw_plane(self):
        x, y = self.plane_x, self.plane_y
        facing_x, facing_y = self.facing
        body = "#55a9d8"
        wing = "#397da9"
        cockpit = "#fff0a8"

        def block(center_x, center_y, width, height, color, outline=""):
            self.canvas.create_rectangle(
                center_x - width / 2,
                center_y - height / 2,
                center_x + width / 2,
                center_y + height / 2,
                fill=color,
                outline=outline,
            )

        if facing_x:
            block(x, y, 28, 10, body, "#ffffff")
            block(x, y, 12, 26, wing)
            block(x + facing_x * 17, y, 8, 6, body)
            block(x + facing_x * 5, y, 7, 6, cockpit)
            block(x - facing_x * 13, y, 6, 14, wing)
        else:
            block(x, y, 10, 28, body, "#ffffff")
            block(x, y, 26, 12, wing)
            block(x, y + facing_y * 17, 6, 8, body)
            block(x, y + facing_y * 5, 6, 7, cockpit)
            block(x, y - facing_y * 13, 14, 6, wing)

    def _draw_overlay(self, title, subtitle, primary_label, primary_action):
        self.canvas.create_rectangle(
            0,
            0,
            self._width,
            self._height,
            fill="#273d56",
            stipple="gray50",
            outline="",
        )
        center_x = self._width / 2
        center_y = self._height / 2
        panel_width = min(420, self._width - 36)
        panel_height = 258 if self.state == "game_over" else 238
        left = center_x - panel_width / 2
        top = center_y - panel_height / 2
        self.canvas.create_rectangle(left + 5, top + 6, left + panel_width + 5, top + panel_height + 6, fill="#52687b", outline="")
        self.canvas.create_rectangle(left, top, left + panel_width, top + panel_height, fill="#f7f5e9", outline="#ffffff", width=3)
        self.canvas.create_text(
            center_x,
            top + 48,
            text=title,
            fill="#354356",
            font=("Courier New", 20, "bold"),
        )
        self.canvas.create_text(
            center_x,
            top + 88,
            text=subtitle,
            fill="#637c91",
            font=("Courier New", 10, "bold"),
        )
        self._draw_overlay_button(center_x, top + 124, primary_label, primary_action, "#b9e3c9")
        self._draw_overlay_button(center_x, top + 180, "EXIT TO MAIN MENU", self.exit_to_menu, "#f2c5d4")

    def _draw_overlay_button(self, center_x, top, label, action, color):
        width, height = min(250, self._width - 72), 42
        tag = f"game-action-{label.lower().replace(' ', '-')}"
        self.canvas.create_rectangle(center_x - width / 2 + 3, top + 3, center_x + width / 2 + 3, top + height + 3, fill="#71808c", outline="")
        self.canvas.create_rectangle(
            center_x - width / 2,
            top,
            center_x + width / 2,
            top + height,
            fill=color,
            outline="#ffffff",
            width=2,
            tags=(tag,),
        )
        self.canvas.create_text(
            center_x,
            top + height / 2,
            text=label,
            fill="#354356",
            font=("Courier New", 10, "bold"),
            tags=(tag,),
        )
        self.canvas.tag_bind(tag, "<Button-1>", lambda _event: action())