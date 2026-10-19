"""Main menu window and its interactive canvas controls."""

from __future__ import annotations

import queue
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox
import webbrowser
from pathlib import Path

from game.plane_game import POWER_UP_CATALOG, PlaneGame
from services.updater import GitHubUpdater
from ui.contact_window import EMAIL, GITHUB_URL, WEBSITE_URL


WINDOW_WIDTH = 900
WINDOW_HEIGHT = 600
BUY_ME_A_COFFEE_URL = "https://www.buymeacoffee.com/YOURNAME"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ENTRY = Path(__file__).resolve().parents[1] / "main.py"


def _hex_rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def _blend(start: str, end: str, amount: float) -> str:
    left = _hex_rgb(start)
    right = _hex_rgb(end)
    channels = [round(a + (b - a) * amount) for a, b in zip(left, right)]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


class MainWindow:
    """Own the app's canvas screens, game, and background updater."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Balloon Pop")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(720, 540)
        self.root.configure(bg="#f8dce8")

        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self._update_queue: queue.Queue[str | tuple[bool, str]] = queue.Queue()
        self._update_running = False
        self._update_status = ""
        self._screen = "menu"
        self._transition_id = None
        self._settings = {"music": True, "pixel_effects": True}
        self._stats = StatsStore()
        self._game = PlaneGame(
            self.root,
            self.canvas,
            self._return_to_menu,
            self._stats.record_balloon_popped,
            self._stats.record_boss_defeated,
            self._record_score,
        )

        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.root.bind("<KeyPress>", self._on_key_press)
        self.root.bind("<KeyRelease>", self._on_key_release)
        self.root.after(100, self._poll_update_result)

    def run(self):
        """Enter Tk's event loop."""
        self.root.mainloop()

    def _draw_menu(self, _event=None):
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        self.canvas.delete("all")

        stops = [(0.0, "#f8dce8"), (0.52, "#dceafa"), (1.0, "#d6eee1")]
        strip_height = 3
        for y in range(0, height, strip_height):
            progress = y / max(height - 1, 1)
            for index in range(len(stops) - 1):
                if stops[index][0] <= progress <= stops[index + 1][0]:
                    start_position, start_color = stops[index]
                    end_position, end_color = stops[index + 1]
                    segment_progress = (progress - start_position) / (end_position - start_position)
                    color = _blend(start_color, end_color, segment_progress)
                    break
            self.canvas.create_rectangle(0, y, width, y + strip_height, fill=color, outline="")

        title, subtitle = {
            "menu": ("BALLOON POP", "A PLANE GAME"),
            "settings": ("SETTINGS", "CUSTOMIZE YOUR FLIGHT"),
            "controls": ("CONTROLS", "CHOOSE HOW TO FLY"),
            "guide": ("FLIGHT GUIDE", "POWER-UPS AND BOSSES"),
            "scores": ("ARCADE RECORDS", "BEST BOSS AND ENDLESS RUNS"),
            "contact": ("SAY HELLO", "CONTACT AND PROJECT LINKS"),
        }.get(self._screen, ("BALLOON POP", "A PLANE GAME"))
        center_x = width / 2
        self.canvas.create_text(center_x, max(36, height * 0.10), text=title, fill="#354356",
                                font=("Courier New", 23, "bold"))
        self.canvas.create_text(center_x, max(65, height * 0.16), text=subtitle, fill="#607386",
                                font=("Courier New", 9, "bold"))
        if self._screen == "menu":
            self.canvas.create_text(
                center_x, max(88, height * 0.22),
                text="SHIFT + CLICK BOSS CAMPAIGN FOR DEVELOPER MODE",
                fill="#607386", font=("Courier New", 8, "bold"),
            )

        if self._screen == "menu":
            self._draw_home_page(width, height)
        elif self._screen == "settings":
            self._draw_settings_page(width, height)
        elif self._screen == "controls":
            self._draw_controls_page(width, height)
        elif self._screen == "guide":
            self._draw_guide_page(width, height)
        elif self._screen == "scores":
            self._draw_scores_page(width, height)
        elif self._screen == "contact":
            self._draw_contact_page(width, height)

    def _draw_home_page(self, width, height):
        center_x = width / 2
        button_width = min(275, (width - 72) / 2)
        button_height = 48
        left_x, right_x = center_x - button_width / 2 - 10, center_x + button_width / 2 + 10
        items = (
            (left_x, "BOSS CAMPAIGN", "#d1edda", self._start_boss_campaign),
            (right_x, "SETTINGS", "#d4e8fa", self._open_settings),
            (left_x, "CONTROLS", "#e4d8f5", self._open_controls),
            (right_x, "GUIDE & RECORDS", "#f6d9e8", self._open_book),
            (left_x, "CONTACT", "#f7edbe", self._open_contact),
            (right_x, "BUY ME A COFFEE", "#f7edbe", self._buy_coffee),
            (center_x, "UPDATE", "#f5c99b", self._update_app),
        )
        first_y = max(height * 0.29, 165)
        for index, (x, label, color, action) in enumerate(items):
            row = index // 2
            if index == len(items) - 1:
                row = 3
            self._add_page_button(
                x, first_y + row * 62, button_width, button_height, label, color, action, index,
                pass_event=label == "BOSS CAMPAIGN",
            )
        if self._update_running:
            self.canvas.create_text(center_x, min(height - 35, first_y + 4 * 62),
                                    text=self._update_status or "UPDATING REPOSITORY...",
                                    fill="#5a6877", font=("Courier New", 9, "bold"))
        self.canvas.create_text(center_x, height - 18,
                                text="Author: Soullessrage - Made with AI as a proof of concept",
                                fill="#607386", font=("Courier New", 8))

    def _draw_settings_page(self, width, height):
        center_x = width / 2
        for index, (key, label, color) in enumerate((
            ("music", "Music", "#d4e8fa"),
            ("pixel_effects", "Pixel effects", "#e4d8f5"),
        )):
            state = "ON" if self._settings[key] else "OFF"
            self._add_page_button(center_x, 210 + index * 65, 330, 48, f"{label}: {state}", color,
                                  lambda setting=key: self._toggle_setting(setting), index)
        self._draw_back_button(width, height)

    def _draw_controls_page(self, width, height):
        center_x = width / 2
        self.canvas.create_text(center_x, 175, text="MOVEMENT KEYS", fill="#354356",
                                font=("Courier New", 11, "bold"))
        for index, (label, scheme) in enumerate((("WASD", "wasd"), ("ARROW KEYS", "arrows"))):
            color = "#b9e3c9" if self._game.movement_scheme == scheme else "#e4d8f5"
            self._add_page_button(center_x, 220 + index * 62, 250, 46, label, color,
                                  lambda value=scheme: self._set_movement_scheme(value), index)
        self._draw_back_button(width, height)

    def _draw_guide_page(self, width, height):
        x, y = max(42, width * 0.12), 145
        for power_up in POWER_UP_CATALOG:
            self.canvas.create_oval(x, y - 8, x + 16, y + 8, fill=power_up.color, outline="#ffffff", width=2)
            self.canvas.create_text(x + 31, y, anchor="w",
                                    text=f"{power_up.name}  -  {power_up.description} ({power_up.duration:g}s)",
                                    fill="#354356", font=("Courier New", 9))
            y += 34
        y += 12
        boss_descriptions = (
            "Heavy Balloon: fires large, two-hit balloons that can be dodged or shot.",
            "Fast Balloon: jolts around and releases balloons that chase the plane.",
            "Battle Balloon: combines the other bosses' attacks. Defeat it to unlock endless.",
        )
        for index, description in enumerate(boss_descriptions):
            self.canvas.create_text(x, y, anchor="w", width=width - 2 * x,
                                    text=description, fill="#354356", font=("Courier New", 9))
            y += 36
        self.canvas.create_text(x, y + 4, anchor="w", width=width - 2 * x,
                                text="Pop balloons for a chance to drop a power-up. Boss score falls with fight time.",
                                fill="#607386", font=("Courier New", 9))
        self._add_page_button(width / 2 - 130, height - 82, 200, 44, "ARCADE RECORDS", "#d4e8fa",
                              lambda: self._navigate("scores"), "records")
        self._add_page_button(width / 2 + 130, height - 82, 200, 44, "BACK TO MENU", "#f2c5d4",
                              lambda: self._navigate("menu"), "back")

    def _draw_scores_page(self, width, height):
        center_x = width / 2
        stats = self._stats.snapshot()
        self.canvas.create_text(center_x, 125, text=f"BALLOONS POPPED  {stats['balloons_popped']:,}     "
                                f"BOSSES DEFEATED  {stats['bosses_defeated']:,}",
                                fill="#354356", font=("Courier New", 9, "bold"))
        columns = (("BOSS BATTLE", "boss_battle", center_x - width * 0.22),
                   ("ENDLESS MODE", "endless", center_x + width * 0.22))
        for title, mode, x in columns:
            self.canvas.create_text(x, 170, text=title, fill="#354356", font=("Courier New", 11, "bold"))
            scores = self._stats.high_scores(mode)
            if not scores:
                self.canvas.create_text(x, 205, text="NO RECORDS YET", fill="#607386", font=("Courier New", 9))
            for index, entry in enumerate(scores[:10]):
                initials = str(entry["initials"])
                score = int(entry["score"])
                self.canvas.create_text(x, 205 + index * 26,
                                        text=f"{index + 1:2}. {initials:<3}  {score:>6,}",
                                        fill="#354356", font=("Courier New", 10))
        self._draw_back_button(width, height)

    def _draw_contact_page(self, width, height):
        center_x = width / 2
        details = (("Email", EMAIL), ("GitHub", GITHUB_URL), ("Website", WEBSITE_URL or "Not provided"))
        for index, (label, value) in enumerate(details):
            self.canvas.create_text(center_x, 210 + index * 38, text=f"{label}:  {value}",
                                    fill="#354356", font=("Courier New", 9))
        self._add_page_button(center_x, 345, 220, 46, "OPEN GITHUB", "#d4e8fa",
                              lambda: webbrowser.open(GITHUB_URL), 0)
        self._draw_back_button(width, height)

    def _draw_back_button(self, width, height):
        self._add_page_button(width / 2, height - 82, 220, 44, "BACK TO MENU", "#f2c5d4",
                              lambda: self._navigate("menu"), "back")

    def _add_page_button(self, center_x, top, width, height, label, color, action, tag, pass_event=False):
        button_tag = f"page-button-{tag}"
        self._draw_button(center_x, top, width, height, label, color, button_tag)
        self.canvas.tag_bind(button_tag, "<Enter>", lambda _event, t=button_tag, c=_blend(color, "#ffffff", 0.14):
                             self._set_button_color(t, c))
        self.canvas.tag_bind(button_tag, "<Leave>", lambda _event, t=button_tag, c=color:
                             self._set_button_color(t, c))
        if pass_event:
            self.canvas.tag_bind(button_tag, "<Button-1>", lambda event, callback=action: callback(event))
        else:
            self.canvas.tag_bind(button_tag, "<Button-1>", lambda _event, callback=action: callback())

    def _toggle_setting(self, key):
        self._settings[key] = not self._settings[key]
        self._draw_menu()

    def _set_movement_scheme(self, scheme):
        self._game.set_movement_scheme(scheme)
        self._draw_menu()

    def _navigate(self, screen):
        self._screen = screen
        self._draw_menu()
        if self._settings["pixel_effects"]:
            if self._transition_id is not None:
                self.root.after_cancel(self._transition_id)
            width = max(self.canvas.winfo_width(), 1)
            height = max(self.canvas.winfo_height(), 1)
            self.canvas.delete("screen-transition")
            self.canvas.create_rectangle(0, 0, width, height, fill="#ffffff", stipple="gray50",
                                         outline="", tags=("screen-transition",))
            self._reveal_screen(0, width, height)

    def _reveal_screen(self, frame, width, height):
        if frame >= 6:
            self.canvas.delete("screen-transition")
            self._transition_id = None
            return
        self.canvas.coords("screen-transition", 0, 0, width * (1 - (frame + 1) / 6), height)
        self._transition_id = self.root.after(
            18, lambda: self._reveal_screen(frame + 1, width, height)
        )

    def _draw_button(self, center_x, top, width, height, label, color, tag):
        left = center_x - width / 2
        right = center_x + width / 2
        radius = 10
        points = [
            left + radius, top,
            right - radius, top,
            right, top + radius,
            right, top + height - radius,
            right - radius, top + height,
            left + radius, top + height,
            left, top + height - radius,
            left, top + radius,
        ]
        shadow_points = [coordinate + (3 if index % 2 else 2) for index, coordinate in enumerate(points)]
        self.canvas.create_polygon(shadow_points, smooth=True, splinesteps=8, fill="#71808c", outline="")
        self.canvas.create_polygon(
            points,
            smooth=True,
            splinesteps=8,
            fill=color,
            outline="#ffffff",
            width=2,
            tags=(tag, f"{tag}-face"),
        )
        self.canvas.create_text(
            center_x,
            top + height / 2,
            text=label,
            fill="#354356",
            font=("Courier New", 11, "bold"),
            tags=(tag,),
        )

    def _set_button_color(self, tag, color):
        for item in self.canvas.find_withtag(f"{tag}-face"):
            self.canvas.itemconfigure(item, fill=color)

    def _play(self, mode="boss_battle", developer_mode=False):
        self._screen = "game"
        self._game.start(mode, developer_mode=developer_mode)

    def _start_boss_campaign(self, event):
        self._play(developer_mode=bool(event.state & 0x0001))

    def _return_to_menu(self):
        self._navigate("menu")

    def _on_canvas_configure(self, event=None):
        if self._screen == "game":
            self._game.draw()
        else:
            self._draw_menu(event)

    def _on_key_press(self, event):
        if self._screen == "game":
            self._game.handle_keypress(event.keysym)
            return "break"
        if event.keysym == "Escape":
            if self._screen == "menu":
                self.root.destroy()
            else:
                self._navigate("menu")
            return "break"
        return None

    def _on_key_release(self, event):
        if self._screen == "game":
            self._game.handle_keyrelease(event.keysym)
            return "break"
        return None

    def _open_settings(self):
        self._navigate("settings")

    def _open_controls(self):
        self._navigate("controls")

    def _open_book(self):
        self._navigate("guide")

    def _open_contact(self):
        self._navigate("contact")

    def _record_score(self, mode, score, initials):
        try:
            saved = self._stats.add_high_score(mode, initials, score)
        except OSError as error:
            messagebox.showerror("Score not saved", f"The high score could not be saved:\n{error}", parent=self.root)
            return False
        if not saved:
            messagebox.showinfo("High score", "That score did not make the top 10.", parent=self.root)
        return saved

    @staticmethod
    def _buy_coffee():
        webbrowser.open(BUY_ME_A_COFFEE_URL)

    def _update_app(self):
        if self._update_running:
            return
        self._update_running = True
        self._update_status = "Contacting GitHub..."
        self._draw_menu()

        def update_in_background():
            try:
                GitHubUpdater(PROJECT_ROOT, self._update_queue.put).update()
                result = (True, "The latest app files were installed. The app will now restart.")
            except Exception as error:
                result = (False, f"Update failed:\n{error}")
            self._update_queue.put(result)

        threading.Thread(target=update_in_background, name="repository-updater", daemon=True).start()

    def _poll_update_result(self):
        try:
            update_message = self._update_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            if isinstance(update_message, str):
                self._update_status = update_message
                self._on_canvas_configure()
            else:
                self._update_running = False
                self._update_status = ""
                success, message = update_message
                self._on_canvas_configure()
                if success:
                    messagebox.showinfo("Update complete", message, parent=self.root)
                    self._restart_after_update()
                else:
                    messagebox.showerror("Update failed", message, parent=self.root)
        try:
            self.root.after(100, self._poll_update_result)
        except tk.TclError:
            pass

    def _restart_after_update(self):
        try:
            subprocess.Popen([sys.executable, str(APP_ENTRY)], cwd=PROJECT_ROOT)
        except OSError as error:
            messagebox.showerror(
                "Restart failed",
                f"The update installed successfully, but the app could not restart:\n{error}\n\n"
                "Close this window and launch the app again.",
                parent=self.root,
            )
            return
        self.root.destroy()


