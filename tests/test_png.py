"""Проверки растрового экспорта без зависимости от установленного браузера."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from blockwright import png


class RasterExport(unittest.TestCase):
    @unittest.skipUnless(png.find_browser(), "Chromium отсутствует")
    def test_chromium_keeps_bottom_of_tall_chart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svg, target = Path(tmp) / "tall.svg", Path(tmp) / "out.png"
            svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="150" height="1200"><rect width="150" height="1200" fill="white"/><rect x="10" y="1170" width="130" height="20" fill="black"/></svg>',
                encoding="utf-8",
            )
            self.assertTrue(
                png.convert(str(svg), str(target), browser=png.find_browser(), scale=1)
            )
            with Image.open(target) as image:
                self.assertEqual(image.size, (150, 1200))
                self.assertLess(max(image.convert("RGB").getpixel((70, 1180))), 30)

    def test_failed_converter_does_not_accept_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svg, target = Path(tmp) / "in.svg", Path(tmp) / "out.png"
            svg.write_text('<svg width="20" height="20"></svg>', encoding="utf-8")
            target.write_bytes(b"old result")
            with patch.object(
                png.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)
            ):
                self.assertFalse(png.convert(str(svg), str(target), browser="broken"))
            self.assertEqual(target.read_bytes(), b"old result")

    def test_rsvg_converter_is_used_without_browser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svg, target = Path(tmp) / "схема.svg", Path(tmp) / "out.png"
            svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20" fill="white"/></svg>',
                encoding="utf-8",
            )
            if not png.shutil.which("rsvg-convert"):
                self.skipTest("rsvg-convert отсутствует")
            with patch.object(png, "find_browser", return_value=None):
                self.assertTrue(png.convert(str(svg), str(target)))
            self.assertEqual(target.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
