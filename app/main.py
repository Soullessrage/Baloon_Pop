"""Launch the retro pastel desktop app."""

from pathlib import Path
import sys


APP_DIRECTORY = Path(__file__).resolve().parent
if str(APP_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(APP_DIRECTORY))

from ui.main_window import MainWindow


def main():
    """Create and run the application window."""
    MainWindow().run()


if __name__ == "__main__":
    main()