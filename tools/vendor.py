#!/usr/bin/env python
"""Rebuild vendor/: tree-sitter parsers and the editor libraries.

    python tools/vendor.py                       Windows x64 + Linux x86-64 + web
    python tools/vendor.py --only linux_aarch64  a single platform
    python tools/vendor.py --web                 browser libraries only
    python tools/vendor.py --grammars            add missing grammars only,
                                                 leaving everything else as is

Wheels come from PyPI and are unpacked into vendor/<platform>/<cpXY>; the
grammars (abi3, one build for every Python) go to vendor/<platform>/common.
Which grammars to bundle is read from blockwright/languages/*.toml.
libavoid-js comes from npm into vendor/web, shared by all platforms; Node.js
is not needed. Needs network access.
"""

import argparse
import base64
import glob
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# a cp1252/cp866 Windows console would garble non-ASCII output
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PYTHONS = ["3.12", "3.13", "3.14"]
# Only the two common platforms are bundled to keep vendor/ small; ARM users
# take a release binary or install the parsers with pip.
TARGETS = {
    "win_amd64": "win_amd64",
    "linux_x86_64": "manylinux2014_x86_64",
}
OPTIONAL = {
    "linux_aarch64": "manylinux2014_aarch64",
    "macos_arm64": "macosx_11_0_arm64",
    "macos_x86_64": "macosx_10_9_x86_64",
}
LANG_DIR = os.path.join(ROOT, "blockwright", "languages")


def grammars():
    """{module: pip package} for every built-in language description."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    out = {}
    for nm in sorted(os.listdir(LANG_DIR)):
        if not nm.endswith(".toml"):
            continue
        with open(os.path.join(LANG_DIR, nm), "rb") as fh:
            data = tomllib.load(fh)
        g = data.get("grammar")
        # bundle = false: a grammar whose license does not allow shipping it here
        if not g or data.get("bundle", True) is False:
            continue
        module = g if isinstance(g, str) else g["module"]
        out[module] = data.get("package", module.replace("_", "-"))
    return out


def download(pkgs, dest, py, platform_tag):
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        *pkgs,
        "-d",
        dest,
        "--only-binary=:all:",
        "--python-version",
        py,
        "--platform",
        platform_tag,
        "-q",
    ]
    return subprocess.call(cmd) == 0


def extract(whl, dest, keep):
    with zipfile.ZipFile(whl) as z:
        for name in z.namelist():
            top = name.split("/")[0]
            if top.endswith((".dist-info", ".data")) or top not in keep:
                continue
            z.extract(name, dest)


def add_grammars(out, pip_tag, missing_only=False):
    """Unpack the grammars into <out>/common, replacing older copies."""
    gram = grammars()
    if missing_only:
        gram = {
            m: p
            for m, p in gram.items()
            if not os.path.isdir(os.path.join(out, "common", m))
        }
    with tempfile.TemporaryDirectory() as tmp:
        if gram and not download(sorted(set(gram.values())), tmp, PYTHONS[0], pip_tag):
            print("  ! не все грамматики скачались", file=sys.stderr)
        for module in gram:
            found = sorted(glob.glob(os.path.join(tmp, module + "-*.whl")))
            if not found:
                print(f"  ! нет колеса {module}", file=sys.stderr)
                continue
            dest = os.path.join(out, "common", module)
            if os.path.isdir(dest):
                shutil.rmtree(dest)
            extract(found[-1], os.path.join(out, "common"), {module})
        # Python 3.10 has no tomllib: the language descriptions need tomli
        if download(["tomli"], tmp, "3.10", pip_tag):
            for whl in glob.glob(os.path.join(tmp, "tomli-*.whl")):
                dest = os.path.join(out, "cp310")
                if os.path.isdir(os.path.join(dest, "tomli")):
                    shutil.rmtree(os.path.join(dest, "tomli"))
                extract(whl, dest, {"tomli"})


def build(platform_name, pip_tag, grammars_only=False):
    out = os.path.join(ROOT, "vendor", platform_name)
    if grammars_only:
        add_grammars(out, pip_tag, missing_only=True)
    else:
        if os.path.isdir(out):
            shutil.rmtree(out)
        os.makedirs(os.path.join(out, "common"), exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            for py in PYTHONS:
                if not download(["tree_sitter"], tmp, py, pip_tag):
                    print(f"  ! не удалось скачать для Python {py}", file=sys.stderr)
            for whl in glob.glob(os.path.join(tmp, "tree_sitter-*.whl")):
                tag = os.path.basename(whl).split("-")[2]
                if tag.startswith("cp"):
                    extract(whl, os.path.join(out, tag), {"tree_sitter"})
        add_grammars(out, pip_tag)
    size = sum(
        os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(out) for f in fs
    )
    print(f"{platform_name}: {sorted(os.listdir(out))}  ({size / 1024 / 1024:.1f} МБ)")


# -------------------------------------------------------------------- web
# libavoid (Adaptagrams): orthogonal connector routing around obstacles, as
# used by Inkscape and Dunnart; libavoid-js is its WebAssembly build.
AVOID_VERSION = "0.5.0-beta.5"
AVOID_URL = f"https://registry.npmjs.org/libavoid-js/-/libavoid-js-{AVOID_VERSION}.tgz"
AVOID_SHA512 = (
    "jHkn6A10815TgFhZ1paUD/NDnQkg4C66qJc2Juj1NpmO/"
    "+QXnJ4UjIdKQarkXLmI/QgXhEO3RWDxMi3i+uHPwA=="
)
AVOID_README = """\
# libavoid-js {version}

