"""Language descriptions: what a programming language looks like to blockwright.

Each language is a TOML file (blockwright/languages/*.toml) that names its
tree-sitter grammar and maps the grammar's node types onto flowchart
constructs. Adding a language is writing such a file; docs/languages.md
describes the format. Extra folders with descriptions come from --lang-dir
and the BLOCKWRIGHT_LANGS environment variable; a file there replaces a
built-in description of the same name.
"""

import importlib
import importlib.util
import os
import re

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib

BUILTIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "languages")
ENV_DIRS = "BLOCKWRIGHT_LANGS"

# statement kinds a description may use, with the keys each one accepts
KINDS = {
    "block": {"skip"},
    "skip": set(),
    "simple": set(),
    "expression": {"skip"},
    "if": {"condition", "then", "else", "elif", "init"},
    "while": {"condition", "body", "else"},
    "do": {"condition", "body", "until"},
    "for": {"init", "condition", "update", "body", "else"},
    "counting": {"var", "start", "end", "step", "descending", "body"},
    "foreach": {"var", "iterable", "body", "else", "range"},
    "switch": {
        "value",
        "body",
        "cases",
        "fallthrough",
        "default_labels",
        "default_after",
    },
    "break": set(),
    "continue": set(),
    "return": {"value"},
    "throw": {"value"},
    "goto": {"label"},
    "label": {"label"},
    "try": {"body", "handlers", "else", "finally", "catch_all"},
    "inline": {"body"},
    "hook": {"hook"},
}
COMMON_KEYS = {"kind", "when", "hook"}
CASE_KEYS = {"value", "labels", "body", "default", "fallthrough"}
HANDLER_KEYS = {"parameter", "body"}

# every key a description may have, by section; anything else is a typo
SECTIONS = {
    "": {
        "name",
        "title",
        "grammar",
        "package",
        "extensions",
        "priority",
        "markers",
        "retry",
        "case_sensitive",
        "separators",
        "statement_end",
        "assign",
        "strip",
        "skip",
        "skip_pattern",
        "empty",
        "conditions",
        "words",
        "functions",
        "program",
        "calls",
        "io",
        "strings",
        "hooks",
        "statements",
        "bundle",
        "extends",
    },
    "functions": {
        "nodes",
        "declarations",
        "requires",
        "name",
        "body",
        "parameters",
        "parameter_nodes",
        "ignore_parameters",
        "signature",
        "names",
        "scopes",
        "scope_separator",
        "entry",
        "ok_exit",
        "nested",
    },
    "program": {"node", "body", "name", "skip"},
    "calls": {"nodes", "callee", "callee_types"},
    "io": {
        "output",
        "input",
        "assign",
        "skip_args",
        "unwrap_args",
        "input_strip",
        "printf_conversions",
        "format_replace",
        "streams",
    },
    "io.streams": {
        "output",
        "input",
        "output_operator",
        "input_operator",
        "newline",
        "manipulators",
    },
    "strings": {
        "nodes",
        "concat",
        "concat_operator",
        "escape",
        "template",
        "format_operator",
        "format_tuples",
    },
}
OUTPUT_KEYS = {"format", "style", "weave", "sep", "args"}
INPUT_KEYS = {"args", "stream"}

DEFAULT_LABEL_STRIP = r"^\s*(?:case|default)\b\s*|\s*(?::|->)\s*$"


class SpecError(Exception):
    pass


def _check_keys(data, where):
    for section, allowed in SECTIONS.items():
        table = data
        for part in section.split(".") if section else []:
            table = table.get(part, {}) if isinstance(table, dict) else {}
        if not isinstance(table, dict):
            raise SpecError(f"{where}: [{section}] должен быть таблицей")
        bad = set(table) - allowed
        if bad:
            name = f"[{section}]" if section else "верхнем уровне"
            raise SpecError(
                f"{where}: неизвестные ключи в {name}: {', '.join(sorted(bad))}"
            )
    io = data.get("io", {})
    for kind, allowed in (("output", OUTPUT_KEYS), ("input", INPUT_KEYS)):
        for fn, opts in io.get(kind, {}).items():
            bad = set(opts) - allowed
            if bad:
                raise SpecError(
                    f'{where}: io.{kind}."{fn}": неизвестные ключи '
                    f"{', '.join(sorted(bad))}"
                )


def _as_list(v):
    if v is None:
        return []
    return list(v) if isinstance(v, list) else [v]


