"""Учебная схема строкового ввода сохраняет нормализацию и алгоритм."""

import unittest

from test_input_study import build, walk

from blockwright import model as M
from blockwright.cli import Opts, layout_for_report
from blockwright.geometry import validate_geometry, validate_ports

CODE = r"""
#include <iostream>
#include <cwctype>
using namespace std;
int main() {
    wchar_t text[1001]; int n; int start = -1; int count = 0;
    wcout << L"Введите текст: ";
    if (!wcin.getline(text, 1001)) {
        wcout << L"Ошибка ввода" << endl; return 1;
    }
    n = wcin.gcount();
    if (!wcin.eof()) { n--; }
    for (int i = 0; i < n; i++) {
        text[i] = towlower(text[i]);
        if (text[i] != L' ' && text[i] != L'ё' &&
            (text[i] < L'а' || text[i] > L'я')) {
            wcout << L"Ошибка символа" << endl; return 1;
        }
    }
    for (int i = 0; i <= n; i++) {
        if (text[i] == L' ' || text[i] == L'\0') {
            if (start != -1) {
                if (text[start] == text[i - 1]) { count++; }
                start = -1;
            }
        } else if (start == -1) { start = i; }
    }
    wcout << count; return 0;
}
"""


class CharacterLine(unittest.TestCase):
    def test_inline_length_before_splitting(self) -> None:
        code = """
        int main() {
            wchar_t text[1001];
            const wchar_t* words[501];
            wcout << L"Введите текст: ";
            if (!wcin.getline(text, 1001)) {
                wcout << L"Ошибка чтения" << endl;
                return 1;
            }
            int length = wcin.gcount() - !wcin.eof();
            int count = splitWords(text, length, words);
            wcout << count;
        }
        """
        items = build(code).items
        start = items.index(M.Simple(M.INPUT, "Ввод text"))
        self.assertEqual(
            items[start + 1],
            M.Simple(M.PROCESS, "length = wcin.gcount() - !wcin.eof()"),
        )
        self.assertIn("splitWords(text, length, words)", items[start + 2].text)
        for options in ({"checks": "show"}, {"study": False}):
            self.assertTrue(
                any(
                    isinstance(item, M.If) and "getline" in item.cond
                    for item in walk(build(code, **options))
                )
            )
        for unsafe in (
            code.replace("text[1001]", "text[10]"),
            code.replace("text[1001]", "text[01001]"),
            code.replace("int length", "unsigned char length"),
            code.replace("wcin.eof()", "other.eof()"),
            code.replace('wcout << L"Ошибка', 'audit(); wcout << L"Ошибка'),
        ):
            self.assertNotIn(M.Simple(M.INPUT, "Ввод text"), build(unsafe).items)

    def test_line_protocol_is_compact_but_algorithm_is_preserved(self) -> None:
        body = build(CODE)
        self.assertIn(M.Simple(M.INPUT, "Ввод text"), body.items)
        texts = [x.text for x in walk(body) if isinstance(x, M.Simple)]
        self.assertIn("n = длина text", texts)
        self.assertIn("Привести text к нижнему регистру", texts)
        self.assertFalse(any("Ошибка" in text or "gcount" in text for text in texts))
        self.assertTrue(
            any(isinstance(x, M.If) and "text[start]" in x.cond for x in walk(body))
        )

    def test_compact_chart_has_no_crossing_routes(self) -> None:
        for style in ("auto", "decision"):
            fn = M.Function("main", "main()", "Начало", "", "", 1, "cpp", build(CODE))
            frame, _ = layout_for_report(fn, Opts(checks="hide", for_style=style))
            self.assertEqual(validate_geometry(frame), [])
            self.assertEqual(validate_ports(frame), [])
            segments = [
                (a, b)
                for edge in frame.edges
                for a, b in zip(edge["points"], edge["points"][1:])
            ]
            horizontal = [(a, b) for a, b in segments if a[1] == b[1]]
            vertical = [(a, b) for a, b in segments if a[0] == b[0]]
            for a, b in horizontal:
                for c, d in vertical:
                    self.assertFalse(
                        min(a[0], b[0]) < c[0] < max(a[0], b[0])
                        and min(c[1], d[1]) < a[1] < max(c[1], d[1]),
                        (a, b, c, d),
                    )

    def test_explicit_modes_preserve_checks(self) -> None:
        for options in ({"checks": "show"}, {"study": False}):
            self.assertTrue(
                any(
                    isinstance(x, M.Simple) and "Ошибка" in x.text
                    for x in walk(build(CODE, **options))
                )
            )

    def test_unknown_effects_prevent_protocol_folding(self) -> None:
        for code in (
            CODE.replace("text[i] = towlower", "audit(); text[i] = towlower"),
            CODE.replace(
                'wcout << L"Ошибка символа', 'audit(); wcout << L"Ошибка символа'
            ),
            CODE.replace("text[i] < L'а'", "next() < L'а'"),
            CODE.replace("n--;", "n -= 2;"),
            "#define towlower custom\n" + CODE,
            CODE.replace("int n;", "unsigned char n;"),
            CODE.replace("int n;", "int n; int i;")
            .replace("n = wcin", "i = wcin")
            .replace("n--;", "i--;")
            .replace("i < n;", "i < i;"),
            CODE.replace("int start = -1;", "auto alias = &text[0]; int start = -1;"),
        ):
            with self.subTest(code=code):
                self.assertFalse(
                    any(
                        isinstance(item, M.Simple) and "= длина text" in item.text
                        for item in build(code).items
                    )
                )
