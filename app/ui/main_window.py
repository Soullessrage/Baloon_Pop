"""Main menu window and its interactive canvas controls."""

from __future__ import annotations

import queue
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser
from pathlib import Path

from game.plane_game import PASTEL_BALLOON_COLORS, POWER_UP_CATALOG, PlaneGame
from services.updater import GitHubUpdater
from ui.contact_window import ContactWindow
from ui.controls_window import ControlsWindow
from ui.settings_window import SettingsWindow


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
    """Own the root window, main menu, dialogs, and background updater."""

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
        self._stats = StatsStore()
        self._game = PlaneGame(
            self.root,
            self.canvas,
            self._return_to_menu,
            self._stats.record_balloon_popped,
            self._stats.record_boss_defeated,
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

        center_x = width / 2
        self.canvas.create_text(
            center_x,
            max(40, height * 0.12),
            text="BALLOON POP",
            fill="#354356",
            font=("Courier New", 24, "bold"),
        )
        self.canvas.create_text(
            center_x,
            max(72, height * 0.18),
            text="A PLANE GAME",
            fill="#607386",
            font=("Courier New", 10, "bold"),
        )

        button_width = min(390, width - 56)
        button_height = 46
        button_gap = 10
        labels = [
            ("PLAY", "#d1edda", "#b8e3c8", self._play),
            ("SETTINGS", "#d4e8fa", "#bddcf5", self._open_settings),
            ("CONTROLS", "#e4d8f5", "#d1c0ed", self._open_controls),
            ("CONTACT ME", "#f6d9e8", "#efc2d8", self._open_contact),
            ("BUY ME A COFFEE", "#f7edbe", "#f0e39e", self._buy_coffee),
            ("UPDATE", "#f5c99b", "#efa96d", self._update_app),
        ]
        menu_height = button_height * len(labels) + button_gap * (len(labels) - 1) + 20
        first_y = max(height * 0.31, (height - menu_height) / 2 + 26)

        for index, (label, color, hover_color, callback) in enumerate(labels):
            y = first_y + index * (button_height + button_gap)
            if label == "UPDATE":
                separator_y = y - 10
                self.canvas.create_line(
                    center_x - button_width / 2,
                    separator_y,
                    center_x + button_width / 2,
                    separator_y,
                    fill="#9aabb7",
                    width=2,
                )
            tag = f"menu-{index}"
            self._draw_button(center_x, y, button_width, button_height, label, color, tag)
            self.canvas.tag_bind(tag, "<Enter>", lambda _event, t=tag, c=hover_color: self._set_button_color(t, c))
            self.canvas.tag_bind(tag, "<Leave>", lambda _event, t=tag, c=color: self._set_button_color(t, c))
            self.canvas.tag_bind(tag, "<Button-1>", lambda _event, action=callback: action())

        if self._update_running:
            self.canvas.create_text(
                center_x,
                min(height - 40, first_y + menu_height + 9),
                text=self._update_status or "UPDATING REPOSITORY...",
                fill="#5a6877",
                font=("Courier New", 9, "bold"),
            )

        self.canvas.create_text(
            center_x,
            height - 18,
            text="Author: Soullessrage - Made with AI as a proof of concept",
            fill="#607386",
            font=("Courier New", 8),
        )

        book_tag = "main-menu-book"
        book_left = width - 62
        book_top = height - 56
        book_bottom = height - 20
        self.canvas.create_polygon(
            book_left,
            book_top + 3,
            book_left + 15,
            book_top + 7,
            book_left + 15,
            book_bottom,
            book_left,
            book_bottom - 4,
            fill="#d7b5e8",
            outline="#ffffff",
            width=2,
            tags=(book_tag,),
        )
        self.canvas.create_polygon(
            book_left + 17,
            book_top + 7,
            book_left + 32,
            book_top + 3,
            book_left + 32,
            book_bottom - 4,
            book_left + 17,
            book_bottom,
            fill="#f3e6b0",
            outline="#ffffff",
            width=2,
            tags=(book_tag,),
        )
        self.canvas.create_line(
            book_left + 16,
            book_top + 7,
            book_left + 16,
            book_bottom,
            fill="#71808c",
            width=2,
            tags=(book_tag,),
        )
        self.canvas.tag_bind(book_tag, "<Button-1>", lambda _event: self._open_book())

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

    def _play(self):
        self._screen = "game"
        self._game.start()

    def _return_to_menu(self):
        self._screen = "menu"
        self._draw_menu()

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
            self.root.destroy()
            return "break"
        return None

    def _on_key_release(self, event):
        if self._screen == "game":
            self._game.handle_keyrelease(event.keysym)
            return "break"
        return None

    def _open_settings(self):
        SettingsWindow(self.root)

    def _open_controls(self):
        ControlsWindow(self.root, self._game.movement_scheme, self._game.set_movement_scheme)

    def _open_book(self):
        BookWindow(self.root, self._stats)

    def _open_contact(self):
        ContactWindow(self.root)

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
        self._load()

    def record_balloon_popped(self) -> None:
        self._stats["balloons_popped"] += 1
        self._save()

    def record_boss_defeated(self) -> None:
        self._stats["bosses_defeated"] += 1
        self._save()

    def snapshot(self) -> dict[str, int]:
        return dict(self._stats)

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

    def _save(self) -> None:
        temporary_path = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(json.dumps(self._stats, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary_path, self.path)
        except OSError:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


class BookWindow:
    """Show balloon types, planned power-ups, and lifetime statistics."""

    def __init__(self, parent, stats_store):
        self.window = tk.Toplevel(parent)
        self.window.title("Balloon Pop Book")
        self.window.geometry("620x440")
        self.window.minsize(520, 360)
        self.window.configure(bg="#e4edf5")
        self.window.transient(parent)
        self.window.grab_set()

        ttk.Label(self.window, text="BALLOON POP BOOK", font=("Courier New", 15, "bold")).pack(pady=(16, 10))
        notebook = ttk.Notebook(self.window)
        notebook.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        self._build_balloon_tab(notebook)
        self._build_power_up_tab(notebook)
        self._build_stats_tab(notebook, stats_store)

    def _build_balloon_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=14)
        notebook.add(tab, text="Balloons")
        row = 0
        for index, color in enumerate(PASTEL_BALLOON_COLORS, start=1):
            row = self._add_guide_row(tab, row, color, f"Pastel balloon {index}", "Pop for one point; a miss costs one life.")
        row = self._add_guide_row(tab, row, "#a8dba8", "Boss balloon", "Turns grey while shields remain, then green, yellow, and red as health falls.")
        row = self._add_guide_row(tab, row, "#c5a3e8", "Orbiting shield balloon", "Three orbit the boss. Pop all three before damaging its core.")
        self._add_guide_row(tab, row, "#a9b8c9", "Indestructible hazard", "Released during the boss fight. Dodge it; it gives no points.")

    def _build_power_up_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=14)
        notebook.add(tab, text="Power-ups")
        for row, power_up in enumerate(POWER_UP_CATALOG):
            tk.Label(tab, text=" ", bg=power_up.color, width=3, relief="solid", bd=1).grid(
                row=row, column=0, padx=(2, 12), pady=10, sticky="n"
            )
            ttk.Label(tab, text=power_up.name, font=("Courier New", 10, "bold")).grid(
                row=row, column=1, sticky="w", pady=(7, 0)
            )
            ttk.Label(tab, text=f"{power_up.description} ({power_up.duration:g}s)", wraplength=420).grid(
                row=row, column=2, sticky="w", pady=(7, 0)
            )
        ttk.Label(tab, text="Power-up drops can be added to flights in a future update.", wraplength=500).grid(
            row=len(POWER_UP_CATALOG), column=0, columnspan=3, sticky="w", pady=(18, 0)
        )
        tab.columnconfigure(2, weight=1)

    def _build_stats_tab(self, notebook, stats_store):
        tab = ttk.Frame(notebook, padding=20)
        notebook.add(tab, text="Stats")
        stats = stats_store.snapshot()
        ttk.Label(tab, text="LIFETIME FLIGHT RECORD", font=("Courier New", 12, "bold")).pack(pady=(18, 24))
        for label, key in (("Balloons popped", "balloons_popped"), ("Bosses defeated", "bosses_defeated")):
            row = ttk.Frame(tab)
            row.pack(fill="x", padx=85, pady=10)
            ttk.Label(row, text=label).pack(side="left")
            ttk.Label(row, text=f"{stats[key]:,}", font=("Courier New", 14, "bold")).pack(side="right")

    @staticmethod
    def _add_guide_row(tab, row, color, name, description):
        tk.Label(tab, text=" ", bg=color, width=3, relief="solid", bd=1).grid(
            row=row, column=0, padx=(2, 12), pady=5, sticky="n"
        )
        ttk.Label(tab, text=name, font=("Courier New", 9, "bold")).grid(row=row, column=1, sticky="w", pady=5)
        ttk.Label(tab, text=description, wraplength=360).grid(row=row, column=2, sticky="w", pady=5)
        tab.columnconfigure(2, weight=1)
        return row + 1