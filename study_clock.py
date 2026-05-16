import ctypes
import os
import tkinter as tk

CHIME_FILE = "freesound_community-timer-with-chime-101253.mp3"
CHIME_LEAD_SECS = 10

W = 320
H_BASE = 156
H_SETTINGS = 78
H_COMPACT = 24
PAD_X = 16
BRACKET_ARM = 12
BRACKET_INSET = 6

BAR_Y0_NORMAL  = 96
BAR_Y1_NORMAL  = 112
BAR_Y0_COMPACT = 4
BAR_Y1_COMPACT = 20

BG  = "#000000"
FG  = "#ffffff"
DIM = "#e0e0e0"

FONT_LABEL   = ("Courier New", 9)
FONT_TIMER   = ("Courier New", 26)
FONT_SMALL   = ("Courier New", 8)
FONT_ICON    = ("Courier New", 11)
FONT_ICON_LG = ("Courier New", 13)


def fmt_ms(s):
    s = max(0, int(s))
    return f"{s // 60:02d}:{s % 60:02d}"


def fmt_hms(s):
    s = max(0, int(s))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


class StudyClock(tk.Tk):
    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=FG)

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

        self.update_idletasks()
        sw   = self.winfo_screenwidth()
        sh_p = self.winfo_screenheight()
        self.geometry(f"{W}x{H_BASE}+{sw - W - 20}+{sh_p - H_BASE - 60}")

        self.cv = tk.Canvas(self, width=W - 2, height=H_BASE - 2,
                            bg=BG, highlightthickness=0, bd=0)
        self.cv.pack(padx=1, pady=1)
        self.cv.bind("<ButtonPress-1>",   self._on_press)
        self.cv.bind("<B1-Motion>",       self._on_drag)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
        self.cv.bind("<ButtonRelease-3>", self._on_right_release)
        self.bind("<Escape>", lambda _e: self._quit())

        self._build()
        self._render()

    # ── Derived durations ────────────────────────────────────────────────────

    def _focus_secs(self):
        return (60 - self.break_mins) * 60

    def _break_secs(self):
        return self.break_mins * 60

    # ── Build static layout ──────────────────────────────────────────────────

    def _build(self):
        cv = self.cv
        self._draw_brackets()

        # Header: dynamic phase label left, ⚙ _ × right
        self._id_phase = cv.create_text(PAD_X, 18, text="STANDBY",
                                        font=FONT_LABEL, fill=FG, anchor="w",
                                        tags="main_ui")
        cv.create_text(W - PAD_X - 40, 18, text="⚙",
                       font=FONT_ICON, fill=FG, activefill=DIM,
                       anchor="center", tags=("main_ui", "btn_cfg"))
        self._draw_settings_icon(W - PAD_X - 40, 18)
        cv.create_text(W - PAD_X - 22, 22, text="_",
                       font=FONT_ICON, fill=FG, activefill=DIM,
                       anchor="center", tags=("main_ui", "btn_min"))
        cv.create_text(W - PAD_X - 4, 18, text="×",
                       font=FONT_ICON_LG, fill=FG, activefill=DIM,
                       anchor="center", tags=("main_ui", "btn_cls"))

        # Timer (current phase MM:SS)
        self._id_timer = cv.create_text(W // 2, 64, text="55:00",
                                        font=FONT_TIMER, fill=FG,
                                        anchor="center", tags="main_ui")

        # Progress bar (current phase)
        self._bar_y0 = BAR_Y0_NORMAL
        self._bar_y1 = BAR_Y1_NORMAL
        self._bar_x0 = PAD_X
        self._bar_x1 = W - PAD_X
        self._id_bar_outline = cv.create_rectangle(
            self._bar_x0, self._bar_y0,
            self._bar_x1, self._bar_y1,
            outline=FG, width=1, fill="", tags="bar")
        self._id_bar_fill = cv.create_rectangle(
            self._bar_x0 + 1, self._bar_y0 + 1,
            self._bar_x0 + 1, self._bar_y1 - 1,
            fill=FG, outline="", stipple="gray50", tags="bar")

        # Footer
        self._id_remaining = cv.create_text(
            PAD_X, 132, text="REMAINING 01:00:00",
            font=FONT_SMALL, fill=DIM, anchor="w", tags="main_ui")
        self._id_play = cv.create_text(
            W - PAD_X - 22, 132, text="▶", font=FONT_ICON,
            fill=FG, activefill=DIM, anchor="center",
            tags=("main_ui", "btn_play"))
        cv.create_text(
            W - PAD_X - 4, 132, text="■", font=FONT_ICON,
            fill=FG, activefill=DIM, anchor="center",
            tags=("main_ui", "btn_reset"))

    def _draw_brackets(self):
        cv = self.cv
        cv.delete("bracket")
        h = self._h_current - 2
        p, arm = BRACKET_INSET, BRACKET_ARM
        for x, y, dx, dy in [(p, p, 1, 1), (W - p - 2, p, -1, 1),
                              (p, h - p, 1, -1), (W - p - 2, h - p, -1, -1)]:
            cv.create_line(x, y, x + dx * arm, y, fill=FG, width=1, tags="bracket")
            cv.create_line(x, y, x, y + dy * arm, fill=FG, width=1, tags="bracket")

    def _draw_settings_icon(self, x, y):
        cv = self.cv
        tags = ("main_ui", "btn_cfg")

        # Invisible hit target keeps the hand-drawn icon easy to click.
        cv.create_rectangle(x - 8, y - 8, x + 8, y + 8,
                            fill=BG, outline="", tags=tags)

        cv.create_oval(x - 4, y - 4, x + 4, y + 4,
                       outline=FG, width=1, tags=tags)
        cv.create_oval(x - 1, y - 1, x + 1, y + 1,
                       outline=FG, width=1, tags=tags)
        cv.create_line(x, y - 7, x, y - 5, fill=FG, width=1, tags=tags)
        cv.create_line(x, y + 5, x, y + 7, fill=FG, width=1, tags=tags)
        cv.create_line(x - 7, y, x - 5, y, fill=FG, width=1, tags=tags)
        cv.create_line(x + 5, y, x + 7, y, fill=FG, width=1, tags=tags)
        cv.create_line(x - 5, y - 5, x - 4, y - 4, fill=FG, width=1, tags=tags)
        cv.create_line(x + 4, y - 4, x + 5, y - 5, fill=FG, width=1, tags=tags)
        cv.create_line(x - 5, y + 5, x - 4, y + 4, fill=FG, width=1, tags=tags)
        cv.create_line(x + 4, y + 4, x + 5, y + 5, fill=FG, width=1, tags=tags)

    # ── Render ───────────────────────────────────────────────────────────────

    def _render(self):
        cv = self.cv

        # Phase label
        label = {"idle": "STANDBY", "completed": "DONE"}.get(
            self.state,
            "FOCUS" if self.current_phase == "focus" else "BREAK")
        cv.itemconfig(self._id_phase, text=label)

        # Timer shows current phase countdown
        cv.itemconfig(self._id_timer, text=fmt_ms(self.time_left))

        # REMAINING: total session time left (or full session when idle)
        if self.state == "idle":
            remaining = self.study_hours * 3600
        elif self.state == "completed":
            remaining = 0
        else:
            remaining = self.total_left
        cv.itemconfig(self._id_remaining,
                      text=f"REMAINING {fmt_hms(remaining)}")

        # Progress bar: fraction of current phase elapsed
        pct = ((self.phase_total - self.time_left) / self.phase_total
               if self.phase_total > 0 else 0)
        bar_w = self._bar_x1 - self._bar_x0 - 2
        fill_x = self._bar_x0 + 1 + bar_w * pct
        cv.coords(self._id_bar_fill,
                  self._bar_x0 + 1, self._bar_y0 + 1,
                  fill_x, self._bar_y1 - 1)

        # Dim ▶ while running
        cv.itemconfig(self._id_play,
                      fill=DIM if self.state == "running" else FG)

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
        # if   tag == "btn_cls":   self._minimize()
        if   tag == "btn_cls":   self._quit()
        elif tag == "btn_cfg":   self._toggle_settings()
        elif tag == "btn_min":   self._enter_compact()
        elif tag == "btn_play":  self._toggle_play()
        elif tag == "btn_reset": self._reset()

    def _on_right_release(self, e):
        if self._hit_button(e.x, e.y) == "btn_cls":
            self._quit()

    def _hit_button(self, x, y):
        items = self.cv.find_closest(x, y)
        if not items:
            return None
        bbox = self.cv.bbox(items[0])
        if not bbox:
            return None
        bx0, by0, bx1, by1 = bbox
        if not (bx0 - 4 <= x <= bx1 + 4 and by0 - 4 <= y <= by1 + 4):
            return None
        for tag in self.cv.gettags(items[0]):
            if tag.startswith("btn_"):
                return tag
        return None

    def _quit(self):
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

    def _play_chime(self):
        try:
            winmm = ctypes.windll.winmm
            path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), CHIME_FILE)
            winmm.mciSendStringW("close chime", None, 0, 0)
            winmm.mciSendStringW(
                f'open "{path}" type mpegvideo alias chime', None, 0, 0)
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
        if self.state == "running":
            self._pause()
        else:
            self._start()

    def _start(self):
        if self.state == "completed":
            return
        if self.settings_open:
            self._close_settings()
        if self.state == "idle":
            self._init_session()
        self.state = "running"
        if self.timer_id:
            self.after_cancel(self.timer_id)
        self.timer_id = self.after(1000, self._tick)
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
        self.state = "idle"
        if self.timer_id:
            self.after_cancel(self.timer_id)
            self.timer_id = None
        if self.flash_id:
            self.after_cancel(self.flash_id)
            self.flash_id = None
        self._stop_chime()
        self.cv.itemconfig(self._id_timer, fill=FG)
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
        self.time_left = self.phase_total

    # ── Flash on completion ──────────────────────────────────────────────────

    def _begin_flash(self):
        self.flash_count = 0
        self._flash_step()

    def _flash_step(self):
        on = self.flash_count % 2 == 0
        self.cv.itemconfig(self._id_timer, fill=BG if on else FG)
        self.flash_count += 1
        if self.flash_count >= 6:
            self.cv.itemconfig(self._id_timer, fill=FG)
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
        self._bar_y0 = BAR_Y0_COMPACT
        self._bar_y1 = BAR_Y1_COMPACT
        self.cv.coords(self._id_bar_outline,
                       self._bar_x0, self._bar_y0,
                       self._bar_x1, self._bar_y1)
        self._draw_brackets()
        self._render()

    def _exit_compact(self):
        if not self.compact_open:
            return
        self.compact_open = False
        self._h_current   = H_BASE
        self.geometry(f"{W}x{H_BASE}+{self.winfo_x()}+{self.winfo_y()}")
        self.cv.configure(height=H_BASE - 2)
        self.cv.itemconfig("main_ui", state="normal")
        self._bar_y0 = BAR_Y0_NORMAL
        self._bar_y1 = BAR_Y1_NORMAL
        self.cv.coords(self._id_bar_outline,
                       self._bar_x0, self._bar_y0,
                       self._bar_x1, self._bar_y1)
        self._draw_brackets()
        self._render()

    # ── Inline settings panel ────────────────────────────────────────────────

    def _toggle_settings(self):
        if self.settings_open:
            self._close_settings()
        elif self.state in ("idle", "completed"):
            self._open_settings()

    def _open_settings(self):
        self.settings_open = True
        self._h_current = H_BASE + H_SETTINGS
        self.geometry(f"{W}x{self._h_current}"
                      f"+{self.winfo_x()}+{self.winfo_y()}")
        self.cv.configure(height=self._h_current - 2)
        self._draw_brackets()

        cv  = self.cv
        sy0 = H_BASE - 4
        sy1 = sy0 + H_SETTINGS - 8
        cv.create_rectangle(PAD_X, sy0, W - PAD_X, sy1,
                            outline=FG, width=1, fill="", tags="settings")

        cv.create_text(PAD_X + 8, sy0 + 18, text="SESSION (H)",
                       font=FONT_SMALL, fill=DIM, anchor="w", tags="settings")
        cv.create_text(PAD_X + 8, sy0 + 46, text="BREAK (MIN)",
                       font=FONT_SMALL, fill=DIM, anchor="w", tags="settings")

        self._sh_var = tk.StringVar(value=str(self.study_hours))
        self._bm_var = tk.StringVar(value=str(self.break_mins))

        ekw = dict(bg=BG, fg=FG, insertbackground=FG, relief="solid", bd=1,
                   highlightthickness=0, font=FONT_SMALL, justify="center",
                   width=5)
        self._sh_entry = tk.Entry(self, textvariable=self._sh_var, **ekw)
        self._bm_entry = tk.Entry(self, textvariable=self._bm_var, **ekw)
        for entry in (self._sh_entry, self._bm_entry):
            entry.bind("<FocusOut>", self._apply_settings)
            entry.bind("<Return>",   self._apply_settings)

        cv.create_window(W - PAD_X - 12, sy0 + 18, anchor="e",
                         window=self._sh_entry, tags="settings")
        cv.create_window(W - PAD_X - 12, sy0 + 46, anchor="e",
                         window=self._bm_entry, tags="settings")
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
        self._h_current = H_BASE
        self.geometry(f"{W}x{H_BASE}+{self.winfo_x()}+{self.winfo_y()}")
        self.cv.configure(height=H_BASE - 2)
        self._draw_brackets()
        self._render()

    def _commit_settings(self):
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
        rv.configure(bg=FG)
        rv.geometry(f"{rw}x{rh}+{x + W - rw}+{y}")
        inner = tk.Frame(rv, bg=BG)
        inner.pack(padx=1, pady=1, fill="both", expand=True)
        lbl = tk.Label(inner, text="FOCUS", font=FONT_SMALL,
                       bg=BG, fg=FG, cursor="hand2")
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
