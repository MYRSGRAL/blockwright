"""Полная запись управляющих выражений в блоках for."""

import tempfile
import unittest
from pathlib import Path

from blockwright import vendored

vendored.activate()

from blockwright import model as M
from blockwright import project
from blockwright.cli import Opts
from tests.test_input_study import walk


class LoopHeadersTests(unittest.TestCase):
    def test_counting_headers_keep_condition_and_update(self) -> None:
        for control, expected in (
            ("j=0; j < m; j++", "j = 0; j < m; j++"),
            ("j=0; j < m - 1; j++", "j = 0; j < m - 1; j++"),
            ("j=m; j >= 0; --j", "j = m; j >= 0; --j"),
            ("j=0; j <= m; j += 2", "j = 0; j <= m; j += 2"),
        ):
            with self.subTest(control=control), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "loops.cpp"
                path.write_text(
                    "int main(){int j,m=10,sum=0;for(" + control + "){sum+=j;}}"
                )
                source = project.load(str(path))
                for style in ("auto", "hexagon"):
                    chart = project.charts(source, Opts(for_style=style), source.known)[0]
                    loop = next(x for x in walk(chart.body) if isinstance(x, M.ForLoop))
                    self.assertEqual(loop.style, "hexagon")
                    self.assertEqual(loop.header, expected)
