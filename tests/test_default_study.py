"""Основной профиль автоматически строит одобренную схему сортировки строк."""

import tempfile
import unittest
from pathlib import Path

from blockwright import vendored

vendored.activate()

from blockwright import model as M
from blockwright import project
from blockwright.cli import Opts, layout_for_report, main
from blockwright.geometry import shape_port, validate_geometry, validate_ports
from tests.test_input_study import walk

SOURCE = r"""int main(){
int a[10][10],n,m,mode,i,j,k,temp;long long sum[10],tempSum;
cout<<"Введите размеры:";
if(!(cin>>n>>m)||n<1||n>10||m<1||m>10){cout<<"Ошибка";return 1;}
cout<<"Заполнение: 1 — вручную, 2 — случайно:";
if(!(cin>>mode)||(mode!=1&&mode!=2)){cout<<"Ошибка";return 1;}
if(mode==2){srand(time(0));}
if(mode==1){cout<<"Введите элементы матрицы:";}
for(i=0;i<n;i++){for(j=0;j<m;j++){
if(mode==1){if(!(cin>>a[i][j])){cout<<"Ошибка";return 1;}}
else{a[i][j]=rand()%19-9;}}}
cout<<"Исходная матрица:";
for(i=0;i<n;i++){sum[i]=0;for(j=0;j<m;j++){
cout<<a[i][j]<<" ";sum[i]+=a[i][j];}cout<<"\n";}
for(i=0;i<n-1;i++){for(j=0;j<n-1-i;j++){
if(sum[j]>sum[j+1]){tempSum=sum[j];sum[j]=sum[j+1];sum[j+1]=tempSum;
for(k=0;k<m;k++){temp=a[j][k];a[j][k]=a[j+1][k];a[j+1][k]=temp;}}}}
cout<<"Упорядоченная матрица:";
for(i=0;i<n;i++){for(j=0;j<m;j++){cout<<a[i][j]<<" ";}cout<<"\n";}
return 0;}"""


class DefaultStudy(unittest.TestCase):
    def test_sorting_source_generates_approved_structure_without_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "sorting.cpp"
            source_path.write_text(SOURCE)
            source = project.load(str(source_path))
            chart = project.charts(source, Opts(), source.known)[0]
            items = list(walk(chart.body))
            self.assertEqual(sum(isinstance(item, M.ForLoop) for item in items), 5)
            self.assertEqual(
                [
                    item.text
                    for item in items
                    if isinstance(item, M.Simple) and item.kind == M.INPUT
                ],
                ["n, m", "mode", "a[n][m]"],
            )
            self.assertEqual(
                [
                    item.text
                    for item in items
                    if isinstance(item, M.Simple) and item.kind == M.OUTPUT
                ],
                ["a[n][m]", "a[n][m]"],
            )
            self.assertTrue(
                any(
                    isinstance(item, M.Simple)
                    and item.text == "a[n][m] = random(-9, 9)"
                    for item in items
                )
            )
            self.assertEqual(len([item for item in items if isinstance(item, M.If)]), 2)
            info = chart.info
            fn = M.Function(
                info["name"],
                info["signature"],
                info["short"],
                str(source_path),
                source_path.name,
                info["line"],
                "cpp",
                chart.body,
            )
            frame, options = layout_for_report(fn, Opts())
            self.assertEqual(len(frame.shapes), 19)
            self.assertEqual(options.page_height, 0)
            self.assertEqual(validate_geometry(frame), [])
            self.assertEqual(validate_ports(frame), [])
            for header in (shape for shape in frame.shapes if shape["kind"] == M.PREP):
                left = shape_port(header, "left")
                self.assertTrue(
                    any(
                        edge["arrow"] and edge["points"][-1] == left
                        for edge in frame.edges
                    )
                )
            out = Path(directory) / "out"
            self.assertEqual(
                main([str(source_path), "--no-ui", "-q", "-o", str(out)]), 0
            )
            self.assertEqual(
                [path.name for path in out.glob("*.svg")], ["sorting__main.svg"]
            )

    def test_explicit_checks_keep_the_original_input_control(self) -> None:
        from tests.test_symbolic_study import build

        # Подробный builder не применяет сокращения основного профиля.
        body = build(SOURCE, study=False)
        self.assertTrue(
            any(isinstance(item, M.If) and "cin" in item.cond for item in walk(body))
        )