Orthogonal connector routing for the chart editor (index.html).

* Source: https://github.com/Aksem/libavoid-js, a WebAssembly port of libavoid
  from Adaptagrams (https://github.com/mjwybrow/adaptagrams).
* License: LGPL-2.1-or-later, see LICENSE next to this file.
* libavoid.wasm is unmodified from the npm package libavoid-js@{version}.
* libavoid.js is dist/index.js of the same package turned from an ES module
  into a classic script: `import.meta.url` is replaced and a global
  `AvoidModule` factory is exposed instead of `export`, because modules do not
  load from a page opened as file://.

Rebuild with `python tools/vendor.py --web`.
"""


def _classic_script(js):
    js = js.replace("import.meta.url", '(typeof document<"u"&&document.baseURI||"")')
    js = re.sub(r"\n?//# sourceMappingURL=\S*\s*$", "", js)
    # the module ends with: var W=Wrap(Factory);export{W as AvoidLib};
    tail = re.search(
        r"var (\w+)=\w+\((\w+)\);export\s*\{\s*\1 as AvoidLib\s*\};?\s*$", js
    )
    if not tail:
        raise SystemExit("libavoid-js: не узнаю конец модуля — формат пакета сменился")
    js = js[: tail.start()] + f"return {tail.group(2)};"
    if re.search(r"\bimport\.meta\b|\bexport\s*\{", js):
        raise SystemExit("libavoid-js: в модуле остались import/export")
    return (
        f"/* libavoid-js {AVOID_VERSION} (LGPL-2.1-or-later), "
        "https://github.com/Aksem/libavoid-js */\n"
        f"var AvoidModule=(function(){{{js}\n}})();\n"
    )


def build_web():
    out = os.path.join(ROOT, "vendor", "web", "libavoid")
    print(f"Скачиваю libavoid-js {AVOID_VERSION} …")
    with urllib.request.urlopen(AVOID_URL, timeout=60) as resp:
        blob = resp.read()
    digest = base64.b64encode(hashlib.sha512(blob).digest()).decode()
    if digest != AVOID_SHA512:
        raise SystemExit("libavoid-js: контрольная сумма не совпала")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        read = lambda name: tar.extractfile(f"package/{name}").read()
        js, wasm, lic = (
            read("dist/index.js"),
            read("dist/libavoid.wasm"),
            read("LICENSE"),
        )
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    with open(
        os.path.join(out, "libavoid.js"), "w", encoding="utf-8", newline="\n"
    ) as fh:
        fh.write(_classic_script(js.decode("utf-8")))
    with open(os.path.join(out, "libavoid.wasm"), "wb") as fh:
        fh.write(wasm)
    with open(os.path.join(out, "LICENSE"), "wb") as fh:
        fh.write(lic)
    with open(
        os.path.join(out, "README.md"), "w", encoding="utf-8", newline="\n"
    ) as fh:
        fh.write(AVOID_README.format(version=AVOID_VERSION))
    size = sum(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out))
    print(f"web: {sorted(os.listdir(out))}  ({size / 1024:.0f} КБ)")


def main():
    ap = argparse.ArgumentParser(description="Пересборка папки vendor")
    ap.add_argument(
        "--only",
        choices=sorted({**TARGETS, **OPTIONAL}),
        help="только одна платформа (в том числе необязательная)",
    )
    ap.add_argument(
        "--web", action="store_true", help="только библиотеки редактора (libavoid-js)"
    )
    ap.add_argument(
        "--grammars",
        action="store_true",
        help="только добавить недостающие грамматики языков (и tomli "
        "для Python 3.10), не трогая уже скачанное",
    )
    args = ap.parse_args()
    if args.web:
        build_web()
        return 0
    if not args.only and not args.grammars:
        build_web()
    targets = dict(TARGETS)
    if args.only and args.only in OPTIONAL:
        targets = {args.only: OPTIONAL[args.only]}
    for name, tag in targets.items():
        if args.only and args.only != name:
            continue
        print(f"Собираю {name} …")
        build(name, tag, grammars_only=args.grammars)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
