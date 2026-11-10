"""Консервативное распознавание случайного заполнения матрицы."""

import unittest
from typing import Any

from blockwright.random_study import random_fill, random_seed
from blockwright.study import StudyBuilder
from tests.test_study import P, options


def prepared(code: str) -> tuple[StudyBuilder, list[Any]]:
    src = code.encode()
    tree, spec, errors = P.parse_source(src, P.guess_language("random.cpp", code))
    if errors:
        raise AssertionError(errors)
    function = next(
        n for n in tree.root_node.named_children if n.type == "function_definition"
    )
    body = function.child_by_field_name("body")
    builder = StudyBuilder(
        src, options(), P.collect_known_names(src, tree.root_node, spec), spec
    )
    builder.build_body(body, True)
    return builder, builder._statements(body)


def fill(code: str) -> str | None:
    builder, statements = prepared(code)
    loop = next(n for n in statements if n.type == "for_statement")
    return random_fill(builder, loop)


class RandomFill(unittest.TestCase):
    def test_plain_matrix_ranges(self) -> None:
        for expression, expected in (
            ("rand()%201-100", "-100, 100"),
            ("std::rand()%19-9", "-9, 9"),
            ("(rand() % 10) - 2", "-2, 7"),
        ):
            with self.subTest(expression=expression):
                self.assertEqual(
                    fill(
                        "int main(){int a[5][6],m=5,n=6;for(int i=0;i<m;i++){for(int j=0;j<n;++j){a[i][j]="
                        + expression
                        + ";}}}"
                    ),
                    "a[m][n] = random(" + expected + ")",
                )

    def test_narrow_indices_and_wider_bounds_are_not_summarized(self) -> None:
        for index_type, bound_type, bound in (
            ("unsigned char", "int", "300"),
            ("short", "int", "40000"),
            ("int", "long long", "3000000000LL"),
        ):
            with self.subTest(index_type=index_type, bound_type=bound_type):
                self.assertIsNone(
                    fill(
                        f"int main(){{int a[300][1];{bound_type} m={bound};int n=1;"
                        f"for({index_type} i=0;i<m;i++)for(int j=0;j<n;j++)a[i][j]=rand()%19-9;}}"
                    )
                )
        self.assertIsNone(
            fill(
                "int main(){int a[300][1];for(int i=0;i<3000000000LL;i++)"
                "for(int j=0;j<1;j++)a[i][j]=rand()%19-9;}"
            )
        )

    def test_dynamic_matrix(self) -> None:
        self.assertEqual(
            fill(
                "int main(){int m=5,n=6;int** a=new int*[m];for(int i=0;i<m;i++)for(int j=0;j<n;j++)a[i][j]=rand()%201-100;}"
            ),
            "a[m][n] = random(-100, 100)",
        )

    def test_external_indices_overwritten_before_read(self) -> None:
        self.assertEqual(
            fill(
                "int main(){int a[5][6],m=5,n=6,i,j;for(i=0;i<m;i++)for(j=0;j<n;j++)a[i][j]=rand()%19-9;i=0;j=0;return i+j;}"
            ),
            "a[m][n] = random(-9, 9)",
        )

    def test_impure_or_unsupported_loops(self) -> None:
        for replacement in (
            "a[j][i]=rand()%201-100;",
            "a[i][j]+=rand()%201-100;",
            "a[i][j]=other()%201-100;",
            "a[i][j]=rand(1)%201-100;",
            "a[i][j]=rand()%201-offset;",
            "a[i][j]=rand()%0-100;",
            "a[i][j]=rand()%201-100;counter++;",
            "if(flag)a[i][j]=rand()%201-100;",
            "a[i][j]=(rand()%201-100)*2;",
            "a[i][j]=rand()%2147483648-100;",
        ):
            with self.subTest(replacement=replacement):
                self.assertIsNone(
                    fill(
                        "int main(){int a[5][6],m=5,n=6,counter,offset,flag;for(int i=0;i<m;i++)for(int j=0;j<n;j++){"
                        + replacement
                        + "}}"
                    )
                )

    def test_shadowing_types_macros_and_rank(self) -> None:
        cases = (
            "int rand(); int main(){int a[5][6];",
            "#define rand custom\nint main(){int a[5][6];",
            "#define m 5\nint main(){int a[5][6];",
            "#define int long\nint main(){int a[5][6];",
            "int main(){float a[5][6];",
            "int main(){unsigned int a[5][6];",
            "int main(){volatile int a[5][6];",
            "int main(){int a[5][6][7];",
            "int main(){int a[5];",
            "int main(){int a[5][6];int rand;",
            "#define std custom\nint main(){int a[5][6];",
        )
        for prefix in cases:
            with self.subTest(prefix=prefix):
                self.assertIsNone(
                    fill(
                        prefix
                        + "int m=5,n=6;for(int i=0;i<m;i++)for(int j=0;j<n;j++)a[i][j]=std::rand()%201-100;}"
                    )
                )

    def test_live_external_index(self) -> None:
        self.assertIsNone(
            fill(
                "int main(){int a[5][6],m=5,n=6,i,j;for(i=0;i<m;i++)for(j=0;j<n;j++)a[i][j]=rand()%19-9;return j;}"
            )
        )


class RandomSeed(unittest.TestCase):
    def test_standard_seed(self) -> None:
        for expression in (
            "srand(time(0))",
            "std::srand(std::time(nullptr))",
            "srand((time((0))))",
        ):
            with self.subTest(expression=expression):
                builder, statements = prepared("int main(){" + expression + ";}")
                self.assertTrue(random_seed(builder, statements[0]))

    def test_seed_with_custom_names_or_side_effects(self) -> None:
        for prefix, expression in (
            ("", "srand(time(&t))"),
            ("", "srand(42)"),
            ("", "srand(time(0)), action()"),
            ("", "srand(custom(0))"),
            ("int time(int);", "srand(time(0))"),
            ("#define time custom\n", "srand(time(0))"),
            ("#define std custom\n", "std::srand(std::time(0))"),
            ("int srand(int);", "std::srand(std::time(0))"),
        ):
            with self.subTest(expression=expression, prefix=prefix):
                builder, statements = prepared(
                    prefix + "int main(){" + expression + ";}"
                )
                self.assertFalse(random_seed(builder, statements[0]))
