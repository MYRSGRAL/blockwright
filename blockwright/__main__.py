"""Entry point.

python -m blockwright             pick sources in the terminal
python -m blockwright "Lab 1"     build charts right away
"""

import sys

from . import vendored

# Windows consoles often default to cp866/cp1251
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main(argv=None):
    if not vendored.activate():
        sys.stderr.write(vendored.install_hint())
        return 3
    from .cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
