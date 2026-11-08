import unittest

from helpers import SAMPLE_CATALOG
from tmreg import catalog


class CatalogTest(unittest.TestCase):
    def test_parse_and_title(self):
        rows = catalog.parse(SAMPLE_CATALOG)
        self.assertEqual([r.id for r in rows], ["T-01", "T-02", "PT-01"])
        self.assertEqual((rows[0].elements, rows[0].category), (["E1", "F1"], "S"))
        self.assertEqual(rows[2].category, "Linking")
        self.assertLessEqual(len(catalog.title_for("word " * 60)), 120)

    def test_missing_section(self):
        with self.assertRaises(catalog.CatalogError):
            catalog.parse("# nothing")

    def test_duplicate_id(self):
        text = SAMPLE_CATALOG.replace("| T-02 |", "| T-01 |")
        with self.assertRaises(catalog.CatalogError):
            catalog.parse(text)

    def test_malformed_rows_raise(self):
        for bad in ("| T-02 | P2 | T |",
                    "| PT-01 | | | |",
                    "| T-02 | P2 | T | text | extra |",
                    "| T-02 | , | T | text |"):
            text = SAMPLE_CATALOG.replace(
                "| PT-01 | D1 | Linking |", bad + "\n| PT-01 | D1 | Linking |", 1)
            with self.subTest(bad=bad), self.assertRaisesRegex(catalog.CatalogError, "needs ID"):
                catalog.parse(text.replace("| T-02 | F2, P2 | T |", "| T-03 | F2 | T |", 1)
                              if "T-02" in bad else text)


if __name__ == "__main__":
    unittest.main()
