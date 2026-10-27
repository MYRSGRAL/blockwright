"""Абстрактный вывод массива без скрытия вычислений."""

import unittest

from blockwright import model as M
from tests.test_study import chart


class ArrayOutput(unittest.TestCase):
    def test_printing_matrix_row_addresses_is_not_element_output(self) -> None:
        body = chart("int main(){int a[4][4];for(int i=0;i<4;i++){std::cout << a[i];}}")
        self.assertTrue(any(isinstance(item, M.ForLoop) for item in body.items))

    def test_whitespace_output_does_not_create_a_block(self) -> None:
        for expression in (r"'\n'", r'" \t\n"', '""', "std::endl", r"' ' << std::endl"):
            with self.subTest(expression=expression):
                body = chart("int main(){std::cout << " + expression + ";}")
                self.assertEqual(body.items, [])

    def test_nonempty_output_and_output_effects_remain(self) -> None:
        for expression in ("'!'", '"Готово"', "next()", "++counter"):
            with self.subTest(expression=expression):
                body = chart(
                    "int main(){int counter=0; std::cout << " + expression + ";}"
                )
                self.assertTrue(
                    any(
                        isinstance(i, M.Simple) and i.kind == M.OUTPUT
                        for i in body.items
                    )
                )

    def test_detailed_mode_preserves_whitespace_output(self) -> None:
        body = chart(r"int main(){std::cout << '\n';}", study=False)
        self.assertEqual(body.items, [M.Simple(M.IO, "Перевод строки")])

    def test_shadowed_array_types_and_fractional_lengths_remain_explicit(self) -> None:
        for code in (
            "int a[4]; struct Item{operator int()const;}; int main(){Item a[4]; int n=4; for(int i=0;i<n;i++) std::cout << a[i];}",
            "int a[4]; int main(){volatile int a[4]={1,2,3,4}; for(int i=0;i<4;i++) std::cout << a[i];}",
            "int n; int main(){int a[4]; double n=2.5; for(int i=0;i<n;i++) std::cout << a[i];}",
        ):
            with self.subTest(code=code):
                body = chart(code)
                self.assertTrue(any(isinstance(i, M.ForLoop) for i in body.items))

    def test_array_is_printed_as_one_value_with_its_length(self) -> None:
        body = chart(
            'int main(){int a[100],n=4,i; std::cout << "Количество: " << n; std::cout << "Массив: "; for(i=0;i<n;i++){std::cout << a[i] << \' \';} return 0;}'
        )
        self.assertIn(M.Simple(M.OUTPUT, "Вывод n, a[n]"), body.items)
        self.assertFalse(any(isinstance(i, M.ForLoop) for i in body.items))

    def test_empty_array_formatting_is_part_of_array_output(self) -> None:
        body = chart(
            "int main(){int a[100],n=4,i; if(n==0){std::cout << \"пустой\";}else{for(i=0;i<n;i++){std::cout << a[i] << ' ';}} return 0;}"
        )
        self.assertIn(M.Simple(M.OUTPUT, "Вывод a[n]"), body.items)
        self.assertFalse(any(isinstance(i, M.If) for i in body.items))

    def test_output_with_computations_or_live_index_remains_explicit(self) -> None:
        for loop, end in (
            ("for(i=0;i<n;i++){std::cout << a[i]; a[i]*=2;}", "return 0;"),
            ("for(i=0;i<n;i+=2){std::cout << a[i];}", "return 0;"),
            ("for(i=0;i<n;i++){std::cout << a[++i];}", "return 0;"),
            ("for(i=0;i<n;i++){std::cout << a[i];}", "return i;"),
            ("for(i=0;i<n;i++){std::cout << transform(a[i]);}", "return 0;"),
        ):
            with self.subTest(loop=loop, end=end):
                body = chart("int main(){int a[100],n=4,i;" + loop + end + "}")
                self.assertTrue(any(isinstance(i, M.ForLoop) for i in body.items))

    def test_detailed_mode_preserves_array_print_loop(self) -> None:
        body = chart(
            "int main(){int a[100],n=4,i; for(i=0;i<n;i++){std::cout << a[i];} return 0;}",
            study=False,
        )
        self.assertTrue(any(isinstance(i, M.ForLoop) for i in body.items))


if __name__ == "__main__":
    unittest.main()
