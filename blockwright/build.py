"""Building the flowchart IR from a tree-sitter syntax tree.

The builder knows flowchart constructs, not languages: which node types are
loops, branches or I/O calls comes from the language description (a Spec,
see blockwright/langs.py). Statement kinds map to the k_<kind> methods below.
"""

import re

from . import model as M
from .langs import find, find_all, parse_slice
from .text import normalize

# escape sequence -> what appears on screen
_ESCAPES = {
    "n": " ",
    "t": " ",
    "r": "",
    "0": "",
    "a": "",
    "b": "",
    "f": " ",
    "v": " ",
    "\\": "\\",
    '"': '"',
    "'": "'",
    "?": "?",
}

_INT_RE = re.compile(r"^[+-]?\d+$")
_VAR_RE = re.compile(r"[^\W\d]\w*")
_COMPOSITE_RE = re.compile(r"\{(\d+)(?:[,:][^}]*)?\}")

# words printed inside blocks
CHART_L10N = {
    "ru": {
        "out": "Вывод: ",
        "out_plain": "Вывод",
        "in": "Ввод: ",
        "in_plain": "Ввод",
        "newline": "Перевод строки",
        "return": "Возврат {0}",
        "return_bare": "Возврат",
        "exception": "Исключение: {0}",
        "exception_bare": "Исключение",
        "caught": "Возникло исключение {0}",
        "caught_bare": "Возникло исключение",
        "foreach": "для каждого {0} из {1}",
        "more": "есть ещё элементы {0}?",
        "true": "истина",
        "condition": "условие",
        "default": "иначе",
        "no_break": "цикл завершён без break?",
    },
    "en": {
        "out": "Output: ",
        "out_plain": "Output",
        "in": "Input: ",
        "in_plain": "Input",
        "newline": "New line",
        "return": "Return {0}",
        "return_bare": "Return",
        "exception": "Exception: {0}",
        "exception_bare": "Exception",
        "caught": "Exception caught {0}",
        "caught_bare": "Exception caught",
        "foreach": "for each {0} in {1}",
        "more": "more elements in {0}?",
        "true": "true",
        "condition": "condition",
        "default": "else",
        "no_break": "loop ended without break?",
    },
}


def label(lang, key, *args):
    text = CHART_L10N.get(lang, CHART_L10N["ru"]).get(key, key)
    for i, value in enumerate(args):
        text = text.replace("{" + str(i) + "}", str(value))
    return text


