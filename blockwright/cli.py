"""Command-line interface."""

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, replace

from . import __version__, langs, project, vendored
from . import model as M
from . import parse as P
from . import png as PNG
from .album import render_html
from .layout import Frame, layout_function
from .pages import CONNECTOR_DIAMETER, split_pages
from .render import MARGIN, TITLE_H, frame_to_dict, render_svg


@dataclass
class Opts:
    max_chars: int = 38
    keep_std: bool = False
    io_style: str = "pretty"  # pretty | list | code
    for_style: str = "decision"  # Явные условие и шаг цикла по умолчанию.
    return_style: str = "auto"  # auto | value | end
    lang: str = "ru"  # language of the words on the charts
    yes_label: str = "Да"
    no_label: str = "Нет"
    begin_label: str = "Начало"
    end_label: str = "Конец"
    default_label: str = "иначе"
    plain_begin: bool = False
    study: bool = True
    notation: str = "course"
    page_height: float = 926.0
    page_width: float = 605.0


CHART_WORDS = {
    "ru": {
        "yes": "Да",
        "no": "Нет",
        "begin": "Начало",
        "end": "Конец",
        "default": "иначе",
    },
    "en": {"yes": "Yes", "no": "No", "begin": "Begin", "end": "End", "default": "else"},
}


def layout_for_report(fn: M.Function, opts: Opts) -> tuple[Frame, Opts]:
    """Выбирает переносы под ширину отчёта, сохраняя размер шрифта."""
    frame = layout_function(fn, opts)

    def width_with_connectors(geometry: Frame) -> float:
        reserve = (
            CONNECTOR_DIAMETER
            if opts.page_height and geometry.height + 2 * MARGIN > opts.page_height
            else 0
        )
        return geometry.width + 2 * MARGIN + reserve

    if not opts.study or width_with_connectors(frame) <= opts.page_width:
        return frame, opts
    candidates = [(frame, opts)]
    for width in (32, 28, 24, 20, 16):
        if width >= opts.max_chars:
            continue
        candidate_opts = replace(opts, max_chars=width)
        candidates.append((layout_function(fn, candidate_opts), candidate_opts))

    def score(candidate: tuple[Frame, Opts]) -> tuple[float, float]:
        geometry, _ = candidate
        overflow = max(0.0, width_with_connectors(geometry) - opts.page_width)
        return overflow, geometry.height

    return min(candidates, key=score)


_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def open_in_browser(path):
    """Open the album; on Android through termux-open."""
    full = os.path.abspath(path)
    if vendored.is_termux():
        opener = shutil.which("termux-open")
        if opener:
            try:
                subprocess.run(
                    [opener, "--content-type", "text/html", full],
                    check=False,
                    timeout=20,
                )
                return True
            except (OSError, subprocess.TimeoutExpired):
                pass
        print(f"Откройте в браузере: {full}")
        return False
    try:
        return webbrowser.open("file:///" + full.replace("\\", "/"))
    except Exception:  # noqa: BLE001
        print(f"Откройте в браузере: {full}")
        return False


def rel_path(path, base):
    try:
        rel = os.path.relpath(path, base)
    except ValueError:  # another drive on Windows
        rel = path
    if rel.startswith((".." + os.sep, "../")):
        rel = os.path.basename(path)
    return rel.replace("\\", "/")


def safe_name(s, limit=90):
    s = _BAD.sub("_", s).strip(" .")
    s = re.sub(r"\s+", "_", s)
    return s[:limit] or "diagram"


