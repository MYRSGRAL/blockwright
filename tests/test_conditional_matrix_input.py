"""Ввод в ветвях заполнения матрицы и составные проверки режима."""

import unittest
from pathlib import Path

from blockwright import model as M
from tests.test_input_study import build, walk


class ConditionalMatrixInput(unittest.TestCase):
    def test_even_column_sums_source_keeps_algorithm(self) -> None:
        code = (
            Path(__file__).parent / "fixtures/study/even_column_sums.cpp"
        ).read_text()
        items = list(walk(build(code)))
        for name in ("n, m", "mode", "a[i][j]"):
            self.assertIn(M.Simple(M.INPUT, "Ввод " + name), items)
        self.assertFalse(
            any(isinstance(item, M.If) and "cin" in item.cond for item in items)
        )
        self.assertEqual(sum(isinstance(item, M.ForLoop) for item in items), 4)
        self.assertIn(M.Simple(M.PROCESS, "sum = sum + a[i][j]"), items)
        self.assertIn(M.Simple(M.PROCESS, "count = count + 1"), items)
        self.assertTrue(
            any(
                isinstance(item, M.If) and item.cond == "sum % 2 == 0" for item in items
            )
        )
        self.assertIn(M.Simple(M.OUTPUT, "Вывод count"), items)

    def test_mode_validation_becomes_input(self) -> None:
        body = build(
            "int main(){int mode;if(!(cin>>mode)||(mode!=1&&mode!=2)){"
            'cout<<"Ошибка";return 1;}if(mode==2){generate();}}'
        )
        self.assertEqual(body.items[0], M.Simple(M.INPUT, "Ввод mode"))
        self.assertIsInstance(body.items[1], M.If)
        self.assertEqual(body.items[1].cond, "mode==2")

    def test_conditional_element_read_preserves_generation_and_loops(self) -> None:
        body = build(
            "int main(){int a[100][100];int n,m,mode;"
            "for(int i=0;i<n;i++){for(int j=0;j<m;j++){"
            'if(mode==1){if(!(cin>>a[i][j])){cout<<"Ошибка";return 1;}}'
            "else{a[i][j]=rand()%21-10;}}}}"
        )
        items = list(walk(body))
        self.assertIn(M.Simple(M.INPUT, "Ввод a[i][j]"), items)
        self.assertEqual(sum(isinstance(item, M.ForLoop) for item in items), 2)
        self.assertTrue(
            any(isinstance(item, M.If) and item.cond == "mode==1" for item in items)
        )
        self.assertTrue(
            any(isinstance(item, M.Simple) and "rand()" in item.text for item in items)
        )
        self.assertFalse(
            any(isinstance(item, M.If) and "cin" in item.cond for item in items)
        )

    def test_effects_and_unknown_targets_keep_checks(self) -> None:
        for target in ("a[i++]", "a[next()]", "object[i]", "a[i]"):
            declaration = (
                "volatile int a[2];" if target == "a[i]" else "int a[2];Object object;"
            )
            with self.subTest(target=target):
                body = build(
                    f"int main(){{{declaration}int i;"
                    f'if(!(cin>>{target})){{cout<<"Ошибка";return 1;}}}}'
                )
                self.assertTrue(any(isinstance(item, M.If) for item in walk(body)))

    def test_validation_effects_and_explicit_modes_remain(self) -> None:
        for condition in ("mode!=1&&observe()", "mode!=1&&(mode++!=2)"):
            body = build(
                f"int main(){{int mode;if(!(cin>>mode)||({condition}))"
                '{cout<<"Ошибка";return 1;}}'
            )
            self.assertIsInstance(body.items[0], M.If)
        code = 'int main(){int mode;if(!(cin>>mode)||(mode!=1&&mode!=2)){cout<<"Ошибка";return 1;}}'
        for options in ({"checks": "show"}, {"study": False}):
            self.assertTrue(
                any(isinstance(item, M.If) for item in walk(build(code, **options)))
            )
