"""Registry.c4_status, c4_preview, c4_approve, and c4_checked_bytes."""
import hashlib
import unittest
from pathlib import Path
from unittest import mock

from helpers import (SAMPLE_WORKSPACE, TmpTestCase, approve_model, make_registry, session,
                     write_model)
from tmreg import c4
from tmreg.core import RegistryError, StaleRecord

NOTE = "Checked against the DFD checklist."
TEXT = SAMPLE_WORKSPACE.decode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def edited(old: str, new: str) -> bytes:
    assert old in TEXT
    return TEXT.replace(old, new, 1).encode()


C3_BLOCK = TEXT[TEXT.index("            C3 = container"):TEXT.index("        }\n\n        R1 =")]
R3_BLOCK = TEXT[TEXT.index("        R3 = C2 -> C3"):TEXT.index("        ENV1 =")]
TAIL = "        }\n\n        R1 ="


def without_c3() -> str:
    return (TEXT.replace(C3_BLOCK, "").replace(R3_BLOCK, "")
            .replace("                containerInstance C3\n", ""))


def with_container(text: str, cid: str) -> str:
    """text plus a container cid (with an instance in TB2), a copy of C3's block."""
    block = C3_BLOCK.replace("C3", cid).replace("Holds the data.", "Holds other data.")
    return (text.replace(TAIL, block + TAIL, 1)
            .replace("                containerInstance C2\n",
                     f"                containerInstance C2\n                containerInstance {cid}\n", 1))


