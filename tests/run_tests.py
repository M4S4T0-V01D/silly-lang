#!/usr/bin/env python3
"""Silly test suite.

tests/run/*.silly   compiled and run; stdout must equal the `#> ` lines in the file
                    (`#! exit N` sets the expected exit status, default 0;
                     `#! stderr TEXT` requires TEXT in stderr).
tests/fail/*.silly  must be rejected; the first line is `# error: TEXT` and TEXT must
                    appear in the diagnostic.
tests/unit/*.silly  run with `silly test`; every @test must pass.
tests/pkg_test.py   the package manager, end to end (needs git).
tests/selfhost_test.py  the self-hosted compiler: bootstrap fixpoint, then tests/run.
"""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from silly.driver import compile_to_c, build_c  # noqa: E402
from silly.errors import SillyError  # noqa: E402

OUT = os.path.join(ROOT, "tests", ".build")


def expectations(path):
    out, code, stderr = [], 0, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.rstrip("\n")
            if s.startswith("#> ") or s == "#>":
                out.append(s[3:])
            elif s.startswith("#! exit "):
                code = int(s[8:])
            elif s.startswith("#! stderr "):
                stderr.append(s[10:])
    return out, code, stderr


def run_case(path, opt):
    name = os.path.relpath(path, os.path.join(ROOT, "tests"))
    try:
        csrc = compile_to_c(path)
    except SillyError as e:
        return name, e.render(getattr(e, "sources", {}))
    exe = os.path.join(OUT, name.replace(os.sep, "_")[:-6] + "_" + opt)
    try:
        build_c(csrc, exe, opt)
    except SillyError as e:
        return name, e.msg
    want, code, stderr = expectations(path)
    r = subprocess.run([exe], capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, SILLY_GFX="headless", SILLY_GFX_SHOT=""))
    got = r.stdout.split("\n")
    if got and got[-1] == "":
        got.pop()
    problems = []
    if got != want:
        for i in range(max(len(got), len(want))):
            g = got[i] if i < len(got) else "<missing>"
            w = want[i] if i < len(want) else "<missing>"
            if g != w:
                problems.append(f"line {i + 1}: expected {w!r}, got {g!r}")
                break
    if r.returncode != code:
        problems.append(f"exit status {r.returncode}, expected {code}; stderr: {r.stderr.strip()[-300:]}")
    for s in stderr:
        if s not in r.stderr:
            problems.append(f"stderr lacks {s!r}: {r.stderr.strip()[-300:]}")
    return name, "; ".join(problems) or None


def fail_case(path, opt):
    name = os.path.relpath(path, os.path.join(ROOT, "tests"))
    with open(path, encoding="utf-8") as f:
        first = f.readline().strip()
    if not first.startswith("# error: "):
        return name, "fail test lacks a `# error: TEXT` first line"
    want = first[len("# error: "):]
    try:
        compile_to_c(path)
    except SillyError as e:
        msg = e.render(getattr(e, "sources", {}))
        return name, None if want in msg else f"expected error containing {want!r}, got:\n{msg}"
    return name, "compiled, but it should have been rejected"


def unit_case(path, opt):
    name = os.path.relpath(path, os.path.join(ROOT, "tests"))
    try:
        csrc = compile_to_c(path, test_mode=True)
        exe = os.path.join(OUT, name.replace(os.sep, "_")[:-6] + "_" + opt)
        build_c(csrc, exe, opt)
    except SillyError as e:
        return name, e.render(getattr(e, "sources", {}))
    r = subprocess.run([exe], capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, SILLY_GFX="headless", SILLY_GFX_SHOT=""))
    return name, None if r.returncode == 0 else r.stdout[-800:] + r.stderr[-400:]


def pkg_case(path, opt):
    r = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=300)
    return "pkg_test.py", None if r.returncode == 0 else (r.stdout + r.stderr)[-1500:]


def selfhost_case(path, opt):
    r = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=600)
    return "selfhost_test.py", None if r.returncode == 0 else (r.stdout + r.stderr)[-1500:]


def main():
    os.makedirs(OUT, exist_ok=True)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    opts = ["debug", "release"] if "--both" in sys.argv else ["release"]
    jobs = []
    for kind, fn in (("run", run_case), ("fail", fail_case), ("unit", unit_case)):
        d = os.path.join(ROOT, "tests", kind)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".silly") and (not args or any(a in f for a in args)):
                for opt in (opts if kind != "fail" else ["release"]):
                    jobs.append((fn, os.path.join(d, f), opt))
    if not args or "pkg" in args:
        jobs.append((pkg_case, os.path.join(ROOT, "tests", "pkg_test.py"), "release"))
    if not args or "selfhost" in args:
        jobs.append((selfhost_case, os.path.join(ROOT, "tests", "selfhost_test.py"), "release"))
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        results = list(ex.map(lambda j: (j[2],) + j[0](j[1], j[2]), jobs))
    failed = 0
    for opt, name, err in results:
        if err:
            failed += 1
            print(f"FAIL {name} [{opt}]\n    " + err.replace("\n", "\n    "))
    print(f"{len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
