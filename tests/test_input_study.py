"""Группы проверяемого ввода с повторным использованием строкового буфера."""

import re
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

DIRECT_CODE = r"""#include <iostream>
using namespace std;
int main() {
    setlocale(LC_ALL, "Russian");
    int a[100];
    int n;
    cout << "Введите количество элементов от 1 до 100: ";
    if (!(cin >> n) || n < 1 || n > 100) {
        cout << "Ошибка ввода";
        return 1;
    }
    cout << "Введите элементы массива: ";
    for (int i = 0; i < n; i++) {
        if (!(cin >> a[i])) {
            cout << "Ошибка ввода";
            return 1;
        }
    }
    int k = 0;
    for (int i = 0; i < n; i++) {
        if (a[i] % 2 != 0) {
            a[k] = a[i];
            k++;
        }
    }
    n = k;
    cout << "Массив после удаления: ";
    if (n == 0) { cout << "пустой"; }
    else { for (int i = 0; i < n; i++) { cout << a[i] << ' '; } }
    cout << '\n';
    return 0;
}"""


def build(code: str, *, checks: str = "hide", study: bool = True) -> M.Seq:
    src = code.encode()
    tree, spec, errors = P.parse_source(src, P.guess_language("input.cpp", code))
    source = project.Source("input.cpp", src, spec, tree, errors)
    known = P.collect_known_names(src, tree.root_node, spec)
    charts = project.charts(source, Opts(study=study, checks=checks), known)
    return next(chart.body for chart in charts if chart.info["main"])


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
    def test_global_index_observed_by_function_keeps_direct_loop(self) -> None:
        body = build(
            "int i; void observe_global(){cout<<i;} "
            "int main(){int a[10];int n=10;for(i=0;i<n;i++){cin>>a[i];}"
            "observe_global();return 0;}"
        )
        self.assertNotIn(M.Simple(M.INPUT, "Ввод a[n]"), body.items)
        self.assertTrue(any(isinstance(item, M.ForLoop) for item in walk(body)))

    def test_global_index_observed_by_function_keeps_buffered_loop(self) -> None:
        code = "int i; void observe_global(){cout<<i;}\n" + USER_CODE.replace(
            "int n, i;", "int n;"
        )
        marker = "    for (i = 0; i < n; i++) {\n        if (a[i] % 2"
        code = code.replace(marker, "    observe_global();\n" + marker)
        body = build(code)
        self.assertNotIn(M.Simple(M.INPUT, "Ввод a[n]"), body.items)
        self.assertTrue(
            any(
                isinstance(item, M.If) and "arrayInput >> a[i]" in item.cond
                for item in walk(body)
            )
        )

    def test_scoped_index_can_shadow_global_without_changing_it(self) -> None:
        body = build(
            "int i; void observe_global(){cout<<i;} "
            "int main(){int a[10];int n=10;for(int i=0;i<n;i++){cin>>a[i];}"
            "observe_global();return 0;}"
        )
        self.assertIn(M.Simple(M.INPUT, "Ввод a[n]"), body.items)

    def test_direct_user_example_keeps_one_algorithmic_loop(self) -> None:
        body = build(DIRECT_CODE)
        inputs = [
            item.text
            for item in walk(body)
            if isinstance(item, M.Simple) and item.kind == M.INPUT
        ]
        self.assertEqual(inputs, ["Ввод n", "Ввод a[n]"])
        self.assertEqual(
            sum(isinstance(item, (M.ForLoop, M.While)) for item in walk(body)), 1
        )
        self.assertTrue(
            any(
                isinstance(item, M.If) and item.cond == "a[i] % 2 != 0"
                for item in walk(body)
            )
        )
        texts = [item.text for item in walk(body) if isinstance(item, M.Simple)]
        self.assertFalse(
            any(
                "Ошибка" in text or "Введите" in text or text in {"Вывод", "Вывод "}
                for text in texts
            )
        )

        self.assertIn("n = k", texts)

    def test_direct_standalone_reads_and_adjacent_checks(self) -> None:
        for validation in (
            "!cin || n<1 || n>100",
            "cin.fail() || n<1 || n>100",
            "n<1 || n>100",
        ):
            with self.subTest(validation=validation):
                body = build(
                    'int main(){int n; cout<<"Введите число:"; cin>>n; if('
                    + validation
                    + '){cout<<"Неверное число";return 1;} use(n);return 0;}'
                )
                self.assertEqual(body.items[0], M.Simple(M.INPUT, "Ввод n"))
                self.assertFalse(any(isinstance(item, M.If) for item in walk(body)))
                self.assertIn(M.Simple(M.PROCESS, "use(n)"), body.items)

    def test_direct_indexed_for_and_while_variants(self) -> None:
        loops = [
            'for(int i=0;i<n;i++){cin>>a[i];if(cin.fail()){cout<<"Ошибка";return 1;}}',
            "for(int i=0;i<n;i++){cin>>a[i];}",
            'i=0;while(i<n){if(!(cin>>a[i])){cout<<"Ошибка";return 1;}i++;}',
            'i=0;while(i<n && (cin>>a[i])){i++;}if(i!=n){cout<<"Ошибка";return 1;}',
        ]
        for loop in loops:
            with self.subTest(loop=loop):
                body = build(
                    "int main(){int n=10;int a[10];int i;" + loop + "return 0;}"
                )
                self.assertIn(M.Simple(M.INPUT, "Ввод a[n]"), body.items)
                self.assertFalse(
                    any(isinstance(item, (M.ForLoop, M.While)) for item in walk(body))
                )

    def test_direct_checks_remain_visible_in_show_and_full(self) -> None:
        for opts in ({"checks": "show"}, {"study": False}):
            with self.subTest(opts=opts):
                body = build(DIRECT_CODE, **opts)
                self.assertTrue(
                    any(
                        isinstance(item, M.If) and "cin >> n" in item.cond
                        for item in walk(body)
                    )
                )
                self.assertTrue(
                    any(
                        isinstance(item, M.If) and "cin >> a[i]" in item.cond
                        for item in walk(body)
                    )
                )

    def test_direct_validation_effects_and_unknown_types_remain_visible(self) -> None:
        cases = [
            DIRECT_CODE.replace(
                'cout << "Ошибка ввода";', 'cout << "Ошибка ввода" << ++counter;'
            ),
            DIRECT_CODE.replace(
                'cout << "Ошибка ввода";', 'cout << "Ошибка ввода" << report();'
            ),
            DIRECT_CODE.replace("return 1;", "record();return 1;"),
            DIRECT_CODE.replace("int a[100];", "Array a;"),
            DIRECT_CODE.replace("int n;", "Number n;"),
            "#define cin custom_stream\n" + DIRECT_CODE,
        ]
        for code in cases:
            with self.subTest(code=code):
                body = build(code)
                self.assertNotIn(M.Simple(M.INPUT, "Ввод a[n]"), body.items)
                self.assertTrue(
                    any(
                        isinstance(item, M.ForLoop)
                        and any(
                            isinstance(child, M.If) and "cin >> a[i]" in child.cond
                            for child in walk(item.body)
                        )
                        for item in walk(body)
                    )
                )

    def test_direct_external_index_is_not_removed_when_live(self) -> None:
        body = build(
            'int main(){int n=10;int a[10];int i;for(i=0;i<n;i++){if(!(cin>>a[i])){cout<<"Ошибка";return 1;}}observe(i);return 0;}'
        )
        self.assertNotIn(M.Simple(M.INPUT, "Ввод a[n]"), body.items)
        self.assertIn(M.Simple(M.PROCESS, "observe(i)"), body.items)

    def test_direct_index_observed_through_alias_keeps_loop(self) -> None:
        for declaration, expression in (
            ("int* saved=&i;", "*saved"),
            ("int& saved=i;", "saved"),
            ("auto saved=[&i](){return i;};", "saved()"),
            ("auto saved=[&](){return i;};", "saved()"),
        ):
            with self.subTest(declaration=declaration):
                body = build(
                    "int main(){int n=10;int a[10];int i;"
                    + declaration
                    + "for(i=0;i<n;i++){cin>>a[i];}observe("
                    + expression
                    + ");return 0;}"
                )
                self.assertNotIn(M.Simple(M.INPUT, "Ввод a[n]"), body.items)

    def test_scoped_later_loop_does_not_overwrite_external_index(self) -> None:
        body = build(
            "int main(){int n=10;int a[10];int i;for(i=0;i<n;i++){cin>>a[i];}for(int i=0;i<n;i++){work(i);}observe(i);return 0;}"
        )
        self.assertNotIn(M.Simple(M.INPUT, "Ввод a[n]"), body.items)

    def test_direct_local_index_does_not_modify_outer_index(self) -> None:
        body = build(
            'int main(){int n=10;int a[10];int i=7;for(int i=0;i<n;i++){if(!(cin>>a[i])){cout<<"Ошибка";return 1;}}observe(i);return 0;}'
        )
        self.assertIn(M.Simple(M.INPUT, "Ввод a[n]"), body.items)
        self.assertIn(M.Simple(M.PROCESS, "observe(i)"), body.items)

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
        self.assertIn("k = k + 1", texts)
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


