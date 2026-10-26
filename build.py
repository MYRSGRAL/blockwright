#!/usr/bin/env python
"""Build blockwright into a single executable with PyInstaller.

    python build.py            build for the current OS
    python build.py --clean    remove build leftovers

Produces `dist/blockwright.exe` on Windows and `dist/blockwright` on Linux,
with Python, the parsers and the editor libraries inside. Build on the target
OS (WSL works for Linux).
"""

import argparse
import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# a cp1252/cp866 Windows console would crash on non-ASCII output
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from blockwright.vendored import paths as vendor_paths
from blockwright.vendored import platform_tag

NAME = "blockwright"


def have_pyinstaller():
    try:
        import PyInstaller  # noqa: F401

        return True
    except ImportError:
        return False


def grammar_modules():
    """Grammar modules named by the built-in language descriptions."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    folder = os.path.join(BASE, "blockwright", "languages")
    out = []
    for nm in sorted(os.listdir(folder)):
        if nm.endswith(".toml"):
            with open(os.path.join(folder, nm), "rb") as fh:
                data = tomllib.load(fh)
            g = data.get("grammar")
            # bundle = false: installed by the user, never packed into the binary
            if g and data.get("bundle", True) is not False:
                out.append(g if isinstance(g, str) else g["module"])
    return out


def sweep(name):
    for junk in ("build", f"{name}.spec"):
        p = os.path.join(BASE, junk)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)


def main():
    ap = argparse.ArgumentParser(description="Сборка blockwright в один файл")
    ap.add_argument("--clean", action="store_true", help="только убрать мусор сборки")
    ap.add_argument("--name", default=NAME, help="имя исполняемого файла")
    args = ap.parse_args()

    sweep(args.name)
    if args.clean:
        print("Временные файлы сборки удалены.")
        return 0

    if not have_pyinstaller():
        print(
            "Нужен PyInstaller. Установите его командой:\n"
            f"    {os.path.basename(sys.executable)} -m pip install pyinstaller\n",
            file=sys.stderr,
        )
        return 2

    vendor = vendor_paths(BASE)
    if not vendor:
        print(
            f"Нет парсеров для {platform_tag()} / Python "
            f"{sys.version_info.major}.{sys.version_info.minor} в папке vendor — "
            "будут взяты установленные в систему.",
            file=sys.stderr,
        )

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",
        "--name",
        args.name,
        "--noconfirm",
        "--clean",
        "--distpath",
        os.path.join(BASE, "dist"),
        "--workpath",
        os.path.join(BASE, "build"),
        "--specpath",
        BASE,
    ]
    for p in vendor:
        cmd += ["--paths", p]
    # grammars are imported by name from the language descriptions
    for mod in ("tree_sitter", *grammar_modules()):
        cmd += ["--hidden-import", mod, "--collect-binaries", mod]
    cmd += ["--copy-metadata", "Pillow"]
    langs = os.path.join(BASE, "blockwright", "languages")
    cmd += [
        "--add-data",
        f"{langs}{os.pathsep}{os.path.join('blockwright', 'languages')}",
    ]
    for mod in (
        "blockwright.tui",
        "blockwright.album",
        "blockwright.png",
        "PIL.ImageFont",
    ):
        cmd += ["--hidden-import", mod]
    # the editor's connector router, inlined into index.html
    web = os.path.join(BASE, "vendor", "web")
    if os.path.isdir(web):
        cmd += ["--add-data", f"{web}{os.pathsep}{os.path.join('vendor', 'web')}"]
    else:
        print(
            "Нет vendor/web — редактор будет прокладывать линии упрощённо.",
            file=sys.stderr,
        )
    cmd += ["--paths", BASE, "--hidden-import", "blockwright"]
    cmd.append(os.path.join(BASE, "tools", "entry.py"))

    print(f"Собираю {args.name} для {platform_tag()} …\n")
    rc = subprocess.call(cmd, cwd=BASE)
    if rc != 0:
        print("\nСборка не удалась.", file=sys.stderr)
        return rc

    exe = os.path.join(BASE, "dist", args.name + (".exe" if os.name == "nt" else ""))
    if os.path.isfile(exe):
        print(f"\nГотово: {exe}  ({os.path.getsize(exe) / 1024 / 1024:.1f} МБ)")
        print("Файл можно скопировать куда угодно и запускать без Python.")
    sweep(args.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
