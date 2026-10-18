"""Contact details dialog with configurable personal information."""

import tkinter as tk
from tkinter import ttk
import webbrowser


# Replace these placeholders with the app owner's contact details.
EMAIL = "your-email@example.com"
GITHUB_URL = "https://github.com/Soullessrage/atest"
WEBSITE_URL = ""


class ContactWindow:
    """Display contact details and open configured links in a browser."""

    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title("Contact Me")
        self.window.geometry("430x275")
        self.window.resizable(False, False)
        self.window.configure(bg="#f8e3ec")
        self.window.transient(parent)
        self.window.grab_set()

        ttk.Label(self.window, text="SAY HELLO", font=("Courier New", 15, "bold")).pack(pady=(22, 16))
        details = ttk.Frame(self.window)
        details.pack(fill="x", padx=38)
        for label, value in (("Email", EMAIL), ("GitHub", GITHUB_URL), ("Website", WEBSITE_URL or "Not provided")):
            row = ttk.Frame(details)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=f"{label}:", width=10).pack(side="left")
            ttk.Label(row, text=value, wraplength=280).pack(side="left", fill="x", expand=True)

        ttk.Button(self.window, text="Open GitHub", command=lambda: webbrowser.open(GITHUB_URL)).pack(pady=(15, 8))
        ttk.Button(self.window, text="Close", command=self.window.destroy).pack()