class MatrixInputGroups(unittest.TestCase):
    @staticmethod
    def source() -> str:
        return (Path(__file__).parent / "fixtures/study/matrix.cpp").read_text(
            encoding="utf-8"
        )

    def assert_matrix_input(
        self, code: str, dimensions: str = "n, m", array: str = "a[n][m]"
    ) -> M.Seq:
        body = build(code)
        inputs = [
            item.text
            for item in walk(body)
            if isinstance(item, M.Simple) and item.kind == M.INPUT
        ]
        self.assertEqual(inputs, ["Ввод " + dimensions, "Ввод " + array])
        return body

    def test_current_matrix_hides_only_the_reading_protocol(self) -> None:
        body = self.assert_matrix_input(self.source())
        self.assertEqual(
            sum(isinstance(item, (M.ForLoop, M.While)) for item in walk(body)), 2
        )
        self.assertTrue(
            any(
                isinstance(item, M.If) and item.cond == "a[i][j] > b[i]"
                for item in walk(body)
            )
        )
        texts = [item.text for item in walk(body) if isinstance(item, M.Simple)]
        self.assertIn("b[i] = a[i][0]", texts)
        self.assertIn("b[i] = a[i][j]", texts)
        self.assertIn("Вывод b[n]", texts)
        self.assertFalse(
            any(
                "input" in text
                or "line" in text
                or "Ошибка" in text
                or "Введите" in text
                for text in texts
            )
        )

    def test_matrix_names_and_optional_boundary_checks_are_generic(self) -> None:
        code = self.source()
        for name, replacement in (
            ("a", "matrix"),
            ("n", "rows"),
            ("m", "columns"),
            ("i", "row"),
            ("j", "column"),
        ):
            code = re.sub(r"\b" + name + r"\b", replacement, code)
        self.assert_matrix_input(code, "rows, columns", "matrix[rows][columns]")
        code = (
            self.source()
            .replace("(!input.eof() && !isspace(input.peek())) ||", "")
            .replace(
                " ||\n                    (!input.eof() && !isspace(input.peek()))", ""
            )
        )
        self.assert_matrix_input(code)

    def test_constructor_per_row_matches_reused_reset_stream(self) -> None:
        code = self.source().replace("    istringstream input;\n", "")
        code = code.replace("input.str(line);", "istringstream input(line);", 1)
        first = code.index("for (i = 0; i < n; i++)")
        second = code.index("for (i = 0; i < n; i++)", first + 1)
        row = (
            code[first:second]
            .replace("input.clear();", "")
            .replace("input.str(line);", "istringstream rowInput(line);")
            .replace("input.", "rowInput.")
            .replace("input >>", "rowInput >>")
        )
        self.assert_matrix_input(code[:first] + row + code[second:])

    def test_direct_cin_nested_matrix_uses_the_same_rank_rules(self) -> None:
        body = build(
            'int main(){int a[20][20];int n=2,m=3;for(int row=0;row<n;row++){for(int column=0;column<m;column++){if(!(cin>>a[row][column])){cout<<"Ошибка";return 1;}}}return 0;}'
        )
        self.assertIn(M.Simple(M.INPUT, "Ввод a[n][m]"), body.items)
        self.assertFalse(any(isinstance(item, M.ForLoop) for item in walk(body)))

    def test_matrix_effects_macros_and_external_state_force_fallback(self) -> None:
        source = self.source()
        first = source.index("for (i = 0; i < n; i++)")
        second = source.index("for (i = 0; i < n; i++)", first + 1)
        cases = [
            source.replace("isspace(input.peek())", "classify(input.peek())"),
            source.replace("<< m\n", "<< ++m\n"),
            source.replace("return 1;", "audit();return 1;"),
            "#define peek change_state\n" + source,
            "#define isspace custom_space\n" + source,
            "int isspace(int x){return x;}\n" + source,
            source[:second] + "observe(input.eof());" + source[second:],
            source[:second] + "use(line);" + source[second:],
            source[:second] + "use(j);" + source[second:],
            source.replace("string line;", 'string line; string other; other="value";')
            .replace("line.clear();", "other.clear();")
            .replace(
                '        cout << "Массив максимумов строк:";',
                '        use(other); cout << "Массив максимумов строк:";',
            ),
        ]
        for number, code in enumerate(cases):
            with self.subTest(case=number):
                body = build(code)
                self.assertNotIn(M.Simple(M.INPUT, "Ввод a[n][m]"), body.items)

    def test_show_and_full_keep_matrix_input_conditions(self) -> None:
        for opts in ({"checks": "show"}, {"study": False}):
            with self.subTest(opts=opts):
                body = build(self.source(), **opts)
                self.assertTrue(
                    any(
                        isinstance(item, M.If) and "input >> n" in item.cond
                        for item in walk(body)
                    )
                )
                self.assertTrue(
                    any(
                        isinstance(item, M.If) and "input >> a[i][j]" in item.cond
                        for item in walk(body)
                    )
                )


