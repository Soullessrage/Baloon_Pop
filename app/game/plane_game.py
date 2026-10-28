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
REGULAR_SPAWN_START = 1.5
REGULAR_SPAWN_MIN = 0.72
REGULAR_SPAWN_RAMP = 0.006
GAME_VERSION = "VER. 0.4"
BOSS_SCORE_THRESHOLD = 100
BOSS_INTERMISSION_DURATION = 60.0
POWER_UP_DROP_CHANCE = 0.12
POWER_UP_DROP_SPEED = 92
BOSS_TYPES = ("heavy", "fast", "battle")
SHOT_SPEED = 470
SHOT_SPREAD = math.pi / 6
STARTING_HEALTH = 3
SPECIAL_CHARGE_MAX = 100
SPECIAL_CHARGE_PER_BALLOON = 10


@dataclass(frozen=True)
class PowerUpDefinition:
    """Describe an effect available to the game and reference book."""

    key: str
    name: str
    description: str
    duration: float | None
    color: str


POWER_UP_CATALOG = (
    PowerUpDefinition("double_shot", "Double Shot", "Fire two shots at once.", 8.0, "#c5a3e8"),
    PowerUpDefinition("triple_shot", "Triple Shot", "Fire three shots at once.", 8.0, "#f3ad7b"),
    PowerUpDefinition("rapid_fire", "Faster Shooting", "Fire shots more frequently.", 8.0, "#f5d76e"),
    PowerUpDefinition("extra_heart", "Heart", "Permanently heal 1 health; can build an overheal shield.", None, "#82c9e8"),
    PowerUpDefinition("speed_boost", "Plane Speed Up", "Fly faster for a short time.", 8.0, "#a8dba8"),
)
POWER_UPS_BY_KEY = {power_up.key: power_up for power_up in POWER_UP_CATALOG}
TIMED_POWER_UPS = tuple(power_up for power_up in POWER_UP_CATALOG if power_up.duration is not None)


class PowerUpSystem:
    """Track refreshable timed effects and expose a simple collection API."""

    def __init__(self):
        self._remaining: dict[str, float] = {}
        self._permanent: set[str] = set()

    def collect(self, key: str) -> None:
        """Activate a catalogued effect; unknown keys fail explicitly."""
        if key in self._permanent:
            return
        duration = POWER_UPS_BY_KEY[key].duration
        if duration is None:
            raise ValueError(f"{key!r} is not a timed power-up.")
        self._remaining[key] = duration

    def update(self, delta: float) -> None:
        """Advance timers and expire effects whose duration has elapsed."""
        for key in tuple(self._remaining):
            if key in self._permanent:
                continue
            remaining = self._remaining[key] - max(0.0, delta)
            if remaining <= 0:
                del self._remaining[key]
            else:
                self._remaining[key] = remaining

    def is_active(self, key: str) -> bool:
        """Return whether an effect is currently active."""
        return key in self._permanent or self._remaining.get(key, 0) > 0

    def deactivate(self, key: str) -> None:
        """Expire an active effect immediately."""
        self._remaining.pop(key, None)
        self._permanent.discard(key)

    def remaining(self, key: str) -> float:
        """Return the seconds remaining for an effect."""
        if key in self._permanent:
            return math.inf
        return self._remaining.get(key, 0.0)

    def is_permanent(self, key: str) -> bool:
        """Return whether an effect is permanently enabled for this run."""
        return key in self._permanent

    def toggle_permanent(self, key: str) -> bool:
        """Toggle a catalogued effect permanently for the current run."""
        if key not in POWER_UPS_BY_KEY or POWER_UPS_BY_KEY[key].duration is None:
            raise KeyError(key)
        if key in self._permanent:
            self._permanent.remove(key)
            self._remaining.pop(key, None)
            return False
        self._permanent.add(key)
        self._remaining.pop(key, None)
        return True

    def clear(self) -> None:
        """Clear all active effects when starting a new flight."""
        self._remaining.clear()
        self._permanent.clear()


@dataclass
class Balloon:
    """A pastel balloon drifting in from the right edge."""

    x: float
    y: float
    radius: float
    speed: float
    drift: float
    color: str
    indestructible: bool = False
    hostile: bool = False
    health: int = 1
    homing: bool = False
    velocity_x: float | None = None
    velocity_y: float = 0.0
    remaining_life: float | None = None
    kind: str = "normal"
    wiggle_center_y: float | None = None
    wiggle_phase: float = 0.0
    wiggle_speed: float = 0.0
    wiggle_amplitude: float = 0.0


@dataclass
class PowerUpPickup:
    """A floating power-up dropped by a popped balloon."""

    key: str
    x: float
    y: float
    phase: float


@dataclass
class Projectile:
    """A small pixel shot travelling rightward across the screen."""

    x: float
    y: float
    velocity_x: float
    velocity_y: float


@dataclass
class BossBalloon:
    """A boss encounter with movement and attack timers."""

    x: float
    y: float
    radius: float
    health: int
    kind: str
    fight_time: float
    attack_in: float
    mode_change_in: float
    jump_in: float
    target_x: float
    target_y: float
    attack_mode: str
    entering: bool = False
    entrance_start_x: float = 0.0


