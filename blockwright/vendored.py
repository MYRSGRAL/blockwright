"""Zero-install mode: tree-sitter parsers bundled in vendor/.

The repository carries prebuilt parsers for several platforms and CPython
versions. When the system has none, the matching folder is put on sys.path,
so a plain clone runs without pip.

Termux is the exception: Android's libc has no wheels on PyPI, so the parsers
are compiled on the device (tools/install-termux.sh).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_termux():
    return "com.termux" in os.environ.get("PREFIX", "") or os.path.isdir(
        "/data/data/com.termux/files/usr"
    )


def platform_tag():
    import platform

    arch = platform.machine().lower()
    if sys.platform.startswith("win"):
        return "win_amd64" if sys.maxsize > 2**32 else "win32"
    if sys.platform.startswith("linux"):
        if is_termux():
            return "android_" + (arch or "unknown")
        if arch in ("x86_64", "amd64"):
            return "linux_x86_64"
        return "linux_" + (arch or "unknown")
    if sys.platform == "darwin":
        return "macos_arm64" if arch in ("arm64", "aarch64") else "macos_x86_64"
    return sys.platform


def paths(root=None):
    tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    base = os.path.join(root or ROOT, "vendor", platform_tag())
    return [
        p
        for p in (os.path.join(base, tag), os.path.join(base, "common"))
        if os.path.isdir(p)
    ]


def have_parsers():
    """tree-sitter itself and a TOML reader for the language descriptions."""
    try:
        import tree_sitter  # noqa: F401

        try:
            import tomllib  # noqa: F401
        except ImportError:
            import tomli  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def activate(root=None):
    """Put the bundled parsers on sys.path.

    When the system has tree-sitter of its own, the bundle only fills the
    gaps: it goes to the end of sys.path, so grammars missing from the
    system still come from vendor/.
    """
    have = have_parsers()
    for p in paths(root):
        if p not in sys.path:
            if have:
                sys.path.append(p)
            else:
                sys.path.insert(0, p)
    return have_parsers()


def web_asset(*parts):
    """A file from vendor/web (editor libraries, platform independent) or None.

    In a PyInstaller build ROOT points inside the bundle, so this still works.
    """
    p = os.path.join(ROOT, "vendor", "web", *parts)
    return p if os.path.isfile(p) else None


def install_hint():
    req = os.path.join(ROOT, "requirements.txt")
    head = (
        "Не найдены парсеры tree-sitter.\n"
        f"Python {sys.version.split()[0]}, платформа {platform_tag()}.\n"
    )
    if is_termux():
        return head + (
            "Termux собирает парсеры сам — нужен компилятор:\n"
            "    pkg install python clang\n"
            f"    pip install -r {req}\n"
            "Либо разом: sh tools/install-termux.sh\n"
        )
    return head + (
        "В комплекте есть сборки для CPython 3.12–3.14: "
        "Windows x64 и Linux x86-64.\n"
        "Для другой платформы выполните один раз:\n"
        f"    {os.path.basename(sys.executable)} -m pip install -r {req}\n"
    )
