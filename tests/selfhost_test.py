#!/usr/bin/env python3
"""The self-hosted compiler, end to end.

1. The reference compiler builds selfhost/sillyc.silly (stage 1).
2. Stage 1 compiles sillyc.silly to C, which gcc builds (stage 2).
3. Stage 2 compiles sillyc.silly again; its C must equal stage 1's byte for byte.
4. Stage 2 compiles every tests/run program. Programs outside Silly Core must be
   rejected with a "not part of Silly Core" error; the rest must build, print their
   `#> ` lines, exit with their `#! exit` status and match their `#! stderr` text.
   tests/run/core_*.silly must all be inside Silly Core.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from run_tests import expectations  # noqa: E402

SELF = os.path.join(ROOT, "selfhost")
OUT = os.path.join(ROOT, "tests", ".build", "selfhost")
CC = ["gcc", "-O2", "-fwrapv", "-w", "-I", SELF]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300, **kw)


def die(msg):
    print("FAIL selfhost: " + msg)
    sys.exit(1)


def gcc(c_file, exe):
    r = run(CC + [c_file, "-o", exe])
    if r.returncode != 0:
        die(f"gcc rejected {c_file}:\n{r.stderr[-1500:]}")


def sillyc(exe, src, c_file):
    return run([exe, src, c_file])


def main():
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(SELF, "sillyc.silly")
    stage1 = os.path.join(OUT, "sillyc1")
    stage2 = os.path.join(OUT, "sillyc2")
    r = run([os.path.join(ROOT, "bin", "silly"), "build", src, "-o", stage1])
    if r.returncode != 0:
        die("the reference compiler rejected sillyc.silly:\n" + (r.stdout + r.stderr)[-1500:])
    c2, c3 = os.path.join(OUT, "stage2.c"), os.path.join(OUT, "stage3.c")
    r = sillyc(stage1, src, c2)
    if r.returncode != 0:
        die("stage 1 could not compile sillyc.silly:\n" + r.stderr[-1500:])
    gcc(c2, stage2)
    r = sillyc(stage2, src, c3)
    if r.returncode != 0:
        die("stage 2 could not compile sillyc.silly:\n" + r.stderr[-1500:])
    with open(c2, "rb") as a, open(c3, "rb") as b:
        if a.read() != b.read():
            die(f"no fixpoint: {c2} and {c3} differ")

    run_dir = os.path.join(ROOT, "tests", "run")
    failed, ran, skipped = [], 0, 0
    for f in sorted(os.listdir(run_dir)):
        if not f.endswith(".silly"):
            continue
        path = os.path.join(run_dir, f)
        base = os.path.join(OUT, f[:-6])
        r = sillyc(stage2, path, base + ".c")
        if r.returncode != 0:
            if "not part of Silly Core" in r.stderr and not f.startswith("core_"):
                skipped += 1
            else:
                failed.append(f"{f}: sillyc: {r.stderr.strip()[-500:]}")
            continue
        b = run(CC + [base + ".c", "-o", base])
        if b.returncode != 0:
            failed.append(f"{f}: gcc: {b.stderr.strip()[-800:]}")
            continue
        want, code, stderr = expectations(path)
        p = run([base])
        got = p.stdout.split("\n")
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
        if p.returncode != code:
            problems.append(f"exit status {p.returncode}, expected {code}")
        for s in stderr:
            if s not in p.stderr:
                problems.append(f"stderr lacks {s!r}: {p.stderr.strip()[-300:]}")
        if problems:
            failed.append(f"{f}: " + "; ".join(problems))
        ran += 1
    for msg in failed:
        print("FAIL selfhost " + msg)
    print(f"selfhost: fixpoint ok, {ran} programs run, {skipped} outside Silly Core, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
