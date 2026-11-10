"""Учебная схема ввода слова сохраняет алгоритм и скрывает проверку длины."""

import unittest

from test_input_study import build, walk

from blockwright import model as M

CODE = r"""
#include <iostream>
using namespace std;
int main() {
    wchar_t word[102];
    int n = 0;
    bool palindrome = true;
    if (!(wcin >> word)) { wcout << L"Ошибка ввода"; return 1; }
    while (word[n] != L'\0') { n++; }
    if (n > 100) { wcout << L"Слишком длинное слово"; return 1; }
    for (int i = 0; i < n / 2; i++) {
        if (word[i] != word[n - 1 - i]) { palindrome = false; break; }
    }
    wcout << palindrome;
    return 0;
}
"""


class CharacterInput(unittest.TestCase):
    def test_width_between_prompt_and_read_does_not_leave_prompt_output(self) -> None:
        code = CODE.replace(
            "if (!(wcin >> word))",
            'wcout << L"Введите слово: "; wcin.width(102); if (!(wcin >> word))',
        )
        body = build(code)
        self.assertIn(M.Simple(M.INPUT, "Ввод word"), body.items)
        self.assertFalse(
            any(isinstance(x, M.Simple) and "Введите" in x.text for x in body.items)
        )

    def test_length_guard_hidden_and_comparison_preserved(self) -> None:
        for code in (CODE, CODE.replace("wchar_t", "char").replace("wcin", "cin")):
            with self.subTest(code=code):
                body = build(code)
                self.assertIn(M.Simple(M.INPUT, "Ввод word"), body.items)
                self.assertFalse(any(isinstance(x, M.If) for x in body.items))
                self.assertTrue(any(isinstance(x, M.While) for x in body.items))
                self.assertTrue(
                    any(isinstance(x, M.If) and "word[i]" in x.cond for x in walk(body))
                )

    def test_effects_and_unproven_length_preserve_guard(self) -> None:
        for code in (
            CODE.replace("n++;", "n++; audit();"),
            CODE.replace("n++;", "n += 2;"),
            CODE.replace("int n = 0;", "int n = 1;"),
            CODE.replace("int n = 0;", "wchar_t *alias = word; int n = 0;").replace(
                "while (word[n]", "alias[0] = L'x'; while (word[n]"
            ),
            CODE.replace("int n = 0;", "wchar_t *alias = &word[0]; int n = 0;").replace(
                "while (word[n]", "alias[0] = L'x'; while (word[n]"
            ),
            CODE.replace("if (n > 100)", "word[0] = L'x'; if (n > 100)"),
            CODE.replace("if (n > 100)", "n++; if (n > 100)"),
            CODE.replace('wcout << L"Слишком', 'audit(); wcout << L"Слишком'),
        ):
            with self.subTest(code=code):
                self.assertTrue(
                    any(
                        isinstance(x, M.If) and x.cond == "n > 100"
                        for x in build(code).items
                    )
                )

    def test_show_and_full_preserve_length_guard(self) -> None:
        for opts in ({"checks": "show"}, {"study": False}):
            self.assertTrue(
                any(
                    isinstance(x, M.If) and x.cond == "n > 100"
                    for x in build(CODE, **opts).items
                )
            )
