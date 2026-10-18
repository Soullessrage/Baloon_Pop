"""Movement-key selection dialog."""

import tkinter as tk
from tkinter import ttk


class ControlsWindow:
    """Let the player choose WASD or arrow-key movement."""

    def __init__(self, parent, movement_scheme, on_change):
        self.window = tk.Toplevel(parent)
        self.window.title("Controls")
        self.window.geometry("380x220")
        self.window.resizable(False, False)
        self.window.configure(bg="#dceafa")
        self.window.transient(parent)
        self.window.grab_set()

        ttk.Label(self.window, text="CONTROLS", font=("Courier New", 15, "bold")).pack(pady=(24, 20))
        ttk.Label(self.window, text="Movement keys").pack(pady=(0, 9))
        self.movement_scheme = tk.StringVar(value=movement_scheme)
        key_options = ttk.Frame(self.window)
        key_options.pack()
        for label, value in (("WASD", "wasd"), ("Arrow keys", "arrows")):
            ttk.Radiobutton(
                key_options,
                text=label,
                value=value,
                variable=self.movement_scheme,
                command=lambda: on_change(self.movement_scheme.get()),
                style="Toolbutton",
            ).pack(side="left", padx=5)
        ttk.Button(self.window, text="Done", command=self.window.destroy).pack(pady=24)