# Balloon Pop

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

## Play

Select **Play** from the menu. Steer the plane with **W**, **A**, **S**, and
**D**; press **Space** to fire to the right. Pop
balloons to score. A balloon that escapes the left edge or collides with the
plane costs one of your three lives. Press **Escape** to pause. Continue resumes
the flight; Exit returns to the main menu. After game over, Fly Again starts a
fresh game. Endless mode also offers the option to submit a high score.

Each run opens with a short General B. briefing, shown in a typewriter-style
dialogue box as the plane flies in. Boss introductions use the same cutscene,
gliding the plane back to the left-center while the boss enters; movement and
shooting resume after the dialogue fades.

Balloon spawns become more frequent over time. At 100 popped balloons the boss
campaign begins. Defeat the Heavy Balloon, play for another minute, then defeat
the Fast Balloon and play for a minute before the final Battle Balloon. A
cutscene clears the screen and slides each boss in from the right; play and
damage are disabled until the entrance ends. The final boss brings in a dark,
stormy sky. Double and Triple Shot use 30-degree diagonals.
Heavy bosses fire large balloons that take two hits to pop. Fast bosses jolt
around and release balloons that chase the plane; the final boss mixes both
attack styles and has 45 health. Bosses award a score bonus that decreases by
one point per second (10 per second for the final boss), with a minimum of 10
points.
Defeating the final boss lets you save a boss-campaign high score or continue in
endless mode.

Popped balloons have a chance to drop one of five timed power-ups: Double Shot,
Triple Shot, Faster Shooting, Extra Heart, or Plane Speed Up. Double and Triple
Shot fire diagonal V-patterns; Triple Shot also fires a straight center shot.
Collect drops by flying into them. Active effects are shown along the bottom of
the screen and also change the plane's appearance. The Extra Heart is blue and
absorbs one hit while its timer is active. Endless-mode scores can be entered
after game over. Both modes keep separate top-ten arcade records with
three-letter initials.

Open **Controls** from the main screen to switch movement between WASD and the
arrow keys. Settings, controls, the flight guide, records, and contact details
are shown within the main screen, with a short screen transition between pages.
Hold **Shift** while clicking **Boss Campaign** to enable developer mode for
that run. Press **Escape** to pause and open Developer Tools to add 50 score,
spawn the next boss, or toggle permanent power-ups for the run.

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
	game/
		plane_game.py
	ui/
		main_window.py
		controls_window.py
		settings_window.py
		contact_window.py
	services/
		updater.py
```

Power-up timers, the reference book, and persistent stats are kept in the
already-updatable game and main-window modules so existing app copies can
receive this release without a separate bootstrap step.

The app uses only Python standard-library modules; there is no `pip install`
step or dependency list to maintain.
