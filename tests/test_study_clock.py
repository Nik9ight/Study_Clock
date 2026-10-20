"""Desktop integration checks: python -m unittest discover -s tests -v."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import study_clock


class StudyClockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.prefs = Path(self.temp.name) / "preferences.json"
        self.preference_patch = patch.object(study_clock, "PREFERENCES_FILE", self.prefs)
        self.preference_patch.start()
        self.addCleanup(self.preference_patch.stop)
        self.app = study_clock.StudyClock()
        self.app.withdraw()
        self.app.update_idletasks()
        self.addCleanup(self.app._quit)

    def test_clock_and_themes_preserve_running_session(self):
        app = self.app
        app._start()
        timer_id, remaining = app.timer_id, app.time_left
        app._set_view("clock")
        for theme in study_clock.THEMES:
            app._set_theme(theme)
            self.assertEqual(app.cv.cget("bg"), study_clock.THEMES[theme]["bg"])
            self.assertEqual(app.time_left, remaining)
            self.assertEqual(app.timer_id, timer_id)
            self.assertEqual(app.state, "running")
            self.assertRegex(app.cv.itemcget(app._id_timer, "text"), r"\d{2}:\d{2}:\d{2}")
        self.assertEqual(json.loads(self.prefs.read_text())["theme"], "Forest")
        app._set_view("timer")
        app._pause()
        self.assertIsNone(app.timer_id)
        self.assertEqual(app.cv.itemcget(app._id_play, "text"), "Resume")
        app._reset()
        self.assertEqual(app.time_left, 55 * 60)

    def test_settings_validation_and_theme_refresh(self):
        app = self.app
        app._open_settings()
        app._sh_var.set("99")
        app._bm_var.set("12")
        app._apply_settings()
        self.assertEqual((app.study_hours, app.break_mins), (3, 10))
        app._set_theme("Paper")
        self.assertTrue(app.settings_open)
        self.assertEqual(app._sh_entry.cget("bg"), study_clock.THEMES["Paper"]["surface"])
        app._start()
        self.assertFalse(app.settings_open)
        app._toggle_settings()
        self.assertTrue(app.settings_open)
        self.assertEqual(app._sh_entry.cget("state"), "disabled")
        app._sh_var.set("1")
        app._commit_settings()
        self.assertEqual(app.study_hours, 3)
        app._reset()
        self.assertEqual(app._sh_entry.cget("state"), "normal")

    def test_phase_completion_and_compact_restore(self):
        app = self.app
        app.state = "running"
        app.time_left = 1
        app.total_left = 301
        app._tick()
        self.assertEqual(app.current_phase, "break")
        self.assertEqual(app.time_left, 300)
        app.after_cancel(app.timer_id)
        app.timer_id = None
        app._set_view("clock")
        app._enter_compact()
        app.time_left = app.total_left = 1
        app._tick()
        self.assertEqual(app.state, "completed")
        self.assertFalse(app.compact_open)
        self.assertEqual(app.view_mode, "timer")
        self.assertIsNotNone(app.flash_id)
        app._reset()
        self.assertIsNone(app.flash_id)
        self.assertEqual(app.cv.itemcget(app._id_timer, "fill"), app.colors["fg"])

    def test_button_targets_and_text_fit(self):
        app = self.app
        for tag in ("btn_timer", "btn_clock", "btn_play", "btn_reset",
                    "btn_cfg", "btn_cls", "btn_hide", "btn_min"):
            rectangle, text = app.cv.find_withtag(tag)
            x0, y0, x1, y1 = app.cv.bbox(rectangle)
            self.assertEqual(app._hit_button((x0 + x1) / 2, (y0 + y1) / 2), tag)
            tx0, ty0, tx1, ty1 = app.cv.bbox(text)
            self.assertGreaterEqual(tx0, x0)
            self.assertLessEqual(tx1, x1)
            self.assertGreaterEqual(ty0, y0)
            self.assertLessEqual(ty1, y1)
        self.assertIsNone(app._hit_button(10, 200))
        app._enter_compact()
        self.assertIsNone(app._hit_button(170, 330))
        app._exit_compact()
        self.assertEqual(app._hit_button(170, 330), "btn_play")

    def test_progress_styles_preserve_session_and_fit_compact_view(self):
        app = self.app
        app._start()
        app.time_left = 1914  # 42% of the 55-minute focus phase elapsed.
        timer_id = app.timer_id
        for style in study_clock.PROGRESS_STYLES:
            app._set_progress_style(style)
            self.assertEqual((app.time_left, app.timer_id, app.state), (1914, timer_id, "running"))
            percent = app.cv.find_withtag("bar_percent")[0]
            self.assertEqual(app.cv.itemcget(percent, "text"), "42%")
            for compact in (True, False):
                app._enter_compact() if compact else app._exit_compact()
                x0, y0, x1, y1 = app.cv.bbox("bar")
                self.assertGreaterEqual(x0, 0)
                self.assertGreaterEqual(y0, 0)
                self.assertLessEqual(x1, study_clock.W)
                self.assertLessEqual(y1, study_clock.H_COMPACT if compact else 380)
                if compact:
                    track = app.cv.bbox("bar_track")
                    self.assertGreaterEqual(track[2] - track[0], study_clock.W - 2 * study_clock.COMPACT_PAD_X - 20)
                    status = app.cv.bbox("bar_status")
                    remaining = app.cv.bbox("bar_remaining")
                    percent_box = app.cv.bbox("bar_percent")
                    self.assertLess(track[3], remaining[1])
                    self.assertLess(status[2], remaining[0])
                    self.assertLess(remaining[2], percent_box[0])
        app._pause()
        self.assertEqual(app.cv.itemcget(app._id_phase, "text"), "PAUSED")
        app._enter_compact()
        app._set_theme("Paper")
        self.assertEqual(app.cv.itemcget(app._id_play, "state"), "hidden")
        self.assertEqual(app.progress_style, "Segments")
        app._exit_compact()
        prefs = json.loads(self.prefs.read_text())
        self.assertEqual(prefs["progress_style"], "Segments")
        app.progress_style = "Installer"
        app._load_preferences()
        self.assertEqual(app.progress_style, "Segments")

    def test_progress_empty_and_complete(self):
        app = self.app
        for style in study_clock.PROGRESS_STYLES:
            app._set_progress_style(style)
            for remaining, percent in ((app.phase_total, "0%"), (1, "99%"), (0, "100%")):
                app.time_left = remaining
                app._render()
                self.assertEqual(app.cv.itemcget(app.cv.find_withtag("bar_percent")[0], "text"), percent)
                if style == "Installer":
                    text = app.cv.itemcget(app.cv.find_withtag("bar_installer")[0], "text")
                    self.assertEqual(len(text), 30)
                    expected = int((app.phase_total - remaining) / app.phase_total * 28)
                    self.assertEqual(text, "[" + "█" * expected + "░" * (28 - expected) + "]")
                if remaining == 0:
                    if style == "ASCII":
                        text = app.cv.itemcget(app.cv.find_withtag("bar_ascii")[0], "text")
                        self.assertEqual(text, "[" + "=" * 30 + "]")
                    else:
                        self.assertEqual(len(app.cv.find_withtag("bar_empty")), 0)
                elif remaining == app.phase_total:
                    self.assertEqual(len(app.cv.find_withtag("bar_filled")), 0)

    def test_choice_menus_and_active_tab(self):
        app = self.app
        app._open_settings()
        with patch("tkinter.Menu.tk_popup"):
            app._show_choice_menu("btn_style", study_clock.PROGRESS_STYLES,
                                  app.progress_style, app._set_progress_style)
        app._choice_menu.invoke(1)
        app._choice_menu.unpost()
        self.assertEqual(app.progress_style, "ASCII")
        with patch("tkinter.Menu.tk_popup"):
            app._show_choice_menu("btn_theme", study_clock.THEMES, app.theme_name, app._set_theme)
        app._choice_menu.invoke(1)
        app._choice_menu.unpost()
        self.assertEqual(app.theme_name, "Paper")
        app._close_settings()
        app._set_view("clock")
        clock_background = app.cv.find_withtag("btn_clock")[0]
        timer_background = app.cv.find_withtag("btn_timer")[0]
        self.assertEqual(app.cv.itemcget(clock_background, "fill"), app.colors["bg"])
        self.assertEqual(app.cv.itemcget(timer_background, "fill"), app.colors["surface"])

    def test_customize_panel_preserves_timer_and_closes_with_escape(self):
        app = self.app
        self.assertFalse(app.cv.find_withtag("btn_theme"))
        self.assertFalse(app.cv.find_withtag("btn_format"))
        app._start()
        remaining, timer_id = app.time_left, app.timer_id
        app._toggle_settings()
        self.assertTrue(app.settings_open)
        self.assertEqual(app._h_current, study_clock.H_BASE)
        self.assertFalse(app.cv.find_withtag("bar"))
        self.assertEqual(app.cv.itemcget(app._id_play, "state"), "hidden")
        self.assertIsNone(app._hit_button(170, 330))
        self.assertEqual(app._sh_entry.cget("state"), "disabled")
        for tag in ("btn_theme", "btn_style", "btn_format", "btn_done"):
            shape, text = app.cv.find_withtag(tag)
            x0, y0, x1, y1 = app.cv.bbox(shape)
            self.assertEqual(app._hit_button((x0 + x1) / 2, (y0 + y1) / 2), tag)
            tx0, ty0, tx1, ty1 = app.cv.bbox(text)
            self.assertTrue(x0 <= tx0 < tx1 <= x1)
            self.assertTrue(y0 <= ty0 < ty1 <= y1)
        app._set_theme("Forest")
        app._set_progress_style("ASCII")
        app._on_space(None)
        self.assertEqual((app.time_left, app.timer_id, app.state), (remaining, timer_id, "running"))
        self.assertTrue(app.settings_open)
        app._on_escape()
        self.assertFalse(app.settings_open)
        self.assertFalse(app.cv.find_withtag("btn_theme"))
        self.assertTrue(app.cv.find_withtag("bar_ascii"))
        self.assertEqual(app.cv.itemcget(app._id_play, "state"), "normal")
        self.assertEqual(app.state, "running")
        app._open_settings()
        app._enter_compact()
        self.assertFalse(app.settings_open)
        self.assertTrue(app.compact_open)

    def test_legacy_and_invalid_style_preferences(self):
        app = self.app
        self.prefs.write_text('{"theme": "Paper", "use_24_hour": false}')
        app._load_preferences()
        self.assertEqual(app.progress_style, "Installer")
        self.assertEqual(app.theme_name, "Paper")
        self.assertFalse(app.use_24_hour)
        self.prefs.write_text('{"progress_style": "unknown"}')
        app._load_preferences()
        self.assertEqual(app.progress_style, "Installer")

    def test_minimize_and_revive(self):
        app = self.app
        app._start()
        app._minimize()
        self.assertEqual(app.state, "paused")
        self.assertIsNotNone(app._revive_win)
        app._revive_main()
        app.withdraw()
        self.assertIsNone(app._revive_win)


if __name__ == "__main__":
    unittest.main()
