#!/usr/bin/env python3
"""Runs the examples in docs/guide/*.md and checks their output.

An example is a ```silly block containing `fn main` that is followed directly
by a ```text block: the program's stdout must equal the text block. Other
blocks are fragments and are only shown, not run.

    python3 tests/doc_test.py [docs/guide/tour.md ...]
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCK = re.compile(r"```silly\n(.*?)```\n\n?```text\n(.*?)```", re.S)


def examples(path):
    text = path.read_text()
    for m in BLOCK.finditer(text):
        code, want = m.group(1), m.group(2)
        if "fn main" in code:
            line = text.count("\n", 0, m.start()) + 1
            yield line, code, want


def run(code):
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "example.silly")
        Path(src).write_text(code)
        r = subprocess.run([sys.executable, "-m", "silly", "run", src], cwd=d,
                           env={**os.environ, "PYTHONPATH": str(ROOT)},
                           capture_output=True, text=True, timeout=120)
        return r.stdout, r.stderr, r.returncode


def main():
    files = [Path(a) for a in sys.argv[1:]] or sorted((ROOT / "docs" / "guide").glob("*.md"))
    passed = failed = 0
    for f in files:
        for line, code, want in examples(f):
            out, err, rc = run(code)
            if out == want:
                passed += 1
                continue
            failed += 1
            print(f"FAIL {f.relative_to(ROOT) if f.is_absolute() else f}:{line} (exit {rc})")
            print("--- expected\n" + want + "--- got\n" + out + (err and "--- stderr\n" + err[-1500:]))
    print(f"{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
