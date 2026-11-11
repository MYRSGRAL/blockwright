"""Счётные while получают блок цикла без переноса управляющих действий."""

import unittest

from blockwright import model as M
from blockwright import parse as P
from blockwright import project, vendored
from blockwright.cli import Opts
from blockwright.geometry import validate_geometry, validate_ports
from blockwright.layout import layout
from tests.test_geometry import options
from tests.test_input_study import walk

vendored.activate()


def chart(code: str, style: str = "hexagon", study: bool = True) -> M.Seq:
    src = code.encode()
    tree, spec, errors = P.parse_source(src, P.guess_language("input.cpp", code))
    source = project.Source("input.cpp", src, spec, tree, errors)
    return project.charts(
        source,
        Opts(study=study, checks="hide", io_style="symbols", for_style=style),
        source.known,
    )[0].body


class CountedWhileTests(unittest.TestCase):
    def test_enclosing_if_must_not_change_initial_value_dependencies(self) -> None:
        for branch in (
            "if (++n) { while (i<10) { i++; } }",
            "if (n++ < 0) {} else { while (i<10) { i++; } }",
        ):
            with self.subTest(branch=branch):
                body = chart("int main(){int n=1,i=n;" + branch + "}")
                loop = next(item for item in walk(body) if isinstance(item, M.While))
                self.assertEqual(loop.style, "decision")
                self.assertEqual(loop.header, "")

    def test_nested_matrix_counters_keep_actions_and_get_hexagons(self) -> None:
        code = """int main(){
            int a[10][10],m=10,n=10,s=0,k=0,i=0,j=0;
            while(i<m){s=0;k=0;
                while(j<n){if(a[i][j]<0){k=k+1;s=s+a[i][j];}j=j+1;}
                j=0;i=i+1;
            }
        }"""
        for study in (False, True):
            with self.subTest(study=study):
                body = chart(code, study=study)
                loops = [item for item in walk(body) if isinstance(item, M.While)]
                self.assertEqual(len(loops), 2)
                self.assertTrue(all(loop.style == "hexagon" for loop in loops))
                frame = layout(body, options(study=study))
                headers = [s for s in frame.shapes if s["kind"] == M.PREP]
                self.assertEqual(
                    {s["text"] for s in headers},
                    {"i = 0; i<m; i=i+1", "j = 0; j<n; j=j+1"},
                )
                actions = "\n".join(s["text"] for s in frame.shapes)
                for action in ("i = i+1", "j = j+1", "j = 0"):
                    self.assertIn(action.replace(" ", ""), actions.replace(" ", ""))
                self.assertEqual(validate_geometry(frame), [])
                if study:
                    self.assertEqual(validate_ports(frame), [])

    def test_counter_forms(self) -> None:
        for condition, update in (
            ("i<n", "i++"),
            ("i<=n", "++i"),
            ("i>0", "i--"),
            ("i>=0", "i-=2"),
            ("i<n", "i+=2"),
            ("i<n", "i=i+1"),
            ("i>0", "i=i-1"),
        ):
            with self.subTest(update=update):
                loop = next(
                    x
                    for x in walk(
                        chart(
                            f"int main(){{int i=0,n=10;while({condition}){{work(i);{update};}}}}"
                        )
                    )
                    if isinstance(x, M.While)
                )
                self.assertEqual(loop.style, "hexagon")
                self.assertEqual(loop.header, f"i = 0; {condition}; {update}")

    def test_initialization_is_taken_from_the_nearest_assignment(self) -> None:
        for prefix, expected in (
            ("int i; i=3;", "i = 3"),
            ("int i=0; i=5;", "i = 5"),
            ("int n=10; int i=n;", "i = n"),
            ("int i=0; {int j=2;", "i = 0"),
        ):
            with self.subTest(prefix=prefix):
                suffix = "}" if "{" in prefix else ""
                body = chart(f"int main(){{{prefix}while(i<10){{i++;}}{suffix}}}")
                loop = next(x for x in walk(body) if isinstance(x, M.While))
                self.assertEqual(loop.style, "hexagon")
                self.assertEqual(loop.header, f"{expected}; i<10; i++")

    def test_unknown_or_changed_initialization_never_becomes_zero(self) -> None:
        for prefix in (
            "int i;",
            "int i=0; i++;",
            "int i=0; i+=2;",
            "int i=0; if(flag)i=2;",
            "int i=0; change(i);",
            "int i=0; change();",
            "int i=next();",
            "int n=5,i=n; n=8;",
            "int n=5; int i=n; {int n=8;",
            "int n=5; int i=n; {int n;",
            "int n=5; int &r=n; int i=n; r=8;",
            "int i=0; {int i;",
            "int i=0; int &r=i; i=0; r=3;",
            "int i=0; int *p=&i; i=0; p[0]=3;",
            "int i=0; remember(i); i=0; alias=3;",
        ):
            with self.subTest(prefix=prefix):
                suffix = "}" if "{" in prefix else ""
                body = chart(f"int main(){{{prefix}while(i<10){{i++;}}{suffix}}}")
                loop = next(x for x in walk(body) if isinstance(x, M.While))
                self.assertEqual(loop.style, "decision")
                self.assertEqual(loop.cond, "i<10")

    def test_nested_counter_requires_the_same_reset_on_later_entries(self) -> None:
        for reset, expected_style in (
            ("j=0;", "hexagon"),
            ("", "decision"),
            ("j=2;", "decision"),
            ("if(flag)j=0;", "decision"),
            ("if(flag)continue;j=0;", "decision"),
        ):
            with self.subTest(reset=reset):
                body = chart(
                    "int main(){int i=0,j=0;while(i<10){"
                    f"while(j<10){{j++;}}{reset}i++;}}}}"
                )
                loops = [x for x in walk(body) if isinstance(x, M.While)]
                self.assertEqual(loops[1].style, expected_style)
                if expected_style == "hexagon":
                    self.assertEqual(loops[1].header, "j = 0; j<10; j++")

    def test_conditional_counter_step_stays_in_the_body(self) -> None:
        body = chart("int main(){int i=0;while(i<10){if(flag)i++;}}")
        loop = next(x for x in walk(body) if isinstance(x, M.While))
        self.assertEqual(loop.style, "decision")
        self.assertIsInstance(loop.body.items[0], M.If)

    def test_outer_condition_must_not_change_a_dependent_initial_value(self) -> None:
        body = chart("""int main(){int n=0,j=n;
            while(n++<3){while(j<10){j++;}j=n;}
        }""")
        loops = [x for x in walk(body) if isinstance(x, M.While)]
        self.assertEqual(loops[1].style, "decision")

    def test_general_or_ambiguous_while_keeps_decision(self) -> None:
        for condition, body in (
            ("ready()", "work();"),
            ("i<n", "if(flag)i++;"),
            ("i<n", "j++;"),
            ("i<n", "i--;"),
            ("i<n", "i+=0;"),
            ("i<n && ready()", "i++;"),
            ("i<n", "i=next();"),
            ("i<limit()", "i++;"),
        ):
            with self.subTest(condition=condition, body=body):
                loop = next(
                    x
                    for x in walk(
                        chart(
                            f"int main(){{int i=0,n=10,j=0;while({condition}){{{body}}}}}"
                        )
                    )
                    if isinstance(x, M.While)
                )
                self.assertEqual(loop.style, "decision")

    def test_decision_mode_preserves_diamonds(self) -> None:
        body = chart("int main(){int i=0;while(i<10){i++;}}", style="decision")
        frame = layout(body, options())
        self.assertFalse(any(s["kind"] == M.PREP for s in frame.shapes))
        self.assertTrue(any(s["kind"] == M.DECISION for s in frame.shapes))

    def test_break_and_continue_remain_in_original_body(self) -> None:
        body = chart("""int main(){int i=0;
            while(i<10){if(skip())continue;if(stop())break;i++;}
        }""")
        loop = next(x for x in walk(body) if isinstance(x, M.While))
        self.assertEqual(loop.style, "hexagon")
        self.assertEqual(
            [x.kind for x in walk(loop.body) if isinstance(x, M.Jump)],
            ["continue", "break"],
        )
        frame = layout(body, options())
        self.assertEqual(validate_geometry(frame), [])
        self.assertEqual(validate_ports(frame), [])