class BufferedLocalIndex(unittest.TestCase):
    @staticmethod
    def source() -> str:
        return (Path(__file__).parent / "fixtures/study/pairs_while.cpp").read_text(
            encoding="utf-8"
        )

    def test_shared_buffer_declaration_and_local_read_counter(self) -> None:
        body = build(self.source())
        inputs = [
            item.text
            for item in walk(body)
            if isinstance(item, M.Simple) and item.kind == M.INPUT
        ]
        self.assertEqual(inputs, ["Ввод n", "Ввод a[n]"])
        self.assertEqual(
            [item.cond for item in walk(body) if isinstance(item, M.While)],
            ["i < n - 1"],
        )
        self.assertEqual(
            [item.cond for item in walk(body) if isinstance(item, M.If)],
            ["a[i] < a[j]", "j == n"],
        )
        self.assertFalse(any(isinstance(item, M.ForLoop) for item in walk(body)))
        self.assertIn(M.Simple(M.OUTPUT, "Вывод count"), body.items)

    def test_separate_buffers_and_renamed_local_index_are_equivalent(self) -> None:
        for buffers in ("string line, elements;", "string line;string elements;"):
            code = self.source().replace("string line, elements;", buffers)
            code = code.replace(
                "int k = 0; k < n; k++", "int position = 0; position < n; position++"
            ).replace("a[k]", "a[position]")
            body = build(code)
            self.assertIn(M.Simple(M.INPUT, "Ввод a[n]"), body.items)

    def test_effectful_error_and_mixed_declaration_are_preserved(self) -> None:
        for code in (
            self.source().replace("return 1;", "audit();return 1;"),
            self.source().replace(
                "string line, elements;", "string line, elements, keep = make_label();"
            ),
        ):
            with self.subTest(code=code):
                body = build(code)
                self.assertTrue(any(isinstance(item, M.ForLoop) for item in walk(body)))
                if "make_label" in code:
                    self.assertTrue(
                        any(
                            isinstance(item, M.Simple) and "make_label()" in item.text
                            for item in walk(body)
                        )
                    )

    def test_show_and_full_keep_buffered_checks(self) -> None:
        for opts in ({"checks": "show"}, {"study": False}):
            with self.subTest(opts=opts):
                body = build(self.source(), **opts)
                self.assertTrue(
                    any(
                        isinstance(item, M.If) and "input >> a[k]" in item.cond
                        for item in walk(body)
                    )
                )


