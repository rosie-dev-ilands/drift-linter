#!/usr/bin/env python3
"""Regenerate the BUILTINS block in web/drift_engine.js from dir(builtins).

Run before every release:  python3 tools/sync_js_builtins.py

Keeps the browser engine's builtin name set in lockstep with the CPython
the Python engine runs against. The hand-typed list drifted once (dateutil
field test #8: the OSError family and Warning classes were missing, which
false-flagged `except FileNotFoundError:` in the browser engine). Aether's
review of the v0.1.16 diff (2026-08-25): "BUILTINS still hand-typed; freeze
vs dir(builtins) so the next gap isn't a field test." This script is that
freeze — the diff after running it should be empty.
"""
import builtins
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = ROOT / "web" / "drift_engine.js"

MARK_START = "  var BUILTINS = ("
MARK_END = '").split(" ");'


def main() -> int:
    names = sorted(n for n in dir(builtins) if not n.startswith("__"))
    lines = []
    for i in range(0, len(names), 12):
        # trailing space before the closing quote: the string is built by
        # concatenating these literals, so each line must end on a word
        # boundary or the seam merges names (ConnectionError + Refused...)
        lines.append('    "' + " ".join(names[i:i + 12]) + ' " +')
    lines[-1] = lines[-1][:-4] + '").split(" ");'
    block = MARK_START + "\n" + "\n".join(lines)

    src = ENGINE.read_text(encoding="utf-8")
    i0 = src.index(MARK_START)
    i1 = src.index(MARK_END) + len(MARK_END)
    if src[i0:i1] == block:
        print(f"BUILTINS already in sync ({len(names)} names)")
        return 0
    ENGINE.write_text(src[:i0] + block + src[i1:], encoding="utf-8")
    print(f"rewrote BUILTINS in {ENGINE} ({len(names)} names)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
