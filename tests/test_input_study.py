"""Группы проверяемого ввода с повторным использованием строкового буфера."""

import unittest
from collections.abc import Iterator
from pathlib import Path

from blockwright import vendored

vendored.activate()

from blockwright import model as M
from blockwright import parse as P
from blockwright import project
from blockwright.cli import Opts

USER_CODE = r"""#include <iostream>
#include <sstream>
#include <string>
#include <clocale>
using namespace std;
int main() {
    setlocale(LC_ALL, "Russian");
    const int c = 100;
    int a[c];
    int n, i;
    int k = 0;
    string line;
    char e;
    cout << "Введите количество элементов (от 1 до 100): ";
    getline(cin, line);
    istringstream sizeInput(line);
    if (!(sizeInput >> n) || (sizeInput >> e) || n < 1 || n > c) {
        cout << "Ошибка: введите одно целое число от 1 до 100." << endl;
        return 1;
    }
    cout << "Введите " << n << " целых чисел в одной строке: ";
    getline(cin, line);
    istringstream arrayInput(line);
    for (i = 0; i < n; i++) {
        if (!(arrayInput >> a[i])) {
            cout << "Ошибка: требуется ровно " << n << " целых чисел." << endl;
            return 1;
        }
    }
    if (arrayInput >> e) {
        cout << "Ошибка: требуется ровно " << n << " целых чисел." << endl;
        return 1;
    }
    for (i = 0; i < n; i++) {
        if (a[i] % 2 != 0) {
            a[k] = a[i];
            k++;
        }
    }
    n = k;
    cout << "Количество оставшихся элементов: " << n << endl;
    cout << "Массив после удаления: ";
    if (n == 0) { cout << "пустой"; }
    else { for (i = 0; i < n; i++) { cout << a[i] << ' '; } }
    cout << endl;
    return 0;
}"""


def build(code: str, *, checks: str = "hide", study: bool = True) -> M.Seq:
    src = code.encode()
    tree, spec, errors = P.parse_source(src, P.guess_language("input.cpp", code))
    source = project.Source("input.cpp", src, spec, tree, errors)
    known = P.collect_known_names(src, tree.root_node, spec)
    return project.charts(source, Opts(study=study, checks=checks), known)[0].body


def walk(item: object) -> Iterator[object]:
    yield item
    if isinstance(item, M.Seq):
        for child in item.items:
            yield from walk(child)
    elif isinstance(item, M.If):
        yield from walk(item.then_)
        if item.else_ is not None:
            yield from walk(item.else_)
    elif isinstance(item, (M.ForLoop, M.While, M.DoWhile)):
        yield from walk(item.body)


