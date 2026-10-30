#!/usr/bin/env python3
"""Builds the Silly website from docs/ into website/_site.

    pip install markdown pygments
    python3 website/build.py            # then open website/_site/index.html

Every page in docs/ becomes an HTML page at the same relative path (README.md
becomes index.html). Links between docs pages are rewritten to .html; links to
anything else in the repository point at GitHub.
"""
import html
import json
import os
import posixpath
import re
import shutil
import sys
from pathlib import Path

import markdown
import markdown.extensions.codehilite as codehilite
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexer import RegexLexer, bygroups, words
from pygments.lexers import get_lexer_by_name
from pygments.token import (Comment, Keyword, Name, Number, Operator,
                            Punctuation, String, Whitespace)

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE_SRC = ROOT / "website"
OUT = SITE_SRC / "_site"
REPO = "https://github.com/M4S4T0-V01D/silly-lang"
BLOB = REPO + "/blob/main/"

GUIDE = [("guide/getting-started.md", "Getting started"),
         ("guide/tour.md", "A tour of Silly"),
         ("guide/gui.md", "Building a GUI")]
REFERENCE = [("spec.md", "Language reference"),
             ("memory-model.md", "Memory model"),
             ("std/README.md", "Standard library")]
STD_GROUPS = [
    ("Text", "string re textwrap difflib json csv html base64 url"),
    ("Numbers", "math random statistics bisect heapq"),
    ("Data", "collections itertools binary hashlib uuid"),
    ("Time", "time datetime"),
    ("System", "sys os path glob shutil tempfile subprocess argparse logging"),
    ("Network", "socket http"),
    ("Graphics", "gfx ui"),
    ("Testing", "testing"),
]


class SillyLexer(RegexLexer):
    name = "Silly"
    aliases = ["silly"]
    filenames = ["*.silly"]

    tokens = {
        "root": [
            (r"\s+", Whitespace),
            (r"#.*$", Comment.Single),
            (r"@\w+", Name.Decorator),
            (r'(f)(")', bygroups(String.Affix, String.Double), "fstring"),
            (r'"', String.Double, "string"),
            (r"'(\\.|[^'\\])'", String.Char),
            (r"(fn)(\s+)([A-Za-z_]\w*)", bygroups(Keyword, Whitespace, Name.Function)),
            (r"(struct|enum|trait)(\s+)([A-Za-z_]\w*)", bygroups(Keyword, Whitespace, Name.Class)),
            (words(("fn", "let", "var", "const", "struct", "enum", "match", "case", "if",
                    "elif", "else", "while", "for", "in", "loop", "break", "continue",
                    "return", "and", "or", "not", "as", "import", "from", "pass", "mut",
                    "extern", "is", "trait", "impl", "link"), suffix=r"\b"), Keyword),
            (words(("true", "false", "None", "self"), suffix=r"\b"), Keyword.Constant),
            (words(("int", "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64",
                    "bool", "char", "str", "list", "map", "Option", "Result", "Task"),
                   suffix=r"\b"), Keyword.Type),
            (words(("Some", "Ok", "Err"), suffix=r"\b"), Name.Builtin),
            (words(("print", "len", "sum", "min", "max", "abs", "range", "enumerate", "zip",
                    "spawn", "join_all", "cpu_count", "assert", "panic", "sorted", "reversed"),
                   suffix=r"\b"), Name.Builtin),
            (r"[A-Z]\w*", Name.Class),
            (r"0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+", Number.Integer),
            (r"\d[\d_]*\.\d[\d_]*([eE][+-]?\d+)?|\d[\d_]*[eE][+-]?\d+", Number.Float),
            (r"\d[\d_]*", Number.Integer),
            (r"[A-Za-z_]\w*", Name),
            (r"\.\.=|\.\.|->|=>|\*\*|//|[-+*/%&|^~<>=!]=?", Operator),
            (r"[()\[\]{}:,.;?]", Punctuation),
        ],
        "string": [
            (r'\\.', String.Escape),
            (r'"', String.Double, "#pop"),
            (r'[^"\\]+', String.Double),
        ],
        "fstring": [
            (r'\\.', String.Escape),
            (r"\{\{|\}\}", String.Double),
            (r"\{[^{}]*\}", String.Interpol),
            (r'"', String.Double, "#pop"),
            (r'[^"\\{}]+', String.Double),
        ],
    }


def lexer_by_name(name, **opts):
    if name in ("silly", ""):
        return SillyLexer(**opts)
    return get_lexer_by_name(name, **opts)


codehilite.get_lexer_by_name = lexer_by_name


def slug(text, sep="-"):
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s-]+", sep, text)


def md():
    return markdown.Markdown(extensions=[
        "tables", "fenced_code", "toc", "codehilite", "attr_list", "sane_lists"],
        extension_configs={
            "codehilite": {"css_class": "hl", "guess_lang": False},
            "toc": {"slugify": slug, "toc_depth": "2-3"},
        })


def out_path(src):
    """docs-relative .md path -> site-relative .html path."""
    p = src[:-3] + ".html"
    if p.endswith("README.html"):
        p = p[:-len("README.html")] + "index.html"
    return p


