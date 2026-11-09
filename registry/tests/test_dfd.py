import hashlib
import re
import unittest

from tmreg import dfd

DFD = b"""| Field | Value |
|---|---|
| DFD version | 1.0 |

```mermaid
flowchart LR
  | E99 | not a table |
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

    def test_details_from_sample(self):
        d = dfd.parse(DFD)
        self.assertEqual(d.details["P1"], {"name": "Web", "type": "Process", "description": ""})
        self.assertEqual(d.details["F2"], {"name": "REST", "type": "Data flow", "description": "",
                                           "from": "P1", "to": "P2 (via CDN)"})
        self.assertEqual(d.details["TB1"], {"name": "Internet to edge", "type": "Trust boundary",
                                            "description": "WAF"})
        self.assertNotIn("E99", d.details)  # the fenced row stays ignored
        self.assertEqual(d.sha256, hashlib.sha256(DFD).hexdigest())

    def test_details_read_notes_column(self):
        data = DFD.replace(b"| ID | Element | Type |\n|---|---|---|",
                           b"| ID | Element | Type | Notes |\n|---|---|---|---|") \
                  .replace(b"| E1 | Customer | External entity |",
                           b"| E1 | Customer | External entity | Signs in first |")
        self.assertEqual(dfd.parse(data).details["E1"]["description"], "Signs in first")

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


HEAD = b"| Field | Value |\n|---|---|\n| DFD version | 1.0 |\n\n"
ELEMS = b"| ID | Element |\n|---|---|\n| E1 | a |\n| P1 | b |\n"


class HardeningTest(unittest.TestCase):
    def raises(self, data, msg):
        with self.assertRaisesRegex(dfd.DfdError, re.escape(msg)):
            dfd.parse(data)

    def test_fenced_rows_ignored(self):
        for fence in (b"```", b"~~~"):
            with self.subTest(fence=fence):
                data = HEAD + ELEMS + b"\n" + fence + b"\n| ID | X |\n|---|---|\n| E99 | x |\n" + fence + b"\n"
                self.assertNotIn("E99", dfd.parse(data).all_ids())

    def test_inner_info_string_does_not_close_fence(self):
        data = HEAD + ELEMS + b"\n```\n```mermaid\n| ID | X |\n|---|---|\n| E99 | x |\n```\n"
        self.assertNotIn("E99", dfd.parse(data).all_ids())

    def test_shorter_closer_does_not_close(self):
        data = HEAD + ELEMS + b"\n````\n```\n| ID | X |\n|---|---|\n| E99 | x |\n````\n"
        self.assertNotIn("E99", dfd.parse(data).all_ids())

    def test_unclosed_fence(self):
        self.raises(HEAD + ELEMS + b"\n```\n| ID | X |\n", "unclosed code fence opened at line 10")

    def test_unclosed_comment(self):  # M6
        self.raises(HEAD + ELEMS + b"\n<!-- note\n| ID | X |\n", "unclosed HTML comment opened at line 10")
        self.raises(HEAD + ELEMS + b"\n<!-- a --> text\nmore <!-- b\n",
                    "unclosed HTML comment opened at line 11")

    def test_indented_and_comments_ignored(self):
        data = (HEAD + ELEMS + b"\n    | ID | X |\n    |---|---|\n    | E98 | x |\n"
                b"\n<!-- note\n| ID | X |\n|---|---|\n| E99 | x |\n-->\n")
        self.assertEqual(dfd.parse(data).all_ids(), {"E1", "P1"})

    def test_blank_line_in_table(self):
        self.raises(HEAD + b"| ID | Element |\n|---|---|\n| E1 | a |\n\n| P1 | b |\n",
                    "outside a table")

    def test_row_without_leading_pipe(self):
        self.raises(HEAD + ELEMS + b"D1 | c |\n| D2 | d |\n", "without a leading pipe")

    def test_header_without_separator(self):
        self.raises(HEAD + b"| ID | Element |\n| E1 | a |\n", "outside a table")

    def test_header_casing(self):
        data = HEAD + ELEMS + b"\n| Id | FROM | to |\n|---|---|---|\n| F1 | E1 | P1 |\n"
        self.assertEqual(dfd.parse(data).ids["F"], ["F1"])
        self.raises(data.replace(b"| P1 |\n", b"| X1 |\n"), "F1: unknown endpoint X1")

    def test_flows_need_from_to(self):
        self.raises(HEAD + ELEMS + b"\n| ID | Label |\n|---|---|\n| F1 | x |\n",
                    "flows table needs From and To columns")

    def test_zero_elements(self):
        self.raises(HEAD, "defines no elements")

    def test_endpoint_word_boundary(self):
        self.raises(HEAD + ELEMS + b"\n| ID | From | To |\n|---|---|---|\n| F1 | E1 | P1x |\n",
                    "F1: unknown endpoint P1x")

    def test_empty_version(self):
        self.raises(HEAD.replace(b"1.0", b"") + ELEMS, "DFD version")

    def test_version_must_be_plain(self):
        # The version cell is AI-writable and printed at the DFD gate; escape codes there could
        # hide the sha256 and added/removed lines from the owner, so only a plain token parses.
        # U+2028 splits the line, so the row is refused earlier, as a row without a leading pipe.
        with self.assertRaises(dfd.DfdError) as cm:
            dfd.parse(HEAD.replace(b"1.0", "1.0 x".encode()) + ELEMS)
        self.assertTrue(str(cm.exception).isascii())
        for bad in ("1.1\x1b[8m", "1.0‮", "1.0​", "1.0 beta", "-1.0"):
            with self.subTest(version=bad):
                data = HEAD.replace(b"1.0", bad.encode()) + ELEMS
                with self.assertRaisesRegex(dfd.DfdError, "DFD version must be") as cm:
                    dfd.parse(data)
                self.assertTrue(str(cm.exception).isascii())
                self.assertNotIn("\x1b", str(cm.exception))
        for good in ("1.0", "2.13", "v3", "2026-11-07", "1.0-rc1", "1.0+b2"):
            with self.subTest(version=good):
                self.assertEqual(dfd.parse(HEAD.replace(b"1.0", good.encode()) + ELEMS).version, good)

    def test_error_messages_escape_cell_text(self):
        data = HEAD + ELEMS + "\n| ID | From | To |\n|---|---|---|\n| F1 | E1 | X9\x1b[2K |\n".encode()
        with self.assertRaises(dfd.DfdError) as cm:
            dfd.parse(data)
        self.assertNotIn("\x1b", str(cm.exception))
        self.assertIn("F1: unknown endpoint", str(cm.exception))

    def test_bom_and_non_utf8(self):
        data = b"\xef\xbb\xbf" + HEAD + ELEMS
        d = dfd.parse(data)
        self.assertEqual(d.version, "1.0")
        self.assertEqual(d.sha256, hashlib.sha256(data).hexdigest())
        self.raises(HEAD + ELEMS + b"\xff\xfe", "not UTF-8")


if __name__ == "__main__":
    unittest.main()
