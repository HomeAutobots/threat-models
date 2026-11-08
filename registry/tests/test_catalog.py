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


if __name__ == "__main__":
    unittest.main()
