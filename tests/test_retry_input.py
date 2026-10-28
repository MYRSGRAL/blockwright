"""Повторный ввод скаляров и элементов массивов."""

import unittest

from blockwright import model as M
from tests.test_input_study import build, walk

HEADER = (
    "#include <iostream>\n#include <string>\n#include <sstream>\nusing namespace std;\n"
)


def retry(target: str, validation: str = "") -> str:
    return (
        'while(true){cout<<"Введите число: ";getline(cin,input);'
        "istringstream iss(input);if((iss>>"
        + target
        + ")"
        + validation
        + "&&!(iss>>extra)){break;}"
        'cout<<"Ошибка ввода";cout<<"\\n";}'
    )


def program(code: str) -> str:
    return (
        HEADER + "int main(){int n,m,y;string input;char extra;" + code + "return 0;}"
    )


class RetryInput(unittest.TestCase):
    def test_scalar_retry_hides_protocol_and_keeps_value(self) -> None:
        body = build(program(retry("n", "&&n>0") + "cout<<n;"))
        self.assertIn(M.Simple(M.INPUT, "Ввод n"), body.items)
        self.assertFalse(any(isinstance(item, M.While) for item in walk(body)))
        self.assertTrue(
            any(
                isinstance(item, M.Simple)
                and item.kind == M.OUTPUT
                and "n" in item.text
                for item in walk(body)
            )
        )
        self.assertFalse(
            any(
                isinstance(item, M.Simple)
                and ("input" in item.text or "extra" in item.text)
                for item in walk(body)
            )
        )

    def test_retry_in_array_and_nested_branch(self) -> None:
        code = retry("n", "&&n>0") + retry("y", "&&(y==0||y==1)")
        code += (
            "int a[10][10];if(y==0){for(int i=0;i<m;i++){for(int j=0;j<n;j++){"
            + retry("a[i][j]")
            + "}}}"
        )
        body = build(program(code))
        inputs = [
            item.text
            for item in walk(body)
            if isinstance(item, M.Simple) and item.kind == M.INPUT
        ]
        self.assertEqual(inputs, ["Ввод n", "Ввод y", "Ввод a[m][n]"])
        self.assertFalse(
            any(isinstance(item, (M.While, M.ForLoop)) for item in walk(body))
        )

    def test_array_retry(self) -> None:
        body = build(program("int a[10];for(int i=0;i<n;i++){" + retry("a[i]") + "}"))
        self.assertIn(M.Simple(M.INPUT, "Ввод a[n]"), body.items)

    def test_enclosing_scope_keeps_live_or_escaped_index(self) -> None:
        for code in (
            "int a[10];int i=7;if(y==0){for(i=0;i<n;i++){"
            + retry("a[i]")
            + "}}cout<<i;",
            "int a[10];int i=7;int* alias=&i;if(y==0){for(i=0;i<n;i++){"
            + retry("a[i]")
            + "}}cout<<*alias;",
        ):
            with self.subTest(code=code):
                self.assertTrue(
                    any(
                        isinstance(item, M.ForLoop)
                        for item in walk(build(program(code)))
                    )
                )

    def test_enclosing_index_reset_allows_compact_input(self) -> None:
        code = (
            "int a[10];int i=7;if(y==0){for(i=0;i<n;i++){"
            + retry("a[i]")
            + "}}i=0;cout<<i;"
        )
        self.assertTrue(
            any(
                isinstance(item, M.Simple) and item.text == "Ввод a[n]"
                for item in walk(build(program(code)))
            )
        )

    def test_empty_statement_does_not_break_input_recognition(self) -> None:
        body = build(program(";" + retry("n")))
        self.assertIn(M.Simple(M.INPUT, "Ввод n"), body.items)

    def test_observed_buffer_keeps_nested_protocol(self) -> None:
        code = (
            "int a[10];if(y==0){for(int i=0;i<n;i++){"
            + retry("a[i]")
            + "}}cout<<input;"
        )
        body = build(program(code))
        self.assertTrue(any(isinstance(item, M.While) for item in walk(body)))

    def test_side_effects_and_buffer_observation_keep_retry(self) -> None:
        for code in (
            retry("n").replace("n)", "n)&&observe()"),
            retry("n").replace("break;", "observe();break;"),
            retry("n") + "cout<<input;",
            retry("n").replace('cout<<"Ошибка ввода";', "observe();"),
            retry("n").replace("getline(cin,input)", "getline(custom,input)"),
        ):
            with self.subTest(code=code):
                self.assertTrue(
                    any(
                        isinstance(item, M.While) for item in walk(build(program(code)))
                    )
                )

    def test_show_and_full_keep_retry(self) -> None:
        code = program(retry("n", "&&n>0"))
        for options in ({"checks": "show"}, {"study": False}):
            with self.subTest(options=options):
                self.assertTrue(
                    any(
                        isinstance(item, M.While)
                        for item in walk(build(code, **options))
                    )
                )

    def test_interactive_text_keeps_exit_and_computation(self) -> None:
        code = """while(true){cout<<"Введите символ: ";getline(cin,input);
        if(input.empty()){cout<<"Ошибка";continue;}
        if(input.length()!=1){cout<<"Ошибка";continue;}
        if(input[0]=='#'){break;}char symbol=input[0];
        if(symbol=='*'||symbol=='#'){cout<<"Ошибка";continue;}
        int count=0;for(int i=0;i<n;i++){if(a[i]==symbol){a[i]='*';count++;}}
        cout<<count;}"""
        body = build(program("char a[10];" + code))
        conditions = [item.cond for item in walk(body) if isinstance(item, M.If)]
        self.assertIn("input[0]=='#'", conditions)
        self.assertIn("a[i]==symbol", conditions)
        self.assertFalse(
            any(
                "empty" in condition
                or "length" in condition
                or "symbol=='*'" in condition
                for condition in conditions
            )
        )
        self.assertTrue(
            any(
                isinstance(item, M.Simple)
                and item.kind == M.INPUT
                and item.text == "Ввод input"
                for item in walk(body)
            )
        )

    def test_interactive_text_guard_with_effect_keeps_details(self) -> None:
        code = "while(true){getline(cin,input);if(input.empty()){observe();continue;}if(input[0]=='#')break;}"
        body = build(program(code))
        self.assertTrue(
            any(isinstance(item, M.If) and "empty" in item.cond for item in walk(body))
        )

    def test_mutating_control_keeps_later_character_validation(self) -> None:
        code = """while(true){getline(cin,input);
        if(input.length()!=1){cout<<"Ошибка";continue;}
        if(mutate(input)){break;}char symbol=input[0];
        if(symbol=='*'){cout<<"Ошибка";continue;}cout<<symbol;}"""
        body = build(program(code))
        self.assertTrue(
            any(
                isinstance(item, M.If) and "symbol=='*'" in item.cond
                for item in walk(body)
            )
        )
