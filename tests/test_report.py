"""Автоматическая компоновка реальных лабораторных под ширину отчёта."""

import unittest
from dataclasses import replace
from pathlib import Path

from blockwright import vendored

vendored.activate()

from blockwright import model as M
from blockwright import project
from blockwright.cli import Opts
from blockwright.geometry import validate_geometry
from blockwright.pages import split_pages
from blockwright.render import MARGIN


class ReportLayout(unittest.TestCase):
    def test_laboratories_fit_report_width_without_font_scaling(self) -> None:
        from blockwright.cli import layout_for_report

        for path in sorted((Path(__file__).parent / "fixtures/study").glob("*.cpp")):
            with self.subTest(path=path.name):
                source = project.load(str(path))
                for chart in project.charts(source, Opts(), source.known):
                    info = chart.info
                    fn = M.Function(
                        info["name"],
                        info["signature"],
                        info["short"],
                        str(path),
                        path.name,
                        info["line"],
                        "cpp",
                        chart.body,
                    )
                    frame, options = layout_for_report(fn, Opts())
                    self.assertLessEqual(frame.width + 2 * MARGIN, options.page_width)
                    self.assertTrue(all(s["h"] >= 28 for s in frame.shapes))
                    pages = split_pages(
                        frame,
                        replace(options, page_height=options.page_height - 2 * MARGIN),
                    )
                    for page in pages:
                        self.assertEqual(validate_geometry(page), [], path.name)
                        bbox = page.bbox()
                        self.assertLessEqual(
                            bbox[2] - bbox[0] + 2 * MARGIN, options.page_width
                        )


if __name__ == "__main__":
    unittest.main()
