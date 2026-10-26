"""Порты всех фигур и фактические направления соединений."""

import unittest
from dataclasses import replace
from pathlib import Path

from blockwright import vendored

vendored.activate()

from blockwright import model as M
from blockwright import project
from blockwright.cli import Opts, layout_for_report
from blockwright.pages import split_pages
from blockwright.render import MARGIN


class ShapePorts(unittest.TestCase):
    def test_port_rules_and_generated_connections(self) -> None:
        from blockwright.geometry import allowed_ports, validate_ports

        for kind in (M.PROCESS, M.INPUT, M.OUTPUT, M.PREDEF, M.PREP, M.CONNECTOR):
            self.assertEqual(allowed_ports({"kind": kind}, True), ("bottom",))
            self.assertEqual(allowed_ports({"kind": kind}, False), ("top",))
        self.assertEqual(allowed_ports({"kind": M.DECISION}, True), ("bottom", "right"))
        for path in sorted((Path(__file__).parent / "fixtures/study").glob("*.cpp")):
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
                self.assertEqual(validate_ports(frame), [], path.name)
                for page in split_pages(
                    frame,
                    replace(options, page_height=options.page_height - 2 * MARGIN),
                ):
                    self.assertEqual(validate_ports(page), [], path.name)
