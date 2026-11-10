"""Группировка условного заполнения и вывода с вычислением сумм."""

import unittest

from blockwright import model as M
from blockwright.matrix_study import conditional_matrix_fill, summed_matrix_output
from tests.test_random_study import prepared

FILL = """if(choice==2){srand(time(0));}
if(choice==1){cout<<"Введите матрицу:";}
for(int row=0;row<rows;row++)for(int col=0;col<cols;col++){
if(choice==1){if(!(cin>>data[row][col])){cout<<"Ошибка";return 1;}}
else{data[row][col]=rand()%19-9;}}"""
SUM = """for(int row=0;row<rows;row++){
totals[row]=0;
for(int col=0;col<cols;col++){
cout<<data[row][col]<<" ";totals[row]+=data[row][col];}
cout<<"\\n";}"""
PREFIX = "int main(){int data[4][5],rows=4,cols=5,choice;long long totals[4];"


class MatrixStudy(unittest.TestCase):
    def test_conditional_fill_renamed_and_ast_unchanged(self) -> None:
        builder, nodes = prepared(PREFIX + FILL + "}")
        start = next(i for i, node in enumerate(nodes) if node.type == "if_statement")
        before = [str(node) for node in nodes]
        result = conditional_matrix_fill(builder, nodes, start)
        self.assertIsNotNone(result)
        end, items = result
        self.assertEqual(end, start + 3)
        self.assertEqual(
            items,
            [
                M.If(
                    "choice==1",
                    M.Seq([M.Simple(M.INPUT, "Ввод data[rows][cols]")]),
                    M.Seq([M.Simple(M.PROCESS, "data[rows][cols] = random(-9, 9)")]),
                )
            ],
        )
        self.assertEqual(before, [str(node) for node in nodes])

    def test_conditional_fill_rejects_effects_and_unsupported_patterns(self) -> None:
        for code in (
            FILL.replace("srand(time(0));", "srand(time(0));choice++;"),
            FILL.replace('"Введите матрицу:"', "action()"),
            FILL.replace("return 1;", "counter++;return 1;"),
            FILL.replace(
                'cout<<"Введите матрицу:"', 'cout<<setw(8)<<"Введите матрицу:"'
            ),
            FILL.replace("rand()%19-9", "custom()%19-9"),
            FILL.replace("if(choice==1){if", "if(++choice==1){if"),
            FILL.replace("data[row][col]=", "data[col][row]="),
        ):
            with self.subTest(code=code):
                builder, nodes = prepared(PREFIX + code + "}")
                start = next(i for i, n in enumerate(nodes) if n.type == "if_statement")
                self.assertIsNone(conditional_matrix_fill(builder, nodes, start))

    def test_sum_preserves_computation_and_loop_style(self) -> None:
        builder, nodes = prepared(PREFIX + SUM + "}")
        loop = nodes[-1]
        for style in ("decision", "hexagon", "auto"):
            builder.opts.for_style = style
            items = summed_matrix_output(builder, loop)
            self.assertIsNotNone(items)
            self.assertEqual(items[0], M.Simple(M.OUTPUT, "Вывод data[rows][cols]"))
            self.assertIsInstance(items[1], M.ForLoop)
            self.assertEqual(
                items[1].style, "decision" if style == "decision" else "hexagon"
            )
            self.assertEqual(items[1].body.items[0].text, "totals[row]=0")
            self.assertEqual(
                items[1].body.items[1].body.items[0].text,
                "totals[row] = totals[row] + data[row][col]",
            )

    def test_sum_rejects_extra_effects_types_and_reordered_access(self) -> None:
        for prefix, code in (
            (
                PREFIX,
                SUM.replace(
                    "totals[row]+=data[row][col];",
                    "totals[row]+=data[row][col];action();",
                ),
            ),
            (
                PREFIX,
                SUM.replace(
                    "totals[row]+=data[row][col];", "totals[row]+=data[col][row];"
                ),
            ),
            (PREFIX, SUM.replace("totals[row]=0;", "totals[row]=1;")),
            (PREFIX.replace("long long", "double"), SUM),
            (PREFIX.replace("int data", "volatile int data"), SUM),
            (PREFIX.replace("int data[4][5]", "int **data"), SUM),
        ):
            with self.subTest(prefix=prefix, code=code):
                builder, nodes = prepared(prefix + code + "}")
                self.assertIsNone(summed_matrix_output(builder, nodes[-1]))

    def test_original_style_external_indices(self) -> None:
        code = PREFIX.replace("choice;", "choice,i,j;")
        fill = (
            FILL.replace("int row", "row")
            .replace("int col", "col")
            .replace("[row]", "[i]")
            .replace("[col]", "[j]")
            .replace("row=", "i=")
            .replace("row<", "i<")
            .replace("row++", "i++")
            .replace("col=", "j=")
            .replace("col<", "j<")
            .replace("col++", "j++")
        )
        sums = (
            SUM.replace("int row", "row")
            .replace("int col", "col")
            .replace("[row]", "[i]")
            .replace("[col]", "[j]")
            .replace("row=", "i=")
            .replace("row<", "i<")
            .replace("row++", "i++")
            .replace("col=", "j=")
            .replace("col<", "j<")
            .replace("col++", "j++")
        )
        builder, nodes = prepared(code + fill + sums + "}")
        start = next(i for i, n in enumerate(nodes) if n.type == "if_statement")
        self.assertIsNotNone(conditional_matrix_fill(builder, nodes, start))
        self.assertIsNotNone(summed_matrix_output(builder, nodes[-1]))

    def test_global_indices_macros_and_custom_standard_calls(self) -> None:
        external = FILL.replace("int row", "row").replace("int col", "col")
        for prefix, code in (
            ("int row,col;" + PREFIX, external),
            ("#define choice replacement\n" + PREFIX, FILL),
            ("int rand();" + PREFIX, FILL),
            ("int srand(int);" + PREFIX, FILL),
            ("int time(int);" + PREFIX, FILL),
            (
                PREFIX.replace("choice;", "choice,row,col;"),
                external + "return row+col;",
            ),
        ):
            with self.subTest(prefix=prefix):
                builder, nodes = prepared(prefix + code + "}")
                start = next(i for i, n in enumerate(nodes) if n.type == "if_statement")
                self.assertIsNone(conditional_matrix_fill(builder, nodes, start))