class PlaneGame:
    """Manage game state, controls, collisions, and Canvas rendering."""

    def __init__(
        self,
        root: tk.Tk,
        canvas: tk.Canvas,
        on_exit,
        on_balloon_popped=None,
        on_boss_defeated=None,
        on_score_submitted=None,
    ):
        self.root = root
        self.canvas = canvas
        self.on_exit = on_exit
        self.on_balloon_popped = on_balloon_popped or (lambda: None)
        self.on_boss_defeated = on_boss_defeated or (lambda: None)
        self.on_score_submitted = on_score_submitted or (lambda _mode, _score, _initials: None)
        self.power_ups = PowerUpSystem()
        self.state = "stopped"
        self._after_id = None
        self._held_keys = set()
        self._last_frame = 0.0
        self._last_shot = 0.0
        self._spawn_in = 0.0
        self._elapsed = 0.0
        self._world_time = 0.0
        self._player_hit_cooldown = 0.0
        self._boss: BossBalloon | None = None
        self._boss_index = 0
        self._boss_campaign_started = False
        self._boss_intermission_remaining = 0.0
        self._game_mode = "boss_battle"
        self.developer_mode = False
        self._dialogue_text = ""
        self._dialogue_elapsed = 0.0
        self._dialogue_type_speed = 38.0
        self._dialogue_hold_duration = 1.2
        self._dialogue_fade_duration = 0.7
        self._dialogue_target_x = 0.0
        self._dialogue_target_y = 0.0
        self._dialogue_plane_start = (0.0, 0.0)
        self._storm_amount = 0.0
        self._score_entry_mode = ""
        self._score_initials = ""
        self.movement_scheme = "wasd"
        self._cloud_offset = 0.0
        self._width = 1
        self._height = 1

    def start(self, mode="boss_battle", developer_mode=False):
        """Start a fresh game and focus keyboard input on the game canvas."""
        self._cancel_frame()
        if mode not in {"boss_battle", "endless"}:
            raise ValueError("Game mode must be 'boss_battle' or 'endless'.")
        self.state = "story_intro"
        self._game_mode = mode
        self.developer_mode = bool(developer_mode)
        self.score = 0
        self.health = STARTING_HEALTH
        self.max_health = STARTING_HEALTH
        self.special_charge = 0
        self.plane_x = max(60, self.canvas.winfo_width() * 0.14)
        self.plane_y = self.canvas.winfo_height() * 0.5
        self.balloons: list[Balloon] = []
        self.pickups: list[PowerUpPickup] = []
        self.projectiles: list[Projectile] = []
        self._elapsed = 0.0
        self._world_time = 0.0
        self._player_hit_cooldown = 0.0
        self._boss = None
        self._boss_index = 0
        self._boss_campaign_started = mode == "endless"
        self._boss_intermission_remaining = 0.0
        self._storm_amount = 0.0
        self.power_ups.clear()
        self._held_keys.clear()
        self._spawn_in = 0.45
        self._last_shot = 0.0
        self.plane_x = -36
        self.plane_y = max(74, self.canvas.winfo_height() * 0.5)
        self._dialogue_target_x = max(60, self.canvas.winfo_width() * 0.14)
        self._dialogue_target_y = self.canvas.winfo_height() * 0.5
        self._begin_dialogue(
            "Hello Pilot, You have been tasked with destroying the 99 Balloons Group, "
            "an evil organization planning to spread balloons all over the world. "
            "You must defeat them!"
        )
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
        if self.state == "score_entry":
            self._handle_score_key(key)
            return True
        if key == "Escape" and self.state == "developer_menu":
            self.state = "paused"
            self.draw()
            return True
        normalized = self._normalize_key(key)
        if normalized is None:
            return False
        if normalized == "escape":
            self.handle_escape()
            return True
        if self.state != "playing":
            return normalized in {"w", "a", "s", "d", "space"}
        if normalized == "space":
            self._activate_special()
            return True
        if normalized in {"w", "a", "s", "d"}:
            self._held_keys.add(normalized)
            return True
        return False

    def handle_keyrelease(self, key):
        """Stop continuous movement when a movement key is released."""
        normalized = self._normalize_key(key)
        if normalized is None:
            return False
        self._held_keys.discard(normalized)
        return normalized in {"w", "a", "s", "d", "space"}

    def set_movement_scheme(self, scheme):
        """Set the active physical keys used for plane movement."""
        if scheme not in {"wasd", "arrows"}:
            raise ValueError("Movement scheme must be 'wasd' or 'arrows'.")
        self.movement_scheme = scheme
        self._held_keys.clear()

    def collect_power_up(self, key):
        """Apply an instant heal or activate a timed effect."""
        if key == "extra_heart":
            self.health += 1
            self.max_health += 1
        else:
            self.power_ups.collect(key)

    def _activate_special(self):
        if self.special_charge < SPECIAL_CHARGE_MAX:
            return False
        self.special_charge = 0
        self.balloons.clear()
        self.draw()
        return True

    def start_endless(self):
        """Continue a completed boss campaign in endless mode."""
        if self.state != "boss_complete":
            return
        self._game_mode = "endless"
        self.state = "playing"
        self._held_keys.clear()
        self._spawn_in = 0.0
        self._last_frame = time.perf_counter()
        self.canvas.focus_set()
        self._schedule_frame()

    def save_boss_score(self):
        """Ask the player to enter initials for the completed boss campaign."""
        if self.state == "boss_complete":
            self._begin_score_entry("boss_battle")

    def save_endless_score(self):
        """Ask the player to enter initials for an endless-mode record."""
        if self.state == "game_over" and self._game_mode == "endless":
            self._begin_score_entry("endless")

    def open_developer_menu(self):
        if self.developer_mode and self.state == "paused":
            self.state = "developer_menu"
            self.draw()

    def developer_add_score(self):
        if self.developer_mode and self.state == "developer_menu":
            self.score += 50
            self.draw()

    def developer_spawn_boss(self):
        if not self.developer_mode or self.state != "developer_menu":
            return
        if self._boss_index >= len(BOSS_TYPES):
            self._boss_index = 0
        self._game_mode = "boss_battle"
        self._boss_campaign_started = True
        self._boss_intermission_remaining = 0.0
        self._spawn_boss()
        self._schedule_frame()

    def developer_toggle_power_up(self, key):
        if self.developer_mode and self.state == "developer_menu":
            self.power_ups.toggle_permanent(key)
            self.draw()

    def _begin_score_entry(self, mode):
        self._score_entry_mode = mode
        self._score_initials = ""
        self.state = "score_entry"
        self.draw()

    def _handle_score_key(self, key):
        if key in {"BackSpace", "Backspace"}:
            self._score_initials = self._score_initials[:-1]
        elif key in {"Return", "KP_Enter"}:
            if len(self._score_initials) == 3:
                if self.on_score_submitted(self._score_entry_mode, self.score, self._score_initials):
                    self.state = "score_saved"
        elif len(key) == 1 and key.isalpha() and len(self._score_initials) < 3:
            self._score_initials += key.upper()
        self.draw()

    def _normalize_key(self, key):
        normalized = key.lower()
        if normalized in {"escape", "space"}:
            return normalized
        if self.movement_scheme == "arrows":
            return {"up": "w", "left": "a", "down": "s", "right": "d"}.get(normalized)
        return normalized if normalized in {"w", "a", "s", "d"} else None

    def handle_escape(self):
        """Pause the game when Escape is pressed during play."""
        if self.state == "playing":
            self.state = "paused"
            self._held_keys.clear()
            self._cancel_frame()
            self.draw()

    def continue_game(self):
        """Resume a paused game without resetting its score or lives."""
        if self.state not in {"paused", "developer_menu"}:
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
        if self.state in {"playing", "story_intro", "boss_entrance", "boss_victory"} and self._after_id is None:
            self._after_id = self.root.after(16, self._tick)

    def _begin_dialogue(self, text):
        self._dialogue_text = text
        self._dialogue_elapsed = 0.0
        self._dialogue_plane_start = (self.plane_x, self.plane_y)

    def _step_story_cinematic(self, delta):
        self._dialogue_elapsed += delta
        text_duration = len(self._dialogue_text) / self._dialogue_type_speed
        fade_start = text_duration + self._dialogue_hold_duration
        total_duration = fade_start + self._dialogue_fade_duration

        if self.state == "story_intro":
            self._move_plane_to_dialogue_target(self._dialogue_elapsed, 1.8)
        elif self.state == "boss_entrance":
            self._move_plane_to_dialogue_target(self._dialogue_elapsed, 2.2)
            boss = self._boss
            if boss is not None:
                self._move_boss_to_target(boss, self._dialogue_elapsed, 2.6)
                if boss.kind == "battle":
                    self._storm_amount = min(1.0, self._dialogue_elapsed / 2.4)
        elif self.state == "boss_victory":
            self._storm_amount = max(0.0, 1.0 - self._dialogue_elapsed / total_duration)

        if self._dialogue_elapsed < total_duration:
            return
        if self.state == "story_intro":
            self.state = "playing"
            self._spawn_in = 0.45
        elif self.state == "boss_entrance":
            boss = self._boss
            if boss is not None:
                boss.x = boss.target_x
                boss.y = boss.target_y
                boss.entering = False
                boss.attack_in = 1.2
            self.state = "playing"
            self._last_shot = 0.0
        else:
            self.state = "boss_complete"

    def _move_plane_to_dialogue_target(self, elapsed, duration):
        progress = min(1.0, elapsed / duration)
        eased = 1.0 - (1.0 - progress) ** 3
        start_x, start_y = self._dialogue_plane_start
        self.plane_x = start_x + (self._dialogue_target_x - start_x) * eased
        self.plane_y = start_y + (self._dialogue_target_y - start_y) * eased

    @staticmethod
    def _move_boss_to_target(boss, elapsed, duration):
        progress = min(1.0, elapsed / duration)
        eased = 1.0 - (1.0 - progress) ** 3
        boss.x = boss.entrance_start_x + (boss.target_x - boss.entrance_start_x) * eased

    def _cancel_frame(self):
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _tick(self):
        self._after_id = None
        if self.state not in {"playing", "story_intro", "boss_entrance", "boss_victory"}:
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
        self._world_time += delta
        self._player_hit_cooldown = max(0.0, self._player_hit_cooldown - delta)
        self._cloud_offset += 38 * delta
        if self.state in {"story_intro", "boss_entrance", "boss_victory"}:
            self._step_story_cinematic(delta)
            return
        self.power_ups.update(delta)

        horizontal = int("d" in self._held_keys) - int("a" in self._held_keys)
        vertical = int("s" in self._held_keys) - int("w" in self._held_keys)
        magnitude = math.hypot(horizontal, vertical)
        if magnitude:
            speed = PLAYER_SPEED * (1.45 if self.power_ups.is_active("speed_boost") else 1.0)
            self.plane_x += horizontal / magnitude * speed * delta
            self.plane_y += vertical / magnitude * speed * delta
        self.plane_x = max(26, min(self._width - 26, self.plane_x))
        self.plane_y = max(74, min(self._height - 42, self.plane_y))

        self._last_shot -= delta
        if self._last_shot <= 0:
            self._fire()
            self._last_shot = SHOT_INTERVAL * (0.45 if self.power_ups.is_active("rapid_fire") else 1.0)

        if self._boss is None:
            self._elapsed += delta
            if (
                self._game_mode == "boss_battle"
                and not self._boss_campaign_started
                and self.score >= BOSS_SCORE_THRESHOLD
            ):
                self._boss_campaign_started = True
                self._boss_index = 0
                self._spawn_boss()
            elif self._game_mode == "boss_battle" and self._boss_intermission_remaining > 0:
                if self._boss_intermission_remaining <= delta + 1e-9:
                    self._boss_intermission_remaining = 0.0
                    self._spawn_boss()
                else:
                    self._boss_intermission_remaining -= delta
            if self._boss is None:
                self._spawn_in -= delta
                if self._spawn_in <= 0:
                    self._spawn_balloon()
                    spawn_interval = max(
                        REGULAR_SPAWN_MIN,
                        REGULAR_SPAWN_START - self._elapsed * REGULAR_SPAWN_RAMP,
                    )
                    self._spawn_in = random.uniform(spawn_interval * 0.9, spawn_interval * 1.1)
        else:
            self._update_boss(delta)

        if self.state == "boss_entrance":
            self._step_story_cinematic(delta)
            return

        expired_balloons = []
        for balloon in self.balloons:
            if balloon.remaining_life is not None:
                balloon.remaining_life -= delta
                if balloon.remaining_life <= 0:
                    expired_balloons.append(balloon)
                    continue
            if balloon.homing:
                angle = math.atan2(self.plane_y - balloon.y, self.plane_x - balloon.x)
                balloon.velocity_x = math.cos(angle) * balloon.speed
                balloon.velocity_y = math.sin(angle) * balloon.speed
            if balloon.velocity_x is not None:
                balloon.x += balloon.velocity_x * delta
                balloon.y += balloon.velocity_y * delta
            elif balloon.kind == "wiggly":
                balloon.x -= balloon.speed * delta
                balloon.wiggle_phase += balloon.wiggle_speed * delta
                center_y = balloon.wiggle_center_y if balloon.wiggle_center_y is not None else balloon.y
                balloon.y = max(
                    56,
                    min(self._height - 44, center_y + math.sin(balloon.wiggle_phase) * balloon.wiggle_amplitude),
                )
            else:
                balloon.x -= balloon.speed * delta
                balloon.y = max(56, min(self._height - 44, balloon.y + balloon.drift * delta))
            if balloon.hostile and balloon.x - balloon.radius > self._width:
                expired_balloons.append(balloon)
        for balloon in expired_balloons:
            if balloon in self.balloons:
                self.balloons.remove(balloon)

        for pickup in self.pickups:
            pickup.x -= POWER_UP_DROP_SPEED * delta
            pickup.phase += delta * 4
            pickup.y = max(55, min(self._height - 55, pickup.y + math.sin(pickup.phase) * 12 * delta))
        self.pickups = [pickup for pickup in self.pickups if pickup.x > -24]

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
            if balloon.x + balloon.radius < 0:
                missed.append(balloon)
                if not balloon.hostile:
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
            if balloon.kind == "target":
                continue
            if math.hypot(balloon.x - self.plane_x, balloon.y - self.plane_y) < balloon.radius + player_radius:
                self.balloons.remove(balloon)
                self._take_hit()
                break

        if self.state != "playing":
            return

        if self._boss is not None and math.hypot(
            self._boss.x - self.plane_x, self._boss.y - self.plane_y
        ) < self._boss.radius + 14:
            self._take_hit()

        if self.state != "playing":
            return

        for pickup in tuple(self.pickups):
            if math.hypot(pickup.x - self.plane_x, pickup.y - self.plane_y) <= 29:
                self.collect_power_up(pickup.key)
                self.pickups.remove(pickup)

        for projectile in tuple(self.projectiles):
            hit_balloon = None
            for balloon in tuple(self.balloons):
                if not balloon.indestructible and math.hypot(
                    balloon.x - projectile.x, balloon.y - projectile.y
                ) <= balloon.radius + 4:
                    hit_balloon = balloon
                    break
            if hit_balloon is not None:
                self.projectiles.remove(projectile)
                hit_balloon.health -= 1
                if hit_balloon.health <= 0:
                    self.balloons.remove(hit_balloon)
                    self.special_charge = min(
                        SPECIAL_CHARGE_MAX,
                        self.special_charge + SPECIAL_CHARGE_PER_BALLOON,
                    )
                    if not hit_balloon.hostile:
                        self._record_balloon_popped(hit_balloon.x, hit_balloon.y)
                continue

            if self._boss is None:
                continue
            if math.hypot(self._boss.x - projectile.x, self._boss.y - projectile.y) <= self._boss.radius:
                self._boss.health -= 1
                self.projectiles.remove(projectile)
                if self._boss.health <= 0:
                    self._defeat_boss()
                    return

    def _record_balloon_popped(self, x, y):
        self.score += 1
        self.on_balloon_popped()
        if random.random() < POWER_UP_DROP_CHANCE:
            key = random.choice(tuple(POWER_UPS_BY_KEY))
            self.pickups.append(PowerUpPickup(key, x, y, random.uniform(0, math.tau)))

    def _take_hit(self):
        if self._player_hit_cooldown > 0:
            return
        self._lose_life()
        self._player_hit_cooldown = 1.0

    def _spawn_boss(self):
        kind = BOSS_TYPES[self._boss_index]
        health = {"heavy": 12, "fast": 14, "battle": 45}[kind]
        target_x = self._width * 0.74
        boss_y = self._height * 0.5
        plane_target_x = max(60, self._width * 0.14)
        self.balloons.clear()
        self.pickups.clear()
        self.projectiles.clear()
        self._held_keys.clear()
        self._dialogue_target_x = plane_target_x
        self._dialogue_target_y = self._height * 0.5
        boss_dialogue = {
            "heavy": "Oh no! That must be a boss! Seems pretty strong!",
            "fast": "Another boss! It's quick, so stay sharp and keep moving!",
            "battle": "It's the Battle Balloon! It's using every trick they've got. Take it down!",
        }
        self._boss = BossBalloon(
            x=self._width + 90,
            y=boss_y,
            radius=76 if kind == "battle" else 66,
            health=health,
            kind=kind,
            fight_time=0.0,
            attack_in=1.2,
            mode_change_in=2.8,
            jump_in=0.0,
            target_x=target_x,
            target_y=boss_y,
            attack_mode="heavy",
            entering=True,
            entrance_start_x=self._width + 90,
        )
        self._begin_dialogue(boss_dialogue[kind])
        self.state = "boss_entrance"

    def _update_boss(self, delta):
        boss = self._boss
        if boss is None:
            return
        boss.fight_time += delta
        if boss.entering:
            return
        if boss.kind in {"fast", "battle"}:
            boss.jump_in -= delta
            if boss.jump_in <= 0:
                boss.target_x = random.uniform(self._width * 0.52, self._width * 0.86)
                boss.target_y = random.uniform(max(100, boss.radius + 20), max(boss.radius + 21, self._height - 130))
                boss.jump_in = random.uniform(0.45, 0.8)
            angle = math.atan2(boss.target_y - boss.y, boss.target_x - boss.x)
            jump_speed = 420 if boss.kind == "fast" else 300
            distance = jump_speed * delta
            if math.hypot(boss.target_x - boss.x, boss.target_y - boss.y) <= distance:
                boss.x, boss.y = boss.target_x, boss.target_y
            else:
                boss.x += math.cos(angle) * distance
                boss.y += math.sin(angle) * distance
        else:
            bob_range = min(90, self._height * 0.18)
            boss.y = max(
                boss.radius + 80,
                min(self._height - boss.radius - 36, self._height * 0.5 + math.sin(self._world_time * 1.0) * bob_range),
            )

        if boss.kind == "battle":
            boss.mode_change_in -= delta
        if boss.kind == "battle" and boss.mode_change_in <= 0:
            boss.attack_mode = random.choice(("heavy", "fast"))
            boss.mode_change_in = random.uniform(2.2, 3.4)
        boss.attack_in -= delta
        if boss.attack_in <= 0:
            if boss.kind == "heavy" or (boss.kind == "battle" and boss.attack_mode == "heavy"):
                self._spawn_heavy_attack(boss)
                boss.attack_in = 1.15
            else:
                self._spawn_fast_attack(boss)
                boss.attack_in = 2.4

    def _spawn_heavy_attack(self, boss):
        for offset in (-15, 15):
            target_x = self.plane_x
            target_y = self.plane_y + offset
            angle = math.atan2(target_y - boss.y, target_x - boss.x)
            speed = 190
            self.balloons.append(
                Balloon(
                    x=boss.x - boss.radius,
                    y=boss.y + offset,
                    radius=25,
                    speed=speed,
                    drift=0,
                    color="#e57b8f",
                    hostile=True,
                    health=2,
                    velocity_x=math.cos(angle) * speed,
                    velocity_y=math.sin(angle) * speed,
                    remaining_life=8,
                )
            )

    def _spawn_fast_attack(self, boss):
        for index in range(3):
            self.balloons.append(
                Balloon(
                    x=boss.x - 18 * index,
                    y=boss.y + (index - 1) * 22,
                    radius=18,
                    speed=130 + index * 15,
                    drift=0,
                    color=PASTEL_BALLOON_COLORS[index],
                    hostile=True,
                    homing=True,
                    remaining_life=7,
                )
            )

    def _defeat_boss(self):
        boss = self._boss
        if boss is None:
            return
        base_score = 1000 if boss.kind == "battle" else 100
        score_loss_per_second = 10 if boss.kind == "battle" else 1
        bonus = max(10, base_score - int(boss.fight_time * score_loss_per_second))
        self.score += bonus
        self._boss = None
        self.on_boss_defeated()
        self.balloons = [balloon for balloon in self.balloons if not balloon.hostile]
        if boss.kind == "battle":
            self._held_keys.clear()
            self._begin_dialogue("You did it, Pilot! The 99 Balloons Group is finished. Excellent work!")
            self.state = "boss_victory"
        else:
            self._boss_index += 1
            self._boss_intermission_remaining = BOSS_INTERMISSION_DURATION

    def _fire(self):
        if self.power_ups.is_active("triple_shot"):
            shot_angles = (0, -SHOT_SPREAD, SHOT_SPREAD)
        elif self.power_ups.is_active("double_shot"):
            shot_angles = (-SHOT_SPREAD, SHOT_SPREAD)
        else:
            shot_angles = (0,)
        for angle in shot_angles:
            self.projectiles.append(
                Projectile(
                    self.plane_x + 21,
                    self.plane_y,
                    SHOT_SPEED * math.cos(angle),
                    SHOT_SPEED * math.sin(angle),
                )
            )

    def _spawn_balloon(self):
        kind = random.choices(
            ("normal", "metal", "wiggly", "target"),
            weights=(0.50, 0.18, 0.20, 0.12),
            k=1,
        )[0]
        radius = random.uniform(14, 21)
        y = random.uniform(82, max(83, self._height - 58))
        self.balloons.append(
            Balloon(
                x=self._width + 24,
                y=y,
                radius=radius,
                speed=random.uniform(100, 155),
                drift=random.uniform(-18, 18),
                color="#778a99" if kind == "metal" else random.choice(PASTEL_BALLOON_COLORS),
                health=3 if kind == "metal" else 1,
                kind=kind,
                wiggle_center_y=y if kind == "wiggly" else None,
                wiggle_phase=random.uniform(0, math.tau),
                wiggle_speed=random.uniform(1.3, 2.4),
                wiggle_amplitude=random.uniform(14, 30),
            )
        )

    def _lose_life(self):
        self.health = max(0, self.health - 1)
        if self.health == 0:
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
        for pickup in self.pickups:
            self._draw_power_up_pickup(pickup)
        for balloon in self.balloons:
            self._draw_balloon(balloon)
        if self._boss is not None:
            self._draw_boss()
        for projectile in self.projectiles:
            self.canvas.create_rectangle(
                projectile.x - 4,
                projectile.y - 3,
                projectile.x + 4,
                projectile.y + 3,
                fill="#22252a",
                outline="#050607",
            )
        if self.state not in {"game_over", "score_entry", "score_saved"}:
            self._draw_plane()
        if self.state in {"story_intro", "boss_entrance", "boss_victory"}:
            self._draw_dialogue_box()
        if self.state == "paused":
            buttons = [("CONTINUE", self.continue_game, "#b9e3c9")]
            if self.developer_mode:
                buttons.append(("DEVELOPER TOOLS", self.open_developer_menu, "#d4e8fa"))
            buttons.append(("EXIT TO MAIN MENU", self.exit_to_menu, "#f2c5d4"))
            self._draw_overlay("PAUSED", "Take a breather, pilot.", buttons)
        elif self.state == "developer_menu":
            self._draw_developer_menu()
        elif self.state == "game_over":
            buttons = [("FLY AGAIN", lambda: self.start(self._game_mode), "#b9e3c9")]
            if self._game_mode == "endless":
                buttons.append(("SAVE HIGH SCORE", self.save_endless_score, "#c5d5f2"))
            buttons.append(("EXIT TO MAIN MENU", self.exit_to_menu, "#f2c5d4"))
            self._draw_overlay("FLIGHT OVER", f"SCORE: {self.score}", buttons)
        elif self.state == "boss_complete":
            self._draw_overlay(
                "BATTLE BALLOON DEFEATED",
                f"CAMPAIGN SCORE: {self.score}",
                [("CONTINUE IN ENDLESS", self.start_endless, "#b9e3c9"),
                 ("SAVE BOSS SCORE", self.save_boss_score, "#c5d5f2"),
                 ("EXIT TO MAIN MENU", self.exit_to_menu, "#f2c5d4")],
            )
        elif self.state == "score_entry":
            self._draw_overlay(
                "NEW HIGH SCORE",
                f"TYPE 3 INITIALS: {self._score_initials or '___'}   (ENTER TO SAVE)",
                [("CANCEL", self._cancel_score_entry, "#f2c5d4")],
            )
        elif self.state == "score_saved":
            self._draw_overlay(
                "SCORE SAVED",
                f"{self._score_initials}  {self.score}",
                [("EXIT TO MAIN MENU", self.exit_to_menu, "#b9e3c9")],
            )

    def _draw_developer_menu(self):
        self.canvas.create_rectangle(0, 0, self._width, self._height, fill="#273d56", stipple="gray50", outline="")
        center_x, center_y = self._width / 2, self._height / 2
        panel_width, panel_height = min(650, self._width - 36), min(474, self._height - 32)
        left, top = center_x - panel_width / 2, center_y - panel_height / 2
        self.canvas.create_rectangle(left, top, left + panel_width, top + panel_height,
                                     fill="#f7f5e9", outline="#ffffff", width=3)
        self.canvas.create_text(center_x, top + 34, text="DEVELOPER TOOLS", fill="#354356",
                                font=("Courier New", 17, "bold"))
        self.canvas.create_text(center_x, top + 62, text=f"RUN SCORE: {self.score}",
                                fill="#637c91", font=("Courier New", 10, "bold"))
        button_width = min(270, (panel_width - 50) / 2)
        first_y = top + 88
        options = [
            ("ADD 50 SCORE", self.developer_add_score, "#b9e3c9"),
            ("SPAWN NEXT BOSS", self.developer_spawn_boss, "#f2c5d4"),
        ]
        options.extend(
            (
                f"{'ON' if self.power_ups.is_permanent(power_up.key) else 'OFF'}  {power_up.name.upper()}",
                lambda key=power_up.key: self.developer_toggle_power_up(key),
                power_up.color,
            )
            for power_up in TIMED_POWER_UPS
        )
        options.extend((
            ("RESUME GAME", self.continue_game, "#d4e8fa"),
            ("BACK TO PAUSE", self._return_to_pause, "#e4d8f5"),
        ))
        for index, (label, action, color) in enumerate(options):
            row, column = divmod(index, 2)
            x = center_x + (column * 2 - 1) * (button_width / 2 + 12)
            button_tag = f"dev-action-{index}"
            self._draw_overlay_button(x, first_y + row * 50, label, action, color, button_tag, button_width, 38)

    def _return_to_pause(self):
        self.state = "paused"
        self.draw()

    def _cancel_score_entry(self):
        self.state = "game_over" if self._score_entry_mode == "endless" else "boss_complete"
        self.draw()

    def _draw_sky(self):
        for y in range(0, self._height, 4):
            amount = y / max(self._height, 1)
            red = round(193 + (229 - 193) * amount)
            green = round(229 + (244 - 229) * amount)
            blue = round(249 + (250 - 249) * amount)
            sky_color = f"#{red:02x}{green:02x}{blue:02x}"
            sky_color = self._blend_color(sky_color, "#59636f", self._storm_amount)
            self.canvas.create_rectangle(
                0,
                y,
                self._width,
                y + 4,
                fill=sky_color,
                outline="",
            )

        sun_x = self._width - 92
        sun_color = self._blend_color("#fff0a8", "#818991", self._storm_amount)
        self.canvas.create_oval(sun_x - 27, 72, sun_x + 27, 126, fill=sun_color, outline="")
        cloud_rows = ((118, 0.75), (188, 1.0), (260, 0.8), (332, 1.0), (404, 0.7), (478, 0.9))
        cloud_period = self._width + 180
        for index, (base_y, scale) in enumerate(cloud_rows):
            speed = 0.65 + (index % 3) * 0.2
            offset = self._cloud_offset * speed + index * cloud_period / len(cloud_rows)
            cloud_x = (self._width + 100 - offset) % cloud_period - 60
            cloud_color = self._blend_color("#f8fcff", "#89939d", self._storm_amount)
            self._draw_cloud(cloud_x, base_y, scale, cloud_color)
        if self._storm_amount > 0.05:
            rain_color = self._blend_color("#d5e1eb", "#77838f", self._storm_amount)
            rain_offset = (self._world_time * 210) % 58
            for index in range(20):
                x = (index * 71 + rain_offset) % max(self._width, 1)
                y = (index * 47 + rain_offset * 1.8) % max(self._height, 1)
                self.canvas.create_line(x, y, x - 9, y + 18, fill=rain_color, width=1)

    @staticmethod
    def _blend_color(start, end, amount):
        amount = max(0.0, min(1.0, amount))
        start_rgb = tuple(int(start[index:index + 2], 16) for index in (1, 3, 5))
        end_rgb = tuple(int(end[index:index + 2], 16) for index in (1, 3, 5))
        blended = tuple(round(first + (last - first) * amount) for first, last in zip(start_rgb, end_rgb))
        return f"#{blended[0]:02x}{blended[1]:02x}{blended[2]:02x}"

    def _draw_cloud(self, x, y, scale, color="#f8fcff"):
        block = 12 * scale
        self.canvas.create_rectangle(x, y, x + 5 * block, y + block, fill=color, outline="")
        self.canvas.create_rectangle(x + block, y - block, x + 4 * block, y + block, fill=color, outline="")
        self.canvas.create_rectangle(x + 2 * block, y - 2 * block, x + 3 * block, y + block, fill=color, outline="")
        self.canvas.create_rectangle(x + block / 2, y + block, x + 4.5 * block, y + 1.5 * block, fill=color, outline="")

    def _draw_dialogue_box(self):
        text_duration = len(self._dialogue_text) / self._dialogue_type_speed
        fade_start = text_duration + self._dialogue_hold_duration
        fade = max(0.0, min(1.0, (self._dialogue_elapsed - fade_start) / self._dialogue_fade_duration))
        panel_color = self._blend_color("#26384a", "#f7f5e9", fade)
        panel_edge = self._blend_color("#f7f5e9", "#26384a", fade)
        text_color = self._blend_color("#f7f5e9", "#26384a", fade)
        silhouette = self._blend_color("#111c29", "#f7f5e9", fade)
        margin = 22
        panel_height = min(144, self._height * 0.28)
        top = self._height - panel_height - margin
        left = margin
        right = self._width - margin
        self.canvas.create_rectangle(left + 4, top + 5, right + 4, self._height - margin + 5,
                                     fill="#26384a", outline="")
        self.canvas.create_rectangle(left, top, right, self._height - margin, fill=panel_color,
                                     outline=panel_edge, width=2)

        card_left = left + 12
        card_right = left + 157
        card_top = top + 12
        self.canvas.create_rectangle(card_left, card_top, card_right, self._height - margin - 12,
                                     fill=self._blend_color("#34495d", "#e4e0d2", fade),
                                     outline=self._blend_color("#71869a", "#d0cbbd", fade))
        center = (card_left + card_right) / 2
        figure_y = card_top + (panel_height - 48) * 0.48
        self.canvas.create_rectangle(center - 25, figure_y - 27, center + 25, figure_y + 10,
                                     fill=silhouette, outline="")
        self.canvas.create_rectangle(center - 12, figure_y - 48, center + 12, figure_y - 29,
                                     fill=silhouette, outline="")
        self.canvas.create_polygon(
            center - 24, figure_y + 10, center + 24, figure_y + 10,
            center + 31, figure_y + 37, center - 31, figure_y + 37,
            fill=silhouette, outline="",
        )
        self.canvas.create_text(center, self._height - margin - 25, text="GENERAL B.",
                                fill=text_color, font=("Courier New", 10, "bold"))
        visible_characters = min(len(self._dialogue_text), int(self._dialogue_elapsed * self._dialogue_type_speed))
        shown_text = self._dialogue_text[:visible_characters]
        text_left = card_right + 26
        self.canvas.create_text(
            text_left,
            top + panel_height / 2,
            anchor="w",
            width=max(80, right - text_left - 16),
            text=shown_text,
            fill=text_color,
            font=("Courier New", 11, "bold"),
        )

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
            24,
            43,
            anchor="nw",
            text=f"HEALTH  {self.health}/{self.max_health}"
                 + (f"  SHIELD +{self.health - STARTING_HEALTH}" if self.health > STARTING_HEALTH else ""),
            fill="#354356",
            font=("Courier New", 9, "bold"),
        )
        health_width = max(0, min(180, self._width - 48))
        health_top = 59
        self.canvas.create_rectangle(
            24, health_top, 24 + health_width, health_top + 10,
            fill="#e5e9ec", outline="#ffffff",
        )
        health_fill = health_width * self.health / self.max_health
        base_fill = health_width * min(self.health, STARTING_HEALTH) / self.max_health
        if base_fill > 0:
            self.canvas.create_rectangle(
                24, health_top, 24 + base_fill, health_top + 10,
                fill="#7cc99a", outline="",
            )
        if health_fill > base_fill:
            self.canvas.create_rectangle(
                24 + base_fill, health_top, 24 + health_fill, health_top + 10,
                fill="#5baee8", outline="",
            )
        self.canvas.create_text(
            24,
            77,
            anchor="nw",
            text=f"SPECIAL  {self.special_charge}% - SPACE"
                 + ("  READY!" if self.special_charge >= SPECIAL_CHARGE_MAX else ""),
            fill="#354356",
            font=("Courier New", 9, "bold"),
        )
        special_width = max(0, min(180, self._width - 48))
        special_top = 93
        self.canvas.create_rectangle(
            24, special_top,
            24 + special_width, special_top + 10,
            fill="#e5e9ec", outline="#ffffff",
        )
        if self.special_charge > 0:
            self.canvas.create_rectangle(
                24, special_top,
                24 + special_width * self.special_charge / SPECIAL_CHARGE_MAX,
                special_top + 10,
                fill="#438fe0", outline="",
            )
        active_effects = [
            f"{power_up.name.upper()} "
            f"{'∞' if self.power_ups.is_permanent(power_up.key) else f'{self.power_ups.remaining(power_up.key):.0f}s'}"
            for power_up in TIMED_POWER_UPS
            if self.power_ups.is_active(power_up.key)
        ]
        if active_effects:
            self.canvas.create_text(
                self._width / 2,
                self._height - 17,
                anchor="s",
                text="  |  ".join(active_effects),
                fill="#354356",
                font=("Courier New", 9, "bold"),
            )
        if self._game_mode == "boss_battle" and self._boss is None and self._boss_intermission_remaining > 0:
            next_boss = BOSS_TYPES[self._boss_index].upper()
            self.canvas.create_text(
                self._width / 2, 20, anchor="n",
                text=f"{next_boss} IN {math.ceil(self._boss_intermission_remaining)}s",
                fill="#354356", font=("Courier New", 10, "bold"),
            )
        self.canvas.create_text(
            self._width - 14,
            self._height - 14,
            anchor="se",
            text=GAME_VERSION,
            fill="#607386",
            font=("Courier New", 8),
        )

    def _draw_boss(self):
        boss = self._boss
        if boss is None:
            return
        boss_color = {"heavy": "#f28fad", "fast": "#82c9e8", "battle": "#9e78c4"}[boss.kind]
        boss_balloon = Balloon(boss.x, boss.y, boss.radius, 0, 0, boss_color)
        self._draw_balloon(boss_balloon)
        boss_name = {"heavy": "HEAVY", "fast": "FAST", "battle": "BATTLE"}[boss.kind]
        self.canvas.create_text(boss.x, boss.y, text=boss_name, fill="#ffffff", font=("Courier New", 12, "bold"))

        crown_y = boss.y - boss.radius - 32 + math.sin(self._world_time * 3) * 4
        self.canvas.create_polygon(
            boss.x - 27, crown_y + 18,
            boss.x - 24, crown_y,
            boss.x - 9, crown_y + 10,
            boss.x, crown_y - 5,
            boss.x + 9, crown_y + 10,
            boss.x + 24, crown_y,
            boss.x + 27, crown_y + 18,
            fill="#f4cf5d",
            outline="#fff2b3",
            width=2,
        )
        self.canvas.create_rectangle(
            boss.x - 27,
            crown_y + 18,
            boss.x + 27,
            crown_y + 25,
            fill="#e6b839",
            outline="#fff2b3",
        )

        bar_width = 126
        bar_left = boss.x - bar_width / 2
        bar_top = max(60, boss.y - boss.radius - 35)
        self.canvas.create_text(
            boss.x,
            bar_top - 11,
            text=f"{boss_name} BALLOON  {boss.health}",
            fill="#354356",
            font=("Courier New", 8, "bold"),
        )
        self.canvas.create_rectangle(bar_left, bar_top, bar_left + bar_width, bar_top + 7, fill="#e3d7f2", outline="")
        self.canvas.create_rectangle(
            bar_left,
            bar_top,
            bar_left + bar_width * boss.health / {"heavy": 12, "fast": 14, "battle": 45}[boss.kind],
            bar_top + 7,
            fill="#a67dc9",
            outline="",
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
        if balloon.kind == "wiggly":
            self.canvas.create_polygon(
                x - radius * 0.62, y - radius * 0.5,
                x - radius * 0.88, y - radius * 1.42,
                x - radius * 0.17, y - radius * 0.88,
                fill=balloon.color, outline="#ffffff", width=2,
            )
            self.canvas.create_polygon(
                x + radius * 0.62, y - radius * 0.5,
                x + radius * 0.88, y - radius * 1.42,
                x + radius * 0.17, y - radius * 0.88,
                fill=balloon.color, outline="#ffffff", width=2,
            )
            self.canvas.create_oval(
                x - radius * 0.78, y - radius * 0.85,
                x + radius * 0.78, y + radius * 0.85,
                fill=balloon.color, outline="#ffffff", width=2,
            )
            self.canvas.create_oval(
                x - radius * 0.38, y + radius * 0.15,
                x + radius * 0.38, y + radius * 0.58,
                fill="#fff2df", outline="",
            )
            self.canvas.create_oval(
                x - radius * 0.34, y - radius * 0.24,
                x - radius * 0.19, y - radius * 0.09,
                fill="#354356", outline="",
            )
            self.canvas.create_oval(
                x + radius * 0.19, y - radius * 0.24,
                x + radius * 0.34, y - radius * 0.09,
                fill="#354356", outline="",
            )
            self.canvas.create_oval(
                x - radius * 0.09, y + radius * 0.27,
                x + radius * 0.09, y + radius * 0.43,
                fill="#e9879d", outline="",
            )
        else:
            self.canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill=balloon.color, outline="#ffffff", width=2,
            )
        self.canvas.create_oval(
            x - radius * 0.48,
            y - radius * 0.56,
            x - radius * 0.16,
            y - radius * 0.16,
            fill="#fff9f7",
            outline="",
        )
        if balloon.kind == "metal":
            self.canvas.create_polygon(
                x - radius * 0.78, y - radius * 0.12,
                x - radius * 0.58, y - radius * 0.62,
                x + radius * 0.58, y - radius * 0.62,
                x + radius * 0.78, y - radius * 0.12,
                x + radius * 0.58, y + radius * 0.04,
                x - radius * 0.58, y + radius * 0.04,
                fill="#bac5ce", outline="#eef3f6", width=1,
            )
            self.canvas.create_polygon(
                x - radius * 0.72, y + radius * 0.15,
                x - radius * 0.52, y + radius * 0.57,
                x + radius * 0.52, y + radius * 0.57,
                x + radius * 0.72, y + radius * 0.15,
                fill="#8f9eaa", outline="#dbe3e9", width=1,
            )
            for rivet_x, rivet_y in (
                (x - radius * 0.48, y - radius * 0.38),
                (x + radius * 0.48, y - radius * 0.38),
                (x - radius * 0.42, y + radius * 0.34),
                (x + radius * 0.42, y + radius * 0.34),
            ):
                self.canvas.create_oval(
                    rivet_x - 1.5, rivet_y - 1.5, rivet_x + 1.5, rivet_y + 1.5,
                    fill="#f3f6f8", outline="#52616d",
                )
        elif balloon.kind == "target":
            for scale, color in ((0.72, "#ffffff"), (0.48, "#e65d64"), (0.24, "#ffffff")):
                self.canvas.create_oval(
                    x - radius * scale, y - radius * scale,
                    x + radius * scale, y + radius * scale,
                    outline=color, width=2,
                )
            self.canvas.create_oval(
                x - radius * 0.11, y - radius * 0.11,
                x + radius * 0.11, y + radius * 0.11,
                fill="#e65d64", outline="",
            )
        if balloon.indestructible:
            self.canvas.create_text(x, y, text="X", fill="#ffffff", font=("Courier New", 11, "bold"))
        elif balloon.kind == "metal":
            self.canvas.create_text(x, y, text=str(balloon.health), fill="#ffffff", font=("Courier New", 9, "bold"))
        elif balloon.hostile and balloon.health > 1:
            self.canvas.create_text(x, y, text=str(balloon.health), fill="#ffffff", font=("Courier New", 9, "bold"))

    def _draw_power_up_pickup(self, pickup):
        power_up = POWER_UPS_BY_KEY[pickup.key]
        self.canvas.create_oval(
            pickup.x - 15, pickup.y - 15, pickup.x + 15, pickup.y + 15,
            fill=power_up.color, outline="#ffffff", width=2,
        )
        icon = {"double_shot": "2x", "triple_shot": "3x", "rapid_fire": "R",
                "extra_heart": "♥", "speed_boost": "S"}[pickup.key]
        self.canvas.create_text(
            pickup.x, pickup.y, text=icon,
            fill="#ffffff" if pickup.key != "extra_heart" else "#1976b9",
            font=("Courier New", 9, "bold"),
        )

    def _draw_plane(self):
        x, y = self.plane_x, self.plane_y
        body = "#55a9d8"
        wing = "#8c6eb5" if self.power_ups.is_active("speed_boost") else "#397da9"
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

        block(x, y, 28, 10, body, "#ffffff")
        block(x, y, 12, 26, wing)
        block(x + 17, y, 8, 6, body)
        block(x + 5, y, 7, 6, cockpit)
        block(x - 13, y, 6, 14, wing)
        if self.power_ups.is_active("triple_shot") or self.power_ups.is_active("double_shot"):
            offsets = (-14, 0, 14) if self.power_ups.is_active("triple_shot") else (-8, 8)
            for offset in offsets:
                block(x + 22, y + offset, 5, 4, "#f3ad7b")
        if self.power_ups.is_active("rapid_fire"):
            block(x - 21, y, 5, 8, "#f5d76e")

    def _draw_overlay(self, title, subtitle, buttons):
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
        panel_height = 150 + 52 * len(buttons)
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
        first_button_y = top + 112
        for index, (label, action, color) in enumerate(buttons):
            self._draw_overlay_button(center_x, first_button_y + index * 52, label, action, color)

    def _draw_overlay_button(self, center_x, top, label, action, color, tag=None, width=None, height=42):
        width = width or min(250, self._width - 72)
        tag = tag or f"game-action-{label.lower().replace(' ', '-')}"
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