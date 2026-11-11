"""Специальный блок цикла не получает подписи логического условия."""

import unittest

from blockwright import model as M
from blockwright.layout import layout
from tests.test_geometry import options


class LoopLabelsTests(unittest.TestCase):
    def test_hexagon_has_no_yes_no_labels(self) -> None:
        for yes, no in (("Да", "Нет"), ("Yes", "No")):
            with self.subTest(yes=yes):
                frame = layout(
                    M.ForLoop(
                        M.Seq([M.Simple(M.PROCESS, "sum += a[i][j]")]),
                        style="hexagon",
                        header="j = 0; j < m; j++",
                    ),
                    options(yes_label=yes, no_label=no),
                )
                self.assertEqual(frame.labels, [])


if __name__ == "__main__":
    unittest.main()