def parse_slice(text):
    """'1:' / ':1' / '2' -> slice."""
    if text is None or text == "" or text == ":":
        return slice(None)
    if isinstance(text, int):
        return slice(text, text + 1)
    a, _, b = str(text).partition(":")
    if not _:
        i = int(a)
        return slice(i, i + 1)
    return slice(int(a) if a else None, int(b) if b else None)


class Spec:
    """One loaded language description."""

    def __init__(self, data, path):
        self.path = path
        self.data = data
        where = os.path.basename(path)
        _check_keys(data, where)
        try:
            self.name = data["name"]
            grammar = data["grammar"]
        except KeyError as e:
            raise SpecError(f"{where}: нет обязательного ключа {e}") from None
        if isinstance(grammar, str):
            grammar = {"module": grammar}
        self.grammar_module = grammar["module"]
        self.grammar_function = grammar.get("function", "language")
        self.package = data.get("package", self.grammar_module.replace("_", "-"))
        self.title = data.get("title", self.name)
        self.bundle = data.get("bundle", True)
        self.extensions = [e.lower() for e in data.get("extensions", [])]
        self.priority = data.get("priority", 0)
        self.markers = data.get("markers", [])
        self.retry = data.get("retry", [])
        self.case_sensitive = data.get("case_sensitive", True)
        self.separators = data.get("separators", ["."])
        self.statement_end = data.get("statement_end", ";")
        self.assign = data.get("assign", "=")
        self.strip = [re.compile(p) for p in data.get("strip", [])]
        self.skip = set(data.get("skip", []))
        pat = data.get("skip_pattern")
        self.skip_pattern = re.compile(pat) if pat else None
        self.empty = set(data.get("empty", []))
        self.conditions = data.get("conditions", {})
        self.words = {
            self.fold(w): k for k, ws in data.get("words", {}).items() for w in ws
        }

        fn = data.get("functions", {})
        self.fn_nodes = set(fn.get("nodes", []))
        self.fn_declarations = set(fn.get("declarations", []))
        self.fn_requires = fn.get("requires")
        self.fn_name = fn.get("name", "name")
        self.fn_body = fn.get("body", "body")
        self.fn_parameters = fn.get("parameters", "parameters")
        self.fn_parameter_nodes = set(fn.get("parameter_nodes", []))
        self.fn_ignore_parameters = set(fn.get("ignore_parameters", []))
        self.fn_signature = fn.get("signature")
        self.name_types = set(fn.get("names", ["identifier"]))
        self.scopes = fn.get("scopes", [])
        self.scope_separator = fn.get("scope_separator", self.separators[0])
        self.entry = {self.fold(e) for e in fn.get("entry", ["main"])}
        self.ok_exit = set(fn.get("ok_exit", []))
        self.nested = fn.get("nested", False)

        prog = data.get("program")
        self.program = None
        if prog:
            self.program = {
                "node": prog["node"],
                "body": _as_list(prog.get("body")),
                "name": prog.get("name"),
                "skip": set(prog.get("skip", [])),
            }

        calls = data.get("calls", {})
        self.call_nodes = calls.get("nodes", {})
        self.callee = calls.get("callee")
        self.callee_types = set(calls.get("callee_types", []))

        io = data.get("io", {})
        self.io_output = {self.fold(k): v for k, v in io.get("output", {}).items()}
        self.io_input = {self.fold(k): v for k, v in io.get("input", {}).items()}
        self.io_assign = io.get("assign", {})
        self.io_skip_args = set(io.get("skip_args", []))
        self.io_unwrap_args = set(io.get("unwrap_args", []))
        strip = io.get("input_strip", [])
        self.io_input_strip = [strip] if isinstance(strip, str) else list(strip)
        self.io_conversions = io.get("printf_conversions", "diuoxXfFeEgGaAcspn")
        self.io_format_replace = io.get("format_replace", {})
        st = io.get("streams")
        self.streams = None
        if st:
            self.streams = {
                "output": set(st.get("output", [])),
                "input": set(st.get("input", [])),
                "output_operator": st.get("output_operator", "<<"),
                "input_operator": st.get("input_operator", ">>"),
                "newline": set(st.get("newline", [])),
                "manipulators": set(st.get("manipulators", [])),
            }

        strings = data.get("strings", {})
        self.string_nodes = set(strings.get("nodes", []))
        self.string_concat = set(strings.get("concat", []))
        self.concat_operator = strings.get("concat_operator")
        self.format_operator = strings.get("format_operator")
        self.format_tuples = set(strings.get("format_tuples", []))
        self.escape = strings.get("escape", "backslash")
        self.template = strings.get("template")

        self.hooks = {}
        hooks_file = data.get("hooks")
        if hooks_file:
            self.hooks = _load_hooks(os.path.join(os.path.dirname(path), hooks_file))

        self.rules = {}
        for node_type, raw in data.get("statements", {}).items():
            variants = raw if isinstance(raw, list) else [raw]
            self.rules[node_type] = [self._rule(node_type, v, where) for v in variants]

        self._language = None
        self._error = None

    # ------------------------------------------------------------- rules
    def _rule(self, node_type, raw, where):
        if isinstance(raw, str):
            raw = {"kind": raw}
        rule = dict(raw)
        kind = rule.get("kind")
        if "hook" in rule and kind is None:
            kind = rule["kind"] = "hook"
        if kind not in KINDS:
            raise SpecError(
                f"{where}: statements.{node_type}: неизвестный вид «{kind}»"
            )
        extra = set(rule) - KINDS[kind] - COMMON_KEYS
        if extra:
            raise SpecError(
                f"{where}: statements.{node_type}: лишние ключи "
                f"{', '.join(sorted(extra))} для вида «{kind}»"
            )
        if rule.get("hook") and rule["hook"] not in self.hooks:
            from . import hooks as builtin

            if not hasattr(builtin, rule["hook"]):
                raise SpecError(
                    f"{where}: statements.{node_type}: нет функции «{rule['hook']}»"
                )
        if kind == "switch":
            cases = {}
            for ct, co in rule.get("cases", {}).items():
                co = dict(co)
                bad = set(co) - CASE_KEYS
                if bad:
                    raise SpecError(
                        f"{where}: statements.{node_type}.cases.{ct}: "
                        f"лишние ключи {', '.join(sorted(bad))}"
                    )
                cases[ct] = co
            rule["cases"] = cases
            rule["label_strip"] = re.compile(DEFAULT_LABEL_STRIP)
        if kind == "try":
            handlers = rule.get("handlers", {})
            if isinstance(handlers, list):
                handlers = {h: {} for h in handlers}
            for ht, ho in handlers.items():
                bad = set(ho) - HANDLER_KEYS
                if bad:
                    raise SpecError(
                        f"{where}: statements.{node_type}.handlers.{ht}: "
                        f"лишние ключи {', '.join(sorted(bad))}"
                    )
            rule["handlers"] = handlers
        for key in ("else", "finally", "catch_all"):
            if kind == "try" and isinstance(rule.get(key), str):
                rule[key] = [rule[key]]
        return rule

    def rule(self, node):
        variants = self.rules.get(node.type)
        if not variants:
            return None
        for r in variants:
            when = r.get("when")
            if when is None or find(node, when, self) is not None:
                return r
        return None

    # ----------------------------------------------------------- helpers
    def fold(self, s):
        return s if self.case_sensitive else s.casefold()

    def skipped(self, node):
        t = node.type
        if t in self.skip or node.is_extra:
            return True
        return bool(self.skip_pattern and self.skip_pattern.search(t))

    def named(self, node):
        return [c for c in node.named_children if not self.skipped(c)]

    def last_segment(self, name):
        for sep in self.separators:
            name = name.split(sep)[-1]
        return name.strip()

    # ----------------------------------------------------------- grammar
    def language(self):
        """The tree-sitter Language, or None when the grammar is not installed."""
        if self._language is None and self._error is None:
            try:
                from tree_sitter import Language

                mod = importlib.import_module(self.grammar_module)
                self._language = Language(getattr(mod, self.grammar_function)())
            except Exception as e:  # noqa: BLE001
                self._error = e
        return self._language

    @property
    def available(self):
        return self.language() is not None

    def install_hint(self):
        return f"pip install {self.package}"


