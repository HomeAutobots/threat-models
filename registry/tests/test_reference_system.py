"""Runs against the real project, not a temp dir: the reference system's tracked workspace.dsl,
and the guide's threat catalog it must cover."""
import unittest
from pathlib import Path

from tmreg import c4, catalog, config

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "systems/ordering-platform/workspace.dsl"
# Every ID of the guide's old DFD: its level-1 diagram and its extensions.
EXPECTED = ({f"E{i}" for i in range(1, 7)} | {f"P{i}" for i in range(1, 9)}
            | {f"D{i}" for i in range(1, 7)} | {f"F{i}" for i in range(1, 31)}
            | {f"TB{i}" for i in range(1, 7)})


def _model():
    return c4.parse(WORKSPACE.read_bytes())


class ReferenceSystemTest(unittest.TestCase):
    def test_reference_workspace_is_clean(self):
        self.assertEqual(c4.problems(_model()), [])

    def test_every_old_id_is_claimed(self):
        self.assertEqual(len(EXPECTED), 56)
        self.assertEqual(set(c4.was_map(c4.to_record(_model()))), EXPECTED)

    def test_every_catalog_citation_maps(self):
        # Needs a local project.toml and the threat-model-framework guide beside this repo;
        # a fresh clone without them skips rather than fails.
        try:
            cfg = config.load_project(ROOT)
        except config.ConfigError as e:
            self.skipTest(f"needs project.toml and the threat-model-framework guide: {e}")
        rows = catalog.parse(
            (cfg.framework_path / "docs/reference/reference-system.md").read_text())
        self.assertEqual(len(rows), 44)  # T-01..T-36, PT-01..PT-08
        claimed = c4.was_map(c4.to_record(_model()))
        for r in rows:
            with self.subTest(id=r.id):
                self.assertTrue(r.elements)
                self.assertLessEqual(set(r.elements), set(claimed))


if __name__ == "__main__":
    unittest.main()