def rewrite_links(body, src):
    """Points relative links at the right page: .md -> .html inside docs, GitHub outside."""
    here = posixpath.dirname(src)
    page_dir = posixpath.dirname(out_path(src))

    def fix(m):
        attr, url = m.group(1), html.unescape(m.group(2))
        if re.match(r"[a-z]+:|#|/", url):
            return m.group(0)
        path, _, frag = url.partition("#")
        target = posixpath.normpath(posixpath.join("docs", here, path))
        if target.startswith("docs/") and target.endswith(".md"):
            rel = posixpath.relpath(out_path(target[5:]), page_dir or ".")
            new = rel + ("#" + frag if frag else "")
        elif target.startswith("docs/") and (DOCS / target[5:]).is_file():
            new = url
        else:
            kind = "tree/main/" if (ROOT / target).is_dir() else "blob/main/"
            new = REPO + "/" + kind + target + ("#" + frag if frag else "")
        return f'{attr}="{html.escape(new)}"'

    return re.sub(r'(href|src)="([^"]*)"', fix, body)


def nav_html(current, root):
    def link(src, title):
        cls = ' class="active"' if src == current else ""
        return f'<li><a href="{root}{out_path(src)}"{cls}>{html.escape(title)}</a></li>'

    parts = ['<nav class="sidebar" id="sidebar">']
    parts.append("<h4>Guide</h4><ul>" + "".join(link(s, t) for s, t in GUIDE) + "</ul>")
    parts.append("<h4>Reference</h4><ul>" + "".join(link(s, t) for s, t in REFERENCE) + "</ul>")
    for group, mods in STD_GROUPS:
        items = "".join(link(f"std/{m}.md", m) for m in mods.split())
        parts.append(f'<h4>{group}</h4><ul class="mods">{items}</ul>')
    parts.append("</nav>")
    return "".join(parts)


def page_toc(toc_tokens):
    items = []
    for t in toc_tokens:
        for h in ([t] if t["level"] == 2 else []):
            items.append(f'<li><a href="#{h["id"]}">{h["name"]}</a></li>')
    if len(items) < 2:
        return ""
    return '<aside class="toc"><h4>On this page</h4><ul>' + "".join(items) + "</ul></aside>"


def search_entries(body, title, url):
    """One entry per heading: the heading, its anchor, and the text under it."""
    entries = []
    chunks = re.split(r'(<h[1-3][^>]*id="[^"]*"[^>]*>.*?</h[1-3]>)', body, flags=re.S)
    head, anchor = title, ""
    for chunk in chunks:
        m = re.match(r'<h([1-3])[^>]*id="([^"]*)"[^>]*>(.*?)</h\1>', chunk, re.S)
        if m:
            head, anchor = html.unescape(re.sub(r"<[^>]+>", "", m.group(3))), m.group(2)
            continue
        text = html.unescape(re.sub(r"<[^>]+>", " ", chunk))
        text = re.sub(r"\s+", " ", text).strip()
        if text or anchor:
            entries.append({"p": title, "h": head, "u": url + ("#" + anchor if anchor else ""),
                            "x": text[:400]})
    return entries


def render(template, **vals):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: vals[m.group(1)], template)


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    template = (SITE_SRC / "template.html").read_text()
    index = []
    sources = [p.relative_to(DOCS).as_posix() for p in sorted(DOCS.rglob("*.md"))]
    sources = [s for s in sources if not s.startswith("licenses/")]
    for src in sources:
        conv = md()
        text = re.sub(r"^```text$", "```{.text .output}", (DOCS / src).read_text(), flags=re.M)
        body = conv.convert(text)
        m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))) if m else src
        body = rewrite_links(body, src)
        dest = out_path(src)
        root = "../" * dest.count("/")
        edit = BLOB + "docs/" + src
        if src.startswith("std/") and src != "std/README.md":
            edit = BLOB + "silly/std/" + Path(src).stem + ".silly"
        page = render(template, title=html.escape(title), root=root,
                      nav=nav_html(src, root), body=body, toc=page_toc(conv.toc_tokens),
                      edit=edit, repo=REPO)
        (OUT / dest).parent.mkdir(parents=True, exist_ok=True)
        (OUT / dest).write_text(page)
        index += search_entries(body, title, dest)

    landing = (SITE_SRC / "index.html").read_text()
    hl = HtmlFormatter(cssclass="hl")
    landing = re.sub(r"<pre data-silly>\n?(.*?)</pre>",
                     lambda m: highlight(html.unescape(m.group(1)), SillyLexer(), hl),
                     landing, flags=re.S)
    (OUT / "index.html").write_text(render(landing, repo=REPO, root=""))

    (OUT / "search.json").write_text(json.dumps(index, separators=(",", ":")))
    (OUT / "hl.css").write_text(HtmlFormatter(style="github-dark").get_style_defs(".hl"))
    for name in ("style.css", "site.js"):
        shutil.copy(SITE_SRC / name, OUT / name)
    shutil.copytree(DOCS / "guide" / "img", OUT / "guide" / "img")
    shutil.copy(ROOT / "assets" / "logo.svg", OUT / "logo.svg")
    shutil.copy(ROOT / "assets" / "favicon.png", OUT / "favicon.png")
    (OUT / ".nojekyll").write_text("")
    print(f"built {len(sources) + 1} pages, {len(index)} search entries into {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    os.chdir(ROOT)
    build()
    sys.exit(0)
