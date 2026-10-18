"""Main menu window and its interactive canvas controls."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox
import webbrowser
from pathlib import Path

from game.plane_game import PlaneGame
from services.updater import GitHubUpdater
from ui.contact_window import ContactWindow
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
        self._game = PlaneGame(self.root, self.canvas, self._return_to_menu)

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
        menu_height = button_height * 5 + button_gap * 4 + 20
        first_y = max(height * 0.31, (height - menu_height) / 2 + 26)
        labels = [
            ("PLAY", "#d1edda", "#b8e3c8", self._play),
            ("SETTINGS", "#d4e8fa", "#bddcf5", self._open_settings),
            ("CONTACT ME", "#f6d9e8", "#efc2d8", self._open_contact),
            ("BUY ME A COFFEE", "#f7edbe", "#f0e39e", self._buy_coffee),
            ("UPDATE APP", "#f5c99b", "#efa96d", self._update_app),
        ]

        for index, (label, color, hover_color, callback) in enumerate(labels):
            y = first_y + index * (button_height + button_gap)
            if index == 4:
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
                min(height - 20, first_y + menu_height + 9),
                text=self._update_status or "UPDATING REPOSITORY...",
                fill="#5a6877",
                font=("Courier New", 9, "bold"),
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
            try:
                self.root.after(100, self._poll_update_result)
            except tk.TclError:
                pass
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