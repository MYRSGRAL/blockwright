"""From source files to flowchart IR: the steps shared by the CLI, the picker
and the tests."""

from dataclasses import dataclass, field

from . import model as M
from . import parse as P
from .build import Builder


@dataclass
class Source:
    path: str
    src: bytes
    spec: object  # langs.Spec the file was parsed with
    tree: object = None  # None when the grammar is not installed
    errors: int = 0
    known: set = field(default_factory=set)


@dataclass
class Chart:
    info: dict  # name, base, signature, short, line, main
    body: M.Seq


def load(path, only=None) -> Source | None:
    """Read and parse one file; None if it is unreadable or no language fits."""
    with open(path, "rb") as fh:
        src = fh.read()
    spec = P.guess_language(path, src.decode("utf-8", "replace"), only)
    if spec is None:
        return None
    tree, spec, errs = P.parse_source(src, spec)
    s = Source(path, src, spec, tree, errs)
    if tree is not None:
        s.known = P.collect_known_names(src, tree.root_node, spec)
    return s


def outline(source: Source):
    """Function infos of a parsed file, the program chart (if any) first."""
    if source.tree is None:
        return []
    root = source.tree.root_node
    out = []
    prog = P.describe_program(source.src, root, source.spec, source.path)
    if prog is not None:
        out.append(prog)
    for node in P.collect_functions(source.src, root, source.spec):
        out.append(P.describe_function(source.src, node, source.spec))
    return out


def _does_work(item):
    """False for module code that only sets constants and calls the user's
    functions (`if __name__ == "__main__": main()`): no chart for that."""
    if isinstance(item, M.Seq):
        return any(_does_work(i) for i in item.items)
    if isinstance(item, M.Simple):
        return item.kind == M.IO
    if isinstance(item, M.If):
        return _does_work(item.then_) or (
            item.else_ is not None and _does_work(item.else_)
        )
    return not isinstance(item, M.Jump)


def charts(source: Source, opts, known, infos=None) -> list[Chart]:
    if source.errors:
        raise ValueError(
            f"{source.path}: ошибок синтаксиса: {source.errors}; схема не построена"
        )
    builder_type = Builder
    if getattr(opts, "study", True) and source.spec.name == "cpp":
        from .study import StudyBuilder

        builder_type = StudyBuilder
    builder = builder_type(source.src, opts, known, source.spec)
    out = []
    for info in outline(source) if infos is None else infos:
        body = builder.build_body(info["body"], is_main=info["main"])
        if info.get("program") and not _does_work(body):
            continue
        out.append(Chart(info, body))
    return out
