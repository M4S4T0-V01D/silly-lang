"""Command-line driver: silly run | build | check | emit-c | test."""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys

from . import pkg
from .checker import check_program
from .codegen import CodeGen
from .errors import SillyError
from .program import Program

VERSION = "0.1.0"
CFLAGS = ["-std=gnu11", "-fwrapv", "-fno-strict-aliasing", "-fno-math-errno", "-w"]
OPT = {"debug": ["-O0", "-g", "-DSL_POISON"], "release": ["-O2"], "fast": ["-O3", "-march=native"]}


def find_cc():
    cc = os.environ.get("SILLY_CC") or os.environ.get("CC")
    if cc:
        return cc
    for name in ("gcc", "clang", "cc"):
        if shutil.which(name):
            return name
    raise SillyError("no C compiler found; install gcc or clang, or set SILLY_CC")


def load_program(path):
    return Program(path, packages=pkg.package_paths(path))


def compile_to_c(path, test_mode=False):
    prog = load_program(path)
    try:
        main, tests = check_program(prog, want_main=not test_mode)
        if test_mode and not tests:
            raise SillyError(f"no @test functions in {path}")
        return CodeGen(prog).generate(main, tests, test_mode=test_mode)
    except SillyError as e:
        e.sources = prog.sources
        raise


def cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    d = os.path.join(base, "silly")
    os.makedirs(d, exist_ok=True)
    return d


def build_c(csrc, out, opt="release", extra=()):
    cc = find_cc()
    cpath = out + ".c"
    with open(cpath, "w", encoding="utf-8") as f:
        f.write(csrc)
    link = []
    if csrc.startswith("/* silly-link: "):
        link = csrc[15:csrc.index(" */")].split()
    cmd = [cc] + CFLAGS + OPT[opt] + [cpath, "-o", out, "-lm", "-pthread"] + link + list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-4000:])
        if "/* ---- native: " in csrc:
            raise SillyError(f"the C compiler failed on {cpath}; check the program's native (extern \"*.c\") sources")
        raise SillyError(f"the C compiler failed on generated code ({cpath}); this is a bug in the Silly compiler")
    return out


