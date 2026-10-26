"""Проверки учебной семантики C++ и безопасного подробного режима."""

import unittest
from pathlib import Path
from types import SimpleNamespace

from blockwright import vendored

vendored.activate()

from blockwright import model as M
from blockwright import parse as P
from blockwright import project


def options(study: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        study=study,
        keep_std=False,
        lang="ru",
        io_style="pretty",
        for_style="decision",
        return_style="auto",
        end_label="Конец",
    )


def chart(code: str, study: bool = True) -> M.Seq:
    src = code.encode()
    tree, spec, errors = P.parse_source(src, P.guess_language("study.cpp", code))
    source = project.Source("study.cpp", src, spec, tree, errors)
    known = P.collect_known_names(src, tree.root_node, spec)
    return project.charts(source, options(study), known)[0].body


class StudySemantics(unittest.TestCase):
    def test_io_direction_does_not_depend_on_output_text(self) -> None:
        body = chart(
            'int main(){int x; std::cout << "Ввод x"; std::cin >> x; return 0;}'
        )
        self.assertEqual([item.kind for item in body.items[:2]], ["output", "input"])
        self.assertEqual(body.items[1].text, "Ввод x")

    def test_declarations_preserve_computations_and_constructors(self) -> None:
        body = chart(
            "int main(){int x; int a[10]; int n = read(); Widget w; Widget z(make()); int b[size()]; return f();}"
        )
        texts = [item.text for item in body.items if isinstance(item, M.Simple)]
        self.assertIn("n = read()", texts)
        self.assertIn("Widget w", texts)
        self.assertIn("Widget z(make())", texts)
        self.assertIn("int b[size()]", texts)
        self.assertNotIn("int x", texts)
        self.assertNotIn("int a[10]", texts)
        self.assertEqual(type(body.items[-1]).__name__, "Return")
        self.assertEqual(body.items[-1].value, "f()")
        self.assertTrue(body.items[-1].main)

    def test_lab2_input_validation_and_loop_keep_branches(self) -> None:
        source = project.load(str(Path(__file__).parent / "fixtures/study/lab2.cpp"))
        body = project.charts(source, options(), source.known)[0].body
        self.assertEqual(body.items[0], M.Simple("input", "Ввод x"))
        check = body.items[1]
        self.assertIsInstance(check, M.If)
        self.assertEqual(check.cond, "Ошибка ввода?")
        self.assertEqual(check.then_.items[0], M.Simple("output", "Ошибка ввода"))
        self.assertEqual(check.then_.items[-1].value, "1")
        self.assertEqual(
            body.items[2],
            M.Simple(M.PROCESS, "power = 1.0; sum = 1.0; sign = -1"),
        )
        self.assertIsInstance(body.items[3], M.ForLoop)
        loop = next(item for item in body.items if isinstance(item, M.ForLoop))
        self.assertEqual(loop.init.text, "i = 1")
        self.assertEqual(loop.update.text, "i = i + 1")
        self.assertEqual(len(loop.body.items), 3)
        finite = next(
            item for item in body.items if isinstance(item, M.If) and item is not check
        )
        self.assertEqual(finite.cond, "Сумма конечна?")
        self.assertEqual(finite.then_.items, [])
        self.assertEqual(finite.else_.items[-1].value, "1")
        outputs = [
            item.text
            for item in body.items
            if isinstance(item, M.Simple) and item.kind == "output"
        ]
        self.assertEqual(outputs, ["Вывод x, sum"])

    def test_arbitrary_conditions_and_short_circuit_effects_are_preserved(self) -> None:
        body = chart(
            "int main(){int x; if (ready() && (std::cin >> x)) use(x); if (!std::isfinite(next())) fail(); return 0;}"
        )
        self.assertIn("ready()", body.items[0].cond)
        self.assertIn("cin >> x", body.items[0].cond)
        self.assertIn("next()", body.items[1].cond)

    def test_finite_condition_polarity_and_throw(self) -> None:
        body = chart(
            "double f(double sum){if (std::isfinite(sum)) return sum; throw error();}"
        )
        self.assertEqual(body.items[0].cond, "sum конечна?")
        ret = body.items[0].then_.items[0]
        self.assertEqual(ret.value, "sum")
        self.assertFalse(ret.main)
        self.assertTrue(body.items[1].terminal)
        self.assertIn("error()", body.items[1].text)

    def test_detailed_mode_keeps_legacy_ir(self) -> None:
        body = chart("int main(){int x; std::cin >> x; return 0;}", study=False)
        self.assertEqual(body.items[0], M.Simple(M.PROCESS, "int x"))
        self.assertEqual(body.items[1].kind, M.IO)
        self.assertEqual(body.items[-1], M.Simple(M.TERMINATOR, "Конец", True))

    def test_syntax_errors_are_not_silently_charted(self) -> None:
        with self.assertRaisesRegex(ValueError, "study.cpp.*ошиб"):
            chart("int main(){ int x = ; return 0; }")

    def test_similar_stringstream_with_extra_work_is_not_elided(self) -> None:
        body = chart(
            "int main(){std::string line; std::getline(std::cin,line); std::istringstream input(line); log(line); if (!(input >> x) || (input >> extra) || !std::isfinite(x)) fail(); return 0;}"
        )
        text = " ".join(item.text for item in body.items if isinstance(item, M.Simple))
        self.assertIn("istringstream input(line)", text)
        self.assertIn("log(line)", text)

    def test_shadowed_standard_names_preserve_original_operations(self) -> None:
        # Выбираем main отдельно: первая функция — пользовательский isfinite.
        code = "bool isfinite(double x){return false;} int main(){Sink cout; double x; cout << x; if (!isfinite(x)) fail(); std::cout << x; return 0;}"
        src = code.encode()
        tree, spec, errors = P.parse_source(src, P.guess_language("study.cpp", code))
        source = project.Source("study.cpp", src, spec, tree, errors)
        body = project.charts(
            source, options(), P.collect_known_names(src, tree.root_node, spec)
        )[1].body
        self.assertEqual(body.items[1], M.Simple(M.PROCESS, "cout << x"))
        self.assertEqual(body.items[2].cond, "!isfinite(x)")
        self.assertEqual(body.items[3].kind, "output")

    def test_stringstream_buffer_used_in_branch_is_not_hidden(self) -> None:
        body = chart(
            "int main(){std::string line; std::getline(std::cin,line); std::istringstream input(line); if (!(input >> x) || (input >> extra) || !std::isfinite(x)) {log(line); return 1;} return 0;}"
        )
        text = " ".join(item.text for item in body.items if isinstance(item, M.Simple))
        self.assertIn("istringstream input(line)", text)

    def test_function_parameter_stream_is_not_mistaken_for_cout(self) -> None:
        body = chart("int f(Sink& cout){cout << value; return 0;}")
        self.assertEqual(body.items[0], M.Simple(M.PROCESS, "cout << value"))

    def test_manipulator_arguments_with_side_effects_are_visible(self) -> None:
        body = chart(
            "int main(){std::cout << std::setprecision(next()); custom::fixed(); return 0;}"
        )
        self.assertIn("setprecision(next())", body.items[0].text)
        self.assertIn("custom::fixed()", body.items[1].text)

    def test_static_zero_initialization_is_preserved(self) -> None:
        body = chart("int f(){static int count; return ++count;}")
        self.assertEqual(body.items[0], M.Simple(M.PROCESS, "static int count"))

    def test_output_merging_does_not_cross_side_effects(self) -> None:
        body = chart("int main(){std::cout << x; log(); std::cout << y; return 0;}")
        self.assertEqual(
            [item.text for item in body.items[:3]], ["Вывод x", "log()", "Вывод y"]
        )

    def test_global_shadowed_stream_is_not_standard_io(self) -> None:
        body = chart("Sink cout; int main(){cout << x; return 0;}")
        self.assertEqual(body.items[0], M.Simple(M.PROCESS, "cout << x"))

    def test_stringstream_extra_character_used_later_remains_visible(self) -> None:
        body = chart(
            "int main(){std::string line; char extra; std::getline(std::cin,line); std::istringstream input(line); if (!(input >> x) || (input >> extra) || !std::isfinite(x)) return 1; use(extra); return 0;}"
        )
        text = " ".join(item.text for item in body.items if isinstance(item, M.Simple))
        self.assertIn("istringstream input(line)", text)

    def test_dynamic_error_output_retains_message_and_argument(self) -> None:
        body = chart(
            'int main(){std::cout << "Ошибка: введите ровно " << n << " целых чисел."; return 1;}'
        )
        self.assertIn("Ошибка", body.items[0].text)
        self.assertIn("n", body.items[0].text)
        self.assertIn("ровно", body.items[0].text)

    def test_literal_initialization_groups_are_bounded_and_ordered(self) -> None:
        body = chart(
            "int main(){int a=1; int b=-2; int c=3; int d=4; int e=5; return 0;}"
        )
        self.assertEqual(body.items[0], M.Simple(M.PROCESS, "a = 1; b = -2; c = 3"))
        self.assertEqual(body.items[1], M.Simple(M.PROCESS, "d = 4; e = 5"))

    def test_initializations_do_not_merge_across_observable_operations(self) -> None:
        body = chart(
            "int main(){int a=1; volatile int v=2; int b=3; Widget w(4); int c=5; static int s=6; int d=read(); int e=7; a=8; b=9; return 0;}"
        )
        texts = [item.text for item in body.items if isinstance(item, M.Simple)]
        self.assertEqual(
            texts,
            [
                "a = 1",
                "volatile int v=2",
                "b = 3",
                "Widget w(4)",
                "c = 5",
                "static int s=6",
                "d = read()",
                "e = 7",
                "a=8",
                "b=9",
            ],
        )

    def test_initialization_group_has_readable_length_limit(self) -> None:
        first = "first_" + "a" * 35
        second = "second_" + "b" * 35
        body = chart(f"int main(){{int {first}=1; int {second}=2; return 0;}}")
        self.assertEqual(body.items[0].text, f"{first} = 1")
        self.assertEqual(body.items[1].text, f"{second} = 2")


if __name__ == "__main__":
    unittest.main()
