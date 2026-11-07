"""Regression tests for Settings persistence on badge and simulator."""

import builtins
import errno
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock


APP = Path(__file__).resolve().parents[1] / "badge/apps/settings/__init__.py"


class MicroPythonFile:
    """Expose the subset of file methods supported by MicroPython."""

    def __init__(self, path, mode):
        self.file = open(path, mode)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self.file.__exit__(*args)

    def readlines(self):
        return self.file.readlines()

    def write(self, text):
        return self.file.write(text)

    def flush(self):
        return self.file.flush()


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        directory = Path(self.temp.name)
        self.root = directory / "secrets.py"
        self.system = directory / "system-secrets.py"
        self.temporary = directory / "secrets.py.tmp"
        self.secrets = types.SimpleNamespace(
            WIFI_SSID="original",
            WIFI_PASSWORD="password",
            GITHUB_USERNAME="octocat",
            GITHUB_TOKEN="token",
            REGION="eu",
            TIMEZONE=0,
        )
        self.screen = Mock()
        self.screen.measure_text.return_value = (20, 10)
        self.badge = Mock()
        self.badge.ticks = 100
        self.badge.pressed.return_value = False
        self.os = types.SimpleNamespace(rename=__import__("os").rename, remove=__import__("os").remove)
        self.modules = {
            "os": self.os,
            "hints": types.SimpleNamespace(Style=Mock(), hint_width=Mock(return_value=10), draw_hint=Mock()),
            "badgeware": types.SimpleNamespace(get_backlight=lambda: 50, set_backlight=Mock()),
            "secrets": self.secrets,
        }
        self.namespace = {
            "__name__": "settings_under_test",
            "__builtins__": dict(vars(builtins), __import__=self.import_module, open=MicroPythonFile),
            "badge": self.badge,
            "screen": self.screen,
            "image": types.SimpleNamespace(X2=2),
            "color": types.SimpleNamespace(rgb=lambda *args: args),
            "font": types.SimpleNamespace(**{name: name for name in (
                "salty", "corset", "ziplock", "sins", "ignore", "yesterday"
            )}),
            "run": Mock(),
            "reset": Mock(),
            "HIRES": 1,
            "VSYNC": 2,
            **{name: name for name in (
                "BUTTON_LEFT", "BUTTON_RIGHT", "BUTTON_UP", "BUTTON_DOWN",
                "BUTTON_SELECT", "BUTTON_BACK", "BUTTON_MENU", "BUTTON_HOME"
            )},
        }
        exec(compile(APP.read_text(), str(APP), "exec"), self.namespace)
        self.namespace.update(
            SECRETS_FILE=str(self.root),
            TEMP_SECRETS_FILE=str(self.temporary),
            SYSTEM_SECRETS_FILE=str(self.system),
        )
        self.system.write_text(
            "# Existing configuration\n"
            "WIFI_SSID = 'original'\n"
            "WIFI_PASSWORD = 'password'\n"
            "GITHUB_USERNAME = 'octocat'\n"
            "GITHUB_TOKEN = 'token'\n"
            "REGION = 'eu'\n"
            "TIMEZONE = 0\n"
            "CUSTOM = ('first',\n"
            "          'second')\n"
        )

    def import_module(self, name, globals=None, locals=None, fromlist=(), level=0):
        if name in self.modules:
            return self.modules[name]
        return builtins.__import__(name, globals, locals, fromlist, level)

    def save(self, key, value):
        self.namespace["save_value"](key, value)

    def reboot_values(self):
        result = {}
        exec(compile(self.root.read_text(), str(self.root), "exec"), result)
        return result

    def test_first_save_preserves_system_settings_and_extra_values(self):
        self.save("WIFI_SSID", "new 'network'\nline")
        values = self.reboot_values()
        self.assertEqual(values["WIFI_SSID"], "new 'network'\nline")
        self.assertEqual(values["WIFI_PASSWORD"], "password")
        self.assertEqual(values["GITHUB_USERNAME"], "octocat")
        self.assertEqual(values["GITHUB_TOKEN"], "token")
        self.assertEqual((values["REGION"], values["TIMEZONE"]), ("eu", 0))
        self.assertEqual(values["CUSTOM"], ("first", "second"))
        self.assertIn("# Existing configuration", self.root.read_text())
        self.assertEqual(self.secrets.WIFI_SSID, values["WIFI_SSID"])
        self.assertFalse(self.temporary.exists())

    def test_repeated_edits_preserve_overrides_and_do_not_accumulate(self):
        self.save("WIFI_SSID", "one")
        self.save("REGION", "us")
        self.save("TIMEZONE", -7)
        self.save("WIFI_SSID", "two")
        values = self.reboot_values()
        self.assertEqual((values["WIFI_SSID"], values["REGION"], values["TIMEZONE"]), ("two", "us", -7))
        source = self.root.read_text()
        self.assertEqual(source.count("# Settings app overrides"), 1)
        self.assertNotIn("WIFI_SSID = 'one'", source)

    def test_existing_root_configuration_is_preserved(self):
        self.root.write_text("WIFI_SSID = ('a'\n             'b')\nCUSTOM = 42")
        self.save("WIFI_SSID", "new")
        values = self.reboot_values()
        self.assertEqual(values["WIFI_SSID"], "new")
        self.assertEqual(values["CUSTOM"], 42)
        self.assertNotIn("GITHUB_TOKEN", values)

    def test_failed_rename_keeps_original_and_current_values(self):
        self.root.write_text("WIFI_SSID = 'original'\nCUSTOM = 42\n")
        original = self.root.read_bytes()
        self.os.rename = Mock(side_effect=OSError(errno.EIO, "rename failed"))
        settings = self.namespace["SettingsList"](self.namespace["load_values"]())
        self.assertFalse(settings.edited("WIFI_SSID", "new"))
        self.assertEqual(self.root.read_bytes(), original)
        self.assertEqual(settings.values["WIFI_SSID"], "original")
        self.assertEqual(self.secrets.WIFI_SSID, "original")
        self.assertIsNotNone(settings.save_error)
        self.assertFalse(settings.apply_pending)
        self.assertFalse(self.temporary.exists())

    def test_interrupted_write_does_not_replace_active_configuration(self):
        self.root.write_text("WIFI_SID = 'original'\nCUSTOM = 42\n")
        original = self.root.read_bytes()

        class FailingFile(MicroPythonFile):
            def write(self, text):
                super().write(text[:2])
                raise OSError(errno.ENOSPC, "disk full")

        def open_file(path, mode):
            return FailingFile(path, mode) if mode == "w" else MicroPythonFile(path, mode)

        self.namespace["__builtins__"]["open"] = open_file
        settings = self.namespace["SettingsList"](self.namespace["load_values"]())
        self.assertFalse(settings.edited("WIFI_SSID", "new"))
        self.assertEqual(self.root.read_bytes(), original)
        self.assertEqual(self.secrets.WIFI_SSID, "original")
        self.assertFalse(self.temporary.exists())

    def test_read_permission_failure_does_not_fall_back_to_system(self):
        self.root.write_text("WIFI_SSID = 'original'\n")
        original = self.root.read_bytes()

        def open_file(path, mode):
            if path == str(self.root) and mode == "r":
                raise OSError(errno.EACCES, "permission denied")
            return MicroPythonFile(path, mode)

        self.namespace["__builtins__"]["open"] = open_file
        with self.assertRaises(OSError):
            self.save("WIFI_SSID", "new")
        self.assertEqual(self.root.read_bytes(), original)
        self.assertFalse(self.temporary.exists())

    def test_missing_system_file_fails_without_creating_partial_root(self):
        self.system.unlink()
        settings = self.namespace["SettingsList"](self.namespace["load_values"]())
        self.assertFalse(settings.edited("WIFI_SSID", "new"))
        self.assertFalse(self.root.exists())
        self.assertEqual(self.secrets.WIFI_SSID, "original")

    def test_invalid_inputs_are_not_persisted(self):
        for key, value in (("REGION", "unknown"), ("TIMEZONE", -13), ("TIMEZONE", 15),
                           ("TIMEZONE", True), ("TIMEZONE", "0"), ("UNKNOWN", "value")):
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    self.save(key, value)
        self.assertFalse(self.root.exists())

    def test_simulator_uses_its_settings_storage(self):
        saved = {}

        def simulator_save(values):
            saved.update(values)
            for key, value in values.items():
                setattr(self.secrets, key, value)

        self.secrets.save = simulator_save
        self.save("TIMEZONE", -7)
        self.assertEqual(saved, {"TIMEZONE": -7})
        self.assertEqual(self.secrets.TIMEZONE, -7)
        self.assertFalse(self.root.exists())
        self.assertFalse(self.temporary.exists())

    def test_region_save_error_is_visible(self):
        self.secrets.save = Mock(side_effect=OSError(errno.EIO, "save failed"))
        settings = self.namespace["SettingsList"](self.namespace["load_values"]())
        self.assertFalse(settings.edited("REGION", "us"))
        editor = self.namespace["RegionEditor"](settings, "REGION", "Region", "eu")
        editor.draw()
        self.assertTrue(any(call.args[0] == "save failed" for call in self.screen.text.call_args_list))

    def test_simulator_save_error_is_visible_and_does_not_update_ui(self):
        self.secrets.save = Mock(side_effect=OSError(errno.EIO, "save failed"))
        settings = self.namespace["SettingsList"](self.namespace["load_values"]())
        self.assertFalse(settings.edited("TIMEZONE", -7))
        self.assertEqual(settings.values["TIMEZONE"], 0)
        self.assertIsNotNone(settings.save_error)
        editor = self.namespace["TimezoneEditor"](settings, "TIMEZONE", "Timezone", 0)
        editor.draw()
        self.assertTrue(any(call.args[0] == "save failed" for call in self.screen.text.call_args_list))


if __name__ == "__main__":
    unittest.main()
