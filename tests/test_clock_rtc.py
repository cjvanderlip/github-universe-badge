"""Regression tests for the Clock app's RTC sync and display paths."""

import ast
from pathlib import Path
import types
import unittest
from unittest.mock import Mock


APP = Path(__file__).resolve().parents[1] / "badge/apps/clock/__init__.py"


class ClockRTCTests(unittest.TestCase):
    def setUp(self):
        source = ast.parse(APP.read_text())
        functions = [
            node for node in source.body
            if isinstance(node, ast.FunctionDef) and node.name in ("update_time", "display_time")
        ]
        self.rtc = Mock()
        self.ntptime = Mock()
        self.time = Mock()
        self.time.gmtime.side_effect = [
            (2026, 11, 7, 12, 0, 0, 5, 311),
            (2026, 11, 7, 5, 0, 0, 5, 311),
        ]
        self.time.mktime.return_value = 100000
        self.daylight = Mock()
        self.daylight.localtime.return_value = 74800
        self.policy = Mock()
        self.draw_text = Mock()
        self.draw_dots = Mock()
        self.image = Mock()
        self.font = types.SimpleNamespace(sins=Mock())
        self.screen = Mock()
        self.namespace = {
            "RTC": lambda: self.rtc,
            "ntptime": self.ntptime,
            "time": self.time,
            "regions": {"us": (0, 2, 3, 6, 2, 1, 11, 6, 2, 60)},
            "DaylightSavingPolicy": self.policy,
            "DaylightSaving": Mock(return_value=self.daylight),
            "DisplayType": types.SimpleNamespace(textclock=1, dotsclock=2, nixie=3, sevenseg=4),
            "state": {"clock_style": 1, "dark_mode": True},
            "draw_text_clock": self.draw_text,
            "draw_dots_clock": self.draw_dots,
            "draw_nixie_clock": Mock(),
            "draw_sevenseg_clock": Mock(),
            "image": self.image,
            "screen": self.screen,
            "nixie_font": self.font.sins,
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(APP), "exec"), self.namespace)

    def test_sync_sets_machine_rtc_with_correct_weekday_and_local_time(self):
        self.assertTrue(self.namespace["update_time"]("us", -7))
        self.ntptime.settime.assert_called_once_with()
        self.policy.assert_any_call(0, 2, 3, 6, 2, -360)
        self.policy.assert_any_call(0, 1, 11, 6, 2, -420)
        self.daylight.localtime.assert_called_once_with(100000)
        self.rtc.datetime.assert_called_once_with((2026, 11, 7, 5, 5, 0, 0, 0))

    def test_ntp_failure_does_not_update_rtc(self):
        self.ntptime.settime.side_effect = OSError("NTP failed")
        self.assertFalse(self.namespace["update_time"]("us", -7))
        self.rtc.datetime.assert_not_called()

    def test_all_clock_faces_receive_expected_time_tuple(self):
        self.rtc.datetime.return_value = (2026, 11, 7, 5, 5, 42, 33, 0)
        expected = (2026, 11, 7, 5, 42, 33, 5)
        for style, name in ((1, "draw_text_clock"), (2, "draw_dots_clock"),
                            (3, "draw_nixie_clock"), (4, "draw_sevenseg_clock")):
            with self.subTest(style=style):
                self.namespace["state"]["clock_style"] = style
                self.namespace["display_time"]()
                self.namespace[name].assert_called_once_with(expected)


if __name__ == "__main__":
    unittest.main()
