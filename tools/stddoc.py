#!/usr/bin/env python3
"""Writes docs/std/<module>.md for each standard-library module, and an index.

The pages come from the modules' own comments: the header comment at the top of
the file becomes the introduction (lines indented four spaces are code), and
each public const, struct, enum and fn is listed with the comment just above
it. Names starting with "_" are left out, and so are the extern fns of modules
with C of their own (math's externs are libc's, so they are listed).

    python3 tools/stddoc.py          # rewrite docs/std/
    python3 tools/stddoc.py --check  # exit 1 if docs/std/ is out of date
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STD = ROOT / "silly" / "std"
OUT = ROOT / "docs" / "std"

DECL = re.compile(r"^(?:extern )?(fn|struct|enum|const)\s+([A-Za-z]\w*)")
METHOD = re.compile(r"^    fn\s+([A-Za-z]\w*)")
FIELD = re.compile(r"^    ([a-z]\w*):\s*(.+?)\s*(?:#\s*(.*))?$")
VARIANT = re.compile(r"^    ([A-Z]\w*(?:\(.*\))?)\s*(?:#\s*(.*))?$")


def header(lines):
    """The leading comment block as markdown, and the line after it."""
    out, code, i = [], False, 0
    while i < len(lines) and lines[i].startswith("#"):
        text = lines[i][2:] if lines[i].startswith("# ") else lines[i][1:]
        is_code = text.startswith("    ")
        if is_code and not code:
            if out and out[-1] != "":
                out.append("")
            out.append("```silly")
            code = True
        elif code and not is_code and text.strip() != "":
            while out[-1] == "":
                out.pop()
            out.append("```")
            out.append("")
            code = False
        out.append(text[4:] if code and is_code else ("" if code and not text.strip() else text))
        i += 1
    if code:
        while out and out[-1] == "":
            out.pop()
        out.append("```")
    return "\n".join(out).strip() + "\n", i


def comment_above(lines, i, indent):
    """The comment lines directly above line i, joined."""
    got = []
    j = i - 1
    prefix = " " * indent + "#"
    while j >= 0 and lines[j].startswith(prefix) and not lines[j].startswith(prefix + "!"):
        got.append(lines[j][len(prefix):].strip())
        j -= 1
    return " ".join(reversed(got)).strip()


def signature(line):
    sig = line.strip()
    if sig.startswith("extern "):
        sig = sig[len("extern "):]
    if sig.endswith(":"):
        sig = sig[:-1]
    return sig


def items(lines, start):
    """(kind, name, signature, doc, members) for each public declaration.
    extern fns count only in modules without C of their own (like math, whose
    externs are libc's functions); otherwise they are the module's internals."""
    native = any(l.startswith('extern "') for l in lines)
    out = []
    i = start
    while i < len(lines):
        line = lines[i]
        m = DECL.match(line)
        if not m or (line.startswith("extern") and native):
            i += 1
            continue
        kind, name = m.group(1), m.group(2)
        doc = comment_above(lines, i, 0)
        members = []
        j = i + 1
        if kind in ("struct", "enum"):
            while j < len(lines) and (lines[j].startswith(" ") or lines[j].strip() == ""):
                body = lines[j]
                mm = METHOD.match(body)
                if mm and not mm.group(1).startswith("_"):
                    members.append(("method", signature(body), comment_above(lines, j, 4)))
                elif kind == "struct" and FIELD.match(body) and not body.strip().startswith("fn"):
                    f = FIELD.match(body)
                    if not f.group(1).startswith("_"):
                        members.append(("field", f.group(1) + ": " + f.group(2), f.group(3) or ""))
                elif kind == "enum" and VARIANT.match(body):
                    v = VARIANT.match(body)
                    members.append(("variant", v.group(1), v.group(2) or ""))
                j += 1
        out.append((kind, name, signature(line), doc, members))
        i = j
    return out


def page(mod, text):
    lines = text.split("\n")
    intro, start = header(lines)
    intro = re.sub(r"^" + re.escape(mod) + r":\s*(.)", lambda m: m.group(1).upper(), intro)
    md = ["# " + mod, "", intro]
    decls = [d for d in items(lines, start) if not d[1].startswith("_")]
    sections = [("Constants", "const"), ("Types", "struct"), ("Types", "enum"), ("Functions", "fn")]
    done = set()
    for title, _ in sections:
        if title in done:
            continue
        kinds = [k for t, k in sections if t == title]
        group = [d for d in decls if d[0] in kinds]
        if not group:
            continue
        done.add(title)
        md.append("## " + title)
        md.append("")
        if title == "Constants":
            for _, _, sig, doc, _ in group:
                md.append("- `" + sig[len("const "):] + "`" + (" — " + doc if doc else ""))
            md.append("")
            continue
        for kind, name, sig, doc, members in group:
            md.append("### `" + (name if kind != "fn" else sig[3:]) + "`")
            md.append("")
            if kind != "fn" and sig != kind + " " + name:
                md.append("`" + sig + "`")
                md.append("")
            if doc:
                md.append(doc)
                md.append("")
            fields = [m for m in members if m[0] in ("field", "variant")]
            methods = [m for m in members if m[0] == "method"]
            for _, s, d in fields:
                md.append("- `" + s + "`" + (" — " + d if d else ""))
            if fields:
                md.append("")
            for _, s, d in methods:
                md.append("- `" + s[3:] + "`" + (" — " + d if d else ""))
            if methods:
                md.append("")
    return "\n".join(md).rstrip() + "\n"


def summary(text):
    """The header's first sentence, for the index."""
    lines = []
    for line in text.split("\n"):
        if not line.startswith("#"):
            break
        t = line[1:].strip()
        if t == "":
            break
        lines.append(t)
    s = " ".join(lines)
    s = re.sub(r"^\w+:\s*", "", s)
    end = s.find(". ")
    return s if end < 0 else s[: end + 1]


def build():
    pages = {}
    rows = []
    for f in sorted(STD.glob("*.silly")):
        mod = f.stem
        if mod == "prelude":
            continue
        text = f.read_text()
        pages[mod + ".md"] = page(mod, text)
        rows.append("| [`" + mod + "`](" + mod + ".md) | " + summary(text) + " |")
    index = [
        "# The standard library",
        "",
        "`import name` loads any of these. The pages are generated from the comments in",
        "`silly/std/*.silly` by `tools/stddoc.py`; edit the source, then rerun it.",
        "",
        "| Module | |",
        "|---|---|",
    ] + rows
    pages["README.md"] = "\n".join(index) + "\n"
    return pages


def main():
    pages = build()
    check = "--check" in sys.argv
    stale = []
    if not check:
        OUT.mkdir(parents=True, exist_ok=True)
    for name, text in pages.items():
        p = OUT / name
        if check:
            if not p.exists() or p.read_text() != text:
                stale.append(name)
        else:
            p.write_text(text)
    if check:
        for name in sorted(set(x.name for x in OUT.glob("*.md")) - set(pages)):
            stale.append(name + " (no module)")
        if stale:
            print("docs/std is out of date: " + ", ".join(stale))
            sys.exit(1)
        print("docs/std is up to date")
    else:
        print("wrote " + str(len(pages)) + " pages to docs/std/")


if __name__ == "__main__":
    main()
