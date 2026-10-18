# Pastel Quest

A small desktop menu app with a pastel, 16-bit-inspired look. It uses Python's
standard-library Tkinter toolkit; no pip packages or Git installation are required.

## Run

After extracting the downloaded ZIP, double-click the launcher for your system:

- Windows: `run.bat`
- macOS: `Run_Pastel_Quest.command`
- Linux: `Run_Pastel_Quest`

Python 3.10 or newer with Tkinter is required. Most Python desktop installers
include Tkinter. On Debian or Ubuntu, install the OS package `python3-tk` if
Tkinter is missing. The launchers start the app directly and do not open a
command prompt that requires typing commands. You can also run
`python app/main.py` from a terminal for development.

## Configure

- Replace `EMAIL` and `WEBSITE_URL` in `app/ui/contact_window.py` with your
	contact details. The GitHub link is set to the supplied repository.
- Replace `YOURNAME` in `app/ui/main_window.py` with your Buy Me a Coffee name.
- **Update App** downloads the latest `main` branch archive, validates and stages
	the app files, installs them with backups, then restarts the app. It does not
	require Git and leaves other files in the extracted folder alone.
- If the GitHub repository is private, authenticate with `gh auth login` or set
	`RETRO_PASTEL_GITHUB_TOKEN` to a token with read-only Contents access. Public
	repositories can update without a token.

## Project layout

```text
app/
	main.py
	ui/
		main_window.py
		settings_window.py
		contact_window.py
	services/
		updater.py

The app uses only Python standard-library modules; there is no `pip install`
step or dependency list to maintain.
```
