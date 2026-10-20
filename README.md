# Focus — Study clock

A small study timer with Midnight, Paper, and Forest themes and a live local clock.

## Desktop

Run `python study_clock.py` with Python 3 and Tkinter installed.

- Choose **Timer** or **Clock**. Switching views keeps the timer running.
- Open **Customize** for themes, progress-bar styles, and the **24 hour / 12 hour** clock format. Appearance choices are saved locally and can change during a session.
- Choose **Package installer**, **ASCII terminal**, or **Retro segments** in the panel's **Progress bar** menu. The style also applies in compact mode.
- The **Session** section in Customize offers 1–3 study hours and a 5, 10, or 15-minute break each hour. Reset before editing an active plan.
- Use **Done** or **Escape** to return from Customize to the timer.
- **Start / Pause / Resume** controls the timer; **Reset** restarts the session.
- Drag the window to move it. The header controls hide to a restore pill (**Hide**), show only the progress bar (`▱`), or quit (`×`). Click the compact bar to restore.
- Press **Space** on the main view to start or pause, or **Escape** to quit.

The chime plays on Windows ten seconds before a phase ends. Keep the MP3 beside the script.

## Browser

Open `focus.html`, or run `Start-Process .\focus.html` in PowerShell. No server or installation is required.

The browser version supports 5–60-minute sessions and a daily session goal. Reset before editing an active plan. Completed sessions stay visible until you choose **Next session** or **New goal**. **Hide** pauses the timer. Themes and clock format are saved when browser storage is available.

Use the **Progress bar** selector for **Package installer**, **ASCII terminal**, or **Retro segments**. All three follow your theme and show the percentage, remaining time, and timer status. Your choice is saved when browser storage is available.

## Verification

```powershell
python -m py_compile study_clock.py
python -m unittest discover -s tests -v
node tests/browser_smoke.cjs
```

Desktop tests require a graphical environment with Tkinter. Browser checks require Node 22+ and Chrome/Edge; set `BROWSER_PATH` for another installation. Add `--screenshots` to save browser previews in a temporary directory.

On Windows, `python tests/desktop_preview.py` captures only the app window in each theme and progress style, including compact mode, to a temporary directory. It uses temporary preferences.
