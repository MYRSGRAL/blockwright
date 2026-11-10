"""Краткие обозначения и группы действий для схем по учебному образцу."""

import unittest

from blockwright import vendored

vendored.activate()

from blockwright import model as M
from blockwright import parse as P
from blockwright import project
from blockwright.cli import Opts, build_parser
from blockwright.layout import make_shape
from tests.test_input_study import walk


def build(code: str, *, study: bool = True, style: str = "symbols") -> M.Seq:
    src = code.encode()
    tree, spec, errors = P.parse_source(src, P.guess_language("symbols.cpp", code))
    source = project.Source("symbols.cpp", src, spec, tree, errors)
    known = P.collect_known_names(src, tree.root_node, spec)
    return project.charts(source, Opts(study=study, io_style=style), known)[0].body


class SymbolicStudy(unittest.TestCase):
    def test_io_uses_operands_and_preserves_output_expressions(self) -> None:
        body = build(
            'int main(){int m,n,k,s;cin>>m;cin>>n;cout<<"Количество: "<<k;cout<<"Сумма: "<<s;}'
        )
        self.assertEqual(
            body.items, [M.Simple(M.INPUT, "m, n"), M.Simple(M.OUTPUT, "k, s")]
        )
        body = build('int main(){int i,k;cout<<"Строка "<<i+1<<": "<<k;}')
        self.assertEqual(body.items, [M.Simple(M.OUTPUT, "i+1, k")])

    def test_literal_messages_are_preserved(self) -> None:
        body = build('int main(){cout<<"Ошибка ввода";}')
        self.assertEqual(body.items, [M.Simple(M.OUTPUT, "Ошибка ввода")])

    def test_arithmetic_assignments_share_ordered_lines(self) -> None:
        body = build("int main(){int a[10][10],i,j,k,s;k=k+1;s=s+a[i][j];}")
        self.assertEqual(body.items, [M.Simple(M.PROCESS, "k = k+1\ns = s+a[i][j]")])
        shape = make_shape(M.PROCESS, body.items[0].text, Opts(io_style="symbols"))
        self.assertEqual(shape["lines"], ["k = k+1", "s = s+a[i][j]"])

    def test_group_does_not_absorb_effects_or_cross_control(self) -> None:
        for code in (
            "int main(){int a,b;a=f();b=a+1;}",
            "int main(){int a[10],i,s;i=i+1;s=a[i++];}",
            "int main(){int a,b;a=a+1;if(a>0){b=b+1;}}",
        ):
            with self.subTest(code=code):
                self.assertFalse(
                    any(
                        isinstance(item, M.Simple) and "\n" in item.text
                        for item in walk(build(code))
                    )
                )

    def test_processing_loops_and_predicates_are_preserved(self) -> None:
        body = build(
            "int main(){int a[10][10],m,n,i=0,j=0,k=0,s=0;"
            "while(i<m){s=0;k=0;while(j<n){if(a[i][j]<0){k=k+1;s=s+a[i][j];}j=j+1;}"
            'cout<<"Количество: "<<k;cout<<"Сумма: "<<s;j=0;i=i+1;}}'
        )
        items = list(walk(body))
        self.assertEqual(sum(isinstance(item, M.While) for item in items), 2)
        self.assertTrue(
            any(isinstance(item, M.If) and item.cond == "a[i][j]<0" for item in items)
        )
        self.assertIn(M.Simple(M.OUTPUT, "k, s"), items)
        self.assertIn(M.Simple(M.PROCESS, "j = 0\ni = i+1"), items)

    def test_existing_style_and_full_detail_remain_available(self) -> None:
        code = 'int main(){int a,b;cin>>a;cout<<"Ответ: "<<b;}'
        self.assertIn(M.Simple(M.INPUT, "Ввод a"), build(code, style="pretty").items)
        self.assertTrue(
            any(
                isinstance(item, M.Simple) and "Ответ" in item.text
                for item in walk(build(code, study=False))
            )
        )

    def test_random_fill_is_compact_only_for_symbols(self) -> None:
        code = (
            "int main(){int a[10][10],n,m;srand(time(0));"
            "for(int i=0;i<n;i++){for(int j=0;j<m;j++){a[i][j]=rand()%19-9;}}}"
        )
        self.assertEqual(
            build(code).items, [M.Simple(M.PROCESS, "a[n][m] = random(-9, 9)")]
        )
        self.assertTrue(
            any(
                isinstance(item, M.ForLoop)
                for item in walk(build(code, style="pretty"))
            )
        )
        self.assertTrue(
            any(isinstance(item, M.ForLoop) for item in walk(build(code, study=False)))
        )
        code = code.replace("srand(time(0));", "srand(time(0));observe();")
        self.assertTrue(
            any(
                isinstance(item, M.Simple) and "srand" in item.text
                for item in walk(build(code))
            )
        )

    def test_cli_accepts_symbols_and_no_page_breaks(self) -> None:
        args = build_parser().parse_args(
            ["example.cpp", "--io-style", "symbols", "--page-height", "0"]
        )
        self.assertEqual(args.io_style, "symbols")
        self.assertEqual(args.page_height, 0)
