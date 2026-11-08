"""Runs against the real project, not a temp dir."""
import unittest
from pathlib import Path

from tmreg import catalog, config, dfd

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ({f"E{i}" for i in range(1, 7)} | {f"P{i}" for i in range(1, 9)}
            | {f"D{i}" for i in range(1, 7)} | {f"F{i}" for i in range(1, 31)}
            | {f"TB{i}" for i in range(1, 7)})


class ReferenceSystemTest(unittest.TestCase):
    def test_dfd_has_every_reference_id(self):
        d = dfd.load(ROOT / "systems/ordering-platform/dfd.md")
        self.assertEqual(d.version, "1.0")
        self.assertEqual(d.all_ids(), EXPECTED)

    def test_every_catalog_threat_cites_known_ids(self):
        # Needs a local project.toml and the threat-model-framework guide beside this repo;
        # a fresh clone without them skips rather than fails.
        try:
            cfg = config.load_project(ROOT)
        except config.ConfigError as e:
            self.skipTest(f"needs project.toml and the threat-model-framework guide: {e}")
        rows = catalog.parse(
            (cfg.framework_path / "docs/reference/reference-system.md").read_text())
        self.assertEqual(len(rows), 44)  # T-01..T-36, PT-01..PT-08
        for r in rows:
            with self.subTest(id=r.id):
                self.assertLessEqual(set(r.elements), EXPECTED)


if __name__ == "__main__":
    unittest.main()