class C4CoreTest(TmpTestCase):
    def reg(self, **kw):
        return make_registry(self.tmp, **kw)

    def test_sample_is_clean(self):
        self.assertEqual(c4.problems(c4.parse(SAMPLE_WORKSPACE)), [])

    def test_status_none_without_file(self):
        reg = self.reg()
        st = reg.c4_status("demo")
        self.assertEqual((st.state, st.latest, st.current_sha256), ("none", None, None))
        self.assertTrue(reg.c4_preview("demo")["error"].startswith("no workspace.dsl for demo"))

    def test_status_with_only_dfd_md(self):
        reg = self.reg()
        self.assertTrue((reg.root / "systems/demo/dfd.md").exists())
        self.assertEqual(reg.c4_status("demo").state, "none")
        self.assertTrue(reg.c4_preview("demo")["error"].startswith("no workspace.dsl"))

    def test_status_current_then_changed(self):
        reg = self.reg()
        write_model(reg, "demo")
        approve_model(reg, "demo")
        self.assertEqual(reg.c4_status("demo").state, "current")
        write_model(reg, "demo", edited("Answers the web app.", "Answers the web app well."))
        st = reg.c4_status("demo")
        self.assertEqual(st.state, "changed")
        self.assertEqual(st.latest["id"], "MODEL-1")

    def test_preview_comes_from_one_read(self):
        reg = self.reg()
        write_model(reg, "demo")
        real = Path.read_bytes
        calls = []

        def spy(self_):
            if self_.name == "workspace.dsl":
                calls.append(self_)
            return real(self_)

        with mock.patch.object(Path, "read_bytes", spy):
            p = reg.c4_preview("demo")
        self.assertEqual(len(calls), 1)
        self.assertEqual(p["sha256"], sha(p["text"].encode()))
        self.assertEqual(p["record"], c4.to_record(p["model"]))
        self.assertIsNone(p["error"])
        self.assertIsNone(p["adoption"])

    def test_approve_records_model_and_source(self):
        reg = self.reg()
        write_model(reg, "demo")
        row = reg.c4_approve(session(), "demo", NOTE, expected_sha256=sha(SAMPLE_WORKSPACE))
        self.assertEqual(row["id"], "MODEL-1")
        self.assertEqual(row["source"], TEXT)
        self.assertEqual(row["model"], c4.to_record(c4.parse(SAMPLE_WORKSPACE)))
        self.assertEqual(reg.history("demo")[-1]["op"], "model-approve")
        self.assertEqual(reg.model_record("demo", "MODEL-1"), row["model"])
        self.assertEqual([a["id"] for a in reg.model_approvals("demo")], ["MODEL-1"])

    def test_approve_refusals(self):
        reg = self.reg()
        write_model(reg, "demo")
        good = sha(SAMPLE_WORKSPACE)
        with self.assertRaises(StaleRecord):
            reg.c4_approve(session(), "demo", NOTE, expected_sha256="0" * 64)
        with self.assertRaises(RegistryError):
            reg.c4_approve(object(), "demo", NOTE, expected_sha256=good)
        with self.assertRaises(RegistryError):
            reg.c4_approve(session(), "demo", "short", expected_sha256=good)
        approve_model(reg, "demo")
        with self.assertRaisesRegex(RegistryError, "already approved as MODEL-1"):
            reg.c4_approve(session(), "demo", NOTE, expected_sha256=good)
        bad = edited('"tm.auth" "Session cookie"', '"tm.auth" ""')
        write_model(reg, "demo", bad)
        with self.assertRaisesRegex(RegistryError, "tm.auth"):
            reg.c4_approve(session(), "demo", NOTE, expected_sha256=sha(bad))
        broken = b"workspace {"
        write_model(reg, "demo", broken)
        with self.assertRaisesRegex(RegistryError, "line"):
            reg.c4_approve(session(), "demo", NOTE, expected_sha256=sha(broken))
        self.assertEqual(len(reg.model_approvals("demo")), 1)

    def test_changes_since_latest(self):
        reg = self.reg()
        write_model(reg, "demo")
        approve_model(reg, "demo")
        write_model(reg, "demo", edited("Answers the web app.", "Answers the web app well."))
        p = reg.c4_preview("demo")
        self.assertEqual(p["changed"], {"C2": ["description"]})
        self.assertEqual((p["added"], p["removed"]), ([], []))

    def test_reused_id_is_refused(self):
        reg = self.reg()
        write_model(reg, "demo")
        approve_model(reg, "demo")
        write_model(reg, "demo", without_c3().encode())
        self.assertEqual(c4.problems(c4.parse(without_c3().encode())), [])
        approve_model(reg, "demo")
        new = with_container(without_c3(), "C3")
        write_model(reg, "demo", new.encode())
        p = reg.c4_preview("demo")
        self.assertEqual(p["problems"], [])
        self.assertEqual(p["reused"], ["C3"])
        with self.assertRaisesRegex(RegistryError, "C3"):
            reg.c4_approve(session(), "demo", NOTE, expected_sha256=p["sha256"])

    def test_reuse_counts_the_sibling_register(self):
        real = self.reg()
        trial = make_registry(self.tmp, root=real.root, trial=True)
        c9 = with_container(TEXT, "C9")
        self.assertEqual(c4.problems(c4.parse(c9.encode())), [])
        write_model(trial, "demo", c9.encode())
        approve_model(trial, "demo")
        write_model(trial, "demo")
        approve_model(trial, "demo")
        write_model(real, "demo")
        approve_model(real, "demo")
        write_model(real, "demo", c9.encode())
        p = real.c4_preview("demo")
        self.assertEqual(p["reused"], ["C9"])
        self.assertEqual(p["next_ids"]["C"], "C10")

    def test_reused_dfd_boundary_without_was(self):
        reg = self.reg()
        write_model(reg, "demo", edited('                    "tm.was" "TB1"\n', ""))
        self.assertEqual(reg.c4_preview("demo")["reused"], ["TB1"])
        write_model(reg, "demo")
        self.assertEqual(reg.c4_preview("demo")["reused"], [])

    def test_next_ids(self):
        reg = self.reg()
        write_model(reg, "demo")
        p = reg.c4_preview("demo")
        self.assertEqual(p["next_ids"]["C"], "C4")
        self.assertEqual(p["next_ids"]["R"], "R4")

    def test_diff_lines(self):
        reg = self.reg()
        write_model(reg, "demo")
        self.assertTrue(any(l.startswith("+") for l in reg.c4_preview("demo")["diff"]))
        approve_model(reg, "demo")
        self.assertEqual(reg.c4_preview("demo")["diff"], [])
        write_model(reg, "demo", edited("Answers the web app.", "Answers the web app well."))
        d = reg.c4_preview("demo")["diff"]
        self.assertTrue(any(l.startswith("-") and "Answers the web app." in l for l in d))
        self.assertTrue(any(l.startswith("+") and "well" in l for l in d))

    def test_checked_bytes(self):
        reg = self.reg()
        write_model(reg, "demo", b"workspace {")
        with self.assertRaises(RegistryError):
            reg.c4_checked_bytes("demo")
        write_model(reg, "demo", edited('"tm.auth" "Session cookie"', '"tm.auth" ""'))
        with self.assertRaises(RegistryError):
            reg.c4_checked_bytes("demo")
        write_model(reg, "demo")
        data, model = reg.c4_checked_bytes("demo")
        self.assertEqual(data, SAMPLE_WORKSPACE)
        self.assertIsInstance(model, c4.Model)

    def test_personal_data_classes_must_be_declared(self):
        reg = self.reg()
        write_model(reg, "demo")
        toml = reg.root / "systems/demo/system.toml"
        toml.write_text(toml.read_text() + 'personal_data_classes = ["Health"]\n')
        p = reg.c4_preview("demo")
        self.assertIn("system.toml personal_data_classes names Health, which workspace.dsl "
                      "does not declare", p["problems"])
        with self.assertRaises(RegistryError):
            reg.c4_approve(session(), "demo", NOTE, expected_sha256=p["sha256"])
        toml.write_text(toml.read_text().replace("Health", "PII"))
        self.assertEqual(reg.c4_preview("demo")["problems"], [])


if __name__ == "__main__":
    unittest.main()