class TextInputGroups(unittest.TestCase):
    @staticmethod
    def source() -> str:
        return (Path(__file__).parent / "fixtures/study/longest_word.cpp").read_text(
            encoding="utf-8"
        )

    def test_text_input_hides_guards_and_preserves_word_algorithm(self) -> None:
        body = build(self.source())
        self.assertIn(M.Simple(M.INPUT, "Ввод text"), body.items)
        self.assertFalse(any(isinstance(item, M.If) for item in body.items))
        loops = [item for item in body.items if isinstance(item, M.While)]
        self.assertEqual(len(loops), 1)
        self.assertEqual(loops[0].cond, "iss >> word")
        self.assertTrue(
            any(
                isinstance(item, M.If)
                and item.cond == "word.size() > longestWord.size()"
                for item in walk(body)
            )
        )
        texts = [item.text for item in walk(body) if isinstance(item, M.Simple)]
        for text in (
            "number = number + 1",
            "longestWord = word",
            "maxNumber = number",
            "Вывод longestWord, maxNumber",
        ):
            self.assertIn(text, texts)
        self.assertTrue(any("iss = text" in text for text in texts))
        self.assertFalse(any("Ошибка" in text or "Введите" in text for text in texts))

    def test_other_names_bounds_exit_codes_and_standalone_getline(self) -> None:
        code = self.source()
        for name, replacement in (
            ("text", "sentence"),
            ("word", "token"),
            ("number", "count"),
        ):
            code = re.sub(r"\b" + name + r"\b", replacement, code)
        code = (
            code.replace("1000", "2048")
            .replace("return 1;", "return 7;")
            .replace("Ошибка", "Неверный ввод")
            .replace("number++", "++number")
        )
        body = build(code)
        self.assertIn(M.Simple(M.INPUT, "Ввод sentence"), body.items)
        self.assertFalse(any(isinstance(item, M.If) for item in body.items))
        code = (
            self.source()
            .replace(
                "if (!getline(cin, text))",
                "getline(std::cin, text); if (std::cin.fail())",
            )
            .replace("number++", "++number")
        )
        body = build(code)
        self.assertIn(M.Simple(M.INPUT, "Ввод text"), body.items)
        self.assertFalse(any(isinstance(item, M.If) for item in body.items))

    def test_effectful_handlers_and_unknown_string_methods_stay(self) -> None:
        for code in (
            self.source().replace("return 1;", "audit(); return 1;"),
            self.source().replace('cout << "Ошибка', 'cout << ++number << "Ошибка'),
            self.source()
            .replace("text.empty()", "custom.empty()")
            .replace("string text;", "string text; Custom custom;"),
        ):
            with self.subTest(code=code):
                body = build(code)
                self.assertTrue(any(isinstance(item, M.If) for item in body.items))
                self.assertTrue(any(isinstance(item, M.While) for item in body.items))

    def test_only_proven_word_count_guard_is_hidden(self) -> None:
        later_stream = (
            '#include <sstream>\nstd::istringstream iss("external words");\n'
            + self.source()
            .replace("    istringstream iss(text);\n", "")
            .replace(
                "    if (number == 0)",
                "    istringstream iss(text);\n    if (number == 0)",
            )
        )
        for code, condition in (
            (
                self.source().replace("if (number == 0)", "if (maxNumber == 0)"),
                "maxNumber == 0",
            ),
            (
                self.source().replace("int number = 0;", "int number = 5;"),
                "number == 0",
            ),
            (
                self.source().replace("number++;", "if (word.size()>2) number++;"),
                "number == 0",
            ),
            (self.source().replace("number++;", "number++; number=0;"), "number == 0"),
            (
                self.source().replace("number++;", "number++; mutate(number);"),
                "number == 0",
            ),
            (later_stream, "number == 0"),
        ):
            with self.subTest(condition=condition, code=code):
                body = build(code)
                self.assertTrue(
                    any(
                        isinstance(item, M.If) and item.cond == condition
                        for item in body.items
                    )
                )

    def test_changed_text_and_aliases_do_not_become_input_guards(self) -> None:
        for code in (
            self.source().replace(
                "if (text.size() > 1000)", "text.clear(); if (text.size() > 1000)"
            ),
            self.source().replace("string word;", "string& alias=text; string word;"),
        ):
            body = build(code)
            self.assertTrue(
                any(
                    isinstance(item, M.If) and "text.size()" in item.cond
                    for item in body.items
                )
            )

    def test_string_macros_shadowing_show_and_full_preserve_guards(self) -> None:
        for prefix in (
            "#define size changed_size\n",
            "#define getline my_read\n",
            "using string = Custom;\n",
        ):
            body = build(prefix + self.source())
            self.assertTrue(
                any(
                    isinstance(item, M.If) and "size()" in item.cond
                    for item in body.items
                )
            )
        for opts in ({"checks": "show"}, {"study": False}):
            body = build(self.source(), **opts)
            self.assertEqual(sum(isinstance(item, M.If) for item in body.items), 4)

    def test_other_functions_keep_string_guards(self) -> None:
        code = (
            self.source().replace("int main()", "int helper()")
            + "\nint main(){return 0;}"
        )
        src = code.encode()
        tree, spec, errors = P.parse_source(src, P.guess_language("input.cpp", code))
        source = project.Source("input.cpp", src, spec, tree, errors)
        charts = project.charts(
            source,
            Opts(checks="hide"),
            P.collect_known_names(src, tree.root_node, spec),
        )
        body = next(chart.body for chart in charts if not chart.info["main"])
        self.assertEqual(sum(isinstance(item, M.If) for item in body.items), 4)


if __name__ == "__main__":
    unittest.main()
