"""Placeholder settings dialog."""

import tkinter as tk
from tkinter import ttk


class SettingsWindow:
    """Show local placeholder options without changing app behavior."""

    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title("Settings")
        self.window.geometry("360x250")
        self.window.resizable(False, False)
        self.window.configure(bg="#e6eff8")
        self.window.transient(parent)
        self.window.grab_set()

        ttk.Label(self.window, text="SETTINGS", font=("Courier New", 15, "bold")).pack(pady=(22, 15))
        self.music_enabled = tk.BooleanVar(value=True)
        self.pixel_effects_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.window, text="Music", variable=self.music_enabled).pack(anchor="w", padx=52, pady=6)
        ttk.Checkbutton(self.window, text="Pixel effects", variable=self.pixel_effects_enabled).pack(
            anchor="w", padx=52, pady=6
        )
        ttk.Label(self.window, text="Text size").pack(anchor="w", padx=52, pady=(8, 0))
        ttk.Scale(self.window, from_=8, to=16, orient="horizontal").pack(fill="x", padx=52, pady=(4, 14))
        ttk.Button(self.window, text="Done", command=self.window.destroy).pack(pady=4)