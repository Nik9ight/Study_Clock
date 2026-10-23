# Focus — Study clock

A small study timer with Midnight, Paper, and Forest themes and a live local clock.

## Desktop

Run `python study_clock.py` with Python 3 and Tkinter installed.

Windows DPI awareness is enabled before the window opens to avoid blurry bitmap scaling. The interface remains 440 × 424 pixels, or 440 × 38 in compact mode; text and layout sizes are unchanged.

- Choose **Timer** or **Clock**. Switching views keeps the timer running.
- Open **Customize** for themes, progress-bar styles, and the **24 hour / 12 hour** clock format. Appearance choices are saved locally and can change during a session.
- Choose **Package installer**, **ASCII terminal**, or **Retro segments** in the panel's **Progress bar** menu. The style also applies in compact mode.
- The **Session** section in Customize offers a 1–3-hour plan (including breaks), a break length of 5, 10, or 15 minutes, and **1, 2, or 3 breaks**. Reset before editing an active plan.
- Use **Done** or **Escape** to return from Customize to the timer.
- **Start / Pause / Resume** controls the timer; **Reset** restarts the session.
- **Start** shows a 10-second **Get ready** countdown, then begins the session with the start chime. Preparation does not use study time. **Cancel**, **Reset**, or **Hide** cancels preparation. Resume starts immediately without a new countdown.
- Drag the window to move it. The header controls hide to a restore pill (**Hide**), show only the progress bar (`▱`), or quit (`×`). Click the compact bar to restore.
- Press **Space** on the main view to start or pause, or **Escape** to quit.

On Windows, the short two-note start sound plays when you start a new session and when a break transitions back to focus. Resume stays silent. The original end recording begins ten seconds before each phase ends. Pause, reset, and quit stop playback. Keep `start-chime.wav` and the MP3 beside the script.

Focus time is divided evenly around the selected number of breaks, always starting and finishing in focus. For example, a two-hour plan with one ten-minute break runs **55 minutes focus → 10 minutes break → 55 minutes focus**. With two ten-minute breaks, the same plan has three focus blocks of about 33 minutes 20 seconds. The 10-second preparation countdown is separate from the plan.

## Browser

Open `focus.html`, or run `Start-Process .\focus.html` in PowerShell. No server or installation is required.

The layout adapts as you resize the tab: narrow windows stack controls, short windows reduce spacing, and wide windows place preferences beside the timer. Very small windows scroll so every control remains accessible. Resizing keeps your session running.

The browser version supports 5–60-minute sessions and a daily session goal. Reset before editing an active plan. Completed sessions stay visible until you choose **Next session** or **New goal**. **Hide** pauses the timer. Themes and clock format are saved when browser storage is available.

New sessions start with a gentle, rising two-note cue (`start-chime.wav`, 0.8 seconds). The original MP3 starts during the final ten seconds and continues through completion. It plays once per session, including if the tab catches up after missing the countdown. Resume continues silently; pause and reset stop playback. Keep both audio files beside `focus.html`. Use **Settings → Test start / Test end** to preview each sound, and allow audio for the tab if your browser blocks it.

Use the **Progress bar** selector for **Package installer**, **ASCII terminal**, or **Retro segments**. All three follow your theme and show the percentage, remaining time, and timer status. Your choice is saved when browser storage is available.

The browser tab shows a compact version of your chosen progress bar and the session percentage. Pausing or finishing adds **Paused** or **Done**, so you can check progress while using another tab.

**Notes / Reminders** sits below the right-side preferences (below the timer on narrow screens). Notes save as you type. Add reminders with Enter or **Add**, check them off, or delete them with **×**. These are checklist reminders, without scheduled notifications. Notes and reminders are stored in this browser, survive reloads and timer resets, and are not synced between devices. A message appears if saving fails.

## Verification

```powershell
python -m py_compile study_clock.py
python -m unittest discover -s tests -v
node tests/browser_smoke.cjs
```

Desktop tests require a graphical environment with Tkinter. Browser checks require Node 22+ and Chrome/Edge; set `BROWSER_PATH` for another installation. Add `--screenshots` to save browser previews in a temporary directory.

On Windows, `python tests/desktop_preview.py` captures only the app window in each theme and progress style, including compact mode, to a temporary directory. It uses temporary preferences.
