import tempfile
import unittest
from pathlib import Path

from tmreg import config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def project(self, text, fw=True):
        (self.root / "project.toml").write_text(text)
        if fw:
            (self.root / "fw").mkdir(exist_ok=True)

    def system(self, text, slug="demo"):
        d = self.root / "systems" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "system.toml").write_text(text)

    def test_project_defaults_and_resolution(self):
        self.project('framework_path = "fw"\nreviewer_name = "R"\n')
        cfg = config.load_project(self.root)
        self.assertEqual(cfg.framework_path, (self.root / "fw").resolve())
        self.assertEqual(cfg.origins, config.DEFAULT_ORIGINS)
        self.assertEqual(cfg.reviewer_name, "R")
        self.assertEqual(cfg.reviewer_email, "")

    def test_project_errors(self):
        self.project('framework_path = "fw"\nreviewer_name = "R"\n', fw=False)
        with self.assertRaisesRegex(config.ConfigError, "framework_path"):
            config.load_project(self.root)
        self.project('framework_path = "fw"\nreviewer_name = ""\n')
        with self.assertRaisesRegex(config.ConfigError, "reviewer_name"):
            config.load_project(self.root)
        self.project('framework_path = "fw"\nreviewer_name = "R"\norigins = ["a", "a"]\n')
        with self.assertRaisesRegex(config.ConfigError, "origins"):
            config.load_project(self.root)

    def test_system_effective_methods(self):
        self.system('name = "Demo"\npersonal_data_classes = ["PII"]\n')
        s = config.load_system(self.root, "demo")
        self.assertEqual(s.effective_methods, ("stride-per-element", "linddun"))
        self.assertEqual(s.methods, ("stride-per-element",))

    def test_effective_methods_no_duplicate(self):
        self.system('name = "Demo"\nmethods = ["linddun"]\npersonal_data_classes = ["PII"]\n')
        self.assertEqual(config.load_system(self.root, "demo").effective_methods, ("linddun",))

    def test_unknown_method_rejected(self):
        self.system('name = "Demo"\nmethods = ["pasta"]\n')
        with self.assertRaisesRegex(config.ConfigError, "pasta"):
            config.load_system(self.root, "demo")

    def test_system_name_required(self):
        self.system('owner = "x"\n')
        with self.assertRaisesRegex(config.ConfigError, "name"):
            config.load_system(self.root, "demo")


if __name__ == "__main__":
    unittest.main()