def _load_hooks(path):
    if not os.path.isfile(path):
        raise SpecError(f"не найден файл функций {path}")
    name = "blockwright_hooks_" + re.sub(
        r"\W", "_", os.path.splitext(os.path.basename(path))[0]
    )
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {k: v for k, v in vars(mod).items() if callable(v) and not k.startswith("_")}


# ------------------------------------------------------------- node paths
def _step(nodes, seg, spec):
    out = []
    for node in nodes:
        if seg.startswith("#"):
            idx = int(seg[1:])
            free = [
                c
                for i, c in enumerate(node.children)
                if c.is_named
                and not node.field_name_for_child(i)
                and not (spec and spec.skipped(c))
            ]
            if idx < len(free):
                out.append(free[idx])
            continue
        hits = [c for c in node.children_by_field_name(seg) if c.is_named]
        if not hits:
            hits = [c for c in node.named_children if c.type == seg]
        out.extend(hits)
    return out


def find_all(node, path, spec=None):
    """Nodes at a path such as `body`, `for_clause.initializer` or `#0`.

    Each dot-separated step is a field name, else a child node type, else
    `#N` — the N-th named child that has no field name.
    """
    if node is None or not path:
        return []
    nodes = [node]
    segs = path.split(".")
    for i, seg in enumerate(segs):
        nodes = _step(nodes, seg, spec)
        if not nodes:
            return []
        if i < len(segs) - 1:
            nodes = nodes[:1]
    return nodes


