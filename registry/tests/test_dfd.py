import hashlib
import re
import unittest

from tmreg import dfd

DFD = b"""| Field | Value |
|---|---|
| DFD version | 1.0 |

```mermaid
flowchart LR
  | ID | not a table |
```

| ID | Element | Type |
|---|---|---|
| E1 | Customer | External entity |
| P1 | Web | Process |
| P2 | Gateway | Process |
| D1 | DB | Data store |

| ID | From | To | Label |
|---|---|---|---|
| F1 | E1 | P1 | HTTPS |
| F2 | P1 | P2 (via CDN) | REST |
| F3 | P2 | D1 | SQL |

| ID | Boundary | What enforces it |
|---|---|---|
| TB1 | Internet to edge | WAF |

| Class | Examples |
|---|---|
| PII | name |
"""


class DfdTest(unittest.TestCase):
    def test_parses_version_ids_and_hash(self):
        d = dfd.parse(DFD)
        self.assertEqual(d.version, "1.0")
        self.assertEqual(d.ids["F"], ["F1", "F2", "F3"])
        self.assertEqual(d.all_ids(), {"E1", "P1", "P2", "D1", "F1", "F2", "F3", "TB1"})
        self.assertEqual(d.sha256, hashlib.sha256(DFD).hexdigest())

    def test_numeric_sort(self):
        data = DFD + b"\n| ID | From | To |\n|---|---|---|\n| F10 | P1 | P2 |\n"
        self.assertEqual(dfd.parse(data).ids["F"], ["F1", "F2", "F3", "F10"])

    def test_errors(self):
        cases = {
            b"| ID | X |\n|---|---|\n| E1 | a |\n": "DFD version",
            DFD.replace(b"| D1 | DB", b"| E1 | DB"): "duplicate ID E1",
            DFD.replace(b"| F3 | P2 | D1", b"| F3 | P2 | X9"): "F3: unknown endpoint X9",
            DFD.replace(b"| TB1 |", b"| T-01 |"): "T-01",
        }
        for data, msg in cases.items():
            with self.subTest(msg=msg), self.assertRaisesRegex(dfd.DfdError, re.escape(msg)):
                dfd.parse(data)


if __name__ == "__main__":
    unittest.main()
