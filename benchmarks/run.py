#!/usr/bin/env python3
"""Build every benchmark in Silly, C++ and Rust, check the outputs agree, then
report best-of-N wall time and peak resident memory.

    python3 benchmarks/run.py                # all benchmarks, 5 runs each
    python3 benchmarks/run.py -n 3 trees     # just one, 3 runs
    python3 benchmarks/run.py --markdown     # print a markdown table

Peak memory is ru_maxrss from wait4(), so it includes each runtime's baseline
(libc, libstdc++, Rust's std) and not just the workload.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join("/tmp", "silly-bench")

# name -> argument. Sizes chosen so each run takes a fraction of a second to a few seconds.
BENCHES = {
    "nbody": "5000000",
    "trees": "18",
    "wordfreq": "2000000",
    "collatz": "1000000",
    "strings": "2000000",
    "sieve": "50000000",
}
# Extra variants that aren't idiomatic but show what a hand-written arena does.
VARIANTS = {"trees": ["cpp/trees_arena.cpp", "rust/trees_arena.rs"]}


def build(src, exe, opt):
    if src.endswith(".silly"):
        cmd = [sys.executable, "-m", "silly", "build", "--opt", opt, src, "-o", exe]
    elif src.endswith(".cpp"):
        cmd = ["g++", "-O2", "-std=c++20", src, "-o", exe]
        if opt == "fast":
            cmd[1:2] = ["-O3", "-march=native"]
    else:
        cmd = ["rustc", "-C", "opt-level=3", src, "-o", exe]
        if opt == "fast":
            cmd += ["-C", "target-cpu=native"]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"build failed: {' '.join(cmd)}\n{r.stderr}")


MEMTIME = os.path.join(OUT, "memtime")


def run_once(exe, arg):
    # Timed and measured by memtime: a process's peak RSS survives exec, so a child
    # forked straight from Python would report Python's own footprint as its floor.
    r = subprocess.run([MEMTIME, exe, arg], capture_output=True)
    if r.returncode != 0:
        sys.exit(f"{exe} {arg} exited with {r.returncode}")
    dt, rss = r.stderr.decode().split()[-2:]
    return float(dt), int(rss), r.stdout  # ru_maxrss is KiB on Linux


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("benches", nargs="*", default=list(BENCHES))
    ap.add_argument("-n", "--runs", type=int, default=5)
    ap.add_argument("--opt", choices=["release", "fast"], default="release",
                    help="release: Silly -O2 / g++ -O2 / rustc opt-level=3; fast adds -O3 -march=native")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()
    for t in ("g++", "rustc", "gcc"):
        if not shutil.which(t):
            sys.exit(f"{t} not found")
    os.makedirs(OUT, exist_ok=True)
    subprocess.run(["gcc", "-O2", os.path.join(HERE, "memtime.c"), "-o", MEMTIME], check=True)

    rows = []
    for name in args.benches:
        arg = BENCHES[name]
        srcs = [f"silly/{name}.silly", f"cpp/{name}.cpp", f"rust/{name}.rs"] + VARIANTS.get(name, [])
        results = []
        for rel in srcs:
            src = os.path.join(HERE, rel)
            label = {"silly": "Silly", "cpp": "C++", "rust": "Rust"}[rel.split("/")[0]]
            stem = os.path.splitext(os.path.basename(rel))[0]
            if stem != name:
                label += " (" + stem[len(name) + 1:] + ")"
            exe = os.path.join(OUT, f"{stem}-{rel.split('/')[0]}")
            build(src, exe, args.opt)
            best, mem, out = None, 0, None
            for _ in range(args.runs):
                dt, rss, o = run_once(exe, arg)
                best = dt if best is None else min(best, dt)
                mem = max(mem, rss)
                if out is not None and o != out:
                    sys.exit(f"{label} {name}: output changed between runs")
                out = o
            results.append((label, best, mem, out))
            print(f"  {name:9} {label:16} {best * 1000:9.1f} ms {mem / 1024:8.1f} MiB", file=sys.stderr)
        ref = results[0][3]
        for label, _, _, out in results[1:]:
            if out != ref:
                sys.exit(f"{name}: {label} output differs from Silly\n{out!r}\nvs\n{ref!r}")
        rows.append((name, arg, results))

    if args.markdown:
        print("| benchmark | language | time (ms) | peak RSS (MiB) |")
        print("|---|---|---:|---:|")
        for name, arg, results in rows:
            for label, best, mem, _ in results:
                print(f"| {name} {arg} | {label} | {best * 1000:.1f} | {mem / 1024:.1f} |")
    else:
        print(f"\n{'benchmark':12} {'language':16} {'time':>10} {'peak RSS':>10}")
        for name, arg, results in rows:
            for label, best, mem, _ in results:
                print(f"{name:12} {label:16} {best * 1000:8.1f}ms {mem / 1024:7.1f}MiB")
    print("\nall outputs match", file=sys.stderr)


if __name__ == "__main__":
    main()
