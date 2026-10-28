"""Вывод матриц скрывает только форматирование и мёртвые индексы."""

import unittest

from blockwright import model as M
from tests.test_study import chart


class MatrixOutput(unittest.TestCase):
    def test_effects_and_live_indices_keep_print_loops(self) -> None:
        for output, tail in (
            ("std::cout << label() << a[i];", ""),
            ("std::cout << a[++i];", ""),
            ("std::cout << a[i];", "return i;"),
            ("std::cout << a[i];", "for(;i<n;i++) a[i]=0;"),
            ("std::cout << a[i];", "if(n>0)i=0;return i;"),
        ):
            with self.subTest(output=output, tail=tail):
                body = chart(
                    "int label();int main(){int a[4],n=4,i;for(i=0;i<n;i++){"
                    + output
                    + "}"
                    + tail
                    + "}"
                )
                self.assertTrue(any(isinstance(i, M.ForLoop) for i in body.items))
                self.assertNotIn(M.Simple(M.OUTPUT, "Вывод a[n]"), body.items)

    def test_observable_global_or_escaped_index_remains_explicit(self) -> None:
        for code in (
            (
                "int i;int observe();int main(){int a[4],n=4;"
                "for(i=0;i<n;i++)std::cout<<a[i];observe();}"
                "int observe(){return i;}"
            ),
            (
                "int main(){int a[4],n=4,i;int* p=&i;"
                "for(i=0;i<n;i++)std::cout<<a[i];return *p;}"
            ),
            (
                "int main(){int a[4],n=4,i;auto read=[&](){return i;};"
                "for(i=0;i<n;i++)std::cout<<a[i];return read();}"
            ),
            "int i;int main(){int a[4],n=4;{int i;}for(i=0;i<n;i++)std::cout<<a[i];}",
        ):
            with self.subTest(code=code):
                self.assertTrue(
                    any(isinstance(i, M.ForLoop) for i in chart(code).items)
                )

    def test_indexed_dynamic_array_is_one_output(self) -> None:
        body = chart(
            "int main(){int n=3;int* a=new int[n];"
            'for(int i=0;i<n;i++)std::cout<<"["<<i+1<<"]:"<<a[i]<<"   ";}'
        )
        self.assertIn(M.Simple(M.OUTPUT, "Вывод a[n]"), body.items)
        self.assertFalse(any(isinstance(i, M.ForLoop) for i in body.items))

    def test_matrix_output_keeps_later_computations_after_index_reset(self) -> None:
        body = chart(
            "int main(){int m=2,n=3,i,j;int** a=new int*[m];"
            "for(i=0;i<m;i++)a[i]=new int[n];"
            'for(i=0;i<m;i++){for(j=0;j<n;j++)std::cout<<a[i][j]<<"\\t";'
            'std::cout<<"\\n";}'
            "for(i=0;i<m;i++){for(j=0;j<n;j++)a[i][j]*=2;}}"
        )
        self.assertIn(M.Simple(M.OUTPUT, "Вывод a[m][n]"), body.items)
        self.assertTrue(any(isinstance(i, M.ForLoop) for i in body.items))

    def test_matrix_side_effect_or_live_column_remains_explicit(self) -> None:
        for expression, tail in (
            ("a[i][++j]", ""),
            ("a[i][j]", "return j;"),
            ("label()<<a[i][j]", ""),
        ):
            with self.subTest(expression=expression, tail=tail):
                body = chart(
                    "int label();int main(){int a[2][3],m=2,n=3,i,j;"
                    "for(i=0;i<m;i++)for(j=0;j<n;j++)std::cout<<"
                    + expression
                    + ";"
                    + tail
                    + "}"
                )
                self.assertNotIn(M.Simple(M.OUTPUT, "Вывод a[m][n]"), body.items)
                self.assertTrue(any(isinstance(i, M.ForLoop) for i in body.items))

    def test_nonrectangular_or_post_loop_access_remains_explicit(self) -> None:
        for loops in (
            "for(i=0;i<m;i++)for(j=0;j<i;j++)std::cout<<a[i][j];",
            "for(i=0;i<m;i++){for(j=0;j<n;j++){}std::cout<<a[i][j];}",
        ):
            with self.subTest(loops=loops):
                body = chart("int main(){int a[2][3],m=2,n=3,i,j;" + loops + "}")
                self.assertTrue(any(isinstance(i, M.ForLoop) for i in body.items))
                self.assertFalse(
                    any(
                        isinstance(i, M.Simple) and i.text == "Вывод a[m][n]"
                        for i in body.items
                    )
                )

    def test_inner_external_index_cannot_change_outer_bound(self) -> None:
        body = chart(
            "int main(){int a[3][3],m=3,n=2,i;for(i=0;i<n;i++){for(n=0;n<m;n++)std::cout<<a[i][n];}n=0;}"
        )
        self.assertTrue(any(isinstance(x, M.ForLoop) for x in body.items))
        self.assertNotIn(M.Simple(M.OUTPUT, "Вывод a[n][m]"), body.items)
