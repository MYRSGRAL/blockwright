"""Interactive source picker in the terminal.

Output is ANSI escape codes, input comes from msvcrt on Windows and termios
elsewhere. Mouse reporting is enabled when the terminal supports it.
"""

import logging
import os
import shutil
import sys
from typing import ClassVar

from . import parse as P
from . import project

IS_WIN = os.name == "nt"

# ------------------------------------------------------------------- style
R = "\x1b[0m"
B = "\x1b[1m"
DIM = "\x1b[38;5;245m"
TITLE = "\x1b[1;38;5;255;48;5;24m"
HEAD = "\x1b[1;38;5;39m"
SEL = "\x1b[1;38;5;231;48;5;25m"
SEL2 = "\x1b[38;5;252;48;5;238m"
KEY = "\x1b[38;5;214m"
ON = "\x1b[38;5;41m"
DIR = "\x1b[38;5;75m"
WARN = "\x1b[38;5;203m"
OKC = "\x1b[38;5;41m"


def _unicode_ok():
    enc = (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "")
    return enc in ("utf8", "cp65001", "utf8mb4")


class Glyphs:
    def __init__(self, uni):
        if uni:
            self.tl, self.tr, self.bl, self.br = "╭", "╮", "╰", "╯"
            self.h, self.v = "─", "│"
            self.on, self.off = "◉", "○"
            self.dir, self.up, self.cur = "▸", "↑", "❯"
            self.dot = "·"
        else:
            self.tl = self.tr = self.bl = self.br = "+"
            self.h, self.v = "-", "|"
            self.on, self.off = "[x]", "[ ]"
            self.dir, self.up, self.cur = ">", "^", ">"
            self.dot = "-"


FOR_STYLES = ["auto", "hexagon", "decision"]
IO_STYLES = ["pretty", "list", "code"]
RET_STYLES = ["auto", "value", "end"]
PNG_SCALES = [0, 1, 2, 3, 4]

DEFAULTS = {
    "for_style": "decision",
    "io_style": "pretty",
    "return_style": "auto",
    "width": 38,
    "png": 0,
    "keep_std": False,
    "ui_lang": "ru",
}

# -------------------------------------------------------------------- i18n
L10N = {
    "ru": {
        "title": "  Блок-схемы по исходному коду   ·   выбор исходников",
        "folder": "Папка:",
        "marked": "отмечено файлов: {0}",
        "files": "ФАЙЛЫ И ПАПКИ",
        "funcs": "ФУНКЦИИ  {0} из {1}",
        "up": "на уровень выше",
        "settings": "Настройки",
        "o_for": "цикл for",
        "o_io": "ввод-вывод",
        "o_ret": "return",
        "o_width": "ширина текста",
        "o_png": "растр PNG",
        "o_std": "префикс std::",
        "for_auto": "как в коде",
        "for_hexagon": "шестиугольник",
        "for_decision": "через условие",
        "io_pretty": "связной фразой",
        "io_list": "перечислением",
        "io_code": "как в коде",
        "ret_auto": "авто",
        "ret_value": "всегда «Возврат»",
        "ret_end": "всегда «Конец»",
        "png_off": "не делать",
        "std_keep": "оставить",
        "std_drop": "убирать",
        "hint": "{k}↑↓{r} выбор  {k}Space{r} отметить  {k}→{r} в папку  {k}←{r} наверх  "
        "{k}Tab{r} панель  {k}a/n{r} все/снять  {k}/{r} поиск  {k}l{r} язык  "
        "{k}Enter{r} ПОСТРОИТЬ  {k}q{r} выход",
        "hint_short": "{k}↑↓{r} {k}Space{r} {k}←→{r} {k}Tab{r}  {k}Enter{r} построить  "
        "{k}q{r} выход",
        "filter": "Фильтр:",
        "filter_hint": "Enter — применить, Esc — сбросить",
        "no_files": "Не отмечено ни одного файла — нажмите Space",
        "no_funcs": "Все функции выключены",
        "press_any": "Нажмите любую клавишу…",
    },
    "en": {
        "title": "  Flowcharts from source code   ·   pick the sources",
        "folder": "Folder:",
        "marked": "files selected: {0}",
        "files": "FILES AND FOLDERS",
        "funcs": "FUNCTIONS  {0} of {1}",
        "up": "one level up",
        "settings": "Settings",
        "o_for": "for loop",
        "o_io": "input/output",
        "o_ret": "return",
        "o_width": "text width",
        "o_png": "PNG raster",
        "o_std": "std:: prefix",
        "for_auto": "as in code",
        "for_hexagon": "hexagon",
        "for_decision": "as a decision",
        "io_pretty": "as a sentence",
        "io_list": "as a list",
        "io_code": "as in code",
        "ret_auto": "auto",
        "ret_value": "always “Return”",
        "ret_end": "always “End”",
        "png_off": "skip",
        "std_keep": "keep",
        "std_drop": "strip",
        "hint": "{k}↑↓{r} move  {k}Space{r} mark  {k}→{r} enter  {k}←{r} up  "
        "{k}Tab{r} panel  {k}a/n{r} all/none  {k}/{r} filter  {k}l{r} language  "
        "{k}Enter{r} BUILD  {k}q{r} quit",
        "hint_short": "{k}↑↓{r} {k}Space{r} {k}←→{r} {k}Tab{r}  {k}Enter{r} build  "
        "{k}q{r} quit",
        "filter": "Filter:",
        "filter_hint": "Enter — apply, Esc — clear",
        "no_files": "No files selected — press Space",
        "no_funcs": "All functions are switched off",
        "press_any": "Press any key…",
    },
}
LANG = "ru"


