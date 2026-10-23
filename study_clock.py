import ctypes
import json
import math
import os
import time
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime
from pathlib import Path

CHIME_FILE = "freesound_community-timer-with-chime-101253.mp3"
START_CHIME_FILE = "start-chime.wav"
CHIME_LEAD_SECS = 10
PREPARATION_SECS = 10

W = 440
H_BASE = 424
H_COMPACT = 38
PAD_X = 28
COMPACT_PAD_X = 8

BAR_Y0_NORMAL  = 244
BAR_Y1_NORMAL  = 260
BAR_Y0_COMPACT = 3
BAR_Y1_COMPACT = 17
PROGRESS_STYLES = ("Installer", "ASCII", "Segments")

THEMES = {
    "Midnight": {"bg": "#141820", "fg": "#f2f4f8", "dim": "#a4adbd",
                 "accent": "#b5c6ff", "surface": "#242c3b", "border": "#394459"},
    "Paper": {"bg": "#faf7f0", "fg": "#292b32", "dim": "#64646c",
              "accent": "#5554a5", "surface": "#eae5db", "border": "#c9c3b8"},
    "Forest": {"bg": "#12231e", "fg": "#edf5ee", "dim": "#a0b9ab",
               "accent": "#a6dbb5", "surface": "#233c31", "border": "#3e5d4d"},
}
PREFERENCES_FILE = Path(os.environ.get("APPDATA", str(Path.home()))) / "StudyClock" / "preferences.json"

FONT_LABEL   = ("Segoe UI", -11, "bold")
FONT_TIMER   = ("Consolas", -64)
FONT_SMALL   = ("Segoe UI", -13)


def enable_high_dpi():
    """Render at native monitor pixels instead of Windows bitmap scaling."""
    if os.name != "nt":
        return
    try:
        set_context = ctypes.windll.user32.SetProcessDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = ctypes.c_int
        if set_context(ctypes.c_void_p(-4)):  # Per-monitor awareness V2.
            return
    except (AttributeError, OSError):
        pass
    try:
        # Older Windows versions, or a host that already selected its DPI mode.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def fmt_ms(s):
    s = max(0, int(s))
    return f"{s // 60:02d}:{s % 60:02d}"


def fmt_hms(s):
    s = max(0, int(s))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


