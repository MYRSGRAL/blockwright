"""SVG to PNG through a headless Chromium-based browser (Edge or Chrome).

Edge ships with every Windows, so no rasterisation library is needed.
"""

import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Chromium\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
    "/usr/bin/microsoft-edge",
    "/var/lib/flatpak/exports/bin/org.chromium.Chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
NAMES = [
    "msedge",
    "chrome",
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "microsoft-edge",
    "microsoft-edge-stable",
]

# Chromium вычитает высоту browser chrome из области документа даже в headless.
VIEWPORT_ALLOWANCE = 128

_SIZE_RE = re.compile(
    r'<svg[^>]*?\bwidth="([\d.]+)"[^>]*?\bheight="([\d.]+)"', re.DOTALL
)


def find_browser() -> str | None:
    override = os.environ.get("BLOCKWRIGHT_BROWSER")
    if override and os.path.isfile(override):
        return override
    for name in NAMES:
        p = shutil.which(name)
        if p:
            return p
    for p in CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def svg_size(path: str) -> tuple[float, float]:
    with open(path, encoding="utf-8") as fh:
        head = fh.read(4096)
    m = _SIZE_RE.search(head)
    if not m:
        return 1200, 900
    return float(m.group(1)), float(m.group(2))


def convert(
    svg_path: str,
    png_path: str,
    scale: float = 2.0,
    browser: str | None = None,
    timeout: float = 90,
) -> bool:
    """Создаёт PNG через Chromium или librsvg и атомарно заменяет результат."""
    rasterizer = shutil.which("rsvg-convert") if browser is None else None
    browser = browser or (find_browser() if not rasterizer else None)
    if not browser and not rasterizer:
        return False
    w, h = svg_size(svg_path)
    if not all(math.isfinite(v) and v > 0 for v in (w, h, scale)):
        return False
    if scale > 8 or w * h * scale**2 > 100_000_000:
        return False
    target = Path(png_path).resolve()
    try:
        with tempfile.TemporaryDirectory(
            prefix="blockwright-png-", dir=target.parent
        ) as tmp:
            output = Path(tmp) / "result.png"
            if rasterizer:
                cmd = [
                    rasterizer,
                    "-z",
                    str(scale),
                    "-o",
                    str(output),
                    str(Path(svg_path).resolve()),
                ]
            else:
                cmd = [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--no-first-run",
                    "--disable-extensions",
                    f"--force-device-scale-factor={scale}",
                    f"--screenshot={output}",
                    f"--window-size={math.ceil(w)},{math.ceil(h) + VIEWPORT_ALLOWANCE}",
                    Path(svg_path).resolve().as_uri(),
                ]
            result = subprocess.run(
                cmd,
                timeout=timeout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if result.returncode != 0 or not output.is_file():
                return False
            with output.open("rb") as stream:
                if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                    return False
            if browser:
                from PIL import Image

                dimensions = (math.ceil(w * scale), math.ceil(h * scale))
                with Image.open(output) as image:
                    if image.width < dimensions[0] or image.height < dimensions[1]:
                        return False
                    image.crop((0, 0, *dimensions)).save(output)
            output.replace(target)
            return True
    except (OSError, subprocess.TimeoutExpired):
        return False
