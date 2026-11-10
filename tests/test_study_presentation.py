"""Единообразные подписи и скрытие технической подготовки учебной схемы."""

import unittest

from blockwright import model as M
from tests.test_input_study import build, walk
from tests.test_study import _RETRY_INPUT


class StudyPresentation(unittest.TestCase):
    def test_menu_caption_belongs_to_validated_input(self) -> None:
        code = (
            'int main(){int mode;cout<<"Заполнение: 1 - вручную, 2 - случайно: ";'
            'if(!(cin>>mode)||(mode!=1&&mode!=2)){cout<<"Ошибка";return 1;}}'
        )
        self.assertEqual(build(code).items, [M.Simple(M.INPUT, "Ввод mode")])
        self.assertTrue(
            any(
                isinstance(x, M.Simple) and "Заполнение" in x.text
                for x in walk(build(code, study=False))
            )
        )

    def test_question_caption_belongs_to_direct_input(self) -> None:
        self.assertEqual(
            build('int main(){int n;cout<<"Сколько строк? ";cin>>n;}').items,
            [M.Simple(M.INPUT, "Ввод n")],
        )
        body = build('int main(){int n;cout<<"Результат готов";cin>>n;}')
        self.assertEqual(len(body.items), 2)

    def test_short_numeric_assignments_share_a_block(self) -> None:
        body = build(
            "int main(){int a[10],j,t;t=a[j];a[j]=a[j + 1];a[j + 1]=t;cout<<t;}"
        )
        self.assertEqual(
            body.items[0],
            M.Simple(M.PROCESS, "t = a[j]; a[j] = a[j + 1]; a[j + 1] = t"),
        )
        self.assertEqual(body.items[1], M.Simple(M.OUTPUT, "Вывод t"))
        detailed = build("int main(){int a,b,t;t=a;a=b;b=t;}", study=False)
        self.assertGreaterEqual(len(detailed.items), 3)

    def test_assignment_groups_do_not_cross_control_or_effects(self) -> None:
        for code in (
            "int main(){int a,b;a=b;cout<<a;b=a;}",
            "int main(){int a,b;a=f();b=a;}",
            "int main(){int a[10],j,t;t=a[j++];a[j]=t;}",
        ):
            with self.subTest(code=code):
                self.assertFalse(
                    any(
                        isinstance(x, M.Simple) and "; " in x.text
                        for x in walk(build(code))
                    )
                )

    def test_prompt_before_input_and_processing_loop_is_absorbed(self) -> None:
        code = (
            "int main(){int a[100],n;long long sum=0;int count=0;cin>>n;"
            'cout<<"Введите элементы массива: ";'
            'for(int i=0;i<n;i++){if(!(cin>>a[i])){cout<<"Ошибка";return 1;}'
            "if(a[i]%2==0){sum=sum+a[i];count++;}}cout<<sum<<count;}"
        )
        body = build(code)
        self.assertFalse(
            any(
                isinstance(x, M.Simple) and "Введите элементы" in x.text
                for x in walk(body)
            )
        )
        self.assertEqual(sum(isinstance(x, M.ForLoop) for x in walk(body)), 1)
        self.assertIn(M.Simple(M.INPUT, "Ввод a[i]"), list(walk(body)))
        self.assertTrue(
            any(isinstance(x, M.If) and "a[i]" in x.cond for x in walk(body))
        )
        for name in ("sum", "count"):
            self.assertTrue(
                any(
                    isinstance(x, M.Simple) and x.kind == M.PROCESS and name in x.text
                    for x in walk(body)
                )
            )
        self.assertTrue(
            any(
                isinstance(x, M.Simple) and "Введите элементы" in x.text
                for x in walk(build(code, study=False))
            )
        )

    def test_prompt_is_preserved_when_loop_does_not_start_with_input(self) -> None:
        for action in ('cout<<"Результат";', "n=f();"):
            code = (
                'int main(){int a[10],n;cout<<"Введите элементы массива: ";'
                "for(int i=0;i<n;i++){" + action + "cin>>a[i];}}"
            )
            with self.subTest(action=action):
                self.assertTrue(
                    any(
                        isinstance(x, M.Simple) and "Введите элементы" in x.text
                        for x in walk(build(code))
                    )
                )

    def test_independent_cin_retries_share_no_state(self) -> None:
        code = (
            "int main(){double a,b;"
            + _RETRY_INPUT.replace("r)", "a)")
            + _RETRY_INPUT.replace("r)", "b)")
            + "std::cout<<a<<b;}"
        )
        body = build(code)
        self.assertEqual(
            [
                x.text
                for x in walk(body)
                if isinstance(x, M.Simple) and x.kind == M.INPUT
            ],
            ["Ввод a", "Ввод b"],
        )
        self.assertFalse(any(isinstance(x, M.While) for x in walk(body)))

    def test_compound_assignments_expand_only_simple_numeric_targets(self) -> None:
        body = build("int main(){int n=2,i=0,a[5];i+=1;n*=2;a[i]*=2;}")
        texts = [x.text for x in walk(body) if isinstance(x, M.Simple)]
        for expected in ("i = i + 1", "n = n * 2", "a[i] = a[i] * 2"):
            self.assertIn(expected, texts)
        body = build("int main(){Counter c;int i=0,a[5];c+=2;a[i++]*=2;}")
        self.assertIn(M.Simple(M.PROCESS, "c+=2"), body.items)
        self.assertIn(M.Simple(M.PROCESS, "a[i++]*=2"), body.items)

    def test_pause_redirect_and_exit_prompt_are_technical(self) -> None:
        code = 'int main(){std::cout<<"Нажмите любую кнопку для закрытия программы...";system("pause > nul");}'
        self.assertEqual(build(code).items, [])
        self.assertTrue(build(code, study=False).items)
        self.assertTrue(build('int main(){system("pause > file");}').items)

    def test_terminal_enter_and_ignore_are_hidden_together(self) -> None:
        code = r"""int main(){std::string text;std::getline(std::cin,text);std::cout<<text;
std::cout<<"Введите Enter для выхода из программы...";
std::cin.ignore(std::numeric_limits<std::streamsize>::max(), '\n');return 0;}"""
        body = build(code)
        self.assertFalse(
            any(
                isinstance(x, M.Simple) and ("ignore" in x.text or "Enter" in x.text)
                for x in walk(body)
            )
        )
        self.assertTrue(
            any(
                isinstance(x, M.Simple) and "ignore" in x.text
                for x in walk(build(code, study=False))
            )
        )

    def test_primitive_dynamic_matrix_storage_and_printing_are_compact(self) -> None:
        code = r"""int main(){int m=2,n=3,i,j;int** a=new int*[m];for(int row=0;row<m;row++){a[row]=new int[n];}
std::cout<<"Матрица:\n";for(i=0;i<m;i++){for(j=0;j<n;j++){std::cout<<a[i][j]<<'\t';}std::cout<<'\n';}
for(i=0;i<m;i++){for(j=0;j<n;j++){a[i][j]*=2;}}}"""
        body = build(code)
        self.assertIn(M.Simple(M.OUTPUT, "Вывод a[m][n]"), body.items)
        self.assertFalse(
            any(isinstance(x, M.Simple) and "new " in x.text for x in walk(body))
        )
        self.assertEqual(sum(isinstance(x, M.ForLoop) for x in walk(body)), 2)
        self.assertIn(M.Simple(M.PROCESS, "a[i][j] = a[i][j] * 2"), list(walk(body)))

    def test_indexed_array_printing_is_one_output(self) -> None:
        body = build(
            'int main(){int n=3;int* a=new int[n];for(int i=0;i<n;i++){std::cout<<"["<<i+1<<"]:"<<a[i]<<"   ";}}'
        )
        self.assertIn(M.Simple(M.OUTPUT, "Вывод a[n]"), body.items)
        self.assertFalse(any(isinstance(x, M.ForLoop) for x in walk(body)))

    def test_allocations_with_initializers_and_placement_keep_effects(self) -> None:
        for allocation in ("new int[n]{compute()}", "new (arena()) int[n]"):
            with self.subTest(allocation=allocation):
                body = build(
                    "int main(){int n=3;int* a=" + allocation + ";std::cout<<a[0];}"
                )
                self.assertTrue(
                    any(
                        isinstance(x, M.Simple) and allocation in x.text
                        for x in walk(body)
                    )
                )

    def test_empty_statement_is_not_a_process(self) -> None:
        self.assertEqual(build("int main(){;}").items, [])

    def test_compound_assignment_keeps_macro_and_volatile_indices(self) -> None:
        for code in (
            "#define IDX next_index()\nint main(){int a[10];a[IDX]+=1;}",
            "int main(){int a[10];volatile int i=0;a[i]+=1;}",
        ):
            with self.subTest(code=code):
                body = build(code)
                self.assertTrue(
                    any(isinstance(x, M.Simple) and "+=" in x.text for x in walk(body))
                )

    def test_numeric_output_uses_values_and_separators_only(self) -> None:
        body = build(
            'int main(){double a=1,b=2,c=3;std::cout<<"Значение a, b, c: "<<a<<", "<<b<<", "<<c;}'
        )
        self.assertIn(M.Simple(M.OUTPUT, "Вывод a, b, c"), body.items)

    def test_static_input_notice_is_part_of_the_following_input(self) -> None:
        body = build(
            'int main(){std::string a;std::cout<<"Внимание! Вводите слово нижним регистром.";std::getline(std::cin,a);}'
        )
        self.assertEqual(body.items, [M.Simple(M.INPUT, "Ввод a")])

    def test_dynamic_storage_preserves_observable_dimension_reads(self) -> None:
        for code in (
            "#define SIZE count++\nint main(){int count=3;int* a=new int[SIZE];std::cout<<count;}",
            "int main(){volatile int n=3;int* a=new int[n];}",
            "int main(){Size n;int* a=new int[n];}",
        ):
            with self.subTest(code=code):
                self.assertTrue(
                    any(
                        isinstance(x, M.Simple) and "new " in x.text
                        for x in walk(build(code))
                    )
                )