def cached_binary(path, opt, test_mode=False):
    csrc = compile_to_c(path, test_mode)
    key = hashlib.sha256((csrc + opt + " ".join(CFLAGS)).encode()).hexdigest()[:20]
    out = os.path.join(cache_dir(), key)
    if not os.path.exists(out):
        tmp = out + f".tmp{os.getpid()}"
        build_c(csrc, tmp, opt)
        os.replace(tmp, out)
        os.replace(tmp + ".c", out + ".c")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="silly", description="The Silly programming language")
    ap.add_argument("--version", action="version", version=f"silly {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("file", nargs="?", help="source file (default: the package entry point)")
        return p

    p = add("run", "compile and run a program")
    p.add_argument("--opt", choices=OPT, default="release")
    p.add_argument("args", nargs=argparse.REMAINDER)
    p = add("build", "compile a program to a native executable")
    p.add_argument("-o", "--output")
    p.add_argument("--opt", choices=OPT, default="release")
    add("check", "type-check a program without compiling it")
    p = add("emit-c", "print the generated C code")
    p.add_argument("--test", action="store_true", help="emit the test harness instead of main()")
    p = add("test", "run the @test functions in a file")
    p.add_argument("filter", nargs="?")
    p.add_argument("--opt", choices=OPT, default="debug")
    p = sub.add_parser("new", help="create a new package")
    p.add_argument("path")
    p.add_argument("--lib", action="store_true", help="a library (src/lib.silly) instead of a program")
    p = sub.add_parser("add", help="add a dependency to silly.toml")
    p.add_argument("name")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--path", help="a package directory on this machine")
    src.add_argument("--git", help="a git repository URL")
    p.add_argument("--rev", help="git commit, tag or branch (default: the remote's default branch)")
    p = sub.add_parser("remove", help="remove a dependency from silly.toml")
    p.add_argument("name")
    sub.add_parser("fetch", help="download dependencies and write silly.lock")
    sub.add_parser("update", help="move git dependencies to their newest allowed commit")
    a = ap.parse_args(argv)

    try:
        if a.cmd in ("new", "add", "remove", "fetch", "update"):
            return package_cmd(a)
        if a.cmd == "run" and a.file and not a.file.endswith(".silly") and pkg.find_root(os.getcwd()):
            a.args.insert(0, a.file)    # `silly run x y` in a package: x and y are program arguments
            a.file = None
        if a.file is None:
            a.file = default_file(a.cmd)
            if a.file is None:
                return run_package_tests(a.opt, a.filter)
        if a.cmd == "check":
            prog = load_program(a.file)
            try:
                check_program(prog, want_main=False)
            except SillyError as e:
                e.sources = prog.sources
                raise
            print(f"{a.file}: ok")
            return 0
        if a.cmd == "emit-c":
            sys.stdout.write(compile_to_c(a.file, a.test))
            return 0
        if a.cmd == "build":
            out = a.output or package_binary_name(a.file)
            build_c(compile_to_c(a.file), os.path.abspath(out), a.opt)
            os.remove(os.path.abspath(out) + ".c")
            return 0
        if a.cmd == "run":
            exe = cached_binary(a.file, a.opt)
            sys.stdout.flush()
            os.execv(exe, [a.file] + a.args)
        if a.cmd == "test":
            exe = cached_binary(a.file, a.opt, test_mode=True)
            return subprocess.call([exe] + ([a.filter] if a.filter else []))
    except SillyError as e:
        sys.stderr.write(e.render(getattr(e, "sources", {})) + "\n")
        return 1
    return 0


def require_root():
    root = pkg.find_root(os.getcwd())
    if root is None:
        raise SillyError(f"no {pkg.MANIFEST} in this directory or any parent",
                         hint="run `silly new NAME` to create a package, or pass a file")
    return root


def default_file(cmd):
    """The file a command works on when none is given: the package entry point.

    `silly test` with no file returns None: it runs every test file in the package.
    """
    root = require_root()
    if cmd == "test":
        return None
    m = pkg.load_manifest(root)
    if not os.path.exists(m.entry):
        lib = os.path.join(m.src, "lib.silly")
        if cmd in ("check", "emit-c") and os.path.exists(lib):
            return lib
        raise SillyError(f"package '{m.name}' has no entry point {os.path.relpath(m.entry)}",
                         hint="a library package can be checked and tested, not run")
    return m.entry


def package_binary_name(path):
    root = pkg.find_root(path)
    if root is not None and os.path.abspath(path) == pkg.load_manifest(root).entry:
        return pkg.load_manifest(root).name
    return os.path.splitext(os.path.basename(path))[0]


def run_package_tests(opt, filter_):
    root = require_root()
    files = pkg.test_files(root)
    if not files:
        raise SillyError(f"no @test functions under {os.path.relpath(root)}/src or tests/")
    failed = 0
    for f in files:
        print(f"== {os.path.relpath(f)}")
        sys.stdout.flush()
        exe = cached_binary(f, opt, test_mode=True)
        if subprocess.call([exe] + ([filter_] if filter_ else [])) != 0:
            failed += 1
    if failed:
        print(f"{failed} of {len(files)} test files failed")
    return 1 if failed else 0


def package_cmd(a):
    if a.cmd == "new":
        name = pkg.new_package(a.path, a.lib)
        print(f"created {'library' if a.lib else 'program'} package '{name}' in {a.path}")
        return 0
    root = require_root()
    if a.cmd == "add":
        if a.rev and not a.git:
            raise SillyError("--rev only applies to --git dependencies")
        if a.path:
            spec = {"path": os.path.relpath(os.path.abspath(a.path), root)}
        else:
            spec = {"git": a.git}
            if a.rev:
                spec["rev"] = a.rev
        before = open(os.path.join(root, pkg.MANIFEST), encoding="utf-8").read()
        pkg.set_dependency(root, a.name, spec)
        try:
            pkg.resolve(root)
        except SillyError:
            with open(os.path.join(root, pkg.MANIFEST), "w", encoding="utf-8") as f:
                f.write(before)   # leave the manifest as it was if the new dependency is unusable
            raise
        print(f"added {a.name}")
        return 0
    if a.cmd == "remove":
        pkg.remove_dependency(root, a.name)
        pkg.resolve(root, quiet=True)
        print(f"removed {a.name}")
        return 0
    top, deps = pkg.resolve(root, update=(a.cmd == "update"))
    for name in sorted(deps):
        r = deps[name]
        print(f"  {name} {r.version} ({r.source}{' @ ' + r.rev[:12] if r.rev else ''})")
    print(f"{top.name}: {len(deps)} dependenc{'y' if len(deps) == 1 else 'ies'} ready")
    return 0
