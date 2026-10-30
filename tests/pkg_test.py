#!/usr/bin/env python3
"""Package manager tests: silly new/add/remove/fetch/update, silly.lock, imports from packages.

Builds throwaway packages and local git repositories in a temp directory and drives
the real `silly` command.  Prints nothing and exits 0 on success; otherwise prints
the first failed check.
"""

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SILLY = os.path.join(ROOT, "bin", "silly")
GIT = ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", "-c", "init.defaultBranch=main"]


def sh(cmd, cwd, ok=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    if ok and r.returncode != 0:
        raise AssertionError(f"`{' '.join(cmd)}` in {cwd} failed:\n{r.stdout}{r.stderr}")
    return r


def silly(cwd, *args, ok=True):
    return sh([SILLY, *args], cwd, ok)


def expect_error(cwd, text, *args):
    r = silly(cwd, *args, ok=False)
    assert r.returncode != 0, f"silly {' '.join(args)} should fail"
    assert text in r.stderr, f"silly {' '.join(args)}: expected {text!r} in:\n{r.stderr}"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def commit(repo, msg, tag=None):
    if not os.path.isdir(os.path.join(repo, ".git")):
        sh(GIT + ["init", "-q"], repo)
    sh(GIT + ["add", "-A"], repo)
    sh(GIT + ["commit", "-qm", msg], repo)
    if tag:
        sh(GIT + ["tag", "-f", tag], repo)
    return sh(GIT + ["rev-parse", "HEAD"], repo).stdout.strip()


def run(tmp):
    # A library with a test, used through a path dependency.
    silly(tmp, "new", "geom", "--lib")
    geom = os.path.join(tmp, "geom")
    write(f"{geom}/src/lib.silly", "import geom.shapes\n\nfn area(s: shapes.Rect) -> int:\n    return s.w * s.h\n")
    write(f"{geom}/src/shapes.silly", "struct Rect:\n    w: int\n    h: int\n")
    write(f"{geom}/tests/lib_test.silly",
          "import geom\nimport geom.shapes\n\n@test\nfn area():\n    assert geom.area(shapes.Rect(2, 3)) == 6\n")
    out = silly(geom, "test").stdout
    assert "1 passed" in out, out
    expect_error(geom, "has no entry point", "run")

    # A library in git that itself depends on another git library.
    silly(tmp, "new", "util", "--lib")
    util = os.path.join(tmp, "util")
    write(f"{util}/src/lib.silly", 'fn shout(s: str) -> str:\n    return s.upper() + "!"\n')
    u1 = commit(util, "one")
    silly(tmp, "new", "greet", "--lib")
    greet = os.path.join(tmp, "greet")
    write(f"{greet}/src/lib.silly", 'import util\n\nfn hello(n: str) -> str:\n    return util.shout(f"hello {n}")\n')
    silly(greet, "add", "util", "--git", "file://" + util)
    g1 = commit(greet, "one", tag="v1")

    # The application.
    silly(tmp, "new", "app")
    app = os.path.join(tmp, "app")
    with open(f"{app}/silly.toml", "a", encoding="utf-8") as f:
        f.write("# my deps\n")
    silly(app, "add", "geom", "--path", "../geom")
    silly(app, "add", "greet", "--git", "file://" + greet, "--rev", "v1")
    toml = read(f"{app}/silly.toml")
    assert "# my deps" in toml and 'geom = { path = "../geom" }' in toml, toml
    write(f"{app}/src/main.silly",
          "import geom\nimport geom.shapes\nfrom greet import hello\n\nfn main():\n"
          "    print(geom.area(shapes.Rect(4, 5)), hello(\"you\"))\n")
    out = silly(app, "run").stdout
    assert out == "20 HELLO YOU!\n", out
    lock = read(f"{app}/silly.lock")
    assert f'rev = "{u1}"' in lock and f'rev = "{g1}"' in lock and 'source = "path+../geom"' in lock, lock

    # silly build names the binary after the package.
    silly(app, "build")
    assert sh([os.path.join(app, "app")], app).stdout == "20 HELLO YOU!\n"

    # New upstream commits: the lockfile keeps builds on the old ones until `silly update`.
    write(f"{util}/src/lib.silly", 'fn shout(s: str) -> str:\n    return s.upper() + "!!"\n')
    u2 = commit(util, "two")
    silly(app, "fetch")
    assert silly(app, "run").stdout == "20 HELLO YOU!\n"
    silly(app, "update")
    assert silly(app, "run").stdout == "20 HELLO YOU!!\n"
    assert f'rev = "{u2}"' in read(f"{app}/silly.lock")
    assert f'rev = "{g1}"' in read(f"{app}/silly.lock")   # still pinned to tag v1

    # Running a single file inside the package still sees the dependencies.
    write(f"{app}/src/extra.silly", "from greet import hello\n\nfn main():\n    print(hello(\"x\"))\n")
    assert silly(tmp, "run", "app/src/extra.silly").stdout == "HELLO X!!\n"

    # Errors.
    expect_error(app, "required from two different sources", "add", "util", "--path", "../util")
    assert "util" not in read(f"{app}/silly.toml").split("[dependencies]")[1].replace("file://", "")
    expect_error(app, "has no silly.toml", "add", "nothing", "--path", "../nowhere")
    expect_error(app, "is not a valid package name", "add", "Bad-Name", "--path", "../geom")
    expect_error(app, "cannot depend on itself", "add", "app", "--path", ".")
    expect_error(app, "is a package named 'geom'", "add", "shapes", "--path", "../geom")
    expect_error(app, "is not a dependency", "remove", "nothing")
    expect_error(tmp, "no silly.toml", "fetch")
    write(f"{greet}/silly.toml", read(f"{greet}/silly.toml") + 'geom = { path = "../geom" }\n')
    commit(greet, "escape", tag="v2")
    expect_error(app, "outside its repository", "add", "greet", "--git", "file://" + greet, "--rev", "v2")
    assert 'rev = "v1"' in read(f"{app}/silly.toml")   # the failed add left the manifest alone

    # Removing a dependency drops it from the lockfile; imports of it then fail.
    silly(app, "remove", "greet")
    lock = read(f"{app}/silly.lock")
    assert "greet" not in lock and "util" not in lock, lock
    expect_error(app, "module 'greet' not found", "check")


def main():
    with tempfile.TemporaryDirectory(prefix="silly-pkg-") as tmp:
        try:
            run(os.path.realpath(tmp))
        except AssertionError as e:
            print(str(e)[-2000:])
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