def find(node, path, spec=None):
    hits = find_all(node, path, spec)
    return hits[0] if hits else None


# --------------------------------------------------------------- registry
def merge(base, over):
    """`extends`: tables merge key by key, anything else is replaced."""
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


class Registry:
    def __init__(self, dirs=()):
        self.raw = {}
        self.specs = {}
        self.errors = []
        for d in [BUILTIN_DIR, *_env_dirs(), *dirs]:
            self.load_dir(d)

    def load_dir(self, folder):
        if not os.path.isdir(folder):
            self.errors.append(f"нет папки с описаниями языков: {folder}")
            return
        names = sorted(nm for nm in os.listdir(folder) if nm.endswith(".toml"))
        loaded = []
        for nm in names:
            path = os.path.join(folder, nm)
            try:
                with open(path, "rb") as fh:
                    data = tomllib.load(fh)
            except (OSError, tomllib.TOMLDecodeError) as e:
                self.errors.append(f"{nm}: {e}")
                continue
            if "hooks" in data:
                data["hooks"] = os.path.abspath(os.path.join(folder, data["hooks"]))
            name = data.get("name") or os.path.splitext(nm)[0]
            data["name"] = name
            self.raw[name] = (data, path)
            loaded.append(name)
        for name in loaded:
            self._build(name)

    def _resolve(self, name, seen=()):
        data, _path = self.raw[name]
        base = data.get("extends")
        if not base:
            return data
        if base not in self.raw:
            raise SpecError(f'extends = "{base}": нет такого языка')
        if base in seen:
            raise SpecError("цикл в extends")
        merged = merge(self._resolve(base, seen + (name,)), data)
        merged.pop("extends", None)
        return merged

    def _build(self, name):
        _data, path = self.raw[name]
        try:
            spec = Spec(self._resolve(name), path)
        except (SpecError, KeyError, TypeError, ValueError, re.error) as e:
            msg = str(e)
            self.errors.append(
                msg
                if msg.startswith(os.path.basename(path))
                else f"{os.path.basename(path)}: {msg}"
            )
            self.specs.pop(name, None)
            return None
        self.specs[name] = spec
        # descriptions built on this one see the change too
        for other, (odata, _) in self.raw.items():
            if odata.get("extends") == name and other in self.specs:
                self._build(other)
        return spec

    def get(self, name):
        return self.specs.get(name)

    def names(self):
        return sorted(self.specs)

    def extensions(self, only=None):
        return {e for s in self.select(only) for e in s.extensions}

    def select(self, only=None):
        return [s for n, s in sorted(self.specs.items()) if not only or n in only]

    def guess(self, path, text, only=None):
        """The description that fits a file best, or None."""
        ext = os.path.splitext(path)[1].lower()
        pool = self.select(only)
        cands = [s for s in pool if ext in s.extensions]
        if not cands and only:
            cands = pool
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0]

        def score(s):
            return (sum(1 for m in s.markers if m in text), s.priority)

        return max(cands, key=score)


def _env_dirs():
    raw = os.environ.get(ENV_DIRS, "")
    return [p for p in raw.split(os.pathsep) if p]


_DEFAULT = None


def registry(dirs=()):
    """The shared registry; extra dirs replace it with a fresh one."""
    global _DEFAULT
    if dirs or _DEFAULT is None:
        _DEFAULT = Registry(dirs)
    return _DEFAULT
