"""Сокращение настройки широкой консоли без сокрытия вычислений."""

import unittest

from blockwright import model as M
from tests.test_study import chart


class ConsoleLocale(unittest.TestCase):
    def test_simple_wide_console_setup_is_hidden_only_in_study(self) -> None:
        for call in (
            'locale::global(locale(""))',
            'std::locale::global(std::locale(""))',
            "wcin.imbue(locale())",
            "std::wcout.imbue(std::locale())",
            "wcin.width(102)",
            "std::wcin.width(102)",
        ):
            with self.subTest(call=call):
                code = f"int main(){{{call}; return 0;}}"
                self.assertEqual(len(chart(code).items), 1)
                self.assertEqual(len(chart(code, study=False).items), 2)

    def test_effectful_or_custom_setup_is_preserved(self) -> None:
        for call in (
            "locale::global(locale(next_name()))",
            "locale::global(get_locale())",
            "wcin.imbue(locale(next_name()))",
            "wcin.width(next_width())",
            "wcin.width(++n)",
            'custom::locale::global(locale(""))',
            "other.imbue(locale())",
            "wcout.width(102)",
        ):
            with self.subTest(call=call):
                self.assertEqual(
                    len(chart(f"int main(){{{call}; return 0;}}").items), 2
                )

    def test_shadowed_names_and_macros_are_preserved(self) -> None:
        for prefix, call in (
            ("#define locale custom_locale\n", 'locale::global(locale(""))'),
            ("#define global custom_global\n", 'std::locale::global(std::locale(""))'),
            ("#define imbue custom_imbue\n", "wcin.imbue(locale())"),
            ("#define width custom_width\n", "wcin.width(102)"),
            ("#define wcin custom_stream\n", "wcin.width(102)"),
            ("", "wcin.width(102)"),
        ):
            with self.subTest(prefix=prefix, call=call):
                decl = "Stream wcin;" if not prefix else ""
                body = chart(f"{prefix}int main(){{{decl}{call}; return 0;}}")
                self.assertTrue(
                    any(
                        isinstance(i, M.Simple)
                        and call.split("(")[0].split(".")[-1].split("::")[-1] in i.text
                        for i in body.items
                    )
                )

    def test_custom_locale_namespace_is_preserved(self) -> None:
        for prefix in ("namespace locale {}", "namespace locale = custom;"):
            with self.subTest(prefix=prefix):
                body = chart(
                    prefix + 'int main(){locale::global(locale("")); return 0;}'
                )
                self.assertEqual(len(body.items), 2)

    def test_wchar_array_declaration_has_no_action(self) -> None:
        self.assertEqual(
            len(chart("int main(){wchar_t word[102]; return 0;}").items), 1
        )
        self.assertEqual(
            len(chart("int main(){wchar_t word[102]; return 0;}", study=False).items), 2
        )
        self.assertEqual(
            len(
                chart(
                    "#define wchar_t Custom\nint main(){wchar_t word[102]; return 0;}"
                ).items
            ),
            2,
        )
