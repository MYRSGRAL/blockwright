"""Flowchart IR snapshots for every fixture folder in tests/fixtures.

python -m unittest discover tests                  check
BLOCKWRIGHT_UPDATE=1 python -m unittest discover tests   rewrite snapshots
"""

import dataclasses
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from blockwright import vendored

vendored.activate()

from blockwright import (
    langs,
    project,
)
from blockwright import parse as P
from blockwright.cli import CHART_WORDS, Opts

FIXTURES = os.path.join(HERE, "fixtures")
SNAPSHOTS = os.path.join(HERE, "snapshots")
UPDATE = bool(os.environ.get("BLOCKWRIGHT_UPDATE"))

VARIANTS = {
    "default": {},
    "list": {"io_style": "list", "for_style": "decision", "return_style": "value"},
    "code": {
        "io_style": "code",
        "for_style": "hexagon",
        "return_style": "end",
        "keep_std": True,
        "lang": "en",
    },
}


def make_opts(**kw):
    kw = {"study": False, "for_style": "auto", **kw}
    words = CHART_WORDS[kw.get("lang", "ru")]
    return Opts(
        yes_label=words["yes"],
        no_label=words["no"],
        begin_label=words["begin"],
        end_label=words["end"],
        default_label=words["default"],
        **kw,
    )


def ir(obj):
    if dataclasses.is_dataclass(obj):
        out = {"type": type(obj).__name__}
        for f in dataclasses.fields(obj):
            out[f.name] = ir(getattr(obj, f.name))
        return out
    if isinstance(obj, list):
        return [ir(x) for x in obj]
    return obj


def analyze(folder, opts):
    sources, known = [], set()
    for path in P.discover([folder]):
        src = project.load(path)
        if src.tree is None:
            continue  # grammar not installed (Pascal)
        known |= src.known
        sources.append(src)
    result = {}
    for src in sources:
        funcs = []
        for ch in project.charts(src, opts, known):
            info = ch.info
            funcs.append(
                {
                    "name": info["name"],
                    "signature": info["signature"],
                    "short": info["short"],
                    "line": info["line"],
                    "body": ir(ch.body),
                }
            )
        rel = os.path.relpath(src.path, folder).replace("\\", "/")
        result[rel] = {"lang": src.spec.name, "errors": src.errors, "functions": funcs}
    return result


class Snapshots(unittest.TestCase):
    maxDiff = None


def _available(lang):
    spec = langs.registry().get(lang)
    return spec is not None and spec.available


def _make_test(folder, path):
    def test(self):
        got = {name: analyze(path, make_opts(**kw)) for name, kw in VARIANTS.items()}
        snap = os.path.join(SNAPSHOTS, folder + ".json")
        want = {}
        if os.path.exists(snap):
            with open(snap, encoding="utf-8") as fh:
                want = json.load(fh)
        want = {
            name: {rel: data for rel, data in files.items() if data["lang"] == "cpp"}
            for name, files in want.items()
        }
        # files of a language whose grammar is missing here are kept as they are
        for name, files in want.items():
            for rel, data in files.items():
                if not _available(data["lang"]):
                    got.setdefault(name, {})[rel] = data
        if not got.get("default"):
            self.skipTest("no grammar installed for " + folder)
        text = json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        if UPDATE or not want:
            os.makedirs(SNAPSHOTS, exist_ok=True)
            with open(snap, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            return
        self.assertEqual(want, json.loads(text))

    return test


for _folder in sorted(os.listdir(FIXTURES)):
    if _folder == "cpp" and os.path.isdir(os.path.join(FIXTURES, _folder)):
        setattr(
            Snapshots,
            "test_" + _folder,
            _make_test(_folder, os.path.join(FIXTURES, _folder)),
        )
Snapshots.test_examples = _make_test("examples", os.path.join(ROOT, "examples"))


if __name__ == "__main__":
    unittest.main()
