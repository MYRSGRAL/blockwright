"""Пользовательские настройки и ограничения учебного C++-форка."""

import tempfile
import unittest
from pathlib import Path

from blockwright import vendored

vendored.activate()

from blockwright import langs
from blockwright.cli import Opts, build_parser, main


class Product(unittest.TestCase):
    def test_checks_flag_controls_lab2_error_branches(self) -> None:
        source = Path(__file__).parent / "fixtures/study/lab2.cpp"
        with tempfile.TemporaryDirectory() as tmp:
            for name, flags, visible in (
                ("default", [], False),
                ("show", ["--checks", "show"], True),
                ("full", ["--detail", "full"], True),
            ):
                with self.subTest(mode=name):
                    out = Path(tmp) / name
                    self.assertEqual(
                        main([str(source), "--no-ui", "-q", "-o", str(out), *flags]), 0
                    )
                    svg = next(out.glob("*.svg")).read_text(encoding="utf-8")
                    self.assertEqual("Ошибка" in svg, visible)
                    self.assertIn("sum", svg)
                    self.assertIn("i &lt;= 10", svg)

    def test_default_cpp_registry(self) -> None:
        reg = langs.Registry()
        self.assertEqual(reg.errors, [])
        self.assertEqual(reg.names(), ["cpp"])
        self.assertNotIn(".c", reg.extensions())
        self.assertEqual(reg.guess("a.h", "int f();").name, "cpp")
        self.assertIsNone(reg.guess("program.py", "print(1)"))

    def test_study_defaults_and_explicit_full_mode(self) -> None:
        opts = Opts()
        self.assertTrue(opts.study)
        self.assertEqual(opts.checks, "hide")
        self.assertEqual(build_parser().parse_args(["--checks", "show"]).checks, "show")
        self.assertEqual(opts.notation, "course")
        self.assertEqual(opts.for_style, "decision")
        args = build_parser().parse_args(["--detail", "full", "--notation", "gost"])
        self.assertEqual(args.detail, "full")
        self.assertEqual(args.notation, "gost")

    def test_syntax_error_is_reported_without_partial_chart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "broken.cpp"
            out = Path(tmp) / "out"
            src.write_text("int main() { if ( }", encoding="utf-8")
            result = main([str(src), "-o", str(out), "--no-ui", "-q"])
            self.assertNotEqual(result, 0)
            self.assertFalse(list(out.glob("*.svg")))

    def test_cli_profile_generates_black_white_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "program.cpp"
            out = Path(tmp) / "out"
            src.write_text(
                "#include <iostream>\nint main(){ std::cout << 42; }", encoding="utf-8"
            )
            result = main(
                [
                    str(src),
                    "-o",
                    str(out),
                    "--no-ui",
                    "--detail",
                    "study",
                    "--notation",
                    "course",
                    "-q",
                ]
            )
            self.assertEqual(result, 0)
            svg = next(out.glob("*.svg")).read_text(encoding="utf-8")
            self.assertNotIn("#fff6e5", svg)
            self.assertIn("Вывод", svg)


if __name__ == "__main__":
    unittest.main()