def build_parser():
    ap = argparse.ArgumentParser(
        prog="blockwright",
        description="Компактные чёрно-белые блок-схемы учебных программ C++. "
        "Разбор кода выполняется tree-sitter; обозначения — по ГОСТ "
        "19.701-90 или методичке с волнистым выводом.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Примеры:\n"
        '  python -m blockwright "Лабораторная работа №1"\n'
        "  python -m blockwright src -o out --only main --only *Queue*\n"
        "  python -m blockwright . --for-style decision --io-style code\n",
    )
    ap.add_argument(
        "paths",
        nargs="*",
        default=[],
        help="файлы или папки с исходниками; если не указать — "
        "откроется интерактивный выбор в консоли",
    )
    ap.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="открыть интерактивный выбор, даже если путь указан",
    )
    ap.add_argument(
        "--no-ui",
        action="store_true",
        help="не открывать интерактивный выбор (для скриптов)",
    )
    ap.add_argument(
        "-o",
        "--out",
        default=None,
        help="папка для результата (по умолчанию <путь>/блок-схемы)",
    )
    ap.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="ШАБЛОН",
        help="строить только функции, подходящие под шаблон (можно повторять)",
    )
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="ШАБЛОН",
        help="пропустить функции по шаблону",
    )
    ap.add_argument(
        "--lang",
        action="append",
        default=[],
        metavar="ЯЗЫК",
        help="явно выбрать cpp, в том числе для файла без расширения",
    )
    ap.add_argument(
        "--lang-dir",
        action="append",
        default=[],
        metavar="ПАПКА",
        help="папка с дополнительными описаниями языков (*.toml); "
        "см. docs/languages.md",
    )
    ap.add_argument(
        "--langs",
        action="store_true",
        dest="list_langs",
        help="показать известные языки и выйти",
    )
    ap.add_argument(
        "--tree",
        action="store_true",
        help="напечатать синтаксическое дерево файлов (типы узлов и поля) "
        "— подсказка для тех, кто пишет описание языка",
    )
    ap.add_argument(
        "--detail",
        choices=["study", "full"],
        default="study",
        help="study — краткая учебная схема; full — подробные выражения C++",
    )
    ap.add_argument(
        "--notation",
        choices=["course", "gost"],
        default="course",
        help="course — вывод с волной по методичке; gost — ввод и вывод "
        "параллелограммами для схем программ ГОСТ 19.701-90",
    )
    ap.add_argument(
        "--page-height",
        type=float,
        default=926.0,
        metavar="PX",
        help="высота области страницы при 96 dpi; 0 — непрерывная схема",
    )
    ap.add_argument(
        "--page-width",
        type=float,
        default=605.0,
        metavar="PX",
        help="ширина области отчёта при 96 dpi (605 px ≈ 160 мм)",
    )
    ap.add_argument(
        "--for-style",
        choices=["auto", "hexagon", "decision"],
        default="decision",
        help="оформление for: шестиугольник «подготовка» или явные блоки",
    )
    ap.add_argument(
        "--io-style",
        choices=["pretty", "list", "natural", "code"],
        default="pretty",
        help="текст ввода-вывода: pretty — связная фраза «Вывод: Итого {n} шт.», "
        "list — перечисление через запятую, code — исходный текст",
    )
    ap.add_argument(
        "--return-style",
        choices=["auto", "value", "end"],
        default="auto",
        help="оформление return: auto — «Конец» для return без значения "
        "и для return 0 в main, value — всегда «Возврат …», "
        "end — всегда «Конец»",
    )
    ap.add_argument(
        "--theme",
        choices=["light", "dark"],
        default=None,
        help="палитра схем и альбома: светлая или тёмная",
    )
    ap.add_argument(
        "--ui-lang",
        choices=["ru", "en"],
        default=None,
        dest="ui_lang",
        help="язык интерфейса альбома и консоли",
    )
    ap.add_argument(
        "--keep-std",
        action="store_true",
        help="не убирать префикс std:: из текста блоков",
    )
    ap.add_argument(
        "--width",
        type=int,
        default=38,
        metavar="N",
        help="максимальная длина строки текста в блоке (по умолчанию 38)",
    )
    ap.add_argument(
        "--plain-begin",
        action="store_true",
        help="в стартовом блоке писать «Начало» вместо сигнатуры функции",
    )
    ap.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="только перечислить найденные функции, ничего не строить",
    )
    ap.add_argument(
        "--png",
        nargs="?",
        type=float,
        const=2.0,
        default=None,
        metavar="МАСШТАБ",
        help="дополнительно сохранить растровые .png (по умолчанию ×2); "
        "нужен установленный Edge или Chrome",
    )
    ap.add_argument("--no-svg", action="store_true", help="не сохранять отдельные .svg")
    ap.add_argument("--no-html", action="store_true", help="не собирать index.html")
    ap.add_argument(
        "--no-recursive", action="store_true", help="не заходить во вложенные папки"
    )
    ap.add_argument(
        "--open", action="store_true", help="открыть готовый index.html в браузере"
    )
    ap.add_argument("-q", "--quiet", action="store_true", help="меньше сообщений")
    ap.add_argument(
        "-V", "--version", action="version", version=f"blockwright {__version__}"
    )
    return ap


def match_name(name, base, only, exclude):
    if only and not any(
        fnmatch.fnmatch(name, p) or fnmatch.fnmatch(base, p) for p in only
    ):
        return False
    return not (
        exclude
        and any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(base, p) for p in exclude)
    )


PREFS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".blockwright-prefs.json",
)


