"""Language descriptions: loading, `extends`, hooks, errors, and the CLI on
every fixture."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from blockwright import vendored

vendored.activate()

from blockwright import langs, project
from blockwright import model as M
from blockwright.cli import Opts, main

LANGS = os.path.join(HERE, "langs")
FIXTURES = os.path.join(HERE, "fixtures")


class Descriptions(unittest.TestCase):
    def tearDown(self):
        langs._DEFAULT = None

    def test_builtin_load_cleanly(self):
        reg = langs.Registry()
        self.assertEqual(reg.errors, [])
        self.assertEqual(reg.names(), ["cpp"])
        # everything that is bundled must load from vendor/
        for spec in reg.select():
            if spec.bundle:
                self.assertTrue(spec.available, spec.name)

    def test_extends_and_hooks(self):
        reg = langs.registry([LANGS])
        self.assertEqual(reg.errors, [])
        spec = reg.get("mini")
        self.assertEqual(spec.extensions, [".mini"])
        self.assertIn("printf", spec.io_output)
        src = project.load(os.path.join(LANGS, "sample.mini"))
        self.assertEqual(src.spec.name, "mini")
        (chart,) = project.charts(src, Opts(study=False), src.known)
        first, second = chart.body.items
        self.assertIsInstance(first, M.If)
        self.assertEqual(first.cond, "x > 0")
        self.assertEqual(second.kind, M.IO)
        self.assertIn("x", second.text)

    def test_bad_description_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "bad.toml"), "w", encoding="utf-8") as fh:
                fh.write(
                    'name = "bad"\ngrammar = "tree_sitter_c"\n'
                    '[statements]\nif_statement = { kind = "iff" }\n'
                )
            with open(os.path.join(tmp, "typo.toml"), "w", encoding="utf-8") as fh:
                fh.write(
                    'name = "typo"\ngrammar = "tree_sitter_c"\n[function]\nnodes = []\n'
                )
            with open(os.path.join(tmp, "orphan.toml"), "w", encoding="utf-8") as fh:
                fh.write(
                    'name = "orphan"\nextends = "nope"\ngrammar = "tree_sitter_c"\n'
                )
            reg = langs.Registry([tmp])
        self.assertIsNone(reg.get("bad"))
        self.assertIsNone(reg.get("orphan"))
        text = "\n".join(reg.errors)
        self.assertIn("iff", text)
        self.assertIn("nope", text)
        self.assertIn("function", text)
        self.assertIsNone(reg.get("typo"))

    def test_missing_grammar(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "ghost.toml"), "w", encoding="utf-8") as fh:
                fh.write(
                    'name = "ghost"\ngrammar = "tree_sitter_ghost"\n'
                    'extensions = [".ghost"]\n'
                )
            reg = langs.Registry([tmp])
        spec = reg.get("ghost")
        self.assertFalse(spec.available)
        self.assertEqual(spec.install_hint(), "pip install tree-sitter-ghost")

    def test_guess(self):
        reg = langs.Registry()
        self.assertEqual(reg.guess("a.h", "int f(void);").name, "cpp")
        self.assertEqual(reg.guess("a.h", "namespace x {}").name, "cpp")
        self.assertIsNone(reg.guess("a.py", ""))
        self.assertIsNone(reg.guess("A.java", ""))
        self.assertEqual(reg.guess("a.c", "", {"cpp"}).name, "cpp")


class Cli(unittest.TestCase):
    def test_every_fixture_builds(self):
        for folder in sorted(os.listdir(FIXTURES)):
            spec = langs.registry().get(folder)
            if spec is None or not spec.available:
                continue
            with self.subTest(folder=folder), tempfile.TemporaryDirectory() as out:
                rc = main([os.path.join(FIXTURES, folder), "-o", out, "--no-ui", "-q"])
                self.assertEqual(rc, 0)
                svgs = [f for f in os.listdir(out) if f.endswith(".svg")]
                self.assertTrue(svgs)
                self.assertIn("index.html", os.listdir(out))

    def test_lang_filter(self):
        with tempfile.TemporaryDirectory() as out:
            rc = main([FIXTURES, "-o", out, "--no-ui", "-q", "--lang", "cpp"])
            self.assertEqual(rc, 0)
            svgs = sorted(f for f in os.listdir(out) if f.endswith(".svg"))
            self.assertTrue(svgs)
            self.assertTrue(all("lab_py" not in name for name in svgs))

    def test_same_stem_in_two_cpp_extensions(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as out:
            for name, code in (
                ("lab.cpp", "int main(void) { return 0; }\n"),
                ("lab.cc", "int main() { return 1; }\n"),
            ):
                with open(os.path.join(src, name), "w", encoding="utf-8") as fh:
                    fh.write(code)
            self.assertEqual(main([src, "-o", out, "--no-ui", "-q", "--no-html"]), 0)
            self.assertEqual(
                sorted(os.listdir(out)), ["lab_cc__main.svg", "lab_cpp__main.svg"]
            )

    def test_unknown_lang(self):
        self.assertEqual(main([FIXTURES, "--no-ui", "--lang", "cobol"]), 2)


if __name__ == "__main__":
    unittest.main()
