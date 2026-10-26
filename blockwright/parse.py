"""Finding sources, choosing a grammar and extracting functions.

Everything language-specific comes from the language description (a Spec);
see blockwright/langs.py.
"""

import os
import re

from tree_sitter import Parser

from .langs import find, find_all, registry
from .text import normalize

SKIP_DIRS = {
    ".git",
    ".svn",
    "node_modules",
    "build",
    "cmake-build-debug",
    "cmake-build-release",
    "Debug",
    "Release",
    ".vs",
    ".idea",
    "x64",
    "x86",
    "__pycache__",
    "venv",
    ".venv",
    "vendor",
    "third_party",
    "external",
    "site-packages",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".gradle",
    "target",
    "obj",
    "dist",
}


def extensions(only=None):
    return registry().extensions(only)


def discover(paths, recursive=True, only=None):
    exts = extensions(only)
    files = []
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isfile(p):
            files.append(p)
        elif os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for nm in sorted(names):
                    if os.path.splitext(nm)[1].lower() in exts:
                        files.append(os.path.join(root, nm))
                if not recursive:
                    dirs[:] = []
    seen, out = set(), []
    for f in files:
        k = os.path.normcase(f)
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def count_errors(node):
    total = 0
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type == "ERROR" or n.is_missing:
            total += 1
        stack.extend(n.children)
    return total


def guess_language(path, src_text, only=None):
    """The language description for a file, or None."""
    return registry().guess(path, src_text, only)


def parse_source(src: bytes, spec):
    """Parse with the language's grammar; on syntax errors try its `retry` ones.

    Returns (tree, spec, errors); tree is None if no grammar is installed.
    """
    reg = registry()
    order = [spec] + [reg.get(n) for n in spec.retry if reg.get(n)]
    best = None
    for s in order:
        lang = s.language()
        if lang is None:
            continue
        tree = Parser(lang).parse(src)
        errs = count_errors(tree.root_node)
        if errs == 0:
            return tree, s, 0
        if best is None or errs < best[2]:
            best = (tree, s, errs)
    return best or (None, spec, 0)


def _text(src, node):
    if node is None:
        return ""
    return src[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _chain(node, depth=12):
    """The node and its `declarator` descendants: C declarators nest."""
    out = []
    cur = node
    while cur is not None and len(out) < depth:
        out.append(cur)
        cur = cur.child_by_field_name("declarator")
    return out


def _innermost_name(src, node, spec):
    for cur in _chain(node):
        if cur.type in spec.name_types:
            return _text(src, cur).strip()
        if cur.child_by_field_name("declarator") is None:
            for c in cur.named_children:
                if c.type in spec.name_types:
                    return _text(src, c).strip()
            return ""
    return ""


def _required(node, spec):
    """The node on the declarator chain that marks a function (C), or the node."""
    if not spec.fn_requires:
        return node
    for cur in _chain(node)[1:]:
        if cur.type == spec.fn_requires:
            return cur
    return None


def function_name(src, node, spec):
    hit = find(node, spec.fn_name, spec) if spec.fn_name else None
    if hit is not None and hit.type in spec.name_types:
        return _text(src, hit).strip()
    head = _required(node, spec)
    return _innermost_name(src, head, spec) if head is not None else ""


def _scope_prefix(src, node, spec):
    parts = []
    cur = node.parent
    while cur is not None:
        if cur.type in spec.scopes:
            nm = _text(src, cur.child_by_field_name("name")).strip()
            if nm:
                parts.append(nm)
        cur = cur.parent
    return spec.scope_separator.join(reversed(parts))


def _param_names(src, p, spec):
    if p.type in spec.name_types:
        return [_text(src, p).strip()]
    named = [c for c in p.children_by_field_name("name") if c.is_named]
    if named:
        return [_text(src, c).strip() for c in named]
    nm = _innermost_name(src, p, spec)
    return [nm or normalize(_text(src, p))]


def _params(src, node, spec):
    plist = None
    head = _required(node, spec)
    for cur in _chain(head) if head is not None else []:
        plist = find(cur, spec.fn_parameters, spec)
        if plist is not None:
            break
    if plist is None:
        return []
    out = []
    for p in spec.named(plist):
        if spec.fn_parameter_nodes and p.type not in spec.fn_parameter_nodes:
            continue
        out.extend(_param_names(src, p, spec))
    return [x for x in out if x and x not in spec.fn_ignore_parameters]


def collect_functions(src, root, spec):
    """Function nodes with a body; nested ones only if the language wants them."""
    out = []

    def rec(node, inside):
        if node.type in spec.fn_nodes:
            if (not inside or spec.nested) and find(
                node, spec.fn_body, spec
            ) is not None:
                out.append(node)
            inside = True
        for c in node.named_children:
            rec(c, inside)

    rec(root, False)
    return out


def _signature(src, node, body, spec):
    if spec.fn_signature:
        head = find(node, spec.fn_signature, spec)
        raw = _text(src, head)
    else:
        raw = src[node.start_byte : body.start_byte].decode("utf-8", "replace")
    return re.sub(r"\s*(?:=>|[:;{])\s*$", "", normalize(raw))


def describe_function(src, node, spec):
    body = find(node, spec.fn_body, spec)
    name = function_name(src, node, spec) or "<аноним>"
    scope = _scope_prefix(src, node, spec)
    full = f"{scope}{spec.scope_separator}{name}" if scope else name
    params = _params(src, node, spec)
    base = name
    for sep in spec.separators:
        base = base.split(sep)[-1]
    is_main = spec.fold(base) in spec.entry
    short = "Начало" if is_main else f"{full}({', '.join(params)})"
    return {
        "name": full,
        "base": base,
        "signature": _signature(src, node, body, spec),
        "short": short,
        "line": node.start_point[0] + 1,
        "body": body,
        "main": is_main,
    }


def describe_program(src, root, spec, path):
    """Code outside functions (a Python script, a Pascal program) as a chart."""
    prog = spec.program
    if not prog:
        return None
    node = root if root.type == prog["node"] else find(root, prog["node"], spec)
    if node is None:
        return None
    holder = node
    if prog["body"]:
        holder = next(
            (h for h in (find(node, b, spec) for b in prog["body"]) if h is not None),
            None,
        )
    if holder is None:
        return None
    stmts = [
        c
        for c in spec.named(holder)
        if c.type not in prog["skip"] and c.type not in spec.fn_nodes
    ]
    if not stmts:
        return None
    name = ""
    if prog["name"]:
        name = normalize(_text(src, find(node, prog["name"], spec)))
    if not name:
        name = os.path.splitext(os.path.basename(path))[0]
    return {
        "name": name,
        "base": name,
        "signature": name,
        "short": "Начало",
        "line": stmts[0].start_point[0] + 1,
        "body": stmts,
        "main": True,
        "program": True,
    }


def collect_known_names(src, root, spec):
    """Names of functions defined or declared in the file."""
    names = set()
    kinds = spec.fn_nodes | spec.fn_declarations
    stack = [root]
    while stack:
        n = stack.pop()
        if n.type in kinds and (
            n.type in spec.fn_nodes or _required(n, spec) is not None
        ):
            nm = function_name(src, n, spec)
            if nm:
                for sep in spec.separators:
                    nm = nm.split(sep)[-1]
                names.add(spec.fold(nm))
        stack.extend(n.named_children)
    return names


__all__ = [
    "SKIP_DIRS",
    "collect_functions",
    "collect_known_names",
    "count_errors",
    "describe_function",
    "describe_program",
    "discover",
    "extensions",
    "find_all",
    "guess_language",
    "parse_source",
]
