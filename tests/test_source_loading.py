"""Загрузка русских исходников и совместимость грамматики C++."""

import tempfile
import unittest
from pathlib import Path

from blockwright import vendored

vendored.activate()

from blockwright import parse as P
from blockwright.cli import Opts
from blockwright.langs import registry
from blockwright.project import charts, load, outline


class SourceLoading(unittest.TestCase):
    def test_legacy_encodings_preserve_text_and_utf8_offsets(self) -> None:
        text = '// Проверка входных данных\nint main(){ puts("Введите размер массива"); }\n'
        for encoding in ("utf-8", "utf-8-sig", "cp866", "cp1251"):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "input.cpp"
                path.write_bytes(text.encode(encoding))
                source = load(str(path))
                self.assertEqual(source.src.decode("utf-8"), text)
                self.assertEqual(source.errors, 0)
                info = outline(source)[0]
                self.assertEqual(info["name"], "main")
                self.assertEqual(info["line"], 2)
                self.assertIn(
                    b"puts(",
                    source.src[info["body"].start_byte : info["body"].end_byte],
                )

    def test_pointer_array_new_preserves_original_source_in_full_mode(self) -> None:
        for allocation in ("new int*[m]", "new int ** [m]", "new Widget*[m]"):
            for newline in ("\n", "\r\n"):
                with (
                    self.subTest(allocation=allocation, newline=repr(newline)),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    text = (
                        f"// Русский комментарий{newline}"
                        f"int main(){{int m=3; auto a={allocation};}}"
                    )
                    original = text.encode("utf-8")
                    path = Path(tmp) / "input.cpp"
                    path.write_bytes(original)
                    source = load(str(path))
                    self.assertEqual(source.errors, 0)
                    self.assertEqual(source.src, original)
                    info = outline(source)[0]
                    self.assertEqual(info["line"], 2)
                    self.assertIn(
                        allocation.encode("utf-8"),
                        source.src[info["body"].start_byte : info["body"].end_byte],
                    )
                    opts = Opts()
                    opts.study = False
                    result = charts(source, opts, source.known)
                    self.assertEqual(len(result), 1)
                    self.assertIn(allocation, repr(result[0].body))

    def test_pointer_new_does_not_hide_invalid_syntax(self) -> None:
        for statement in (
            "auto a = new int*[m +];",
            "auto a = new int*[m]; int broken = ;",
            "auto a = new int * other[; ",
        ):
            with self.subTest(statement=statement):
                src = f"int main(){{{statement}}}".encode()
                _, _, errors = P.parse_source(src, registry().get("cpp"))
                self.assertGreater(errors, 0)

    def test_new_syntax_in_literals_and_comments_is_not_rewritten(self) -> None:
        src = b'int main(){const char *s="new int*[m]"; /* new X*[m] */}'
        tree, _, errors = P.parse_source(src, registry().get("cpp"))
        self.assertEqual(errors, 0)
        self.assertIn(b'"new int*[m]"', tree.root_node.text)
