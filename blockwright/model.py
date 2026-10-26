"""Intermediate representation of a flowchart.

A structured tree (sequence, branch, loops, switch) plus non-local jumps
(break / continue / return / goto). Every construct lays itself out, so no
general-purpose graph layout is needed.
"""

from dataclasses import dataclass, field

# block kinds of GOST 19.701-90
TERMINATOR = "terminator"  # start / end / return
PROCESS = "process"
IO = "io"
INPUT = "input"
OUTPUT = "output"
DECISION = "decision"
PREDEF = "predefined"  # call of a user function
PREP = "preparation"  # loop header
CONNECTOR = "connector"


@dataclass
class Simple:
    """A single block with one entry and at most one exit."""

    kind: str
    text: str
    terminal: bool = False  # no exit: return / throw


@dataclass
class Jump:
    """break / continue: a jump without a block of its own."""

    kind: str


@dataclass
class Return:
    """Обычный возврат: значение сохраняется до этапа компоновки."""

    value: str
    main: bool = False


@dataclass
class Seq:
    items: list[object] = field(default_factory=list)


@dataclass
class If:
    cond: str
    then_: object
    else_: object | None = None


@dataclass
class While:
    cond: str
    body: object


@dataclass
class DoWhile:
    cond: str
    body: object
    until: bool = False  # Pascal `repeat … until`: the loop ends when cond holds


@dataclass
class ForLoop:
    body: object
    style: str = "decision"
    header: str = ""
    init: Simple | None = None
    cond: str | None = None
    update: Simple | None = None


@dataclass
class Case:
    labels: list[str]
    body: object
    fallthrough: bool = False
    is_default: bool = False


@dataclass
class Switch:
    expr: str
    cases: list[Case] = field(default_factory=list)


@dataclass
class Function:
    name: str  # qualified with class / namespace
    signature: str
    short: str  # text of the start block
    file: str
    rel: str
    line: int
    lang: str
    body: Seq