def unescape(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(_ESCAPES.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _shift(t, delta):
    """`t + delta` for a loop bound: `n + 1` - 1 is `n`, `n - 1` - 1 is `n - 2`."""
    t = t.strip()
    if _INT_RE.match(t):
        return str(int(t) + delta)
    base, offset = t, 0
    m = re.fullmatch(r"(.+?)\s*([+-])\s*(\d+)", t)
    if m and not m.group(1).rstrip().endswith(("*", "/", "%", "(", "[", ",")):
        base, offset = m.group(1), int(m.group(3)) * (1 if m.group(2) == "+" else -1)
    offset += delta
    if offset == 0:
        return base
    return f"{base} + {offset}" if offset > 0 else f"{base} - {-offset}"


def _minus_one(t):
    return _shift(t, -1)


def _plus_one(t):
    return _shift(t, 1)


def strip_parens(s):
    s = s.strip()
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        ok = True
        for i, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(s) - 1:
                    ok = False
                    break
        if not ok:
            break
        s = s[1:-1].strip()
    return s


class Builder:
    """Turns a function body into flowchart IR."""

    def __init__(self, src: bytes, opts, known_funcs=frozenset(), spec=None):
        if spec is None:
            from .langs import registry

            spec = registry().get("cpp")
        self.src = src
        self.opts = opts
        self.spec = spec
        self.known = known_funcs
        self.fn_is_main = False
        self.lang = getattr(opts, "lang", "ru")
        # printf/scanf conversion specifiers
        self._spec_re = re.compile(
            r"%(?:%|[-+ #0']*\*?\d*(?:\.\*?\d+)?(?:hh|h|ll|l|L|q|z|j|t)?"
            "[" + re.escape(spec.io_conversions) + "])"
        )

    # ------------------------------------------------------------ basics
    def L(self, key, *args):
        return label(self.lang, key, *args)

    def raw(self, node):
        if node is None:
            return ""
        return (
            self.src[node.start_byte : node.end_byte].decode("utf-8", "replace").strip()
        )

    def t(self, node):
        if node is None:
            return ""
        s = normalize(
            self.src[node.start_byte : node.end_byte].decode("utf-8", "replace")
        )
        if not self.opts.keep_std:
            for rx in self.spec.strip:
                s = rx.sub("", s)
        return s

    def strip_all(self, s):
        for rx in self.spec.strip:
            s = rx.sub("", s)
        return s

    def find(self, node, path):
        if node is None or not path:
            return None
        hit = find(node, path, self.spec)
        if hit is not None and hit.type in self.spec.empty:
            return None
        return hit

    def find_all(self, node, path):
        return [
            n for n in find_all(node, path, self.spec) if n.type not in self.spec.empty
        ]

    def named(self, node):
        return self.spec.named(node) if node is not None else []

    def op_of(self, node):
        o = node.child_by_field_name("operator")
        if o is not None:
            return self.raw(o)
        for i in range(node.child_count):
            c = node.child(i)
            if not c.is_named and node.field_name_for_child(i) == "operator":
                return self.raw(c)
        return ""

    def sides(self, node):
        """(left, right) of a binary node, else (None, None)."""
        for a, b in (("left", "right"), ("lhs", "rhs")):
            left, right = node.child_by_field_name(a), node.child_by_field_name(b)
            if left is not None and right is not None:
                return left, right
        return None, None

    def text_line(self, node):
        end = self.spec.statement_end
        txt = self.t(node)
        if end:
            txt = txt.rstrip(end)
        return txt.strip()

    # -------------------------------------------------------- statements
    def build_body(self, body, is_main=False):
        self.fn_is_main = is_main
        if isinstance(body, list):
            out = []
            for n in body:
                out.extend(self.stmt(n))
            return M.Seq(out)
        return M.Seq(self.stmt_list(body))

    def stmt_list(self, node):
        if node is None:
            return []
        return self.stmt(node)

    def block(self, node):
        return M.Seq(self.stmt_list(node))

    def inner(self, node, skip=()):
        out = []
        for c in self.named(node):
            if c.type not in skip:
                out.extend(self.stmt(c))
        return out

    def stmt(self, n):
        if self.spec.skipped(n) or n.type == "ERROR":
            return []
        rule = self.spec.rule(n)
        if rule is None:
            txt = self.text_line(n)
            return [M.Simple(M.PROCESS, txt)] if txt else []
        if rule.get("hook"):
            res = self.run_hook(rule["hook"], n, rule)
            if res is not None:
                return res
            if rule["kind"] == "hook":
                txt = self.text_line(n)
                return [M.Simple(M.PROCESS, txt)] if txt else []
        return getattr(self, "k_" + rule["kind"])(n, rule)

    def run_hook(self, name, node, rule):
        fn = self.spec.hooks.get(name)
        if fn is None:
            from . import hooks

            fn = getattr(hooks, name)
        return fn(self, node, rule)

    def k_block(self, n, r):
        return self.inner(n, r.get("skip", ()))

    def k_skip(self, n, r):
        return []

    def k_simple(self, n, r):
        io = self.assign_input(n)
        if io is not None:
            return [io]
        txt = self.text_line(n)
        return [M.Simple(M.PROCESS, txt)] if txt else []

    def k_expression(self, n, r):
        kids = self.named(n)
        inner = kids[0] if kids else None
        if inner is None or inner.type in r.get("skip", ()):
            return []
        if self.spec.rule(inner) is not None:
            # `if`, `while`, `match` are expressions in Rust and Kotlin
            return self.stmt(inner)
        word = self.word(inner)
        if word is not None:
            return word
        io = self.try_io(inner)
        if io is None:
            io = self.assign_input(inner)
        if io is not None:
            return [io]
        if self.is_user_call(inner) or (
            not inner.named_child_count
            and self.spec.fold(self.raw(inner)) in self.known
        ):
            # `f(x)`, or a bare `Show;` in Pascal
            return [M.Simple(M.PREDEF, self.t(inner))]
        txt = self.t(inner)
        return [M.Simple(M.PROCESS, txt)] if txt else []

    def word(self, node):
        """A bare keyword written as an identifier: Pascal `break`, `exit`."""
        if not self.spec.words or node.named_child_count:
            return None
        kind = self.spec.words.get(self.spec.fold(self.raw(node)))
        if kind in ("break", "continue"):
            return [M.Jump(kind)]
        if kind == "return":
            return [self.make_return("")]
        return None

    def cond_text(self, node, missing="condition"):
        if node is None:
            return self.L(missing)
        path = self.spec.conditions.get(node.type)
        if path is not None:
            v = self.find(node, path)
            if v is None:
                kids = self.named(node)
                v = kids[-1] if kids else None
            node = v
        return strip_parens(self.t(node))

    def k_if(self, n, r):
        cond = self.cond_text(self.find(n, r.get("condition")))
        then_ = self.block(self.find(n, r.get("then")))
        else_ = self._else_chain(self.find_all(n, r.get("else")), r)
        if else_ is not None and not else_.items:
            else_ = None
        out = []
        init = self.find(n, r.get("init"))
        if init is not None:
            out.extend(self.stmt_as_process(init))
        out.append(M.If(cond, then_, else_))
        return out

    def _else_chain(self, alts, r):
        if not alts:
            return None
        a = alts[0]
        if a.type in r.get("elif", ()):
            cond = self.cond_text(self.find(a, r.get("condition")))
            then_ = self.block(self.find(a, r.get("then")))
            rest = self._else_chain(alts[1:], r)
            if rest is not None and not rest.items:
                rest = None
            return M.Seq([M.If(cond, then_, rest)])
        return M.Seq(self.stmt_list(a))

    def stmt_as_process(self, node):
        txt = self.text_line(node)
        return [M.Simple(M.PROCESS, txt)] if txt else []

    def k_while(self, n, r):
        cond = self.find(n, r.get("condition"))
        loop = M.While(
            self.cond_text(cond) if cond is not None else self.L("true"),
            self.block(self.find(n, r.get("body"))),
        )
        return self.loop_else(loop, self.find(n, r.get("else")))

    def k_do(self, n, r):
        cond = self.find(n, r.get("condition"))
        return [
            M.DoWhile(
                self.cond_text(cond) if cond is not None else self.L("true"),
                self.block(self.find(n, r.get("body"))),
                until=bool(r.get("until")),
            )
        ]

    def loop_else(self, loop, else_node):
        """Python's `for … else` / `while … else`."""
        if else_node is None:
            return [loop]
        tail = self.stmt_list(else_node)
        if not tail:
            return [loop]
        if not _breaks(loop.body):
            return [loop] + tail
        return [loop, M.If(self.L("no_break"), M.Seq(tail), None)]

    def _simple_from_node(self, node):
        if node is None:
            return None
        txt = self.text_line(node)
        return M.Simple(M.PROCESS, txt) if txt else None

    def _var_and_start(self, init):
        left, right = self.sides(init)
        if left is not None:
            return self.t(left), self.t(right)
        decls = []
        stack = list(init.named_children)
        while stack:
            c = stack.pop(0)
            target = c.child_by_field_name("declarator") or c.child_by_field_name(
                "name"
            )
            if target is not None and c.type not in self.spec.fn_nodes:
                value = c.child_by_field_name("value")
                if value is None:
                    rest = [k for k in c.named_children if k.id != target.id]
                    value = rest[-1] if rest else None
                if value is not None:
                    decls.append((target, value))
                    continue
            if c.named_child_count and not decls:
                stack.extend(c.named_children)
        if len(decls) != 1:
            return None, None
        return self.t(decls[0][0]), self.t(decls[0][1])

    def _canonical_for(self, init, cond, upd):
        """Header text for a plain counting loop, e.g. `i = 0, n - 1`; None otherwise."""
        if init is None or cond is None or upd is None:
            return None
        var, start = self._var_and_start(init)
        if not var or not start or not _VAR_RE.fullmatch(var):
            return None
        left, right = self.sides(cond)
        if left is None:
            return None
        op = self.op_of(cond)
        if op not in ("<", "<=", ">", ">="):
            return None
        if self.t(left) != var:
            return None
        limit = self.t(right)
        u = self.t(upd).rstrip(self.spec.statement_end or ";").strip()
        v = re.escape(var)
        step = None
        if re.fullmatch(rf"(?:\+\+\s*{v}|{v}\s*\+\+)", u):
            step = 1
        elif re.fullmatch(rf"(?:--\s*{v}|{v}\s*--)", u):
            step = -1
        else:
            m = re.fullmatch(rf"{v}\s*([+-])=\s*([+-]?\d+)", u)
            if not m:
                return None
            step = int(m.group(2)) * (1 if m.group(1) == "+" else -1)
        if step == 0:
            return None
        if step > 0 and op not in ("<", "<="):
            return None
        if step < 0 and op not in (">", ">="):
            return None
        end = (
            limit
            if op in ("<=", ">=")
            else (_minus_one(limit) if step > 0 else _plus_one(limit))
        )
        header = f"{var} = {start}, {end}"
        if step != 1:
            header += f", {step}"
        return header

    def k_for(self, n, r):
        body = self.block(self.find(n, r.get("body")))
        init = self.find(n, r.get("init"))
        cond = self.find(n, r.get("condition"))
        upd = self.find(n, r.get("update"))
        style = self.opts.for_style
        header = None
        if style in ("auto", "hexagon"):
            header = self._canonical_for(init, cond, upd)
        if header:
            loop = M.ForLoop(body=body, style="hexagon", header=header)
        else:
            loop = M.ForLoop(
                body=body,
                style="decision",
                init=self._simple_from_node(init),
                cond=self.cond_text(cond) if cond is not None else self.L("true"),
                update=self._simple_from_node(upd),
            )
        return self.loop_else(loop, self.find(n, r.get("else")))

    def counting_loop(self, var, start, end, step, body):
        """A loop from start to end inclusive."""
        if self.opts.for_style == "decision":
            a = self.spec.assign
            op = "<=" if step > 0 else ">="
            upd = f"{var} + {step}" if step > 0 else f"{var} - {-step}"
            return M.ForLoop(
                body=body,
                style="decision",
                init=M.Simple(M.PROCESS, f"{var} {a} {start}"),
                cond=f"{var} {op} {end}",
                update=M.Simple(M.PROCESS, f"{var} {a} {upd}"),
            )
        header = f"{var} = {start}, {end}"
        if step != 1:
            header += f", {step}"
        return M.ForLoop(body=body, style="hexagon", header=header)

    def k_counting(self, n, r):
        var = self.t(self.find(n, r.get("var")))
        start = self.t(self.find(n, r.get("start")))
        end = self.t(self.find(n, r.get("end")))
        step = 1
        if r.get("step"):
            st = self.t(self.find(n, r["step"]))
            step = int(st) if _INT_RE.match(st) else 1
        if r.get("descending") and any(c.type == r["descending"] for c in n.children):
            step = -abs(step)
        return [
            self.counting_loop(
                var, start, end, step, self.block(self.find(n, r.get("body")))
            )
        ]

    def _range_loop(self, var, it, r, body):
        """`for i in range(a, b, step)` as a counting loop."""
        names = r.get("range")
        if not names or not _VAR_RE.fullmatch(var):
            return None
        kind = self.spec.call_nodes.get(it.type)
        if kind is None or self.spec.fold(self.callee(it)) not in {
            self.spec.fold(x) for x in names
        }:
            return None
        args = [
            a
            for a in self.named(self.find(it, kind))
            if a.type not in self.spec.io_skip_args
        ]
        vals = [self.t(a) for a in args]
        if not 1 <= len(vals) <= 3:
            return None
        start, stop = ("0", vals[0]) if len(vals) == 1 else (vals[0], vals[1])
        step = 1
        if len(vals) == 3:
            if not _INT_RE.match(vals[2]) or int(vals[2]) == 0:
                return None
            step = int(vals[2])
        end = _minus_one(stop) if step > 0 else _plus_one(stop)
        return self.counting_loop(var, start, end, step, body)

    def k_foreach(self, n, r):
        var = self.t(self.find(n, r.get("var"))).lstrip("&* ").strip()
        it_node = self.find(n, r.get("iterable"))
        cont = self.t(it_node)
        body = self.block(self.find(n, r.get("body")))
        loop = self._range_loop(var, it_node, r, body) if it_node is not None else None
        if loop is None:
            if self.opts.for_style == "decision":
                loop = M.ForLoop(
                    body=body,
                    style="decision",
                    init=None,
                    cond=self.L("more", cont),
                    update=None,
                )
            else:
                loop = M.ForLoop(
                    body=body, style="hexagon", header=self.L("foreach", var, cont)
                )
        return self.loop_else(loop, self.find(n, r.get("else")))

    # ------------------------------------------------------------ switch
    def k_switch(self, n, r):
        value = self.find(n, r.get("value"))
        holder = self.find(n, r.get("body")) if r.get("body") else n
        case_rules = r.get("cases", {})
        mode = r.get("fallthrough", False)
        default_labels = set(r.get("default_labels", []))
        strip = r["label_strip"]
        raw = [c for c in self.named(holder)] if holder is not None else []
        cases_raw = [c for c in raw if c.type in case_rules]

        tail_default = []
        after = r.get("default_after")
        if after and holder is not None:
            seen = False
            for c in holder.children:
                if c.type == after:
                    seen = True
                elif (
                    seen
                    and c.is_named
                    and not self.spec.skipped(c)
                    and c.type not in case_rules
                ):
                    tail_default.append(c)

        cases, pending = [], []
        for idx, cs in enumerate(cases_raw):
            co = case_rules[cs.type]
            label_nodes = self.find_all(cs, co["value"]) if co.get("value") else []
            if co.get("labels"):
                label_nodes += [c for c in self.named(cs) if c.type in co["labels"]]
            labels = [strip.sub("", self.t(x)).strip() for x in label_nodes]
            labels = [x for x in labels if x]
            is_default = (
                bool(co.get("default"))
                or not labels
                or any(x in default_labels for x in labels)
            )
            if is_default:
                labels = [self.L("default")]
            if co.get("body"):
                body_nodes = self.find_all(cs, co["body"])
            else:
                used = {x.id for x in label_nodes}
                body_nodes = [c for c in self.named(cs) if c.id not in used]
            stmts = []
            for b in body_nodes:
                stmts.extend(self.stmt(b))
            falls = co.get("fallthrough", mode)
            if not stmts and falls is True:
                # an empty `case X:` shares the next case's body
                pending.extend(labels)
                continue
            if isinstance(falls, str):
                falls = _contains_type(body_nodes, falls)
            case = M.Case(pending + labels, M.Seq(stmts), is_default=is_default)
            case.fallthrough = falls
            pending = []
            cases.append(case)
        if tail_default:
            stmts = []
            for b in tail_default:
                stmts.extend(self.stmt(b))
            case = M.Case(pending + [self.L("default")], M.Seq(stmts), is_default=True)
            case.fallthrough = False
            pending = []
            cases.append(case)
        if pending:
            case = M.Case(pending, M.Seq([]))
            case.fallthrough = True
            cases.append(case)
        for i, c in enumerate(cases):
            last = i == len(cases) - 1
            if c.fallthrough is True:
                c.fallthrough = not last and not _ends_flow(c.body)
            else:
                c.fallthrough = bool(c.fallthrough) and not last
        if value is None and r.get("value") and cases:
            return [self._if_chain(cases)]
        return [M.Switch(self.cond_text(value), cases)]

    def _if_chain(self, cases):
        """A switch without a value (Go `switch {`) is a chain of conditions."""
        default = next((c for c in cases if c.is_default), None)
        rest = [c for c in cases if not c.is_default]
        tail = default.body if default is not None and default.body.items else None
        for c in reversed(rest):
            tail = M.Seq([M.If(" || ".join(c.labels), c.body, tail)])
        return tail.items[0] if tail is not None and tail.items else M.Seq([])

    # ------------------------------------------------------------- jumps
    def k_break(self, n, r):
        return [M.Jump("break")]

    def k_continue(self, n, r):
        return [M.Jump("continue")]

    def make_return(self, txt):
        style = getattr(self.opts, "return_style", "auto")
        if style == "end" or not txt:
            text = self.opts.end_label
        elif style == "auto" and self.fn_is_main and txt in self.spec.ok_exit:
            # `return 0` in main is a normal end of the program, not a value
            text = self.opts.end_label
        else:
            text = self.L("return", txt)
        return M.Simple(M.TERMINATOR, text, terminal=True)

    def _value(self, n, r):
        if r.get("value"):
            return self.find(n, r["value"])
        kids = self.named(n)
        return kids[0] if kids else None

    def k_return(self, n, r):
        return [self.make_return(self.t(self._value(n, r)))]

    def k_throw(self, n, r):
        txt = self.t(self._value(n, r))
        return [
            M.Simple(
                M.TERMINATOR,
                self.L("exception", txt) if txt else self.L("exception_bare"),
                terminal=True,
            )
        ]

    def k_goto(self, n, r):
        return [
            M.Simple(
                M.CONNECTOR,
                self.raw(self.find(n, r.get("label", "label"))),
                terminal=True,
            )
        ]

    def k_label(self, n, r):
        lab = self.find(n, r.get("label", "label"))
        items = [M.Simple(M.CONNECTOR, self.raw(lab))]
        for c in self.named(n):
            if lab is None or c.id != lab.id:
                items.extend(self.stmt(c))
        return items

    def _clause(self, node):
        """`else:` / `finally:` wrappers hold statements; a statement node is one."""
        return self.stmt(node) if self.spec.rule(node) else self.inner(node)

    def _parts(self, n, paths, exclude):
        out = []
        for path in paths:
            for c in self.find_all(n, path):
                if c.id not in exclude:
                    out.append(c)
        return out

    def k_try(self, n, r):
        body = self.find(n, r.get("body"))
        items = self.stmt_list(body)
        taken = {body.id} if body is not None else set()
        for c in self._parts(n, r.get("else", ()), taken):
            items.extend(self._clause(c))
        handlers = r.get("handlers", {})
        for c in self.named(n):
            h = handlers.get(c.type)
            if h is None:
                continue
            body = self.find(c, h.get("body", "body"))
            if body is None:
                rest = self.named(c)
                body = rest[-1] if rest else None
            param = self.find(c, h["parameter"]) if h.get("parameter") else None
            if param is not None and body is not None and param.id == body.id:
                param = None
            params = strip_parens(self.t(param)) if param is not None else ""
            cond = self.L("caught", params) if params else self.L("caught_bare")
            items.append(M.If(cond, self.block(body), None))
        # Pascal `except … end` without `on`: statements that catch anything
        rest = []
        for c in self._parts(n, r.get("catch_all", ()), taken):
            if c.type not in handlers:
                rest.extend(self.stmt(c))
        if rest:
            items.append(M.If(self.L("caught_bare"), M.Seq(rest), None))
        for c in self._parts(n, r.get("finally", ()), taken):
            items.extend(self._clause(c))
        return items

    def k_inline(self, n, r):
        """A statement with a header and a body run once: `with`, `using`, `lock`."""
        body = self.find(n, r.get("body", "body"))
        if body is None:
            return self.stmt_as_process(n)
        head = self.src[n.start_byte : body.start_byte].decode("utf-8", "replace")
        head = re.sub(r"\s*[:{]\s*$", "", normalize(head))
        out = [M.Simple(M.PROCESS, head)] if head else []
        return out + self.stmt_list(body)

    # ------------------------------------------------------------- calls
    def callee(self, call):
        """The called name as written: `printf`, `System.out.println`, `fmt.Println`."""
        if self.spec.callee:
            fn = self.find(call, self.spec.callee)
            if fn is not None:
                return re.sub(r"\s+", "", self.raw(fn))
        args = self.find(call, self.spec.call_nodes.get(call.type))
        end = args.start_byte if args is not None else call.end_byte
        head = self.src[call.start_byte : end].decode("utf-8", "replace")
        return re.sub(r"\s+", "", head)

    def callee_name(self, call):
        return self.spec.last_segment(self.callee(call))

    def is_user_call(self, call):
        if call.type not in self.spec.call_nodes:
            return False
        if self.spec.callee_types:
            fn = self.find(call, self.spec.callee) if self.spec.callee else None
            if fn is None or fn.type not in self.spec.callee_types:
                return False
        return self.spec.fold(self.callee_name(call)) in self.known

    def call_args(self, call):
        arglist = self.find(call, self.spec.call_nodes.get(call.type))
        out = []
        for a in arglist.named_children if arglist is not None else []:
            if a.type in self.spec.io_skip_args:
                continue
            if a.type in self.spec.io_unwrap_args and a.named_child_count == 1:
                a = a.named_children[0]
            out.append(a)
        return out

    def io_rule(self, table, call):
        full = self.spec.fold(self.callee(call))
        if full in table:
            return table[full]
        return table.get(self.spec.fold(self.callee_name(call)))

    # ---------------------------------------------------------- literals
    def _string_value(self, node):
        if node is None:
            return None
        sp = self.spec
        if node.type in sp.string_concat:
            vals = [
                self._string_value(c)
                for c in node.named_children
                if c.type in sp.string_nodes
            ]
            if not vals or any(v is None for v in vals):
                return None
            return "".join(vals)
        if node.type not in sp.string_nodes:
            return None
        raw = self.raw(node)
        pos = [p for p in (raw.find('"'), raw.find("'"), raw.find("`")) if p >= 0]
        if not pos:
            return None
        i = min(pos)
        quote = raw[i]
        prefix = raw[:i].lower()
        width = 3 if raw[i : i + 3] == quote * 3 and len(raw) >= i + 6 else 1
        j = len(raw) - width
        if j < i + width or raw[j : j + width] != quote * width:
            j = raw.rfind(quote)
            width = 1
        if j <= i:
            return None
        body = raw[i + width : j]
        if sp.template:
            body = body.replace(sp.template, "{")
        if sp.escape == "double":
            return body.replace(quote * 2, quote)
        if sp.escape == "none" or "r" in prefix or "@" in prefix:
            return body
        return unescape(body)

    def _is_manipulator(self, node):
        st = self.spec.streams
        if not st or not st["manipulators"]:
            return False
        name = self.raw(node).split("::")[-1].split("(")[0].strip()
        return name in st["manipulators"]

    def _concat_parts(self, node):
        """`"Sum: " + n + "!"` -> its operands, when strings are glued with `+`."""
        op = self.spec.concat_operator
        if not op:
            return [node]
        left, right = self.sides(node)
        if left is None or self.op_of(node) != op:
            return [node]
        parts = self._concat_parts(left) + self._concat_parts(right)
        if any(self._string_value(p) is not None for p in parts):
            return parts
        return [node]

    def _weave(self, segments, prefix):
        """Join literal text and expressions into one readable line.

        Literals are kept as is and expressions go in braces, giving
        `Output: Job #{job.id}` instead of `Output: " Job #", job.id`.
        """
        exprs = [v for kind, v in segments if kind == "expr"]
        if not any(kind == "text" for kind, _ in segments):
            return prefix + ", ".join(exprs) if exprs else self.L("newline")
        buf = []
        for kind, v in segments:
            buf.append("{" + v + "}" if kind == "expr" else v)
        body = normalize("".join(buf)).strip()
        if not body:
            return prefix + ", ".join(exprs) if exprs else self.L("newline")
        return prefix + body

    def _percent(self, node):
        """Python's `"%d items" % n` as the text it prints, else None."""
        op = self.spec.format_operator
        left, right = self.sides(node) if op else (None, None)
        if left is None or self.op_of(node) != op or self._string_value(left) is None:
            return None
        args = [right]
        if right.type in self.spec.format_tuples:
            args = self.named(right)
        return self._format_call(left, args, "")

    def _segments(self, nodes, sep=""):
        segs = []
        for i, p in enumerate(nodes):
            if i and sep:
                segs.append(("sep", sep))
            if self._is_manipulator(p):
                segs.append(("text", " "))
                continue
            pct = self._percent(p)
            if pct is not None:
                segs.append(("text", pct))
                continue
            for part in self._concat_parts(p):
                val = self._string_value(part)
                if val is not None:
                    segs.append(("text", val))
                else:
                    segs.append(("expr", self.t(part)))
        return segs

    def _format_call(self, fmt_node, arg_nodes, prefix, style="printf"):
        """A printf-style call as its format string with the arguments filled in."""
        fmt = self._string_value(fmt_node)
        args = [self.t(a) for a in arg_nodes]
        if fmt is None:
            parts = ([self.t(fmt_node)] if fmt_node is not None else []) + args
            return prefix + ", ".join(p for p in parts if p)
        used = [0]
        if style == "composite":

            def repl(m):
                k = int(m.group(1))
                if k < len(args):
                    used[0] = max(used[0], k + 1)
                    return "{" + args[k] + "}"
                return m.group(0)

            body = _COMPOSITE_RE.sub(repl, fmt)
        else:

            def repl(m):
                if m.group(0) == "%%":
                    return "%"
                if used[0] < len(args):
                    used[0] += 1
                    return "{" + args[used[0] - 1] + "}"
                return m.group(0)

            body = self._spec_re.sub(repl, fmt)
            for k, v in self.spec.io_format_replace.items():
                body = body.replace(k, v)
        tail = args[used[0] :]
        if tail:
            body = body.rstrip() + " " + ", ".join("{" + a + "}" for a in tail)
        body = normalize(body).strip()
        return prefix + body if body else self.L("newline")

    # ---------------------------------------------------------------- io
    def _flatten_stream(self, node, op):
        left, right = self.sides(node)
        if left is not None and self.op_of(node) == op:
            return self._flatten_stream(left, op) + [right]
        return [node]

    def _stream_io(self, node):
        st = self.spec.streams
        left, _right = self.sides(node)
        op = self.op_of(node) if left is not None else ""
        if op not in (st["output_operator"], st["input_operator"]):
            return None
        style = self.opts.io_style
        parts = self._flatten_stream(node, op)
        head = self.raw(parts[0]).split("::")[-1]
        if op == st["output_operator"] and head in st["output"]:
            if style == "code":
                return M.Simple(M.IO, self.t(node))
            if style == "pretty":
                return M.Simple(
                    M.IO, self._weave(self._segments(parts[1:]), self.L("out"))
                )
            nl = st["newline"]
            args = [self.t(p) for p in parts[1:]]
            args = [a for a in args if a not in nl and self.strip_all(a) not in nl]
            return M.Simple(
                M.IO, self.L("out") + ", ".join(args) if args else self.L("newline")
            )
        if op == st["input_operator"] and head in st["input"]:
            if style == "code":
                return M.Simple(M.IO, self.t(node))
            args = [self.t(p) for p in parts[1:]]
            return M.Simple(M.IO, self.L("in") + ", ".join(args))
        return None

    def try_io(self, node):
        """An I/O block for stream or stdio-like calls, None for anything else."""
        if self.spec.streams is not None:
            res = self._stream_io(node)
            if res is not None:
                return res
        if node.type not in self.spec.call_nodes:
            if node.named_child_count:
                return None
            # a call without parentheses: Pascal `writeln;`, `readln;`
            name = self.spec.fold(self.raw(node))
            if name in self.spec.io_output:
                return M.Simple(
                    M.IO,
                    self.t(node) if self.opts.io_style == "code" else self.L("newline"),
                )
            if name in self.spec.io_input:
                return M.Simple(
                    M.IO,
                    self.t(node)
                    if self.opts.io_style == "code"
                    else self.L("in_plain"),
                )
            return None
        style = self.opts.io_style
        code_style = style == "code"
        nodes = self.call_args(node)
        args = [self.t(a) for a in nodes]
        f = self.io_rule(self.spec.io_input, node)
        if f is not None and "stream" in f:
            st = self.spec.streams
            k = f["stream"]
            if not (st and len(args) > k and args[k].split("::")[-1] in st["input"]):
                f = None
                if self.io_rule(self.spec.io_output, node) is None:
                    return None
        out = self.io_rule(self.spec.io_output, node)
        if out is not None:
            if code_style:
                return M.Simple(M.IO, self.t(node))
            if style == "pretty" and nodes:
                k = out.get("format")
                # with `weave` too, the format is used only when it is a literal
                # followed by arguments: Console.WriteLine("{0}", x) vs ("a" + x)
                if (
                    k is not None
                    and k < len(nodes)
                    and (
                        "weave" not in out
                        or (
                            len(nodes) > k + 1
                            and self._string_value(nodes[k]) is not None
                        )
                    )
                ):
                    return M.Simple(
                        M.IO,
                        self._format_call(
                            nodes[k],
                            nodes[k + 1 :],
                            self.L("out"),
                            out.get("style", "printf"),
                        ),
                    )
                if "weave" in out:
                    picked = nodes[parse_slice(out["weave"])]
                    return M.Simple(
                        M.IO,
                        self._weave(
                            self._segments(picked, out.get("sep", "")), self.L("out")
                        ),
                    )
            if style == "pretty" and "weave" in out:
                return M.Simple(M.IO, self.L("newline"))
            picked = args[parse_slice(out.get("args"))]
            return M.Simple(
                M.IO,
                self.L("out") + ", ".join(picked) if picked else self.L("out_plain"),
            )
        if f is not None:
            if code_style:
                return M.Simple(M.IO, self.t(node))
            rest = [self._strip_prefix(a) for a in args[parse_slice(f.get("args"))]]
            return M.Simple(
                M.IO, self.L("in") + ", ".join(rest) if rest else self.L("in_plain")
            )
        return None

    def _strip_prefix(self, arg):
        """scanf("%d", &n) -> n: drop the address-of and similar prefixes."""
        changed = True
        while changed:
            changed = False
            for p in self.spec.io_input_strip:
                if p and arg.startswith(p):
                    arg = arg[len(p) :].lstrip()
                    changed = True
        return arg

    def _reads_input(self, node):
        stack = [node]
        while stack:
            c = stack.pop()
            if (
                c.type in self.spec.call_nodes
                and self.io_rule(self.spec.io_input, c) is not None
            ):
                return True
            stack.extend(c.named_children)
        return False

    def assign_input(self, node):
        """`n = int(input())`, `int n = sc.nextInt();` -> Input: n."""
        table = self.spec.io_assign
        if not table:
            return None
        found = [node] if node.type in table else []
        if not found:
            stack = list(node.named_children)
            while stack:
                c = stack.pop(0)
                if c.type in table:
                    found.append(c)
                elif c.type not in self.spec.call_nodes:
                    stack.extend(c.named_children)
        targets = []
        for a in found:
            tpath, vpath = table[a.type]
            target, value = self.find(a, tpath), self.find(a, vpath)
            if target is None or value is None or not self._reads_input(value):
                return None
            targets.append(self.t(target))
        if not targets:
            return None
        if self.opts.io_style == "code":
            return M.Simple(M.IO, self.text_line(node))
        return M.Simple(M.IO, self.L("in") + ", ".join(targets))


def _contains_type(nodes, node_type):
    stack = list(nodes)
    while stack:
        n = stack.pop()
        if n.type == node_type:
            return True
        stack.extend(n.named_children)
    return False


def _breaks(item):
    """True if a `break` inside leaves the enclosing loop (not a nested one)."""
    if isinstance(item, M.Jump):
        return item.kind == "break"
    if isinstance(item, M.Seq):
        return any(_breaks(i) for i in item.items)
    if isinstance(item, M.If):
        return _breaks(item.then_) or (item.else_ is not None and _breaks(item.else_))
    if isinstance(item, M.Switch):
        return any(_breaks(c.body) for c in item.cases)
    return False


def _ends_flow(block):
    """True if control never reaches the end of the block (break / return)."""
    items = block.items if isinstance(block, M.Seq) else [block]
    if not items:
        return False
    last = items[-1]
    if isinstance(last, M.Jump):
        return True
    if isinstance(last, M.Return):
        return True
    if isinstance(last, M.Simple):
        return last.terminal
    if isinstance(last, M.If):
        return (
            last.else_ is not None and _ends_flow(last.then_) and _ends_flow(last.else_)
        )
    if isinstance(last, M.Switch):
        return bool(last.cases) and all(_ends_flow(c.body) for c in last.cases)
    return False