def _default_stats_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "BalloonPop" / "stats.json"


class StatsStore:
    """Keep lifetime pop and boss counts outside the app install folder."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else _default_stats_path()
        self._stats = {"balloons_popped": 0, "bosses_defeated": 0}
        self._high_scores: dict[str, list[dict[str, int | str]]] = {
            "boss_battle": [],
            "endless": [],
        }
        self._last_save_error: OSError | None = None
        self._load()

    def record_balloon_popped(self) -> None:
        self._stats["balloons_popped"] += 1
        self._save()

    def record_boss_defeated(self) -> None:
        self._stats["bosses_defeated"] += 1
        self._save()

    def snapshot(self) -> dict[str, int]:
        return dict(self._stats)

    def high_scores(self, mode: str) -> list[dict[str, int | str]]:
        if mode not in self._high_scores:
            raise ValueError("High-score mode must be 'boss_battle' or 'endless'.")
        return [dict(entry) for entry in self._high_scores[mode]]

    def qualifies_for_high_score(self, mode: str, score: int) -> bool:
        scores = self.high_scores(mode)
        return len(scores) < 10 or score > scores[-1]["score"]

    def add_high_score(self, mode: str, initials: str, score: int) -> bool:
        if mode not in self._high_scores:
            raise ValueError("High-score mode must be 'boss_battle' or 'endless'.")
        if not (len(initials) == 3 and initials.isalpha() and initials.isupper()):
            raise ValueError("Initials must contain three uppercase letters.")
        if isinstance(score, bool) or not isinstance(score, int) or score < 0:
            raise ValueError("High scores must be non-negative integers.")
        if not self.qualifies_for_high_score(mode, score):
            return False

        previous = self._high_scores[mode]
        updated = [*previous, {"initials": initials, "score": score}]
        updated.sort(key=lambda entry: entry["score"], reverse=True)
        self._high_scores[mode] = updated[:10]
        if not self._save():
            self._high_scores[mode] = previous
            raise OSError(f"Could not write high scores to {self.path}.") from self._last_save_error
        return True

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        for key in self._stats:
            value = data.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                self._stats[key] = value
        raw_high_scores = data.get("high_scores")
        if not isinstance(raw_high_scores, dict):
            return
        for mode in self._high_scores:
            entries = raw_high_scores.get(mode)
            if not isinstance(entries, list):
                continue
            valid_entries = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                initials, score = entry.get("initials"), entry.get("score")
                if (
                    isinstance(initials, str)
                    and 1 <= len(initials) <= 3
                    and initials.isalpha()
                    and initials.isupper()
                    and isinstance(score, int)
                    and not isinstance(score, bool)
                    and score >= 0
                ):
                    valid_entries.append({"initials": initials, "score": score})
            valid_entries.sort(key=lambda entry: entry["score"], reverse=True)
            self._high_scores[mode] = valid_entries[:10]

    def _save(self) -> bool:
        temporary_path = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {**self._stats, "high_scores": self._high_scores}
            temporary_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary_path, self.path)
            self._last_save_error = None
            return True
        except OSError as error:
            self._last_save_error = error
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False