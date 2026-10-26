"""Измерение и перенос текста со шрифтом Times New Roman/Liberation Serif."""

import os
import re
from functools import lru_cache
from pathlib import Path

FONT_MONO = "Times New Roman, Liberation Serif, Times, serif"
FONT_UI = FONT_MONO

CHAR_RATIO = 0.6


@lru_cache(maxsize=16)
def _font(size: float) -> object | None:
    """Использует установленный метрически совместимый шрифт без сетевых ресурсов."""
    try:
        from PIL import ImageFont

        windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for path in (
            windows / "times.ttf",
            "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
            "/Library/Fonts/Times New Roman.ttf",
            Path.home() / "Library/Fonts/Times New Roman.ttf",
            "/usr/share/fonts/TTF/LiberationSerif-Regular.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
            "/usr/share/fonts/liberation/LiberationSerif-Regular.ttf",
        ):
            if Path(path).is_file():
                return ImageFont.truetype(path, size=size * 4)
        return ImageFont.truetype("LiberationSerif-Regular.ttf", size=size * 4)
    except (ImportError, OSError):
        return None


@lru_cache(maxsize=4096)
def text_width(s: str, size: float) -> float:
    font = _font(size)
    if font is not None:
        return font.getlength(s) / 4
    # Консервативная оценка при отсутствии системного шрифта/Pillow.
    return (
        sum(0.9 if c in "ЖШЩМW@%" else 0.35 if c in "il.,:;!|' " else 0.6 for c in s)
        * size
    )


def normalize(s: str) -> str:
    """Collapse newlines and runs of whitespace."""
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    return s.strip()


_SOFT_BREAK = re.compile(r"(?<=[,;])|(?<=\))(?=\s*[&|+\-*/%<>=?:])|(?<=[&|])(?=\s)")


def _hard_split(token: str, width: int):
    """Split an over-long token at soft break points, or hard if there are none."""
    parts, cur = [], ""
    for piece in re.split(r"(?<=[,;.:_>])", token):
        if not piece:
            continue
        if cur and len(cur) + len(piece) > width:
            parts.append(cur)
            cur = piece
        else:
            cur += piece
    if cur:
        parts.append(cur)
    out = []
    for p in parts:
        while len(p) > width:
            out.append(p[:width])
            p = p[width:]
        if p:
            out.append(p)
    return out or [token]


def wrap_text(text: str, width: int):
    """Wrap a string into lines of at most `width` characters."""
    text = normalize(text)
    if not text:
        return [""]
    if len(text) <= width:
        return [text]
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        if len(w) > width:
            if cur:
                lines.append(cur)
                cur = ""
            chunks = _hard_split(w, width)
            lines.extend(chunks[:-1])
            cur = chunks[-1]
            continue
        cand = w if not cur else cur + " " + w
        if len(cand) <= width:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