def load_prefs():
    try:
        with open(PREFS, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_prefs(cfg):
    keep = {
        k: cfg[k]
        for k in (
            "for_style",
            "io_style",
            "return_style",
            "width",
            "png",
            "keep_std",
            "ui_lang",
            "theme",
        )
        if k in cfg
    }
    keep["root"] = cfg.get("root", "")
    try:
        with open(PREFS, "w", encoding="utf-8") as fh:
            json.dump(keep, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass


def run_picker(args):
    """Run the picker and update args in place; False if cancelled."""
    from . import tui

    prefs = load_prefs()
    start = args.paths[0] if args.paths else prefs.get("root") or os.getcwd()
    if not os.path.isdir(start):
        start = os.path.dirname(os.path.abspath(start)) or os.getcwd()
    cfg = {k: prefs[k] for k in tui.DEFAULTS if k in prefs}
    cfg.setdefault("ui_lang", args.ui_lang)
    res = tui.run(start, cfg)
    if res is None:
        return None
    if res is False:
        return False
    res["theme"] = args.theme
    save_prefs(res)
    args.paths = res["paths"]
    if res["only"]:
        args.only = res["only"]
    args.for_style = res["for_style"]
    args.io_style = res["io_style"]
    args.return_style = res["return_style"]
    args.width = res["width"]
    args.keep_std = res["keep_std"]
    args.png = float(res["png"]) if res["png"] else None
    args.ui_lang = res.get("ui_lang", args.ui_lang)
    args.open = True
    return True


def print_langs(reg):
    for spec in reg.select():
        state = "есть" if spec.available else f"нет — {spec.install_hint()}"
        print(
            f"  {spec.name:<12} {spec.title:<12} {' '.join(spec.extensions):<40} "
            f"грамматика: {state}"
        )
        print(f"  {'':<12} {spec.path}")


def print_trees(paths, only):
    """`--tree`: node types with field names, as a language description sees them."""
    files = P.discover(paths, only=only) if paths else []
    if not files:
        print("Укажите файл: python -m blockwright --tree prog.cpp", file=sys.stderr)
        return 2
    for path in files:
        source = project.load(path, only)
        if source is None or source.tree is None:
            what = source.spec.install_hint() if source else "язык не определён"
            print(f"{path}: не разобран ({what})", file=sys.stderr)
            continue
        print(f"# {path} [{source.spec.name}]")
        src = source.src

        def walk(node, depth, field, src=src):
            text = src[node.start_byte : node.end_byte].decode("utf-8", "replace")
            head = f"{field}: " if field else ""
            leaf = (
                f"  «{' '.join(text.split())[:60]}»"
                if node.named_child_count == 0
                else ""
            )
            print(f"{'  ' * depth}{head}{node.type}{leaf}")
            for i in range(node.child_count):
                c = node.child(i)
                if c.is_named:
                    walk(c, depth + 1, node.field_name_for_child(i))

        walk(source.tree.root_node, 0, None)
    return 0


def setup_languages(args):
    """Load language descriptions; returns the set of languages to use or None."""
    reg = langs.registry(args.lang_dir)
    for err in reg.errors:
        print(f"  ! {err}", file=sys.stderr)
    only = {x.strip() for v in args.lang for x in v.split(",") if x.strip()}
    only.discard("auto")
    unknown = sorted(only - set(reg.names()))
    if unknown:
        print(
            f"Неизвестный язык: {', '.join(unknown)}. Доступны: {', '.join(reg.names())}",
            file=sys.stderr,
        )
        return False
    return only or None


def main(argv=None):
    args = build_parser().parse_args(argv)
    if (
        args.width < 16
        or not 0 <= args.page_height <= 100_000
        or not 250 <= args.page_width <= 100_000
    ):
        print(
            "Ширина должна быть не меньше 16, высота страницы — от 0 до 100000.",
            file=sys.stderr,
        )
        return 2
    if args.png is not None and not 0 < args.png <= 8:
        print("Масштаб PNG должен быть больше 0 и не больше 8.", file=sys.stderr)
        return 2
    only = setup_languages(args)
    if only is False:
        return 2
    if args.list_langs:
        print_langs(langs.registry())
        return 0
    if args.tree:
        return print_trees(args.paths, only)
    prefs = load_prefs()
    # command-line flags win over remembered choices
    args.ui_lang = args.ui_lang or prefs.get("ui_lang") or "ru"
    args.theme = args.theme or prefs.get("theme") or "light"
    from_ui = False
    if not args.no_ui and not args.list_only and (args.interactive or not args.paths):
        state = run_picker(args)
        if state is False:
            return 0
        from_ui = state is True
        if state is None and not args.paths:
            print(
                'Не указан путь. Пример: python -m blockwright "Лабораторная работа №1"',
                file=sys.stderr,
            )
            return 2
    paths = args.paths or ["."]
    io_style = "list" if args.io_style == "natural" else args.io_style
    words = CHART_WORDS.get(args.ui_lang, CHART_WORDS["ru"])
    opts = Opts(
        max_chars=max(16, args.width),
        keep_std=args.keep_std,
        io_style=io_style,
        for_style=args.for_style,
        return_style=args.return_style,
        plain_begin=args.plain_begin,
        lang=args.ui_lang,
        yes_label=words["yes"],
        no_label=words["no"],
        begin_label=words["begin"],
        end_label=words["end"],
        default_label=words["default"],
        study=args.detail == "study",
        notation=args.notation,
        page_height=args.page_height,
        page_width=args.page_width,
    )

    files = P.discover(paths, recursive=not args.no_recursive, only=only)
    if not files:
        exts = " ".join(sorted(P.extensions(only)))
        print(f"Исходные файлы не найдены (расширения: {exts}).", file=sys.stderr)
        return 2

    root = os.path.abspath(paths[0])
    if os.path.isfile(root):
        root = os.path.dirname(root)
    # common folder of all sources keeps chart captions short
    base_dir = root
    try:
        common = os.path.commonpath(files)
        base_dir = common if os.path.isdir(common) else os.path.dirname(common)
    except ValueError:
        pass
    out_dir = (
        os.path.abspath(args.out) if args.out else os.path.join(root, "блок-схемы")
    )
    if not args.list_only:
        os.makedirs(out_dir, exist_ok=True)

    def log(*a):
        if not args.quiet:
            print(*a)

    # first pass: names of user functions across the whole project
    sources = []
    known = set()
    missing = {}
    failed = False
    for path in files:
        try:
            src = project.load(path, only)
        except OSError as e:
            print(f"  ! {path}: {e}", file=sys.stderr)
            failed = True
            continue
        if src is None:
            continue
        if src.tree is None:
            missing.setdefault(src.spec.name, (src.spec, []))[1].append(path)
            continue
        if src.errors:
            print(
                f"  ! {path}: ошибки синтаксиса C++ — {src.errors}; "
                "схема не построена.",
                file=sys.stderr,
            )
            failed = True
            continue
        known |= src.known
        sources.append(src)
    for spec, paths_ in missing.values():
        print(
            f"  ! {spec.title}: нет грамматики tree-sitter, пропущено файлов — "
            f"{len(paths_)}. Установите: {spec.install_hint()}",
            file=sys.stderr,
        )

    # lab.cpp and lab.py side by side: keep the extension in chart file names
    stems = {}
    for source in sources:
        stem = os.path.splitext(rel_path(source.path, base_dir))[0]
        stems[stem] = stems.get(stem, 0) + 1

    entries = []
    svg_files = []
    used = set()
    total_funcs = 0
    for source in sources:
        path = source.path
        rel = rel_path(path, base_dir)
        file_stem = os.path.splitext(rel)[0]
        if stems[file_stem] > 1:
            file_stem = rel.replace(".", "_")
        if source.errors:
            log(
                f"  ~ {rel}: разобран с {source.errors} ошибочн. участк. "
                f"(схемы строятся по распознанной части)"
            )
        infos = [
            i
            for i in project.outline(source)
            if match_name(i["name"], i["base"], args.only, args.exclude)
        ]
        made = 0
        if args.list_only:
            for info in infos:
                total_funcs += 1
                print(f"{rel}:{info['line']}: {info['name']}  —  {info['signature']}")
            continue
        try:
            charts = project.charts(source, opts, known, infos)
        except ValueError as error:
            print(f"  ! {rel}: {error}", file=sys.stderr)
            failed = True
            continue
        for chart in charts:
            info = chart.info
            total_funcs += 1
            from .model import Function

            short = opts.begin_label if info["main"] else info["short"]
            fn = Function(
                name=info["name"],
                signature=info["signature"],
                short=short,
                file=path,
                rel=rel,
                line=info["line"],
                lang=source.spec.name,
                body=chart.body,
            )
            try:
                frame, chart_opts = layout_for_report(fn, opts)
            except Exception as e:  # noqa: BLE001
                print(
                    f"  ! {rel}:{fn.line} {fn.name}: ошибка разметки — {e}",
                    file=sys.stderr,
                )
                failed = True
                continue
            title = None if opts.study else f"{fn.name} — {rel}"
            stem = safe_name(f"{file_stem.replace('/', '_')}__{fn.name}")
            uniq, k = stem, 2
            while uniq in used:
                uniq = f"{stem}_{k}"
                k += 1
            used.add(uniq)

            if opts.study and frame.width + 2 * MARGIN > opts.page_width:
                print(
                    f"  ! {rel}:{fn.line}: схема шире области отчёта; "
                    "сохранён естественный размер без уменьшения шрифта.",
                    file=sys.stderr,
                )
            model = frame_to_dict(frame, chart_opts)
            if not args.no_svg or args.png is not None:
                svg_path = os.path.join(out_dir, uniq + ".svg")
                with open(svg_path, "w", encoding="utf-8") as fh:
                    fh.write(
                        render_svg(
                            frame,
                            title=title,
                            standalone=True,
                            name=fn.name,
                            theme=args.theme,
                        )
                    )
                svg_files.append(svg_path)
            entries.append(
                {
                    "rel": rel,
                    "name": fn.name,
                    "signature": fn.signature,
                    "line": fn.line,
                    "anchor": safe_name(uniq).replace(" ", "_"),
                    "model": model,
                }
            )
            if opts.study and opts.page_height:
                page_opts = replace(
                    chart_opts,
                    page_height=opts.page_height
                    - 2 * MARGIN
                    - (TITLE_H if title else 0),
                )
                try:
                    pages = split_pages(frame, page_opts)
                except ValueError as error:
                    print(
                        f"  ! {rel}:{fn.line}: разбиение по страницам — {error}",
                        file=sys.stderr,
                    )
                    failed = True
                    pages = []
                if len(pages) > 1:
                    for number, page in enumerate(pages, 1):
                        page_stem = f"{uniq}__p{number:02d}"
                        page_name = f"{fn.name} · стр. {number}/{len(pages)}"
                        if not args.no_svg or args.png is not None:
                            page_path = os.path.join(out_dir, page_stem + ".svg")
                            with open(page_path, "w", encoding="utf-8") as stream:
                                stream.write(
                                    render_svg(
                                        page,
                                        title=None,
                                        name=page_name,
                                        theme=args.theme,
                                    )
                                )
                            svg_files.append(page_path)
                        entries.append(
                            {
                                "rel": rel,
                                "name": page_name,
                                "signature": fn.signature,
                                "line": fn.line,
                                "anchor": page_stem,
                                "model": frame_to_dict(page, chart_opts),
                            }
                        )
            made += 1
        log(f"  {rel}: функций — {made} [{source.spec.name}]")

    if args.list_only:
        print(f"\nВсего функций: {total_funcs}")
        return 0

    if not entries:
        print("Не найдено ни одной функции, подходящей под условия.", file=sys.stderr)
        return 1

    if args.png is not None:
        browser = None if shutil.which("rsvg-convert") else PNG.find_browser()
        if not browser and not shutil.which("rsvg-convert"):
            print(
                "  ! Для PNG нужен Chromium/Edge/Chrome или rsvg-convert.",
                file=sys.stderr,
            )
            failed = True
        else:
            ok = 0
            for svg_path in svg_files:
                png_path = os.path.splitext(svg_path)[0] + ".png"
                if PNG.convert(svg_path, png_path, scale=args.png, browser=browser):
                    ok += 1
                else:
                    print(f"  ! Не удалось создать PNG: {png_path}", file=sys.stderr)
                    failed = True
            log(f"  PNG ×{args.png:g}: {ok} из {len(svg_files)}")
            if args.no_svg:
                for svg_path in svg_files:
                    try:
                        os.remove(svg_path)
                    except OSError:
                        pass

    index = None
    if not args.no_html:
        index = os.path.join(out_dir, "index.html")
        folder = os.path.basename(base_dir) or base_dir
        head = "Flowcharts" if args.ui_lang == "en" else "Блок-схемы"
        with open(index, "w", encoding="utf-8") as fh:
            fh.write(
                render_html(
                    entries,
                    title=f"{head}: {folder}",
                    folder=folder,
                    lang=args.ui_lang,
                    theme=args.theme,
                )
            )

    log(f"\nГотово: {len(entries)} блок-схем -> {out_dir}")
    if index:
        log(f"Альбом схем: {index}")
        if args.open:
            open_in_browser(index)
    if from_ui:
        from . import tui

        tui.pause("Альбом открыт в браузере. Нажмите любую клавишу, чтобы закрыть…")
    return 1 if failed or missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
