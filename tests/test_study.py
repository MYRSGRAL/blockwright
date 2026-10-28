"""Проверки учебной семантики C++ и безопасного подробного режима."""

import unittest
from pathlib import Path
from types import SimpleNamespace

from blockwright import vendored

vendored.activate()

from blockwright import model as M
from blockwright import parse as P
from blockwright import project


def options(study: bool = True, checks: str = "show") -> SimpleNamespace:
    return SimpleNamespace(
        study=study,
        checks=checks,
        keep_std=False,
        lang="ru",
        io_style="pretty",
        for_style="decision",
        return_style="auto",
        end_label="Конец",
    )


def chart(code: str, study: bool = True, checks: str = "show") -> M.Seq:
    src = code.encode()
    tree, spec, errors = P.parse_source(src, P.guess_language("study.cpp", code))
    source = project.Source("study.cpp", src, spec, tree, errors)
    known = P.collect_known_names(src, tree.root_node, spec)
    return project.charts(source, options(study, checks), known)[0].body


_RETRY_INPUT = r"""while (true) {
    cout << "Введите число: ";
    if (cin >> r) {
        break;
    } else {
        cout << "Это не число." << endl;
        cin.clear();
        cin.ignore(10000, '\n');
    }
}"""


class StudySemantics(unittest.TestCase):
    def test_string_stream_construction_is_an_action_without_cpp_type(self) -> None:
        for declaration in (
            "std::istringstream words(text);",
            "std::istringstream words{text};",
        ):
            with self.subTest(declaration=declaration):
                body = chart("int main(){std::string text;" + declaration + "}")
                self.assertEqual(body.items, [M.Simple(M.PROCESS, "words = text")])

    def test_unknown_stream_constructor_is_preserved(self) -> None:
        for code in (
            "std::string text;int main(){using text=int;std::istringstream words(text);}",
            "struct istringstream{};int main(){std::string text;istringstream words(text);}",
            "int main(){Widget text;std::istringstream words(text);}",
            "int main(){std::string text;std::istringstream words(make_text());}",
        ):
            with self.subTest(code=code):
                self.assertTrue(
                    any(
                        isinstance(item, M.Simple) and "istringstream" in item.text
                        for item in chart(code).items
                    )
                )

    def test_standalone_increment_and_decrement_have_explicit_assignment(self) -> None:
        for expression, expected in (
            ("count++", "count = count + 1"),
            ("++count", "count = count + 1"),
            ("count--", "count = count - 1"),
            ("--count", "count = count - 1"),
            ("((count++))", "count = count + 1"),
        ):
            with self.subTest(expression=expression):
                body = chart("int main(){int count=0;" + expression + ";}")
                self.assertEqual(body.items[-1], M.Simple(M.PROCESS, expected))

    def test_increment_inside_expression_and_full_mode_keep_cpp(self) -> None:
        for statement in ("x = count++", "x = ++count", "use(count++)", "a[i++]++"):
            with self.subTest(statement=statement):
                body = chart("int main(){int x,count,i,a[10];" + statement + ";}")
                self.assertTrue(
                    any(
                        isinstance(item, M.Simple) and item.text == statement
                        for item in body.items
                    )
                )
        body = chart("int main(){int count=0;count++;}", study=False)
        self.assertEqual(body.items[-1], M.Simple(M.PROCESS, "count++"))

    def test_loop_step_and_body_use_the_same_increment_notation(self) -> None:
        body = chart("int main(){int count=0;for(int i=0;i<10;i++){count++;}}")
        loop = body.items[-1]
        self.assertIsInstance(loop, M.ForLoop)
        self.assertEqual(loop.update, M.Simple(M.PROCESS, "i = i + 1"))
        self.assertEqual(loop.body.items, [M.Simple(M.PROCESS, "count = count + 1")])

    def test_overloaded_and_macro_increments_remain_explicit_cpp(self) -> None:
        for code in (
            "struct Counter{};int main(){Counter count;count++;}",
            "#define count custom()\nint main(){int count;count++;}",
        ):
            with self.subTest(code=code):
                self.assertEqual(chart(code).items[-1], M.Simple(M.PROCESS, "count++"))

    def test_array_rank_distinguishes_matrices_from_arrays_of_pointers(self) -> None:
        from blockwright.study import StudyBuilder

        for code, expected in (
            (b"int main(){int a[20][20], b[20]; int* pointers[20];}", {"a": 2, "b": 1}),
            (b"int a[4];int main(){int a[4][4];}", {}),
            (b"int main(){volatile int a[4][4];}", {}),
        ):
            with self.subTest(code=code):
                tree, spec, _ = P.parse_source(code, P.guess_language("rank.cpp", ""))
                function = tree.root_node.named_children[-1]
                builder = StudyBuilder(code, options(), spec=spec)
                builder.build_body(function.child_by_field_name("body"), is_main=True)
                self.assertEqual(builder._array_ranks, expected)

    def test_initialized_arrays_keep_values_without_type(self) -> None:
        for declaration, text in (
            ("bool seen[10] = {};", "seen[10] = {}"),
            ("int a[3] = {1, 2, 3};", "a[3] = {1, 2, 3}"),
            ("double matrix[2][2] = {};", "matrix[2][2] = {}"),
        ):
            with self.subTest(declaration=declaration):
                self.assertEqual(
                    chart("int main(){" + declaration + "}").items,
                    [M.Simple(M.PROCESS, text)],
                )

    def test_plain_declarations_are_hidden_and_explicit_values_remain(self) -> None:
        body = chart(
            'int main(){int n,i; int *p; double a[100]; std::string line; std::string label="имя"; int k=0; Widget work; return 0;}'
        )
        texts = [i.text for i in body.items if isinstance(i, M.Simple)]
        self.assertEqual(texts, ['label = "имя"', "k = 0", "Widget work"])

    def test_dynamic_input_prompt_is_part_of_input_but_effects_remain(self) -> None:
        body = chart(
            'int main(){int n=3,x; std::cout << "Введите " << n << " чисел:"; std::cin >> x; return 0;}'
        )
        self.assertEqual(body.items[1], M.Simple(M.INPUT, "Ввод x"))
        for value in ("++n", "count()", "widget"):
            body = chart(
                'int main(){int n=3,x; Widget widget; std::cout << "Введите " << '
                + value
                + "; std::cin >> x; return 0;}"
            )
            self.assertTrue(
                any(isinstance(i, M.Simple) and value in i.text for i in body.items)
            )

    def test_hide_checks_keeps_lab2_algorithm_and_input(self) -> None:
        source = project.load(str(Path(__file__).parent / "fixtures/study/lab2.cpp"))
        body = project.charts(source, options(checks="hide"), source.known)[0].body
        self.assertEqual(body.items[0], M.Simple(M.INPUT, "Ввод x"))
        self.assertFalse(any(isinstance(item, M.If) for item in body.items))
        self.assertTrue(any(isinstance(item, M.ForLoop) for item in body.items))
        self.assertEqual(body.items[-2], M.Simple(M.OUTPUT, "Вывод x, sum"))
        self.assertEqual(body.items[-1], M.Return("0", True))

    def test_hide_checks_keeps_observable_work_in_error_branches(self) -> None:
        for action in (
            'std::cout << "Ошибка" << ++counter;',
            "report();",
            'std::cout << "Ошибка"; save();',
        ):
            body = chart(
                "int main(){double sum=0; if(!std::isfinite(sum)){"
                + action
                + "return 1;} return 0;}",
                checks="hide",
            )
            self.assertTrue(any(isinstance(item, M.If) for item in body.items))
        body = chart(
            'int main(){if(!std::isfinite(sum)){std::cout << "Ошибка"; return 1;} else {compute();} return 0;}',
            checks="hide",
        )
        self.assertIsInstance(body.items[0], M.If)

    def test_hide_checks_preserves_reads_and_other_function_results(self) -> None:
        body = chart(
            'int main(){if(!(std::cin >> x)){std::cout << "Ошибка"; return 1;} compute(x); return 0;}',
            checks="hide",
        )
        self.assertEqual(body.items[0], M.Simple(M.INPUT, "Ввод x"))
        self.assertFalse(any(isinstance(item, M.If) for item in body.items))
        retry = chart(
            "int main(){double r;" + _RETRY_INPUT + "return 0;}", checks="hide"
        )
        self.assertEqual(
            retry.items, [M.Simple(M.INPUT, "Ввод r"), M.Return("0", True)]
        )
        body = chart(
            'double f(double x){if(!std::isfinite(x)){std::cout << "Ошибка"; return 1;} return x;}',
            checks="hide",
        )
        self.assertIsInstance(body.items[0], M.If)

    def test_macro_names_disable_environment_and_retry_shortening(self) -> None:
        for define, call in (
            ("#define system(x) report(x)", 'system("pause")'),
            ("#define system report", 'std::system("pause")'),
            ("#define SetConsoleCP(x) report(x)", "SetConsoleCP(CP_UTF8)"),
        ):
            with self.subTest(define=define):
                body = chart(define + f"\nint main(){{{call}; return 0;}}")
                self.assertEqual(len(body.items), 2)
        for name in ("cin", "cout"):
            body = chart(
                f"#define {name} instrumented\nint main(){{double r;"
                + _RETRY_INPUT
                + "return 0;}"
            )
            self.assertEqual(body.items[0].cond, "true")

    def test_appendix_retry_input_becomes_one_error_check_and_retry(self) -> None:
        code = (
            "int main(){SetConsoleOutputCP(CP_UTF8); SetConsoleCP(CP_UTF8); "
            "double r; const double pi = 3.1415; "
            + _RETRY_INPUT
            + " double P = 2 * pi * r; double S = pi * r * r; "
            "P = (int)(P * 10 + 0.5) / 10.0; S = (int)(S * 10 + 0.5) / 10.0; "
            'cout << "Периметр круга: " << P << endl; '
            'cout << "Площадь круга: " << S << endl; system("pause"); return 0;}'
        )
        body = chart(code)
        self.assertEqual(body.items[1], M.Simple(M.INPUT, "Ввод r"))
        loop = body.items[2]
        self.assertIsInstance(loop, M.While)
        self.assertEqual(loop.cond, "Ошибка ввода?")
        self.assertEqual(
            loop.body.items,
            [
                M.Simple(M.OUTPUT, "Это не число."),
                M.Simple(M.PROCESS, "Очистить ошибочный ввод"),
                M.Simple(M.INPUT, "Ввод r"),
            ],
        )
        texts = " ".join(item.text for item in body.items if isinstance(item, M.Simple))
        self.assertNotIn("pause", texts)
        self.assertIn("P = целая часть(P * 10 + 0.5) / 10.0", texts)
        self.assertIn("S = целая часть(S * 10 + 0.5) / 10.0", texts)

    def test_retry_input_falls_back_for_effects_flags_and_other_cleanup(self) -> None:
        alternatives = [
            _RETRY_INPUT.replace("break;", "saved(); break;"),
            _RETRY_INPUT.replace("cin.clear();", "saved(); cin.clear();"),
            _RETRY_INPUT.replace("cin.clear();", "cin.clear(state);"),
            _RETRY_INPUT.replace("10000", "limit()"),
            _RETRY_INPUT.replace("'\\n'", "'x'"),
            _RETRY_INPUT.replace("cin >> r", "(cin >> r) && ready()"),
            _RETRY_INPUT.replace('"Это не число."', '"Это не число." << ++counter'),
            _RETRY_INPUT.replace('"Введите число: "', '"Введите число: " << prompt()'),
            _RETRY_INPUT.replace('"Введите число: "', '"Контрольное сообщение"'),
            _RETRY_INPUT.replace("cin >> r", "int status=setup(); cin >> r"),
            _RETRY_INPUT + " if(cin.eof()) inspect();",
            "Stream cin; " + _RETRY_INPUT,
        ]
        for snippet in alternatives:
            with self.subTest(snippet=snippet):
                body = chart("int main(){double r;" + snippet + "return 0;}")
                loop = next(item for item in body.items if isinstance(item, M.While))
                self.assertEqual(loop.cond, "true")
                self.assertTrue(any(isinstance(item, M.If) for item in loop.body.items))

    def test_retry_input_pause_and_cast_stay_detailed_in_full_mode(self) -> None:
        body = chart(
            "int main(){double r; "
            + _RETRY_INPUT
            + 'r = (int)(r * 10 + 0.5) / 10.0; system("pause"); return 0;}',
            study=False,
        )
        loop = next(item for item in body.items if isinstance(item, M.While))
        self.assertEqual(loop.cond, "true")
        self.assertEqual(loop.body.items[1].then_.items, [M.Jump("break")])
        texts = " ".join(item.text for item in body.items if isinstance(item, M.Simple))
        self.assertIn("(int)(r * 10 + 0.5)", texts)
        self.assertIn('system("pause")', texts)

    def test_only_standalone_unshadowed_literal_pause_is_hidden(self) -> None:
        self.assertEqual(
            chart('int main(){system("pause"); std::system("pause"); return 0;}').items,
            [M.Return("0", True)],
        )
        cases = [
            'int main(){system("pause & other"); return 0;}',
            "int main(){system(command); return 0;}",
            'int main(){if(system("pause")) inspect(); return 0;}',
            'int main(){int status=system("pause"); return 0;}',
            'int main(){custom::system("pause"); return 0;}',
            'int main(){Callable system; system("pause"); return 0;}',
        ]
        for code in cases:
            with self.subTest(code=code):
                body = chart(code)
                self.assertGreater(len(body.items), 1)
        body = chart('int system(const char*); int main(){system("pause"); return 0;}')
        self.assertIn('system("pause")', body.items[0].text)

    def test_int_cast_label_keeps_truncation_and_operand_effects(self) -> None:
        body = chart(
            "int main(){x = (int)(-1.8) / 10.0; y = (int)next(); z = (long)next(); return 0;}"
        )
        self.assertEqual(body.items[0].text, "x = целая часть(-1.8) / 10.0")
        self.assertEqual(body.items[1].text, "y = целая часть(next())")
        self.assertEqual(body.items[2].text, "z = (long)next()")
        body = chart(
            'int main(){x = (int)((int)next()); std::cout << "(int)"; return 0;}'
        )
        self.assertEqual(body.items[0].text, "x = целая часть(целая часть(next()))")
        self.assertEqual(body.items[1].text, "Вывод (int)")

    def test_console_setup_is_hidden_only_in_study_mode(self) -> None:
        calls = [
            "SetConsoleOutputCP(CP_UTF8)",
            "SetConsoleCP(65001)",
            'setlocale(LC_ALL, "Russian")',
            'std::setlocale(LC_CTYPE, "")',
            "std::ios::sync_with_stdio(false)",
            "std::ios_base::sync_with_stdio(true)",
            "std::cin.tie(nullptr)",
            "std::cout.tie(0)",
        ]
        for call in calls:
            with self.subTest(call=call):
                code = f"int main(){{{call}; int x=read(); return 0;}}"
                body = chart(code)
                self.assertEqual(body.items[0], M.Simple(M.PROCESS, "x = read()"))
                self.assertEqual(len(body.items), 2)
                detailed = chart(code, study=False)
                self.assertGreater(len(detailed.items), len(body.items))

    def test_console_setup_preserves_computations_and_observed_results(self) -> None:
        for call in (
            "SetConsoleOutputCP(next_codepage())",
            "SetConsoleCP(++cp)",
            "setlocale(LC_ALL, locale_name())",
            "std::ios::sync_with_stdio(flag())",
            "std::cin.tie(get_stream())",
            "custom::SetConsoleCP(CP_UTF8)",
            'system("other")',
        ):
            with self.subTest(call=call):
                body = chart(f"int main(){{{call}; return 0;}}")
                self.assertEqual(len(body.items), 2)
        body = chart("int main(){if(!SetConsoleCP(CP_UTF8)){return 1;} return 0;}")
        self.assertIsInstance(body.items[0], M.If)
        self.assertIn("SetConsoleCP", body.items[0].cond)

    def test_user_defined_console_names_are_not_hidden(self) -> None:
        for code in (
            "void SetConsoleCP(int cp){} int main(){SetConsoleCP(CP_UTF8); return 0;}",
            "int main(){auto SetConsoleOutputCP=callback; SetConsoleOutputCP(CP_UTF8); return 0;}",
            "int main(){Stream cin; cin.tie(nullptr); return 0;}",
            "int main(){int CP_UTF8=read(); SetConsoleCP(CP_UTF8); return 0;}",
        ):
            with self.subTest(code=code):
                # В первом примере пользовательская функция предшествует main.
                src = code.encode()
                tree, spec, errors = P.parse_source(
                    src, P.guess_language("study.cpp", code)
                )
                source = project.Source("study.cpp", src, spec, tree, errors)
                known = P.collect_known_names(src, tree.root_node, spec)
                body = project.charts(source, options(), known)[-1].body
                self.assertTrue(
                    any(
                        isinstance(i, M.Simple)
                        and ("SetConsole" in i.text or "tie(" in i.text)
                        for i in body.items
                    )
                )

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
        self.assertIn("input = line", text)
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
        self.assertIn("input = line", text)

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
        self.assertIn("input = line", text)

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

    def test_finite_error_output_preserves_increment_and_call(self) -> None:
        for expression in ("++counter", "report_failure()"):
            with self.subTest(expression=expression):
                body = chart(
                    "int main(){double sum=0; int counter=0; if (!std::isfinite(sum)) {"
                    'std::cout << "Ошибка:" << '
                    + expression
                    + "; return 1;} return 0;}"
                )
                branch = next(item for item in body.items if isinstance(item, M.If))
                self.assertIn(expression, branch.then_.items[0].text)
                self.assertEqual(branch.then_.items[-1].value, "1")

    def test_input_error_output_preserves_increment_and_call(self) -> None:
        for expression in ("++counter", "report_failure()"):
            with self.subTest(expression=expression):
                body = chart(
                    "int main(){double x; char extra; int counter=0; std::string line; "
                    "std::getline(std::cin,line); std::istringstream input(line); "
                    "if (!(input >> x) || (input >> extra) || !std::isfinite(x)) {"
                    'std::cout << "Ошибка:" << '
                    + expression
                    + "; return 1;} return 0;}"
                )
                branch = next(item for item in body.items if isinstance(item, M.If))
                self.assertEqual(branch.cond, "Ошибка ввода?")
                self.assertIn(expression, branch.then_.items[0].text)

    def test_static_error_output_shortening_uses_ast_not_text_prefix(self) -> None:
        body = chart(
            "int main(){double sum=0; if (!std::isfinite(sum)) {"
            'std::cout << "Сбой вычисления" << std::endl; return 1;} return 0;}'
        )
        branch = next(item for item in body.items if isinstance(item, M.If))
        self.assertEqual(
            branch.then_.items[0], M.Simple(M.OUTPUT, "Ошибка: результат не конечен")
        )


if __name__ == "__main__":
    unittest.main()
