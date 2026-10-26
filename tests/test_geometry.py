"""Проверки учебной геометрии и разрывов страниц."""

import unittest
from types import SimpleNamespace

from blockwright import model as M
from blockwright.geometry import document_bottom, shape_port, validate_geometry
from blockwright.layout import layout, layout_function, make_shape
from blockwright.pages import split_pages
from blockwright.render import render_svg, shape_outline


def options(**changes: object) -> SimpleNamespace:
    values = {
        "max_chars": 30,
        "study": True,
        "notation": "course",
        "yes_label": "Да",
        "no_label": "Нет",
        "begin_label": "Начало",
        "end_label": "Конец",
        "plain_begin": True,
        "page_height": 600,
    }
    values.update(changes)
    return SimpleNamespace(**values)


class GeometryTests(unittest.TestCase):
    def test_document_port_is_on_wave(self) -> None:
        shape = make_shape("output", "Вывод результата", options())
        x, y = shape_port(shape, "bottom")
        self.assertAlmostEqual(x, shape["w"] / 2)
        self.assertAlmostEqual(y, document_bottom(shape["w"], shape["h"], 0.5)[1])
        self.assertNotEqual(y, shape["h"])
        self.assertIn(" C", "".join(shape_outline(shape)))
        gost = make_shape("output", "Вывод", options(notation="gost"))
        self.assertIn("polygon", "".join(shape_outline(gost)))

    def test_decision_ports_are_down_and_right(self) -> None:
        frame = layout(M.If("условие?", M.Simple(M.PROCESS, "работа")), options())
        decision = next(s for s in frame.shapes if s["kind"] == M.DECISION)
        outgoing = [e["points"][0] for e in frame.edges]
        self.assertIn(shape_port(decision, "bottom"), outgoing)
        self.assertIn(shape_port(decision, "right"), outgoing)
        self.assertNotIn(shape_port(decision, "left"), outgoing)
        self.assertEqual(validate_geometry(frame), [])

    def test_return_inside_loop_reaches_common_end(self) -> None:
        body = M.Seq(
            [
                M.While("ещё?", M.If("готово?", M.Return("f()"))),
                M.Return("0", main=True),
            ]
        )
        fn = M.Function("main", "main()", "main", "", "", 1, "cpp", body)
        frame = layout_function(fn, options())
        self.assertEqual(sum(s["text"] == "Конец" for s in frame.shapes), 1)
        self.assertTrue(any("f()" in s["text"] for s in frame.shapes))
        self.assertEqual(frame.pend, [])
        self.assertTrue(any(e.get("return_value") == "0" for e in frame.edges))
        self.assertEqual(validate_geometry(frame), [])

    def test_monochrome_and_serif(self) -> None:
        frame = layout(M.Simple(M.PROCESS, "Текст"), options())
        svg = render_svg(frame, theme="dark")
        self.assertIn("Times New Roman", svg)
        self.assertNotIn("#11161d", svg)
        self.assertIn('fill="#ffffff"', svg)

    def test_pages_keep_all_shapes_and_paired_connectors(self) -> None:
        frame = layout(
            M.Seq([M.Simple(M.PROCESS, f"шаг {i}") for i in range(25)]), options()
        )
        pages = split_pages(frame, options())
        self.assertGreater(len(pages), 1)
        shapes = [s for p in pages for s in p.shapes]
        self.assertEqual(sum(s["kind"] == M.PROCESS for s in shapes), 25)
        connectors = [s["text"] for s in shapes if s["kind"] == M.CONNECTOR]
        self.assertTrue(connectors)
        for label in set(connectors):
            self.assertEqual(connectors.count(label), 2)
        self.assertTrue(all(p.height <= 600 for p in pages))

    def test_loop_merges_have_one_final_arrow(self) -> None:
        body = M.ForLoop(
            M.If("пропустить?", M.Jump("continue")),
            init=M.Simple(M.PROCESS, "i = 0"),
            cond="i < 5",
            update=M.Simple(M.PROCESS, "i = i + 1"),
        )
        fn = M.Function("f", "f()", "f", "", "", 1, "cpp", M.Seq([body]))
        frame = layout_function(fn, options())
        targets = [tuple(e["points"][-1]) for e in frame.edges if e["arrow"]]
        self.assertEqual(len(targets), len(set(targets)))
        self.assertEqual(validate_geometry(frame), [])

    def test_throw_is_separate_from_normal_end(self) -> None:
        body = M.Seq(
            [
                M.If("ошибка?", M.Simple(M.TERMINATOR, "throw error", terminal=True)),
                M.Return("result"),
            ]
        )
        frame = layout_function(
            M.Function("f", "f()", "f", "", "", 1, "cpp", body), options()
        )
        thrown = next(s for s in frame.shapes if s["text"] == "throw error")
        self.assertFalse(
            any(e["points"][0] == shape_port(thrown, "bottom") for e in frame.edges)
        )
        self.assertEqual(sum(s["text"] == "Конец" for s in frame.shapes), 1)

    def test_upward_page_crossings_are_paired(self) -> None:
        frame = layout(
            M.Seq([M.Simple(M.PROCESS, f"шаг {i}") for i in range(35)]), options()
        )
        frame.edges.append(
            {
                "points": [(frame.width + 30, frame.height), (frame.width + 30, 0)],
                "arrow": True,
            }
        )
        pages = split_pages(frame, options())
        labels = [
            s["text"] for page in pages for s in page.shapes if s["kind"] == M.CONNECTOR
        ]
        self.assertTrue(all(labels.count(label) == 2 for label in set(labels)))
        self.assertTrue(all(validate_geometry(page) == [] for page in pages))
        self.assertTrue(all(page.page_number == i for i, page in enumerate(pages, 1)))

    def test_page_height_zero_disables_pagination(self) -> None:
        frame = layout(M.Seq([M.Simple(M.PROCESS, "работа")] * 50), options())
        pages = split_pages(frame, options(page_height=0))
        self.assertEqual(len(pages), 1)
        self.assertIsNot(pages[0], frame)
        with self.assertRaisesRegex(ValueError, "отрицательной"):
            split_pages(frame, options(page_height=-1))

    def test_returns_leave_wave_vertically_and_success_stays_on_spine(self) -> None:
        body = M.Seq(
            [
                M.If(
                    "ошибка?",
                    M.Seq([M.Simple(M.OUTPUT, "Ошибка"), M.Return("1", main=True)]),
                ),
                M.Simple(M.OUTPUT, "Результат"),
                M.Return("0", main=True),
            ]
        )
        frame = layout_function(
            M.Function("main", "main()", "main", "", "", 1, "cpp", body), options()
        )
        for shape in [s for s in frame.shapes if s["kind"] == M.OUTPUT]:
            origin = shape_port(shape, "bottom")
            edges = [e for e in frame.edges if e["points"][0] == origin]
            self.assertEqual(len(edges), 1)
            points = edges[0]["points"]
            self.assertEqual(points[0][0], points[1][0])
            self.assertGreaterEqual(points[1][1] - points[0][1], 16)
        success = next(e for e in frame.edges if e.get("return_value") == "0")
        self.assertTrue(all(x == frame.spine for x, _ in success["points"]))

    def test_editor_metadata_and_left_direction_arrow(self) -> None:
        from blockwright.render import edge_svg, frame_to_dict

        frame = layout(M.Simple(M.CONNECTOR, "A1"), options())
        frame.shapes[0]["page_target"] = 2
        frame.edges.append(
            {"points": [(100, 100), (0, 100)], "arrow": False, "return_value": "1"}
        )
        frame.page_number, frame.page_count = 1, 2
        data = frame_to_dict(frame, options())
        self.assertEqual(data["edges"][0]["return_value"], "1")
        self.assertEqual(data["shapes"][0]["page_target"], 2)
        self.assertEqual(data["shapes"][0]["lines"], ["A1"])
        self.assertEqual(data["page_count"], 2)
        self.assertTrue(any(' Z"' in item for item in edge_svg(frame.edges[0])))
