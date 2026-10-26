"""Согласованность контуров и экранирования браузерного редактора."""

import json
import shutil
import subprocess
import unittest

from blockwright.album import JS_CORE


@unittest.skipUnless(shutil.which("node"), "Для проверки JavaScript нужен Node.js")
class EditorGeometry(unittest.TestCase):
    def test_junction_arrow_matches_generator(self) -> None:
        from blockwright.geometry import junction_arrows

        edges = [
            {"points": [(0, 0), (0, 100)], "arrow": False},
            {"points": [(-50, 50), (0, 50)], "arrow": False},
            {"points": [(-50, 75), (50, 75)], "arrow": False},
        ]
        actual = self.evaluate("junctionArrows(" + json.dumps(edges) + ")")
        self.assertEqual(actual, json.loads(json.dumps(junction_arrows(edges))))

    def test_kind_change_normalizes_ports_without_router(self) -> None:
        core = JS_CORE.split("/* ---------- state ----------")[0]
        script = (
            core
            + """
const m={shapes:[{id:'a',kind:'process',x:0,y:0,w:150,h:54},
 {id:'b',kind:'process',x:250,y:100,w:150,h:54}],labels:[],edges:[
 {id:'e',from:{id:'a',port:'right'},to:{id:'b',port:'top'},points:[[150,27],[325,27],[325,100]]}]};
syncEdges(m,['a']);
process.stdout.write(JSON.stringify(m.edges[0].from.port));
"""
        )
        result = subprocess.run(
            ["node"], input=script, text=True, capture_output=True, check=True
        )
        self.assertEqual(json.loads(result.stdout), "bottom")

    def evaluate(self, expression: str) -> object:
        core = JS_CORE.split("/* ---------- model: attachments")[0]
        script = core + "\nprocess.stdout.write(JSON.stringify(" + expression + "));"
        result = subprocess.run(
            ["node"], input=script, text=True, capture_output=True, check=True
        )
        return json.loads(result.stdout)

    def test_document_contour_and_wave_port(self) -> None:
        result = self.evaluate(
            "outline({kind:'output',notation:'course',x:10,y:20,w:200,h:80})"
        )
        self.assertIn(" C", result[0])
        self.assertNotIn("rx=", result[0])
        point = self.evaluate(
            "contourPorts({kind:'output',notation:'course',x:10,y:20,w:200,h:80}).bottom"
        )
        self.assertEqual(point, [110, 95.4])

    def test_gost_output_is_data_symbol(self) -> None:
        result = self.evaluate(
            "outline({kind:'output',notation:'gost',x:0,y:0,w:200,h:80})"
        )
        self.assertIn("<polygon", result[0])

    def test_dark_interface_does_not_change_print_colors(self) -> None:
        result = self.evaluate(
            "(THEME='dark', outline({kind:'input',x:0,y:0,w:200,h:80}))"
        )
        self.assertIn('fill="#ffffff"', result[0])
        self.assertIn('stroke="#000000"', result[0])

    def test_user_text_is_escaped(self) -> None:
        result = self.evaluate(
            "shapeText({kind:'process',x:0,y:0,w:200,h:80,text:'x < 2 && y > 0'},38)"
        )
        self.assertIn("&lt;", result[0])
        self.assertIn("&amp;&amp;", result[0])

    def test_flow_ports_for_all_shape_kinds(self) -> None:
        for kind in (
            "process",
            "input",
            "output",
            "predefined",
            "preparation",
            "connector",
        ):
            with self.subTest(kind=kind):
                self.assertEqual(
                    self.evaluate(f"flowPorts({{kind:'{kind}'}},true)"), ["bottom"]
                )
                self.assertEqual(
                    self.evaluate(f"flowPorts({{kind:'{kind}'}},false)"), ["top"]
                )
        self.assertEqual(
            self.evaluate("flowPorts({kind:'decision'},true)"), ["bottom", "right"]
        )
        self.assertEqual(
            self.evaluate("flowPorts({kind:'terminator',role:'start'},false)"), []
        )
        self.assertEqual(
            self.evaluate("flowPorts({kind:'terminator',role:'end'},true)"), []
        )


if __name__ == "__main__":
    unittest.main()