def tr(key, *args):
    text = L10N.get(LANG, L10N["ru"]).get(key) or L10N["ru"].get(key, key)
    for i, value in enumerate(args):
        text = text.replace("{" + str(i) + "}", str(value))
    return text


# ---------------------------------------------------------------- terminal
def enable_vt():
    if not IS_WIN:
        return True
    try:
        import ctypes

        k = ctypes.windll.kernel32
        for handle, flag in ((-11, 0x0004), (-10, 0x0200)):
            h = k.GetStdHandle(handle)
            mode = ctypes.c_uint32()
            if k.GetConsoleMode(h, ctypes.byref(mode)):
                k.SetConsoleMode(h, mode.value | flag)
        return True
    except Exception:  # noqa: BLE001
        return False


class Input:
    """Events: ('key', name) or ('mouse', button, x, y)."""

    def __init__(self):
        self._saved = None

    def __enter__(self):
        if not IS_WIN:
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        sys.stdout.write("\x1b[?1000h\x1b[?1006h")
        sys.stdout.flush()
        return self

    def __exit__(self, *exc):
        sys.stdout.write("\x1b[?1006l\x1b[?1000l")
        sys.stdout.flush()
        if self._saved is not None:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)

    def _getch(self):
        if IS_WIN:
            import msvcrt

            return msvcrt.getwch()
        return sys.stdin.read(1)

    def _ready(self):
        if IS_WIN:
            import msvcrt

            return msvcrt.kbhit()
        import select

        return bool(select.select([sys.stdin], [], [], 0.03)[0])

    _WIN: ClassVar[dict[str, str]] = {
        "H": "up",
        "P": "down",
        "K": "left",
        "M": "right",
        "I": "pgup",
        "Q": "pgdn",
        "G": "home",
        "O": "end",
        "S": "del",
    }
    _CSI: ClassVar[dict[str, str]] = {
        "A": "up",
        "B": "down",
        "C": "right",
        "D": "left",
        "H": "home",
        "F": "end",
    }
    _TILDE: ClassVar[dict[str, str]] = {
        "5": "pgup",
        "6": "pgdn",
        "1": "home",
        "4": "end",
        "3": "del",
    }

    def read(self):
        ch = self._getch()
        if ch in ("\x00", "\xe0"):
            return ("key", self._WIN.get(self._getch(), ""))
        if ch == "\x1b":
            if not self._ready():
                return ("key", "esc")
            if self._getch() != "[":
                return ("key", "esc")
            body = ""
            while self._ready():
                c = self._getch()
                body += c
                if c.isalpha() or c == "~":
                    break
            if body.startswith("<"):
                try:
                    btn, x, y = (int(v) for v in body[1:-1].split(";"))
                    return ("mouse", btn if body[-1] == "M" else -1, x, y)
                except ValueError:
                    return ("key", "")
            if body and body[-1] in self._CSI:
                return ("key", self._CSI[body[-1]])
            if body.endswith("~"):
                return ("key", self._TILDE.get(body[:-1], ""))
            return ("key", "")
        if ch in ("\r", "\n"):
            return ("key", "enter")
        if ch == "\t":
            return ("key", "tab")
        if ch in ("\x7f", "\b"):
            return ("key", "backspace")
        if ch == "\x03":
            return ("key", "quit")
        return ("key", ch)