class InputGroups(unittest.TestCase):
    def test_array_count_must_be_integer_even_when_global_name_is_integer(self) -> None:
        for prefix in ("", "int n;\n"):
            code = prefix + USER_CODE.replace("int n, i;", "double n; int i;")
            body = build(code)
            self.assertFalse(
                any(
                    isinstance(i, M.Simple) and i.text == "Ввод a[n]"
                    for i in walk(body)
                )
            )

    def test_corrected_user_example_hides_only_input_protocol(self) -> None:
        body = build(USER_CODE)
        inputs = [
            item.text
            for item in walk(body)
            if isinstance(item, M.Simple) and item.kind == M.INPUT
        ]
        self.assertEqual(inputs, ["Ввод n", "Ввод a[n]"])
        conditions = [item.cond for item in walk(body) if isinstance(item, M.If)]
        self.assertIn("a[i] % 2 != 0", conditions)
        self.assertNotIn("n == 0", conditions)
        self.assertFalse(any("Input" in cond for cond in conditions))
        texts = [item.text for item in walk(body) if isinstance(item, M.Simple)]
        self.assertIn("a[k] = a[i]", texts)
        self.assertIn("k++", texts)
        self.assertIn("n = k", texts)
        self.assertIn("Вывод n, a[n]", texts)
        self.assertFalse(
            any(
                "Ошибка" in text or "Введите" in text or "istringstream" in text
                for text in texts
            )
        )

    def test_lab4_while_reader_and_three_reused_buffer_groups(self) -> None:
        code = (Path(__file__).parent / "fixtures/study/lab4.cpp").read_text(
            encoding="utf-8"
        )
        body = build(code)
        inputs = [
            item.text
            for item in walk(body)
            if isinstance(item, M.Simple) and item.kind == M.INPUT
        ]
        self.assertEqual(inputs, ["Ввод n", "Ввод a[n]", "Ввод limit"])
        self.assertFalse(any(isinstance(item, M.While) for item in walk(body)))
        self.assertTrue(
            any(
                isinstance(item, M.If) and item.cond == "a[i] <= limit"
                for item in walk(body)
            )
        )

    def test_show_and_full_modes_keep_input_checks(self) -> None:
        for opts in ({"checks": "show"}, {"study": False}):
            with self.subTest(opts=opts):
                body = build(USER_CODE, **opts)
                self.assertTrue(
                    any(
                        isinstance(item, M.If) and "sizeInput >> n" in item.cond
                        for item in walk(body)
                    )
                )
                self.assertTrue(
                    any(
                        isinstance(item, M.If) and "arrayInput >> a[i]" in item.cond
                        for item in walk(body)
                    )
                )

    def test_effectful_validation_is_not_hidden(self) -> None:
        cases = [
            USER_CODE.replace(
                '"Ошибка: требуется ровно " << n', '"Ошибка: требуется ровно " << ++n'
            ),
            USER_CODE.replace(
                '"Ошибка: требуется ровно " << n',
                '"Ошибка: требуется ровно " << count()',
            ),
            USER_CODE.replace("return 1;", "log(); return 1;"),
            USER_CODE.replace("n > c", "n > bound()"),
        ]
        for code in cases:
            with self.subTest(code=code):
                body = build(code)
                self.assertFalse(
                    any(
                        isinstance(item, M.Simple) and item.text == "Ввод a[n]"
                        for item in walk(body)
                    )
                )
                self.assertTrue(
                    any(
                        isinstance(item, M.If) and "Input" in item.cond
                        for item in walk(body)
                    )
                )

    def test_shadowed_and_macro_names_keep_detailed_protocol(self) -> None:
        cases = [
            USER_CODE.replace("int main() {", "int main() { Stream cin;"),
            "#define getline custom_getline\n" + USER_CODE,
            "#define n next_count()\n" + USER_CODE,
            "#define endl custom_endl\n" + USER_CODE,
            "#define return traced_return\n" + USER_CODE,
            "#define int CustomNumber\n" + USER_CODE,
            "class istringstream {};\n" + USER_CODE,
        ]
        for code in cases:
            with self.subTest(code=code):
                body = build(code)
                self.assertFalse(
                    any(
                        isinstance(item, M.Simple) and item.text == "Ввод a[n]"
                        for item in walk(body)
                    )
                )

    def test_external_buffer_or_index_use_prevents_elision(self) -> None:
        marker = "    for (i = 0; i < n; i++) {\n        if (a[i] % 2"
        for statement in ("log(line);", "use(i);", "use(e);", "sizeInput.fail();"):
            code = USER_CODE.replace(marker, statement + "\n" + marker)
            with self.subTest(statement=statement):
                body = build(code)
                self.assertFalse(
                    any(
                        isinstance(item, M.Simple) and item.text == "Ввод a[n]"
                        for item in walk(body)
                    )
                )
                texts = [item.text for item in walk(body) if isinstance(item, M.Simple)]
                self.assertIn(statement.rstrip(";"), texts)

    def test_volatile_array_elements_keep_the_read_loop(self) -> None:
        body = build(USER_CODE.replace("int a[c];", "volatile int a[c];"))
        self.assertFalse(
            any(
                isinstance(item, M.Simple) and item.text == "Ввод a[n]"
                for item in walk(body)
            )
        )


if __name__ == "__main__":
    unittest.main()