class StudyClock(tk.Tk):
    def __init__(self):
        # DPI awareness must be set before Tk creates any native windows.
        enable_high_dpi()
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.theme_name = "Midnight"
        self.use_24_hour = True
        self.progress_style = "Installer"
        self._load_preferences()
        self.colors = THEMES[self.theme_name]
        self.configure(bg=self.colors["border"])
        self.view_mode = "timer"
        self.clock_id = None

        # Settings
        self.study_hours = 1    # 1, 2, or 3
        self.break_mins  = 5    # 5, 10, or 15

        # Timer state
        self.state         = "idle"   # idle | running | paused | completed
        self.current_phase = "focus"  # focus | break
        self.phase_total   = self._focus_secs()
        self.time_left     = self.phase_total
        self.total_left    = self.study_hours * 3600
        self.timer_id      = None
        self.preparation_id = None
        self.preparation_deadline = None
        self.preparation_left = 0
        self.flash_id      = None
        self.flash_count   = 0

        # UI state
        self.settings_open = False
        self.compact_open  = False
        self._h_current    = H_BASE
        self._revive_win   = None
        self._sh_var       = None
        self._bm_var       = None
        self._sh_entry     = None
        self._bm_entry     = None

        # Drag state
        self._ox = self._oy = 0
        self._cx = self._cy = 0
        self._px = self._py = 0
        self._moved = False
        self._mono_fonts = {}

        self.update_idletasks()
        sw   = self.winfo_screenwidth()
        sh_p = self.winfo_screenheight()
        self.geometry(f"{W}x{H_BASE}+{sw - W - 20}+{sh_p - H_BASE - 60}")

        self.cv = tk.Canvas(self, width=W - 2, height=H_BASE - 2,
                            bg=self.colors["bg"], highlightthickness=0, bd=0)
        self.cv.pack(padx=1, pady=1)
        self.cv.bind("<ButtonPress-1>",   self._on_press)
        self.cv.bind("<B1-Motion>",       self._on_drag)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
        self.cv.bind("<ButtonRelease-3>", self._on_right_release)
        self.cv.bind("<Motion>", self._on_hover)
        self.bind("<Escape>", self._on_escape)
        self.bind("<space>", self._on_space)

        self._build()
        self._render()
        self._clock_tick()

    def _load_preferences(self):
        try:
            prefs = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
            if isinstance(prefs, dict):
                if prefs.get("theme") in THEMES:
                    self.theme_name = prefs["theme"]
                self.use_24_hour = prefs.get("use_24_hour", True) is not False
                if prefs.get("progress_style") in PROGRESS_STYLES:
                    self.progress_style = prefs["progress_style"]
        except (OSError, ValueError, TypeError):
            pass

    def _save_preferences(self):
        try:
            PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
            PREFERENCES_FILE.write_text(json.dumps({
                "theme": self.theme_name, "use_24_hour": self.use_24_hour,
                "progress_style": self.progress_style,
            }), encoding="utf-8")
        except OSError:
            pass

    def _clock_tick(self):
        self._render()
        self.clock_id = self.after(1000, self._clock_tick)

    def _on_space(self, _event):
        if self.settings_open or isinstance(self.focus_get(), tk.Entry):
            return
        self._toggle_play()
        return "break"

    def _on_escape(self, _event=None):
        if self.settings_open:
            self._close_settings()
        else:
            self._quit()
        return "break"

    def _on_hover(self, event):
        self.cv.configure(cursor="hand2" if self._hit_button(event.x, event.y) else "")

    def _set_view(self, mode):
        self.view_mode = mode
        self._render()

    @property
    def preparing(self):
        return self.preparation_deadline is not None

    def _set_progress_style(self, style):
        if style not in PROGRESS_STYLES:
            return
        self.progress_style = style
        self._render()
        self._save_preferences()

    def _set_theme(self, name):
        reopen_settings = self.settings_open
        if reopen_settings:
            self._close_settings()
        self.theme_name = name
        self.colors = THEMES[name]
        self.configure(bg=self.colors["border"])
        self.cv.configure(bg=self.colors["bg"])
        self.cv.delete("all")
        self._build()
        if self.compact_open:
            self.cv.itemconfig("main_ui", state="hidden")
        if reopen_settings:
            self._open_settings()
        self._render()
        self._save_preferences()

    # ── Derived durations ────────────────────────────────────────────────────

    def _focus_secs(self):
        return (60 - self.break_mins) * 60

    def _break_secs(self):
        return self.break_mins * 60

    # ── Build static layout ──────────────────────────────────────────────────

    def _build(self):
        cv = self.cv
        c = self.colors
        cv.create_text(PAD_X, 30, text="Focus",
                       font=("Segoe UI", -17, "bold"), fill=c["fg"], anchor="w", tags="main_ui")
        self._button("btn_hide", 272, 12, 64, 36, "Hide", quiet=True)
        self._button("btn_min", 340, 12, 32, 36, "▱", quiet=True)
        self._button("btn_cls", 380, 12, 32, 36, "×", quiet=True)
        self._rounded_rect(112, 60, 328, 104, 12, fill=c["surface"], tags="main_ui")
        self._timer_tab = self._button("btn_timer", 116, 64, 104, 36, "Timer")
        self._clock_tab = self._button("btn_clock", 224, 64, 100, 36, "Clock")
        self._id_phase = cv.create_text(W // 2, 130, font=FONT_LABEL,
                                        fill=c["accent"], tags="main_ui")
        self._id_timer = cv.create_text(W // 2, 178, font=FONT_TIMER,
                                        fill=c["fg"], tags="main_ui")
        self._id_detail = cv.create_text(W // 2, 222, font=FONT_SMALL,
                                         fill=c["dim"], tags="main_ui")
        self._id_play = self._button("btn_play", 128, 308, 100, 44, "Start", primary=True)
        self._button("btn_reset", 236, 308, 76, 44, "Reset", quiet=True)
        self._id_settings = self._button("btn_cfg", 160, 374, 120, 32, "Customize", quiet=True)

    def _rounded_rect(self, x0, y0, x1, y1, radius, **options):
        points = (x0 + radius, y0, x1 - radius, y0, x1, y0, x1, y0 + radius,
                  x1, y1 - radius, x1, y1, x1 - radius, y1, x0 + radius, y1,
                  x0, y1, x0, y1 - radius, x0, y0 + radius, x0, y0)
        return self.cv.create_polygon(points, smooth=True, splinesteps=24, outline="", **options)

    def _button(self, tag, x, y, width, height, text, primary=False, quiet=False, group="main_ui"):
        c = self.colors
        tags = (group, tag)
        self._rounded_rect(x, y, x + width, y + height, 10,
                           fill=c["accent"] if primary else c["bg"] if quiet else c["surface"], tags=tags)
        return self.cv.create_text(
            x + width / 2, y + height / 2, text=text,
            font=("Segoe UI", -14, "bold") if primary else FONT_SMALL,
            fill=c["bg"] if primary else c["dim"] if quiet else c["fg"], tags=tags)

    def _show_choice_menu(self, tag, choices, selected, callback):
        c = self.colors
        previous = getattr(self, "_choice_menu", None)
        if previous:
            previous.destroy()
        menu = tk.Menu(self, tearoff=False, bg=c["surface"], fg=c["fg"],
                       activebackground=c["accent"], activeforeground=c["bg"],
                       font=FONT_SMALL, bd=0)
        self._choice_menu = menu
        labels = {"Installer": "Package installer", "ASCII": "ASCII terminal", "Segments": "Retro segments"}
        for choice in choices:
            menu.add_command(label=("✓  " if choice == selected else "    ") + labels.get(choice, choice),
                             command=lambda value=choice: callback(value))
        bbox = self.cv.bbox(tag)
        try:
            menu.tk_popup(self.winfo_rootx() + bbox[0], self.winfo_rooty() + bbox[3])
        finally:
            menu.grab_release()

    # ── Render ───────────────────────────────────────────────────────────────

    def _render(self):
        cv = self.cv

        label = {"idle": "READY TO FOCUS", "completed": "SESSION COMPLETE",
                 "paused": "PAUSED"}.get(
            self.state,
            "FOCUS TIME" if self.current_phase == "focus" else "TAKE A BREAK")
        if self.preparing:
            label = "GET READY"
        now = datetime.now()
        clock_mode = self.view_mode == "clock" and not self.preparing
        clock_text = now.strftime("%H:%M:%S" if self.use_24_hour else "%I:%M:%S")
        cv.itemconfig(self._id_phase, text="LOCAL TIME" if clock_mode else label)
        timer_text = fmt_ms(self.preparation_left if self.preparing else self.time_left)
        cv.itemconfig(self._id_timer, text=clock_text if clock_mode else timer_text,
                      font=("Consolas", -52 if clock_mode else -64))
        detail = (now.strftime("%A, %d %B") + ("" if self.use_24_hour else now.strftime(" · %p"))
                  if clock_mode else f"{self.study_hours}h session  ·  {self.break_mins}m breaks")
        cv.itemconfig(self._id_detail, text=detail)
        if self.preparing:
            cv.itemconfig(self._id_detail, text="Your session starts after the countdown")
        for tag, tab, active in (("btn_timer", self._timer_tab, not clock_mode),
                                ("btn_clock", self._clock_tab, clock_mode)):
            cv.itemconfig(tab, fill=self.colors["accent"] if active else self.colors["dim"])
            cv.itemconfig(cv.find_withtag(tag)[0],
                          fill=self.colors["bg"] if active else self.colors["surface"])

        self._render_progress()

        cv.itemconfig(self._id_play,
                      text="Cancel" if self.preparing else {"running": "Pause", "paused": "Resume",
                            "completed": "Done"}.get(self.state, "Start"))
        if self.settings_open:
            cv.itemconfig(self._theme_btn, text=self.theme_name + "  ▾")
            style_label = {"Installer": "Package installer", "ASCII": "ASCII terminal", "Segments": "Retro segments"}
            cv.itemconfig(self._style_btn, text=style_label[self.progress_style] + "  ▾")
            cv.itemconfig(self._format_btn, text="24 hour" if self.use_24_hour else "12 hour")
            editable = self.state in ("idle", "completed") and not self.preparing
            for entry in (self._sh_entry, self._bm_entry):
                entry.configure(state="normal" if editable else "disabled")
            cv.itemconfig("settings_hint", text="Hours: 1–3 · Break: 5, 10 or 15 minutes"
                          if editable else "Reset the timer to change your plan.")

    def _render_progress(self):
        cv, c = self.cv, self.colors
        cv.delete("bar")
        if self.settings_open:
            return
        fraction = max(0, min(1, (self.phase_total - self.time_left) / self.phase_total
                             if self.phase_total else 0))
        # Never show 100% before the phase has actually finished.
        percent = int(fraction * 100)
        y0 = BAR_Y0_COMPACT if self.compact_open else BAR_Y0_NORMAL
        y1 = BAR_Y1_COMPACT if self.compact_open else BAR_Y1_NORMAL
        padding = COMPACT_PAD_X if self.compact_open else PAD_X
        x0, x1 = padding, W - padding
        font = ("Consolas", -12)
        status = {"idle": "READY", "paused": "PAUSED", "completed": "DONE"}.get(
            self.state, "BREAK" if self.current_phase == "break" else "STUDYING")
        if self.preparing:
            status = "GET READY"
        cv.create_text(x1, 28 if self.compact_open else 282,
                       text=f"{percent}%", font=font, fill=c["accent"], anchor="e", tags=("bar", "bar_percent"))
        remaining = self.study_hours * 3600 if self.state == "idle" else max(0, self.total_left)
        meta = (status if self.compact_open
                else f"Session left {fmt_hms(remaining)}")
        if self.preparing and not self.compact_open:
            meta = f"Starting in {self.preparation_left}s"
        cv.create_text(x0, 28 if self.compact_open else 282, text=meta,
                       font=font, fill=c["dim"], anchor="w", tags=("bar", "bar_status"))
        if self.compact_open:
            compact_time = (f"{self.preparation_left}s to start" if self.preparing
                            else f"{fmt_ms(self.time_left)} left")
            cv.create_text(W // 2, 28, text=compact_time,
                           font=font, fill=c["fg"], tags=("bar", "bar_remaining"))
        if self.progress_style == "Installer":
            count = self._bar_cell_count(28)
            filled = int(fraction * count)
            text = "[" + "█" * filled + "░" * (count - filled) + "]"
            cv.create_text(W // 2, (y0 + y1) / 2, text=text,
                           font=self._bar_font(text), fill=c["accent"], tags=("bar", "bar_installer", "bar_track"))
            return
        if self.progress_style == "ASCII":
            count = self._bar_cell_count(30)
            filled = int(fraction * count)
            contents = "=" * filled
            if filled < count:
                contents += ">" + "-" * (count - filled - 1)
            cv.create_text(W // 2, (y0 + y1) / 2, text=f"[{contents}]",
                           font=self._bar_font(f"[{contents}]"), fill=c["accent"], tags=("bar", "bar_ascii", "bar_track"))
            return
        count, gap = 20, 3 if self.compact_open else 4
        width = (x1 - x0 - gap * (count - 1)) / count
        filled = int(fraction * count)
        for index in range(count):
            left = x0 + index * (width + gap)
            cv.create_rectangle(left, y0, left + width, y1,
                                 fill=c["accent"] if index < filled else c["surface"],
                                 outline=c["border"],
                                 tags=("bar", "bar_track", "bar_filled" if index < filled else "bar_empty"))

    def _bar_cell_count(self, normal_count):
        if not self.compact_open:
            return normal_count
        # Add characters to fill the strip without stretching or shrinking the font.
        character_width = max(1, self._bar_font("[]").measure("0"))
        return max(1, (W - 2 * COMPACT_PAD_X - 4) // character_width - 2)

    def _bar_font(self, text):
        key = (len(text), self.compact_open)
        if key not in self._mono_fonts:
            font = tkfont.Font(self, family="Consolas", size=-16 if self.compact_open else -22)
            padding = COMPACT_PAD_X if self.compact_open else PAD_X
            while font.measure(text) > W - 2 * padding - 4:
                font.configure(size=font.cget("size") + 1)
            self._mono_fonts[key] = font
        return self._mono_fonts[key]

    # ── Input ────────────────────────────────────────────────────────────────

    def _on_press(self, e):
        self._ox = e.x_root - self.winfo_x()
        self._oy = e.y_root - self.winfo_y()
        self._px, self._py = e.x_root, e.y_root
        self._cx, self._cy = e.x, e.y
        self._moved = False

    def _on_drag(self, e):
        if abs(e.x_root - self._px) > 4 or abs(e.y_root - self._py) > 4:
            self._moved = True
        if self._moved:
            self.geometry(f"+{e.x_root - self._ox}+{e.y_root - self._oy}")

    def _on_release(self, e):
        if self._moved:
            self._moved = False
            return
        if self.compact_open:
            self._exit_compact()
            return
        tag = self._hit_button(self._cx, self._cy)
        if   tag == "btn_cls":   self._quit()
        elif tag == "btn_hide":  self._minimize()
        elif tag == "btn_cfg":   self._toggle_settings()
        elif tag == "btn_done":  self._close_settings()
        elif tag == "btn_min":   self._enter_compact()
        elif tag == "btn_play":  self._toggle_play()
        elif tag == "btn_reset": self._reset()
        elif tag == "btn_timer": self._set_view("timer")
        elif tag == "btn_clock": self._set_view("clock")
        elif tag == "btn_format":
            self.use_24_hour = not self.use_24_hour
            self._save_preferences()
            self._render()
        elif tag == "btn_theme":
            self._show_choice_menu(tag, THEMES, self.theme_name, self._set_theme)
        elif tag == "btn_style":
            self._show_choice_menu(tag, PROGRESS_STYLES, self.progress_style, self._set_progress_style)

    def _on_right_release(self, e):
        if self._hit_button(e.x, e.y) == "btn_cls":
            self._quit()

    def _hit_button(self, x, y):
        for item in reversed(self.cv.find_overlapping(x, y, x, y)):
            if self.cv.itemcget(item, "state") == "hidden":
                continue
            for tag in self.cv.gettags(item):
                if tag.startswith("btn_"):
                    return tag
        return None

    def _quit(self):
        self._cancel_preparation()
        if self.clock_id:
            self.after_cancel(self.clock_id)
            self.clock_id = None
        if self.timer_id:
            self.after_cancel(self.timer_id)
            self.timer_id = None
        if self.flash_id:
            self.after_cancel(self.flash_id)
            self.flash_id = None
        self._stop_chime()
        if self._revive_win:
            self._revive_win.destroy()
            self._revive_win = None
        self.destroy()

    # ── Chime ────────────────────────────────────────────────────────────────

    def _play_chime(self, kind="end"):
        try:
            winmm = ctypes.windll.winmm
            filename = START_CHIME_FILE if kind == "start" else CHIME_FILE
            media_type = "waveaudio" if kind == "start" else "mpegvideo"
            path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), filename)
            winmm.mciSendStringW("close chime", None, 0, 0)
            winmm.mciSendStringW(
                f'open "{path}" type {media_type} alias chime', None, 0, 0)
            winmm.mciSendStringW("play chime from 0", None, 0, 0)
        except Exception:
            pass

    def _stop_chime(self):
        try:
            ctypes.windll.winmm.mciSendStringW("close chime", None, 0, 0)
        except Exception:
            pass

    # ── Timer state machine ──────────────────────────────────────────────────

    def _toggle_play(self):
        if self.preparing:
            self._reset()
        elif self.state == "running":
            self._pause()
        else:
            self._start()

    def _start(self):
        if self.state in ("completed", "running") or self.preparing:
            return
        if self.settings_open:
            self._close_settings()
        if self.state == "idle":
            self._init_session()
            self.view_mode = "timer"
            self.preparation_left = PREPARATION_SECS
            self.preparation_deadline = time.monotonic() + PREPARATION_SECS
            self.preparation_id = self.after(100, self._preparation_tick)
            self._render()
            return
        self._begin_session()

    def _preparation_tick(self):
        self.preparation_id = None
        if not self.preparing:
            return
        self.preparation_left = max(0, math.ceil(self.preparation_deadline - time.monotonic()))
        if self.preparation_left == 0:
            self.preparation_deadline = None
            self._begin_session(play_start=True)
            return
        self._render()
        self.preparation_id = self.after(100, self._preparation_tick)

    def _cancel_preparation(self):
        if self.preparation_id is not None:
            self.after_cancel(self.preparation_id)
            self.preparation_id = None
        self.preparation_deadline = None
        self.preparation_left = 0

    def _begin_session(self, play_start=False):
        self.state = "running"
        if self.timer_id:
            self.after_cancel(self.timer_id)
        self.timer_id = self.after(1000, self._tick)
        if play_start:
            self._play_chime("start")
        self._render()

    def _init_session(self):
        self.current_phase = "focus"
        self.phase_total   = self._focus_secs()
        self.time_left     = self.phase_total
        self.total_left    = self.study_hours * 3600

    def _pause(self):
        if self.state != "running":
            return
        self.state = "paused"
        if self.timer_id:
            self.after_cancel(self.timer_id)
            self.timer_id = None
        self._stop_chime()
        self._render()

    def _reset(self):
        self._cancel_preparation()
        self.state = "idle"
        if self.timer_id:
            self.after_cancel(self.timer_id)
            self.timer_id = None
        if self.flash_id:
            self.after_cancel(self.flash_id)
            self.flash_id = None
        self._stop_chime()
        self.cv.itemconfig(self._id_timer, fill=self.colors["fg"])
        self.current_phase = "focus"
        self.phase_total   = self._focus_secs()
        self.time_left     = self.phase_total
        self.total_left    = self.study_hours * 3600
        self._render()

    def _tick(self):
        if self.state != "running":
            return
        self.time_left  -= 1
        self.total_left -= 1

        if self.time_left == CHIME_LEAD_SECS:
            self._play_chime()

        if self.total_left <= 0:
            self.view_mode = "timer"
            self.time_left  = 0
            self.total_left = 0
            self.state      = "completed"
            self.timer_id   = None
            if self.compact_open:
                self._exit_compact()
            else:
                self._render()
            self._begin_flash()
            return

        if self.time_left <= 0:
            self._switch_phase()

        self._render()
        self.timer_id = self.after(1000, self._tick)

    def _switch_phase(self):
        if self.current_phase == "focus":
            self.current_phase = "break"
            self.phase_total   = self._break_secs()
        else:
            self.current_phase = "focus"
            self.phase_total   = self._focus_secs()
            self._play_chime("start")
        self.time_left = self.phase_total

    # ── Flash on completion ──────────────────────────────────────────────────

    def _begin_flash(self):
        self.flash_count = 0
        self._flash_step()

    def _flash_step(self):
        on = self.flash_count % 2 == 0
        self.cv.itemconfig(self._id_timer, fill=self.colors["bg"] if on else self.colors["fg"])
        self.flash_count += 1
        if self.flash_count >= 6:
            self.cv.itemconfig(self._id_timer, fill=self.colors["fg"])
            self.flash_id = None
            self._reset()
            return
        self.flash_id = self.after(250, self._flash_step)

    # ── Compact (bar-only) mode ──────────────────────────────────────────────

    def _enter_compact(self):
        if self.compact_open:
            return
        if self.settings_open:
            self._close_settings()
        self.compact_open = True
        self._h_current   = H_COMPACT
        self.geometry(f"{W}x{H_COMPACT}+{self.winfo_x()}+{self.winfo_y()}")
        self.cv.configure(height=H_COMPACT - 2)
        self.cv.itemconfig("main_ui", state="hidden")
        self._render()

    def _exit_compact(self):
        if not self.compact_open:
            return
        self.compact_open = False
        self._h_current   = H_BASE
        self.geometry(f"{W}x{H_BASE}+{self.winfo_x()}+{self.winfo_y()}")
        self.cv.configure(height=H_BASE - 2)
        self.cv.itemconfig("main_ui", state="normal")
        self._render()

    # ── Customization panel ──────────────────────────────────────────────────

    def _toggle_settings(self):
        if self.settings_open:
            self._close_settings()
        else:
            self._open_settings()

    def _open_settings(self):
        if self.settings_open:
            return
        if self.compact_open:
            self._exit_compact()
        self.settings_open = True
        cv  = self.cv
        cv.itemconfig("main_ui", state="hidden")
        cv.delete("bar")
        cv.create_text(PAD_X, 32, text="Customize", font=("Segoe UI", -18, "bold"),
                       fill=self.colors["fg"], anchor="w", tags="settings")
        self._button("btn_done", W - PAD_X - 72, 14, 72, 36, "Done",
                     quiet=True, group="settings")
        cv.create_text(PAD_X, 72, text="APPEARANCE", font=FONT_LABEL,
                       fill=self.colors["dim"], anchor="w", tags="settings")
        for y, text in ((106, "Theme"), (158, "Progress bar"), (210, "Clock format")):
            cv.create_text(PAD_X, y, text=text, font=FONT_SMALL,
                           fill=self.colors["dim"], anchor="w", tags="settings")
        self._theme_btn = self._button("btn_theme", 212, 86, 200, 40, "", group="settings")
        self._style_btn = self._button("btn_style", 212, 138, 200, 40, "", group="settings")
        self._format_btn = self._button("btn_format", 212, 190, 200, 40, "", group="settings")
        cv.create_line(PAD_X, 248, W - PAD_X, 248, fill=self.colors["border"], tags="settings")
        cv.create_text(PAD_X, 272, text="SESSION", font=FONT_LABEL,
                       fill=self.colors["dim"], anchor="w", tags="settings")
        cv.create_text(PAD_X, 306, text="Study hours",
                       font=FONT_SMALL, fill=self.colors["dim"], anchor="w", tags="settings")
        cv.create_text(PAD_X, 346, text="Break minutes",
                       font=FONT_SMALL, fill=self.colors["dim"], anchor="w", tags="settings")
        cv.create_text(PAD_X, 392, font=("Segoe UI", -12), fill=self.colors["dim"],
                       anchor="w", tags=("settings", "settings_hint"))

        self._sh_var = tk.StringVar(value=str(self.study_hours))
        self._bm_var = tk.StringVar(value=str(self.break_mins))

        ekw = dict(bg=self.colors["surface"], fg=self.colors["fg"],
                   disabledbackground=self.colors["surface"], disabledforeground=self.colors["dim"],
                   insertbackground=self.colors["fg"], relief="solid", bd=1,
                   highlightthickness=0, font=FONT_SMALL, justify="center",
                   width=5)
        self._sh_entry = tk.Entry(self, textvariable=self._sh_var, **ekw)
        self._bm_entry = tk.Entry(self, textvariable=self._bm_var, **ekw)
        for entry in (self._sh_entry, self._bm_entry):
            entry.bind("<FocusOut>", self._apply_settings)
            entry.bind("<Return>",   self._apply_settings)

        cv.create_window(W - PAD_X, 306, anchor="e",
                         window=self._sh_entry, height=30, width=80, tags="settings")
        cv.create_window(W - PAD_X, 346, anchor="e",
                         window=self._bm_entry, height=30, width=80, tags="settings")
        self._render()

    def _close_settings(self):
        self.settings_open = False
        self._commit_settings()
        if self._sh_entry:
            self._sh_entry.destroy()
            self._sh_entry = None
        if self._bm_entry:
            self._bm_entry.destroy()
            self._bm_entry = None
        self._sh_var = None
        self._bm_var = None
        self.cv.delete("settings")
        self.cv.itemconfig("main_ui", state="normal")
        self._render()

    def _commit_settings(self):
        if self.state not in ("idle", "completed") or self.preparing:
            return
        sh_var, bm_var = self._sh_var, self._bm_var
        if sh_var is None or bm_var is None:
            return

        try:
            sh = max(1, min(3, int(sh_var.get())))
        except ValueError:
            sh = self.study_hours
        sh_var.set(str(sh))
        self.study_hours = sh

        try:
            bm_in = int(bm_var.get())
            bm = min([5, 10, 15], key=lambda v: abs(v - bm_in))
        except ValueError:
            bm = self.break_mins
        bm_var.set(str(bm))
        self.break_mins = bm

        if self.state == "idle":
            self.current_phase = "focus"
            self.phase_total   = self._focus_secs()
            self.time_left     = self.phase_total
            self.total_left    = self.study_hours * 3600

    def _apply_settings(self, _e=None):
        self._commit_settings()
        self._render()

    # ── Minimize / revive ────────────────────────────────────────────────────

    def _minimize(self):
        if self.preparing:
            self._reset()
        if self.state == "running":
            self._pause()
        if self.settings_open:
            self._close_settings()
        if self.compact_open:
            self._exit_compact()
        x, y = self.winfo_x(), self.winfo_y()
        self.withdraw()
        self._show_revive(x, y)

    def _show_revive(self, x, y):
        rw, rh = 84, 26
        rv = tk.Toplevel(self)
        rv.overrideredirect(True)
        rv.attributes("-topmost", True)
        rv.configure(bg=self.colors["border"])
        rv.geometry(f"{rw}x{rh}+{x + W - rw}+{y}")
        inner = tk.Frame(rv, bg=self.colors["bg"])
        inner.pack(padx=1, pady=1, fill="both", expand=True)
        lbl = tk.Label(inner, text="FOCUS", font=FONT_SMALL,
                       bg=self.colors["bg"], fg=self.colors["fg"], cursor="hand2")
        lbl.pack(expand=True, fill="both")
        lbl.bind("<Button-1>", lambda _e: self._revive_main())
        lbl.bind("<Button-3>", lambda _e: self._quit())
        self._revive_win = rv

    def _revive_main(self):
        if self._revive_win:
            self._revive_win.destroy()
            self._revive_win = None
        self.deiconify()


if __name__ == "__main__":
    StudyClock().mainloop()