def plain_len(s):
    out, i = 0, 0
    while i < len(s):
        if s[i] == "\x1b":
            j = s.find("m", i)
            i = len(s) if j < 0 else j + 1
        else:
            out += 1
            i += 1
    return out


def fit(s, width):
    """Cut a string with ANSI codes to `width` visible characters."""
    if plain_len(s) <= width:
        return s
    out, seen, i = [], 0, 0
    while i < len(s) and seen < width - 1:
        if s[i] == "\x1b":
            j = s.find("m", i)
            j = len(s) - 1 if j < 0 else j
            out.append(s[i : j + 1])
            i = j + 1
        else:
            out.append(s[i])
            seen += 1
            i += 1
    return "".join(out) + "…" + R


def pad(s, width):
    n = plain_len(s)
    return s + " " * max(0, width - n) if n <= width else fit(s, width)


# ------------------------------------------------------------------ picker
class Picker:
    def __init__(self, root, cfg):
        self.cwd = os.path.abspath(root)
        if not os.path.isdir(self.cwd):
            self.cwd = os.path.dirname(self.cwd) or os.getcwd()
        self.cfg = cfg
        self.g = Glyphs(_unicode_ok())
        self.marked = set()  # absolute paths of marked files
        self.cache = {}  # path -> (mtime, [(name, line)])
        self.funcs = []
        self.func_off = set()  # functions switched off, keyed rel::name
        self.panel = 0
        self.cur = [0, 0]
        self.top = [0, 0]
        self.filter = ""
        self.typing = False
        self.msg = ""
        self.zones = []
        self.entries = []
        self.mark_all_in(self.cwd, True)
        self.refresh()

    # --- file system
    def listing(self):
        items = []
        parent = os.path.dirname(self.cwd)
        if parent and parent != self.cwd:
            items.append(("up", parent, ".."))
        try:
            names = sorted(os.listdir(self.cwd), key=str.lower)
        except OSError:
            names = []
        dirs, files = [], []
        exts = P.extensions()
        for nm in names:
            full = os.path.join(self.cwd, nm)
            if os.path.isdir(full):
                if nm in P.SKIP_DIRS or nm.startswith("."):
                    continue
                dirs.append(("dir", full, nm))
            elif os.path.splitext(nm)[1].lower() in exts:
                files.append(("file", full, nm))
        return items + dirs + files

    def sources_in(self, folder):
        return P.discover([folder], recursive=True)

    def mark_all_in(self, folder, value):
        for f in self.sources_in(folder):
            if value:
                self.marked.add(f)
            else:
                self.marked.discard(f)

    def dir_state(self, folder):
        src = self.sources_in(folder)
        if not src:
            return (0, 0)
        return (sum(1 for f in src if f in self.marked), len(src))

    # --- functions
    def file_funcs(self, path):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return []
        hit = self.cache.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
        try:
            source = project.load(path)
        except OSError:
            return []
        out = []
        for info in project.outline(source) if source is not None else []:
            out.append((info["name"], info["line"]))
        self.cache[path] = (mtime, out)
        return out

    def refresh(self):
        self.entries = self.listing()
        self.funcs = []
        base = self.common_base()
        for path in sorted(self.marked):
            rel = self.short(path, base)
            for name, line in self.file_funcs(path):
                self.funcs.append((rel, name, line, rel + "::" + name))
        for panel in (0, 1):
            self.cur[panel] = min(self.cur[panel], max(0, len(self.items(panel)) - 1))

    def common_base(self):
        if not self.marked:
            return self.cwd
        try:
            c = os.path.commonpath(list(self.marked))
            return c if os.path.isdir(c) else os.path.dirname(c)
        except ValueError:
            return self.cwd

    @staticmethod
    def short(path, base):
        try:
            rel = os.path.relpath(path, base)
        except ValueError:
            rel = path
        return rel.replace("\\", "/")

    def visible_entries(self):
        if not self.filter:
            return self.entries
        q = self.filter.lower()
        return [e for e in self.entries if e[0] != "file" or q in e[2].lower()]

    def visible_funcs(self):
        if not self.filter:
            return self.funcs
        q = self.filter.lower()
        return [f for f in self.funcs if q in f[1].lower() or q in f[0].lower()]

    def items(self, panel):
        return self.visible_entries() if panel == 0 else self.visible_funcs()

    # --- drawing
    def frame(self, out, row, width, text, kind):
        g = self.g
        if kind == "top":
            out(
                row,
                DIM
                + g.tl
                + g.h * 2
                + R
                + " "
                + text
                + " "
                + DIM
                + g.h * max(0, width - plain_len(text) - 6)
                + g.tr
                + R,
            )
        else:
            out(row, DIM + g.bl + g.h * (width - 2) + g.br + R)

    def draw(self):
        W, H = shutil.get_terminal_size((100, 30))
        W = max(66, min(W, 200))
        H = max(18, H)
        g = self.g
        self.zones = []
        buf = ["\x1b[H"]

        def line(row, s=""):
            buf.append(f"\x1b[{row};1H{fit(s, W)}\x1b[K")

        line(1, TITLE + pad(tr("title").replace("·", g.dot), W) + R)
        marked = len(self.marked)
        info = f" {DIM}{tr('folder')}{R} {self.cwd}"
        right = f"{ON}{tr('marked', marked)}{R}"
        line(2, pad(info, W - plain_len(right) - 1) + right)

        two = W >= 100
        lw = (W * 45 // 100) if two else W
        rx = lw + 3
        rw = W - rx
        body_top = 4
        opts_h = 5
        body_h = max(4, H - body_top - opts_h - 3)

        ents = self.visible_entries()
        fns = self.visible_funcs()
        on = sum(1 for f in self.funcs if f[3] not in self.func_off)
        head_l = (HEAD if self.panel == 0 else DIM) + tr("files") + R
        head_r = (
            (HEAD if self.panel == 1 else DIM) + tr("funcs", on, len(self.funcs)) + R
        )
        line(body_top - 1, " " + pad(head_l, lw) + (("  " + head_r) if two else ""))

        self._scroll(0, body_h, len(ents))
        self._scroll(1, body_h, len(fns))
        for i in range(body_h):
            row = body_top + i
            if two:
                line(
                    row,
                    " "
                    + pad(self._left(ents, i, lw - 1), lw - 1)
                    + "  "
                    + pad(self._right(fns, i, rw), rw),
                )
                if self.top[0] + i < len(ents):
                    self.zones.append((row, 1, lw, 0, self.top[0] + i))
                if self.top[1] + i < len(fns):
                    self.zones.append((row, rx, W, 1, self.top[1] + i))
            else:
                src = ents if self.panel == 0 else fns
                txt = (
                    self._left(src, i, W - 2)
                    if self.panel == 0
                    else self._right(src, i, W - 2)
                )
                line(row, " " + txt)
                if self.top[self.panel] + i < len(src):
                    self.zones.append((row, 1, W, self.panel, self.top[self.panel] + i))

        c = self.cfg
        o_row = H - opts_h - 1
        self.frame(line, o_row, W, B + tr("settings") + R, "top")
        col = (W - 2) // 2

        def opt(k, name, val):
            return (
                f"{KEY}{k}{R} {name} {DIM}{'.' * max(1, 16 - len(name))}{R} {B}{val}{R}"
            )

        rows = [
            (
                opt("f", tr("o_for"), tr("for_" + c["for_style"])),
                opt("w", tr("o_width"), c["width"]),
            ),
            (
                opt("i", tr("o_io"), tr("io_" + c["io_style"])),
                opt("p", tr("o_png"), f"×{c['png']}" if c["png"] else tr("png_off")),
            ),
            (
                opt("r", tr("o_ret"), tr("ret_" + c["return_style"])),
                opt("s", tr("o_std"), tr("std_keep" if c["keep_std"] else "std_drop")),
            ),
        ]
        for i, (a, b) in enumerate(rows):
            line(
                o_row + 1 + i,
                DIM + g.v + R + pad(" " + a, col) + pad(b, W - 2 - col) + DIM + g.v + R,
            )
        self.frame(line, o_row + 4, W, "", "bottom")

        if self.typing:
            line(
                H - 1,
                f"{KEY}{tr('filter')}{R} {self.filter}█   {DIM}{tr('filter_hint')}{R}",
            )
        elif self.msg:
            line(H - 1, self.msg)
        else:
            long_hint = tr("hint").replace("{k}", KEY).replace("{r}", R)
            short_hint = tr("hint_short").replace("{k}", KEY).replace("{r}", R)
            line(H - 1, long_hint if plain_len(long_hint) <= W else short_hint)
        buf.append("\x1b[J")
        sys.stdout.write("".join(buf))
        sys.stdout.flush()

    def _scroll(self, panel, body_h, total):
        if self.cur[panel] >= total:
            self.cur[panel] = max(0, total - 1)
        self.top[panel] = min(self.top[panel], self.cur[panel])
        if self.cur[panel] >= self.top[panel] + body_h:
            self.top[panel] = self.cur[panel] - body_h + 1
        self.top[panel] = max(0, min(self.top[panel], max(0, total - body_h)))

    def _cursor(self, panel, idx, text):
        if idx != self.cur[panel]:
            return "  " + text
        style = SEL if panel == self.panel else SEL2
        return style + self.g.cur + " " + text + R

    def _left(self, items, i, width):
        idx = self.top[0] + i
        if idx >= len(items):
            return ""
        kind, full, name = items[idx]
        g = self.g
        if kind == "up":
            body = f"{DIR}{g.up} ..{R}  {DIM}{tr('up')}{R}"
        elif kind == "dir":
            got, tot = self.dir_state(full)
            tag = (
                f"{ON}{got}/{tot}{R}"
                if got
                else (f"{DIM}{tot}{R}" if tot else f"{DIM}—{R}")
            )
            body = f"{DIR}{g.dir} {name}/{R}  {tag}"
        else:
            mark = (ON + g.on + R) if full in self.marked else (DIM + g.off + R)
            body = f"{mark} {name}"
        return self._cursor(0, idx, pad(body, width - 2))

    def _right(self, items, i, width):
        idx = self.top[1] + i
        if idx >= len(items):
            return ""
        rel, name, line_no, key = items[idx]
        mark = (DIM + self.g.off + R) if key in self.func_off else (ON + self.g.on + R)
        loc = f"{DIM}{rel}:{line_no}{R}"
        body = f"{mark} {name}"
        space = width - 2 - plain_len(body) - plain_len(loc) - 1
        body = body + " " * max(1, space) + loc
        return self._cursor(1, idx, pad(body, width - 2))

    # --- actions
    def enter_dir(self, path):
        self.cwd = os.path.abspath(path)
        self.cur[0] = 0
        self.top[0] = 0
        self.filter = ""
        self.refresh()

    def toggle(self, panel, idx):
        items = self.items(panel)
        if idx >= len(items):
            return
        if panel == 0:
            kind, full, _ = items[idx]
            if kind == "file":
                self.marked.discard(full) if full in self.marked else self.marked.add(
                    full
                )
            else:
                got, tot = self.dir_state(full)
                self.mark_all_in(full, got < tot)
            self.refresh()
        else:
            key = items[idx][3]
            self.func_off.discard(key) if key in self.func_off else self.func_off.add(
                key
            )

    def set_all(self, value):
        if self.panel == 0:
            for kind, full, _ in self.visible_entries():
                if kind == "file":
                    self.marked.add(full) if value else self.marked.discard(full)
                elif kind == "dir":
                    self.mark_all_in(full, value)
            self.refresh()
        else:
            for f in self.visible_funcs():
                self.func_off.discard(f[3]) if value else self.func_off.add(f[3])

    def toggle_lang(self):
        global LANG
        LANG = "en" if LANG == "ru" else "ru"
        self.cfg["ui_lang"] = LANG
        self.g = Glyphs(_unicode_ok())

    def cycle(self, key):
        c = self.cfg

        def nxt(keys, val):
            return keys[(keys.index(val) + 1) % len(keys)]

        if key == "f":
            c["for_style"] = nxt(FOR_STYLES, c["for_style"])
        elif key == "i":
            c["io_style"] = nxt(IO_STYLES, c["io_style"])
        elif key == "r":
            c["return_style"] = nxt(RET_STYLES, c["return_style"])
        elif key == "p":
            c["png"] = PNG_SCALES[(PNG_SCALES.index(c["png"]) + 1) % len(PNG_SCALES)]
        elif key == "s":
            c["keep_std"] = not c["keep_std"]
        elif key == "w":
            c["width"] = 26 if c["width"] >= 50 else c["width"] + 6

    # --- main loop
    def run(self):
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
        try:
            with Input() as inp:
                while True:
                    self.draw()
                    res = self.handle(inp.read())
                    if res is not None:
                        return res
        finally:
            sys.stdout.write("\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()

    def handle(self, ev):
        self.msg = ""
        if ev[0] == "mouse":
            _, btn, x, y = ev
            if btn in (64, 65):
                step = -3 if btn == 64 else 3
                self.cur[self.panel] = max(
                    0, min(len(self.items(self.panel)) - 1, self.cur[self.panel] + step)
                )
                return None
            if btn != 0:
                return None
            for row, x0, x1, panel, idx in self.zones:
                if y == row and x0 <= x <= x1:
                    same = self.panel == panel and self.cur[panel] == idx
                    self.panel, self.cur[panel] = panel, idx
                    items = self.items(panel)
                    if (
                        same
                        and panel == 0
                        and idx < len(items)
                        and items[idx][0] != "file"
                    ):
                        self.enter_dir(items[idx][1])
                    else:
                        self.toggle(panel, idx)
                    return None
            return None

        key = ev[1]
        if self.typing:
            if key in ("enter", "esc"):
                if key == "esc":
                    self.filter = ""
                self.typing = False
            elif key == "backspace":
                self.filter = self.filter[:-1]
            elif len(key) == 1 and key.isprintable():
                self.filter += key
            self.cur = [0, 0]
            return None

        items = self.items(self.panel)
        last = max(0, len(items) - 1)
        if key in ("q", "esc", "quit"):
            return False
        if key == "tab":
            self.panel = 1 - self.panel
        elif key == "up":
            self.cur[self.panel] = max(0, self.cur[self.panel] - 1)
        elif key == "down":
            self.cur[self.panel] = min(last, self.cur[self.panel] + 1)
        elif key == "pgup":
            self.cur[self.panel] = max(0, self.cur[self.panel] - 10)
        elif key == "pgdn":
            self.cur[self.panel] = min(last, self.cur[self.panel] + 10)
        elif key == "home":
            self.cur[self.panel] = 0
        elif key == "end":
            self.cur[self.panel] = last
        elif key == "right":
            if self.panel == 0 and items:
                kind, full, _ = items[self.cur[0]]
                if kind in ("dir", "up"):
                    self.enter_dir(full)
                else:
                    self.panel = 1
            else:
                self.panel = 1
        elif key == "left":
            if self.panel == 1:
                self.panel = 0
            else:
                parent = os.path.dirname(self.cwd)
                if parent and parent != self.cwd:
                    self.enter_dir(parent)
        elif key == " ":
            self.toggle(self.panel, self.cur[self.panel])
        elif key == "a":
            self.set_all(True)
        elif key == "n":
            self.set_all(False)
        elif key == "/":
            self.typing = True
            self.filter = ""
        elif key == "l":
            self.toggle_lang()
        elif key in ("f", "i", "r", "p", "s", "w"):
            self.cycle(key)
        elif key == "enter":
            if self.panel == 0 and items:
                kind, full, _ = items[self.cur[0]]
                if kind in ("dir", "up"):
                    self.enter_dir(full)
                    return None
            return self.finish()
        return None

    def finish(self):
        if not self.marked:
            self.msg = WARN + tr("no_files") + R
            return None
        names = [f[1] for f in self.funcs if f[3] not in self.func_off]
        if not names:
            self.msg = WARN + tr("no_funcs") + R
            return None
        self.cfg["paths"] = sorted(self.marked)
        self.cfg["only"] = [] if len(names) == len(self.funcs) else sorted(set(names))
        self.cfg["root"] = self.cwd
        self.cfg["ui_lang"] = LANG
        return self.cfg


def run(root, cfg=None):
    """Show the picker; returns the config, False when cancelled, or None."""
    global LANG
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return None
    enable_vt()
    conf = dict(DEFAULTS)
    conf.update(cfg or {})
    if conf.get("ui_lang") in L10N:
        LANG = conf["ui_lang"]
    try:
        return Picker(root, conf).run()
    except KeyboardInterrupt:
        return False


def pause(message=None):
    """Wait for a key so a double-clicked console window does not vanish."""
    if not sys.stdin.isatty():
        return
    sys.stdout.write("\n" + DIM + message + R + "\n")
    sys.stdout.flush()
    try:
        if IS_WIN:
            import msvcrt

            msvcrt.getwch()
        else:
            import termios
            import tty

            fd = sys.stdin.fileno()
            saved = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    except Exception:
        logging.getLogger(__name__).debug("Не удалось дождаться клавиши", exc_info=True)
